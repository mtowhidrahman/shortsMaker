# Short Video Maker

Turns a YouTube video into 3 vertical short clips (9:16) with face tracking and captions.
Runs only on your computer and costs nothing.

> Use it only on your own videos, or videos you have permission to use.

## Start the app

Open PowerShell in this folder and run:

```
.\.venv\Scripts\streamlit.exe run app.py
```

Your browser opens the app. Paste a YouTube link and click the button.
Finished clips are saved in the `output` folder.

## One-time setup (already done)

Everything heavy is kept inside this folder (E: drive) to save space on C:.

- Python 3.12 virtual environment in `.venv`
- ffmpeg: `ffmpeg.exe` and `ffprobe.exe` in `tools\ffmpeg` (from the gyan.dev build)
- Whisper speech models download into `models\whisper` on first use
- Libraries: `.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt`
- Gemini API key saved as the environment variable `GEMINI_API_KEY`

## If YouTube downloads stop working

Update the downloader:

```
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -U yt-dlp
```
