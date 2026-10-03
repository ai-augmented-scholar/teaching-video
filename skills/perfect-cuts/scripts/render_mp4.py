#!/usr/bin/env python3
"""Render a cuts.json to a single MP4 — frame-accurate, gapless.

Uses one ffmpeg filter_complex (trim + concat, full re-encode). Never use
stream-copy concat of separately encoded segments: timestamps glitch and
players show frozen frames (learned on real footage).

Usage:
    python3 render_mp4.py cuts.json /abs/output.mp4

Two-camera mode: cuts.json may carry an "angles" map and a clip
may carry "angle": "<key>" — see export_fcpxml.py for the schema. The picture
of such a clip comes from the angle's file (time-shifted by offset_frames,
fitted into the master frame with padding, conformed to the master fps); the
audio always comes from the master. A clip outside the angle's recording falls
back to the master picture.
"""
import json
import subprocess
import sys
import os

# Find ffmpeg even under a bare PATH: the plugin's own environment
# (TV_DATA, passed in by the skill), then Homebrew, then the inherited PATH.
_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])


def main():
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    fps = spec["fps"]
    clips = spec["clips"]

    w, h = spec.get("width"), spec.get("height")
    angles = spec.get("angles") or {}
    inputs = ["-i", spec["source"]]
    idx = {}
    for key, a in angles.items():
        idx[key] = len(inputs) // 2
        inputs += ["-i", a["source"]]
    conform = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")

    parts, vlabels, alabels, fallback = [], [], [], 0
    for n, c in enumerate(clips):
        s, e = c["in_frame"] / fps, c["out_frame"] / fps
        # Video trims sit HALF A FRAME inside the frame boundaries. A trim
        # time written at the exact boundary and rounded can land a hair
        # after the clip's first frame (dropping it: that is the voice-onset
        # frame) or a hair after its last frame (adding one). Each such
        # rounding also leaves a one-frame timestamp gap at the join. With
        # half-frame margins the trim keeps exactly out_frame - in_frame
        # frames whatever the rounding. Audio is cut at the exact times.
        vs, ve = (c["in_frame"] - 0.5) / fps, (c["out_frame"] - 0.5) / fps
        vsrc = "[0:v]trim=start={:.6f}:end={:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p".format(max(vs, 0), ve)
        a = angles.get(c.get("angle") or "")
        if a:
            off = a["offset_frames"] / a["fps"]
            a_end = a.get("source_duration") or (a.get("source_frames", 0) / a["fps"])
            if s - off >= 0 and (not a_end or e - off <= a_end):
                vsrc = (f"[{idx[c['angle']]}:v]trim=start={max(vs - off, 0):.6f}:end={ve - off:.6f},"
                        f"setpts=PTS-STARTPTS,{conform}")
            else:
                fallback += 1
        parts.append(
            f"{vsrc}[v{n}];"
            f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{n}];")
        vlabels.append(f"[v{n}]")
        alabels.append(f"[a{n}]")
    fc = "".join(parts) + "".join(
        f"{v}{a}" for v, a in zip(vlabels, alabels)
    ) + f"concat=n={len(clips)}:v=1:a=1[outv][outa]"
    if fallback:
        print(f"{fallback} clip(s) outside the angle's recording; master picture used")

    cmd = ["ffmpeg", "-nostdin", *inputs,
           "-filter_complex", fc, "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           "-y", out]
    subprocess.run(cmd, check=True, capture_output=True)
    total = sum(c["out_frame"] - c["in_frame"] for c in clips) / fps
    print(f"{len(clips)} clips, {total:.2f}s -> {out}")


if __name__ == "__main__":
    main()
