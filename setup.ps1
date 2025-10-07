# AI Agent Setup Script for Windows
# This script installs all required dependencies including Tesseract OCR

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent Setup - Windows Installer  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "⚠️  Warning: Running without Administrator privileges." -ForegroundColor Yellow
    Write-Host "   Some features (like Tesseract installation) may require admin rights." -ForegroundColor Yellow
    Write-Host ""
}

# Step 1: Check Python installation
Write-Host "Step 1: Checking Python installation..." -ForegroundColor Green
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
    
    # Check version
    $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
    if ($versionMatch) {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
            Write-Host "❌ Python 3.8+ is required. Please update Python." -ForegroundColor Red
            exit 1
        }
    }
} catch {
    Write-Host "❌ Python not found. Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Check pip
Write-Host "Step 2: Checking pip installation..." -ForegroundColor Green
try {
    $pipVersion = pip --version 2>&1
    Write-Host "✅ pip found: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ pip not found. Installing pip..." -ForegroundColor Yellow
    python -m ensurepip --default-pip
    python -m pip install --upgrade pip
}

Write-Host ""

# Step 3: Install Python dependencies
Write-Host "Step 3: Installing Python dependencies..." -ForegroundColor Green
Write-Host "   This may take a few minutes..." -ForegroundColor Yellow

$requirements = @(
    "google-generativeai>=0.3.0",
    "pyautogui>=0.9.54",
    "pywinauto>=0.6.9",
    "pillow>=10.0.0",
    "opencv-python>=4.8.0",
    "pytesseract>=0.3.10",
    "psutil>=5.9.0",
    "pygetwindow>=0.0.9",
    "pyperclip>=1.8.2",
    "keyboard>=0.13.5"
)

$failedPackages = @()

foreach ($package in $requirements) {
    Write-Host "   Installing $package..." -NoNewline
    try {
        pip install $package --quiet --disable-pip-version-check 2>&1 | Out-Null
        Write-Host " ✅" -ForegroundColor Green
    } catch {
        Write-Host " ❌" -ForegroundColor Red
        $failedPackages += $package
    }
}

if ($failedPackages.Count -gt 0) {
    Write-Host ""
    Write-Host "⚠️  Failed to install some packages:" -ForegroundColor Yellow
    foreach ($pkg in $failedPackages) {
        Write-Host "   - $pkg" -ForegroundColor Yellow
    }
    Write-Host "   Try installing them manually with: pip install <package>" -ForegroundColor Yellow
}

Write-Host ""

# Step 4: Install Tesseract OCR
Write-Host "Step 4: Checking Tesseract OCR..." -ForegroundColor Green

$tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$tesseractExists = Test-Path $tesseractPath

if ($tesseractExists) {
    Write-Host "✅ Tesseract OCR already installed at: $tesseractPath" -ForegroundColor Green
    
    # Verify it's in PATH
    try {
        tesseract --version 2>&1 | Out-Null
        Write-Host "✅ Tesseract is in PATH" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Tesseract found but not in PATH. Adding to PATH..." -ForegroundColor Yellow
        
        # Add to user PATH
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($currentPath -notlike "*Tesseract-OCR*") {
            $newPath = $currentPath + ";C:\Program Files\Tesseract-OCR"
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            Write-Host "✅ Added Tesseract to PATH. You may need to restart your terminal." -ForegroundColor Green
        }
    }
} else {
    Write-Host "⚠️  Tesseract OCR not found." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Tesseract is required for OCR text recognition features." -ForegroundColor Cyan
    Write-Host "   Would you like to download and install it now? (Y/N)" -ForegroundColor Cyan
    
    $response = Read-Host "   "
    
    if ($response -eq "Y" -or $response -eq "y") {
        Write-Host ""
        Write-Host "   Downloading Tesseract OCR installer..." -ForegroundColor Yellow
        
        # Download latest Tesseract installer
        $tesseractUrl = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
        $installerPath = "$env:TEMP\tesseract-installer.exe"
        
        try {
            # Use System.Net.WebClient for better progress
            $webClient = New-Object System.Net.WebClient
            $webClient.DownloadFile($tesseractUrl, $installerPath)
            Write-Host "   ✅ Download complete" -ForegroundColor Green
            
            Write-Host ""
            Write-Host "   Launching Tesseract installer..." -ForegroundColor Yellow
            Write-Host "   ⚠️  IMPORTANT: During installation, make sure to:" -ForegroundColor Yellow
            Write-Host "      1. Select 'Add to PATH' option" -ForegroundColor Yellow
            Write-Host "      2. Install all language data packs" -ForegroundColor Yellow
            Write-Host ""
            
            # Run installer
            Start-Process -FilePath $installerPath -Wait
            
            Write-Host "   ✅ Tesseract installation complete" -ForegroundColor Green
            Write-Host "   You may need to restart your terminal for PATH changes to take effect." -ForegroundColor Cyan
            
            # Clean up
            Remove-Item $installerPath -ErrorAction SilentlyContinue
            
        } catch {
            Write-Host "   ❌ Failed to download/install Tesseract" -ForegroundColor Red
            Write-Host "   Please download manually from: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
        }
    } else {
        Write-Host ""
        Write-Host "   ⚠️  Skipping Tesseract installation." -ForegroundColor Yellow
        Write-Host "   OCR features will not work without Tesseract." -ForegroundColor Yellow
        Write-Host "   You can install it later from: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Cyan
    }
}

Write-Host ""

# Step 5: Check configuration
Write-Host "Step 5: Checking configuration..." -ForegroundColor Green

$configPath = "config.py"
if (Test-Path $configPath) {
    $configContent = Get-Content $configPath -Raw
    
    if ($configContent -match 'GEMINI_API_KEY\s*=\s*"[^"]+"' -and $configContent -notmatch 'your_api_key_here') {
        Write-Host "✅ Gemini API key is configured" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Gemini API key not configured" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   To configure your API key:" -ForegroundColor Cyan
        Write-Host "   1. Get an API key from: https://makersuite.google.com/app/apikey" -ForegroundColor Cyan
        Write-Host "   2. Edit config.py and set GEMINI_API_KEY = 'your_key_here'" -ForegroundColor Cyan
    }
} else {
    Write-Host "⚠️  config.py not found" -ForegroundColor Yellow
}

Write-Host ""

# Step 6: Verify installation
Write-Host "Step 6: Verifying installation..." -ForegroundColor Green

Write-Host "   Testing imports..." -ForegroundColor Yellow

$testScript = @"
import sys
try:
    import google.generativeai as genai
    import pyautogui
    import pywinauto
    import PIL
    import cv2
    import pytesseract
    import psutil
    import pygetwindow
    import pyperclip
    import keyboard
    print('SUCCESS')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)
"@

$result = python -c $testScript 2>&1

if ($result -match "SUCCESS") {
    Write-Host "   ✅ All packages imported successfully" -ForegroundColor Green
} else {
    Write-Host "   ❌ Import test failed:" -ForegroundColor Red
    Write-Host "   $result" -ForegroundColor Red
}

Write-Host ""

# Final summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          Setup Complete!              " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Configure your Gemini API key in config.py" -ForegroundColor White
Write-Host "  2. Run the agent with: python main.py 'your task'" -ForegroundColor White
Write-Host "  3. Press Ctrl+Shift+Q to emergency stop" -ForegroundColor White
Write-Host ""
Write-Host "Examples:" -ForegroundColor Green
Write-Host "  python main.py 'open calculator'" -ForegroundColor Cyan
Write-Host "  python main.py 'open edge and go to youtube'" -ForegroundColor Cyan
Write-Host "  python main.py 'open notepad and type hello world'" -ForegroundColor Cyan
Write-Host ""
Write-Host "For help: python main.py --help" -ForegroundColor Yellow
Write-Host ""
