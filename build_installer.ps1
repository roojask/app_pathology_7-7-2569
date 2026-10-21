# Automated Build Script for PathoWhisper Windows Setup Installer
$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  PATHO-WHISPER: ONE-CLICK WINDOWS SETUP INSTALLER BUILDER" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Check Python virtual environment
$PyInstaller = ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    Write-Error "PyInstaller not found at $PyInstaller! Please ensure the virtual environment is set up."
}

# 2. Check Inno Setup Compiler
$ISCC = "C:\Users\project\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    $ISCC = "C:\Users\project\AppData\Local\Programs\Inno Setup 7\ISCC.exe"
}
if (-not (Test-Path $ISCC)) {
    Write-Error "Inno Setup Compiler (ISCC.exe) not found!"
}

# 3. Compile standalone application bundle with PyInstaller
Write-Host "`n[STEP 1/2] Compiling Python & CTranslate2 INT8 model with PyInstaller..." -ForegroundColor Yellow
& $PyInstaller gui_app.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE"
}
Write-Host "[SUCCESS] Standalone bundle created in dist\PathologyApp" -ForegroundColor Green

# 4. Compile Inno Setup Installer
Write-Host "`n[STEP 2/2] Compiling Windows Setup Installer with Inno Setup (LZMA2 Ultra Compression)..." -ForegroundColor Yellow
if (-not (Test-Path "dist_installer")) {
    New-Item -ItemType Directory -Path "dist_installer" | Out-Null
}

& $ISCC installer.iss

if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup compilation failed with exit code $LASTEXITCODE"
}

$InstallerPath = "dist_installer\PathoWhisper_Setup_v1.0.exe"
if (Test-Path $InstallerPath) {
    $SizeMB = [math]::Round((Get-Item $InstallerPath).Length / 1MB, 2)
    Write-Host "`n==================================================================" -ForegroundColor Green
    Write-Host "  BUILD COMPLETE!" -ForegroundColor Green
    Write-Host "  Installer Path: $InstallerPath" -ForegroundColor White
    Write-Host "  Installer Size: $SizeMB MB" -ForegroundColor White
    Write-Host "==================================================================" -ForegroundColor Green
} else {
    Write-Error "Installer executable not found in dist_installer!"
}
