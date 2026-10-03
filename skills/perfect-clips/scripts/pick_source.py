#!/usr/bin/env python3
"""Pick the source video for upright and for wide clips.

Usage:
    python3 pick_source.py "<video folder>" [--source "<file the user named>"]

Prints JSON and exits 0, or exits 2 with "ask": true when the files cannot
settle it (then the skill asks the user; it never guesses).

Why: the user's final export usually carries burned-in text cards. An
upright clip crops the frame to 9:16, and a card near the centre would be cut
in half. So upright clips come from the clean cut the export was built on;
wide clips keep the export, cards and all, because they ship the frame as
shot. The rules, first match wins:

1. Slide-deck lecture (video-with-slides output in the folder):
   upright = the speaker cut, wide = the slides MP4 (found through
   slides-video/source.json, or by its -with-slides name). Same as
   `slides_plan.py detect`.
2. A perfect-cuts package in the folder ("<stem> perfect cut (C)/1 WATCH -
   final video (C).mp4"):
   upright = that cut MP4, wide = the export (--source, else the cut).
   Only when the export is the same length as the cut (within 0.5 s): a
   different length means the user edited further in the editor, and the
   cut would bring back material they removed — then ask.
3. Otherwise: upright = wide = --source.

Stdlib only.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pc_env  # noqa: F401  (tool PATH: ffprobe)

CUT_NAME = "1 WATCH - final video (C).mp4"
SAME_LENGTH = 0.5


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out) if out else None


def slides_case(folder):
    here = Path(__file__).resolve().parent
    r = subprocess.run([sys.executable, str(here / "slides_plan.py"), "detect",
                        str(folder)], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--source", default=None,
                    help="the file the user named (usually the final export)")
    a = ap.parse_args()
    folder = Path(a.folder).expanduser().resolve()
    source = Path(a.source).expanduser().resolve() if a.source else None
    res = {"folder": str(folder), "source": str(source) if source else None}

    s = slides_case(folder)
    if s and s.get("found"):
        if not s.get("cut") or not s.get("cut_matches"):
            res.update(case="slides", ask=True,
                       note=s.get("note") or "The speaker cut does not match "
                       "the slides video in length. Ask which file is the cut "
                       "the slides video was made from.")
            print(json.dumps(res, indent=1))
            return 2
        res.update(case="slides", upright=s["cut"], wide=s["with_slides"],
                   say="This lecture has slides: upright clips show the slide "
                       "on top and the speaker below; wide clips use the "
                       "slides video.")
        print(json.dumps(res, indent=1))
        return 0

    cuts = sorted(folder.glob("* perfect cut (C)/" + CUT_NAME))
    if cuts:
        cut = cuts[-1]
        res["cut"] = str(cut)
        if source is None or source == cut:
            res.update(case="cut", upright=str(cut), wide=str(cut),
                       say="Clips come from the clean cut.")
            print(json.dumps(res, indent=1))
            return 0
        d_cut, d_src = duration(cut), duration(source)
        res.update(cut_seconds=d_cut, source_seconds=d_src)
        if d_cut is not None and d_src is not None and abs(d_cut - d_src) <= SAME_LENGTH:
            res.update(case="cut+export", upright=str(cut), wide=str(source),
                       say="Upright clips come from the clean cut, so no text "
                           "card is cropped in half; wide clips come from "
                           "your export, with its cards.")
            print(json.dumps(res, indent=1))
            return 0
        res.update(case="cut+export", ask=True,
                   note="The export is %.1f s and the cut %.1f s, so the export "
                        "was edited further. Ask the user: cut upright clips "
                        "from the export (text cards may be cropped), or from "
                        "the cut (edits made after the cut come back)?"
                        % (d_src or 0, d_cut or 0))
        print(json.dumps(res, indent=1))
        return 2

    if source is None:
        res.update(ask=True, note="No cut and no source named. Ask the user "
                   "for the video file.")
        print(json.dumps(res, indent=1))
        return 2
    res.update(case="plain", upright=str(source), wide=str(source),
               say="Clips come from the file you named.")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
