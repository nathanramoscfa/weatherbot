# scripts/install_dev.ps1
# Development installation script for weatherbot

param(
    [string]$PythonVersion = "3.11"
)

Write-Host "🚀 Setting up Weatherbot development environment..." -ForegroundColor Green

# Check if we're in the project root
if (!(Test-Path "pyproject.toml")) {
    Write-Error "Please run this script from the project root directory"
    exit 1
}

# Check for Python installation
Write-Host "Checking Python installation..." -ForegroundColor Yellow

# Try different Python commands
$PythonCmd = $null
$PythonExes = @("python", "python3", "py")

foreach ($cmd in $PythonExes) {
    try {
        $version = & $cmd --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -match "Python (\d+\.\d+)") {
            $PythonCmd = $cmd
            Write-Host "Found Python: $version using command '$cmd'" -ForegroundColor Green
            break
        }
    } catch {
        continue
    }
}

if (-not $PythonCmd) {
    Write-Host ""
    Write-Host "❌ Python not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python first:" -ForegroundColor Yellow
    Write-Host "1. Go to https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "2. Download Python 3.11 or newer" -ForegroundColor White
    Write-Host "3. During installation, check 'Add Python to PATH'" -ForegroundColor White
    Write-Host "4. After installation, restart PowerShell and run this script again" -ForegroundColor White
    Write-Host ""
    Write-Host "Alternative: Install via winget:" -ForegroundColor Yellow
    Write-Host "winget install Python.Python.3.11" -ForegroundColor White
    exit 1
}

# Create virtual environment
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
try {
    & $PythonCmd -m venv weatherbot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment"
    }
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
} catch {
    Write-Error "Failed to create virtual environment: $_"
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
try {
    & E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to activate virtual environment"
    }
    Write-Host "✅ Virtual environment activated" -ForegroundColor Green
} catch {
    Write-Error "Failed to activate virtual environment: $_"
    Write-Host ""
    Write-Host "You may need to change the execution policy:" -ForegroundColor Yellow
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor White
    exit 1
}

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& python -m pip install --upgrade pip
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Pip upgraded" -ForegroundColor Green
} else {
    Write-Warning "Failed to upgrade pip (continuing anyway)"
}

# Install package in development mode
Write-Host "Installing Weatherbot in development mode..." -ForegroundColor Yellow
& pip install -e .[dev]
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install Weatherbot. Check the error messages above."
    exit 1
}
Write-Host "✅ Weatherbot installed" -ForegroundColor Green

# Install pre-commit hooks
Write-Host "Installing pre-commit hooks..." -ForegroundColor Yellow
& pre-commit install
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Failed to install pre-commit hooks (optional)"
} else {
    Write-Host "✅ Pre-commit hooks installed" -ForegroundColor Green
}

# Copy .env.example to .env if it doesn't exist
if (!(Test-Path ".env")) {
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item "env.example" ".env"
    Write-Host "📝 Please edit .env with your location coordinates!" -ForegroundColor Cyan
} else {
    Write-Host ".env file already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ Development environment setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env with your coordinates:" -ForegroundColor White
Write-Host "   notepad .env" -ForegroundColor Gray
Write-Host "2. Test installation:" -ForegroundColor White
Write-Host "   python -m weatherbot --help" -ForegroundColor Gray
Write-Host "3. Test alerts:" -ForegroundColor White
Write-Host "   python -m weatherbot test-alert" -ForegroundColor Gray
Write-Host "4. Run once:" -ForegroundColor White
Write-Host "   python -m weatherbot run --once" -ForegroundColor Gray
Write-Host ""
Write-Host "To activate the environment later:" -ForegroundColor Cyan
Write-Host "E:\Code\Python\venvs\weatherbot\Scripts\Activate.ps1" -ForegroundColor White