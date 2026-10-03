#!/usr/bin/env python3
"""Clean a wide clip's SRT caption track WITHOUT moving any timing.

    srt_clean.py <clip.srt> --dur <clip seconds> --out <clean.srt>

Drops a trailing cue shorter than MIN_TAIL and clamps any cue that runs past
the clip. perfect-clips pads each segment's out-point to a waveform frame,
which catches the ONSET of the next spoken word, so the last cue is often a
5-12 ms fragment of a word the viewer never hears ("And", "The"). Multi-
segment clips nearly always have one. It is too short to render as a burned
chip, but a subtitle track shows it as a real line, past the end of the video.

Timestamps that survive are rewritten from their parsed values, never
shifted, so the track cannot drift against the audio.
"""
import re
import sys

TIME = re.compile(r"^(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)")
MIN_TAIL = 0.12   # seconds; below this a trailing cue is a padding fragment


def secs(ts):
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def stamp(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def parse(path):
    """-> [ {time, lines[]} ] in file order."""
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    cues = []
    for block in [b for b in raw.split("\n\n") if b.strip()]:
        lines = block.split("\n")
        ti = next((n for n, l in enumerate(lines) if TIME.match(l)), None)
        if ti is None:
            sys.exit(f"{path}: block without a timestamp:\n{block}")
        cues.append({"time": lines[ti],
                     "lines": [l for l in lines[ti + 1:] if l.strip() != ""]})
    if not cues:
        sys.exit(f"{path}: no cues found")
    return cues


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    src = sys.argv[1]
    dur = float(sys.argv[sys.argv.index("--dur") + 1]) if "--dur" in sys.argv else None
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    if dur is None or not out:
        sys.exit("needs --dur <clip seconds> and --out <clean.srt>")
    cues = parse(src)
    kept, dropped, clamped = [], 0, 0
    for c in cues:
        m = TIME.match(c["time"])
        t0, t1 = secs(m.group(1)), secs(m.group(2))
        if t0 >= dur:                       # starts after the video ends
            dropped += 1
            continue
        if t1 > dur:
            t1 = dur
            clamped += 1
        if (t1 - t0) < MIN_TAIL and c is cues[-1]:
            dropped += 1
            continue
        kept.append((t0, t1, " ".join(c["lines"])))
    if not kept:
        sys.exit("cleaning removed every cue; check --dur")
    with open(out, "w", encoding="utf-8", newline="") as f:
        for n, (t0, t1, text) in enumerate(kept, 1):
            f.write(f"{n}\n{stamp(t0)} --> {stamp(t1)}\n{text}\n\n")
    print(f"{len(cues)} cues in, {len(kept)} out "
          f"({dropped} dropped, {clamped} clamped) -> {out}")


if __name__ == "__main__":
    main()
