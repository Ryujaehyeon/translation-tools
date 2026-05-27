#!/usr/bin/env python3
"""Find YML files that have triple-byte \\\\n (double backslash + n)."""
from pathlib import Path

root = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack")
yml_root = root / "localisation/korean"

results = []
for f in yml_root.rglob("*.yml"):
    if ".bak" in f.name:
        continue
    raw = f.read_bytes()
    n = raw.count(b'\\\\n')  # 3 bytes: 0x5C 0x5C 0x6E
    if n > 0:
        results.append((n, f.name))

results.sort(reverse=True)
for n, name in results[:20]:
    print(f"{n:4d}  {name}")
print(f"\ntotal files: {len(results)}, total occurrences: {sum(n for n,_ in results)}")
