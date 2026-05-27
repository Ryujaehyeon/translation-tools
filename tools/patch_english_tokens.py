"""
영어 원문(english_value)의 망가진 £아이콘 토큰을 보정하는 스크립트.

모드:
  --report   : 보정 대상 리포트 CSV 생성 (파일 변경 없음)
  --apply    : 리포트 CSV 기준으로 auto_keys CSV에 실제 적용
  --auto     : 리포트 생성 후 바로 적용

자동 보정 규칙 (확신도 높음):
  R1. £word  텍스트  (공백2+, 뒤에 일반텍스트, §가 아닌 것) → £word£ 텍스트
  R2. £word  $var$   (공백2+, 뒤에 달러변수)                → £word£ $var$
  R3. £word  £word2  (공백2+, 뒤에 아이콘)                  → £word£ £word2
  R4. £word £word2   (공백1, 뒤에 아이콘)                   → £word£ £word2
  R5. £word $var$    (공백1, 뒤에 달러변수)                  → £word£ $var$
  R6. £word. 등      (구두점/개행/따옴표)                    → £word£. 등

  규칙을 수렴할 때까지 반복 적용 (R3+R4 연쇄로 아이콘 나열 전체 처리)

건너뜀:
  - £word  §Y  : 이슈5, TOKEN_RE lookahead에서 이미 처리됨
  - space1_text: £word£텍스트 오탐 포함 가능, 불확실
  - £word - §G 등 other 패턴: 의도적일 수 있음
"""
import csv, re, sys, os, glob, argparse, datetime, collections, shutil

from tool_config import translation_keys_root

def get_paths():
    base = os.path.dirname(__file__)
    auto_keys = os.path.normpath(str(translation_keys_root()))
    reports   = os.path.normpath(os.path.join(base, '..', 'maintenance', 'reports', 'token_validation'))
    backups   = os.path.normpath(os.path.join(base, '..', 'maintenance', 'backups', 'patch_english_tokens'))
    return auto_keys, reports, backups

# ── 규칙 정의 ──────────────────────────────────────────────────────────────

# 각 규칙: (rule_id, compiled_pattern, replacement_fn, description)
# 주의: R1은 공백2+ 뒤 §로 시작하는 케이스(이슈5)를 제외해야 함
#       £word  §Y 패턴은 translate_keys.py TOKEN_RE에서 이미 lookahead로 처리됨

RULE_DEFS = [
    ('R1',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( {2,})([^§\n£$])'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space2+_text'),

    ('R2',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( {2,})(\$)'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space2+_dollar'),

    ('R3',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( {2,})(£)'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space2+_icon'),

    ('R4',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( )(£)'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space1_icon'),

    ('R5',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( )(\$[A-Za-z_])'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space1_dollar'),

    ('R6',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)([.,;\n"\']|$)'),
     lambda m: f'£{m.group(1)}£{m.group(2)}',
     'punct_end'),

    # R7: 공백/개행(실제 또는 리터럴 \n) 뒤 § (TOKEN_RE의 (?=\s+§) 커버)
    ('R7',
     re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)((?:\s|\\n)+)(§)'),
     lambda m: f'£{m.group(1)}£ {m.group(3)}',
     'space_para: £word §Y -> £word£ §Y'),

]

# R8은 닫힌 £word£ 뒤에 오는 텍스트를 건드리면 안 되므로
# apply_rules 내부에서 정상 토큰을 strip한 텍스트에만 적용
_CLOSED_ICON_RE = re.compile(r'£[A-Za-z_][A-Za-z0-9_|]*£')
_R8_PAT = re.compile(r'£([A-Za-z_][A-Za-z0-9_|]*)( )([^§£$\s])')

def apply_rules(text):
    """규칙을 수렴할 때까지 반복 적용. (rule_id, count, desc) 목록 반환."""
    all_changes = []
    for _ in range(10):  # 최대 10회 반복
        changed = False
        for rule_id, pat, repl, desc in RULE_DEFS:
            new_text, n = pat.subn(repl, text)
            if n:
                all_changes.append((rule_id, n, desc))
                text = new_text
                changed = True

        # R8: 정상 닫힌 £word£ 를 마스킹 후 space1_text 적용
        stripped = _CLOSED_ICON_RE.sub(lambda m: 'X' * len(m.group()), text)
        new_stripped, n = _R8_PAT.subn(lambda m: f'£{m.group(1)}£ {m.group(3)}', stripped)
        if n:
            # strip된 위치에 동일하게 원본에 적용
            new_text, n2 = _R8_PAT.subn(lambda m: f'£{m.group(1)}£ {m.group(3)}', text)
            # 오탐 방지: 변경된 위치가 닫힌 토큰 바로 뒤인지 확인
            # stripped 결과와 비교해서 실제 unclosed인 곳만 반영
            if new_stripped != stripped:
                # 실제로 unclosed인 매칭만 적용
                def r8_safe(m):
                    # 원본에서 이 위치 직전이 닫힌 £이면 건너뜀
                    pos = m.start()
                    if pos > 0 and text[pos - 1] == '£':
                        return m.group(0)
                    # stripped에서 이 위치가 X로 시작하면 (닫힌 토큰 내부) 건너뜀
                    if stripped[pos] == 'X':
                        return m.group(0)
                    return f'£{m.group(1)}£ {m.group(3)}'
                new_text2 = _R8_PAT.sub(r8_safe, text)
                if new_text2 != text:
                    all_changes.append(('R8', n, 'space1_text'))
                    text = new_text2
                    changed = True

        if not changed:
            break
    return text, all_changes

