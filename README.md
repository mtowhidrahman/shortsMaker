# Short Video Maker

Turns a YouTube video into 3 vertical short clips (9:16) with face tracking and captions.
Runs only on your computer and costs nothing.

> Use it only on your own videos, or videos you have permission to use.

Remember always, I dont Want C drive of my PC to be taken so much space

## Start the app

Open PowerShell in this folder and run:

```
.\.venv\Scripts\streamlit.exe run app.py
```

Your browser opens the app. Paste a YouTube link and click the button.
Finished clips are saved in the `output` folder.

## One-time setup (run again if you move this folder)

```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Everything is kept inside this folder to save space on C: (only Python 3.12 itself is on C:).

- Python environment in `.venv` (rebuilt by `setup.ps1`)
- ffmpeg: `ffmpeg.exe` and `ffprobe.exe` in `tools\ffmpeg` (from the gyan.dev build)
- Whisper speech models in `models\whisper`, and tool caches and temporary files in `temp\`
- Gemini API key saved as the environment variable `GEMINI_API_KEY`

## If YouTube downloads stop working

Update the downloader:

```
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -U yt-dlp
```
