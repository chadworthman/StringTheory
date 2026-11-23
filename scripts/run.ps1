# Run String Theory on a Windows home computer (desktop or laptop), no Raspberry Pi needed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run.ps1
#
# Starts the light engine and the control page; close this window (or Ctrl-C) to stop. The lights only
# follow the show and the schedule while this is running, so keep the computer awake and on your Wi-Fi.
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $env:STRINGTHEORY_DATA) { $env:STRINGTHEORY_DATA = Join-Path $Repo 'data' }
if (-not $env:PORT) { $env:PORT = '8080' }
$Venv = Join-Path $Repo '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'

if (-not (Test-Path $Py)) {
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))"
  if ($LASTEXITCODE) { Write-Host 'Needs Python 3.11 or newer from python.org (tick "Add to PATH").'; exit 1 }
  py -3 -m venv $Venv
}
& $Py -c "import tinytuya" 2>$null
if ($LASTEXITCODE) { & $Py -m pip install -q tinytuya }

New-Item -ItemType Directory -Force $env:STRINGTHEORY_DATA | Out-Null
if (-not (Test-Path (Join-Path $env:STRINGTHEORY_DATA 'devices.json'))) {
  Write-Host 'First, your keys: the tinytuya wizard makes devices.json (see the README for the Tuya account steps).'
  if ((Read-Host 'Run the wizard now? [y/N]') -notmatch '^[Yy]') { Write-Host "Put devices.json in $env:STRINGTHEORY_DATA and run this again."; exit 0 }
  Push-Location $env:STRINGTHEORY_DATA; & $Py -m tinytuya wizard; Pop-Location
}
if (-not (Test-Path (Join-Path $env:STRINGTHEORY_DATA 'config.json'))) { & $Py (Join-Path $Repo 'pi\configure.py') }

$engine = Start-Process -PassThru -NoNewWindow $Py -ArgumentList @((Join-Path $Repo 'pi\lights.py'), 'run')
$web = Start-Process -PassThru -NoNewWindow $Py -ArgumentList @((Join-Path $Repo 'pi\web.py'))
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -in 'Dhcp', 'Manual' -and $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress
Write-Host ''
Write-Host "String Theory is running. On your phone (same Wi-Fi), open http://$($ip):$($env:PORT)"
Write-Host 'If Windows asks, allow Python on private networks. Close this window to stop.'
try { Wait-Process -Id $engine.Id, $web.Id } finally { Stop-Process -Id $engine.Id, $web.Id -ErrorAction SilentlyContinue }
