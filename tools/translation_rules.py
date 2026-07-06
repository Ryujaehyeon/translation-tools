"""Stellaris 로컬라이징의 순수 텍스트·토큰 규칙 계층.

번역 파이프라인에서 LLM 클라이언트·오케스트레이션과 분리해 재사용하는 문자열/토큰
처리 함수와 정규식 상수를 모았다. 용어집 CSV 로드를 빼면 외부 상태에 의존하지 않는다.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from token_parser import extract_token_values, parse_tokens

# Stellaris 로컬라이징에서 사용되는 토큰 패턴
# - dollar_ref: $energy$, $TRIGGER_HOME_PLANET$ 등 다른 키 참조
# - icon: £energy£, £minerals£ 등 아이콘
# - bracket_expr: [Root.GetName], ['concept_x'] 등 스크립트 참조
# - color_code: §Y, §R, §! 등 색상/서식 코드
# - escaped_newline: \n 리터럴 줄바꿈
TOKEN_PATTERNS = {
    # 공백 포함 달러 토큰 허용 ($Fleet Capacity$ 등): \n\t만 불허
    "dollar_ref": re.compile(r"\$[^$\n\t]+\$"),
    # 정상: £word£ / 오타: £word  (닫는 £ 없이 공백 앞에서 끊김) 둘 다 매칭.
    # 공백 뒤가 §(색상)이든 $(변수)이든 일반 텍스트든 모두 토큰 경계로 본다.
    "icon": re.compile(r"£[^£\s]+(?:£|(?=\s))"),
    "bracket_expr": re.compile(r"\[[^\]\n]+\]"),
    "color_code": re.compile(r"§[A-Za-z0-9!#]"),
    "escaped_newline": re.compile(r"\\n"),
}
# 하드 토큰: 개수·순서가 반드시 일치해야 하는 토큰 (게임 동작에 직결)
HARD_TOKEN_TYPES = ("dollar_ref", "icon", "bracket_expr")
ALL_TOKEN_TYPES = tuple(TOKEN_PATTERNS)
HANGUL_RE = re.compile(r"[가-힣]")
# AI에 보내기 전에 토큰을 임시 마커로 치환할 때 쓰는 패턴
# 정상 아이콘(£word£)과 오타 아이콘(£word 공백+§) 둘 다 포함
# 공백 포함 달러 토큰($Fleet Capacity$)도 매칭하도록 \n\t만 불허
TOKEN_RE = re.compile(
    r"\$[^$\n\t]+\$|£[^£\s]+(?:£|(?=\s+§))|\[[^\]\n]+\]|§[A-Za-z0-9!#]|\\n|\\t|\\\"|\\\\"
)
PROTECT_TOKEN_RE = TOKEN_RE  # 하위 호환 별칭
_STRIP_TOKENS_RE = TOKEN_RE  # 하위 호환 별칭
# 토큰 제거 후 남은 텍스트에서 번역 가능한 자연어 단어를 찾는 패턴
# 2자 이상 연속 알파벳 — 로마숫자(I, II, V, X), 단일 문자는 제외
_TRANSLATABLE_WORD_RE = re.compile(r"[A-Za-z]{2,}")
# 로마숫자만으로 구성된 단어는 번역 대상 아님
_ROMAN_NUMERAL_RE = re.compile(r"^[IVXivx]+$")
# 모델이 "번역:" 같은 접두어를 붙여 반환할 때 제거하기 위한 패턴
# 모델이 "번역: ...", "Korean: ..." 처럼 접두어를 붙일 때 한 번에 제거하는 정규식
PROMPT_LABEL_RE = re.compile(
    r"^(?:korean_value|Korean|Translation|원문|번역|번역문|해석)\s*[:：]\s*",
    re.IGNORECASE,
)


def console_text(value: object) -> str:
    # Windows 터미널에서 한글이 깨지지 않도록 인코딩 안전하게 처리
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(value).encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")


def has_source(value: str) -> bool:
    # english_value inner가 실질적으로 비어 있는지 판단
    return bool((value or "").strip())


def strip_code_fence(text: str) -> str:
    # 모델이 ```로 감싼 코드 블록을 반환할 때 블록 마커 제거
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


@dataclass
class CsvCell:
    """CSV 한 셀의 raw 상태를 보존하는 타입.

    raw  : 파일에서 읽은 그대로 (따옴표 포함). 저장 시 이 값을 사용.
    inner: 따옴표를 벗긴 실제 내용. 번역·검증·토큰 검사에 사용.
    quoted: raw가 따옴표로 감싸여 있었는지 여부.
    quote_noise: raw에 불필요한 다중 따옴표가 누적되었는지 여부.
    """

    raw: str
    inner: str
    quoted: bool
    quote_noise: bool = False

    @staticmethod
    def parse(raw: str) -> "CsvCell":
        # 파일에서 읽은 raw 문자열로 CsvCell을 만든다.
        # csv.reader는 `"""값"""` → `"값"` 으로 파싱하므로
        # 여기서 raw는 이미 csv.reader를 거친 문자열이다.
        # 따옴표 1개씩으로 감싸여 있으면 quoted=True.
        s = raw.strip()
        quote_noise = has_quote_noise(s)
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return CsvCell(
                raw=raw, inner=strip_wrapping_quotes(s), quoted=True, quote_noise=quote_noise
            )
        return CsvCell(raw=raw, inner=s, quoted=False, quote_noise=quote_noise)

    def with_translated(self, translated_inner: str) -> str:
        """번역된 inner를 받아 raw 형식으로 재조립한다.
        quoted였으면 따옴표를 붙여 반환, 아니면 그대로.
        """
        if self.quoted:
            return f'"{translated_inner}"'
        return translated_inner


# AI가 CSV 형식으로 응답할 때 감지하는 패턴
# 예: "job_u_engineer_drone,Engineer Drone,엔지니어 드론"
# key 부분은 영숫자·_·- 로만 구성, 쉼표로 구분된 3열 구조
# §(U+00A7) 대신 쓰이는 유사 유니코드 문자 패턴
_SECTION_SIGN_LOOKALIKE_RE = re.compile(r"[∽≈～∼](?=[A-Za-z!_])")


def fix_section_sign_corruption(text: str) -> str:
    """AI가 §(U+00A7)를 ∽(U+223D) 등 유사 문자로 대체한 경우 복원."""
    return _SECTION_SIGN_LOOKALIKE_RE.sub("§", text)


_CSV_ROW_RE = re.compile(r"^[A-Za-z0-9_.\-]+\s*,\s*.+?\s*,\s*(.+)$", re.DOTALL)


def strip_prompt_echo(value: str) -> str:
    # 모델이 "번역: ...", "Korean: ..." 처럼 접두어를 붙여 반환할 때 제거
    # PROMPT_LABEL_RE 한 번으로 처리 (루프 불필요)
    text = value.strip()
    prev = None
    while prev != text:
        prev = text
        text = PROMPT_LABEL_RE.sub("", text).lstrip()

    # AI가 프롬프트 지시문을 번역문 앞에 그대로 포함해 반환한 경우 제거
    # 패턴: "__식별자__ 형태의 마커는 ... key: <키명>   실제 번역문"
    # "key: <키명>" 다음 공백 이후를 실제 번역으로 간주
    if text.startswith("__") and "key:" in text:
        m = re.search(r"\bkey\s*:\s*\S+\s+", text)
        if m:
            extracted = text[m.end() :].strip()
            if extracted:
                print("  [경고] 프롬프트 에코 감지, 지시문 제거 후 번역 추출", flush=True)
                text = extracted

    # AI가 CSV 행 전체를 반환한 경우 → 세 번째 열(korean_value)만 추출
    # 예: "job_key,English text,한국어 번역" → "한국어 번역"
    m = _CSV_ROW_RE.match(text)
    if m:
        extracted = m.group(1).strip().strip('"')
        if extracted:
            print(f"  [경고] CSV 형식 응답 감지, korean_value만 추출: {console_text(extracted)}")
            text = extracted

    # §(U+00A7) 색상코드 오염 교정
    # AI가 §를 유사 유니코드 문자(∽ U+223D 등)로 대체하는 경우 복원
    text = fix_section_sign_corruption(text)

    # 따옴표 불균형 감지 및 보정
    # CSV 셀은 따옴표로 감싸거나(짝수) 감싸지 않아야 함
    # 예: `"""엔지니어 드론"` → 앞 3개, 뒤 1개 → 불균형
    text = clean_quote_noise(text)

    return text


