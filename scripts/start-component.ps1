param([Parameter(Mandatory=$true)][ValidateSet('api','worker','frontend')][string]$Component)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if ($Component -eq 'frontend') {
        Set-Location (Join-Path $projectRoot 'frontend')
        & npm.cmd run dev
    } else {
        $projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Create .venv and install requirements.txt first.' }
        $entry = if ($Component -eq 'api') { 'serve' } else { 'worker' }
        & $projectPython -m tram.cli $entry
    }
    exit $LASTEXITCODE
} finally { Pop-Location }
