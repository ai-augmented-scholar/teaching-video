#!/usr/bin/env python3
"""Run the bundled 10-second test clip through the plugin's main chain.

    TV_DATA="<plugin data folder>" python3 run_test.py [--work DIR] [--json]

The clip (test-media/test-clip.mov) is a synthetic voice over a plain picture,
with light background noise and one deliberate false start:
"Today we look at ... today we look at two ideas. The first one is reason.
The second one is evidence."

Steps, each reported as PASS or FAIL with one line of detail:
  1. sound    audio-enhance cleans the clip (noise removal, loudness)
  2. words    Parakeet transcribes the cleaned clip
  3. restart  perfect-cuts' speech map finds the false start as its own block
  4. cut      perfect-cuts renders the clip without the false start
  5. check    audio-quality-check: loudness and true peak pass on the cut

The first run downloads the speech model (about 2.5 GB) and the noise model,
so it can take several minutes; later runs take well under a minute.

Exit code: 0 all passed, 1 a step failed. Stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # the plugin folder
CLIP = ROOT / "test-media" / "test-clip.mov"
TRANSCRIBE = ROOT / "scripts" / "transcribe"
ENHANCE = ROOT / "skills" / "audio-enhance" / "scripts" / "audio_enhance.py"
SPEECH_MAP = ROOT / "skills" / "perfect-cuts" / "scripts" / "speech_map.py"
RENDER = ROOT / "skills" / "perfect-cuts" / "scripts" / "render_mp4.py"
ANALYZE = ROOT / "skills" / "audio-quality-check" / "scripts" / "analyze.py"
EXPECTED_WORDS = ("two ideas", "reason", "evidence")


def run(cmd, env, timeout=1800):
    return subprocess.run([str(c) for c in cmd], env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)


def tail(proc):
    text = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    return text[-1] if text else "exit %d" % proc.returncode


def duration(path, env):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nk=1:nw=1", path], env)
    return float(out.stdout.decode().strip() or 0)


def norm(text):
    return re.sub(r"[^a-z ]", "", text.lower()).split()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work", help="folder for the test files (default: a temp folder)")
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    args = ap.parse_args()

    data = os.environ.get("TV_DATA", "")
    env = dict(os.environ)
    extra = [os.path.join(data, "venv", "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    env["PATH"] = os.pathsep.join([p for p in extra if os.path.isdir(p)] + [env.get("PATH", "")])

    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="tv-setup-test-"))
    work.mkdir(parents=True, exist_ok=True)
    clip = work / "test-clip.mov"
    shutil.copyfile(str(CLIP), str(clip))
    results = []

    def record(step, ok, detail, started):
        results.append({"step": step, "status": "PASS" if ok else "FAIL",
                        "detail": detail, "seconds": round(time.time() - started, 1)})
        return ok

    # 1. sound
    t = time.time()
    cleaned = work / "test-clip-cleaned.mov"
    report = work / "enhance-report.json"
    p = run([sys.executable, ENHANCE, clip, cleaned, "--json", report, "--quiet"], env)
    ok = p.returncode == 0 and cleaned.exists()
    detail = tail(p)
    if ok and report.exists():
        try:
            rep = json.loads(report.read_text())
            item = rep[0] if isinstance(rep, list) else rep
            if item.get("output_i") is not None:
                detail = "%.1f -> %.1f LUFS, true peak %.1f dBTP" % (
                    item.get("input_i", 0), item["output_i"], item.get("output_tp", 0))
            else:
                detail = "cleaned file written"
            ok = ok and item.get("status", "OK") != "FAIL"
        except (ValueError, IndexError, AttributeError, TypeError):
            detail = "cleaned file written"
    record("sound", ok, detail, t)

    source = cleaned if ok else clip

    # 2. words
    t = time.time()
    words_json = work / "words.json"
    p = run([TRANSCRIBE, source, "--words", words_json, "--quiet"], env)
    words = []
    if p.returncode == 0 and words_json.exists():
        tx = json.loads(words_json.read_text())
        words = [w.get("word", "").strip() for s in tx.get("segments", []) for w in s.get("words", [])]
    text = " ".join(words)
    ok = all(phrase in " ".join(norm(text)) for phrase in EXPECTED_WORDS)
    record("words", ok, ('heard: "%s"' % text) if words else tail(p), t)

    # 3. restart
    t = time.time()
    map_json = work / "map.json"
    p = run([sys.executable, SPEECH_MAP, source, words_json, "--out", map_json], env)
    blocks, false_starts = [], []
    if p.returncode == 0 and map_json.exists():
        spec = json.loads(map_json.read_text())
        blocks = spec.get("blocks", [])
        for a, b in zip(blocks, blocks[1:]):
            wa, wb = norm(a.get("text", "")), norm(b.get("text", ""))
            if wa and len(wb) > len(wa) and wb[:len(wa)] == wa:
                false_starts.append(a["i"])
    ok = bool(false_starts)
    record("restart", ok,
           ("%d blocks; false start in block %s" % (len(blocks), ", ".join(map(str, false_starts))))
           if blocks else tail(p), t)

    # 4. cut
    t = time.time()
    cut = work / "test-clip-cut.mp4"
    ok = False
    detail = "skipped: no speech map"
    if blocks:
        spec = json.loads(map_json.read_text())
        fps = spec["fps"]
        clips = []
        for b in blocks:
            if b["i"] in false_starts or not b.get("text"):
                continue
            clips.append({"in_frame": int(b["onset"] * fps),
                          "out_frame": int(-(-b["end"] * fps // 1)) + 1,
                          "text": b["text"]})
        cuts = {"source": str(source), "fps": fps, "width": spec.get("width"),
                "height": spec.get("height"), "samplerate": spec.get("samplerate"),
                "source_duration": spec.get("duration"),
                "sequence_name": "setup test cut", "output": str(cut), "clips": clips}
        cuts_json = work / "cuts.json"
        cuts_json.write_text(json.dumps(cuts, indent=2))
        p = run([sys.executable, RENDER, cuts_json, cut], env)
        if p.returncode == 0 and cut.exists():
            before, after = duration(source, env), duration(cut, env)
            ok = 0 < after < before - 1.0
            detail = "%.1f s -> %.1f s, %d clips" % (before, after, len(clips))
        else:
            detail = tail(p)
    record("cut", ok, detail, t)

    # 5. check
    t = time.time()
    target = cut if cut.exists() else source
    p = run([sys.executable, ANALYZE, "--json", target], env)
    ok, detail = False, tail(p)
    try:
        res = json.loads(p.stdout.decode())
        status = {c["check"]: c["status"] for c in res.get("checks", [])}
        loud = status.get("Integrated loudness")
        peak = status.get("True peak / clipping")
        ok = loud == "PASS" and peak == "PASS"
        detail = "loudness %s, true peak %s (overall %s)" % (loud, peak, res.get("verdict"))
    except ValueError:
        pass
    record("check", ok, detail, t)

    all_ok = all(r["status"] == "PASS" for r in results)
    if args.json:
        print(json.dumps({"passed": all_ok, "work": str(work), "steps": results}, indent=2))
    else:
        names = {"sound": "Sound cleanup", "words": "Transcription", "restart": "Finds the restart",
                 "cut": "Cuts the restart", "check": "Sound check on the cut"}
        print("Setup test (files in %s)" % work)
        for r in results:
            print("  %-24s %-4s  %s" % (names[r["step"]], r["status"], r["detail"]))
        print("Result: %s" % ("all steps passed." if all_ok else "a step failed; see above."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
