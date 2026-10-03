#!/usr/bin/env bash
# Show a Mac notification when a step of the workflow is the user's turn.
# Usage: notify.sh "Step 05: watch the cut" ["Open 1 WATCH - final video (C).mp4"]
# The message travels as arguments into AppleScript, never pasted into the
# script text, so quotes or apostrophes in a file name cannot break it.
set -u
msg="${1:-Your turn}"
sub="${2:-}"
/usr/bin/osascript - "$msg" "$sub" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
  set m to item 1 of argv
  set s to item 2 of argv
  if s is "" then
    display notification m with title "Teaching video" sound name "Glass"
  else
    display notification s with title "Teaching video" subtitle m sound name "Glass"
  end if
end run
APPLESCRIPT
# A notification is a courtesy, not a step: never fail the workflow over it.
exit 0
