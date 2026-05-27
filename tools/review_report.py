"""번역 검수 리포트 생성기.

auto_keys CSV를 스캔해 의심스러운 번역 행 (기본 모드) 또는
정상 번역 행 (퀄리티 모드) 을 CSV로 출력한다.
재번역은 translate_keys.py --from-report 로만 수행한다.

────────────────────────────────────────────────────
모드 A — 기본 (기본값): 양식/토큰 깨진 행만 추출
────────────────────────────────────────────────────
의심 기준 (reason 컬럼에 표기):
  empty        — korean_value가 비어 있음
  identical    — 영문과 한국어가 완전히 동일 (번역 안 됨)
  token_broken — 하드 토큰 불일치 ($var$, [Ref], £icon£ 개수·종류가 다름)
  no_hangul    — 한글이 없고 토큰 전용 행도 아님 (영문 그대로)
  too_short    — 번역문 길이가 원문의 15% 미만 (기본 리포트에서는 제외, --reason too_short로만 출력)
  quote_noise  — CSV/게임 출력용 따옴표가 여러 겹으로 누적됨

리포트: maintenance/reports/review/review_latest.csv

실행:
  # 리포트 생성 (retranslate 열 비워둠 — 직접 표시 후 --from-report 사용)
  python tools/review_report.py

  # 깨진 행 전체를 retranslate=1로 즉시 재번역 대기열에 넣기
  python tools/review_report.py --mark-errors
  python tools/translate_keys.py --from-report

  # 특정 이유만
  python tools/review_report.py --reason token_broken no_hangul
  python tools/review_report.py --reason too_short

────────────────────────────────────────────────────
모드 B — 퀄리티 (--quality): 정상 번역 행만 추출
────────────────────────────────────────────────────
양식은 정상이지만 번역 품질을 재검토하고 싶을 때 사용.
기본 검사를 통과한 (이상 없는) 행만 포함.

리포트: maintenance/reports/review/review_quality_latest.csv

실행:
  # 퀄리티 리포트 생성 (retranslate 열 비워둠)
  python tools/review_report.py --quality

  # 전체 정상 번역을 재번역 대기열에 넣기 (대용량 주의)
  python tools/review_report.py --quality --mark-retranslate
  python tools/translate_keys.py --from-report quality

  # 특정 모드만
  python tools/review_report.py --quality --mod <모드폴더>
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

# translate_keys가 같은 tools/ 폴더에 있으므로 해당 디렉토리를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from tool_config import translation_keys_root
from translate_keys import (
    HANGUL_RE,
    has_quote_noise,
    hard_tokens_differ,
    is_token_only,
    _strip_all_tokens,
)

# <...> 동적 포맷 토큰 (네임 포맷 등) — 번역 불가 구조
_ANGLE_FMT_RE = re.compile(r"<[^>]+>")
# YML 인라인 주석: 값 뒤에 공백+"# ..." 형태로 붙는 원본 모드 주석
# 예: `$giga_birch_orykta_col$‌§!"  # between the $ and §...`
_YML_INLINE_COMMENT_RE = re.compile(r'\s+#.*$')
# 번역 불필요 단어 패턴:
#   - 대문자 시작 고유명사 (Ssha, T'lind, Ndeir 등)
#   - 숫자·기호만으로 구성 (수식, 범위: n100+10+(0-9):, -100%, 1 - 10)
#   - 약어/코드 (AI, AI:, "Society:" 같은 레이블 뒤 콜론은 stripped에서 별도 토큰)
#   소문자 시작이라도 번역 불필요한 케이스: 단어가 숫자를 포함하거나 콜론으로 끝남
_PROPER_WORD_RE = re.compile(
    r"^[A-Z][A-Za-z0-9''\-]*$"        # 대문자 시작 고유명사
    r"|^[A-Z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+\.?$"  # 점 포함 약어 (F.S.A.E., U.T.A. 등)
    r"|^[A-Za-z]{1,5}:?$"              # 짧은 약어 (AI, AI:, def, def: 등 5자 이하)
    r"|^[A-Za-z0-9]*[0-9\+\-\(\)\*][A-Za-z0-9\+\-\(\)\*\:\.]*$"  # 수식/포맷 (n100, +1%, 0-9: 등)
    r"|^[^A-Za-z]*$"                   # 숫자·기호만 (수식, 퍼센트 등)
)


def _is_untranslatable_identical(text: str) -> bool:
    """영문=한국어여도 identical warning을 내지 않아야 하는 행인지 판별.

    해당 케이스:
    1. <...> 동적 네임 포맷 포함 — 번역 불가 구조
    2. 토큰 제거 후 남은 텍스트가 고유명사/코드 패턴 (네임리스트, 수식, 약어 레이블 등)
    """
    if _ANGLE_FMT_RE.search(text):
        return True
    stripped = _strip_all_tokens(text).strip()
    if not stripped:
        # 토큰만 남음 (is_token_only가 잡지 못한 경계 케이스)
        return True
    words = stripped.split()
    return all(_PROPER_WORD_RE.match(w) for w in words if w)


ROOT = Path(__file__).resolve().parents[1]
AUTO_KEYS_DIR = translation_keys_root()
REPORT_DIR = ROOT / "maintenance" / "reports" / "review"
DEFAULT_GLOSSARY = ROOT / "maintenance" / "term_glossary.csv"
DEFAULT_EXCLUDED_REASONS = {"too_short"}
ERROR_REASONS = {"empty", "token_broken", "no_hangul", "quote_noise"}


# ── 단어집 ────────────────────────────────────────────────────────────────────

def load_glossary(path: Path) -> dict[str, str]:
    """english(소문자) → korean 매핑 반환. 파일 없으면 빈 딕셔너리."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                eng = (row.get("english") or "").strip()
                kor = (row.get("korean") or "").strip()
                if eng and kor:
                    result[eng.lower()] = kor
    except Exception:
        pass
    return result


