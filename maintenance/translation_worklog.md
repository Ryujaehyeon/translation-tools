# 자동키 번역 작업내역

최종 갱신: 2026-05-25

이 문서는 번역 작업의 주요 결정·변경 사항을 기록한다. 상세 진행률은 `maintenance/translation_progress_tree.md`를 기준으로 본다.

## 기준 문서

- 번역 지침: `maintenance/translation_guidelines.md`
- 전체 모드/파일별 번역률 트리: `maintenance/translation_progress_tree.md`
- 빈 원문 키 목록: `maintenance/reports/translation_work/empty_english_keys.csv`

## 작업 규칙 요약

- `key`, `english_value`, `korean_value` 컬럼 구조와 행 순서를 유지한다.
- `english_value`가 실제 원문을 가진 행만 번역해 빈 `korean_value`에 넣는다.
- 이미 값이 있는 `korean_value`는 사용자가 요청하지 않는 한 수정하지 않는다.
- `english_value`가 비어 있거나 `""`뿐인 행은 임의로 번역하지 않고 빈 원문 키 목록에 기록한다.
- `$...$`, `[Root.GetName]`, `§Y`, `§!`, `£society£`, `\n`, `['concept_x']` 같은 Stellaris 토큰은 원문 순서대로 보존한다.
- 작업 후 토큰 순서, 따옴표 구조, 남은 원문 있는 행 수를 확인한다.

## 현재 잔여 요약

자세한 파일별 수치는 `maintenance/translation_progress_tree.md`를 기준으로 본다.

- `more_events_mod__727000451`: 진행 중 (~9,000행 잔여, 가장 큰 모드)
- `plentiful_traditions_4_2_x__1311725711`: 진행 중 (~1,700행 잔여)
- `psionic_species_expansion__2461999384`: 진행 중 (~1,600행 잔여)
- `merged_leader_levels__2123646681`: 진행 중 (~1,500행 잔여)
- 그 외 소규모 잔여: `stellaris_101`, `trait_diversity`, `otter_editor` 등

## 변경 이력

| 날짜 | 내용 |
| --- | --- |
| 2026-05-25 | 음질량 용어 통일 (giga_ehof 65행, 참조 모드 기준) |
| 2026-05-25 | `glossary_pd.csv` → `--extra-glossary` 옵션으로 연결 |
| 2026-05-25 | Empty response → RuntimeError 변경 (행 단위 스킵, 파일 중단 방지) |
| 2026-05-25 | 파일명 정리 (ai_auto_translate→translate_keys, translation_tool→export_localisation 등) |
