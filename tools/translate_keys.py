#!/usr/bin/env python3
"""Translate Stellaris auto_keys CSV files with Claude or OpenAI.

Default behavior is conservative:

- fill only blank `korean_value` cells;
- skip rows whose `english_value` is empty;
- copy pure token/reference rows without an API call;
- reject model output when hard Stellaris tokens differ from the source;
- write JSON reports for every run.

Use `--rewrite-existing` to intentionally overwrite existing `korean_value`
cells. Use `--sample-rows` to create a translated sample CSV without modifying
the source CSV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from tool_config import translation_keys_root


SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
AUTO_KEYS_DIR = translation_keys_root()
REPORT_DIR = PACK_ROOT / "maintenance" / "reports" / "ai_translation"
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "translate_keys"
LOCK_FILE_PATH = PACK_ROOT / "maintenance" / "ai_current_task.txt"
DEFAULT_API_KEY_FILE = SCRIPT_DIR / "api_key.txt"
_LEGACY_API_KEY_FILE = SCRIPT_DIR / "openai_api_key.txt"  # 하위호환 폴백
DEFAULT_GUIDELINES_FILE = PACK_ROOT / "maintenance" / "translation_guidelines.md"
DEFAULT_GLOSSARY_FILE = PACK_ROOT / "maintenance" / "term_glossary.csv"

# 기본 모델: gpt-4o-mini (가장 저렴한 모델로 설정)
# 2026-05 기준 가격 (input / output, USD per 1M tokens)
#
# ── 저렴한 순 ──────────────────────────────────────────────────
# gpt-4o-mini               $0.15 / $0.60   ← 기본값, 최저가
# gpt-4.1-mini              $0.40 / $1.60
# claude-haiku-4-5-20251001  $1.00 / $5.00
#
# ── 성능 좋은 순 ───────────────────────────────────────────────
# claude-opus-4-8            $5.00 / $25.00  (Anthropic 최상위)
# claude-sonnet-4-6          $3.00 / $15.00  (성능·비용 균형 최적)
# gpt-4.1-mini              $0.40 / $1.60   (OpenAI 중상급)
DEFAULT_MODEL = "gpt-4o-mini"
# 온도: 0.0=완전 결정론, 1.0=창의적. 번역은 0.1~0.3이 적합 (일관성 우선)
DEFAULT_TEMPERATURE = 0.2
# API 실패 시 최대 재시도 횟수 (지수 대기 적용)
DEFAULT_MAX_RETRIES = 4

# Stellaris 로컬라이징에서 사용되는 토큰 패턴
# - dollar_ref: $energy$, $TRIGGER_HOME_PLANET$ 등 다른 키 참조
# - icon: £energy£, £minerals£ 등 아이콘
# - bracket_expr: [Root.GetName], ['concept_x'] 등 스크립트 참조
# - color_code: §Y, §R, §! 등 색상/서식 코드
# - escaped_newline: \n 리터럴 줄바꿈
TOKEN_PATTERNS = {
    # 공백 포함 달러 토큰 허용 ($Fleet Capacity$ 등): \n\t만 불허
    "dollar_ref": re.compile(r"\$[^$\n\t]+\$"),
    # 정상: £word£ / 오타: £word  (닫는 £ 없이 공백+§ 앞에서 끊김) 둘 다 매칭
    "icon": re.compile(r"£[^£\s]+(?:£|(?=\s+§))"),
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
PROMPT_LABEL_RE = re.compile(
    r"^(?:korean_value|Korean|Translation|원문|번역|번역문|해석)\s*[:：]?\s*(?:\\n|\r\n|\r|\n)+",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """너는 Stellaris 모드 로컬라이징을 한국어로 번역하는 전문 번역가다.

문체:
- 이벤트·설명문: ~습니다/~입니다 합쇼체. UI 레이블·이름: 명사형.
- 공식 한국어판 표기 우선 (팝, 제국, 항성계, 행성, 초공간 등).
- 게임 토큰($...$, £...£, [...], §X...§!)은 원형 그대로 유지한다.

출력: 번역문만. 설명·마크다운·코드블록 없음.
"""

# 토큰이 포함된 텍스트에 사용하는 확장 프롬프트
# 참조: https://stellaris.paradoxwikis.com/Localisation_modding
_SYSTEM_PROMPT_TOKEN_RULES = """
토큰 규칙:
1. $...$ 변수($PLANET$, $VALUE|*1$ 등): 전체를 그대로 유지.
2. [...] 스크립트 표현식([Root.GetName] 등): 그대로 유지.
3. £...£ 아이콘(£energy£ 등): 그대로 유지.
4. §X...§! 색상코드: 열기(§R, §Y, §G, §H, §L 등)와 닫기(§!) 쌍을 반드시 유지.
   - 원문의 §! 개수와 위치를 정확히 복사한다.
   - §!가 연속으로 나오면(§!!§!) 각각 독립 닫기 코드다. 개수를 줄이지 않는다.
   - 코드 사이의 일반 텍스트만 번역한다.
