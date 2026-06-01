"""Validate Stellaris localisation tokens in translation key CSV files.

The checker is read-only. It is designed to reduce review noise by splitting
token problems into actionable groups:

- critical: `$...$`, `£...£`, or `[...]` token count differs.
- hard_order: the same hard tokens exist, but their order differs.
- style: only `§...` or explicit `\\n` shape differs.

Default outputs are written under maintenance/reports/token_validation/.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from tool_config import translation_keys_root


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTO_KEYS = translation_keys_root()
DEFAULT_REPORT_DIR = ROOT / "maintenance" / "reports" / "token_validation"


TOKEN_PATTERNS = {
    "dollar_ref": re.compile(r"\$[^$\s]+\$"),
    "icon": re.compile(r"\u00a3[^\u00a3\s]+\u00a3"),
    "bracket_expr": re.compile(r"\[[^\]\n]+\]"),
    "color_code": re.compile(r"\u00a7[A-Za-z0-9!#]"),
    "escaped_newline": re.compile(r"\\n"),
}

# \u00a7(U+00A7) \ub300\uc2e0 \uc4f0\uc774\ub294 \uc720\uc0ac \uc720\ub2c8\ucf54\ub4dc \ubb38\uc790 \u2014 AI \ubc88\uc5ed \uacb0\uacfc \uc624\uc5fc \uac10\uc9c0\uc6a9
SECTION_SIGN_LOOKALIKE_RE = re.compile(r"[\u223d\u2248\uff5e\u223c][A-Za-z!_]")

HARD_TOKEN_TYPES = ("dollar_ref", "icon", "bracket_expr")
STYLE_TOKEN_TYPES = ("color_code", "escaped_newline")

SEVERITY_PRIORITY = {
    "critical": 1,
    "hard_order": 2,
    "style": 3,
}


@dataclass
class QuoteIssue:
    mod: str
    file: str
    line_number: int
    key: str
    field: str          # 문제가 발생한 열 (english_value / korean_value)
    issue_type: str     # "imbalance" | "missing"
    leading: int        # 앞 따옴표 개수 (imbalance일 때만 의미 있음)
    trailing: int       # 뒤 따옴표 개수 (imbalance일 때만 의미 있음)
    english_value: str  # 원본 english_value (보정 참고용)
    raw_value: str      # 문제가 있는 셀의 원본 값


@dataclass
class TokenIssue:
    mod: str
    file: str
    line_number: int
    key: str
    severity: str
    priority: int
    issue_types: list[str]
    hard_missing: dict[str, list[str]]
    hard_extra: dict[str, list[str]]
    hard_order_only: dict[str, list[str]]
    style_missing: dict[str, list[str]]
    style_extra: dict[str, list[str]]
    english_tokens: dict[str, list[str]]
    korean_tokens: dict[str, list[str]]
    english_value: str
    korean_value: str


def check_quote_balance(value: str) -> tuple[int, int] | None:
    """앞뒤 따옴표 개수가 불균형하면 (leading, trailing) 반환, 정상이면 None.
    따옴표가 아예 없는 경우는 이 함수로 판단하지 않는다 — check_missing_quotes 참고.
    """
    stripped = value.strip()
    if not stripped:
        return None
    leading = len(stripped) - len(stripped.lstrip('"'))
    trailing = len(stripped) - len(stripped.rstrip('"'))
    if leading == 0 and trailing == 0:
        return None
    if leading == trailing:
        return None  # 균형 — 정상
    return leading, trailing


def check_missing_quotes(english_value: str, korean_value: str) -> bool:
    '''english_value가 따옴표로 감싸여 있는데 korean_value는 그렇지 않으면 True.

    정상: english=`"""값"""`, korean=`"""번역"""`
    문제: english=`"""값"""`, korean=`번역`  (따옴표 없음)
    문제: english=`"""값"""`, korean=` 번역`  (공백 후 따옴표 없음)
    '''
    e = english_value.strip()
    k = korean_value.strip()
    if not k:
        return False  # 빈 셀은 별도 처리
    e_quoted = e.startswith('"')
    k_quoted = k.startswith('"')
    return e_quoted and not k_quoted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate non-translatable Stellaris token shape in auto_keys CSV files."
    )
    parser.add_argument(
        "--auto-keys-dir",
        default=str(DEFAULT_AUTO_KEYS),
        help="Path to translation keys directory.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory where token validation reports will be written.",
    )
    parser.add_argument(
        "--mod",
        action="append",
        default=[],
        help="Limit validation to one mod folder. Can be passed multiple times.",
    )
    parser.add_argument(
        "--include-style",
        action="store_true",
        help="Include style-only rows in token_repair_worklist. By default they go only to style review.",
    )
    parser.add_argument(
        "--include-order",
        action="store_true",
        help="Include hard-token order-only rows in token_repair_worklist. Count mismatches are always included.",
    )
    return parser.parse_args()


def extract_tokens(value: str) -> dict[str, list[str]]:
    return {name: pattern.findall(value or "") for name, pattern in TOKEN_PATTERNS.items()}


def compact(tokens: dict[str, list[str]]) -> dict[str, list[str]]:
    return {name: values for name, values in tokens.items() if values}


def counter_delta(source: Iterable[str], target: Iterable[str]) -> list[str]:
    source_counter = Counter(source)
    target_counter = Counter(target)
    delta: list[str] = []
    for token, count in sorted((source_counter - target_counter).items()):
        delta.extend([token] * count)
    return delta


def has_values(delta: dict[str, list[str]]) -> bool:
    return any(delta.values())


def issue_action(severity: str) -> str:
    if severity == "critical":
        return "Copy missing hard tokens from english_value into korean_value, or remove extra hard tokens."
    if severity == "hard_order":
        return "Check hard token order against english_value; keep translated prose around tokens."
    return "Review color/highlight/newline shape only; this can be intentional."


def classify_issue(
    english_tokens: dict[str, list[str]], korean_tokens: dict[str, list[str]]
) -> tuple[str | None, list[str], dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    issue_types: list[str] = []
    hard_missing: dict[str, list[str]] = {}
    hard_extra: dict[str, list[str]] = {}
    hard_order_only: dict[str, list[str]] = {}
    style_missing: dict[str, list[str]] = {}
    style_extra: dict[str, list[str]] = {}

    for token_type in HARD_TOKEN_TYPES:
        en = english_tokens[token_type]
        ko = korean_tokens[token_type]
        missing = counter_delta(en, ko)
        extra = counter_delta(ko, en)
        if missing or extra:
            issue_types.append(token_type)
            hard_missing[token_type] = missing
            hard_extra[token_type] = extra
        elif en != ko:
            issue_types.append(f"{token_type}_order")
            hard_order_only[token_type] = en

    for token_type in STYLE_TOKEN_TYPES:
        en = english_tokens[token_type]
        ko = korean_tokens[token_type]
        missing = counter_delta(en, ko)
        extra = counter_delta(ko, en)
        if missing or extra:
            issue_types.append(token_type)
            style_missing[token_type] = missing
            style_extra[token_type] = extra

    if has_values(hard_missing) or has_values(hard_extra):
        return "critical", issue_types, hard_missing, hard_extra, hard_order_only, style_missing, style_extra
    if has_values(hard_order_only):
        return "hard_order", issue_types, hard_missing, hard_extra, hard_order_only, style_missing, style_extra
    if has_values(style_missing) or has_values(style_extra):
        return "style", issue_types, hard_missing, hard_extra, hard_order_only, style_missing, style_extra
    return None, issue_types, hard_missing, hard_extra, hard_order_only, style_missing, style_extra


def iter_csv_files(auto_keys_dir: Path, mods: set[str]) -> Iterable[Path]:
    if mods:
        for mod in sorted(mods):
            mod_dir = auto_keys_dir / mod
            if mod_dir.is_dir():
                yield from sorted(mod_dir.rglob("*_key.csv"))
        return
    yield from sorted(auto_keys_dir.rglob("*_key.csv"))


def relative_file(auto_keys_dir: Path, csv_path: Path) -> tuple[str, str]:
    rel = csv_path.relative_to(auto_keys_dir)
    mod = rel.parts[0]
    file_inside_mod = Path(*rel.parts[1:]).as_posix()
    return mod, file_inside_mod


def validate(auto_keys_dir: Path, mods: set[str]) -> tuple[list[TokenIssue], list[QuoteIssue], dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    issues: list[TokenIssue] = []
    quote_issues: list[QuoteIssue] = []
    file_stats: dict[tuple[str, str], dict[str, object]] = {}
    mod_stats: dict[str, dict[str, object]] = {}
    summary: dict[str, object] = {
        "scanned_files": 0,
        "rows_with_korean": 0,
        "rows_with_english_tokens": 0,
        "issue_rows": 0,
        "critical_rows": 0,
        "hard_order_rows": 0,
        "style_rows": 0,
        "quote_issue_rows": 0,
        "issues_by_type": defaultdict(int),
        "issues_by_mod": defaultdict(int),
        "critical_by_mod": defaultdict(int),
        "hard_order_by_mod": defaultdict(int),
        "style_by_mod": defaultdict(int),
    }

    for csv_path in iter_csv_files(auto_keys_dir, mods):
        summary["scanned_files"] += 1
        mod, file_inside_mod = relative_file(auto_keys_dir, csv_path)
        file_key = (mod, file_inside_mod)
        file_stats.setdefault(
            file_key,
            {
                "mod": mod,
                "file": file_inside_mod,
                "rows_with_korean": 0,
                "rows_with_english_tokens": 0,
                "critical_rows": 0,
                "hard_order_rows": 0,
                "style_rows": 0,
                "quote_rows": 0,
            },
        )
        mod_stats.setdefault(
            mod,
            {
                "mod": mod,
                "files_scanned": 0,
                "rows_with_korean": 0,
                "rows_with_english_tokens": 0,
                "critical_rows": 0,
                "hard_order_rows": 0,
                "style_rows": 0,
                "quote_rows": 0,
            },
        )
        mod_stats[mod]["files_scanned"] = int(mod_stats[mod]["files_scanned"]) + 1

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for line_number, row in enumerate(reader, start=2):
                key = row.get("key", "")
                english_value = row.get("english_value") or ""
                korean_value = row.get("korean_value") or ""

                # 따옴표 검사 1: 불균형 (english/korean 각각)
                for field_name, field_value in (("korean_value", korean_value), ("english_value", english_value)):
                    result = check_quote_balance(field_value)
                    if result is not None:
                        leading, trailing = result
                        quote_issues.append(QuoteIssue(
                            mod=mod,
                            file=file_inside_mod,
                            line_number=line_number,
                            key=key,
                            field=field_name,
                            issue_type="imbalance",
                            leading=leading,
                            trailing=trailing,
                            english_value=english_value,
                            raw_value=field_value,
                        ))
                        summary["quote_issue_rows"] = int(summary["quote_issue_rows"]) + 1
                        file_stats[file_key]["quote_rows"] = int(file_stats[file_key]["quote_rows"]) + 1
                        mod_stats[mod]["quote_rows"] = int(mod_stats[mod]["quote_rows"]) + 1

                # 따옴표 검사 2: english는 따옴표 있는데 korean은 없음
                if check_missing_quotes(english_value, korean_value):
                    quote_issues.append(QuoteIssue(
                        mod=mod,
                        file=file_inside_mod,
                        line_number=line_number,
                        key=key,
                        field="korean_value",
                        issue_type="missing",
                        leading=0,
                        trailing=0,
                        english_value=english_value,
                        raw_value=korean_value,
                    ))
                    summary["quote_issue_rows"] = int(summary["quote_issue_rows"]) + 1
                    file_stats[file_key]["quote_rows"] = int(file_stats[file_key]["quote_rows"]) + 1
                    mod_stats[mod]["quote_rows"] = int(mod_stats[mod]["quote_rows"]) + 1

                # §(U+00A7) 유사 문자 오염 감지 — AI가 §를 ∽ 등으로 대체한 경우
                if SECTION_SIGN_LOOKALIKE_RE.search(korean_value):
                    issues.append(TokenIssue(
                        mod=mod,
                        file=file_inside_mod,
                        line_number=line_number,
                        key=key,
                        severity="critical",
                        priority=SEVERITY_PRIORITY["critical"],
                        issue_types=["section_sign_corruption"],
                        hard_missing={},
                        hard_extra={},
                        hard_order_only={},
                        style_missing={},
                        style_extra={},
                        english_tokens={},
                        korean_tokens={},
                        english_value=english_value,
                        korean_value=korean_value,
                    ))
                    summary["critical_rows"] = int(summary["critical_rows"]) + 1
                    summary["issue_rows"] = int(summary["issue_rows"]) + 1
                    summary["issues_by_type"]["section_sign_corruption"] += 1
                    summary["issues_by_mod"][mod] += 1
                    summary["critical_by_mod"][mod] += 1
                    file_stats[file_key]["critical_rows"] = int(file_stats[file_key]["critical_rows"]) + 1
                    mod_stats[mod]["critical_rows"] = int(mod_stats[mod]["critical_rows"]) + 1

                if not korean_value.strip():
                    continue

                summary["rows_with_korean"] += 1
                file_stats[file_key]["rows_with_korean"] = int(file_stats[file_key]["rows_with_korean"]) + 1
                mod_stats[mod]["rows_with_korean"] = int(mod_stats[mod]["rows_with_korean"]) + 1

                english_tokens = extract_tokens(english_value)
                if not any(english_tokens.values()):
                    continue
                korean_tokens = extract_tokens(korean_value)

                summary["rows_with_english_tokens"] += 1
                file_stats[file_key]["rows_with_english_tokens"] = int(file_stats[file_key]["rows_with_english_tokens"]) + 1
                mod_stats[mod]["rows_with_english_tokens"] = int(mod_stats[mod]["rows_with_english_tokens"]) + 1

                (
                    severity,
                    issue_types,
                    hard_missing,
                    hard_extra,
                    hard_order_only,
                    style_missing,
                    style_extra,
                ) = classify_issue(english_tokens, korean_tokens)
                if severity is None:
                    continue

                priority = SEVERITY_PRIORITY[severity]
                issue = TokenIssue(
                    mod=mod,
                    file=file_inside_mod,
                    line_number=line_number,
                    key=key,
                    severity=severity,
                    priority=priority,
                    issue_types=issue_types,
                    hard_missing={k: v for k, v in hard_missing.items() if v},
                    hard_extra={k: v for k, v in hard_extra.items() if v},
                    hard_order_only={k: v for k, v in hard_order_only.items() if v},
                    style_missing={k: v for k, v in style_missing.items() if v},
                    style_extra={k: v for k, v in style_extra.items() if v},
                    english_tokens=compact(english_tokens),
                    korean_tokens=compact(korean_tokens),
                    english_value=english_value,
                    korean_value=korean_value,
                )
                issues.append(issue)

                summary["issue_rows"] += 1
                summary["issues_by_mod"][mod] += 1
                severity_key = f"{severity}_rows"
                summary[severity_key] += 1
                file_stats[file_key][severity_key] = int(file_stats[file_key][severity_key]) + 1
                mod_stats[mod][severity_key] = int(mod_stats[mod][severity_key]) + 1
                summary[f"{severity}_by_mod"][mod] += 1
                for issue_type in issue_types:
                    summary["issues_by_type"][issue_type] += 1

    for key in [
        "issues_by_type",
        "issues_by_mod",
        "critical_by_mod",
        "hard_order_by_mod",
        "style_by_mod",
    ]:
        summary[key] = dict(summary[key])  # type: ignore[index]

    file_rows = sorted(
        file_stats.values(),
        key=lambda row: (
            -int(row["critical_rows"]),
            -int(row["hard_order_rows"]),
            -int(row["style_rows"]),
            str(row["mod"]),
            str(row["file"]),
        ),
    )
    mod_rows = sorted(
        mod_stats.values(),
        key=lambda row: (
            -int(row["critical_rows"]),
            -int(row["hard_order_rows"]),
            -int(row["style_rows"]),
            str(row["mod"]),
        ),
    )
    return issues, quote_issues, summary, mod_rows, file_rows


def issue_to_row(issue: TokenIssue) -> dict[str, object]:
    return {
        "priority": issue.priority,
        "mod": issue.mod,
        "file": issue.file,
        "line_number": issue.line_number,
        "key": issue.key,
        "severity": issue.severity,
        "issue_types": ";".join(issue.issue_types),
        "hard_missing": json.dumps(issue.hard_missing, ensure_ascii=False),
        "hard_extra": json.dumps(issue.hard_extra, ensure_ascii=False),
        "hard_order_expected": json.dumps(issue.hard_order_only, ensure_ascii=False),
        "style_missing": json.dumps(issue.style_missing, ensure_ascii=False),
        "style_extra": json.dumps(issue.style_extra, ensure_ascii=False),
        "english_tokens": json.dumps(issue.english_tokens, ensure_ascii=False),
        "korean_tokens": json.dumps(issue.korean_tokens, ensure_ascii=False),
        "english_value": issue.english_value,
        "korean_value": issue.korean_value,
        "suggested_action": issue_action(issue.severity),
    }


def write_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            count += 1
            writer.writerow(row)
    return count


def issue_fieldnames(include_fix_columns: bool = False) -> list[str]:
    fields = [
        "priority",
        "mod",
        "file",
        "line_number",
        "key",
        "severity",
        "issue_types",
        "hard_missing",
        "hard_extra",
        "hard_order_expected",
        "style_missing",
        "style_extra",
        "english_tokens",
        "korean_tokens",
        "english_value",
        "korean_value",
        "suggested_action",
    ]
    if include_fix_columns:
        fields.extend(["fixed_korean_value", "notes"])
    return fields


def write_issue_csv(path: Path, issues: Iterable[TokenIssue]) -> int:
    return write_rows(path, issue_fieldnames(), [issue_to_row(issue) for issue in issues])


def write_worklist_csv(
    path: Path, issues: Iterable[TokenIssue], include_style: bool, include_order: bool
) -> int:
    rows = []
    for issue in issues:
        if issue.severity == "style" and not include_style:
            continue
        if issue.severity == "hard_order" and not include_order:
            continue
        row = issue_to_row(issue)
        row["fixed_korean_value"] = ""
        row["notes"] = ""
        rows.append(row)
    return write_rows(path, issue_fieldnames(include_fix_columns=True), rows)


def main() -> int:
    args = parse_args()
    auto_keys_dir = Path(args.auto_keys_dir)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    issues, quote_issues, summary, mod_rows, file_rows = validate(auto_keys_dir, set(args.mod))
    issues = sorted(
        issues,
        key=lambda issue: (
            issue.priority,
            issue.mod,
            issue.file,
            issue.line_number,
            issue.key,
        ),
    )
    quote_issues = sorted(
        quote_issues,
        key=lambda q: (q.mod, q.file, q.line_number),
    )

    issue_csv = report_dir / f"token_shape_issues_{timestamp}.csv"
    repair_csv = report_dir / f"token_repair_worklist_{timestamp}.csv"
    style_csv = report_dir / f"token_style_review_{timestamp}.csv"
    quote_csv = report_dir / f"quote_issues_{timestamp}.csv"
    mod_summary_csv = report_dir / f"token_mod_summary_{timestamp}.csv"
    file_summary_csv = report_dir / f"token_file_summary_{timestamp}.csv"
    json_report = report_dir / f"token_validation_report_{timestamp}.json"

    issue_count = write_issue_csv(issue_csv, issues)
    repair_count = write_worklist_csv(
        repair_csv,
        issues,
        include_style=args.include_style,
        include_order=args.include_order,
    )
    style_count = write_issue_csv(style_csv, [issue for issue in issues if issue.severity == "style"])
    quote_count = write_rows(
        quote_csv,
        ["mod", "file", "line_number", "key", "field", "leading_quotes", "trailing_quotes", "raw_value"],
        [
            {
                "mod": q.mod,
                "file": q.file,
                "line_number": q.line_number,
                "key": q.key,
                "field": q.field,
                "leading_quotes": q.leading,
                "trailing_quotes": q.trailing,
                "raw_value": q.raw_value,
            }
            for q in quote_issues
        ],
    )
    mod_summary_count = write_rows(
        mod_summary_csv,
        [
            "mod",
            "files_scanned",
            "rows_with_korean",
            "rows_with_english_tokens",
            "critical_rows",
            "hard_order_rows",
            "style_rows",
            "quote_rows",
        ],
        mod_rows,
    )
    file_summary_count = write_rows(
        file_summary_csv,
        [
            "mod",
            "file",
            "rows_with_korean",
            "rows_with_english_tokens",
            "critical_rows",
            "hard_order_rows",
            "style_rows",
            "quote_rows",
        ],
        file_rows,
    )

    summary.update(
        {
            "auto_keys_dir": str(auto_keys_dir),
            "mods_filter": args.mod,
            "issue_csv": str(issue_csv),
            "repair_worklist_csv": str(repair_csv),
            "style_review_csv": str(style_csv),
            "quote_issues_csv": str(quote_csv),
            "mod_summary_csv": str(mod_summary_csv),
            "file_summary_csv": str(file_summary_csv),
            "json_report": str(json_report),
            "issue_csv_rows": issue_count,
            "repair_worklist_rows": repair_count,
            "style_review_rows": style_count,
            "quote_issue_rows_written": quote_count,
            "mod_summary_rows": mod_summary_count,
            "file_summary_rows": file_summary_count,
            "repair_worklist_policy": {
                "default": "critical rows only",
                "include_order": args.include_order,
                "include_style": args.include_style,
            },
        }
    )
    with json_report.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"scanned_files={summary['scanned_files']}")
    print(f"rows_with_korean={summary['rows_with_korean']}")
    print(f"rows_with_english_tokens={summary['rows_with_english_tokens']}")
    print(f"issue_rows={summary['issue_rows']}")
    print(f"critical_rows={summary['critical_rows']}")
    print(f"hard_order_rows={summary['hard_order_rows']}")
    print(f"style_rows={summary['style_rows']}")
    print(f"quote_issue_rows={summary['quote_issue_rows']}")
    print(f"repair_worklist_rows={repair_count}")
    print(f'issue_csv="{issue_csv}"')
    print(f'repair_worklist_csv="{repair_csv}"')
    print(f'style_review_csv="{style_csv}"')
    print(f'quote_issues_csv="{quote_csv}"')
    print(f'mod_summary_csv="{mod_summary_csv}"')
    print(f'file_summary_csv="{file_summary_csv}"')
    print(f'json_report="{json_report}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
