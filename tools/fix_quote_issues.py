"""auto_keys CSV 파일의 따옴표 문제를 일괄 보정하는 스크립트.

보정 대상:
  1. imbalance : 앞뒤 따옴표 개수가 다른 셀 → 따옴표를 전부 벗겨내고 내용만 남김
  2. missing   : english_value는 따옴표로 감싸여 있는데 korean_value에 따옴표가 없는 경우
                 → korean_value를 따옴표로 감쌈
  3. double_wrap: csv.reader 통과 후 inner에 따옴표가 또 남아있는 경우
                  (파일에 5중 따옴표 형태 — 이중 저장으로 발생)
                  → inner의 바깥 따옴표를 한 겹 더 벗겨냄

실행 방법:
  # 1. validate_auto_key_tokens.py 먼저 실행해 리포트 생성
  python tools/validate_auto_key_tokens.py

  # 2. 특정 리포트를 지정해 보정
  python tools/fix_quote_issues.py --report maintenance/reports/token_validation/quote_issues_*.csv

  # 3. 리포트 없이 auto_keys 전체를 직접 스캔·보정 (느리지만 별도 단계 불필요)
  python tools/fix_quote_issues.py --scan

  # dry-run: 실제 수정 없이 변경 대상만 출력
  python tools/fix_quote_issues.py --scan --dry-run

  # 특정 모드 폴더만
  python tools/fix_quote_issues.py --scan --mod unique_ascension_perks_4_3_dev_branch__2811428998
"""

from __future__ import annotations

import argparse
import csv
import glob as glob_module
import io
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tool_config import translation_keys_root

ROOT = Path(__file__).resolve().parents[1]
AUTO_KEYS_DIR = translation_keys_root()
BACKUP_ROOT = ROOT / "maintenance" / "backups" / "fix_quote_issues"


# ── 따옴표 보정 함수 ───────────────────────────────────────────────────────────


def fix_imbalance(value: str) -> tuple[str, bool]:
    """앞뒤 따옴표 개수가 불균형하면 전부 제거 후 내용만 반환.
    반환: (보정된 값, 변경 여부)
    """
    stripped = value.strip()
    if not stripped:
        return value, False
    leading = len(stripped) - len(stripped.lstrip('"'))
    trailing = len(stripped) - len(stripped.rstrip('"'))
    if leading == 0 and trailing == 0:
        return value, False
    if leading == trailing:
        return value, False  # 균형 — 정상
    inner = stripped.strip('"')
    return inner, True


def fix_double_wrap(value: str) -> tuple[str, bool]:
    # csv.reader 통과 후 inner에 따옴표가 또 남아있는 이중 감싸기를 보정.
    # 파일의 5중 따옴표 → csv.reader → outer 1쌍 + inner 1쌍 (이중)
    # 정상: 파일의 3중 따옴표 → csv.reader → outer 1쌍만
    # outer가 있고 inner도 따옴표로 감싸여 있으면 inner 겹을 제거한다.
    s = value.strip()
    # outer 따옴표 1쌍 확인
    if not (len(s) >= 4 and s[0] == '"' and s[-1] == '"'):
        return value, False
    inner = s[1:-1]
    # inner가 또 따옴표로 감싸여 있으면 이중 감싸기
    if not (len(inner) >= 2 and inner[0] == '"' and inner[-1] == '"'):
        return value, False
    # inner의 따옴표도 벗기고 내용만 남긴 뒤 outer 1쌍만 다시 감쌈
    content = inner[1:-1]
    return f'"{content}"', True


def fix_missing_quotes(english_value: str, korean_value: str) -> tuple[str, bool]:
    """english_value가 따옴표로 시작하는데 korean_value에 따옴표가 없으면 추가.
    반환: (보정된 korean_value, 변경 여부)
    """
    e = english_value.strip()
    k = korean_value.strip()
    if not k or not e.startswith('"'):
        return korean_value, False
    if k.startswith('"'):
        return korean_value, False
    return f'"{k}"', True


_OVER_ESCAPED_NL_RE = re.compile(r"\\{2,}n")


def fix_over_escaped_newline(english_value: str, korean_value: str) -> tuple[str, bool]:
    """korean_value의 over-escape된 줄바꿈(\\\\n 등)을 \\n으로 정규화.

    게임에서 줄바꿈 대신 \\n 글자가 노출되던 손상을 복구한다. english_value에
    동일한 over-escape가 있으면 원작자 의도로 보고 건드리지 않는다.
    반환: (보정된 korean_value, 변경 여부)
    """
    if not _OVER_ESCAPED_NL_RE.search(korean_value):
        return korean_value, False
    if _OVER_ESCAPED_NL_RE.search(english_value or ""):
        return korean_value, False
    fixed = _OVER_ESCAPED_NL_RE.sub(r"\\n", korean_value)
    return fixed, fixed != korean_value


