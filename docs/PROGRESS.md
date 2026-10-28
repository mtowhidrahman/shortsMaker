# Progress notes (for Claude: read this after CLAUDE.md)

Last updated: 2026-10-28. **All 7 steps are done** and committed in git. The app works end to end.
Start it with `start.bat` (or `.venv\Scripts\python.exe -m streamlit run app.py`).
Any further work is fixes or tweaks the user asks for. Keep following the C: rules below.

## Round 2: agreed plan (2026-10-28). Wait for the user to say "start", then do one part at a time

The user tested the app and everything worked. Do these in order, test and commit each one, and report after each:
- **A. Folders (DONE):** move the engine into `shorts/` (config, downloader, clipper, cutter, tracker, captions),
  `setup.ps1` into `scripts/`, PROGRESS.md into `docs/`. app.py, start.bat, README and CLAUDE.md stay at the root.
  No change in behaviour.
- **B. Page cleanup:** hide the Deploy button, the menu and the running animation. Fix the delete section
  (a one-line expression `shutil.rmtree(p) if ... else p.unlink()` is printed as "None" by Streamlit magic).
  Show the size before deleting and "Freed X MB" after.
- **C. Clean endings (most important):** clips end mid-sentence because YouTube auto-captions have no
  punctuation. After Gemini picks a clip, run Whisper a few seconds past the end and move the end (and the start)
  to a real sentence end followed by a pause, without going over the length limit.
- **D. Clip count and length:** an input for 1–10 clips and a length slider. **The user approved clips up to
  90 s** (this replaces "under 60 s" in CLAUDE.md). The default should prefer long clips. Long videos (30+ min)
  should be able to give 5–7 clips of up to 90 s. Check the count against the video length.
  **Both are inputs, not hardcoded.** Flow: paste a link → "Check video" (one small info request, no download;
  cache the info so the download reuses it) → show the title and length plus a suggested count (about 1 per
  4–5 min, at least 1, at most 10), pre-filled and editable → length slider (default 60–90 s, range 15–90) →
  "Make shorts".
- **E. Speed:** encode once instead of twice (no intermediate crf16 cut), x264 preset medium → veryfast,
  face detection on smaller frames. Time each stage before and after and report the numbers. Keep RAM low.
- **F. Progress:** a bar for each stage (download %, clip picking, per clip: captions, face scan, render %),
  an estimated time left, a total timer, and a final "Finished in X" with each stage's time.
- **G. Copyright:** show the video's license (Creative Commons or Standard) and a credit line for CC videos.
  No tricks to dodge Content ID.
- **H. Hosting:** the user said "not right now". Don't build anything.

## Project location

The project stays at `E:\Personal Work\Programming\Shorts` (the user decided not to move it).
If it is ever moved, run `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` first (it rebuilds `.venv`).

## Hard rule from the user: never use space on C:

The user wants C: to stay at about 11+ GB free, always. They said this clearly and more than once.
- **Scratch folder: `E:\Personal Work\Programming\Shorts Temp`** (`config.TEMP_DIR`). Downloads,
  cut pieces, tool caches and Claude's own test scripts/images go there (scripts in `Shorts Temp\scratch`),
  never in the system Temp or the Claude scratchpad on C:. Models and tools stay in the project folder.
- `config.py` redirects TMP/TEMP, HF_HOME, XDG_CACHE_HOME (yt-dlp) and PIP_CACHE_DIR into
  that folder for anything that imports it. Always `from shorts import config` first (inside the package: `from . import config`).
