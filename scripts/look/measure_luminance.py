#!/usr/bin/env python3
"""Measure how light an area of a frame is, and whether white text needs a plate.

  measure_luminance.py FRAME x y w h

x y w h are fractions of the frame (0 to 1). Prints JSON with the mean and the
90th-percentile relative luminance of the area (0 = black, 1 = white), the
contrast ratio white text gets against each, and a plate recommendation.

The rule (WCAG contrast, white text = luminance 1.0):
  contrast = 1.05 / (L + 0.05)
  - body-size text needs 4.5:1 against the area's average, so mean L <= 0.18;
  - the brightest tenth of the area (a window, a lamp, a white shelf) must
    still give large text 3:1, so 90th-percentile L <= 0.30.
If either fails, the recommendation is a plate: white text on a dark grey
backdrop at 70% opacity. The user confirms or overrides it.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_tool, parse_area  # noqa: E402

SAMPLE_W = 240  # the area is scaled to this width before measuring


def lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def contrast(lum):
    return round(1.05 / (lum + 0.05), 2)


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__.strip())
    frame = Path(sys.argv[1]).expanduser()
    x, y, w, h = parse_area(sys.argv[2:6])
    if not frame.is_file():
        sys.exit("ERROR: no such frame: %s" % frame)
    ffmpeg = find_tool("ffmpeg")
    vf = "crop=iw*%.6f:ih*%.6f:iw*%.6f:ih*%.6f,scale=%d:-2" % (w, h, x, y, SAMPLE_W)
    r = subprocess.run([ffmpeg, "-v", "error", "-i", str(frame), "-vf", vf,
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        sys.exit("ERROR: could not read the area: %s" % r.stderr.decode("utf-8", "replace").strip())
    data = r.stdout
    table = [lin(i) for i in range(256)]
    lums = []
    for i in range(0, len(data) - 2, 3):
        lums.append(0.2126 * table[data[i]] + 0.7152 * table[data[i + 1]] + 0.0722 * table[data[i + 2]])
    lums.sort()
    mean = sum(lums) / len(lums)
    p90 = lums[int(0.9 * (len(lums) - 1))]
    reasons = []
    if mean > 0.18:
        reasons.append("the area's average is too light for white text (%.2f:1, needs 4.5:1)" % contrast(mean))
    if p90 > 0.30:
        reasons.append("its brightest parts are too light even for large white text (%.2f:1, needs 3:1)" % contrast(p90))
    print(json.dumps({
        "frame": str(frame),
        "area": {"x": x, "y": y, "w": w, "h": h},
        "mean_luminance": round(mean, 3),
        "p90_luminance": round(p90, 3),
        "white_text_contrast_mean": contrast(mean),
        "white_text_contrast_p90": contrast(p90),
        "plate_recommended": bool(reasons),
        "reason": "; ".join(reasons) if reasons else "dark enough: white text reads without a plate",
    }, indent=2))


if __name__ == "__main__":
    main()
