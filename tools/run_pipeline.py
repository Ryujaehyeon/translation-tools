#!/usr/bin/env python3
"""Run localisation maintenance tools across workshop mod folders.

This script is the orchestration layer for the translation-pack workflow. It
does not parse or rewrite localisation files by itself; instead it discovers
Stellaris workshop mods and runs the smaller single-purpose tools in order:

1. extract_localisation_keys.py
2. optionally import_korean_references.py
3. optionally translate_keys.py
4. optionally validate_auto_key_tokens.py
5. export_localisation.py
6. validate_translation_outputs.py
7. resolve_conflict_translations.py --prepare

By default export_localisation.py is called in dry-run mode, so a plain
`python tools/run_pipeline.py` should only create key CSVs and reports.
Use --apply-translations when you explicitly want localisation files updated.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from tool_config import translation_keys_root_arg, workshop_root as configured_workshop_root, output_root, ensure_standalone_mod, is_integrated_mode


STELLARIS_APP_ID = "281990"
# 캐시 포맷이 바뀌면 이 값을 올린다 (캐시 자동 무효화).
# 올려야 하는 경우: mod state JSON 구조 변경, slug 생성 방식 변경,
#   extraction 결과 포맷 변경 등 기존 캐시가 잘못된 skip 판단을 낼 수 있을 때.
CACHE_VERSION = 1
PACK_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PACK_ROOT / "tools"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for selecting mods and workflow steps."""
    parser = argparse.ArgumentParser(
        description="Loop over workshop mods and run extract/translation/validation/conflict tools."
    )
    parser.add_argument(
        "--workshop-root",
        default=str(configured_workshop_root()),
        help="Workshop content root. If omitted, detect it from Steam libraries.",
    )
    parser.add_argument(
        "--mod-ids",
        nargs="*",
        help="Optional list of workshop mod ids to process. Defaults to every mod folder with localisation/english.",
    )
    parser.add_argument(
        "--mod",
        action="append",
        default=[],
        help="Optional generated mod slug or workshop id to process. Can repeat.",
    )
    parser.add_argument(
        "--keys-root",
        default=translation_keys_root_arg(),
        help="Root directory for generated per-mod key CSV folders. Relative paths are resolved from the pack root.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N discovered mods. Useful for smoke tests.",
    )
    parser.add_argument(
        "--apply-translations",
        action="store_true",
        help="Run export_localisation.py without --dry-run. Default is dry-run only.",
    )
    parser.add_argument(
        "--skip-translation",
        action="store_true",
        help="Only extract keys; skip translation dry-run/apply.",
    )
    parser.add_argument(
        "--import-korean-references",
        action="store_true",
        help=(
            "Optionally fill translation keys from subscribed Korean reference mods before translation. "
            "Default is off because reference mods rarely need to be rescanned."
        ),
    )
    parser.add_argument(
        "--reference-dry-run",
        action="store_true",
        help="With --import-korean-references, report reference matches without writing auto_keys CSV files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Avoid CSV/YML writes: skip extraction and force write-capable tools into dry-run mode.",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Fill blank korean_value cells with translate_keys.py before export. Requires tools/api_key.txt.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validate_translation_outputs.py.",
    )
    parser.add_argument(
        "--skip-conflict-prepare",
        action="store_true",
        help="Skip resolve_conflict_translations.py --prepare.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining mods when one tool fails.",
    )
    parser.add_argument(
        "--workers",
        default="auto",
        help="Number of mods to process in parallel, or 'auto'. Default: auto.",
    )
    parser.add_argument(
        "--mode",
        choices=["scan", "plan", "report", "apply", "auto"],
        default="report",
        help="Preset workflow mode. scan=list, plan=dry-run counts, report=reports, apply=write translations, auto=quiet apply.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress logs and print only the final summary.",
    )
    parser.add_argument(
        "--list-mods",
        action="store_true",
        help="List discovered target mods and exit without running tools.",
    )
    parser.add_argument(
        "--list-json",
        action="store_true",
        help="With --list-mods, print discovered mods as JSON.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Run key extraction plus translation dry-run and print work/skip counts.",
    )
    parser.add_argument(
        "--plan-json",
        action="store_true",
        help="With --plan, print the planning result as JSON.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip key extraction for unchanged source trees when cached CSVs exist.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cache and rerun every enabled step.",
    )
    parser.add_argument(
        "--integrated",
        action="store_true",
        help=(
            "Write all output into a single integrated_korean_translation_pack folder. "
            "Without this flag each mod gets its own standalone addon folder."
        ),
    )
    return parser.parse_args()


def resolve_pack_path(raw: str) -> Path:
    """Resolve a user path relative to the translation pack root."""
    path = Path(raw)
    if path.is_absolute():
        return path
    return PACK_ROOT / path


def resolve_workers(raw: str, apply_translations: bool) -> int:
    """Resolve --workers, keeping actual write mode conservative by default."""
    if str(raw).lower() == "auto":
        if apply_translations:
            return 1
        return max(1, min(4, os.cpu_count() or 1))
    try:
        return max(1, int(raw))
    except ValueError as exc:
        raise SystemExit("--workers must be an integer or 'auto'") from exc


def apply_mode_preset(args: argparse.Namespace) -> None:
    """Translate high-level --mode presets into existing low-level flags."""
    if args.mode == "scan":
        args.list_mods = True
    elif args.mode == "plan":
        args.plan = True
    elif args.mode == "apply":
        args.apply_translations = True
    elif args.mode == "auto":
        args.apply_translations = True
        args.quiet = True
    # report is the historical default: extract, translation dry-run,
    # validation, and conflict worklist preparation.


