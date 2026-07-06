#!/usr/bin/env python3
"""translate_keys.py 순수 텍스트/토큰 함수의 현재 동작을 고정하는 특성화 테스트.

곧 예정된 "순수 함수 별도 모듈 추출" 리팩토링의 회귀 게이트다. 기대값은
2026-07 시점 구현이 실제로 반환한 값을 리터럴로 고정한 것이며(특성화 테스트),
현재 동작이 의심스러운 케이스도 그대로 고정하고 `# NOTE: 버그 의심` 주석으로만
표시했다. 기존 파일을 읽거나 쓰지 않는 순수 로컬 검증 — API 호출 없음.

사용:
  python3 tools/test_translation_rules.py   # 실패 있으면 목록 출력 후 exit 1
"""

from __future__ import annotations

import contextlib
import io
import tempfile
from collections.abc import Callable
from pathlib import Path

from translate_keys import (
    HARD_TOKEN_TYPES,
    CsvCell,
    _fallback_glossary,
    auto_patch_tokens,
    clean_quote_noise,
    console_text,
    extract_tokens,
    find_matching_terms,
    fix_section_sign_corruption,
    hard_tokens_differ,
    has_quote_noise,
    has_source,
    is_suspicious_translation,
    is_token_only,
    load_glossary,
    normalize_csv_cell,
    protect_tokens,
    restore_protected_tokens,
    strip_code_fence,
    strip_extra_color_codes,
    strip_prompt_echo,
    strip_wrapping_quotes,
    token_delta,
    tokens_match,
)

# (label, 실행 thunk, 기대값). 기대값은 반드시 리터럴로 고정한다 — 런타임에
# 현재 구현을 다시 호출해 만들면 리팩토링 회귀를 잡지 못한다.
Case = tuple[str, Callable[[], object], object]

# maintenance/translation_keys/.../adv_info_tech_tree 실데이터 행 (따옴표로 감싼 셀)
REAL_ROW_INNER = (
    "$NEW_LINE$$NEW_LINE$§H$adv_info_tech_tree_title$§!$NEW_LINE$£line_branch_end_right£ "
    "['technology:tech_fe_affluence_2', £engineering£§R$tech_fe_affluence_2$§!] §EI§!$NEW_LINE$"
)
REAL_ROW_RAW = '"' + REAL_ROW_INNER + '"'

# find_matching_terms / _fallback_glossary 용 인라인 용어집
_TERM_GLOSSARY = {"hyperlane": "초공간 항로", "pop": "팝", "empire": "제국", "pluto": "명왕성", "mars": "화성"}
_FALLBACK_GLOSSARY = {"energy": "에너지", "hyperlane": "초공간 항로"}


def _cell_fields(raw: str) -> tuple[str, str, bool, bool]:
    """CsvCell.parse 결과 4필드를 튜플로 반환 (한 케이스로 전체 필드 검증)."""
    cell = CsvCell.parse(raw)
    return (cell.raw, cell.inner, cell.quoted, cell.quote_noise)


def _protect_roundtrip(text: str) -> str:
    """protect → restore 라운드트립 결과 (닫힘 없는 £ 교정 포함)."""
    masked, replacements = protect_tokens(text)
    return restore_protected_tokens(masked, replacements)


