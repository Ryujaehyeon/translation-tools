param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ArgsForTranslator
)

$ErrorActionPreference = "Stop"

$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackRoot = Split-Path -Parent $ScriptDir
$Translator = Join-Path $ScriptDir "translate_keys.py"

Push-Location $PackRoot
try {
    python $Translator @ArgsForTranslator
}
finally {
    Pop-Location
}
