#!/usr/bin/env python3
"""Layout plan for upright clips of a slide-deck lecture.

When the video folder holds `video-with-slides` output, an upright clip is
split horizontally wherever the approved slide timing shows a slide: the
slide on the TOP panel, the speaker's head and shoulders on the BOTTOM panel
(rule 8's split doctrine). Where the timing shows the speaker alone, the clip
uses the normal single-speaker crop. No OpenCV, no probe: the slide timing
already says what is on screen, frame by frame.

Two commands:

  python3 slides_plan.py detect "<video folder>"
      Prints JSON: whether the folder holds video-with-slides output, and the
      paths of timing.json, slides.json, the with-slides MP4 and the SPEAKER
      cut it was made from (the clean cut, same timeline). Exit 0 = found,
      1 = not a slide-deck lecture.

  python3 slides_plan.py plan --clip "<work>/clip NN cuts.json" \
      --slides-dir "<video folder>/slides-video" \
      --out "<work>/clip NN layout plan.json" \
      --face-x 0.61 --face-y 0.44 [--head 0.60] [--panels "<work>/panels"] \
      [--background PNG_OR_HEX]
      Writes the layout plan that render_clip.py --plan and
      render_captions.mjs --plan read, and one 1080x960 top-panel image per
      slide used.

--face-x / --face-y: the centre of the speaker's face as fractions of the
source frame, measured from one extracted frame. --head: the height of the
head-and-shoulders crop as a fraction of the source height (0.60 keeps the
head, shoulders and upper chest of a seated speaker).

Times become frames exactly as video-with-slides' compose.py does it
(round(start * fps) on the cut's nominal rate), so a layout change in the
clip lands on the same frame as the slide change in the wide video. Clip
segments are in SOURCE frames (the speaker cut), so no extra mapping is
needed: a slide change inside a kept segment splits that segment there.
"""
import pc_env  # noqa: F401  (tool PATH; see pc_env.py)
import argparse
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

OUT_W, PANEL_H = 1080, 960
# The slide sits inside this box of the top panel (panel coordinates). The
# top ~250 px of an upright frame sit under phone app buttons (rule 5), and
# the caption chip rides the seam at y 960, so the slide keeps clear of both.
SAFE_X0, SAFE_X1 = 40, 1040
SAFE_Y0, SAFE_Y1 = 262, 892
MIN_SLIVER_S = 0.4      # shorter layout regions at a segment edge get merged
FACE_FROM_TOP = 0.36    # face centre sits this far down the speaker panel

SKILLS = Path(__file__).resolve().parents[2]
DEFAULT_BG = SKILLS / "video-with-slides" / "assets" / "background.png"
VIDEO_EXT = {".mp4", ".mov", ".m4v"}


def fps_fraction(fps):
    return Fraction(str(fps)).limit_denominator(1001)


# ------------------------------------------------------------------ detect

def find_cut(folder, stem, skip):
    """The speaker cut: a video named <stem> anywhere in the folder."""
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() in VIDEO_EXT and p.stem == stem and skip not in p.parents:
            return p
    return None


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out) if out else None


def read_source(work):
    """compose.py's record of the cut it started from, or None (older runs)."""
    try:
        rec = json.loads((Path(work) / "source.json").read_text())
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("cut") else None


def same_length(path, seconds):
    d = duration(path)
    return d is not None and abs(d - seconds) < 0.05


def find_by_record(folder, work, rec):
    """Cut and slides video from source.json, surviving a rename or a move.

    The recorded paths win when they still exist. A cut that moved is found
    again by its file name and length; a slides video that was renamed is
    the one video in the video folder or slides-video/ (not the cut, not a
    clip package) with the cut's length."""
    cut = Path(rec["cut"])
    if not cut.is_file():
        cut = next((p for p in sorted(Path(folder).rglob(cut.name))
                    if p.suffix.lower() in VIDEO_EXT and work not in p.parents
                    and same_length(p, rec.get("cut_duration", 0))), None)
    out = Path(rec.get("output", ""))
    if not out.is_file():
        cands = [p for d in (work, Path(folder)) if d.is_dir()
                 for p in sorted(d.iterdir())
                 if p.suffix.lower() in VIDEO_EXT and p.is_file()
                 and (cut is None or p.resolve() != cut.resolve())]
        cands = [p for p in cands if same_length(p, rec.get("cut_duration", 0))
                 and "slides" in p.name.lower()] or \
                [p for p in cands if same_length(p, rec.get("cut_duration", 0))
                 and p.parent == work]
        out = cands[0] if len(cands) == 1 else None
    return cut, out


