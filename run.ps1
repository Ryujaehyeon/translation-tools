#!/usr/bin/env pwsh
<#
.SYNOPSIS
    통합한글모드 번역 툴 런처

.DESCRIPTION
    사용법: .\run.ps1 <액션> [옵션...]

    액션 목록:
      translate   [target] [--mod <mod>] [--workers N] [--tpm N] [--rewrite] [--from-report] [--from-worklist <path>] [--file <path>] [--start N] [--end N]
      review      [target] [--mod <mod>] [--mark-errors] [--mark-retranslate] [--fix-quotes] [--quality]
      validate    [target] [--mod <mod>]
      export      <workshop_id_or_slug> [csv_dir] [--dry-run]
      extract     <workshop_id> [output_dir] [--sync-source]
      import-ref  [target] [--mod <mod>] [--source <id_or_path>...] [--overwrite] [--dry-run]
      pipeline    [target] [--mode report|auto] [--mod <mod>] [--import-ref] [--translate] [--dry-run]
      status      <workshop_id_or_slug>
      work        <workshop_id_or_slug>
      progress    (진행률 트리 갱신)
      diagnose    [--dollar] [--color]
      patch       [--dry-run]
      bom         [--fix]
      full-check  [--mod <mod>] (validate + review + progress 한번에)

    예시:
      .\run.ps1 translate 1121692237 --workers 3
      .\run.ps1 review 1121692237 --mark-errors --fix-quotes
      .\run.ps1 translate --from-report --workers 3
      .\run.ps1 export 1121692237
      .\run.ps1 full-check
#>

param(
    [Parameter(Position=0, Mandatory=$true)]
    [string]$Action,

    [Parameter(Position=1)]
    [string]$Arg1,

    [Parameter(Position=2)]
    [string]$Arg2,

    [string]$Mod,
    [string[]]$Source,
    [string]$File,
    [Alias("from-worklist")]
    [string]$FromWorklist,
    [string]$Mode = "report",
    [int]$Workers = 3,
    [int]$Tpm = 2000000,
    [int]$Start = 0,
    [string]$End = "",
    [switch]$Rewrite,
    [Alias("from-report")]
    [switch]$FromReport,
    [Alias("mark-errors")]
    [switch]$MarkErrors,
    [Alias("mark-retranslate")]
    [switch]$MarkRetranslate,
    [Alias("fix-quotes")]
    [switch]$FixQuotes,
    [switch]$Quality,
    [switch]$Overwrite,
    [Alias("sync-source")]
    [switch]$SyncSource,
    [Alias("import-ref")]
    [switch]$ImportRef,
    [switch]$Translate,
    [Alias("dry-run")]
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 경로 설정 — 이 파일 기준
$ToolRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolsDir  = Join-Path $ToolRoot "tools"
$ToolingIni = Join-Path $ToolRoot "maintenance\tooling.ini"

Set-Location $ToolRoot

function py {
    param([string]$Script, [string[]]$ScriptArgs)
    $scriptPath = Join-Path $ToolsDir $Script
    python $scriptPath @ScriptArgs
}

function Get-ModArgs {
    if ($Mod) { return @("--mod", (Resolve-ModSlug $Mod -AllowComputed)) }
    if ($Arg1 -and $Action -in @("translate", "review", "validate", "import-ref", "pipeline", "full-check")) {
        return @("--mod", (Resolve-ModSlug $Arg1 -AllowComputed))
    }
    return @()
}

function Get-ToolConfigValue {
    param([string]$Section, [string]$Key, [string]$Default)
    if (-not (Test-Path -LiteralPath $ToolingIni -PathType Leaf)) { return $Default }
    $inSection = $false
    foreach ($line in Get-Content -LiteralPath $ToolingIni) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith(";") -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -match '^\[(.+)\]$') {
            $inSection = ($Matches[1] -eq $Section)
            continue
        }
        if ($inSection -and $trimmed -match '^([^=]+?)\s*=\s*(.+)$') {
            if ($Matches[1].Trim() -eq $Key) { return $Matches[2].Trim() }
        }
    }
    return $Default
}