5. \\n, \\t, \\" 이스케이프: 위치·개수 그대로.
"""

SYSTEM_PROMPT_WITH_TOKENS = SYSTEM_PROMPT.rstrip() + _SYSTEM_PROMPT_TOKEN_RULES

GUIDELINE_START_HEADING = "## 기본 원칙"
GUIDELINE_STOP_HEADINGS = ("## 토큰 참고 파일", "## 검수 기준")


def print_block(header: str, **fields: str) -> None:
    """[헤더] 뒤에 필드들을 헤더 너비에 맞춰 정렬 출력.

    예) print_block("[번역 완료] key", 원문="...", 번역="...")
    →  [번역 완료] key
                   원문: ...
                   번역: ...
    """
    print(header, flush=True)
    for label, value in fields.items():
        print(f"{label}: {value}", flush=True)


# 복구 불가능한 오류 (잘못된 모델명, API 키 없음 등) — 발생 시 즉시 작업 중단
class TranslationFatalError(Exception):
    """Raised when the current run cannot continue safely."""


def console_text(value: object) -> str:
    # Windows 터미널에서 한글이 깨지지 않도록 인코딩 안전하게 처리
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(value).encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")


@dataclass
class TranslationConfig:
    # 모델명. OpenAI: gpt-4o-mini, gpt-4.1-mini 등
    #        Claude: claude-haiku-4-5-20251001, claude-sonnet-4-6 등
    model: str = DEFAULT_MODEL
    # 번역 온도 (0.0~1.0): 낮을수록 결정론적, 번역에는 0.1~0.3 권장
    temperature: float = DEFAULT_TEMPERATURE
    # API 오류 시 최대 재시도 횟수
    max_retries: int = DEFAULT_MAX_RETRIES
    # 하드 토큰 불일치 시 재시도 횟수 (재시도해도 다른 번역이 나올 수 있음)
    retry_token_mismatch: int = 2
    # 요청 간 강제 대기 시간 (초). TPMThrottle 없이 간단히 속도 조절할 때 사용
    request_delay: float = 0.0
    api_key_file: Path = DEFAULT_API_KEY_FILE
    guidelines_file: Path = DEFAULT_GUIDELINES_FILE
    # True면 translation_guidelines.md 일부를 시스템 프롬프트에 포함
    # 토큰 보존·후처리는 코드가 보장하므로 기본 비활성화 (토큰 절약)
    use_guidelines: bool = False
    # True면 Stellaris 토큰을 __STELLARIS_TOKEN_N__ 마커로 치환 후 API 전송
    protect_tokens: bool = True
    # 용어집 파일 경로 (None이면 사용 안 함)
    glossary_file: Path | None = DEFAULT_GLOSSARY_FILE
    # 추가 용어집 파일 목록 (glossary_file에 병합됨, 나중 파일이 우선)
    extra_glossary_files: list[Path] = field(default_factory=list)


@dataclass
class FileResult:
    # 처리한 CSV 파일 경로
    path: str
    # 파일 전체 행 수 (헤더 제외)
    rows: int = 0
    # 번역 대상으로 선별된 행 수
    candidates: int = 0
    # 실제로 번역 완료한 행 수
    translated: int = 0
    # 토큰만으로 구성된 행이라 그대로 복사한 행 수
    copied_token_only: int = 0
    # 단어집 exact match로 API 없이 직접 대체한 행 수
    glossary_applied: int = 0
    # 이미 번역이 있어 건너뛴 행 수 (--rewrite-existing 없을 때)
    skipped_existing: int = 0
    # english_value가 비어 있어 건너뛴 행 수
    skipped_empty_english: int = 0
    # 하드 토큰 불일치로 저장 거부된 행 수
    skipped_token_mismatch: int = 0
    # API 오류 등으로 실패한 행 수
    failed: int = 0
    # 이 파일에 실제로 변경된 내용이 있으면 True
    changed: bool = False
    # 백업 경로 (변경이 있을 때 자동 생성)
    backup_path: str = ""
    # 마지막으로 처리(번역 시도)한 CSV 줄 번호. 재개 시 --start-row에 사용
    last_processed_row: int = 0
    # 토큰 불일치, 실패 등 개별 문제 목록
    issues: list[dict[str, str]] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate auto_keys CSV files with OpenAI GPT-4.1 mini.")
    # 처리 범위 옵션 -------------------------------------------------------
    # translation keys 디렉토리 (기본: maintenance/tooling.ini)
    parser.add_argument("--auto-keys-dir", default=str(AUTO_KEYS_DIR))
    # 특정 모드 폴더만 처리. --mod GW --mod NSC 처럼 반복 가능
    parser.add_argument("--mod", action="append", default=[], help="Limit to a mod folder. Can repeat.")
    # 특정 CSV 파일명/경로만 처리. 파일명 만 넣어도 auto_keys 하위에서 검색
    parser.add_argument("--file", action="append", default=[], help="Limit to a CSV path or filename. Can repeat.")
    # 특정 로컬라이징 키만 처리. --key some_key --key other_key 처럼 반복 가능
    parser.add_argument("--key", action="append", default=[], help="Limit to one localisation key. Can repeat.")
    # 작업량 제한 -----------------------------------------------------------
    # 번역 작업이 생긴 파일 N개만 처리하고 중단 (0 = 무제한)
    parser.add_argument("--limit-files", type=int, default=0, help="Stop after N files with work. 0 means unlimited.")
    # 번역/복사 합산 N행 이후 중단 (0 = 무제한)
    parser.add_argument("--limit-rows", type=int, default=0, help="Stop after N translated/copied rows. 0 means unlimited.")
    # 시작/종료 행 -----------------------------------------------------------
    # 이 행(CSV 줄 번호, 헤더=1)부터 처리. 중간에 중단 후 재개할 때 사용
    parser.add_argument("--start-row", type=int, default=2, help="CSV line number to start at. Header is line 1. Default: 2.")
    # 이 행까지만 처리 (포함). 'end'로 지정하면 파일 끝까지
    parser.add_argument(
        "--end-row",
        default="end",
        help="CSV line number to stop at, inclusive. Use 'end' to continue to the end.",
    )
    # 번역 대상 선택 --------------------------------------------------------
    # 기본은 빈 korean_value만 채운다. 이 옵션을 주면 기존 번역도 덮어쓴다
    parser.add_argument("--rewrite-existing", action="store_true", help="Overwrite existing korean_value cells too.")
    # --rewrite-existing과 함께 사용: 의심스러운(미번역/영문그대로) 행만 재번역
    parser.add_argument(
        "--only-suspicious",
        action="store_true",
        help="With --rewrite-existing, only rewrite rows that look untranslated or token-broken.",
    )
    # dry-run / 샘플 모드 --------------------------------------------------
    # 실제 API 호출·파일 수정 없이 대상 행 수만 출력
    parser.add_argument("--dry-run", action="store_true", help="Count work only; do not write files or call OpenAI.")
    parser.add_argument("--dry-run-with-api", action="store_true", help="Call OpenAI but do not write files. For testing token masking/restoration.")
    # 원본 CSV를 수정하지 않고 N행만 번역해 별도 CSV로 저장 (품질 확인용)
    parser.add_argument("--sample-rows", type=int, default=0, help="Translate N rows into a separate sample CSV only.")
    parser.add_argument("--sample-output", default="", help="Sample CSV output path.")
    # 샘플 모드에서 기존 번역이 있는 행도 포함할지 여부
    parser.add_argument("--sample-include-existing", action="store_true", help="Sample existing korean_value rows too.")
    # 번역 대상이 없는 파일도 로그에 출력할지 여부
    parser.add_argument("--verbose-skips", action="store_true", help="Print files with no translatable rows.")
    # 모델·번역 품질 옵션 --------------------------------------------------
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model. Default: {DEFAULT_MODEL}")
    # 번역 온도 (0.0~1.0). 기본값 0.2 — 일관성 우선
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    # API 오류(네트워크, 서버 등) 시 최대 재시도 횟수
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    # 하드 토큰 불일치 시 재번역 시도 횟수 (시도 횟수 초과 시 해당 행 건너뜀)
    parser.add_argument("--retry-token-mismatch", type=int, default=2)
    # 요청 간 강제 대기(초). TPM throttle가 있으면 대부분 불필요
    parser.add_argument("--request-delay", type=float, default=0.0)
    # 인증·설정 파일 경로 --------------------------------------------------
    parser.add_argument("--api-key-file", default=str(DEFAULT_API_KEY_FILE))
    parser.add_argument("--guidelines-file", default=str(DEFAULT_GUIDELINES_FILE))
    # 번역 지침서를 시스템 프롬프트에 포함할 때 사용 (기본 비활성 — 코드가 토큰 보존을 보장)
    parser.add_argument("--use-guidelines", action="store_true", help="Load maintenance/translation_guidelines.md into the OpenAI prompt. 기본: 토큰 포함 행에만 자동 적용.")
    parser.add_argument("--no-glossary", action="store_true", help="용어집(term_glossary.csv)을 프롬프트에 포함하지 않는다.")
    parser.add_argument("--glossary-file", default=str(DEFAULT_GLOSSARY_FILE), help="용어집 CSV 경로. 기본: maintenance/term_glossary.csv")
    parser.add_argument("--extra-glossary", action="append", default=[], metavar="CSV", help="추가 용어집 CSV 경로. 반복 가능. 기본 용어집보다 우선 적용.")
    # Stellaris 토큰을 마커로 치환하지 않고 그대로 API에 전송 (테스트용)
    parser.add_argument("--no-protect-tokens", action="store_true", help="Send Stellaris tokens to OpenAI without temporary masking.")
    # 토큰만으로 구성된 행을 API 없이 그대로 복사하는 최적화를 끌 때 사용
    parser.add_argument("--no-copy-token-only", action="store_true")
    # 하드 토큰이 달라도 번역 결과를 저장 (검수 후 수동 수정을 전제로 할 때)
    parser.add_argument("--allow-token-mismatch", action="store_true", help="Write output even when hard tokens differ.")
    # 보고서 저장 경로
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    # 검수 리포트 기반 선별 재번역 (review_report.py 가 생성한 CSV)
    # retranslate=1 로 표시된 행만 번역. --rewrite-existing 자동 적용.
    parser.add_argument(
        "--from-report",
        nargs="?",
        const="latest",
        default=None,
        metavar="REPORT_CSV",
        help="review_report.py 가 생성한 검수 리포트 CSV. 기본: maintenance/reports/review/review_latest.csv. retranslate=1 행만 재번역.",
    )
    parser.add_argument(
        "--from-worklist",
        nargs="?",
        const="latest",
        default=None,
        metavar="WORKLIST_CSV",
        help="validate_auto_key_tokens.py 가 생성한 token_repair_worklist CSV. 기본: latest. 전 행을 재번역 대상으로 처리.",
    )
    # 저장 타이밍 -----------------------------------------------------------
    # 기본은 매행 번역 직후 저장 (프로세스 중단 시 손실 최소화)
    # 이 옵션을 주면 파일 전체가 끝난 후 한 번만 저장 (I/O 절약, 손실 위험 있음)
    parser.add_argument(
        "--save-at-end",
        action="store_true",
        help="Save CSV only at the end of each file instead of after every row.",
    )
    # 병렬·속도 제어 -------------------------------------------------------
    # 동시 API 요청 수. 1=순차. TPM 한도 안에서 3~5 권장
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel translation requests. Default: 1. Recommended max: 3~5.",
    )
    # 분당 토큰(TPM) 한도. 이 값에 맞춰 요청 속도를 자동 조절
    # OpenAI Tier 1: 200,000 / Tier 2: 2,000,000. 0이면 throttle 비활성화
    parser.add_argument(
        "--tpm-limit",
        type=int,
        default=200000,
        help="OpenAI TPM(분당 토큰) 한도. Default: 200000. 0이면 throttle 비활성화.",
    )
    return parser.parse_args()


def normalize_model_name(model: str) -> str:
    # 자주 쓰이는 오탈자/별명을 정규 모델 ID로 변환
    aliases = {
        # OpenAI
        "gpt-4.1o-mini": "gpt-4.1-mini",
        "gpt-4.1-o-mini": "gpt-4.1-mini",
        "gpt4.1-mini": "gpt-4.1-mini",
        "gpt4o-mini": "gpt-4o-mini",
        # Claude 약칭
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-8",
        "claude-haiku": "claude-haiku-4-5-20251001",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-opus": "claude-opus-4-8",
    }
    return aliases.get(model.strip(), model.strip())


def parse_end_row(raw: str) -> int | None:
    # 'end'/'eof' 등은 None(파일 끝까지)으로, 숫자는 정수로 변환
    text = str(raw).strip().lower()
    if text in ("", "end", "eof", "last"):
        return None
    value = int(text)
    if value < 2:
        raise ValueError("--end-row must be >= 2 or 'end'")
    return value


def row_in_range(line_number: int, start_row: int, end_row: int | None) -> bool:
    # 헤더가 줄 1이므로 데이터 행은 줄 2부터 시작
    if line_number < start_row:
        return False
    if end_row is not None and line_number > end_row:
        return False
    return True


def resolve_pack_path(raw: str) -> Path:
    # 상대 경로면 PACK_ROOT 기준으로, 절대 경로면 그대로 반환
    path = Path(raw)
    return path if path.is_absolute() else PACK_ROOT / path


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
            return CsvCell(raw=raw, inner=strip_wrapping_quotes(s), quoted=True, quote_noise=quote_noise)
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
_CSV_ROW_RE = re.compile(r'^[A-Za-z0-9_.\-]+\s*,\s*.+?\s*,\s*(.+)$', re.DOTALL)


def strip_prompt_echo(value: str) -> str:
    # 모델이 "번역: ...", "Korean: ..." 처럼 접두어를 붙여 반환할 때 제거
    text = value.strip()
    prompt_prefixes = (
        "원문:",
        "번역:",
        "번역문:",
        "korean_value:",
        "Korean:",
        "Translation:",
        "해석:",
    )
    changed = True
    while changed:
        changed = False
        label_cleaned = PROMPT_LABEL_RE.sub("", text).lstrip()
        if label_cleaned != text:
            text = label_cleaned
            changed = True
        for prefix in prompt_prefixes:
            if text.startswith(prefix):
                text = text[len(prefix) :].lstrip()
                changed = True

    # AI가 프롬프트 지시문을 번역문 앞에 그대로 포함해 반환한 경우 제거
    # 패턴: "__식별자__ 형태의 마커는 ... key: <키명>   실제 번역문"
    # "key: <키명>" 다음 공백 이후를 실제 번역으로 간주
    if text.startswith("__") and "key:" in text:
        m = re.search(r"\bkey\s*:\s*\S+\s+", text)
        if m:
            extracted = text[m.end():].strip()
            if extracted:
                print(f"  [경고] 프롬프트 에코 감지, 지시문 제거 후 번역 추출", flush=True)
                text = extracted

    # AI가 CSV 행 전체를 반환한 경우 → 세 번째 열(korean_value)만 추출
    # 예: "job_key,English text,한국어 번역" → "한국어 번역"
    m = _CSV_ROW_RE.match(text)
    if m:
        extracted = m.group(1).strip().strip('"')
        if extracted:
            print(f"  [경고] CSV 형식 응답 감지, korean_value만 추출: {console_text(extracted)}")
            text = extracted

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


def load_guidelines_prompt(path: Path) -> str:
    # translation_guidelines.md에서 '## 기본 원칙' ~ 특정 헤딩 전까지만 발췌
    # 발췌 범위를 제한하는 이유: 전체 파일을 넣으면 프롬프트 토큰이 너무 커짐
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8-sig")
    start = text.find(GUIDELINE_START_HEADING)
    if start == -1:
        start = 0
    stop_positions = [text.find(heading, start + 1) for heading in GUIDELINE_STOP_HEADINGS]
    stop_positions = [pos for pos in stop_positions if pos != -1]
    stop = min(stop_positions) if stop_positions else len(text)
    excerpt = text[start:stop].strip()
    return (
        "프로젝트 번역지침 발췌:\n"
        "아래 지침은 반드시 따른다. 특히 토큰은 번역하지 말고 원형을 유지한다.\n\n"
        f"{excerpt}"
    )


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
    for extra in (extra_paths or []):
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
    # 특수 구분자를 마커로 치환해 AI가 토큰을 누락·변형하지 못하게 보호
    # - £pop£        → __ICON_pop__    (구분자 타입 prefix로 충돌 방지)
    # - $energy$     → __DOLLAR_energy__ (동일)
    # - [Root.GetName] → __B0__        (길고 복잡한 스크립트 표현식 → 순번 마커)
    # - §Y, §!, \n 등 → 그대로 (시스템 프롬프트 규칙으로 보호)
    # 복원 맵: {마커 → 원래 토큰 전체}
    replacements: dict[str, str] = {}
    bracket_counter = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal bracket_counter
        token = match.group(0)
        if token.startswith("£"):
            # 정상: £word£ → inner=word / 오타: £word → inner=word (닫는 £ 없음)
            inner = token[1:-1] if token.endswith("£") else token[1:]
            marker = f"__ICON_{inner}__"
            replacements[marker] = token
            return marker
        if token.startswith("$") and token.endswith("$"):
            marker = f"__DOLLAR_{token[1:-1]}__"
            replacements[marker] = token
            return marker
        if token.startswith("[") and token.endswith("]"):
            # 스크립트 표현식은 길고 복잡해서 내용을 그대로 두면 AI가 혼란 → 순번 마커
            marker = f"__B{bracket_counter}__"
            bracket_counter += 1
            replacements[marker] = token
            return marker
        # §X, \n, \t 등 — 치환하지 않음
        return token

    masked = PROTECT_TOKEN_RE.sub(replace, value)
    return masked, replacements


def restore_protected_tokens(value: str, replacements: dict[str, str]) -> str:
    # 모델 출력에서 __TN__ 마커를 원래 식별자로 복원
    # 마커가 £...£ / $...$ / [...] 안에 있으면 구조는 이미 유지된 상태
    restored = value
    for marker, original in replacements.items():
        restored = restored.replace(marker, original)
    return restored


def extract_tokens(value: str) -> dict[str, list[str]]:
    """토큰 유형별 목록 반환. 반환 예: {"dollar_ref": ["$energy$"], ...}"""
    return {name: pattern.findall(value or "") for name, pattern in TOKEN_PATTERNS.items()}


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
            return m.group(0)   # 원문에 있는 코드는 유지
        return inner            # 없는 코드는 태그만 제거, 텍스트 보존
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
        # EN에 있는 \n의 위치(순서)를 구한다 — 이 위치의 \n은 건드리면 안 됨
        en_nl_count = len(TOKEN_PATTERNS["escaped_newline"].findall(source))
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
                result = result[:pos] + _TABBED_NL + result[pos + 2:]  # \n = 2글자

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


def _detect_provider(key: str) -> str:
    """API 키 prefix로 provider를 자동 감지한다.

    sk-ant- 또는 sk-ant로 시작하면 anthropic, 그 외는 openai.
    """
    if key.startswith("sk-ant"):
        return "anthropic"
    return "openai"


class APIKeyManager:
    """API 키를 환경 변수 → 파일 순서로 로드하고 provider를 자동 감지한다.

    키 파일 우선순위:
      1. ANTHROPIC_API_KEY 환경 변수
      2. OPENAI_API_KEY 환경 변수
      3. tools/api_key.txt
      4. tools/openai_api_key.txt (하위호환 폴백)

    provider는 키 prefix로 자동 감지된다:
      sk-ant-... → anthropic
      sk-...     → openai
    """

    def __init__(self, api_key_file: str | Path = DEFAULT_API_KEY_FILE) -> None:
        self.api_key_file = Path(api_key_file)
        self.api_key = self._load_key()
        self.provider = _detect_provider(self.api_key)

    def _load_key(self) -> str:
        # 1순위: ANTHROPIC_API_KEY 환경 변수
        for env_var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            env_key = os.environ.get(env_var, "").strip()
            if env_key:
                return env_key
        # 2순위: api_key.txt → openai_api_key.txt (하위호환)
        for candidate in (self.api_key_file, _LEGACY_API_KEY_FILE):
            if candidate.is_file():
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        return stripped
        raise ValueError(
            "API 키가 없습니다. ANTHROPIC_API_KEY / OPENAI_API_KEY 환경 변수 또는 "
            "tools/api_key.txt에 키를 설정하세요."
        )


class TPMThrottle:
    """분당 토큰 한도를 초과하지 않도록 요청 전에 대기시키는 버킷."""

    def __init__(self, tpm_limit: int, workers: int, system_prompt: str = "") -> None:
        self.tpm_limit = tpm_limit
        self.workers = max(1, workers)
        # 시스템 프롬프트는 매 요청마다 소비되므로 고정 오버헤드로 포함
        self._system_tokens = max(1, len(system_prompt) // 3)
        self._lock = threading.Lock()
        self._window: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._force_wait_until: float = 0.0  # 429 발생 시 강제 대기 종료 시각

    def _estimate_tokens(self, text: str) -> int:
        # 시스템 프롬프트 + 유저 메시지 + 예상 응답(입력의 0.8배) 합산
        user_tokens = max(1, len(text) // 3)
        response_tokens = max(50, int(user_tokens * 0.8))
        return self._system_tokens + user_tokens + response_tokens

    def _flush_old(self, now: float) -> None:
        cutoff = now - 60.0
        self._window = [(ts, tok) for ts, tok in self._window if ts > cutoff]

    def _used_tokens(self) -> int:
        return sum(tok for _, tok in self._window)

    def acquire(self, text: str) -> None:
        """토큰 한도 내에 들어올 때까지 대기 후 사용량 등록.

        메인 스레드에서 순차적으로 호출되므로 in_flight 중인 요청들의
        토큰은 이미 윈도우에 등록되어 있다. margin은 이번 요청 1개분만 확보.
        """
        estimated = self._estimate_tokens(text)
        margin = estimated  # 이번 요청 1개분 마진 (workers배 불필요)
        while True:
            # 429로 인한 강제 대기 중이면 먼저 처리
            now = time.monotonic()
            if now < self._force_wait_until:
                wait = self._force_wait_until - now
                print(f"  [429 대기] {wait:.1f}초 대기...", flush=True)
                time.sleep(wait)

            with self._lock:
                now = time.monotonic()
                self._flush_old(now)
                used = self._used_tokens()
                if used + margin <= self.tpm_limit * 0.95:
                    self._window.append((now, estimated))
                    return
                oldest_ts = self._window[0][0] if self._window else now
                wait = max(0.5, 60.0 - (now - oldest_ts) + 1.0)
            print(f"  [TPM 대기] 사용량 {used:,}/{self.tpm_limit:,} 토큰, {wait:.1f}초 대기...", flush=True)
            time.sleep(wait)

    def record_actual(self, actual_tokens: int) -> None:
        """API 응답의 실제 토큰 수로 마지막 추정치를 보정."""
        with self._lock:
            if self._window:
                ts, _ = self._window[-1]
                self._window[-1] = (ts, actual_tokens)

    def notify_rate_limit(self, retry_after_ms: int = 5000) -> None:
        """429 수신 시 force_wait_until만 설정해 대기한다.

        _window에는 아무것도 추가하지 않는다.
        추가하면 가상의 200,000토큰이 60초간 윈도우에 남아
        force_wait 해제 후에도 불필요하게 추가 대기하게 된다.
        force_wait_until 자체가 재요청을 막는 역할을 하므로 충분하다.
        """
        wait_sec = max(1.0, retry_after_ms / 1000.0) + 1.0
        with self._lock:
            self._force_wait_until = time.monotonic() + wait_sec


class Translator:
    """단일 OpenAI 클라이언트 인스턴스. 멀티스레드 환경에서 공유해 사용한다."""

    def __init__(
        self,
        key_manager: APIKeyManager | None = None,
        config: TranslationConfig | None = None,
        tpm_throttle: TPMThrottle | None = None,
    ) -> None:
        self.config = config or TranslationConfig()
        self.key_manager = key_manager or APIKeyManager(self.config.api_key_file)
        self.tpm_throttle = tpm_throttle
        self.translated_count = 0  # 성공적으로 번역된 행 수 (재시도 포함)
        self.request_count = 0      # 실제 OpenAI API 요청 횟수 (재시도 포함)
        # 시스템 프롬프트: 3단계
        #   system_prompt           — 토큰 없는 단순 텍스트용 (기본, 짧음)
        #   system_prompt_with_tokens — 토큰 포함 텍스트용 (토큰 규칙 추가)
        #   system_prompt_full      — 토큰 포함 + 가이드라인 (use_guidelines 시)
        guideline_prompt = load_guidelines_prompt(self.config.guidelines_file) if self.config.use_guidelines else ""
        self.system_prompt = SYSTEM_PROMPT
        self.system_prompt_with_tokens = SYSTEM_PROMPT_WITH_TOKENS
        self.system_prompt_full = f"{SYSTEM_PROMPT_WITH_TOKENS}\n\n{guideline_prompt}" if guideline_prompt else SYSTEM_PROMPT_WITH_TOKENS
        # 용어집 로드 (번역 텍스트별 매칭에 사용)
        self.glossary = load_glossary(self.config.glossary_file, self.config.extra_glossary_files)
        # TPMThrottle에 실제 시스템 프롬프트 토큰 수 전달 (지침서 포함 후 확정)
        if tpm_throttle is not None:
            tpm_throttle._system_tokens = max(1, len(self.system_prompt_full) // 3)
        self.provider = self.key_manager.provider
        if self.provider == "anthropic":
            try:
                import anthropic as _anthropic
            except ModuleNotFoundError as exc:
                raise TranslationFatalError("anthropic 패키지가 없습니다. `python -m pip install anthropic`를 실행하세요.") from exc
            self.client = _anthropic.Anthropic(api_key=self.key_manager.api_key)
        else:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as exc:
                raise TranslationFatalError("openai 패키지가 없습니다. `python -m pip install openai`를 실행하세요.") from exc
            self.client = OpenAI(api_key=self.key_manager.api_key)

    def _build_user_prompt(
        self,
        key: str,
        text: str,
        protected: dict[str, str] | None,
        missing_tokens: list[str] | None = None,
    ) -> str:
        lines = [
            "다음 Stellaris 로컬라이징 값을 한국어로 번역하세요.",
            "출력은 번역문 하나만 작성하세요.",
        ]
        if protected:
            marker_list = ", ".join(protected.keys())
            lines.append(
                f"__ICON_xxx__, __DOLLAR_xxx__, __B0__ 형태의 마커는 Stellaris 게임 토큰을 대체한 것입니다. "
                f"번역문에 반드시 그대로 포함하세요. 절대 삭제하거나 번역하지 마세요.\n"
                f"반드시 포함해야 할 마커 목록: {marker_list}"
            )
        if missing_tokens:
            token_list = ", ".join(missing_tokens)
            lines.append(
                f"이전 번역에서 다음 토큰이 누락되었습니다. 반드시 번역문에 포함하세요: {token_list}"
            )
        matched_terms = find_matching_terms(text, self.glossary)
        if matched_terms:
            term_lines = "\n".join(f"  {eng} → {kor}" for eng, kor in sorted(matched_terms.items()))
            lines.append(
                f"다음 용어는 반드시 아래 한국어로 번역하세요 (다른 표현 금지):\n{term_lines}"
            )
        lines += [f"key: {key}", f"english_value:\n{text}"]
        return "\n".join(lines)

    def translate(self, key: str, text: str, protected: dict[str, str] | None = None, missing_tokens: list[str] | None = None) -> tuple[str, str, str]:
        """한 행의 english_value를 OpenAI에 보내 한국어 번역을 받는다.

        반환: (번역 결과, system_prompt, user_prompt)

        재시도 로직:
          - 네트워크 오류·서버 오류: 지수 대기(최대 15초) 후 재시도
          - 429 (TPM/RPM 초과): TPMThrottle에 알리고 재시도
          - 모델 없음 등 복구 불가 오류: TranslationFatalError 즉시 raise
        """
        last_error: Exception | None = None
        # 프롬프트 선택:
        #   토큰 없음 → system_prompt (기본, 짧음)
        #   토큰 있음 → system_prompt_with_tokens (토큰 규칙 포함)
        #   use_guidelines → system_prompt_full (토큰 규칙 + 가이드라인)
        has_tokens = bool(TOKEN_RE.search(text))
        if self.config.use_guidelines:
            active_system_prompt = self.system_prompt_full
        elif has_tokens:
            active_system_prompt = self.system_prompt_with_tokens
        else:
            active_system_prompt = self.system_prompt
        user_prompt = self._build_user_prompt(key, text, protected, missing_tokens)
        for attempt in range(max(1, self.config.max_retries)):
            try:
                # TPM acquire는 메인 스레드(process_csv_file)에서 이미 처리됨
                # 여기서 중복 호출하지 않는다
                self.request_count += 1
                if self.provider == "anthropic":
                    response = self.client.messages.create(
                        model=self.config.model,
                        max_tokens=1024,
                        system=active_system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    content = response.content[0].text if response.content else ""
                    total_tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
                else:
                    response = self.client.chat.completions.create(
                        model=self.config.model,
                        temperature=self.config.temperature,
                        messages=[
                            {"role": "system", "content": active_system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    )
                    content = response.choices[0].message.content or ""
                    total_tokens = response.usage.total_tokens if response.usage else 0
                result = strip_code_fence(content)
                if not result:
                    preview = repr(content) if content else "<빈 문자열>"
                    print(f"  [디버그] 빈 응답 — key: {key} / 원문: {console_text(text)}")
                    print(f"  [디버그] API raw content: {preview}")
                    raise RuntimeError("Empty response from API")
                # 추정치 대신 API가 알려준 실제 토큰 수로 TPM 버킷 보정
                if self.tpm_throttle and total_tokens:
                    self.tpm_throttle.record_actual(total_tokens)
                self.translated_count += 1
                if self.config.request_delay > 0:
                    time.sleep(self.config.request_delay)
                return result, active_system_prompt, user_prompt
            except Exception as exc:
                last_error = exc
                message = str(exc)
                lower = message.lower()
                print(f"  [경고] API 번역 실패 (key={key}, 시도={attempt+1}/{max(1, self.config.max_retries)}): {console_text(message)}")
                # 복구 불가 오류: 모델명 오류, 접근 권한 없음 등
                if "model_not_found" in lower or "does not exist" in lower or "invalid_request_error" in lower or "not_found_error" in lower:
                    raise TranslationFatalError(
                        f"모델을 찾을 수 없거나 접근 권한이 없습니다: {self.config.model}"
                    ) from exc
                if any(token in lower for token in ("rate limit", "429", "temporarily unavailable", "timeout")):
                    # API 응답에서 retry_after 시간을 파싱해 TPM throttle에 전달
                    import re as _re
                    retry_ms_match = _re.search(r"try again in (\d+)ms", message)
                    retry_ms = int(retry_ms_match.group(1)) if retry_ms_match else 5000
                    wait_sec = max(1.0, retry_ms / 1000.0) + 1.0
                    print(f"  [429] Rate limit — {wait_sec:.1f}초 대기 후 재시도", flush=True)
                    if self.tpm_throttle:
                        self.tpm_throttle.notify_rate_limit(retry_ms)
                    else:
                        time.sleep(wait_sec)
                    continue
                # 일반 오류: 지수 대기 후 재시도 (최대 15초)
                if attempt < self.config.max_retries - 1:
                    time.sleep(min(3 * (attempt + 1), 15))
        raise RuntimeError("API retries exhausted") from last_error


def iter_csv_files(auto_keys_dir: Path, mods: set[str], file_filters: list[str]) -> list[Path]:
    # 우선순위: --file 지정 > --mod 지정 > 전체 탐색
    if file_filters:
        paths: list[Path] = []
        for raw in file_filters:
            candidate = resolve_pack_path(raw)
            if candidate.is_file():
                paths.append(candidate)
                continue
            # 파일명만 넣어도 auto_keys 하위 전체에서 검색
            paths.extend(auto_keys_dir.rglob(Path(raw).name))
        return sorted(set(paths))
    if mods:
        files: list[Path] = []
        for mod in sorted(mods):
            mod_dir = auto_keys_dir / mod
            if mod_dir.is_dir():
                files.extend(mod_dir.rglob("*_key.csv"))
        return sorted(files)
    # 필터 없음: auto_keys 하위 모든 *_key.csv
    return sorted(Path(p) for p in glob.glob(str(auto_keys_dir / "**" / "*_key.csv"), recursive=True))


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    # CSV를 읽어 (열 이름 목록, 행 목록)을 반환.
    # 각 행의 english_value / korean_value는 csv.reader가 따옴표를 벗긴 상태다.
    # 파일의 `"""값"""` → `'"값"'` (따옴표 1개씩) — CsvCell.parse()로 분리.
    # korean_value 열이 없으면 자동 추가 (신규 파일 대응).
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "key" not in fieldnames or "english_value" not in fieldnames:
            raise ValueError(f"{path}: key and english_value columns are required")
        if "korean_value" not in fieldnames:
            fieldnames.append("korean_value")
        rows = [{field: row.get(field, "") or "" for field in fieldnames} for row in reader]
        return fieldnames, rows


def count_candidates(
    path: Path,
    include_existing: bool = False,
    only_suspicious: bool = False,
    start_row: int = 2,
    end_row: int | None = None,
) -> int:
    # 실제 번역 전에 작업 대상 행 수를 세는 사전 검사 (API 호출 없음)
    # include_existing=True면 이미 번역된 행도 포함해서 셈
    _, rows = read_rows(path)
    count = 0
    for offset, row in enumerate(rows, start=2):
        if not row_in_range(offset, start_row, end_row):
            continue
        eng = CsvCell.parse(row.get("english_value", ""))
        kor = CsvCell.parse(row.get("korean_value", ""))
        if kor.inner.strip() and not include_existing:
            continue
        if has_source(eng.inner) and (not only_suspicious or is_suspicious_translation(eng.inner, kor.inner)):
            count += 1
    return count


def write_rows_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    # .tmp 임시 파일에 쓰고 완료 후 rename — 중간에 프로세스가 죽어도 파일 손상 없음.
    # row의 english/korean_value는 CsvCell raw 값 (`"내용"` 형태).
    # csv.writer(QUOTE_MINIMAL)가 이를 파일에 `"""내용"""` 으로 올바르게 escape한다.
    # translate_value 단계에서 이미 정리됐으므로 저장 시 추가 변환 없이 그대로 쓴다.
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow([row.get(f, "") or "" for f in fieldnames])
    shutil.move(str(temp_path), str(path))


def backup_csv(path: Path, auto_keys_dir: Path) -> Path:
    # 원본 CSV를 maintenance/backups/translate_keys/타임스탬프/ 에 복사
    # 변경 전 최초 1회만 실행 (backed_up 플래그로 제어)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        rel = path.relative_to(auto_keys_dir)
    except ValueError:
        rel = Path(path.name)
    backup_path = BACKUP_ROOT / timestamp / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def sample_path_from_arg(raw: str, report_dir: Path) -> Path:
    if raw:
        return resolve_pack_path(raw)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return report_dir / f"ai_translation_sample_{timestamp}.csv"


def should_stop(total_changed: int, limit_rows: int) -> bool:
    return bool(limit_rows and total_changed >= limit_rows)


def translate_value(
    key: str,
    eng_cell: CsvCell,
    translator: Translator,
    allow_token_mismatch: bool,
    retry_token_mismatch: int,
) -> tuple[str | None, str | None, str, str]:
    """한 행을 번역하고 토큰 일치 여부를 검증한다.

    eng_cell: CsvCell (raw/inner/quoted 분리된 상태)
    반환: (번역 성공 시 korean raw 값, None, system_prompt, user_prompt)
         또는 (None, 마지막 거부된 raw 값, system_prompt, user_prompt)
    - API에는 inner(따옴표 없는 내용)만 전송
    - 번역 결과를 정리한 뒤 eng_cell.with_translated()로 따옴표 복원
    - 토큰 검증은 inner 기준으로 수행
    """
    attempts = max(1, retry_token_mismatch + 1)
    last_value = ""
    last_system_prompt = ""
    last_user_prompt = ""
    missing_tokens: list[str] | None = None
    request_text, protected = (
        protect_tokens(eng_cell.inner) if translator.config.protect_tokens
        else (eng_cell.inner, {})
    )
    for attempt in range(attempts):
        raw_translation, last_system_prompt, last_user_prompt = translator.translate(key, request_text, protected, missing_tokens)
        restored = restore_protected_tokens(raw_translation, protected)
        cleaned_inner = normalize_csv_cell(strip_prompt_echo(strip_code_fence(restored).strip()), source=eng_cell.inner)
        cleaned_inner = strip_extra_color_codes(cleaned_inner, eng_cell.inner)
        cleaned_inner = auto_patch_tokens(cleaned_inner, eng_cell.inner)
        # API가 영문을 그대로 반환한 경우 단어집에서 직접 대체 시도
        cleaned_inner = _fallback_glossary(cleaned_inner, eng_cell.inner, translator.glossary)
        translated_raw = eng_cell.with_translated(cleaned_inner)
        last_value = translated_raw
        if allow_token_mismatch or tokens_match(eng_cell.inner, cleaned_inner):
            return translated_raw, None, last_system_prompt, last_user_prompt
        delta = token_delta(eng_cell.inner, cleaned_inner)
        delta_summary = ", ".join(
            f"{t}: 누락={v['missing']} 추가={v['extra']}"
            for t, v in delta.items()
        )
        print_block(
            f"  [토큰 불일치] {key} (재시도 {attempt + 1}/{attempts}): {console_text(delta_summary)}",
            원문=console_text(eng_cell.inner),
            번역=console_text(cleaned_inner),
        )
        # 다음 재시도 시 누락/추가 토큰 정보를 프롬프트에 포함
        missing_tokens = [t for v in delta.values() for t in v.get("missing", [])]
        extra_tokens = [t for v in delta.values() for t in v.get("extra", [])]
        if extra_tokens:
            missing_tokens = missing_tokens + [f"(원문에 없는 토큰 추가 금지: {', '.join(extra_tokens)})"]
    return None, last_value, last_system_prompt, last_user_prompt


def process_csv_file(
    filepath: Path,
    auto_keys_dir: Path,
    translator: Translator | None,
    *,
    dry_run: bool,
    dry_run_with_api: bool = False,
    copy_token_only: bool,
    allow_token_mismatch: bool,
    retry_token_mismatch: int,
    limit_rows: int,
    total_changed_so_far: int,
    rewrite_existing: bool,
    key_filter: set[str],
    only_suspicious: bool,
    start_row: int,
    end_row: int | None,
    save_at_end: bool = False,
    workers: int = 1,
    progress: tuple[int, int] | None = None,
    log_success=None,
    log_failure=None,
) -> tuple[FileResult, int]:
    """CSV 파일 한 개를 처리해 번역 결과를 저장한다.

    처리 흐름:
      1. 행 전체를 읽고 번역 대상 필터링 (candidates)
      2. 토큰 전용 행은 API 없이 즉시 복사
      3. 나머지(api_candidates)를 ThreadPoolExecutor로 병렬 번역
      4. 번역 결과를 제출 순서대로 받아 행에 기록 + 저장 (save_at_end=False면 매행)
      5. Ctrl+C 시 이미 제출된 요청 완료를 기다렸다가 결과 저장 후 중단

    반환: (FileResult, 이 파일에서 변경된 행 수)
    """
    result = FileResult(path=str(filepath))
    fieldnames, rows = read_rows(filepath)
    changed_this_file = 0
    backed_up = False
    save_lock = threading.Lock()  # 멀티스레드 저장 직렬화

    def do_save() -> None:
        # 첫 저장 시 원본을 백업하고 atomic write
        nonlocal backed_up
        if not backed_up:
            result.backup_path = str(backup_csv(filepath, auto_keys_dir))
            backed_up = True
        write_rows_atomic(filepath, fieldnames, rows)

    # ── 1단계: 번역 대상 행 수집 ──────────────────────────────────────────
    candidates: list[tuple[int, dict[str, str], CsvCell]] = []
    for line_number, row in enumerate(rows, start=2):
        result.rows += 1
        if not row_in_range(line_number, start_row, end_row):
            continue
        key = row.get("key", "").strip()
        if key_filter and key not in key_filter:
            continue
        eng = CsvCell.parse(row.get("english_value", ""))
        kor = CsvCell.parse(row.get("korean_value", ""))
        if kor.inner.strip() and not rewrite_existing:
            result.skipped_existing += 1
            continue
        if not has_source(eng.inner):
            result.skipped_empty_english += 1
            continue
        if only_suspicious and not (is_suspicious_translation(eng.inner, kor.inner) or kor.quote_noise):
            result.skipped_existing += 1
            continue
        if should_stop(total_changed_so_far + changed_this_file, limit_rows):
            continue
        result.candidates += 1
        candidates.append((line_number, row, eng))

    if dry_run and not dry_run_with_api:
        return result, changed_this_file
    if not candidates:
        return result, changed_this_file

    # ── 2단계: API 불필요 행 즉시 처리 ──────────────────────────────────
    # 2a. 토큰 전용 행 → english_value 그대로 복사
    # 2b. 단어집 exact match 행 (토큰 없는 순수 텍스트) → API 없이 한국어로 대체
    api_candidates: list[tuple[int, dict[str, str]]] = []
    glossary = translator.glossary if translator is not None else {}
    for line_number, row, eng in candidates:
        key_name = row.get("key", "").strip()
        if copy_token_only and is_token_only(eng.inner):
            row["korean_value"] = row.get("english_value", "")
            result.copied_token_only += 1
            changed_this_file += 1
            result.changed = True
            print(f"  [토큰 복사] {key_name}: {console_text(eng.inner)}")
        elif glossary:
            source_text = _strip_all_tokens(eng.inner).strip()
            kor_direct = glossary.get(source_text.lower()) if source_text else None
            if kor_direct and not TOKEN_RE.search(eng.inner):
                # 원문 전체가 순수 텍스트이고 단어집에 exact match인 경우만 API 스킵
                translated_raw = eng.with_translated(kor_direct)
                row["korean_value"] = translated_raw
                result.glossary_applied += 1
                changed_this_file += 1
                result.changed = True
                print(f"  [단어집 대체] {key_name}: {console_text(eng.inner)} → {console_text(kor_direct)}")
            else:
                api_candidates.append((line_number, row))
        else:
            api_candidates.append((line_number, row))

    if not api_candidates or translator is None:
        if result.changed and not dry_run and not dry_run_with_api:
            do_save()
        return result, changed_this_file

    # ── 3~5단계: 슬라이딩 윈도우 방식 병렬 번역 ─────────────────────────
    # in_flight: 현재 실행 중인 (row, future) 쌍을 최대 workers개 유지
    # submit → in_flight 가득 참 → 가장 오래된 것 결과 수집 → 다음 submit
    # 결과 수집이 submit과 교대로 이루어지므로 즉시 출력 가능
    fatal_event = threading.Event()

    def translate_one(
        row: dict[str, str],
    ) -> tuple[str | None, str | None, str, str, Exception | None]:
        # 스레드 함수: CsvCell로 파싱 후 API 요청만 수행
        try:
            key = row.get("key", "").strip()
            eng = CsvCell.parse(row.get("english_value", ""))
            translated_raw, rejected_raw, sys_prompt, usr_prompt = translate_value(
                key, eng, translator, allow_token_mismatch, retry_token_mismatch
            )
            return translated_raw, rejected_raw, sys_prompt, usr_prompt, None
        except TranslationFatalError as exc:
            fatal_event.set()
            return None, None, "", "", exc
        except Exception as exc:
            return None, None, "", "", exc

    def _write_log(handle, record: dict) -> None:
        if handle is None:
            return
        try:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
        except Exception:
            pass

    def collect_one(row: dict[str, str], future: "Future[tuple[str|None,str|None,str,str,Exception|None]]") -> None:
        # future 하나의 결과를 받아 저장·출력 처리
        nonlocal changed_this_file
        key = row.get("key", "").strip()
        eng = CsvCell.parse(row.get("english_value", ""))
        translated_raw, rejected_raw, sys_prompt, usr_prompt, exc = future.result()
        ts = dt.datetime.now().isoformat(timespec="seconds")
        if exc is not None:
            if isinstance(exc, TranslationFatalError):
                raise exc
            result.failed += 1
            result.issues.append({"key": key, "reason": "translation_failed", "english_value": eng.inner, "error": str(exc)})
            print_block(
                f"  [오류] 번역 실패 — key={key}",
                원문=console_text(eng.inner),
                에러=console_text(exc),
            )
            _write_log(log_failure, {
                "timestamp": ts,
                "key": key,
                "english_value": eng.inner,
                "reason": "translation_error",
                "error": str(exc),
                "system_prompt": sys_prompt,
                "user_prompt": usr_prompt,
            })
            return
        if translated_raw is None:
            result.skipped_token_mismatch += 1
            rejected_inner = CsvCell.parse(rejected_raw or "").inner
            delta = token_delta(eng.inner, rejected_inner) if rejected_inner else {}
            result.issues.append({
                "key": key,
                "reason": "hard_token_mismatch",
                "english_value": eng.inner,
                "rejected_value": rejected_raw or "",
                "token_delta": delta,
            })
            _write_log(log_failure, {
                "timestamp": ts,
                "key": key,
                "english_value": eng.inner,
                "reason": "hard_token_mismatch",
                "rejected_value": rejected_raw or "",
                "token_delta": delta,
                "system_prompt": sys_prompt,
                "user_prompt": usr_prompt,
            })
            return
        with save_lock:
            row["korean_value"] = translated_raw
            result.translated += 1
            changed_this_file += 1
            result.changed = True
            kor_inner = CsvCell.parse(translated_raw).inner
            if progress is not None:
                done, total = progress
                done += result.translated + result.copied_token_only
                pct = done / total * 100 if total else 0
                print_block(f"  [번역 완료] {key}  ({done}/{total}, {pct:.1f}%)", 원문=console_text(eng.inner), 번역=console_text(kor_inner))
            else:
                print_block(f"  [번역 완료] {key}", 원문=console_text(eng.inner), 번역=console_text(kor_inner))
            _write_log(log_success, {
                "timestamp": ts,
                "key": key,
                "english_value": eng.inner,
                "korean_value": kor_inner,
                "system_prompt": sys_prompt,
                "user_prompt": usr_prompt,
            })
            if not save_at_end:
                do_save()

    interrupted = False
    # in_flight: deque[(row, future)], 최대 workers개
    in_flight: deque[tuple[dict[str, str], Future[tuple[str | None, str | None, str, str, Exception | None]]]] = deque()

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        try:
            for line_number, row in api_candidates:
                if fatal_event.is_set():
                    break

                english_value = row.get("english_value", "")

                # 슬롯이 가득 찼으면 가장 오래된 것 먼저 수집 → 즉시 출력
                if len(in_flight) >= max(1, workers):
                    oldest_row, oldest_future = in_flight.popleft()
                    collect_one(oldest_row, oldest_future)

                if fatal_event.is_set():
                    break

                # 메인 스레드에서 TPM 대기 (스레드 낭비 없음)
                if translator.tpm_throttle:
                    translator.tpm_throttle.acquire(english_value)

                result.last_processed_row = line_number
                future = executor.submit(translate_one, row)
                in_flight.append((row, future))

            # 남은 in_flight 모두 수집
            while in_flight:
                oldest_row, oldest_future = in_flight.popleft()
                collect_one(oldest_row, oldest_future)

        except KeyboardInterrupt:
            interrupted = True
            fatal_event.set()
            print("\n  [중단] Ctrl+C 감지 — 이미 요청한 항목 응답 대기 중...")
            # in_flight에 남은 것(최대 workers개)만 완료 대기 후 저장
            while in_flight:
                oldest_row, oldest_future = in_flight.popleft()
                try:
                    translated_raw, _rejected, _sys, _usr, exc = oldest_future.result()
                    if translated_raw and exc is None:
                        with save_lock:
                            oldest_row["korean_value"] = translated_raw
                            result.translated += 1
                            changed_this_file += 1
                            result.changed = True
                            print(f"  [저장] {oldest_row.get('key','')}")
                            if not save_at_end:
                                do_save()
                except Exception:
                    pass
            print("  [중단] 요청 완료분 저장 끝.")
            raise

    # --save-at-end 모드: 파일 처리가 모두 끝난 후 한 번만 저장
    if result.changed and not dry_run and not dry_run_with_api:
        do_save()
    return result, changed_this_file


def write_sample_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_file",
        "line_number",
        "key",
        "english_value",
        "sample_korean_value",
        "existing_korean_value",
        "status",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: normalize_csv_cell(row.get(field, "") or "") for field in fieldnames})


def translate_sample_file(
    filepath: Path,
    auto_keys_dir: Path,
    translator: Translator,
    *,
    sample_rows: int,
    include_existing: bool,
    only_suspicious: bool,
    copy_token_only: bool,
    allow_token_mismatch: bool,
    retry_token_mismatch: int,
    key_filter: set[str],
    start_row: int,
    end_row: int | None,
    workers: int = 1,
) -> tuple[list[dict[str, str]], FileResult]:
    """원본 CSV를 수정하지 않고 N행만 번역해 샘플 목록을 반환한다.

    --sample-rows 모드에서 사용. 번역 품질 사전 확인용.
    원본 파일에는 어떠한 쓰기도 하지 않는다.
    """
    result = FileResult(path=str(filepath))
    _, rows = read_rows(filepath)
    rel_file = str(filepath.relative_to(auto_keys_dir)) if filepath.is_relative_to(auto_keys_dir) else str(filepath)

    # ── 대상 행 수집 ──────────────────────────────────────────────────────
    # (line_number, key, eng_cell, kor_inner)
    candidates: list[tuple[int, str, CsvCell, str]] = []
    for line_number, row in enumerate(rows, start=2):
        result.rows += 1
        if not row_in_range(line_number, start_row, end_row):
            continue
        key = row.get("key", "").strip()
        if key_filter and key not in key_filter:
            continue
        eng = CsvCell.parse(row.get("english_value", ""))
        kor = CsvCell.parse(row.get("korean_value", ""))
        if kor.inner.strip() and not include_existing:
            result.skipped_existing += 1
            continue
        if not has_source(eng.inner):
            result.skipped_empty_english += 1
            continue
        if only_suspicious and not (is_suspicious_translation(eng.inner, kor.inner) or kor.quote_noise):
            result.skipped_existing += 1
            continue
        if sample_rows and len(candidates) >= sample_rows:
            continue
        result.candidates += 1
        candidates.append((line_number, key, eng, kor.inner))

    # ── 토큰 전용 행은 API 없이 즉시 처리 ────────────────────────────────
    token_results: dict[int, tuple[str, str, str]] = {}  # line_number → (sample_inner, status, note)
    api_candidates: list[tuple[int, str, CsvCell, str]] = []
    for line_number, key, eng, kor_inner in candidates:
        if copy_token_only and is_token_only(eng.inner):
            token_results[line_number] = (eng.inner, "copied_token_only", "")
            result.copied_token_only += 1
        else:
            api_candidates.append((line_number, key, eng, kor_inner))

    def translate_one_sample(item: tuple[int, str, CsvCell, str]) -> tuple[int, str, str, str, str]:
        line_number, key, eng, kor_inner = item
        try:
            # 샘플 모드는 스레드에서 직접 호출하므로 여기서 TPM acquire
            if translator.tpm_throttle:
                translator.tpm_throttle.acquire(eng.inner)
            translated_raw, rejected_raw, _sys, _usr = translate_value(
                key, eng, translator, allow_token_mismatch, retry_token_mismatch
            )
            if translated_raw is None:
                return line_number, key, "", "token_mismatch", rejected_raw or ""
            return line_number, key, CsvCell.parse(translated_raw).inner, "translated", ""
        except Exception as exc:
            return line_number, key, "", "failed", str(exc)

    # ── 병렬 API 요청 (완료 순서로 수집, 출력은 행 번호 기준 정렬) ────────
    api_results: dict[int, tuple[str, str, str]] = {}  # line_number → (sample_inner, status, note)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(translate_one_sample, item): item[0] for item in api_candidates}
        for future in as_completed(futures):
            line_number, key, sample_inner, status, note = future.result()
            api_results[line_number] = (sample_inner, status, note)
            if status == "translated":
                result.translated += 1
            elif status == "token_mismatch":
                result.skipped_token_mismatch += 1
            elif status == "failed":
                result.failed += 1

    # ── 원래 행 순서로 샘플 목록 구성 ─────────────────────────────────────
    samples: list[dict[str, str]] = []
    for line_number, key, eng, kor_inner in candidates:
        if line_number in token_results:
            sample_inner, status, note = token_results[line_number]
        else:
            sample_inner, status, note = api_results.get(line_number, ("", "failed", "no result"))
        print(f"  [{status}] {key}: {console_text(sample_inner)}")
        samples.append(
            {
                "source_file": rel_file,
                "line_number": str(line_number),
                "key": key,
                "english_value": eng.inner,
                "sample_korean_value": sample_inner,
                "existing_korean_value": kor_inner,
                "status": status,
                "note": note,
            }
        )
    return samples, result


def set_current_task(filepath: str | Path) -> None:
    # maintenance/ai_current_task.txt에 현재 작업 파일을 기록
    # 중단 후 어느 파일까지 했는지 확인용 (--start-row 재개 시 참고)
    try:
        LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE_PATH.write_text(
            f"현재 AI가 번역 중인 파일: {filepath}\n업데이트 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def clear_current_task() -> None:
    # 정상 완료 시 ai_current_task.txt 삭제
    try:
        if LOCK_FILE_PATH.exists():
            LOCK_FILE_PATH.unlink()
    except Exception:
        pass


def write_report(report_dir: Path, payload: dict[str, object]) -> Path:
    # 타임스탬프 보고서 + latest 고정 링크 두 가지를 저장
    # latest.json을 읽으면 가장 최근 실행 결과를 항상 확인 가능
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = report_dir / f"translate_keys_report_{timestamp}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8-sig")
    (report_dir / "translate_keys_latest.json").write_text(text, encoding="utf-8-sig")
    return path


def write_latest(report_dir: Path, payload: dict[str, object]) -> None:
    # 파일 처리 완료마다 latest.json만 갱신 (타임스탬프 파일은 최종에만 생성)
    report_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    (report_dir / "translate_keys_latest.json").write_text(text, encoding="utf-8-sig")


def load_report_targets(report_csv: Path) -> tuple[list[str], list[str]]:
    # review_report.py 가 생성한 검수 리포트 CSV를 읽어
    # retranslate=1 인 행의 파일 이름 목록과 키 목록을 반환한다.
    files: list[str] = []
    keys: list[str] = []
    with report_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("retranslate", "")).strip() != "1":
                continue
            fname = row.get("file", "").strip()
            key = row.get("key", "").strip()
            if fname:
                files.append(fname)
            if key:
                keys.append(key)
    return files, keys


def load_worklist_targets(worklist_csv: Path) -> tuple[list[str], list[str]]:
    # validate_auto_key_tokens.py 가 생성한 token_repair_worklist CSV를 읽어
    # file·key 목록을 반환한다. severity 필터 없이 전 행 대상.
    files: list[str] = []
    keys: list[str] = []
    with worklist_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fname = row.get("file", "").strip()
            key = row.get("key", "").strip()
            if fname:
                files.append(fname)
            if key:
                keys.append(key)
    return files, keys


def main() -> int:
    """진입점. 인수 파싱 → 파일 목록 구성 → 파일별 번역 루프 → 보고서 저장."""
    args = parse_args()
    auto_keys_dir = Path(args.auto_keys_dir)
    report_dir = Path(args.report_dir)

    report_keys: list[str] = []
    worklist_keys: list[str] = []

    # ── --from-report: 검수 리포트 기반 파일·키 필터 구성 ────────────────
    if args.from_report is not None:
        raw = args.from_report
        review_dir = PACK_ROOT / "maintenance" / "reports" / "review"
        if raw == "latest":
            report_path = review_dir / "review_latest.csv"
        elif raw == "quality":
            report_path = review_dir / "review_quality_latest.csv"
        else:
            report_path = Path(raw)
            if not report_path.is_absolute():
                report_path = PACK_ROOT / report_path
        if not report_path.exists():
            print(f"에러: 리포트 파일 없음: {report_path}")
            return 2
        report_files, report_keys = load_report_targets(report_path)
        if not report_keys:
            print("리포트에 retranslate=1 행이 없습니다. 종료.")
            return 0
        # --file / --key 와 합산 (중복 제거)
        combined_files = list(dict.fromkeys(args.file + report_files))
        combined_keys = list(dict.fromkeys(args.key + report_keys))
        args.file = combined_files
        args.key = combined_keys
        # 검수 리포트 재번역은 기존 번역 덮어쓰기 필수
        args.rewrite_existing = True
        print(f"검수 리포트: {report_path}")
        print(f"  재번역 대상: {len(report_keys)}개 키 / {len(set(report_files))}개 파일")

    # ── --from-worklist: 토큰 검증 worklist 기반 재번역 ──────────────────
    if args.from_worklist is not None:
        raw = args.from_worklist
        worklist_dir = PACK_ROOT / "maintenance" / "reports" / "token_validation"
        if raw == "latest":
            candidates = sorted(worklist_dir.glob("token_repair_worklist_*.csv"), reverse=True)
            if not candidates:
                print(f"에러: worklist 파일 없음: {worklist_dir}")
                return 2
            worklist_path = candidates[0]
        else:
            worklist_path = Path(raw)
            if not worklist_path.is_absolute():
                worklist_path = PACK_ROOT / worklist_path
        if not worklist_path.exists():
            print(f"에러: worklist 파일 없음: {worklist_path}")
            return 2
        worklist_files, worklist_keys = load_worklist_targets(worklist_path)
        if not worklist_keys:
            print("worklist에 대상 행이 없습니다. 종료.")
            return 0
        combined_files = list(dict.fromkeys(args.file + worklist_files))
        combined_keys = list(dict.fromkeys(args.key + worklist_keys))
        args.file = combined_files
        args.key = combined_keys
        args.rewrite_existing = True
        print(f"토큰 repair worklist: {worklist_path}")
        print(f"  재번역 대상: {len(worklist_keys)}개 키 / {len(set(worklist_files))}개 파일")

    # 처리 대상 CSV 파일 목록 수집 (--file / --mod / 전체 중 우선순위 적용)
    csv_files = iter_csv_files(auto_keys_dir, set(args.mod), args.file)

    # ── 인수 유효성 검사 ──────────────────────────────────────────────────
    if args.start_row < 2:
        print("에러: --start-row must be >= 2 because line 1 is the CSV header.")
        return 2
    try:
        end_row = parse_end_row(args.end_row)
    except ValueError as exc:
        print(f"에러: {exc}")
        return 2
    if end_row is not None and end_row < args.start_row:
        print("에러: --end-row must be >= --start-row, or use --end-row end.")
        return 2

    # sample_rows > 0이면 샘플 모드 (원본 수정 없음, API는 호출함)
    sample_mode = args.sample_rows > 0
    if sample_mode:
        args.dry_run = True  # 원본 저장 비활성화

    print(f"작업 디렉토리: {auto_keys_dir}")
    print(f"대상 CSV: {len(csv_files)}개")
    if args.dry_run and not sample_mode and not args.dry_run_with_api:
        print("모드: dry-run (API 호출 및 파일 수정 없음)")
    if args.dry_run_with_api:
        print("모드: dry-run-with-api (API 호출 O, 파일 수정 없음 / 토큰 마스킹 테스트용)")
    if sample_mode:
        print(f"모드: sample dry-run (원본 CSV 수정 없음, 최대 {args.sample_rows}행 OpenAI 번역 후 별도 CSV 저장)")

    # ── Translator 초기화 ─────────────────────────────────────────────────
    translator: Translator | None = None
    if not args.dry_run or sample_mode or args.dry_run_with_api:
        config = TranslationConfig(
            model=normalize_model_name(args.model),
            temperature=args.temperature,
            max_retries=args.max_retries,
            retry_token_mismatch=args.retry_token_mismatch,
            request_delay=args.request_delay,
            api_key_file=Path(args.api_key_file),
            guidelines_file=Path(args.guidelines_file),
            use_guidelines=args.use_guidelines,  # True면 토큰 없는 행에도 가이드라인 강제 포함
            protect_tokens=not args.no_protect_tokens,
            glossary_file=None if args.no_glossary else Path(args.glossary_file),
            extra_glossary_files=[Path(p) for p in args.extra_glossary],
        )
        try:
            # tpm_limit=0이면 throttle 비활성화
            throttle = TPMThrottle(args.tpm_limit, args.workers) if args.tpm_limit > 0 else None
            if throttle:
                print(f"TPM throttle: 한도 {args.tpm_limit:,}토큰/분 / workers {args.workers}")
            translator = Translator(APIKeyManager(config.api_key_file), config, tpm_throttle=throttle)
        except (ValueError, TranslationFatalError) as exc:
            print(f"에러: {exc}")
            return 2

    files_processed = 0     # 번역 작업이 실제로 생긴 파일 수
    total_changed = 0       # 전체 변경(번역+복사) 행 수
    interrupted = False
    file_results: list[FileResult] = []
    # 실시간 latest.json 갱신용 공통 payload 베이스 (루프에서 재사용)
    _report_base: dict[str, object] = {
        "dry_run": args.dry_run,
        "rewrite_existing": args.rewrite_existing,
        "only_suspicious": args.only_suspicious,
        "sample_mode": False,
        "auto_keys_dir": str(auto_keys_dir),
        "model": args.model,
        "guidelines_file": args.guidelines_file,
        "use_guidelines": args.use_guidelines,
        "protect_tokens": not args.no_protect_tokens,
        "key_filter": args.key,
        "start_row": args.start_row,
        "end_row": args.end_row,
    }
    sample_rows: list[dict[str, str]] = []
    sample_output_path = sample_path_from_arg(args.sample_output, report_dir) if sample_mode else None
    key_filter = set(args.key)
    # --from-report / --from-worklist 일 때 전체 진행률 추적용
    if args.from_report is not None:
        progress_total = len(report_keys)
    elif args.from_worklist is not None:
        progress_total = len(worklist_keys)
    else:
        progress_total = 0

    # ── 번역 로그 파일 오픈 ───────────────────────────────────────────────
    log_success_handle = None
    log_failure_handle = None
    if not args.dry_run and not sample_mode:
        timestamp_str = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        report_dir.mkdir(parents=True, exist_ok=True)
        log_success_path = report_dir / f"translate_log_success_{timestamp_str}.jsonl"
        log_failure_path = report_dir / f"translate_log_failure_{timestamp_str}.jsonl"
        log_success_handle = log_success_path.open("a", encoding="utf-8")
        log_failure_handle = log_failure_path.open("a", encoding="utf-8")
        print(f"번역 로그: {log_success_path.name} / {log_failure_path.name}")

    # ── 파일별 번역 루프 ──────────────────────────────────────────────────
    try:
        for filepath in csv_files:
            # 제한 조건 확인
            if args.limit_files and files_processed >= args.limit_files:
                break
            if should_stop(total_changed, args.limit_rows):
                break
            if sample_mode and len(sample_rows) >= args.sample_rows:
                break

            # 실제 번역 전에 대상 행 수를 세서 작업 없는 파일은 건너뜀 (API 절약)
            preflight_candidates = count_candidates(
                filepath,
                include_existing=args.rewrite_existing or (sample_mode and args.sample_include_existing),
                only_suspicious=args.only_suspicious,
                start_row=args.start_row,
                end_row=end_row,
            )
            if preflight_candidates == 0 and not args.verbose_skips:
                continue

            set_current_task(filepath)
            rel = filepath.relative_to(auto_keys_dir) if filepath.is_relative_to(auto_keys_dir) else filepath
            file_idx = len(file_results) + 1
            total_files = len(csv_files)
            if progress_total:
                progress_done = sum(r.translated + r.copied_token_only for r in file_results)
                pct = progress_done / progress_total * 100
                print(f"[{file_idx}/{total_files}] 처리 중: {rel}  ({progress_done}/{progress_total} 키, {pct:.1f}%)")
            else:
                print(f"[{file_idx}/{total_files}] 처리 중: {rel}")
            if sample_mode:
                assert translator is not None
                new_samples, result = translate_sample_file(
                    filepath,
                    auto_keys_dir,
                    translator,
                    sample_rows=args.sample_rows - len(sample_rows),
                    include_existing=args.sample_include_existing,
                    only_suspicious=args.only_suspicious,
                    copy_token_only=not args.no_copy_token_only,
                    allow_token_mismatch=args.allow_token_mismatch,
                    retry_token_mismatch=args.retry_token_mismatch,
                    key_filter=key_filter,
                    start_row=args.start_row,
                    end_row=end_row,
                    workers=args.workers,
                )
                sample_rows.extend(new_samples)
                changed = 0
            else:
                result, changed = process_csv_file(
                    filepath,
                    auto_keys_dir,
                    translator,
                    dry_run=args.dry_run,
                    dry_run_with_api=args.dry_run_with_api,
                    copy_token_only=not args.no_copy_token_only,
                    allow_token_mismatch=args.allow_token_mismatch,
                    retry_token_mismatch=args.retry_token_mismatch,
                    limit_rows=args.limit_rows,
                    total_changed_so_far=total_changed,
                    rewrite_existing=args.rewrite_existing,
                    key_filter=key_filter,
                    only_suspicious=args.only_suspicious,
                    start_row=args.start_row,
                    end_row=end_row,
                    save_at_end=args.save_at_end,
                    workers=args.workers,
                    progress=None,
                    log_success=log_success_handle,
                    log_failure=log_failure_handle,
                )

            if result.candidates or result.changed:
                files_processed += 1
            total_changed += changed
            file_results.append(result)
            # 파일 완료마다 latest.json 실시간 갱신
            if not sample_mode and not args.dry_run:
                write_latest(report_dir, {
                    **_report_base,
                    "files_seen": len(csv_files),
                    "files_processed_with_work": files_processed,
                    "total_changed": total_changed,
                    "api_translated": translator.translated_count if translator else 0,
                    "api_requests": translator.request_count if translator else 0,
                    "interrupted": False,
                    "files": [r.__dict__ for r in file_results],
                })
            last_row_info = f", last_processed_row={result.last_processed_row}" if result.last_processed_row else ""
            print(
                "  -> "
                f"candidates={result.candidates}, translated={result.translated}, "
                f"copied_token_only={result.copied_token_only}, glossary={result.glossary_applied}, "
                f"token_mismatch={result.skipped_token_mismatch}"
                f"{last_row_info}"
            )
    except KeyboardInterrupt:
        interrupted = True
        print("\n  [중단] 사용자 인터럽트로 작업을 멈춥니다.")
    except TranslationFatalError as exc:
        interrupted = True
        print(f"\n  [중단] {exc}")
    finally:
        # 로그 파일 닫기
        if log_success_handle:
            log_success_handle.close()
        if log_failure_handle:
            log_failure_handle.close()
        # 중단 시에는 ai_current_task.txt를 남겨서 어느 파일에서 멈췄는지 확인 가능하게 함
        if interrupted:
            print(f"  [안내] 현재 작업 파일 정보가 유지됩니다: {LOCK_FILE_PATH}")
        else:
            clear_current_task()

    # ── 샘플 CSV 저장 ─────────────────────────────────────────────────────
    if sample_mode and sample_output_path is not None:
        write_sample_csv(sample_output_path, sample_rows)

    # ── JSON 보고서 저장 ──────────────────────────────────────────────────
    payload = {
        "dry_run": args.dry_run,
        "rewrite_existing": args.rewrite_existing,
        "only_suspicious": args.only_suspicious,
        "sample_mode": sample_mode,
        "sample_rows_requested": args.sample_rows,
        "sample_rows_written": len(sample_rows),
        "sample_include_existing": args.sample_include_existing,
        "sample_output": str(sample_output_path) if sample_output_path else "",
        "auto_keys_dir": str(auto_keys_dir),
        "model": args.model,
        "normalized_model": normalize_model_name(args.model),
        "temperature": args.temperature,
        "request_delay": args.request_delay,
        "guidelines_file": args.guidelines_file,
        "use_guidelines": args.use_guidelines,
        "protect_tokens": not args.no_protect_tokens,
        "files_seen": len(csv_files),
        "key_filter": args.key,
        "start_row": args.start_row,
        "end_row": args.end_row,
        "files_processed_with_work": files_processed,
        "total_changed": total_changed,
        "api_translated": translator.translated_count if translator else 0,
        "api_requests": translator.request_count if translator else 0,
        "interrupted": interrupted,
        "files": [result.__dict__ for result in file_results],
    }
    report_path = write_report(report_dir, payload)

    print("\n=== 작업 종료 ===")
    print(f"files_processed_with_work={files_processed}")
    print(f"total_changed={total_changed}")
    print(f"api_translated={payload['api_translated']}")
    if sample_mode:
        print(f"sample_rows_written={len(sample_rows)}")
        print(f"sample_output={sample_output_path}")
    print(f"report={report_path}")
    # 정상 종료: 0, Ctrl+C 중단: 130 (Unix 관례)
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