# ── console_text / has_source / strip_code_fence / fix_section_sign ──────────
_TEXT_CASES: list[Case] = [
    ("console_text: ASCII 그대로", lambda: console_text("abc"), "abc"),
    ("console_text: 한글+토큰 그대로", lambda: console_text("한글 £energy£"), "한글 £energy£"),
    ("has_source: 빈 문자열", lambda: has_source(""), False),
    ("has_source: 단어", lambda: has_source("Colony"), True),
    ("has_source: \\n 리터럴도 원문으로 침", lambda: has_source("\\n"), True),
    ("strip_code_fence: 3줄 펜스 벗김", lambda: strip_code_fence("```\ncode line\n```"), "code line"),
    (
        "strip_code_fence: 언어 태그 줄 제거",
        lambda: strip_code_fence("```python\nx = 1\ny = 2\n```"),
        "x = 1\ny = 2",
    ),
    ("strip_code_fence: 한 줄 펜스는 유지", lambda: strip_code_fence("```안녕```"), "```안녕```"),
    ("strip_code_fence: 평문은 strip만", lambda: strip_code_fence("  일반 텍스트  "), "일반 텍스트"),
    ("strip_code_fence: 닫힘 없으면 유지", lambda: strip_code_fence("```\nhello"), "```\nhello"),
    ("section_sign: 열기+닫기 복원", lambda: fix_section_sign_corruption("∽Y경고∽!"), "§Y경고§!"),
    ("section_sign: ≈ 복원", lambda: fix_section_sign_corruption("≈R강조≈!"), "§R강조§!"),
    ("section_sign: ～/∼ 복원", lambda: fix_section_sign_corruption("～G텍스트∼H"), "§G텍스트§H"),
    ("section_sign: 뒤가 숫자면 미치환", lambda: fix_section_sign_corruption("∽1"), "∽1"),
]

# ── CsvCell.parse / with_translated (raw/inner/quoted/quote_noise 4필드) ─────
_CSV_CELL_CASES: list[Case] = [
    (
        "CsvCell.parse: 따옴표 1쌍",
        lambda: _cell_fields('"Engineer Drone"'),
        ('"Engineer Drone"', "Engineer Drone", True, False),
    ),
    (
        "CsvCell.parse: 비따옴표",
        lambda: _cell_fields("Engineer Drone"),
        ("Engineer Drone", "Engineer Drone", False, False),
    ),
    (
        "CsvCell.parse: 3중 따옴표는 noise",
        lambda: _cell_fields('"""Engineer Drone"""'),
        ('"""Engineer Drone"""', "Engineer Drone", True, True),
    ),
    (
        "CsvCell.parse: 앞만 따옴표면 비quoted+noise",
        lambda: _cell_fields('"unbalanced'),
        ('"unbalanced', '"unbalanced', False, True),
    ),
    (
        "CsvCell.parse: 실데이터 quoted 행",
        lambda: _cell_fields(REAL_ROW_RAW),
        (REAL_ROW_RAW, REAL_ROW_INNER, True, False),
    ),
    (
        "CsvCell.with_translated: quoted면 재감쌈",
        lambda: CsvCell.parse('"Engineer Drone"').with_translated("엔지니어 드론"),
        '"엔지니어 드론"',
    ),
    (
        "CsvCell.with_translated: 비quoted면 그대로",
        lambda: CsvCell.parse("Engineer Drone").with_translated("엔지니어 드론"),
        "엔지니어 드론",
    ),
]

# ── has_quote_noise / strip_wrapping_quotes / clean_quote_noise ──────────────
_QUOTE_CASES: list[Case] = [
    ("has_quote_noise: 1쌍 균형", lambda: has_quote_noise('"x"'), False),
    ("has_quote_noise: 따옴표 없음", lambda: has_quote_noise("x"), False),
    ("has_quote_noise: 앞3/뒤1", lambda: has_quote_noise('"""x"'), True),
    ("has_quote_noise: 앞1/뒤0", lambda: has_quote_noise('"x'), True),
    # 따옴표 1글자는 앞1/뒤1로 세어져 노이즈로 안 잡힘 (현재 동작 고정)
    ("has_quote_noise: 따옴표 한 글자", lambda: has_quote_noise('"'), False),
    ("strip_wrapping_quotes: 1쌍", lambda: strip_wrapping_quotes('"값"'), "값"),
    ("strip_wrapping_quotes: 3쌍 반복 제거", lambda: strip_wrapping_quotes('"""값"""'), "값"),
    ("strip_wrapping_quotes: 감싸지 않으면 유지", lambda: strip_wrapping_quotes('""x'), '""x'),
    ("strip_wrapping_quotes: 내부 공백 strip", lambda: strip_wrapping_quotes('" spaced "'), "spaced"),
    ("clean_quote_noise: 평문 유지", lambda: clean_quote_noise("평문"), "평문"),
    ("clean_quote_noise: 1쌍 균형 유지", lambda: clean_quote_noise('"값"'), '"값"'),
    ("clean_quote_noise: 앞3/뒤1 보정", lambda: clean_quote_noise('"""값"'), "값"),
    # 따옴표가 아예 없으면 strip 없이 원문 그대로 반환 (현재 동작 고정)
    ("clean_quote_noise: 공백 포함 원문 유지", lambda: clean_quote_noise("  공백  "), "  공백  "),
    ("clean_quote_noise: 따옴표만 2개", lambda: clean_quote_noise('""'), ""),
]

