#!/usr/bin/env python3
"""Put the lecturer and the slides on one screen, slide changes from timing.json.

Usage:
    python3 compose.py --video CUT.mp4 --work DIR --timing DIR/timing.json \
        --out OUT.mp4 [--background PNG_OR_HEX] [--speaker-x 0.6]
        [--layout side-by-side|pip|slide] [--speaker-side right|left]
    python3 compose.py ... --preview [--at 75,190]   stills only, no render

DIR is the folder slides_prepare.py wrote (slides/ and slides.json). Command
line options override the same keys in timing.json; anything set nowhere
gets the default.

Layouts, per segment (timing.json "layout" sets the default, a segment's own
"layout" overrides it):
    side-by-side  slide on one side, the lecturer cropped into a tall box
                  beside it (default)
    pip           slide nearly full frame, the lecturer in a small box in the
                  bottom corner, over the slide
    slide         slide alone, nearly full frame
A segment with {"show": "speaker"} shows the lecturer full frame.

How it renders, in one ffmpeg pass. Every segment gets a still "plate": the
background, the slide and the soft shadows, drawn once per slide and layout.
The plates play back to back for exact frame counts, the lecturer's video is
cropped and scaled on top, and overlays switch on and off by frame number. The
sound is copied from the cut untouched, so it stays in sync by construction.

Output: 1920x1080 at the frame rate of the cut, H.264 + the cut's audio.
Stdlib only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

W, H = 1920, 1080
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BG = SKILL_DIR / "assets" / "background.png"
LAYOUTS = ("side-by-side", "pip", "slide")
SHADOW = 28          # blur reach of the soft shadow, px
SHADOW_ALPHA = 0.45

TV_DATA = os.environ.get("TV_DATA", "").strip()
_front = [os.path.join(TV_DATA, "venv", "bin")] if TV_DATA else []
_front.append(os.path.expanduser("~/.local/bin"))
_path = os.environ.get("PATH", "").split(os.pathsep)
os.environ["PATH"] = os.pathsep.join(
    [p for p in _front if p not in _path] + _path +
    [p for p in ("/opt/homebrew/bin", "/usr/local/bin") if p not in _path])


def need(tool):
    p = shutil.which(tool)
    if not p:
        sys.exit("ERROR: %s is not installed. Run /video-teach-plugin:setup." % tool)
    return p


FFMPEG, FFPROBE = need("ffmpeg"), need("ffprobe")


def run(cmd, quiet=True):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace")[-3000:])
        sys.exit("ERROR: ffmpeg failed (%s)" % " ".join(cmd[:3]))
    return r.stdout.decode("utf-8", "replace")


def even(x):
    return int(round(x / 2.0)) * 2


# ---------------------------------------------------------------- probing

def probe(video):
    out = json.loads(run([FFPROBE, "-v", "error", "-print_format", "json",
                          "-show_streams", "-show_format", str(video)]))
    v = next((s for s in out["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        sys.exit("ERROR: %s has no video stream." % video)
    a = next((s for s in out["streams"] if s["codec_type"] == "audio"), None)
    # The nominal rate (r_frame_rate) is the one the footage was shot at.
    # The average drifts on edited or phone files (an exact 60 fps cut
    # reported 59.953), so it is used only when the nominal rate is not a
    # real frame rate (some files report 90000/1 or 1000/1).
    std_rates = (Fraction(24000, 1001), Fraction(24), Fraction(25),
                 Fraction(30000, 1001), Fraction(30), Fraction(50),
                 Fraction(60000, 1001), Fraction(60))
    fps = None
    for key in ("r_frame_rate", "avg_frame_rate"):
        rate = v.get(key) or "0/0"
        if rate.startswith("0"):
            continue
        cand = Fraction(rate)
        near = min(std_rates, key=lambda s: abs(float(s) - float(cand)))
        tol = 0.001 if key == "r_frame_rate" else 0.02
        if abs(float(near) - float(cand)) < tol:
            fps = near
            break
        if key == "avg_frame_rate" and 10 <= float(cand) <= 120:
            fps = cand
    if fps is None:
        fps = Fraction(30)
    dur = float(v.get("duration") or out["format"]["duration"])
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"w": w, "h": h, "fps": fps, "duration": dur,
            "audio": a["codec_name"] if a else None}


# ---------------------------------------------------------------- geometry

def fit(aspect, max_w, max_h):
    w = max_w
    h = w / aspect
    if h > max_h:
        h = max_h
        w = h * aspect
    return even(w), even(h)


def geometry(layout, aspect, side):
    """Slide rectangle and speaker box (x, y, w, h) on the 1920x1080 frame."""
    if layout == "side-by-side":
        margin, gap, box_min = 56, 40, 480
        sw, sh = fit(aspect, W - 2 * margin - gap - box_min, 720)
        bw = min(W - 2 * margin - gap - sw, even(sh * 0.75))
        bh = sh
        x0 = (W - (sw + gap + bw)) // 2
        y = (H - sh) // 2
        if side == "left":
            box, slide = (x0, y, bw, bh), (x0 + bw + gap, y, sw, sh)
        else:
            slide, box = (x0, y, sw, sh), (x0 + sw + gap, y, bw, bh)
        return slide, box
    sw, sh = fit(aspect, W - 2 * 48, H - 2 * 48)
    slide = ((W - sw) // 2, (H - sh) // 2, sw, sh)
    if layout == "slide":
        return slide, None
    # The box sits inside the slide's bottom corner, 24 px in from its edges.
    bw, bh = 352, 440
    sx, sy = slide[0], slide[1]
    bx = sx + sw - 24 - bw if side != "left" else sx + 24
    return slide, (bx, sy + sh - 24 - bh, bw, bh)


def speaker_crop(src_w, src_h, box_w, box_h, cx_frac):
    """The part of the source frame that fills the speaker box.

    Camera files often carry a dark row or two at the frame edge, invisible
    full frame and an ugly line along a box edge, so the crop keeps 1% clear
    of the top and bottom.
    """
    aspect = box_w / float(box_h)
    inset = even(src_h * 0.01)
    ch = src_h - 2 * inset
    cw = even(ch * aspect)
    if cw > src_w:
        cw = src_w - src_w % 2
        ch = even(cw / aspect)
    cx = cx_frac * src_w
    x = int(min(max(cx - cw / 2.0, 0), src_w - cw))
    y = (src_h - ch) // 2
    return cw, ch, x, y


def speaker_x_from_config():
    """Middle of the part of the frame the look's free area leaves to the speaker."""
    if not TV_DATA:
        return None
    try:
        look = json.loads(Path(TV_DATA, "config.json").read_text()).get("look") or {}
        fa = look.get("free_area")
        if look.get("layout") == "lower-thirds" or not fa:
            return None
        x, w = float(fa["x"]), float(fa["w"])
        if x + w / 2 < 0.5:
            return (x + w + 1.0) / 2
        return x / 2
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------- plates

