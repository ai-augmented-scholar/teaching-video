#!/usr/bin/env python3
"""
Local audio quality analyzer. ffmpeg only, Python standard library only.

Runs a six-point quality check on a spoken-word audio or video file and
reports pass/warn/fail per check, with a recommended fix.

Everything is computed on this machine. No upload, no API key.

Deliberately stdlib-only and Python 3.9 compatible, so the macOS system
python3 runs it with no private environment.

Usage:
    analyze.py <input> [<input> ...] [--json] [--target-lufs -16]
                                     [--ceiling-dbtp -1.5] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

AUDIO_EXT = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".aiff", ".aif", ".ogg", ".opus", ".caf"}
VIDEO_EXT = {".mov", ".mp4", ".mkv", ".m4v", ".avi", ".webm"}

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
MARK = {PASS: "[ok]", WARN: "[!!]", FAIL: "[XX]"}
RANK = {PASS: 0, WARN: 1, FAIL: 2}


# --------------------------------------------------------------------------
# ffmpeg plumbing
# --------------------------------------------------------------------------

# A GUI-launched app or a bare shell may lack Homebrew on PATH. Add the two
# usual Homebrew locations so ffmpeg is found the same way everywhere.
for _extra in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _extra not in os.environ.get("PATH", "").split(":"):
        os.environ["PATH"] = os.environ.get("PATH", "") + ":" + _extra


def need_tool(name):
    path = shutil.which(name)
    if not path:
        sys.exit(
            "%s not found on PATH.\n"
            "Run /video-teach-plugin:setup, or install it with: brew install ffmpeg" % name
        )
    return path


def run(cmd):
    """Run a command, return (stdout, stderr). ffmpeg writes stats to stderr."""
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        errors="replace",
    )
    return proc.stdout, proc.stderr


def probe(path):
    """Container and stream facts from ffprobe."""
    out, _ = run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample"
        ":format=duration",
        "-of", "json", path,
    ])
    try:
        data = json.loads(out)
    except ValueError:
        return {}
    streams = data.get("streams") or [{}]
    stream = streams[0]
    fmt = data.get("format") or {}

    def as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    depth = as_int(stream.get("bits_per_raw_sample")) or as_int(stream.get("bits_per_sample"))
    duration = None
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        pass

    return {
        "codec": stream.get("codec_name"),
        "sample_rate": as_int(stream.get("sample_rate")),
        "channels": as_int(stream.get("channels")),
        "bit_depth": depth or None,
        "duration_s": duration,
    }


def ebur128(path):
    """Integrated loudness, loudness range and true peak, from one R128 scan."""
    _, err = run([
        "ffmpeg", "-nostats", "-hide_banner", "-i", path,
        "-filter:a", "ebur128=peak=true:framelog=verbose",
        "-f", "null", "-",
    ])
    # The summary block sits at the end. Parse it, not the per-frame log.
    tail = err[err.rfind("Summary:"):] if "Summary:" in err else err

    def grab(label):
        # \b anchors the label so "I" does not match inside another token.
        m = re.search(
            r"\b" + re.escape(label) + r":\s*(-?\d+(?:\.\d+)?|-inf)", tail
        )
        if not m:
            return None
        value = m.group(1)
        return float("-inf") if value == "-inf" else float(value)

    return {
        "integrated_lufs": grab("I"),
        "loudness_range_lu": grab("LRA"),
        "true_peak_dbtp": grab("Peak"),
        "threshold_lufs": grab("Threshold"),
    }


# A window of pure digital silence reports -inf dBFS. Such windows are kept in
# the list at this floor value so the window count stays aligned with the
# timeline, then filtered out before any statistic is computed.
SILENCE_FLOOR_DBFS = -120.0

# 0.05 s windows. Short enough to land inside the gaps between words, which is
# the only place the room noise is audible on its own. Measured against three
# fixtures with a known injected floor, the 5th percentile of these windows
# lands within about 1 dB of the true floor; 0.25 s windows miss it by 20 dB,
# because at that length every window still contains some speech.
FLOOR_WINDOW_SAMPLES = 2400
FLOOR_WINDOW_SECONDS = FLOOR_WINDOW_SAMPLES / 48000.0

# The level-consistency measure needs a longer window than the floor does, or
# it reads syllable-to-syllable variation instead of delivery. Five short
# windows are averaged in the power domain to make one 0.25 s block.
BLOCK_FACTOR = 5


def window_rms(path):
    """
    One RMS value (dBFS) per 0.05 s of audio.

    asetnsamples fixes the window, so the numbers do not depend on the source
    codec's own frame size.
    """
    _, err = run([
        "ffmpeg", "-nostats", "-hide_banner", "-i", path,
        "-af",
        "aresample=48000,asetnsamples=n=%d:p=0,"
        "astats=metadata=1:reset=1,"
        "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level"
        % FLOOR_WINDOW_SAMPLES,
        "-f", "null", "-",
    ])
    values = []
    for m in re.finditer(r"lavfi\.astats\.Overall\.RMS_level=(-?\d+(?:\.\d+)?|-inf)", err):
        raw = m.group(1)
        values.append(SILENCE_FLOOR_DBFS if raw == "-inf" else float(raw))
    return values


def to_blocks(values, factor=BLOCK_FACTOR):
    """Average groups of short windows into longer blocks, in the power domain."""
    blocks = []
    for i in range(0, len(values) - factor + 1, factor):
        group = values[i:i + factor]
        power = sum(10 ** (v / 10.0) for v in group) / float(factor)
        blocks.append(10 * math.log10(power) if power > 0 else SILENCE_FLOOR_DBFS)
    return blocks


def astats_overall(path):
    """Whole-file astats: peak level, DC offset, clipped-sample count, flatness."""
    _, err = run([
        "ffmpeg", "-nostats", "-hide_banner", "-i", path,
        "-af", "astats=measure_perchannel=none",
        "-f", "null", "-",
    ])

    def grab(label, cast=float):
        m = re.search(re.escape(label) + r":\s*(-?\d+(?:\.\d+)?|-inf|nan)", err)
        if not m:
            return None
        raw = m.group(1)
        if raw in ("-inf", "nan"):
            return None
        try:
            return cast(raw)
        except ValueError:
            return None

    # ffmpeg spells the RMS trough "RMS through dB" in some builds. Accept both.
    trough = grab("RMS trough dB")
    if trough is None:
        trough = grab("RMS through dB")

    return {
        "peak_dbfs": grab("Peak level dB"),
        "rms_dbfs": grab("RMS level dB"),
        "rms_trough_dbfs": trough,
        "dc_offset": grab("DC offset"),
        "flat_factor": grab("Flat factor"),
        "peak_count": grab("Peak count", lambda v: int(float(v))),
        "astats_noise_floor_dbfs": grab("Noise floor dB"),
    }


def long_silences(path, threshold_db, min_seconds):
    """Stretches of near-silence longer than min_seconds."""
    _, err = run([
        "ffmpeg", "-nostats", "-hide_banner", "-i", path,
        "-af", "silencedetect=noise=%ddB:d=%s" % (threshold_db, min_seconds),
        "-f", "null", "-",
    ])
    gaps = []
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*(-?[\d.]+)", err)]
    ends = re.finditer(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", err)
    for i, m in enumerate(ends):
        start = starts[i] if i < len(starts) else None
        gaps.append({
            "start_s": round(start, 2) if start is not None else None,
            "end_s": round(float(m.group(1)), 2),
            "duration_s": round(float(m.group(2)), 2),
        })
    # A file that fades out at the end leaves a silence_start with no end.
    if len(starts) > len(gaps):
        gaps.append({
            "start_s": round(starts[-1], 2),
            "end_s": None,
            "duration_s": None,
            "note": "runs to end of file",
        })
    return gaps


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def speech_window_stats(rms_values):
    """
    Derive the noise floor, the speech level, and the spread between them.

    Two resolutions, both from the one pass of 0.05 s windows:

    - The noise floor is the 5th percentile of the short windows. Short windows
      fall inside the gaps between words, where the room noise stands alone.
    - The level spread and the speech level come from 0.25 s blocks, which
      measure delivery rather than syllable-to-syllable variation.

    A file too short for a stable estimate returns nothing rather than a number
    that would be noise.
    """
    empty = {"noise_floor_dbfs": None, "speech_rms_dbfs": None,
             "level_spread_db": None, "snr_db": None, "speech_blocks": 0,
             "gated_fraction": 0.0}
    if len(rms_values) < 100:  # under 5 s
        return empty

    # Windows of pure digital silence are an edit artifact — a gate, a cut, or
    # padding — not room tone. They must not set the floor and must not count
    # as speech, or a single spliced gap ruins both numbers.
    audible = [v for v in rms_values if v > SILENCE_FLOOR_DBFS + 1.0]
    gated_fraction = 1.0 - (len(audible) / float(len(rms_values)))
    if len(audible) < 100:
        return empty

    floor = percentile(audible, 5)

    blocks = [v for v in to_blocks(rms_values) if v > SILENCE_FLOOR_DBFS + 1.0]
    if len(blocks) < 8:
        return empty

    # Speech is everything well clear of the floor. If the voice never pauses,
    # that test keeps almost everything, so fall back to the loud half.
    speech = [v for v in blocks if v >= floor + 15.0]
    if len(speech) < 8 or len(speech) > 0.98 * len(blocks):
        speech = [v for v in blocks if v >= percentile(blocks, 50)]
    if len(speech) < 4:
        return empty

    median = percentile(speech, 50)
    spread = percentile(speech, 90) - percentile(speech, 10)

    return {
        "noise_floor_dbfs": round(floor, 1),
        "speech_rms_dbfs": round(median, 1),
        "level_spread_db": round(spread, 1),
        "snr_db": round(median - floor, 1),
        "speech_blocks": len(speech),
        "gated_fraction": round(gated_fraction, 3),
    }


# --------------------------------------------------------------------------
# the six checks
# --------------------------------------------------------------------------

def band(value, pass_lo, pass_hi, warn_lo, warn_hi):
    """Two-sided verdict: inside pass band, inside warn band, else fail."""
    if value is None:
        return WARN
    if pass_lo <= value <= pass_hi:
        return PASS
    if warn_lo <= value <= warn_hi:
        return WARN
    return FAIL


def build_checks(m, target_lufs, ceiling_dbtp):
    checks = []

    # 1. Integrated loudness
    lufs = m["ebur128"]["integrated_lufs"]
    checks.append({
        "id": "loudness",
        "check": "Integrated loudness",
        "value": "%.1f LUFS" % lufs if lufs is not None else "not measured",
        "target": "%.1f LUFS" % target_lufs,
        "status": band(lufs, target_lufs - 1.5, target_lufs + 1.5,
                       target_lufs - 3.0, target_lufs + 3.0),
        "fix": "Normalize to %.1f LUFS at the END of the chain, then limit. "
               "Run /video-teach-plugin:audio-enhance; it does this." % target_lufs,
    })

    # 2. True peak / clipping
    tp = m["ebur128"]["true_peak_dbtp"]
    if tp is None:
        tp_status = WARN
    elif tp <= ceiling_dbtp:
        tp_status = PASS
    elif tp < 0.0:
        tp_status = WARN
    else:
        tp_status = FAIL
    checks.append({
        "id": "true_peak",
        "check": "True peak / clipping",
        "value": "%.1f dBTP" % tp if tp is not None else "not measured",
        "target": "at or below %.1f dBTP" % ceiling_dbtp,
        "status": tp_status,
        "fix": "Run /video-teach-plugin:audio-enhance; its last stage is a "
               "true-peak limiter (alimiter=limit=%.3f, that is %.1f dBTP)."
               % (10 ** (ceiling_dbtp / 20.0), ceiling_dbtp),
    })

    # 3. Noise floor
    floor = m["windows"]["noise_floor_dbfs"]
    if floor is None:
        floor_status, floor_text = WARN, "file too short to measure"
    else:
        floor_text = "%.1f dBFS" % floor
        if floor <= -60.0:
            floor_status = PASS
        elif floor <= -50.0:
            floor_status = WARN
        else:
            floor_status = FAIL
    checks.append({
        "id": "noise_floor",
        "check": "Background noise floor",
        "value": floor_text,
        "target": "at or below -60 dBFS",
        "status": floor_status,
        "fix": "Run /video-teach-plugin:audio-enhance (DeepFilterNet noise removal), "
               "or fix the room: fan, AC, computer, hard reflective surfaces.",
    })

    # 4. Long silences
    gaps = m["silences"]
    long_gaps = [g for g in gaps if (g.get("duration_s") or 0) >= 2.0]
    if len(long_gaps) == 0:
        gap_status = PASS
    elif len(long_gaps) <= 3:
        gap_status = WARN
    else:
        gap_status = FAIL
    checks.append({
        "id": "silences",
        "check": "Long silences",
        "value": "%d gap(s) of 2 s or more" % len(long_gaps),
        "target": "none over 2 s",
        "status": gap_status,
        "fix": "Cut the dead air. /video-teach-plugin:perfect-cuts removes it from a "
               "talking-head take.",
    })

    # 5. Level consistency
    spread = m["windows"]["level_spread_db"]
    lra = m["ebur128"]["loudness_range_lu"]
    if spread is None:
        spread_status = WARN
        spread_text = "not measured"
    else:
        spread_text = "%.1f dB spread" % spread
        if spread <= 8.0:
            spread_status = PASS
        elif spread <= 13.0:
            spread_status = WARN
        else:
            spread_status = FAIL
    if lra is not None:
        spread_text += " (LRA %.1f LU)" % lra
    checks.append({
        "id": "level_consistency",
        "check": "Level consistency",
        "value": spread_text,
        "target": "8 dB or less across speech",
        "status": spread_status,
        "fix": "Compress before you normalize, or stay a fixed distance from "
               "the mic. A swinging level usually means head movement.",
    })

    # 6. Clarity (composite: signal-to-noise, sample rate, DC offset)
    snr = m["windows"]["snr_db"]
    rate = m["probe"].get("sample_rate")
    dc = m["astats"].get("dc_offset")
    faults = []
    if snr is None:
        clarity_status = WARN
    elif snr >= 40.0:
        clarity_status = PASS
    elif snr >= 30.0:
        clarity_status = WARN
        faults.append("signal-to-noise under 40 dB")
    else:
        clarity_status = FAIL
        faults.append("signal-to-noise under 30 dB")
    if rate is not None and rate < 44100:
        clarity_status = FAIL
        faults.append("sample rate %d Hz is below 44.1 kHz" % rate)
    if dc is not None and abs(dc) > 0.01:
        if clarity_status == PASS:
            clarity_status = WARN
        faults.append("DC offset %.3f" % dc)
    if snr is None:
        snr_text = "SNR not measured"
    else:
        snr_text = "SNR %.1f dB" % snr
    checks.append({
        "id": "clarity",
        "check": "Clarity",
        "value": snr_text + ("; " + "; ".join(faults) if faults else ""),
        "target": "SNR 40 dB or better, 44.1 kHz or higher, no DC offset",
        "status": clarity_status,
        "fix": "Raise the mic gain and lower the room noise so the voice sits "
               "40 dB above the floor. Record at 48 kHz.",
    })

    return checks


# --------------------------------------------------------------------------
# per-file driver
# --------------------------------------------------------------------------

def analyze(path, target_lufs, ceiling_dbtp):
    m = {
        "file": os.path.abspath(path),
        "probe": probe(path),
        "ebur128": ebur128(path),
        "astats": astats_overall(path),
        "silences": long_silences(path, -45, 2.0),
    }
    rms = window_rms(path)
    m["windows"] = speech_window_stats(rms)
    m["windows"]["total_windows"] = len(rms)
    m["windows"]["window_seconds"] = FLOOR_WINDOW_SECONDS

    checks = build_checks(m, target_lufs, ceiling_dbtp)
    worst = max((RANK[c["status"]] for c in checks), default=0)
    verdict = [PASS, WARN, FAIL][worst]

    return {
        "file": m["file"],
        "verdict": verdict,
        "publishable": verdict != FAIL,
        "measurements": m,
        "checks": checks,
    }


def fmt_duration(seconds):
    if not seconds:
        return "unknown"
    minutes, secs = divmod(int(round(seconds)), 60)
    return "%d:%02d" % (minutes, secs)


def print_report(result, show_verdict=True):
    p = result["measurements"]["probe"]
    print("")
    print("=" * 76)
    print(os.path.basename(result["file"]))
    print("%s | %s Hz | %s ch | %s | %s"
          % (p.get("codec") or "?", p.get("sample_rate") or "?",
             p.get("channels") or "?",
             ("%d-bit" % p["bit_depth"]) if p.get("bit_depth") else "?",
             fmt_duration(p.get("duration_s"))))
    print("=" * 76)
    for c in result["checks"]:
        print("%s %-24s %s" % (MARK[c["status"]], c["check"], c["value"]))
        if c["status"] != PASS:
            print("     target: %s" % c["target"])
            print("     fix:    %s" % c["fix"])
    print("-" * 76)
    if not show_verdict:
        # Gate mode (make-video's aqc_gate.py): the gate prints its own
        # verdict first, so this table must not add a contradicting one.
        print("")
        return
    verdict = result["verdict"]
    if verdict == PASS:
        print("VERDICT: PASS - ready to publish.")
    elif verdict == WARN:
        print("VERDICT: WARN - publishable, but the flagged items are worth fixing.")
    else:
        print("VERDICT: FAIL - fix the flagged items before you publish.")
    print("")


def collect_inputs(paths):
    files = []
    for raw in paths:
        if os.path.isdir(raw):
            for entry in sorted(os.listdir(raw)):
                ext = os.path.splitext(entry)[1].lower()
                if ext in AUDIO_EXT or ext in VIDEO_EXT:
                    files.append(os.path.join(raw, entry))
        elif os.path.isfile(raw):
            files.append(raw)
        else:
            sys.exit("Not found: %s" % raw)
    if not files:
        sys.exit("No audio or video files found in the given path(s).")
    return files


def main():
    ap = argparse.ArgumentParser(description="Local six-point audio quality check.")
    ap.add_argument("inputs", nargs="+", help="audio file, video file, or folder")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--target-lufs", type=float, default=-16.0)
    ap.add_argument("--ceiling-dbtp", type=float, default=-1.5)
    ap.add_argument("--quiet", action="store_true", help="verdict lines only")
    ap.add_argument("--no-verdict", action="store_true",
                    help="table without the VERDICT line (used by a caller that "
                         "prints its own verdict)")
    args = ap.parse_args()

    need_tool("ffmpeg")
    need_tool("ffprobe")

    results = [analyze(f, args.target_lufs, args.ceiling_dbtp)
               for f in collect_inputs(args.inputs)]

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    elif args.quiet:
        for r in results:
            print("%s %s" % (MARK[r["verdict"]], os.path.basename(r["file"])))
    else:
        for r in results:
            print_report(r, show_verdict=not args.no_verdict)

    worst = max(RANK[r["verdict"]] for r in results)
    sys.exit(0 if worst == 0 else (1 if worst == 1 else 2))


if __name__ == "__main__":
    main()
