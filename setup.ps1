<#
.SYNOPSIS
        Write-Log -Message "Python not found. Please install Python 3.14 from https://www.python.org/ or ensure the 'python'/'py' launcher is enabled." -Level Error

        if ($script:PythonCandidateDiagnostics -and $script:PythonCandidateDiagnostics.Count -gt 0) {
            Write-Log -Message "Python launcher diagnostics:" -Level Warning
            foreach ($diag in $script:PythonCandidateDiagnostics) {
                Write-Log -Message "  Candidate: $($diag.Candidate) | ExitCode: $($diag.ExitCode) | Output: $($diag.Output)" -Level Warning
            }
        }
    
.DESCRIPTION
    Installs and configures all dependencies for AI Agent including:
    - Python 3.14+ (latest version)
    - Python packages with version verification
    - Tesseract OCR
    - System compatibility checks
    - Configuration validation
    - Windows environment profile export for the agent
    
.PARAMETER SkipTesseract
    Skip Tesseract OCR installation
    
.PARAMETER SkipSystemCheck
    Skip system requirements validation
    
.PARAMETER LogPath
    Custom path for installation log file
    
.PARAMETER Force
    Force reinstallation of all packages
    
.EXAMPLE
    .\setup.ps1
    
.EXAMPLE
    .\setup.ps1 -SkipTesseract -Force
    
.NOTES
    Version: 2.0
    Updated: October 2025
    Requires: PowerShell 5.1+
#>

#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$SkipTesseract,
    [switch]$SkipSystemCheck,
    [string]$LogPath = ".\setup_log.txt",
    [switch]$Force,
    [string]$SystemProfilePath = ".\system_profile.json"
)

# Script configuration
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$InformationPreference = 'Continue'

# Ensure log directory exists before writing
try {
    $resolvedLogPath = $LogPath
    try {
        $resolvedCandidate = Resolve-Path -Path $LogPath -ErrorAction Stop
        if ($null -ne $resolvedCandidate) {
            $resolvedLogPath = $resolvedCandidate.ProviderPath
        }
    }
    catch {
    $resolvedLogPath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine((Get-Location).Path, $LogPath))
    }

        $logDirectory = [System.IO.Path]::GetDirectoryName($resolvedLogPath)
        if ([string]::IsNullOrWhiteSpace($logDirectory)) {
            $logDirectory = (Get-Location).Path
    }
    if (-not (Test-Path -LiteralPath $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }
    $LogPath = $resolvedLogPath
    if (-not (Test-Path -LiteralPath $LogPath)) {
        New-Item -ItemType File -Path $LogPath -Force | Out-Null
    }
}
catch {
    Write-Warning "Unable to initialize log directory for $LogPath. Logging may be limited."
}

