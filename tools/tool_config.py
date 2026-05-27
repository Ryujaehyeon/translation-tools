"""Shared configuration for translation maintenance tools."""

from __future__ import annotations

import configparser
import os
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACK_ROOT / "maintenance" / "tooling.ini"
TRANSLATION_KEYS_ENV = "STELLARIS_TRANSLATION_KEYS_DIR"
DEFAULT_TRANSLATION_KEYS = "maintenance/translation_keys"
DEFAULT_WORKSHOP_ROOT = r"D:\Program Files (x86)\Steam\steamapps\workshop\content\281990"


def _read_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if CONFIG_PATH.is_file():
        config.read(CONFIG_PATH, encoding="utf-8-sig")
    return config


def pack_path(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PACK_ROOT / path


def translation_keys_root() -> Path:
    raw = os.environ.get(TRANSLATION_KEYS_ENV, "").strip()
    if not raw:
        config = _read_config()
        raw = config.get("paths", "translation_keys", fallback=DEFAULT_TRANSLATION_KEYS).strip()
    return pack_path(raw or DEFAULT_TRANSLATION_KEYS)


def translation_keys_root_arg() -> str:
    root = translation_keys_root()
    try:
        return str(root.relative_to(PACK_ROOT))
    except ValueError:
        return str(root)


def workshop_root() -> Path:
    raw = os.environ.get("STELLARIS_WORKSHOP_ROOT", "").strip()
    if not raw:
        config = _read_config()
        raw = config.get("paths", "workshop_root", fallback=DEFAULT_WORKSHOP_ROOT).strip()
    return Path(raw or DEFAULT_WORKSHOP_ROOT)
