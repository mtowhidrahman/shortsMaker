# Step 4: cut clips out of the long video and make them vertical (9:16, 1080x1920).
# The center crop here is the simple version; tracker.py replaces it with face tracking.
import subprocess
import sys

import config

OUT_W, OUT_H = 1080, 1920


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


def pad(clip, duration):
    """Caption times are often a little late, so start slightly earlier and end slightly
    later to avoid chopping the first/last word. Never exceed the max clip length."""
    start = max(0.0, clip["start"] - config.PAD_START)
    end = min(duration, clip["end"] + config.PAD_END, start + config.MAX_CLIP_SECONDS + 0.9)
    return start, end


def make_clips(video, clips, duration, progress=print):
    """Cut every clip into temp/ and write vertical versions to output/clip_N.mp4."""
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    outputs = []
    for i, c in enumerate(clips, 1):
        start, end = pad(c, duration)
        progress(f"Clip {i}: cutting {start:.1f}s - {end:.1f}s...")
        raw = cut(video, start, end, config.TEMP_DIR / f"clip_{i}_raw.mp4")
        progress(f"Clip {i}: making it vertical...")
        outputs.append(center_crop(raw, config.OUTPUT_DIR / f"clip_{i}.mp4"))
    return outputs


if __name__ == "__main__":
    # Quick test: python cutter.py <youtube link>   (needs GEMINI_API_KEY)
    from clipper import pick_clips
    from downloader import download
    r = download(sys.argv[1])
    clips = pick_clips(r["segments"], r["duration"], r["title"])
    for p in make_clips(r["video_path"], clips, r["duration"]):
        print("Wrote", p)
