# The web page. Run with start.bat (or: .\.venv\Scripts\python.exe -m streamlit run app.py)
# Paste a YouTube link, choose how many clips and how long, click one button,
# get vertical shorts with face tracking and captions.
#
# The page has two views. Settings: link, options, "Make shorts". Working: only the progress, a
# Cancel button, and each clip as soon as it is ready. "Make shorts" saves the job and reloads
# the page into the working view, so the settings are never shown (or changed) while it runs.
from shorts import config  # first: memory limits, cache folders, ffmpeg path

import json
import shutil

import streamlit as st

from shorts.clipper import ClipError, max_fit, parse_manual, pick_clips, save_transcript, suggest_count
from shorts.cutter import make_clips
from shorts.downloader import download, transcript_text, video_info
from progress_view import Reporter, clip_plan, estimate, fmt

RESULTS = config.OUTPUT_DIR / "results.json"   # the last results, so they survive a page reload

st.set_page_config(page_title="Short Video Maker", page_icon="🎬")
st.title("🎬 Short Video Maker")
st.caption("Paste a YouTube link (English). You get vertical clips with face tracking and captions.")

# Fixed areas: whatever a view draws replaces what the other view drew there.
main, results_area, space_area = st.empty(), st.empty(), st.empty()
state = st.session_state

# Streamlit forgets a setting whose box isn't drawn in a run (the working view draws none),
# so keep the link and options explicitly.
for key in [k for k in state.keys() if k in ("url", "length", "watermark", "corner") or k.startswith("n_")]:
    state[key] = state[key]


def save_results():
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps({"outputs": state.get("outputs", []), "timing": state.get("timing"),
                                   "title": state.get("results_title", "")}), encoding="utf-8")


def load_results():
    """After a page reload (new session), show the last finished clips again."""
    try:
        r = json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    outputs = [p for p in r.get("outputs", []) if config.OUTPUT_DIR.joinpath(p).exists()]
    if outputs:
        state.outputs, state.timing, state.results_title = outputs, r.get("timing"), r.get("title", "")


def show_clip(i, path, key):
    st.video(path)
    with open(path, "rb") as f:   # on_click="ignore": downloading doesn't reload the page
        st.download_button(f"Download clip {i}", f, file_name=f"clip_{i}.mp4", mime="video/mp4",
                           key=key, on_click="ignore")


# ----- A Cancel click (or anything else) stopped a running job: keep what is finished -----
if state.get("job", {}).get("started"):
    done, total = len(state.get("outputs", [])), state.job.get("total", "?")
    state.notice = (f"Stopped. {done} of {total} clips were finished" +
                    (": you can download them below." if done else "."))
    state.pop("job")
    save_results()

if "outputs" not in state and "job" not in state:
    load_results()


