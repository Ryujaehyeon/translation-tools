"""Claude/OpenAI 번역 클라이언트 인프라.

API 키 로드·provider 감지(APIKeyManager), 분당 토큰 스로틀(TPMThrottle), 번역 요청·
재시도(Translator)와 관련 설정·프롬프트 상수를 담는다. 순수 텍스트 규칙은
translation_rules에 의존한다(역방향 의존 없음).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from translation_rules import (
    TOKEN_RE,
    console_text,
    find_matching_terms,
    load_glossary,
    strip_code_fence,
)

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
DEFAULT_API_KEY_FILE = SCRIPT_DIR / "api_key.txt"
DEFAULT_GUIDELINES_FILE = PACK_ROOT / "maintenance" / "docs" / "translation_guidelines.md"
DEFAULT_GLOSSARY_FILE = PACK_ROOT / "maintenance" / "term_glossary.csv"


# 기본 모델: gpt-4o-mini (저렴한 편이며 번역 품질 검증된 모델)
# 2026-05 기준 가격 (input / output, USD per 1M tokens)
#
# ── 저렴한 순 ──────────────────────────────────────────────────
# gpt-4.1-nano               $0.10 / $0.40   (OpenAI 최저가)
# gpt-4o-mini                $0.15 / $0.60   ← 기본값
# gpt-4.1-mini               $0.40 / $1.60
#
# ── 성능 좋은 순 ───────────────────────────────────────────────
# claude-opus-4-8             $5.00 / $25.00  (Anthropic 최상위)
# claude-sonnet-4-6           $3.00 / $15.00  (성능·비용 균형 최적)
# claude-haiku-4-5-20251001   $1.00 / $5.00   (Claude 중저가)
DEFAULT_MODEL = "gpt-4o-mini"
# 온도: 0.0=완전 결정론, 1.0=창의적. 번역은 0.1~0.3이 적합 (일관성 우선)
DEFAULT_TEMPERATURE = 0.2
# API 실패 시 최대 재시도 횟수 (지수 대기 적용)
DEFAULT_MAX_RETRIES = 4


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


# 복구 불가능한 오류 (잘못된 모델명, API 키 없음 등) — 발생 시 즉시 작업 중단
class TranslationFatalError(Exception):
    """Raised when the current run cannot continue safely."""


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
        # 2순위: tools/api_key.txt
        if self.api_key_file.is_file():
            for line in self.api_key_file.read_text(encoding="utf-8").splitlines():
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
            print(
                f"  [TPM 대기] 사용량 {used:,}/{self.tpm_limit:,} 토큰, {wait:.1f}초 대기...",
                flush=True,
            )
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
        self.request_count = 0  # 실제 OpenAI API 요청 횟수 (재시도 포함)
        # 시스템 프롬프트: 3단계
        #   system_prompt           — 토큰 없는 단순 텍스트용 (기본, 짧음)
        #   system_prompt_with_tokens — 토큰 포함 텍스트용 (토큰 규칙 추가)
        #   system_prompt_full      — 토큰 포함 + 가이드라인 (use_guidelines 시)
        guideline_prompt = (
            load_guidelines_prompt(self.config.guidelines_file)
            if self.config.use_guidelines
            else ""
        )
        self.system_prompt = SYSTEM_PROMPT
        self.system_prompt_with_tokens = SYSTEM_PROMPT_WITH_TOKENS
        self.system_prompt_full = (
            f"{SYSTEM_PROMPT_WITH_TOKENS}\n\n{guideline_prompt}"
            if guideline_prompt
            else SYSTEM_PROMPT_WITH_TOKENS
        )
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
                raise TranslationFatalError(
                    "anthropic 패키지가 없습니다. `python -m pip install anthropic`를 실행하세요."
                ) from exc
            self.client = _anthropic.Anthropic(api_key=self.key_manager.api_key)
        else:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as exc:
                raise TranslationFatalError(
                    "openai 패키지가 없습니다. `python -m pip install openai`를 실행하세요."
                ) from exc
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

    def translate(
        self,
        key: str,
        text: str,
        protected: dict[str, str] | None = None,
        missing_tokens: list[str] | None = None,
    ) -> tuple[str, str, str]:
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
                    total_tokens = (response.usage.input_tokens or 0) + (
                        response.usage.output_tokens or 0
                    )
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
                print(
                    f"  [경고] API 번역 실패 (key={key}, 시도={attempt + 1}/{max(1, self.config.max_retries)}): {console_text(message)}"
                )
                # 복구 불가 오류: 모델명 오류, 접근 권한 없음 등
                if (
                    "model_not_found" in lower
                    or "does not exist" in lower
                    or "invalid_request_error" in lower
                    or "not_found_error" in lower
                ):
                    raise TranslationFatalError(
                        f"모델을 찾을 수 없거나 접근 권한이 없습니다: {self.config.model}"
                    ) from exc
                if any(
                    token in lower
                    for token in ("rate limit", "429", "temporarily unavailable", "timeout")
                ):
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
