#!/usr/bin/env python3
"""Check or normalize UTF-8 BOM on project text outputs.

Project standard:
- CSV/YML/JSON/MD generated outputs: UTF-8 with BOM
- Python/PowerShell scripts: UTF-8, BOM optional
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from tool_config import translation_keys_root_arg

PACK_ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"
DEFAULT_PATTERNS = ("*.csv", "*.yml", "*.json", "*.md")
DEFAULT_ROOTS = (translation_keys_root_arg(), "localisation")
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "utf8_bom"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or add UTF-8 BOM for generated text files.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan. Defaults to translation keys and localisation.",
    )
    parser.add_argument("--fix", action="store_true", help="Add BOM to files missing it.")
    parser.add_argument("--pattern", action="append", default=[], help="Glob pattern. Can repeat.")
    return parser.parse_args()


def iter_files(paths: list[str], patterns: tuple[str, ...]):
    roots = [
        Path(raw) if Path(raw).is_absolute() else PACK_ROOT / raw
        for raw in (paths or list(DEFAULT_ROOTS))
    ]
    for root in roots:
        if root.is_file():
            yield root
        elif root.is_dir():
            for pattern in patterns:
                yield from root.rglob(pattern)


def has_bom(path: Path) -> bool:
    return path.read_bytes()[:3] == BOM


def add_bom(path: Path, timestamp: str) -> Path:
    try:
        rel = path.relative_to(PACK_ROOT)
    except ValueError:
        rel = Path(path.name)
    backup = BACKUP_ROOT / timestamp / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    data = path.read_bytes()
    if not data.startswith(BOM):
        path.write_bytes(BOM + data)
    return backup


def main() -> int:
    args = parse_args()
    patterns = tuple(args.pattern) if args.pattern else DEFAULT_PATTERNS
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    scanned = 0
    missing: list[Path] = []
    fixed: list[Path] = []
    for path in sorted(set(iter_files(args.paths, patterns))):
        if not path.is_file():
            continue
        scanned += 1
        if not has_bom(path):
            missing.append(path)
            if args.fix:
                add_bom(path, timestamp)
                fixed.append(path)

    print(f"scanned={scanned}")
    print(f"missing_bom={len(missing)}")
    print(f"fixed={len(fixed)}")
    for path in missing[:100]:
        print(path.relative_to(PACK_ROOT) if path.is_relative_to(PACK_ROOT) else path)
    return 1 if missing and not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
