#!/usr/bin/env bash
#
# 통합한글모드 번역 툴 런처 (WSL/bash 버전, run.ps1과 동등)
#
# 사용법: ./run.sh <액션> [옵션...]
#
#   translate   [target] [--mod <mod>] [--workers N] [--tpm N] [--rewrite]
#               [--from-report] [--from-worklist <path>] [--file <path>] [--start N] [--end N]
#   review      [target] [--mod <mod>] [--mark-errors] [--mark-retranslate] [--fix-quotes] [--quality]
#   validate    [target] [--mod <mod>]
#   export      <workshop_id_or_slug> [csv_dir] [--dry-run]
#   extract     <workshop_id> [output_dir] [--sync-source]
#   import-ref  [target] [--mod <mod>] [--source <id_or_path>...] [--overwrite] [--dry-run]
#   pipeline    [target] [--mode report|auto] [--mod <mod>] [--import-ref] [--translate] [--dry-run]
#   status      <workshop_id_or_slug>
#   work        <workshop_id_or_slug>
#   progress
#   diagnose    [--dollar] [--color]
#   patch       [--dry-run]
#   bom         [--fix]
#   full-check  [--mod <mod>]

# set -e 는 쓰지 않는다. run.ps1은 PowerShell에서 python(네이티브 명령)의 nonzero
# 종료 코드로 스크립트를 중단하지 않으므로(full-check/review 등 다단계 액션이 한 툴이
# 경고성 exit 1 을 내도 계속 진행), 그 동작을 맞추기 위해 -e 를 끈다.
set -uo pipefail

export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

TOOL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$TOOL_ROOT/tools"
TOOLING_INI="$TOOL_ROOT/maintenance/tooling.ini"
cd "$TOOL_ROOT"

die() { echo "$*" >&2; exit 1; }

py() {
    local script="$1"; shift
    python3 "$TOOLS_DIR/$script" "$@"
}