# ── strip_prompt_echo (접두어/마커 에코/CSV 행/따옴표 보정 전체 경로) ─────────
_ECHO_CASES: list[Case] = [
    ("strip_prompt_echo: '번역:' 접두어", lambda: strip_prompt_echo("번역: 에너지망"), "에너지망"),
    (
        "strip_prompt_echo: 'korean_value:' 접두어",
        lambda: strip_prompt_echo("korean_value: 에너지망"),
        "에너지망",
    ),
    (
        "strip_prompt_echo: 중첩 접두어 반복 제거",
        lambda: strip_prompt_echo("번역: Korean: 에너지망"),
        "에너지망",
    ),
    (
        "strip_prompt_echo: __마커__ 지시문 에코 제거",
        lambda: strip_prompt_echo("__DOLLAR_energy__ 마커는 번역하지 말 것 key: mod_energy 에너지 생산 +10%"),
        "에너지 생산 +10%",
    ),
    (
        "strip_prompt_echo: CSV 행에서 3열 추출",
        lambda: strip_prompt_echo("job_engineer,Engineer,엔지니어"),
        "엔지니어",
    ),
    (
        "strip_prompt_echo: CSV 행 3열 따옴표 제거",
        lambda: strip_prompt_echo('job_engineer,Engineer,"엔지니어"'),
        "엔지니어",
    ),
    # NOTE: 버그 의심 — 쉼표 2개 이상 포함한 라틴 문자 시작 평문이 CSV 행으로
    # 오인되어 마지막 열만 남는다. 정상 번역문이 잘릴 수 있는 경로.
    (
        "strip_prompt_echo: 쉼표 포함 영문 평문",
        lambda: strip_prompt_echo("Attack, defend, retreat"),
        "retreat",
    ),
    (
        "strip_prompt_echo: 접두어+§오염 복원 연쇄",
        lambda: strip_prompt_echo("번역: ∽Y에너지∽!"),
        "§Y에너지§!",
    ),
    (
        "strip_prompt_echo: 따옴표 노이즈 보정 연쇄",
        lambda: strip_prompt_echo('"""엔지니어 드론"'),
        "엔지니어 드론",
    ),
    ("strip_prompt_echo: 평문은 strip만", lambda: strip_prompt_echo("  에너지  "), "에너지"),
]

# ── normalize_csv_cell (원문 \n 리터럴 유무 분기) ─────────────────────────────
_NORMALIZE_CASES: list[Case] = [
    (
        "normalize: 원문에 \\n 있으면 실제 개행→\\n",
        lambda: normalize_csv_cell("안녕\n하세요", "Line1\\nLine2"),
        "안녕\\n하세요",
    ),
    (
        "normalize: CRLF→\\n",
        lambda: normalize_csv_cell("안녕\r\n하세요", "Line1\\nLine2"),
        "안녕\\n하세요",
    ),
    (
        "normalize: 원문에 \\n 없으면 개행→공백",
        lambda: normalize_csv_cell("안녕\n하세요", "no token"),
        "안녕 하세요",
    ),
    ("normalize: CR→공백 (source 기본값)", lambda: normalize_csv_cell("안녕\r하세요", ""), "안녕 하세요"),
    ("normalize: 개행 없으면 불변", lambda: normalize_csv_cell("그대로", "Line1\\nLine2"), "그대로"),
]

