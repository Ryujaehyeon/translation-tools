# 협업 참고 문서 — Stellaris 통합 한국어 번역 팩

> AI 또는 신규 협업자가 작업 맥락을 바로 파악할 수 있도록 작성된 문서입니다.
> 최종 갱신: 2026-05-31 (9차)

---

## 0. 작업 시작 전 필독 파일

새 세션을 시작하거나 작업 맥락이 없을 때 아래 순서로 읽는다.

| 순서 | 파일 | 목적 |
| --- | --- | --- |
| 1 | `translation-tools/maintenance/COLLABORATION.md` | 이 파일 — 전체 맥락 파악 |
| 2 | `translation-tools/maintenance/translation_guidelines.md` | 번역 규칙 (토큰·문체·용어) |
| 3 | `translation-tools/maintenance/workflow.md` | 작업 단계별 명령어 |
| 4 | `translation-tools/maintenance/tools_overview.md` | 도구별 옵션 레퍼런스 |
| 5 | `translation-tools/maintenance/translation_progress_tree.md` | 현재 번역 진행 상태 |

**주요 규칙 요약 (숙지 필수):**

- 번역 대상은 **한국어 파일만** (`l_korean.yml`, `*_key.csv`의 `korean_value` 열)
- 토큰(`$variable$`, `£icon£`, `§X...§!`) 보존 필수 — 절대 번역하거나 제거하지 않는다
- 작업 전·후 이 파일(COLLABORATION.md)의 `9. 작업 이력` 갱신
- 도구 실행은 `translation-tools/` 디렉토리에서 `.\run.ps1 <액션>` 으로

---

## 1. 프로젝트 목적

Stellaris 모드들의 영문 로컬라이징 파일을 한국어로 번역하는 통합 팩을 구축한다.
수십 개 모드 · 수십만 행을 대상으로 **참조 번역 임포트 → AI 자동 번역 → 수동 검수** 파이프라인으로 작업한다.

---

## 2. 폴더 구조

```text
mod/
├── translation-tools/              ← 자동번역 도구 전체 (2026-05-27 분리)
│   ├── run.ps1                     ← 단일 진입점 런처 (모든 도구 실행)
│   ├── tools/                      ← Python 스크립트
│   │   ├── translate_keys.py
│   │   ├── import_korean_references.py
│   │   ├── review_report.py
│   │   ├── validate_auto_key_tokens.py
│   │   ├── fix_quote_issues.py
│   │   ├── export_localisation.py
│   │   ├── extract_localisation_keys.py
│   │   ├── diagnose_source_tokens.py
│   │   ├── patch_english_tokens.py
│   │   └── generate_translation_progress_tree.py
│   └── maintenance/
│       ├── translation_keys/       ← 번역 작업 CSV (모드별 폴더)
│       │   └── <mod_slug>__<id>/
│       │       ├── *_key.csv       ← key, english_value, korean_value 3열
│       │       └── replace/*_key.csv ← localisation/replace 대응 CSV
│       ├── term_glossary.csv       ← 공식 번역 추출 용어집 (~3,632개)
│       ├── reports/
│       │   ├── review/             ← review_latest.csv 및 날짜별 백업
│       │   ├── ai_translation/     ← AI 번역 로그 (JSON/JSONL)
│       │   ├── token_validation/   ← 토큰 검증 리포트
│       │   └── reference_import/   ← 참조 번역 임포트 리포트
│       ├── backups/                ← 도구 실행 전 자동 백업
│       ├── COLLABORATION.md        ← 이 파일
│       ├── workflow.md             ← 작업 순서 및 명령어
│       ├── translation_guidelines.md ← 번역 규칙 (토큰·문체·용어)
│       ├── tools_overview.md       ← 도구별 역할·옵션 레퍼런스
│       └── translation_progress_tree.md ← 모드별 번역 진행률
└── integrated_korean_translation_pack/
    └── localisation/korean/        ← 실제 번역 YML 파일 (export 결과물)
```

---

## 3. 도구 실행 방법

모든 도구는 `translation-tools/run.ps1` 런처로 실행한다. `translation-tools/` 디렉토리에서:

