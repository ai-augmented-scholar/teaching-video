#!/usr/bin/env python3
"""Draw a proposed free area on a frame, so the user can approve it.

  mark_area.py FRAME x y w h OUT.png

x y w h are fractions of the frame (0 to 1), from the top-left corner. The area
is outlined twice, black outside and yellow inside, so it reads on light and on
dark footage, and everything outside it is dimmed. No text is drawn: this
ffmpeg may be built without font support.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_tool, parse_area  # noqa: E402


def main():
    if len(sys.argv) != 7:
        sys.exit(__doc__.strip())
    frame = Path(sys.argv[1]).expanduser()
    x, y, w, h = parse_area(sys.argv[2:6])
    out = Path(sys.argv[6]).expanduser()
    if not frame.is_file():
        sys.exit("ERROR: no such frame: %s" % frame)
    ffmpeg = find_tool("ffmpeg")
    X, Y, W, H = ("iw*%.6f" % x, "ih*%.6f" % y, "iw*%.6f" % w, "ih*%.6f" % h)
    dim = "black@0.45"
    chain = ",".join([
        # dim the four bands around the area
        "drawbox=x=0:y=0:w=iw:h=%s:color=%s:t=fill" % (Y, dim),
        "drawbox=x=0:y=%s+%s:w=iw:h=ih-(%s+%s):color=%s:t=fill" % (Y, H, Y, H, dim),
        "drawbox=x=0:y=%s:w=%s:h=%s:color=%s:t=fill" % (Y, X, H, dim),
        "drawbox=x=%s+%s:y=%s:w=iw-(%s+%s):h=%s:color=%s:t=fill" % (X, W, Y, X, W, H, dim),
        # double outline
        "drawbox=x=%s-6:y=%s-6:w=%s+12:h=%s+12:color=black:t=6" % (X, Y, W, H),
        "drawbox=x=%s:y=%s:w=%s:h=%s:color=0xFFD400:t=6" % (X, Y, W, H),
    ])
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(frame), "-vf", chain,
                        "-frames:v", "1", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.is_file():
        sys.exit("ERROR: could not mark the frame: %s" % r.stderr.strip())
    print(json.dumps({"frame": str(frame), "area": {"x": x, "y": y, "w": w, "h": h},
                      "marked": str(out)}, indent=2))


if __name__ == "__main__":
    main()
