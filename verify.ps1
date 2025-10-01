# Project Verification Script
# Run this to verify the project is properly set up

Write-Host "=== DjenisAiAgent Project Verification ===" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Function to check file existence
function Test-FileExists {
    param([string]$Path, [string]$Description)
    
    if (Test-Path $Path) {
        Write-Host "✓ $Description" -ForegroundColor Green
        return $true
    } else {
        Write-Host "✗ $Description - MISSING" -ForegroundColor Red
        return $false
    }
}

# Function to check directory existence
function Test-DirectoryExists {
    param([string]$Path, [string]$Description)
    
    if (Test-Path $Path -PathType Container) {
        Write-Host "✓ $Description" -ForegroundColor Green
        return $true
    } else {
        Write-Host "✗ $Description - MISSING" -ForegroundColor Red
        return $false
    }
}

Write-Host "Checking core files..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-FileExists "README.md" "README.md")
$allGood = $allGood -and (Test-FileExists "requirements.txt" "requirements.txt")
$allGood = $allGood -and (Test-FileExists "launch_ui.py" "launch_ui.py")
$allGood = $allGood -and (Test-FileExists "setup.py" "setup.py")
Write-Host ""

Write-Host "Checking documentation..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-FileExists "QUICKSTART.md" "QUICKSTART.md")
$allGood = $allGood -and (Test-FileExists "CONTRIBUTING.md" "CONTRIBUTING.md")
$allGood = $allGood -and (Test-FileExists "CHANGELOG.md" "CHANGELOG.md")
$allGood = $allGood -and (Test-FileExists "LICENSE" "LICENSE")
$allGood = $allGood -and (Test-FileExists "docs\README.md" "docs\README.md")
$allGood = $allGood -and (Test-FileExists "docs\getting-started.md" "docs\getting-started.md")
$allGood = $allGood -and (Test-FileExists "docs\architecture.md" "docs\architecture.md")
Write-Host ""

Write-Host "Checking configuration files..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-FileExists "pyproject.toml" "pyproject.toml")
$allGood = $allGood -and (Test-FileExists ".editorconfig" ".editorconfig")
$allGood = $allGood -and (Test-FileExists ".gitignore" ".gitignore")
$allGood = $allGood -and (Test-FileExists ".pre-commit-config.yaml" ".pre-commit-config.yaml")
Write-Host ""

Write-Host "Checking automation scripts..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-FileExists "setup.ps1" "setup.ps1")
$allGood = $allGood -and (Test-FileExists "clean.ps1" "clean.ps1")
$allGood = $allGood -and (Test-FileExists "Makefile" "Makefile")
Write-Host ""

Write-Host "Checking GitHub configuration..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-FileExists ".github\workflows\ci.yml" "CI workflow")
$allGood = $allGood -and (Test-FileExists ".github\workflows\codeql.yml" "CodeQL workflow")
$allGood = $allGood -and (Test-FileExists ".github\ISSUE_TEMPLATE\bug_report.yml" "Bug report template")
$allGood = $allGood -and (Test-FileExists ".github\ISSUE_TEMPLATE\feature_request.yml" "Feature request template")
$allGood = $allGood -and (Test-FileExists ".github\PULL_REQUEST_TEMPLATE.md" "PR template")
Write-Host ""

Write-Host "Checking source directories..." -ForegroundColor Yellow
$allGood = $allGood -and (Test-DirectoryExists "src" "src/")
$allGood = $allGood -and (Test-FileExists "src\__init__.py" "src\__init__.py")
$allGood = $allGood -and (Test-FileExists "src\agent_core.py" "src\agent_core.py")
$allGood = $allGood -and (Test-FileExists "src\main.py" "src\main.py")
$allGood = $allGood -and (Test-DirectoryExists "tests" "tests/")
Write-Host ""

Write-Host "Checking Python environment..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.(9|10|11|12|13)") {
        Write-Host "✓ Python version: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ Python version not compatible: $pythonVersion" -ForegroundColor Red
        $allGood = $false
    }
} catch {
    Write-Host "✗ Python not found or not in PATH" -ForegroundColor Red
    $allGood = $false
}
Write-Host ""

Write-Host "Checking for cache files (should be clean)..." -ForegroundColor Yellow
$cacheFiles = Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue
if ($cacheFiles.Count -eq 0) {
    Write-Host "✓ No __pycache__ directories found (clean)" -ForegroundColor Green
} else {
    Write-Host "⚠ Found $($cacheFiles.Count) __pycache__ directories (run .\clean.ps1)" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "=== Verification Summary ===" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "✓ All checks passed! Project is properly set up." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Add your Gemini API key to config\credentials.json" -ForegroundColor White
    Write-Host "  2. Run .\setup.ps1 to create virtual environment" -ForegroundColor White
    Write-Host "  3. Read QUICKSTART.md for usage instructions" -ForegroundColor White
} else {
    Write-Host "✗ Some checks failed. Please review the issues above." -ForegroundColor Red
    Write-Host ""
    Write-Host "Try running:" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1  # to set up the project" -ForegroundColor White
}
Write-Host ""
