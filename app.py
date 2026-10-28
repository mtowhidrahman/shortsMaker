# Step 7: the web page. Run with:  .\.venv\Scripts\streamlit.exe run app.py
# Paste a YouTube link, click one button, get 3 vertical shorts with face tracking and captions.
from shorts import config  # first: memory limits, cache folders, ffmpeg path

import shutil

import streamlit as st

from shorts.clipper import ClipError, parse_manual, pick_clips, save_transcript
from shorts.cutter import make_clips
from shorts.downloader import download, transcript_text

st.set_page_config(page_title="Short Video Maker", page_icon="🎬")
st.title("🎬 Short Video Maker")
st.caption("Paste a YouTube link (English). You get 3 vertical clips under 60 seconds, "
           "with face tracking and captions.")

url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...")
go = st.button("Make 3 shorts", type="primary")
if go and not url.strip():
    st.warning("Please paste a YouTube link first.")
    go = False


def run(clips_from_user=None):
    """Download -> pick clips (Gemini, or the user's times) -> cut, captions, face tracking."""
    with st.status("Working... (this takes a few minutes)", expanded=True) as status:
        try:
            video = download(url.strip(), progress=status.write)
            st.session_state.video = video
            if clips_from_user:
                clips = clips_from_user
            else:
                try:
                    clips = pick_clips(video["segments"], video["duration"], video["title"],
                                       progress=status.write)
                except ClipError as e:
                    st.session_state.ai_error = str(e)
                    status.update(label="The AI could not pick clips. You can choose them yourself below.",
                                  state="error")
                    return
            for i, c in enumerate(clips, 1):
                status.write(f"Clip {i}: {c['start']:.1f}s – {c['end']:.1f}s. {c.get('reason', '')}")
            st.session_state.outputs = [str(p) for p in
                                        make_clips(video["video_path"], clips, video["duration"],
                                                   progress=status.write)]
            st.session_state.clips = clips
            st.session_state.pop("ai_error", None)
            status.update(label="Done! Your 3 shorts are ready.", state="complete", expanded=False)
            return True
        except Exception as e:  # show a readable message instead of a crash
            status.update(label="Something went wrong.", state="error")
            st.error(str(e))


if go:
    for k in ("outputs", "ai_error", "video", "clips"):
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
    st.write("Each transcript line starts with [start-end] in seconds. Type 3 clips below, "
             "one per line, each under 60 seconds. Examples: `75 - 120` or `1:15 - 2:00`.")
    manual = st.text_area("Clip times", height=100, placeholder="0:13 - 0:40\n2:23 - 2:54\n3:03 - 3:32")
    if st.button("Make shorts from these times", type="primary"):
        clips, problems = parse_manual(manual, video["duration"])
        if problems:
            st.error("Please fix: " + "; ".join(problems))
        elif run(clips_from_user=clips):
            st.rerun()          # redraw the page without this fallback section

# ----- Results -----
if st.session_state.get("outputs"):
    st.subheader("Your shorts")
    st.caption(f"Also saved in: {config.OUTPUT_DIR}")
    cols = st.columns(3)
    for i, (col, path) in enumerate(zip(cols, st.session_state.outputs), 1):
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
