"""
영어 원문(english_value)에 translate_keys.protect_tokens(파서 기반 마스킹)을 적용해
토큰 보호와 닫힘 없는 £ 정상화가 올바른지 검수한다(예전 TOKEN_RE 사본은 제거됨).

위키 기준: https://stellaris.paradoxwikis.com/Localisation_modding
  - £name£  : 아이콘 토큰 (앞뒤 £ 필수)
  - $name$  : 변수/키 참조 ($VALUE|*1$ 포맷팅, 공백 허용)
  - [scope.Cmd] : 스크립트 표현식
  - §X...§! : 색상코드 (공식 목록: W T g L P R S H K Y I G V E C B M c v d r l !)
  - \n \t \" \\ : 이스케이프 문자

API 호출 없음 — 순수 로컬 로직 테스트.

출력:
  - 토큰 타입별 매칭 통계
  - 마스킹 후 남은 미처리 토큰 패턴 (£, $...$, [...], 단독 §X)
  - 파일/키 단위 이상 목록

사용:
  python test_token_masking.py
  python test_token_masking.py --mod expanded_stellaris
  python test_token_masking.py -n 5
"""

import argparse
import collections
import csv
import glob
import os
import re
import sys

from token_parser import TOKEN_TYPES, extract_token_values
from tool_config import translation_keys_root
from translate_keys import protect_tokens, restore_protected_tokens


def get_auto_keys():
    return os.path.normpath(str(translation_keys_root()))


# 마스킹은 translate_keys.protect_tokens(파서 기반)를 그대로 쓴다. 과거에는 이 파일에
# TOKEN_RE 사본이 있어 실제 마스킹과 미묘하게 달랐다(닫힘 없는 £ 검출 범위 불일치).
# 토큰 통계도 token_parser.extract_token_values 한 곳을 기준으로 낸다.

# 마스킹 후 남아서는 안 되는 잔류 패턴
RESIDUAL_PATTERNS = {
    "unclosed_icon": re.compile(r"£[A-Za-z_][A-Za-z0-9_|]*"),  # £word (닫힘 없음)
    "bracket_expr": re.compile(r"\[[^\]\n]{3,}\]"),  # [...] 미마스킹
    # 공백 포함 달러 토큰: $Foo Bar$ 형태
    "dollar_with_space": re.compile(r"\$[A-Za-z_][A-Za-z0-9_ ]+\$"),
}


def mask(value: str) -> str:
    return protect_tokens(value)[0]


# 닫힘 없는 £ 아이콘이 번역 복원(protect→restore)에서 정상형 £x£로 교정되는지 회귀 케이스.
# closed icon / $...$ / [...] 은 원형 그대로 유지돼야 한다.
NORMALIZATION_CASES = [
    ("1000£energy and 1000£minerals .", "1000£energy£ and 1000£minerals£ ."),
    ("£dna £blocker£ Dense Jungle", "£dna£ £blocker£ Dense Jungle"),
    ("£pop£ §YPop§! [Root.GetName]", "£pop£ §YPop§! [Root.GetName]"),
    ("§Y$Fleet Capacity$§!", "§Y$Fleet Capacity$§!"),
]


def check_normalization() -> list[str]:
    """protect→restore에서 닫힘 없는 £가 £x£로 정상화되는지 확인하고 실패 목록을 반환."""
    fails: list[str] = []
    for text, expected in NORMALIZATION_CASES:
        masked, repl = protect_tokens(text)
        restored = restore_protected_tokens(masked, repl)
        if restored != expected:
            fails.append(f"{text!r} -> {restored!r} (기대 {expected!r})")
    return fails


# ── 스캔 ──────────────────────────────────────────────────────────────────────
def scan(auto_keys, mod_filter=None):
    stats = collections.Counter()  # token_type -> 총 매칭 수
    residual = collections.defaultdict(list)  # residual_type -> [(rel, key, ctx)]
    files_seen = 0

    for csv_path in sorted(glob.glob(auto_keys + "/**/*_key.csv", recursive=True)):
        rel = os.path.relpath(csv_path, auto_keys)
        mod = rel.split(os.sep)[0]
        if mod_filter and mod_filter not in mod:
            continue
        files_seen += 1

        with open(csv_path, encoding="utf-8-sig") as f:
            try:
                for row in csv.DictReader(f):
                    en = row.get("english_value", "")
                    if not en:
                        continue
                    key = row.get("key", "")

                    # 토큰 타입별 카운트 (파서 기준 — 마스킹과 동일한 토큰 정의)
                    for ttype, vals in extract_token_values(en).items():
                        stats[ttype] += len(vals)

                    # 마스킹 후 잔류 검사
                    masked = mask(en)
                    for rtype, rpat in RESIDUAL_PATTERNS.items():
                        for m in rpat.finditer(masked):
                            ctx = masked[max(0, m.start() - 15) : m.end() + 20].replace("\n", "\\n")
                            residual[rtype].append((rel, key, m.group(0), ctx))

            except Exception as e:
                print(f"ERROR {rel}: {e}", file=sys.stderr)

    return files_seen, stats, residual


# ── 출력 ──────────────────────────────────────────────────────────────────────
def print_stats(stats, files_seen):
    sys.stdout.buffer.write(
        f"\n=== 토큰 타입별 매칭 통계 (파일 {files_seen}개) ===\n".encode("utf-8")
    )
    for ttype in TOKEN_TYPES:
        cnt = stats.get(ttype, 0)
        if cnt:
            sys.stdout.buffer.write(f"  {ttype:<20}: {cnt:>6}건\n".encode("utf-8"))


def print_residual(residual, show_n):
    total = sum(len(v) for v in residual.values())
    sys.stdout.buffer.write(f"\n=== 마스킹 후 잔류 토큰 ({total}건) ===\n".encode("utf-8"))
    if not total:
        sys.stdout.buffer.write("  (없음 — 모든 토큰 정상 마스킹)\n".encode("utf-8"))
        return
    for rtype, items in residual.items():
        if not items:
            continue
        sys.stdout.buffer.write(f"\n  [{rtype}] {len(items)}건\n".encode("utf-8"))
        by_file = collections.defaultdict(list)
        for rel, key, token, ctx in items:
            by_file[rel].append((key, token, ctx))
        for rel, rows in sorted(by_file.items()):
            sys.stdout.buffer.write(f"    {rel} ({len(rows)}건)\n".encode("utf-8"))
            for key, token, ctx in rows[:show_n]:
                sys.stdout.buffer.write(
                    f"      {key[:42]} | {token} | ...{ctx}...\n".encode("utf-8")
                )
            if len(rows) > show_n:
                sys.stdout.buffer.write(f"      ... 외 {len(rows) - show_n}건\n".encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="토큰 마스킹 검수 (API 호출 없음)")
    parser.add_argument("--mod", help="특정 모드만 (부분 이름 매칭)")
    parser.add_argument("-n", type=int, default=3, help="파일당 예시 출력 수 (기본 3)")
    args = parser.parse_args()

    auto_keys = get_auto_keys()
    files_seen, stats, residual = scan(auto_keys, args.mod)
    print_stats(stats, files_seen)
    print_residual(residual, args.n)

    fails = check_normalization()
    passed = len(NORMALIZATION_CASES) - len(fails)
    sys.stdout.buffer.write(
        f"\n=== 닫힘 없는 £ 정상화 회귀 ({passed}/{len(NORMALIZATION_CASES)}) ===\n".encode("utf-8")
    )
    for f in fails:
        sys.stdout.buffer.write(f"  FAIL: {f}\n".encode("utf-8"))


if __name__ == "__main__":
    main()
