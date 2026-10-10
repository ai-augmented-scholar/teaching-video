#!/bin/sh
# Check that this Mac can run the video-teach-plugin, and which tools are
# still missing. POSIX sh on purpose: this runs before Homebrew, and on a fresh
# Mac /usr/bin/python3 is only a stub that asks to install developer tools.
#
#   sh check_machine.sh [--json]
#
# Exit codes:
#   0  the Mac is supported and every tool is present
#   1  the Mac is supported, but Homebrew, ffmpeg, node or uv is missing
#   2  the Mac cannot run the plugin (not Apple Silicon, macOS too old,
#      or not enough free disk space); stop here
#
# Needs: macOS 14 or later (the MLX speech model needs it), about 8 GB free in
# the home folder (the speech model ~2.5 GB, the noise-removal libraries
# ~2 GB, the text-card renderer ~0.5 GB plus its own browser).

JSON=0
[ "$1" = "--json" ] && JSON=1

MIN_MACOS_MAJOR=14
MIN_FREE_GB=8
PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
export PATH

stop=""
missing=""

arch=$(uname -m)
os=$(uname -s)
macos=$(sw_vers -productVersion 2>/dev/null || echo "0")
major=$(echo "$macos" | cut -d. -f1)
free_gb=$(df -g "$HOME" | awk 'NR==2 {print $4}')

[ "$os" = "Darwin" ] || stop="$stop not-a-mac"
[ "$arch" = "arm64" ] || stop="$stop not-apple-silicon"
[ "${major:-0}" -ge "$MIN_MACOS_MAJOR" ] 2>/dev/null || stop="$stop macos-too-old"
[ "${free_gb:-0}" -ge "$MIN_FREE_GB" ] 2>/dev/null || stop="$stop low-disk"

found() { command -v "$1" >/dev/null 2>&1; }

brew_ok=0; found brew && brew_ok=1
ffmpeg_ok=0; found ffmpeg && ffmpeg_ok=1
uv_ok=0; found uv && uv_ok=1
node_ok=0; node_ver=""
if found node; then
  node_ver=$(node --version 2>/dev/null | sed 's/^v//')
  [ "$(echo "$node_ver" | cut -d. -f1)" -ge 18 ] 2>/dev/null && node_ok=1
fi
claude_ok=0
if found claude || [ -x "$HOME/.claude/local/claude" ]; then claude_ok=1; fi

[ $brew_ok = 1 ] || missing="$missing homebrew"
[ $ffmpeg_ok = 1 ] || missing="$missing ffmpeg"
[ $node_ok = 1 ] || missing="$missing node"
[ $uv_ok = 1 ] || missing="$missing uv"

if [ -n "$stop" ]; then code=2; elif [ -n "$missing" ]; then code=1; else code=0; fi

if [ $JSON = 1 ]; then
  printf '{"arch":"%s","macos":"%s","free_gb":%s,"homebrew":%s,"ffmpeg":%s,"node":%s,"node_version":"%s","uv":%s,"claude_code":%s,"stop":"%s","missing":"%s","exit":%s}\n' \
    "$arch" "$macos" "${free_gb:-0}" $brew_ok $ffmpeg_ok $node_ok "$node_ver" $uv_ok $claude_ok \
    "$(echo $stop)" "$(echo $missing)" $code
  exit $code
fi

mark() { [ "$1" = 1 ] && echo "ok" || echo "MISSING"; }
echo "Mac check"
echo "  Chip:           $arch $( [ "$arch" = arm64 ] && echo '(Apple Silicon, ok)' || echo '(needs Apple Silicon)')"
echo "  macOS:          $macos $( [ "${major:-0}" -ge $MIN_MACOS_MAJOR ] 2>/dev/null && echo '(ok)' || echo "(needs $MIN_MACOS_MAJOR or later)")"
echo "  Free disk:      ${free_gb:-0} GB $( [ "${free_gb:-0}" -ge $MIN_FREE_GB ] 2>/dev/null && echo '(ok)' || echo "(needs about $MIN_FREE_GB GB)")"
echo "  Claude Code:    $(mark $claude_ok)"
echo "  Homebrew:       $(mark $brew_ok)"
echo "  ffmpeg:         $(mark $ffmpeg_ok)"
echo "  node 18+:       $(mark $node_ok)${node_ver:+ ($node_ver)}"
echo "  uv:             $(mark $uv_ok)"
case $code in
  0) echo "Result: ready." ;;
  1) echo "Result: supported Mac; still to install:$missing" ;;
  2) echo "Result: this Mac cannot run the plugin:$stop" ;;
esac
exit $code
