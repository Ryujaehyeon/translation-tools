# 통합한글모드 번역 프로세스

최종 갱신: 2026-06-03

이 문서는 번역 작업 순서와 각 단계의 명령어를 정리한다.
번역 규칙은 `translation_guidelines.md`, 도구 옵션 상세는 `tools_overview.md`를 참조한다.

역할: **절차 문서**. "무슨 순서로 실행할지"와 대표 명령어만 둔다.
도구별 전체 옵션은 `tools_overview.md`, 사용자용 빠른 시작은 `manual.md`, 최신 인계는
`../../../HANDOFF.md`를 기준으로 본다.

넣지 말 것:

- 세션별 진단 로그
- 도구 내부 구현 설명
- 옵션 전체 목록
- 오래된 진행률 숫자

## 기본 원칙

- 번역은 `korean_value`에만 반영한다. `key`와 `english_value`는 수정하지 않는다.
- 인코딩: UTF-8 with BOM.
- CSV 셀 안의 줄바꿈은 실제 줄바꿈 금지 — `\n` 리터럴로 저장한다.
- 같은 키의 기존 한국어 참고 번역은 AI 번역보다 우선할 수 있지만, 참고 번역 임포트는 필요할 때만 실행한다.

## 작업 디렉토리

모든 명령어는 번역툴 루트에서 실행한다.

```powershell
Set-Location "$env:USERPROFILE\Documents\Paradox Interactive\Stellaris\mod\translation-tools"
```

대부분의 명령은 Workshop ID와 `<mod_slug>__<workshop_id>` 둘 다 받는다.

```powershell
.\run.ps1 validate 1121692237
.\run.ps1 validate gigastructural_engineering_more_4_3__1121692237
```

기본 작업 CSV 폴더는 `maintenance\tooling.ini`의 `translation_keys` 값으로 관리한다.
`--dry-run`은 CSV/YML을 쓰지 않는 모드다. 검증·리뷰·번역 dry-run의 보고서 파일은 생성될 수 있다.

---

## 신규 모드 추가 흐름

원본 모드 폴더만 있고 `translation_keys`에 아직 없는 경우.

### 1. 모드 정보 확인

`.mod` 파일에서 모드명과 Workshop ID를 확인한다.

```text
원본 모드 경로: D:\Program Files (x86)\Steam\steamapps\workshop\content\281990\<workshop_id>\
```

### 2. translation_keys CSV 생성

```powershell
.\run.ps1 extract <workshop_id>
```

- 지원 원본 구조: `localisation/english/**/*_l_english.yml`, `localisation/replace/english/**/*_l_english.yml`
- `replace` 원본은 `translation_keys/<mod>/replace/*_key.csv`로 추출된다.
- 기존 CSV가 있으면 `korean_value`를 보존하고 `english_value`만 갱신한다.
- 원본 기준 완전 동기화가 필요할 때만 `--sync-source`를 사용한다.

### 3. 한국어 참고 번역 임포트 (선택)

기존 한글 보완모드/MKC/Giga 한국어 패치 등의 번역을 새로 참고해야 할 때만 실행한다.
참고 모드가 업데이트되지 않았거나, 그 번역이 낡아서 직접 번역하려는 경우에는 이 단계를 건너뛴다.

```powershell
.\run.ps1 import-ref <workshop_id> --dry-run
.\run.ps1 import-ref <workshop_id>
```

참고 한글모드는 워크샵 ID나 로컬 경로로 직접 고를 수 있다.

```powershell
.\run.ps1 import-ref <workshop_id> --source 2506141839 --dry-run
.\run.ps1 import-ref <workshop_id> --source "..\addon_Mod_Korean_Collection_모드_한국어_모음_kr" --dry-run
```

한글모드의 폴더 구조를 보존해 먼저 추출해두고 싶으면:

```powershell
# run.ps1 미지원 — 직접 실행:
python tools/extract_korean_reference_keys.py --reference-source "..\addon_Mod_Korean_Collection_모드_한국어_모음_kr"
# run.ps1 미지원 — 직접 실행:
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-csv-dir maintenance\reference_keys\<source_slug> --dry-run
# run.ps1 미지원 — 직접 실행:
python tools/import_korean_references.py --mod <mod_slug>__<workshop_id> --reference-csv-dir maintenance\reference_keys\<source_slug>
```

`import_korean_references.py`는 대상 CSV의 `korean_value`만 채우거나 덮어쓴다. `key`와 `english_value`는 수정하지 않는다.

참고 소스 우선순위 및 옵션 상세: `translation_guidelines.md` → "한국어 참고 소스 우선순위"

### 4. AI 번역 (빈 행 채우기)

```powershell
.\run.ps1 translate <workshop_id> --workers 3 --tpm 2000000
```

