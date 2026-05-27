#!/usr/bin/env python3
"""CSV 양식 검사 래퍼 — normalize_csv_newlines, fix_quote_issues, validate_auto_key_tokens를 순서대로 실행한다.

사용:
    python tools/check_format.py
    python tools/check_format.py --mod gigastructural_engineering_more_4_3__1121692237
    python tools/check_format.py --file maintenance/translation_keys/.../frameworld_key.csv
    python tools/check_format.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

from tool_config import translation_keys_root

# Windows CP949 환경에서도 한글·유니코드 출력 가능하도록
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
AUTO_KEYS_DIR = translation_keys_root()

# ── 출력 헬퍼 ─────────────────────────────────────────────────────────

def header(step: int, total: int, title: str) -> None:
    print(f"\n┌─ [{step}/{total}] {title}")

def footer_ok(msg: str) -> None:
    print(f"└─ ✓ {msg}")

def footer_warn(msg: str) -> None:
    print(f"└─ ⚠ {msg}")

def footer_err(msg: str) -> None:
    print(f"└─ ✗ {msg}")

def item(msg: str) -> None:
    print(f"│  {msg}")

def divider() -> None:
    print()


# ── 파싱 헬퍼 ─────────────────────────────────────────────────────────

def parse_kv(text: str) -> dict[str, str]:
    """key=value 형식의 출력을 딕셔너리로 변환."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^(\w+)=(.*)$", line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip().strip('"')
    return result


def short_path(path_str: str) -> str:
    """절대 경로를 maintenance/... 상대 경로로 줄임."""
    try:
        return str(Path(path_str).relative_to(PACK_ROOT))
    except ValueError:
        return path_str


# ── 각 단계 실행 ──────────────────────────────────────────────────────

def run_normalize(csv_files: list[Path], dry_run: bool) -> int:
    header(1, 3, "줄바꿈 정규화  (실제 줄바꿈 → \\n 리터럴)")
    dry = ["--dry-run"] if dry_run else []
    changed_files: list[tuple[str, int]] = []
    errors = 0

    for p in csv_files:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "normalize_csv_newlines.py"), str(p)] + dry,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            errors += 1
            continue
        kv = parse_kv(result.stdout)
        n = int(kv.get("changed_cells", 0))
        if n:
            rel = str(p.relative_to(AUTO_KEYS_DIR))
            changed_files.append((rel, n))

    if not changed_files:
        footer_ok("변경 없음.")
    else:
        total_cells = sum(n for _, n in changed_files)
        for rel, n in changed_files:
            item(f"{rel}  ({n}셀)")
        label = "탐지됨" if dry_run else "수정됨"
        footer_warn(f"{len(changed_files)}개 파일, {total_cells}셀 {label}")

    return errors


def run_fix_quote(mods: list[str], dry_run: bool) -> int:
    header(2, 3, "따옴표 보정  (누락·이중 감싸기 수정)")
    cmd = [sys.executable, str(SCRIPT_DIR / "fix_quote_issues.py"), "--scan"]
    if dry_run:
        cmd.append("--dry-run")
    for mod in mods:
        cmd += ["--mod", mod]

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )

    out = result.stdout + result.stderr
    # 최종 요약 줄 파싱
    added = re.search(r"재배치.*?(\d+)개", out)
    removed = re.search(r"불균형.*?(\d+)개", out)
    double = re.search(r"이중.*?(\d+)개", out)

    # 파일별 변경 줄
    file_lines = re.findall(r"\[(dry-run)\]\s+(.+?\.csv):\s+(.+)", out)
    normal_lines = re.findall(r"(?<!\[dry-run\] )(\S+\.csv):\s+(재배치\S*\s+\d+개.+)", out)
    changed_lines = re.findall(r"(.+\.csv):.+?(?:이중감싸기|재배치|불균형)\s+(\d+)개.+합계\s+(\d+)개", out)

    # 합계 추출
    total_match = re.search(r"합계:\s*(\d+)개", out)
    total = int(total_match.group(1)) if total_match else 0

    if total == 0:
        footer_ok("변경 없음.")
    else:
        # 파일별 요약만 출력
        for line in out.splitlines():
            if ".csv:" in line and ("개" in line or "행" in line):
                cleaned = re.sub(r"\s+", " ", line.strip())
                if cleaned:
                    item(cleaned)
        label = "탐지됨" if dry_run else "수정됨"
        footer_warn(f"총 {total}개 {label}")

    return max(0, result.returncode)


