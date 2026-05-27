"""번역 진행률 트리를 maintenance/translation_progress_tree.md에 생성.

사용:
    python tools/generate_translation_progress_tree.py
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from tool_config import translation_keys_root, translation_keys_root_arg

SCRIPT_DIR = Path(__file__).parent.resolve()
PACK_ROOT = SCRIPT_DIR.parent
AUTO_KEYS = translation_keys_root()
OUTPUT = PACK_ROOT / "maintenance" / "translation_progress_tree.md"

sys.path.insert(0, str(SCRIPT_DIR))
from review_report import _parse_cell, get_reasons, ERROR_REASONS


def has_source(value: str) -> bool:
    text = (value or "").strip()
    return bool(text and text.strip('"').strip())


def pct(done: int, total: int) -> float:
    return 100.0 if total == 0 else done / total * 100.0


def status(done: int, total: int, suspicious: int, empty: int) -> str:
    if total == 0 and empty:
        return "원문 빈 값만 있음"
    if total == 0:
        return "대상 없음"
    if done == total:
        return "완료"
    if done == 0:
        return "미시작"
    if suspicious:
        return f"진행 중 (의심 {suspicious:,})"
    return "진행 중"


def scan_file(path: Path) -> tuple[int, int, int, int]:
    """(total, done, suspicious, empty) 반환.

    - total: english_value가 있는 행 수
    - done: 번역이 있고 error 없는 행 수
    - suspicious: error 판정된 행 수 (empty/token_broken/no_hangul/quote_noise)
    - empty: english_value가 비어 있는 행 수
    warning(identical/too_short)은 진행률에 영향 없음.
    """
    total = done = suspicious = empty = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            eng_raw = row.get("english_value") or ""
            kor_raw = row.get("korean_value") or ""
            eng_inner = _parse_cell(eng_raw)
            kor_inner = _parse_cell(kor_raw)
            if not has_source(eng_raw):
                empty += 1
                continue
            total += 1
            reasons = get_reasons(eng_inner, kor_inner, kor_raw)
            has_error = any(r in ERROR_REASONS for r in reasons)
            if has_error:
                suspicious += 1
            else:
                done += 1
    return total, done, suspicious, empty


def main() -> None:
    mods = []
    for mod_dir in sorted(p for p in AUTO_KEYS.iterdir() if p.is_dir()):
        files = []
        mod_total = mod_done = mod_suspicious = mod_empty = 0
        for csv_path in sorted(mod_dir.rglob("*_key.csv")):
            total, done, suspicious, empty = scan_file(csv_path)
            if total == 0 and empty == 0:
                continue
            rel_name = str(csv_path.relative_to(mod_dir))
            files.append({
                "name": rel_name,
                "total": total, "done": done, "suspicious": suspicious, "empty": empty,
                "pct": pct(done, total),
                "status": status(done, total, suspicious, empty),
            })
            mod_total += total
            mod_done += done
            mod_suspicious += suspicious
            mod_empty += empty
        if files:
            mods.append({
                "name": mod_dir.name,
                "total": mod_total, "done": mod_done,
                "suspicious": mod_suspicious, "empty": mod_empty,
                "pct": pct(mod_done, mod_total),
                "status": status(mod_done, mod_total, mod_suspicious, mod_empty),
                "files": sorted(files, key=lambda x: (x["pct"], x["name"].lower())),
            })

    mods.sort(key=lambda x: x["name"].lower())

    total_rows = sum(m["total"] for m in mods)
    done_rows = sum(m["done"] for m in mods)
    suspicious_rows = sum(m["suspicious"] for m in mods)
    empty_rows = sum(m["empty"] for m in mods)
    file_count = sum(len(m["files"]) for m in mods)

    lines = [
        "# 자동키 번역률 트리",
        "",
        f"최종 갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"이 문서는 `{translation_keys_root_arg()}`의 CSV를 스캔해 모드/파일/번역률 순서로 정리한 진행률 표이다.",
        "번역률은 error 판정(empty/token_broken/no_hangul/quote_noise) 제외 기준이다. warning(identical/too_short)은 진행률에 영향 없음.",
        "",
        "## 전체 요약",
        "",
        "| 항목 | 수량 |",
        "| --- | ---: |",
        f"| 모드 폴더 | {len(mods):,} |",
        f"| CSV 파일 | {file_count:,} |",
        f"| 번역 완료 행 | {done_rows:,} |",
        f"| 의심 번역 행 | {suspicious_rows:,} |",
        f"| 번역 대상 행 | {total_rows:,} |",
        f"| 전체 번역률 | {pct(done_rows, total_rows):.1f}% |",
        f"| 원문 빈 값 행 | {empty_rows:,} |",
        "",
        "## 모드/파일/번역률 트리",
        "",
        "| 모드 / 파일 | 번역률 | 완료/의심/대상 | 원문 빈 값 | 상태 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]

    for mod in mods:
        lines.append(
            f"| `{mod['name']}` | {mod['pct']:.1f}% "
            f"| {mod['done']:,} / {mod['suspicious']:,} / {mod['total']:,} "
            f"| {mod['empty']:,} | {mod['status']} |"
        )
        for f in mod["files"]:
            lines.append(
                f"| └─ `{f['name']}` | {f['pct']:.1f}% "
                f"| {f['done']:,} / {f['suspicious']:,} / {f['total']:,} "
                f"| {f['empty']:,} | {f['status']} |"
            )

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"생성 완료: {OUTPUT}")


if __name__ == "__main__":
    main()
