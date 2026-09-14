param([string]$OutputDir = (Join-Path $PSScriptRoot 'results'))
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$targets = @(Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match '^(HID|ACPI)\\(VID_045E&PID_0C77|MSHW0238)'
})
$keys = @('DEVPKEY_Device_Parent', 'DEVPKEY_Device_HardwareIds',
          'DEVPKEY_Device_Service', 'DEVPKEY_Device_DriverVersion',
          'DEVPKEY_Device_DriverDate')
$devices = foreach ($device in $targets) {
    $properties = @{}
    foreach ($key in $keys) {
        try {
            $properties[$key] = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName $key).Data
        } catch { $properties[$key] = 'Unavailable' }
    }
    [ordered]@{ InstanceId=$device.InstanceId; Status=$device.Status;
                FriendlyName=$device.FriendlyName; Properties=$properties }
}
$registry = foreach ($device in $targets) {
    $path = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\' + $device.InstanceId + '\Device Parameters'
    if (Test-Path $path) {
        $value = Get-ItemProperty -LiteralPath $path
        $fields = @{}
        foreach ($name in @('EnhancedPowerManagementEnabled','DeviceResetNotificationEnabled','FirmwareIdentified','D3ColdSupported')) {
            if ($null -ne $value.$name) { $fields[$name] = $value.$name }
        }
        [ordered]@{ Path=$path; Values=$fields }
    }
}
$dlls = @(Get-ChildItem -Path "$env:windir\System32\DriverStore\FileRepository\surfacetouchpadprocessorupdate.inf_arm64_*\TouchPenProcessor0C77.dll" -ErrorAction SilentlyContinue | ForEach-Object {
    [ordered]@{ Path=$_.FullName; Version=$_.VersionInfo.FileVersion;
                SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
})
[ordered]@{ Timestamp=(Get-Date).ToString('o'); OS=[Environment]::OSVersion.VersionString;
            Devices=@($devices); Registry=@($registry); ProcessorDlls=$dlls;
            ChangedDeviceSettings=$false } | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $OutputDir "state-$stamp.json") -Encoding UTF8
# Provider discovery only: this command does not start an ETW trace session.
(& logman query providers 2>&1 | Select-String -Pattern 'Surface|Touch|Heat|Haptic|Precision') |
    ForEach-Object { $_.Line } |
    Set-Content -LiteralPath (Join-Path $OutputDir "provider-candidates-$stamp.txt") -Encoding UTF8
Write-Output "Read-only snapshot saved under $OutputDir"