def cmd_detect(a):
    folder = Path(a.folder).expanduser()
    work = folder / "slides-video"
    res = {"found": False, "work": str(work)}
    timing, slides = work / "timing.json", work / "slides.json"
    if not (timing.is_file() and slides.is_file()):
        print(json.dumps(res, indent=1))
        return 1
    rec = read_source(work)
    if rec:
        # compose.py recorded the cut: names no longer matter.
        cut, with_slides = find_by_record(folder, work, rec)
        res["via"] = "source.json"
        if with_slides is None:
            res.update(found=True, timing=str(timing), slides=str(slides),
                       with_slides=None, cut=str(cut) if cut else None,
                       cut_matches=False,
                       note="slides-video/source.json names a slides video "
                            "that is no longer there, and no single video in "
                            "the folder has the cut's length. Ask the user "
                            "which file is the slides video.")
            print(json.dumps(res, indent=1))
            return 0
        stem = Path(rec["cut"]).stem
    else:
        # Older folders: the name rule, <cut stem>-with-slides.mp4.
        outs = sorted(work.glob("*-with-slides.mp4"))
        if not outs:
            print(json.dumps(res, indent=1))
            return 1
        with_slides = outs[-1]
        stem = with_slides.stem[: -len("-with-slides")]
        cut = find_cut(folder, stem, work)
        res["via"] = "file name"
    res.update(found=True, timing=str(timing), slides=str(slides),
               with_slides=str(with_slides),
               cut=str(cut) if cut else None)
    if cut:
        d_cut, d_ws = duration(cut), duration(with_slides)
        res["cut_matches"] = (d_cut is not None and d_ws is not None
                              and abs(d_cut - d_ws) < 0.05)
    else:
        res["cut_matches"] = False
        res["note"] = ("No video named '%s' in the folder. Ask the user which "
                       "file is the cut that video-with-slides started from."
                       % stem)
    print(json.dumps(res, indent=1))
    return 0


# -------------------------------------------------------------------- plan

def resolve_background(arg, timing):
    bg = arg or timing.get("background")
    data = os.environ.get("TV_DATA", "").strip()
    if not bg and data:
        try:
            cfg = json.loads(Path(data, "config.json").read_text())
            bg = (cfg.get("slides") or {}).get("background")
        except (OSError, ValueError):
            pass
    bg = bg or str(DEFAULT_BG)
    if not bg.startswith("#"):
        bg = str(Path(bg).expanduser())
        if not Path(bg).is_file():
            sys.exit("ERROR: no background image at %s" % bg)
    return bg


# Slide content crop. A slide made for a wide screen often has broad empty
# margins; in the upright top panel the whole slide shrinks to ~1000 px wide,
# so a 3-bullet slide reads at ~2.5% of the frame height. Cropping to the
# content (plus padding) before fitting makes the text larger. It never cuts
# content: the box comes from every pixel that differs from the slide's own
# background colour, measured on a 480-px-wide copy, then widened by one
# measuring pixel and CROP_PAD of the slide size on each side.
PROBE_W = 480
BG_DIFF = 28            # max channel difference that still counts as background
CROP_PAD = 0.04         # padding around the content, fraction of slide size
CROP_MIN_GAIN = 1.10    # crop only when the text grows by at least 10%


