# Python 코딩 스타일 가이드

범용 Python 프로젝트를 위한 코딩 규칙입니다. 널리 권장되는 표준
[PEP 8](https://peps.python.org/pep-0008/) · [PEP 257](https://peps.python.org/pep-0257/) ·
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)를 따릅니다.

> **대원칙: 최소 변경.** 기존 코드를 손볼 때는 작업과 직접 관련된 줄만 바꿉니다.
> 멀쩡한 코드를 "개선"하거나 주변 포맷·주석을 함께 고치지 마세요. 이 가이드는
> *새로 쓰는 코드*의 기준이며, 기존 코드를 일괄 재작성하라는 뜻이 아닙니다.

이 저장소에서의 기준 구현체와 프로젝트 고유 규약(인코딩·보존 토큰·오케스트레이션
등)은 [PROJECT_CONVENTIONS.md](PROJECT_CONVENTIONS.md)에 따로 정리되어 있습니다.

---

## 1. 파일 머리말

실행 가능한 스크립트는 다음 순서로 시작합니다.

```python
#!/usr/bin/env python3
"""한 줄 요약 — 이 모듈/도구가 무엇을 하는지.

필요하면 빈 줄 뒤에 동작 방식·입출력·주의사항을 설명한다.
파일을 쓰는 도구라면 기본 동작이 읽기 전용(dry-run)인지 쓰기인지 밝힌다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
```

- **shebang**은 실행 스크립트에 한해 `#!/usr/bin/env python3`로 통일합니다.
- 모듈 docstring(PEP 257)은 `"""..."""`로 작성하고, 첫 줄은 마침표로 끝나는 한 문장
  요약으로 합니다.
- `from __future__ import annotations`를 둡니다. 타입 힌트를 지연 평가해
  `list[dict[str, object]]` 같은 표기를 런타임 비용 없이 쓸 수 있습니다.

## 2. import

- **표준 라이브러리 → 서드파티 → 로컬 모듈** 순서로 그룹을 나누고, 그룹 사이는
  빈 줄로 구분합니다. 각 그룹 안에서는 알파벳순으로 정렬합니다.
- 패키지·모듈 단위로 import 합니다. `typing`에서 가져올 게 있으면
  `from typing import Any` 처럼 심볼만 가져오고 `import typing` 식은 피합니다.
- 와일드카드 import(`from x import *`)는 쓰지 않습니다.

## 3. 명명 규칙

| 대상 | 표기 | 예 |
| --- | --- | --- |
| 모듈·파일 | `lower_snake_case.py` | `run_pipeline.py` |
| 함수·변수 | `lower_snake_case` | `parse_args`, `keys_dir` |
| 상수(모듈 최상단) | `UPPER_SNAKE_CASE` | `CACHE_VERSION` |
| 클래스 | `CapWords` | `TokenMask` |
| 내부 전용 | 앞에 `_` | `_read_config` |

한 글자 이름은 루프 카운터(`i`)와 예외 변수(`exc`)에만 씁니다. 그 외에는 의미가
드러나는 이름을 씁니다.

## 4. 타입 힌트

- 공개 함수의 인자와 반환값에 타입 힌트를 답니다. 한 모듈 안에서는 힌트 유무를
  일관되게 유지합니다.
- `Optional[X]` 대신 `X | None`을 씁니다(`from __future__ import annotations` 사용 시
  구버전에서도 안전).
- 단순한 구조는 `dict[str, object]` / `list[str]`처럼 내장 제네릭을 직접 씁니다.

## 5. Docstring

- 공개 API·비자명한 로직·일정 규모 이상의 함수에는 docstring이 **필수**입니다.
  한 줄짜리 자명한 헬퍼는 생략해도 됩니다.
- 첫 줄은 마침표로 끝나는 한 문장 요약. 세부 설명은 빈 줄 뒤에 잇습니다.
- **한 프로젝트 안에서는 docstring 언어를 하나로 통일합니다**(한국어 또는 영어).
  여러 언어를 섞지 마세요.
- "코드가 무엇을 하는지" 옮겨 적지 말고 **왜 그렇게 했는지**·어떤 함정이 있는지를
  설명합니다.

```python
def parse_vdf_paths(path: Path) -> list[Path]:
    """단순 VDF 파일에서 경로 항목을 뽑는다.

    필요한 항목만 가져오면 되므로 전체 VDF 파서 대신 좁은 정규식을
    의도적으로 쓴다.
    """
```

## 6. 레이아웃·포맷

- 들여쓰기는 **스페이스 4칸**. 탭 금지.
- 한 줄은 **100자 이내**를 목표로 합니다(PEP 8의 79자를 완화한 실용 기준). 단,
  긴 문자열을 억지로 쪼개 가독성이 떨어지는 경우는 예외 — **가독성이 길이 규칙보다
  우선**합니다.