```powershell
# 번역
.\run.ps1 translate --mod <mod_slug> --workers 3
.\run.ps1 translate --from-report --workers 3

# 검수
.\run.ps1 review --mod <mod_slug> --mark-errors --fix-quotes
.\run.ps1 validate --mod <mod_slug>

# 전체 체크 (validate + review + progress)
.\run.ps1 full-check

# 진행률 트리 갱신
.\run.ps1 progress

# YML export (워크샵 ID → localisation/korean/)
.\run.ps1 export <workshop_id>

# 키 추출 (워크샵 원본 → CSV, translation_keys 경로 자동 생성)
.\run.ps1 extract <workshop_id>

# 참고 번역 임포트
.\run.ps1 import-ref --mod <mod_slug> --source <id_or_path>

# 파이프라인 (report 모드: 현황 파악 / auto 모드: 자동 번역)
.\run.ps1 pipeline --mode report
.\run.ps1 pipeline --mode auto --mod <mod_slug>
```

상세 옵션: `tools_overview.md`

---

## 4. CSV 형식

```csv
key,english_value,korean_value
origin_example,"""This is a §Hbold§! text with $planet$ token.""","""이것은 $planet$ 토큰이 있는 §H굵은§! 텍스트입니다."""
```

- `key`, `english_value` — 수정 금지
- `korean_value` — 번역 결과만 기록
- 인코딩: UTF-8 with BOM
- `english_value`가 따옴표로 감싸여 있으면 `korean_value`도 반드시 같은 형태로 감싼다

번역 규칙 상세: `translation_guidelines.md`

---

## 5. 현재 번역 상태 (2026-05-25 기준)

| 항목 | 수치 |
|---|---|
| 전체 CSV | 361개 |
| 번역 완료 행 | 101,569행 |
| 전체 번역률 | 100.0% |
| error 행 (진행률 감소 기준) | 1건 (message_dontsub_desc232 — 방치 확정) |
| critical 토큰 불일치 | 0건 |
| export 완료 | 46개 모드 전체 (2026-05-25) |

진행률 상세: `translation_progress_tree.md`

---

## 6. 알려진 문제 및 처리 방식

### 6-1. AI 토큰 누락

`translate_keys.py`가 토큰을 마커로 치환(`__ICON_xxx__`, `__DOLLAR_xxx__`, `__Bn__`)한 뒤 번역을 요청하고 복원한다. 프롬프트에 "반드시 포함해야 할 마커 목록"도 명시하여 이중 보호.

### 6-2. 토큰 불일치 잔존 행

재시도 후에도 불일치가 남으면 `validate_auto_key_tokens.py`로 `token_repair_worklist` 생성 → `--from-worklist`로 재번역. 그래도 안 되면 `--allow-token-mismatch` 강제 저장 또는 CSV 직접 수정.

### 6-3. AI 토큰 변형 자동 보정 대상

| 패턴 | 자동 보정 방식 |
|---|---|
| EN에 없는 `§X...§!` 쌍 추가 | 쌍 단위 제거, 내부 텍스트 보존 |
| `$TABBED_NEW_LINE$` → `\n` | extra `\n` == missing `$TABBED_NEW_LINE$` 수일 때 복원 |
| EN에 없는 `£word£` 추가 | 태그 제거, 내부 텍스트 보존 |

### 6-4. 원본 모드 토큰 오타

`£unity`처럼 닫는 `£` 누락 시 `diagnose_source_tokens.py`로 진단 후 `patch_english_tokens.py`로 보정.

### 6-5. `message_dontsub_desc232` token_broken 오탐 (방치)

원본 모드가 의도적으로 비정상 값(`§Y9.99$§!`)을 사용하는 메타 유머 모드. 번역은 정상이므로 방치. `tooling_known_issues.md` #7 참조.

### 6-6. 백그라운드 실행 시 exit 130

Claude Code 세션에서 백그라운드 실행 시 약 10분 후 강제 종료. AI 번역은 반드시 터미널에서 직접 실행.

### 6-7. review warning은 자동 재번역 대상 아님

