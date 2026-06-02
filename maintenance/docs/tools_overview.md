# 통합한글모드 도구 설명

최종 갱신: 2026-06-03

`tools/` 아래 각 스크립트의 역할, 주요 옵션, 출력 파일을 정리한다.
작업 순서와 명령어 조합은 `workflow.md`를 참조한다.

역할: **도구 레퍼런스**. 각 스크립트가 무엇을 입력받고 무엇을 출력하는지, 그리고 주요
옵션이 무엇인지 설명한다. 절차형 레시피는 `workflow.md`, 사용자용 빠른 시작은
`manual.md`, 최신 세션 상태는 `../../../HANDOFF.md`에 둔다.

넣지 말 것:

- 번역 문체·용어 규칙 (`translation_guidelines.md`)
- 세션별 작업 로그 (`../../../HANDOFF.md`)
- 프로젝트 구조 설명 (`COLLABORATION.md`)

---

## 핵심 작업 단위

```text
maintenance/translation_keys/<mod_slug>__<workshop_id>/**/*_key.csv
```

```text
key,english_value,korean_value
```

`key`와 `english_value`는 수정하지 않는다. 번역은 `korean_value`에만 반영한다.

---

## translate_keys.py

OpenAI API로 `korean_value`를 채우거나 재번역한다.

주요 동작:

- 토큰을 마커로 치환(`__ICON_xxx__`, `__DOLLAR_xxx__`, `__Bn__`)한 뒤 번역 후 복원
- 기본적으로 빈 `korean_value`만 번역
- 하드 토큰 불일치 시 재시도, 재시도 후에도 불일치면 건너뛰고 리포트에 기록
- 번역 후 `auto_patch_tokens()`로 일부 패턴 자동 보정

시스템 프롬프트 선택:

| 조건 | 사용 프롬프트 |
|---|---|
| 토큰 없는 텍스트 | `SYSTEM_PROMPT` (기본, ~70토큰) |
| 토큰 포함 텍스트 | `SYSTEM_PROMPT_WITH_TOKENS` (~182토큰) |
| `--use-guidelines` 플래그 | `system_prompt_full` (토큰 규칙 + 가이드라인) |

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--mod` | 모드 폴더명으로 대상 지정 |
| `--file` | 특정 CSV 파일 경로 |
| `--key` | 특정 키만 처리 (반복 가능) |
| `--start-row N` | N번 행부터 (헤더=1). 중단 후 재개 시 사용 |
| `--end-row N` | N번 행까지 (`end` 입력 시 끝까지) |
| `--workers N` | 병렬 요청 수 (기본 1, 권장 3) |
| `--tpm-limit N` | 분당 토큰 한도 (기본 200,000) |
| `--rewrite-existing` | 기존 번역도 덮어쓰기 |
| `--only-suspicious` | 의심 행만 재번역 (빈 값·identical·토큰 불일치·한글 없음·너무 짧음) |
| `--from-report` | `review_latest.csv`의 `retranslate=1` 행만 처리. `--rewrite-existing` 자동 적용 |
| `--from-worklist` | `token_repair_worklist_*.csv` 기반 재번역 |
| `--dry-run` | 대상 수만 출력, 파일 수정 없음 |
| `--sample-rows N` | N행만 번역해 별도 CSV 저장 (원본 무수정) |
| `--allow-token-mismatch` | 토큰 불일치여도 강제 저장 |
| `--request-delay N` | 요청 간 대기 시간(초) |

출력:

```text
maintenance/reports/ai_translation/translate_log_success_<timestamp>.jsonl
maintenance/reports/ai_translation/translate_log_failure_<timestamp>.jsonl
maintenance/reports/ai_translation/translate_keys_report_<timestamp>.json
```

---

## import_korean_references.py

MKC, 한국어 보완 모드, MKC Addon, Giga 한국어 패치 등에서 같은 키의 번역을 찾아 `korean_value`에 복사한다.
이 도구는 기본 파이프라인의 필수 단계가 아니다. 참고 번역 소스를 새로 반영하고 싶을 때만 수동 실행하거나 `run_pipeline.py --import-korean-references`로 켠다.

참고 소스 우선순위 및 Workshop ID 목록: `translation_guidelines.md` → "한국어 참고 소스 우선순위"

기본 동작:

- 빈 `korean_value`만 채운다. 기존 값은 보존.
- 여러 소스에 같은 키가 있으면 우선순위 높은 값 사용.
- 토큰 차이는 자동 수정하지 않고 리포트의 `issue_types`에 기록.

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--mod` | 특정 모드 폴더만 처리 |
| `--file` | 특정 CSV 파일만 처리 |
| `--overwrite-existing` | 기존 `korean_value`도 덮어씀 |
| `--dry-run` | 변경 예정 수만 출력, 파일 수정 없음 |
| `--limit-rows N` | 변경 행 수 상한 |
| `--reference-mod-id` | 참조할 모드 ID 직접 지정 (반복 가능) |
| `--reference-path` | 참조할 로컬 한글 모드 폴더 경로 직접 지정 (반복 가능) |
| `--reference-source` | Workshop ID 또는 폴더 경로를 우선순위 순서대로 지정 (반복 가능, 기본 목록 대체) |
| `--reference-csv-dir` | `extract_korean_reference_keys.py`로 뽑은 참고 CSV 디렉터리 지정 (반복 가능) |
| `--workshop-root` | Steam 워크샵 경로 지정 |

