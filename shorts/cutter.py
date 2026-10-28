# Cut clips out of the long video and turn them into finished vertical shorts (1080x1920):
# cut (Step 4) -> captions (Step 6, captions.py) -> face-tracking crop + burn-in (Step 5, tracker.py).
# center_crop() is the simple Step 4 version, kept for reference.
from . import config  # first: sets memory limits and cache folders

import re
import subprocess
import sys

from .captions import captions_for, transcribe_words
from .clipper import fix_edges
from .downloader import load_whisper
from .tracker import track_crop

OUT_W, OUT_H = 1080, 1920
START_SEARCH = 4.0     # look this many seconds around the AI's start for a sentence start
END_SEARCH = 10.0      # Whisper listens this far past the clip, so a sentence can be finished
SENTENCE_PAUSE = 0.7   # a pause this long (without a comma) also counts as the end of a sentence
LEAD = 0.3             # seconds of quiet kept before the first word
TAIL = 0.4             # seconds kept after the last word, so it doesn't sound cut off
ABBREVIATIONS = {"dr.", "mr.", "mrs.", "ms.", "jr.", "sr.", "st.", "vs.", "etc.", "e.g.", "i.e.", "u.s."}


def run(cmd):
    """Run ffmpeg and show its error message if it fails."""
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{p.stderr[-1500:]}")


def cut(video, start, end, out):
    """Cut [start, end] seconds from the video, re-encoded so the cut is frame-accurate
    and audio stays in sync. Keeps the original size (cropping happens later)."""
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
         "-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "0:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    return out


def center_crop(src, out):
    """Crop the middle 9:16 slice of the frame and scale it to 1080x1920."""
    vf = f"crop=trunc(ih*9/16/2)*2:ih,scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", str(out)])
    return out


def _gap_after(words, i):
    """Silence after word i. Unknown (0) for the last word heard: Whisper's listening
    window may have cut it off mid-sentence."""
    return words[i + 1]["start"] - words[i]["end"] if i + 1 < len(words) else 0.0


def _end_penalty(words, i):
    """How bad it is to end a sentence after word i (None = word i does not end one).
    Backup rules, used only when Gemini can't check the edges: Whisper's full stops are
    often right but not always; a long pause without a comma counts a little."""
    w = words[i]
    if w.get("cut_off"):
        return None
    if re.search(r"[.?!][\"')\]]*$", w["word"]) and w["word"].lower().strip("\"')]") not in ABBREVIATIONS:
        return 0.0
    if _gap_after(words, i) >= SENTENCE_PAUSE and not w["word"].endswith(","):
        return 1.5
    return None


def listen(video, model, start, end, duration):
    """Whisper words (times in video seconds, with punctuation) for [start, end] of the video.
    Words in the last 1.5 s may be cut off by the window, so they are marked."""
    words = transcribe_words(video, model, start, end)
    for w in words:
        w["cut_off"] = end < duration and w["end"] > end - 1.5
    return words


def sentence_edges(words, start, end, min_len, max_len):
    """Backup rules: the word numbers where the clip should start and end, so it holds whole
    sentences near the AI's [start, end]. Ending earlier than the AI is worse than ending later."""
    # Start: the sentence start nearest to the AI's start (a little earlier or later).
    # The first word heard counts too: Whisper listened from START_SEARCH + 1 s before the
    # AI's start, so a first word starting later than that had silence before it.
    near = [(abs(words[i]["start"] - start) + p, i) for i in range(len(words))
            if abs(words[i]["start"] - start) <= START_SEARCH
            and (p := (_end_penalty(words, i - 1) if i else 0.0)) is not None]
    s = min(near)[1] if near else next((i for i, w in enumerate(words) if w["start"] >= start - 0.3), 0)

    # End: the best sentence end near the AI's end, keeping the clip between min and max length.
    lo, hi = words[s]["start"] + min_len, words[s]["start"] + max_len - LEAD - TAIL
    ends = []
    for i in range(s, len(words)):
        p = _end_penalty(words, i)
        if p is not None and lo <= words[i]["end"] <= hi:
            moved = words[i]["end"] - end
            ends.append((p + (moved if moved >= 0 else -1.5 * moved), i))
    if ends:
        return s, min(ends)[1]
    # No sentence end fits: stop at the longest pause near the AI's end.
    fits = [i for i in range(s, len(words)) if lo <= words[i]["end"] <= hi and not words[i]["cut_off"]] or [s]
    return s, max(fits, key=lambda i: (_gap_after(words, i), -abs(words[i]["end"] - end)))


