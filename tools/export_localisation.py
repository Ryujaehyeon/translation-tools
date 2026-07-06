#!/usr/bin/env python3
"""Build Korean localisation files from per-file key CSVs.

This tool turns the extracted key CSV tree into real `localisation/korean`
files. It prefers manual CSV translations, then existing Korean translations,
then English fallback text from the source mod. That last fallback avoids the
game showing only raw keys/modifier names when a Korean translation is missing.

The source mod can use `localisation/english/**/*_l_english.yml`,
`localisation/*_l_english.yml`, or replace-only files under
`localisation/replace`.

Use --dry-run first. Without --dry-run this script writes yml files and backs up
any overwritten target files under maintenance/backups/.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from csv_io import write_json
from tool_config import (
    PACK_ROOT as _TOOL_CONFIG_PACK_ROOT,
)
from tool_config import (
    read_text,
    resolve_pack_path,
)
from tool_config import (
    workshop_root as _configured_workshop_root,
)
from yml_localisation import HEADER_RE, parse_entry

DEFAULT_WORKSHOP_ROOT = _configured_workshop_root()
TOOL_ROOT = Path(__file__).resolve().parents[1]
# PACK_ROOT: --output-root 미지정 시 폴백. tool_config 기준으로 통일
PACK_ROOT = _TOOL_CONFIG_PACK_ROOT.parent / "integrated_korean_translation_pack"


def parse_args() -> argparse.Namespace:
    """Parse the target mod, CSV tree, and dry-run/write mode."""
    parser = argparse.ArgumentParser(
        description="Create/update Korean localisation files using per-source-file key CSVs."
    )
    parser.add_argument("mod_id", help="Steam workshop mod id, for example 1121692237")
    parser.add_argument(
        "csv_dir",
        help="Directory containing per-file *_key.csv files. Relative paths are resolved from the translation pack root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write only a report; do not create backups or update localisation files.",
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help=(
            "Override the localisation/korean output directory. "
            "Relative paths are resolved from the translation pack root. "
            "Defaults to integrated_korean_translation_pack/localisation/korean."
        ),
    )
    return parser.parse_args()



def write_text(path: Path, text: str) -> None:
    """Write generated localisation text with a BOM and LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")


def parse_entries(path: Path) -> dict[str, str]:
    """Parse a localisation file into key -> rendered line.

    The rendered line preserves the key's version style (`:0` or bare `:`) so
    output stays close to the source or existing Korean file.
    """
    entries: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if HEADER_RE.match(line):
            continue
        entry = parse_entry(line)
        if entry is None:
            continue
        key = entry.key.strip()
        version = entry.version
        value = entry.value
        if version is None:
            entries[key] = f" {key}: {value}".rstrip()
        else:
            entries[key] = f" {key}:{version} {value}".rstrip()
    return entries


def build_translation_index(
    korean_root: Path,
) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
    """Scan all Korean files and split unique translations from conflicts.

    A key with exactly one distinct rendered value is safe to reuse. A key with
    multiple distinct rendered values is reported as a conflict and will fall
    back to the English source unless the CSV provides an explicit korean_value.
    """
    values_by_key: dict[str, set[str]] = defaultdict(set)
    sources_by_key_value: dict[tuple[str, str], list[str]] = defaultdict(list)

    for path in sorted(korean_root.rglob("*_l_korean.yml")):
        for key, rendered in parse_entries(path).items():
            values_by_key[key].add(rendered)
            sources_by_key_value[(key, rendered)].append(str(path.relative_to(korean_root)))

    translations: dict[str, str] = {}
    conflicts: dict[str, list[dict[str, object]]] = {}
    for key, values in values_by_key.items():
        if len(values) == 1:
            translations[key] = next(iter(values))
        elif len(values) > 1:
            conflicts[key] = [
                {
                    "value": value,
                    "sources": sorted(sources_by_key_value[(key, value)]),
                }
                for value in sorted(values)
            ]
    return translations, conflicts


def read_keys(csv_path: Path) -> dict[str, str]:
    """Return ordered dict of key -> korean_value (empty string if not filled)."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "key" not in fieldnames:
            raise ValueError(f"{csv_path}: CSV must have a 'key' column")
        has_korean = "korean_value" in fieldnames
        result: dict[str, str] = {}
        seen: set[str] = set()
        for row in reader:
            key = (row.get("key") or "").strip()
            if key and key not in seen:
                korean = (row.get("korean_value") or "").strip() if has_korean else ""
                result[key] = korean
                seen.add(key)
        return result


def target_path_for(csv_path: Path, csv_root: Path, korean_root: Path) -> Path:
    """Map a *_key.csv path to its target *_l_korean.yml path."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    if not name.endswith("_key.csv"):
        raise ValueError(f"CSV file name must end with _key.csv: {csv_path}")
    target_name = name[: -len("_key.csv")] + "_l_korean.yml"
    return korean_root / relative.parent / target_name


def source_path_for(csv_path: Path, csv_root: Path, mod_root: Path) -> Path:
    """Map a *_key.csv path back to its source *_l_english.yml path."""
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


def render_from_csv_value(key: str, raw: str) -> str:
    """Convert a user-supplied korean_value into a localisation line.

    Accepts either a bare translated string or a full localisation line.
    Always uses version :0 when constructing from bare text.
    """
    stripped = raw.strip()
    # Full line already supplied (contains key name before colon)
    match = re.match(r"^(\s*)([^:#\s][^:]*)\s*:\s*(?:-?\d+\s*)?(.*)$", stripped)
    if match and match.group(2).strip() == key:
        return stripped
    # Bare value — wrap with quotes if needed
    if not (stripped.startswith('"') and stripped.endswith('"')):
        # Escape only literal backslashes that are NOT part of a recognised
        # Stellaris escape sequence (\n, \t, \", \\).  A simple way is to
        # escape lone backslashes (not already followed by n/t/"/\).
        escaped = re.sub(r'\\(?![nt"\\])', r"\\\\", stripped)
        escaped = escaped.replace('"', '\\"')
        stripped = f'"{escaped}"'
    return f" {key}:0 {stripped}"