def run_job(job):
    """Working view: download -> pick clips (Gemini, or the user's times) -> cut, captions, face tracking.
    Each finished clip is shown (and saved in results.json) right away."""
    job["started"] = True
    space_area.empty()
    lo, hi, n = job["lo"], job["hi"], job["n"]
    state.outputs, state.timing, state.results_title = [], None, job["title"]
    save_results()
    with main.container():
        what = f"{len(job['clips'])} clips" if job["clips"] else f"{n} clip{'s' if n != 1 else ''}"
        st.subheader(f"Making {what} ({lo}–{hi} s) from “{job['title']}”")
        st.button("⏹ Cancel", help="Stop now. Clips that are already finished stay below for download.")
        cached = (config.TEMP_DIR / f"{job['id']}.mp4").exists()
        lengths = [c["end"] - c["start"] for c in job["clips"]] if job["clips"] else [(lo + hi) / 2] * n
        plan = ([("download", 1 if cached else estimate("download"))]
                + ([] if job["clips"] else [("pick", estimate("pick"))]) + clip_plan(lengths))
        bars = st.container()
        with st.status("Working... (this takes a few minutes)", expanded=True) as status:
            progress = Reporter(status, bars, plan, job["duration"])
    with results_area.container():
        live = st.container()
    row = {}                                  # the current row of three columns

    def clip_ready(i, path):
        state.outputs.append(str(path.relative_to(config.OUTPUT_DIR)))
        save_results()
        if (i - 1) % 3 == 0:
            row["cols"] = live.columns(3)
        with row["cols"][(i - 1) % 3]:
            show_clip(i, path, f"live{i}")

    try:
        video = download(job["url"], progress=progress)
        state.video = video
        clips = job["clips"]
        if not clips:
            try:
                clips = pick_clips(video["segments"], video["duration"], video["title"],
                                   progress=progress, n=n, min_len=lo, max_len=hi)
            except ClipError as e:
                progress.finish()
                state.ai_error = str(e)
                return
        job["total"] = len(clips)
        for i, c in enumerate(clips, 1):
            status.write(f"Clip {i}: {c['start']:.1f}s – {c['end']:.1f}s. {c.get('reason', '')}")
        progress.replan(clip_plan([c["end"] - c["start"] for c in clips]))
        make_clips(video["video_path"], clips, video["duration"], progress=progress, min_len=lo, max_len=hi,
                   watermark=job["watermark"], corner=job["corner"], on_clip=clip_ready)
        state.pop("ai_error", None)
        total, steps = progress.finish()
        state.timing = (total, steps)
        save_results()
    except Exception as e:  # show a readable message instead of a crash
        progress.finish()
        state.error = str(e)


# ----- Working view -----
if state.get("job"):
    run_job(state.job)
    state.pop("job", None)
    st.rerun()                      # back to the settings view, with the results


# ----- Settings view -----
with main.container():
    for kind in ("notice", "error"):
        if state.get(kind):
            (st.info if kind == "notice" else st.error)(state.pop(kind))

    url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...",
                        key="url").strip()

    # As soon as a link is pasted: show the video's title and length, and suggest a number of clips.
    info = None
    if url:
        try:
            if state.get("info_url") != url:
                with st.spinner("Checking the video..."):
                    state.info = video_info(url)
                state.info_url = url
            info = state.info
        except Exception as e:
            state.pop("info_url", None)
            st.error(str(e))

    lo, hi = config.DEFAULT_LENGTH
    if info:
        minutes, seconds = divmod(int(info["duration"]), 60)
        st.write(f"**{info['title']}** · {minutes}:{seconds:02d} long")
        # Copyright: show how this video may be reused (no tricks to hide clips from YouTube's checks).
        if info["license"] == "cc":
            st.success("✅ Creative Commons: you may reuse this video if you credit the creator. "
                       "Paste this in your post's description:")
            st.code(f"Source: \"{info['title']}\" by {info['channel'] or 'the creator'} "
                    f"(https://youtu.be/{info['id']}), licensed under CC BY.", language=None)
        elif info["license"] == "standard":
            st.info("ℹ️ Standard YouTube license: posting clips of this video needs the owner's permission "
                    "(unless it is your own video). Tip: in YouTube search, choose Filters → Creative Commons "
                    "to find videos you may reuse.")
        else:
            st.caption("License unknown for this saved copy: check it on YouTube before posting clips.")
        # (a remembered setting must not also get a starting value, or Streamlit warns)
        lo, hi = st.slider("Clip length (seconds)", int(config.MIN_CLIP_SECONDS), int(config.MAX_CLIP_SECONDS),
                           **({} if "length" in state else {"value": config.DEFAULT_LENGTH}), step=5, key="length",
                           help="Each clip will be between these lengths. It always ends at the end of a sentence.")
        most = max(1, min(config.MAX_CLIPS, max_fit(info["duration"], lo)))
        n = st.number_input(f"How many clips (suggested for this video: {suggest_count(info['duration'], lo)})",
                            min_value=1, max_value=most, key=f"n_{info['id']}_{lo}",
                            **({} if f"n_{info['id']}_{lo}" in state else {"value": suggest_count(info["duration"], lo)}),
                            help=f"Up to {most} clips of {lo}+ seconds fit into this video.")
        if max_fit(info["duration"], lo) < 1:
            st.warning(f"This video is too short for clips of {lo}+ seconds. Make the clip length shorter.")
        elif most < config.MAX_CLIPS:
            st.caption(f"This video is long enough for at most {most} clip{'s' if most != 1 else ''} "
                       f"of {lo}+ seconds. Make the clips shorter to get more.")
        wm_col, corner_col = st.columns([3, 2])
        watermark = wm_col.text_input("Watermark text (optional)", max_chars=40, key="watermark",
                                      placeholder="@yourchannel",
                                      help="Shown small in a bottom corner of every clip. Leave empty for none.")
        corner = corner_col.radio("Watermark corner", ["Bottom right", "Bottom left"], key="corner",
                                  horizontal=True)

    def start(clips=None):
        """Save the job and reload the page into the working view."""
        state.job = {"url": url, "id": info["id"], "title": info["title"], "duration": info["duration"],
                     "n": int(n), "lo": lo, "hi": hi, "clips": clips or [], "watermark": watermark,
                     "corner": "left" if corner == "Bottom left" else "right"}
        for k in ("outputs", "ai_error", "timing", "notice", "error"):
            state.pop(k, None)
        st.rerun()

    if st.button("Make shorts", type="primary"):
        if not info:
            st.warning("Please paste a YouTube link first." if not url else "Please use a working YouTube link.")
        else:
            start()

    # ----- Manual fallback: the AI was unavailable, so the user types the clip times -----
    if state.get("ai_error") and state.get("video") and info and state.video["id"] == info["id"]:
        video = state.video
        st.warning(f"The AI could not pick clips: {state.ai_error}")
        if st.button("Save transcript to a text file"):
            path = save_transcript(video["segments"], config.OUTPUT_DIR / f"transcript_{video['id']}.txt")
            st.success(f"Saved: {path}")
        st.download_button("Download transcript", transcript_text(video["segments"]),
                           file_name=f"transcript_{video['id']}.txt", on_click="ignore")
        st.write(f"Each transcript line starts with [start-end] in seconds. Type 1 to {config.MAX_CLIPS} clips "
                 f"below, one per line, each {lo} to {hi} seconds long. Examples: `75 - 140` or `1:15 - 2:20`. "
                 "The edges are moved to whole sentences for you.")
        manual = st.text_area("Clip times", height=100, placeholder="0:13 - 1:20\n2:23 - 3:40")
        if st.button("Make shorts from these times", type="primary"):
            clips, problems = parse_manual(manual, video["duration"], lo, hi)
            if problems:
                st.error("Please fix: " + "; ".join(problems))
            else:
                start(clips)

