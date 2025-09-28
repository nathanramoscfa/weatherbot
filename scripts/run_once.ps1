# scripts/run_once.ps1
# Run Weatherbot once (for Task Scheduler)

param(
    [switch]$Verbose
)

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Change to project directory
Set-Location $ProjectRoot

# Check if virtual environment exists
if (!(Test-Path "E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1")) {
    Write-Error "Virtual environment not found at E:\Code\Python\venvs\weatherbot"
    Write-Error "Run: python -m venv E:\Code\Python\venvs\weatherbot"
    exit 1
}

# Activate virtual environment
& E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

# Build command arguments
$Args = @("run", "--once")
if ($Verbose) {
    $Args += "--verbose"
}

# Run Weatherbot
Write-Host "Running Weatherbot..." -ForegroundColor Green
& python -m weatherbot @Args

# Capture exit code
$ExitCode = $LASTEXITCODE

# Log completion
if ($ExitCode -eq 0) {
    Write-Host "Weatherbot completed successfully" -ForegroundColor Green
} else {
    Write-Error "Weatherbot failed with exit code $ExitCode"
}

exit $ExitCode
