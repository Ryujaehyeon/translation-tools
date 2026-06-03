#!/usr/bin/env python3
"""Prepare and apply manual resolutions for conflicting localisation translations.

This tool has two modes:

- --prepare creates a CSV containing the English source line plus all conflicting
  Korean candidates. It does not edit localisation files.
- --apply reads that CSV after the user fills new_korean_value and patches only
  those filled rows, backing up touched files first.

It intentionally does not call an online translation service or choose a
conflict winner automatically. The user stays in control of the final Korean
line.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from tool_config import csv_dict_writer, read_text, resolve_pack_path

DEFAULT_WORKSHOP_ROOT = Path(r"D:\Program Files (x86)\Steam\steamapps\workshop\content\281990")
TOOL_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = Path(__file__).resolve().parents[2] / "integrated_korean_translation_pack"
ENTRY_RE = re.compile(r"^(\s*)([^:#\s][^:]*)\s*:\s*(?:(-?\d+)\s*)?(.*)$")
HEADER_RE = re.compile(r"^\s*l_[A-Za-z_]+:\s*$")
CSV_FIELDS = [
    "target_file",
    "key",
    "english_value",
    "conflict_values",
    "conflict_sources",
    "new_korean_value",
    "notes",
]


def parse_args() -> argparse.Namespace:
    """Parse conflict preparation/application mode and paths."""
    parser = argparse.ArgumentParser(
        description="Prepare/apply manual Korean translations for conflicting localisation keys."
    )
    parser.add_argument("mod_id", help="Steam workshop mod id, for example 1121692237")
    parser.add_argument(
        "csv_dir",
        help="Directory containing per-file *_key.csv files. Relative paths are resolved from the translation pack root.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--prepare", action="store_true", help="Create a conflict resolution work CSV."
    )
    mode.add_argument(
        "--apply", metavar="CSV", help="Apply filled new_korean_value rows from a work CSV."
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--report-dir",
        default="maintenance/reports/conflict_resolution",
        help="Directory for reports. Relative paths are resolved from the translation pack root.",
    )
    return parser.parse_args()



def write_text(path: Path, text: str) -> None:
    """Write patched localisation text with BOM and LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")




def english_source_root(mod_root: Path) -> Path:
    """Return the English localisation root for both Stellaris mod layouts."""
    localisation_root = mod_root / "localisation"
    nested_root = localisation_root / "english"
    if nested_root.is_dir():
        return nested_root
    if localisation_root.is_dir() and any(localisation_root.glob("*_l_english.yml")):
        return localisation_root
    return nested_root


def parse_entry_line(line: str) -> tuple[str, str | None, str] | None:
    """Parse one localisation line into key/version/value, ignoring headers."""
    if HEADER_RE.match(line):
        return None
    match = ENTRY_RE.match(line)
    if not match:
        return None
    return match.group(2).strip(), match.group(3), match.group(4)


def render_entry(key: str, version: str | None, value: str) -> str:
    """Render a localisation line while preserving :0 vs bare-colon style."""
    if version is None:
        return f" {key}: {value}".rstrip()
    return f" {key}:{version} {value}".rstrip()


def parse_entries(path: Path) -> dict[str, tuple[str | None, str, str]]:
    """Parse a file into key -> (version, value, rendered_line)."""
    entries: dict[str, tuple[str | None, str, str]] = {}
    for line in read_text(path).splitlines():
        parsed = parse_entry_line(line)
        if not parsed:
            continue
        key, version, value = parsed
        entries[key] = (version, value, render_entry(key, version, value))
    return entries


def read_keys(csv_path: Path) -> list[str]:
    """Read ordered keys from a key CSV, deduplicating repeated rows."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "key" not in reader.fieldnames:
            raise ValueError(f"{csv_path}: CSV must have a 'key' column")
        keys: list[str] = []
        seen: set[str] = set()
        for row in reader:
            key = (row.get("key") or "").strip()
            if key and key not in seen:
                keys.append(key)
                seen.add(key)
        return keys


def target_path_for(csv_path: Path, csv_root: Path, korean_root: Path) -> Path:
    """Map a key CSV path to its target Korean yml file."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    if not name.endswith("_key.csv"):
        raise ValueError(f"CSV file name must end with _key.csv: {csv_path}")
    return korean_root / relative.parent / (name[: -len("_key.csv")] + "_l_korean.yml")