# ── find_matching_terms / _fallback_glossary (인라인 용어집) ──────────────────
_TERM_CASES: list[Case] = [
    (
        "find_terms: 5자 이상 단어 경계 매칭",
        lambda: find_matching_terms("The Hyperlane network of the Empire", _TERM_GLOSSARY),
        {"hyperlane": "초공간 항로", "empire": "제국"},
    ),
    (
        "find_terms: 부분 문자열은 경계 실패",
        lambda: find_matching_terms("hyperlanes are fast", _TERM_GLOSSARY),
        {},
    ),
    (
        "find_terms: 5자 미만(mars/pop) 제외",
        lambda: find_matching_terms("Mars and Pluto pop", _TERM_GLOSSARY),
        {"pluto": "명왕성"},
    ),
    ("find_terms: 빈 용어집", lambda: find_matching_terms("anything", {}), {}),
    (
        "fallback: 한글 있으면 불변",
        lambda: _fallback_glossary("에너지", "energy", _FALLBACK_GLOSSARY),
        "에너지",
    ),
    (
        "fallback: 원문에 토큰 섞이면 불변",
        lambda: _fallback_glossary("energy", "$energy$", _FALLBACK_GLOSSARY),
        "energy",
    ),
    (
        "fallback: exact match 대체",
        lambda: _fallback_glossary("energy", "energy", _FALLBACK_GLOSSARY),
        "에너지",
    ),
    (
        "fallback: exact 아니면 불변",
        lambda: _fallback_glossary("energy cell", "energy cell", _FALLBACK_GLOSSARY),
        "energy cell",
    ),
    ("fallback: 빈 용어집이면 불변", lambda: _fallback_glossary("energy", "energy", {}), "energy"),
    # 대체 키는 translation이 아니라 source다 — 모델 응답("power")과 무관하게
    # source("energy")의 용어집 값으로 대체된다 (의도된 source 기준 동작 고정).
    (
        "fallback: source 기준 대체",
        lambda: _fallback_glossary("power", "energy", _FALLBACK_GLOSSARY),
        "에너지",
    ),
]

# ── protect_tokens / restore_protected_tokens ────────────────────────────────
_PROTECT_CASES: list[Case] = [
    (
        "protect: __ICON_x__/__DOLLAR_x__ 마커",
        lambda: protect_tokens("£energy£ and $money$"),
        (
            "__ICON_energy__ and __DOLLAR_money__",
            {"__ICON_energy__": "£energy£", "__DOLLAR_money__": "$money$"},
        ),
    ),
    (
        "protect: 브래킷은 __B0__ 순번 마커",
        lambda: protect_tokens("[Root.GetName] meets [This.GetName]"),
        (
            "__B0__ meets __B1__",
            {"__B0__": "[Root.GetName]", "__B1__": "[This.GetName]"},
        ),
    ),
    (
        "protect: 색코드·\\n은 치환 안 함",
        lambda: protect_tokens("§YHello§! \\n"),
        ("§YHello§! \\n", {}),
    ),
    (
        "protect: 닫힘 없는 £도 마스킹+정상형 맵",
        lambda: protect_tokens("1000£energy and"),
        ("1000__ICON_energy__ and", {"__ICON_energy__": "£energy£"}),
    ),
    (
        "protect: $VALUE|*1$ 포맷 토큰",
        lambda: protect_tokens("$VALUE|*1$ months"),
        ("__DOLLAR_VALUE|*1__ months", {"__DOLLAR_VALUE|*1__": "$VALUE|*1$"}),
    ),
    (
        "roundtrip: 닫힘 없는 £ 2개 교정",
        lambda: _protect_roundtrip("1000£energy and 1000£minerals ."),
        "1000£energy£ and 1000£minerals£ .",
    ),
    (
        "roundtrip: 닫힘 유무 혼재 교정",
        lambda: _protect_roundtrip("£dna £blocker£ Dense Jungle"),
        "£dna£ £blocker£ Dense Jungle",
    ),
    (
        "roundtrip: 정상 토큰은 원형 유지",
        lambda: _protect_roundtrip("£pop£ §YPop§! [Root.GetName]"),
        "£pop£ §YPop§! [Root.GetName]",
    ),
    (
        "roundtrip: 공백 포함 $토큰 유지",
        lambda: _protect_roundtrip("§Y$Fleet Capacity$§!"),
        "§Y$Fleet Capacity$§!",
    ),
    (
        "restore: 번역문 속 마커 복원",
        lambda: restore_protected_tokens(
            "__B0__은(는) __DOLLAR_energy__ 획득",
            {"__B0__": "[Root.GetName]", "__DOLLAR_energy__": "$energy$"},
        ),
        "[Root.GetName]은(는) $energy$ 획득",
    ),
]

