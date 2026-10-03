#!/usr/bin/env python3
"""List the video files in a video folder, so the user can name the final export.

Usage: find_export.py VIDEO_FOLDER [--json]

Captions must come from the file the user exported from their editor. The
folder also holds files that look like a finished video but are not: the
cleaned-audio take, the perfect-cuts MP4, text-card renders, the slides video,
short clips. Guessing "the newest video" picks one of those, so this script
never guesses. It lists every video file with its size, length and modified
time, labels the ones the plugin itself wrote, and leaves the choice to the
user. The model shows the list and asks which file is the export.

Labels:
  raw take            step 02 output named in make-video-status.json
  cleaned audio       audio-enhance output (*_enhanced-audio.*)
  perfect-cuts cut    the MP4 in a "* perfect cut (C)" package; the export
                      only if the user changed nothing in the editor
  text cards          text-treatments renders (text-cards/, -alpha, -imovie, -ground)
  slides video        video-with-slides output; the export only if the user
                      changed nothing after it
  short clip          perfect-clips output ("* perfect clips/")
  working file        a perfect-cuts or perfect-clips work folder
  (no label)          not written by the plugin: most likely the export

Exit 0 always; the JSON lists every file with its label.
Stdlib only, so the macOS system python3 can run it.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".avi"}
MAX_DEPTH = 4
# Labels that mark a file the plugin wrote on the way to the export.
INTERMEDIATE = {"raw take", "cleaned audio", "text cards", "short clip", "working file"}
# Labels that can be the export when the user changed nothing afterwards.
MAYBE = {"perfect-cuts cut", "slides video"}


def ffprobe_bin():
    for p in (shutil.which("ffprobe"), "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):
        if p and os.path.isfile(p):
            return p
    return None


def duration(path, probe):
    if not probe:
        return None
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except (ValueError, subprocess.SubprocessError):
        return None


def raw_take(folder):
    """The step-02 output that make-video recorded, if a status file exists."""
    status = folder / "make-video-status.json"
    try:
        data = json.loads(status.read_text())
    except (OSError, ValueError):
        return None
    steps = data.get("steps", data)
    items = steps.values() if isinstance(steps, dict) else steps
    for s in items:
        if isinstance(s, dict) and str(s.get("step", s.get("id", ""))).zfill(2) == "02":
            outs = s.get("outputs") or ([s["output"]] if s.get("output") else [])
            if outs:
                p = Path(outs[0])
                return (p if p.is_absolute() else folder / p).resolve()
    return None


def label(path, folder, raw):
    rel_parts = [p.lower() for p in path.relative_to(folder).parts]
    name = path.name.lower()
    dirs = rel_parts[:-1]
    if raw and path.resolve() == raw:
        return "raw take"
    if any(d in (".perfect-cuts-work", "work") or d.startswith(".") for d in dirs):
        return "working file"
    if any(d.endswith("perfect clips") for d in dirs):
        return "short clip"
    if any(d.endswith("perfect cut (c)") for d in dirs):
        return "perfect-cuts cut"
    if "text-cards" in dirs or name.startswith("text-cards") or any(
            t in name for t in ("-alpha.", "-imovie", "-ground.")):
        return "text cards"
    if "slides-video" in dirs or "-with-slides." in name:
        return "slides video"
    if "_enhanced-audio" in name:
        return "cleaned audio"
    return ""


def walk(folder):
    for root, dirnames, files in os.walk(folder):
        depth = len(Path(root).relative_to(folder).parts)
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames.sort()
        for f in sorted(files):
            if Path(f).suffix.lower() in VIDEO_EXT and not f.startswith("._"):
                yield Path(root) / f


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    folder = Path(a.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"ERROR: not a folder: {folder}")
    probe = ffprobe_bin()
    raw = raw_take(folder)

    rows = []
    for p in walk(folder):
        st = p.stat()
        lab = label(p, folder, raw)
        rows.append({
            "path": str(p),
            "relative": str(p.relative_to(folder)),
            "label": lab,
            "kind": "intermediate" if lab in INTERMEDIATE else ("maybe" if lab in MAYBE else "candidate"),
            "size_bytes": st.st_size,
            "duration_s": duration(p, probe),
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    order = {"candidate": 0, "maybe": 1, "intermediate": 2}
    rows.sort(key=lambda r: (order[r["kind"]], -os.path.getmtime(r["path"])))

    if a.json:
        print(json.dumps({"folder": str(folder), "files": rows}, indent=2))
        return
    if not rows:
        print(f"No video files in {folder}.")
        return
    print(f"Video files in {folder}\n")
    for i, r in enumerate(rows, 1):
        dur = "?" if r["duration_s"] is None else f"{int(r['duration_s'] // 60)}:{int(r['duration_s'] % 60):02d}"
        tag = r["label"] or "not written by the plugin"
        print(f"{i:>2}. {r['relative']}\n    {human_size(r['size_bytes'])}, {dur}, modified {r['modified']}  [{tag}]")
    cands = [r for r in rows if r["kind"] == "candidate"]
    print("\nMost likely export:" if cands else "\nNo file outside the plugin's own outputs.",
          cands[0]["relative"] if cands else "Ask the user to export the final video, or to name a file.")


if __name__ == "__main__":
    main()
