#!/usr/bin/env python3
"""The make-video status file: one JSON file per video, read and written only here.

The conductor skill never edits make-video-status.json by hand. Every change
goes through this script, so the file always has the same shape and a session
that resumes after a break finds exactly where the last one stopped.

Usage:
  status.py new   --title "Why the Enlightenment is not the Renaissance" [--slug S] [--root DIR]
  status.py init  VIDEO_DIR --title T
  status.py show  VIDEO_DIR              # table of the 14 steps + the next step
  status.py next  VIDEO_DIR              # JSON: the first step that is not done or skipped
  status.py set   VIDEO_DIR STEP STATE [--input F]... [--output F]... [--note N] [--choice K=V]...
  status.py reopen VIDEO_DIR STEP        # send a step (and every later one) back to pending
  status.py find  [--root DIR] [QUERY]   # list video folders and where each one stands
  status.py look                         # one-line summary of the saved look, or "none"

STATE is one of: pending, running, waiting-for-you, done, skipped.
STEP is the two-digit step number ("04") or the step key ("cut").

Settings come from $TV_DATA/config.json (the skill passes TV_DATA). The videos
folder is `videos_root` there, default ~/Movies/teaching-videos; --root
overrides it. Standard library only, so the macOS system python3 runs it.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

STATUS_NAME = "make-video-status.json"
STATES = ("pending", "running", "waiting-for-you", "done", "skipped")
FINISHED = ("done", "skipped")

# The 14 steps of the workflow, in order. owner: who does the work.
STEPS = [
    ("01", "beatsheet",  "Draft the beat sheet",          "you + Claude", "beatsheet"),
    ("02", "film",       "Film",                          "you",          None),
    ("03", "sound",      "Clean the sound",               "Claude",       "audio-enhance"),
    ("04", "cut",        "Cut the retakes",               "Claude",       "perfect-cuts"),
    ("05", "review",     "Review the cut",                "you",          None),
    ("06", "cards",      "Text cards or slides",          "Claude",       "text-treatments | video-with-slides"),
    ("07", "assemble",   "Assemble in the editor",        "you",          None),
    ("08", "thumbnail",  "Title, opening and thumbnail",  "Claude + you", "first-impression"),
    ("09", "captions",   "Captions and description",      "Claude",       "captions-and-description"),
    ("10", "publish",    "Publish on the course site",    "you",          None),
    ("11", "clips",      "Short clips",                   "Claude",       "perfect-clips"),
    ("12", "pick",       "Pick the clips",                "you",          None),
    ("13", "polish",     "Polish the clips",              "you",          None),
    ("14", "publish-clips", "Publish the clips",          "you",          None),
]


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def tv_config():
    data = os.environ.get("TV_DATA", "")
    path = Path(data, "config.json") if data else None
    if path and path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            sys.exit(f"ERROR: cannot read {path}: {exc}")
    return {}


def videos_root(cli_root=None):
    root = cli_root or tv_config().get("videos_root") or "~/Movies/teaching-videos"
    return Path(os.path.expanduser(root))


SLUG_SKIP = {"a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "is", "are", "with", "my", "your"}


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    words = [w for w in s.split("-") if w and w not in SLUG_SKIP][:6]
    return "-".join(words) or "video"


def status_path(video_dir):
    return Path(video_dir).expanduser().resolve() / STATUS_NAME


def load(video_dir):
    p = status_path(video_dir)
    if not p.is_file():
        sys.exit(f"ERROR: no {STATUS_NAME} in {p.parent}. Start the video with `status.py new` or `init`.")
    return json.loads(p.read_text(encoding="utf-8"))


def save(video_dir, data):
    p = status_path(video_dir)
    data["updated"] = now()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)  # atomic: a crash never leaves half a file


def fresh(title, folder):
    return {
        "title": title,
        "folder": str(folder),
        "created": now(),
        "updated": now(),
        "steps": [
            {"step": n, "key": k, "name": name, "owner": owner, "skill": skill,
             "state": "pending", "inputs": [], "outputs": [], "choices": {},
             "notes": [], "started": None, "finished": None}
            for n, k, name, owner, skill in STEPS
        ],
    }


def find_step(data, ref):
    ref = ref.strip().lower()
    if ref.isdigit():
        ref = ref.zfill(2)
    for s in data["steps"]:
        if s["step"] == ref or s["key"] == ref:
            return s
    sys.exit(f"ERROR: no step '{ref}'. Use 01-14 or one of: " + ", ".join(k for _, k, *_ in STEPS))


def next_step(data):
    for s in data["steps"]:
        if s["state"] not in FINISHED:
            return s
    return None


def table(data):
    lines = [f"{data['title']}  ({data['folder']})", ""]
    width = max(len(s["name"]) for s in data["steps"])
    nxt = next_step(data)
    for s in data["steps"]:
        mark = "->" if nxt is s else "  "
        extra = []
        if s["choices"]:
            extra.append(", ".join(f"{k}={v}" for k, v in s["choices"].items()))
        # Every output, not only the last: steps 06 and 09 write several files
        # (two renders; captions plus description), and the user needs them all.
        if s["outputs"]:
            extra.append("out: " + ", ".join(Path(o).name for o in s["outputs"]))
        lines.append(f"{mark} {s['step']}  {s['name']:<{width}}  {s['owner']:<12}  {s['state']:<15}  {'; '.join(extra)}")
    lines.append("")
    lines.append("Next: " + (f"step {nxt['step']}, {nxt['name']} ({nxt['state']})" if nxt else "nothing - every step is done."))
    return "\n".join(lines)


def cmd_new(a):
    root = videos_root(a.root)
    root.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for d in root.iterdir() if d.is_dir() and (m := re.match(r"^(\d{2,})-", d.name))]
    num = (max(nums) + 1) if nums else 1
    folder = root / f"{num:02d}-{a.slug or slugify(a.title)}"
    folder.mkdir()
    save(folder, fresh(a.title, folder))
    print(folder)


def cmd_init(a):
    folder = Path(a.video_dir).expanduser().resolve()
    if status_path(folder).exists():
        sys.exit(f"ERROR: {STATUS_NAME} already exists in {folder}; use `show` to resume.")
    folder.mkdir(parents=True, exist_ok=True)
    save(folder, fresh(a.title, folder))
    print(folder)


def cmd_show(a):
    print(table(load(a.video_dir)))


def cmd_next(a):
    s = next_step(load(a.video_dir))
    print(json.dumps(s, indent=2, ensure_ascii=False) if s else "null")


def cmd_set(a):
    if a.state not in STATES:
        sys.exit(f"ERROR: state must be one of {', '.join(STATES)}")
    data = load(a.video_dir)
    s = find_step(data, a.step)
    # Steps run in order. Refuse to start or finish a step while an earlier one is open,
    # unless the earlier one was explicitly skipped.
    if a.state in ("running", "done", "waiting-for-you") and not a.force:
        for earlier in data["steps"]:
            if earlier is s:
                break
            if earlier["state"] not in FINISHED:
                sys.exit(f"ERROR: step {earlier['step']} ({earlier['name']}) is still {earlier['state']}. "
                         f"Finish or skip it first, or pass --force.")
    s["state"] = a.state
    if a.state in ("running", "waiting-for-you") and not s["started"]:
        s["started"] = now()
    if a.state in FINISHED:
        s["finished"] = now()
    for f in a.input or []:
        f = str(Path(f).expanduser().resolve())
        if f not in s["inputs"]:
            s["inputs"].append(f)
    for f in a.output or []:
        f = str(Path(f).expanduser().resolve())
        if a.state == "done" and not Path(f).exists():
            sys.exit(f"ERROR: output does not exist: {f}")
        if f not in s["outputs"]:
            s["outputs"].append(f)
    for kv in a.choice or []:
        if "=" not in kv:
            sys.exit("ERROR: --choice takes KEY=VALUE")
        k, v = kv.split("=", 1)
        s["choices"][k.strip()] = v.strip()
    if a.note:
        s["notes"].append(f"{now()}  {a.note}")
    save(a.video_dir, data)
    print(table(data))


def cmd_reopen(a):
    data = load(a.video_dir)
    s = find_step(data, a.step)
    hit = False
    for x in data["steps"]:
        if x is s:
            hit = True
        if hit and x["state"] != "pending":
            x["state"] = "pending"
            x["finished"] = None
            x["notes"].append(f"{now()}  reopened from step {s['step']}")
    save(a.video_dir, data)
    print(table(data))


def cmd_find(a):
    root = videos_root(a.root)
    if not root.is_dir():
        print(f"No videos folder yet: {root}")
        return
    rows = []
    for d in sorted(root.iterdir()):
        p = d / STATUS_NAME
        if not (d.is_dir() and p.is_file()):
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if a.query and a.query.lower() not in (d.name + " " + data.get("title", "")).lower():
            continue
        nxt = next_step(data)
        rows.append(f"{d.name:<40}  " + (f"next: {nxt['step']} {nxt['name']} ({nxt['state']})" if nxt else "finished"))
    print("\n".join(rows) if rows else f"No video with a status file under {root}" + (f" matching '{a.query}'" if a.query else ""))


def cmd_look(a):
    look = tv_config().get("look")
    if not look:
        print("none")
        return
    if look.get("layout") == "lower-thirds":
        where = "lower thirds along the bottom of the frame"
    else:
        fa = look.get("free_area") or {}
        x, w = fa.get("x"), fa.get("w")
        if x is not None and w is not None:
            side = "left" if x + w / 2 < 0.4 else "right" if x + w / 2 > 0.6 else "middle"
            where = f"text in the {side} {round(w * 100)}% of the frame"
        else:
            where = "text in the free area of the frame"
    plate = "on a dark grey plate" if look.get("plate") else "no plate"
    print(f"{where.capitalize()}, white, {plate}, {look.get('font') or 'Inter'}.")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("--title", required=True); s.add_argument("--slug"); s.add_argument("--root")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("init"); s.add_argument("video_dir"); s.add_argument("--title", required=True); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("show"); s.add_argument("video_dir"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("next"); s.add_argument("video_dir"); s.set_defaults(fn=cmd_next)
    s = sub.add_parser("set"); s.add_argument("video_dir"); s.add_argument("step"); s.add_argument("state")
    s.add_argument("--input", action="append"); s.add_argument("--output", action="append")
    s.add_argument("--note"); s.add_argument("--choice", action="append"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_set)
    s = sub.add_parser("reopen"); s.add_argument("video_dir"); s.add_argument("step"); s.set_defaults(fn=cmd_reopen)
    s = sub.add_parser("find"); s.add_argument("query", nargs="?"); s.add_argument("--root"); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("look"); s.set_defaults(fn=cmd_look)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
