#!/usr/bin/env python3
"""Discover and classify Stellaris workshop mods for the pipeline.

Locates the Steam workshop content directory from libraryfolders.vdf and
classifies each mod folder by its localisation layout, so the orchestrator can
select the English-source mods worth processing. This module only produces
data; human-facing display of the results stays in the caller.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tool_config import descriptor_name, read_text, slugify

STELLARIS_APP_ID = "281990"


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
        'Pass --workshop-root explicitly, for example --workshop-root "D:\\Steam\\steamapps\\workshop\\content\\281990".'
    )


def classify_mod_root(mod_root: Path) -> dict[str, object]:
    """Classify one workshop folder for reporting and target selection."""
    mod_id = mod_root.name
    name = descriptor_name(mod_root) if mod_root.is_dir() else mod_id
    localisation_root = mod_root / "localisation"
    english_root = localisation_root / "english"
    direct_english_files = (
        sorted(localisation_root.glob("*_l_english.yml")) if localisation_root.is_dir() else []
    )
    replace_root = localisation_root / "replace"
    replace_english_files = (
        sorted(replace_root.rglob("*_l_english.yml")) if replace_root.is_dir() else []
    )
    korean_root = localisation_root / "korean"
    localisation_dirs = []
    if localisation_root.is_dir():
        localisation_dirs = sorted(
            path.name for path in localisation_root.iterdir() if path.is_dir()
        )

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


def target_mods_from_classification(
    classified: list[dict[str, object]], limit: int
) -> list[dict[str, str]]:
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