def bg_input(bg):
    if bg.startswith("#"):
        return ["-f", "lavfi", "-i", "color=c=0x%s:s=%dx%d" % (bg[1:], W, H)]
    return ["-i", bg]


def shadow_chain(label_in, rect, label_out, idx):
    """Filter text: a soft shadow for rect, drawn onto label_in."""
    x, y, w, h = rect
    r = SHADOW
    return (
        "color=c=black:s=%dx%d,format=rgba,colorchannelmixer=aa=%.2f,"
        "pad=%d:%d:%d:%d:color=black@0,boxblur=%d:2[sh%d];"
        "[%s][sh%d]overlay=%d:%d[%s]" % (
            w, h, SHADOW_ALPHA, w + 2 * r, h + 2 * r, r, r, r // 2, idx,
            label_in, idx, x - r + 6, y - r + 10, label_out))


def make_plate(path, bg, slide_png, layout, aspect, side):
    """Background + shadows + slide for one slide in one layout."""
    cmd = [FFMPEG, "-v", "error", "-y"] + bg_input(bg)
    chain = ["[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
             "crop=%d:%d,format=rgb24[bg]" % (W, H, W, H)]
    cur = "bg"
    if slide_png is not None:
        cmd += ["-i", str(slide_png)]
        srect, box = geometry(layout, aspect, side)
        chain.append(shadow_chain(cur, srect, "b1", 1))
        chain.append("[1:v]scale=%d:%d:flags=lanczos[sl];[b1][sl]overlay=%d:%d[b2]"
                     % (srect[2], srect[3], srect[0], srect[1]))
        # The box shadow goes on after the slide: in pip the box sits on it.
        if box is not None:
            chain.append(shadow_chain("b2", box, "out", 2))
        else:
            chain.append("[b2]null[out]")
    else:
        chain.append("[%s]null[out]" % cur)
    cmd += ["-filter_complex", ";".join(chain), "-map", "[out]",
            "-frames:v", "1", str(path)]
    run(cmd)


