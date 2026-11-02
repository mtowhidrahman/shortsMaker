# Progress on the page: a bar for the whole job (time so far, about how long is left), a bar for
# the current step, a log of steps, and at the end how long each kind of step took.
# The engine calls the Reporter like this: progress(text, done=None, step=None) (see shorts/report.py).
import time

import streamlit as st

# Names shown for each kind of step.
STEP_NAMES = {"download": "Download", "transcribe": "Transcript (Whisper)", "pick": "AI picks the clips",
              "listen": "Listening for sentences", "edges": "AI sentence check", "cut": "Cutting",
              "faces": "Face tracking", "render": "Rendering with captions"}


def estimate(step, length=0.0, duration=0.0):
    """Rough seconds a step takes on this PC (measured with 720p video). length: clip length,
    duration: video length. Only used until the step reports how far it is."""
    kind = step.split()[0]
    return {"download": 30, "transcribe": 0.05 * duration, "pick": 15, "listen": 0.1 * length + 1,
            "edges": 5, "cut": 0.04 * length + 0.3, "faces": 0.14 * length,
            "render": 0.29 * length}.get(kind, 5)


def clip_plan(lengths, numbers=None):
    """The steps make_clips() goes through, with estimates, for clips of these lengths
    (numbers: the clip numbers, when only some clips are remade)."""
    numbers = numbers or range(1, len(lengths) + 1)
    plan = [(f"listen {i}", estimate("listen", L)) for i, L in zip(numbers, lengths)]
    plan.append(("edges", estimate("edges")))
    for i, L in zip(numbers, lengths):
        plan += [(f"{kind} {i}", estimate(kind, L)) for kind in ("cut", "faces", "render")]
    return plan


def fmt(seconds):
    m, s = divmod(int(round(max(0, seconds))), 60)
    return f"{m}:{s:02d}"


class Reporter:
    def __init__(self, log, bars, plan, duration=0.0):
        self.log, self.duration = log, duration              # log: st.status box for the step lines
        self.total_bar, self.step_bar = bars.empty(), bars.empty()
        self.plan = list(plan)                               # steps still to come: [(step, seconds)]
        self.t0 = self.step_t0 = self.last_draw = time.time()
        self.step, self.est, self.done, self.text = None, 0.0, 0.0, ""
        self.times = {}                                      # step -> seconds it took
        self.real = self.guessed = 0.0                       # finished steps: real vs estimated time

    def __call__(self, text, done=None, step=None):
        now = time.time()
        if step and step != self.step:
            self._start(step, now)
        if done is None:
            self.log.write(text)
            self.text = text.strip()
        else:
            self.done = done
        if done is None or now - self.last_draw > 0.3:    # redraw at most ~3 times a second
            self._draw(now)

    def replan(self, plan):
        """The clips are known now: replace the rough plan for the rest of the job."""
        self.plan = list(plan)
        self._draw(time.time())

    def _start(self, step, now):
        if self.step:
            took = now - self.step_t0
            self.times[self.step] = took
            self.real += took
            self.guessed += self.est
        names = [s for s, _ in self.plan]
        if step in names:                                   # skip planned steps that didn't happen
            k = names.index(step)
            self.est = self.plan[k][1]
            self.plan = self.plan[k + 1:]
        else:
            self.est = estimate(step, duration=self.duration)
        self.step, self.step_t0, self.done = step, now, 0.0

    def _left(self, now):
        """(seconds left in this step, seconds left in total)"""
        speed = min(3.0, max(0.5, self.real / self.guessed)) if self.guessed > 5 else 1.0
        spent = now - self.step_t0
        step_left = spent / self.done - spent if self.done > 0.05 else max(1.0, self.est * speed - spent)
        return step_left, step_left + speed * sum(s for _, s in self.plan)

    def _draw(self, now):
        self.last_draw = now
        spent = now - self.t0
        step_left, total_left = self._left(now)
        self.total_bar.progress(min(1.0, spent / max(spent + total_left, 1e-6)),
                                text=f"Total: {fmt(spent)} so far · about {fmt(total_left)} left")
        if self.step:
            kind, _, n = self.step.partition(" ")
            label = STEP_NAMES.get(kind, kind) + (f" (clip {n})" if n else "")
            pct = f"{self.done:.0%} · " if self.done else ""
            self.step_bar.progress(min(1.0, self.done), text=f"{label}: {pct}about {fmt(step_left)} left")

    def finish(self):
        """Stop the clock, remove the bars. Returns (total seconds, [(step name, seconds)])."""
        now = time.time()
        if self.step:
            self.times[self.step] = now - self.step_t0
        self.total_bar.empty()
        self.step_bar.empty()
        summary = {}
        for step, took in self.times.items():
            name = STEP_NAMES.get(step.split()[0], step)
            summary[name] = summary.get(name, 0.0) + took
        return now - self.t0, list(summary.items())