- Keep RAM use low (stream frames one at a time, never load a whole video into memory) so
  Windows' page file on C: does not grow. The PC has 15.4 GB RAM, and other apps (Chrome, VS Code, ChatGPT,
  Edge) already commit about 23 of the 24.8 GB limit. During Step 5 the page file grew to about 14 GB.
  Fixes in place: `OPENBLAS_NUM_THREADS=2` in config.py (saves ~470 MB, so **`import config` must be the first
  import**), `cv2.setNumThreads(4)`, ffmpeg `-threads` + `rc-lookahead=10`. Measured peak for one clip:
  about 540 MB (was 1.9 GB). Also `CT2_USE_MKL=0` (Whisper's CTranslate2 with MKL committed ~1 GB to load
  `base`; without it, 0.39 GB peak at the same speed). Full pipeline for 3 clips: peak about 770 MB, about 2 minutes.
  The Whisper `small` model peaks at 2.7 GB, so don't use it on this PC.
- Check C: free space before and after each step and tell the user.
- Install with `pip install --no-cache-dir`. No winget or global installs.
- Python 3.12 itself is on C: (installed before this project). That is allowed.
- The user said no to Windows changes (moving the page file, turning off hibernate). Don't bring them up again.
- Streamlit (Step 7): add `.streamlit/config.toml` in the project with
  `[browser] gatherUsageStats = false` and run it headless so it doesn't write `~/.streamlit`.

## Where things live

| What | Where |
|---|---|
| Python env | `.venv` (Python 3.12) |
| ffmpeg / ffprobe | `tools/ffmpeg/` (gyan.dev 9.0.2 full build). `config.py` adds it to PATH |
| Whisper model | `models/whisper/` (faster-whisper `base`, int8, CPU) |
| Face model | `models/face_detection_yunet_2023mar.onnx` (OpenCV YuNet, `cv2.FaceDetectorYN`) |
| Downloads, cache, intermediates | `E:\Personal Work\Programming\Shorts Temp` |
| Finished clips | `output/clip_N.mp4` |
| Gemini key | User env var `GEMINI_API_KEY` (already set). If a shell doesn't see it, load it with `[Environment]::GetEnvironmentVariable("GEMINI_API_KEY","User")`. Never print it |

`tools/`, `models/whisper/`, `output/`, `.venv/` are git-ignored.

## Files

Layout: `app.py` (the page) and `start.bat` at the root; the engine is the `shorts/` package. Run a
module's quick test with `.venv\Scripts\python.exe -m shorts.<name>` from the project folder.
Baseline speed before Part E: 3 clips (27.5 + 31.5 + 29.5 s) took 254 s through the app (manual times).


- `shorts/config.py`: paths, cache redirects, settings (Gemini model `gemini-3.8-flash`, which is free tier;
  3 clips; 15–59 s; PAD_START 0.5 s, PAD_END 0).
- `shorts/downloader.py` (Step 2): `download(url)` → dict(id, video_path, title, duration, segments,
  transcript_source). Uses English YouTube captions (json3), and Whisper as a fallback.
  **Caches** each video in TEMP_DIR as `{id}.mp4` + `{id}_info.json` and reuses it.
  Also has `load_audio()` (ffmpeg → numpy) and `load_whisper()`.
- `shorts/clipper.py` (Step 3): `pick_clips()` (Gemini JSON, validate, retry once, raises ClipError),
  `validate()`, `save_transcript()`, `parse_manual()` (lines like `1:05 - 1:50`).
- `shorts/cutter.py` (Step 4): `cut()` (frame-accurate re-encode at original size → TEMP_DIR `clip_N_raw.mp4`),
  `center_crop()` (simple version, unused), **`make_clips(video, clips, duration, progress)`** = the whole
  per-clip pipeline: cut → `make_captions` → `track_crop(vf="ass=clip_N.ass")` → `output/clip_N.mp4`.
- `shorts/captions.py` (Step 6): Whisper `base` word timestamps on the raw clip (vad, word_timestamps), chunks of
  ≤3 words / ≤1.6 s / break at pause >0.45 s or punctuation, UPPERCASE, trailing `.,;:` removed. ASS style: Arial bold 112,
  white with black outline 9 + shadow 4, bottom-center, MarginV 460. The encoder ffmpeg runs with cwd=TEMP_DIR, so
  `ass=clip_N.ass` needs no path escaping. `config.py` writes its own fonts.conf (cache in TEMP_DIR) so
  fontconfig never writes to C:.
