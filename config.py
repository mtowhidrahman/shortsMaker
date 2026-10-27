# Shared settings. Everything heavy lives inside this project folder (E: drive), not on C:.
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "output"
MODELS_DIR = ROOT / "models"

# Keep all temporary files of this program (and ffmpeg/yt-dlp) on E:, never in C:\...\Temp.
TEMP_DIR.mkdir(exist_ok=True)
os.environ["TMP"] = os.environ["TEMP"] = str(TEMP_DIR)
import tempfile
tempfile.tempdir = str(TEMP_DIR)

# ffmpeg lives in tools/ffmpeg; put it on PATH for this program only.
FFMPEG_DIR = ROOT / "tools" / "ffmpeg"
os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")

# Whisper models download into models/whisper instead of C:\Users\...\.cache.
WHISPER_DIR = MODELS_DIR / "whisper"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
WHISPER_MODEL = "base"
FACE_MODEL = MODELS_DIR / "blaze_face_short_range.tflite"

# Gemini model for picking clips (free tier). Key is read from the GEMINI_API_KEY environment variable.
GEMINI_MODEL = "gemini-3.8-flash"
NUM_CLIPS = 3
MAX_CLIP_SECONDS = 59.0   # "under 60 seconds", with a small safety margin
MIN_CLIP_SECONDS = 15.0
PAD_START = 0.5   # seconds added before each clip so the first word is not cut off
PAD_END = 0.0     # seconds added after each clip (caption end times already run a bit late)
