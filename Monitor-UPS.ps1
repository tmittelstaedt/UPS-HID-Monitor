param(
    [switch]$Server,
    [string]$NutServer,
    [string]$UpsName
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- Helper Functions ---
function Format-BatteryFlag {
    param([byte]$flag)
    $flags = @()
    if ($flag -band 1)   { $flags += "High (>66%)" }
    if ($flag -band 2)   { $flags += "Low (<33%)" }
    if ($flag -band 4)   { $flags += "Critical (<5%)" }
    if ($flag -band 8)   { $flags += "Charging" }
    if ($flag -band 128) { $flags += "No battery" }
    if (-not $flags) { $flags += "Unknown" }
    return ($flags -join ", ")
}

function Format-FullChargeTime {
    param([int]$seconds)
    if ($seconds -ge 0) {
        $ts = [TimeSpan]::FromSeconds($seconds)
        return "{0:D2}:{1:D2}:{2:D2}" -f $ts.Hours, $ts.Minutes, $ts.Seconds
    }
    else {
        return "Unknown"
    }
}

# --- Local UPS Status ---
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
public class NativeMethods {
    [DllImport("kernel32.dll")]
    public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS sps);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern bool DestroyIcon(IntPtr handle);
}
"@

# function Get-LocalUPSStatus {
#     $status = New-Object SYSTEM_POWER_STATUS
#     [NativeMethods]::GetSystemPowerStatus([ref]$status) | Out-Null
#     return $status
# }


function Get-LocalUPSStatus {
    # Touch WMI to force HID UPS driver to refresh
    try {
        $null = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
    } catch { }

    # Now call the API
    $status = New-Object SYSTEM_POWER_STATUS
    if (-not ([NativeMethods]::GetSystemPowerStatus([ref]$status))) {
        throw "Unable to get power status."
    }
    return $status
}


function Get-LocalUPSName {
    try {
        $name = (Get-CimInstance Win32_Battery | Select-Object -First 1 -ExpandProperty Name)
        if ([string]::IsNullOrWhiteSpace($name)) {
            return "Local UPS"
        }
        return $name
    }
    catch {
        return "Local UPS"
    }
}

function Get-LocalUPSDetails {
    try {
        $batt = Get-CimInstance Win32_Battery | Select-Object -First 1
        if (-not $batt) { return $null }

        [PSCustomObject]@{
            Name                   = $batt.Name
            Status                 = $batt.Status
            BatteryStatus          = $batt.BatteryStatus
            EstimatedChargeRemaining = $batt.EstimatedChargeRemaining
            EstimatedRunTime       = if ($batt.EstimatedRunTime -ge 0) { "$($batt.EstimatedRunTime) min" } else { "Unknown" }
            TimeOnBattery          = if ($batt.TimeOnBattery -ge 0) { "$($batt.TimeOnBattery) sec" } else { "Unknown" }
            DesignVoltage          = if ($batt.DesignVoltage) { "$($batt.DesignVoltage / 1000.0) V" } else { "Unknown" }
            Chemistry              = $batt.Chemistry
            DesignCapacity         = $batt.DesignCapacity
            FullChargeCapacity     = $batt.FullChargeCapacity
        }
    }
    catch {
        return $null
    }
}

# --- NUT UPS Status ---
function Get-NutUPSStatus {
    param (
        [string]$NutServer,
        [string]$UpsName,
        [int]$TimeoutSeconds = 60
    )
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($NutServer, 3493, $null, $null)

        if (-not $async.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds), $false)) {
            $client.Close()
            throw "Timeout: Unable to connect to NUT server ${NutServer}:${UpsName} within $TimeoutSeconds seconds."
        }

        $client.EndConnect($async)
        $stream = $client.GetStream()
        $writer = New-Object System.IO.StreamWriter($stream)
        $reader = New-Object System.IO.StreamReader($stream)

        $writer.WriteLine("LIST VAR $UpsName")
        $writer.Flush()

        $status = @{}
        while ($true) {
            $line = $reader.ReadLine()
            if (-not $line) { break }

            if ($line -match '^ERR\s+DATA-STALE') {
                throw "NUT server reports UPS data stale for $UpsName."
            }

            if ($line -match ('^VAR\s+' + $UpsName + '\s+(\S+)\s+"(.+)"$')) {
                $status[$matches[1]] = $matches[2]
            }
            elseif ($line -match '^END') {
                break
            }
        }

        $reader.Close()
        $writer.Close()
        $client.Close()

        if ($status.Count -eq 0) {
            throw "No UPS data returned from NUT server for $UpsName."
        }

        return $status
    }
    catch {
        Write-Warning "Error querying NUT server: $_"
        return $null
    }
}

