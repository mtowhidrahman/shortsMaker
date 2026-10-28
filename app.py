# The web page. Run with start.bat (or: .\.venv\Scripts\python.exe -m streamlit run app.py)
# Paste a YouTube link, choose how many clips and how long, click one button,
# get vertical shorts with face tracking and captions.
from shorts import config  # first: memory limits, cache folders, ffmpeg path

import shutil

import streamlit as st

from shorts.clipper import ClipError, max_fit, parse_manual, pick_clips, save_transcript, suggest_count
from shorts.cutter import make_clips
from shorts.downloader import download, transcript_text, video_info
from progress_view import Reporter, clip_plan, estimate, fmt

st.set_page_config(page_title="Short Video Maker", page_icon="🎬")
st.title("🎬 Short Video Maker")
st.caption("Paste a YouTube link (English). You get vertical clips with face tracking and captions.")

url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...").strip()

# As soon as a link is pasted: show the video's title and length, and suggest a number of clips.
info = None
if url:
    try:
        if st.session_state.get("info_url") != url:
            with st.spinner("Checking the video..."):
                st.session_state.info = video_info(url)
            st.session_state.info_url = url
        info = st.session_state.info
    except Exception as e:
        st.session_state.pop("info_url", None)
        st.error(str(e))

if info:
    minutes, seconds = divmod(int(info["duration"]), 60)
    st.write(f"**{info['title']}** · {minutes}:{seconds:02d} long")
    lo, hi = st.slider("Clip length (seconds)", int(config.MIN_CLIP_SECONDS), int(config.MAX_CLIP_SECONDS),
                       config.DEFAULT_LENGTH, step=5,
                       help="Each clip will be between these lengths. It always ends at the end of a sentence.")
    most = max(1, min(config.MAX_CLIPS, max_fit(info["duration"], lo)))
    n = st.number_input(f"How many clips (suggested for this video: {suggest_count(info['duration'], lo)})",
                        min_value=1, max_value=most, value=suggest_count(info["duration"], lo),
                        key=f"n_{info['id']}_{lo}",
                        help=f"Up to {most} clips of {lo}+ seconds fit into this video.")
    if max_fit(info["duration"], lo) < 1:
        st.warning(f"This video is too short for clips of {lo}+ seconds. Make the clip length shorter.")
    elif most < config.MAX_CLIPS:
        st.caption(f"This video is long enough for at most {most} clip{'s' if most != 1 else ''} "
                   f"of {lo}+ seconds. Make the clips shorter to get more.")
else:
    lo, hi = config.DEFAULT_LENGTH
    n = 3

go = st.button("Make shorts", type="primary")
if go and not info:
    st.warning("Please paste a YouTube link first." if not url else "Please use a working YouTube link.")
    go = False


def run(clips_from_user=None):
    """Download -> pick clips (Gemini, or the user's times) -> cut, captions, face tracking."""
    # Rough plan for the time estimate; refined once the clips are known.
    cached = (config.TEMP_DIR / f"{info['id']}.mp4").exists()
    lengths = ([c["end"] - c["start"] for c in clips_from_user] if clips_from_user
               else [(lo + hi) / 2] * n)
    plan = ([("download", 1 if cached else estimate("download"))]
            + ([] if clips_from_user else [("pick", estimate("pick"))]) + clip_plan(lengths))
    bars = st.container()
    with st.status("Working... (this takes a few minutes)", expanded=True) as status:
        progress = Reporter(status, bars, plan, info["duration"])
        try:
            video = download(url, progress=progress)
            st.session_state.video = video
            if clips_from_user:
                clips = clips_from_user
            else:
                try:
                    clips = pick_clips(video["segments"], video["duration"], video["title"],
                                       progress=progress, n=n, min_len=lo, max_len=hi)
                except ClipError as e:
                    progress.finish()
                    st.session_state.ai_error = str(e)
                    status.update(label="The AI could not pick clips. You can choose them yourself below.",
                                  state="error")
                    return
            for i, c in enumerate(clips, 1):
                status.write(f"Clip {i}: {c['start']:.1f}s – {c['end']:.1f}s. {c.get('reason', '')}")
            progress.replan(clip_plan([c["end"] - c["start"] for c in clips]))
            st.session_state.outputs = [str(p) for p in
                                        make_clips(video["video_path"], clips, video["duration"],
                                                   progress=progress, min_len=lo, max_len=hi)]
            st.session_state.clips = clips
            st.session_state.pop("ai_error", None)
            total, steps = progress.finish()
            st.session_state.timing = (total, steps)
            k = len(st.session_state.outputs)
            status.update(label=f"Done! Your {k} short{'s are' if k != 1 else ' is'} ready "
                                f"(finished in {fmt(total)}).", state="complete", expanded=False)
            return True
        except Exception as e:  # show a readable message instead of a crash
            progress.finish()
            status.update(label="Something went wrong.", state="error")
            st.error(str(e))


