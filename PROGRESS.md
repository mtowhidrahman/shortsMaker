# Progress notes (for Claude: read this after CLAUDE.md)

Last updated: 2026-10-28. Steps 1–4 are done and committed in git. **Next: Step 5 (face tracking).**
Wait for the user to say "next" before starting Step 5.

## FIRST THING after the project folder was moved

The user moved this folder from `E:\Personal Work\Programming\Shorts` to a new place. The
`.venv` folder stores its old path and no longer works. Do this first:

1. Run `powershell -ExecutionPolicy Bypass -File setup.ps1` in the project folder.
   It deletes and rebuilds `.venv` (Python 3.12, `--no-cache-dir`), checks the face model,
   checks ffmpeg in `tools\ffmpeg`, and loads Whisper. It must print `Setup OK`.
2. Check that the old C: caches did not come back: `C:\Users\USER\.cache\huggingface`
   and `C:\Users\USER\AppData\Local\pip` should not exist.
3. Then tell the user it worked and ask before starting Step 5.

## Hard rule from the user: keep C: free

The user's C: drive is almost full (about 4–5 GB free). They said this clearly and more than once.
- Everything the project creates or downloads must stay inside the project folder: models,
  caches, temp files, downloaded videos, generated clips, and Claude's own test scripts
  (put those in `temp/`, not in the system Temp/scratchpad).
- `config.py` already redirects TMP/TEMP, HF_HOME, XDG_CACHE_HOME (yt-dlp) and PIP_CACHE_DIR
  into `temp/` for anything that imports it. Always `import config` first.
- Install with `pip install --no-cache-dir`. No winget or global installs.
- Python 3.12 itself is on C: (installed before this project). That is allowed.
- The user said no to Windows changes (moving the page file, turning off hibernate). Don't bring them up again.
- Streamlit (Step 7): add `.streamlit/config.toml` in the project with
  `[browser] gatherUsageStats = false` and run it headless so it doesn't write `~/.streamlit`.

## Where things live (all inside the project)

| What | Where |
|---|---|
| Python env | `.venv` (Python 3.12; MediaPipe does not support the 3.14 that is also installed) |
| ffmpeg / ffprobe | `tools/ffmpeg/` (gyan.dev 9.0.2 full build). `config.py` adds it to PATH |
| Whisper model | `models/whisper/` (faster-whisper `base`, int8, CPU) |
| Face model | `models/blaze_face_short_range.tflite` (MediaPipe Tasks FaceDetector) |
| Downloads, cache, intermediates | `temp/` |
| Finished clips | `output/clip_N.mp4` |
| Gemini key | User env var `GEMINI_API_KEY` (already set). If a shell doesn't see it, load it with `[Environment]::GetEnvironmentVariable("GEMINI_API_KEY","User")`. Never print it |

`tools/`, `models/whisper/`, `temp/`, `output/`, `.venv/` are git-ignored.

## Files

- `config.py`: paths, cache redirects, settings (Gemini model `gemini-3.8-flash`, which is free tier;
  3 clips; 15–59 s; PAD_START 0.5 s, PAD_END 0).
- `downloader.py` (Step 2): `download(url)` → dict(id, video_path, title, duration, segments,
  transcript_source). Uses English YouTube captions (json3), and Whisper as a fallback.
  **Caches** each video in `temp/{id}.mp4` + `temp/{id}_info.json` and reuses it.
  Also has `load_audio()` (ffmpeg → numpy) and `load_whisper()`.
- `clipper.py` (Step 3): `pick_clips()` (Gemini JSON, validate, retry once, raises ClipError),
  `validate()`, `save_transcript()`, `parse_manual()` (lines like `1:05 - 1:50`).
- `cutter.py` (Step 4): `cut()` (frame-accurate re-encode at original size → `temp/clip_N_raw.mp4`),
  `center_crop()` (1080x1920), `make_clips(video, clips, duration)`.
- `setup.ps1`: rebuild the environment.

## Test data (avoid re-downloading: the user worries about YouTube blocks)

- Test video: https://www.youtube.com/watch?v=NiKtZgImdlY ("The danger of silence", Clint Smith, 4:23,
  720p H.264). Already cached in `temp/` and moves with the folder. **Do not download it again.**
  Keep download tests to a minimum.
- Gemini's picks for it (reuse them instead of calling Gemini again): 13.1–39.7, 143.2–173.7, 182.9–212.0.
- In clip 2 the speaker stands off-center, so the center crop cuts him off. Good test for Step 5.

## Problems solved (don't repeat them)

- YouTube "Sign in to confirm you're not a bot" after several downloads → added the download cache and a clear
  error message. Never use the user's browser cookies (the user worries about their account).
- faster-whisper + PyAV 19 mismatch (`metadata_errors` TypeError) → never pass file paths to
  Whisper. Pass `downloader.load_audio(path, start, end)` (numpy) instead.
- Installing both `opencv-python` and `opencv-contrib-python` breaks cv2 → only `opencv-contrib-python`.
- MediaPipe 1.1.1 has no `mp.solutions`; use `mediapipe.tasks.python.vision.FaceDetector`.
- Download format: highest real resolution ≤1080p, skip AI-upscaled `-sr` formats, prefer
  H.264/AAC. Videos may still be AV1/VP9, so in Step 5 read frames through an ffmpeg pipe, not
  `cv2.VideoCapture`.
- Caption start times are late, so clips start 0.5 s early. Caption end times are already late, so no end padding.

## Plan for the next steps

- Step 5 `tracker.py`: read `temp/clip_N_raw.mp4` frames through an ffmpeg rawvideo pipe, detect
  faces (every frame or every 2nd), pick the largest/main face, smooth the crop center (keep the
  crop still unless the face moves far), fall back to the center when no face is found, crop 9:16, write
  1080x1920 frames to an ffmpeg pipe, and mux the audio from the raw clip. Check a few frames.
- Step 6 `captions.py`: Whisper word timestamps on each clip only (`load_audio` of the clip),
  ASS file with a few words at a time, large bottom-center text with an outline, burned in with ffmpeg (ideally in
  the same encode as Step 5 to avoid encoding twice).
- Step 7 `app.py`: Streamlit page with link → button → progress → 3 downloads, plus the manual fallback
  (save the transcript, paste timestamps).
