# 번역 실패 사례 모음

최종 갱신: 2026-06-03

AI 번역 실행 중 실제로 관찰된 실패 패턴을 정리한다. 각 사례마다 원인과 현재 대응 방법을 기록한다.

역할: **실패 사례 아카이브**. 재발 방지에 필요한 원인·재현 패턴·대응만 기록한다.
현재 작업 큐는 `../../../HANDOFF.md`, 도구 개선 목록은 `tooling_known_issues.md`, 토큰 검출
회귀 케이스는 `../fixtures/token_detection_cases.jsonl`에 둔다.

---

## 1. 아이콘 토큰이 변수 토큰으로 교체됨 (마커 충돌)

- 상태: 수정됨 (2026-05-25 — `__ICON_xxx__` / `__DOLLAR_xxx__` prefix 도입)
- 재현 키: `job_elven_dragon_researcher_effect_desc`
- 원문 패턴: `£trade£ §Y$trade$§!` — 같은 내부 이름(`trade`)을 가진 아이콘·변수 토큰이 공존
- 실패 양상: 복원 후 `£trade£`가 `$trade$`로 바뀌거나 반대로 치환됨
- 원인: `£trade£`와 `$trade$`가 모두 `__trade__` 단일 마커로 치환되어 복원 시 어느 쪽으로 돌아올지 불확정
- 수정: `£trade£` → `__ICON_trade__`, `$trade$` → `__DOLLAR_trade__`로 타입 prefix 구분

---

## 2. AI가 마커를 번역문에 흡수·누락

- 상태: 부분 완화 (마커 방식 개선으로 빈도 감소, 근본 해결 불가)
- 재현 키: `ap_esap_hive_devouring_tooltip` 외 다수
- 원문 패턴: `£pop£ §YPop§!` 처럼 아이콘과 색상 코드가 붙어 있는 경우
- 실패 양상: `__pop__` 마커가 번역 과정에서 누락되거나 주변 텍스트에 흡수됨
- 원인: AI가 마커를 번역해야 할 단어로 인식하거나 맥락상 생략 가능하다고 판단
- 현재 대응: 재시도(최대 3회) → 그래도 안 되면 `hard_token_mismatch` 기록 → `--from-worklist` 재번역
- 잔여 위험: 재시도에도 지속적으로 누락되는 경우 수동 처리 필요

---

## 3. AI가 프롬프트 지시문을 번역문 앞에 그대로 출력 (프롬프트 에코)

- 상태: 수정됨 (2026-05-25 — `strip_prompt_echo()` 자동 감지·제거)
- 재현 키: `giga_frameworld_expand_desc_cost` 외
- 실패 양상: 번역 결과가 `"__ICON_xxx__ 형태의 마커는 Stellaris 게임 토큰을... key: giga_frameworld_expand_desc_cost   실제번역"` 형태로 반환됨
- 원인: AI가 시스템 프롬프트 내용을 번역문 앞에 복사해 출력
- 수정: `key: <키명>` 패턴 감지 후 그 뒤 텍스트만 추출

---

## 4. `[...]` 표현식 내용이 수학 용어 등으로 연상되어 무한 반복 출력

- 상태: 수정됨 (2026-05-25 — `[...]`는 순번 마커 `__B0__`로 치환)
- 재현 키: `mem_primitives.101.desc`
- 원문 패턴: `[pre_ftl_country.GetSpeciesNamePlural]`
- 실패 양상: `__pre_ftl_country.GetSpeciesNamePlural__` 마커 안의 `pre_ftl_country`를 AI가 맥락 없이 처리하다가 "원주율 원주율 원주율..." 형태로 무한 반복 출력
- 원인: 긴 스크립트 표현식을 내용 그대로 마커화하면 AI가 내용을 번역 대상으로 오인
- 수정: `[...]` 표현식 전체를 `__B0__`, `__B1__` 순번 마커로 치환

---

## 5. 원본 모드 YML 오타 — 닫는 `£` 누락 + 공백 삽입

- 상태: 수정됨 (2026-06-03 — `token_parser` 범위 인식 파서로 전환 + 마스킹 복원 시 정상화)
- 예시: `£unity`(완전 누락), `£opinion  §YOpinion§!`, `£minerals .`, `£energy upkeep`,
  `£dna £blocker£`(deposit 아이콘) — 단어·구두점·줄끝 앞 등 모든 형태
