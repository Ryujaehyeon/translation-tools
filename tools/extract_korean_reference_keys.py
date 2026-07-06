#!/usr/bin/env python3
"""Extract Korean localisation references while preserving source structure.

This tool is for Korean translation/addon mods, not English source mods. It
mirrors the Korean localisation tree into CSV files that can later be imported
into auto_keys. Only Korean text is extracted; English text is intentionally
left blank so downstream import can overwrite only the `korean_value` column.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from csv_io import write_json
from tool_config import csv_writer, descriptor_name, read_text, resolve_pack_path
from tool_config import workshop_root as _configured_workshop_root
from yml_localisation import HEADER_RE, parse_entry

DEFAULT_WORKSHOP_ROOT = _configured_workshop_root()
PACK_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReferenceSource:
    identifier: str
    root: Path
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract key/korean_value CSVs from Korean localisation mods while preserving folder structure."
    )
    parser.add_argument(
        "--reference-source",
        action="append",
        required=True,
        help="Korean reference source as a workshop id or folder path. Can repeat.",
    )
    parser.add_argument(
        "--output-dir",
        default="maintenance/reference_keys",
        help="Output directory for extracted reference CSVs. Relative paths are resolved from the pack root.",
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--report-dir",
        default="maintenance/reports/reference_extraction",
        help="Report directory. Relative paths are resolved from the pack root.",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Write directly under output-dir instead of output-dir/<source_slug>.",
    )
    return parser.parse_args()







def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^\w가-힣]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "reference"


def resolve_source(raw: str, workshop_root: Path) -> ReferenceSource:
    if re.fullmatch(r"\d+", raw):
        root = workshop_root / raw
        identifier = raw
    else:
        path = Path(raw)
        if path.is_absolute():
            root = path
        else:
            pack_relative = PACK_ROOT / path
            root = pack_relative if pack_relative.exists() else Path.cwd() / path
        identifier = str(root)
    label = descriptor_name(root) if root.is_dir() else raw
    return ReferenceSource(identifier=identifier, root=root, label=label)


def iter_korean_files(source_root: Path) -> list[Path]:
    localisation_root = source_root / "localisation"
    if not localisation_root.is_dir():
        return []
    return sorted(path for path in localisation_root.rglob("*_l_korean.yml") if path.is_file())


def iter_entries(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in read_text(path).splitlines():
        if HEADER_RE.match(line):
            continue
        entry = parse_entry(line)
        if entry is None:
            continue
        key = entry.key.strip()
        korean_value = entry.value.strip() if entry.value else ""
        if key and key not in seen:
            entries.append((key, korean_value))
            seen.add(key)
    return entries


def relative_korean_path(path: Path, source_root: Path) -> Path:
    localisation_root = source_root / "localisation"
    try:
        rel = path.relative_to(localisation_root / "korean")
    except ValueError:
        try:
            rel = path.relative_to(localisation_root)
        except ValueError:
            rel = Path(path.name)
    name = rel.name
    if name.endswith("_l_korean.yml"):
        name = name[: -len("_l_korean.yml")] + "_key.csv"
    else:
        name = rel.stem + "_key.csv"
    return rel.parent / name


def write_reference_csv(path: Path, entries: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_writer(handle)
        writer.writerow(["key", "english_value", "korean_value"])
        for key, korean_value in entries:
            writer.writerow([key, "", korean_value])


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    workshop_root = Path(args.workshop_root)
    output_root = resolve_pack_path(args.output_dir)
    report_dir = resolve_pack_path(args.report_dir)
    sources = [resolve_source(raw, workshop_root) for raw in args.reference_source]

    summaries: list[dict[str, object]] = []
    total_files = 0
    total_rows = 0

    for source in sources:
        files = iter_korean_files(source.root)
        source_slug = slugify(source.label)
        source_output = output_root if args.flat else output_root / source_slug
        written_files = 0
        written_rows = 0
        for korean_file in files:
            entries = iter_entries(korean_file)
            if not entries:
                continue
            target = source_output / relative_korean_path(korean_file, source.root)
            write_reference_csv(target, entries)
            written_files += 1
            written_rows += len(entries)
        total_files += written_files
        total_rows += written_rows
        summaries.append(
            {
                "identifier": source.identifier,
                "label": source.label,
                "root": str(source.root),
                "exists": source.root.is_dir(),
                "korean_files": len(files),
                "written_csv_files": written_files,
                "written_rows": written_rows,
                "output_dir": str(source_output),
            }
        )

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"korean_reference_extraction_report_{timestamp}.json"
    write_json(
        report_path,
        {
            "output_dir": str(output_root),
            "sources": summaries,
            "total_written_csv_files": total_files,
            "total_written_rows": total_rows,
        },
    )

    print(f"sources={len(sources)}")
    print(f"csv_files={total_files}")
    print(f"rows={total_rows}")
    print(f"output_dir={output_root}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
