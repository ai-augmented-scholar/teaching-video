#!/bin/sh
# Install the text-card renderer and prove it works, by drawing one sample
# card as a short preview video.
#
#   TV_DATA="<plugin data folder>" sh warm_renderer.sh
#
# The first run copies the renderer into $TV_DATA/renderer and installs its
# packages and its own headless browser: about 500 MB, a few minutes. Later
# runs find everything in place and take well under a minute.
#
# Exit codes: 0 the sample card rendered, 1 it did not, 2 TV_DATA or node missing.

set -u
if [ -z "${TV_DATA:-}" ]; then
  echo "warm_renderer: TV_DATA is not set (the plugin data folder)." >&2
  exit 2
fi
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
command -v node >/dev/null 2>&1 || { echo "warm_renderer: node is not installed. Run: brew install node" >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
PLUGIN=$(cd "$HERE/../../.." && pwd)
# One fixed folder in the plugin's data folder, replaced on every run, so
# repeated setups leave nothing behind in the system temp folder.
OUT="$TV_DATA/work/renderer-sample"
rm -rf "$OUT" && mkdir -p "$OUT"

echo "Text-card renderer: installing if needed, then drawing one sample card..."
TV_DATA="$TV_DATA" node "$PLUGIN/skills/text-treatments/scripts/render.mjs" \
  --cards "$HERE/../assets/sample-card.json" --out "$OUT" --modes ground --name sample
code=$?
preview=$(ls "$OUT"/*preview*.mp4 2>/dev/null | head -1)
if [ $code -eq 0 ] && [ -n "$preview" ] && [ -s "$preview" ]; then
  echo "Renderer ready. Sample: $preview"
  exit 0
fi
echo "warm_renderer: the sample card did not render (exit $code)." >&2
exit 1