# ── 검사 함수 ─────────────────────────────────────────────────────────────────

def _parse_cell(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def get_reasons(
    eng_inner: str,
    kor_inner: str,
    kor_raw: str = "",
    glossary: dict[str, str] | None = None,
) -> list[str]:
    # YML 인라인 주석 제거 (공백+# ... 형태) — EN/KO 모두 주석 제외하고 비교
    english = _YML_INLINE_COMMENT_RE.sub("", eng_inner).strip()
    korean = _YML_INLINE_COMMENT_RE.sub("", kor_inner).strip()
    if not english:
        return []
    # 토큰 전용 행은 영문=한국어여도 정상 — 검수 불필요
    if is_token_only(english):
        return []
    reasons: list[str] = []
    quote_noise = has_quote_noise(kor_raw) or has_quote_noise(kor_inner)
    if not korean:
        reasons.append("empty")
        if quote_noise:
            reasons.append("quote_noise")
        return reasons
    if quote_noise:
        reasons.append("quote_noise")
    if english == korean and not is_token_only(english):
        if _is_untranslatable_identical(english):
            # 동적 포맷(<...>) 또는 고유명사 패턴 — 영문 유지가 정상
            pass
        else:
            words = english.split()
            if len(words) > 1:
                # 다단어는 identical
                reasons.append("identical")
            elif glossary is not None and english.lower() in glossary:
                # 단어 1개라도 단어집에 한국어 번역이 있으면 identical
                reasons.append("identical")
            # 단어 1개이고 단어집에도 없으면 고유명사로 간주해 통과
    if hard_tokens_differ(english, korean):
        reasons.append("token_broken")
    # 한글 없음 — identical이 이미 잡은 경우 중복 불필요
    # 단어 1개 고유명사(행성명·종족명 등)는 영문 그대로여도 정상
    if not HANGUL_RE.search(korean) and "identical" not in reasons:
        eng_text = _strip_all_tokens(english)
        if len(eng_text.split()) > 1 and not _is_untranslatable_identical(english):
            reasons.append("no_hangul")
    # too_short: 토큰 제거 후 순수 텍스트 길이로 비교
    if not reasons:
        eng_text = _strip_all_tokens(english)
        kor_text = _strip_all_tokens(korean)
        if eng_text and len(kor_text) < max(4, int(len(eng_text) * 0.15)):
            reasons.append("too_short")
    return reasons


def filter_reasons_for_report(reasons: list[str], reason_filter: set[str]) -> list[str]:
    """Return reasons that should be emitted in the report.

    `too_short` is useful for broad quality sampling, but it creates heavy
    noise for short labels and names. Keep detecting it, but only report it
    when the user explicitly asks with `--reason too_short`.
    """
    if reason_filter:
        return [reason for reason in reasons if reason in reason_filter]
    return [reason for reason in reasons if reason not in DEFAULT_EXCLUDED_REASONS]


def classify_severity(reasons: list[str]) -> str:
    """Classify report rows for automatic workflow decisions."""
    if any(reason in ERROR_REASONS for reason in reasons):
        return "error"
    return "warning"


# ── 스캔 ─────────────────────────────────────────────────────────────────────

def scan_file(
    csv_path: Path,
    reason_filter: set[str],
    retranslate_default: str = "",
    mark_errors: bool = False,
    quality_mode: bool = False,
    glossary: dict[str, str] | None = None,
    auto_keys_dir: Path | None = None,
) -> list[dict[str, str]]:
    """CSV 파일 한 개를 스캔해 리포트 행 목록을 반환한다.

    quality_mode=False (기본): 의심 행(reasons 있음)만 포함.
    quality_mode=True: 정상 번역 행(reasons 없음, 영문 있고 한국어 있음)만 포함.
    """
    # auto_keys_dir 기준 상대 경로: 첫 파트=mod, 나머지=file (replace/ 하위 포함)
    if auto_keys_dir and csv_path.is_relative_to(auto_keys_dir):
        rel_parts = csv_path.relative_to(auto_keys_dir).parts
        mod_col = rel_parts[0] if rel_parts else ""
        file_col = str(Path(*rel_parts[1:])) if len(rel_parts) > 1 else csv_path.name
    else:
        mod_col = csv_path.parts[-2] if len(csv_path.parts) >= 2 else ""
        file_col = csv_path.name

    rows_out: list[dict[str, str]] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return rows_out
            required = {"key", "english_value", "korean_value"}
            if not required.issubset(set(reader.fieldnames)):
                return rows_out
            for lineno, row in enumerate(reader, start=2):
                eng_raw = row.get("english_value") or ""
                kor_raw = row.get("korean_value") or ""
                eng_inner = _parse_cell(eng_raw)
                kor_inner = _parse_cell(kor_raw)
                reasons = get_reasons(eng_inner, kor_inner, kor_raw, glossary)
                report_reasons = filter_reasons_for_report(reasons, reason_filter)

                if quality_mode:
                    # 정상 행: 영문 있고, 한국어 있고, reasons 없고, 토큰 전용 아님
                    if report_reasons:
                        continue
                    if not eng_inner.strip() or not kor_inner.strip():
                        continue
                    if is_token_only(eng_inner):
                        continue
                    rows_out.append({
                        "mod": mod_col,
                        "file": file_col,
                        "row": str(lineno),
                        "key": row.get("key", ""),
                        "severity": "quality",
                        "reason": "quality_review",
                        "english_value": eng_raw,
                        "korean_value": kor_raw,
                        "retranslate": retranslate_default,
                    })
                else:
                    # 기본 모드: 의심 행만
                    if not report_reasons:
                        continue
                    severity = classify_severity(report_reasons)
                    retranslate_value = "1" if mark_errors and severity == "error" else retranslate_default
                    rows_out.append({
                        "mod": mod_col,
                        "file": file_col,
                        "row": str(lineno),
                        "key": row.get("key", ""),
                        "severity": severity,
                        "reason": "|".join(report_reasons),
                        "english_value": eng_raw,
                        "korean_value": kor_raw,
                        "retranslate": retranslate_value,
                    })
    except Exception as exc:
        print(f"[WARN] 읽기 실패 {csv_path}: {exc}", file=sys.stderr)
    return rows_out


def _collect_csv_files(auto_keys_dir: Path, mods: list[str], files: list[str]) -> list[Path]:
    if mods:
        csv_files: list[Path] = []
        for mod in sorted(mods):
            csv_files.extend(sorted((auto_keys_dir / mod).rglob("*_key.csv")))
        return csv_files
    if files:
        result: list[Path] = []
        for f in files:
            fp = Path(f)
            if fp.is_absolute() and fp.exists():
                result.append(fp)
            else:
                matches = list(auto_keys_dir.rglob(fp.name))
                if matches:
                    result.extend(sorted(matches))
                else:
                    print(f"[WARN] 파일 없음: {f}", file=sys.stderr)
        return result
    return sorted(auto_keys_dir.rglob("*_key.csv"))


def run(
    auto_keys_dir: Path,
    mods: list[str],
    files: list[str],
    reason_filter: set[str],
    output: Path,
    retranslate_default: str = "",
    mark_errors: bool = False,
    quality_mode: bool = False,
    glossary_path: Path = DEFAULT_GLOSSARY,
) -> None:
    csv_files = _collect_csv_files(auto_keys_dir, mods, files)
    mode_label = "정상 번역(퀄리티)" if quality_mode else "의심"
    glossary = load_glossary(glossary_path)
    if glossary:
        print(f"단어집: {len(glossary)}개 항목 로드")

    all_rows: list[dict[str, str]] = []
    for csv_path in csv_files:
        rows = scan_file(
            csv_path,
            reason_filter,
            retranslate_default,
            mark_errors,
            quality_mode,
            glossary,
            auto_keys_dir=auto_keys_dir,
        )
        if rows:
            print(f"  {csv_path.name}: {len(rows)}행 {mode_label}")
        all_rows.extend(rows)

    if not all_rows:
        print(f"{mode_label} 행 없음.")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["mod", "file", "row", "key", "severity", "reason", "english_value", "korean_value", "retranslate"]
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n합계: {len(all_rows)}행")
    print(f"리포트: {output}")

    if quality_mode:
        print("\n퀄리티 검수 방법:")
        print("  1. 리포트를 Excel/Sheets에서 열어 번역 품질 검토")
        print("  2. 재번역할 행의 'retranslate' 열에 1 입력")
        print("  3. 저장 후 실행:")
        print(f"     python tools/translate_keys.py --from-report quality")
    else:
        print("\n검수 방법:")
        print("  1. 자동 절차: --mark-errors로 생성한 뒤 translate_keys.py --from-report 실행")
        print("  2. 수동 검수: 리포트를 열어 재번역할 행의 'retranslate' 열에 1 입력")
        print("  3. 저장 후 실행:")
        print(f"     python tools/translate_keys.py --from-report")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "번역 검수 리포트를 생성합니다.\n"
            "기본 모드: 양식/토큰이 깨진 의심 행 추출 → review_latest.csv\n"
            "too_short는 기본 제외, --reason too_short 지정 시에만 출력\n"
            "퀄리티 모드 (--quality): 정상 번역 행 추출 → review_quality_latest.csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--auto-keys-dir", default=str(AUTO_KEYS_DIR))
    parser.add_argument("--mod", action="append", default=[], help="특정 모드 폴더만 처리. 반복 가능.")
    parser.add_argument("--file", action="append", default=[], help="특정 CSV 파일명/경로. 반복 가능.")
    parser.add_argument(
        "--reason",
        nargs="+",
        choices=["empty", "identical", "token_broken", "no_hangul", "too_short", "quote_noise"],
        default=[],
        help="[기본 모드] 특정 이유의 행만 출력. 기본: too_short 제외 전체. --quality 와 함께 쓸 수 없음.",
    )
    parser.add_argument(
        "--quality",
        action="store_true",
        help=(
            "퀄리티 모드: 양식이 정상인 번역 행만 추출합니다. "
            "번역 품질을 전체적으로 재검토할 때 사용. "
            "리포트: review_quality_latest.csv"
        ),
    )
    parser.add_argument("--output", default="", help="출력 CSV 경로를 직접 지정. 기본: 모드에 따라 자동 결정.")
    parser.add_argument(
        "--mark-retranslate",
        action="store_true",
        help="모든 대상 행의 retranslate 열을 1로 채워 생성합니다. translate_keys.py --from-report 로 전체 재번역할 때 사용.",
    )
    parser.add_argument(
        "--mark-errors",
        action="store_true",
        help="severity=error 행만 retranslate=1로 표시합니다. 자동 검수/재번역 파이프라인용입니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auto_keys_dir = Path(args.auto_keys_dir)
    if not auto_keys_dir.is_dir():
        print(f"오류: auto_keys 디렉토리 없음: {auto_keys_dir}", file=sys.stderr)
        return 1

    if args.quality and args.reason:
        print("오류: --quality 와 --reason 은 함께 사용할 수 없습니다.", file=sys.stderr)
        return 1
    if args.quality and args.mark_errors:
        print("오류: --quality 와 --mark-errors 는 함께 사용할 수 없습니다.", file=sys.stderr)
        return 1
    if args.mark_retranslate and args.mark_errors:
        print("오류: --mark-retranslate 와 --mark-errors 는 함께 사용할 수 없습니다.", file=sys.stderr)
        return 1

    if args.output:
        output = Path(args.output)
    elif args.quality:
        latest = REPORT_DIR / "review_quality_latest.csv"
        if latest.exists():
            mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
            latest.rename(REPORT_DIR / f"review_quality_{mtime}.csv")
        output = latest
    else:
        latest = REPORT_DIR / "review_latest.csv"
        if latest.exists():
            mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
            latest.rename(REPORT_DIR / f"review_{mtime}.csv")
        output = latest

    reason_filter = set(args.reason)
    retranslate_default = "1" if args.mark_retranslate else ""
    run(auto_keys_dir, args.mod, args.file, reason_filter, output, retranslate_default, args.mark_errors, args.quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
