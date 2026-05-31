# 통합 번역팩 자동 처리 매뉴얼

최종 갱신: 2026-05-31

## 설치 및 준비

### 사전 요구사항

- Python 3.10 이상
- PowerShell 7 이상 (Windows 기본 PowerShell 5는 불가)
- Steam + Stellaris 설치됨

### 패키지 설치

```powershell
pip install openai tiktoken chardet
```

### 폴더 구조

이 저장소(`translation-tools`)는 번역팩 폴더 안에 위치해야 한다.

```text
mod/
  integrated_korean_translation_pack/   # 번역팩 (Stellaris 모드)
  translation-tools/                    # 이 저장소
    run.ps1
    tools/
    maintenance/
```

Steam 경로(`workshop/content/281990`)는 자동으로 탐지한다.
Windows 기본 설치 경로(`C:\Program Files (x86)\Steam` 또는 `D:\...`)를 자동으로 찾으며, 찾지 못하면 `tooling.ini`에서 직접 지정할 수 있다.

### API 키 설정 (선택)

Claude API를 사용한 자동 번역을 원할 경우 `tools/` 아래에 키 파일을 추가한다.

```text
tools/openai_api_key.txt   # 파일 내용: sk-... (키 문자열만)
```

API 키가 없으면 자동 번역 없이 수동 번역 흐름만 사용할 수 있다.

### 첫 실행

```powershell
cd translation-tools

# 1. 처리 가능한 모드 목록 확인
python tools/run_pipeline.py --mode scan

# 2. 특정 모드 키 추출
.\run.ps1 extract <workshop_id>

# 3. 번역 파일 생성 (dry-run으로 먼저 확인)
.\run.ps1 export <workshop_id> --dry-run

# 4. 실제 반영
.\run.ps1 export <workshop_id>
```

---

## 기본 위치

작업 전에 통합 번역팩 폴더로 이동한다.

```powershell
cd "$env:USERPROFILE\Documents\Paradox Interactive\Stellaris\mod\integrated_korean_translation_pack"
```

도구는 Steam 설치 경로를 자동으로 찾고, Stellaris Workshop 폴더인 `workshop/content/281990` 아래의 구독 모드를 순회한다.

## 핵심 구조

자동 생성 키 CSV는 모드별 폴더에 저장된다.

```text
maintenance/translation_keys/<모드명_slug>__<모드id>/
```

예시:

```text
maintenance/translation_keys/more_events_mod__727000451/mem_sight_unseen_key.csv
```

CSV 컬럼:

```text
key,english_value,korean_value
```

- `key`: Stellaris 로컬라이징 키
- `english_value`: 원본 모드의 영어 원문
- `korean_value`: 사용자가 채우는 한국어 번역문

`extract_localisation_keys.py`는 CSV를 다시 만들 때 기존 `korean_value`를 보존한다.

## 자동 처리 명령

### 1. 스캔만 하기

```powershell
python tools/run_pipeline.py --mode scan
```

하는 일:

- 전체 구독 모드 수 확인
- `localisation/english`가 있는 처리 대상 모드 수 확인
- 스킵되는 모드를 유형별로 분류

파일은 생성하거나 수정하지 않는다.

### 2. 작업량 미리 보기

```powershell
python tools/run_pipeline.py --mode plan --use-cache
```

하는 일:

- 키 추출 상태 확인
- 번역 dry-run 실행
- 생성/갱신/변경없음 파일 수 계산
- 누락/충돌/영어 fallback 개수 확인

실제 `localisation/korean` 파일은 수정하지 않는다.

### 3. 리포트 생성 중심 dry-run

```powershell
python tools/run_pipeline.py --mode report --use-cache
```

하는 일:

- 키 CSV 생성/갱신
- 번역 dry-run
- 검증 리포트 생성
- 충돌 해결용 CSV 생성

기본적으로 실제 한국어 `.yml` 파일은 수정하지 않는다.

조용히 진행률만 보려면:

```powershell
python tools/run_pipeline.py --mode report --use-cache --quiet
```

### 4. 실제 한국어 파일 반영

진행 로그를 보면서 실제 반영:

```powershell
python tools/run_pipeline.py --mode apply --use-cache
```

간단한 프로그레스바만 보면서 실제 반영:

```powershell
python tools/run_pipeline.py --mode auto --use-cache
```

`--mode auto`는 다음과 같다.

```text
--mode apply + --quiet
```

즉 실제 `localisation/korean` 파일을 갱신하므로, 실행 전 `plan` 또는 `report`로 먼저 확인하는 것을 권장한다.

## 자주 쓰는 옵션

### 일부 모드만 테스트

```powershell
python tools/run_pipeline.py --mode report --use-cache --limit 1
```

### 특정 모드만 처리

```powershell
python tools/run_pipeline.py --mode report --use-cache --mod-ids 727000451
```

여러 모드:

```powershell
python tools/run_pipeline.py --mode report --use-cache --mod-ids 727000451 1121692237
```

### 캐시 무시하고 다시 처리

```powershell
python tools/run_pipeline.py --mode report --force
```

### 병렬 처리 개수 지정

```powershell
python tools/run_pipeline.py --mode report --use-cache --workers 4
```

기본값은 `--workers auto`이다.

