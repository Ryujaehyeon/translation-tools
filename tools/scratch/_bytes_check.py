#!/usr/bin/env python3
"""Check actual bytes in YML files to distinguish \\n (2 bytes) vs \\\\n (3 bytes)."""
from pathlib import Path

root = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack")

# Check asteroid industry
yml = root / "localisation/korean/giga_asteroid_industry_l_korean.yml"
raw = yml.read_bytes()
# backslash = 0x5C, n = 0x6E
# \n in file = 5C 6E (two bytes) = good Stellaris newline
# \\n in file = 5C 5C 6E (three bytes) = literal \n shown in game
double_bs = raw.count(b'\\\\n')
single_bs = raw.count(b'\\n') - double_bs * 2  # subtract matches from double

print(f"giga_asteroid_industry_l_korean.yml:")
print(f"  double-escaped (\\\\n, 3 bytes) — shows as literal in game: {double_bs}")
print(f"  single (\\n, 2 bytes) — correct Stellaris newline: {single_bs}")

# Check original CSV
csv = root / "maintenance/translation_keys/gigastructural_engineering_more_4_3__1121692237/giga_asteroid_industry_key.csv"
raw_csv = csv.read_bytes()
double_bs_csv = raw_csv.count(b'\\\\n')
single_bs_csv = raw_csv.count(b'\\n') - double_bs_csv * 2
print(f"\ngiga_asteroid_industry_key.csv:")
print(f"  double-escaped (\\\\n): {double_bs_csv}")
print(f"  single (\\n): {single_bs_csv}")