# Normalize profile path target
try {
    $resolvedProfilePath = $SystemProfilePath
    try {
        $profileCandidate = Resolve-Path -Path $SystemProfilePath -ErrorAction Stop
        if ($null -ne $profileCandidate) {
            $resolvedProfilePath = $profileCandidate.ProviderPath
        }
    }
    catch {
        $resolvedProfilePath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine((Get-Location).Path, $SystemProfilePath))
    }

    $profileDir = Split-Path -Parent $resolvedProfilePath
    if ([string]::IsNullOrWhiteSpace($profileDir)) {
        $profileDir = (Get-Location).Path
    }
    if (-not (Test-Path -LiteralPath $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    $SystemProfilePath = $resolvedProfilePath
}
catch {
    Write-Warning "Unable to normalize system profile path $SystemProfilePath. Using original value."
}

# Constants
$PYTHON_MIN_MAJOR = 3
$PYTHON_MIN_MINOR = 10
$PYTHON_RECOMMENDED_MAJOR = 3
$PYTHON_RECOMMENDED_MINOR = 14
$TESSERACT_DEFAULT_PATH = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$TESSERACT_DOWNLOAD_URL = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
$MIN_DISK_SPACE_GB = 5
$MIN_RAM_GB = 4
$TOTAL_STEPS = 9

# Python packages with latest compatible versions
$PYTHON_PACKAGES = [ordered]@{
    "google-generativeai" = ">=0.8.0"
    "pyautogui"           = ">=0.9.54"
    "pywinauto"           = ">=0.6.9"
    "pillow"              = ">=11.0.0"
    "opencv-python"       = ">=4.10.0"
    "pytesseract"         = ">=0.3.13"
    "psutil"              = ">=6.1.0"
    "pygetwindow"         = ">=0.0.9"
    "pyperclip"           = ">=1.9.0"
    "keyboard"            = ">=0.13.5"
}

# Global counters
$script:ErrorCount = 0
$script:WarningCount = 0
$script:SuccessCount = 0

# Python command resolution cache
$script:PythonCommand = $null
$script:PythonExecutablePath = $null
$script:ResolvedPythonVersion = $null
$script:PythonCandidateDiagnostics = @()

function Resolve-PythonCommand {
    # Locate an available Python launcher (python/py/python3).

    if ($script:PythonCommand) {
        return $script:PythonCommand
    }

    $candidates = @("py", "python", "python3")

    $script:PythonCandidateDiagnostics = @()

    foreach ($candidate in $candidates) {
        try {
            $commandInfo = Get-Command $candidate -ErrorAction Stop
            if (-not $commandInfo) {
                continue
            }

            $versionOutput = & $candidate --version 2>&1 | Out-String
            $versionOutput = $versionOutput.Trim()

            if ([string]::IsNullOrWhiteSpace($versionOutput)) {
                $script:PythonCandidateDiagnostics += [pscustomobject]@{
                    Candidate = $candidate
                    ExitCode  = $LASTEXITCODE
                    Output    = "(no output)"
                }
                continue
            }

            $match = [regex]::Match($versionOutput, 'Python\s+(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)')
            if (-not $match.Success) {
                $script:PythonCandidateDiagnostics += [pscustomobject]@{
                    Candidate = $candidate
                    ExitCode  = $LASTEXITCODE
                    Output    = $versionOutput
                }
                continue
            }

            $script:ResolvedPythonVersion = [pscustomobject]@{
                Major = [int]$match.Groups['major'].Value
                Minor = [int]$match.Groups['minor'].Value
                Patch = [int]$match.Groups['patch'].Value
                Raw   = $versionOutput
            }

            $script:PythonCommand = $candidate
            if ($commandInfo.Source) {
                $script:PythonExecutablePath = $commandInfo.Source
            }

            Write-Log -Message "Resolved Python launcher '$candidate' : $($script:ResolvedPythonVersion.Raw)" -Level Info
            return $script:PythonCommand
        }
        catch {
            $script:PythonCandidateDiagnostics += [pscustomobject]@{
                Candidate = $candidate
                ExitCode  = $LASTEXITCODE
                Output    = $_.Exception.Message
            }
            # Continue to next candidate
        }
    }

    return $null
}

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet('Info', 'Success', 'Warning', 'Error')]
        [string]$Level = 'Info'
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"

    try {
        Add-Content -Path $LogPath -Value $logMessage -ErrorAction SilentlyContinue
    }
    catch {
        # Logging failures are non-fatal
    }

    switch ($Level) {
        'Success' {
            Write-Host "[SUCCESS] $Message" -ForegroundColor Green
            $script:SuccessCount++
        }
        'Warning' {
            Write-Host "[WARNING] $Message" -ForegroundColor Yellow
            $script:WarningCount++
        }
        'Error' {
            Write-Host "[ERROR] $Message" -ForegroundColor Red
            $script:ErrorCount++
        }
        default {
            Write-Host "[INFO] $Message" -ForegroundColor Cyan
        }
    }
}

