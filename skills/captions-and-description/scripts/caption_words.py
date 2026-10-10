#!/usr/bin/env python3
"""Transcribe a finished video for captions, and recover dropped speech.

Parakeet can drop whole sentences on noisy audio, even in a short clip. The
dropped speech shows up as a stretch the waveform says is speech, but that has
no words on it. This script finds those stretches and re-transcribes the video
in ~20 s windows when it finds one, so the captions do not skip lines.

Steps:
  1. One Parakeet pass over the whole file (`transcribe --words`).
  2. A speech map from the waveform (perfect-cuts' speech_map.py).
  3. Measure every block. Two kinds count as dropped speech:
     - empty: no words, longer than 0.4 s, within 5 dB of the median speech
       level;
     - sparse: longer than 2 s, at speech level, but with fewer than 40% of
       the median words per second of such blocks. Parakeet sometimes keeps
       the first words of a block and drops the rest of the sentence; the
       block is then not empty, so only the word rate shows the loss.
  4. If any block is dropped speech: re-transcribe in windows
     (perfect-cuts' transcribe_windows.py), map again, measure again.
  5. Keep the pass with more words.

Usage:
    python3 caption_words.py <video> --workdir <dir> --out <words.json>

Prints a one-line JSON summary on stdout. Pass TV_DATA through the
environment, as for every script in this plugin.
"""
import argparse
import array
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

HERE = Path(__file__).resolve()
PLUGIN = HERE.parents[3]
TRANSCRIBE = PLUGIN / "scripts" / "transcribe"
CUTS = PLUGIN / "skills" / "perfect-cuts" / "scripts"
RATE = 8000          # samples per second for the level measurement
SPEECH_RANGE_DB = 5  # an empty block this close to speech level is speech
MIN_BLOCK_S = 0.4    # shorter than this is a breath or a click
SPARSE_MIN_S = 2.0   # word-rate check only on blocks at least this long
SPARSE_RATIO = 0.4   # below this share of the median words/second = sparse


def run(cmd):
    proc = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        tool = cmd[1] if cmd[0] == sys.executable else cmd[0]
        sys.exit("ERROR: %s failed" % Path(str(tool)).name)
    return proc


def load_samples(video):
    """Decode the audio once, mono 8 kHz signed 16-bit."""
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found. Run /video-teach-plugin:setup.")
    proc = run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vn",
                "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"])
    samples = array.array("h")
    samples.frombytes(proc.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def level_db(samples, start, end):
    a, b = int(start * RATE), int(end * RATE)
    chunk = samples[a:b]
    if not chunk:
        return -120.0
    ms = sum(x * x for x in chunk) / len(chunk)
    return 10 * math.log10(ms / (32768.0 ** 2)) if ms > 0 else -120.0


def word_count(words_json):
    data = json.load(open(words_json))
    return sum(len(s.get("words", [])) for s in data.get("segments", []))


def dropped_blocks(map_json, samples):
    """Blocks at speech level that lost words: empty ones and sparse ones.

    Returns (blocks, speech level dB, median words/second). Each block carries
    "kind": "empty" or "sparse".
    """
    blocks = json.load(open(map_json))["blocks"]
    for b in blocks:
        b["db"] = level_db(samples, b["start"], b["end"])
        b["dur"] = b["end"] - b["start"]
        b["nwords"] = len(b.get("text", "").split())
    speech = [b["db"] for b in blocks if b["nwords"]]
    if not speech:
        return [], None, None
    ref = statistics.median(speech)
    at_level = [b for b in blocks if b["db"] >= ref - SPEECH_RANGE_DB]

    long_rates = [b["nwords"] / b["dur"] for b in at_level
                  if b["nwords"] and b["dur"] >= SPARSE_MIN_S]
    med_rate = statistics.median(long_rates) if long_rates else None

    out = []
    for b in at_level:
        kind = None
        if not b["nwords"] and b["dur"] >= MIN_BLOCK_S:
            kind = "empty"
        elif (med_rate and b["nwords"] and b["dur"] >= SPARSE_MIN_S
              and b["nwords"] / b["dur"] < SPARSE_RATIO * med_rate):
            kind = "sparse"
        if kind:
            out.append({"start": round(b["start"], 2), "end": round(b["end"], 2),
                        "db": round(b["db"], 1), "kind": kind,
                        "words": b["nwords"],
                        "words_per_s": round(b["nwords"] / b["dur"], 2)})
    return out, round(ref, 1), (round(med_rate, 2) if med_rate else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    work = Path(a.workdir)
    work.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    pass1 = work / "words-pass1.json"
    map1 = work / "map-pass1.json"
    run([TRANSCRIBE, a.video, "--words", pass1, "--quiet"])
    run([py, CUTS / "speech_map.py", a.video, pass1, "--out", map1])
    samples = load_samples(a.video)
    lost1, ref, rate = dropped_blocks(map1, samples)
    summary = {"words_pass1": word_count(pass1), "speech_level_db": ref,
               "median_words_per_s": rate,
               "dropped_blocks_pass1": len(lost1),
               "empty_pass1": sum(1 for b in lost1 if b["kind"] == "empty"),
               "sparse_pass1": sum(1 for b in lost1 if b["kind"] == "sparse")}
    best = pass1

    if lost1:
        pass2 = work / "words-windows.json"
        map2 = work / "map-windows.json"
        run([py, CUTS / "transcribe_windows.py", a.video, map1, "--out", pass2])
        run([py, CUTS / "speech_map.py", a.video, pass2, "--out", map2])
        lost2, _, _ = dropped_blocks(map2, samples)
        summary.update({"words_windows": word_count(pass2),
                        "dropped_blocks_windows": len(lost2),
                        "empty_windows": sum(1 for b in lost2 if b["kind"] == "empty"),
                        "sparse_windows": sum(1 for b in lost2 if b["kind"] == "sparse")})
        if word_count(pass2) >= word_count(pass1):
            best, lost1 = pass2, lost2

    shutil.copyfile(best, a.out)
    summary.update({"used": Path(best).name, "words_final": word_count(a.out),
                    "still_dropped": lost1})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