def content_box(slide_png):
    """(x, y, w, h) of the slide's content in source pixels, or None when the
    slide has no margin worth cropping. Stdlib only: reads a small raw RGB
    copy through ffmpeg."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(slide_png)],
        capture_output=True, text=True).stdout.strip()
    try:
        sw, sh = (int(v) for v in probe.split(",")[:2])
    except ValueError:
        return None
    pw = PROBE_W
    ph = max(1, round(sh * pw / sw))
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(slide_png), "-vf",
         "scale=%d:%d:flags=area,format=rgb24" % (pw, ph),
         "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(raw) != pw * ph * 3:
        return None

    def px(x, y):
        i = (y * pw + x) * 3
        return raw[i], raw[i + 1], raw[i + 2]

    border = [px(x, 0) for x in range(pw)] + [px(x, ph - 1) for x in range(pw)] + \
             [px(0, y) for y in range(ph)] + [px(pw - 1, y) for y in range(ph)]
    counts = {}
    for c in border:
        key = (c[0] // 8, c[1] // 8, c[2] // 8)
        counts[key] = counts.get(key, 0) + 1
    top = max(counts, key=counts.get)
    if counts[top] < 0.6 * len(border):
        return None          # no uniform background (a photo slide): leave it
    ref = [v * 8 + 4 for v in top]
    x0, y0, x1, y1 = pw, ph, -1, -1
    for y in range(ph):
        for x in range(pw):
            r, g, b = px(x, y)
            if max(abs(r - ref[0]), abs(g - ref[1]), abs(b - ref[2])) > BG_DIFF:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if x1 < 0:
        return None          # blank slide
    k = sw / pw
    padx, pady = CROP_PAD * sw, CROP_PAD * sh
    cx0 = max(0, int((x0 - 1) * k - padx))
    cy0 = max(0, int((y0 - 1) * k - pady))
    cx1 = min(sw, int((x1 + 2) * k + padx + 1))
    cy1 = min(sh, int((y1 + 2) * k + pady + 1))
    bw, bh = SAFE_X1 - SAFE_X0, SAFE_Y1 - SAFE_Y0
    before = min(bw / sw, bh / sh)
    after = min(bw / (cx1 - cx0), bh / (cy1 - cy0))
    if after < CROP_MIN_GAIN * before:
        return None
    return cx0, cy0, cx1 - cx0, cy1 - cy0, round(after / before, 2)


def make_panel(slide_png, bg, out_png):
    """1080x960 top panel: the slide, cropped to its content when it has wide
    empty margins, fitted (never stretched) into the safe box, centred, on
    the slide background. Returns the text-size gain of the crop (1.0 = no
    crop)."""
    bw, bh = SAFE_X1 - SAFE_X0, SAFE_Y1 - SAFE_Y0
    box = content_box(slide_png)
    crop = "crop=%d:%d:%d:%d," % (box[2], box[3], box[0], box[1]) if box else ""
    if bg.startswith("#"):
        bg_in = ["-f", "lavfi", "-i",
                 "color=c=0x%s:s=%dx%d" % (bg[1:], OUT_W, PANEL_H)]
        bg_chain = "[0:v]format=rgb24[bg];"
    else:
        bg_in = ["-i", bg]
        bg_chain = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
                    "crop=%d:%d,format=rgb24[bg];" % (OUT_W, PANEL_H, OUT_W, PANEL_H))
    fc = (bg_chain +
          "[1:v]" + crop + "scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
          "format=rgb24[sl];"
          "[bg][sl]overlay=x=%d+(%d-w)/2:y=%d+(%d-h)/2:format=rgb" % (
              bw, bh, SAFE_X0, bw, SAFE_Y0, bh))
    cmd = (["ffmpeg", "-nostdin", "-v", "error", "-y"] + bg_in +
           ["-i", str(slide_png), "-filter_complex", fc, "-frames:v", "1",
            str(out_png)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR: panel render failed for %s:\n%s" % (slide_png, r.stderr[-800:]))
    return box[4] if box else 1.0


def speaker_rect(fx, fy, head, w, h):
    """Head-and-shoulders crop with the exact 1080:960 panel aspect, as
    [x, y, w, h] fractions of the source frame."""
    ch = head * h
    cw = ch * OUT_W / PANEL_H
    if cw > w:
        cw = w
        ch = cw * PANEL_H / OUT_W
    x = min(max(fx * w - cw / 2, 0), w - cw)
    y = min(max(fy * h - FACE_FROM_TOP * ch, 0), h - ch)
    return [round(x / w, 4), round(y / h, 4), round(cw / w, 4), round(ch / h, 4)]


def timing_frames(timing, fps):
    """Each segment's start frame and what it shows, as compose.py computes it."""
    out = []
    for i, s in enumerate(timing.get("segments") or []):
        f0 = 0 if i == 0 else int(round(Fraction(str(s["start"])) * fps))
        if "slide" in s:
            out.append((f0, int(s["slide"])))
        elif s.get("show") == "speaker":
            out.append((f0, None))
        else:
            sys.exit("ERROR: timing segment %d needs \"slide\" or \"show\": "
                     "\"speaker\"." % (i + 1))
    if not out:
        sys.exit("ERROR: timing.json has no segments.")
    return out


def shows_at(frames, f):
    cur = frames[0][1]
    for f0, slide in frames:
        if f0 <= f:
            cur = slide
        else:
            break
    return cur