# ----- Results -----
if state.get("outputs"):
    with results_area.container():
        st.subheader("Your shorts" + (f" from “{state.results_title}”" if state.get("results_title") else ""))
        st.caption(f"Also saved in: {config.OUTPUT_DIR} (the next run replaces them)")
        if state.get("timing"):
            total, steps = state.timing
            st.write(f"⏱️ Finished in **{fmt(total)}** — " +
                     " · ".join(f"{name} {fmt(sec)}" for name, sec in steps if sec >= 0.5))
        outputs = [str(config.OUTPUT_DIR / p) for p in state.outputs]
        for row in range(0, len(outputs), 3):          # three videos per row
            for col, (i, path) in zip(st.columns(3), list(enumerate(outputs, 1))[row:row + 3]):
                with col:
                    show_clip(i, path, f"dl{i}")


# ----- Housekeeping -----
def temp_items():
    """Files in the temp folder we may delete (tool caches and test scripts are kept)."""
    return [p for p in config.TEMP_DIR.iterdir() if p.name not in ("cache", "scratch")]


def size_mb(paths):
    files = [f for p in paths for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file()]
    return sum(f.stat().st_size for f in files) / 1e6


with space_area.container():
    with st.expander("Free up space", expanded=state.get("freed") is not None):
        items = temp_items()
        videos = len([p for p in items if p.suffix == ".mp4" and not p.stem.startswith("clip_")])
        if state.get("freed") is not None:
            st.success(f"Freed {state.pop('freed'):.0f} MB. Finished clips in the output folder are kept.")
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
                state.freed = freed
                st.rerun()