def read_text(path: Path) -> str:
    """Read text files used by Steam/Paradox, tolerating BOMs and odd bytes."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_vdf_paths(path: Path) -> list[Path]:
    """Extract Steam library paths from a simple Valve VDF file.

    This intentionally uses a narrow regex instead of a full VDF parser because
    we only need repeated `"path" "..."` entries from libraryfolders.vdf.
    """
    if not path.is_file():
        return []
    paths: list[Path] = []
    for match in re.finditer(r'"path"\s+"([^"]+)"', read_text(path)):
        paths.append(Path(match.group(1).replace("\\\\", "\\")))
    return paths


def steam_root_candidates() -> list[Path]:
    """Return likely Steam install roots before reading libraryfolders.vdf."""
    candidates: list[Path] = []
    env_steam = os.environ.get("STEAM_DIR")
    if env_steam:
        candidates.append(Path(env_steam))
    for raw in (
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Program Files (x86)\Steam",
        r"D:\Steam",
    ):
        candidates.append(Path(raw))
    return list(dict.fromkeys(candidates))


def discover_steam_libraries() -> list[Path]:
    """Find Steam libraries from common roots and libraryfolders.vdf files."""
    libraries: list[Path] = []
    for steam_root in steam_root_candidates():
        if not steam_root.is_dir():
            continue
        libraries.append(steam_root)
        libraries.extend(parse_vdf_paths(steam_root / "steamapps" / "libraryfolders.vdf"))
    return list(dict.fromkeys(libraries))


def detect_workshop_root() -> Path:
    """Locate the Stellaris workshop content directory from Steam libraries."""
    candidates: list[Path] = []
    for library in discover_steam_libraries():
        candidates.append(library / "steamapps" / "workshop" / "content" / STELLARIS_APP_ID)
        appworkshop = library / "steamapps" / "workshop" / f"appworkshop_{STELLARIS_APP_ID}.acf"
        if appworkshop.is_file():
            candidates.append(library / "steamapps" / "workshop" / "content" / STELLARIS_APP_ID)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit(
        "Could not find Stellaris workshop content folder. "
        "Pass --workshop-root explicitly, for example --workshop-root \"D:\\Steam\\steamapps\\workshop\\content\\281990\"."
    )


def descriptor_name(mod_root: Path) -> str:
    """Read the user-facing mod name from descriptor.mod when available."""
    descriptor = mod_root / "descriptor.mod"
    if not descriptor.is_file():
        return mod_root.name
    match = re.search(r'^\s*name\s*=\s*"([^"]+)"', read_text(descriptor), flags=re.MULTILINE)
    return match.group(1) if match else mod_root.name


def slugify(value: str) -> str:
    """Create an ASCII folder-safe slug for generated key directories.

    The workshop id is appended later, so collisions between similar names are
    still avoided even though this strips punctuation and non-ASCII text.
    """
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "mod"


def english_source_root(mod_root: Path) -> Path:
    """Return the English localisation root for both Stellaris mod layouts."""
    localisation_root = mod_root / "localisation"
    nested_root = localisation_root / "english"
    if nested_root.is_dir():
        return nested_root
    if localisation_root.is_dir() and any(localisation_root.glob("*_l_english.yml")):
        return localisation_root
    replace_english = localisation_root / "replace" / "english"
    if replace_english.is_dir():
        return replace_english
    replace_root = localisation_root / "replace"
    if replace_root.is_dir() and any(replace_root.glob("*_l_english.yml")):
        return replace_root
    return nested_root


def classify_mod_root(mod_root: Path) -> dict[str, object]:
    """Classify one workshop folder for reporting and target selection."""
    mod_id = mod_root.name
    name = descriptor_name(mod_root) if mod_root.is_dir() else mod_id
    localisation_root = mod_root / "localisation"
    english_root = localisation_root / "english"
    direct_english_files = sorted(localisation_root.glob("*_l_english.yml")) if localisation_root.is_dir() else []
    replace_root = localisation_root / "replace"
    replace_english_files = sorted(replace_root.rglob("*_l_english.yml")) if replace_root.is_dir() else []
    korean_root = localisation_root / "korean"
    localisation_dirs = []
    if localisation_root.is_dir():
        localisation_dirs = sorted(path.name for path in localisation_root.iterdir() if path.is_dir())

    if not mod_root.is_dir():
        category = "missing_mod_folder"
    elif english_root.is_dir():
        category = "english"
    elif direct_english_files:
        category = "english_direct"
    elif replace_english_files:
        category = "replace_english"
    elif not localisation_root.exists():
        category = "no_localisation"
    elif korean_root.is_dir() and len(localisation_dirs) == 1:
        category = "korean_only"
    elif replace_root.is_dir() and len(localisation_dirs) == 1:
        category = "replace_only"
    else:
        category = "localisation_without_english"

    return {
        "mod_id": mod_id,
        "name": name,
        "slug": f"{slugify(name)}__{mod_id}",
        "root": str(mod_root),
        "category": category,
        "localisation_dirs": localisation_dirs,
        "is_target": category in {"english", "english_direct", "replace_english"},
    }


def classify_mods(workshop_root: Path, mod_ids: list[str] | None) -> list[dict[str, object]]:
    """Classify all requested/installed workshop mods.

    Categories `english`, `english_direct`, and `replace_english` are
    processed. `replace_english` is the layout where English files live under
    `localisation/replace`.
    """
    if mod_ids:
        candidates = [workshop_root / mod_id for mod_id in mod_ids]
    else:
        candidates = sorted(path for path in workshop_root.iterdir() if path.is_dir())
    return [classify_mod_root(path) for path in candidates]


def filter_classified_mods(
    classified: list[dict[str, object]],
    mod_filters: list[str],
) -> list[dict[str, object]]:
    """Limit classified mods by generated slug or workshop id."""
    if not mod_filters:
        return classified
    wanted = set(mod_filters)
    return [
        item
        for item in classified
        if str(item.get("slug", "")) in wanted or str(item.get("mod_id", "")) in wanted
    ]


def target_mods_from_classification(classified: list[dict[str, object]], limit: int) -> list[dict[str, str]]:
    """Return processable mods from classification records."""
    targets: list[dict[str, str]] = [
        {
            "mod_id": str(item["mod_id"]),
            "name": str(item["name"]),
            "slug": str(item["slug"]),
            "root": str(item["root"]),
        }
        for item in classified
        if item.get("is_target")
    ]
    return targets[:limit] if limit else targets


def classification_counts(classified: list[dict[str, object]]) -> dict[str, int]:
    """Count classification categories for summaries."""
    counts: dict[str, int] = {}
    for item in classified:
        category = str(item["category"])
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def print_mod_table(workshop_root: Path, mods: list[dict[str, str]]) -> None:
    """Print discovered mods in aligned columns for human scanning."""
    print(f"workshop_root={workshop_root}")
    print(f"mods={len(mods)}")
    if not mods:
        return

    id_width = max(len("mod_id"), *(len(mod["mod_id"]) for mod in mods))
    name_width = max(len("name"), *(len(mod["name"]) for mod in mods))
    slug_width = max(len("slug"), *(len(mod["slug"]) for mod in mods))

    header = f"{'mod_id':<{id_width}}  {'name':<{name_width}}  {'slug':<{slug_width}}  root"
    print(header)
    print("-" * len(header))
    for mod in mods:
        print(
            f"{mod['mod_id']:<{id_width}}  "
            f"{mod['name']:<{name_width}}  "
            f"{mod['slug']:<{slug_width}}  "
            f"{mod['root']}"
        )


def print_discovery_summary(
    workshop_root: Path,
    total_mod_dirs: int,
    target_mods: int,
    skipped_no_english: int,
    counts: dict[str, int],
) -> None:
    """Print the headline counts before doing any substantial work."""
    print(f"workshop_root={workshop_root}", flush=True)
    print(f"total_mod_folders={total_mod_dirs}", flush=True)
    print(f"target_mods_with_localisation_english={target_mods}", flush=True)
    print(f"skipped_without_localisation_english={skipped_no_english}", flush=True)
    print("classification_counts=" + json.dumps(counts, ensure_ascii=False), flush=True)


def parse_stdout_counts(stdout: str) -> dict[str, int | str]:
    """Parse simple key=value lines emitted by child tools."""
    counts: dict[str, int | str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            counts[key] = int(value)
        except ValueError:
            counts[key] = value
    return counts


def cache_path() -> Path:
    """Return the persistent auto-process cache path."""
    return PACK_ROOT / "maintenance" / "cache" / "mod_state.json"


def load_cache() -> dict[str, object]:
    """Load the incremental cache, ignoring missing or stale cache files."""
    path = cache_path()
    if not path.is_file():
        return {"version": CACHE_VERSION, "mods": {}}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {"version": CACHE_VERSION, "mods": {}}
    if payload.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "mods": {}}
    payload.setdefault("mods", {})
    return payload


def save_cache(payload: dict[str, object]) -> None:
    """Persist the incremental cache."""
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def source_signature(mod_root: Path) -> dict[str, int]:
    """Compute a cheap signature of localisation/english source files."""
    localisation_root = mod_root / "localisation"
    files = sorted(localisation_root.rglob("*_l_english.yml")) if localisation_root.is_dir() else []
    latest_mtime_ns = 0
    total_size = 0
    for path in files:
        stat = path.stat()
        latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
        total_size += stat.st_size
    return {
        "file_count": len(files),
        "latest_mtime_ns": latest_mtime_ns,
        "total_size": total_size,
    }


def csv_tree_exists(keys_dir_arg: str) -> bool:
    """Return true if a generated key tree exists and contains CSV files."""
    keys_dir = PACK_ROOT / keys_dir_arg
    return keys_dir.is_dir() and any(keys_dir.rglob("*_key.csv"))


def cache_hit(mod: dict[str, str], keys_dir_arg: str, cache: dict[str, object], force: bool) -> bool:
    """Decide whether extraction can be skipped for an unchanged source tree."""
    if force:
        return False
    mod_cache = cache.get("mods", {})
    if not isinstance(mod_cache, dict):
        return False
    cached = mod_cache.get(mod["mod_id"])
    if not isinstance(cached, dict):
        return False
    if cached.get("source_signature") != source_signature(Path(mod["root"])):
        return False
    return csv_tree_exists(keys_dir_arg)


def step_succeeded(item: dict[str, object], step_name: str) -> bool:
    """Return true when a named step succeeded or was intentionally skipped."""
    for step in item.get("steps", []):
        if not isinstance(step, dict) or step.get("name") != step_name:
            continue
        if step.get("skipped"):
            return True
        return step.get("returncode") == 0
    return False


def update_cache_from_item(cache: dict[str, object], item: dict[str, object]) -> None:
    """Store source signature once extraction completed successfully.

    The cache only answers "can key extraction be skipped next time?", so a
    validation or conflict-report failure should not invalidate a good extract.
    """
    if not step_succeeded(item, "extract_keys"):
        return
    mod_id = str(item["mod_id"])
    mod_root = Path(str(item.get("root", "")))
    if not mod_root.is_dir():
        return
    mods = cache.setdefault("mods", {})
    if isinstance(mods, dict):
        mods[mod_id] = {
            "name": item.get("name", ""),
            "root": str(mod_root),
            "keys_dir": item.get("keys_dir", ""),
            "source_signature": source_signature(mod_root),
        }


def run_tool(command: list[str]) -> dict[str, object]:
    """Run one child tool and capture its output for the JSON summary report."""
    result = subprocess.run(
        command,
        cwd=str(PACK_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def run_or_record(command: list[str], steps: list[dict[str, object]], continue_on_error: bool) -> bool:
    """Compatibility helper for sequential command execution."""
    result = run_tool(command)
    steps.append(result)
    if result["returncode"] != 0 and not continue_on_error:
        return False
    return True


def print_plan_table(workshop_root: Path, planned: list[dict[str, object]], skipped_count: int) -> None:
    """Print dry-run work estimates in aligned columns."""
    print(f"workshop_root={workshop_root}")
    print(f"planned_mods={len(planned)}")
    print(f"skipped_no_english={skipped_count}")
    if not planned:
        return

    columns = [
        ("mod_id", "mod_id"),
        ("name", "name"),
        ("work", "work_files"),
        ("skip", "skip_files"),
        ("new", "created_files"),
        ("upd", "updated_files"),
        ("same", "unchanged_files"),
        ("fallback", "english_fallback_files"),
        ("missing", "missing_key_files"),
        ("conflict", "conflict_key_files"),
        ("status", "status"),
    ]
    widths = {
        label: max(len(label), *(len(str(row.get(field, ""))) for row in planned))
        for label, field in columns
    }
    header = "  ".join(f"{label:<{widths[label]}}" for label, _ in columns)
    print(header)
    print("-" * len(header))
    for row in planned:
        print("  ".join(f"{str(row.get(field, '')):<{widths[label]}}" for label, field in columns))


def print_progress(done: int, total: int, failed: int) -> None:
    """Print a compact one-line progress bar for quiet/auto mode."""
    width = 30
    if total <= 0:
        percent = 100
        filled = width
    else:
        percent = int(done * 100 / total)
        filled = int(width * done / total)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r[{bar}] {done}/{total} {percent:3d}% failed={failed}", end="", flush=True)
    if done >= total:
        print("", flush=True)


def skipped_classifications(classified: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return non-target mod records for JSON reports."""
    skipped: list[dict[str, object]] = []
    for item in classified:
        if item.get("is_target"):
            continue
        skipped.append(
            {
                "mod_id": item.get("mod_id", ""),
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "localisation_dirs": item.get("localisation_dirs", []),
                "root": item.get("root", ""),
            }
        )
    return skipped


