#!/bin/sh
# Install the plugin's private Python environments, or check them.
#
#   TV_DATA="<plugin data folder>" sh install_env.sh [--check] [--with-opencv]
#
# Two environments, both made by uv with Python 3.11, both inside the plugin
# data folder. Nothing touches the user's own Python.
#
#   $TV_DATA/venv      parakeet-mlx (speech to text: Parakeet TDT 0.6b v3 on
#                      MLX), pypdfium2 (reads slide decks saved as PDF), and
#                      optionally opencv-python-headless (--with-opencv; only
#                      for short clips cut from slides with a camera inset)
#   $TV_DATA/denoise   deepfilternet, torch<2.9, torchaudio<2.9, soundfile
#                      (noise removal; all four are needed: without soundfile,
#                      deepFilter stops with a missing audio-backend error)
#
# Why two: parakeet-mlx needs numpy 2.2.5 or later, and every deepfilternet
# release needs numpy below 2.0, so one environment cannot hold both. The
# deepFilter command is linked into $TV_DATA/venv/bin, so every skill finds all
# tools in one place ($TV_DATA/venv/bin/<tool>).
#
# A second run checks first and skips whatever already works. The speech model
# (about 2.5 GB) and the noise model download on first use, into ~/.cache.
#
# Exit codes: 0 ready, 1 install or check failed, 2 TV_DATA or uv missing.

set -u
CHECK=0
OPENCV=0
for a in "$@"; do
  case "$a" in
    --check) CHECK=1 ;;
    --with-opencv) OPENCV=1 ;;
    *) echo "install_env: unknown option $a" >&2; exit 2 ;;
  esac
done

if [ -z "${TV_DATA:-}" ]; then
  echo "install_env: TV_DATA is not set (the plugin data folder)." >&2
  exit 2
fi
PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
export PATH
UV=$(command -v uv || true)
if [ -z "$UV" ]; then
  echo "install_env: uv is not installed. Run: brew install uv" >&2
  exit 2
fi

VENV="$TV_DATA/venv"
DENOISE="$TV_DATA/denoise"
# uv downloads its own Python into the plugin folder, so the tools never
# depend on a Homebrew Python that the user may remove.
UV_PYTHON_INSTALL_DIR="$TV_DATA/python"; export UV_PYTHON_INSTALL_DIR

speech_ok() {
  "$VENV/bin/parakeet-mlx" --help >/dev/null 2>&1 &&
  "$VENV/bin/python" -c "import pypdfium2" >/dev/null 2>&1 &&
  { [ $OPENCV = 0 ] || "$VENV/bin/python" -c "import cv2" >/dev/null 2>&1; }
}
denoise_ok() {
  "$DENOISE/bin/python" -c "import torch, torchaudio, soundfile, df" >/dev/null 2>&1 &&
  "$VENV/bin/deepFilter" --help >/dev/null 2>&1
}

report() {
  if speech_ok; then s="ok"; else s="MISSING"; fi
  if denoise_ok; then d="ok"; else d="MISSING"; fi
  echo "  speech to text, PDF reader:  $s"
  echo "  noise removal (deepFilter):  $d"
}

echo "Private tool environments in $TV_DATA"
if speech_ok && denoise_ok; then
  report
  echo "Already installed. Nothing to do."
  exit 0
fi
if [ $CHECK = 1 ]; then
  report
  echo "Not complete. Run setup to install."
  exit 1
fi
mkdir -p "$TV_DATA"

if speech_ok; then
  echo "Step 1 of 3: speech to text already installed."
else
  echo "Step 1 of 3: speech to text and PDF reader (uv downloads Python 3.11 if needed)..."
  [ -x "$VENV/bin/python" ] || "$UV" venv --python 3.11 --managed-python "$VENV" ||
    { echo "install_env: could not create $VENV" >&2; exit 1; }
  set -- parakeet-mlx pypdfium2
  [ $OPENCV = 1 ] && set -- "$@" opencv-python-headless
  "$UV" pip install --python "$VENV/bin/python" "$@" ||
    { echo "install_env: the speech-to-text install failed (see above)." >&2; exit 1; }
fi

if denoise_ok; then
  echo "Step 2 of 3: noise removal already installed."
else
  echo "Step 2 of 3: noise removal (about 500 MB; this takes a few minutes)..."
  [ -x "$DENOISE/bin/python" ] || "$UV" venv --python 3.11 --managed-python "$DENOISE" ||
    { echo "install_env: could not create $DENOISE" >&2; exit 1; }
  "$UV" pip install --python "$DENOISE/bin/python" \
      deepfilternet "torch<2.9" "torchaudio<2.9" soundfile ||
    { echo "install_env: the noise-removal install failed (see above)." >&2; exit 1; }
  ln -sf "$DENOISE/bin/deepFilter" "$VENV/bin/deepFilter"
fi

echo "Step 3 of 3: checking every tool..."
report
if speech_ok && denoise_ok; then
  echo "Done."
  exit 0
fi
echo "install_env: some tools still do not run (see MISSING above)." >&2
exit 1
