#!/usr/bin/env python3
"""Grab three still frames from a recording, at 25%, 50% and 75% of its length.

  grab_frames.py VIDEO OUTDIR

Prints JSON: the frame paths and the video's width, height and duration. The
skill shows the frames to the user and uses them to find a free area of the
frame and to measure how light it is.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_tool  # noqa: E402


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    video, outdir = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
    if not video.is_file():
        sys.exit("ERROR: no such video: %s" % video)
    outdir.mkdir(parents=True, exist_ok=True)
    ffprobe, ffmpeg = find_tool("ffprobe"), find_tool("ffmpeg")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True)
    if probe.returncode != 0:
        sys.exit("ERROR: cannot read the video: %s" % probe.stderr.strip())
    info = json.loads(probe.stdout)
    duration = float(info["format"]["duration"])
    stream = info["streams"][0]
    frames = []
    for pct in (25, 50, 75):
        t = duration * pct / 100.0
        out = outdir / ("%s-frame-%02d.png" % (video.stem, pct))
        r = subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-ss", "%.3f" % t, "-i", str(video),
             "-frames:v", "1", str(out)], capture_output=True, text=True)
        if r.returncode != 0 or not out.is_file():
            sys.exit("ERROR: could not grab a frame at %d%%: %s" % (pct, r.stderr.strip()))
        frames.append({"percent": pct, "seconds": round(t, 2), "path": str(out)})
    print(json.dumps({"video": str(video), "width": stream["width"], "height": stream["height"],
                      "duration": round(duration, 2), "frames": frames}, indent=2))


if __name__ == "__main__":
    main()