# ---------------------------------------------------------------- timing

def load_segments(timing, info, n_slides):
    segs = timing.get("segments") or []
    if not segs:
        sys.exit("ERROR: timing.json has no segments.")
    fps = info["fps"]
    total = int(round(info["duration"] * fps))
    out = []
    for i, s in enumerate(segs):
        f0 = 0 if i == 0 else int(round(Fraction(str(s["start"])) * fps))
        if "slide" in s:
            n = int(s["slide"])
            if not 1 <= n <= n_slides:
                sys.exit("ERROR: segment %d asks for slide %d; the deck has %d."
                         % (i + 1, n, n_slides))
            kind = s.get("layout") or timing["layout"]
            if kind not in LAYOUTS:
                sys.exit("ERROR: segment %d: unknown layout %r (use %s)."
                         % (i + 1, kind, ", ".join(LAYOUTS)))
        elif s.get("show") == "speaker":
            n, kind = None, "speaker"
        else:
            sys.exit("ERROR: segment %d needs \"slide\": N or \"show\": \"speaker\"."
                     % (i + 1))
        out.append({"f0": f0, "slide": n, "kind": kind})
    for i, s in enumerate(out):
        s["f1"] = out[i + 1]["f0"] if i + 1 < len(out) else total
        if s["f1"] <= s["f0"]:
            sys.exit("ERROR: segment %d has no length: each start must come after "
                     "the one before, and before the end of the video." % (i + 1))
    return out, total


def ranges_expr(segs, kind):
    """overlay enable= expression: on for every frame of the given kind."""
    spans = []
    for s in segs:
        if s["kind"] != kind:
            continue
        if spans and spans[-1][1] == s["f0"]:
            spans[-1][1] = s["f1"]
        else:
            spans.append([s["f0"], s["f1"]])
    if not spans:
        return None
    return "+".join("between(n,%d,%d)" % (a, b - 1) for a, b in spans)


# ---------------------------------------------------------------- graph

def speaker_branches(kinds, info, aspect, side, cx):
    """Filter text that turns the lecturer's video into one stream per use."""
    uses = [k for k in ("side-by-side", "pip", "speaker") if k in kinds]
    parts = []
    for k in uses:
        if k == "speaker":
            parts.append("[s_speaker]scale=%d:%d:force_original_aspect_ratio=decrease,"
                         "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[o_speaker]"
                         % (W, H, W, H))
        else:
            _, box = geometry(k, aspect, side)
            cw, ch, x, y = speaker_crop(info["w"], info["h"], box[2], box[3], cx)
            parts.append("[s_%s]crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos,setsar=1[o_%s]"
                         % (k, cw, ch, x, y, box[2], box[3], k))
    return uses, parts


def build_graph(segs, plate_inputs, info, aspect, side, cx, still=False):
    fps = info["fps"]
    kinds = {s["kind"] for s in segs}
    uses, parts = speaker_branches(kinds, info, aspect, side, cx)
    chain = []
    src = "[0:v]setpts=PTS-STARTPTS" + ("" if still else ",fps=%s" % fps)
    if uses:
        if len(uses) == 1:
            chain.append(src + "[s_%s]" % uses[0])
        else:
            chain.append(src + ",split=%d%s" % (len(uses), "".join("[s_%s]" % u for u in uses)))
    chain += parts
    labels = []
    for i, s in enumerate(segs):
        idx = plate_inputs[i]
        lab = "p%d" % i
        if still:
            chain.append("[%d:v]format=yuv420p,setsar=1[%s]" % (idx, lab))
        else:
            chain.append("[%d:v]trim=end_frame=%d,setpts=PTS-STARTPTS,format=yuv420p,setsar=1[%s]"
                         % (idx, s["f1"] - s["f0"], lab))
        labels.append(lab)
    if len(labels) > 1:
        chain.append("%sconcat=n=%d:v=1:a=0,setpts=N/(%s)/TB[base]"
                     % ("".join("[%s]" % l for l in labels), len(labels), fps))
    else:
        chain.append("[%s]null[base]" % labels[0])
    cur = "base"
    for k in uses:
        expr = None if still else ranges_expr(segs, k)
        if k == "speaker":
            x, y = 0, 0
        else:
            _, box = geometry(k, aspect, side)
            x, y = box[0], box[1]
        en = (":enable='%s'" % expr) if expr else ""
        chain.append("[%s][o_%s]overlay=%d:%d:eof_action=repeat%s[c_%s]"
                     % (cur, k, x, y, en, k))
        cur = "c_" + k
    chain.append("[%s]format=yuv420p[vout]" % cur)
    return ";".join(chain)


