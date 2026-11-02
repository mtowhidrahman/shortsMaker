# Short Video Maker

Turns a YouTube video into vertical short clips (9:16) with face tracking and captions.
Runs only on your computer and costs nothing.

> Use it only on your own videos, or videos you have permission to use. After you paste a link, the page
> shows the video's license. Creative Commons videos may be reused with credit, and the page gives you the credit line.

Remember always, I dont Want C drive of my PC to be taken so much space

## Start the app

**Double-click `start.bat`** in this folder. Your browser opens http://localhost:8501.
(Or in PowerShell in this folder: `.\.venv\Scripts\python.exe -m streamlit run app.py`)

1. Paste a YouTube link. The page shows the video's title and length and suggests a number of clips.
2. Choose the clip length (15 to 90 seconds, default 60–90) and how many clips (1 to 10).
   Optional: type a watermark (for example your channel name) and choose the bottom corner for it.
   Choose the caption size and the colour that lights up the word being spoken (or None).
   Tick **Let me check the clips before they are made** to see the AI's picks first: untick clips you
   don't want or change their start/end, then click **Make these clips**.
3. Click **Make shorts**. It takes a few minutes (more clips take longer). Each clip appears with a
   download button as soon as it is ready. **Cancel** stops the rest; finished clips stay.
4. Watch and download the clips on the page. They are also saved in the `output` folder
   (the next run replaces them, so download the ones you want to keep).
   Under each clip: **Title, description, hashtags** (written by the AI, with a copy button) and
   **Change this clip** (new start/end, then **Remake clip N** makes only that clip again).
5. If the AI can't pick clips (no key, the free limit is reached, or Gemini is busy), the page lets you
   save the transcript and type the clip times yourself, like `1:05 - 2:20` (one clip per line).

Every clip starts at the beginning of a sentence and ends at the end of one. The AI checks this;
when it is not available, the app uses the speech recognizer's punctuation and pauses instead.

To stop the app, close the black `start.bat` window.

Temporary files and downloaded videos go to `E:\Personal Work\Programming\Shorts Temp`.
You can empty that folder from the page ("Free up space") or delete its contents yourself.

For best speed, close apps you don't need (other browsers, the ChatGPT app) while it runs.
The PC's memory is nearly full, and Windows then uses extra space on C:.

## One-time setup (run again if you move this folder)

```
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Everything is kept inside this folder to save space on C: (only Python 3.12 itself is on C:).

- Python environment in `.venv` (rebuilt by `scripts\setup.ps1`)
- ffmpeg: `ffmpeg.exe` and `ffprobe.exe` in `tools\ffmpeg` (from the gyan.dev build)
- Whisper speech model in `models\whisper`, face model in `models\`
- Tool caches and temporary files in `E:\Personal Work\Programming\Shorts Temp`
- Gemini API key saved as the environment variable `GEMINI_API_KEY`

## If YouTube downloads stop working

Update the downloader:

```
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -U yt-dlp
```
