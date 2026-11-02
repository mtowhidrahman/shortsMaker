# Step 6: word-level captions. Whisper listens to one clip, we group the words into
# short chunks, and write an .ass subtitle file that ffmpeg burns into the video.
from . import config  # first: sets memory limits and cache folders

import re
import sys

from .downloader import load_audio, load_whisper

MAX_WORDS = 3            # words shown at the same time
MAX_CHUNK_SECONDS = 1.6  # a chunk never stays longer than this
PAUSE_BREAK = 0.45       # a pause this long starts a new chunk
# A well-punctuated example makes Whisper put full stops more reliably (used to find sentence ends).
PUNCTUATION_HINT = "Hello, and welcome. Today I want to talk about something important. It matters, and here is why."

# Big bold white text, thick black outline + soft shadow, bottom-center (2), raised above the
# area where phone apps put their buttons. Sizes are for the 1080x1920 output.
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{cap_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,70,70,330,1
Style: Watermark,Arial,54,&H40FFFFFF,&H40FFFFFF,&H60000000,&H80000000,-1,0,0,0,100,100,1,0,1,3,1,{wm_align},50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Caption looks the page offers. Colours are ASS colours (blue-green-red order).
CAPTION_SIZES = {"Small": 78, "Medium": 92, "Large": 108}
HIGHLIGHTS = {"Yellow": "&H00FFFF&", "Green": "&H00FF00&", "None": None}
DEFAULT_CAPTION = {"size": "Medium", "highlight": "Yellow"}


def transcribe_words(path, model=None, start=0.0, end=None):
    """Exact start/end time of every spoken word between start and end seconds of the file
    (the whole file by default), with punctuation: [{"word", "start", "end"}] in file time."""
    model = model or load_whisper()
    segments, _ = model.transcribe(load_audio(path, start or None, end), language="en",
                                   word_timestamps=True, vad_filter=True,
                                   condition_on_previous_text=False, initial_prompt=PUNCTUATION_HINT)
    return [{"word": w.word.strip(), "start": w.start + start, "end": w.end + start}
            for s in segments for w in s.words if w.word.strip()]


def group_words(words):
    """Split words into short chunks (a few words), breaking at punctuation and pauses."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= MAX_WORDS
                    or w["start"] - cur[-1]["end"] > PAUSE_BREAK
                    or w["end"] - cur[0]["start"] > MAX_CHUNK_SECONDS):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.,!?;:]$", w["word"]):       # end of a phrase: close the chunk
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def _ts(t):
    """Seconds -> ASS time format h:mm:ss.cc"""
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(word):
    """Text as shown on screen: no trailing commas/full stops, no ASS control characters."""
    word = re.sub(r"[.,;:]+$", "", word)
    return word.replace("{", "(").replace("}", ")").replace("\\", "/")


def write_ass(words, path, watermark="", corner="right", length=0.0, caption=None):
    """Write the subtitle file. Each chunk stays on screen until the next one starts
    (if the gap is short), so the captions don't flicker.
    caption: {"size": Small/Medium/Large, "highlight": Yellow/Green/None}. With a highlight colour,
    the word being spoken lights up (one line per word, the chunk itself stays the same).
    watermark: optional text shown the whole time (length seconds) in the bottom-left or
    bottom-right corner, close to the bottom edge, smaller and a little see-through."""
    caption = {**DEFAULT_CAPTION, **(caption or {})}
    colour = HIGHLIGHTS.get(caption["highlight"])
    chunks = group_words(words)
    lines = []
    for i, c in enumerate(chunks):
        start, end = c[0]["start"], c[-1]["end"]
        if i + 1 < len(chunks):
            nxt = chunks[i + 1][0]["start"]
            if nxt - end < 0.6:
                end = nxt
        end = max(end, start + 0.25)
        shown = [_clean(w["word"]).upper() for w in c]
        if not colour:
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{' '.join(shown)}")
            continue
        for k in range(len(c)):                     # word k lit from its start until the next word starts
            w_start = start if k == 0 else c[k]["start"]
            w_end = end if k + 1 == len(c) else c[k + 1]["start"]
            text = " ".join(f"{{\\c{colour}}}{s}{{\\r}}" if j == k else s for j, s in enumerate(shown))
            lines.append(f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},Caption,,0,0,0,,{text}")
    if watermark.strip():
        end = max(length, max((w["end"] for w in words), default=0.0)) + 1
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end)},Watermark,,0,0,0,,{_clean(watermark.strip())}")
    header = (ASS_HEADER.replace("{wm_align}", "1" if corner == "left" else "3")   # 1/3 = bottom left/right
              .replace("{cap_size}", str(CAPTION_SIZES.get(caption["size"], CAPTION_SIZES["Medium"]))))
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_captions(clip_path, ass_path, model=None):
    """Clip -> .ass subtitle file. Returns the number of words found."""
    words = transcribe_words(clip_path, model)
    write_ass(words, ass_path)
    return len(words)


def captions_for(words, start, end, ass_path, watermark="", corner="right", caption=None):
    """Captions (and the optional watermark) for the part [start, end] of the video, from words
    already transcribed (times in video seconds). Times in the .ass file start at the clip start."""
    inside = [dict(w, start=w["start"] - start, end=min(w["end"], end) - start)
              for w in words if w["start"] >= start - 0.05 and w["start"] < end]
    write_ass(inside, ass_path, watermark, corner, end - start, caption)
    return len(inside)


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.captions <clip.mp4>   -> writes <clip>.ass next to it
    from pathlib import Path
    src = Path(sys.argv[1])
    n = make_captions(src, src.with_suffix(".ass"))
    print(f"{n} words -> {src.with_suffix('.ass')}")