예:

```powershell
# 워크샵 ID로 지정
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-source 2506141839

# 로컬 addon 폴더 경로로 지정
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-source "..\addon_Mod_Korean_Collection_모드_한국어_모음_kr"

# 여러 소스를 직접 우선순위대로 지정
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-source 2506141839 --reference-source "..\addon_Korean_Patch_Gigastructural_Engineering_and_More_kr"

# 미리 추출한 참고 CSV에서 korean_value만 삽입
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-csv-dir maintenance\reference_keys\<source_slug>
```

삽입 시 대상 CSV에서 바뀌는 열은 `korean_value`뿐이다. `key`와 `english_value`는 수정하지 않는다.

출력:

```text
maintenance/reports/reference_import/korean_reference_import_report_<timestamp>.json
maintenance/reports/reference_import/korean_reference_import_changes_<timestamp>.csv
maintenance/reports/reference_import/korean_reference_import_changes_latest.csv
```

---

## extract_korean_reference_keys.py

한글 참고 모드의 `localisation/**/*_l_korean.yml`을 읽어 폴더 구조를 유지한 reference CSV로 추출한다.
영어 원본 추출기가 아니라 한글 재사용 소스 준비용 도구다.

출력 CSV 컬럼:

```text
key,english_value,korean_value
```

`english_value`는 비워 두고, `korean_value`에 한글 문장만 저장한다.

예:

```powershell
# 워크샵 ID에서 추출
python tools/extract_korean_reference_keys.py --reference-source 2506141839

# 로컬 addon 폴더에서 추출
python tools/extract_korean_reference_keys.py --reference-source "..\addon_Mod_Korean_Collection_모드_한국어_모음_kr"

# 추출 후 대상 translation_keys에 한글 문장열만 반영
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-csv-dir maintenance\reference_keys\<source_slug> --dry-run
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-csv-dir maintenance\reference_keys\<source_slug>
```

---

## run_pipeline.py 참고 번역 옵션

`run_pipeline.py`는 기본적으로 원본 영어 키 추출, 번역 출력 dry-run/apply, 검증, 충돌 목록 준비만 수행한다.
한국어 참고 모드 스캔은 매번 실행하지 않는다.
AI 자동번역까지 포함하려면 `--translate`를 명시한다.

| 옵션 | 설명 |
|---|---|
| `--mod` | 생성된 모드 slug 또는 Workshop ID로 대상 제한 |
| `--import-korean-references` | 키 추출 뒤 `import_korean_references.py`를 실행 |
| `--reference-dry-run` | 참고 번역 매칭만 보고 CSV는 수정하지 않음 |
| `--dry-run` | CSV/YML 쓰기 방지: 키 추출은 skip, 참고 임포트/AI 번역/export는 dry-run으로 강제 |
| `--translate` | 참고 번역 뒤 `translate_keys.py --workers 1 --tpm-limit 2000000` 실행, 이후 `validate_auto_key_tokens.py` 자동 실행 |

`--translate`는 `tools/api_key.txt` 파일 또는 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 환경 변수 중 하나가 있을 때 실행된다. 모두 없으면 해당 모드의 `translate_keys`와 `validate_auto_key_tokens` 단계는 skip 처리되고 경고를 출력한다.

예:

```powershell
python tools/run_pipeline.py --mode report --import-korean-references --reference-dry-run
python tools/run_pipeline.py --mode auto --import-korean-references
python tools/run_pipeline.py --mode auto --mod <mod_slug> --translate
```

