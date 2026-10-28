# Step 3: transcript -> 3 best clips, picked by Gemini (free tier).
# Manual fallback: save the transcript to a file and type the clip times by hand.
import json
import os
import re
import sys
import time

from . import config
from .downloader import transcript_text


# When Gemini is busy: (model, seconds to wait first). Tries the backup model right away, then both again.
BUSY_TRIES = ((config.GEMINI_MODEL, 0), (config.GEMINI_BACKUP_MODEL, 0),
              (config.GEMINI_MODEL, 5), (config.GEMINI_BACKUP_MODEL, 10))


class ClipError(Exception):
    """Gemini could not give usable clips (no key, rate limit, bad answer...)."""


PROMPT = """You are an expert short-form video editor (TikTok, YouTube Shorts, Reels).
Below is the transcript of a YouTube video titled "{title}" ({duration:.0f} seconds long).
Each line is [start-end seconds] text.

Pick the {n} best clips for vertical short videos. Each clip must:
- be self-contained: it makes sense on its own, starts at the beginning of a sentence
  and ends at the end of a thought (no cut-off sentences)
- have a strong hook in the first few seconds
- be between {min_s:.0f} and {max_s:.0f} seconds long. Prefer LONGER clips, close to {max_s:.0f}
  seconds, as long as the clip stays interesting and complete
- not overlap with the other clips
- lie within 0 and {duration:.1f} seconds

Use the timestamps from the transcript for start and end.
Answer with JSON only: a list of {n} objects with "start" (seconds, number),
"end" (seconds, number) and "reason" (one short sentence).

TRANSCRIPT:
{transcript}
"""


def _ask(prompt, temperature, progress=print, timeout=120, thinking=None, tries=BUSY_TRIES):
    """One Gemini request (JSON answer), at most `timeout` seconds per try. If Gemini is busy
    or too slow (common on the free tier), try the backup model and wait a little between tries."""
    from google import genai
    from google.genai import types
    client = genai.Client(http_options=types.HttpOptions(timeout=timeout * 1000))
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json", temperature=temperature,
        thinking_config=types.ThinkingConfig(thinking_level=thinking) if thinking else None)
    for n, (model, wait) in enumerate(tries):
        if n:
            progress(f"Gemini is busy, trying {model}" + (f" in {wait} seconds..." if wait else "..."))
            time.sleep(wait)
        try:
            return client.models.generate_content(model=model, contents=prompt, config=cfg).text
        except Exception as e:
            # Busy, too slow, or this model's free limit is used up (each model has its own limit).
            busy = any(k in str(e) for k in ("503", "UNAVAILABLE", "504", "DEADLINE", "timed out", "Timeout",
                                             "429", "RESOURCE_EXHAUSTED"))
            if n + 1 == len(tries) or not busy:
                raise


def validate(clips, duration, n=None, min_len=config.MIN_CLIP_SECONDS, max_len=config.MAX_CLIP_SECONDS):
    """Return a list of problems (empty list = clips are OK).
    n: exact number of clips wanted (None = any number from 1 to MAX_CLIPS)."""
    if not isinstance(clips, list):
        return ["answer is not a list"]
    problems, spans = [], []
    if n is not None and len(clips) != n:
        problems.append(f"expected {n} clips, got {len(clips)}")
    if n is None and not 1 <= len(clips) <= config.MAX_CLIPS:
        problems.append(f"type 1 to {config.MAX_CLIPS} clips, one per line (got {len(clips)})")
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
        if e - s > max_len:
            problems.append(f"clip {i}: {e - s:.1f}s is too long (max {max_len:.0f}s)")
        if e - s < min_len:
            problems.append(f"clip {i}: {e - s:.1f}s is too short (min {min_len:.0f}s)")
    spans.sort()
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        if s2 < e1:
            problems.append(f"clips at {s1:.1f}s and {s2:.1f}s overlap")
    return problems


def _clean(clips, duration, max_len=config.MAX_CLIP_SECONDS):
    """Normalize numbers, keep each clip inside the video and under max_len, sort by start time."""
    out = [{"start": round(float(c["start"]), 2),
            "end": round(min(float(c["end"]), duration, float(c["start"]) + max_len), 2),
            "reason": str(c.get("reason", "")).strip()} for c in clips]
    return sorted(out, key=lambda c: c["start"])


def suggest_count(duration, min_len=config.DEFAULT_LENGTH[0]):
    """A sensible number of clips for a video: about one per 4.5 minutes, 1 to MAX_CLIPS,
    and never more than fit into the video."""
    return max(1, min(config.MAX_CLIPS, round(duration / 270), max_fit(duration, min_len)))


