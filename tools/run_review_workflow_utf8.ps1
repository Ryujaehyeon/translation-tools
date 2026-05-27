param(
    [switch]$All,
    [switch]$FixQuotes,
    [switch]$MarkRetranslate,
    [switch]$MarkErrors,
    [switch]$Quality,
    [string[]]$Mod = @(),
    [string[]]$Reason = @()
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 > $null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$packRoot = Split-Path -Parent $scriptDir
Set-Location $packRoot

if ($MarkRetranslate -and $MarkErrors) {
    throw "-MarkRetranslate and -MarkErrors cannot be used together."
}
if ($Quality -and $MarkErrors) {
    throw "-Quality and -MarkErrors cannot be used together."
}
if ($Quality -and $Reason.Count -gt 0) {
    throw "-Quality and -Reason cannot be used together."
}

$modArgs = @()
foreach ($m in $Mod) {
    if ($m) {
        $modArgs += @("--mod", $m)
    }
}

Write-Host "== token validation =="
python .\tools\validate_auto_key_tokens.py @modArgs

if ($FixQuotes) {
    $quoteReport = Get-ChildItem .\maintenance\reports\token_validation -Filter "quote_issues_*.csv" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($quoteReport -and $quoteReport.Length -gt 0) {
        Write-Host "== fix quote issues =="
        python .\tools\fix_quote_issues.py --report $quoteReport.FullName
        Write-Host "== token validation after quote fix =="
        python .\tools\validate_auto_key_tokens.py @modArgs
    } else {
        Write-Host "== no quote issues to fix =="
    }
}

$reviewArgs = @()
$reviewArgs += $modArgs
if ($Quality) {
    $reviewArgs += "--quality"
}
if ($MarkRetranslate) {
    $reviewArgs += "--mark-retranslate"
}
if ($MarkErrors) {
    $reviewArgs += "--mark-errors"
}
if ($Reason.Count -gt 0) {
    $reviewArgs += "--reason"
    foreach ($r in $Reason) {
        if ($r) {
            $reviewArgs += $r
        }
    }
}

Write-Host "== review report =="
python .\tools\review_report.py @reviewArgs
