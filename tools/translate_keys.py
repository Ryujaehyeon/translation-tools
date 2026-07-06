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
import shutil
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from llm_client import (
    _SYSTEM_PROMPT_TOKEN_RULES,
    DEFAULT_API_KEY_FILE,
    DEFAULT_GLOSSARY_FILE,
    DEFAULT_GUIDELINES_FILE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    GUIDELINE_START_HEADING,
    GUIDELINE_STOP_HEADINGS,
    PACK_ROOT,
    SCRIPT_DIR,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_TOKENS,
    APIKeyManager,
    TPMThrottle,
    TranslationConfig,
    TranslationFatalError,
    Translator,
    _detect_provider,
    load_guidelines_prompt,
    normalize_model_name,
)
from tool_config import csv_dict_writer, csv_writer, resolve_pack_path, translation_keys_root
from translation_rules import (
    _CSV_ROW_RE,
    _DUMMY_VALUES,
    _ROMAN_NUMERAL_RE,
    _SECTION_SIGN_LOOKALIKE_RE,
    _STRIP_TOKENS_RE,
    _TABBED_NL,
    _TRANSLATABLE_WORD_RE,
    _WORD_RE_CACHE,
    ALL_TOKEN_TYPES,
    HANGUL_RE,
    HARD_TOKEN_TYPES,
    PROMPT_LABEL_RE,
    PROTECT_TOKEN_RE,
    TOKEN_PATTERNS,
    TOKEN_RE,
    CsvCell,
    _fallback_glossary,
    _load_glossary_file,
    _strip_all_tokens,
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

__all__ = [
    # translation_rules 재수출
    "ALL_TOKEN_TYPES",
    "HANGUL_RE",
    "HARD_TOKEN_TYPES",
    "PROMPT_LABEL_RE",
    "PROTECT_TOKEN_RE",
    "TOKEN_PATTERNS",
    "TOKEN_RE",
    "_CSV_ROW_RE",
    "_DUMMY_VALUES",
    "_ROMAN_NUMERAL_RE",
    "_SECTION_SIGN_LOOKALIKE_RE",
    "_STRIP_TOKENS_RE",
    "_TABBED_NL",
    "_TRANSLATABLE_WORD_RE",
    "_WORD_RE_CACHE",
    "CsvCell",
    "_fallback_glossary",
    "_load_glossary_file",
    "_strip_all_tokens",
    "auto_patch_tokens",
    "clean_quote_noise",
    "console_text",
    "extract_tokens",
    "find_matching_terms",
    "fix_section_sign_corruption",
    "hard_tokens_differ",
    "has_quote_noise",
    "has_source",
    "is_suspicious_translation",
    "is_token_only",
    "load_glossary",
    "normalize_csv_cell",
    "protect_tokens",
    "restore_protected_tokens",
    "strip_code_fence",
    "strip_extra_color_codes",
    "strip_prompt_echo",
    "strip_wrapping_quotes",
    "token_delta",
    "tokens_match",
    # llm_client 재수출
    "APIKeyManager",
    "DEFAULT_API_KEY_FILE",
    "DEFAULT_GLOSSARY_FILE",
    "DEFAULT_GUIDELINES_FILE",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "GUIDELINE_START_HEADING",
    "GUIDELINE_STOP_HEADINGS",
    "PACK_ROOT",
    "SCRIPT_DIR",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_WITH_TOKENS",
    "_SYSTEM_PROMPT_TOKEN_RULES",
    "_detect_provider",
    "load_guidelines_prompt",
    "normalize_model_name",
    "TPMThrottle",
    "TranslationConfig",
    "TranslationFatalError",
    "Translator",
]


AUTO_KEYS_DIR = translation_keys_root()
REPORT_DIR = PACK_ROOT / "maintenance" / "reports" / "ai_translation"
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "translate_keys"
LOCK_FILE_PATH = PACK_ROOT / "maintenance" / "ai_current_task.txt"


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
    parser = argparse.ArgumentParser(
        description="Translate auto_keys CSV files with OpenAI GPT-4.1 mini."
    )
    # 처리 범위 옵션 -------------------------------------------------------
    # translation keys 디렉토리 (기본: maintenance/tooling.ini)
    parser.add_argument("--auto-keys-dir", default=str(AUTO_KEYS_DIR))
    # 특정 모드 폴더만 처리. --mod GW --mod NSC 처럼 반복 가능
    parser.add_argument(
        "--mod", action="append", default=[], help="Limit to a mod folder. Can repeat."
    )
    # 특정 CSV 파일명/경로만 처리. 파일명 만 넣어도 auto_keys 하위에서 검색
    parser.add_argument(
        "--file", action="append", default=[], help="Limit to a CSV path or filename. Can repeat."
    )
    # 특정 로컬라이징 키만 처리. --key some_key --key other_key 처럼 반복 가능
    parser.add_argument(
        "--key", action="append", default=[], help="Limit to one localisation key. Can repeat."
    )
    # 작업량 제한 -----------------------------------------------------------
    # 번역 작업이 생긴 파일 N개만 처리하고 중단 (0 = 무제한)
    parser.add_argument(
        "--limit-files",
        type=int,
        default=0,
        help="Stop after N files with work. 0 means unlimited.",
    )
    # 번역/복사 합산 N행 이후 중단 (0 = 무제한)
    parser.add_argument(
        "--limit-rows",
        type=int,
        default=0,
        help="Stop after N translated/copied rows. 0 means unlimited.",
    )
    # 시작/종료 행 -----------------------------------------------------------
    # 이 행(CSV 줄 번호, 헤더=1)부터 처리. 중간에 중단 후 재개할 때 사용
    parser.add_argument(
        "--start-row",
        type=int,
        default=2,
        help="CSV line number to start at. Header is line 1. Default: 2.",
    )
    # 이 행까지만 처리 (포함). 'end'로 지정하면 파일 끝까지
    parser.add_argument(
        "--end-row",
        default="end",
        help="CSV line number to stop at, inclusive. Use 'end' to continue to the end.",
    )
    # 번역 대상 선택 --------------------------------------------------------
    # 기본은 빈 korean_value만 채운다. 이 옵션을 주면 기존 번역도 덮어쓴다
    parser.add_argument(
        "--rewrite-existing", action="store_true", help="Overwrite existing korean_value cells too."
    )
    # --rewrite-existing과 함께 사용: 의심스러운(미번역/영문그대로) 행만 재번역
    parser.add_argument(
        "--only-suspicious",
        action="store_true",
        help="With --rewrite-existing, only rewrite rows that look untranslated or token-broken.",
    )
    # dry-run / 샘플 모드 --------------------------------------------------
    # 실제 API 호출·파일 수정 없이 대상 행 수만 출력
    parser.add_argument(
        "--dry-run", action="store_true", help="Count work only; do not write files or call OpenAI."
    )
    parser.add_argument(
        "--dry-run-with-api",
        action="store_true",
        help="Call OpenAI but do not write files. For testing token masking/restoration.",
    )
    # 원본 CSV를 수정하지 않고 N행만 번역해 별도 CSV로 저장 (품질 확인용)
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=0,
        help="Translate N rows into a separate sample CSV only.",
    )
    parser.add_argument("--sample-output", default="", help="Sample CSV output path.")
    # 샘플 모드에서 기존 번역이 있는 행도 포함할지 여부
    parser.add_argument(
        "--sample-include-existing",
        action="store_true",
        help="Sample existing korean_value rows too.",
    )
    # 번역 대상이 없는 파일도 로그에 출력할지 여부
    parser.add_argument(
        "--verbose-skips", action="store_true", help="Print files with no translatable rows."
    )
    # 모델·번역 품질 옵션 --------------------------------------------------
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"OpenAI model. Default: {DEFAULT_MODEL}"
    )
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
    parser.add_argument(
        "--use-guidelines",
        action="store_true",
        help="Load maintenance/docs/translation_guidelines.md into the OpenAI prompt. 기본: 토큰 포함 행에만 자동 적용.",
    )
    parser.add_argument(
        "--no-glossary",
        action="store_true",
        help="용어집(term_glossary.csv)을 프롬프트에 포함하지 않는다.",
    )
    parser.add_argument(
        "--glossary-file",
        default=str(DEFAULT_GLOSSARY_FILE),
        help="용어집 CSV 경로. 기본: maintenance/term_glossary.csv",
    )
    parser.add_argument(
        "--extra-glossary",
        action="append",
        default=[],
        metavar="CSV",
        help="추가 용어집 CSV 경로. 반복 가능. 기본 용어집보다 우선 적용.",
    )
    # Stellaris 토큰을 마커로 치환하지 않고 그대로 API에 전송 (테스트용)
    parser.add_argument(
        "--no-protect-tokens",
        action="store_true",
        help="Send Stellaris tokens to OpenAI without temporary masking.",
    )
    # 토큰만으로 구성된 행을 API 없이 그대로 복사하는 최적화를 끌 때 사용
    parser.add_argument("--no-copy-token-only", action="store_true")
    # 하드 토큰이 달라도 번역 결과를 저장 (검수 후 수동 수정을 전제로 할 때)
    parser.add_argument(
        "--allow-token-mismatch",
        action="store_true",
        help="Write output even when hard tokens differ.",
    )
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
    # 기본 100,000은 Anthropic 무료 티어 기준 (안전한 하한).
    # OpenAI Tier 1: 200,000 / Tier 2: 2,000,000. 0이면 throttle 비활성화.
    parser.add_argument(
        "--tpm-limit",
        type=int,
        default=100000,
        help="TPM(분당 토큰) 한도. Default: 100000 (Anthropic 무료 티어 기준). 0이면 throttle 비활성화.",
    )
    return parser.parse_args()


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
    return sorted(
        Path(p) for p in glob.glob(str(auto_keys_dir / "**" / "*_key.csv"), recursive=True)
    )


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
        if has_source(eng.inner) and (
            not only_suspicious or is_suspicious_translation(eng.inner, kor.inner)
        ):
            count += 1
    return count