def has_quote_noise(text: str) -> bool:
    stripped = text.strip()
    leading = len(stripped) - len(stripped.lstrip('"'))
    trailing = len(stripped) - len(stripped.rstrip('"'))
    return leading >= 2 or trailing >= 2 or leading != trailing


def strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip()
    while len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        stripped = stripped[1:-1].strip()
    return stripped


def clean_quote_noise(text: str) -> str:
    """앞뒤 따옴표가 과하거나 불균형하면 내용만 남긴다."""
    stripped = text.strip()
    leading = len(stripped) - len(stripped.lstrip('"'))
    trailing = len(stripped) - len(stripped.rstrip('"'))
    if leading == 0 and trailing == 0:
        return text
    if leading == trailing == 1:
        return text  # 균형 — 정상
    inner = strip_wrapping_quotes(stripped).strip('"').strip()
    print(f"  [경고] 따옴표 노이즈 감지(앞{leading}/뒤{trailing}), 보정: {console_text(inner)}")
    return inner


def normalize_csv_cell(value: str, source: str = "") -> str:
    # 모델이 실제 줄바꿈(\r\n 등)을 반환할 때 처리:
    # - 원문에 \n 리터럴이 있으면 → \\n 리터럴로 변환 (Stellaris 토큰 보존)
    # - 원문에 \n 리터럴이 없으면 → 공백으로 대체 (모델이 임의로 줄바꿈한 것)
    has_newline_token = "\\n" in source
    if has_newline_token:
        return value.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    else:
        return value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _load_glossary_file(path: Path, glossary: dict[str, str]) -> int:
    # CSV 파일 하나를 읽어 glossary 딕셔너리에 병합 (나중 파일이 기존 값을 덮어씀)
    # english/korean 열 또는 english_term/korean_term 열을 모두 지원
    # 반환: 추가된 항목 수
    added = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eng = (row.get("english") or row.get("english_term") or "").strip()
            kor = (row.get("korean") or row.get("korean_term") or "").strip()
            if eng and kor and not eng.startswith("#"):
                glossary[eng.lower()] = kor
                added += 1
    return added


