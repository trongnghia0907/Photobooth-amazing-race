$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$demoPython = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
& $demoPython (Join-Path $PSScriptRoot 'mobile_qr_demo.py') stop
if ($LASTEXITCODE -ne 0) { throw 'Mobile QR demo stop is still pending; inspect its logs.' }