# ── tooling.ini 파서 ────────────────────────────────────────────────────
get_config_value() {
    # get_config_value <section> <key> <default>
    local section="$1" key="$2" default="$3"
    [[ -f "$TOOLING_INI" ]] || { echo "$default"; return; }
    local cur="" line trimmed k v
    while IFS= read -r line || [[ -n "$line" ]]; do
        trimmed="${line#"${line%%[![:space:]]*}"}"   # ltrim
        trimmed="${trimmed%"${trimmed##*[![:space:]]}"}" # rtrim
        [[ -z "$trimmed" || "$trimmed" == ";"* || "$trimmed" == "#"* ]] && continue
        if [[ "$trimmed" =~ ^\[(.+)\]$ ]]; then
            cur="${BASH_REMATCH[1]}"
            continue
        fi
        if [[ "$cur" == "$section" && "$trimmed" == *"="* ]]; then
            k="${trimmed%%=*}"; v="${trimmed#*=}"
            k="${k%"${k##*[![:space:]]}"}"           # rtrim key
            v="${v#"${v%%[![:space:]]*}"}"           # ltrim value
            if [[ "$k" == "$key" ]]; then echo "$v"; return; fi
        fi
    done < "$TOOLING_INI"
    echo "$default"
}

# ── Windows 경로 → WSL 경로 ─────────────────────────────────────────────
winpath_to_wsl() {
    local p="$1"
    if [[ "$p" =~ ^([A-Za-z]):[\\/](.*)$ ]]; then
        local drive="${BASH_REMATCH[1],,}" rest="${BASH_REMATCH[2]}"
        rest="${rest//\\//}"
        echo "/mnt/$drive/$rest"
    else
        echo "${p//\\//}"
    fi
}

# ── translation_keys 루트 ───────────────────────────────────────────────
translation_keys_root() {
    local raw="${STELLARIS_TRANSLATION_KEYS_DIR:-}"
    [[ -z "$raw" ]] && raw="$(get_config_value paths translation_keys "maintenance/translation_keys")"
    if [[ "$raw" = /* ]]; then echo "$raw"; else echo "$TOOL_ROOT/$raw"; fi
}

translation_keys_root_arg() {
    # 파이썬에 넘길 인자: TOOL_ROOT 하위면 상대경로, 아니면 절대경로
    local root; root="$(translation_keys_root)"
    if [[ "$root" == "$TOOL_ROOT/"* ]]; then echo "${root#"$TOOL_ROOT/"}"; else echo "$root"; fi
}

# ── 환경 감지: WSL vs 네이티브 리눅스 ───────────────────────────────────
is_wsl() {
    [[ -n "${WSL_DISTRO_NAME:-}" ]] && return 0
    [[ -r /proc/version ]] && grep -qiE 'microsoft|wsl' /proc/version && return 0
    return 1
}

# ── workshop 루트 ───────────────────────────────────────────────────────
# STELLARIS_WORKSHOP_ROOT(양 환경 최우선, 변환 없음) → WSL이면 tooling.ini의
# Windows 경로를 /mnt 로 변환 → 네이티브 리눅스면 표준 Steam 경로들을 탐색.
workshop_root() {
    local raw="${STELLARIS_WORKSHOP_ROOT:-}"
    if [[ -n "$raw" ]]; then echo "$raw"; return; fi

    if is_wsl; then
        raw="$(get_config_value paths workshop_root "")"
        [[ -z "$raw" ]] && raw="D:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\281990"
        winpath_to_wsl "$raw"
        return
    fi

    # 네이티브 리눅스: tooling.ini의 Windows 경로는 무시하고 표준 경로 탐색.
    local suffix="steamapps/workshop/content/281990"
    local -a candidates=()
    [[ -n "${STEAM_DIR:-}" ]] && candidates+=("$STEAM_DIR/$suffix")
    candidates+=(
        "$HOME/.steam/steam/$suffix"
        "$HOME/.local/share/Steam/$suffix"
        "$HOME/.steam/root/$suffix"
        "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam/$suffix"
    )
    local c
    for c in "${candidates[@]}"; do
        [[ -d "$c" ]] && { echo "$c"; return; }
    done
    die "Stellaris workshop root를 찾지 못했습니다. output_dir을 직접 지정하세요."
}

# ── 슬러그 ──────────────────────────────────────────────────────────────
convert_to_slug() {
    local s="${1,,}"
    s="$(sed -E 's/[^a-z0-9]+/_/g; s/_+/_/g; s/^_//; s/_$//' <<<"$s")"
    [[ -n "$s" ]] && echo "$s" || echo "mod"
}

descriptor_name() {
    # descriptor_name <mod_root> <fallback>
    local desc="$1/descriptor.mod" fallback="$2" name
    [[ -f "$desc" ]] || { echo "$fallback"; return; }
    name="$(grep -m1 -oP '^\s*name\s*=\s*"\K[^"]+' "$desc" 2>/dev/null || true)"
    [[ -n "$name" ]] && echo "$name" || echo "$fallback"
}

find_translation_key_slug() {
    # 숫자면 *__<id> 매칭 폴더명 반환; 아니면 동명 폴더 있으면 그대로; 없으면 ""
    local target="$1" root; root="$(translation_keys_root)"
    [[ -d "$root" ]] || { echo ""; return; }
    if [[ "$target" =~ ^[0-9]+$ ]]; then
        local m
        m="$(find "$root" -maxdepth 1 -type d -name "*__$target" -printf '%f\n' 2>/dev/null | head -n1)"
        echo "$m"; return
    fi
    [[ -d "$root/$target" ]] && echo "$target" || echo ""
}

workshop_id_from_slug() {
    [[ "$1" =~ __([0-9]+)$ ]] && echo "${BASH_REMATCH[1]}" || echo ""
}

translation_keys_dir_for_workshop_id() {
    local id="$1" wroot mod_root name slug
    wroot="$(workshop_root)"
    mod_root="$wroot/$id"
    [[ -d "$mod_root" ]] || die "Workshop mod folder not found: $mod_root"
    name="$(descriptor_name "$mod_root" "$id")"
    slug="$(convert_to_slug "$name")"
    echo "$(translation_keys_root_arg)/${slug}__${id}"
}

resolve_mod_slug() {
    # resolve_mod_slug <target> [allow_computed]
    local target="$1" allow="${2:-}"
    [[ -z "$target" ]] && { echo ""; return; }
    local found; found="$(find_translation_key_slug "$target")"
    [[ -n "$found" ]] && { echo "$found"; return; }
    [[ ! "$target" =~ ^[0-9]+$ ]] && { echo "$target"; return; }
    if [[ -n "$allow" ]]; then
        basename "$(translation_keys_dir_for_workshop_id "$target")"
        return
    fi
    die "translation_keys에서 모드를 찾지 못했습니다: $target"
}

resolve_workshop_id() {
    local target="$1"
    [[ -z "$target" ]] && { echo ""; return; }
    [[ "$target" =~ ^[0-9]+$ ]] && { echo "$target"; return; }
    local id; id="$(workshop_id_from_slug "$target")"
    [[ -n "$id" ]] && { echo "$id"; return; }
    local slug; slug="$(find_translation_key_slug "$target")"
    [[ -n "$slug" ]] && { echo "$(workshop_id_from_slug "$slug")"; return; }
    die "workshop_id를 해석할 수 없습니다: $target"
}

resolve_translation_keys_dir() {
    local target="$1"
    [[ -z "$target" ]] && { echo ""; return; }
    if [[ "$target" =~ ^[0-9]+$ ]]; then
        local slug; slug="$(find_translation_key_slug "$target")"
        [[ -n "$slug" ]] && { echo "$(translation_keys_root_arg)/$slug"; return; }
        translation_keys_dir_for_workshop_id "$target"; return
    fi
    local sop; sop="$(resolve_mod_slug "$target" computed)"
    if [[ "$sop" = /* || "$sop" == *[/\\]* ]]; then echo "$sop"; return; fi
    echo "$(translation_keys_root_arg)/$sop"
}

get_key_stats() {
    # 전역 변수에 통계 채움: ST_exists ST_csv_files ST_rows ST_translated ST_empty ST_no_hangul
    local keys_dir="$1" abs
    if [[ "$keys_dir" = /* ]]; then abs="$keys_dir"; else abs="$TOOL_ROOT/$keys_dir"; fi
    ST_exists=false; ST_csv_files=0; ST_rows=0; ST_translated=0; ST_empty=0; ST_no_hangul=0
    [[ -d "$abs" ]] || return
    ST_exists=true
    local out
    out="$(python3 - "$abs" <<'PY'
import csv, sys, glob, os, re
abs_dir = sys.argv[1]
files = glob.glob(os.path.join(abs_dir, "**", "*_key.csv"), recursive=True)
rows=trans=empty=nohangul=0
han=re.compile("[가-힣]")
for f in files:
    with open(f, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rows+=1
            kor=(row.get("korean_value") or "")
            if not kor.strip():
                empty+=1
            else:
                trans+=1
                if not han.search(kor): nohangul+=1
print(len(files), rows, trans, empty, nohangul)
PY
)"
    read -r ST_csv_files ST_rows ST_translated ST_empty ST_no_hangul <<<"$out"
}

write_mod_status() {
    local target="$1"
    [[ -n "$target" ]] || die "대상 workshop_id 또는 slug 필요"
    local wid slug kdir
    wid="$(resolve_workshop_id "$target")"
    slug="$(resolve_mod_slug "$target" computed)"
    kdir="$(resolve_translation_keys_dir "$target")"
    get_key_stats "$kdir"
    echo "mod_id=$wid"
    echo "slug=$slug"
    echo "keys_dir=$kdir"
    echo "keys_dir_exists=$ST_exists"
    echo "csv_files=$ST_csv_files"
    echo "rows=$ST_rows"
    echo "translated_rows=$ST_translated"
    echo "empty_rows=$ST_empty"
    echo "no_hangul_rows=$ST_no_hangul"
}

write_work_hint() {
    local target="$1"
    [[ -n "$target" ]] || die "대상 workshop_id 또는 slug 필요"
    local wid kdir
    wid="$(resolve_workshop_id "$target")"
    kdir="$(resolve_translation_keys_dir "$target")"
    get_key_stats "$kdir"
    write_mod_status "$target"
    echo ""
    if [[ "$ST_exists" != true || "$ST_csv_files" -eq 0 ]]; then
        echo "next=./run.sh extract $wid"
    elif [[ "$ST_empty" -gt 0 ]]; then
        echo "next=CSV의 korean_value 직접 번역 또는 ./run.sh translate $wid --dry-run"
    else
        echo "next=./run.sh review $wid --mark-errors"
        echo "then=./run.sh export $wid --dry-run"
    fi
    echo "edit=$kdir"
}

# ── 인자 파싱 ───────────────────────────────────────────────────────────
usage() {
    # 셔뱅 다음의 선두 주석 블록(사용법)만 출력한다.
    awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
}
[[ $# -ge 1 ]] || { usage; exit 1; }

ACTION="$1"; shift

MOD=""; FILE=""; FROM_WORKLIST=""; MODE="report"
WORKERS=""; TPM=""; START=0; END=""
REWRITE=0; FROM_REPORT=0; MARK_ERRORS=0; MARK_RETRANSLATE=0; FIX_QUOTES=0
QUALITY=0; OVERWRITE=0; SYNC_SOURCE=0; IMPORT_REF=0; TRANSLATE=0; DRY_RUN=0; INTEGRATED=0
declare -a SOURCE=()
declare -a POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mod)              MOD="$2"; shift 2 ;;
        --workers)          WORKERS="$2"; shift 2 ;;
        --tpm)              TPM="$2"; shift 2 ;;
        --file)             FILE="$2"; shift 2 ;;
        --from-worklist)    FROM_WORKLIST="$2"; shift 2 ;;
        --source)           SOURCE+=("$2"); shift 2 ;;
        --mode)             MODE="$2"; shift 2 ;;
        --start)            START="$2"; shift 2 ;;
        --end)              END="$2"; shift 2 ;;
        --rewrite)          REWRITE=1; shift ;;
        --from-report)      FROM_REPORT=1; shift ;;
        --mark-errors)      MARK_ERRORS=1; shift ;;
        --mark-retranslate) MARK_RETRANSLATE=1; shift ;;
        --fix-quotes)       FIX_QUOTES=1; shift ;;
        --quality)          QUALITY=1; shift ;;
        --overwrite)        OVERWRITE=1; shift ;;
        --sync-source)      SYNC_SOURCE=1; shift ;;
        --import-ref)       IMPORT_REF=1; shift ;;
        --translate)        TRANSLATE=1; shift ;;
        --dry-run)          DRY_RUN=1; shift ;;
        --integrated)       INTEGRATED=1; shift ;;
        *)                  POSITIONAL+=("$1"); shift ;;
    esac
done

ARG1="${POSITIONAL[0]:-}"
ARG2="${POSITIONAL[1]:-}"

# workers/tpm 기본값: CLI 미지정 시 env → ini
if [[ -z "$WORKERS" ]]; then
    WORKERS="${STELLARIS_TRANSLATION_WORKERS:-$(get_config_value translation workers 3)}"
fi
if [[ -z "$TPM" ]]; then
    TPM="${STELLARIS_TRANSLATION_TPM_LIMIT:-$(get_config_value translation tpm_limit 100000)}"
fi

# python 스크립트들이 올바른 workshop 루트를 기본값으로 잡도록 리눅스 경로를 export.
# (tool_config.workshop_root() 가 STELLARIS_WORKSHOP_ROOT 를 최우선으로 읽고,
#  각 스크립트의 --workshop-root 기본값이 그 결과이므로 별도 인자 전달이 불필요하다.)
# 해석에 실패해도(예: Steam 미설치 네이티브 리눅스) workshop 루트가 필요없는
# 액션은 계속 동작해야 하므로, 실패 시 export를 건너뛴다. run.ps1처럼 실제로
# workshop 루트가 필요한 액션에서만 나중에 에러가 난다.
if _wr="$(workshop_root 2>/dev/null)"; then
    export STELLARIS_WORKSHOP_ROOT="$_wr"
fi

get_mod_args() {
    # 배열 MOD_ARGS 채움
    MOD_ARGS=()
    if [[ -n "$MOD" ]]; then
        MOD_ARGS=(--mod "$(resolve_mod_slug "$MOD" computed)")
        return
    fi
    case "$ACTION" in
        translate|review|validate|import-ref|pipeline|full-check)
            if [[ -n "$ARG1" ]]; then
                MOD_ARGS=(--mod "$(resolve_mod_slug "$ARG1" computed)")
            fi
            ;;
    esac
}

case "$ACTION" in
    translate)
        get_mod_args
        pyargs=(--workers "$WORKERS" --tpm-limit "$TPM" "${MOD_ARGS[@]}")
        [[ -n "$FILE" ]]          && pyargs+=(--file "$FILE")
        [[ "$START" -gt 0 ]]      && pyargs+=(--start-row "$START")
        [[ -n "$END" ]]           && pyargs+=(--end-row "$END")
        [[ "$REWRITE" -eq 1 ]]    && pyargs+=(--rewrite-existing)
        [[ "$FROM_REPORT" -eq 1 ]] && pyargs+=(--from-report)
        [[ -n "$FROM_WORKLIST" ]] && pyargs+=(--from-worklist "$FROM_WORKLIST")
        [[ "$DRY_RUN" -eq 1 ]]    && pyargs+=(--dry-run)
        py translate_keys.py "${pyargs[@]}"
        ;;

    review)
        get_mod_args
        echo "== 토큰 검증 =="
        py validate_auto_key_tokens.py "${MOD_ARGS[@]}"
        if [[ "$FIX_QUOTES" -eq 1 ]]; then
            report="$(find "$TOOL_ROOT/maintenance/reports/token_validation" -maxdepth 1 -name 'quote_issues_*.csv' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n1 | cut -d' ' -f2-)"
            if [[ -n "$report" && -s "$report" ]]; then
                echo "== 따옴표 보정 =="
                py fix_quote_issues.py --report "$report"
                echo "== 토큰 재검증 =="
                py validate_auto_key_tokens.py "${MOD_ARGS[@]}"
            else
                echo "== 따옴표 이슈 없음 =="
            fi
        fi
        echo "== 리뷰 리포트 =="
        revargs=("${MOD_ARGS[@]}")
        [[ "$MARK_ERRORS" -eq 1 ]]      && revargs+=(--mark-errors)
        [[ "$MARK_RETRANSLATE" -eq 1 ]] && revargs+=(--mark-retranslate)
        [[ "$QUALITY" -eq 1 ]]          && revargs+=(--quality)
        py review_report.py "${revargs[@]}"
        ;;

    validate)
        get_mod_args
        py validate_auto_key_tokens.py "${MOD_ARGS[@]}"
        ;;

    export)
        [[ -n "$ARG1" ]] || die "workshop_id 또는 slug 필요. 예: ./run.sh export 1121692237"
        wid="$(resolve_workshop_id "$ARG1")"
        csvdir="$ARG2"
        if [[ -z "$csvdir" ]]; then
            csvdir="$(resolve_translation_keys_dir "$ARG1")"
            echo "translation_keys csv_dir=$csvdir"
        fi
        pyargs=("$wid" "$csvdir")
        [[ "$DRY_RUN" -eq 1 ]] && pyargs+=(--dry-run)
        py export_localisation.py "${pyargs[@]}"
        ;;

    extract)
        [[ -n "$ARG1" ]] || die "workshop_id 필요"
        outdir="$ARG2"
        if [[ -z "$outdir" ]]; then
            outdir="$(translation_keys_dir_for_workshop_id "$ARG1")"
            echo "translation_keys output_dir=$outdir"
        fi
        pyargs=("$ARG1" "$outdir")
        [[ "$SYNC_SOURCE" -eq 1 ]] && pyargs+=(--sync-source)
        py extract_localisation_keys.py "${pyargs[@]}"
        ;;

    import-ref)
        get_mod_args
        pyargs=("${MOD_ARGS[@]}")
        for s in "${SOURCE[@]:-}"; do [[ -n "$s" ]] && pyargs+=(--reference-source "$s"); done
        [[ "$OVERWRITE" -eq 1 ]] && pyargs+=(--overwrite-existing)
        [[ "$DRY_RUN" -eq 1 ]]   && pyargs+=(--dry-run)
        py import_korean_references.py "${pyargs[@]}"
        ;;

    pipeline)
        get_mod_args
        pyargs=(--mode "$MODE" "${MOD_ARGS[@]}")
        [[ "$IMPORT_REF" -eq 1 ]] && pyargs+=(--import-korean-references)
        [[ "$TRANSLATE" -eq 1 ]]  && pyargs+=(--translate)
        [[ "$DRY_RUN" -eq 1 ]]    && pyargs+=(--dry-run)
        [[ "$INTEGRATED" -eq 1 ]] && pyargs+=(--integrated)
        py run_pipeline.py "${pyargs[@]}"
        ;;

    progress)
        py generate_translation_progress_tree.py
        ;;

    diagnose)
        pyargs=()
        for a in "${POSITIONAL[@]:-}"; do
            [[ "$a" == "--dollar" ]] && pyargs+=(--dollar)
            [[ "$a" == "--color" ]] && pyargs+=(--color)
        done
        py diagnose_source_tokens.py "${pyargs[@]}"
        ;;

    patch)
        pyargs=()
        [[ "$DRY_RUN" -eq 1 ]] && pyargs+=(--dry-run)
        py patch_english_tokens.py "${pyargs[@]}"
        ;;

    bom)
        if [[ "$ARG1" == "--fix" ]]; then py check_utf8_bom.py --fix; else py check_utf8_bom.py; fi
        ;;

    full-check)
        get_mod_args
        echo "== 토큰 검증 =="
        py validate_auto_key_tokens.py "${MOD_ARGS[@]}"
        echo "== 리뷰 리포트 =="
        py review_report.py "${MOD_ARGS[@]}"
        echo "== BOM 검사 =="
        py check_utf8_bom.py
        echo "== 진행률 갱신 =="
        py generate_translation_progress_tree.py
        echo "== 완료 =="
        ;;

    status)
        write_mod_status "$ARG1"
        ;;

    work)
        write_work_hint "$ARG1"
        ;;

    *)
        echo "알 수 없는 액션: $ACTION" >&2
        echo "사용법은 ./run.sh (인자 없이) 확인" >&2
        exit 1
        ;;
esac