def run_validate(mods: list[str]) -> int:
    header(3, 3, "토큰 검증  (하드 토큰·따옴표 이슈 리포트)")
    cmd = [sys.executable, str(SCRIPT_DIR / "validate_auto_key_tokens.py")]
    for mod in mods:
        cmd += ["--mod", mod]

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    kv = parse_kv(result.stdout)

    scanned   = kv.get("scanned_files", "?")
    critical  = int(kv.get("critical_rows", 0))
    order     = int(kv.get("hard_order_rows", 0))
    style     = int(kv.get("style_rows", 0))
    quote     = int(kv.get("quote_issue_rows", 0))
    repair    = int(kv.get("repair_worklist_rows", 0))

    item(f"스캔 파일: {scanned}개")
    item(f"Critical (토큰 누락·추가): {critical}행  ← 즉시 수정 필요")
    item(f"Hard order (순서 불일치): {order}행")
    item(f"Style (§·\\n 형식):        {style}행")
    item(f"따옴표 이슈:               {quote}행")
    item(f"수정 워크리스트:           {repair}행")

    # 리포트 경로
    for key in ("repair_worklist_csv", "quote_issues_csv", "issue_csv"):
        if key in kv:
            item(f"→ {short_path(kv[key])}")

    if critical == 0 and quote == 0:
        footer_ok("Critical·따옴표 이슈 없음.")
    elif critical > 0:
        footer_err(f"Critical {critical}행 — repair_worklist_csv 확인")
    else:
        footer_warn(f"따옴표 이슈 {quote}행 — quote_issues_csv 확인")

    return max(0, result.returncode)


# ── 메인 ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV 양식 검사·보정 래퍼")
    parser.add_argument("--mod", action="append", default=[], metavar="MOD",
                        help="특정 모드 폴더만 처리. 반복 가능.")
    parser.add_argument("--file", action="append", default=[], metavar="FILE",
                        help="특정 CSV 파일만 처리. 반복 가능.")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일 수정 없이 탐지만.")
    parser.add_argument("--skip-normalize", action="store_true",
                        help="normalize_csv_newlines 건너뜀.")
    parser.add_argument("--skip-quote", action="store_true",
                        help="fix_quote_issues 건너뜀.")
    parser.add_argument("--skip-validate", action="store_true",
                        help="validate_auto_key_tokens 건너뜀.")
    return parser.parse_args()


def resolve_csv_files(mods: list[str], files: list[str]) -> list[Path]:
    if files:
        result = []
        for f in files:
            p = Path(f)
            if not p.is_absolute():
                p = PACK_ROOT / p
            if p.is_file():
                result.append(p)
        return result
    if mods:
        result = []
        for mod in mods:
            mod_dir = AUTO_KEYS_DIR / mod
            if mod_dir.is_dir():
                result.extend(sorted(mod_dir.rglob("*_key.csv")))
        return result
    return sorted(AUTO_KEYS_DIR.rglob("*_key.csv"))


def main() -> int:
    args = parse_args()
    csv_files = resolve_csv_files(args.mod, args.file)

    scope = ""
    if args.mod:
        scope = f"  모드: {', '.join(args.mod)}"
    elif args.file:
        scope = f"  파일: {len(args.file)}개"
    else:
        scope = f"  전체 auto_keys ({len(csv_files)}개 파일)"

    print("━" * 60)
    print("  CSV 양식 검사" + ("  [dry-run]" if args.dry_run else ""))
    print(scope)
    print("━" * 60)

    errors = 0

    if not args.skip_normalize:
        errors += run_normalize(csv_files, args.dry_run)

    if not args.skip_quote:
        errors += run_fix_quote(args.mod, args.dry_run)

    if not args.skip_validate:
        errors += run_validate(args.mod)

    divider()
    print("━" * 60)
    if errors:
        print(f"  완료  (오류 {errors}건 — 위 로그 확인)")
    else:
        print("  완료")
    print("━" * 60)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
