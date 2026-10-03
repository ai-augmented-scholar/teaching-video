#!/usr/bin/env python3
"""Re-transcribe a take in ~20 s windows cut at block gaps, and merge the words.

Why: on a long or noisy take, one Parakeet pass over the whole file can drop
whole sentences. They show up in the speech map as empty blocks at speech
level. Windows of about 20 s, cut in the silence between blocks, recover them.

Usage:
    python3 transcribe_windows.py <video> <map.json> --out <transcript.json>
        [--window 20]

<map.json> is the output of speech_map.py (it only needs the blocks). The
result has the same segments[].words[] shape the bundled `transcribe --words`
writes, with every time on the source timeline, so speech_map.py can be run
again on it. Pass TV_DATA through the environment, as for every script here.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Find ffmpeg even under a bare PATH: the plugin's own environment
# (TV_DATA, passed in by the skill), then Homebrew, then the inherited PATH.
_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

# skills/perfect-cuts/scripts/ -> plugin root -> scripts/transcribe
TRANSCRIBE = Path(__file__).resolve().parents[3] / "scripts" / "transcribe"
PAD = 0.2  # seconds of silence kept on each side of a window


def windows(blocks, size):
    """Group consecutive blocks into windows of about `size` seconds."""
    out, cur = [], []
    for b in sorted(blocks, key=lambda b: b["start"]):
        if cur and b["end"] - cur[0]["start"] > size:
            out.append(cur)
            cur = []
        cur.append(b)
    if cur:
        out.append(cur)
    # Pad each window into the silence around it, but never past the middle of
    # the gap to the next window: overlapping windows would count words twice.
    spans = []
    for i, w in enumerate(out):
        s, e = w[0]["start"] - PAD, w[-1]["end"] + PAD
        if i > 0:
            s = max(s, (out[i - 1][-1]["end"] + w[0]["start"]) / 2)
        if i < len(out) - 1:
            e = min(e, (w[-1]["end"] + out[i + 1][0]["start"]) / 2)
        spans.append((max(0.0, s), e))
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("map")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=float, default=20.0)
    a = ap.parse_args()

    blocks = json.load(open(a.map))["blocks"]
    spans = windows(blocks, a.window)
    segments, total = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for n, (s, e) in enumerate(spans):
            wav = Path(tmp) / f"w{n:04d}.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{s:.3f}",
                            "-to", f"{e:.3f}", "-i", a.video, "-ac", "1",
                            "-ar", "16000", str(wav)], check=True)
            js = Path(tmp) / f"w{n:04d}.json"
            subprocess.run([str(TRANSCRIBE), str(wav), "--words", str(js),
                            "--quiet"], check=True)
            for seg in json.load(open(js)).get("segments", []):
                seg = dict(seg)
                for k in ("start", "end"):
                    if k in seg:
                        seg[k] = round(seg[k] + s, 3)
                words = []
                for w in seg.get("words", []):
                    w = dict(w)
                    w["start"] = round(w["start"] + s, 3)
                    w["end"] = round(w["end"] + s, 3)
                    words.append(w)
                seg["words"] = words
                total += len(words)
                segments.append(seg)
            print(f"window {n + 1}/{len(spans)}: {s:7.2f}-{e:7.2f}s", file=sys.stderr)
    text = " ".join(seg.get("text", "").strip() for seg in segments).strip()
    json.dump({"text": text, "segments": segments}, open(a.out, "w"),
              ensure_ascii=False, indent=1)
    print(f"{len(spans)} windows, {total} words -> {a.out}")


if __name__ == "__main__":
    main()
