"""Shared helpers for the look scripts: find ffmpeg/ffprobe and parse areas.

Tool lookup follows the plugin's order: $TV_DATA/venv/bin, ~/.local/bin, PATH,
then Homebrew's folders. Stdlib only, so the macOS system python3 runs it.
"""
import os
import shutil
import sys
from pathlib import Path


def find_tool(name):
    data = os.environ.get("TV_DATA")
    candidates = []
    if data:
        candidates.append(Path(data) / "venv" / "bin" / name)
    candidates.append(Path.home() / ".local" / "bin" / name)
    for p in candidates:
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
    found = shutil.which(name)
    if found:
        return found
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        p = Path(d) / name
        if p.is_file():
            return str(p)
    sys.exit("ERROR: %s is not installed. Run /video-teach-plugin:setup." % name)


def parse_area(values):
    """x y w h as fractions of the frame (0..1). Returns four floats."""
    try:
        x, y, w, h = (float(v) for v in values)
    except (TypeError, ValueError):
        sys.exit("ERROR: the area is four numbers: x y w h, as fractions of the frame (0 to 1).")
    for v in (x, y, w, h):
        if not 0 <= v <= 1:
            sys.exit("ERROR: area values are fractions of the frame, between 0 and 1.")
    if w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
        sys.exit("ERROR: the area must have a size and stay inside the frame.")
    return x, y, w, h
