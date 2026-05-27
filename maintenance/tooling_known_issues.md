# 도구 개선 필요사항

최종 갱신: 2026-05-25 (3차)

이 문서는 `tools/*.py`와 번역 프로세스 문서를 읽으며 바로 확인된 개선 필요사항을 정리한 참고 문서이다. 작업 큐가 아니라 다음 코드 정리 때 확인할 목록이며, 실제 수정은 별도 단계에서 진행한다.

관련 기준 문서:

- `maintenance/COLLABORATION.md`
- `maintenance/workflow.md`
- `maintenance/translation_guidelines.md`
- `maintenance/tools_overview.md`

## 1. `translate_keys.py` 샘플 모드 반환값 불일치

- 상태: 수정됨
- 우선순위: 높음
- 영향: `python tools/translate_keys.py --sample-rows N` 실행 시 샘플 번역 단계에서 예외가 발생할 수 있다.
- 원인: `translate_value()`는 현재 `(translated_raw, rejected_raw, system_prompt, user_prompt)` 4개 값을 반환하지만, `translate_sample_file()` 내부 호출부는 2개 값만 언패킹한다.
- 수정 방향: 샘플 모드 호출부도 4개 반환값을 받도록 맞추고, 샘플 CSV에는 기존 컬럼 구조를 유지한다. 프롬프트 값은 샘플 출력에 추가하지 않고 버려도 된다.
- 확인 방법: `python tools/translate_keys.py --mod <모드폴더> --sample-rows 3 --sample-output maintenance/reports/ai_translation/sample_check.csv`

## 2. `review_report.py`의 `replace/` 하위 CSV 경로 처리

- 상태: 수정됨
- 우선순위: 높음
- 영향: `auto_keys/<mod>/replace/*_key.csv`를 검수할 때 `review_latest.csv`의 `mod` 컬럼이 실제 모드 폴더가 아니라 `replace`로 기록될 수 있다. 이후 `translate_keys.py --from-report`나 사람이 리포트를 볼 때 대상 위치가 헷갈릴 수 있다.
- 원인: 리포트 행의 `mod` 값을 `csv_path.parts[-2]`로 계산한다. 하위 폴더가 있는 CSV에서는 이 값이 모드명이 아니라 바로 위 폴더명이 된다.
- 수정 방향: `auto_keys_dir` 기준 상대 경로를 계산해 첫 번째 path part를 `mod`로 쓰고, 나머지 path parts 전체를 `file`로 기록한다.
- 확인 방법: `python tools/review_report.py --file maintenance/translation_keys/<모드폴더>/replace/<파일>_key.csv --output maintenance/reports/review/replace_path_check.csv`

## 3. `generate_translation_progress_tree.py`의 `replace/` 하위 CSV 누락

- 상태: 수정됨
- 우선순위: 중간
- 영향: `maintenance/translation_progress_tree.md`의 전체 CSV 수, 번역 대상 행 수, 번역률에서 `replace/` 하위 파일이 빠질 수 있다.
- 원인: 모드 폴더마다 `mod_dir.glob("*_key.csv")`만 사용해 1단계 CSV만 집계한다.
- 수정 방향: `mod_dir.rglob("*_key.csv")`로 바꾸고, 출력 파일명은 모드 폴더 기준 상대 경로(`replace/<파일>_key.csv`)로 표시한다.
- 확인 방법: `python tools/generate_translation_progress_tree.py` 실행 후 `replace/` 하위 CSV가 `translation_progress_tree.md`에 표시되는지 확인한다.

## 4. `translate_keys.py` 토큰 보호 마커 충돌 가능성

- 상태: 수정됨
- 우선순위: 중간
- 영향: 같은 문장 안에 `$energy$`와 `£energy£`처럼 내부 이름이 같은 서로 다른 토큰 타입이 함께 있으면 복원 결과가 잘못될 가능성이 있다.
- 원인: `$...$`, `£...£`, `[...]`가 모두 `__inner__` 형식으로 치환된다. 예를 들어 `$energy$`와 `£energy£`가 모두 `__energy__`가 된다.
- 수정 방향: 토큰 타입과 순번을 포함한 충돌 없는 마커를 사용한다. 예: `__IKTP_DOLLAR_0__`, `__IKTP_ICON_1__`, `__IKTP_BRACKET_2__`.
- 확인 방법: `$energy$`와 `£energy£`가 함께 있는 테스트 문자열로 `protect_tokens()`와 `restore_protected_tokens()` 왕복 결과가 원문과 같은지 확인한다.

