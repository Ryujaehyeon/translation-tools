#!/usr/bin/env python3
"""Import Korean reference translations into translation key CSV files.

The tool scans Korean localisation files from known Korean translation mods,
builds a priority-ordered key -> Korean value index, and copies matching values
into `maintenance/translation_keys/**/_key.csv`.

Default behavior is conservative:

- fill only blank `korean_value` cells;
- preserve `key` and `english_value`;
- report token shape differences without automatically fixing them.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tool_config import (
    csv_dict_writer,
    csv_writer,
    descriptor_name,
    read_text,
    resolve_pack_path,
    translation_keys_root,
)

PACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTO_KEYS_DIR = translation_keys_root()
DEFAULT_WORKSHOP_ROOT = Path(r"D:\Program Files (x86)\Steam\steamapps\workshop\content\281990")
DEFAULT_REPORT_DIR = PACK_ROOT / "maintenance" / "reports" / "reference_import"
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "import_korean_references"

REFERENCE_MOD_IDS = [
    "2506141839",  # Mod Korean Collection
    "2918194940",  # 한국어 보완 모드
    "2524944243",
    "2524947989",
    "2836348228",  # MKC Addon: Even More Origins
    "2836353697",  # MKC Addon: Expanded Stellaris Traditions
    "2836362654",
    "2836364177",
    "2836366568",
    "2836367458",
    "2880546634",
    "2994467117",  # Giga Korean patch
]

ENTRY_RE = re.compile(r"^\s*([^:#\s][^:]*)\s*:\s*(?:(-?\d+)\s*)?(.*)$")
HEADER_RE = re.compile(r"^\s*l_[A-Za-z_]+:\s*$")

TOKEN_PATTERNS = {
    "dollar": re.compile(r"\$[^$\n]+\$"),
    "icon": re.compile(r"£[^£\n]+£"),
    "bracket": re.compile(r"\[[^\]\n]+\]"),
    "concept": re.compile(r"\['[^'\n]+'\]"),
    "style": re.compile(r"§."),
    "newline": re.compile(r"\\n"),
}


@dataclass(frozen=True)
class ReferenceValue:
    value: str
    mod_id: str
    source_file: str
    line_number: int
    priority: int


@dataclass(frozen=True)
class ReferenceSource:
    identifier: str
    root: Path
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="한국어 참고 모드의 localisation 값을 auto_keys CSV의 korean_value에 복사합니다."
    )
    parser.add_argument(
        "--auto-keys-dir",
        default=str(DEFAULT_AUTO_KEYS_DIR),
        help="Translation keys directory. Default: maintenance/tooling.ini.",
    )
    parser.add_argument(
        "--workshop-root",
        default=str(DEFAULT_WORKSHOP_ROOT),
        help=f"Workshop content root. Default: {DEFAULT_WORKSHOP_ROOT}",
    )
    parser.add_argument(
        "--reference-mod-id",
        action="append",
        default=[],
        help="Reference Korean mod id. Can repeat. Defaults to the configured priority list.",
    )
    parser.add_argument(
        "--reference-path",
        action="append",
        default=[],
        help="Reference Korean mod folder path. Can repeat. Use this for local addon folders or non-workshop sources.",
    )
    parser.add_argument(
        "--reference-source",
        action="append",
        default=[],
        help=(
            "Reference source as either a workshop id or a folder path. Can repeat and preserves priority order. "
            "When supplied, it replaces the default reference mod list."
        ),
    )
    parser.add_argument(
        "--reference-csv-dir",
        action="append",
        default=[],
        help=(
            "Directory containing extracted Korean reference *_key.csv files. Can repeat. "
            "Rows are matched by key and only korean_value is imported."
        ),
    )
    parser.add_argument(
        "--mod", action="append", default=[], help="Limit to an auto_keys mod folder. Can repeat."
    )
    parser.add_argument(
        "--file", action="append", default=[], help="Limit to a CSV path or filename. Can repeat."
    )
    parser.add_argument(
        "--limit-rows", type=int, default=0, help="Stop after N changed rows. 0 means unlimited."
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite non-empty korean_value cells too.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report changes without writing CSV files."
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Report directory. Default: maintenance/reports/reference_import.",
    )
    return parser.parse_args()







def resolve_reference_path(raw: str, workshop_root: Path) -> Path:
    if re.fullmatch(r"\d+", raw):
        return workshop_root / raw
    path = Path(raw)
    if path.is_absolute():
        return path
    pack_relative = PACK_ROOT / path
    if pack_relative.exists():
        return pack_relative
    return Path.cwd() / path


def reference_sources_from_args(
    args: argparse.Namespace, workshop_root: Path
) -> list[ReferenceSource]:
    raw_sources: list[str]
    if args.reference_source:
        raw_sources = list(args.reference_source)
    elif args.reference_mod_id or args.reference_path:
        raw_sources = [*args.reference_mod_id, *args.reference_path]
    else:
        raw_sources = list(REFERENCE_MOD_IDS)

    sources: list[ReferenceSource] = []
    for raw in raw_sources:
        root = resolve_reference_path(raw, workshop_root)
        identifier = raw if re.fullmatch(r"\d+", raw) else str(root)
        label = descriptor_name(root) if root.is_dir() else raw
        sources.append(ReferenceSource(identifier=identifier, root=root, label=label))
    return sources


def iter_localisation_entries(path: Path) -> list[tuple[int, str, str]]:
    entries: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if HEADER_RE.match(line):
            continue
        match = ENTRY_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(3).strip() if match.group(3) else ""
        if key:
            entries.append((line_number, key, value))
    return entries


def discover_korean_files(mod_root: Path) -> list[Path]:
    localisation_root = mod_root / "localisation"
    if not localisation_root.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(localisation_root.rglob("*_l_korean.yml")):
        if path.is_file():
            files.append(path)
    return files


def build_reference_index(
    sources: list[ReferenceSource],
) -> tuple[dict[str, ReferenceValue], dict[str, object]]:
    index: dict[str, ReferenceValue] = {}
    duplicate_count = 0
    scanned_files = 0
    scanned_entries = 0
    per_source: list[dict[str, object]] = []

    for priority, source in enumerate(sources, start=1):
        files = discover_korean_files(source.root)
        source_entries = 0
        source_added = 0
        for path in files:
            scanned_files += 1
            rel = str(path.relative_to(source.root)).replace("\\", "/")
            for line_number, key, value in iter_localisation_entries(path):
                scanned_entries += 1
                source_entries += 1
                if key in index:
                    duplicate_count += 1
                    continue
                index[key] = ReferenceValue(
                    value=value,
                    mod_id=source.identifier,
                    source_file=rel,
                    line_number=line_number,
                    priority=priority,
                )
                source_added += 1
        per_source.append(
            {
                "identifier": source.identifier,
                "label": source.label,
                "root": str(source.root),
                "exists": source.root.is_dir(),
                "korean_files": len(files),
                "entries": source_entries,
                "unique_added": source_added,
            }
        )

    summary = {
        "reference_sources": [source.identifier for source in sources],
        "scanned_files": scanned_files,
        "scanned_entries": scanned_entries,
        "unique_keys": len(index),
        "duplicate_lower_priority_entries": duplicate_count,
        "per_source": per_source,
    }
    return index, summary


def build_reference_index_from_csv_dirs(
    csv_dirs: list[Path],
) -> tuple[dict[str, ReferenceValue], dict[str, object]]:
    index: dict[str, ReferenceValue] = {}
    duplicate_count = 0
    scanned_files = 0
    scanned_entries = 0
    per_source: list[dict[str, object]] = []

    for priority, csv_dir in enumerate(csv_dirs, start=1):
        files = (
            sorted(path for path in csv_dir.rglob("*_key.csv") if path.is_file())
            if csv_dir.is_dir()
            else []
        )
        source_entries = 0
        source_added = 0
        for path in files:
            scanned_files += 1
            try:
                rel = str(path.relative_to(csv_dir)).replace("\\", "/")
            except ValueError:
                rel = path.name
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for line_number, row in enumerate(reader, start=2):
                    key = (row.get("key") or "").strip()
                    value = (row.get("korean_value") or "").strip()
                    if not key or not value:
                        continue
                    scanned_entries += 1
                    source_entries += 1
                    if key in index:
                        duplicate_count += 1
                        continue
                    index[key] = ReferenceValue(
                        value=value,
                        mod_id=str(csv_dir),
                        source_file=rel,
                        line_number=line_number,
                        priority=priority,
                    )
                    source_added += 1
        per_source.append(
            {
                "identifier": str(csv_dir),
                "label": csv_dir.name,
                "root": str(csv_dir),
                "exists": csv_dir.is_dir(),
                "csv_files": len(files),
                "entries": source_entries,
                "unique_added": source_added,
            }
        )

    summary = {
        "reference_csv_dirs": [str(path) for path in csv_dirs],
        "scanned_files": scanned_files,
        "scanned_entries": scanned_entries,
        "unique_keys": len(index),
        "duplicate_lower_priority_entries": duplicate_count,
        "per_source": per_source,
    }
    return index, summary


def resolve_csv_files(auto_keys_dir: Path, mods: list[str], files: list[str]) -> list[Path]:
    result: list[Path] = []
    if files:
        for raw in files:
            path = Path(raw)
            if not path.is_absolute():
                direct = PACK_ROOT / path
                path = direct if direct.exists() else auto_keys_dir / path
            if path.is_file():
                result.append(path)
            else:
                result.extend(auto_keys_dir.rglob(Path(raw).name))
    elif mods:
        for mod in mods:
            mod_dir = auto_keys_dir / mod
            if mod_dir.is_dir():
                result.extend(mod_dir.rglob("*_key.csv"))
    else:
        result.extend(auto_keys_dir.rglob("*_key.csv"))
    return sorted(set(result))


def token_counts(value: str) -> dict[str, Counter[str]]:
    return {name: Counter(pattern.findall(value or "")) for name, pattern in TOKEN_PATTERNS.items()}


def token_issue_types(english_value: str, korean_value: str) -> list[str]:
    eng = token_counts(english_value)
    kor = token_counts(korean_value)
    return [f"{name}_mismatch" for name in TOKEN_PATTERNS if eng[name] != kor[name]]


def backup_csv(path: Path, auto_keys_dir: Path, timestamp: str) -> None:
    try:
        rel = path.relative_to(auto_keys_dir)
    except ValueError:
        rel = Path(path.name)
    dest = BACKUP_ROOT / timestamp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def _yml_value_to_csv_raw(yml_value: str, english_raw: str) -> str:
    # yml에서 읽은 값을 CSV raw 형식으로 변환한다.
    # yml 값이 따옴표로 감싸여 있으면 그대로 유지,
    # 없으면 english_value의 따옴표 유무에 맞춰 감싸준다.
    v = yml_value.strip()
    eng = english_raw.strip()
    eng_quoted = len(eng) >= 2 and eng[0] == '"' and eng[-1] == '"'
    val_quoted = len(v) >= 2 and v[0] == '"' and v[-1] == '"'
    if eng_quoted and not val_quoted:
        return f'"{v}"'
    return v


def write_csv_report(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_dict_writer(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def process_file(
    csv_path: Path,
    auto_keys_dir: Path,
    references: dict[str, ReferenceValue],
    overwrite_existing: bool,
    dry_run: bool,
    remaining_limit: int | None,
    timestamp: str,
) -> tuple[int, int, int, list[dict[str, object]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not {"key", "english_value", "korean_value"}.issubset(set(fieldnames)):
        raise ValueError(f"{csv_path}: required columns missing")

    changed = 0
    matched = 0
    token_issue_count = 0
    report_rows: list[dict[str, object]] = []
    rel_file = str(csv_path.relative_to(auto_keys_dir)).replace("\\", "/")
    mod = csv_path.relative_to(auto_keys_dir).parts[0]

    for line_number, row in enumerate(rows, start=2):
        if remaining_limit is not None and changed >= remaining_limit:
            break
        key = (row.get("key") or "").strip()
        if not key:
            continue
        ref = references.get(key)
        if not ref:
            continue
        matched += 1
        current = row.get("korean_value") or ""
        if current.strip() and not overwrite_existing:
            continue
        english_raw = row.get("english_value") or ""
        korean_raw = _yml_value_to_csv_raw(ref.value, english_raw)
        # 토큰 검사는 inner 값(따옴표 제거 후) 기준으로 수행
        eng_inner = english_raw.strip().strip('"')
        kor_inner = ref.value.strip().strip('"')
        issues = token_issue_types(eng_inner, kor_inner)
        if issues:
            token_issue_count += 1
        report_rows.append(
            {
                "mod": mod,
                "file": rel_file,
                "line_number": line_number,
                "key": key,
                "action": "overwrite" if current.strip() else "fill",
                "reference_mod_id": ref.mod_id,
                "reference_file": ref.source_file,
                "reference_line_number": ref.line_number,
                "issue_types": ";".join(issues),
                "old_korean_value": current,
                "new_korean_value": korean_raw,
            }
        )
        # Only the Korean sentence column is imported. key and english_value
        # remain exactly as they were in the target auto_keys CSV.
        row["korean_value"] = korean_raw
        changed += 1

    if changed and not dry_run:
        backup_csv(csv_path, auto_keys_dir, timestamp)
        temp = csv_path.with_suffix(csv_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv_writer(handle, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(fieldnames)
            for row in rows:
                writer.writerow([row.get(f, "") or "" for f in fieldnames])
        shutil.move(str(temp), str(csv_path))

    return changed, matched, token_issue_count, report_rows


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    auto_keys_dir = resolve_pack_path(args.auto_keys_dir)
    workshop_root = Path(args.workshop_root)
    report_dir = resolve_pack_path(args.report_dir)
    reference_csv_dirs = [resolve_pack_path(raw) for raw in args.reference_csv_dir]
    reference_sources = reference_sources_from_args(args, workshop_root)

    if not auto_keys_dir.is_dir():
        raise SystemExit(f"translation keys directory not found: {auto_keys_dir}")
    needs_workshop_root = not reference_csv_dirs and any(
        re.fullmatch(r"\d+", source.identifier) for source in reference_sources
    )
    if needs_workshop_root and not workshop_root.is_dir():
        raise SystemExit(f"workshop root not found: {workshop_root}")

    if reference_csv_dirs:
        references, reference_summary = build_reference_index_from_csv_dirs(reference_csv_dirs)
    else:
        references, reference_summary = build_reference_index(reference_sources)
    csv_files = resolve_csv_files(auto_keys_dir, args.mod, args.file)

    changed_total = 0
    matched_total = 0
    token_issue_total = 0
    changed_files = 0
    change_rows: list[dict[str, object]] = []
    file_summaries: list[dict[str, object]] = []

    for csv_path in csv_files:
        if args.limit_rows:
            remaining: int | None = max(args.limit_rows - changed_total, 0)
            if remaining <= 0:
                break
        else:
            remaining = None
        changed, matched, token_issues, rows = process_file(
            csv_path,
            auto_keys_dir,
            references,
            args.overwrite_existing,
            args.dry_run,
            remaining,
            timestamp,
        )
        matched_total += matched
        token_issue_total += token_issues
        changed_total += changed
        change_rows.extend(rows)
        if changed:
            changed_files += 1
            file_summaries.append(
                {
                    "file": str(csv_path.relative_to(auto_keys_dir)).replace("\\", "/"),
                    "changed_rows": changed,
                    "matched_rows": matched,
                    "token_issue_rows": token_issues,
                }
            )

    report_json = report_dir / f"korean_reference_import_report_{timestamp}.json"
    report_csv = report_dir / f"korean_reference_import_changes_{timestamp}.csv"
    latest_csv = report_dir / "korean_reference_import_changes_latest.csv"

    fieldnames = [
        "mod",
        "file",
        "line_number",
        "key",
        "action",
        "reference_mod_id",
        "reference_file",
        "reference_line_number",
        "issue_types",
        "old_korean_value",
        "new_korean_value",
    ]
    write_csv_report(report_csv, change_rows, fieldnames)
    write_csv_report(latest_csv, change_rows, fieldnames)
    write_json(
        report_json,
        {
            "dry_run": args.dry_run,
            "overwrite_existing": args.overwrite_existing,
            "auto_keys_dir": str(auto_keys_dir),
            "csv_files": len(csv_files),
            "changed_files": changed_files,
            "matched_rows": matched_total,
            "changed_rows": changed_total,
            "token_issue_rows": token_issue_total,
            "reference_summary": reference_summary,
            "file_summaries": file_summaries,
            "outputs": {
                "report_json": str(report_json),
                "changes_csv": str(report_csv),
                "latest_changes_csv": str(latest_csv),
            },
        },
    )

    label = "[dry-run]" if args.dry_run else "[적용]"
    mode = "덮어쓰기 포함" if args.overwrite_existing else "빈 칸만"
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  한국어 참조 가져오기 완료  {label}  ({mode})")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  참조 모드 고유 키   {reference_summary['unique_keys']:>8,}개")
    print(f"  대상 CSV 파일       {len(csv_files):>8,}개")
    print(f"  매칭된 행           {matched_total:>8,}행")
    if args.dry_run:
        print(f"  변경 예정 파일      {changed_files:>8,}개")
        print(f"  변경 예정 행        {changed_total:>8,}행")
    else:
        print(f"  변경된 파일         {changed_files:>8,}개")
        print(f"  변경된 행           {changed_total:>8,}행")
    print(f"  토큰 이슈 행        {token_issue_total:>8,}행  (적용됨, 검수 필요)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    try:
        rel_csv = report_csv.relative_to(PACK_ROOT)
    except ValueError:
        rel_csv = report_csv
    print(f"  변경 내역 CSV  →  {rel_csv}")
    if not args.dry_run and changed_total:
        print("\n  가져온 참조 번역의 토큰을 validate로 확인하세요 (참조 모드 품질 이슈 주의):")
        print("    python tools/validate_auto_key_tokens.py")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