- 줄을 나눌 때는 백슬래시(`\`) 대신 괄호 안 묵시적 연결을 씁니다.
- 함수 정의 사이는 빈 줄 2개, 함수 내부 논리 블록 사이는 빈 줄 1개.
- 포맷팅은 손으로 다투지 말고 **Black/Ruff** 같은 도구에 맡기는 것을 권장합니다.

## 7. 함수 크기와 구조

- **작고 한 가지 일만 하는 함수**를 선호합니다. 40줄을 넘기고 구조를 해치지 않고
  쪼갤 수 있으면 쪼갭니다.
- `main()`은 **오케스트레이션만** 담당하게 유지합니다. 인자 파싱(`parse_args`),
  실제 작업, 출력·리포트는 각각 별도 함수로 빼서 흐름이 읽히게 합니다.
- 실행 진입점은 main 가드로 감쌉니다. `main()`은 종료 코드(int)를 반환하고,
  성공은 `0`·실패는 `1`로 통일합니다.

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

## 8. CLI (argparse)

- 인자 정의는 `parse_args() -> argparse.Namespace` 한 함수에 모읍니다.
- 모든 옵션에 `help=`를 답니다. 특히 **파일을 쓰는 옵션**은 기본값이 읽기 전용인지
  쓰기인지 help에 명시합니다.
- 안전 기본값: **쓰기는 옵트인**. 플래그 없이 실행하면 리포트만 만들고 실제 산출물은
  건드리지 않는 것을 기본으로 합니다.

## 9. 파일 입출력과 인코딩

- 파일을 열 때 **인코딩을 항상 명시**합니다(`encoding="utf-8"`). 플랫폼 기본 인코딩에
  의존하지 마세요.
- 외부에서 들어온, 신뢰할 수 없는 텍스트는 BOM·깨진 바이트를 견디게 읽습니다
  (`encoding="utf-8-sig"`, 필요 시 `errors="replace"`).
- 경로는 문자열 연결 대신 `pathlib.Path`로 다룹니다.
- 변환 로직은 **데이터의 의미를 보존**해야 할 부분(이스케이프·특수 토큰·서식 코드 등)을
  깨뜨리지 않는지 항상 확인합니다.

## 10. 동시성

- 입출력·자식 프로세스 위주의 작업은 스레드(`concurrent.futures.ThreadPoolExecutor`)로
  병렬화합니다.
- 워커 함수는 **공유 가변 상태를 변경하지 않도록** 설계해 스레드 안전성을 확보합니다.
  결과는 반환값으로 모아 메인 스레드에서 합칩니다.
- 외부 명령은 `sys.executable`/명시적 경로로 호출하고(`"python"` 하드코딩 금지),
  실행 결과(`returncode`/`stdout`/`stderr`)를 한 곳에서 구조화해 수집합니다.

## 11. 에러 처리

- 빈 `except:`나 광범위한 `except Exception` 남용을 피합니다. 잡아야 하면 구체 예외를
  잡고(`json.JSONDecodeError`, `ValueError` 등), 격리 지점이 아니면 다시 던집니다.
- 사용자 입력·환경 오류로 더 진행할 수 없으면 `raise SystemExit("사람이 읽을 안내")`로
  깔끔히 종료합니다. 안내에는 **고치는 방법**을 함께 적습니다.
- `try` 블록은 실패할 수 있는 최소 범위만 감쌉니다.

## 12. 주석

- "코드를 그대로 설명"하지 말고 **왜**를 적습니다.
- 인라인 주석은 코드에서 최소 2칸 띄웁니다.
- 유지보수자가 놓치기 쉬운 약속(예: 캐시 포맷이 바뀌면 버전을 올려야 한다)은 그 자리에
  주석으로 남깁니다.

## 13. 커밋 전 검증

> **종속성 구분.** 도구를 **사용**만 하는 사람은 `requirements.txt`(런타임)만 설치하면
> 되고, 아래 린터·포매터는 필요 없습니다. 코드를 **고치는** 사람만 개발 종속성
> `requirements-dev.txt`(`ruff` 등)를 추가로 설치합니다. 린터는 어디까지나 **선택**이며,
> 없어도 도구는 그대로 동작합니다.

커밋 전 최소한 구문 검사와 `--help`는 확인합니다(표준 라이브러리만으로 가능).

```powershell
# 구문 검사 — 추가 설치 불필요
python -m py_compile <바꾼파일>.py

# CLI 도구라면 인자 정의 실수를 빨리 잡기 위해
python <바꾼파일>.py --help
```

개발 종속성을 설치했다면 정적 검사·포맷도 돌립니다.

```powershell
pip install -r tools/requirements-dev.txt   # 최초 1회 (개발자만)

python -m ruff check <바꾼파일>.py            # 정적 검사
python -m ruff format <바꾼파일>.py           # 포맷
```
