#!/usr/bin/env python3
"""Build the whole perfect-cuts package from the editorial pass, in one call.

Usage:
    python3 build_package.py --source <video> --cuts <cuts.json> --out <package dir>
        [--title <text>] [--no-mp4] [--transcript <words.json>]

<video>      the file the speech map was built on (the cleaned-audio file from
             audio-enhance when there is one, otherwise the raw take).
<cuts.json>  the editorial decisions (schema in SKILL.md, step 5):
             {
               "map": "<path to map.json>",
               "script": "exact" | "rough" | "freestyled",        (optional)
               "clips": [                                           (timeline order)
                 {"blocks": [6], "reason": "take 4 of 4", "text": "optional fix"},
                 {"blocks": [8, 9], "start": 31.2, "end": 36.0}   (start/end optional)
               ],
               "cut": {"2": "retake 1 of 4", "26": "false start"},
               "angles": {...}                                      (optional, two cameras)
             }
             Every block in the map must be either in a clip or in "cut".
<package dir> created if missing; every package file goes here.

Writes: the MP4 (main output), FCPXML, Premiere/Resolve XML, EDL, SRT, the
README, the cut log (UTF-8 with BOM), the exporter spec, the Remotion
launcher. Each file comes from the existing exporter scripts; this script only
turns decisions into frames and calls them. Verifies the MP4 (streams, and
duration against the sum of the clips within one frame). Prints a JSON summary.
Exit 0 on success, 1 on any failure.

Two checks ride along. The lost-word guard lists, under "warnings", every
transcript word inside a kept block that the clip's in- or out-point would cut
off (words cut by a deliberate start/end trim go under "trimmed_words"
instead). The MP4's audio is held at or below -1.5 dBTP after AAC encoding
("true_peak_dbtp", "audio_gain_db"). A trimmed clip with no "text" gets its
caption from the words inside the kept range, not the whole block.
Word times come from the map ("words" on each block); a map built before
that needs --transcript (or "transcript" in cuts.json).
"""
import argparse
import csv
import json
import math
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Find ffmpeg/ffprobe even under a bare PATH: the plugin's own environment
# (TV_DATA, passed in by the skill), then Homebrew, then the inherited PATH.
_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

NAMES = {
    "readme": "README (C).txt",
    "mp4": "1 WATCH - final video (C).mp4",
    "fcpxml": "2 EDIT - Final Cut Pro (C).fcpxml",
    "fcp7": "3 EDIT - Premiere + Resolve (C).xml",
    "cutlog": "4 REVIVE - cut decisions (C).csv",
    "command": "5 OPEN IN REMOTION - Mac (C).command",
    "srt": "6 CAPTIONS (C).srt",
    "edl": "7 AVID + LEGACY (C).edl",
    "spec": "cut data (C).json",
    "launcher": "_remotion-launcher (C).mjs",
}


