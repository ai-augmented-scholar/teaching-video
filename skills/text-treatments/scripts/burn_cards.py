#!/usr/bin/env python3
"""Burn text cards into a finished video, each at the words it belongs to.

  burn_cards.py plan VIDEO --cards cards.json --out-dir DIR
      Transcribes VIDEO (the user's final export), finds each card's anchor
      words, sets every card's start, length and row times, and writes
      DIR/cards-timed.json. Prints the timing table for the user to approve.
      The words are kept in DIR/<video>-words.json and reused while the video
      file is unchanged.

  burn_cards.py burn VIDEO --timed DIR/cards-timed.json --clip ALPHA.mov
                     --out VIDEO-with-cards.mp4 [--sheet SHEET.png]
      Lays every card from the alpha clip over VIDEO at its time, in one
      ffmpeg pass. Sound is copied unchanged. --sheet writes one frame per
      card, tiled, to look at before the hand-off.

Between the two: render the alpha clip from cards-timed.json with render.mjs
(the same file, so the clip and the times agree; `burn` checks this).

Stdlib only; runs on /usr/bin/python3 (3.9).
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import place_cards  # noqa: E402


def die(msg):
    sys.exit("burn_cards: " + msg)


def probe(path):
    out = subprocess.run(
        [place_cards.tool("ffprobe"), "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt:format=duration",
         "-of", "json", str(path)], stdout=subprocess.PIPE, check=True).stdout
    d = json.loads(out)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        die("%s has no video stream" % path)
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    return {"w": v["width"], "h": v["height"], "num": num, "den": den,
            "fps": num / den, "pix": v.get("pix_fmt", ""),
            "duration": float(d["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}


def plan(a):
    video = Path(a.video).expanduser().resolve()
    out = Path(a.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    words_path = out / (video.stem + "-words.json")
    stamp = {"file": str(video), "size": video.stat().st_size,
             "mtime": int(video.stat().st_mtime)}
    words = None
    if words_path.is_file():
        old = json.loads(words_path.read_text())
        if old.get("source") == stamp:
            words = old
    if words is None:
        words = place_cards.words_for(video, place_cards.find_transcribe(a.transcribe))
        words["source"] = stamp
        words_path.write_text(json.dumps(words, ensure_ascii=False))

    raw = json.loads(Path(a.cards).expanduser().read_text())
    cards = raw["cards"] if isinstance(raw, dict) else raw
    wlist, _ = place_cards.load_words(words_path)
    placed, duration = place_cards.place(cards, wlist, info["duration"], info["fps"])
    timed = []
    for c in placed:
        d = {k: v for k, v in c.items() if not k.startswith("_")}
        d["place"] = {"heard": c["_heard"], "notes": c["_notes"]}
        timed.append(d)
    target = out / "cards-timed.json"
    target.write_text(json.dumps({"fps": info["fps"], "duration": duration,
                                  "video": str(video), "cards": timed},
                                 ensure_ascii=False, indent=1))
    print(place_cards.table(placed))
    print("\n%d cards. Timed cards -> %s" % (len(placed), target))


def burn(a):
    video = Path(a.video).expanduser().resolve()
    clip = Path(a.clip).expanduser().resolve()
    out = Path(a.out).expanduser()
    if out.resolve() == video:
        die("--out must be a new file")
    timed = json.loads(Path(a.timed).expanduser().read_text())
    cards = timed["cards"]
    v, c = probe(video), probe(clip)
    if not c["pix"].startswith(("yuva", "rgba", "argb", "bgra", "abgr")):
        die("%s has no alpha channel (%s). Render the alpha mode." % (clip.name, c["pix"]))

    # Where each card sits inside the clip: render.mjs lays them end to end,
    # round(dur * fps) frames each, in the order of the cards file.
    fps_num, fps_den = c["num"], c["den"]
    offsets, acc = [], 0
    for card in cards:
        offsets.append(acc)
        acc += int(round(float(card["dur"]) * fps_num / fps_den))
    clip_frames = round(c["duration"] * fps_num / fps_den)
    if abs(clip_frames - acc) > 2:
        die("the clip has %d frames but the timed cards add up to %d. Render the clip "
            "from the same cards-timed.json." % (clip_frames, acc))

    live = [(i, card) for i, card in enumerate(cards) if card.get("start") is not None]
    if not live:
        die("no card has a start time")
    chains = ["[1:v]format=yuva444p,scale=%d:%d,split=%d%s" % (
        v["w"], v["h"], len(live), "".join("[c%d]" % i for i, _ in live))]
    last = "0:v"
    for n, (i, card) in enumerate(live):
        f0 = offsets[i]
        f1 = f0 + int(round(float(card["dur"]) * fps_num / fps_den))
        t0 = float(card["start"])
        chains.append("[c%d]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS+%.6f/TB[s%d]"
                      % (i, f0, f1, t0, i))
        nxt = "v%d" % n
        chains.append("[%s][s%d]overlay=0:0:format=auto:eof_action=pass:repeatlast=0:"
                      "enable='between(t,%.6f,%.6f)'[%s]"
                      % (last, i, t0, t0 + float(card["dur"]), nxt))
        last = nxt
    chains.append("[%s]format=yuv420p[vout]" % last)

    cmd = [place_cards.tool("ffmpeg"), "-v", "error", "-y",
           "-i", str(video), "-i", str(clip),
           "-filter_complex", ";".join(chains), "-map", "[vout]"]
    if v["audio"]:
        cmd += ["-map", "0:a:0", "-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
            "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)

    got = probe(out)
    if abs(got["duration"] - v["duration"]) > 0.1:
        die("the output is %.2f s, the video %.2f s" % (got["duration"], v["duration"]))
    print("wrote %s (%d cards, %.1f s)" % (out, len(live), got["duration"]))

    if a.sheet:
        sheet(out, live, Path(a.sheet).expanduser())


def sheet(video, live, target):
    """One frame per card, at the moment its text is complete, tiled."""
    ffmpeg = place_cards.tool("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="burn-cards-") as work:
        for n, (_i, card) in enumerate(live):
            entries = card.get("delays") or [1.4]
            at = float(card["start"]) + min(float(card["dur"]) - 0.8, max(entries) + 1.2)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", "%.3f" % at, "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=640:-2",
                            str(Path(work) / ("f%02d.png" % n))], check=True)
        cols = 3
        rows = (len(live) + cols - 1) // cols
        subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", "1",
                        "-i", str(Path(work) / "f%02d.png"),
                        "-vf", "tile=%dx%d:padding=8:color=white" % (cols, rows),
                        "-frames:v", "1", str(target)], check=True)
    print("contact sheet: %s" % target)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("video")
    p.add_argument("--cards", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--transcribe", default=None)
    b = sub.add_parser("burn")
    b.add_argument("video")
    b.add_argument("--timed", required=True)
    b.add_argument("--clip", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--sheet", default=None)
    b.add_argument("--crf", type=int, default=19)
    b.add_argument("--preset", default="fast")
    a = ap.parse_args()
    plan(a) if a.cmd == "plan" else burn(a)


if __name__ == "__main__":
    main()
