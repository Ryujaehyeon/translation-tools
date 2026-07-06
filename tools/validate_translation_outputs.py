#!/usr/bin/env python3
"""Validate generated Korean localisation outputs and write fix-up worklists.

This tool is read-only for localisation files. It checks whether the generated
`localisation/korean` tree matches the per-file key CSV tree and emits worklist
CSVs for humans or later scripts:

- missing_keys: keys from CSV that are not present in the target Korean file
- conflict_keys: keys that exist with multiple distinct Korean values
- format_issues: malformed localisation or CSV rows
- extra_keys: keys in target files that are not listed in the CSV

Use this after export_localisation.py to see what still needs manual attention.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from csv_io import write_json
from tool_config import (
    PACK_ROOT as _TOOL_CONFIG_PACK_ROOT,
)
from tool_config import (
    csv_dict_writer,
    read_text,
    resolve_pack_path,
)
from tool_config import (
    workshop_root as _configured_workshop_root,
)
from yml_localisation import HEADER_RE, parse_entry

DEFAULT_WORKSHOP_ROOT = _configured_workshop_root()
TOOL_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = _TOOL_CONFIG_PACK_ROOT.parent / "integrated_korean_translation_pack"


def parse_args() -> argparse.Namespace:
    """Parse the mod id, key CSV tree, and validation report directory."""
    parser = argparse.ArgumentParser(
        description="Validate Korean localisation files against per-source-file key CSVs."
    )
    parser.add_argument("mod_id", help="Steam workshop mod id, for example 1121692237")
    parser.add_argument(
        "csv_dir",
        help="Directory containing per-file *_key.csv files. Relative paths are resolved from the translation pack root.",
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--report-dir",
        default="maintenance/reports/validation",
        help="Directory for validation outputs. Relative paths are resolved from the translation pack root.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Override the localisation/korean directory to validate against. Relative paths resolved from pack root.",
    )
    return parser.parse_args()



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
    for source_root, csv_prefix, recursive in candidates:
        if not source_root.is_dir():
            continue
        files = sorted(
            source_root.rglob("*_l_english.yml")
            if recursive
            else source_root.glob("*_l_english.yml")
        )
        for source_file in files:
            resolved = source_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            sources.append((source_file, source_root, csv_prefix))
    return sources


def parse_localisation_file(path: Path) -> tuple[dict[str, str], list[dict[str, object]], int]:
    """Parse one localisation file and collect format issues.

    Returns:
    - entries: key -> rendered localisation line
    - issues: rows suitable for format_issues CSV
    - header_count: number of l_* headers found
    """
    entries: dict[str, str] = {}
    issues: list[dict[str, object]] = []
    header_count = 0

    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if HEADER_RE.match(line):
            header_count += 1
            continue

        entry = parse_entry(line)
        if entry is not None:
            key = entry.key.strip()
            version = entry.version
            value = entry.value
            if version is None:
                entries[key] = f" {key}: {value}".rstrip()
            else:
                entries[key] = f" {key}:{version} {value}".rstrip()
            continue

        issues.append(
            {
                "file": str(path),
                "line_number": line_number,
                "line": line,
                "issue": "line does not match localisation entry format",
            }
        )

    return entries, issues, header_count


def read_keys(csv_path: Path) -> tuple[list[str], list[dict[str, object]]]:
    """Read ordered keys from a key CSV and report CSV-level issues."""
    issues: list[dict[str, object]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "key" not in reader.fieldnames:
            issues.append(
                {
                    "file": str(csv_path),
                    "line_number": 1,
                    "line": ",".join(reader.fieldnames or []),
                    "issue": "CSV header must contain a 'key' column",
                }
            )
            return [], issues

        keys: list[str] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            key = (row.get("key") or "").strip()
            if not key:
                issues.append(
                    {
                        "file": str(csv_path),
                        "line_number": row_number,
                        "line": "",
                        "issue": "empty key in CSV",
                    }
                )
                continue
            if key in seen:
                issues.append(
                    {
                        "file": str(csv_path),
                        "line_number": row_number,
                        "line": key,
                        "issue": "duplicate key in CSV",
                    }
                )
                continue
            keys.append(key)
            seen.add(key)
    return keys, issues


def csv_path_for(
    source_file: Path, source_root: Path, csv_root: Path, csv_prefix: Path = Path()
) -> Path:
    """Map a source English yml file to its expected key CSV path."""
    relative = source_file.relative_to(source_root)
    name = relative.name
    if name.endswith("_l_english.yml"):
        name = name[: -len("_l_english.yml")] + "_key.csv"
    else:
        name = relative.stem + "_key.csv"
    return csv_root / csv_prefix / relative.parent / name


def source_path_for(csv_path: Path, csv_root: Path, mod_root: Path) -> Path:
    """Map a key CSV path back to its source English yml file."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    source_name = (
        name[: -len("_key.csv")] + "_l_english.yml"
        if name.endswith("_key.csv")
        else relative.stem + "_l_english.yml"
    )
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