function Write-ColoredHeader {
    param([string]$Text)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Write-Step {
    param(
        [int]$StepNumber,
        [string]$Message
    )
    Write-Host "`n[$StepNumber/$TOTAL_STEPS] $Message" -ForegroundColor Green -BackgroundColor Black
    Write-Log -Message "Step $StepNumber : $Message" -Level Info
}

function Test-AdminPrivileges {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-InternetConnection {
    try {
        $testConnection = Test-NetConnection -ComputerName "8.8.8.8" -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction Stop
        return $testConnection
    }
    catch {
        try {
            $webRequest = [System.Net.WebRequest]::Create("https://www.google.com")
            $webRequest.Timeout = 5000
            $response = $webRequest.GetResponse()
            $response.Close()
            return $true
        }
        catch {
            return $false
        }
    }
}

function Get-SystemInfo {
    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        $cpu = Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | Select-Object -First 1
        $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction Stop
        
        return @{
            OSName            = $os.Caption
            OSVersion         = $os.Version
            OSArchitecture    = $os.OSArchitecture
            TotalRAM_GB       = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
            FreeRAM_GB        = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
            CPUName           = $cpu.Name
            CPUCores          = $cpu.NumberOfCores
            CPULogicalCores   = $cpu.NumberOfLogicalProcessors
            DiskFreeSpace_GB  = [math]::Round($disk.FreeSpace / 1GB, 2)
            DiskTotalSpace_GB = [math]::Round($disk.Size / 1GB, 2)
        }
    }
    catch {
        Write-Log -Message "Failed to retrieve system information: $_" -Level Warning
        return $null
    }
}

function Test-SystemRequirements {
    Write-Log -Message "Validating system requirements..." -Level Info
    
    $sysInfo = Get-SystemInfo
    if ($null -eq $sysInfo) {
        Write-Log -Message "Could not validate system requirements" -Level Warning
        return $false
    }
    
    $allChecksPassed = $true
    
    # Check OS Architecture
    Write-Host "   OS: $($sysInfo.OSName) ($($sysInfo.OSArchitecture))" -ForegroundColor Gray
    if ($sysInfo.OSArchitecture -notmatch "64") {
        Write-Log -Message "64-bit OS required. Current: $($sysInfo.OSArchitecture)" -Level Error
        $allChecksPassed = $false
    }
    
    # Check RAM
    Write-Host "   RAM: $($sysInfo.TotalRAM_GB) GB (Free: $($sysInfo.FreeRAM_GB) GB)" -ForegroundColor Gray
    if ($sysInfo.TotalRAM_GB -lt $MIN_RAM_GB) {
        Write-Log -Message "Insufficient RAM. Required: ${MIN_RAM_GB}GB, Available: $($sysInfo.TotalRAM_GB)GB" -Level Warning
        $allChecksPassed = $false
    }
    
    # Check Disk Space
    Write-Host "   Disk: $($sysInfo.DiskFreeSpace_GB) GB free of $($sysInfo.DiskTotalSpace_GB) GB" -ForegroundColor Gray
    if ($sysInfo.DiskFreeSpace_GB -lt $MIN_DISK_SPACE_GB) {
        Write-Log -Message "Insufficient disk space. Required: ${MIN_DISK_SPACE_GB}GB, Available: $($sysInfo.DiskFreeSpace_GB)GB" -Level Error
        $allChecksPassed = $false
    }
    
    # Check CPU
    Write-Host "   CPU: $($sysInfo.CPUName) ($($sysInfo.CPUCores) cores)" -ForegroundColor Gray
    
    return $allChecksPassed
}

function Test-PythonVersion {
    param(
        [string]$VersionString,
        [int]$MinMajor,
        [int]$MinMinor
    )
    
    if ($VersionString -match "Python (\d+)\.(\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        $patch = [int]$Matches[3]
        
        if ($major -gt $MinMajor) { return $true }
        if ($major -eq $MinMajor -and $minor -ge $MinMinor) { return $true }
        return $false
    }
    return $false
}

function Install-PythonPackage {
    param(
        [string]$PackageName,
        [string]$Version,
        [switch]$Upgrade
    )
    
    $packageSpec = if ($Version) { "$PackageName$Version" } else { $PackageName }
    $pythonCmd = Resolve-PythonCommand
    if (-not $pythonCmd) {
        Write-Log -Message "Python command not available; cannot install $packageSpec" -Level Error
        return $false
    }
    
    try {
        $args = @('install', $packageSpec, '--quiet', '--disable-pip-version-check')
        if ($Upgrade -or $Force) {
            $args += '--upgrade'
        }
        
        $result = & $pythonCmd -m pip $args 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "Successfully installed: $packageSpec" -Level Info
            return $true
        }
        else {
            Write-Log -Message "Failed to install $packageSpec : $result" -Level Error
            return $false
        }
    }
    catch {
        Write-Log -Message "Exception installing $packageSpec : $_" -Level Error
        return $false
    }
}