- dry-run/report 계열: 최대 4개 병렬 처리
- 실제 적용 계열: 기본 1개 처리

## 개별 도구 사용

### 키 CSV 추출

```powershell
.\run.ps1 extract "모드id"
```

예시:

```powershell
.\run.ps1 extract 727000451
```

### 번역 파일 생성 dry-run

```powershell
.\run.ps1 export "모드id" "maintenance/translation_keys/모드명__모드id" --dry-run
```

### 번역 파일 실제 생성/갱신

```powershell
.\run.ps1 export "모드id" "maintenance/translation_keys/모드명__모드id"
```

### 결과 검증

```powershell
python tools/validate_translation_outputs.py "모드id" "maintenance/translation_keys/모드명__모드id"
```

### 충돌 해결 CSV 만들기

```powershell
python tools/resolve_conflict_translations.py "모드id" "maintenance/translation_keys/모드명__모드id" --prepare
```

## 리포트 위치

리포트는 도구별 하위 폴더에 저장된다.

```text
maintenance/reports/extraction/
maintenance/reports/translation/
maintenance/reports/validation/
maintenance/reports/conflict_resolution/
maintenance/reports/auto_process/
```

최신 리포트 인덱스:

```text
maintenance/reports/index.json
maintenance/reports/index.md
```

## CSV 비교 방법

사용자가 수동으로 비교할 때는 이전 CSV와 새 CSV를 VS Code에서 비교하면 된다.

예시:

```text
mem_cold_key_old.csv
mem_cold_key.csv
```

VS Code에서:

1. 이전 파일 우클릭
2. `Select for Compare`
3. 새 파일 우클릭
4. `Compare with Selected`

비교 기준:

- `key`: 같은 항목인지 판단하는 기준
- `english_value`: 원본 모드에서 바뀐 원문 확인
- `korean_value`: 유지하거나 수정할 번역문

## 권장 순서

평소에는 다음 순서로 진행한다.

```powershell
python tools/run_pipeline.py --mode scan
python tools/run_pipeline.py --mode plan --use-cache
python tools/run_pipeline.py --mode report --use-cache
```

문제가 없으면 실제 반영한다.

```powershell
python tools/run_pipeline.py --mode auto --use-cache
```

## 수동 번역 흐름 (AI API 없이)

OpenAI API 키가 없거나 AI 번역을 사용하지 않을 때는 CSV를 직접 편집해 `korean_value`를 채운다.

### 1. 키 CSV 추출

```powershell
# 특정 모드
.\run.ps1 extract <모드id>

# 또는 전체 자동 처리
python tools/run_pipeline.py --mode report --use-cache
```

`maintenance/translation_keys/<모드폴더>/` 아래에 `*_key.csv` 파일들이 생성된다.

### 2. 참조 번역 임포트 (선택)

한국어 참고 모드가 Steam에 구독되어 있고 그 번역을 재사용하고 싶을 때만 먼저 채운다.
참고 모드가 업데이트되지 않았거나, 참고 번역이 낡아서 직접 번역하려는 경우에는 건너뛴다.

```powershell
python tools/import_korean_references.py --mod <모드폴더> --dry-run
python tools/import_korean_references.py --mod <모드폴더>
```

### 3. CSV 직접 편집

`*_key.csv`를 Excel, VS Code, 또는 텍스트 에디터로 열어 `korean_value` 열을 채운다.

주의사항:

- 인코딩은 반드시 **UTF-8 with BOM**으로 저장한다. Excel은 기본적으로 BOM을 붙여 저장한다.
- `key`와 `english_value`는 수정하지 않는다.
- `english_value`가 따옴표로 감싸여 있으면 (`"값"`) `korean_value`도 같은 형태로 감싼다.
- 줄바꿈은 실제 줄바꿈이 아니라 `\n` 리터럴로 입력한다.
- 토큰(`$...$`, `[...]`, `£...£`, `§Y` 등)은 원문 그대로 유지한다.

빈 행만 확인하려면:

```powershell
# 검수 리포트로 미번역 행(empty) 목록 출력
python tools/review_report.py --mod <모드폴더> --reason empty
```

### 4. 따옴표·토큰 검사

편집 후 문제 없는지 확인한다.

```powershell
python tools/validate_auto_key_tokens.py --mod <모드폴더>
python tools/fix_quote_issues.py --scan --mod <모드폴더> --dry-run
python tools/fix_quote_issues.py --scan --mod <모드폴더>
```

### 5. 한국어 yml 파일 생성

```powershell
python tools/run_pipeline.py --mode apply --use-cache --mod-ids <모드id>
```

## 주의사항

- `--mode scan`, `--mode plan`, `--mode report`는 기본적으로 한국어 `.yml` 파일을 수정하지 않는다.
- `--mode apply`와 `--mode auto`는 실제 `localisation/korean` 파일을 갱신한다.
- 실제 반영 시 기존 대상 파일은 `maintenance/backups/` 아래에 백업된다.
- 충돌 키는 자동으로 한국어 후보를 선택하지 않는다.
- CSV의 `korean_value`가 비어 있으면 기존 한국어 번역을 찾고, 없으면 원본 영어가 fallback으로 들어갈 수 있다.