function Get-ToolConfigInt {
    param([string]$Section, [string]$Key, [int]$Default)
    $raw = Get-ToolConfigValue $Section $Key ([string]$Default)
    $value = 0
    if ([int]::TryParse($raw, [ref]$value)) { return $value }
    return $Default
}

function Get-TranslationKeysRoot {
    $raw = $env:STELLARIS_TRANSLATION_KEYS_DIR
    if (-not $raw) {
        $raw = Get-ToolConfigValue "paths" "translation_keys" "maintenance/translation_keys"
    }
    if ([System.IO.Path]::IsPathRooted($raw)) { return $raw }
    return Join-Path $ToolRoot $raw
}

function Get-TranslationKeysRootArg {
    $root = Get-TranslationKeysRoot
    $relative = [System.IO.Path]::GetRelativePath($ToolRoot, $root)
    if (-not $relative.StartsWith("..")) { return $relative }
    return $root
}

function Get-ConfiguredWorkshopRoot {
    $raw = Get-ToolConfigValue "paths" "workshop_root" ""
    if ($raw -and (Test-Path -LiteralPath $raw -PathType Container)) { return $raw }
    return ""
}

function ConvertTo-Slug {
    param([string]$Value)
    $slug = $Value.ToLowerInvariant()
    $slug = [regex]::Replace($slug, "[^a-z0-9]+", "_")
    $slug = [regex]::Replace($slug, "_+", "_").Trim("_")
    if ($slug) { return $slug }
    return "mod"
}

function Get-SteamLibraryPaths {
    $roots = @()
    if ($env:STEAM_DIR) { $roots += $env:STEAM_DIR }
    $roots += @(
        "C:\Program Files (x86)\Steam",
        "C:\Program Files\Steam",
        "D:\Program Files (x86)\Steam",
        "D:\Steam"
    )

    $libraries = @()
    foreach ($root in $roots | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        $libraries += $root
        $vdfPath = Join-Path $root "steamapps\libraryfolders.vdf"
        if (-not (Test-Path -LiteralPath $vdfPath -PathType Leaf)) { continue }
        $text = Get-Content -Raw -LiteralPath $vdfPath
        foreach ($match in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
            $libraries += $match.Groups[1].Value.Replace("\\", "\")
        }
    }
    return $libraries | Select-Object -Unique
}

function Get-WorkshopRoot {
    $configured = Get-ConfiguredWorkshopRoot
    if ($configured) { return $configured }
    foreach ($library in Get-SteamLibraryPaths) {
        $candidate = Join-Path $library "steamapps\workshop\content\281990"
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            return $candidate
        }
    }
    Write-Error "Stellaris workshop root를 찾지 못했습니다. output_dir을 직접 지정하세요."
    exit 1
}

function Get-DescriptorName {
    param([string]$ModRoot, [string]$Fallback)
    $descriptor = Join-Path $ModRoot "descriptor.mod"
    if (-not (Test-Path -LiteralPath $descriptor -PathType Leaf)) { return $Fallback }
    $text = Get-Content -Raw -LiteralPath $descriptor
    $match = [regex]::Match($text, '(?m)^\s*name\s*=\s*"([^"]+)"')
    if ($match.Success) { return $match.Groups[1].Value }
    return $Fallback
}

function Get-TranslationKeysDirForWorkshopId {
    param([string]$WorkshopId)
    $workshopRoot = Get-WorkshopRoot
    $modRoot = Join-Path $workshopRoot $WorkshopId
    if (-not (Test-Path -LiteralPath $modRoot -PathType Container)) {
        Write-Error "Workshop mod folder not found: $modRoot"
        exit 1
    }
    $name = Get-DescriptorName $modRoot $WorkshopId
    $slug = ConvertTo-Slug $name
    return (Join-Path (Get-TranslationKeysRootArg) "$($slug)__$WorkshopId")
}

function Get-WorkshopIdFromSlug {
    param([string]$Slug)
    if ($Slug -match "__([0-9]+)$") { return $Matches[1] }
    return ""
}