def write_rows_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    # .tmp 임시 파일에 쓰고 완료 후 rename — 중간에 프로세스가 죽어도 파일 손상 없음.
    # row의 english/korean_value는 CsvCell raw 값 (`"내용"` 형태).
    # csv_writer(QUOTE_MINIMAL)가 이를 파일에 `"""내용"""` 으로 올바르게 escape한다.
    # translate_value 단계에서 이미 정리됐으므로 저장 시 추가 변환 없이 그대로 쓴다.
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv_writer(handle, quoting=csv.QUOTE_MINIMAL)
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
        protect_tokens(eng_cell.inner) if translator.config.protect_tokens else (eng_cell.inner, {})
    )
    for attempt in range(attempts):
        raw_translation, last_system_prompt, last_user_prompt = translator.translate(
            key, request_text, protected, missing_tokens
        )
        restored = restore_protected_tokens(raw_translation, protected)
        cleaned_inner = normalize_csv_cell(
            strip_prompt_echo(strip_code_fence(restored).strip()), source=eng_cell.inner
        )
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
            f"{t}: 누락={v['missing']} 추가={v['extra']}" for t, v in delta.items()
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
            missing_tokens = missing_tokens + [
                f"(원문에 없는 토큰 추가 금지: {', '.join(extra_tokens)})"
            ]
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
        if only_suspicious and not (
            is_suspicious_translation(eng.inner, kor.inner) or kor.quote_noise
        ):
            result.skipped_existing += 1  # suspicious 아닌 기존 번역 skip (skipped_existing에 합산)
            continue
        if should_stop(total_changed_so_far + changed_this_file, limit_rows):
            break  # 한도 도달 — 이후 행 처리 불필요
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
                print(
                    f"  [단어집 대체] {key_name}: {console_text(eng.inner)} → {console_text(kor_direct)}"
                )
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

    def collect_one(
        row: dict[str, str], future: "Future[tuple[str|None,str|None,str,str,Exception|None]]"
    ) -> None:
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
            result.issues.append(
                {
                    "key": key,
                    "reason": "translation_failed",
                    "english_value": eng.inner,
                    "error": str(exc),
                }
            )
            print_block(
                f"  [오류] 번역 실패 — key={key}",
                원문=console_text(eng.inner),
                에러=console_text(exc),
            )
            _write_log(
                log_failure,
                {
                    "timestamp": ts,
                    "key": key,
                    "english_value": eng.inner,
                    "reason": "translation_error",
                    "error": str(exc),
                    "system_prompt": sys_prompt,
                    "user_prompt": usr_prompt,
                },
            )
            return
        if translated_raw is None:
            result.skipped_token_mismatch += 1
            rejected_inner = CsvCell.parse(rejected_raw or "").inner
            delta = token_delta(eng.inner, rejected_inner) if rejected_inner else {}
            result.issues.append(
                {
                    "key": key,
                    "reason": "hard_token_mismatch",
                    "english_value": eng.inner,
                    "rejected_value": rejected_raw or "",
                    "token_delta": delta,
                }
            )
            _write_log(
                log_failure,
                {
                    "timestamp": ts,
                    "key": key,
                    "english_value": eng.inner,
                    "reason": "hard_token_mismatch",
                    "rejected_value": rejected_raw or "",
                    "token_delta": delta,
                    "system_prompt": sys_prompt,
                    "user_prompt": usr_prompt,
                },
            )
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
                print_block(
                    f"  [번역 완료] {key}  ({done}/{total}, {pct:.1f}%)",
                    원문=console_text(eng.inner),
                    번역=console_text(kor_inner),
                )
            else:
                print_block(
                    f"  [번역 완료] {key}",
                    원문=console_text(eng.inner),
                    번역=console_text(kor_inner),
                )
            _write_log(
                log_success,
                {
                    "timestamp": ts,
                    "key": key,
                    "english_value": eng.inner,
                    "korean_value": kor_inner,
                    "system_prompt": sys_prompt,
                    "user_prompt": usr_prompt,
                },
            )
            if not save_at_end:
                do_save()

    # in_flight: deque[(row, future)], 최대 workers개
    in_flight: deque[
        tuple[dict[str, str], Future[tuple[str | None, str | None, str, str, Exception | None]]]
    ] = deque()

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
                            print(f"  [저장] {oldest_row.get('key', '')}")
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
        writer = csv_dict_writer(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: normalize_csv_cell(row.get(field, "") or "") for field in fieldnames}
            )


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
    rel_file = (
        str(filepath.relative_to(auto_keys_dir))
        if filepath.is_relative_to(auto_keys_dir)
        else str(filepath)
    )

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
        if only_suspicious and not (
            is_suspicious_translation(eng.inner, kor.inner) or kor.quote_noise
        ):
            result.skipped_existing += 1
            continue
        if sample_rows and len(candidates) >= sample_rows:
            continue
        result.candidates += 1
        candidates.append((line_number, key, eng, kor.inner))

    # ── 토큰 전용 행은 API 없이 즉시 처리 ────────────────────────────────
    token_results: dict[
        int, tuple[str, str, str]
    ] = {}  # line_number → (sample_inner, status, note)
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
        print(
            f"모드: sample dry-run (원본 CSV 수정 없음, 최대 {args.sample_rows}행 OpenAI 번역 후 별도 CSV 저장)"
        )

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
            translator = Translator(
                APIKeyManager(config.api_key_file), config, tpm_throttle=throttle
            )
        except (ValueError, TranslationFatalError) as exc:
            print(f"에러: {exc}")
            return 2

    files_processed = 0  # 번역 작업이 실제로 생긴 파일 수
    total_changed = 0  # 전체 변경(번역+복사) 행 수
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
    sample_output_path = (
        sample_path_from_arg(args.sample_output, report_dir) if sample_mode else None
    )
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
                include_existing=args.rewrite_existing
                or (sample_mode and args.sample_include_existing),
                only_suspicious=args.only_suspicious,
                start_row=args.start_row,
                end_row=end_row,
            )
            if preflight_candidates == 0 and not args.verbose_skips:
                continue

            set_current_task(filepath)
            rel = (
                filepath.relative_to(auto_keys_dir)
                if filepath.is_relative_to(auto_keys_dir)
                else filepath
            )
            file_idx = len(file_results) + 1
            total_files = len(csv_files)
            if progress_total:
                progress_done = sum(r.translated + r.copied_token_only for r in file_results)
                pct = progress_done / progress_total * 100
                print(
                    f"[{file_idx}/{total_files}] 처리 중: {rel}  ({progress_done}/{progress_total} 키, {pct:.1f}%)"
                )
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
                write_latest(
                    report_dir,
                    {
                        **_report_base,
                        "files_seen": len(csv_files),
                        "files_processed_with_work": files_processed,
                        "total_changed": total_changed,
                        "api_translated": translator.translated_count if translator else 0,
                        "api_requests": translator.request_count if translator else 0,
                        "interrupted": False,
                        "files": [r.__dict__ for r in file_results],
                    },
                )
            last_row_info = (
                f", last_processed_row={result.last_processed_row}"
                if result.last_processed_row
                else ""
            )
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
    if total_changed and not sample_mode:
        print("\n번역 결과의 토큰 무결성을 validate로 확인하세요:")
        print("  python tools/validate_auto_key_tokens.py")
    # 정상 종료: 0, Ctrl+C 중단: 130 (Unix 관례)
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
