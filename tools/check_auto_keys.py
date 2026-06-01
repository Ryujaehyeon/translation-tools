"""auto_keys CSV와 원본 YML의 파일 구조·키·영문값 1:1 대응 검증.

사용:
    python tools/check_auto_keys.py
    python tools/check_auto_keys.py --mod gigastructural_engineering_more_4_3__1121692237
    python tools/check_auto_keys.py --mod-id 1121692237
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from tool_config import translation_keys_root

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
AUTO_KEYS_DIR = translation_keys_root()
MOD_DIR = PACK_ROOT.parent


def get_mod_id(folder_name: str) -> str | None:
    parts = folder_name.split("__")
    return parts[-1] if len(parts) >= 2 else None


def get_mod_path(mod_id: str) -> Path | None:
    mod_file = MOD_DIR / f"ugc_{mod_id}.mod"
    if mod_file.exists():
        content = mod_file.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'path="([^"]+)"', content)
        if m:
            return Path(m.group(1))
    return None


def parse_yml_keys(yml_path: Path) -> dict[str, str]:
    PATTERN = re.compile(r'^\s*([\w.\-]+):(?:\d+\s*|\s+)(".*)')
    LANG_HEADERS = {
        "l_english",
        "l_korean",
        "l_french",
        "l_german",
        "l_spanish",
        "l_russian",
        "l_polish",
        "l_braz_por",
        "l_simp_chinese",
    }
    result: dict[str, str] = {}
    try:
        for line in yml_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = PATTERN.match(line)
            if not m or m.group(1) in LANG_HEADERS:
                continue
            result[m.group(1)] = m.group(2).rstrip()
    except Exception as e:
        print(f"  [ERROR] YML 파싱 실패 {yml_path}: {e}")
    return result


def parse_csv_keys(csv_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = (row.get("key") or "").strip()
                if key:
                    result[key] = row.get("english_value") or ""
    except Exception as e:
        print(f"  [ERROR] CSV 파싱 실패 {csv_path}: {e}")
    return result


def check_mod(folder: str) -> None:
    mod_id = get_mod_id(folder)
    if not mod_id:
        print(f"[WARN] ID 추출 불가: {folder}")
        return

    mod_path = get_mod_path(mod_id)
    if not mod_path:
        print(f"[WARN] 경로 없음 (ID={mod_id}): {folder}")
        return

    loc_en = mod_path / "localisation" / "english"
    if not loc_en.is_dir():
        print(f"[WARN] localisation/english 없음: {mod_path}")
        return

    auto_key_folder = AUTO_KEYS_DIR / folder

    csv_map = {f.name[: -len("_key.csv")]: f for f in auto_key_folder.glob("*_key.csv")}
    yml_map = {f.name[: -len("_l_english.yml")]: f for f in loc_en.glob("*_l_english.yml")}

    missing_csv = sorted(set(yml_map) - set(csv_map))
    extra_csv = sorted(set(csv_map) - set(yml_map))

    print(f"\n{'=' * 70}")
    print(f"[모드] {folder}")
    print(f"  원본 YML: {len(yml_map)}개 / auto_keys CSV: {len(csv_map)}개")

    for b in missing_csv:
        print(f"  [파일 누락] {b}_key.csv")
    for b in extra_csv:
        print(f"  [파일 초과] {b}_key.csv")

    total_key_errors = 0
    for base in sorted(set(csv_map) & set(yml_map)):
        csv_keys = parse_csv_keys(csv_map[base])
        yml_keys = parse_yml_keys(yml_map[base])

        missing_keys = sorted(set(yml_keys) - set(csv_keys))
        extra_keys = sorted(set(csv_keys) - set(yml_keys))
        value_mismatches = [
            (k, yml_keys[k], csv_keys[k])
            for k in set(csv_keys) & set(yml_keys)
            if csv_keys[k] != yml_keys[k]
        ]

        if missing_keys or extra_keys or value_mismatches:
            total_key_errors += len(missing_keys) + len(extra_keys) + len(value_mismatches)
            print(f"\n  [파일] {base}_key.csv  (CSV={len(csv_keys)}키, YML={len(yml_keys)}키)")
            for k in missing_keys:
                print(f"    KEY 누락: {k}")
            for k in extra_keys:
                print(f"    KEY 초과: {k}")
            for k, yv, cv in value_mismatches[:10]:
                print(f"    값 불일치: {k}")
                print(f"      YML: {yv}")
                print(f"      CSV: {cv}")
            if len(value_mismatches) > 10:
                print(f"    ... 외 {len(value_mismatches) - 10}개 값 불일치")

    if not missing_csv and not extra_csv and total_key_errors == 0:
        print(f"  [OK] 파일 {len(csv_map)}개, 키 일치")


def main() -> None:
    parser = argparse.ArgumentParser(description="auto_keys CSV ↔ 원본 YML 구조 검증")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mod", metavar="FOLDER", help="특정 모드 폴더명 (예: gigastructural_...)")
    group.add_argument("--mod-id", metavar="ID", help="특정 모드 워크샵 ID (예: 1121692237)")
    args = parser.parse_args()

    folders = sorted(d.name for d in AUTO_KEYS_DIR.iterdir() if d.is_dir())

    if args.mod:
        folders = [f for f in folders if f == args.mod]
    elif args.mod_id:
        folders = [f for f in folders if f.endswith(f"__{args.mod_id}")]

    for folder in folders:
        check_mod(folder)

    print(f"\n검증 완료. 총 {len(folders)}개 모드 폴더 처리.")


if __name__ == "__main__":
    main()