def render_file(
    keys: dict[str, str],
    translations: dict[str, str],
    conflicts: dict[str, list[dict[str, object]]],
    source_entries: dict[str, str],
) -> tuple[str, list[str], list[str], list[dict[str, str]]]:
    """Render one target Korean file and collect report buckets.

    Priority per key:
    1. CSV korean_value
    2. Existing unique Korean translation
    3. English source fallback

    Conflict keys are still reported, but they are not omitted from output;
    they receive English fallback so the game has something readable.
    """
    lines = ["l_korean:"]
    missing: list[str] = []
    conflicted: list[str] = []
    fallback: list[dict[str, str]] = []
    for key, csv_korean in keys.items():
        rendered = render_from_csv_value(key, csv_korean) if csv_korean else None
        if rendered is None:
            if key in conflicts:
                conflicted.append(key)
                rendered = source_entries.get(key)
                if rendered is not None:
                    fallback.append({"key": key, "reason": "conflict", "value": rendered})
            else:
                rendered = translations.get(key)
        if rendered is None:
            rendered = source_entries.get(key)
            if rendered is not None:
                fallback.append({"key": key, "reason": "missing_translation", "value": rendered})
        if rendered is None:
            missing.append(key)
            continue
        lines.append(rendered)
    return "\n".join(lines) + "\n", missing, conflicted, fallback


def backup_file(path: Path, backup_root: Path, korean_root: Path) -> None:
    """Copy an existing target file into the timestamped backup tree."""
    relative = path.relative_to(korean_root)
    backup_path = backup_root / relative
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)


def write_report(report: dict, reports_root: Path, timestamp: str) -> Path:
    """Write the JSON report for this run."""
    report_path = reports_root / f"export_localisation_report_{timestamp}.json"
    write_json(report_path, report)
    return report_path


def main() -> int:
    """Render all target files for the provided mod CSV tree."""
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
        print(f"[경고] --output-root 미지정: {korean_root} 로 출력합니다.", flush=True)
    reports_root = TOOL_ROOT / "maintenance" / "reports" / "translation"
    backup_root = TOOL_ROOT / "maintenance" / "backups" / f"export_localisation_{timestamp}"

    if not (mod_root / "localisation").is_dir():
        raise SystemExit(f"Localisation directory not found: {mod_root / 'localisation'}")
    if not csv_root.is_dir():
        raise SystemExit(f"CSV directory not found: {csv_root}")
    if not korean_root.is_dir():
        if args.output_root:
            # --output-root 지정 시 standalone 모드 — 폴더 자동 생성
            korean_root.mkdir(parents=True, exist_ok=True)
        else:
            raise SystemExit(f"Korean localisation directory not found: {korean_root}")

    translations, global_conflicts = build_translation_index(korean_root)
    csv_files = sorted(csv_root.rglob("*_key.csv"))

    report = {
        "mod_id": args.mod_id,
        "dry_run": args.dry_run,
        "csv_dir": str(csv_root),
        "source_root": str(mod_root / "localisation"),
        "korean_root": str(korean_root),
        "csv_files": len(csv_files),
        "created_files": [],
        "updated_files": [],
        "unchanged_files": [],
        "missing_keys": {},
        "english_fallback_keys": {},
        "conflict_keys": {},
        "missing_source_files": [],
        "processed_keys": 0,
    }

    for csv_path in csv_files:
        source_path = source_path_for(csv_path, csv_root, mod_root)
        target_path = target_path_for(csv_path, csv_root, korean_root)
        rel_target = str(target_path.relative_to(korean_root))
        if not source_path.is_file():
            report["missing_source_files"].append(str(source_path))
            continue

        keys = read_keys(csv_path)
        source_entries = parse_entries(source_path)
        rendered, missing, conflicted, fallback = render_file(
            keys,
            translations,
            global_conflicts,
            source_entries,
        )
        report["processed_keys"] += len(keys)

        if missing:
            report["missing_keys"][rel_target] = missing
        if fallback:
            report["english_fallback_keys"][rel_target] = fallback
        if conflicted:
            report["conflict_keys"][rel_target] = {key: global_conflicts[key] for key in conflicted}

        existing = read_text(target_path) if target_path.exists() else None
        if existing == rendered:
            report["unchanged_files"].append(rel_target)
            continue

        if target_path.exists():
            report["updated_files"].append(rel_target)
            if not args.dry_run:
                backup_file(target_path, backup_root, korean_root)
        else:
            report["created_files"].append(rel_target)

        if not args.dry_run:
            write_text(target_path, rendered)

    report_path = write_report(report, reports_root, timestamp)

    print(f"csv_files={report['csv_files']}")
    print(f"processed_keys={report['processed_keys']}")
    print(f"created_files={len(report['created_files'])}")
    print(f"updated_files={len(report['updated_files'])}")
    print(f"unchanged_files={len(report['unchanged_files'])}")
    print(f"missing_key_files={len(report['missing_keys'])}")
    print(f"english_fallback_files={len(report['english_fallback_keys'])}")
    print(f"conflict_key_files={len(report['conflict_keys'])}")
    print(f"missing_source_files={len(report['missing_source_files'])}")
    print(f"report={report_path}")
    if not args.dry_run and report["updated_files"]:
        print(f"backup_dir={backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