if go:
    for k in ("outputs", "ai_error", "video", "clips", "timing"):
        st.session_state.pop(k, None)
    run()

# ----- Manual fallback: the AI was unavailable, so the user types the clip times -----
if st.session_state.get("ai_error") and st.session_state.get("video"):
    video = st.session_state.video
    st.warning(f"The AI could not pick clips: {st.session_state.ai_error}")
    if st.button("Save transcript to a text file"):
        path = save_transcript(video["segments"], config.OUTPUT_DIR / f"transcript_{video['id']}.txt")
        st.success(f"Saved: {path}")
    st.download_button("Download transcript", transcript_text(video["segments"]),
                       file_name=f"transcript_{video['id']}.txt")
    st.write(f"Each transcript line starts with [start-end] in seconds. Type 1 to {config.MAX_CLIPS} clips "
             f"below, one per line, each {lo} to {hi} seconds long. Examples: `75 - 140` or `1:15 - 2:20`. "
             "The edges are moved to whole sentences for you.")
    manual = st.text_area("Clip times", height=100, placeholder="0:13 - 1:20\n2:23 - 3:40")
    if st.button("Make shorts from these times", type="primary"):
        clips, problems = parse_manual(manual, video["duration"], lo, hi)
        if problems:
            st.error("Please fix: " + "; ".join(problems))
        elif run(clips_from_user=clips):
            st.rerun()          # redraw the page without this fallback section

# ----- Results -----
if st.session_state.get("outputs"):
    st.subheader("Your shorts")
    st.caption(f"Also saved in: {config.OUTPUT_DIR}")
    if st.session_state.get("timing"):
        total, steps = st.session_state.timing
        st.write(f"⏱️ Finished in **{fmt(total)}** — " +
                 " · ".join(f"{name} {fmt(sec)}" for name, sec in steps if sec >= 0.5))
    outputs = st.session_state.outputs
    for row in range(0, len(outputs), 3):          # three videos per row
        for col, (i, path) in zip(st.columns(3), list(enumerate(outputs, 1))[row:row + 3]):
            with col:
                st.video(path)
                with open(path, "rb") as f:
                    st.download_button(f"Download clip {i}", f, file_name=f"clip_{i}.mp4",
                                       mime="video/mp4", key=f"dl{i}")

# ----- Housekeeping -----
def temp_items():
    """Files in the temp folder we may delete (tool caches and test scripts are kept)."""
    return [p for p in config.TEMP_DIR.iterdir() if p.name not in ("cache", "scratch")]


def size_mb(paths):
    files = [f for p in paths for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file()]
    return sum(f.stat().st_size for f in files) / 1e6


with st.expander("Free up space", expanded=st.session_state.get("freed") is not None):
    items = temp_items()
    videos = len([p for p in items if p.suffix == ".mp4" and not p.stem.startswith("clip_")])
    if st.session_state.get("freed") is not None:
        st.success(f"Freed {st.session_state.pop('freed'):.0f} MB. Finished clips in the output folder are kept.")
    elif not items:
        st.write("Nothing to delete. The temp folder is empty.")
    else:
        st.write(f"Downloaded videos and temporary files: **{size_mb(items):.0f} MB** "
                 f"({videos} downloaded video{'s' if videos != 1 else ''}) in `{config.TEMP_DIR}`. "
                 "Finished clips in the output folder are not touched.")
        if st.button("Delete temporary files"):
            freed = size_mb(items)
            for p in items:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            st.session_state.freed = freed
            st.rerun()