# ── CSV 읽기/쓰기 ─────────────────────────────────────────────────────────────


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """헤더와 전체 행을 읽어 반환."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    shutil.move(str(temp_path), str(path))


def backup_csv(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = path.relative_to(AUTO_KEYS_DIR)
    except ValueError:
        rel = Path(path.name)
    backup_path = BACKUP_ROOT / timestamp / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def csv_cell_literal(value: str) -> str:
    """Return the exact one-cell CSV literal csv.writer would emit."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="")
    writer.writerow([value])
    return buffer.getvalue()


# ── 보정 핵심 로직 ────────────────────────────────────────────────────────────


@dataclass
class FileFixResult:
    path: Path
    imbalance_fixed: int = 0
    double_wrap_fixed: int = 0
    missing_fixed: int = 0
    over_escape_fixed: int = 0
    backup_path: str = ""

    @property
    def total_fixed(self) -> int:
        return (
            self.imbalance_fixed
            + self.double_wrap_fixed
            + self.missing_fixed
            + self.over_escape_fixed
        )


def fix_csv_file(path: Path, dry_run: bool) -> FileFixResult:
    result = FileFixResult(path=path)
    fieldnames, rows = read_csv_rows(path)

    if not all(f in fieldnames for f in ("key", "english_value", "korean_value")):
        return result  # 필수 컬럼 없으면 스킵

    def _show(kind: str, key: str, field: str, before: str, after: str) -> None:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"

        def s(v: str) -> str:
            return v.encode(enc, errors="backslashreplace").decode(enc, errors="replace")

        print(f"  [{kind}] {key} / {field}")
        print(f"    전: {s(csv_cell_literal(before))}")
        print(f"    후: {s(csv_cell_literal(after))}")

    changed = False
    for row in rows:
        key = row.get("key", "")
        english = row.get("english_value", "") or ""
        korean = row.get("korean_value", "") or ""

        # 1) 이중 감싸기 보정 (korean_value)
        fixed_kor, dw_changed = fix_double_wrap(korean)
        if dw_changed:
            result.double_wrap_fixed += 1
            changed = True
            _show("이중감싸기", key, "korean_value", korean, fixed_kor)
            row["korean_value"] = fixed_kor
            korean = fixed_kor

        # 2) 불균형 보정 (korean_value)
        fixed_kor, kor_changed = fix_imbalance(korean)
        if kor_changed:
            result.imbalance_fixed += 1
            changed = True
            _show("불균형", key, "korean_value", korean, fixed_kor)
            row["korean_value"] = fixed_kor
            korean = fixed_kor

        # 3) 누락 따옴표 보정 (korean_value)
        fixed_kor, miss_changed = fix_missing_quotes(english, korean)
        if miss_changed:
            result.missing_fixed += 1
            changed = True
            _show("누락따옴표", key, "korean_value", korean, fixed_kor)
            row["korean_value"] = fixed_kor
            korean = fixed_kor

        # 3.5) over-escape 줄바꿈 보정 (korean_value)
        fixed_kor, oe_changed = fix_over_escaped_newline(english, korean)
        if oe_changed:
            result.over_escape_fixed += 1
            changed = True
            _show("over-escape", key, "korean_value", korean, fixed_kor)
            row["korean_value"] = fixed_kor
            korean = fixed_kor

        # 4) 이중 감싸기 + 불균형 보정 (english_value) — 드물지만 체크
        fixed_eng, dw_eng = fix_double_wrap(english)
        if dw_eng:
            result.double_wrap_fixed += 1
            changed = True
            _show("이중감싸기", key, "english_value", english, fixed_eng)
            row["english_value"] = fixed_eng
            english = fixed_eng
        fixed_eng, kor_eng = fix_imbalance(english)
        if kor_eng:
            result.imbalance_fixed += 1
            changed = True
            _show("불균형", key, "english_value", english, fixed_eng)
            row["english_value"] = fixed_eng

    if changed and not dry_run:
        result.backup_path = str(backup_csv(path))
        write_csv_rows(path, fieldnames, rows)

    return result


# ── 모드 1: report CSV를 읽어 대상 파일만 보정 ───────────────────────────────