def edge_times(words, s, e, duration, max_len):
    """Clip start/end in seconds for words s..e, with a little quiet before and after
    (never reaching into the neighbouring words)."""
    lead = words[s]["start"] - (words[s - 1]["end"] if s else 0.0)
    start = max(0.0, words[s]["start"] - min(LEAD, max(0.0, lead - 0.05)))
    gap = _gap_after(words, e) if e + 1 < len(words) else TAIL
    end = min(duration, words[e]["end"] + min(TAIL, max(0.0, gap - 0.05)), start + max_len)
    return round(start, 2), round(end, 2)


def make_clips(video, clips, duration, progress=print,
               min_len=config.MIN_CLIP_SECONDS, max_len=config.MAX_CLIP_SECONDS):
    """Cut every clip, add captions and face tracking, and write output/clip_N.mp4."""
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    for old in config.OUTPUT_DIR.glob("clip_*.mp4"):   # clips from the last run (they'd be overwritten
        try:                                            # anyway; extra ones would only confuse)
            old.unlink()
        except OSError:                                 # open in a video player: leave it
            pass
    model = load_whisper()                      # load the speech model once for all clips
    # 1. Whisper listens a bit beyond each clip, so the edges can move to whole sentences.
    windows = []
    clips = sorted(clips, key=lambda c: c["start"])
    for i, c in enumerate(clips, 1):
        progress(f"Clip {i}: listening for sentences and exact word timing...")
        # Neighbouring clips must not grow into each other.
        prev_end = clips[i - 2]["end"] if i > 1 else 0.0
        next_start = clips[i]["start"] if i < len(clips) else duration
        win_start = max(0.0, prev_end, c["start"] - START_SEARCH - 1)
        win_end = min(duration, next_start, max(c["end"], c["start"] + min_len) + END_SEARCH)
        windows.append((listen(video, model, win_start, win_end, duration), c["start"], c["end"]))
    # 2. Gemini picks the first and last word of each clip by meaning (one request for all clips).
    #    Where it can't, Whisper's punctuation and pauses decide.
    picks = fix_edges(windows, min_len, max_len, progress)
    outputs = []
    for i, ((words, ai_start, ai_end), pick) in enumerate(zip(windows, picks), 1):
        if not words:
            start, end = ai_start, ai_end
        else:
            start, end = edge_times(words, *(pick or sentence_edges(words, ai_start, ai_end, min_len, max_len)),
                                    duration, max_len)
        progress(f"Clip {i}: cutting {start:.1f}s - {end:.1f}s (AI picked {ai_start:.1f}s - {ai_end:.1f}s, "
                 f"edges by {'Gemini' if pick else 'Whisper'})...")
        raw = cut(video, start, end, config.TEMP_DIR / f"clip_{i}_raw.mp4")
        ass = config.TEMP_DIR / f"clip_{i}.ass"
        captions_for(words, start, end, ass)
        progress(f"Clip {i}: making it vertical with face tracking and captions...")
        out = config.OUTPUT_DIR / f"clip_{i}.mp4"
        track_crop(raw, out, vf=f"ass={ass.name}", progress=progress)
        outputs.append(out)
    return outputs


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.cutter <youtube link>   (needs GEMINI_API_KEY)
    from .clipper import pick_clips
    from .downloader import download
    r = download(sys.argv[1])
    clips = pick_clips(r["segments"], r["duration"], r["title"])
    for p in make_clips(r["video_path"], clips, r["duration"]):
        print("Wrote", p)
