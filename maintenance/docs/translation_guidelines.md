# Stellaris 한국어 번역 지침

최종 갱신: 2026-06-03

번역 작업 시 지켜야 하는 규칙을 정리한다.
작업 순서와 명령어는 `workflow.md`, 도구 옵션은 `tools_overview.md`를 참조한다.

---

## 기본 원칙

- `korean_value`에만 번역 결과를 넣는다. `key`와 `english_value`는 수정하지 않는다.
- 원문이 비어 있으면 번역하지 않는다.
- 토큰은 번역하지 않고 원형을 유지한다.
- CSV 셀 안의 줄바꿈은 실제 줄바꿈 금지 — `\n` 리터럴로 저장한다.
- 인코딩: UTF-8 with BOM.

---

## 토큰 규칙

참조: <https://stellaris.paradoxwikis.com/Localisation_modding>

토큰은 게임이 런타임에 치환하거나 색상·아이콘·링크·값을 표시하기 위한 문법이다.
원문의 토큰은 `korean_value`에서도 원형 그대로 유지한다. 삭제·변형·번역 금지.

### 토큰 종류

| 토큰 형식 | 의미 | 처리 |
|---|---|---|
| `$planet$`, `$energy$`, `$VALUE\|*1$` | 다른 키 참조 또는 변수 | 그대로 유지 |
| `£energy£`, `£alloys£` | 아이콘 | 그대로 유지 |
| `[Root.GetName]`, `['concept_x']` | 스크립트 표현식 | 그대로 유지 |
| `§Y`, `§R`, `§G`, `§H` 등 | 색상 코드 시작 | 그대로 유지 |
| `§!` | 색상 코드 종료 | 그대로 유지 |
| `\n`, `\t`, `\"`, `\\` | 이스케이프 문자 | 위치·개수 그대로 유지 |

### 색상 코드 쌍 규칙

`§X...§!` 구조에서 열기 코드와 닫기 코드는 반드시 쌍으로 유지한다.

공식 색상 코드 전체 목록: `W T g L P R S H K Y I G V E C B M c v d r l !`
비공식(모드 자체 확장, 번역 파이프라인에는 영향 없음): `t O f F`

```text
좋은 번역: §H참고§!: 이 선택지는 위험합니다.
나쁜 번역: 참고: 이 선택지는 위험합니다.    ← §H...§! 삭제됨
```

`§!`가 연속으로 나오는 경우(`§!!§!`):

- 각각 독립적인 닫기 코드다. 원문의 `§!` 개수를 정확히 복사한다.
- 예: `§Y[GetShroudPatron]§!!§!` → 번역 시에도 `§Y[GetShroudPatron]§!!§!` 유지 (`§Y` 닫기 + `!` 느낌표 + `§R` 닫기)

### $...$ 처리 기준

`$...$`는 다른 로컬라이징 키를 불러오는 참조인 경우가 많다. `$...$` 안의 내용은 번역하지 않는다.

```text
좋은 처리:
  우리는 $domesticated_crystal$을 만들기 위해 수정체 생명체를 선택했습니다.

나쁜 처리:
  우리는 수정체 생명체를 만들기 위해 선택했습니다.    ← 토큰 삭제
  우리는 $수정체 생명체$를 만들기 위해 선택했습니다.  ← 토큰 내용 번역
```

### 토큰 전용 행

값 전체가 토큰 조합으로만 이루어진 행은 `korean_value`도 원문과 동일하게 둔다.

```text
$ap_aggressive_hivemind$
$ap_aggressive_hivemind_desc$\n\n$ap_aggressive_hivemind_tooltip$
```

실제 번역은 참조 대상 키(`ap_aggressive_hivemind` 등)에서 처리한다.

---

## 번역 스타일

공식 Stellaris 한국어 번역 (`Stellaris/localisation/korean/`)을 기준으로 한다.

### 어미·경어

| 맥락 | 형식 |
|---|---|
| 설명문·이벤트 본문 | `~습니다`, `~입니다` (합쇼체) |
| UI 레이블·이름 | 명사형 (어미 없음) |
| 선택지 | `~합니다`, `~겠습니다` |

### 고유명사 조어

- 짧은 이름(기원·전통·특성 등)은 명사구로 번역한다.
  - `"Ocean Paradise"` → `"해양 낙원"`, `"Shroud-Forged"` → `"장막 단조체"`
- 한자어 기반 조어를 선호한다.
- SF 맥락에서 성별 중립 표현을 우선한다.
- 어색한 직역보다 게임 내 의미가 분명한 표현을 우선한다.

### 공식 고정 용어

반드시 아래 표현으로 통일한다. 전체 목록: `../term_glossary.csv`

| 영어 | 한국어 |
|---|---|
| Empire | 제국 |
| Planet | 행성 |
| System / Star System | 성계 |
| Fleet | 함대 |
| Ship | 함선 |
| Leader | 지도자 |
| Species | 종족 |
| Pops | 팝 |
| Ethics | 윤리관 |
| Civics | 사회 제도 |
| Origin | 기원 |
| Tradition | 전통 |
| Ascension Perk | 승격 특전 |
| Edict | 칙령 |
| Habitat | 거주지 |
| Megastructure | 거대 구조물 |
| Relic | 유물 |
| Modifier | 보정치 |
| Upkeep | 유지비 |
| Alloys | 합금 |
| Consumer Goods | 소비재 |
| Rare Crystals | 희귀 결정 |
| Volatile Motes | 휘발성 먼지 |
| Exotic Gases | 이국적 기체 |
| Nanites | 나노 로봇 |
| Dark Matter | 암흑 물질 |
| Living Metal | 생체 금속 |
| Zro | 즈로 |

---

## CSV 따옴표 규칙

`english_value`가 따옴표로 감싸여 있으면 `korean_value`도 반드시 같은 형태로 감싼다.

```text
좋은 예: nanite_factory_DESC,"""The §Y$NAME$§! is a factory.""","""§Y$NAME$§!는 공장입니다."""
나쁜 예: nanite_factory,"""$NAME_Nanite_Factory$""", $NAME_Nanite_Factory$
```

따옴표 불균형·누락은 `fix_quote_issues.py`로 자동 보정한다. 상세: `tools_overview.md`

---

## 검수 기준

번역 후 아래 항목을 확인한다.

- 빈 `korean_value`가 남아 있지 않은가
- 원문과 번역문의 하드 토큰(`$...$`, `£...£`, `[...]`) 개수와 원형이 같은가
- `§X` 열기와 `§!` 닫기 쌍이 맞는가
- `english_value`가 따옴표로 감싸여 있는데 `korean_value`에 따옴표가 없는 행이 있는가
- CSV 셀 안에 실제 줄바꿈이 들어가지 않았는가
- UTF-8 BOM이 유지되는가

검수 도구 사용법: `tools_overview.md` → `review_report.py`, `validate_auto_key_tokens.py`
