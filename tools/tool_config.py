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


def translation_keys_root(validate: bool = False) -> Path:
    """Return the translation keys root directory.

    validate=True のとき、パスが存在しなければ SystemExit を送出する。
    パイプライン起動時など、早期に失敗させたい場合に使う。
    """
    raw = os.environ.get(TRANSLATION_KEYS_ENV, "").strip()
    if not raw:
        config = _read_config()
        raw = config.get("paths", "translation_keys", fallback=DEFAULT_TRANSLATION_KEYS).strip()
    path = pack_path(raw or DEFAULT_TRANSLATION_KEYS)
    if validate and not path.is_dir():
        raise SystemExit(
            f"translation_keys 디렉토리를 찾을 수 없습니다: {path}\n"
            f"tooling.ini의 [paths] translation_keys 또는 "
            f"{TRANSLATION_KEYS_ENV} 환경 변수를 확인하세요."
        )
    return path


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


def is_integrated_mode(cli_flag: bool) -> bool:
    """cli_flag(--integrated)가 있으면 True.
    없으면 tooling.ini의 [output] mode 값을 읽는다.
    ini에 항목이 없으면 False (standalone).
    """
    if cli_flag:
        return True
    config = _read_config()
    raw = config.get("output", "mode", fallback="").strip().lower()
    return raw == "integrated"


def output_root(mod_id: str, mod_name: str, integrated: bool) -> Path:
    """Return the localisation/korean output root for a mod.

    integrated=True  → shared integrated_korean_translation_pack folder
    integrated=False → per-mod folder named "<slug>__<mod_id>_korean" next to translation-tools
    """
    if integrated:
        return PACK_ROOT.parent / "integrated_korean_translation_pack" / "localisation" / "korean"
    slug = "".join(c if c.isalnum() else "_" for c in mod_name.lower()).strip("_")
    folder_name = f"{slug}__{mod_id}_korean"
    return PACK_ROOT.parent / folder_name / "localisation" / "korean"


def resolve_pack_path(raw: str | Path) -> Path:
    """Relative 경로는 PACK_ROOT 기준으로, 절대 경로는 그대로 반환."""
    path = Path(raw)
    return path if path.is_absolute() else PACK_ROOT / path


def english_source_root(mod_root: Path) -> Path:
    """모드의 English 로컬라이제이션 루트를 반환한다.

    Stellaris 모드는 두 가지 레이아웃을 사용한다:
      - localisation/english/
      - localisation/*_l_english.yml (직접 배치)
    replace 서브디렉토리도 동일하게 탐색한다.
    반환값이 실제로 존재하지 않을 수 있다 — 호출자가 확인해야 한다.
    """
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


def ensure_standalone_mod(mod_id: str, mod_name: str) -> Path:
    """Create a minimal Stellaris mod folder for a standalone Korean addon.

    Returns the mod root (parent of localisation/).
    Skips descriptor.mod creation if it already exists.
    """
    slug = "".join(c if c.isalnum() else "_" for c in mod_name.lower()).strip("_")
    folder_name = f"{slug}__{mod_id}_korean"
    mod_root = PACK_ROOT.parent / folder_name
    descriptor = mod_root / "descriptor.mod"
    if not descriptor.is_file():
        mod_root.mkdir(parents=True, exist_ok=True)
        kr_name = f"{mod_name} KR"
        descriptor.write_text(
            f'version="1.0"\n'
            f'tags={{\n    "Translation"\n    "Localisation"\n}}\n'
            f'name="{kr_name}"\n'
            f'supported_version="*"\n'
            f'path="mod/{folder_name}"\n',
            encoding="utf-8",
        )
    return mod_root