### 5. 검수 및 재번역

```powershell
# 검수 리포트 생성 + error 행 retranslate=1 표시
.\run.ps1 review <workshop_id> --mark-errors

# error 행만 재번역
.\run.ps1 translate --from-report --workers 3 --tpm 2000000

# 재번역 후 리포트 재생성 (잔여 이슈 확인)
.\run.ps1 review <workshop_id>
```

### 6. 토큰 검증

```powershell
.\run.ps1 validate <workshop_id>
```

critical 불일치가 남아 있으면:

```powershell
.\run.ps1 translate --rewrite --workers 3 --from-worklist maintenance/reports/token_validation/token_repair_worklist_<timestamp>.csv
```

### 7. 출력 및 최종 검증

```powershell
.\run.ps1 export <workshop_id>
# run.ps1 미지원 — 직접 실행:
python tools/validate_translation_outputs.py <workshop_id> maintenance\translation_keys\<mod_slug>__<workshop_id>
.\run.ps1 bom --fix
.\run.ps1 progress
```

---

## 기존 모드 갱신 흐름

원본 모드가 업데이트된 경우 또는 번역을 보완하는 경우.

### 1. translation_keys 갱신

```powershell
.\run.ps1 extract <workshop_id>
```

### 2. 검수

```powershell
.\run.ps1 review <workshop_id> --mark-errors
```

### 3. 재번역 및 검증

신규 모드 흐름의 4~7단계와 동일.

---

## 전체 모드 일괄 검수 및 재번역

```powershell
# 전체 검수 리포트 생성
.\run.ps1 review --mark-errors

# 전체 error 행 재번역
.\run.ps1 translate --from-report --workers 3 --tpm 2000000

# 재번역 후 리포트 재생성
.\run.ps1 review
```

---

## review report 사용 기준

- `review_latest.csv`는 현재 상태 스냅샷이다.
- `severity=error` (empty, token_broken, no_hangul, quote_noise) — 자동 재번역 대상.
- `severity=warning` (identical, too_short) — 참고 검수용. 자동 재번역 대상 아님. 진행률에도 영향 없음.
- `--mark-errors`: error 행에만 `retranslate=1` 표시 → 자동 파이프라인 기본값.
- `--mark-retranslate`: 전체 행에 `retranslate=1` 표시 → 전수 강제 재번역 시에만 사용.
- `translate_keys.py --from-report`는 `retranslate=1`인 행만 처리한다.
- 재번역 후 `review_report.py`를 다시 실행해 잔여 이슈를 확인한다.
- 실행 시 기존 `review_latest.csv`는 날짜 파일로 자동 백업된다.

---

## 자주 쓰는 명령어

```powershell
# 특정 모드 단위 검수 (따옴표 보정 포함)
.\run.ps1 review <workshop_id> --fix-quotes

# 전체 translation_keys 검수
.\run.ps1 review

# 한국어 참고 번역 전체 임포트 (선택, 빈 행만)
.\run.ps1 import-ref --dry-run
.\run.ps1 import-ref

# run_pipeline에서 참고 번역 임포트를 같이 실행하고 싶을 때만
.\run.ps1 pipeline --mode report --import-ref --dry-run
.\run.ps1 pipeline --mode auto --import-ref

# AI 자동번역까지 포함한 파이프라인
.\run.ps1 pipeline <workshop_id> --mode auto --import-ref --translate

# 현재 상태 확인 / 다음 작업 추천
.\run.ps1 status <workshop_id>
.\run.ps1 work <workshop_id>

# 특정 행 범위 번역
.\run.ps1 translate --file maintenance\translation_keys\<mod>\<file>_key.csv --start 201 --end 300

# 끝까지 번역
.\run.ps1 translate --file maintenance\translation_keys\<mod>\<file>_key.csv --start 201 --end end

# 의심 행만 재번역
# run.ps1 미지원 — 직접 실행:
python tools/translate_keys.py --file maintenance\translation_keys\<mod>\<file>_key.csv --rewrite-existing --only-suspicious

# 원본 토큰 오타 진단 및 보정
.\run.ps1 diagnose
.\run.ps1 patch

# 진행률 갱신
.\run.ps1 progress
```

---

## 최종 검증 체크리스트

```powershell
.\run.ps1 validate
# run.ps1 미지원 — 직접 실행:
python tools/validate_translation_outputs.py <workshop_id> maintenance\translation_keys\<mod_slug>__<workshop_id>
.\run.ps1 bom --fix
.\run.ps1 progress
```

확인 항목:

- `../translation_progress_tree.md`에서 error 행(진행률 감소 기준) 0건인지 확인
- `review_latest.csv`에서 warning 행은 번역 불필요 케이스인지 샘플 확인
- critical 토큰 불일치 0건인지 확인
