# Add the Windows API definition for GetSystemPowerStatus
Add-Type @"
using System;
using System.Runtime.InteropServices;

public struct SYSTEM_POWER_STATUS {
    public byte ACLineStatus;
    public byte BatteryFlag;
    public byte BatteryLifePercent;
    public byte Reserved1;
    public int BatteryLifeTime;
    public int BatteryFullLifeTime;
}

public class PowerStatus {
    [DllImport("kernel32.dll")]
    public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS sps);
}
"@

# Known UPS Vendor/Product mapping
$UPSNameMap = @{
    "VID_05DD&PID_A0A0" = "Minuteman UPS"
    "VID_051D&PID_0002" = "APC Back-UPS"
    # Add more mappings here as needed
}

# Function to auto-detect UPS VendorID and ProductID
function Get-UPSDeviceInfo {
    try {
        $devices = Get-CimInstance Win32_PnPEntity -ErrorAction Stop

        # Find first UPS-like device
        $upsDevice = $devices |
            Where-Object {
                $_.PNPDeviceID -match "(?i)VID_" -and
                $_.PNPDeviceID -match "(?i)PID_" -and
                ($_.Name -match "(?i)UPS" -or $_.Name -match "(?i)Battery")
            } |
            Select-Object -First 1

        if ($upsDevice) {
            $vid = if ($upsDevice.PNPDeviceID -match "VID_([0-9A-F]{4})") { "VID_$($matches[1])" } else { $null }
            $prodId = if ($upsDevice.PNPDeviceID -match "PID_([0-9A-F]{4})") { "PID_$($matches[1])" } else { $null }

            return [PSCustomObject]@{
                Name      = $upsDevice.Name
                VendorID  = $vid
                ProductID = $prodId
            }
        }
    }
    catch {
        Write-Warning "Error detecting UPS device: $_"
    }

    return $null
}

# Function to get friendly UPS name from mapping
function Get-FriendlyUPSName {
    param (
        [string]$VendorID,
        [string]$ProductID,
        [string]$DefaultName
    )

    $key = "$VendorID&$ProductID"
    if ($UPSNameMap.ContainsKey($key)) {
        return $UPSNameMap[$key]
    }
    return $DefaultName
}

# Function to get UPS status from Windows Power API
function Get-UPSStatus {
    param (
        [string]$UPSName
    )

    try {
        $status = New-Object SYSTEM_POWER_STATUS
        if (-not [PowerStatus]::GetSystemPowerStatus([ref]$status)) {
            throw "Unable to retrieve system power status."
        }

        $acStatus = switch ($status.ACLineStatus) {
            0 { "Offline" }
            1 { "Online" }
            default { "Unknown" }
        }

        $batteryPercent = if ($status.BatteryLifePercent -ne 255) {
            "$($status.BatteryLifePercent)%"
        } else {
            "Unknown"
        }

        $batteryLife = if ($status.BatteryLifeTime -ne -1) {
            $ts = [TimeSpan]::FromSeconds($status.BatteryLifeTime)
            "{0:D2}:{1:D2}" -f $ts.Minutes, $ts.Seconds
        } else {
            "Unknown"
        }

        return [PSCustomObject]@{
            Timestamp         = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            UPSName           = $UPSName
            ACLineStatus      = $acStatus
            BatteryPercent    = $batteryPercent
            BatteryLife       = $batteryLife
        }
    }
    catch {
        Write-Warning "Error retrieving UPS status: $_"
        return $null
    }
}

# MAIN EXECUTION
$upsInfo = Get-UPSDeviceInfo

if ($upsInfo) {
    $upsName = Get-FriendlyUPSName -VendorID $upsInfo.VendorID -ProductID $upsInfo.ProductID -DefaultName $upsInfo.Name
    $upsStatus = Get-UPSStatus -UPSName $upsName
    if ($upsStatus) {
        $upsStatus | Format-Table -AutoSize
    }
    else {
        Write-Host "No UPS status available." -ForegroundColor Red
    }
}
else {
    Write-Host "No UPS device detected." -ForegroundColor Red
}