# --- Icon Drawing ---
function New-UPSIcon {
    param (
        [string]$text = "UPS",
        [System.Drawing.Color]$bgColor = [System.Drawing.Color]::Green
    )
    $bmp = [System.Drawing.Bitmap]::new(32, 32)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear($bgColor)

    $fontFamily = [System.Drawing.FontFamily]::new("Arial Narrow")
    $maxRect = [System.Drawing.RectangleF]::new(0, 0, 32, 32)

    $fontSize = 20.0
    do {
        $font = [System.Drawing.Font]::new($fontFamily, [float]$fontSize, [System.Drawing.FontStyle]::Bold)
        $size = $g.MeasureString($text, $font)
        if ($size.Width -le $maxRect.Width -and $size.Height -le $maxRect.Height) { break }
        $fontSize -= 0.5
    } while ($fontSize -gt 1)

    $sf = [System.Drawing.StringFormat]::new()
    $sf.Alignment = [System.Drawing.StringAlignment]::Center
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    $g.DrawString($text, $font, [System.Drawing.Brushes]::White, $maxRect, $sf)
    $g.Dispose()
    return $bmp
}

# --- Tray Icon Setup ---
$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Visible = $true
$notifyIcon.Text = "UPS Monitor"

$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$notifyIcon.ContextMenuStrip = $contextMenu

# --- Shutdown Tracking ---
$shutdownPending = $false
$shutdownStartTime = $null
$shutdownDelaySeconds = 300  # 5 minutes

# --- TCP Server Setup ---
$enableTcpServer = $Server -and -not ($NutServer -and $UpsName)
if ($enableTcpServer) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, 50000)
    $listener.Start()
    Write-Host "UPS status server listening on port 50000..."
}

# --- Update Timer ---
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000

# Script-level variables
if (-not (Get-Variable -Name acOfflineCount -Scope Script -ErrorAction SilentlyContinue)) { $script:acOfflineCount = 0 }
if (-not (Get-Variable -Name shutdownPending -Scope Script -ErrorAction SilentlyContinue)) { $script:shutdownPending = $false }
if (-not (Get-Variable -Name shutdownStartTime -Scope Script -ErrorAction SilentlyContinue)) { $script:shutdownStartTime = $null }
if (-not (Get-Variable -Name lastUPSStatus -Scope Script -ErrorAction SilentlyContinue)) { $script:lastUPSStatus = $null }
if (-not (Get-Variable -Name lastUPSReadTime -Scope Script -ErrorAction SilentlyContinue)) { $script:lastUPSReadTime = Get-Date 0 }
if (-not (Get-Variable -Name pollCount -Scope Script -ErrorAction SilentlyContinue)) { $script:pollCount = 0 }

