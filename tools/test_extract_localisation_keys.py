#!/usr/bin/env python3
"""extract_localisation_keys.strip_trailing_comment 동작 고정 테스트.

닫는 따옴표 판정(뒤에 공백/`#` 주석만 오는 첫 비이스케이프 `"`)과
이스케이프 `\\"`·이스케이프 안 된 내장 따옴표 보존을 검증한다.
파일 I/O·API 호출 없음.

사용:
  python3 tools/test_extract_localisation_keys.py   # 실패 있으면 목록 출력 후 exit 1
"""

from __future__ import annotations

from extract_localisation_keys import strip_trailing_comment

Case = tuple[str, str, str]

_CASES: list[Case] = [
    ("plain", '"hello"', '"hello"'),
    ("trailing comment removed", '"val" # comment', '"val"'),
    ("trailing comment without space", '"val"# comment', '"val"'),
    ("trailing whitespace removed", '"val"   ', '"val"'),
    ("escaped quote preserved", r'"say \"hi\" now"', r'"say \"hi\" now"'),
    ("escaped quote + comment", r'"say \"hi\"" # c', r'"say \"hi\""'),
    ("embedded unescaped quotes kept", '"a "solve" b"', '"a "solve" b"'),
    ("embedded quotes + comment", '"a "solve" b" # note', '"a "solve" b"'),
    ("embedded quote inside comment ignored", '"val" # say "x"', '"val"'),
    (
        "real case ending with section sign",
        '"§B"What is it you wish to do?"§!"',
        '"§B"What is it you wish to do?"§!"',
    ),
    ("no leading quote unchanged", "raw value # c", "raw value # c"),
    ("empty value unchanged", "", ""),
    ("unclosed quote unchanged", '"open', '"open'),
]


def main() -> int:
    failures = []
    for label, value, expected in _CASES:
        got = strip_trailing_comment(value)
        if got != expected:
            failures.append((label, expected, got))
    for label, expected, got in failures:
        print(f"FAIL {label}")
        print(f"  - expected {expected!r}, got {got!r}")
    print(f"cases={len(_CASES)} passed={len(_CASES) - len(failures)} failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