def latest_report(folder: Path, pattern: str) -> dict[str, object] | None:
    """Return metadata for the newest matching report file."""
    files = [path for path in folder.glob(pattern) if path.is_file()]
    if not files:
        return None
    newest = max(files, key=lambda path: path.stat().st_mtime_ns)
    stat = newest.stat()
    return {
        "path": str(newest),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def write_report_index(current_report: Path, run_summary: dict[str, object]) -> tuple[Path, Path]:
    """Write a compact index pointing to the latest reports by tool category."""
    reports_root = PACK_ROOT / "maintenance" / "reports"
    categories = {
        "ai_translation": (reports_root / "ai_translation", "*.json"),
        "extraction": (reports_root / "extraction", "*.json"),
        "token_validation": (reports_root / "token_validation", "*"),
        "translation": (reports_root / "translation", "*.json"),
        "validation": (reports_root / "validation", "*"),
        "conflict_resolution": (reports_root / "conflict_resolution", "*"),
        "auto_process": (reports_root / "auto_process", "*.json"),
    }
    latest = {
        name: latest_report(folder, pattern)
        for name, (folder, pattern) in categories.items()
    }
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current_report": str(current_report),
        "latest": latest,
        "last_run": {
            "mode": run_summary.get("mode", ""),
            "workshop_root": run_summary.get("workshop_root", ""),
            "total_mod_folders": run_summary.get("total_mod_folders", 0),
            "target_mods": run_summary.get("target_mods", 0),
            "selected_mods": run_summary.get("selected_mods", 0),
            "processed": len(run_summary.get("processed", [])),
            "failed": run_summary.get("failed", 0),
            "workers": run_summary.get("workers", 0),
            "use_cache": run_summary.get("use_cache", False),
            "import_korean_references": run_summary.get("import_korean_references", False),
            "reference_dry_run": run_summary.get("reference_dry_run", False),
            "dry_run": run_summary.get("dry_run", False),
            "translate": run_summary.get("translate", False),
        },
    }

    index_json = reports_root / "index.json"
    index_md = reports_root / "index.md"
    reports_root.mkdir(parents=True, exist_ok=True)
    index_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    lines = [
        "# Maintenance Report Index",
        "",
        f"- Updated at: {payload['updated_at']}",
        f"- Current report: `{current_report}`",
        "",
        "## Latest Reports",
        "",
    ]
    for name, info in latest.items():
        if info:
            lines.append(f"- {name}: `{info['path']}`")
        else:
            lines.append(f"- {name}: none")
    lines.extend(
        [
            "",
            "## Last Run",
            "",
            f"- Mode: {payload['last_run']['mode']}",
            f"- Total mod folders: {payload['last_run']['total_mod_folders']}",
            f"- Target mods: {payload['last_run']['target_mods']}",
            f"- Selected mods: {payload['last_run']['selected_mods']}",
            f"- Processed: {payload['last_run']['processed']}",
            f"- Failed: {payload['last_run']['failed']}",
            f"- Workers: {payload['last_run']['workers']}",
            f"- Cache enabled: {payload['last_run']['use_cache']}",
            f"- Import Korean references: {payload['last_run']['import_korean_references']}",
            f"- Reference dry-run: {payload['last_run']['reference_dry_run']}",
            f"- Dry-run: {payload['last_run']['dry_run']}",
            f"- Translate: {payload['last_run']['translate']}",
            "",
        ]
    )
    index_md.write_text("\n".join(lines), encoding="utf-8-sig")
    return index_json, index_md


