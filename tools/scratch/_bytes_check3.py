#!/usr/bin/env python3
"""Find YML files that have triple-byte \\\\n with full paths."""
from pathlib import Path

root = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack")
yml_root = root / "localisation/korean"

results = []
for f in yml_root.rglob("*.yml"):
    if ".bak" in f.name:
        continue
    raw = f.read_bytes()
    n = raw.count(b'\\\\n')
    if n > 0:
        results.append((n, str(f.relative_to(yml_root))))

results.sort(reverse=True)
for n, path in results:
    print(f"{n:4d}  {path}")
print(f"\ntotal: {sum(n for n,_ in results)}")
