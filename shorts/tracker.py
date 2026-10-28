# Step 5: vertical 9:16 crop that follows the speaker's face, smoothly.
# Pass 1: find the face (OpenCV YuNet) in every few frames -> list of face positions.
# Plan:   fill gaps, smooth the positions into calm "camera moves".
# Pass 2: crop each frame around the planned position, scale to 1080x1920, add the audio.
# Frames are streamed one at a time through ffmpeg pipes, so memory use stays small.
from . import config  # first: sets memory limits before numpy/cv2 load

import json
import subprocess
import sys

import cv2
import numpy as np

from .report import console

OUT_W, OUT_H = 1080, 1920
DETECT_EVERY = 3          # run the face detector on every 3rd frame
DETECT_WIDTH = 640        # the detector looks at frames shrunk to this width: 4x faster than full
                          # size, and the camera path stays within 1% (measured on 3 clips)
SMOOTH_SECONDS = 0.6      # how gently the "camera" follows the face (bigger = calmer)
DEAD_ZONE = 0.12          # ignore face movement smaller than this part of the crop width
SCENE_CUT = 18            # average pixel change (0-255) that counts as a cut to another camera
                          # (measured: real cuts 22-37, normal movement under 11)

# Low memory: the PC's memory is nearly full from other apps, and extra use makes Windows grow
# its page file on C:. Fewer threads and a short encoder look-ahead keep ffmpeg small.
cv2.setNumThreads(8)      # 8 of the 16 CPU threads: face finding 2x faster, same memory
DECODE_ARGS = ["-threads", "2"]
ENCODE_ARGS = ["-threads", "4", "-x264-params", "rc-lookahead=10"]


def probe(path):
    """Width, height, frame rate, start time and length (seconds) of the first video stream."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,start_time:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return (int(s["width"]), int(s["height"]), s["r_frame_rate"], float(num) / float(den),
            float(s.get("start_time") or 0), float(j.get("format", {}).get("duration") or 0))


def read_frames(path, w, h):
    """Yield video frames (BGR numpy arrays) one by one, decoded by ffmpeg."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", *DECODE_ARGS, "-i", str(path), "-f", "rawvideo",
                          "-fps_mode", "passthrough", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.kill()            # stops ffmpeg quietly if we stop reading early
        p.stdout.close()
        p.wait()


def find_faces(path, w, h, detect_w=None, every=None, report=None):
    """Pass 1: x-center of the speaker's face per frame (NaN where unknown),
    and the frames where the video cuts to another camera angle.
    The detector looks at frames shrunk to detect_w pixels wide (faster), every few frames.
    report(i): called every 15 frames with the frame number (for a progress bar)."""
    detect_w, every = min(w, detect_w or DETECT_WIDTH), every or DETECT_EVERY
    dw, dh = detect_w, int(round(h * detect_w / w / 2)) * 2
    back = np.array([w / dw, h / dh, w / dw, h / dh, 1])       # detector size -> frame size
    det = cv2.FaceDetectorYN.create(str(config.FACE_MODEL), "", (dw, dh), 0.6)
    found, cuts, last_small, n = {}, [], None, 0
    for i, frame in enumerate(read_frames(path, w, h)):
        n = i + 1
        if report and i % 15 == 0:
            report(i)
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36)).astype(np.int16)
        if last_small is not None and np.abs(small - last_small).mean() > SCENE_CUT:
            cuts.append(i)
        last_small = small
        if i % every == 0 or (cuts and cuts[-1] == i):
            img = frame if dw == w else cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_AREA)
            _, faces = det.detect(img)
            if faces is not None and len(faces):
                found[i] = faces[:, [0, 1, 2, 3, 14]] * back   # x, y, width, height, confidence
    xs = np.full(n, np.nan)
    bounds = [0] + cuts + [n]
    for a, b in zip(bounds, bounds[1:]):                 # choose the speaker separately per shot
        for i, x in _speaker_track({i: f for i, f in found.items() if a <= i < b}, w, h).items():
            xs[i] = x
    return xs, cuts


def _speaker_track(found, w, h):
    """Link face detections over time into tracks (same person = close position from frame
    to frame), then return the positions of the track most likely to be the speaker:
    on screen most often, big, confident, and in the upper part of the frame
    (audience heads are usually low in the frame)."""
    tracks = []                                          # each: {"last": x, "frame": i, "pts": {}, "score": 0}
    for i in sorted(found):
        for x, y, fw, fh, conf in found[i]:
            cx, cy = x + fw / 2, y + fh / 2
            near = [t for t in tracks if i - t["frame"] <= 12 and abs(t["last"] - cx) < 0.08 * w
                    and i not in t["pts"]]
            t = min(near, key=lambda t: abs(t["last"] - cx)) if near else None
            if t is None:
                t = {"last": cx, "frame": i, "pts": {}, "score": 0.0}
                tracks.append(t)
            t["last"], t["frame"] = cx, i
            t["pts"][i] = cx
            t["score"] += fw * fh * conf ** 2 * (1.0 if cy < 0.5 * h else 0.3)
    return max(tracks, key=lambda t: t["score"])["pts"] if tracks else {}


