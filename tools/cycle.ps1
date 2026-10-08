param([string]$Port, [int]$Seconds=15)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install tools/requirements.txt first' }
$linuxRoot=$taskRoot -replace '\\','/' -replace '^D:','/mnt/d'
wsl -d Ubuntu -- bash -lc "cd '$linuxRoot' && make"
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
& $taskPython (Join-Path $PSScriptRoot 'host.py') cycle (Join-Path $taskRoot 'build/app.img')
if ($LASTEXITCODE -ne 0) { throw 'USB cycle failed' }
if ($Port) { & $taskPython (Join-Path $PSScriptRoot 'log.py') $Port --seconds $Seconds --output (Join-Path $taskRoot 'logs/uart.txt') }