def cmd_plan(a):
    spec = json.loads(Path(a.clip).read_text())
    sd = Path(a.slides_dir).expanduser()
    timing = json.loads((sd / "timing.json").read_text())
    slides = json.loads((sd / "slides.json").read_text())
    src = Path(spec["source"])
    rec = read_source(sd)
    made_here = False
    if rec:
        # The slides video under any name: the same lookup detect uses.
        _, ws = find_by_record(sd.parent, sd, rec)
        made_here = ws is not None and src.exists() and \
            ws.resolve() == src.resolve()
    if src.stem.endswith("-with-slides") or made_here:
        sys.exit("ERROR: this clip is cut from the with-slides video. Cut "
                 "upright clips from the SPEAKER cut that video-with-slides "
                 "started from (slides_plan.py detect names it).")
    fps = fps_fraction(spec["fps"])
    w, h = spec["width"], spec["height"]
    frames = timing_frames(timing, fps)
    pages = {p["n"]: p for p in slides["pages"]}
    bg = resolve_background(a.background, timing)
    panels = Path(a.panels).expanduser() if a.panels else Path(a.out).parent / "panels"
    panels.mkdir(parents=True, exist_ok=True)
    rect = speaker_rect(a.face_x, a.face_y, a.head, w, h)
    sliver = max(1, int(round(MIN_SLIVER_S * fps)))

    regions, made, merged = [], {}, []
    for c in spec["clips"]:
        cuts = [c["in_frame"]] + [f0 for f0, _ in frames
                                 if c["in_frame"] < f0 < c["out_frame"]] + [c["out_frame"]]
        seg = [[cuts[i], cuts[i + 1], shows_at(frames, cuts[i])]
               for i in range(len(cuts) - 1)]
        # A sliver at a segment edge would flash one layout for a few frames:
        # give it to its neighbour inside the same segment.
        if len(seg) > 1 and seg[0][1] - seg[0][0] < sliver:
            merged.append((seg[0][0], seg[0][1]))
            seg[1][0] = seg[0][0]
            seg.pop(0)
        if len(seg) > 1 and seg[-1][1] - seg[-1][0] < sliver:
            merged.append((seg[-1][0], seg[-1][1]))
            seg[-2][1] = seg[-1][1]
            seg.pop()
        # Neighbours that show the same thing become one region.
        tight = []
        for s in seg:
            if tight and tight[-1][2] == s[2]:
                tight[-1][1] = s[1]
            else:
                tight.append(s)
        for f_in, f_out, slide in tight:
            if slide is None:
                regions.append({"in_frame": f_in, "out_frame": f_out,
                                "mode": "crop", "face_x": round(a.face_x, 4)})
                continue
            if slide not in pages:
                sys.exit("ERROR: timing shows slide %d; slides.json has %d."
                         % (slide, len(pages)))
            if slide not in made:
                png = panels / ("slide-%03d-panel.png" % slide)
                gain = make_panel(sd / pages[slide]["image"], bg, png)
                made[slide] = str(png)
                if gain > 1.0:
                    print("slide %d: cropped to its content, text %.0f%% larger"
                          % (slide, (gain - 1) * 100))
            regions.append({"in_frame": f_in, "out_frame": f_out, "mode": "split",
                            "slide": slide, "slide_panel": made[slide],
                            "speaker": rect})

    plan = {"_comment": "Made by slides_plan.py from video-with-slides timing. "
                        "split = slide on top, speaker below; crop = speaker alone.",
            "source": str(src), "regions": regions}
    Path(a.out).write_text(json.dumps(plan, indent=1))

    print("%-6s %-12s %-8s %s" % ("#", "clip time", "frames", "shows"))
    t = 0
    for i, r in enumerate(regions, 1):
        n = r["out_frame"] - r["in_frame"]
        what = "slide %d + speaker" % r["slide"] if r["mode"] == "split" else "speaker"
        print("%-6d %-12s %-8d %s" % (i, "%.2f-%.2f" % (t / fps, (t + n) / fps), n, what))
        t += n
    for f_in, f_out in merged:
        print("merged a %d-frame sliver at source frames %d-%d into its neighbour"
              % (f_out - f_in, f_in, f_out))
    print("speaker panel crop (fractions of the source): %s" % rect)
    print("plan -> %s" % a.out)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("folder")
    p = sub.add_parser("plan")
    p.add_argument("--clip", required=True)
    p.add_argument("--slides-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--face-x", type=float, required=True)
    p.add_argument("--face-y", type=float, required=True)
    p.add_argument("--head", type=float, default=0.60)
    p.add_argument("--panels", default=None)
    p.add_argument("--background", default=None)
    a = ap.parse_args()
    if a.cmd == "detect":
        sys.exit(cmd_detect(a))
    if not (0 < a.face_x < 1 and 0 < a.face_y < 1 and 0.2 <= a.head <= 1):
        sys.exit("ERROR: --face-x/--face-y are fractions in (0,1); --head in [0.2,1].")
    sys.exit(cmd_plan(a))


if __name__ == "__main__":
    main()
