# Short Video Maker: Project Scope

> Read this whole file first. Then follow "How to start" at the bottom.
> Do NOT write code or install anything until the user says "start".
>
> **Work already started: read `docs/PROGRESS.md` next. It says where we are and what to do first.**
> **Never use space on the C: drive. Scratch files, caches, downloads and test scripts go to
> `E:\Personal Work\Programming\Shorts Temp`; models and tools stay in this project folder.**

## 1. What we are building

A very simple, local-only tool that turns a long YouTube video into 3 short
vertical clips (like OpusClip), with face tracking and burned-in captions.

User flow:

1. User pastes a YouTube link into a minimal web page (Streamlit, localhost).
2. App downloads the video and its English transcript.
3. An AI picks the 3 best self-contained clips, each under 60 seconds.
4. Each clip is cut and converted to 9:16 vertical, with the speaker's face tracked.
5. Word-level captions are burned into each clip.
6. User gets 3 finished .mp4 files to download.

## 2. About the user (important)

- Not a programmer. Needs you to do all installation, coding, testing and fixing.
- Explain things in simple words. Keep explanations short.
- Windows laptop, Intel Core Ultra 7 255h, **no GPU**. Everything must run on CPU.
- Videos are in English for now.
- Personal use only. Runs locally on `localhost`.

## 3. Hard constraints

- **Zero cost.** Only free tools and free tiers. No paid APIs, no paid hosting.
- No domain, no hosting, no database. Do not add Vercel or any deployment.
- Keep it as simple as possible. No extra features, no fancy UI.
- API keys are read from environment variables, never written in code or committed.
- Prefer the fewest dependencies that do the job.

## 4. Tech choices (change only if something does not work, and tell the user why)

| Job | Tool |
|---|---|
| Download video + captions | yt-dlp (keep it updatable: `pip install -U yt-dlp`) |
| Transcript fallback and caption timing | faster-whisper, CPU, `small` or `base` model |
| Pick the 3 best clips | Gemini API free tier (key in `GEMINI_API_KEY`). Check current docs for a free model name; keep it in one config variable |
| Cut and encode video | ffmpeg |
| Face tracking | MediaPipe + OpenCV, with smoothing so the crop does not jitter |
| Captions | Word-level timestamps from faster-whisper, burned in via ffmpeg (ASS subtitles) or similar |
| Interface | Streamlit, localhost only |

Do not use MoviePy for the face-tracking step. Process frames with OpenCV and
use ffmpeg for cutting and muxing audio.

## 5. Key design decisions

- **Clip selection uses YouTube's captions** when available (fast and free).
  If the video has no captions, fall back to faster-whisper on the audio.
- **Run Whisper only on the 3 chosen clips** for accurate word timing for the
  captions. Do not run Whisper on a full long video unless there are no captions.
- **Clip selection output is JSON:**
  `[{"start": 12.5, "end": 58.0, "reason": "..."}]`
  Validate it: 3 clips, each under 60 seconds, within video length, start < end.
  Retry once on invalid output.
- **Manual fallback:** if the AI API is unavailable or rate limited, a button
  saves the transcript to a text file, and the user can paste clip timestamps
  by hand to continue.
- **Face tracking:** track the main speaker's face, keep the face roughly
  centered in the 9:16 crop, smooth movement over time, and fall back to
  center crop when no face is found. Output 1080x1920.
- **Captions:** large readable font, bottom-center, a few words at a time,
  good contrast (outline or shadow).
- Output files go into an `output/` folder, named clearly (for example
  `clip_1.mp4`). Temp downloads go into a `temp/` folder that can be cleaned.

## 6. Build order (each step must be tested on its own before the next)

1. Setup: install Python, ffmpeg, libraries; create a virtual environment; verify
   each tool works; write a short README with how to start the app.
2. Download: YouTube link to video file + English transcript.
3. Clip selection: transcript to Gemini to JSON with 3 clips, plus the manual fallback.
4. Cut + 9:16: center crop first, check audio stays in sync.
5. Face tracking: replace the center crop with a smoothed face-tracking crop.
6. Captions: word-level, burned in.
7. Streamlit page: paste a link, click one button, get 3 mp4 files, show progress.

## 7. Working rules

- Work on ONE step at a time. Stop after each step and tell the user what works.
- **Test everything yourself** before saying a step is done. Use a short public
  video (about 3 to 5 minutes), not a long one. Check output files exist, play
  correctly, and have audio. Inspect a few frames for face tracking.
- If something fails, read the error, fix it, and retry before asking the user.
- Use git: `git init` once, then commit after every working step with a clear message.
- Never delete files outside this project folder. Ask before any risky command.
- Keep code in a few clearly named files (for example `downloader.py`,
  `clipper.py`, `tracker.py`, `captions.py`, `app.py`) with short comments.
- Tell the user in plain words what you did and what to do next.
- Copyright note: the tool is for the user's own videos or content they have
  permission to use. Mention this once in the README, do not repeat it.

## 8. Definition of done

User runs one command (for example `streamlit run app.py`), pastes a YouTube
link, clicks one button, and gets 3 vertical clips under 60 seconds, with the
speaker's face tracked and readable captions, without spending any money.

## 9. Out of scope (do not build)

Cloud hosting, login, database, payments, batch queues, multi-language,
fancy editing UI, auto-posting to social media, speaker diarization.

## 10. How to start

1. Read this file fully.
2. Reply with a SHORT plan (not code): the build order in your own words,
   what you will install, anything unclear or risky, and any question you have.
3. Then **wait**. Do not install or write code until the user says "start".
4. When the user says "start", begin with Step 1 and continue one step at a
   time as described in section 7.