class Fail(Exception):
    pass


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,r_frame_rate,width,height,sample_rate,duration,nb_frames:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise Fail(f"ffprobe could not read {path}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def source_meta(path):
    info = ffprobe(path)
    meta = {"source_duration": float(info["format"]["duration"])}
    for s in info["streams"]:
        if s["codec_type"] == "video" and "fps" not in meta:
            # First video stream only: a .mov timecode track also reports
            # codec_type=video, at 90000 fps.
            num, den = s["r_frame_rate"].split("/")
            meta["fps"] = int(num) / int(den)
            meta["width"], meta["height"] = s["width"], s["height"]
        elif s["codec_type"] == "audio" and "samplerate" not in meta:
            meta["samplerate"] = int(s.get("sample_rate", 48000))
    if "fps" not in meta:
        raise Fail(f"{path} has no video stream")
    meta.setdefault("samplerate", 48000)
    return meta


PAD = 0.30         # Parakeet starts words up to ~0.3 s before the voice
MAX_WORD = 1.2     # longest believable spoken word, in seconds


def wstart(w):
    """The LATEST believable start of a word: its span held to MAX_WORD.

    Parakeet can stretch a word back across a long pause before it ("learning."
    timed 86.58-96.75 s, spoken at about 95.3 s). Read raw, such a word looks
    as if it started before the in-point and the guard reports it MISSING
    although it is in the cut. The caption scripts hold words to 1.2 s for
    the same reason. It can also stretch a word FORWARD over the pause after
    it ("yourself." timed 129.76-138.32 s), so a test at the out-point uses
    the word's raw start, its earliest believable start: a word is lost at
    the head only if even its latest start is before the in-point, and at the
    tail only if even its earliest start is after the out-point."""
    return max(w[0], w[1] - MAX_WORD)


def head_mid(w):
    """Middle of a word read from its latest believable start."""
    s = wstart(w)
    return (s + min(w[1], s + MAX_WORD)) / 2


def tail_mid(w):
    """Middle of a word read from its raw (earliest) start."""
    return (w[0] + min(w[1], w[0] + MAX_WORD)) / 2
TP_CEILING = -1.5  # dBTP, the same ceiling audio-enhance delivers to


def block_words(smap, transcript):
    """{block id: [(start, end, text), ...]} from the map's own "words", or,
    for a map built before blocks carried words, from the transcript JSON
    assigned to blocks with the speech map's own rule."""
    blocks = smap["blocks"]
    if all("words" in b for b in blocks):
        return {b["i"]: [tuple(w) for w in b["words"]] for b in blocks}
    if not transcript:
        return None
    sys.path.insert(0, str(HERE))
    from speech_map import assign_word_lists
    tx = json.load(open(transcript, encoding="utf-8"))
    words = sorted((w["start"], max(w.get("end", w["start"]), w["start"]),
                    w.get("word", "").strip())
                   for seg in tx.get("segments", []) for w in seg.get("words", [])
                   if "start" in w)
    lists = assign_word_lists(words, [[b["start"], b["end"]] for b in blocks])
    return {b["i"]: lists[n] for n, b in enumerate(blocks)}


def lost_words(words, t_in, t_out):
    """Words that a clip running t_in..t_out would cut off.

    A word is lost at the head when it starts more than PAD before the
    in-point: Parakeet times words up to ~0.3 s early, start and end alike,
    so a word ending just before an ordinary onset is usually the first word
    heard right at it (tested: "So" timed 25.12-25.36 s, onset 25.39 s, and
    a snippet from 25.39 s transcribes as "So in today's video"). It is lost
    at the tail when it starts at or after the out-point."""
    head = [w for w in words if wstart(w) < t_in - PAD]
    tail = [w for w in words if w[0] >= t_out - 0.02]
    return head, tail


def kept_text(words, t_in, t_out, trim_in, trim_out):
    """Caption text for a trimmed clip.

    Only a trimmed side is cut by time, and there a word stays when its middle
    is inside the clip. An untrimmed side keeps every word but those the
    lost-word guard flags, because Parakeet times words up to ~0.3 s early and
    a middle-of-word test would drop a first word that is in the cut."""
    kept = []
    for w in words:
        if trim_in and head_mid(w) < t_in:
            continue
        if not trim_in and wstart(w) < t_in - PAD:
            continue
        if trim_out and tail_mid(w) > t_out:
            continue
        if not trim_out and w[0] >= t_out - 0.02:
            continue
        kept.append(w[2])
    return " ".join(kept).strip()


def true_peak(path):
    """Integrated loudness (LUFS) and true peak (dBTP) of a file's audio."""
    p = subprocess.run(["ffmpeg", "-nostdin", "-i", str(path), "-map", "0:a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = p.stderr[p.stderr.rfind("Summary:"):]
    import re
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    t = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+) dBFS", tail)
    if not (i and t):
        raise Fail(f"could not measure loudness of {path}")
    return float(i.group(1)), float(t.group(1))


def hold_ceiling(mp4):
    """Keep the MP4's audio at or below TP_CEILING dBTP.

    The AAC encoder adds inter-sample peaks: a source delivered at -1.5 dBTP
    comes back at about -1.4. If the encoded file is over the ceiling, the
    audio is encoded once more with a small gain cut (the overshoot plus
    0.1 dB, so typically -0.1 to -0.3 dB), the video stream copied untouched.
    Loudness moves by the same small amount, far inside 0.5 LU. Returns
    (loudness, true peak, gain applied)."""
    lufs, tp = true_peak(mp4)
    if tp <= TP_CEILING:
        return lufs, tp, 0.0
    gain = round(TP_CEILING - tp - 0.1, 2)
    tmp = mp4.with_name(mp4.stem + ".tp.mp4")
    for _ in range(2):
        p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(mp4),
                            "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                            "-af", f"volume={gain}dB", "-c:a", "aac", "-b:a", "192k",
                            "-movflags", "+faststart", "-y", str(tmp)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise Fail(f"could not re-encode the audio: {p.stderr.strip()[-300:]}")
        lufs2, tp2 = true_peak(tmp)
        if tp2 <= TP_CEILING:
            tmp.replace(mp4)
            return lufs2, tp2, gain
        gain = round(gain - 0.2, 2)
    tmp.unlink(missing_ok=True)
    raise Fail(f"the MP4's true peak stays above {TP_CEILING} dBTP after a gain cut")


def timecode(seconds, fps):
    f = int(round(seconds * fps))
    r = int(round(fps))
    return "%02d:%02d:%02d:%02d" % (f // (3600 * r), f // (60 * r) % 60,
                                     f // r % 60, f % r)


def run(script, *args):
    p = subprocess.run([sys.executable, str(HERE / script), *map(str, args)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise Fail(f"{script} failed:\n{p.stderr.strip() or p.stdout.strip()}")
    return p.stdout.strip()


def build(a):
    source = Path(a.source).expanduser().resolve()
    if not source.is_file():
        raise Fail(f"source video not found: {source}")
    decisions = json.load(open(a.cuts, encoding="utf-8"))
    map_path = Path(decisions.get("map", "")).expanduser()
    if not map_path.is_absolute():
        map_path = (Path(a.cuts).resolve().parent / map_path)
    if not map_path.is_file():
        raise Fail(f'cuts.json "map" must name the speech map; not found: {map_path}')
    smap = json.load(open(map_path, encoding="utf-8"))
    blocks = {b["i"]: b for b in smap["blocks"]}

    meta = source_meta(source)
    if abs(meta["source_duration"] - float(smap.get("duration", 0))) > 0.1:
        raise Fail(f"the speech map was built on a different file "
                   f"({smap.get('source')}, {smap.get('duration')} s) than --source "
                   f"({source}, {meta['source_duration']:.3f} s)")
    fps = meta["fps"]
    src_frames = int(math.floor(meta["source_duration"] * fps + 1e-6))

    # Every block gets exactly one decision.
    kept, cut = {}, {int(k): v for k, v in (decisions.get("cut") or {}).items()}
    clips_in = decisions.get("clips") or []
    if not clips_in:
        raise Fail('cuts.json has no "clips"')
    for n, c in enumerate(clips_in, 1):
        ids = c.get("blocks") or []
        if not ids:
            raise Fail(f"clip {n} names no blocks")
        for i in ids:
            if i not in blocks:
                raise Fail(f"clip {n} names block {i}, which is not in the map")
            if i in kept or i in cut:
                raise Fail(f"block {i} has two decisions")
            kept[i] = n
    unknown = [i for i in cut if i not in blocks]
    if unknown:
        raise Fail(f'"cut" names blocks not in the map: {unknown}')
    missing = [i for i in sorted(blocks) if i not in kept and i not in cut]
    if missing:
        raise Fail(f"blocks with no decision (keep them in a clip or give a cut "
                   f"reason): {missing}")

    # Word times, for the lost-word guard and trimmed captions.
    transcript = a.transcript or decisions.get("transcript")
    wmap = block_words(smap, transcript)
    if wmap is None:
        warnings_pre = ["the speech map carries no word times and no --transcript "
                        "was given: the lost-word check did not run"]
    else:
        warnings_pre = []

    # Decisions -> frames. In = first block's onset (the -30 dB voice onset,
    # breath-proof); out = last block's end (the -38 dB tail) + 1 frame.
    clips, warnings, trimmed, last_end = [], list(warnings_pre), [], -1.0
    for n, c in enumerate(clips_in, 1):
        ids = c["blocks"]
        first, last = blocks[ids[0]], blocks[ids[-1]]
        start = float(c.get("start", first["onset"]))
        end = float(c.get("end", last["end"]))
        if end <= start:
            raise Fail(f"clip {n} ends before it starts ({start} -> {end})")
        if start < last_end:
            warnings.append(f"clip {n} starts before clip {n - 1} ends in the "
                            f"source (out-of-order takes); fine if intended")
        last_end = end
        words = [w for i in ids for w in (wmap or {}).get(i, [])]
        if wmap is not None:
            # Lost-word guard: a word inside the kept blocks that the in- or
            # out-point cuts off. On a deliberate trim (explicit start/end)
            # this is the point, so it is listed, not warned about.
            head, tail = lost_words(words, start, end)
            # On a deliberately trimmed side, list what the trim drops with
            # the same middle-of-word test the trimmed caption uses.
            if "start" in c:
                head = [w for w in words if (w[0] + w[1]) / 2 < start]
            if "end" in c:
                tail = [w for w in words if (w[0] + w[1]) / 2 > end]
            for side, lost, explicit in (("before the in-point", head, "start" in c),
                                         ("after the out-point", tail, "end" in c)):
                if not lost:
                    continue
                said = " ".join(w[2] for w in lost)
                note = (f"clip {n} (blocks {ids}): \"{said}\" "
                        f"({lost[0][0]:.2f}-{lost[-1][1]:.2f} s) falls {side} "
                        f"({start if side.endswith('in-point') else end:.2f} s)")
                if explicit:
                    trimmed.append(note + " - trimmed on purpose")
                else:
                    warnings.append(note + " - these words will be MISSING "
                                    "from the cut")
        if c.get("text"):
            text = c["text"]
        elif words and ("start" in c or "end" in c):
            text = kept_text(words, start, end, "start" in c, "end" in c)
        else:
            text = " ".join(blocks[i]["text"] for i in ids).strip()
        # Hold the out-point inside the source: a take that ends on a kept
        # sentence gives ceil(end * fps) + 1 past the last frame, and the MP4
        # then comes out short and fails the duration check.
        clip = {"in_frame": int(math.floor(start * fps)),
                "out_frame": min(int(math.ceil(end * fps)) + 1, src_frames),
                "text": text}
        if c.get("angle"):
            clip["angle"] = c["angle"]
        clips.append(clip)

    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    spec = dict(meta)
    spec.update({
        "source": str(source),
        "sequence_name": a.title or f"{stem} perfect cut",
        "output": str(out / NAMES["fcp7"]),
        "clips": clips,
    })
    if decisions.get("angles"):
        spec["angles"] = decisions["angles"]
    spec_path = out / NAMES["spec"]
    json.dump(spec, open(spec_path, "w", encoding="utf-8"), indent=1)

    files = {"spec": spec_path}
    if not a.no_mp4:
        run("render_mp4.py", spec_path, out / NAMES["mp4"])
        files["mp4"] = out / NAMES["mp4"]
    run("export_fcpxml.py", spec_path, out / NAMES["fcpxml"])
    run("export_fcp7.py", spec_path)  # reads "output" from the spec
    run("export_srt.py", spec_path, out / NAMES["srt"])
    run("export_edl.py", spec_path, out / NAMES["edl"])
    for k in ("fcpxml", "fcp7", "srt", "edl"):
        files[k] = out / NAMES[k]
    shutil.copyfile(HERE / "readme_template.txt", out / NAMES["readme"])
    shutil.copyfile(HERE / "_remotion-launcher.mjs", out / NAMES["launcher"])
    cmd = out / NAMES["command"]
    shutil.copyfile(HERE / "open-in-remotion-mac.command", cmd)
    cmd.chmod(cmd.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    files.update(readme=out / NAMES["readme"], launcher=out / NAMES["launcher"],
                 command=cmd)

    # Cut log: every block, kept and cut, with the reason. UTF-8 WITH a BOM,
    # or Excel on macOS reads it as MacRoman and mangles accents and dashes.
    log = out / NAMES["cutlog"]
    with open(log, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["block", "status", "source_in", "source_out",
                    "timeline_position", "text", "reason"])
        for i in sorted(blocks):
            b = blocks[i]
            if i in kept:
                c = clips_in[kept[i] - 1]
                w.writerow([i, "KEPT", timecode(b["onset"], fps), timecode(b["end"], fps),
                            kept[i], b["text"], c.get("reason", "kept")])
            else:
                w.writerow([i, "CUT", timecode(b["start"], fps), timecode(b["end"], fps),
                            "", b["text"], cut[i]])
    files["cutlog"] = log

    # Verify.
    for k, p in files.items():
        if not p.is_file() or p.stat().st_size == 0:
            raise Fail(f"{p.name} was not written")
    expected = sum(c["out_frame"] - c["in_frame"] for c in clips) / fps
    result = {"ok": True, "package": str(out), "source": str(source),
              "source_duration": round(meta["source_duration"], 3),
              "expected_duration": round(expected, 3),
              "clips": len(clips), "blocks_kept": len(kept), "blocks_cut": len(cut),
              "files": {k: str(v) for k, v in files.items()}, "warnings": warnings,
              "trimmed_words": trimmed}
    if "mp4" in files:
        lufs, tp, gain = hold_ceiling(files["mp4"])
        result.update(loudness_lufs=lufs, true_peak_dbtp=tp, audio_gain_db=gain)
        info = ffprobe(files["mp4"])
        kinds = sorted({s["codec_type"] for s in info["streams"]})
        if kinds != ["audio", "video"]:
            raise Fail(f"the MP4 has streams {kinds}, expected audio and video")
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        vdur = float(v.get("duration") or info["format"]["duration"])
        result["mp4_duration"] = round(vdur, 3)
        if abs(vdur - expected) > 1.0 / fps + 1e-6:
            raise Fail(f"the MP4 runs {vdur:.3f} s, expected {expected:.3f} s "
                       f"(more than one frame off)")
        # The frame count catches what the duration hides: a clip that lost
        # its first frame and another that gained one cancel out in length.
        want = sum(c["out_frame"] - c["in_frame"] for c in clips)
        got = int(v.get("nb_frames") or 0)
        result["mp4_frames"], result["expected_frames"] = got, want
        if got and got != want:
            raise Fail(f"the MP4 has {got} frames, expected {want}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--cuts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--transcript",
                    help="word-timestamp JSON, only for a map built before "
                         "blocks carried word times")
    ap.add_argument("--no-mp4", action="store_true",
                    help="timeline files only (the user said no at Q2)")
    a = ap.parse_args()
    try:
        result = build(a)
    except (Fail, KeyError, ValueError, json.JSONDecodeError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=1))
        sys.exit(1)
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
