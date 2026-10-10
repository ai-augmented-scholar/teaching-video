---
name: setup
description: "Set up the Video Teach Plugin on this Mac, once per computer: check the Mac (Apple Silicon, macOS 14+, disk space), install the tools into a private folder (Parakeet speech-to-text, DeepFilterNet noise removal, the text-card renderer), ask where videos live and which editor the user has, ask the three first-run questions about the look of the text cards (free area of the frame, contrast, font), and finish with a 10-second test clip that reports pass or fail per step. For educational videos with talking-head footage, on a Mac with Apple Silicon, in Claude Code only. Use when the user runs /video-teach-plugin:setup, says 'set up the teaching video plugin', 'install the video tools', or when a session-start message says tools are missing. Safe to run again: it checks and skips what is already done."
---

# Setup

This plugin is for educational videos with talking-head footage: one person on
camera, explaining. Setup runs once per computer. Work through the steps in
order. Tell the user in one short line what each step is doing, and ask before
every large download. A second run is safe: every script checks first and skips
what is already in place.

Every script lives in `${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/`. The plugin
data folder is `${CLAUDE_PLUGIN_DATA}`; it is not in the Bash environment, so
pass it on every call as `TV_DATA="${CLAUDE_PLUGIN_DATA}"`.

## 1. Check the Mac

```bash
sh "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/check_machine.sh"
```

Show the user its table. Act on the exit code:

- **2 — this Mac cannot run the plugin.** Say why in one plain sentence (it
  needs a Mac with Apple Silicon, macOS 14 or later, and about 8 GB of free
  disk space) and stop. Do not try workarounds.
- **1 — tools missing.** Go on to step 2.
- **0 — ready.** Skip step 2.

Then say this about the Claude plan, in plain words: the step that cuts the
retakes (`perfect-cuts`) needs a strong model, Sonnet at high effort or Opus at
medium effort, and a cheaper model gives poor cuts. Claude Code needs a paid
Claude plan (Pro or Max); the free plan does not include it. Both paid plans
include Sonnet and Opus. The user can check the current model with `/model`.

## 2. Homebrew and the command-line tools

- **Homebrew missing:** never install it yourself. It asks for the user's Mac
  password, which only the user can type. Give them the official one-line
  installer from https://brew.sh to run in this session with a `!` in front:

  ```
  ! /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

  Tell them it also installs Apple's command-line developer tools and can take
  10 minutes. When it finishes, it prints two "Next steps" lines that add
  Homebrew to the shell; ask them to run those too (again with `!`). Then run
  the check from step 1 again.
- **ffmpeg, node or uv missing:** ask once, then install only what is missing:

  ```bash
  /opt/homebrew/bin/brew install ffmpeg node uv
  ```

  (Name only the missing ones.) Run the step-1 check again; it must now exit 0.

## 3. The private tool environments

Ask first: "Next I install the speech-to-text and noise-removal tools into the
plugin's own folder. That is about 300 MB of downloads, 1 GB on disk, and a few minutes. Your
own Python stays as it is. Go ahead?"

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" sh "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/install_env.sh"
```

It makes two environments, because the two tools need incompatible versions
of a shared library (NumPy): `venv/` holds Parakeet and the PDF reader for
slide decks, and `denoise/` holds DeepFilterNet. It links `deepFilter` into
`venv/bin`, so every skill finds every tool in one place. It ends with a check
of each tool. Relay any MISSING line and the error above it.

Only if the user plans to cut short clips from lectures where the slides carry
a small camera inset, add `--with-opencv` (a further ~100 MB). Do not ask about
this unless slides come up.

## 4. The text-card renderer

Ask first: "The text cards are drawn by a renderer that needs about 500 MB,
including its own browser. Install it now? (If you say later, the first text
cards will install it then.)"

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" sh "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/warm_renderer.sh"
```

It draws one sample card. On success it prints the path of a short preview.

## 5. Videos folder and editor

Ask two questions, one at a time:

1. "Where should your videos live? Each new video gets its own numbered
   folder there." Default: `~/Movies/teaching-videos`. Create the folder.
2. "Which video editor do you use?" Default: iMovie. Any editor works; every
   hand-off from this plugin is a plain video or image file.

## 6. The look of the text cards: three questions

If the user has a recording of themselves in their usual filming setup, ask
these now. If not, say: "I can ask three short questions about the look of
your text cards once you have a first recording. `make-video` will ask them
then." and skip to step 7.

The look scripts are in `${CLAUDE_PLUGIN_ROOT}/scripts/look/`; call each one
as `TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/look/<script>"`.
Ask the questions one at a time.

