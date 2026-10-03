#!/usr/bin/env python3
"""Perfect Clips setup check: prints what the pipeline can find on this machine.

Usage: TV_DATA="<plugin data folder>" python3 doctor.py [--help]

Stdlib only. Installs nothing, touches no network, always exits 0.
Tool lookup follows pc_env.py: $TV_DATA/venv/bin, ~/.local/bin, the
inherited PATH, then Homebrew. One line per item, in this order, then a
SUMMARY line:

  PYTHON:   the interpreter running this script
  FFMPEG:   ffmpeg + ffprobe
  TRANSCRIBE= the plugin's bundled `transcribe` (Parakeet TDT 0.6b v3),
            <plugin root>/scripts/transcribe; else MISSING
  PARAKEET= the parakeet-mlx engine behind it: $TV_DATA/venv/bin, then
            ~/.local/bin, the uv tool location, PATH; else MISSING
  WINDOWS=  the plugin's windowed re-transcription script (perfect-cuts'
            transcribe_windows.py), used when Parakeet drops speech
  NODE:     node version, or MISSING (captions need it)
  PYCV=     first python that can `import cv2`: $TV_DATA/venv/bin/python,
            then <PC_HOME>/venv, then this interpreter; else MISSING
            (only needed for multi-layout sources: slides plus a camera
            inset)
  PC_HOME=  where per-user state lives ($TV_DATA/perfect-clips)
  CONFIG=   $TV_DATA/config.json, or MISSING (setup has not run yet)
  FONT=     the caption font file: look.font_file when set; the plugin's
            bundled Inter (WOFF2) when look.font is Inter or unset; else a
            .ttf/.otf of look.font's name on disk; else the shipped Montserrat
  MUSIC=    the resolved music folder and its track count, EMPTY <path>,
            DISABLED, or OFF; MUSIC_SOURCE= names where it came from
            (config music_folder > <PC_HOME>/music-folder.txt >
            <PC_HOME>/music/ when it holds audio). OFF is the default.

Read TRANSCRIBE=, WINDOWS=, PYCV= and FONT= straight into the skill's
$TRANSCRIBE / $WINDOWS / $PYCV / $FONT.
"""
import pc_env  # noqa: F401  (tool PATH + PC_HOME; see pc_env.py)
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 20
HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent.parent.parent      # skills/perfect-clips/scripts -> root
TV_DATA = os.environ.get("TV_DATA", "").strip()
PC_HOME = Path(pc_env.PC_HOME)
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".aif", ".aiff"}
FONT_DIRS = [Path.home() / "Library/Fonts", Path("/Library/Fonts"),
             Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental")]
DEFAULT_FONT = HERE.parent / "assets" / "Montserrat-Variable.ttf"
BUNDLED_INTER = (HERE.parent.parent / "text-treatments" / "renderer" / "public"
                 / "fonts" / "InterVariable.woff2")


def run(cmd):
    """Run a command list; return (ok, stdout) where ok = exit 0 and non-empty stdout."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    out = (r.stdout or "").strip()
    return (r.returncode == 0 and bool(out)), out


def find_transcribe():
    cand = PLUGIN_ROOT / "scripts" / "transcribe"
    if cand.is_file() and os.access(str(cand), os.X_OK):
        return cand
    return None


def find_windows():
    cand = PLUGIN_ROOT / "skills" / "perfect-cuts" / "scripts" / "transcribe_windows.py"
    return cand if cand.is_file() else None


def find_parakeet():
    home = Path.home()
    cands = []
    if TV_DATA:
        cands.append(Path(TV_DATA) / "venv/bin/parakeet-mlx")
    cands += [home / ".local/bin/parakeet-mlx",
              home / ".local/share/uv/tools/parakeet-mlx/bin/parakeet-mlx"]
    for cand in cands:
        if cand.is_file():
            return cand
    on_path = shutil.which("parakeet-mlx")
    return Path(on_path) if on_path else None


def cv_candidates():
    out = []
    if TV_DATA:
        out.append(Path(TV_DATA) / "venv/bin/python")
    out.append(PC_HOME / "venv/bin/python")
    out.append(Path(sys.executable))
    return [c for c in out if c.is_file()]


def can_import_cv2(py):
    ok, _ = run([str(py), "-c", "import cv2; print(cv2.__version__)"])
    return ok


def load_config():
    if not TV_DATA:
        return None, {}
    p = Path(TV_DATA) / "config.json"
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (p if p.is_file() else None), {}


def find_font(name):
    """A .ttf/.otf whose file name starts with the font name (spaces ignored)."""
    if not name:
        return None
    key = name.replace(" ", "").lower()
    for d in FONT_DIRS:
        try:
            files = sorted(d.iterdir())
        except OSError:
            continue
        hits = [f for f in files if f.suffix.lower() in (".ttf", ".otf")
                and f.name.replace(" ", "").lower().startswith(key)]
        # Prefer a bold cut: captions are display type.
        for f in hits:
            if "bold" in f.name.lower():
                return f
        if hits:
            return hits[0]
    return None


def count_tracks(folder):
    try:
        return sum(1 for f in folder.iterdir()
                   if f.is_file() and f.suffix.lower() in AUDIO_EXT)
    except OSError:
        return 0


def resolve_music(cfg):
    """-> (state, path, source). Off unless the user set a folder."""
    cfg_val = str(cfg.get("music_folder") or "").strip()
    if cfg_val:
        if cfg_val.lower() == "disabled":
            return "DISABLED", None, "config"
        return "SET", Path(os.path.expanduser(cfg_val)), "config"
    txt = PC_HOME / "music-folder.txt"
    if txt.is_file():
        try:
            val = txt.read_text(encoding="utf-8").strip()
        except OSError:
            val = ""
        if val.lower() == "disabled":
            return "DISABLED", None, "music-folder.txt"
        if val:
            return "SET", Path(os.path.expanduser(val)), "music-folder.txt"
    default = PC_HOME / "music"
    if count_tracks(default):
        return "SET", default, "default folder"
    return "OFF", None, "none"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()

    ok_items, missing_items = [], []

    print(f"PYTHON: {' '.join(sys.version.split())} at {sys.executable}")
    ok_items.append("python")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    print(f"FFMPEG: {ffmpeg or 'MISSING'} | FFPROBE: {ffprobe or 'MISSING'}")
    (ok_items if ffmpeg else missing_items).append("ffmpeg")
    (ok_items if ffprobe else missing_items).append("ffprobe")

    tr = find_transcribe()
    print(f"TRANSCRIBE={tr if tr else 'MISSING'}")
    (ok_items if tr else missing_items).append("transcribe")
    pk = find_parakeet()
    print(f"PARAKEET={pk if pk else 'MISSING'}")
    (ok_items if pk else missing_items).append("parakeet-mlx")
    win = find_windows()
    print(f"WINDOWS={win if win else 'MISSING'}")
    (ok_items if win else missing_items).append("transcribe_windows")

    node = shutil.which("node")
    node_ver = ""
    if node:
        _, node_ver = run([node, "--version"])
    print(f"NODE: {node_ver + ' at ' + node if node else 'MISSING'}")
    (ok_items if node else missing_items).append("node")

    pycv = None
    for cand in cv_candidates():
        if can_import_cv2(cand):
            pycv = cand
            break
    print(f"PYCV={pycv if pycv else 'MISSING'} (only needed for multi-layout sources)")
    (ok_items if pycv else missing_items).append("pycv (multi-layout sources only)")

    print(f"PC_HOME={PC_HOME}")
    cfg_path, cfg = load_config()
    print(f"CONFIG={cfg_path if cfg_path else 'MISSING'}")

    look = cfg.get("look") or {}
    font_name = str(look.get("font") or "").strip()
    font_file = Path(os.path.expanduser(str(look.get("font_file") or "").strip()))
    # setup records the exact file it checked; a bare name is the fallback.
    font = font_file if str(font_file) not in ("", ".") and font_file.is_file() else None
    # Inter is setup's default and ships with the plugin (as WOFF2, inside
    # text-treatments), so the default needs no install. Prefer that copy to
    # any system Inter, so captions match the text cards exactly.
    if not font and font_name.lower() in ("", "inter") and BUNDLED_INTER.is_file():
        font = BUNDLED_INTER
        font_name = font_name or "Inter"
    if not font:
        font = find_font(font_name)
    if font:
        print(f"FONT={font} (config look.font: {font_name})")
    else:
        note = f" (config look.font '{font_name}' has no .ttf/.otf on disk)" if font_name else ""
        print(f"FONT={DEFAULT_FONT}{note}")

    state, path, source = resolve_music(cfg)
    if state == "SET":
        n = count_tracks(path)
        print(f"MUSIC={path} ({n} tracks)" if n else f"MUSIC=EMPTY {path}")
    else:
        print(f"MUSIC={state}")
    print(f"MUSIC_SOURCE={source}")

    print(f"SUMMARY: OK: {', '.join(ok_items)} | MISSING: {', '.join(missing_items) if missing_items else 'none'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never block a run on the doctor itself
        print(f"DOCTOR-ERROR: {exc}")
    sys.exit(0)
