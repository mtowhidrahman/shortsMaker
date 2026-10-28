# Step 6: word-level captions. Whisper listens to one clip, we group the words into
# short chunks, and write an .ass subtitle file that ffmpeg burns into the video.
from . import config  # first: sets memory limits and cache folders

import re
import sys

from .downloader import load_audio, load_whisper

MAX_WORDS = 3            # words shown at the same time
MAX_CHUNK_SECONDS = 1.6  # a chunk never stays longer than this
PAUSE_BREAK = 0.45       # a pause this long starts a new chunk

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
Style: Caption,Arial,112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,9,4,2,70,70,460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def transcribe_words(clip_path, model=None):
    """Exact start/end time of every spoken word in the clip: [{"word", "start", "end"}]."""
    model = model or load_whisper()
    segments, _ = model.transcribe(load_audio(clip_path), language="en", word_timestamps=True,
                                   vad_filter=True, condition_on_previous_text=False)
    return [{"word": w.word.strip(), "start": w.start, "end": w.end}
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


def write_ass(words, path):
    """Write the subtitle file. Each chunk stays on screen until the next one starts
    (if the gap is short), so the captions don't flicker."""
    chunks = group_words(words)
    lines = []
    for i, c in enumerate(chunks):
        start, end = c[0]["start"], c[-1]["end"]
        if i + 1 < len(chunks):
            nxt = chunks[i + 1][0]["start"]
            if nxt - end < 0.6:
                end = nxt
        end = max(end, start + 0.25)
        text = " ".join(_clean(w["word"]) for w in c).upper()
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{text}")
    path.write_text(ASS_HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_captions(clip_path, ass_path, model=None):
    """Clip -> .ass subtitle file. Returns the number of words found."""
    words = transcribe_words(clip_path, model)
    write_ass(words, ass_path)
    return len(words)


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.captions <clip.mp4>   -> writes <clip>.ass next to it
    from pathlib import Path
    src = Path(sys.argv[1])
    n = make_captions(src, src.with_suffix(".ass"))
    print(f"{n} words -> {src.with_suffix('.ass')}")