def target_path_for(csv_path: Path, csv_root: Path, korean_root: Path) -> Path:
    """Map a key CSV path to its generated Korean yml file."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    if not name.endswith("_key.csv"):
        return korean_root / relative.parent / (relative.stem + "_l_korean.yml")
    return korean_root / relative.parent / (name[: -len("_key.csv")] + "_l_korean.yml")


def build_korean_value_index(korean_root: Path) -> dict[str, list[dict[str, object]]]:
    """Find keys with multiple distinct rendered Korean values and sources."""
    values_by_key: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in sorted(korean_root.rglob("*_l_korean.yml")):
        entries, _, _ = parse_localisation_file(path)
        rel_path = str(path.relative_to(korean_root))
        for key, rendered in entries.items():
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


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    """Write a UTF-8 BOM CSV worklist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_dict_writer(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    """Run validation and emit all worklist files."""
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mod_root = Path(args.workshop_root) / args.mod_id
    csv_root = resolve_pack_path(args.csv_dir)
    if args.output_root:
        korean_root = resolve_pack_path(args.output_root)
    else:
        # --output-root 미지정 시 integrated_korean_translation_pack 폴더로 폴백.
        # run_pipeline.py는 항상 --output-root를 명시해서 전달한다.
        # 단독 실행 시에는 --output-root를 직접 지정할 것.
        korean_root = PACK_ROOT / "localisation" / "korean"
        print(f"[경고] --output-root 미지정: {korean_root} 를 검증합니다.", flush=True)
    report_root = resolve_pack_path(args.report_dir)

    if not (mod_root / "localisation").is_dir():
        raise SystemExit(f"Localisation directory not found: {mod_root / 'localisation'}")
    if not csv_root.is_dir():
        raise SystemExit(f"CSV directory not found: {csv_root}")
    if not korean_root.is_dir():
        raise SystemExit(f"Korean localisation directory not found: {korean_root}")

    source_files = discover_english_sources(mod_root)
    csv_files = sorted(csv_root.rglob("*_key.csv"))
    expected_csv_paths = {
        csv_path_for(path, root, csv_root, prefix) for path, root, prefix in source_files
    }
    actual_csv_paths = set(csv_files)

    format_issues: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []
    conflict_rows: list[dict[str, object]] = []
    extra_rows: list[dict[str, object]] = []
    missing_target_files: list[str] = []
    missing_csv_files = sorted(
        str(path.relative_to(csv_root)) for path in expected_csv_paths - actual_csv_paths
    )
    extra_csv_files = sorted(
        str(path.relative_to(csv_root)) for path in actual_csv_paths - expected_csv_paths
    )

    global_conflicts = build_korean_value_index(korean_root)

    for csv_path in csv_files:
        source_path = source_path_for(csv_path, csv_root, mod_root)
        target_path = target_path_for(csv_path, csv_root, korean_root)
        rel_target = str(target_path.relative_to(korean_root))

        keys, csv_issues = read_keys(csv_path)
        format_issues.extend(csv_issues)

        source_entries: dict[str, str] = {}
        if source_path.is_file():
            source_entries, source_issues, _ = parse_localisation_file(source_path)
            format_issues.extend(source_issues)

        if not target_path.is_file():
            missing_target_files.append(rel_target)
            for key in keys:
                missing_rows.append(
                    {
                        "target_file": rel_target,
                        "key": key,
                        "english_value": source_entries.get(key, ""),
                    }
                )
            continue

        target_entries, target_issues, header_count = parse_localisation_file(target_path)
        format_issues.extend(target_issues)
        if header_count != 1:
            format_issues.append(
                {
                    "file": str(target_path),
                    "line_number": 1,
                    "line": "",
                    "issue": f"expected exactly one l_korean header, found {header_count}",
                }
            )

        key_set = set(keys)
        target_key_set = set(target_entries)

        for key in keys:
            if key not in target_entries:
                missing_rows.append(
                    {
                        "target_file": rel_target,
                        "key": key,
                        "english_value": source_entries.get(key, ""),
                    }
                )
            if key in global_conflicts:
                for item in global_conflicts[key]:
                    conflict_rows.append(
                        {
                            "target_file": rel_target,
                            "key": key,
                            "value": item["value"],
                            "sources": ";".join(item["sources"]),
                        }
                    )

        for key in sorted(target_key_set - key_set):
            extra_rows.append({"target_file": rel_target, "key": key})

    validation_report_path = report_root / f"validation_report_{timestamp}.json"
    missing_csv_path = report_root / f"missing_keys_{timestamp}.csv"
    conflict_csv_path = report_root / f"conflict_keys_{timestamp}.csv"
    format_csv_path = report_root / f"format_issues_{timestamp}.csv"
    extra_csv_path = report_root / f"extra_keys_{timestamp}.csv"

    report = {
        "mod_id": args.mod_id,
        "source_root": str(mod_root / "localisation"),
        "csv_root": str(csv_root),
        "korean_root": str(korean_root),
        "source_files": len(source_files),
        "csv_files": len(csv_files),
        "source_csv_file_counts_match": len(source_files) == len(csv_files),
        "missing_csv_files": missing_csv_files,
        "extra_csv_files": extra_csv_files,
        "missing_target_files": missing_target_files,
        "missing_keys": len(missing_rows),
        "conflict_key_rows": len(conflict_rows),
        "extra_keys": len(extra_rows),
        "format_issues": len(format_issues),
        "outputs": {
            "validation_report": str(validation_report_path),
            "missing_keys_csv": str(missing_csv_path),
            "conflict_keys_csv": str(conflict_csv_path),
            "format_issues_csv": str(format_csv_path),
            "extra_keys_csv": str(extra_csv_path),
        },
    }

    write_json(validation_report_path, report)
    write_csv(missing_csv_path, ["target_file", "key", "english_value"], missing_rows)
    write_csv(conflict_csv_path, ["target_file", "key", "value", "sources"], conflict_rows)
    write_csv(format_csv_path, ["file", "line_number", "line", "issue"], format_issues)
    write_csv(extra_csv_path, ["target_file", "key"], extra_rows)

    print(f"source_files={len(source_files)}")
    print(f"csv_files={len(csv_files)}")
    print(f"source_csv_file_counts_match={report['source_csv_file_counts_match']}")
    print(f"missing_target_files={len(missing_target_files)}")
    print(f"missing_keys={len(missing_rows)}")
    print(f"conflict_key_rows={len(conflict_rows)}")
    print(f"extra_keys={len(extra_rows)}")
    print(f"format_issues={len(format_issues)}")
    print(f"report={validation_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