# ── extract_tokens / token_delta / tokens_match / hard_tokens_differ ─────────
_TOKEN_CHECK_CASES: list[Case] = [
    (
        "extract: 실데이터 행 유형별 목록",
        lambda: extract_tokens(REAL_ROW_INNER),
        {
            "dollar_ref": [
                "$NEW_LINE$",
                "$NEW_LINE$",
                "$adv_info_tech_tree_title$",
                "$NEW_LINE$",
                "$NEW_LINE$",
            ],
            "icon": ["£line_branch_end_right£"],
            "bracket_expr": [
                "['technology:tech_fe_affluence_2', £engineering£§R$tech_fe_affluence_2$§!]"
            ],
            "color_code": ["§H", "§!", "§E", "§!"],
            "escaped_newline": [],
        },
    ),
    (
        "extract: 단순 혼합",
        lambda: extract_tokens("$energy$ £mineral£ [Root.GetName] §Y\\n"),
        {
            "dollar_ref": ["$energy$"],
            "icon": ["£mineral£"],
            "bracket_expr": ["[Root.GetName]"],
            "color_code": ["§Y"],
            "escaped_newline": ["\\n"],
        },
    ),
    (
        "extract: 닫힘 없는 £는 정상형으로 집계",
        lambda: extract_tokens("1000£energy and"),
        {
            "dollar_ref": [],
            "icon": ["£energy£"],
            "bracket_expr": [],
            "color_code": [],
            "escaped_newline": [],
        },
    ),
    (
        "delta: $토큰 누락",
        lambda: token_delta("Gain $energy$", "획득"),
        {"dollar_ref": {"missing": ["$energy$"], "extra": []}},
    ),
    (
        "delta: £토큰 추가",
        lambda: token_delta("Gain", "£pop£ 획득"),
        {"icon": {"missing": [], "extra": ["£pop£"]}},
    ),
    (
        "delta: \\n 누락",
        lambda: token_delta("A\\nB", "AB"),
        {"escaped_newline": {"missing": ["\\n"], "extra": []}},
    ),
    ("match: $토큰 동일하면 True", lambda: tokens_match("Gain $energy$", "$energy$ 획득"), True),
    ("match: \\n 차이도 기본은 False", lambda: tokens_match("A\\nB", "AB"), False),
    (
        "match: 하드 타입만 지정하면 색코드 무시",
        lambda: tokens_match("§YHi§!", "Hi", HARD_TOKEN_TYPES),
        True,
    ),
    ("hard_differ: 색코드는 소프트", lambda: hard_tokens_differ("§YHi§!", "Hi"), False),
    ("hard_differ: $토큰 개명", lambda: hard_tokens_differ("$a$ x", "$b$ x"), True),
    ("hard_differ: £토큰 누락", lambda: hard_tokens_differ("£x£ hi", "hi"), True),
    (
        "hard_differ: 닫힘 없는 £ vs 정상형은 동일 취급",
        lambda: hard_tokens_differ("1000£energy and", "1000£energy£ 그리고"),
        False,
    ),
]

