#!/usr/bin/env python3
"""audio_enhance.py — the audio-enhance skill as one deterministic script.

Chain (see SKILL.md for every reason behind every number):

  working-level normalize (-15 LUFS, two-pass)
  -> DeepFilterNet noise removal, strength from the measured noise floor
  -> 3-band EQ (+1.5 / -2.5 / +2.6 dB)          [skipped with --no-eq]
  -> compressor  (-14 dB, 3:1, 10 ms or 1 ms attack, 100 ms release)
  -> peak limiter (-6 dB, level=disabled)
  -> delivery normalize (default -16 LUFS / -1.5 dBTP, two-pass, linear)
  -> true-peak ceiling (-1.0 dBFS, level=disabled)
  -> verification (not silent, loudness in band, true peak under ceiling, duration)
  -> [video inputs] 50 ms duration gate -> remux with -c:v copy -> muxed-file checks

Audio in, audio out (WAV). Video in, video out (same container, original audio
dropped, video stream untouched). The source file is never modified.

Usage:
  audio_enhance.py <input> [output] [--audio-only] [--alternative]
                   [--target-lufs -16] [--ceiling-dbtp -1.5] [--no-eq]
                   [--json report.json] [--keep-temp] [--quiet]

Exit code 0 when every file passed, 1 when any file failed. One line per
failing file on stderr, a summary table per file on stdout, and the same data
as JSON with --json for agent workflows.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- constants
WORKING_LUFS = -15.0          # Step 2: what the fixed-threshold compressor expects
WORKING_TP = -1.5
LRA_PARAM = 11
DEFAULT_TARGET_LUFS = -16.0   # Step 8: delivery target, recommended band -18..-16
DEFAULT_CEILING_DBTP = -1.5
CEILING_LIMIT = "0.891"       # -1.0 dBFS hard catch after the delivery normalize
HARD_TP_MAX = -0.7            # -1.0 dBFS catch + 0.3 dB allowance for inter-sample (true) peaks
PEAK_LIMIT = "0.501"          # -6 dB peak limiter (Step 6)
EQ_CHAIN = "lowshelf=f=200:g=1.5,equalizer=f=1000:width_type=o:width=2:g=-2.5,highshelf=f=4000:g=2.6"
COMPRESSOR = "acompressor=threshold=-14dB:ratio=3:attack={attack}:release=100:makeup=1"
PEAK_LIMITER = f"alimiter=level=disabled:limit={PEAK_LIMIT}:attack=5:release=60"
CEILING_LIMITER = f"alimiter=level=disabled:limit={CEILING_LIMIT}:attack=5:release=60"
ATTACK = {"standard": 10, "alternative": 1}
DURATION_TOLERANCE_MS = 50.0
EXTRACT_TOLERANCE_MS = 200.0   # extracted WAV vs the source audio stream's declared duration (codec priming)
START_TOLERANCE_MS = 25.0      # muxed audio start vs the source audio start (relative to video)
VIDEO_COPY_TOLERANCE_MS = 5.0  # stream-copied video vs the source video stream duration
SILENT_MEAN_DB = -80.0
LOUDNESS_TOLERANCE_LU = 1.0
LOUDNESS_FLOOR_LUFS = -18.0
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".wma", ".caf"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts", ".mxf"}

QUIET = False


def log(msg):
    if not QUIET:
        print(msg, file=sys.stderr, flush=True)


class StepError(Exception):
    pass


# ---------------------------------------------------------------- tool lookup
# Lookup order, shared by every script in the plugin:
#   1. $TV_DATA/venv/bin/<tool>  (the plugin's private environment; the skill
#      passes TV_DATA, because the plugin data folder is not in the Bash env)
#   2. ~/.local/bin/<tool>
#   3. PATH, then /opt/homebrew/bin and /usr/local/bin (a GUI- or launchd-started
#      process often has a bare PATH without Homebrew)
def _executable(p):
    p = Path(p).expanduser()
    return str(p) if p.is_file() and os.access(p, os.X_OK) else None


def find_tool(name, extra_dirs=("/opt/homebrew/bin", "/usr/local/bin")):
    tv_data = os.environ.get("TV_DATA")
    if tv_data:
        hit = _executable(Path(tv_data) / "venv" / "bin" / name)
        if hit:
            return hit
    hit = _executable(Path("~/.local/bin") / name)
    if hit:
        return hit
    p = shutil.which(name)
    if p:
        return p
    for d in extra_dirs:
        hit = _executable(Path(d) / name)
        if hit:
            return hit
    return None


# DeepFilterNet needs Python 3.11 (deepfilterlib has no 3.12+ wheels), so the
# plugin's setup skill installs it into the private environment at
# $TV_DATA/venv. DEEPFILTER_BIN (full path to a deepFilter) overrides the lookup.
DEEPFILTER_HINT = ("run the plugin's setup skill (/video-teach-plugin:setup), which installs "
                   "DeepFilterNet into the plugin's own environment "
                   "(or set DEEPFILTER_BIN to an existing deepFilter)")


def find_deepfilter():
    env = os.environ.get("DEEPFILTER_BIN")
    if env:
        hit = _executable(env)
        if hit:
            return hit
        print(f"WARNING: DEEPFILTER_BIN={env} is not an executable file; searching the defaults", file=sys.stderr)
    return find_tool("deepFilter")


def check_tools():
    tools = {
        "ffmpeg": find_tool("ffmpeg"),
        "ffprobe": find_tool("ffprobe"),
        "deepFilter": find_deepfilter(),
    }
    hints = {
        "ffmpeg": "brew install ffmpeg",
        "ffprobe": "brew install ffmpeg",
        "deepFilter": DEEPFILTER_HINT,
    }
    missing = [t for t, p in tools.items() if not p]
    if missing:
        for t in missing:
            print(f"MISSING {t}: install with  {hints[t]}", file=sys.stderr)
        sys.exit(2)
    return tools


def run(cmd, check=True):
    """Run a command, return (returncode, stdout, stderr). Never reads stdin."""
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    if check and r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-8:])
        raise StepError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- probes
def probe(T, path):
    _, out, _ = run([T["ffprobe"], "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(out)


def classify(info):
    """Return ('audio'|'video'|'video-no-audio'|'none', video_stream, audio_stream)."""
    v = a = None
    for s in info.get("streams", []):
        ct = s.get("codec_type")
        if ct == "video" and v is None:
            attached = int(s.get("disposition", {}).get("attached_pic", 0)) == 1
            fr = s.get("r_frame_rate", "0/0")
            still = s.get("codec_name") in ("mjpeg", "png", "bmp", "gif") and fr in ("0/0", "0/1", "")
            if not (attached or still):
                v = s
        elif ct == "audio" and a is None:
            a = s
    if v and a:
        return "video", v, a
    if v and not a:
        return "video-no-audio", v, None
    if a:
        return "audio", None, a
    return "none", None, None


def fmt_duration(info):
    d = info.get("format", {}).get("duration")
    return float(d) if d else None


def stream_duration(T, path, sel):
    _, out, _ = run([T["ffprobe"], "-v", "error", "-select_streams", sel, "-show_entries", "stream=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    out = out.strip().splitlines()
    return float(out[0]) if out and out[0] not in ("", "N/A") else None


def sample_rate(T, path):
    _, out, _ = run([T["ffprobe"], "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return int(out.strip().splitlines()[0]) if out.strip() else None


def loudnorm_measure(T, path, I, TP):
    _, _, err = run([T["ffmpeg"], "-nostdin", "-hide_banner", "-i", str(path),
                     "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA_PARAM}:print_format=json", "-f", "null", "-"])
    m = re.findall(r"\{[^{}]*\}", err, re.S)
    if not m:
        raise StepError("loudnorm printed no JSON block")
    d = json.loads(m[-1])
    for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        if k not in d:
            raise StepError(f"loudnorm JSON lacks {k}")
    return d


def volumedetect(T, path, ss=None, to=None):
    cmd = [T["ffmpeg"], "-nostdin", "-hide_banner"]
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}", "-to", f"{to:.3f}"]
    cmd += ["-i", str(path), "-af", "volumedetect", "-f", "null", "-"]
    _, _, err = run(cmd)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)", err)
    mx = re.search(r"max_volume:\s*(-?[\d.]+|-inf)", err)
    f = lambda m: (float("-inf") if m and m.group(1) == "-inf" else float(m.group(1))) if m else None
    return f(mean), f(mx)


# ---------------------------------------------------------------- Step 3 helpers
def find_pause(T, path):
    """Longest silence at -38 dB / 0.35 s. Returns (start, end) or None."""
    _, _, err = run([T["ffmpeg"], "-nostdin", "-hide_banner", "-i", str(path),
                     "-af", "silencedetect=noise=-38dB:d=0.35", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", err)]
    pairs = [(s, e) for s, e in zip(starts, ends) if e > s]
    if not pairs:
        return None
    return max(pairs, key=lambda p: p[1] - p[0])


def quietest_windows(T, path, n=8):
    """Upper bound on the floor from the n quietest ~85 ms RMS windows (gap-removed files)."""
    _, out, _ = run([T["ffmpeg"], "-nostdin", "-hide_banner", "-i", str(path),
                     "-af", "astats=metadata=1:reset=6,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                     "-f", "null", "-"])
    vals = []
    for m in re.finditer(r"RMS_level=(-?[\d.]+|-inf)", out):
        v = m.group(1)
        if v != "-inf":
            vals.append(float(v))
    vals.sort()
    low = vals[:n]
    if not low:
        return None
    return sorted(low)[len(low) // 2]  # median of the quietest windows


def atten_for_floor(floor_db):
    if floor_db is None:
        return 20, "floor unmeasured — default"
    if floor_db < -55:
        return 12, "already clean; heavy attenuation only costs naturalness"
    if floor_db <= -40:
        return 20, "the default"
    return 30, "audibly noisy room — a mic/room problem this chain can only paper over"


# ---------------------------------------------------------------- one file
def process_file(T, src, out_path, opts, tmp_root):
    src = Path(src).resolve()
    rep = {"input": str(src), "status": "FAILED", "steps": [], "warnings": [], "checks": {}}
    stem = src.stem
    tmp = Path(tempfile.mkdtemp(prefix=f"{stem[:40]}_", dir=tmp_root))
    keep_tmp = opts.keep_temp

    if "_enhanced" in stem:
        rep["warnings"].append("input name contains '_enhanced' — this chain assumes a RAW recording; "
                               "never re-process a previous output")

    try:
        # ---- Step 1: classify
        info = probe(T, src)
        kind, vstream, astream = classify(info)
        if kind == "none":
            raise StepError("no audio or video stream found")
        if kind == "video-no-audio":
            raise StepError("video has no audio stream — nothing to enhance")
        is_video = kind == "video" and not opts.audio_only
        rep["input_kind"] = kind
        rep["mode"] = "video->video" if is_video else ("video->wav (--audio-only)" if kind == "video" else "audio->wav")
        src_duration = fmt_duration(info)
        rep["source_duration_s"] = src_duration
        # The container duration is NOT the reference for the duration gate: on a macOS camera
        # capture (QuickTime Player, Continuity Camera) it runs longer than both streams, and the
        # audio stream starts tens of ms after the video (measured: 51 and 87 ms on two Mac
        # camera captures). The gate below compares the final WAV against the EXTRACTED
        # WAV (did the chain change the length?), and the remux restores the audio start offset
        # so the enhanced track lands where the original one played.
        src_audio_duration = float(astream["duration"]) if astream.get("duration") not in (None, "N/A") else None
        a_start = float(astream.get("start_time") or 0.0)
        v_start = float(vstream.get("start_time") or 0.0) if vstream else 0.0
        audio_offset_s = a_start - v_start if vstream else 0.0
        rep["source_audio_duration_s"] = src_audio_duration
        rep["source_audio_offset_s"] = audio_offset_s
        log(f"[1/10] {src.name}: {rep['mode']}, container {src_duration:.3f} s, audio stream "
            f"{src_audio_duration if src_audio_duration is None else round(src_audio_duration, 3)} s, "
            f"audio starts {audio_offset_s * 1000:+.1f} ms vs video")

        # resolve output
        if out_path is None:
            if is_video:
                dest = src.with_name(f"{stem}_enhanced-audio{src.suffix}")
            else:
                dest = src.with_name(f"{stem}_enhanced.wav")
        else:
            dest = Path(out_path)
            if dest.is_dir() or (out_path.endswith(os.sep)):
                dest.mkdir(parents=True, exist_ok=True)
                dest = dest / (f"{stem}_enhanced-audio{src.suffix}" if is_video else f"{stem}_enhanced.wav")
        if dest.resolve() == src:
            raise StepError("output path equals the source; the source is never modified in place")
        rep["deliverable"] = str(dest)

        wav48 = tmp / f"{stem}_48k.wav"
        run([T["ffmpeg"], "-nostdin", "-hide_banner", "-y", "-i", str(src), "-vn", "-ar", "48000", "-ac", "1", str(wav48)])
        d0 = stream_duration(T, wav48, "a:0")
        rep["steps"].append({"step": "extract", "duration_s": d0})
        # Extraction may differ from the stream's declared duration by the codec's priming
        # samples (tens of ms). Anything beyond that means the extraction itself lost or
        # padded audio, and no later gate could tell — so refuse here.
        if src_audio_duration and d0 and abs(d0 - src_audio_duration) * 1000.0 > EXTRACT_TOLERANCE_MS:
            raise StepError(f"extracted WAV is {d0:.3f} s but the source audio stream is {src_audio_duration:.3f} s "
                            f"(> {EXTRACT_TOLERANCE_MS:.0f} ms apart) — extraction changed the length")
        rep["extract_vs_source_audio_ms"] = abs(d0 - src_audio_duration) * 1000.0 if (src_audio_duration and d0) else None

        # ---- Step 2: working-level normalize (two-pass)
        m2 = loudnorm_measure(T, wav48, WORKING_LUFS, WORKING_TP)
        rep["input_i"] = float(m2["input_i"])
        rep["input_tp"] = float(m2["input_tp"])
        rep["input_lra"] = float(m2["input_lra"])
        log(f"[2/10] input {rep['input_i']:.1f} LUFS, {rep['input_tp']:.1f} dBTP, LRA {rep['input_lra']:.1f}")
        normalized = tmp / f"{stem}_normalized.wav"
        af = (f"loudnorm=I={WORKING_LUFS}:TP={WORKING_TP}:LRA={LRA_PARAM}:measured_I={m2['input_i']}:"
              f"measured_TP={m2['input_tp']}:measured_LRA={m2['input_lra']}:measured_thresh={m2['input_thresh']}:"
              f"offset={m2['target_offset']}:linear=true")
        run([T["ffmpeg"], "-nostdin", "-hide_banner", "-y", "-i", str(wav48), "-af", af, "-ar", "48000", str(normalized)])
        sr = sample_rate(T, normalized)
        if sr != 48000:
            raise StepError(f"working normalize came out at {sr} Hz, not 48000 — the loudnorm 192 kHz quirk")
        m2b = loudnorm_measure(T, normalized, WORKING_LUFS, WORKING_TP)
        lra_after = float(m2b["input_lra"])
        rep["working_lufs"] = float(m2b["input_i"])
        rep["working_lra"] = lra_after
        went_dynamic = lra_after < rep["input_lra"] - 0.5
        rep["working_stage_dynamic"] = went_dynamic
        if went_dynamic:
            rep["warnings"].append(f"working-level stage went DYNAMIC: LRA {rep['input_lra']:.2f} -> {lra_after:.2f} LU. "
                                   "Usually acceptable (evens out level between passages); the source could not reach "
                                   "-15 LUFS linearly without passing the true-peak limit — a capture-gain matter.")
        d2 = stream_duration(T, normalized, "a:0")
        rep["steps"].append({"step": "working_normalize", "duration_s": d2, "lufs": rep["working_lufs"], "lra": lra_after})

        # ---- Step 3: noise floor -> DeepFilterNet
        pause = find_pause(T, normalized)
        if pause:
            _, floor = volumedetect(T, normalized, pause[0], pause[1])
            floor_src = f"pause {pause[0]:.2f}-{pause[1]:.2f} s (max_volume)"
        else:
            floor = quietest_windows(T, normalized)
            floor_src = "upper bound from the quietest ~85 ms inter-word windows (no pause ≥0.35 s found)"
            rep["warnings"].append("no pause found — noise floor is an upper bound from inter-word gaps, not measured room tone")
        if floor is not None and floor == float("-inf"):
            floor = -120.0
        atten, why = atten_for_floor(floor)
        rep["noise_floor_dbfs"] = floor
        rep["noise_floor_source"] = floor_src
        rep["atten_lim"] = atten
        if atten == 30:
            rep["warnings"].append(f"noise floor {floor:.1f} dBFS is above -40 dBFS: audibly noisy room. "
                                   "Denoised at --atten-lim 30, but the fix is upstream (mic, room).")
        log(f"[3/10] noise floor {floor if floor is None else round(floor, 1)} dBFS ({floor_src}) -> --atten-lim {atten} ({why})")
        dn_dir = tmp / "denoised"
        dn_dir.mkdir()
        run([T["deepFilter"], str(normalized), "--atten-lim", str(atten), "-m", "DeepFilterNet3", "--no-suffix", "-o", str(dn_dir)])
        denoised = dn_dir / normalized.name
        if not denoised.exists():
            cands = list(dn_dir.glob("*.wav"))
            if not cands:
                raise StepError("deepFilter produced no output file")
            denoised = cands[0]
        d3 = stream_duration(T, denoised, "a:0")
        rep["steps"].append({"step": "denoise", "duration_s": d3})
        if sample_rate(T, denoised) != 48000:
            raise StepError("deepFilter output is not 48 kHz")

        # ---- Steps 4-7: EQ + compressor + peak limiter, one pass
        attack = ATTACK["alternative" if opts.alternative else "standard"]
        chain = [] if opts.no_eq else [EQ_CHAIN]
        chain += [COMPRESSOR.format(attack=attack), PEAK_LIMITER]
        processed = tmp / f"{stem}_processed.wav"
        run([T["ffmpeg"], "-nostdin", "-hide_banner", "-y", "-i", str(denoised), "-af", ",".join(chain), "-ar", "48000", str(processed)])
        rep["preset"] = ("alternative" if opts.alternative else "standard") + (" / EQ off" if opts.no_eq else " / EQ on")
        log(f"[7/10] {rep['preset']}, attack {attack} ms, peak limiter -6 dB")
        rep["steps"].append({"step": "eq_comp_limit", "duration_s": stream_duration(T, processed, "a:0")})

        # ---- Step 8: delivery normalize + ceiling
        target, ceiling = opts.target_lufs, opts.ceiling_dbtp
        m8 = loudnorm_measure(T, processed, target, ceiling)
        final = tmp / f"{stem}_final.wav"
        af8 = (f"loudnorm=I={target}:TP={ceiling}:LRA={LRA_PARAM}:measured_I={m8['input_i']}:measured_TP={m8['input_tp']}:"
               f"measured_LRA={m8['input_lra']}:measured_thresh={m8['input_thresh']}:offset={m8['target_offset']}:linear=true,"
               f"{CEILING_LIMITER}")
        run([T["ffmpeg"], "-nostdin", "-hide_banner", "-y", "-i", str(processed), "-af", af8, "-ar", "48000", str(final)])
        if sample_rate(T, final) != 48000:
            raise StepError("delivery normalize came out at a rate other than 48 kHz")
        log(f"[8/10] delivery target {target} LUFS / {ceiling} dBTP, ceiling -1.0 dBFS")

        # ---- Verification (on the WAV)
        mean_db, _ = volumedetect(T, final)
        m9 = loudnorm_measure(T, final, target, ceiling)
        out_i, out_tp = float(m9["input_i"]), float(m9["input_tp"])
        d_final = stream_duration(T, final, "a:0")
        # Drift gate: the chain must hand back exactly the length it was given. The reference is
        # the extracted WAV (d0), not the container — see the note at Step 1.
        delta_ms = abs(d_final - d0) * 1000.0 if (d_final and d0) else None
        checks = rep["checks"]
        checks["not_silent"] = mean_db is not None and mean_db > SILENT_MEAN_DB
        checks["loudness_in_band"] = abs(out_i - target) <= LOUDNESS_TOLERANCE_LU and out_i >= LOUDNESS_FLOOR_LUFS
        # Hard bar = the -1.0 dBFS ceiling limiter (plus 0.3 dB inter-sample overshoot a sample-peak
        # limiter cannot see), and never positive. The loudnorm TP target (-1.5) is a prediction, so
        # a peak between the target and the hard catch is a warning, not a failure.
        checks["true_peak_ok"] = out_tp <= HARD_TP_MAX and out_tp < 0.0
        if checks["true_peak_ok"] and out_tp > ceiling + 0.05:
            rep["warnings"].append(f"true peak {out_tp:.2f} dBTP is above the {ceiling} dBTP target but under the "
                                   f"-1.0 dBFS hard catch; the delivery normalize could not hold its TP prediction exactly")
        checks["duration_match"] = delta_ms is not None and delta_ms <= DURATION_TOLERANCE_MS
        rep.update({"output_i": out_i, "output_tp": out_tp, "output_mean_db": mean_db,
                    "output_duration_s": d_final, "duration_delta_ms": delta_ms})
        log(f"[9/10] output {out_i:.1f} LUFS, {out_tp:.1f} dBTP, mean {mean_db:.1f} dB, Δduration {delta_ms:.1f} ms")
        failed = [k for k, v in checks.items() if not v]
        if failed:
            if not checks["duration_match"]:
                evidence = dest.with_suffix("") .with_name(f"{stem}_enhanced-UNVERIFIED.wav")
                shutil.copy2(final, evidence)
                rep["evidence_wav"] = str(evidence)
            raise StepError("verification failed: " + ", ".join(failed) +
                            (f" (delta {delta_ms:.1f} ms)" if not checks["duration_match"] else "") +
                            (f" (true peak {out_tp:.2f} dBTP)" if not checks["true_peak_ok"] else "") +
                            (f" (integrated {out_i:.2f} LUFS)" if not checks["loudness_in_band"] else ""))

        # ---- Step 9/10: deliver
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not is_video:
            shutil.copy2(final, dest)
            rep["status"] = "OK"
            log(f"[10/10] wrote {dest}")
            return rep

        # 10a gate already passed via duration_match (same 50 ms bar). 10b mux.
        # -itsoffset puts the enhanced track back at the source audio's start time. A WAV has no
        # timestamps, so without it a track that began 87 ms after the video would come back
        # 87 ms early — 2.6 frames at 30 fps, a visible lip-sync error.
        offset_args = ["-itsoffset", f"{audio_offset_s:.6f}"] if abs(audio_offset_s) * 1000.0 > 1.0 else []
        run([T["ffmpeg"], "-nostdin", "-hide_banner", "-y", "-i", str(src), *offset_args, "-i", str(final),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", str(dest)])
        # 10c verify the muxed file
        oinfo = probe(T, dest)
        ostreams = oinfo.get("streams", [])
        ov = next((s for s in ostreams if s.get("codec_type") == "video"), None)
        oa = next((s for s in ostreams if s.get("codec_type") == "audio"), None)
        mux = rep["mux_checks"] = {}
        mux["two_streams"] = len(ostreams) == 2 and ov is not None and oa is not None
        src_frames, out_frames = vstream.get("nb_frames"), (ov or {}).get("nb_frames")
        if src_frames and out_frames and src_frames != "N/A" and out_frames != "N/A":
            mux["frame_count_equal"] = src_frames == out_frames
        else:
            mux["frame_count_equal"] = None  # container did not report nb_frames; rate + duration checks cover it
        mux["frame_rate_equal"] = (ov or {}).get("r_frame_rate") == vstream.get("r_frame_rate")
        ovd, oad = (ov or {}).get("duration"), (oa or {}).get("duration")
        ovd = float(ovd) if ovd and ovd != "N/A" else None
        oad = float(oad) if oad and oad != "N/A" else None
        av_delta = abs(ovd - oad) * 1000.0 if (ovd is not None and oad is not None) else None
        mux["av_duration_delta_ms"] = av_delta  # information only: the source's own streams differ too
        # The two invariants a stream-copy remux must keep: the video is exactly as long as the
        # source video, and the audio is as long as the track that was extracted (AAC may add a
        # few ms of padding). "Audio equals video" is NOT one of them — a camera capture's own
        # streams differ by tens of ms, and that difference is preserved, not repaired.
        svd = float(vstream["duration"]) if vstream.get("duration") not in (None, "N/A") else None
        mux["video_duration_equal"] = (ovd is not None and svd is not None and abs(ovd - svd) * 1000.0 <= VIDEO_COPY_TOLERANCE_MS) \
            if (ovd is not None and svd is not None) else None
        mux["audio_duration_match"] = oad is not None and d0 is not None and abs(oad - d0) * 1000.0 <= DURATION_TOLERANCE_MS
        mux["audio_aac_48k"] = (oa or {}).get("codec_name") == "aac" and str((oa or {}).get("sample_rate")) == "48000"
        # The audio must start where the source audio started (relative to the video).
        oa_start = float((oa or {}).get("start_time") or 0.0) - float((ov or {}).get("start_time") or 0.0)
        mux["audio_start_offset_ms"] = oa_start * 1000.0
        mux["audio_start_match"] = abs(oa_start - audio_offset_s) * 1000.0 <= START_TOLERANCE_MS
        bad = [k for k, v in mux.items() if v is False]
        if bad:
            evidence = dest.with_name(f"{stem}_enhanced-UNVERIFIED.wav")
            shutil.copy2(final, evidence)
            rep["evidence_wav"] = str(evidence)
            dest.unlink(missing_ok=True)
            raise StepError("muxed file failed: " + ", ".join(bad))
        rep["video_frames"] = out_frames
        rep["video_frame_rate"] = (ov or {}).get("r_frame_rate")
        rep["status"] = "OK"
        log(f"[10/10] wrote {dest}  (video stream copied, {out_frames or '?'} frames @ {rep['video_frame_rate']}, "
            f"A/V Δ {av_delta:.1f} ms, audio starts {oa_start * 1000:+.1f} ms vs video, as in the source)")
        return rep

    except StepError as e:
        rep["error"] = str(e)
        keep_tmp = True
        rep["temp_dir"] = str(tmp)
        return rep
    finally:
        if not keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- report
def fnum(v, nd=1, unit=""):
    if v is None:
        return "—"
    if isinstance(v, float) and v in (float("inf"), float("-inf")):
        return "-inf"
    return f"{v:.{nd}f}{unit}" if isinstance(v, (int, float)) else str(v)


def print_table(rep):
    rows = [
        ("Input", rep["input"]),
        ("Mode", rep.get("mode", "—")),
        ("Input integrated (LUFS)", fnum(rep.get("input_i"))),
        ("Input true peak (dBTP)", fnum(rep.get("input_tp"))),
        ("Working stage", "dynamic (LRA fell)" if rep.get("working_stage_dynamic") else ("linear" if "working_lufs" in rep else "—")),
        ("Noise floor (dBFS)", fnum(rep.get("noise_floor_dbfs"))),
        ("Noise floor source", rep.get("noise_floor_source", "—")),
        ("Denoise strength (--atten-lim)", fnum(rep.get("atten_lim"), 0)),
        ("Preset", rep.get("preset", "—")),
        ("Target (LUFS / dBTP)", f"{rep.get('target_lufs')} / {rep.get('ceiling_dbtp')}"),
        ("Output integrated (LUFS)", fnum(rep.get("output_i"))),
        ("Output true peak (dBTP)", fnum(rep.get("output_tp"))),
        ("Duration match (ms vs source)", fnum(rep.get("duration_delta_ms"))),
        ("Deliverable", rep.get("deliverable", "—") if rep["status"] == "OK" else "— (not delivered)"),
        ("Status", rep["status"]),
    ]
    if rep.get("mux_checks"):
        mc = rep["mux_checks"]
        rows.insert(-2, ("Video", f"frames {rep.get('video_frames') or '?'} @ {rep.get('video_frame_rate')}, "
                                  f"A/V Δ {fnum(mc.get('av_duration_delta_ms'))} ms, {'AAC 48k' if mc.get('audio_aac_48k') else 'audio ?'}"))
    w = max(len(r[0]) for r in rows)
    print("| " + "Field".ljust(w) + " | Value |")
    print("|" + "-" * (w + 2) + "|-------|")
    for k, v in rows:
        print(f"| {k.ljust(w)} | {v} |")
    for wmsg in rep.get("warnings", []):
        print(f"WARNING: {wmsg}")
    if rep.get("error"):
        print(f"ERROR: {rep['error']}")
        if rep.get("evidence_wav"):
            print(f"Evidence WAV kept at: {rep['evidence_wav']}")
        if rep.get("temp_dir"):
            print(f"Temp files kept at: {rep['temp_dir']}")
    print()


# ---------------------------------------------------------------- main
def collect_inputs(p):
    p = Path(p)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXT | VIDEO_EXT
                       and "_enhanced" not in f.stem and not f.name.startswith("."))
        return files
    if p.is_file():
        return [p]
    return []


def main():
    global QUIET
    ap = argparse.ArgumentParser(description="audio-enhance skill as one script")
    ap.add_argument("input", help="audio file, video file, or folder")
    ap.add_argument("output", nargs="?", help="output file (single input) or folder")
    ap.add_argument("--audio-only", action="store_true", help="video input: stop at the WAV, skip the remux")
    ap.add_argument("--alternative", action="store_true", help="alternative preset (1 ms attack)")
    ap.add_argument("--target-lufs", type=float, default=DEFAULT_TARGET_LUFS)
    ap.add_argument("--ceiling-dbtp", type=float, default=DEFAULT_CEILING_DBTP)
    ap.add_argument("--no-eq", action="store_true", help="skip the 3-band EQ (only on explicit request)")
    ap.add_argument("--json", dest="json_out", help="write the per-file report as JSON to this path")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    opts = ap.parse_args()
    QUIET = opts.quiet

    if opts.target_lufs > -16.0 or opts.target_lufs < -18.0:
        print(f"WARNING: --target-lufs {opts.target_lufs} is outside the recommended band -18..-16 LUFS",
              file=sys.stderr)

    T = check_tools()
    files = collect_inputs(opts.input)
    if not files:
        print(f"no audio or video files found at {opts.input}", file=sys.stderr)
        sys.exit(1)
    if len(files) > 1 and opts.output and not Path(opts.output).is_dir() and not opts.output.endswith(os.sep):
        print("several inputs need an output FOLDER, not a file", file=sys.stderr)
        sys.exit(1)

    tmp_root = Path("/tmp/audio-enhance")
    tmp_root.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in files:
        rep = process_file(T, f, opts.output, opts, tmp_root)
        rep["target_lufs"] = opts.target_lufs
        rep["ceiling_dbtp"] = opts.ceiling_dbtp
        reports.append(rep)
        print_table(rep)

    if opts.json_out:
        Path(opts.json_out).write_text(json.dumps(reports, indent=2), encoding="utf-8")
    failed = [r for r in reports if r["status"] != "OK"]
    ok = len(reports) - len(failed)
    print(f"{ok} of {len(reports)} file(s) delivered." + (f" FAILED: {', '.join(Path(r['input']).name for r in failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
