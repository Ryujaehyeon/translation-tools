"""번역 도구들이 공통으로 쓰는 CSV·JSON 입출력 헬퍼.

- CSV 읽기: read_csv_dicts (utf-8-sig + DictReader로 헤더와 전체 행을 뽑는다)
- 백업:     copy_csv_backup (원본을 backup_dir 아래 상대경로 그대로 복사)
- JSON:     write_json (리포트를 UTF-8 BOM으로 저장 — 기존 리포트 포맷 유지)

CSV *쓰기* 는 도구마다 임시파일·quoting 처리가 미묘하게 달라 여기서 통합하지 않는다.
줄 끝(LF) 강제는 tool_config.csv_writer / csv_dict_writer가 담당한다.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


def read_csv_dicts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """CSV를 읽어 (헤더 목록, 행 dict 목록)을 반환한다.

    utf-8-sig로 열어 BOM을 흡수하고 ``newline=""`` 로 열어 csv 모듈이 줄바꿈을
    직접 다루게 한다.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def copy_csv_backup(path: Path, backup_dir: Path, source_root: Path) -> Path:
    """``path`` 를 ``backup_dir`` 아래로 복사하고 복사본 경로를 반환한다.

    ``source_root`` 기준 상대경로를 유지해 백업 트리를 만든다. ``source_root`` 밖의
    파일이면 파일명만 써서 ``backup_dir`` 바로 아래에 둔다.
    """
    try:
        rel = path.relative_to(source_root)
    except ValueError:
        rel = Path(path.name)
    dest = backup_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def write_json(path: Path, payload: object) -> None:
    """리포트 payload를 UTF-8 BOM JSON으로 저장한다(기존 리포트 포맷 유지)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