# ── is_token_only ────────────────────────────────────────────────────────────
_TOKEN_ONLY_CASES: list[Case] = [
    ("token_only: 빈 문자열은 False", lambda: is_token_only(""), False),
    ("token_only: 색코드+$토큰", lambda: is_token_only("§Y$energy$§!"), True),
    ("token_only: 브래킷 단독", lambda: is_token_only("[Root.GetName]"), True),
    ("token_only: $토큰+단어는 False", lambda: is_token_only("$PLANET$ Colony"), False),
    ("token_only: 닫힌 £토큰", lambda: is_token_only("£energy£"), True),
    # TOKEN_RE는 줄 끝의 닫힘 없는 £아이콘을 못 잡아 False (protect_tokens의
    # 파서는 잡음 — 보수적 방향의 비대칭. 추출 시 동작 유지 확인용으로 고정).
    ("token_only: 줄 끝 닫힘 없는 £", lambda: is_token_only("£energy"), False),
    ("token_only: 로마숫자", lambda: is_token_only("IV"), True),
    ("token_only: 일반 단어+로마숫자", lambda: is_token_only("Mk. II"), False),
    ("token_only: 더미값 debug", lambda: is_token_only("debug"), True),
    ("token_only: 더미값 대문자 TODO", lambda: is_token_only("TODO"), True),
]

# ── strip_extra_color_codes / auto_patch_tokens ──────────────────────────────
_POSTPROCESS_CASES: list[Case] = [
    (
        "strip_color: 원문 무색 — 쌍 제거+텍스트 보존",
        lambda: strip_extra_color_codes("§Y안녕§!", "plain"),
        "안녕",
    ),
    (
        "strip_color: 원문 무색 — 고아 열기 제거",
        lambda: strip_extra_color_codes("§Y안녕", "plain"),
        "안녕",
    ),
    (
        "strip_color: 원문 무색 — 고아 닫기 제거",
        lambda: strip_extra_color_codes("안녕§! 세계", "plain"),
        "안녕 세계",
    ),
    (
        "strip_color: 원문 코드 유지+추가분 태그만 제거",
        lambda: strip_extra_color_codes("§RKeep§! §YExtra§!", "§RKeep§! text"),
        "§RKeep§! Extra",
    ),
    (
        "strip_color: 다중 쌍 비탐욕 매칭",
        lambda: strip_extra_color_codes("§YA§! B §YC§!", "plain"),
        "A B C",
    ),
    (
        "auto_patch P1: \\n→$TABBED_NEW_LINE$ 복원",
        lambda: auto_patch_tokens("획득:\\n+5 에너지", "Gain:$TABBED_NEW_LINE$+5 energy"),
        "획득:$TABBED_NEW_LINE$+5 에너지",
    ),
    (
        "auto_patch P1: 원문 \\n 혼재 시 앞쪽만 교체",
        lambda: auto_patch_tokens("가\\n나\\n다", "A$TABBED_NEW_LINE$B\\nC"),
        "가$TABBED_NEW_LINE$나\\n다",
    ),
    (
        "auto_patch P1: 개수 불일치면 미복원",
        lambda: auto_patch_tokens("가\\n나\\n다", "A$TABBED_NEW_LINE$B"),
        "가\\n나\\n다",
    ),
    (
        "auto_patch P4: 원문에 없는 £만 내부 텍스트화",
        lambda: auto_patch_tokens("£energy£ 획득 £minerals£", "£energy£ gain"),
        "£energy£ 획득 minerals",
    ),
    ("auto_patch: delta 없으면 불변", lambda: auto_patch_tokens("$a$ 동일", "$a$ same"), "$a$ 동일"),
]

# ── is_suspicious_translation (분기별 True/False) ─────────────────────────────
_SUSPICIOUS_CASES: list[Case] = [
    ("suspicious: 원문 비면 False", lambda: is_suspicious_translation("", "아무거나"), False),
    (
        "suspicious: 토큰 전용 원문은 영==한이어도 False",
        lambda: is_suspicious_translation("[Root.GetName]", "[Root.GetName]"),
        False,
    ),
    ("suspicious: 로마숫자 원문 False", lambda: is_suspicious_translation("IV", "IV"), False),
    ("suspicious: 한국어 비면 True", lambda: is_suspicious_translation("Colony", ""), True),
    ("suspicious: 영==한 단어 1개 False", lambda: is_suspicious_translation("Colony", "Colony"), False),
    (
        "suspicious: 영==한 다단어 True",
        lambda: is_suspicious_translation("Colony Ship", "Colony Ship"),
        True,
    ),
    (
        "suspicious: 하드 토큰 누락 True",
        lambda: is_suspicious_translation("Gain $energy$ now", "지금 획득"),
        True,
    ),
    (
        "suspicious: 토큰 보존+한글 정상 False",
        lambda: is_suspicious_translation("Gain $energy$ now", "지금 $energy$ 획득"),
        False,
    ),
    (
        "suspicious: 한글 없음+다단어 True",
        lambda: is_suspicious_translation("Colony Ship", "Colony Vessel"),
        True,
    ),
    (
        "suspicious: 한글 없음+단어 1개는 False",
        lambda: is_suspicious_translation("Hyperion", "HYPERION"),
        False,
    ),
    (
        "suspicious: 15% 길이 미달 True",
        lambda: is_suspicious_translation(
            "This colony produces a large amount of energy every month", "네"
        ),
        True,
    ),
    (
        "suspicious: 길이 임계 경계 False",
        lambda: is_suspicious_translation("Short text", "짧은 글"),
        False,
    ),
]