보통은 `run.ps1` 런처를 사용한다. 런처는 Workshop ID와 `<mod_slug>__<workshop_id>`를 모두 받는다.

```powershell
.\run.ps1 pipeline <workshop_id> --mode report
.\run.ps1 pipeline <workshop_id> --mode auto --translate
.\run.ps1 status <workshop_id>
.\run.ps1 work <workshop_id>
.\run.ps1 validate <workshop_id>
.\run.ps1 review <workshop_id> --mark-errors
.\run.ps1 translate <workshop_id> --dry-run
.\run.ps1 export <workshop_id> --dry-run
```

공통 기본값은 `maintenance/tooling.ini`에서 관리한다. `STELLARIS_TRANSLATION_KEYS_DIR`, `STELLARIS_WORKSHOP_ROOT`, `STELLARIS_TRANSLATION_WORKERS`, `STELLARIS_TRANSLATION_TPM_LIMIT` 환경변수로 일시 override할 수 있다.

---

## review_report.py

`translation_keys` CSV 전체 또는 특정 모드를 스캔해 의심 행을 `review_latest.csv`로 출력한다.

severity 분류:

| severity | reason | 의미 | 진행률 영향 |
|---|---|---|---|
| error | `empty` | 번역값 없음 | 감소 |
| error | `token_broken` | 토큰 불일치 | 감소 |
| error | `no_hangul` | 한글 없음 (번역 불필요 행 제외) | 감소 |
| error | `quote_noise` | 과도한 따옴표 중첩 | 감소 |
| warning | `identical` | 영·한 값 동일 (번역 불필요 행 자동 제외) | 없음 |
| warning | `too_short` | 번역이 너무 짧음 | 없음 |

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--mod` | 특정 모드만 검수 |
| `--file` | 특정 CSV 파일만 검수 |
| `--reason` | 특정 reason만 포함 |
| `--mark-errors` | `severity=error` 행에만 `retranslate=1` 표시 (자동 파이프라인 기본) |
| `--mark-retranslate` | 전체 행에 `retranslate=1` 표시 (전수 강제 재번역 시에만 사용) |

출력:

```text
maintenance/reports/review/review_latest.csv  (기존 파일은 날짜 파일로 자동 백업)
```

---

## validate_auto_key_tokens.py

`translation_keys` CSV의 토큰·줄바꿈·따옴표 구조를 검수한다.
토큰 추출은 `token_parser.py`의 범위 인식 파서를 사용한다. 이미 파싱된 `$...$`,
`£...£`, `[...]` 내부는 다시 검사하지 않아 `£menu_1£EHOF`처럼 토큰 뒤에 텍스트가
붙는 정상 케이스와 `['concept_x', '$energy$']`처럼 토큰 내부에 토큰처럼 보이는
문자가 있는 케이스를 구분한다.

검수 항목: `$...$`, `£...£`, 닫힘 없는 아이콘(`£word `), `[...]`, `§X...§!`,
`\n`, CSV 따옴표 구조

닫힘 없는 아이콘은 비교 시 의도된 아이콘으로 정규화한다. 따라서 영어 원문이
`£energy `처럼 깨져 있고 한국어가 `£energy£`로 복원한 행은 critical 오탐으로 보지
않는다. 반대로 `korean_value`에 `£energy `가 남아 있으면 `unclosed_icon` critical로
보고한다.

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--mod` | 특정 모드만 검수 |

출력:

```text
maintenance/reports/token_validation/token_shape_issues_<timestamp>.csv
maintenance/reports/token_validation/token_repair_worklist_<timestamp>.csv
maintenance/reports/token_validation/token_style_review_<timestamp>.csv
maintenance/reports/token_validation/quote_issues_<timestamp>.csv
```

`token_repair_worklist_*.csv`는 `translate_keys.py --from-worklist`에 바로 사용한다.

---

## fix_quote_issues.py

