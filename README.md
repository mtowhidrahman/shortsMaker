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

- Python 3.12 virtual environment in `.venv`
- ffmpeg (installed with `winget install Gyan.FFmpeg`)
- Libraries: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Gemini API key saved as the environment variable `GEMINI_API_KEY`

## If YouTube downloads stop working

Update the downloader:

```
.\.venv\Scripts\python.exe -m pip install -U yt-dlp
```