def load_glossary(path: Path | None, extra_paths: list[Path] | None = None) -> dict[str, str]:
    # 기본 용어집과 추가 용어집을 병합해 {영어소문자: 한국어} 딕셔너리 반환
    # extra_paths의 항목이 기본 용어집보다 우선 (나중에 로드되어 덮어씀)
    glossary: dict[str, str] = {}
    if path and path.is_file():
        _load_glossary_file(path, glossary)
    for extra in extra_paths or []:
        if extra.is_file():
            _load_glossary_file(extra, glossary)
    return glossary


# 용어 매칭: 단어 경계 기준으로 glossary 영어 단어를 텍스트에서 찾음
_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def find_matching_terms(text: str, glossary: dict[str, str]) -> dict[str, str]:
    # 번역할 텍스트에서 glossary의 영어 단어를 찾아 {영어: 한국어} 매핑 반환
    # 단어 경계(\b) 기준으로 대소문자 무시 매칭
    # 5자 미만 단어는 제외 (on, home, size 같은 일반 단어 오매칭 방지)
    if not glossary:
        return {}
    matched: dict[str, str] = {}
    text_lower = text.lower()
    for eng_lower, kor in glossary.items():
        if len(eng_lower) < 5:
            continue
        if eng_lower not in text_lower:
            continue
        if eng_lower not in _WORD_RE_CACHE:
            try:
                _WORD_RE_CACHE[eng_lower] = re.compile(
                    r"\b" + re.escape(eng_lower) + r"\b", re.IGNORECASE
                )
            except re.error:
                continue
        if _WORD_RE_CACHE[eng_lower].search(text):
            matched[eng_lower] = kor
    return matched


