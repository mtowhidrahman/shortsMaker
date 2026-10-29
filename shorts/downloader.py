# Step 2: YouTube link -> video file + English transcript.
# Transcript comes from YouTube captions; if there are none, Whisper listens to the audio.
from . import config  # first: sets memory limits before numpy loads

import json
import re
import subprocess
import sys

import numpy as np
import yt_dlp
from yt_dlp.extractor.youtube import YoutubeIE

from .report import console


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


def _whisper_transcript(video_path, duration=0, progress=console):
    """Fallback when the video has no captions: transcribe the full audio on CPU.
    beam_size=1: 30% faster, same text in tests (the captions use the careful default)."""
    segs, _ = load_whisper().transcribe(load_audio(video_path), language="en", vad_filter=True, beam_size=1)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        if duration:
            progress("Transcribing audio with Whisper...", min(1, s.end / duration), "transcribe")
    return out


def transcript_text(segments):
    """Readable transcript with [seconds] stamps, used for Gemini and the manual fallback."""
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


# Highest real resolution up to 1080p (skip YouTube's AI-upscaled "-sr" versions).
# Between equal resolutions prefer H.264 + AAC (fastest to process).
YDL_OPTS = {
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
    "no_color": True,                # plain error text (no colour codes on the page)
}
_info_cache = {}   # video id -> YouTube's info from video_info(), so download() doesn't ask again


def _video_id(url):
    return YoutubeIE.suitable(url) and YoutubeIE._match_id(url)


def _friendly(e):
    """A readable error for the page."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "").strip()
    if "not a bot" in text:
        return RuntimeError("YouTube is asking to confirm you are not a bot. This is usually "
                            "temporary: wait a while and try again.")
    if "429" in text or "Too Many Requests" in text:
        return RuntimeError("YouTube says there were too many requests from this computer. This is "
                            "temporary: wait an hour or so and try again.")
    return RuntimeError(f"Could not read the video: {text}")


class _Messages:
    """Collects yt-dlp's messages instead of printing them, so problems can be explained on the page."""
    def __init__(self):
        self.errors, self.warnings = [], []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def _rights(info):
    """Who made the video and how it may be reused: {"channel", "license"}.
    license: "cc" (Creative Commons: reuse allowed with credit), "standard" (YouTube's normal
    license: you need the owner's permission) or "unknown" (copies saved by older versions)."""
    if "license" in info and info["license"] in ("cc", "standard", "unknown"):   # our own saved notes
        return {"channel": info.get("channel", ""), "license": info["license"]}
    lic = str(info.get("license") or "")
    return {"channel": info.get("channel") or info.get("uploader") or "",
            "license": "cc" if "creative commons" in lic.lower() else "standard"}


def video_info(url):
    """Title, length and license of a video without downloading it:
    {"id", "title", "duration", "channel", "license"}.
    Uses the downloaded copy's notes if there is one (then YouTube is not asked at all)."""
    vid = _video_id(url)
    if not vid:
        raise RuntimeError("This doesn't look like a YouTube video link.")
    cache = config.TEMP_DIR / f"{vid}_info.json"
    if cache.exists() and (config.TEMP_DIR / f"{vid}.mp4").exists():
        r = json.loads(cache.read_text(encoding="utf-8"))
        r.setdefault("license", "unknown")
    else:
        if vid not in _info_cache:
            try:
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    _info_cache[vid] = ydl.sanitize_info(ydl.extract_info(url, download=False))
            except yt_dlp.utils.DownloadError as e:
                raise _friendly(e) from e
        r = _info_cache[vid]
    return {"id": vid, "title": r.get("title", vid), "duration": float(r.get("duration") or 0), **_rights(r)}


def download(url, progress=console):
    """Download video (max 1080p, mp4) and English captions into the temp folder.
    Returns dict with video_path, title, duration, segments, transcript_source.
    If this video was downloaded before, reuse it (fewer YouTube requests = fewer bot checks)."""
    config.TEMP_DIR.mkdir(exist_ok=True)
    vid = _video_id(url)
    cache = config.TEMP_DIR / f"{vid}_info.json"
    if vid and cache.exists() and (config.TEMP_DIR / f"{vid}.mp4").exists():
        progress("Using the copy already downloaded in the temp folder.", step="download")
        r = json.loads(cache.read_text(encoding="utf-8"))
        r["video_path"] = config.TEMP_DIR / f"{vid}.mp4"
        return r

    progress("Downloading video and captions...", step="download")

    def hook(d):   # yt-dlp reports bytes; video and sound are two files, downloaded one after the other
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if d.get("status") == "downloading" and total:
            kind = "sound" if d.get("info_dict", {}).get("vcodec") == "none" else "video"
            progress(f"Downloading {kind}...", min(1, d.get("downloaded_bytes", 0) / total), "download")

    # ignoreerrors: if YouTube refuses the captions (e.g. "429 Too Many Requests"), still download
    # the video; Whisper then writes the transcript. Real failures are caught below.
    messages = _Messages()
    try:
        with yt_dlp.YoutubeDL({**YDL_OPTS, "progress_hooks": [hook], "logger": messages,
                               "ignoreerrors": True}) as ydl:
            info = None
            if vid in _info_cache:   # video_info() already asked YouTube: download from that answer
                try:
                    info = ydl.process_ie_result(_info_cache.pop(vid), download=True)
                except Exception as e:   # e.g. the answer is too old: ask again below
                    progress(f"Asking YouTube again ({str(e)[:60]})...")
            if info is None or not (config.TEMP_DIR / f"{info['id']}.mp4").exists():
                info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise _friendly(e) from e

    video_path = config.TEMP_DIR / f"{(info or {}).get('id', vid)}.mp4"
    if not info or not video_path.exists():
        raise _friendly(" ".join(messages.errors) or "the download failed for an unknown reason")
    vid = info["id"]
    refused = any("subtitles" in m for m in messages.errors + messages.warnings)

    segments, source = [], "youtube captions"
    for lang in YDL_OPTS["subtitleslangs"]:
        sub = config.TEMP_DIR / f"{vid}.{lang}.json3"
        if sub.exists():
            segments = _parse_json3(sub)
            break
    if not segments:
        progress("YouTube did not give the captions this time (too many requests), so Whisper is writing "
                 "the transcript instead..." if refused else
                 "No English captions found. Transcribing audio with Whisper (this takes a while)...",
                 step="transcribe")
        segments, source = _whisper_transcript(video_path, float(info.get("duration") or 0), progress), "whisper"

    (config.TEMP_DIR / f"{vid}_transcript.txt").write_text(transcript_text(segments), encoding="utf-8")
    r = {"id": vid, "title": info.get("title", vid), "duration": float(info.get("duration") or 0),
         "segments": segments, "transcript_source": source, **_rights(info)}
    (config.TEMP_DIR / f"{vid}_info.json").write_text(json.dumps(r), encoding="utf-8")
    return {**r, "video_path": video_path}


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.downloader <youtube link>
    r = download(sys.argv[1])
    print(f"Title: {r['title']}\nDuration: {r['duration']}s\nVideo: {r['video_path']}")
    print(f"Transcript: {len(r['segments'])} lines from {r['transcript_source']}")
    print(transcript_text(r["segments"][:5]))
