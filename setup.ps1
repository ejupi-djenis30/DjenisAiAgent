# PowerShell script to set up the DjenisAiAgent project
# Run with: .\setup.ps1

Write-Host "Setting up DjenisAiAgent project..." -ForegroundColor Cyan

# Check Python version
Write-Host "`nChecking Python version..." -ForegroundColor Green
$pythonVersion = python --version 2>&1
Write-Host "  Found: $pythonVersion" -ForegroundColor Yellow

if ($pythonVersion -notmatch "Python 3\.(9|10|11|12)") {
    Write-Host "  Warning: Python 3.9+ is required!" -ForegroundColor Red
    exit 1
}

# Create virtual environment if it doesn't exist
if (-not (Test-Path "venv")) {
    Write-Host "`nCreating virtual environment..." -ForegroundColor Green
    python -m venv venv
} else {
    Write-Host "`nVirtual environment already exists." -ForegroundColor Yellow
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Green
& ".\venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Green
python -m pip install --upgrade pip

# Install requirements
Write-Host "`nInstalling dependencies..." -ForegroundColor Green
pip install -r requirements.txt

# Install development requirements (optional)
$installDev = Read-Host "`nInstall development dependencies? (y/N)"
if ($installDev -eq "y" -or $installDev -eq "Y") {
    Write-Host "Installing development dependencies..." -ForegroundColor Green
    pip install -r requirements-dev.txt
}

# Create necessary directories
Write-Host "`nCreating project directories..." -ForegroundColor Green
$dirs = @(
    "data",
    "data/screenshots",
    "data/task_memory",
    "data/ui_memory",
    "config"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Yellow
    }
}

# Copy config templates if they don't exist
Write-Host "`nSetting up configuration files..." -ForegroundColor Green

if (-not (Test-Path "config/credentials.json")) {
    if (Test-Path "config/credentials.json.template") {
        Copy-Item "config/credentials.json.template" "config/credentials.json"
        Write-Host "  Created: config/credentials.json (from template)" -ForegroundColor Yellow
        Write-Host "  Please edit this file to add your API keys!" -ForegroundColor Red
    }
}

if (-not (Test-Path "config/default_config.json")) {
    if (Test-Path "config/default_config.json.template") {
        Copy-Item "config/default_config.json.template" "config/default_config.json"
        Write-Host "  Created: config/default_config.json (from template)" -ForegroundColor Yellow
    }
}

# Run tests to verify setup
$runTests = Read-Host "`nRun tests to verify setup? (y/N)"
if ($runTests -eq "y" -or $runTests -eq "Y") {
    Write-Host "`nRunning tests..." -ForegroundColor Green
    pytest tests/ -v
}

Write-Host "`n✓ Setup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Edit config/credentials.json and add your Gemini API key" -ForegroundColor White
Write-Host "  2. Run the agent UI with: python launch_ui.py" -ForegroundColor White
Write-Host "  3. Or run the CLI with: python src/main.py" -ForegroundColor White
Write-Host "`nFor development, you can install pre-commit hooks with:" -ForegroundColor Cyan
Write-Host "  pre-commit install" -ForegroundColor White