# ── 리포트 생성 ────────────────────────────────────────────────────────────

def build_report(auto_keys, reports):
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out_path = os.path.join(reports, f'english_token_patch_report_{ts}.csv')

    fieldnames = ['mod', 'file', 'key', 'rule', 'original', 'patched', 'description', 'apply']
    rows = []

    for csv_path in sorted(glob.glob(auto_keys + '/**/*_key.csv', recursive=True)):
        rel = os.path.relpath(csv_path, auto_keys)
        mod = rel.split(os.sep)[0]
        fname = os.path.basename(rel)

        with open(csv_path, encoding='utf-8-sig') as f:
            try:
                for row in csv.DictReader(f):
                    en = row.get('english_value', '')
                    if '£' not in en:
                        continue
                    patched, changes = apply_rules(en)
                    if not changes:
                        continue
                    rule_ids = '+'.join(dict.fromkeys(c[0] for c in changes))  # 중복 제거, 순서 유지
                    desc = '; '.join(dict.fromkeys(c[2] for c in changes))
                    rows.append({
                        'mod': mod,
                        'file': fname,
                        'key': row.get('key', ''),
                        'rule': rule_ids,
                        'original': en,
                        'patched': patched,
                        'description': desc,
                        'apply': '1',
                    })
            except Exception as e:
                print(f'ERROR {rel}: {e}', file=sys.stderr)

    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out = [f'리포트: {out_path}', f'총 {len(rows)}건']
    by_mod = collections.Counter(r['mod'] for r in rows)
    for mod, cnt in by_mod.most_common():
        out.append(f'  {mod}: {cnt}건')
    sys.stdout.buffer.write('\n'.join(out).encode('utf-8') + b'\n')

    return out_path, rows

# ── 적용 ──────────────────────────────────────────────────────────────────

def apply_report(report_path, auto_keys, backups):
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backed_up = set()
    changed_files = 0
    changed_rows = 0

    patches = {}  # (mod, file, key) -> patched
    with open(report_path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('apply', '1').strip() != '1':
                continue
            patches[(row['mod'], row['file'], row['key'])] = row['patched']

    sys.stdout.buffer.write(f'적용 대상: {len(patches)}건\n'.encode('utf-8'))

    file_patches = collections.defaultdict(dict)
    for (mod, fname, key), patched in patches.items():
        file_patches[os.path.join(mod, fname)][key] = patched

    for csv_rel, key_patches in sorted(file_patches.items()):
        csv_path = os.path.join(auto_keys, csv_rel)
        if not os.path.exists(csv_path):
            sys.stdout.buffer.write(f'SKIP (없음): {csv_rel}\n'.encode('utf-8'))
            continue

        if csv_path not in backed_up:
            bk_dir = os.path.join(backups, ts, os.path.dirname(csv_rel))
            os.makedirs(bk_dir, exist_ok=True)
            shutil.copy2(csv_path, os.path.join(bk_dir, os.path.basename(csv_path)))
            backed_up.add(csv_path)

        with open(csv_path, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            all_rows = list(reader)

        n_changed = 0
        for row in all_rows:
            key = row.get('key', '')
            if key in key_patches:
                row['english_value'] = key_patches[key]
                n_changed += 1

        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        sys.stdout.buffer.write(f'  {csv_rel}: {n_changed}건\n'.encode('utf-8'))
        changed_files += 1
        changed_rows += n_changed

    sys.stdout.buffer.write(f'\n완료: {changed_files}개 파일, {changed_rows}건 적용\n'.encode('utf-8'))

# ── main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='영어 원문 토큰 보정')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--report', action='store_true', help='보정 대상 리포트 CSV 생성')
    group.add_argument('--apply', metavar='REPORT_CSV', help='리포트 기반 적용')
    group.add_argument('--auto', action='store_true', help='리포트 생성 후 바로 적용')
    args = parser.parse_args()

    auto_keys, reports, backups = get_paths()

    if args.report:
        build_report(auto_keys, reports)
    elif args.apply:
        apply_report(args.apply, auto_keys, backups)
    elif args.auto:
        report_path, _ = build_report(auto_keys, reports)
        apply_report(report_path, auto_keys, backups)

if __name__ == '__main__':
    main()