def source_path_for(csv_path: Path, csv_root: Path, mod_root: Path) -> Path:
    """Map a key CSV path back to its source English yml file."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    if not name.endswith("_key.csv"):
        raise ValueError(f"CSV file name must end with _key.csv: {csv_path}")
    source_name = name[: -len("_key.csv")] + "_l_english.yml"
    localisation_root = mod_root / "localisation"
    if relative.parts and relative.parts[0] == "replace":
        rest = Path(*relative.parts[1:]).parent / source_name
        candidates = [
            localisation_root / "replace" / rest,
            localisation_root / "replace" / "english" / rest,
        ]
    else:
        rest = relative.parent / source_name
        candidates = [
            localisation_root / "english" / rest,
            localisation_root / rest,
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def build_korean_conflicts(korean_root: Path) -> dict[str, list[dict[str, object]]]:
    """Collect only keys that have multiple distinct Korean rendered values."""
    values_by_key: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in sorted(korean_root.rglob("*_l_korean.yml")):
        rel_path = str(path.relative_to(korean_root))
        for key, (_, _, rendered) in parse_entries(path).items():
            values_by_key[key][rendered].add(rel_path)

    conflicts: dict[str, list[dict[str, object]]] = {}
    for key, values in values_by_key.items():
        if len(values) <= 1:
            continue
        conflicts[key] = [
            {"value": value, "sources": sorted(sources)}
            for value, sources in sorted(values.items())
        ]
    return conflicts


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write the conflict-resolution work CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_dict_writer(handle, CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict) -> None:
    """Write a JSON report for prepare/apply mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def prepare(
    args: argparse.Namespace,
    timestamp: str,
    mod_root: Path,
    csv_root: Path,
    korean_root: Path,
    report_root: Path,
) -> int:
    """Create the manual conflict-resolution CSV without editing yml files."""
    conflicts = build_korean_conflicts(korean_root)
    rows: list[dict[str, object]] = []

    for csv_path in sorted(csv_root.rglob("*_key.csv")):
        source_path = source_path_for(csv_path, csv_root, mod_root)
        target_path = target_path_for(csv_path, csv_root, korean_root)
        source_entries = parse_entries(source_path) if source_path.is_file() else {}
        rel_target = str(target_path.relative_to(korean_root))

        for key in read_keys(csv_path):
            if key not in conflicts:
                continue
            rows.append(
                {
                    "target_file": rel_target,
                    "key": key,
                    "english_value": source_entries.get(key, ("", "", ""))[2],
                    "conflict_values": json.dumps(
                        [item["value"] for item in conflicts[key]], ensure_ascii=False
                    ),
                    "conflict_sources": json.dumps(
                        [item["sources"] for item in conflicts[key]], ensure_ascii=False
                    ),
                    "new_korean_value": "",
                    "notes": "",
                }
            )

    work_csv = report_root / f"conflict_resolution_{timestamp}.csv"
    report_path = report_root / f"conflict_resolution_report_{timestamp}.json"
    write_csv(work_csv, rows)
    write_json(
        report_path,
        {
            "mode": "prepare",
            "mod_id": args.mod_id,
            "csv_dir": str(csv_root),
            "work_csv": str(work_csv),
            "conflict_rows": len(rows),
        },
    )

    print(f"conflict_rows={len(rows)}")
    print(f"work_csv={work_csv}")
    print(f"report={report_path}")
    return 0


def normalise_new_value(
    key: str, source_entry: tuple[str | None, str, str] | None, raw_value: str
) -> tuple[str | None, str | None]:
    """Convert new_korean_value into a full localisation line.

    The user may type either a bare Korean value or a complete `key:0 "..."`.
    Bare values inherit the source entry's version style when possible.
    """
    raw_value = raw_value.strip()
    if not raw_value:
        return None, "empty new_korean_value"

    parsed = parse_entry_line(raw_value)
    if parsed:
        parsed_key, _, _ = parsed
        if parsed_key != key:
            return None, f"new line key mismatch: expected {key}, got {parsed_key}"
        return raw_value, None

    version = source_entry[0] if source_entry else "0"
    value = raw_value
    if not (value.startswith('"') and value.endswith('"')):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        value = f'"{escaped}"'
    return render_entry(key, version, value), None