def fix_from_report(report_paths: list[Path], auto_keys_dir: Path, dry_run: bool) -> None:
    # 리포트에서 (mod, file) 조합을 수집
    affected: dict[Path, set[str]] = defaultdict(set)
    for rp in report_paths:
        if not rp.exists():
            print(f"[SKIP] 리포트 파일 없음: {rp}")
            continue
        with rp.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mod = row.get("mod", "")
                file_rel = row.get("file", "")
                if mod and file_rel:
                    csv_path = auto_keys_dir / mod / file_rel
                    affected[csv_path].add(row.get("issue_type", ""))

    if not affected:
        print("[완료] 보정 대상 없음 (리포트에 행이 없음)")
        return

    total_double = total_imbalance = total_missing = total_over_escape = 0
    for csv_path in sorted(affected):
        if not csv_path.exists():
            print(f"[SKIP] CSV 없음: {csv_path}")
            continue
        result = fix_csv_file(csv_path, dry_run)
        if result.total_fixed:
            mode = "[dry-run]" if dry_run else ""
            print(
                f"{mode} {csv_path.name}: 이중감싸기 {result.double_wrap_fixed}건, 불균형 {result.imbalance_fixed}건, 누락 {result.missing_fixed}건, over-escape {result.over_escape_fixed}건 보정"
            )
            if result.backup_path:
                print(f"  백업: {result.backup_path}")
            total_double += result.double_wrap_fixed
            total_imbalance += result.imbalance_fixed
            total_missing += result.missing_fixed
            total_over_escape += result.over_escape_fixed

    _print_summary(total_double, total_imbalance, total_missing, total_over_escape, dry_run)


# ── 모드 2: auto_keys 전체 스캔 ──────────────────────────────────────────────


def fix_by_scan(auto_keys_dir: Path, mods: list[str], dry_run: bool) -> None:
    if mods:
        csv_files: list[Path] = []
        for mod in sorted(mods):
            csv_files.extend(sorted((auto_keys_dir / mod).rglob("*_key.csv")))
    else:
        csv_files = sorted(auto_keys_dir.rglob("*_key.csv"))

    total_double = total_imbalance = total_missing = total_over_escape = 0
    for csv_path in csv_files:
        result = fix_csv_file(csv_path, dry_run)
        if result.total_fixed:
            mode = "[dry-run]" if dry_run else ""
            print(
                f"{mode} {csv_path.name}: 이중감싸기 {result.double_wrap_fixed}건, 불균형 {result.imbalance_fixed}건, 누락 {result.missing_fixed}건, over-escape {result.over_escape_fixed}건 보정"
            )
            if result.backup_path:
                print(f"  백업: {result.backup_path}")
            total_double += result.double_wrap_fixed
            total_imbalance += result.imbalance_fixed
            total_missing += result.missing_fixed
            total_over_escape += result.over_escape_fixed

    _print_summary(total_double, total_imbalance, total_missing, total_over_escape, dry_run)


def _print_summary(double: int, imbalance: int, missing: int, over_escape: int, dry_run: bool) -> None:
    total = double + imbalance + missing + over_escape
    label = "(dry-run, 실제 저장 안 함)" if dry_run else ""
    print(f"\n=== 완료 {label} ===")
    print(f"  이중 감싸기 보정: {double}건")
    print(f"  불균형 보정: {imbalance}건")
    print(f"  누락 따옴표 보정: {missing}건")
    print(f"  over-escape 보정: {over_escape}건")
    print(f"  합계: {total}건")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="auto_keys CSV의 따옴표 문제(불균형·누락)를 보정합니다."
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--report",
        nargs="+",
        metavar="GLOB",
        help="validate_auto_key_tokens.py 가 생성한 quote_issues_*.csv 경로 (glob 가능).",
    )
    mode.add_argument(
        "--scan",
        action="store_true",
        help="auto_keys 디렉토리 전체를 직접 스캔해 보정합니다.",
    )

    parser.add_argument(
        "--auto-keys-dir",
        default=str(AUTO_KEYS_DIR),
        help="translation keys 경로 (기본값: maintenance/tooling.ini 기준).",
    )
    parser.add_argument(
        "--mod",
        action="append",
        default=[],
        help="--scan 모드에서 특정 모드 폴더만 처리. 반복 가능.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 파일을 수정하지 않고 변경 대상만 출력합니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auto_keys_dir = Path(args.auto_keys_dir)

    if not auto_keys_dir.is_dir():
        print(f"오류: auto_keys 디렉토리를 찾을 수 없습니다: {auto_keys_dir}", file=sys.stderr)
        return 1

    if args.scan:
        fix_by_scan(auto_keys_dir, args.mod, args.dry_run)
    else:
        # glob 패턴 확장
        report_paths: list[Path] = []
        for pattern in args.report:
            matches = glob_module.glob(pattern)
            if matches:
                report_paths.extend(Path(m) for m in matches)
            else:
                report_paths.append(Path(pattern))
        fix_from_report(report_paths, auto_keys_dir, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
