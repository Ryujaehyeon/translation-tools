# 협업 참고 문서 — Stellaris 통합 한국어 번역 팩

> AI 또는 신규 협업자가 작업 맥락을 바로 파악할 수 있도록 작성된 문서입니다.
> 최종 갱신: 2026-06-03 (10차)

---

## 문서 역할

| 문서 | 역할 | 넣지 말 것 |
|---|---|---|
| `../../../HANDOFF.md` | 최신 세션 인계, 현재 변경분, 바로 다음 작업 | 장기 배경, 전체 명령어 레퍼런스 |
| `COLLABORATION.md` | 프로젝트 지도, 폴더 구조, 협업 원칙 | 세션별 상세 로그, 오래된 진행률 숫자 |
| `workflow.md` | 작업 단계별 실행 순서와 명령어 레시피 | 도구 내부 구현 설명 |
| `tools_overview.md` | 도구별 옵션, 입력, 출력 레퍼런스 | 프로젝트 역사, 번역 문체 규칙 |
| `translation_guidelines.md` | 번역 문체, 용어, 토큰 보존 규칙 | 실행 절차, 도구 옵션 |
| `../records/translation_failure_cases.md` | 실제 실패 사례와 대응 원인 분석 | 아직 확인되지 않은 작업 큐 |
| `../records/tooling_known_issues.md` | 남은 도구 버그·개선 큐와 방치 결정 | 완료된 일반 작업 로그 |
| `../fixtures/token_detection_cases.jsonl` | 토큰 검출 회귀·손상 케이스 | 세션별 작업 기록 |
| `manual.md` | 사용자용 빠른 사용 설명서 | 내부 개발·검수 세부 사정 |

---

## 0. 작업 시작 전 필독 파일

새 세션을 시작하거나 작업 맥락이 없을 때 아래 순서로 읽는다.

| 순서 | 파일 | 목적 |
| --- | --- | --- |
| 1 | `../../../HANDOFF.md` | 최신 세션 상태와 다음 작업 |
| 2 | `translation-tools/maintenance/docs/COLLABORATION.md` | 이 파일 — 전체 구조와 협업 원칙 |
| 3 | `translation-tools/maintenance/docs/translation_guidelines.md` | 번역 규칙 (토큰·문체·용어) |
| 4 | `translation-tools/maintenance/docs/workflow.md` | 작업 단계별 명령어 |
| 5 | `translation-tools/maintenance/docs/tools_overview.md` | 도구별 옵션 레퍼런스 |
| 6 | `translation-tools/maintenance/translation_progress_tree.md` | 현재 번역 진행 상태 |

**주요 규칙 요약 (숙지 필수):**

- 번역 대상은 **한국어 파일만** (`l_korean.yml`, `*_key.csv`의 `korean_value` 열)
- 토큰(`$variable$`, `£icon£`, `§X...§!`) 보존 필수 — 절대 번역하거나 제거하지 않는다
- 작업 전·후 구조 변화가 있으면 이 파일(COLLABORATION.md)의 `11. 주요 구조 변경 이력` 갱신
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
│       ├── docs/                   ← 협업·절차·도구·번역 기준 문서
│       │   ├── COLLABORATION.md    ← 이 파일
│       │   ├── workflow.md         ← 작업 순서 및 명령어
│       │   ├── translation_guidelines.md ← 번역 규칙 (토큰·문체·용어)
│       │   ├── tools_overview.md   ← 도구별 역할·옵션 레퍼런스
│       │   └── manual.md           ← 사용자용 빠른 사용 설명서
│       ├── records/                ← 실패 사례, 작업 로그, 도구 개선 큐
│       ├── fixtures/               ← 테스트/드라이런 입력 케이스
│       └── translation_progress_tree.md ← 모드별 번역 진행률
└── integrated_korean_translation_pack/
    └── localisation/korean/        ← 실제 번역 YML 파일 (export 결과물)