def read_work_rows(path: Path) -> list[dict[str, str]]:
    """Read a filled conflict-resolution CSV and validate required columns."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in CSV_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def replace_or_insert_entry(path: Path, key: str, new_line: str, key_order: list[str]) -> None:
    """Replace an existing key or insert it according to CSV key order."""
    lines = read_text(path).splitlines() if path.exists() else ["l_korean:"]

    for index, line in enumerate(lines):
        parsed = parse_entry_line(line)
        if parsed and parsed[0] == key:
            lines[index] = new_line
            write_text(path, "\n".join(lines) + "\n")
            return

    order_index = key_order.index(key) if key in key_order else len(key_order)
    insert_at = len(lines)

    previous_keys = set(key_order[:order_index])
    next_keys = set(key_order[order_index + 1 :])
    for index, line in enumerate(lines):
        parsed = parse_entry_line(line)
        if not parsed:
            continue
        if parsed[0] in previous_keys:
            insert_at = index + 1
        elif parsed[0] in next_keys:
            insert_at = index
            break

    lines.insert(insert_at, new_line)
    write_text(path, "\n".join(lines) + "\n")


def validate_target(path: Path, applied_keys: list[str]) -> list[str]:
    """Lightly validate a patched target file after applying rows."""
    errors: list[str] = []
    header_count = 0
    entries: dict[str, str] = {}
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if HEADER_RE.match(line):
            header_count += 1
            continue
        parsed = parse_entry_line(line)
        if not parsed:
            errors.append(f"line {line_number} does not match localisation entry format")
            continue
        entries[parsed[0]] = line

    if header_count != 1:
        errors.append(f"expected exactly one l_korean header, found {header_count}")
    for key in applied_keys:
        if key not in entries:
            errors.append(f"applied key missing after write: {key}")
    return errors


def apply_resolutions(
    args: argparse.Namespace,
    timestamp: str,
    mod_root: Path,
    csv_root: Path,
    korean_root: Path,
    report_root: Path,
) -> int:
    """Apply filled conflict-resolution rows with backups and reporting."""
    work_csv = resolve_pack_path(args.apply)
    rows = read_work_rows(work_csv)
    backup_root = TOOL_ROOT / "maintenance" / "backups" / f"conflict_resolution_{timestamp}"
    source_by_target: dict[str, Path] = {}
    csv_by_target: dict[str, Path] = {}
    keys_by_target: dict[str, list[str]] = {}

    for csv_path in sorted(csv_root.rglob("*_key.csv")):
        target_path = target_path_for(csv_path, csv_root, korean_root)
        rel_target = str(target_path.relative_to(korean_root))
        source_by_target[rel_target] = source_path_for(csv_path, csv_root, mod_root)
        csv_by_target[rel_target] = csv_path
        keys_by_target[rel_target] = read_keys(csv_path)

    applied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    touched_files: set[str] = set()
    backed_up_files: set[str] = set()

    for row in rows:
        rel_target = (row.get("target_file") or "").strip()
        key = (row.get("key") or "").strip()
        raw_new_value = (row.get("new_korean_value") or "").strip()
        if not raw_new_value:
            skipped.append(
                {"target_file": rel_target, "key": key, "reason": "new_korean_value is empty"}
            )
            continue
        if rel_target not in keys_by_target:
            errors.append(
                {
                    "target_file": rel_target,
                    "key": key,
                    "error": "target_file is not part of csv_dir",
                }
            )
            continue
        if key not in keys_by_target[rel_target]:
            errors.append(
                {"target_file": rel_target, "key": key, "error": "key is not part of target CSV"}
            )
            continue

        target_path = korean_root / rel_target
        source_entries = (
            parse_entries(source_by_target[rel_target])
            if source_by_target[rel_target].is_file()
            else {}
        )
        new_line, error = normalise_new_value(key, source_entries.get(key), raw_new_value)
        if error or new_line is None:
            errors.append(
                {
                    "target_file": rel_target,
                    "key": key,
                    "error": error or "unknown normalisation error",
                }
            )
            continue

        if target_path.exists() and rel_target not in backed_up_files:
            backup_path = backup_root / rel_target
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_path, backup_path)
            backed_up_files.add(rel_target)

        replace_or_insert_entry(target_path, key, new_line, keys_by_target[rel_target])
        touched_files.add(rel_target)
        applied.append({"target_file": rel_target, "key": key})

    validation_errors: dict[str, list[str]] = {}
    applied_keys_by_file: dict[str, list[str]] = defaultdict(list)
    for item in applied:
        applied_keys_by_file[item["target_file"]].append(item["key"])
    for rel_target, keys in applied_keys_by_file.items():
        issues = validate_target(korean_root / rel_target, keys)
        if issues:
            validation_errors[rel_target] = issues

    report_path = report_root / f"conflict_resolution_report_{timestamp}.json"
    write_json(
        report_path,
        {
            "mode": "apply",
            "mod_id": args.mod_id,
            "work_csv": str(work_csv),
            "applied": applied,
            "skipped": skipped,
            "errors": errors,
            "validation_errors": validation_errors,
            "touched_files": sorted(touched_files),
            "backup_dir": str(backup_root) if backed_up_files else "",
        },
    )

    print(f"applied={len(applied)}")
    print(f"skipped={len(skipped)}")
    print(f"errors={len(errors)}")
    print(f"validation_error_files={len(validation_errors)}")
    print(f"report={report_path}")
    if backed_up_files:
        print(f"backup_dir={backup_root}")
    return 1 if errors or validation_errors else 0


def main() -> int:
    """Dispatch to prepare or apply mode after validating common paths."""
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mod_root = Path(args.workshop_root) / args.mod_id
    csv_root = resolve_pack_path(args.csv_dir)
    korean_root = PACK_ROOT / "localisation" / "korean"
    report_root = resolve_pack_path(args.report_dir)

    if not (mod_root / "localisation").is_dir():
        raise SystemExit(f"Localisation directory not found: {mod_root / 'localisation'}")
    if not csv_root.is_dir():
        raise SystemExit(f"CSV directory not found: {csv_root}")
    if not korean_root.is_dir():
        raise SystemExit(f"Korean localisation directory not found: {korean_root}")

    if args.prepare:
        return prepare(args, timestamp, mod_root, csv_root, korean_root, report_root)
    return apply_resolutions(args, timestamp, mod_root, csv_root, korean_root, report_root)


if __name__ == "__main__":
    raise SystemExit(main())
