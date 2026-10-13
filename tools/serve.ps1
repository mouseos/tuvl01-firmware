# Loads the application into RAM over UART and has it bring itself up (src/tuner_serve.c):
# tuner, TS path, Wi-Fi radio and access point. It does NOT start streaming; a client
# (BonDriver, phone app) selects the channel and starts/stops it over Wi-Fi (docs/protocol.md).
# A PC is needed here only to load the RAM image; an image built with `make AUTOSERVE=1`
# and stored in the SPI application area brings itself up without any PC.
param(
    [string]$Port='COM3',
    [string]$Image='',
    [string]$Log=''
)
$ErrorActionPreference='Continue'
$fw=Split-Path $PSScriptRoot
$py="$fw\.venv\Scripts\python.exe"
if(-not $Image){$Image="$fw\build\app.img"}
if(-not $Log){$Log="$env:TEMP\tuvl01-serve.uart.bin"}
& $py "$fw\tools\uart.py" cycle --port $Port --image $Image --log $Log 2>&1 | Select-Object -Last 1 | Out-Null
& $py "$fw\tools\uart.py" serve --port $Port --log $Log 2>&1 | Select-Object -Last 1
