param(
    [Parameter(Mandatory=$true)][string]$Port,
    [string]$Distribution = 'Ubuntu',
    [string]$LogDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create the Python .venv and install tools/requirements.txt first.' }
$taskWslInput = $taskRoot.Replace('\','/')
$taskLinuxRootResult = & wsl -d $Distribution -- wslpath -a $taskWslInput
if ($LASTEXITCODE -ne 0 -or -not $taskLinuxRootResult) { throw 'WSL path conversion failed.' }
$taskLinuxRoot = $taskLinuxRootResult.Trim()
& wsl -d $Distribution -- make -C $taskLinuxRoot
if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed; no transfer performed.' }
if (-not $LogDirectory) { $LogDirectory = Join-Path $taskRoot 'logs' }
$taskLog = Join-Path $LogDirectory ((Get-Date -Format 'yyyyMMdd-HHmmss')+'-uart-cycle.bin')
& $taskPython (Join-Path $taskRoot 'tools/uart.py') cycle --port $Port --image (Join-Path $taskRoot 'build/app.img') --log $taskLog
if ($LASTEXITCODE -ne 0) { throw 'UART transfer or execution verification failed.' }
Write-Output ('Captured UART log: '+$taskLog)