function Test-PythonPackageInstalled {
    param([string]$PackageName)
    
    $pythonCmd = Resolve-PythonCommand
    if (-not $pythonCmd) {
        return $false
    }

    try {
        $result = & $pythonCmd -m pip show $PackageName 2>&1
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Add-ToUserPath {
    param([string]$PathToAdd)
    
    try {
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($currentPath -notlike "*$PathToAdd*") {
            $newPath = $currentPath.TrimEnd(';') + ";$PathToAdd"
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            $env:Path += ";$PathToAdd"
            Write-Log -Message "Added to PATH: $PathToAdd" -Level Success
            return $true
        }
        return $false
    }
    catch {
        Write-Log -Message "Failed to add to PATH: $_" -Level Error
        return $false
    }
}

function Test-ConfigFile {
    param([string]$ConfigPath)
    
    if (-not (Test-Path $ConfigPath)) {
        Write-Log -Message "Configuration file not found: $ConfigPath" -Level Warning
        return $false
    }
    
    try {
        $configContent = Get-Content $ConfigPath -Raw -ErrorAction Stop
        
        # Simplified regex pattern to avoid escape issues
        $hasGeminiKey = $configContent -match 'GEMINI_API_KEY\s*=\s*[''"]'
        $hasPlaceholder = $configContent -match 'your_api_key_here'
        
        if ($hasGeminiKey -and -not $hasPlaceholder) {
            Write-Log -Message "Gemini API key is configured" -Level Success
            return $true
        }
        else {
            Write-Log -Message "Gemini API key not configured or still using placeholder" -Level Warning
            return $false
        }
    }
    catch {
        Write-Log -Message "Error reading config file: $_" -Level Error
        return $false
    }
}

function Test-AllImports {
    $testScript = @"
import sys
failed_imports = []
packages = [
    'google.generativeai',
    'pyautogui',
    'pywinauto',
    'PIL',
    'cv2',
    'pytesseract',
    'psutil',
    'pygetwindow',
    'pyperclip',
    'keyboard'
]

for pkg in packages:
    try:
        __import__(pkg)
    except Exception as e:
        failed_imports.append(pkg + ': ' + str(e))

if failed_imports:
    print('FAILED:')
    for fail in failed_imports:
        print('  - ' + fail)
    sys.exit(1)
else:
    print('SUCCESS')
    sys.exit(0)
"@

    $pythonCmd = Resolve-PythonCommand
    if (-not $pythonCmd) {
        return @{ Success = $false; Output = "Python command unavailable for import test." }
    }

    try {
        $result = & $pythonCmd -c $testScript 2>&1 | Out-String
        $result = $result.Trim()

        if ($LASTEXITCODE -eq 0) {
            return @{ Success = $true; Output = $result }
        }

        return @{ Success = $false; Output = $result }
    }
    catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

function Backup-ConfigFile {
    param([string]$ConfigPath)
    
    if (Test-Path $ConfigPath) {
        $backupPath = "$ConfigPath.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        try {
            Copy-Item -Path $ConfigPath -Destination $backupPath -ErrorAction Stop
            Write-Log -Message "Config backup created: $backupPath" -Level Info
            return $true
        }
        catch {
            Write-Log -Message "Failed to backup config: $_" -Level Warning
            return $false
        }
    }
    return $false
}

function Get-ScreenInformation {
    try {
        $videoControllers = Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop
        $screens = @()
        foreach ($controller in $videoControllers) {
            $width = $controller.CurrentHorizontalResolution
            $height = $controller.CurrentVerticalResolution
            if ($width -and $height) {
                $screens += [ordered]@{
                    AdapterName = $controller.Name
                    Width       = [int]$width
                    Height      = [int]$height
                    RefreshRate = $controller.MaxRefreshRate
                    BitsPerPixel = $controller.CurrentBitsPerPixel
                }
            }
        }

        if ($screens.Count -eq 0) {
            throw "No active screen resolutions reported"
        }

        return @{
            Screens           = $screens
            PrimaryResolution = $screens[0]
        }
    }
    catch {
        Write-Log -Message "Unable to gather display information: $_" -Level Warning
        return @{}
    }
}

function Get-SystemConfigurationProfile {
    param(
        [hashtable]$SystemInfo
    )

    if ($null -eq $SystemInfo) {
        $SystemInfo = @{}
    }

    $culture = Get-Culture
    $uiCulture = Get-UICulture
    $timezone = [System.TimeZoneInfo]::Local
    $screenInfo = Get-ScreenInformation
    try {
        $systemLocaleName = (Get-WinSystemLocale).Name
    }
    catch {
        $systemLocaleName = $null
    }

    $profile = [ordered]@{
        GeneratedAtUtc   = (Get-Date).ToUniversalTime().ToString("o")
        OperatingSystem  = [ordered]@{
            Name         = $SystemInfo.OSName
            Version      = $SystemInfo.OSVersion
            Architecture = $SystemInfo.OSArchitecture
            BuildNumber  = [System.Environment]::OSVersion.Version.Build
        }
        Hardware         = [ordered]@{
            CPU           = $SystemInfo.CPUName
            PhysicalCores = $SystemInfo.CPUCores
            LogicalCores  = $SystemInfo.CPULogicalCores
            TotalRamGb    = $SystemInfo.TotalRAM_GB
            FreeRamGb     = $SystemInfo.FreeRAM_GB
        }
        Locale           = [ordered]@{
            Culture           = $culture.Name
            UICulture         = $uiCulture.Name
            InstalledUICulture = [System.Globalization.CultureInfo]::InstalledUICulture.Name
            SystemLocale      = $systemLocaleName
            TimeZone          = $timezone.DisplayName
            TimeZoneId        = $timezone.Id
            TimeZoneOffset    = $timezone.BaseUtcOffset.TotalHours
        }
        Environment      = [ordered]@{
            PowerShellVersion  = $PSVersionTable.PSVersion.ToString()
            PSEdition          = $PSVersionTable.PSEdition
            ShellPath          = $PSHOME
            ComSpec            = $env:ComSpec
            ProcessorIdentifier = $env:PROCESSOR_IDENTIFIER
            UserProfile        = $env:USERPROFILE
            PreferredEncoding  = [Console]::OutputEncoding.WebName
            ShellCandidates    = @($env:SHELL, $env:ComSpec, $env:COMSPEC) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        }
    }

    if ($screenInfo.Count -gt 0) {
        $profile.Display = $screenInfo
    }

    try {
        $languageList = Get-WinUserLanguageList -ErrorAction Stop
        $profile.Locale.LanguageList = $languageList | ForEach-Object {
            if ($_ -and $_.PSObject.Properties['LanguageTag']) {
                $_.LanguageTag
            }
            elseif ($_ -and $_.PSObject.Properties['InputMethodTips']) {
                $_.InputMethodTips
            }
        } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    catch {
        $profile.Locale.LanguageList = @()
    }

    try {
    $profile.Environment.ActiveProcesses = (Get-Process | Sort-Object -Property CPU -Descending | Select-Object -First 10 -ExpandProperty ProcessName)
    }
    catch {
        $profile.Environment.ActiveProcesses = @()
    }

    return $profile
}

function Write-SystemProfile {
    param(
        [string]$Path,
        [hashtable]$Profile
    )

    if ($null -eq $Profile -or $Profile.Count -eq 0) {
        Write-Log -Message "System profile data is empty; skipping export." -Level Warning
        return $false
    }

    try {
        $directory = Split-Path -Parent $Path
        if ([string]::IsNullOrWhiteSpace($directory)) {
            $directory = (Get-Location).Path
        }
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }

        $json = $Profile | ConvertTo-Json -Depth 6
        Set-Content -Path $Path -Value $json -Encoding UTF8
        Write-Log -Message "Exported system profile to ${Path}" -Level Success
        return $true
    }
    catch {
        Write-Log -Message "Failed to write system profile: $_" -Level Error
        return $false
    }
}

#endregion

#region Main Script

try {
    # Initialize log
    Write-ColoredHeader "AI Agent Setup - Windows Installer v2.0"
    Write-Log -Message "=== Setup Started ===" -Level Info
    Write-Log -Message "PowerShell Version: $($PSVersionTable.PSVersion)" -Level Info
    Write-Log -Message "Log file: $LogPath" -Level Info
    
    # Check Administrator privileges
    $isAdmin = Test-AdminPrivileges
    if ($isAdmin) {
        Write-Log -Message "Running with Administrator privileges" -Level Success
    }
    else {
        Write-Log -Message "Running without Administrator privileges - some features may be limited" -Level Warning
        Write-Host "   Consider running as Administrator for full functionality`n" -ForegroundColor Yellow
    }
    
    # Step 1: System Requirements Check
    if (-not $SkipSystemCheck) {
        Write-Step -StepNumber 1 -Message "Checking system requirements..."
        
        if (Test-SystemRequirements) {
            Write-Log -Message "System requirements check passed" -Level Success
        }
        else {
            Write-Log -Message "System requirements check failed - continuing anyway" -Level Warning
        }
    }
    else {
        Write-Host "   Skipping system requirements check" -ForegroundColor Gray
    }
    
    # Check Internet Connection
    Write-Host "`n   Checking internet connection..." -ForegroundColor Yellow
    if (Test-InternetConnection) {
        Write-Log -Message "Internet connection available" -Level Success
    }
    else {
        Write-Log -Message "No internet connection detected - downloads may fail" -Level Warning
    }
    
    # Step 2: Check Python Installation
    Write-Step -StepNumber 2 -Message "Checking Python installation..."
    
    try {
        $pythonCmd = Resolve-PythonCommand
        if (-not $pythonCmd) {
            throw "No Python launcher (python/py) found on PATH"
        }

        $pythonVersion = & $pythonCmd --version 2>&1 | Out-String
        $pythonVersion = $pythonVersion.Trim()
        Write-Log -Message "Python found via '$pythonCmd': $pythonVersion" -Level Success

        if (Test-PythonVersion -VersionString $pythonVersion -MinMajor $PYTHON_MIN_MAJOR -MinMinor $PYTHON_MIN_MINOR) {
            if ($pythonVersion -match "3\.14") {
                Write-Log -Message "Running latest Python $PYTHON_RECOMMENDED_MAJOR.$PYTHON_RECOMMENDED_MINOR" -Level Success
            }
            elseif ($pythonVersion -match "3\.13") {
                Write-Log -Message "Python 3.13 detected - consider upgrading to 3.14" -Level Info
            }
            else {
                Write-Log -Message "Python $PYTHON_RECOMMENDED_MAJOR.$PYTHON_RECOMMENDED_MINOR is recommended. Visit: https://www.python.org/" -Level Warning
            }
        }
        else {
            Write-Log -Message "Python $PYTHON_MIN_MAJOR.$PYTHON_MIN_MINOR+ is required. Current: $pythonVersion" -Level Error
            Write-Host "`nDownload Python 3.14 from: https://www.python.org/downloads/`n" -ForegroundColor Cyan
            throw "Incompatible Python version"
        }

        # Check Python path
        if (-not $script:PythonExecutablePath) {
            $commandInfo = Get-Command $pythonCmd -ErrorAction SilentlyContinue
            if ($commandInfo -and $commandInfo.Source) {
                $script:PythonExecutablePath = $commandInfo.Source
            }
        }

        if ($script:PythonExecutablePath) {
            Write-Host "   Python location: $script:PythonExecutablePath" -ForegroundColor Gray
        }
        else {
            Write-Host "   Using launcher: $pythonCmd (exact path unavailable)" -ForegroundColor Gray
        }
    }
    catch {
        Write-Log -Message "Python not found. Please install Python 3.14 from https://www.python.org/ or ensure the 'python'/'py' launcher is enabled." -Level Error
        if ($_) {
            Write-Log -Message "Python detection error: $($_.Exception.Message)" -Level Error
        }

        if ($script:PythonCandidateDiagnostics -and $script:PythonCandidateDiagnostics.Count -gt 0) {
            Write-Log -Message "Python launcher diagnostics:" -Level Warning
            foreach ($diag in $script:PythonCandidateDiagnostics) {
                Write-Log -Message "  Candidate: $($diag.Candidate) | ExitCode: $($diag.ExitCode) | Output: $($diag.Output)" -Level Warning
            }
        }

        Write-Host "   Hint: On Windows, you can run 'py --version' to verify the Python launcher is available." -ForegroundColor Yellow
        exit 1
    }
    
    # Step 3: Check and Upgrade pip
    Write-Step -StepNumber 3 -Message "Checking pip installation..."
    
    try {
        $pythonCmd = Resolve-PythonCommand
        if (-not $pythonCmd) {
            throw "Python command unavailable for pip checks"
        }

        $pipVersion = & $pythonCmd -m pip --version 2>&1 | Out-String
        $pipVersion = $pipVersion.Trim()
        Write-Log -Message "pip found: $pipVersion" -Level Success
        
        Write-Host "   Upgrading pip, setuptools, and wheel..." -ForegroundColor Yellow
        $upgradeResult = & $pythonCmd -m pip install --upgrade pip setuptools wheel --quiet --disable-pip-version-check 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "pip tools updated successfully" -Level Success
        }
        else {
            Write-Log -Message "pip upgrade encountered issues: $upgradeResult" -Level Warning
        }
    }
    catch {
        Write-Log -Message "pip issues detected. Installing pip..." -Level Warning
        $pythonCmd = Resolve-PythonCommand
        if (-not $pythonCmd) {
            throw
        }
        & $pythonCmd -m ensurepip --default-pip
        & $pythonCmd -m pip install --upgrade pip
    }
    
    # Step 4: Install Python Dependencies
    Write-Step -StepNumber 4 -Message "Installing Python dependencies..."
    Write-Host "   This may take a few minutes...`n" -ForegroundColor Yellow
    
    $pythonDisplayCommand = Resolve-PythonCommand
    if (-not $pythonDisplayCommand) {
        $pythonDisplayCommand = "python"
    }

    $installedCount = 0
    $failedPackages = @()
    $skippedPackages = @()
    
    foreach ($package in $PYTHON_PACKAGES.GetEnumerator()) {
        $packageName = $package.Key
        $packageVersion = $package.Value
        $displayName = "$packageName $packageVersion"
        
        # Check if already installed
        if (-not $Force -and (Test-PythonPackageInstalled -PackageName $packageName)) {
            Write-Host "   $displayName..." -NoNewline -ForegroundColor Gray
            Write-Host " [ALREADY INSTALLED]" -ForegroundColor Cyan
            $skippedPackages += $packageName
            $installedCount++
            continue
        }
        
        Write-Host "   Installing $displayName..." -NoNewline
        
        if (Install-PythonPackage -PackageName $packageName -Version $packageVersion -Upgrade:$Force) {
            Write-Host " [OK]" -ForegroundColor Green
            $installedCount++
        }
        else {
            Write-Host " [FAIL]" -ForegroundColor Red
            $failedPackages += $packageName
        }
    }
    
    Write-Host "`n   Summary: $installedCount/$($PYTHON_PACKAGES.Count) packages ready" -ForegroundColor Cyan
    if ($skippedPackages.Count -gt 0) {
        Write-Host "   Skipped (already installed): $($skippedPackages.Count)" -ForegroundColor Gray
    }
    
    if ($failedPackages.Count -gt 0) {
        Write-Log -Message "Failed packages: $($failedPackages -join ', ')" -Level Error
        Write-Host "`n   Failed to install some packages:" -ForegroundColor Yellow
        $failedPackages | ForEach-Object { Write-Host "      - $_" -ForegroundColor Yellow }
    Write-Host "   Try manually: $pythonDisplayCommand -m pip install <package> --upgrade`n" -ForegroundColor Cyan
    }
    
    # Step 5: Install Tesseract OCR
    Write-Step -StepNumber 5 -Message "Checking Tesseract OCR..."
    
    if (-not $SkipTesseract) {
        $tesseractExists = Test-Path $TESSERACT_DEFAULT_PATH
        
        if ($tesseractExists) {
            Write-Log -Message "Tesseract OCR found at: $TESSERACT_DEFAULT_PATH" -Level Success
            
            try {
                $tesseractVersion = & tesseract --version 2>&1 | Select-Object -First 1
                Write-Host "   Version: $tesseractVersion" -ForegroundColor Gray
                Write-Log -Message "Tesseract version: $tesseractVersion" -Level Info
            }
            catch {
                Write-Log -Message "Tesseract found but not in PATH. Adding to PATH..." -Level Warning
                if (Add-ToUserPath -PathToAdd "C:\Program Files\Tesseract-OCR") {
                    Write-Log -Message "Restart terminal to apply PATH changes" -Level Info
                }
            }
        }
        else {
            Write-Log -Message "Tesseract OCR not found" -Level Warning
            Write-Host "`n   Tesseract is required for OCR text recognition features." -ForegroundColor Cyan
            Write-Host "   Download size: ~70 MB" -ForegroundColor Gray
            
            $response = Read-Host "   Download and install Tesseract now? (Y/N)"
            
            if ($response -eq "Y" -or $response -eq "y") {
                $installerPath = Join-Path $env:TEMP "tesseract-installer.exe"
                
                try {
                    Write-Host "`n   Downloading Tesseract OCR 5.5..." -ForegroundColor Yellow
                    Write-Log -Message "Downloading Tesseract from: $TESSERACT_DOWNLOAD_URL" -Level Info
                    
                    $webClient = New-Object System.Net.WebClient
                    $webClient.DownloadFile($TESSERACT_DOWNLOAD_URL, $installerPath)
                    
                    if (Test-Path $installerPath) {
                        $fileSize = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
                        Write-Log -Message "Download complete ($fileSize MB)" -Level Success
                        
                        Write-Host "`n   Launching Tesseract installer..." -ForegroundColor Yellow
                        Write-Log -Message "IMPORTANT during installation:" -Level Warning
                        Write-Host "      1. Select 'Add to PATH' option" -ForegroundColor Cyan
                        Write-Host "      2. Install all language data packs" -ForegroundColor Cyan
                        Write-Host "      3. Keep default installation path`n" -ForegroundColor Cyan
                        
                        Start-Process -FilePath $installerPath -Wait
                        
                        Write-Log -Message "Tesseract installation completed" -Level Success
                        Write-Host "   Restart your terminal for PATH changes to take effect.`n" -ForegroundColor Cyan
                        
                        Remove-Item $installerPath -ErrorAction SilentlyContinue
                    }
                    else {
                        throw "Downloaded file not found"
                    }
                }
                catch {
                    Write-Log -Message "Failed to download/install Tesseract: $_" -Level Error
                    Write-Host "   Manual download: https://github.com/UB-Mannheim/tesseract/wiki`n" -ForegroundColor Yellow
                }
            }
            else {
                Write-Log -Message "Skipping Tesseract installation" -Level Warning
                Write-Host "   OCR features will not work without Tesseract.`n" -ForegroundColor Yellow
            }
        }
    }
    else {
        Write-Host "   Skipping Tesseract check (--SkipTesseract flag)" -ForegroundColor Gray
    }
    
    # Step 6: Setup Configuration
    Write-Step -StepNumber 6 -Message "Setting up configuration..."
    
    $envExamplePath = ".env.example"
    $envPath = ".env"
    
    # Create .env from .env.example if it doesn't exist
    if (-not (Test-Path $envPath)) {
        if (Test-Path $envExamplePath) {
            Write-Host "   Creating .env file from .env.example..." -ForegroundColor Yellow
            Copy-Item -Path $envExamplePath -Destination $envPath -Force
            Write-Host "   ✓ .env file created successfully" -ForegroundColor Green
            Write-Log -Message ".env file created from .env.example" -Level Success
        }
        else {
            Write-Log -Message ".env.example not found - cannot create .env" -Level Warning
            Write-Host "   ⚠️  .env.example not found. Please create .env manually." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "   .env file already exists" -ForegroundColor Gray
    }
    
    # Check if API key is configured
    if (Test-Path $envPath) {
        $envContent = Get-Content $envPath -Raw
        $hasValidKey = $envContent -match 'GEMINI_API_KEY\s*=\s*(?!your_api_key_here)\S+'
        
        if ($hasValidKey) {
            Write-Host "   ✓ Gemini API key is configured" -ForegroundColor Green
            Write-Log -Message "Gemini API key found in .env" -Level Success
        }
        else {
            Write-Host "`n   [ACTION REQUIRED] Configure your Gemini API key:" -ForegroundColor Cyan
            Write-Host "   1. Get your API key from: https://aistudio.google.com/app/apikey" -ForegroundColor White
            Write-Host "   2. Open .env file in a text editor" -ForegroundColor White
            Write-Host "   3. Replace 'your_api_key_here' with your actual API key" -ForegroundColor White
            Write-Host "   4. Save the file`n" -ForegroundColor White
            Write-Log -Message "API key not configured in .env - user action required" -Level Warning
        }
    }
    
    # Step 7: Verify Installation
    Write-Step -StepNumber 7 -Message "Verifying installation..."
    
    Write-Host "   Testing Python package imports..." -ForegroundColor Yellow
    
    $importTest = Test-AllImports
    
    if ($importTest.Success) {
    Write-Log -Message "All packages imported successfully" -Level Success
    }
    else {
        Write-Log -Message "Import test failed" -Level Error
        Write-Host "   $($importTest.Output)" -ForegroundColor Red
        Write-Host "`n   Some packages may not be properly installed." -ForegroundColor Yellow
    Write-Host "   Try: $pythonDisplayCommand -m pip install --upgrade --force-reinstall <package>`n" -ForegroundColor Cyan
    }
    
    # Step 8: Export Windows configuration profile
    Write-Step -StepNumber 8 -Message "Exporting Windows configuration profile..."

    try {
        $profileSource = Get-SystemInfo
        $systemProfile = Get-SystemConfigurationProfile -SystemInfo $profileSource
        if (Write-SystemProfile -Path $SystemProfilePath -Profile $systemProfile) {
            Write-Host "   System profile available at: $SystemProfilePath" -ForegroundColor Cyan
        }
    }
    catch {
        Write-Log -Message "System profile export failed: $_" -Level Error
    }

    # Step 9: Final Summary
    Write-Step -StepNumber 9 -Message "Installation Summary"
    
    Write-ColoredHeader "Setup Complete!"
    
    Write-Host "Installation Statistics:" -ForegroundColor Cyan
    Write-Host "   [SUCCESS] Successes: $script:SuccessCount" -ForegroundColor Green
    Write-Host "   [WARNING] Warnings: $script:WarningCount" -ForegroundColor Yellow
    Write-Host "   [ERROR] Errors: $script:ErrorCount" -ForegroundColor Red
    Write-Host ""
    
    if ($script:ErrorCount -eq 0) {
           Write-Host "Installation completed successfully!`n" -ForegroundColor Green
    }
    elseif ($script:ErrorCount -le 2) {
           Write-Host "Installation completed with minor issues`n" -ForegroundColor Yellow
    }
    else {
           Write-Host "Installation completed with errors - manual intervention required`n" -ForegroundColor Red
    }
    
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "  1. Configure Gemini API key in config.py" -ForegroundColor White
    Write-Host "  2. Restart your terminal/IDE" -ForegroundColor White
    Write-Host "  3. Run: python main.py 'your task'" -ForegroundColor White
    Write-Host "  4. Emergency stop: Ctrl+Shift+Q`n" -ForegroundColor White
    
    Write-Host "Usage Examples:" -ForegroundColor Cyan
    Write-Host "  python main.py 'open calculator'" -ForegroundColor Gray
    Write-Host "  python main.py 'open edge and navigate to youtube'" -ForegroundColor Gray
    Write-Host "  python main.py 'create a text file with system info'" -ForegroundColor Gray
    Write-Host "  python main.py 'take a screenshot and save it'`n" -ForegroundColor Gray
    
    Write-Host "Documentation:" -ForegroundColor Cyan
    Write-Host "  - Help: python main.py --help" -ForegroundColor Gray
    Write-Host "  - Log file: $LogPath" -ForegroundColor Gray
    Write-Host "  - Config: $configPath" -ForegroundColor Gray
    Write-Host "  - System profile: $SystemProfilePath`n" -ForegroundColor Gray
    
    if (-not $isAdmin) {
        Write-Host "[TIP] Run as Administrator for full installation capabilities`n" -ForegroundColor Yellow
    }
    
    Write-Log -Message "=== Setup Completed Successfully ===" -Level Info
    Write-Log -Message "Errors: $script:ErrorCount | Warnings: $script:WarningCount | Successes: $script:SuccessCount" -Level Info
}
catch {
    Write-Log -Message "FATAL ERROR: $_" -Level Error
    Write-Host "`n[ERROR] Setup failed with error: $_" -ForegroundColor Red
    Write-Host "Check log file for details: $LogPath`n" -ForegroundColor Yellow
    exit 1
}
finally {
    $ProgressPreference = 'Continue'
}

#endregion
