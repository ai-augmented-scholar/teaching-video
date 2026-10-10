#!/usr/bin/env python3
"""Measure the blocks of a speech map that have no words, and say what each is.

Parakeet drops speech on noisy audio, even in a short clip. Dropped speech
shows up as a block the waveform calls speech that carries no words. This
script measures every such block against the median level of the blocks that
do carry words, and gives a verdict:

  dropped   at least 0.4 s and within 5 dB of the speech median: almost
            certainly speech Parakeet lost. Re-transcribe (transcribe_windows.py).
  quiet     at least 0.4 s, 5-15 dB under the speech median: a soft word, a
            murmur or a laugh. Listen, or transcribe the snippet on its own.
  noise     more than 15 dB under the speech median: a breath, a chair, room tone.
  short     under 0.4 s: a breath or a click.

It also flags "sparse" blocks: at least 2 s long, at speech level, with
fewer than 40% of the median words per second of such blocks. Parakeet
sometimes keeps the first words of a block and drops the rest of the
sentence; the block is then not empty, so only the word rate shows the loss.

The thresholds match captions-and-description's caption_words.py (0.4 s,
5 dB, 2 s, 40%), so both skills judge dropped speech the same way.

Usage:
    python3 measure_blocks.py <map.json> <source video> [--json]

Exit 0 when nothing looks dropped, 1 when at least one block is "dropped" or
"sparse" (re-transcribe in windows, rebuild the map, measure again).
Pass TV_DATA through the environment, as for every script in this plugin.
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

_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

RATE = 8000          # samples per second for the level measurement
SPEECH_RANGE_DB = 5  # an empty block this close to speech level is speech
QUIET_RANGE_DB = 15  # 5-15 dB under speech: soft, worth a listen
MIN_BLOCK_S = 0.4    # shorter than this is a breath or a click
SPARSE_MIN_S = 2.0   # word-rate check only on blocks at least this long
SPARSE_RATIO = 0.4   # below this share of the median words/second = sparse


def load_samples(video):
    """Decode the audio once, mono 8 kHz signed 16-bit."""
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found. Run /video-teach-plugin:setup.")
    p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vn",
                        "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                       capture_output=True)
    if p.returncode != 0:
        sys.exit("ERROR: ffmpeg could not read %s" % video)
    samples = array.array("h")
    samples.frombytes(p.stdout[: len(p.stdout) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def level_db(samples, start, end):
    chunk = samples[int(start * RATE):int(end * RATE)]
    if not chunk:
        return -120.0
    ms = sum(x * x for x in chunk) / len(chunk)
    return 10 * math.log10(ms / (32768.0 ** 2)) if ms > 0 else -120.0


def measure(map_json, video):
    blocks = json.load(open(map_json, encoding="utf-8"))["blocks"]
    samples = load_samples(video)
    for b in blocks:
        b["dur"] = b["end"] - b["start"]
        b["db"] = level_db(samples, b["start"], b["end"])
        b["nwords"] = len((b.get("text") or "").split())
    speech = [b["db"] for b in blocks if b["nwords"]]
    if not speech:
        sys.exit("ERROR: no block in the map has words; transcribe first.")
    ref = statistics.median(speech)
    rates = [b["nwords"] / b["dur"] for b in blocks
             if b["nwords"] and b["dur"] >= SPARSE_MIN_S
             and b["db"] >= ref - SPEECH_RANGE_DB]
    med_rate = statistics.median(rates) if rates else None

    rows = []
    for b in blocks:
        below = ref - b["db"]
        verdict = None
        if not b["nwords"]:
            if b["dur"] < MIN_BLOCK_S:
                verdict = "short"
            elif below <= SPEECH_RANGE_DB:
                verdict = "dropped"
            elif below <= QUIET_RANGE_DB:
                verdict = "quiet"
            else:
                verdict = "noise"
        elif (med_rate and b["dur"] >= SPARSE_MIN_S and below <= SPEECH_RANGE_DB
              and b["nwords"] / b["dur"] < SPARSE_RATIO * med_rate):
            verdict = "sparse"
        if verdict:
            rows.append({"i": b["i"], "start": round(b["start"], 2),
                         "end": round(b["end"], 2), "dur": round(b["dur"], 2),
                         "db": round(b["db"], 1), "below_speech_db": round(below, 1),
                         "words": b["nwords"], "verdict": verdict})
    return {"speech_median_db": round(ref, 1),
            "median_words_per_s": round(med_rate, 2) if med_rate else None,
            "blocks": rows,
            "dropped": sum(r["verdict"] in ("dropped", "sparse") for r in rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("map")
    ap.add_argument("source")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = measure(a.map, a.source)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(f"speech median {res['speech_median_db']} dB; "
              f"{len(res['blocks'])} blocks to look at")
        for r in res["blocks"]:
            print(f"  [{r['i']:3d}] {r['start']:8.2f}-{r['end']:8.2f}  "
                  f"{r['db']:6.1f} dB ({r['below_speech_db']:+5.1f} under)  "
                  f"words {r['words']:2d}  {r['verdict']}")
        if res["dropped"]:
            print(f"{res['dropped']} block(s) look like dropped speech: "
                  f"re-transcribe in windows (transcribe_windows.py), rebuild "
                  f"the map, and measure again.")
        else:
            print("no dropped speech.")
    sys.exit(1 if res["dropped"] else 0)


if __name__ == "__main__":
    main()
