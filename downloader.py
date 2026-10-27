# Step 2: YouTube link -> video file + English transcript.
# Transcript comes from YouTube captions; if there are none, Whisper listens to the audio.
import json
import subprocess
import sys

import numpy as np
import yt_dlp

import config


def _parse_json3(path):
    """Turn a YouTube json3 caption file into [{start, end, text}] segments (seconds)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or []).replace("\n", " ").strip()
        if not text:
            continue
        start = ev["tStartMs"] / 1000
        end = start + ev.get("dDurationMs", 0) / 1000
        segments.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return segments


def load_audio(path, start=None, end=None):
    """Read audio with ffmpeg as 16 kHz mono float32 (what Whisper expects).
    Optional start/end in seconds to read only part of the file."""
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def load_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                        download_root=str(config.WHISPER_DIR))


def _whisper_transcript(video_path):
    """Fallback when the video has no captions: transcribe the full audio on CPU."""
    segs, _ = load_whisper().transcribe(load_audio(video_path), language="en", vad_filter=True)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]


def transcript_text(segments):
    """Readable transcript with [seconds] stamps, used for Gemini and the manual fallback."""
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def download(url, progress=print):
    """Download video (max 1080p, mp4) and English captions into temp/.
    Returns dict with video_path, title, duration, segments, transcript_source."""
    config.TEMP_DIR.mkdir(exist_ok=True)
    opts = {
        # Highest real resolution up to 1080p (skip YouTube's AI-upscaled "-sr" versions).
        # Between equal resolutions prefer H.264 + AAC (fastest to process).
        "format": "bv*[height<=1080][format_id!*=-sr]+ba/b[height<=1080]/b",
        "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "outtmpl": str(config.TEMP_DIR / "%(id)s.%(ext)s"),
        "ffmpeg_location": str(config.FFMPEG_DIR),
        "writesubtitles": True,          # human-made captions (preferred)
        "writeautomaticsub": True,       # YouTube auto captions (used if no human ones)
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "json3",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
    }
    progress("Downloading video and captions...")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    vid = info["id"]
    video_path = config.TEMP_DIR / f"{vid}.mp4"
    if not video_path.exists():
        raise RuntimeError("Download finished but the video file was not found.")

    segments, source = [], "youtube captions"
    for lang in opts["subtitleslangs"]:
        sub = config.TEMP_DIR / f"{vid}.{lang}.json3"
        if sub.exists():
            segments = _parse_json3(sub)
            break
    if not segments:
        progress("No English captions found. Transcribing audio with Whisper (this takes a while)...")
        segments, source = _whisper_transcript(video_path), "whisper"

    (config.TEMP_DIR / f"{vid}_transcript.txt").write_text(transcript_text(segments), encoding="utf-8")
    return {"id": vid, "video_path": video_path, "title": info.get("title", vid),
            "duration": float(info.get("duration") or 0), "segments": segments,
            "transcript_source": source}


if __name__ == "__main__":
    # Quick test: python downloader.py <youtube link>
    r = download(sys.argv[1])
    print(f"Title: {r['title']}\nDuration: {r['duration']}s\nVideo: {r['video_path']}")
    print(f"Transcript: {len(r['segments'])} lines from {r['transcript_source']}")
    print(transcript_text(r["segments"][:5]))
