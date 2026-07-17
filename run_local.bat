@echo off
title Pathology Voice Assistant - Standalone Local Launcher
echo ====================================================================
echo  Pathology Voice Assistant - Standalone Local Run (Setup & Start)
echo ====================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to System PATH.
    echo Please install Python 3.11 (or higher) from python.org and try again.
    echo Make sure to check the box "Add Python.exe to PATH" during installation.
    echo.
    pause
    exit /b
)

:: 2. Setup Virtual Environment if not exists
if not exist venv (
    echo [1/4] Creating Virtual Environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
)

echo [2/4] Activating Virtual Environment...
call venv\Scripts\activate

:: 3. Install requirements
echo [3/4] Installing/Checking requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install pip requirements.
    pause
    exit /b
)

:: 4. Download spaCy model if missing
python -c "import spacy; spacy.load('en_core_web_sm')" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Loading] Installing spaCy English language model...
    python -m spacy download en_core_web_sm
)

:: 5. Check FFmpeg dependency (Critical for Whisper)
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] FFmpeg was not found in your system PATH.
    echo OpenAI Whisper requires FFmpeg for audio processing.
    echo.
    if not exist ffmpeg.exe (
        echo [4/4] Downloading portable FFmpeg.exe for offline running...
        :: Use curl to download a portable static build of FFmpeg from a reliable build provider
        curl -L -o ffmpeg.zip https://github.com/GyanD/codexffmpeg/releases/download/6.0/ffmpeg-6.0-essentials_build.zip
        if %errorlevel% neq 0 (
            echo [WARNING] Failed to download FFmpeg automatically.
            echo Whisper may fail to transcribe unless you install FFmpeg manually.
        ) else (
            echo [Loading] Extracting portable FFmpeg...
            tar -xf ffmpeg.zip
            move ffmpeg-6.0-essentials_build\bin\ffmpeg.exe . >nul 2>&1
            move ffmpeg-6.0-essentials_build\bin\ffprobe.exe . >nul 2>&1
            :: Cleanup
            del ffmpeg.zip
            rmdir /s /q ffmpeg-6.0-essentials_build >nul 2>&1
            echo [Success] Portable FFmpeg downloaded and set up successfully.
        )
    ) else (
        echo [Success] Portable ffmpeg.exe is already present in project folder.
    )
) else (
    echo [Success] FFmpeg is already installed globally on this system.
)

echo.
echo ====================================================================
echo  Setup Completed. Starting Server...
echo ====================================================================
echo.
:: Automatically open web browser to the local SSL/HTTPS server port
start "" "https://localhost:7860"
python app.py
pause
