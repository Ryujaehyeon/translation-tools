"""
원본 영문(english_value)의 토큰 이상 패턴 진단 스크립트.

참조: https://stellaris.paradoxwikis.com/Localisation_modding
  - £name£  : 아이콘 토큰 (앞뒤 £ 필수)
  - $name$  : 변수/키 참조 ($VALUE|*1$ 포맷팅 포함, 공백 허용)
  - [scope.Cmd] : 스크립트 표현식
  - §X...§! : 색상코드 (공식 목록: W T g L P R S H K Y I G V E C B M c v d r l !)
  - \n \t \" : 이스케이프 문자

patch_english_tokens.py 적용 전/후 잔여 icon_unclosed를 확인하거나,
새 모드 추가 후 보정 필요 여부를 체크할 때 사용.

기본 출력: icon_unclosed 만 (보정 필요한 케이스)
--dollar 플래그: 달러 토큰 unusual도 추가 출력 (참고용, 대부분 의도적 패턴)
--color  플래그: 위키 미기재 §코드 출력 (참고용, 일부 모드 자체 확장)

달러 토큰 참고:
  $TRIGGER_FAIL$텍스트 — trigger 조건 텍스트 prefix (의도적)
  $prefix_key$텍스트   — 다른 키 내용 삽입 prefix (의도적)
  $base$suffix         — 단어 suffix 조합 (의도적)
  위 패턴들은 번역 파이프라인에 영향 없음. patch 대상 아님.

위키 미기재 §코드 (실제 사용 확인됨):
  §t — 들여쓰기/탭 효과 (gigastructural_engineering 등)
  §O — 오렌지 계열 (more_events_mod, unique_ascension_perks)
  §F — 미확인 (kurosections_expanded)
  §f — 미확인 (plentiful_traditions)
"""

import argparse
import collections
import csv
import glob
import os
import re
import sys

from tool_config import translation_keys_root


def get_auto_keys():
    return os.path.normpath(str(translation_keys_root()))


# ── 필터: 달러 토큰 의도적 패턴 ───────────────────────────────────────────
# Stellaris에서 닫힘 없는 $token이 정상인 케이스들
_DOLLAR_OK = [
    re.compile(r"\$TRIGGER_(?:FAIL|PASS)\$"),  # trigger 결과 prefix
    re.compile(r"\.[a-z_]+\$"),  # .generic$, .desc_1$ 등 suffix prefix
    re.compile(r"_(?:icon|col|prefix|proj|mega|kilo|line|pass|fail)\$"),  # 공통 prefix suffix
    re.compile(r"\$[a-z]\b"),  # $s $a $b 복수형
    re.compile(r'\$[A-Za-z_][A-Za-z0-9_.]*\$[sS](?=[\s"\'$]|$)'),  # $word$s 복수형
    re.compile(r"\$[A-Za-z_][A-Za-z0-9_.]*\|[A-Za-z]"),  # $word|Y 파이프 파라미터
    re.compile(r"\$\d+\$"),  # $1$ $2$ 위치 변수
    re.compile(r"\$t\$"),  # $t$ 탭
]


def _dollar_is_ok(context):
    return any(p.search(context) for p in _DOLLAR_OK)


# 정상 닫힌 £word£ 를 플레이스홀더로 치환해서 £A£B 오탐 방지
_CLOSED_ICON_RE = re.compile(r"£[A-Za-z_][A-Za-z0-9_|]*£")


def _strip_closed_icons(text):
    """정상 닫힌 £word£ 를 같은 길이의 X로 대체해 후속 검사에서 오탐 방지."""

    def repl(m):
        return "X" * len(m.group())

    return _CLOSED_ICON_RE.sub(repl, text)


# ── 아이콘 unclosed 판정 ──────────────────────────────────────────────────
def _find_unclosed_icons(en):
    """정상 닫힌 토큰을 제거한 뒤 남은 £word 를 찾아 반환."""
    stripped = _strip_closed_icons(en)
    results = []
    for m in re.finditer(r"£([A-Za-z_][A-Za-z0-9_|]*)", stripped):
        # 다음이 £이면 아직 닫힌 것 (strip이 못 잡은 중첩 케이스)
        if m.end() < len(stripped) and stripped[m.end()] == "£":
            continue
        remaining = stripped[m.end() :]
        if re.match(r"\s+§", remaining):
            continue  # 이슈5 — TOKEN_RE/patch 처리됨
        # 원본 텍스트에서 context 추출
        ctx = en[max(0, m.start() - 12) : m.end() + 20].replace("\n", "\\n")
        # 원본에서 실제 토큰 텍스트 (X로 치환됐을 수 있으므로 원본에서 직접 추출)
        orig_token = en[m.start() : m.end()]
        results.append((orig_token, ctx))
    return results