1. **Free area.** "Is there an area of the frame that is free most of the
   time, where text could sit, for example an empty wall beside you?"
   - If yes, the user can describe it ("the left third", "above my head"),
     give a screenshot that is typical of their footage, or let you take frames
     from a recording: `grab_frames.py VIDEO OUTDIR` takes three, at 25%, 50%
     and 75%. Look at the frames yourself.
   - Propose the area as fractions of the frame (x, y, w, h from the top-left),
     draw it with `mark_area.py FRAME x y w h OUT.png`, show the user the marked
     frame, and adjust until they approve it. Check all three frames: the
     speaker must not move into the area.
   - If no area is free: the cards become lower thirds, in a band along the
     bottom of the frame (`layout: "lower-thirds"`).
2. **Contrast.** "Is the background in that area dark enough for white text?"
   Measure it rather than guess: `measure_luminance.py FRAME x y w h` (for lower
   thirds, measure the bottom band: x 0.05, y 0.72, w 0.5, h 0.22). Tell the user
   what it found in one sentence and let them confirm or override. If the
   answer is no, the text stays white and gets a dark grey plate behind it,
   `#202020` at 70% opacity.
3. **Font.** Say: "I will be producing some animated text treatments to go
   with your video, based on your words in the footage. The default font face
   for those is Inter, but if you want, you can specify a different font face.
   Do you want to choose a different one? Let me know and I will double-check
   to make sure it is available on this machine."
   - Check any font other than Inter with `check_font.py "Font Name"`. It asks
     the same headless browser that draws the cards, so run it after step 4.
   - If the font is missing, say so. Offer Inter, or a font file the user
     already has: check it with `check_font.py "Font Name" --file PATH` and
     save the path as `look.font_file`.

## 7. Notion (optional)

Ask once: "Do you want your beat sheets copied into Notion as well? They are
always saved as a page in the video's folder." If no, skip.

If yes: the beat sheet skill writes to Notion through the official Notion
connector for Claude Code. Explain how to connect it (in Claude Code, `/mcp`,
then add and authenticate the Notion connector; check Notion's own help page
for the current steps), and ask for the Notion page that beat sheets should go
under. Save `notion.enabled` = true and its page id. One line of advice: Notion
has a free education plan for anyone with a school or university email address.

## 8. Save the answers

Write everything into `${CLAUDE_PLUGIN_DATA}/config.json` with the config
script. It keeps every key that is already there, fills in missing defaults
from `${CLAUDE_PLUGIN_ROOT}/scripts/config.example.json`, and applies only the
answers you pass:

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/write_config.py" \
  --set videos_root="~/Movies/teaching-videos" --set editor="iMovie" \
  --set-json look='{"layout": "column", "free_area": {"x": 0.05, "y": 0.15, "w": 0.4, "h": 0.7}, "background_luminance": 0.13, "plate": true, "plate_color": "#202020", "plate_opacity": 0.7, "text_color": "#FFFFFF", "font": "Inter", "font_file": ""}' \
  --show
```

Pass `--set-json look=…` only when step 6 ran, and `--set-json notion=…` only
when step 7 did. Never write a default look on the user's behalf: if step 6
was skipped, leave `look` out so `make-video` knows to ask.

## 9. The test

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/run_test.py"
```

A bundled 10-second clip (a synthetic voice, with one false start and some
background noise) runs through sound cleanup, transcription, finding the false
start, cutting it, and a sound check on the cut. The first run downloads the
speech model (about 2.5 GB), so say it will take a few minutes. Show the
pass/fail table.

- **All passed:** say setup is complete, and name the one prompt to remember:
  `/video-teach-plugin:make-video` runs the whole workflow, from beat sheet to
  finished video, and stops whenever a step is the user's.
- **A step failed:** show its line, read the error, and fix the cause (most
  often a missing tool from step 3; run `install_env.sh --check`). Then run the
  test again. If it still fails, tell the user plainly and point them to the
  feedback address in the plugin's README.

## Notes

- A session-start check (`hooks/check-tools.sh`) is silent when the tools are
  in place and otherwise tells the user to run this skill.
- Everything installed here lives in `${CLAUDE_PLUGIN_DATA}`, which survives
  plugin updates. Uninstalling the plugin deletes it. Three things stay after
  an uninstall, and the user can delete them by hand: the speech and noise
  models (about 2.3 GB, `~/.cache/huggingface`), uv's download cache (about
  1 GB, `~/.cache/uv`), and the Remotion project that a cut's "open in
  Remotion" launcher writes to `~/.perfect-cuts` when the user runs it.
- `perfect-clips` installs its own renderer (about 250 MB) the first time it
  runs.
- Do not install anything outside these steps, and never with `sudo`.
