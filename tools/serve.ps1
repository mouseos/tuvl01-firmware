# Brings the board up over UART and leaves it serving the Wi-Fi protocol (docs/protocol.md):
# tuner tuned, TS path configured, AP running. It does NOT start streaming; a client
# (BonDriver, phone app, tools/..) starts and stops it over Wi-Fi.
# The tuner profile JSON (32-byte profile for tune.py) is supplied by the caller.
param(
    [Parameter(Mandatory)][string]$Profile,
    [string]$Port='COM3',
    [string]$Image='',
    [string]$Log='',
    [string]$Extra='ts-pipeline,ts-burst,ts-aggregate'
)
$ErrorActionPreference='Continue'
$fw=Split-Path $PSScriptRoot
$py="$fw\.venv\Scripts\python.exe"
if(-not $Image){$Image="$fw\build\app.img"}
if(-not $Log){$Log="$env:TEMP\tuvl01-serve.uart.bin"}
function U($c){ & $py "$fw\tools\uart.py" $c --port $Port --log $Log 2>&1 | Select-Object -Last 1 }
& $py "$fw\tools\uart.py" cycle --port $Port --image $Image --log $Log 2>&1 | Select-Object -Last 1 | Out-Null
# The tuner/TS setup must precede the Wi-Fi radio start.
U 'tuner-init' | Out-Null
& $py "$fw\tools\tune.py" --port $Port --profile $Profile --log $Log 2>&1 | Out-Null
Start-Sleep 6
foreach($c in 'ts-output','ts-dma','ts-clock-max','ts-dma-long','icache'){ U $c | Out-Null }
$seq=@('wifi','wifi-clock','wifi-width','wifi-read-poll','wifi-write-poll','wifi-poll-budget','mac','capability','board','wifi-irq')
$seq += ($Extra -split ',' | Where-Object { $_ })
$seq += 'ap'
foreach($c in $seq){ $r=U $c; if($c -in 'wifi','ap'){ "  $c -> $r" } }
"  tmcc: " + (U 'tmcc')
