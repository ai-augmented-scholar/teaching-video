#!/bin/sh
# SessionStart check for the teaching-video plugin. Silent when every tool is
# in place; otherwise one line telling the user to run setup. Never blocks.
#
# Claude Code exports CLAUDE_PLUGIN_DATA to hook processes. The hook's PATH
# can be bare, so Homebrew's folders are checked by full path as well.

DATA="${CLAUDE_PLUGIN_DATA:-}"
missing=""

has() {
  command -v "$1" >/dev/null 2>&1 || [ -x "/opt/homebrew/bin/$1" ] || [ -x "/usr/local/bin/$1" ]
}

[ -n "$DATA" ] && [ -x "$DATA/venv/bin/parakeet-mlx" ] || missing="$missing Parakeet,"
[ -n "$DATA" ] && [ -x "$DATA/venv/bin/deepFilter" ] || missing="$missing noise removal,"
has ffmpeg || missing="$missing ffmpeg,"
has node || missing="$missing Node,"

[ -z "$missing" ] && exit 0

list=$(echo "$missing" | sed 's/^ //; s/,$//')
msg="Teaching Video plugin: some tools are not installed yet ($list). Run /teaching-video:setup once on this Mac."
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$msg" "$msg"
exit 0
