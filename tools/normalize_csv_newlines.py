#!/usr/bin/env python3
"""Normalize embedded physical newlines in auto_keys CSV cells to \\n."""

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

from tool_config import csv_dict_writer

PACK_ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "normalize_csv_newlines"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace embedded CR/LF inside CSV cells with literal \\n."
    )
    parser.add_argument(
        "csv_path", help="CSV path, relative to the translation pack root or absolute."
    )
    parser.add_argument("--dry-run", action="store_true", help="Report rows only; do not write.")
    return parser.parse_args()


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PACK_ROOT / path


def normalize_value(value: str) -> tuple[str, bool]:
    normalized = value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return normalized, normalized != value


def main() -> int:
    args = parse_args()
    path = resolve_path(args.csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    changed_cells: list[dict[str, object]] = []
    for line_number, row in enumerate(rows, start=2):
        for field in fieldnames:
            new_value, changed = normalize_value(row.get(field, "") or "")
            if changed:
                changed_cells.append(
                    {"line_number": line_number, "key": row.get("key", ""), "field": field}
                )
                row[field] = new_value

    print(f"rows={len(rows)}")
    print(f"changed_cells={len(changed_cells)}")
    for item in changed_cells[:20]:
        print(f"{item['line_number']}\t{item['key']}\t{item['field']}")

    if args.dry_run or not changed_cells:
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = path.relative_to(PACK_ROOT)
    except ValueError:
        rel = Path(path.name)
    backup_path = BACKUP_ROOT / timestamp / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_dict_writer(handle, fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    shutil.move(str(temp_path), str(path))
    print(f"backup={backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
