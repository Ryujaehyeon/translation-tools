#!/usr/bin/env python3
"""Extract Stellaris localisation keys into one CSV per source file.

This is the first step of the workflow. It reads a workshop mod's English
localisation tree and mirrors that tree into a key CSV directory. It supports
both common layouts:

- `localisation/english/**/*_l_english.yml`
- `localisation/*_l_english.yml`
- `localisation/replace/english/**/*_l_english.yml`
- `localisation/replace/*_l_english.yml`

The CSV deliberately keeps three columns:

- key: the localisation key used by Stellaris scripts
- english_value: the raw English value from the source file
- korean_value: an optional manual translation override filled by the user

When a target CSV already exists, extraction merges by key by default: existing
rows stay in place, their `english_value` is refreshed from the current source,
their `korean_value` is preserved, and only new source keys are appended. This
keeps manual translation work stable while still tracking upstream mod updates.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path


DEFAULT_WORKSHOP_ROOT = Path(r"D:\Program Files (x86)\Steam\steamapps\workshop\content\281990")
PACK_ROOT = Path(__file__).resolve().parents[1]
ENTRY_RE = re.compile(r"^\s*([^:#\s][^:]*)\s*:\s*(?:(-?\d+)\s*)?(.*)$")
HEADER_RE = re.compile(r"^\s*l_[A-Za-z_]+:\s*$")


def parse_args() -> argparse.Namespace:
    """Parse the mod id and output directory for generated key CSVs."""
    parser = argparse.ArgumentParser(
        description="Extract localisation keys from a workshop mod's localisation/english files."
    )
    parser.add_argument("mod_id", help="Steam workshop mod id, for example 1121692237")
    parser.add_argument(
        "output_dir",
        help="CSV output directory. Relative paths are resolved from the translation pack root.",
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--report-dir",
        default="maintenance/reports/extraction",
        help="Directory for extraction reports. Relative paths are resolved from the translation pack root.",
    )
    parser.add_argument(
        "--no-preserve-korean",
        action="store_true",
        help="Do not preserve existing korean_value entries when regenerating CSVs.",
    )
    parser.add_argument(
        "--sync-source",
        action="store_true",
        help="Rewrite CSVs to match the current source files exactly, dropping keys no longer present.",
    )
    parser.add_argument(
        "--keep-existing-english",
        action="store_true",
        help="When merging, keep existing english_value for keys already present in an existing CSV.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    """Read Paradox localisation files while accepting an optional UTF-8 BOM."""
    return path.read_text(encoding="utf-8-sig")


def iter_localisation_entries(path: Path) -> list[tuple[str, str]]:
    """Return (key, english_value) pairs in source order, deduplicated by key.

    Stellaris localisation accepts both `key:0 "value"` and `key: "value"`.
    The regex keeps the text after the colon as english_value without trying to
    parse the quoted string contents; preserving raw syntax is safer here.
    """
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in read_text(path).splitlines():
        if HEADER_RE.match(line):
            continue
        match = ENTRY_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        english_value = match.group(3).strip() if match.group(3) else ""
        if key and key not in seen:
            entries.append((key, english_value))
            seen.add(key)
    return entries


def output_path_for(source_file: Path, source_root: Path, output_root: Path, output_prefix: Path = Path()) -> Path:
    """Map an English source yml path to the matching *_key.csv path."""
    relative = source_file.relative_to(source_root)
    stem = relative.name
    if stem.endswith("_l_english.yml"):
        stem = stem[: -len("_l_english.yml")] + "_key.csv"
    else:
        stem = relative.stem + "_key.csv"
    return output_root / output_prefix / relative.parent / stem


def resolve_pack_path(raw: str) -> Path:
    """Resolve relative paths from the translation pack root."""
    path = Path(raw)
    if path.is_absolute():
        return path
    return PACK_ROOT / path


def english_source_root(mod_root: Path) -> Path:
    """Return the English localisation root for both Stellaris mod layouts."""
    localisation_root = mod_root / "localisation"
    nested_root = localisation_root / "english"
    if nested_root.is_dir():
        return nested_root
    if localisation_root.is_dir() and any(localisation_root.glob("*_l_english.yml")):
        return localisation_root
    return nested_root


def discover_english_sources(mod_root: Path) -> list[tuple[Path, Path, Path]]:
    """Return source files with their root and CSV path prefix."""
    localisation_root = mod_root / "localisation"
    candidates: list[tuple[Path, Path, bool]] = [
        (localisation_root / "english", Path(), True),
        (localisation_root, Path(), False),
        (localisation_root / "replace" / "english", Path("replace"), True),
        (localisation_root / "replace", Path("replace"), False),
    ]
    sources: list[tuple[Path, Path, Path]] = []
    seen: set[Path] = set()
    for source_root, output_prefix, recursive in candidates:
        if not source_root.is_dir():
            continue
        files = sorted(source_root.rglob("*_l_english.yml") if recursive else source_root.glob("*_l_english.yml"))
        for source_file in files:
            resolved = source_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            sources.append((source_file, source_root, output_prefix))
    return sources


def read_existing_rows(csv_path: Path) -> list[dict[str, str]]:
    """Read existing CSV rows, returning an empty list for missing/bad files."""
    if not csv_path.is_file():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "key" not in reader.fieldnames:
            return []
        rows: list[dict[str, str]] = []
        for row in reader:
            key = (row.get("key") or "").strip()
            if not key:
                continue
            rows.append(
                {
                    "key": key,
                    "english_value": row.get("english_value") or "",
                    "korean_value": "" if row.get("korean_value") is None else row.get("korean_value") or "",
                }
            )
        return rows


def rows_for_sync(entries: list[tuple[str, str]], existing_rows: list[dict[str, str]], preserve_korean: bool) -> list[dict[str, str]]:
    """Return rows in source order, preserving existing Korean values."""
    korean_by_key = {row["key"]: row.get("korean_value", "") for row in existing_rows}
    return [
        {
            "key": key,
            "english_value": english_value,
            "korean_value": korean_by_key.get(key, "") if preserve_korean else "",
        }
        for key, english_value in entries
    ]


def rows_for_merge(
    entries: list[tuple[str, str]],
    existing_rows: list[dict[str, str]],
    preserve_korean: bool,
    keep_existing_english: bool,
) -> list[dict[str, str]]:
    """Keep existing rows and append only source keys absent from the CSV."""
    source_by_key = {key: english for key, english in entries}
    existing_keys: set[str] = set()
    merged: list[dict[str, str]] = []

    for row in existing_rows:
        key = row["key"]
        if key in existing_keys:
            continue
        existing_keys.add(key)
        english_value = row.get("english_value", "") if keep_existing_english else source_by_key.get(key, row.get("english_value", ""))
        merged.append(
            {
                "key": key,
                "english_value": english_value,
                "korean_value": row.get("korean_value", "") if preserve_korean else "",
            }
        )

    for key, english_value in entries:
        if key in existing_keys:
            continue
        merged.append({"key": key, "english_value": english_value, "korean_value": ""})
        existing_keys.add(key)

    return merged


def write_json(path: Path, payload: dict) -> None:
    """Write a UTF-8 BOM JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def main() -> int:
    """Generate all per-file key CSVs for one workshop mod."""
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mod_root = Path(args.workshop_root) / args.mod_id
    source_root = english_source_root(mod_root)
    output_root = resolve_pack_path(args.output_dir)
    report_root = resolve_pack_path(args.report_dir)

    source_files = discover_english_sources(mod_root)
    if not source_files:
        raise SystemExit(f"English localisation files not found under: {mod_root / 'localisation'}")
    written = 0
    total_keys = 0
    total_added = 0
    total_existing = 0
    total_stale = 0
    total_removed = 0
    total_preserved_korean = 0
    file_reports: list[dict[str, object]] = []

    for source_file, file_source_root, output_prefix in source_files:
        entries = iter_localisation_entries(source_file)
        csv_path = output_path_for(source_file, file_source_root, output_root, output_prefix)
        existing_rows = read_existing_rows(csv_path)
        preserve_korean = not args.no_preserve_korean
        new_keys = {key for key, _ in entries}
        old_keys = {row["key"] for row in existing_rows}
        added_keys = sorted(new_keys - old_keys)
        existing_source_keys = sorted(new_keys & old_keys)
        stale_keys = sorted(old_keys - new_keys)
        removed_keys = stale_keys if args.sync_source else []
        preserved_count = sum(1 for row in existing_rows if row["key"] in new_keys and row.get("korean_value") and preserve_korean)
        if args.sync_source:
            output_rows = rows_for_sync(entries, existing_rows, preserve_korean)
        else:
            output_rows = rows_for_merge(entries, existing_rows, preserve_korean, args.keep_existing_english)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            # korean_value is intentionally blank: it is the user's editable
            # column for manual translations or scripted translation output.
            writer.writerow(["key", "english_value", "korean_value"])
            for row in output_rows:
                writer.writerow([row["key"], row["english_value"], row["korean_value"]])
        written += 1
        total_keys += len(entries)
        total_added += len(added_keys)
        total_existing += len(existing_source_keys)
        total_stale += len(stale_keys)
        total_removed += len(removed_keys)
        total_preserved_korean += preserved_count
        file_reports.append(
            {
                "source_file": str(source_file.relative_to(mod_root / "localisation")),
                "source_root": str(file_source_root),
                "csv_file": str(csv_path.relative_to(output_root)),
                "keys": len(entries),
                "existing_source_keys": existing_source_keys,
                "added_keys": added_keys,
                "stale_keys": stale_keys,
                "removed_keys": removed_keys,
                "preserved_korean_values": preserved_count,
                "mode": "sync_source" if args.sync_source else "merge_existing",
            }
        )

    report_path = report_root / f"extract_localisation_keys_report_{timestamp}.json"
    write_json(
        report_path,
        {
            "mod_id": args.mod_id,
            "source_root": str(source_root),
            "output_root": str(output_root),
            "source_files": len(source_files),
            "csv_files": written,
            "keys": total_keys,
            "existing_source_keys": total_existing,
            "added_keys": total_added,
            "stale_keys": total_stale,
            "removed_keys": total_removed,
            "preserved_korean_values": total_preserved_korean,
            "mode": "sync_source" if args.sync_source else "merge_existing",
            "files": file_reports,
        },
    )

    print(f"source_files={len(source_files)}")
    print(f"csv_files={written}")
    print(f"keys={total_keys}")
    print(f"existing_source_keys={total_existing}")
    print(f"added_keys={total_added}")
    print(f"stale_keys={total_stale}")
    print(f"removed_keys={total_removed}")
    print(f"preserved_korean_values={total_preserved_korean}")
    print(f"mode={'sync_source' if args.sync_source else 'merge_existing'}")
    print(f"output_dir={output_root}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