`severity=warning` (identical, too_short)은 참고 검수용. 진행률 트리에도 영향 없음.
자동 재번역은 `severity=error` 행에만 `--mark-errors` 흐름을 사용한다.

### 6-8. `​`(zero-width space)가 한국어 폰트에서 `▣`로 렌더링

Gigastructural Engineering의 `gc_kilo` 등 색상 마커 키에 `​`가 포함되어 있었음. 영문 폰트에서는 투명하지만 한국어 폰트에서 대체 문자 박스(`▣`)로 표시됨. `giga_l_korean.yml` 내 7개 키에서 제거 완료. 상세: `translation_failure_cases.md` #13.

### 6-9. 프롬프트 에코·`__식별자__` 잔존 행

파이프라인 구버전에서 번역된 일부 행에 시스템 프롬프트 지시문(`__식별자__ 형태의 마커는...`)이 번역문 앞에 붙거나 `__식별자__` 문자열이 잔류하는 케이스가 있음. `strip_prompt_echo()` 도입 이전 잔재이므로 발견 시 CSV 직접 수정 후 재export 필요. 상세: `translation_failure_cases.md` #3.

---

## 7. 환경 요구사항

- Python 3.10 이상 (3.12 권장)
- `pip install -r tools/requirements.txt`
- API 키: `tools/api_key.txt` (prefix `sk-ant-` → Claude, `sk-` → OpenAI)
- Steam 워크샵: `D:\Program Files (x86)\Steam\steamapps\workshop\content\281990`
- 공식 번역: `D:\Program Files (x86)\Steam\steamapps\common\Stellaris\localisation\`

---

## 8. 코드 검수 절차

translation-tools 코드를 수정할 때 반드시 아래 흐름을 따른다.

### 8-1. 흐름

```text
이슈 발견 → GitHub 이슈 등록 → 수정 (커밋) → 드라이런 확인 → 이슈 클로즈
```

### 8-2. 단계별 방법

#### ① 이슈 등록

```powershell
gh issue create --title "제목" --label "bug|enhancement|documentation" --body "내용"
```

#### ② 수정 커밋

커밋 메시지에 반드시 포함:

- **무엇을**: 변경된 파일·함수
- **왜**: 문제 원인 또는 개선 이유

```text
fix: run_pipeline.py의 integrated 변수 스코프 버그

skip_translation=True 시 validate 단계에서 NameError 발생.
integrated 변수를 skip_translation 블록 밖으로 이동.
```

#### ③ 드라이런 확인

```powershell
# 기본 확인 (3개 모드)
python tools/run_pipeline.py --mode plan --use-cache --limit 3

# 특정 모드 확인
python tools/run_pipeline.py --mode report --use-cache --mod-ids <id> --dry-run
```

출력에 오류 없이 `ok` 상태가 나오면 클린.

#### ④ 이슈 클로즈

```powershell
gh issue close <N> --comment "해결: <수정 내용> (commit <hash>)"
```

### 8-3. 예외

- 오탈자·주석 수정 등 동작에 영향 없는 변경은 드라이런 생략 가능
- 여러 이슈가 같은 원인이면 하나로 묶어 등록

---

## 9. 릴리즈 절차

번역 팩 업데이트 시 아래 흐름으로 릴리즈를 만든다.

레포:

- 번역 팩: [integrated_korean_translation_pack](https://github.com/Ryujaehyeon/integrated_korean_translation_pack)
- 번역 도구: [translation-tools](https://github.com/Ryujaehyeon/translation-tools)

### 9-1. 통합팩 릴리즈

```powershell
# 1. 번역 팩 변경사항 커밋·push
cd "integrated_korean_translation_pack"
git add .
git commit -m "vX.Y.Z — 변경 내용 요약"
git push

# 2. 통합 zip 생성 (git, .gitignore, README 제외)
Compress-Archive -Path common,fonts,interface,localisation,descriptor.mod `
  -DestinationPath ..\integrated_korean_translation_pack_vX.Y.Z.zip -Force

# 3. 릴리즈 생성
gh release create vX.Y.Z ..\integrated_korean_translation_pack_vX.Y.Z.zip `
  --title "vX.Y.Z — 변경 요약" --notes "변경 내용"
