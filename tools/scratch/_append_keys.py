#!/usr/bin/env python3
"""Append missing modifier keys to a CSV file."""
import csv
from pathlib import Path

csv_path = Path(r"c:\Users\yjhg1\Documents\Paradox Interactive\Stellaris\mod\translation-tools\maintenance\translation_keys\unique_ascension_perks_4_3_dev_branch__2811428998\unique_ascension_perks_key.csv")

# Check which keys are already in the CSV
existing = set()
with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing.add(row["key"])

new_keys = [
    ("mod_ship_military_minor_artifacts_cost_mult", "Military Ship $minor_artifacts$ Cost", "군함 $minor_artifacts$ 비용"),
    ("mod_ship_colonizer_minor_artifacts_cost_mult", "Colonizer Ship $minor_artifacts$ Cost", "식민선 $minor_artifacts$ 비용"),
    ("mod_stations_minor_artifacts_cost_mult", "Station $minor_artifacts$ Cost", "스테이션 $minor_artifacts$ 비용"),
]

to_add = [(k, en, ko) for k, en, ko in new_keys if k not in existing]
if not to_add:
    print("All keys already present.")
else:
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        for key, en, ko in to_add:
            f.write(f'{key},"""{en}""","""{ko}"""\r\n')
            print(f"Added: {key}")
    print(f"Done: added {len(to_add)} keys")