function Find-TranslationKeySlug {
    param([string]$Target)
    $root = Get-TranslationKeysRoot
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { return "" }
    if ($Target -match "^[0-9]+$") {
        $match = Get-ChildItem -LiteralPath $root -Directory -Filter "*__$Target" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) { return $match.Name }
        return ""
    }
    $direct = Join-Path $root $Target
    if (Test-Path -LiteralPath $direct -PathType Container) { return $Target }
    return ""
}

function Resolve-ModSlug {
    param(
        [string]$Target,
        [switch]$AllowComputed
    )
    if (-not $Target) { return "" }
    $found = Find-TranslationKeySlug $Target
    if ($found) { return $found }
    if ($Target -notmatch "^[0-9]+$") { return $Target }
    if ($AllowComputed) {
        $dir = Get-TranslationKeysDirForWorkshopId $Target
        return Split-Path -Leaf $dir
    }
    Write-Error "translation_keys에서 모드를 찾지 못했습니다: $Target"
    exit 1
}

function Resolve-WorkshopId {
    param([string]$Target)
    if (-not $Target) { return "" }
    if ($Target -match "^[0-9]+$") { return $Target }
    $id = Get-WorkshopIdFromSlug $Target
    if ($id) { return $id }
    $slug = Find-TranslationKeySlug $Target
    if ($slug) { return Get-WorkshopIdFromSlug $slug }
    Write-Error "workshop_id를 해석할 수 없습니다: $Target"
    exit 1
}

function Resolve-TranslationKeysDir {
    param([string]$Target)
    if (-not $Target) { return "" }
    if ($Target -match "^[0-9]+$") {
        $slug = Find-TranslationKeySlug $Target
        if ($slug) { return Join-Path (Get-TranslationKeysRootArg) $slug }
        return Get-TranslationKeysDirForWorkshopId $Target
    }
    $slugOrPath = Resolve-ModSlug $Target -AllowComputed
    if ([System.IO.Path]::IsPathRooted($slugOrPath) -or $slugOrPath -match '[\\/]') { return $slugOrPath }
    return Join-Path (Get-TranslationKeysRootArg) $slugOrPath
}

function Get-KeyStats {
    param([string]$KeysDir)
    $abs = if ([System.IO.Path]::IsPathRooted($KeysDir)) { $KeysDir } else { Join-Path $ToolRoot $KeysDir }
    $stats = [ordered]@{
        exists = (Test-Path -LiteralPath $abs -PathType Container)
        csv_files = 0
        rows = 0
        translated_rows = 0
        empty_rows = 0
        no_hangul_rows = 0
    }
    if (-not $stats.exists) { return [pscustomobject]$stats }
    $files = Get-ChildItem -LiteralPath $abs -Recurse -File -Filter "*_key.csv"
    $stats.csv_files = @($files).Count
    foreach ($file in $files) {
        foreach ($row in Import-Csv -LiteralPath $file.FullName) {
            $stats.rows++
            $kor = [string]$row.korean_value
            if ([string]::IsNullOrWhiteSpace($kor)) {
                $stats.empty_rows++
            } else {
                $stats.translated_rows++
                if ($kor -notmatch "[가-힣]") { $stats.no_hangul_rows++ }
            }
        }
    }
    return [pscustomobject]$stats
}

function Write-ModStatus {
    param([string]$Target)
    if (-not $Target) { Write-Error "대상 workshop_id 또는 slug 필요"; exit 1 }
    $workshopId = Resolve-WorkshopId $Target
    $slug = Resolve-ModSlug $Target -AllowComputed
    $keysDir = Resolve-TranslationKeysDir $Target
    $stats = Get-KeyStats $keysDir
    Write-Host "mod_id=$workshopId"
    Write-Host "slug=$slug"
    Write-Host "keys_dir=$keysDir"
    Write-Host "keys_dir_exists=$($stats.exists)"
    Write-Host "csv_files=$($stats.csv_files)"
    Write-Host "rows=$($stats.rows)"
    Write-Host "translated_rows=$($stats.translated_rows)"
    Write-Host "empty_rows=$($stats.empty_rows)"
    Write-Host "no_hangul_rows=$($stats.no_hangul_rows)"
}

