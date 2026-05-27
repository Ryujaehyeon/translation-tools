#!/usr/bin/env python3
"""Re-export all mods to fix the \\n double-escape issue."""
import subprocess
import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
AUTO_KEYS = PACK_ROOT / "maintenance" / "translation_keys"
PYTHON = sys.executable

mods = []
for d in sorted(AUTO_KEYS.iterdir()):
    if not d.is_dir():
        continue
    parts = d.name.rsplit("__", 1)
    if len(parts) == 2 and parts[1].isdigit():
        mods.append((parts[1], d.name))

print(f"Found {len(mods)} mods to export")
ok = 0
fail = 0
for mod_id, dir_name in mods:
    csv_dir = f"maintenance/translation_keys/{dir_name}"
    result = subprocess.run(
        [PYTHON, "tools/export_localisation.py", mod_id, csv_dir],
        cwd=PACK_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        lines = {k: v for k, v in (l.split("=", 1) for l in result.stdout.strip().splitlines() if "=" in l)}
        updated = lines.get("updated_files", "?")
        print(f"  OK  {mod_id}  updated={updated}")
        ok += 1
    else:
        print(f"  FAIL {mod_id}: {result.stderr.strip()[:120]}")
        fail += 1

print(f"\nDone: {ok} ok, {fail} failed")
