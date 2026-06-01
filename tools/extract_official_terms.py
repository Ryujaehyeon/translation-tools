#!/usr/bin/env python3
"""공식 Stellaris 한국어 번역에서 용어집 CSV 초안을 생성한다.

영문 원본(l_english)과 한국어 번역(l_korean)을 키 기준으로 매핑하여
english, korean 쌍을 term_glossary.csv로 출력한다.

사용:
    python tools/extract_official_terms.py
    python tools/extract_official_terms.py --output maintenance/term_glossary.csv
    python tools/extract_official_terms.py --max-len 40  # 번역문 최대 길이 제한
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent

DEFAULT_OFFICIAL_KOREAN = Path(
    r"D:\Program Files (x86)\Steam\steamapps\common\Stellaris\localisation\korean"
)
DEFAULT_OFFICIAL_ENGLISH = Path(
    r"D:\Program Files (x86)\Steam\steamapps\common\Stellaris\localisation\english"
)
DEFAULT_OUTPUT = PACK_ROOT / "maintenance" / "term_glossary.csv"

ENTRY_RE = re.compile(r"^\s*([^:#\s][^:]*?)\s*:\s*(?:-?\d+\s*)?(.*)$")
HEADER_RE = re.compile(r"^\s*l_[A-Za-z_]+:\s*$")
# 토큰 포함 여부 검사
TOKEN_RE = re.compile(r"\$[^$]+\$|£[^£]+£|\[[^\]]+\]|§.")
# 따옴표 벗기기
QUOTE_RE = re.compile(r'^"(.*)"$', re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공식 번역에서 용어집 CSV 추출")
    parser.add_argument("--korean-dir", default=str(DEFAULT_OFFICIAL_KOREAN))
    parser.add_argument("--english-dir", default=str(DEFAULT_OFFICIAL_ENGLISH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-len", type=int, default=50, help="번역문 최대 글자 수 (기본 50)")
    parser.add_argument("--overwrite", action="store_true", help="기존 파일 덮어쓰기")
    return parser.parse_args()


def parse_yml(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return entries
    for line in text.splitlines():
        if HEADER_RE.match(line):
            continue
        m = ENTRY_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        raw = m.group(2).strip()
        qm = QUOTE_RE.match(raw)
        value = qm.group(1) if qm else raw
        if key:
            entries[key] = value
    return entries


def scan_dir(directory: Path) -> dict[str, str]:
    all_entries: dict[str, str] = {}
    if not directory.is_dir():
        return all_entries
    for path in sorted(directory.rglob("*.yml")):
        entries = parse_yml(path)
        # 나중 파일이 같은 키를 덮어쓰지 않도록 (첫 번째 등장 우선)
        for k, v in entries.items():
            if k not in all_entries:
                all_entries[k] = v
    return all_entries


# 일반 영어 단어 제외 목록 (게임 전용 용어가 아닌 것들)
_COMMON_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "from",
    "into",
    "onto",
    "about",
    "and",
    "or",
    "but",
    "if",
    "as",
    "so",
    "yet",
    "nor",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "they",
    "them",
    "their",
    "our",
    "your",
    "my",
    "his",
    "her",
    "we",
    "you",
    "he",
    "she",
    "not",
    "no",
    "all",
    "any",
    "each",
    "every",
    "more",
    "most",
    "other",
    "also",
    "than",
    "then",
    "when",
    "where",
    "which",
    "who",
    "how",
    "what",
    "new",
    "old",
    "get",
    "use",
    "used",
    "using",
    "make",
    "made",
    "take",
    "give",
    "given",
    "start",
    "end",
    "home",
    "base",
    "time",
    "way",
    "work",
    "level",
    "point",
    "points",
    "value",
    "size",
    "large",
    "small",
    "high",
    "low",
    "number",
    "total",
    "amount",
    "type",
    "set",
    "add",
    "added",
    "increase",
    "decrease",
    "reduce",
    "gain",
    "gains",
    "lose",
    "lost",
    "effect",
    "effects",
    "bonus",
    "penalty",
    "cost",
    "costs",
    "rate",
    "chance",
    "per",
    "max",
    "min",
    "unit",
    "units",
    "group",
    "name",
    "description",
    "note",
    "notes",
    "status",
    "state",
    "class",
    "list",
}


def is_good_term(english: str, korean: str, max_len: int) -> bool:
    """용어집에 포함할 가치가 있는 쌍인지 판단."""
    if not english or not korean:
        return False
    # 토큰 포함된 값은 제외
    if TOKEN_RE.search(english) or TOKEN_RE.search(korean):
        return False
    # 한글이 없으면 제외
    if not re.search(r"[가-힣]", korean):
        return False
    # 번역문이 너무 길면 제외 (문장이지 용어가 아님)
    if len(korean) > max_len:
        return False
    # 영문이 숫자/특수문자만이면 제외
    if not re.search(r"[A-Za-z]", english):
        return False
    # 개행 포함이면 제외
    if "\\n" in english or "\\n" in korean:
        return False
    # 영문이 5자 미만이면 제외 (너무 짧은 단어는 오매칭 위험)
    if len(english.strip()) < 5:
        return False
    # 일반 영어 단어면 제외
    if english.strip().lower() in _COMMON_WORDS:
        return False
    # 영문이 3단어 초과면 문장으로 간주하고 제외
    words = english.strip().split()
    if len(words) > 3:
        return False
    # 영문이 여러 단어인 경우 각 단어가 모두 일반 단어면 제외
    if all(w.lower() in _COMMON_WORDS for w in words):
        return False
    return True


def main() -> int:
    args = parse_args()
    output = Path(args.output)

    if output.exists() and not args.overwrite:
        print(f"이미 존재합니다: {output}")
        print("덮어쓰려면 --overwrite 옵션을 사용하세요.")
        print("기존 파일을 유지합니다.")
        return 0

    print(f"영어 스캔 중: {args.english_dir}")
    english_index = scan_dir(Path(args.english_dir))
    print(f"  → {len(english_index)}개 키")

    print(f"한국어 스캔 중: {args.korean_dir}")
    korean_index = scan_dir(Path(args.korean_dir))
    print(f"  → {len(korean_index)}개 키")

    # 게임 전용 용어 키 접두어 — 이 패턴의 키만 추출
    TERM_KEY_PREFIXES = (
        "job_",
        "building_",
        "tech_",
        "trait_",
        "civic_",
        "origin_",
        "policy_",
        "tradition_",
        "ap_",
        "edict_",
        "decision_",
        "deposit_",
        "modifier_",
        "planet_class_",
        "pc_",
        "resource_",
        "pop_category_",
        "councilor_",
        "agenda_",
        "army_",
        "ship_",
        "weapon_",
        "component_",
        "federation_",
        "megastructure_",
        "starbase_",
        "district_",
        "sector_",
        "situation_",
        "crisis_",
        "ethic_",
        "authority_",
        "government_",
        "species_class_",
        "species_archetype_",
    )

    # 영어-한국어 매핑
    rows: list[dict[str, str]] = []
    for key, korean in sorted(korean_index.items()):
        # 게임 전용 키 접두어를 가진 것만 처리
        if not any(key.startswith(p) for p in TERM_KEY_PREFIXES):
            continue
        english = english_index.get(key, "")
        if not english:
            continue
        if not is_good_term(english, korean, args.max_len):
            continue
        rows.append({"english": english, "korean": korean, "key": key})

    # 중복 english 제거 (같은 영어 단어가 여러 키에 쓰일 수 있음)
    seen: dict[str, str] = {}
    deduped: list[dict[str, str]] = []
    for row in rows:
        eng = row["english"].strip().lower()
        if eng in seen:
            continue
        seen[eng] = row["korean"]
        deduped.append(row)

    print(f"추출된 용어 쌍: {len(deduped)}개")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["english", "korean", "key"])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"저장 완료: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
