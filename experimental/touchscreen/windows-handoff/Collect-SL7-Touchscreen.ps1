# Read-only Windows diagnostics. No driver, registry, boot, or device changes.
# Collect touchscreen PnP metadata and only DSDT/SSDT ACPI tables, never MSDM.
param([string]$OutputDirectory = (Join-Path ([Environment]::GetFolderPath('Desktop')) ('SL7-touchscreen-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))))
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output directory already exists; choose a new directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null

function Read-DeviceMetadata([string]$InstanceId) {
    $device = Get-PnpDevice -InstanceId $InstanceId -ErrorAction SilentlyContinue
    $result = [ordered]@{ InstanceId = $InstanceId; Name = $device.FriendlyName; Class = $device.Class; Status = $device.Status }
    foreach ($key in @('HardwareIds', 'CompatibleIds', 'Parent', 'LocationPaths', 'LocationInfo', 'BusNumber', 'Address', 'Service', 'DriverInfPath', 'BusReportedDeviceDesc')) {
        $property = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName ('DEVPKEY_Device_' + $key) -ErrorAction SilentlyContinue
        if ($null -ne $property) { $result[$key] = $property.Data }
    }
    return $result
}

$devices = @(Get-PnpDevice -PresentOnly -Class HIDClass)
$touch = @()
$hidInventory = @()
foreach ($device in $devices) {
    $metadata = Read-DeviceMetadata $device.InstanceId
    $hidInventory += $metadata
    $ids = @($metadata['CompatibleIds']) -join ';'
    # HID digitizer usage page 0x0D, touchscreen usage 0x04.
    if ($ids -match 'HID_DEVICE_UP:000D_U:0004') {
        $chain = @($metadata)
        $parent = $metadata['Parent']
        for ($depth = 0; $depth -lt 5 -and $parent; $depth++) {
            $node = Read-DeviceMetadata $parent
            $chain += $node
            $parent = $node['Parent']
        }
        $touch += [pscustomobject]@{ Devices = $chain }
    }
}
[pscustomobject]@{
    CapturedAt = (Get-Date).ToString('o')
    Touchscreens = $touch
    HidMetadata = $hidInventory
    Note = 'Device metadata only; no input events or credential stores were read.'
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'pnp.json') -Encoding UTF8

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SL7FirmwareTables {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint EnumSystemFirmwareTables(uint provider, [Out] byte[] buffer, uint size);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint GetSystemFirmwareTable(uint provider, uint tableId, [Out] byte[] buffer, uint size);
}
'@
$provider = [uint32]0x41435049 # 'ACPI' provider, per Microsoft API.
$tableLog = @()
try {
    $size = [SL7FirmwareTables]::EnumSystemFirmwareTables($provider, $null, 0)
    if ($size -eq 0 -or $size -gt 65536 -or ($size % 4) -ne 0) { throw ('Invalid ACPI table list size: ' + $size) }
    $list = New-Object byte[] $size
    $received = [SL7FirmwareTables]::EnumSystemFirmwareTables($provider, $list, $size)
    if ($received -ne $size) { throw 'ACPI table list changed while being read.' }
    $seen = @{}
    for ($offset = 0; $offset -lt $size; $offset += 4) {
        $id = [BitConverter]::ToUInt32($list, $offset)
        $signature = [Text.Encoding]::ASCII.GetString($list, $offset, 4)
        if ($signature -notin @('DSDT', 'SSDT')) { continue }
        if ($seen.ContainsKey($signature)) { continue }
        $seen[$signature] = $true
        $length = [SL7FirmwareTables]::GetSystemFirmwareTable($provider, $id, $null, 0)
        if ($length -lt 36 -or $length -gt 16777216) { throw ('Unexpected table length for ' + $signature) }
        $data = New-Object byte[] $length
        $actual = [SL7FirmwareTables]::GetSystemFirmwareTable($provider, $id, $data, $length)
        if ($actual -ne $length -or [Text.Encoding]::ASCII.GetString($data, 0, 4) -ne $signature) { throw 'Table verification failed.' }
        [IO.File]::WriteAllBytes((Join-Path $OutputDirectory ($signature + '.aml')), $data)
        $tableLog += [pscustomobject]@{ Signature = $signature; Bytes = $length }
    }
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $OutputDirectory 'firmware-read-error.txt') -Encoding UTF8
}
[pscustomobject]@{
    Tables = $tableLog
    Limitation = 'Windows GetSystemFirmwareTable returns only the first table for duplicate signatures; SSDT output may be incomplete.'
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'tables.json') -Encoding UTF8
# Optional read-only fallback: some Windows versions expose additional ACPI
# copies in these volatile registry branches. Never visit the MSDM branch.
$registryTables = @()
foreach ($signature in @('DSDT', 'SSDT')) {
    $branch = 'Registry::HKEY_LOCAL_MACHINE\HARDWARE\ACPI\' + $signature
    if (-not (Test-Path -LiteralPath $branch)) { continue }
    $keys = @((Get-Item -LiteralPath $branch)) + @(Get-ChildItem -LiteralPath $branch -Recurse -ErrorAction SilentlyContinue)
    $index = 0
    foreach ($key in $keys) {
        foreach ($valueName in $key.GetValueNames()) {
            $data = $key.GetValue($valueName)
            if ($data -isnot [byte[]] -or $data.Length -lt 36 -or $data.Length -gt 16777216) { continue }
            if ([Text.Encoding]::ASCII.GetString($data, 0, 4) -ne $signature) { continue }
            if ([BitConverter]::ToUInt32($data, 4) -ne $data.Length) { continue }
            $index++
            $name = '{0}-registry-{1:D2}.aml' -f $signature, $index
            [IO.File]::WriteAllBytes((Join-Path $OutputDirectory $name), $data)
            $registryTables += [pscustomobject]@{ File = $name; RegistryPath = $key.Name; Value = $valueName; Bytes = $data.Length }
        }
    }
}
ConvertTo-Json -InputObject $registryTables -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'registry-tables.json') -Encoding UTF8
Get-ChildItem -LiteralPath $OutputDirectory -File | Where-Object { $_.Name -ne 'hashes.json' } | Get-FileHash -Algorithm SHA256 |
    Select-Object Hash, Path | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'hashes.json') -Encoding UTF8
Write-Host ('Diagnostics saved to: ' + $OutputDirectory)
Write-Host ('Touchscreen candidates: ' + $touch.Count)