function Write-WorkHint {
    param([string]$Target)
    if (-not $Target) { Write-Error "대상 workshop_id 또는 slug 필요"; exit 1 }
    $workshopId = Resolve-WorkshopId $Target
    $slug = Resolve-ModSlug $Target -AllowComputed
    $keysDir = Resolve-TranslationKeysDir $Target
    $stats = Get-KeyStats $keysDir
    Write-ModStatus $Target
    Write-Host ""
    if (-not $stats.exists -or $stats.csv_files -eq 0) {
        Write-Host "next=.\run.ps1 extract $workshopId"
    } elseif ($stats.empty_rows -gt 0) {
        Write-Host "next=CSV의 korean_value 직접 번역 또는 .\run.ps1 translate $workshopId --dry-run"
    } else {
        Write-Host "next=.\run.ps1 review $workshopId --mark-errors"
        Write-Host "then=.\run.ps1 export $workshopId --dry-run"
    }
    Write-Host "edit=$keysDir"
}

if (-not $PSBoundParameters.ContainsKey("Workers")) {
    $Workers = if ($env:STELLARIS_TRANSLATION_WORKERS) {
        [int]$env:STELLARIS_TRANSLATION_WORKERS
    } else {
        Get-ToolConfigInt "translation" "workers" 3
    }
}
if (-not $PSBoundParameters.ContainsKey("Tpm")) {
    $Tpm = if ($env:STELLARIS_TRANSLATION_TPM_LIMIT) {
        [int]$env:STELLARIS_TRANSLATION_TPM_LIMIT
    } else {
        Get-ToolConfigInt "translation" "tpm_limit" 2000000
    }
}