## 6. `review_report.py` identical/no_hangul이 번역 불필요 행을 과잉 경고

- 상태: 수정됨
- 우선순위: 높음
- 영향: `review_latest.csv`에 동적 포맷(`<...>`), 네임리스트 고유명사, 아이콘+색상코드 조합 등 번역 불필요 행이 `identical` warning으로 대량 포함됐다. 327행 중 298행이 warning이고 전부 `reason=identical`이었다.
- 원인: `get_reasons()`의 identical 판정이 "다단어이면 무조건 identical"로 처리했다. `<lunari_supremacist_names>`, `Ssha Dreier`, `§RAssassination Attempt§!` 같이 번역 불필요한 다단어도 모두 잡혔다.
- 수정 내용: `_is_untranslatable_identical()` 함수 추가. 아래 케이스는 identical warning 및 no_hangul에서 면제한다.
  1. `<...>` 동적 네임 포맷 포함 행
  2. 토큰 제거 후 남은 텍스트가 고유명사·약어·수식 패턴 (대문자 시작 단어, 5자 이하 약어, 숫자/기호 포함 수식)
- 결과: 327행 → 25행 (warning 10행은 실제 미번역 케이스만 남음)
- 확인 방법: `python tools/review_report.py` 실행 후 `review_latest.csv` 행 수 확인

## 7. `message_dontsub_desc232` token_broken 오탐 (방치)

- 상태: 미수정 (방치)
- 우선순위: 낮음
- 영향: `review_latest.csv`에 `token_broken` error 1행이 영구적으로 남는다. 자동 재번역 파이프라인에서 매번 `retranslate=1`이 찍히지만, 재번역해도 번역 자체는 정상이다.
- 원인: EN 값 `§Y9.99$§!`에서 `9.99$`의 `$`와 `§Y19.99$§!`의 `19.99$` 사이가 dollar_ref 패턴(`$...$`)으로 잘못 매칭된다. 이는 원본 모드(`stellaris_101_how_to_read__2819720352`)가 의도적으로 비정상 값을 쓰는 메타 유머 모드이기 때문이다.
- KO 번역 상태: 정상 (`"모든 DLC는 §Y9.99$§!에서 시작하며, 확장 DLC는 §Y19.99$§!입니다. DLC의 시대에 오신 것을 환영합니다!"`)
- 수정 방향 (참고): dollar_ref 패턴을 `\$[A-Za-z_][^$\n\t]+\$` (알파벳/언더스코어 시작)으로 좁히면 숫자로 시작하는 `9.99$` 등을 제외할 수 있다. 단, 기존 번역 파이프라인 전체에 영향이 있으므로 별도 검토 필요.

## 5. 토큰 참고 문서 계획과 현재 출력 파일명 불일치

- 상태: 미수정
- 우선순위: 낮음
- 영향: 문서에는 `maintenance/reports/translation_work/token_reference_latest.csv` 갱신 흐름이 남아 있지만, 현재 실제 도구는 `maintenance/reports/token_validation/` 아래에 `token_shape_issues_*`, `token_repair_worklist_*`, `token_style_review_*`, `quote_issues_*`를 생성한다.
- 원인: 토큰 검수 흐름이 개선되면서 실제 산출물이 바뀌었지만 일부 문서 표현이 예전 계획을 유지하고 있다.
- 수정 방향: `workflow.md`와 `translation_guidelines.md`의 토큰 보완 설명을 현재 산출물 기준으로 갱신한다. `token_reference_latest.csv`를 계속 쓸 계획이 없다면 예전 경로 문구는 제거한다.
- 확인 방법: `rg -n "token_reference_latest|token_repair_worklist|token_shape_issues" maintenance/*.md`
