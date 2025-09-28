# scripts/activate_env.ps1
# Quick script to activate the virtual environment

$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (Test-Path "E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1") {
    Write-Host "🐍 Activating Weatherbot virtual environment..." -ForegroundColor Green
    & "E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1"
    Write-Host "✅ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Warning "Virtual environment not found at E:\Code\Python\venvs\weatherbot"
    Write-Warning "Please create it with: python -m venv E:\Code\Python\venvs\weatherbot"
}
