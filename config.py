# Shared settings. Everything heavy lives inside this project folder (E: drive), not on C:.
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "output"
MODELS_DIR = ROOT / "models"

# ffmpeg lives in tools/ffmpeg; put it on PATH for this program only.
FFMPEG_DIR = ROOT / "tools" / "ffmpeg"
os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")

# Whisper models download into models/whisper instead of C:\Users\...\.cache.
WHISPER_DIR = MODELS_DIR / "whisper"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
WHISPER_MODEL = "base"
FACE_MODEL = MODELS_DIR / "blaze_face_short_range.tflite"