switch ($Action) {

    # ── 번역 ───────────────────────────────────────────────────────────
    "translate" {
        $pyArgs = @("--workers", $Workers, "--tpm-limit", $Tpm)
        $pyArgs += Get-ModArgs
        if ($File)         { $pyArgs += @("--file", $File) }
        if ($Start -gt 0)  { $pyArgs += @("--start-row", $Start) }
        if ($End)          { $pyArgs += @("--end-row", $End) }
        if ($Rewrite)      { $pyArgs += "--rewrite-existing" }
        if ($FromReport)   { $pyArgs += "--from-report" }
        if ($FromWorklist) { $pyArgs += @("--from-worklist", $FromWorklist) }
        if ($DryRun)       { $pyArgs += "--dry-run" }
        py "translate_keys.py" $pyArgs
    }

    # ── 검수 ───────────────────────────────────────────────────────────
    "review" {
        # 1. 토큰 검증
        Write-Host "== 토큰 검증 ==" -ForegroundColor Cyan
        py "validate_auto_key_tokens.py" (Get-ModArgs)

        # 2. 따옴표 보정 (옵션)
        if ($FixQuotes) {
            $quoteReport = Get-ChildItem (Join-Path $ToolRoot "maintenance\reports\token_validation") -Filter "quote_issues_*.csv" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($quoteReport -and $quoteReport.Length -gt 0) {
                Write-Host "== 따옴표 보정 ==" -ForegroundColor Cyan
                py "fix_quote_issues.py" @("--report", $quoteReport.FullName)
                Write-Host "== 토큰 재검증 ==" -ForegroundColor Cyan
                py "validate_auto_key_tokens.py" (Get-ModArgs)
            } else {
                Write-Host "== 따옴표 이슈 없음 ==" -ForegroundColor Green
            }
        }

        # 3. 리뷰 리포트
        Write-Host "== 리뷰 리포트 ==" -ForegroundColor Cyan
        $revArgs = Get-ModArgs
        if ($MarkErrors)      { $revArgs += "--mark-errors" }
        if ($MarkRetranslate) { $revArgs += "--mark-retranslate" }
        if ($Quality)         { $revArgs += "--quality" }
        py "review_report.py" $revArgs
    }

    # ── 토큰 검증만 ────────────────────────────────────────────────────
    "validate" {
        py "validate_auto_key_tokens.py" (Get-ModArgs)
    }

    # ── 출력 ───────────────────────────────────────────────────────────
    "export" {
        if (-not $Arg1) { Write-Error "workshop_id 또는 slug 필요. 예: .\run.ps1 export 1121692237"; exit 1 }
        $workshopId = Resolve-WorkshopId $Arg1
        $csvDir = $Arg2
        if (-not $csvDir) {
            $csvDir = Resolve-TranslationKeysDir $Arg1
            Write-Host "translation_keys csv_dir=$csvDir" -ForegroundColor Cyan
        }
        $pyArgs = @($workshopId, $csvDir)
        if ($DryRun) { $pyArgs += "--dry-run" }
        py "export_localisation.py" $pyArgs
    }

    # ── 키 추출 ────────────────────────────────────────────────────────
    "extract" {
        if (-not $Arg1) { Write-Error "workshop_id 필요"; exit 1 }
        $outputDir = $Arg2
        if (-not $outputDir) {
            $outputDir = Get-TranslationKeysDirForWorkshopId $Arg1
            Write-Host "translation_keys output_dir=$outputDir" -ForegroundColor Cyan
        }
        $pyArgs = @($Arg1, $outputDir)
        if ($SyncSource) { $pyArgs += "--sync-source" }
        py "extract_localisation_keys.py" $pyArgs
    }

    # ── 참고 번역 임포트 ───────────────────────────────────────────────
    "import-ref" {
        $pyArgs = Get-ModArgs
        foreach ($s in $Source) { $pyArgs += @("--reference-source", $s) }
        if ($Overwrite) { $pyArgs += "--overwrite-existing" }
        if ($DryRun)    { $pyArgs += "--dry-run" }
        py "import_korean_references.py" $pyArgs
    }

    # ── 파이프라인 ─────────────────────────────────────────────────────
    "pipeline" {
        $pyArgs = @("--mode", $Mode)
        $pyArgs += Get-ModArgs
        if ($ImportRef) { $pyArgs += "--import-korean-references" }
        if ($Translate) { $pyArgs += "--translate" }
        if ($DryRun)    { $pyArgs += "--dry-run" }
        py "run_pipeline.py" $pyArgs
    }

    # ── 진행률 갱신 ────────────────────────────────────────────────────
    "progress" {
        py "generate_translation_progress_tree.py" @()
    }

    # ── 원본 토큰 진단 ─────────────────────────────────────────────────
    "diagnose" {
        $pyArgs = @()
        if ($Arg1 -eq "--dollar" -or $Source -contains "--dollar") { $pyArgs += "--dollar" }
        if ($Arg1 -eq "--color"  -or $Source -contains "--color")  { $pyArgs += "--color" }
        py "diagnose_source_tokens.py" $pyArgs
    }

    # ── 원본 토큰 보정 ─────────────────────────────────────────────────
    "patch" {
        $pyArgs = @()
        if ($DryRun) { $pyArgs += "--dry-run" }
        py "patch_english_tokens.py" $pyArgs
    }

    # ── BOM 검사/보정 ──────────────────────────────────────────────────
    "bom" {
        py "check_utf8_bom.py" $(if ($Arg1 -eq "--fix") { @("--fix") } else { @() })
    }

    # ── 전체 체크 ──────────────────────────────────────────────────────
    "full-check" {
        Write-Host "== 토큰 검증 ==" -ForegroundColor Cyan
        py "validate_auto_key_tokens.py" (Get-ModArgs)
        Write-Host "== 리뷰 리포트 ==" -ForegroundColor Cyan
        py "review_report.py" (Get-ModArgs)
        Write-Host "== BOM 검사 ==" -ForegroundColor Cyan
        py "check_utf8_bom.py" @()
        Write-Host "== 진행률 갱신 ==" -ForegroundColor Cyan
        py "generate_translation_progress_tree.py" @()
        Write-Host "== 완료 ==" -ForegroundColor Green
    }

    "status" {
        Write-ModStatus $Arg1
    }

    "work" {
        Write-WorkHint $Arg1
    }

    default {
        Write-Error "알 수 없는 액션: $Action`n.\run.ps1 --help 로 사용법 확인"
        exit 1
    }
}
