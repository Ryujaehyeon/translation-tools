"""번역 트리(원본 english ↔ key CSV ↔ korean) 경로/렌더링 공유 헬퍼.

extract/export/validate/resolve 계열 도구가 제각기 복붙하던 소스 탐색·경로 매핑·
로컬라이제이션 렌더링·한국어 충돌 인덱스 로직을 한곳에 모은다. 시그니처는 기존
정본 구현을 그대로 옮겼고 동작도 동일하다.

- write_text: 생성 파일을 BOM+LF로 쓴다.
- discover_english_sources / csv_path_for / source_path_for / target_path_for:
  english↔csv↔korean 트리 사이 경로 매핑.
- render_entry / parse_rendered_entries: `:0` vs bare-colon 스타일을 보존해
  로컬라이제이션 한 줄을 렌더/파싱한다.
- collect_rendered_values / conflicts_from_values / build_translation_index:
  korean 트리를 스캔해 단일값 번역과 충돌을 집계한다.
"""

from __future__ import annotations

from pathlib import Path

from tool_config import read_text
from yml_localisation import HEADER_RE, parse_entry


def write_text(path: Path, text: str) -> None:
    """생성 로컬라이제이션 텍스트를 BOM과 LF 줄바꿈으로 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")


def discover_english_sources(mod_root: Path) -> list[tuple[Path, Path, Path]]:
    """원본 파일을 (source_file, source_root, csv_prefix) 튜플로 반환한다."""
    localisation_root = mod_root / "localisation"
    candidates: list[tuple[Path, Path, bool]] = [
        (localisation_root / "english", Path(), True),
        (localisation_root, Path(), False),
        (localisation_root / "replace" / "english", Path("replace"), True),
        (localisation_root / "replace", Path("replace"), False),
    ]
    sources: list[tuple[Path, Path, Path]] = []
    seen: set[Path] = set()
    for source_root, csv_prefix, recursive in candidates:
        if not source_root.is_dir():
            continue
        files = sorted(
            source_root.rglob("*_l_english.yml")
            if recursive
            else source_root.glob("*_l_english.yml")
        )
        for source_file in files:
            resolved = source_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            sources.append((source_file, source_root, csv_prefix))
    return sources


def csv_path_for(
    source_file: Path, source_root: Path, csv_root: Path, csv_prefix: Path = Path()
) -> Path:
    """원본 english yml 경로를 대응하는 *_key.csv 경로로 매핑한다."""
    relative = source_file.relative_to(source_root)
    name = relative.name
    if name.endswith("_l_english.yml"):
        name = name[: -len("_l_english.yml")] + "_key.csv"
    else:
        name = relative.stem + "_key.csv"
    return csv_root / csv_prefix / relative.parent / name


def source_path_for(csv_path: Path, csv_root: Path, mod_root: Path) -> Path:
    """key CSV 경로를 원본 english yml 경로로 되돌려 매핑한다.

    비 `_key.csv` 이름은 stem 폴백으로 관용 처리한다. 호출자가 전부
    rglob("*_key.csv") 결과만 넘기므로 이 분기는 실사용에서 도달하지 않는다
    (export/resolve의 옛 ValueError 분기도 같은 이유로 도달 불가 코드였다).
    """
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    source_name = (
        name[: -len("_key.csv")] + "_l_english.yml"
        if name.endswith("_key.csv")
        else relative.stem + "_l_english.yml"
    )
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


def target_path_for(csv_path: Path, csv_root: Path, korean_root: Path) -> Path:
    """key CSV 경로를 생성 대상 *_l_korean.yml 경로로 매핑한다."""
    relative = csv_path.relative_to(csv_root)
    name = relative.name
    if not name.endswith("_key.csv"):
        return korean_root / relative.parent / (relative.stem + "_l_korean.yml")
    return korean_root / relative.parent / (name[: -len("_key.csv")] + "_l_korean.yml")


def render_entry(key: str, version: str | None, value: str) -> str:
    """`:0` vs bare-colon 스타일을 보존해 로컬라이제이션 한 줄을 렌더한다."""
    if version is None:
        return f" {key}: {value}".rstrip()
    return f" {key}:{version} {value}".rstrip()


def parse_rendered_entries(path: Path) -> dict[str, str]:
    """로컬라이제이션 파일을 key -> 렌더된 한 줄 딕셔너리로 파싱한다.

    렌더된 줄은 키의 버전 스타일(`:0` 또는 bare `:`)을 보존해 출력이 원본이나
    기존 한국어 파일에 가깝게 유지되도록 한다.
    """
    entries: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if HEADER_RE.match(line):
            continue
        entry = parse_entry(line)
        if entry is None:
            continue
        key = entry.key.strip()
        entries[key] = render_entry(key, entry.version, entry.value)
    return entries


def collect_rendered_values(korean_root: Path) -> dict[str, dict[str, set[str]]]:
    """korean_root의 *_l_korean.yml 전체를 스캔해 key -> {rendered -> {relpath}} 집계."""
    values_by_key: dict[str, dict[str, set[str]]] = {}
    for path in sorted(korean_root.rglob("*_l_korean.yml")):
        rel_path = str(path.relative_to(korean_root))
        for key, rendered in parse_rendered_entries(path).items():
            values_by_key.setdefault(key, {}).setdefault(rendered, set()).add(rel_path)
    return values_by_key


def conflicts_from_values(
    values_by_key: dict[str, dict[str, set[str]]],
) -> dict[str, list[dict[str, object]]]:
    """2개 이상 distinct rendered를 가진 key만 [{"value":..., "sources": sorted}] (value 정렬) 반환."""
    conflicts: dict[str, list[dict[str, object]]] = {}
    for key, values in values_by_key.items():
        if len(values) <= 1:
            continue
        conflicts[key] = [
            {"value": value, "sources": sorted(sources)}
            for value, sources in sorted(values.items())
        ]
    return conflicts


def build_translation_index(
    korean_root: Path,
) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
    """(단일값 번역 dict, 충돌 dict) 반환 — export_localisation.build_translation_index와 동일 결과."""
    values_by_key = collect_rendered_values(korean_root)
    translations: dict[str, str] = {}
    for key, values in values_by_key.items():
        if len(values) == 1:
            translations[key] = next(iter(values))
    conflicts = conflicts_from_values(values_by_key)
    return translations, conflicts
