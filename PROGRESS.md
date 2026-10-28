# Progress notes (for Claude: read this after CLAUDE.md)

Last updated: 2026-10-28. Steps 1–6 are done and committed in git. **Next: Step 7 (Streamlit app).**
Wait for the user to say "next" before starting Step 7.

## Project location

The project stays at `E:\Personal Work\Programming\Shorts` (the user decided not to move it).
If it is ever moved, run `powershell -ExecutionPolicy Bypass -File setup.ps1` first (it rebuilds `.venv`).

## Hard rule from the user: never use space on C:

The user wants C: to stay at about 11+ GB free, always. They said this clearly and more than once.
- **Scratch folder: `E:\Personal Work\Programming\Shorts Temp`** (`config.TEMP_DIR`). Downloads,
  cut pieces, tool caches and Claude's own test scripts/images go there (scripts in `Shorts Temp\scratch`),
  never in the system Temp or the Claude scratchpad on C:. Models and tools stay in the project folder.
- `config.py` redirects TMP/TEMP, HF_HOME, XDG_CACHE_HOME (yt-dlp) and PIP_CACHE_DIR into
  that folder for anything that imports it. Always `import config` first.
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

- `config.py`: paths, cache redirects, settings (Gemini model `gemini-3.8-flash`, which is free tier;
  3 clips; 15–59 s; PAD_START 0.5 s, PAD_END 0).
- `downloader.py` (Step 2): `download(url)` → dict(id, video_path, title, duration, segments,
  transcript_source). Uses English YouTube captions (json3), and Whisper as a fallback.
  **Caches** each video in TEMP_DIR as `{id}.mp4` + `{id}_info.json` and reuses it.
  Also has `load_audio()` (ffmpeg → numpy) and `load_whisper()`.
- `clipper.py` (Step 3): `pick_clips()` (Gemini JSON, validate, retry once, raises ClipError),
  `validate()`, `save_transcript()`, `parse_manual()` (lines like `1:05 - 1:50`).
- `cutter.py` (Step 4): `cut()` (frame-accurate re-encode at original size → TEMP_DIR `clip_N_raw.mp4`),
  `center_crop()` (simple version, unused), **`make_clips(video, clips, duration, progress)`** = the whole
  per-clip pipeline: cut → `make_captions` → `track_crop(vf="ass=clip_N.ass")` → `output/clip_N.mp4`.
- `captions.py` (Step 6): Whisper `base` word timestamps on the raw clip (vad, word_timestamps), chunks of
  ≤3 words / ≤1.6 s / break at pause >0.45 s or punctuation, UPPERCASE, trailing `.,;:` removed. ASS style: Arial bold 112,
  white with black outline 9 + shadow 4, bottom-center, MarginV 460. The encoder ffmpeg runs with cwd=TEMP_DIR, so
  `ass=clip_N.ass` needs no path escaping. `config.py` writes its own fonts.conf (cache in TEMP_DIR) so
  fontconfig never writes to C:.
- `tracker.py` (Step 5): `track_crop(src, out, vf=None)`. Pass 1 decodes with an ffmpeg pipe, detects
  camera cuts (mean abs diff of 64x36 gray > 18) and runs YuNet on every 2nd frame. Per shot,
  detections are linked into tracks, and the speaker track is the one with the highest sum of
  area·conf²·(1 if in the upper half else 0.3). The camera plan per shot: interpolate, median filter, dead
  zone 12%, forward+backward EMA (0.6 s). No face → center. Pass 2 crops, resizes to 1080x1920 and pipes to
  ffmpeg with `-itsoffset` = source video start, audio copied. **`vf` hook is for Step 6 (burn in ASS
  captions in the same encode).**
- `setup.ps1`: rebuild the environment.

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

## Plan for the next steps

- Step 7 `app.py`: Streamlit page with link → button → progress → 3 downloads, plus the manual fallback
  (save the transcript, paste timestamps).
