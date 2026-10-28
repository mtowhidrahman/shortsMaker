# Short Video Maker

Turns a YouTube video into 3 vertical short clips (9:16) with face tracking and captions.
Runs only on your computer and costs nothing.

> Use it only on your own videos, or videos you have permission to use.

Remember always, I dont Want C drive of my PC to be taken so much space

## Start the app

**Double-click `start.bat`** in this folder. Your browser opens http://localhost:8501.
(Or in PowerShell in this folder: `.\.venv\Scripts\python.exe -m streamlit run app.py`)

1. Paste a YouTube link and click **Make 3 shorts**. It takes about 2–5 minutes.
2. Watch and download the 3 clips on the page. They are also saved in the `output` folder.
3. If the AI can't pick clips (no key, or the free limit is reached), the page lets you save
   the transcript and type the clip times yourself, like `1:05 - 1:50` (one clip per line).

To stop the app, close the black `start.bat` window.

Temporary files and downloaded videos go to `E:\Personal Work\Programming\Shorts Temp`.
You can empty that folder from the page ("Free up space") or delete its contents yourself.

For best speed, close apps you don't need (other browsers, the ChatGPT app) while it runs.
The PC's memory is nearly full, and Windows then uses extra space on C:.

## One-time setup (run again if you move this folder)

```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Everything is kept inside this folder to save space on C: (only Python 3.12 itself is on C:).

- Python environment in `.venv` (rebuilt by `setup.ps1`)
- ffmpeg: `ffmpeg.exe` and `ffprobe.exe` in `tools\ffmpeg` (from the gyan.dev build)
- Whisper speech model in `models\whisper`, face model in `models\`
- Tool caches and temporary files in `E:\Personal Work\Programming\Shorts Temp`
- Gemini API key saved as the environment variable `GEMINI_API_KEY`

## If YouTube downloads stop working

Update the downloader:

```
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -U yt-dlp
```