# ---------------------------------------------------------------- main

def prepare(a):
    work = Path(a.work).expanduser().resolve()
    slides = json.loads((work / "slides.json").read_text())
    timing = json.loads(Path(a.timing).expanduser().read_text())
    # Precedence: command line, then timing.json, then the user's saved
    # choices in the plugin config ("slides" section), then the defaults.
    saved = {}
    if TV_DATA:
        try:
            saved = json.loads(Path(TV_DATA, "config.json").read_text()).get("slides") or {}
        except (OSError, ValueError):
            saved = {}
    for key in ("layout", "speaker_side", "speaker_x", "background"):
        val = getattr(a, key)
        if val is not None:
            timing[key] = val
        elif timing.get(key) is None and saved.get(key) is not None:
            timing[key] = saved[key]
    timing["layout"] = timing.get("layout") or "side-by-side"
    side = timing.get("speaker_side") or "right"
    bg = timing.get("background") or str(DEFAULT_BG)
    if not bg.startswith("#") and not Path(bg).expanduser().is_file():
        sys.exit("ERROR: no background image at %s" % bg)
    bg = bg if bg.startswith("#") else str(Path(bg).expanduser())
    info = probe(a.video)
    cx = timing.get("speaker_x")
    if cx is None:
        cx = speaker_x_from_config()
    if cx is None:
        cx = 0.5
    segs, total = load_segments(timing, info, slides["count"])
    aspect = float(slides["aspect"])

    plates = work / "plates"
    plates.mkdir(exist_ok=True)
    made = {}
    files = []
    for s in segs:
        if s["kind"] == "speaker":
            key = ("bg",)
        else:
            plate_layout = "slide" if s["kind"] == "slide" else s["kind"]
            key = (plate_layout, s["slide"])
        if key not in made:
            name = "plate-bg.png" if key == ("bg",) else \
                   "plate-%s-%03d.png" % (key[0], key[1])
            path = plates / name
            slide_png = None if key == ("bg",) else work / slides["pages"][key[1] - 1]["image"]
            make_plate(path, bg, slide_png, key[0] if key != ("bg",) else "slide",
                       aspect, side)
            made[key] = path
        files.append(made[key])
    return work, slides, timing, info, segs, total, files, aspect, side, cx


def render(a, ctx):
    work, slides, timing, info, segs, total, files, aspect, side, cx = ctx
    fps = info["fps"]
    # One input per segment, even when two segments share a plate: each
    # needs its own trimmed copy for the concat.
    cmd = [FFMPEG, "-v", "error", "-y", "-i", str(a.video)]
    plate_inputs = []
    for i, f in enumerate(files):
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(f)]
        plate_inputs.append(i + 1)
    graph = build_graph(segs, plate_inputs, info, aspect, side, cx)
    script = work / "filtergraph.txt"
    script.write_text(graph)
    cmd += ["-filter_complex_script", str(script), "-map", "[vout]"]
    if info["audio"]:
        cmd += ["-map", "0:a:0"]
        cmd += ["-c:a", "copy"] if info["audio"] == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-frames:v", str(total), "-r", str(fps),
            "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)]
    print("Rendering %d frames (%d segments) to %s" % (total, len(segs), a.out))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("ERROR: the render failed. The filter graph is in %s" % script)
    check(a, info, segs, total)
    write_source(work, a, info, total)


def write_source(work, a, info, total):
    """Record which cut this slides video was made from, in WORK/source.json.

    perfect-clips cuts upright clips from the SPEAKER cut, so it must find
    that cut. Reading it from here means the user can rename or move the
    slides video freely; older folders without this file fall back to the
    name rule (<cut stem>-with-slides.mp4)."""
    rec = {
        "_comment": "Written by video-with-slides compose.py. Read by "
                    "perfect-clips (slides_plan.py detect) to find the cut.",
        "cut": str(Path(a.video).expanduser().resolve()),
        "cut_duration": round(float(info["duration"]), 3),
        "cut_frames": int(total),
        "fps": str(info["fps"]),
        "output": str(Path(a.out).expanduser().resolve()),
    }
    (Path(work) / "source.json").write_text(json.dumps(rec, indent=1) + "\n")