```

---

## 3. 도구 실행 원칙

모든 도구는 가능하면 `translation-tools/run.ps1` 런처로 실행한다.
작업 디렉터리는 `translation-tools/`다.

```powershell
cd "$env:USERPROFILE\Documents\Paradox Interactive\Stellaris\mod\translation-tools"
.\run.ps1 <action>
```

절차별 명령어는 `workflow.md`, 도구별 옵션과 출력 파일은 `tools_overview.md`를 기준으로
본다. `run.ps1`가 아직 감싸지 않은 명령은 해당 문서에서 "직접 실행"으로 표시한다.

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

## 5. 현재 상태 확인 위치

이 문서에는 진행률 숫자를 고정하지 않는다. 상태가 자주 바뀌므로 아래를 기준으로 본다.

- 최신 세션과 다음 작업: `../../../HANDOFF.md`
- 번역률과 suspicious 행: `../translation_progress_tree.md`
- 최신 review/token validation 산출물: `../reports/`
- 특정 모드의 다음 작업 추천: `.\run.ps1 status <workshop_id>` 또는 `.\run.ps1 work <workshop_id>`

---

## 6. 알려진 문제 확인 위치

문제 자체의 상세는 이 문서에 중복해 적지 않는다.

- 실제 번역·AI 실패 사례: `../records/translation_failure_cases.md`
- 아직 남은 도구 버그/개선 큐: `../records/tooling_known_issues.md`
- 현재 세션에서 새로 발견된 긴급 이슈: `../../../HANDOFF.md`
- 토큰 검출 회귀 케이스: `../fixtures/token_detection_cases.jsonl`

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
이슈 발견 → GitHub 이슈 등록 → 수정 (커밋·push) → 드라이런 확인 → 이슈 클로즈
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

### 8-3. CI (선택)

push하면 GitHub Actions가 자동으로 문법 검사·import 확인을 수행한다.
문법 오류·import 실패만 잡을 수 있고 로직 검사는 불가 (Steam 환경 필요).
보조 수단으로만 활용하고, 핵심 확인은 로컬 드라이런으로 한다.

```powershell
gh run list --limit 3              # 결과 확인
gh run view <run-id> --log-failed  # 실패 시 로그 읽기
```

### 8-4. 예외

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
| `../../../HANDOFF.md` | 최신 세션 인계와 다음 작업 |
| `workflow.md` | 작업 단계별 순서와 명령어 |
| `translation_guidelines.md` | 번역 규칙 — 토큰·문체·용어·검수 기준 |
| `tools_overview.md` | 도구별 역할·옵션 레퍼런스 |
| `../records/translation_failure_cases.md` | 실제 실패 사례와 대응 기록 |
| `../records/tooling_known_issues.md` | 도구 개선 필요사항 및 방치 결정 목록 |
| `../fixtures/token_detection_cases.jsonl` | 토큰 검출 회귀·손상 케이스 카탈로그 |

---

## 11. 주요 구조 변경 이력

세션별 최신 작업은 `../../../HANDOFF.md`, 전체 변경 이력은 git log를 기준으로 본다.
이 표에는 프로젝트 구조나 운영 방식이 바뀐 큰 항목만 남긴다.

| 날짜 | 작업 내용 |
|---|---|
| 2026-06-03 | 토큰 마스킹을 범위 인식 파서 기반으로 전환 + 닫힘 없는 `£` 자동 정상화. CSV 쓰기를 LF+QUOTE_MINIMAL로 표준화(`tool_config` 헬퍼), 공통 유틸(`read_text`/`resolve_pack_path`/`descriptor_name`) 통일 |
| 2026-06-03 | maintenance 문서를 `docs/`, `records/`, `fixtures/`로 역할별 분리 |
| 2026-06-03 | 범위 인식 토큰 파서(`token_parser.py`)와 사용자 추가형 검출 케이스(`token_detection_cases.jsonl`, `test_token_parser.py`) 도입 |
| 2026-05-31 | 코드 검수 절차, GitHub 이슈/커밋/CI 확인 흐름 정리 |
| 2026-05-31 | 단일/통합 출력 모드, provider 자동 감지, 공통 설정(`tooling.ini`, `tool_config.py`) 정비 |
| 2026-05-27 | `translation-tools/` 리포 분리, `run.ps1` 런처와 `maintenance/translation_keys` 구조 정착 |
| 2026-05-25 | 토큰 마스킹 방식과 용어집 기반 번역 파이프라인 구축 |