CSV 따옴표 누락·불균형·과도한 중첩을 자동 보정한다.

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--report CSV` | `quote_issues_*.csv` 기반 보정 |
| `--scan` | 전수 스캔 후 보정 |
| `--mod` | 특정 모드만 처리 |
| `--dry-run` | 변경 예정 수만 출력, 파일 수정 없음 |
| `--only-unclosed-icons` | `korean_value`의 닫힘 없는 아이콘만 보정하고 따옴표·줄바꿈 보정은 건너뜀 |

변경 전 백업: `maintenance/backups/fix_quote_issues/`

---

## test_token_parser.py

사용자 편집 가능한 검출 케이스 파일을 읽어 범위 인식 토큰 파서와 validate 분류가
깨진 토큰 케이스를 기대대로 잡는지 dry-run으로 확인한다.

케이스 파일:

```text
maintenance/fixtures/token_detection_cases.jsonl
```

각 줄은 독립 JSON 객체다. `text` + `expected_tokens`/`expected_fixed`로 파서·보정
결과를 확인하거나, `english_value` + `korean_value` + `expected_severity` +
`expected_issue_types`로 validate 분류를 확인한다. `#`로 시작하는 줄은 주석으로
무시된다.

```powershell
python tools/test_token_parser.py
python tools/test_token_parser.py --show-passed
python tools/test_token_parser.py --id korean_unclosed_is_critical
```

---

## extract_localisation_keys.py

원본 모드 `localisation/english`에서 키를 추출해 `translation_keys` CSV를 만든다.

주요 동작:

- 기존 CSV가 있으면 `korean_value`를 보존하고 `english_value`만 갱신
- 신규 키는 뒤에 추가, 사라진 키는 삭제하지 않고 `stale_keys` 리포트에 기록
- `replace` 원본은 `translation_keys/<mod>/replace/*_key.csv`로 추출
- `.\run.ps1 extract <workshop_id>`는 `descriptor.mod`의 이름으로 `maintenance\translation_keys\<slug>__<workshop_id>` 경로를 자동 지정

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--sync-source` | 원본 기준으로 CSV 완전 동기화 |
| `--keep-existing-english` | 기존 `english_value`도 유지 |

---

## export_localisation.py

`translation_keys` CSV를 기준으로 `localisation/korean` YML을 생성하거나 갱신한다.

```powershell
.\run.ps1 export <workshop_id> --dry-run
.\run.ps1 export <workshop_id>
```

옵션:

| 옵션 | 설명 |
|---|---|
| `--dry-run` | 리포트만 생성, 파일 수정 없음 |
| `--workshop-root` | Steam 워크샵 경로 지정 |

---

## validate_translation_outputs.py

생성된 `localisation/korean` YML과 CSV 기준값이 일치하는지 검증한다.

```powershell
python tools/validate_translation_outputs.py <workshop_id> maintenance\translation_keys\<mod_slug>__<workshop_id>
```

---

## diagnose_source_tokens.py

원본 `english_value`의 토큰 이상 패턴을 진단한다.

```powershell
python tools/diagnose_source_tokens.py              # icon_unclosed만 출력 (기본)
python tools/diagnose_source_tokens.py --dollar     # 달러 토큰 unusual 추가
python tools/diagnose_source_tokens.py --color      # 위키 미기재 §코드 추가
```

---

## patch_english_tokens.py

원본 CSV의 토큰 오타를 자동 보정한다 (닫는 `£` 누락 등).

```powershell
python tools/patch_english_tokens.py --dry-run
python tools/patch_english_tokens.py
```

---

## check_utf8_bom.py

CSV/YML/JSON/MD 파일의 UTF-8 BOM 상태를 확인하거나 보정한다.

```powershell
python tools/check_utf8_bom.py          # 상태 확인만
python tools/check_utf8_bom.py --fix    # BOM 보정
```

---

## generate_translation_progress_tree.py

`translation_keys` CSV를 스캔해 모드별 번역 진행률을 `translation_progress_tree.md`에 생성한다.

집계 기준:

- `done`: 번역이 있고 error 없는 행
- `suspicious`: error 판정 행 (empty / token_broken / no_hangul / quote_noise)
- warning (identical / too_short)은 진행률에 영향 없음

```powershell
python tools/generate_translation_progress_tree.py
```

---

## extract_official_terms.py

공식 Stellaris 한국어 번역에서 게임 용어 쌍을 추출해 `term_glossary.csv`를 생성한다.

```powershell
python tools/extract_official_terms.py --overwrite
python tools/extract_official_terms.py --overwrite --max-len 30
```

---

## test_token_masking.py

API 호출 없이 전체 모드 토큰 마스킹 드라이런 검증을 실행한다.

```powershell
python tools/test_token_masking.py
python tools/test_token_masking.py --mod <mod_slug>__<workshop_id>
```