```

### 9-2. 개별 모드 zip 추가 (선택)

특정 모드만 원하는 사용자를 위해 개별 zip을 릴리즈에 함께 첨부한다.

```powershell
# standalone 모드로 개별 폴더 생성
cd translation-tools
python tools/run_pipeline.py --mode apply --mod-ids <workshop_id>
# → mod/<slug>__<id>_korean/ 폴더 생성됨

# zip 압축
Compress-Archive -Path ..\<slug>__<id>_korean `
  -DestinationPath ..\<slug>_vX.Y.Z.zip -Force

# 기존 릴리즈에 zip 추가
gh release upload vX.Y.Z ..\<slug>_vX.Y.Z.zip
```

### 9-3. 릴리즈 노트 작성 기준

- 추가된 모드 번역 목록
- 수정된 번역 내용 (버그 수정, 용어 통일 등)
- 설치 방법 (초기 릴리즈 이후 변경 없으면 생략 가능)

---

## 10. 참조 문서

| 문서 | 내용 |
|---|---|
| `workflow.md` | 작업 단계별 순서와 명령어 |
| `translation_guidelines.md` | 번역 규칙 — 토큰·문체·용어·검수 기준 |
| `tools_overview.md` | 도구별 역할·옵션 레퍼런스 |
| `tooling_known_issues.md` | 도구 개선 필요사항 및 방치 결정 목록 |

---

## 11. 작업 이력

