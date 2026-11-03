$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$eventPython = if ($env:PHOTOBOOTH_PYTHON) { $env:PHOTOBOOTH_PYTHON } else { Join-Path $projectRoot 'backend\.venv\Scripts\python.exe' }
& $eventPython (Join-Path $PSScriptRoot 'stop_host.py') @args
exit $LASTEXITCODE
