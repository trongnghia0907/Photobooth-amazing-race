param([int]$HostPort = 8000, [int]$PublicPort = 8001, [switch]$RequireDrive,
      [switch]$StandaloneDemo, [string]$StorageRoot, [string]$EnvFile)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$demoPython = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $demoPython)) { throw 'Create backend/.venv and install requirements.lock.txt first.' }
$demoArguments = @((Join-Path $PSScriptRoot 'mobile_qr_demo.py'), 'start', '--host-port', $HostPort, '--public-port', $PublicPort)
if ($StandaloneDemo) {
    if (!$PSBoundParameters.ContainsKey('HostPort')) { $demoArguments[3] = 8010 }
    if (!$PSBoundParameters.ContainsKey('PublicPort')) { $demoArguments[5] = 8011 }
} else { $demoArguments += '--attach-host' }
if ($StorageRoot) { $demoArguments += @('--storage-root', $StorageRoot) }
if ($EnvFile) { $demoArguments += @('--env-file', $EnvFile) }
if ($RequireDrive) { $demoArguments += '--require-drive' }
& $demoPython @demoArguments
if ($LASTEXITCODE -ne 0) { throw 'Mobile QR demo setup failed. Inspect .tools/mobile-qr-demo logs.' }
Write-Host 'Open the booth_url above. Attach mode uses your existing Host login and pairing code.'
if ($StandaloneDemo) { Write-Host 'Standalone DEMO credentials only: .tools/mobile-qr-demo/operator.json' }
Write-Host 'Quick Tunnel is temporary. Keep laptop online. Phone scan on 4G/5G is a manual test.'