| 날짜 | 작업 내용 |
|---|---|
| 2026-05-27 | `run.ps1` 편의성 개선 — Workshop ID/slug 자동 해석, `status`/`work` 액션 추가, `export <id_or_slug>` 자동 경로 지원, `tooling.ini`에 workshop/translation 기본값 추가 |
| 2026-05-27 | 작업 CSV 기본 폴더를 `maintenance/translation_keys`로 변경, `maintenance/tooling.ini` + `tools/tool_config.py` 공통 설정 추가 |
| 2026-05-27 | `run.ps1 extract <workshop_id>`만으로 `maintenance\translation_keys\<slug>__<workshop_id>` 경로 자동 생성하도록 개선 |
| 2026-05-27 | `workflow.md` 명령 예시를 `run.ps1` 기준으로 정리, 런처 미지원 명령은 직접 실행 주석 추가, 임시 `_*.py` 스크립트 8개를 `tools/scratch/`로 이동, 파이프라인 전역 `--dry-run` 안전 분기 추가 |
| 2026-05-27 | `run_pipeline.py --translate` 추가 — extract/import-ref 후 `translate_keys.py` + `validate_auto_key_tokens.py` 연결, API 키 없을 때 모드별 skip 처리, `run.ps1 pipeline -Translate` 연결 |
| 2026-05-31 | 코드 검수 절차 COLLABORATION.md에 추가 (섹션 8) |
| 2026-05-31 | 코드 최적화 — `resolve_pack_path()` / `english_source_root()` 4개 파일 중복 → `tool_config.py` 단일 정의로 통합, `strip_prompt_echo()` 정규식 단일 루프로 개선, `limit_rows` 도달 시 `continue`→`break` 조기 종료 |
| 2026-05-31 | 검수 이슈 5건 수정 — 레거시 스크립트 삭제, 환경변수 키 translate 스킵 버그, CACHE_VERSION 주석, 하드코딩 경로 중복, TPM 기본값 안전 하한 |
| 2026-05-31 | `validate_translation_outputs.py` `--output-root` 추가, `run_pipeline.py` validate 호출 시 output_root 전달 |
| 2026-05-31 | `run_pipeline.py` `integrated` 변수 스코프 버그 수정 (`--skip-translation` 시 NameError) |
| 2026-05-31 | GitHub CLI 설치 및 인증, 이슈 등록·클로즈 워크플로 확립 |
| 2026-05-31 | 단일/통합 출력 모드 추가 — `--integrated` 플래그, `tooling.ini [output] mode` 설정, standalone 시 `descriptor.mod` 자동 생성 |
| 2026-05-31 | Claude/OpenAI 멀티 provider 지원 — `api_key.txt` 통합, prefix `sk-ant-` 감지로 자동 분기 |
| 2026-05-31 | TPM 기본값 100,000으로 통일 (Anthropic 무료 티어 기준), `tooling.ini`에서 일괄 관리 |
| 2026-05-31 | `giga_gui_main_menu.gui` 번역 팩에 추가 — 기가스트럭처 설정 메뉴 하드코딩 텍스트 120개 한국어 교체 |
| 2026-05-27 | `translation-tools/` 폴더 신설 — tools/ + maintenance/ 분리 이전, `run.ps1` 런처 추가, PS 경고 수정 (`$args`→`$pyArgs`, `mod-args`→`Get-ModArgs`) |
| 2026-05-27 | Merged Leader Levels (als/gle/sls/rls) 번역 검수 완료 — 미번역 영단어, §EE 이중코드, 누락 숫자 등 수정 |
| 2026-05-27 | Extra Leader Traits(`3334925693`) 한국어 번역 파일 추출 → 통합한글모드 + 개별모드(`addon_Extra_Leader_Traits_kr`) 신규 생성 |
| 2026-05-27 | ELT 번역 검수 — `fastsoft_3 II→III`, `특화었으며→특화되었으며` 수정 |
| 2026-05-27 | `dlc_load.json` — Extra Leader Traits 원본 활성화(60번), 개별한글모드는 제외 |
| 2026-05-25 | `gc_kilo` 등 7개 색상 마커 키에서 `​`(U+200B) 제거 → 한국어 폰트 `▣` 렌더링 수정 |
| 2026-05-25 | `giga_modifiers_l_korean.yml` job efficiency 표시 순서 수정 47건 (`$BONUS_WORKFORCE_FOR$ X` → `X 직업 효율성`) |
| 2026-05-25 | 프롬프트 에코·`__식별자__` 잔존 행 9건 수동 수정 (6개 파일) |
| 2026-05-25 | `giga_mega_names_l_korean.yml` S.U.C.C. 설명 토큰 복원 실패 수동 수정 |
| 2026-05-25 | 문서 4종 전면 재작성 — 역할 분리, 중복 제거 |
| 2026-05-25 | `translate_keys.py` SYSTEM_PROMPT 3단계 분리 (~70토큰 / ~182토큰 / 가이드라인 포함). §!!§! 연속 닫기 코드 설명 추가 |
| 2026-05-25 | `generate_translation_progress_tree.py` 집계 기준 변경: error만 진행률 감소 반영 → 전체 번역률 100.0% |
| 2026-05-25 | `review_report.py` `_is_untranslatable_identical()` 추가, YML 주석 제거 — 오탐 억제 (327행 → 10행) |
| 2026-05-25 | review error 행 직접 수정 + 재번역: quote_noise 2행, giga_birch 3행, giga_blokkat 1행, gle_direction_expansion 수동 번역, AH_*_intro 주석 복원 |
| 2026-05-25 | `auto_patch_tokens()` 추가 (P1: $TABBED_NEW_LINE$ 복원, P4: extra 아이콘 제거) |
| 2026-05-25 | `strip_extra_color_codes()` 개선 — §X...§! 쌍 단위 제거 |
| 2026-05-25 | hard_token_mismatch 336건 전원 처리 → critical_rows=0 달성 |
| 2026-05-25 | `test_token_masking.py` 신규, `diagnose_source_tokens.py` 개선, TOKEN_RE 달러 패턴 수정 |
| 2026-05-25 | 토큰 마스킹 방식 확립: `__ICON_xxx__` / `__DOLLAR_xxx__` / `__Bn__` |
| 2026-05-25 | 용어집 시스템 구축 (extract_official_terms.py → term_glossary.csv ~3,632개) |
| 2026-05-24 | 번역 스타일 기준 수립, giga_ehof_functions_key.csv "debug" 행 51개 처리 |
| 이전 | import_korean_references.py, validate_auto_key_tokens.py, fix_quote_issues.py 등 도구 구축 |