def command_step(name: str, command: list[str]) -> dict[str, object]:
    """Wrap a command with a stable step name for logs and reports."""
    return {"name": name, "command": command}


def skip_step(name: str, reason: str) -> dict[str, object]:
    """Represent a workflow step that can be skipped without running a process."""
    return {
        "name": name,
        "command": [],
        "skip_reason": reason,
    }


def skipped_result(step: dict[str, object]) -> dict[str, object]:
    """Return a child-tool-shaped result for a skipped step."""
    reason = str(step.get("skip_reason", "skipped"))
    return {
        "name": str(step["name"]),
        "command": [],
        "returncode": 0,
        "stdout": f"skipped={reason}",
        "stderr": "",
        "skipped": True,
        "reason": reason,
    }


def plan_mod(
    mod: dict[str, str],
    args: argparse.Namespace,
    workshop_root: Path,
    extract_tool: Path,
    reference_tool: Path,
    export_localisation: Path,
    cache: dict[str, object],
) -> dict[str, object]:
    """Estimate translation work for one mod without writing localisation files."""
    rel_keys_dir = Path(args.keys_root) / mod["slug"]
    keys_dir_arg = str(rel_keys_dir)
    if args.use_cache and cache_hit(mod, keys_dir_arg, cache, args.force):
        extract_result = {
            "name": "extract_keys",
            "command": [],
            "returncode": 0,
            "stdout": "skipped=source unchanged and key CSVs exist",
            "stderr": "",
            "skipped": True,
            "reason": "source unchanged and key CSVs exist",
        }
    else:
        extract_result = run_tool(
            [
                sys.executable,
                str(extract_tool),
                mod["mod_id"],
                keys_dir_arg,
                "--workshop-root",
                str(workshop_root),
                "--report-dir",
                "maintenance/reports/extraction",
            ]
        )
        extract_result["name"] = "extract_keys"
    translation_result: dict[str, object] | None = None
    translation_counts: dict[str, int | str] = {}
    status = "ok"

    if extract_result["returncode"] == 0:
        export_cmd = [
            sys.executable,
            str(export_localisation),
            mod["mod_id"],
            keys_dir_arg,
            "--workshop-root",
            str(workshop_root),
            "--dry-run",
            "--output-root",
            str(output_root(mod["mod_id"], mod["name"], is_integrated_mode(args.integrated))),
        ]
        translation_result = run_tool(export_cmd)
        translation_counts = parse_stdout_counts(str(translation_result["stdout"]))
        if translation_result["returncode"] != 0:
            status = "translation_failed"
    else:
        status = "extract_failed"

    reference_result: dict[str, object] | None = None
    if args.import_korean_references and extract_result["returncode"] == 0:
        reference_result = run_tool(
            [
                sys.executable,
                str(reference_tool),
                "--mod",
                mod["slug"],
                "--workshop-root",
                str(workshop_root),
                "--dry-run",
            ]
        )
        reference_result["name"] = "import_korean_references_dry_run"
        if reference_result["returncode"] != 0 and status == "ok":
            status = "reference_import_failed"

    created = int(translation_counts.get("created_files", 0) or 0)
    updated = int(translation_counts.get("updated_files", 0) or 0)
    unchanged = int(translation_counts.get("unchanged_files", 0) or 0)
    return {
        "mod_id": mod["mod_id"],
        "name": mod["name"],
        "root": mod["root"],
        "keys_dir": str(PACK_ROOT / rel_keys_dir),
        "status": status,
        "work_files": created + updated,
        "skip_files": unchanged,
        "created_files": created,
        "updated_files": updated,
        "unchanged_files": unchanged,
        "processed_keys": int(translation_counts.get("processed_keys", 0) or 0),
        "english_fallback_files": int(translation_counts.get("english_fallback_files", 0) or 0),
        "missing_key_files": int(translation_counts.get("missing_key_files", 0) or 0),
        "conflict_key_files": int(translation_counts.get("conflict_key_files", 0) or 0),
        "extract": extract_result,
        "reference_import": reference_result,
        "translation": translation_result,
    }