$updateAction = {
    $contextMenu.Items.Clear()

    $now = Get-Date
    $status = $null
    $acStatus = 255
    $percent = "Unknown"

    # Increment poll counter
    $script:pollCount++

    # Only poll UPS if at least 5 seconds since last read
    if (($now - $script:lastUPSReadTime).TotalSeconds -ge 5 -or -not $script:lastUPSStatus) {
        
        # WMI poke only every 5 polls
        if ($script:pollCount -ge 3) {
            $null = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
            $script:pollCount = 0
        }

        if ($NutServer -and $UpsName) {
            $script:lastUPSStatus = Get-NutUPSStatus -NutServer $NutServer -UpsName $UpsName
        }
        else {
            $script:lastUPSStatus = @{
                Status  = Get-LocalUPSStatus
                Details = Get-LocalUPSDetails
            }
        }
        $script:lastUPSReadTime = $now
    }

    # --- NUT Server Mode ---
    if ($NutServer -and $UpsName) {
        $status = $script:lastUPSStatus
        if ($status) {
            foreach ($key in $status.Keys) {
                $contextMenu.Items.Add("${key}: $($status[$key])") | Out-Null
            }
            if ($status.ContainsKey("battery.charging")) {
                $contextMenu.Items.Add("Charging: $($status["battery.charging"])") | Out-Null
            }
            if ($status.ContainsKey("battery.runtime.to.full")) {
                $contextMenu.Items.Add("Time to Full: $(Format-FullChargeTime([int]$status["battery.runtime.to.full"]))") | Out-Null
            }
            $acStatus = if ($status["ups.status"] -match "OL") { 1 } elseif ($status["ups.status"] -match "OB") { 0 } else { 255 }
            $percent  = if ($status["battery.charge"]) { "$($status["battery.charge"])%" } else { "Unknown" }
        }
        else {
            $contextMenu.Items.Add("UPS data unavailable") | Out-Null
        }
    }
    # --- Local UPS Mode ---
    else {
        $status  = $script:lastUPSStatus.Status
        $details = $script:lastUPSStatus.Details
        $contextMenu.Items.Add("UPS: $(Get-LocalUPSName)") | Out-Null
        $contextMenu.Items.Add("ACLineStatus: $($status.ACLineStatus)") | Out-Null
        $contextMenu.Items.Add("BatteryLifePercent: $($status.BatteryLifePercent)%") | Out-Null
        $contextMenu.Items.Add("Battery Flags: $(Format-BatteryFlag $status.BatteryFlag)") | Out-Null
        $contextMenu.Items.Add("Time to Full: $(Format-FullChargeTime $status.BatteryFullLifeTime)") | Out-Null
        if ($details.EstimatedRunTime -gt 0) {
            $contextMenu.Items.Add("Runtime: $($details.EstimatedRunTime)") | Out-Null
        }
        $acStatus = $status.ACLineStatus
        $percent  = if ($status.BatteryLifePercent -ne 255) { "$($status.BatteryLifePercent)%" } else { "Unknown" }
    }

    # --- Debounce AC status changes ---
    if ($acStatus -eq 0) {
        Start-Sleep -Milliseconds 300
        if ((Get-LocalUPSStatus).ACLineStatus -eq 0) {
            $script:acOfflineCount++
        }
    }
    else {
        $script:acOfflineCount = 0
    }

    if ($script:acOfflineCount -ge 2) {
        if (-not $script:shutdownPending) {
            $script:shutdownPending   = $true
            $script:shutdownStartTime = Get-Date
            Write-Host "AC power lost. Shutdown scheduled in 5 minutes unless power returns."
        }
    }
    elseif ($acStatus -eq 1 -and $script:shutdownPending) {
        $script:shutdownPending   = $false
        $script:shutdownStartTime = $null
        Write-Host "AC power restored. Shutdown cancelled."
    }

    # --- Status handling for icon color and tooltip ---
    if ($acStatus -eq 1) {
        $bmp = New-UPSIcon -bgColor ([System.Drawing.Color]::Green)
        $notifyIcon.Text = "Online ($percent)"
        $shutdownPending = $false
        $shutdownStartTime = $null
    }
    elseif ($acStatus -eq 0) {
        $bmp = New-UPSIcon -bgColor ([System.Drawing.Color]::Red)
        $notifyIcon.Text = "On Battery ($percent)"
        if (-not $shutdownPending) {
            $shutdownPending = $true
            $shutdownStartTime = Get-Date
            Write-Host "AC power lost. Shutdown scheduled in 5 minutes unless power returns."
        }
        else {
            $elapsed = (Get-Date) - $shutdownStartTime
            if ($elapsed.TotalSeconds -ge $shutdownDelaySeconds) {
                Write-Host "AC power still offline after 5 minutes. Shutting down..."
                Stop-Computer -Force
            }
        }
    }
    else {
        $bmp = New-UPSIcon -bgColor ([System.Drawing.Color]::Gray)
        $notifyIcon.Text = "Status Unknown"
        $shutdownPending = $false
        $shutdownStartTime = $null
    }

    # --- Append extra info to tooltip ---
    if ($NutServer -and $UpsName) {
        if ($status -and $status.ContainsKey("battery.charging")) {
            $notifyIcon.Text += " - Charging"
        }
        if ($status -and $status.ContainsKey("battery.runtime.to.full")) {
            $notifyIcon.Text += " - Full in $(Format-FullChargeTime([int]$status["battery.runtime.to.full"]))"
        }
    }
    else {
        $notifyIcon.Text += " - $(Format-BatteryFlag $status.BatteryFlag)"
        $notifyIcon.Text += " - Full in $(Format-FullChargeTime $status.BatteryFullLifeTime)"
    }

    # --- Dispose old icons to prevent GDI+ leaks ---
    if ($notifyIcon.Icon) {
        $notifyIcon.Icon.Dispose()
    }
    $hIcon = $bmp.GetHicon()
    $newIcon = [System.Drawing.Icon]::FromHandle($hIcon)
    $notifyIcon.Icon = $newIcon
    $bmp.Dispose()
    [NativeMethods]::DestroyIcon($hIcon) | Out-Null

    # --- Add separator and Exit option ---
    $contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
    $exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $exitItem.Text = "Exit"
    $exitItem.Add_Click({
        $notifyIcon.Visible = $false
        $notifyIcon.Dispose()
        if ($enableTcpServer -and $listener) { $listener.Stop() }
        [System.Windows.Forms.Application]::Exit()
    })
    $contextMenu.Items.Add($exitItem) | Out-Null

    # --- Handle TCP server requests ---
    if ($enableTcpServer -and $listener -and $listener.Pending()) {
        try {
            $client = $listener.AcceptTcpClient()
            $stream = $client.GetStream()

            $acText = if ($acStatus -eq 0) { "On Battery" } elseif ($acStatus -eq 1) { "Online" } else { "Unknown" }
            $percentValue = if ($percent -ne "Unknown" -and $percent) { $percent.TrimEnd('%') } else { $null }
            $details = Get-CimInstance Win32_Battery | Select-Object -First 1
            $statusObj = [PSCustomObject]@{
                UPSName = $(if ($UpsName) { $UpsName } else { Get-LocalUPSName })
                Status         = $acText
                BatteryPercent = $percentValue
                EstimatedRunTime = if ($details.EstimatedRunTime -gt 0) { $details.EstimatedRunTime } else { $null }
                ChargingStatus = if ($NutServer -and $UpsName -and $status) {
                    if ($status.ContainsKey("battery.charging")) { $status["battery.charging"] } else { $null }
                } elseif ($status) {
                    if ($status.BatteryFlag -band 8) { "Charging" }
                    elseif ($status.BatteryFlag -band 4) { "Critical (<5%)" }
                    elseif ($status.BatteryFlag -band 2) { "Low (<33%)" }
                    elseif ($status.BatteryFlag -band 1) { "High (>66%)" }
                    else { "Unknown" }
                } else { $null }
                TimeToFull     = if ($NutServer -and $UpsName -and $status) {
                    if ($status.ContainsKey("battery.runtime.to.full")) {
                        Format-FullChargeTime([int]$status["battery.runtime.to.full"])
                    } else { $null }
                } elseif ($status) {
                    Format-FullChargeTime $status.BatteryFullLifeTime
                } else { $null }
                TimestampUTC   = (Get-Date).ToUniversalTime().ToString("o")
            }

            $json = $statusObj | ConvertTo-Json -Compress
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
            $stream.Write($bytes, 0, $bytes.Length)

            $stream.Close()
            $client.Close()
        }
        catch {
            Write-Warning "TCP server error: $_"
        }
    }
}

# --- Hook up the timer ---
$timer.Add_Tick($updateAction)
$timer.Start()

# --- Run the WinForms message loop ---
[System.Windows.Forms.Application]::Run()

# --- Cleanup on exit ---
if ($enableTcpServer -and $listener) {
    $listener.Stop()
}
if ($notifyIcon) {
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
}