_STATIC_CASES: list[Case] = (
    _TEXT_CASES
    + _CSV_CELL_CASES
    + _QUOTE_CASES
    + _ECHO_CASES
    + _NORMALIZE_CASES
    + _TERM_CASES
    + _PROTECT_CASES
    + _TOKEN_CHECK_CASES
    + _TOKEN_ONLY_CASES
    + _POSTPROCESS_CASES
    + _SUSPICIOUS_CASES
)


def _glossary_file_cases(tmp: Path) -> list[Case]:
    """load_glossary 케이스 — 임시 디렉터리에 용어집 CSV를 만들어 검증한다.

    english/korean 헤더와 english_term/korean_term 헤더, `#` 주석 행 스킵,
    빈 한국어 행 스킵, extra 파일의 우선(덮어쓰기)까지 고정한다.
    """
    base = tmp / "base.csv"
    extra = tmp / "extra.csv"
    base.write_text(
        "english,korean\nHyperlane,초공간 항로\nEnergy,에너지\n#comment,주석\nVoid,\n",
        encoding="utf-8",
    )
    extra.write_text(
        "english_term,korean_term\nEnergy,에너지 크레딧\nEmpire,제국\n",
        encoding="utf-8",
    )
    return [
        (
            "load_glossary: 기본 파일(#주석·빈 값 스킵)",
            lambda: load_glossary(base),
            {"hyperlane": "초공간 항로", "energy": "에너지"},
        ),
        (
            "load_glossary: extra가 기본을 덮어씀",
            lambda: load_glossary(base, [extra]),
            {"hyperlane": "초공간 항로", "energy": "에너지 크레딧", "empire": "제국"},
        ),
        ("load_glossary: None이면 빈 dict", lambda: load_glossary(None), {}),
        ("load_glossary: 없는 파일이면 빈 dict", lambda: load_glossary(tmp / "missing.csv"), {}),
    ]


def _run_cases(cases: list[Case]) -> list[tuple[str, object, object]]:
    """전 케이스 실행 후 실패 목록 반환.

    print를 쓰는 함수(clean_quote_noise, strip_prompt_echo, _fallback_glossary)의
    출력은 StringIO로 흡수하고 반환값만 비교한다. 예외도 실패로 리포트해
    러너가 끝까지 돌게 한다.
    """
    failures: list[tuple[str, object, object]] = []
    sink = io.StringIO()
    for label, thunk, expected in cases:
        try:
            with contextlib.redirect_stdout(sink):
                got: object = thunk()
        except Exception as exc:  # 러너는 격리 지점 — 어떤 예외든 실패로 수집
            failures.append((label, expected, f"exception: {exc!r}"))
            continue
        if got != expected:
            failures.append((label, expected, got))
    return failures


def main() -> int:
    cases: list[Case] = list(_STATIC_CASES)
    with tempfile.TemporaryDirectory() as tmp_name:
        cases += _glossary_file_cases(Path(tmp_name))
        failures = _run_cases(cases)

    for label, expected, got in failures:
        print(f"FAIL {label}")
        print(f"  - expected {expected!r}, got {got!r}")
    print(f"cases={len(cases)} passed={len(cases) - len(failures)} failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
