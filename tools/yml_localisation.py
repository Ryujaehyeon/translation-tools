"""Stellaris 로컬라이제이션 YML 한 줄을 파싱하는 공유 헬퍼.

extract/export/import/validate 계열 도구가 제각기 복붙하던 ``ENTRY_RE`` ·
``HEADER_RE`` 와 그 소비 로직을 한곳에 모은다. 정규식은 선행 공백을 캡처하는
4그룹 형태로 통일했다(indent, key, version, value). 3그룹 변종(선행 ``\\s*`` 를
캡처하지 않던 형태)과 매칭 동작은 동일하다 — 앞의 ``\\s*`` 를 캡처 그룹으로 바꿔도
무엇이 매치되는지는 변하지 않으므로, 각 도구는 필요한 필드만 골라 쓰면 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 그룹: (1) indent 선행 공백, (2) key, (3) version(`:0` 등의 숫자, 없으면 None),
# (4) value. version 앞뒤의 공백은 정규식이 흡수한다.
ENTRY_RE = re.compile(r"^(\s*)([^:#\s][^:]*)\s*:\s*(?:(-?\d+)\s*)?(.*)$")
HEADER_RE = re.compile(r"^\s*l_[A-Za-z_]+:\s*$")


@dataclass(frozen=True)
class LocalisationEntry:
    """``ENTRY_RE`` 로 파싱한 로컬라이제이션 한 줄."""

    indent: str
    key: str
    version: str | None
    value: str


def parse_entry(line: str) -> LocalisationEntry | None:
    """로컬라이제이션 한 줄을 파싱한다. 항목 형식이 아니면 ``None`` 을 반환한다."""
    match = ENTRY_RE.match(line)
    if match is None:
        return None
    return LocalisationEntry(
        indent=match.group(1),
        key=match.group(2),
        version=match.group(3),
        value=match.group(4),
    )
