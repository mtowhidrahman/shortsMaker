# How the engine reports progress. Every long step calls progress(text, done=None, step=None):
#   text: what is happening (shown as a new line when done is None)
#   done: how far the current step is, 0..1 (for progress bars)
#   step: a short name like "faces 2"; a new name means a new step started (used for timing)
# The page (app.py) shows bars and times; on the command line we just print the lines.


def console(text, done=None, step=None):
    """Default reporter for quick tests: print new lines, skip the percentages."""
    if done is None:
        print(text)
