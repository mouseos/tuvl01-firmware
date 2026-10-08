# SPDX-License-Identifier: MIT
# Read-only Windows Mobile Hotspot preflight. Windows PowerShell 5.1.
$ErrorActionPreference='Stop'
try {
    $taskInfo=[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
    $taskType=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $taskBandType=[Windows.Networking.NetworkOperators.TetheringWiFiBand,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $taskProfile=$taskInfo::GetInternetConnectionProfile()
    if($null -eq $taskProfile){[pscustomobject]@{read_only=$true;profile_present=$false;ap_started=$false;credentials_read=$false}|ConvertTo-Json -Compress;exit 0}
    $taskManager=$taskType::CreateFromConnectionProfile($taskProfile)
    $taskConfiguration=$taskManager.GetCurrentAccessPointConfiguration()
    $taskResult=[ordered]@{read_only=$true;capability=$taskType::GetTetheringCapabilityFromConnectionProfile($taskProfile).ToString();operational_state=$taskManager.TetheringOperationalState.ToString();configured_band=$taskConfiguration.Band.ToString();band_2_4_supported=$taskConfiguration.IsBandSupported($taskBandType::TwoPointFourGigahertz);max_clients=$taskManager.MaxClientCount;ap_started=$false;credentials_read=$false}
    $taskResult|ConvertTo-Json -Compress
} catch {
    [pscustomobject]@{error_type=$_.Exception.GetType().FullName;hresult=$_.Exception.HResult;read_only=$true}|ConvertTo-Json -Compress
    exit 1
}