def plan_camera(xs, cuts, w, crop_w, fps):
    """Smooth crop center for every frame. Each camera shot is planned on its own,
    so at a cut the crop jumps straight to the new position instead of sliding."""
    bounds = [0] + list(cuts) + [len(xs)]
    return np.concatenate([_plan_shot(xs[a:b], w, crop_w, fps)
                           for a, b in zip(bounds, bounds[1:]) if b > a])


def _plan_shot(xs, w, crop_w, fps):
    n = len(xs)
    known = ~np.isnan(xs)
    if not known.any():
        return np.full(n, w / 2)                       # no face in this shot: center crop
    idx = np.arange(n)
    x = np.interp(idx, idx[known], xs[known])          # fill gaps (holds the edge values)

    # Remove single wrong detections, then smooth (forward + backward, so there is no lag).
    k = max(3, int(fps * 0.4) | 1)
    pad = np.pad(x, k // 2, mode="edge")
    x = np.array([np.median(pad[i:i + k]) for i in range(n)])

    # Dead zone: the camera only moves when the face leaves the middle area of the crop.
    cam, dz = np.empty(n), DEAD_ZONE * crop_w
    cam[0] = x[0]
    for i in range(1, n):
        diff = x[i] - cam[i - 1]
        cam[i] = cam[i - 1] + (diff - np.sign(diff) * dz if abs(diff) > dz else 0)

    a = 1 / (1 + SMOOTH_SECONDS * fps / 3)
    for order in (range(1, n), range(n - 2, -1, -1)):   # exponential smoothing both ways
        for i in order:
            j = i - 1 if order.step == 1 else i + 1
            cam[i] = cam[j] + a * (cam[i] - cam[j])

    half = crop_w / 2
    return np.clip(cam, half, w - half)                 # keep the crop inside the frame


def track_crop(src, out, vf=None, progress=console, name=""):
    """Make a 1080x1920 face-tracked version of src (with its audio).
    vf: optional extra ffmpeg filter (Step 6 uses it to burn in captions).
    name: added to the progress step names ("faces 2", "render 2")."""
    w, h, rate, fps, v_start, length = probe(src)
    frames = max(1, int(length * fps))
    crop_w = int(h * 9 / 16) // 2 * 2
    crop_h = h
    if crop_w > w:                                       # very narrow video: crop height instead
        crop_w, crop_h = w // 2 * 2, int(w * 16 / 9) // 2 * 2

    step = f"faces {name}".strip()
    progress("  finding the face...", step=step)
    xs, cuts = find_faces(src, w, h, report=lambda i: progress("  finding the face...", min(1, i / frames), step))
    found = np.mean(~np.isnan(xs[::DETECT_EVERY])) if len(xs) else 0.0
    cam = plan_camera(xs, cuts, w, crop_w, fps)

    step = f"render {name}".strip()
    progress("  cropping and encoding...", step=step)
    # -itsoffset keeps the picture at the same time as in the source, so the sound stays in sync.
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{OUT_W}x{OUT_H}", "-r", rate, "-itsoffset", f"{v_start:.6f}", "-i", "-", "-i", str(src),
           "-map", "0:v", "-map", "1:a?"]
    if vf:
        cmd += ["-vf", vf]
    # "veryfast": 2.6x faster than "medium", picture 99.4% the same (SSIM), file slightly smaller.
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", *ENCODE_ARGS, "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", str(out)]
    # Run inside TEMP_DIR so filters can name files there without Windows path escaping (ass=clip_1.ass).
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, cwd=config.TEMP_DIR)
    y0 = (h - crop_h) // 2
    try:
        for i, frame in enumerate(read_frames(src, w, h)):
            x0 = int(round(cam[min(i, len(cam) - 1)] - crop_w / 2))
            x0 = max(0, min(w - crop_w, x0))
            crop = frame[y0:y0 + crop_h, x0:x0 + crop_w]
            if i % 15 == 0:
                progress("  cropping and encoding...", min(1, i / len(cam)), step)
            enc.stdin.write(cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_CUBIC).tobytes())
        enc.stdin.close()
    except BrokenPipeError:
        pass
    err = enc.stderr.read().decode(errors="replace")
    if enc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while encoding:\n{err[-1500:]}")
    return {"face_found": found, "camera": cam, "faces": xs, "cuts": cuts, "crop_w": crop_w}


if __name__ == "__main__":
    # Quick test (from the project folder): .venv\Scripts\python.exe -m shorts.tracker <raw clip> <output.mp4>
    r = track_crop(sys.argv[1], sys.argv[2])
    print(f"Face found in {r['face_found']:.0%} of checked frames -> {sys.argv[2]}")
