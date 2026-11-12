# Run with PowerShell: .\config\start.ps1 --provider codex
$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'windows.ps1')
$PythonBin = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $PythonBin)) {
    $PythonBin = (Get-Command python -ErrorAction Stop).Source
}
$JobConfig = Join-Path $PSScriptRoot 'job.toml'
if ($env:ENGLISH_CONFIG) { $JobConfig = $env:ENGLISH_CONFIG }
& $PythonBin (Join-Path $ProjectDir 'scripts\watch_pdfs.py') --config $JobConfig @args
exit $LASTEXITCODE