def build_commands(
    mod: dict[str, str],
    args: argparse.Namespace,
    workshop_root: Path,
    extract_tool: Path,
    reference_tool: Path,
    translate_tool: Path,
    auto_key_token_tool: Path,
    export_localisation: Path,
    validate_tool: Path,
    conflict_tool: Path,
    cache: dict[str, object],
) -> tuple[str, list[dict[str, object]]]:
    """Build the per-mod command pipeline.

    Each mod gets its own key directory under --keys-root. The validate and
    conflict tools receive explicit report subdirectories so reports do not
    pile up directly under maintenance/reports.
    """
    rel_keys_dir = Path(args.keys_root) / mod["slug"]
    keys_dir_arg = str(rel_keys_dir)
    if args.dry_run:
        commands: list[dict[str, object]] = [
            skip_step("extract_keys", "dry-run mode")
        ]
    elif args.use_cache and cache_hit(mod, keys_dir_arg, cache, args.force):
        commands = [
            skip_step("extract_keys", "source unchanged and key CSVs exist")
        ]
    else:
        commands = [
            command_step(
                "extract_keys",
                [
                    sys.executable,
                    str(extract_tool),
                    mod["mod_id"],
                    keys_dir_arg,
                    "--workshop-root",
                    str(workshop_root),
                    "--report-dir",
                    "maintenance/reports/extraction",
                ],
            )
        ]

    if args.import_korean_references:
        reference_cmd = [
            sys.executable,
            str(reference_tool),
            "--mod",
            mod["slug"],
            "--workshop-root",
            str(workshop_root),
        ]
        if args.reference_dry_run or args.dry_run:
            reference_cmd.append("--dry-run")
        commands.append(
            command_step(
                "import_korean_references_dry_run"
                if args.reference_dry_run or args.dry_run
                else "import_korean_references",
                reference_cmd,
            )
        )

    if args.translate:
        api_key_file = TOOLS_ROOT / "api_key.txt"
        _has_env_key = bool(
            os.environ.get("ANTHROPIC_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )
        if api_key_file.is_file() or _has_env_key:
            commands.append(
                command_step(
                    "translate_keys",
                    [
                        sys.executable,
                        str(translate_tool),
                        "--mod",
                        mod["slug"],
                        "--workers",
                        "1",
                        "--tpm-limit",
                        "2000000",
                    ],
                )
            )
            if args.dry_run:
                commands[-1]["command"].append("--dry-run")
            commands.append(
                command_step(
                    "validate_auto_key_tokens",
                    [
                        sys.executable,
                        str(auto_key_token_tool),
                        "--mod",
                        mod["slug"],
                    ],
                )
            )
        else:
            print(f"warning: --translate skipped for {mod['mod_id']}: api_key.txt not found", flush=True)
            commands.append(skip_step("translate_keys", "api_key.txt not found"))
            commands.append(skip_step("validate_auto_key_tokens", "api_key.txt not found"))

    integrated = is_integrated_mode(args.integrated)
    if not args.skip_translation:
        if not integrated:
            ensure_standalone_mod(mod["mod_id"], mod["name"])
        translation_cmd = [
            sys.executable,
            str(export_localisation),
            mod["mod_id"],
            keys_dir_arg,
            "--workshop-root",
            str(workshop_root),
            "--output-root",
            str(output_root(mod["mod_id"], mod["name"], integrated)),
        ]
        if not args.apply_translations or args.dry_run:
            translation_cmd.append("--dry-run")
        commands.append(
            command_step(
                "translation_apply" if args.apply_translations and not args.dry_run else "translation_dry_run",
                translation_cmd,
            )
        )

    if not args.skip_validation:
        commands.append(
            command_step(
                "validate_outputs",
                [
                sys.executable,
                str(validate_tool),
                mod["mod_id"],
                keys_dir_arg,
                "--workshop-root",
                str(workshop_root),
                "--report-dir",
                "maintenance/reports/validation",
                "--output-root",
                str(output_root(mod["mod_id"], mod["name"], integrated)),
                ],
            )
        )

    if not args.skip_conflict_prepare:
        commands.append(
            command_step(
                "prepare_conflicts",
                [
                sys.executable,
                str(conflict_tool),
                mod["mod_id"],
                keys_dir_arg,
                "--prepare",
                "--workshop-root",
                str(workshop_root),
                "--report-dir",
                "maintenance/reports/conflict_resolution",
                ],
            )
        )

    return keys_dir_arg, commands


def process_mod(
    mod: dict[str, str],
    args: argparse.Namespace,
    workshop_root: Path,
    extract_tool: Path,
    reference_tool: Path,
    translate_tool: Path,
    auto_key_token_tool: Path,
    export_localisation: Path,
    validate_tool: Path,
    conflict_tool: Path,
    cache: dict[str, object],
) -> dict[str, object]:
    """Run all enabled workflow steps for a single mod.

    This function is safe to call from a worker thread because the expensive
    work happens in child Python processes. Terminal lines include the mod id so
    output stays readable even when multiple mods are processed in parallel.
    """
    keys_dir_arg, commands = build_commands(
        mod,
        args,
        workshop_root,
        extract_tool,
        reference_tool,
        translate_tool,
        auto_key_token_tool,
        export_localisation,
        validate_tool,
        conflict_tool,
        cache,
    )
    steps: list[dict[str, object]] = []
    ok = True
    if not args.quiet:
        print(f"[{mod['mod_id']}] start {mod['name']}", flush=True)
    for index, step in enumerate(commands, start=1):
        step_name = str(step["name"])
        if step.get("skip_reason"):
            result = skipped_result(step)
            steps.append(result)
            if not args.quiet:
                print(f"[{mod['mod_id']}] step {index}/{len(commands)} {step_name} skipped ({result['reason']})", flush=True)
            continue
        command = list(step["command"])
        if not args.quiet:
            print(f"[{mod['mod_id']}] step {index}/{len(commands)} {step_name} start", flush=True)
        result = run_tool(command)
        result["name"] = step_name
        steps.append(result)
        ok = result["returncode"] == 0 or args.continue_on_error
        status = "ok" if result["returncode"] == 0 else f"failed rc={result['returncode']}"
        if not args.quiet:
            print(f"[{mod['mod_id']}] step {index}/{len(commands)} {step_name} {status}", flush=True)
        if not ok:
            break
    return {
        "mod_id": mod["mod_id"],
        "name": mod["name"],
        "root": mod["root"],
        "keys_dir": str(PACK_ROOT / keys_dir_arg),
        "ok": all(step["returncode"] == 0 for step in steps),
        "steps": steps,
    }


def main() -> int:
    """Discover mods, process them sequentially or in parallel, and report."""
    args = parse_args()
    apply_mode_preset(args)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    workshop_root = Path(args.workshop_root) if args.workshop_root else detect_workshop_root()
    keys_root = resolve_pack_path(args.keys_root)
    reports_root = PACK_ROOT / "maintenance" / "reports" / "auto_process"
    reports_root.mkdir(parents=True, exist_ok=True)

    if not workshop_root.is_dir():
        raise SystemExit(f"Workshop root not found: {workshop_root}")

    classified = filter_classified_mods(classify_mods(workshop_root, args.mod_ids), args.mod)
    counts = classification_counts(classified)
    total_mod_dirs = len(classified)
    all_eligible_mods = target_mods_from_classification(classified, 0)
    skipped_no_english = max(0, total_mod_dirs - len(all_eligible_mods))
    mods = target_mods_from_classification(classified, args.limit)
    workers = 1 if args.translate else resolve_workers(str(args.workers), args.apply_translations)
    cache = load_cache() if args.use_cache else {"version": CACHE_VERSION, "mods": {}}
    effective_mode = (
        "scan"
        if args.list_mods
        else "plan"
        if args.plan
        else "apply"
        if args.apply_translations
        else args.mode
    )

    if not args.quiet:
        print_discovery_summary(workshop_root, total_mod_dirs, len(all_eligible_mods), skipped_no_english, counts)
        print(f"mode={effective_mode}", flush=True)
        print(f"workers={workers}", flush=True)
        print(f"use_cache={args.use_cache}", flush=True)
        if args.limit:
            print(f"limit={args.limit}", flush=True)
            print(f"selected_mods={len(mods)}", flush=True)

    if args.list_mods:
        if args.list_json:
            print(
                json.dumps(
                    {
                        "workshop_root": str(workshop_root),
                        "classification_counts": counts,
                        "target_mods": mods,
                        "skipped_mods": skipped_classifications(classified),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print_mod_table(workshop_root, mods)
            print("classification_counts=" + json.dumps(counts, ensure_ascii=False))
        return 0

    extract_tool = TOOLS_ROOT / "extract_localisation_keys.py"
    reference_tool = TOOLS_ROOT / "import_korean_references.py"
    translate_tool = TOOLS_ROOT / "translate_keys.py"
    auto_key_token_tool = TOOLS_ROOT / "validate_auto_key_tokens.py"
    export_localisation = TOOLS_ROOT / "export_localisation.py"
    validate_tool = TOOLS_ROOT / "validate_translation_outputs.py"
    conflict_tool = TOOLS_ROOT / "resolve_conflict_translations.py"

    if args.plan:
        if workers == 1:
            planned = [
                plan_mod(mod, args, workshop_root, extract_tool, reference_tool, export_localisation, cache)
                for mod in mods
            ]
        else:
            planned = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_mod = {
                    executor.submit(
                        plan_mod,
                        mod,
                        args,
                        workshop_root,
                        extract_tool,
                        reference_tool,
                        export_localisation,
                        cache,
                    ): mod
                    for mod in mods
                }
                for future in concurrent.futures.as_completed(future_to_mod):
                    mod = future_to_mod[future]
                    try:
                        planned.append(future.result())
                    except Exception as exc:
                        planned.append(
                            {
                                "mod_id": mod["mod_id"],
                                "name": mod["name"],
                                "root": mod["root"],
                                "status": f"failed: {exc!r}",
                                "work_files": 0,
                                "skip_files": 0,
                                "created_files": 0,
                                "updated_files": 0,
                                "unchanged_files": 0,
                                "processed_keys": 0,
                                "english_fallback_files": 0,
                                "missing_key_files": 0,
                                "conflict_key_files": 0,
                            }
                        )
        planned.sort(key=lambda item: str(item["mod_id"]))
        failed_plans = [row for row in planned if row.get("status") != "ok"]
        payload = {
            "timestamp": timestamp,
            "mode": "plan",
            "workshop_root": str(workshop_root),
            "total_mod_folders": total_mod_dirs,
            "target_mods": len(all_eligible_mods),
            "selected_mods": len(mods),
            "planned_mods": len(planned),
            "skipped_no_english": skipped_no_english,
            "classification_counts": counts,
            "workers": workers,
            "use_cache": args.use_cache,
            "totals": {
                "work_files": sum(int(row.get("work_files", 0) or 0) for row in planned),
                "skip_files": sum(int(row.get("skip_files", 0) or 0) for row in planned),
                "created_files": sum(int(row.get("created_files", 0) or 0) for row in planned),
                "updated_files": sum(int(row.get("updated_files", 0) or 0) for row in planned),
                "unchanged_files": sum(int(row.get("unchanged_files", 0) or 0) for row in planned),
                "processed_keys": sum(int(row.get("processed_keys", 0) or 0) for row in planned),
                "english_fallback_files": sum(int(row.get("english_fallback_files", 0) or 0) for row in planned),
                "missing_key_files": sum(int(row.get("missing_key_files", 0) or 0) for row in planned),
                "conflict_key_files": sum(int(row.get("conflict_key_files", 0) or 0) for row in planned),
            },
            "mods": planned,
        }
        plan_report_path = reports_root / f"auto_process_plan_{timestamp}.json"
        payload["plan_report"] = str(plan_report_path)
        plan_report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        if args.use_cache:
            for row in planned:
                extract_result = row.get("extract")
                if isinstance(extract_result, dict):
                    update_cache_from_item(
                        cache,
                        {
                            "mod_id": row.get("mod_id", ""),
                            "name": row.get("name", ""),
                            "root": row.get("root", ""),
                            "keys_dir": row.get("keys_dir", ""),
                            "steps": [extract_result],
                        },
                    )
            save_cache(cache)
        index_json, index_md = write_report_index(
            plan_report_path,
            {
                **payload,
                "processed": planned,
                "failed": len(failed_plans),
            },
        )
        if args.plan_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_plan_table(workshop_root, planned, skipped_no_english)
            print("totals=" + json.dumps(payload["totals"], ensure_ascii=False))
            print(f"plan_report={plan_report_path}")
            print(f"report_index={index_json}")
            print(f"report_index_md={index_md}")
        return 1 if failed_plans else 0

    summary: dict[str, object] = {
        "timestamp": timestamp,
        "mode": effective_mode,
        "workshop_root": str(workshop_root),
        "keys_root": str(keys_root),
        "apply_translations": args.apply_translations,
        "import_korean_references": args.import_korean_references,
        "reference_dry_run": args.reference_dry_run,
        "dry_run": args.dry_run,
        "translate": args.translate,
        "workers": workers,
        "use_cache": args.use_cache,
        "force": args.force,
        "cache_path": str(cache_path()) if args.use_cache else "",
        "total_mod_folders": total_mod_dirs,
        "target_mods": len(all_eligible_mods),
        "selected_mods": len(mods),
        "skipped_without_localisation_english": skipped_no_english,
        "classification_counts": counts,
        "processed": [],
        "skipped_or_missing": skipped_classifications(classified),
    }

    if args.apply_translations and workers > 1 and not args.quiet:
        print("warning: --apply-translations with --workers > 1 can write multiple target files in parallel.")

    completed_count = 0
    failed_count = 0
    if args.quiet:
        print_progress(completed_count, len(mods), failed_count)

    if workers == 1:
        for mod in mods:
            item = process_mod(
                mod,
                args,
                workshop_root,
                extract_tool,
                reference_tool,
                translate_tool,
                auto_key_token_tool,
                export_localisation,
                validate_tool,
                conflict_tool,
                cache,
            )
            summary["processed"].append(item)
            if args.use_cache:
                update_cache_from_item(cache, item)
                save_cache(cache)
            completed_count += 1
            if not item["ok"]:
                failed_count += 1
            if args.quiet:
                print_progress(completed_count, len(mods), failed_count)
            if not args.quiet:
                print(f"{item['mod_id']} {item['name']}: {'ok' if item['ok'] else 'failed'}")
            if not item["ok"] and not args.continue_on_error:
                break
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_mod = {
                executor.submit(
                    process_mod,
                    mod,
                    args,
                    workshop_root,
                    extract_tool,
                    reference_tool,
                    translate_tool,
                    auto_key_token_tool,
                    export_localisation,
                    validate_tool,
                    conflict_tool,
                    cache,
                ): mod
                for mod in mods
            }
            for future in concurrent.futures.as_completed(future_to_mod):
                mod = future_to_mod[future]
                try:
                    item = future.result()
                except Exception as exc:
                    item = {
                        "mod_id": mod["mod_id"],
                        "name": mod["name"],
                        "root": mod["root"],
                        "keys_dir": "",
                        "ok": False,
                        "steps": [{"name": "auto_process", "command": [], "returncode": 1, "stdout": "", "stderr": repr(exc)}],
                    }
                summary["processed"].append(item)
                if args.use_cache:
                    update_cache_from_item(cache, item)
                    save_cache(cache)
                completed_count += 1
                if not item["ok"]:
                    failed_count += 1
                if args.quiet:
                    print_progress(completed_count, len(mods), failed_count)
                if not args.quiet:
                    print(f"{item['mod_id']} {item['name']}: {'ok' if item['ok'] else 'failed'}")

    failures = [item for item in summary["processed"] if not item["ok"]]
    summary["failed"] = len(failures)
    if args.use_cache:
        save_cache(cache)

    report_path = reports_root / f"run_pipeline_report_{timestamp}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    index_json, index_md = write_report_index(report_path, summary)

    print(f"mods={len(mods)}")
    print(f"processed={len(summary['processed'])}")
    print(f"failed={len(failures)}")
    print(f"report={report_path}")
    print(f"report_index={index_json}")
    print(f"report_index_md={index_md}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
