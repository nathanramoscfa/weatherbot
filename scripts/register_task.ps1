# scripts/register_task.ps1
# Register Windows Scheduled Task for Weatherbot

param(
    [int]$EveryMinutes = 180,  # Default: every 3 hours
    [string]$TaskName = "Weatherbot",
    [switch]$Force
)

Write-Host "🕒 Registering Windows Scheduled Task for Weatherbot..." -ForegroundColor Green

# Check if running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "This script must be run as Administrator to register scheduled tasks."
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Get script paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$RunScript = Join-Path $ScriptDir "run_once.ps1"

# Verify run script exists
if (!(Test-Path $RunScript)) {
    Write-Error "Run script not found: $RunScript"
    exit 1
}

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask -and !$Force) {
    Write-Warning "Task '$TaskName' already exists. Use -Force to replace it."
    Write-Host "Current task settings:" -ForegroundColor Cyan
    Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, LastRunTime, NextRunTime | Format-List
    exit 1
}

# Remove existing task if forced
if ($ExistingTask -and $Force) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create scheduled task action
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File `"$RunScript`""

# Create trigger (repeat every N minutes)
$StartTime = (Get-Date).Date.AddHours(0).AddMinutes(15)  # Start at 00:15 today
$Trigger = New-ScheduledTaskTrigger -Once -At $StartTime -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable

# Create principal (run with highest privileges)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Weatherbot hurricane alert monitoring"
    Write-Host "✅ Scheduled task '$TaskName' registered successfully!" -ForegroundColor Green
} catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}

# Display task information
Write-Host ""
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "Name: $TaskName" -ForegroundColor White
Write-Host "Frequency: Every $EveryMinutes minutes" -ForegroundColor White
Write-Host "Start Time: $StartTime" -ForegroundColor White
Write-Host "Script: $RunScript" -ForegroundColor White
Write-Host "Working Directory: $ProjectRoot" -ForegroundColor White

Write-Host ""
Write-Host "Task Management Commands:" -ForegroundColor Cyan
Write-Host "View task: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "Run now: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "Remove task: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White

Write-Host ""
Write-Host "⚠️ Important Notes:" -ForegroundColor Yellow
Write-Host "- Make sure .env is configured with your coordinates" -ForegroundColor White
Write-Host "- Test manually first: python -m weatherbot run --once" -ForegroundColor White
Write-Host "- Check logs in logs/weatherbot.log" -ForegroundColor White
Write-Host "- Task runs with highest privileges for popup notifications" -ForegroundColor White
