# Shared settings. Everything heavy lives inside this project folder (E: drive), not on C:.
# Import this module FIRST in every file (before numpy/cv2), so the limits below take effect.
import os
from pathlib import Path

# Low memory: numpy's math library reserves ~30 MB per CPU core (~470 MB on this 16-core PC)
# that we never use. The PC's memory is nearly full, and extra use grows Windows' page file on C:.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
# Whisper's engine (CTranslate2) with Intel MKL reserves ~1 GB to load the small "base" model.
# Without MKL: ~0.4 GB peak, same speed.
os.environ.setdefault("CT2_USE_MKL", "0")

ROOT = Path(__file__).resolve().parent.parent   # the project folder (this file is in shorts/)
# All scratch files (downloads, cut pieces, caches, test scripts) go to a separate folder on E:.
# The user's C: drive is almost full: nothing from this program may be stored on C:.
TEMP_DIR = Path(r"E:\Personal Work\Programming\Shorts Temp")
OUTPUT_DIR = ROOT / "output"
MODELS_DIR = ROOT / "models"

# Keep all temporary files of this program (and ffmpeg/yt-dlp) on E:, never in C:\...\Temp.
TEMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = os.environ["TEMP"] = str(TEMP_DIR)
import tempfile
tempfile.tempdir = str(TEMP_DIR)

# Tool caches (Hugging Face / Whisper downloads, yt-dlp, pip) also go here instead of C:\Users\...\.cache.
CACHE_DIR = TEMP_DIR / "cache"
os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)
os.environ["PIP_CACHE_DIR"] = str(CACHE_DIR / "pip")

# Caption fonts: ffmpeg's font finder (fontconfig) would otherwise write its cache to C:.
# Our own small config reads Windows' fonts and keeps the cache in the scratch folder.
_fc = CACHE_DIR / "fonts.conf"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
_fc.write_text(f"""<?xml version="1.0"?>
<fontconfig>
  <dir>C:/Windows/Fonts</dir>
  <cachedir>{(CACHE_DIR / "fontconfig").as_posix()}</cachedir>
</fontconfig>
""", encoding="utf-8")
os.environ["FONTCONFIG_FILE"] = str(_fc)

# ffmpeg lives in tools/ffmpeg; put it on PATH for this program only.
FFMPEG_DIR = ROOT / "tools" / "ffmpeg"
os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")

# Whisper models download into models/whisper instead of C:\Users\...\.cache.
WHISPER_DIR = MODELS_DIR / "whisper"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
WHISPER_MODEL = "base"
# OpenCV YuNet face detector (MediaPipe's model missed small faces on wide shots).
FACE_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"

# Gemini model for picking clips (free tier). Key is read from the GEMINI_API_KEY environment variable.
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_BACKUP_MODEL = "gemini-3.7-flash"   # also free; used when the main model is busy
# Clip count and length are chosen on the page; these are the limits and defaults.
MAX_CLIPS = 10
MIN_CLIP_SECONDS = 15.0       # shortest clip the length slider allows
MAX_CLIP_SECONDS = 90.0       # longest clip (the user approved 90 s; Shorts and Reels allow it)
DEFAULT_LENGTH = (60, 90)     # the length slider starts here: the user wants long clips