- 수정: 정규식 TOKEN_RE 대신 `token_parser.parse_tokens`가 닫힘 없는 `£word`를
  `(?=$|[\s§.,;:!?...])` 룩어헤드로 모두 `unclosed_icon`으로 인식 → 마스킹으로 AI 손상 차단.
  복원 시 정상형 `£word£`로 자동 교정한다(`protect_tokens`가 `span.normalized` 사용).
  닫힘 없는 £ 24종 전수 조사 결과 전부 원본 모드 오타(의도된 케이스 0)로 확인됨.
- 참고: 영어 원문은 추출 원본이라 보존 → `validate`가 `source_unclosed`(style)로 추적.
  비번역 경로(import 등)는 `fix_quote_issues --only-unclosed-icons`로 일괄 정상화.

---

## 6. `$TABBED_NEW_LINE$` 토큰 번역 중 누락 또는 `\n`으로 대체

- 상태: 미확인 (재현 빈도 낮음)
- 재현 키: `origin_tooltip_elven_celestial_throne_effects`, `origin_tooltip_elven_foundations_effects`
- 실패 양상: `$TABBED_NEW_LINE$`이 번역 후 사라지거나 `\n`으로 대체됨 (token_delta: dollar_ref 누락 + escaped_newline 추가)
- 원인 추정: 마커 `__DOLLAR_TABBED_NEW_LINE__`이 레이아웃 지시어처럼 보여 AI가 의미상 `\n`으로 대체하려는 경향
- 현재 대응: 재시도로 대부분 해소됨, 미해소 시 `hard_token_mismatch`

---

## 8. 아이콘 토큰이 번역 후 변수 토큰으로 바뀜 (마커 수정 전 구 버전 잔류 사례)

- 상태: 수정됨 (이슈 1과 동일 원인, 마커 충돌 → `__ICON_xxx__` 도입으로 해결)
- 재현 키: `esc_options_preset_everything_but_buildings`, `esc_options_page_ai_enable_eco_boost`
- 원문 패턴: `£sr_dark_matter£ §Y$sr_dark_matter$§!` — 같은 이름 아이콘+변수 공존
- 실패 양상: `£sr_dark_matter£` → `$sr_dark_matter$`로 복원되어 아이콘이 변수로 교체됨
- 비고: `__ICON_xxx__` / `__DOLLAR_xxx__` prefix 도입 후 재번역 시 해소 예정

---

## 9. AI가 토큰 내용을 한국어로 번역 (아이콘 토큰 안의 단어 번역)

- 상태: 수정됨 (2026-06-03 — 이슈 5와 동일 원인, 파서 마스킹으로 해결)
- 재현 키: `decision_esap_industry_modifier_effect` 외
- 원문 패턴: `£minerals  §YMinerals§!` (이슈 5 오타 포함), `£food  §YFood§!`
- 실패 양상: 번역 결과에서 `£광물£`, `£식량£`처럼 아이콘 토큰 내부 이름이 한국어로 번역됨
- 원인: 오타로 인해 마스킹이 안 된 토큰을 AI가 번역 대상으로 처리
- 수정: `token_parser`가 닫힘 없는 `£minerals`도 `unclosed_icon`으로 인식해 마스킹 →
  AI가 토큰 내부를 못 건드린다. 복원 시 `£minerals£`로 정상화.

---

## 10. 로그에서 `\xa3opinion\xa3`로 보이는 케이스 — 실제로는 터미널 인코딩 깨짐

- 상태: 해프닝 (실제 파일은 정상 UTF-8)
- 배경: dry-run-with-api 출력에서 `\xa3opinion\xa3`처럼 보여 latin-1 인코딩 오류로 오해
- 실제 원인: 터미널(cp949)이 UTF-8 `£`(U+00A3, `\xc2\xa3`)를 깨뜨려 출력한 것
- 실제 파일 확인: `raw.count(bytes([0xc2, 0xa3])) = 720` — 정상 UTF-8 `£`
- 결론: 불일치 5건은 모두 `£opinion  §Y` 오타 패턴(닫는 `£` 없이 공백)이 원인 — 이슈 5 범주로 처리

---