def check(a, info, segs, total):
    out = probe(a.out)
    fps = info["fps"]
    frames = int(round(out["duration"] * fps))
    ok = abs(frames - total) <= 1
    print("Length: %.3f s, source %.3f s (%s)" % (
        out["duration"], info["duration"], "ok" if ok else "MISMATCH"))
    if info["audio"] and not out["audio"]:
        print("ERROR: the output has no sound.")
    # One still from the middle of each kind of segment, for a look.
    shots = Path(a.work) / "check"
    shots.mkdir(exist_ok=True)
    seen = set()
    for s in segs:
        if s["kind"] in seen:
            continue
        seen.add(s["kind"])
        t = float((s["f0"] + s["f1"]) / 2 / fps)
        dest = shots / ("check-%s.png" % s["kind"])
        run([FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % t, "-i", str(a.out),
             "-frames:v", "1", str(dest)])
        print("Look at: %s (%.1f s)" % (dest, t))


def preview(a, ctx):
    """Stills of the composite at chosen times, without a render."""
    work, slides, timing, info, segs, total, files, aspect, side, cx = ctx
    fps = info["fps"]
    if a.at:
        times = [float(t) for t in a.at.split(",")]
    else:
        times, seen = [], set()
        for s in segs:
            if s["kind"] not in seen:
                seen.add(s["kind"])
                times.append(float((s["f0"] + s["f1"]) / 2 / fps))
    shots = work / "check"
    shots.mkdir(exist_ok=True)
    for t in times:
        f = int(round(t * float(fps)))
        i = next((j for j, s in enumerate(segs) if s["f0"] <= f < s["f1"]), len(segs) - 1)
        seg = dict(segs[i], f0=0, f1=1)
        frame = shots / "src.png"
        run([FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % t, "-i", str(a.video),
             "-frames:v", "1", str(frame)])
        graph = build_graph([seg], [1], info, aspect, side, cx, still=True)
        dest = shots / ("preview-%07.2fs.png" % t)
        run([FFMPEG, "-v", "error", "-y", "-i", str(frame), "-i", str(files[i]),
             "-filter_complex", graph, "-map", "[vout]", "-frames:v", "1", str(dest)])
        label = ("slide %d, %s" % (seg["slide"], seg["kind"])) if seg["slide"] else "speaker"
        print("Look at: %s (%.1f s, %s)" % (dest, t, label))
    frame = shots / "src.png"
    if frame.exists():
        frame.unlink()
    print("Speaker crop centred at %.2f of the frame width." % cx)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", required=True, help="The cut lecture video")
    ap.add_argument("--work", required=True, help="Folder with slides/ and slides.json")
    ap.add_argument("--timing", required=True, help="timing.json")
    ap.add_argument("--out", help="Output .mp4 (not needed with --preview)")
    ap.add_argument("--layout", choices=LAYOUTS, default=None)
    ap.add_argument("--speaker-side", dest="speaker_side",
                    choices=("right", "left"), default=None)
    ap.add_argument("--speaker-x", dest="speaker_x", type=float, default=None,
                    help="Centre of the speaker, as a fraction of the frame width")
    ap.add_argument("--background", default=None,
                    help="Background image, or a colour like #1e1b3a")
    ap.add_argument("--preview", action="store_true",
                    help="Write stills to WORK/check/ instead of rendering")
    ap.add_argument("--at", default=None,
                    help="With --preview: comma-separated times in seconds")
    ap.add_argument("--crf", type=int, default=19)
    ap.add_argument("--preset", default="fast")
    a = ap.parse_args()
    if a.speaker_x is not None and not 0 <= a.speaker_x <= 1:
        sys.exit("ERROR: --speaker-x is a fraction of the frame width, 0 to 1.")
    if not a.preview and not a.out:
        sys.exit("ERROR: --out is required unless --preview is given.")
    ctx = prepare(a)
    if a.preview:
        preview(a, ctx)
    else:
        render(a, ctx)


if __name__ == "__main__":
    main()
