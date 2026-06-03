# 프로젝트 고유 규약

이 저장소(Stellaris 한국어 번역 도구)에만 해당하는 규약입니다. 언어·포맷 같은
일반 규칙은 [PYTHON_STYLE_GUIDE.md](PYTHON_STYLE_GUIDE.md)를 따르고, 여기서는 그
규칙이 이 프로젝트에서 **구체적으로 어떻게 적용되는지**만 다룹니다.

기준 구현체는 [`tools/run_pipeline.py`](../tools/run_pipeline.py)입니다. 새 도구를
만들거나 기존 도구를 손볼 때 이 파일의 구조를 따르세요.

---

## 인코딩

Stellaris/Paradox 텍스트 파일은 BOM이 섞여 있어 인코딩을 항상 명시합니다.

- **읽기**: BOM·깨진 바이트를 견디게 `utf-8-sig` + 필요 시 `errors="replace"`.

  ```python
  def read_text(path: Path) -> str:
      """Steam/Paradox가 쓰는 텍스트를 BOM·이상 바이트를 견디며 읽는다."""
      return path.read_text(encoding="utf-8-sig", errors="replace")
  ```

- **쓰기**: 리포트·캐시 등 도구 산출물은 `utf-8-sig`. 단 **게임이 직접 읽는
  `descriptor.mod`는 BOM 없는 `utf-8`**로 씁니다
  (`tool_config.ensure_standalone_mod` 참고).

## CSV 줄바꿈·인용 스타일

`translation_keys` CSV는 **LF 줄바꿈 + `QUOTE_MINIMAL`**로 통일합니다. 둘 다 표준에서
벗어나면 보정하지 않은 행까지 전부 바뀐 것처럼 보여 diff가 오염됩니다.

- **줄바꿈**: Python `csv` 모듈은 기본으로 `\r\n`(CRLF)을 씁니다. LF 원본을 Windows에서
  다시 쓰면 모든 줄이 CRLF로 바뀌어 실제 내용 변경이 EOL 노이즈에 묻힙니다.
- **인용**: 원본은 `QUOTE_MINIMAL`(필요한 셀만 인용)입니다. `QUOTE_ALL`로 쓰면 `key`
  컬럼까지 따옴표가 붙어 파일 전체가 변경됩니다.
- CSV를 쓸 때는 반드시 `tool_config`의 `open_csv_write` + `csv_writer` /
  `csv_dict_writer` 헬퍼를 씁니다. 이 헬퍼가 `lineterminator="\n"`을 강제합니다.
  `quoting`은 기본값(`QUOTE_MINIMAL`)을 그대로 두고 `QUOTE_ALL`은 쓰지 않습니다.
- 줄 끝 노이즈가 이미 섞인 CSV는 헬퍼로 다시 한 번 써서 정규화합니다.

## 보존 대상 토큰

번역 텍스트에는 게임이 해석하는 토큰이 들어 있습니다. 텍스트를 가공하는 코드는
이 토큰들을 **절대 깨뜨리면 안 됩니다.**

- `£icon£`, `$variable$`, `[Root.GetName]` — 변수·아이콘·스코프 참조
- `§Y` … `§!` — 색상 코드
- `\n` — 줄바꿈

상세 규칙과 마스킹 방식은 [translation_guidelines.md](translation_guidelines.md)를
참고하세요. (PYTHON_STYLE_GUIDE.md 9절 "데이터 의미 보존"의 프로젝트 적용분.)

## 공통 유틸 (tool_config)

여러 도구에 흩어지기 쉬운 trivial 유틸은 직접 정의하지 말고 `tool_config`를 거칩니다.
(예전엔 `read_text`·`resolve_pack_path`·`descriptor_name`이 각각 7곳·5곳·3곳에
복붙돼 있어, 인코딩·base 경로가 미묘하게 달라지는 문제가 있었습니다.)

- `resolve_pack_path(raw)` — 상대 경로는 팩 루트 기준, 절대 경로는 그대로 반환.
- `workshop_root()` / `translation_keys_root()` — 환경 변수 → `tooling.ini` →
  기본값 순으로 해석. 경로를 새로 읽어야 하면 이 함수들을 재사용하세요.
- `read_text(path)` — Steam/Paradox 텍스트를 BOM·이상 바이트를 견디며 읽습니다
  (`utf-8-sig` + `errors="replace"`).
- `descriptor_name(mod_root)` — `descriptor.mod`의 `name="..."`를 반환(없으면 폴더명).
- `open_csv_write(path)` + `csv_writer` / `csv_dict_writer` — CSV 쓰기 전용
  (아래 "CSV 줄바꿈·인용 스타일" 절 참고).

## 자식 프로세스 오케스트레이션

`run_pipeline.py`는 직접 파일을 파싱하지 않고 단일 목적 도구들을 순서대로
**자식 프로세스로** 실행합니다. 새 단계를 추가할 때:

- 인터프리터는 `sys.executable`로 호출합니다(`"python"` 하드코딩 금지).
- 한 단계는 `command_step(name, command)`로 감싸 로그·리포트에서 추적 가능한
  이름을 붙입니다. 건너뛸 단계는 `skip_step(name, reason)`으로 표현합니다.
- 자식 실행은 `run_tool(command)` 한 곳을 거쳐 `returncode`/`stdout`/`stderr`를
  구조화해 수집합니다.
- 병렬 처리는 스레드(`ThreadPoolExecutor`)로 합니다. 무거운 일은 자식 프로세스에서
  일어나므로 워커 함수(`process_mod`/`plan_mod`)는 공유 상태를 변경하지 않습니다.

## 안전 기본값 (쓰기는 옵트인)

- 플래그 없이 실행하면 리포트·CSV만 만들고 로컬라이제이션 파일은 건드리지 않습니다.
  실제 쓰기는 `--apply-translations` 같은 명시적 옵션으로만 활성화합니다.
- 파일을 쓰는 옵션의 `help=`에는 기본값이 dry-run인지 write인지 명시합니다.

## 캐시 무효화

`run_pipeline.py`의 `CACHE_VERSION`은 캐시 포맷이 바뀌면 올려야 합니다. 다음과 같은
변경 시 기존 캐시가 잘못된 skip 판단을 낼 수 있으므로 버전을 올립니다.

- mod state JSON 구조 변경
- slug 생성 방식 변경
- extraction 결과 포맷 변경