def max_fit(duration, min_len):
    """The most clips of at least min_len seconds that can come from the video without overlapping
    (Gemini needs some room to choose, so only 80% of the video is counted)."""
    return int(duration * 0.8 // max(min_len, 1))


def pick_clips(segments, duration, title="video", progress=print, n=3,
               min_len=config.DEFAULT_LENGTH[0], max_len=config.DEFAULT_LENGTH[1]):
    """Ask Gemini for the n best clips, each min_len to max_len seconds. Retries once if the
    answer is invalid. Raises ClipError if Gemini is unavailable or still gives bad clips."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise ClipError("GEMINI_API_KEY is not set.")
    prompt = PROMPT.format(title=title, duration=duration, n=n, min_s=min_len, max_s=max_len,
                           transcript=transcript_text(segments))

    problems = []
    for attempt in (1, 2):
        progress(f"Asking Gemini to pick {n} clip{'s' if n != 1 else ''} (attempt {attempt})...")
        try:
            clips = json.loads(_ask(prompt, 0.4, progress))
        except json.JSONDecodeError:
            problems = ["answer was not valid JSON"]
        except Exception as e:  # network error, rate limit, bad key...
            raise ClipError(f"Gemini is unavailable: {e}") from e
        else:
            # A few seconds off is fine: the next step moves the edges to whole sentences
            # (and a clip that is too long is shortened there).
            problems = validate(clips, duration, n, min_len - 5, max_len + 15)
            if not problems:
                return _clean(clips, duration, max_len)
        # Second attempt: tell Gemini exactly what was wrong.
        prompt += "\n\nYour previous answer was invalid: " + "; ".join(problems) + ". Fix it."
    raise ClipError("Gemini gave invalid clips twice: " + "; ".join(problems))


# ---------- Clean edges: whole sentences only ----------

EDGES_PROMPT = """You are a video editor. These clips were cut from a talk, but their edges may cut a
sentence in half. The words come from speech recognition, so punctuation is NOT reliable:
judge sentences by their meaning. Words are numbered; every 10th word also shows its time
in seconds. The suggested clip starts at the word after <<START>> and ends at the word before <<END>>.

For each clip choose:
- "start_word": the number of the first word of a sentence, as close as possible to the suggested start.
- "end_word": the number of the LAST word of a complete sentence, so the speaker has finished
  the thought. Never end in the middle of a sentence. Stay close to the suggested end; if the
  sentence is still going at the suggested end, end a little later rather than cutting it short.
Each clip must stay between {min_s:.0f} and {max_s:.0f} seconds long.

Answer with JSON only: a list with one object per clip, in order:
[{{"clip": 1, "start_word": 12, "end_word": 140}}, ...]

{clips}
"""


def _numbered(words, start, end):
    """Words as '12:word', with the time on every 10th word and markers at the AI's edges."""
    out, marked_start, marked_end = [], False, False
    for i, w in enumerate(words):
        if not marked_start and w["start"] >= start - 0.15:
            out.append("<<START>>")
            marked_start = True
        if not marked_end and w["start"] >= end - 0.15:
            out.append("<<END>>")
            marked_end = True
        out.append(f"{i}:{w['word']}" + (f"({w['start']:.1f}s)" if i % 10 == 0 else ""))
    if not marked_end:
        out.append("<<END>>")
    return " ".join(out)


def fix_edges(windows, min_len, max_len, progress=print):
    """Ask Gemini where each clip should start and end so it holds whole sentences.
    windows: [(words, ai_start, ai_end)] where words are Whisper words around each clip.
    Returns [(start_word, end_word) or None] per clip; None = no good answer for that clip
    (the caller then uses its own rules). Never raises: this step only improves the edges."""
    if not os.environ.get("GEMINI_API_KEY"):
        return [None] * len(windows)
    try:
        progress("Asking Gemini to end each clip at the end of a sentence...")
        text = "\n\n".join(f"CLIP {n}:\n{_numbered(w, s, e)}" for n, (w, s, e) in enumerate(windows, 1))
        reply = _ask(EDGES_PROMPT.format(min_s=min_len, max_s=max_len, clips=text), 0.2, progress,
                     timeout=45, thinking="low", tries=BUSY_TRIES[:2])   # optional step: don't wait long
        answer = {int(a["clip"]): (int(a["start_word"]), int(a["end_word"])) for a in json.loads(reply)}
    except Exception as e:  # rate limit, no internet, odd answer: fall back to the rules
        progress(f"Gemini could not check the clip edges ({str(e)[:80]}), using Whisper's sentence marks.")
        return [None] * len(windows)
    result = []
    for n, (words, _, _) in enumerate(windows, 1):
        s, e = answer.get(n, (-1, -1))
        ok = 0 <= s < e < len(words) and min_len - 1 <= words[e]["end"] - words[s]["start"] <= max_len - 0.5
        result.append((s, e) if ok else None)
    return result


# ---------- Manual fallback ----------

def save_transcript(segments, path):
    """Write the timed transcript to a text file the user can read."""
    path.write_text(transcript_text(segments), encoding="utf-8")
    return path


def _to_seconds(t):
    """'75', '75.5', '1:15', '01:15.5' or '0:01:15' -> seconds."""
    parts = t.strip().split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def parse_manual(text, duration, min_len=config.MIN_CLIP_SECONDS, max_len=config.MAX_CLIP_SECONDS):
    """Read clips typed by hand, one per line, like '12.5 - 58' or '1:05 - 1:50'
    (1 to MAX_CLIPS lines, each min_len to max_len seconds). Returns (clips, problems)."""
    clips = []
    for line in text.strip().splitlines():
        m = re.match(r"^\s*([\d:.]+)\s*(?:-|to|,)\s*([\d:.]+)\s*$", line)
        if not line.strip():
            continue
        if not m:
            return [], [f"could not read line: '{line.strip()}' (use start - end, e.g. 1:05 - 1:50)"]
        clips.append({"start": _to_seconds(m[1]), "end": _to_seconds(m[2]), "reason": "manual"})
    problems = validate(clips, duration, None, min_len, max_len)
    return (_clean(clips, duration, max_len) if not problems else []), problems


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.clipper <youtube link>
    from .downloader import download
    r = download(sys.argv[1])
    for i, c in enumerate(pick_clips(r["segments"], r["duration"], r["title"]), 1):
        print(f"Clip {i}: {c['start']:.1f}s - {c['end']:.1f}s ({c['end'] - c['start']:.1f}s)  {c['reason']}")
