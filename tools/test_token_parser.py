#!/usr/bin/env python3
"""Dry-run token parser detection cases from a user-editable JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from token_parser import close_unclosed_icons, extract_token_values
from validate_auto_key_tokens import classify_issue, extract_tokens

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "maintenance" / "fixtures" / "token_detection_cases.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run user-editable token parser detection cases without changing files."
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES),
        help="JSONL detection case file. Blank lines and lines starting with # are ignored.",
    )
    parser.add_argument(
        "--id",
        action="append",
        default=[],
        help="Run only matching case id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--show-passed",
        action="store_true",
        help="Print passed cases as well as failures.",
    )
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if "id" not in case:
                raise SystemExit(f"{path}:{line_number}: case is missing required id")
            case["_line_number"] = line_number
            cases.append(case)
    return cases


def check_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    text = case.get("text")
    if text is not None:
        token_values = extract_token_values(str(text))
        for kind, expected in case.get("expected_tokens", {}).items():
            actual = token_values.get(kind, [])
            if actual != expected:
                errors.append(f"{kind}: expected {expected!r}, got {actual!r}")

        if "expected_fixed" in case:
            fixed, _changed = close_unclosed_icons(str(text))
            if fixed != case["expected_fixed"]:
                errors.append(f"fixed: expected {case['expected_fixed']!r}, got {fixed!r}")

    if "english_value" in case or "korean_value" in case:
        english = str(case.get("english_value", ""))
        korean = str(case.get("korean_value", ""))
        (
            severity,
            issue_types,
            _hard_missing,
            _hard_extra,
            _hard_order_only,
            _style_missing,
            _style_extra,
        ) = classify_issue(extract_tokens(english), extract_tokens(korean))

        if "expected_severity" in case and severity != case["expected_severity"]:
            errors.append(f"severity: expected {case['expected_severity']!r}, got {severity!r}")
        if "expected_issue_types" in case:
            expected_issue_types = set(case["expected_issue_types"])
            actual_issue_types = set(issue_types)
            if actual_issue_types != expected_issue_types:
                errors.append(
                    "issue_types: expected "
                    f"{sorted(expected_issue_types)!r}, got {sorted(actual_issue_types)!r}"
                )

    return errors


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases)
    cases = load_cases(cases_path)
    if args.id:
        wanted = set(args.id)
        cases = [case for case in cases if case["id"] in wanted]

    failures: list[tuple[dict[str, Any], list[str]]] = []
    for case in cases:
        errors = check_case(case)
        if errors:
            failures.append((case, errors))
            continue
        if args.show_passed:
            print(f"PASS {case['id']}")

    for case, errors in failures:
        print(f"FAIL {case['id']} (line {case.get('_line_number')})")
        for error in errors:
            print(f"  - {error}")

    print(f"cases={len(cases)} passed={len(cases) - len(failures)} failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
