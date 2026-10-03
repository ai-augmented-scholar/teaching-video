#!/usr/bin/env python3
"""Create or update the plugin's config.json without losing anything in it.

    TV_DATA="<plugin data folder>" python3 write_config.py [--example PATH] \
        [--set KEY=VALUE ...] [--set-json KEY=JSON ...] [--show]

What it does, in order:
  1. Reads $TV_DATA/config.json if it exists.
  2. Fills in every key that is MISSING, from the example config shipped with
     the plugin (scripts/config.example.json). An existing value is never
     replaced by a default. "look" and "slides" are never filled in: they
     hold the user's own answers, and a missing section tells other skills
     to ask for them. (Missing sub-keys of an existing "look" or "slides",
     such as look.font_file, are filled.)
  3. Applies each --set / --set-json the user answered for. These DO replace
     the current value: they are the user's own answers. KEY may be dotted
     (look.font, notion.enabled).
  4. Writes the file back atomically and prints the result with --show.

--set takes a plain string; --set-json takes JSON (true, 0.18, {"x": 0.1}).
Keys starting with "_" in the example (comments) are not copied.

Stdlib only, so the macOS system python3 can run it.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_EXAMPLE = HERE.parents[2] / "scripts" / "config.example.json"


# Never filled in from the example: these hold the user's own answers, and
# their absence is how other skills know to ask. A missing "look" makes
# make-video and text-treatments run the three first-run questions; a missing
# "slides" makes video-with-slides ask where the speaker sits in the frame
# (a default speaker_x of 0.5 crops anyone who does not sit dead centre).
NO_DEFAULT = {"look", "slides"}


def fill_missing(target, defaults, top=True):
    """Copy keys from defaults that target lacks; recurse into dicts."""
    for key, value in defaults.items():
        if key.startswith("_") or (top and key in NO_DEFAULT and key not in target):
            continue
        if key not in target:
            target[key] = json.loads(json.dumps(value))
        elif isinstance(target[key], dict) and isinstance(value, dict):
            fill_missing(target[key], value, top=False)
    return target


def set_dotted(target, dotted, value):
    parts = dotted.split(".")
    node = target
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--example", default=str(DEFAULT_EXAMPLE))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--set-json", action="append", default=[], metavar="KEY=JSON")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    data_dir = os.environ.get("TV_DATA")
    if not data_dir:
        sys.exit("write_config: TV_DATA is not set (the plugin data folder).")
    path = Path(data_dir) / "config.json"

    config = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            sys.exit("write_config: %s is not valid JSON (%s). Fix or move it "
                     "first; nothing was changed." % (path, exc))

    example = json.loads(Path(args.example).read_text(encoding="utf-8"))
    fill_missing(config, example)

    for item in args.set:
        key, sep, value = item.partition("=")
        if not sep:
            sys.exit("write_config: --set needs KEY=VALUE, got %r" % item)
        set_dotted(config, key, value)
    for item in args.set_json:
        key, sep, value = item.partition("=")
        if not sep:
            sys.exit("write_config: --set-json needs KEY=JSON, got %r" % item)
        try:
            set_dotted(config, key, json.loads(value))
        except ValueError as exc:
            sys.exit("write_config: %s is not JSON (%s)" % (value, exc))

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, str(path))

    if args.show:
        print(json.dumps(config, indent=2, ensure_ascii=False))
    else:
        print("Saved %s" % path)


if __name__ == "__main__":
    main()
