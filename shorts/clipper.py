# Step 3: transcript -> 3 best clips, picked by Gemini (free tier).
# Manual fallback: save the transcript to a file and type the clip times by hand.
import json
import os
import re
import sys

from . import config
from .downloader import transcript_text


class ClipError(Exception):
    """Gemini could not give usable clips (no key, rate limit, bad answer...)."""


PROMPT = """You are an expert short-form video editor (TikTok, YouTube Shorts, Reels).
Below is the transcript of a YouTube video titled "{title}" ({duration:.0f} seconds long).
Each line is [start-end seconds] text.

Pick the {n} best clips for vertical short videos. Each clip must:
- be self-contained: it makes sense on its own, starts at the beginning of a sentence
  and ends at the end of a thought (no cut-off sentences)
- have a strong hook in the first few seconds
- be between {min_s:.0f} and {max_s:.0f} seconds long
- not overlap with the other clips
- lie within 0 and {duration:.1f} seconds

Use the timestamps from the transcript for start and end.
Answer with JSON only: a list of {n} objects with "start" (seconds, number),
"end" (seconds, number) and "reason" (one short sentence).

TRANSCRIPT:
{transcript}
"""


def validate(clips, duration):
    """Return a list of problems (empty list = clips are OK)."""
    if not isinstance(clips, list):
        return ["answer is not a list"]
    problems, spans = [], []
    if len(clips) != config.NUM_CLIPS:
        problems.append(f"expected {config.NUM_CLIPS} clips, got {len(clips)}")
    for i, c in enumerate(clips, 1):
        try:
            s, e = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"clip {i}: missing or invalid start/end")
            continue
        spans.append((s, e))
        if not s < e:
            problems.append(f"clip {i}: start must be before end")
            continue
        if s < 0 or e > duration + 0.5:
            problems.append(f"clip {i}: outside the video (0 to {duration:.1f}s)")
        if e - s > config.MAX_CLIP_SECONDS:
            problems.append(f"clip {i}: {e - s:.1f}s is too long (max {config.MAX_CLIP_SECONDS:.0f}s)")
        if e - s < config.MIN_CLIP_SECONDS:
            problems.append(f"clip {i}: {e - s:.1f}s is too short (min {config.MIN_CLIP_SECONDS:.0f}s)")
    spans.sort()
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        if s2 < e1:
            problems.append(f"clips at {s1:.1f}s and {s2:.1f}s overlap")
    return problems


def _clean(clips, duration):
    """Normalize numbers, clamp the end to the video length, sort by start time."""
    out = [{"start": round(float(c["start"]), 2),
            "end": round(min(float(c["end"]), duration), 2),
            "reason": str(c.get("reason", "")).strip()} for c in clips]
    return sorted(out, key=lambda c: c["start"])


def pick_clips(segments, duration, title="video", progress=print):
    """Ask Gemini for the best clips. Retries once if the answer is invalid.
    Raises ClipError if Gemini is unavailable or still gives bad clips."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise ClipError("GEMINI_API_KEY is not set.")
    from google import genai
    from google.genai import types

    client = genai.Client()
    prompt = PROMPT.format(title=title, duration=duration, n=config.NUM_CLIPS,
                           min_s=config.MIN_CLIP_SECONDS, max_s=config.MAX_CLIP_SECONDS,
                           transcript=transcript_text(segments))
    gen_cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4)

    problems = []
    for attempt in (1, 2):
        progress(f"Asking Gemini to pick clips (attempt {attempt})...")
        try:
            resp = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt, config=gen_cfg)
            clips = json.loads(resp.text)
        except json.JSONDecodeError:
            problems = ["answer was not valid JSON"]
        except Exception as e:  # network error, rate limit, bad key...
            raise ClipError(f"Gemini is unavailable: {e}") from e
        else:
            problems = validate(clips, duration)
            if not problems:
                return _clean(clips, duration)
        # Second attempt: tell Gemini exactly what was wrong.
        prompt += "\n\nYour previous answer was invalid: " + "; ".join(problems) + ". Fix it."
    raise ClipError("Gemini gave invalid clips twice: " + "; ".join(problems))


# ---------- Manual fallback ----------

def save_transcript(segments, path):
    """Write the timed transcript to a text file the user can read."""
    path.write_text(transcript_text(segments), encoding="utf-8")
    return path


def _to_seconds(t):
    """'75', '75.5', '1:15', '01:15.5' or '0:01:15' -> seconds."""
    parts = t.strip().split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def parse_manual(text, duration):
    """Read clips typed by hand, one per line, like '12.5 - 58' or '1:05 - 1:50'.
    Returns (clips, problems)."""
    clips = []
    for line in text.strip().splitlines():
        m = re.match(r"^\s*([\d:.]+)\s*(?:-|to|,)\s*([\d:.]+)\s*$", line)
        if not line.strip():
            continue
        if not m:
            return [], [f"could not read line: '{line.strip()}' (use start - end, e.g. 1:05 - 1:50)"]
        clips.append({"start": _to_seconds(m[1]), "end": _to_seconds(m[2]), "reason": "manual"})
    problems = validate(clips, duration)
    return (_clean(clips, duration) if not problems else []), problems


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.clipper <youtube link>
    from .downloader import download
    r = download(sys.argv[1])
    for i, c in enumerate(pick_clips(r["segments"], r["duration"], r["title"]), 1):
        print(f"Clip {i}: {c['start']:.1f}s - {c['end']:.1f}s ({c['end'] - c['start']:.1f}s)  {c['reason']}")