# ── 위키 기준 색상코드 검증 ────────────────────────────────────────────────
# 참조: https://stellaris.paradoxwikis.com/Localisation_modding
_WIKI_COLOR_CODES = set("WTgLPRSHKYIGVECBMcvdrl!")
# 실제 사용 확인된 비공식 코드 (모드 자체 확장, 번역 파이프라인에는 영향 없음)
_KNOWN_UNOFFICIAL = set("tOfF")
_COLOR_PAT = re.compile(r"§([A-Za-z0-9!#])")


def _find_unofficial_colors(en):
    results = []
    for m in _COLOR_PAT.finditer(en):
        ch = m.group(1)
        if ch not in _WIKI_COLOR_CODES and ch not in _KNOWN_UNOFFICIAL:
            ctx = en[max(0, m.start() - 15) : m.end() + 20].replace("\n", "\\n")
            results.append((m.group(0), ctx))
    return results


# ── 스캔 ──────────────────────────────────────────────────────────────────
def scan(auto_keys, mod_filter=None, check_dollar=False, check_color=False):
    icon_issues = collections.defaultdict(list)
    dollar_issues = collections.defaultdict(list)
    color_issues = collections.defaultdict(list)

    pattern = f"{auto_keys}/**/*_key.csv"
    for csv_path in sorted(glob.glob(pattern, recursive=True)):
        rel = os.path.relpath(csv_path, auto_keys)
        mod = rel.split(os.sep)[0]
        if mod_filter and mod_filter not in mod:
            continue

        with open(csv_path, encoding="utf-8-sig") as f:
            try:
                for row in csv.DictReader(f):
                    en = row.get("english_value", "")
                    if not en:
                        continue
                    key = row.get("key", "")

                    for orig_token, ctx in _find_unclosed_icons(en):
                        icon_issues[rel].append((key, orig_token, ctx))

                    if check_dollar:
                        for m in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_.]*)", en):
                            end_pos = m.end()
                            if end_pos < len(en) and en[end_pos] == "$":
                                continue
                            ctx_wide = en[max(0, m.start() - 25) : end_pos + 25]
                            if not _dollar_is_ok(ctx_wide):
                                ctx = ctx_wide.replace("\n", "\\n")
                                dollar_issues[rel].append((key, m.group(), ctx))

                    if check_color:
                        for token, ctx in _find_unofficial_colors(en):
                            color_issues[rel].append((key, token, ctx))

            except Exception as e:
                print(f"ERROR {rel}: {e}", file=sys.stderr)

    return icon_issues, dollar_issues, color_issues


# ── 출력 ──────────────────────────────────────────────────────────────────
def print_issues(label, issues, show_n=3):
    total = sum(len(v) for v in issues.values())
    sys.stdout.buffer.write(f"\n=== {label} ({total}건) ===\n".encode("utf-8"))
    if not total:
        sys.stdout.buffer.write("  (없음)\n".encode("utf-8"))
        return
    by_mod = collections.defaultdict(int)
    for rel, rows in issues.items():
        mod = rel.split(os.sep)[0]
        by_mod[mod] += len(rows)
    sys.stdout.buffer.write("  모드별: ".encode("utf-8"))
    parts = [f"{m.split('__')[0]}={c}" for m, c in sorted(by_mod.items(), key=lambda x: -x[1])]
    sys.stdout.buffer.write(", ".join(parts).encode("utf-8") + b"\n")
    for rel, rows in sorted(issues.items()):
        sys.stdout.buffer.write(f"\n  [{rel}] {len(rows)}건\n".encode("utf-8"))
        for key, token, ctx in rows[:show_n]:
            sys.stdout.buffer.write(f"    {key[:42]} | {token} | ...{ctx}...\n".encode("utf-8"))
        if len(rows) > show_n:
            sys.stdout.buffer.write(f"    ... 외 {len(rows) - show_n}건\n".encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="원본 영문 토큰 이상 진단",
        epilog="위키 기준: https://stellaris.paradoxwikis.com/Localisation_modding",
    )
    parser.add_argument("--mod", help="특정 모드만 (부분 이름 매칭)")
    parser.add_argument("--dollar", action="store_true", help="달러 토큰 unusual도 출력 (참고용)")
    parser.add_argument("--color", action="store_true", help="위키 미기재 §코드 출력 (참고용)")
    parser.add_argument("-n", type=int, default=3, help="파일당 예시 출력 수 (기본 3)")
    args = parser.parse_args()

    auto_keys = get_auto_keys()
    icon_issues, dollar_issues, color_issues = scan(
        auto_keys, args.mod, check_dollar=args.dollar, check_color=args.color
    )

    print_issues("icon_unclosed (patch_english_tokens.py 보정 대상)", icon_issues, args.n)
    if args.dollar:
        print_issues("dollar_unusual (참고용, 대부분 의도적 패턴)", dollar_issues, args.n)
    if args.color:
        print_issues("color_unofficial (위키 미기재 §코드, 참고용)", color_issues, args.n)


if __name__ == "__main__":
    main()