def protect_tokens(value: str) -> tuple[str, dict[str, str]]:
    # 특수 구분자를 마커로 치환해 AI가 토큰을 누락·변형하지 못하게 보호한다.
    # 토큰 식별은 token_parser의 범위 인식 파서를 쓴다. 정규식 TOKEN_RE는 닫힘 없는
    # 아이콘(`£word`)을 §앞에서만 잡지만, 파서는 단어·구두점·줄끝 앞에서도 잡으므로
    # `1000£energy and`, `£minerals .` 같은 원본 오타 토큰까지 마스킹돼 AI 손상을 막는다.
    # - £pop£ / £pop  → __ICON_pop__   (구분자 타입 prefix로 $토큰과 충돌 방지)
    #   닫힘 없는 £pop은 복원 시 정상형 £pop£로 교정한다(원본 오타 자동 보정).
    # - $energy$      → __DOLLAR_energy__
    # - [Root.GetName]→ __B0__          (길고 복잡한 스크립트 표현식 → 순번 마커)
    # - §Y, §!, \n 등 → 그대로 (시스템 프롬프트 규칙으로 보호)
    # 복원 맵: {마커 → 원래 토큰 전체}
    replacements: dict[str, str] = {}
    bracket_counter = 0
    pieces: list[str] = []
    last = 0

    for span in parse_tokens(value):
        if span.kind in ("icon", "unclosed_icon"):
            # 정상: £word£ → inner=word / 오타: £word → inner=word (닫는 £ 없음)
            inner = span.text[1:-1] if span.text.endswith("£") else span.text[1:]
            marker = f"__ICON_{inner}__"
        elif span.kind == "dollar_ref":
            marker = f"__DOLLAR_{span.text[1:-1]}__"
        elif span.kind == "bracket_expr":
            # 스크립트 표현식은 길고 복잡해서 내용을 그대로 두면 AI가 혼란 → 순번 마커
            marker = f"__B{bracket_counter}__"
            bracket_counter += 1
        else:
            # color_code(§X), escaped_newline(\n) 등 — 치환하지 않고 원문 그대로 둔다
            continue
        # 닫힘 없는 아이콘은 normalized(£x£)로 복원해 원본 오타를 출력에서 교정한다.
        # closed icon / dollar_ref / bracket_expr은 normalized가 None이라 span.text 그대로.
        replacements[marker] = span.normalized or span.text
        pieces.append(value[last : span.start])
        pieces.append(marker)
        last = span.end

    pieces.append(value[last:])
    return "".join(pieces), replacements


def restore_protected_tokens(value: str, replacements: dict[str, str]) -> str:
    # 모델 출력에서 __TN__ 마커를 원래 식별자로 복원
    # 마커가 £...£ / $...$ / [...] 안에 있으면 구조는 이미 유지된 상태
    restored = value
    for marker, original in replacements.items():
        restored = restored.replace(marker, original)
    return restored


def extract_tokens(value: str) -> dict[str, list[str]]:
    """토큰 유형별 목록 반환. 반환 예: {"dollar_ref": ["$energy$"], ...}"""
    parsed = extract_token_values(value)
    return {name: parsed.get(name, []) for name in TOKEN_PATTERNS}


def token_delta(source: str, target: str) -> dict[str, dict[str, list[str]]]:
    """원문 대비 번역문의 누락(missing)/추가(extra) 토큰 계산.

    반환 예: {"dollar_ref": {"missing": ["$energy$"], "extra": []}}
    빈 경우 해당 유형은 결과에서 생략.
    """
    src = extract_tokens(source)
    tgt = extract_tokens(target)
    result: dict[str, dict[str, list[str]]] = {}
    for name in TOKEN_PATTERNS:
        missing = list((Counter(src[name]) - Counter(tgt[name])).elements())
        extra = list((Counter(tgt[name]) - Counter(src[name])).elements())
        if missing or extra:
            result[name] = {"missing": missing, "extra": extra}
    return result


def tokens_match(source: str, target: str, token_types: tuple[str, ...] = ALL_TOKEN_TYPES) -> bool:
    """지정한 유형에서 원문·번역문 토큰이 모두 일치하면 True."""
    delta = token_delta(source, target)
    return not any(k in delta for k in token_types)


def hard_tokens_differ(source: str, target: str) -> bool:
    """하드 토큰($, £, [...]) 중 하나라도 다르면 True."""
    delta = token_delta(source, target)
    return any(k in delta for k in HARD_TOKEN_TYPES)


