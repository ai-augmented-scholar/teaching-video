"""Shared environment for the perfect-clips scripts. Import it first.

Two jobs, both done once at import:

1. PATH. The skill runs its commands with TV_DATA set to the plugin data
   folder, where setup installs the private tools. Tools resolve in this
   order: $TV_DATA/venv/bin, ~/.local/bin, the inherited PATH, then the
   Homebrew folders. A bare `ffmpeg` in a subprocess call then finds the
   same binary every time, even from a session with a thin PATH.
2. PC_HOME. Per-user state (settings, the dashboard, the package registry,
   the music-folder setting, the YuNet model, the caption renderer cache)
   lives in $TV_DATA/perfect-clips. Without TV_DATA (a script run by hand)
   it falls back to ~/.perfect-clips.
"""
import os

_TV_DATA = os.environ.get("TV_DATA", "").strip()

_front = []
if _TV_DATA:
    _front.append(os.path.join(_TV_DATA, "venv", "bin"))
_front.append(os.path.join(os.path.expanduser("~"), ".local", "bin"))
_back = ["/opt/homebrew/bin", "/usr/local/bin"]

_have = os.environ.get("PATH", "").split(os.pathsep)
_parts = [p for p in _front if p not in _have] + _have + [p for p in _back if p not in _have]
os.environ["PATH"] = os.pathsep.join(p for p in _parts if p)

if _TV_DATA:
    PC_HOME = os.path.join(_TV_DATA, "perfect-clips")
else:
    PC_HOME = os.path.join(os.path.expanduser("~"), ".perfect-clips")

# Children (node, a second python) inherit the same answer.
os.environ["PC_HOME"] = PC_HOME
