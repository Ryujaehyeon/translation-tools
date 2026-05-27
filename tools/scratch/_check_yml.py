#!/usr/bin/env python3
"""Check if \\n in YML comes from CSV or from existing Korean translation files."""
from pathlib import Path

root = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack")

# Check giga_l_korean.yml first few lines that have \\n
yml = root / "localisation/korean/giga_l_korean.yml"
lines = yml.read_text(encoding="utf-8-sig").splitlines()
count = 0
for i, line in enumerate(lines):
    if chr(92) + "n" in line:
        print(f"L{i+1}: {line[:120]}")
        count += 1
        if count >= 5:
            break
print(f"... ({yml.stat().st_size} bytes, {len(lines)} lines total)")
