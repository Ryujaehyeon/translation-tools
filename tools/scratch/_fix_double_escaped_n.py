#!/usr/bin/env python3
"""Fix double-escaped \\n (0x5C 0x5C 0x6E) -> \\n (0x5C 0x6E) in YML files."""
from pathlib import Path
import shutil
from datetime import datetime

root = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack")
yml_root = root / "localisation/korean"
backup_root = root / "maintenance/backups" / f"fix_double_escaped_n_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

fixed = 0
for f in yml_root.rglob("*.yml"):
    if ".bak" in f.name:
        continue
    raw = f.read_bytes()
    new_raw = raw.replace(b"\\\\n", b"\\n")
    if new_raw != raw:
        # Backup
        rel = f.relative_to(yml_root)
        bp = backup_root / rel
        bp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, bp)
        f.write_bytes(new_raw)
        n = raw.count(b"\\\\n")
        print(f"Fixed {n:4d} occurrences: {f.name}")
        fixed += 1

print(f"\nFixed {fixed} files. Backup: {backup_root}")