## 11. `§G텍스트§!` 패턴 번역 중 색상코드 누락

- 상태: 미해결 (재시도로도 개선 안 됨, 이슈 2 색상코드 변형)
- 재현 키: `tr_est_archivist_2_desc`, `tr_est_proselytism_5_desc`
- 원문 패턴: `§Gboosts§!`, `§RWar§!` — `§Y` 없이 `§G`/`§R`로 바로 시작하는 색상 강조 텍스트
- 실패 양상: `color_code: 누락=['§!', '§G']` 또는 `누락=['§!', '§R']` — 색상코드가 번역 후 사라짐
- 원인 추정: `§Y` 다음 변수/아이콘이 오는 일반 패턴과 달리, 순수 텍스트를 색상으로만 감싼 경우 AI가 마커 유지를 놓침
- 현재 대응: 3회 재시도 후 `hard_token_mismatch` → 수동 처리
- 구분: 이슈 2(아이콘 마커 누락)의 색상코드 전용 변형

---

## 12. `giga_modifiers_l_korean.yml` job efficiency 표시 순서 오류

- 상태: 수정됨 (2026-05-25)
- 영향 파일: `localisation/korean/giga_modifiers_l_korean.yml`
- 현상: 대규모 물류 시설 등 Gigastructural Engineering 건물 설명에서 modifier가 `"직업 효율성 초인장 소재 기술공: +98%"` 순서로 표시됨
- 바른 표시: `"초인장 소재 기술공 직업 효율성: +98%"` (바닐라 기준 `{직업명} 직업 효율성`)
- 원인: 영어 원본이 `"$BONUS_WORKFORCE_FOR$ {직업명}"` 순서로 정의되어 있고, 한국어 파일이 그대로 `$BONUS_WORKFORCE_FOR$`(`직업 효율성`)를 앞에 두는 구조를 유지했음. 바닐라 한국어는 `"{직업명} 직업 효율성"` 순서를 사용함
- 수정 내용: `$BONUS_WORKFORCE_FOR$ X` → `X 직업 효율성` 으로 47개 키 일괄 변환. tooltip(`_tt`) 패턴도 동일하게 처리
- 재발 방지: 기가스트럭처 계열 신규 `bonus_workforce_mult` 키 추가 시 `$BONUS_WORKFORCE_FOR$` 대신 `{직업명} 직업 효율성` 하드코딩 사용

---

## 13. `​`(zero-width space)가 한국어 폰트에서 `▣`로 렌더링

- 상태: 수정됨 (2026-05-25)
- 영향 파일: `localisation/korean/giga_l_korean.yml`, `giga_replace_l_korean.yml` (2개), `replace/giga_replace_l_korean.yml`
- 현상: 메가스트럭처 이름 앞에 `▣` 깨진 기호가 표시됨 (예: `▣그랜드 아카이브`)
- 원인: `gc_kilo`, `gc_mega`, `gc_giga`, `gc_crisis`, `gc_proj`, `gc_tera`, `gc_blokkat` 키가 `§B​§!` 형태로 정의되어 있었음. `​`(U+200B)는 영문 폰트에서 투명하지만 한국어 폰트에서 지원되지 않아 대체 문자 박스로 렌더링됨
- 수정 내용: 7개 키에서 `​` 제거 → `§B§!` 형태로 변경. `gc_crisis`는 인코딩 손상(`∽R​∽!`)도 함께 수정. `grand_archive_0` 이름 키에서 `$gc_kilo$` 접두사 제거
- 확인: 영문판에서 메가스트럭처 이름 앞에 기호 없이 표시되는 것을 확인 — `gc_*` 키는 색상만 적용하는 빈 마커로 설계된 것임

---

## 7. `fix_quote_issues.py` 반복 실행 시 추가 보정 발생

- 상태: 정상 동작 (버그 아님, 동작 특성)
- 현상: 첫 실행에서 25건 보정 후 재실행 시 0건 — 그러나 새 validate 없이 같은 CSV로 재실행하면 항상 0건
- 원인: 보정 결과가 새 불균형을 만드는 경우가 있어 validate → fix 사이클을 반복해야 추가 케이스가 나옴
- 권장 순서: `validate_auto_key_tokens.py` → `fix_quote_issues.py` 를 변화가 없을 때까지 반복
