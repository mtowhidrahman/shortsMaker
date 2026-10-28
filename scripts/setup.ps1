# One-time setup (run again after moving the project folder).
# Everything is installed INSIDE this folder; nothing big is written to C:.
# Usage (PowerShell, in the project folder):  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)   # the project folder (this script is in scripts\)

# Keep pip's temporary files on E: too (same folder as TEMP_DIR in config.py).
$tmp = "E:\Personal Work\Programming\Shorts Temp"
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TMP = $env:TEMP = $tmp

# 1. Fresh Python 3.12 environment in .venv (an old one breaks when the folder moves).
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -q -U pip
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -q -r requirements.txt

# 2. Face detection model (OpenCV YuNet, small file, kept in models/).
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path models\face_detection_yunet_2023mar.onnx)) {
    Invoke-WebRequest "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile models\face_detection_yunet_2023mar.onnx
}

# 3. ffmpeg must be in tools\ffmpeg (ffmpeg.exe + ffprobe.exe). It moves with the folder.
if (-not (Test-Path tools\ffmpeg\ffmpeg.exe)) {
    Write-Host "MISSING: tools\ffmpeg\ffmpeg.exe and ffprobe.exe (download the 'full build' zip from gyan.dev and copy them there)."
}

# 4. Quick check (Whisper model downloads into models\whisper on first use).
.\.venv\Scripts\python.exe -c "from shorts import config, downloader; import cv2, yt_dlp, faster_whisper, streamlit; from google import genai; downloader.load_whisper(); print('Setup OK')"
