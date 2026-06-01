# -*- coding: utf-8 -*-
"""glossary.csv 기반으로 korean_value의 잘못된 번역을 일괄 교체한다.

단어장 형식 (tools/glossary.csv):
  english,korean_wrong,korean_correct

동작:
  1. english_value에 english 단어가 포함된 행을 찾는다.
  2. 같은 행의 korean_value에서 korean_wrong을 korean_correct로 교체한다.
  3. 변경된 행만 저장한다.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import shutil
from pathlib import Path

from tool_config import translation_keys_root

PACK_ROOT = Path(__file__).resolve().parents[1]
AUTO_KEYS_DIR = translation_keys_root()
DEFAULT_GLOSSARY = Path(__file__).parent / "glossary.csv"
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "glossary_apply"


def load_glossary(path: Path) -> list[tuple[str, str, str]]:
    """(english, korean_wrong, korean_correct) 목록 반환."""
    entries = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            english = row.get("english", "").strip()
            wrong = row.get("korean_wrong", "").strip()
            correct = row.get("korean_correct", "").strip()
            if english and wrong and correct and wrong != correct:
                entries.append((english, wrong, correct))
    return entries


def backup_csv(path: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = path.relative_to(AUTO_KEYS_DIR)
    except ValueError:
        rel = Path(path.name)
    backup_path = BACKUP_ROOT / timestamp / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    shutil.move(str(tmp), str(path))


def apply_glossary(
    filepath: Path,
    glossary: list[tuple[str, str, str]],
    *,
    dry_run: bool,
) -> tuple[int, int, list[dict[str, str]]]:
    """반환: (검사한 행 수, 교체된 행 수, 변경 내역 목록)"""
    with filepath.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if (
        "key" not in fieldnames
        or "english_value" not in fieldnames
        or "korean_value" not in fieldnames
    ):
        return 0, 0, []

    changed_rows = 0
    changes: list[dict[str, str]] = []
    for row in rows:
        english_value = row.get("english_value", "")
        korean_value = row.get("korean_value", "")
        if not english_value or not korean_value:
            continue

        new_korean = korean_value
        matched_rules: list[str] = []
        for english, wrong, correct in glossary:
            if english.lower() in english_value.lower() and wrong in new_korean:
                new_korean = new_korean.replace(wrong, correct)
                matched_rules.append(f"{wrong} → {correct}")

        if new_korean != korean_value:
            changed_rows += 1
            changes.append(
                {
                    "key": row.get("key", ""),
                    "rule": ", ".join(matched_rules),
                    "before": korean_value,
                    "after": new_korean,
                }
            )
            row["korean_value"] = new_korean

    if changed_rows > 0 and not dry_run:
        backup_csv(filepath)
        write_csv(filepath, fieldnames, rows)

    return len(rows), changed_rows, changes


def iter_csv_files(auto_keys_dir: Path, mods: list[str], files: list[str]) -> list[Path]:
    if files:
        result = []
        for f in files:
            candidate = Path(f)
            if candidate.is_absolute() and candidate.is_file():
                result.append(candidate)
            else:
                result.extend(auto_keys_dir.rglob(Path(f).name))
        return sorted(set(result))
    if mods:
        result = []
        for mod in mods:
            result.extend(sorted((auto_keys_dir / mod).rglob("*_key.csv")))
        return result
    return sorted(
        Path(p) for p in glob.glob(str(auto_keys_dir / "**" / "*_key.csv"), recursive=True)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="단어장 기반 korean_value 일괄 교체")
    parser.add_argument("--glossary", default=str(DEFAULT_GLOSSARY), help="단어장 CSV 경로")
    parser.add_argument("--auto-keys-dir", default=str(AUTO_KEYS_DIR))
    parser.add_argument("--mod", action="append", default=[], help="특정 모드만 처리. 반복 가능.")
    parser.add_argument(
        "--file", action="append", default=[], help="특정 CSV 파일만 처리. 반복 가능."
    )
    parser.add_argument("--dry-run", action="store_true", help="실제 저장 없이 교체 대상만 출력.")
    args = parser.parse_args()

    glossary_path = Path(args.glossary)
    if not glossary_path.is_file():
        print(f"단어장 파일을 찾을 수 없습니다: {glossary_path}")
        return 1

    glossary = load_glossary(glossary_path)
    if not glossary:
        print("단어장이 비어 있습니다.")
        return 1

    print(f"단어장 항목: {len(glossary)}개")
    if args.dry_run:
        print("모드: dry-run (파일 수정 없음)")

    auto_keys_dir = Path(args.auto_keys_dir)
    csv_files = iter_csv_files(auto_keys_dir, args.mod, args.file)
    print(f"대상 파일: {len(csv_files)}개\n")

    total_rows = 0
    total_changed = 0
    for filepath in csv_files:
        rows, changed, changes = apply_glossary(filepath, glossary, dry_run=args.dry_run)
        total_rows += rows
        total_changed += changed
        if changed:
            rel = (
                filepath.relative_to(auto_keys_dir)
                if filepath.is_relative_to(auto_keys_dir)
                else filepath
            )
            print(f"\n[{rel}] {changed}행 교체{'예정' if args.dry_run else '완료'}")
            for c in changes:
                print(f"  키:   {c['key']}")
                print(f"  규칙: {c['rule']}")
                print(f"  전:   {c['before']}")
                print(f"  후:   {c['after']}")
                print()

    print(f"{'=' * 50}")
    print(f"검사 행: {total_rows}  /  교체: {total_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