# 번역 불필요한 더미/예약어 — OpenAI에 보내면 빈 응답을 내는 케이스
_DUMMY_VALUES = frozenset({"debug", "todo", "wip", "tbd", "placeholder", "test", "fixme"})


def is_token_only(inner: str) -> bool:
    # 번역할 자연어가 없는 행인지 판단.
    # 모든 Stellaris 토큰을 제거한 뒤 남은 텍스트에
    # 2자 이상 알파벳 단어(로마숫자 제외)가 없으면 True.
    # 개발용 더미값(debug 등)도 번역 불필요로 간주.
    # True면 API 없이 원문을 그대로 복사해도 안전.
    text = inner.strip()
    if not text:
        return False
    if text.lower() in _DUMMY_VALUES:
        return True
    residual = _STRIP_TOKENS_RE.sub(" ", text)
    words = _TRANSLATABLE_WORD_RE.findall(residual)
    return not any(not _ROMAN_NUMERAL_RE.match(w) for w in words)


def _strip_all_tokens(text: str) -> str:
    """Stellaris 토큰을 모두 제거한 순수 텍스트 반환."""
    return _STRIP_TOKENS_RE.sub(" ", text).strip()


def strip_extra_color_codes(translation: str, source: str) -> str:
    """원문에 없는 color_code(§X)를 번역문에서 제거한다.

    모델이 강조를 위해 §Y...§! 같은 색상 태그를 임의로 추가하는 경우 방지.
    원문에 있는 color_code는 그대로 유지.

    §X...§! 쌍을 함께 제거해 고아 §!가 남지 않도록 한다.
    """
    src_codes = set(TOKEN_PATTERNS["color_code"].findall(source))
    if not src_codes:
        # 원문에 color_code가 전혀 없으면 §X와 §! 코드만 제거, 내부 텍스트 보존
        result = re.sub(r"§[A-Za-z0-9#](.*?)§!", r"\1", translation, flags=re.DOTALL)
        return TOKEN_PATTERNS["color_code"].sub("", result)

    # 원문에 없는 §X...§! 쌍: §X와 §!만 제거하고 내부 텍스트 보존
    def _strip_pair_tags(m: re.Match[str]) -> str:
        opener = "§" + m.group(1)
        inner = m.group(2)
        if opener in src_codes:
            return m.group(0)  # 원문에 있는 코드는 유지
        return inner  # 없는 코드는 태그만 제거, 텍스트 보존

    result = re.sub(r"§([A-Za-z0-9#])(.*?)§!", _strip_pair_tags, translation, flags=re.DOTALL)

    # 쌍 제거 후 남은 단독 §X(원문에 없는 것) 제거
    def _remove_if_absent(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0) in src_codes else ""

    return TOKEN_PATTERNS["color_code"].sub(_remove_if_absent, result)


# $TABBED_NEW_LINE$ ↔ \n 불일치: extra \n 수만큼 missing $TABBED_NEW_LINE$과 1:1 교체
_TABBED_NL = "$TABBED_NEW_LINE$"


