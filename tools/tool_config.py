"""번역 유지보수 도구들이 공통으로 쓰는 설정과 작은 유틸 모음.

경로 해석·텍스트 읽기·CSV 쓰기처럼 여러 도구에 흩어지기 쉬운 헬퍼를 한 곳에 둔다.
도구에서 똑같은 함수를 다시 정의하지 말고 여기서 import해 재사용한다.

- 경로:   resolve_pack_path / pack_path / workshop_root / translation_keys_root
- 텍스트: read_text (BOM·이상 바이트를 견디며 읽기)
- 모드:   descriptor_name (descriptor.mod의 name="..." 값)
- CSV:    open_csv_write + csv_writer / csv_dict_writer (LF + QUOTE_MINIMAL 강제)
"""

from __future__ import annotations

import configparser
import csv
import os
import re
from pathlib import Path
from typing import IO, Iterable

PACK_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACK_ROOT / "maintenance" / "tooling.ini"
TRANSLATION_KEYS_ENV = "STELLARIS_TRANSLATION_KEYS_DIR"
DEFAULT_TRANSLATION_KEYS = "maintenance/translation_keys"
DEFAULT_WORKSHOP_ROOT = r"D:\Program Files (x86)\Steam\steamapps\workshop\content\281990"

# CSV 행 구분자는 항상 LF로 고정한다. csv 모듈 기본값은 CRLF라서, Windows에서
# 도구가 LF 원본 CSV를 다시 쓰면 모든 줄이 CRLF로 바뀌어 전체 파일이 변경된 것처럼
# 보인다(실제 내용 변경이 EOL 노이즈에 묻힘). 아래 헬퍼로만 CSV를 쓰도록 통일한다.
CSV_LINE_TERMINATOR = "\n"


def open_csv_write(path: Path) -> IO[str]:
    """Open a path for CSV writing with newline translation disabled.

    csv.writer가 직접 줄 끝을 제어하도록 ``newline=""``로 연다. 줄 끝은 함께 쓰는
    ``csv_writer`` / ``csv_dict_writer``가 LF로 emit한다.
    """
    return path.open("w", encoding="utf-8-sig", newline="")


def csv_writer(handle: IO[str], **kwargs: object) -> "csv._writer":
    """csv.writer wrapper that emits LF line endings instead of the CRLF default."""
    kwargs.setdefault("lineterminator", CSV_LINE_TERMINATOR)
    return csv.writer(handle, **kwargs)


def csv_dict_writer(
    handle: IO[str], fieldnames: Iterable[str], **kwargs: object
) -> csv.DictWriter:
    """csv.DictWriter wrapper that emits LF line endings instead of the CRLF default."""
    kwargs.setdefault("lineterminator", CSV_LINE_TERMINATOR)
    return csv.DictWriter(handle, fieldnames=fieldnames, **kwargs)


def _read_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if CONFIG_PATH.is_file():
        config.read(CONFIG_PATH, encoding="utf-8-sig")
    return config


def pack_path(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PACK_ROOT / path


def read_text(path: Path) -> str:
    """Steam/Paradox가 쓰는 텍스트를 BOM·이상 바이트를 견디며 읽는다."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def descriptor_name(mod_root: Path) -> str:
    """descriptor.mod의 `name="..."` 값을 반환한다. 없으면 폴더 이름."""
    descriptor = mod_root / "descriptor.mod"
    if not descriptor.is_file():
        return mod_root.name
    match = re.search(r'^\s*name\s*=\s*"([^"]+)"', read_text(descriptor), flags=re.MULTILINE)
    return match.group(1) if match else mod_root.name


def translation_keys_root(validate: bool = False) -> Path:
    """Return the translation keys root directory.

    validate=True이면 경로가 없을 때 SystemExit을 던진다.
    파이프라인 시작 시점 등 일찍 실패시키고 싶을 때 쓴다.
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
