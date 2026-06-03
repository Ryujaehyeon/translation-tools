#!/usr/bin/env python3
"""hard_token_mismatch 행을 리포트에서 읽어 번역 후보를 출력한다.

OpenAI API를 사용하지 않는다. 사람(또는 Claude)이 직접 번역을 입력하거나
검토할 수 있도록 미번역 행 목록을 정리해 출력하고, --apply 시 CSV에 저장한다.

사용:
    # 최신 리포트에서 mismatch 행 목록 출력
    python tools/fix_token_mismatch.py

    # 특정 리포트 파일 지정
    python tools/fix_token_mismatch.py --report maintenance/reports/ai_translation/translate_keys_latest.json

    # 특정 모드만
    python tools/fix_token_mismatch.py --mod gigastructural_engineering_more_4_3__1121692237

    # CSV 파일로 내보내기 (검토 후 korean_value 채워서 --apply로 반영)
    python tools/fix_token_mismatch.py --export maintenance/reports/ai_translation/mismatch_to_fix.csv

    # 채워진 CSV를 auto_keys에 반영
    python tools/fix_token_mismatch.py --apply maintenance/reports/ai_translation/mismatch_to_fix.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from tool_config import csv_dict_writer, csv_writer, translation_keys_root

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
AUTO_KEYS_DIR = translation_keys_root()
REPORT_DIR = PACK_ROOT / "maintenance" / "reports" / "ai_translation"
BACKUP_ROOT = PACK_ROOT / "maintenance" / "backups" / "fix_token_mismatch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="hard_token_mismatch 행 검토 및 수동 수정 도구")
    parser.add_argument(
        "--report", default="", help="리포트 JSON 경로. 기본: translate_keys_latest.json"
    )
    parser.add_argument("--mod", default="", help="특정 auto_keys 모드 폴더명으로 필터")
    parser.add_argument("--export", default="", metavar="CSV", help="mismatch 행을 CSV로 내보내기")
    parser.add_argument("--apply", default="", metavar="CSV", help="채워진 CSV를 auto_keys에 반영")
    return parser.parse_args()


def load_report(report_path: Path) -> list[dict]:
    if not report_path.is_file():
        raise SystemExit(f"리포트 파일을 찾을 수 없습니다: {report_path}")
    data = json.loads(report_path.read_text(encoding="utf-8-sig"))
    rows = []
    for file_entry in data.get("files", []):
        csv_path = file_entry.get("path", "")
        for issue in file_entry.get("issues", []):
            if issue.get("reason") == "hard_token_mismatch":
                rows.append(
                    {
                        "csv_path": csv_path,
                        "key": issue.get("key", ""),
                        "english_value": issue.get("english_value", ""),
                        "rejected_value": issue.get("rejected_value", ""),
                        "token_delta": issue.get("token_delta", {}),
                    }
                )
    return rows


def format_delta(delta: dict) -> str:
    if not delta:
        return ""
    parts = []
    for token_type, info in delta.items():
        missing = info.get("missing", [])
        extra = info.get("extra", [])
        if missing:
            parts.append(f"{token_type} 누락: {missing}")
        if extra:
            parts.append(f"{token_type} 추가됨: {extra}")
    return " / ".join(parts)


def print_mismatches(rows: list[dict], mod_filter: str) -> None:
    filtered = [r for r in rows if not mod_filter or mod_filter in r["csv_path"]]
    if not filtered:
        print("mismatch 행이 없습니다.")
        return
    print(f"hard_token_mismatch 행: {len(filtered)}개\n")
    for r in filtered:
        rel = r["csv_path"].replace(str(AUTO_KEYS_DIR), "").lstrip("\\/")
        print(f"[{rel}]  key: {r['key']}")
        print(f"  영문: {r['english_value']}")
        print(f"  거부: {r['rejected_value']}")
        delta_str = format_delta(r["token_delta"])
        if delta_str:
            print(f"  토큰: {delta_str}")
        print()


def export_csv(rows: list[dict], mod_filter: str, output: Path) -> None:
    filtered = [r for r in rows if not mod_filter or mod_filter in r["csv_path"]]
    if not filtered:
        print("내보낼 행이 없습니다.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "csv_path",
        "key",
        "english_value",
        "rejected_value",
        "token_delta",
        "korean_value",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv_dict_writer(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in filtered:
            writer.writerow(
                {
                    "csv_path": r["csv_path"],
                    "key": r["key"],
                    "english_value": r["english_value"],
                    "rejected_value": r["rejected_value"],
                    "token_delta": format_delta(r["token_delta"]),
                    "korean_value": "",  # 사람/Claude가 채울 열
                }
            )
    print(f"내보내기 완료: {output}  ({len(filtered)}행)")
    print("korean_value 열을 채운 뒤 --apply 옵션으로 반영하세요.")


def apply_csv(input_path: Path) -> None:
    if not input_path.is_file():
        raise SystemExit(f"파일을 찾을 수 없습니다: {input_path}")

    rows = list(csv.DictReader(input_path.open(encoding="utf-8-sig")))
    to_apply = [r for r in rows if r.get("korean_value", "").strip()]
    if not to_apply:
        print("korean_value가 채워진 행이 없습니다.")
        return

    # csv_path별로 그룹화
    by_file: dict[str, list[dict]] = {}
    for r in to_apply:
        by_file.setdefault(r["csv_path"], []).append(r)

    total_applied = 0
    for csv_path_str, fix_rows in by_file.items():
        csv_path = Path(csv_path_str)
        if not csv_path.is_file():
            print(f"  [경고] 파일 없음: {csv_path}")
            continue

        # 백업
        import datetime as dt

        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            rel = csv_path.relative_to(AUTO_KEYS_DIR)
        except ValueError:
            rel = Path(csv_path.name)
        backup = BACKUP_ROOT / ts / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(csv_path, backup)

        # CSV 읽기
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            target_rows = list(reader)

        fix_map = {r["key"]: r["korean_value"] for r in fix_rows}
        changed = 0
        for row in target_rows:
            key = row.get("key", "")
            if key in fix_map:
                row["korean_value"] = fix_map[key]
                changed += 1

        # 원자적 저장
        temp = csv_path.with_suffix(csv_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv_writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(fieldnames)
            for row in target_rows:
                writer.writerow([row.get(fn, "") or "" for fn in fieldnames])
        shutil.move(str(temp), str(csv_path))

        rel_str = str(csv_path).replace(str(AUTO_KEYS_DIR), "").lstrip("\\/")
        print(f"  {rel_str}: {changed}행 반영")
        total_applied += changed

    print(f"\n총 {total_applied}행 반영 완료")


def main() -> int:
    args = parse_args()

    if args.apply:
        apply_csv(Path(args.apply))
        return 0

    report_path = Path(args.report) if args.report else REPORT_DIR / "translate_keys_latest.json"
    if not report_path.is_absolute():
        report_path = PACK_ROOT / report_path

    rows = load_report(report_path)

    if args.export:
        export_csv(
            rows,
            args.mod,
            Path(args.export) if Path(args.export).is_absolute() else PACK_ROOT / args.export,
        )
    else:
        print_mismatches(rows, args.mod)

    return 0


if __name__ == "__main__":
    sys.exit(main())