def auto_patch_tokens(translation: str, source: str) -> str:
    """번역 후 규칙 기반으로 수정 가능한 토큰 불일치를 자동 보정한다.

    P1 — $TABBED_NEW_LINE$ 복원:
        AI가 $TABBED_NEW_LINE$을 \\n으로 치환한 경우.
        extra \\n 수 == missing $TABBED_NEW_LINE$ 수일 때만 적용.
        EN에서 $TABBED_NEW_LINE$ 앞에 오는 컨텍스트를 기준으로 위치를 매칭.

    P4 — extra 아이콘 제거:
        EN에 없는 £word£ 토큰을 word 텍스트로 대체.
        토큰 형태만 제거하고 내부 텍스트는 보존.
    """
    delta = token_delta(source, translation)
    if not delta:
        return translation

    result = translation

    # P1: $TABBED_NEW_LINE$ 복원
    # AI가 $TABBED_NEW_LINE$을 \n으로 치환한 경우.
    # extra \n 수 == missing $TABBED_NEW_LINE$ 수일 때, KO의 extra \n을 순서대로 교체.
    # "extra \n" = KO에만 있고 EN에는 없는 \n들. EN에도 있는 \n은 건드리지 않음.
    dr = delta.get("dollar_ref", {})
    dn = delta.get("escaped_newline", {})
    missing_tabbed = [t for t in dr.get("missing", []) if t == _TABBED_NL]
    extra_nl = dn.get("extra", [])
    if missing_tabbed and len(missing_tabbed) == len(extra_nl):
        # KO에서 \n 토큰을 순서대로 스캔하면서, EN에 없는 것(extra)을 $TABBED_NEW_LINE$으로 교체
        # extra \n이 앞에서부터 몇 번째에 오는지 알 수 없으므로,
        # KO의 전체 \n 목록에서 EN 개수를 넘는 부분(오른쪽부터)을 교체
        # 단순화: KO \n 총 개수 - EN \n 개수 = extra 개수. 뒤에서부터 extra개를 교체.
        ko_nl_positions = [m.start() for m in re.finditer(r"\\n", result)]
        n_extra = len(missing_tabbed)
        # EN에서 $TABBED_NEW_LINE$이 \n보다 앞에 오는 경우(일반적):
        #   KO의 \n 중 앞에서 n_extra개가 $TABBED_NEW_LINE$으로 교체되어야 할 것들.
        #   뒤의 en_nl_count개는 원래 \n으로 보존.
        positions_to_replace = ko_nl_positions[:n_extra]
        if len(positions_to_replace) == n_extra:
            # 뒤에서부터 교체 (인덱스 불변)
            for pos in reversed(positions_to_replace):
                result = result[:pos] + _TABBED_NL + result[pos + 2 :]  # \n = 2글자

    # P4: extra 아이콘(£word£) 제거 — EN에 없는 것만
    extra_icons = delta.get("icon", {}).get("extra", [])
    if extra_icons:
        src_icons = set(TOKEN_PATTERNS["icon"].findall(source))

        def _strip_extra_icon(m: re.Match[str]) -> str:
            tok = m.group(0)
            if tok in src_icons:
                return tok
            # £word£ → word (닫힘 없는 £word 형태 포함)
            inner = tok[1:-1] if tok.endswith("£") else tok[1:]
            return inner

        result = TOKEN_PATTERNS["icon"].sub(_strip_extra_icon, result)

    return result


def _fallback_glossary(translation: str, source: str, glossary: dict[str, str]) -> str:
    """API가 한글 없이 영문을 그대로 반환한 경우, 단어집에서 정확히 일치하는 한국어로 대체한다.

    - 한글이 이미 있으면 건드리지 않는다.
    - 단어집에 source(소문자)가 exact match로 있을 때만 대체한다.
    - 토큰이 섞인 복합 텍스트는 대체하지 않는다 (부분 치환 오류 방지).
    """
    if not glossary:
        return translation
    if HANGUL_RE.search(translation):
        return translation
    if TOKEN_RE.search(source):
        return translation  # 토큰 혼합 원문은 부분 치환 오류 방지를 위해 건드리지 않음
    source_stripped = source.strip()
    if not source_stripped:
        return translation
    kor = glossary.get(source_stripped.lower())
    if kor and not HANGUL_RE.search(translation):
        print(f"  [단어집 대체(후처리)] {source_stripped!r} → {kor!r}")
        return kor
    return translation


def is_suspicious_translation(eng_inner: str, kor_inner: str) -> bool:
    english = eng_inner.strip()
    korean = kor_inner.strip()
    if not has_source(english):
        return False
    # 토큰 전용 행은 영문=한국어여도 정상
    if is_token_only(english):
        return False
    if not korean:
        return True
    if english == korean:
        # 단어 1개(고유명사, 약어 등)는 번역 불필요
        if len(english.split()) <= 1:
            return False
        return True
    if hard_tokens_differ(english, korean):
        return True
    # 한글 없음 — 단 단어 1개짜리 고유명사는 제외
    if not HANGUL_RE.search(korean):
        eng_text = _strip_all_tokens(english)
        if len(eng_text.split()) > 1:
            return True
    # 토큰 제거 후 순수 텍스트 길이로 비교 (15% 미만이면 의심)
    eng_text = _strip_all_tokens(english)
    kor_text = _strip_all_tokens(korean)
    if eng_text and len(kor_text) < max(4, int(len(eng_text) * 0.15)):
        return True
    return False