- `shorts/tracker.py` (Step 5): `track_crop(src, out, vf=None)`. Pass 1 decodes with an ffmpeg pipe, detects
  camera cuts (mean abs diff of 64x36 gray > 18) and runs YuNet on every 2nd frame. Per shot,
  detections are linked into tracks, and the speaker track is the one with the highest sum of
  area·conf²·(1 if in the upper half else 0.3). The camera plan per shot: interpolate, median filter, dead
  zone 12%, forward+backward EMA (0.6 s). No face → center. Pass 2 crops, resizes to 1080x1920 and pipes to
  ffmpeg with `-itsoffset` = source video start, audio copied. **`vf` hook is for Step 6 (burn in ASS
  captions in the same encode).**
- `scripts/setup.ps1`: rebuild the environment.

## Test data (avoid re-downloading: the user worries about YouTube blocks)

- Test video: https://www.youtube.com/watch?v=NiKtZgImdlY ("The danger of silence", Clint Smith, 4:23,
  720p H.264). Already cached in `Shorts Temp`. **Do not download it again.**
  Keep download tests to a minimum.
- Gemini's picks for it (reuse them instead of calling Gemini again): 13.1–39.7, 143.2–173.7, 182.9–212.0.
- Step 5 results: face followed in 100% of frames, offset from crop center ≤0.17 of crop width,
  all camera cuts found, about 65 s for 3 clips. Test scripts are in `Shorts Temp\scratch` (test_step5.py, test_tracker.py).

## Problems solved (don't repeat them)

- YouTube "Sign in to confirm you're not a bot" after several downloads → added the download cache and a clear
  error message. Never use the user's browser cookies (the user worries about their account).
- faster-whisper + PyAV 19 mismatch (`metadata_errors` TypeError) → never pass file paths to
  Whisper. Pass `downloader.load_audio(path, start, end)` (numpy) instead.
- Installing two OpenCV packages at once breaks cv2 → only `opencv-python-headless==4.14.0.94` (YuNet works,
  no GUI parts needed). Swapped from opencv-contrib-python 5.0 to save space.
- MediaPipe's BlazeFace (short range) found faces in only about 40% of frames (it missed small faces on wide shots) →
  switched to OpenCV YuNet (100%) and uninstalled MediaPipe. `flatbuffers` must stay (needed by onnxruntime for Whisper VAD).
- Audience faces are as confident as the speaker's → choose the speaker per shot by track (see tracker.py), not per frame.
- Camera-cut threshold 30 missed similar-looking shots → 18.
- `-shortest` dropped the last frames → removed. Decode with `-fps_mode passthrough`.
- Download format: highest real resolution ≤1080p, skip AI-upscaled `-sr` formats, prefer
  H.264/AAC. Always read frames through an ffmpeg pipe, not `cv2.VideoCapture`.
- Caption start times are late, so clips start 0.5 s early. Caption end times are already late, so no end padding.

## Step 7 (done)

- `app.py`: link + "Make 3 shorts" (always enabled; a warning if the link is empty) → `st.status` progress →
  3 `st.video` + download buttons. On ClipError: a warning, "Save transcript" (→ output/transcript_ID.txt),
  "Download transcript", a text area for times → `parse_manual` → `run(clips_from_user)` → `st.rerun()`.
  "Free up space" expander deletes TEMP_DIR contents except `cache` and `scratch`.
- `.streamlit/config.toml`: headless, localhost only, no usage stats → no `~/.streamlit` on C: (verified).
- `start.bat`: opens the browser and runs streamlit.
- Tested with `streamlit.testing.v1.AppTest` (Shorts Temp\scratch\test_app.py, scenarios `ai` and `manual`)
  and a real server (health ok, listens on 127.0.0.1 only). The Chrome extension was not connected, so there was no
  visual browser check. The user allows Chrome use.
