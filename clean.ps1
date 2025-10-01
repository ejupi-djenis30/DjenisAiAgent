# PowerShell script to clean the DjenisAiAgent project
# Run with: .\clean.ps1

Write-Host "Cleaning DjenisAiAgent project..." -ForegroundColor Cyan

# Function to safely remove directories
function Remove-DirectoryIfExists {
    param([string]$Path)
    if (Test-Path $Path) {
        Write-Host "  Removing: $Path" -ForegroundColor Yellow
        Remove-Item -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Function to safely remove files
function Remove-FileIfExists {
    param([string]$Pattern)
    $files = Get-ChildItem -Path . -Filter $Pattern -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        Write-Host "  Removing: $($file.FullName)" -ForegroundColor Yellow
        Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
    }
}

# Clean Python cache files
Write-Host "`nCleaning Python cache files..." -ForegroundColor Green
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory | ForEach-Object {
    Remove-DirectoryIfExists $_.FullName
}

Remove-FileIfExists "*.pyc"
Remove-FileIfExists "*.pyo"
Remove-FileIfExists "*.pyd"

# Clean build artifacts
Write-Host "`nCleaning build artifacts..." -ForegroundColor Green
Remove-DirectoryIfExists "build"
Remove-DirectoryIfExists "dist"
Remove-DirectoryIfExists "*.egg-info"
Get-ChildItem -Path . -Filter "*.egg-info" -Recurse -Directory | ForEach-Object {
    Remove-DirectoryIfExists $_.FullName
}

# Clean test artifacts
Write-Host "`nCleaning test artifacts..." -ForegroundColor Green
Remove-DirectoryIfExists ".pytest_cache"
Remove-DirectoryIfExists ".tox"
Remove-DirectoryIfExists "htmlcov"
Remove-DirectoryIfExists ".coverage"
Remove-FileIfExists ".coverage.*"

# Clean analysis cache
Write-Host "`nCleaning analysis cache..." -ForegroundColor Green
Remove-DirectoryIfExists "analysis_cache"

# Clean empty directories
Write-Host "`nCleaning empty directories..." -ForegroundColor Green
if (Test-Path "analysis_cache") {
    if ((Get-ChildItem "analysis_cache" -Force | Measure-Object).Count -eq 0) {
        Remove-DirectoryIfExists "analysis_cache"
    }
}

# Clean log files (optional - uncomment if you want to remove logs)
# Write-Host "`nCleaning log files..." -ForegroundColor Green
# Remove-FileIfExists "*.log"

# Clean IDE files
Write-Host "`nCleaning IDE files..." -ForegroundColor Green
Remove-DirectoryIfExists ".mypy_cache"
Remove-DirectoryIfExists ".pytype"

Write-Host "`n✓ Cleanup complete!" -ForegroundColor Green
Write-Host "  The project has been cleaned." -ForegroundColor Cyan
