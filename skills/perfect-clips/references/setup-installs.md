# Setup installs — consent-gated recipes (read when the setup check finds something missing)

The plugin's `setup` skill installs the tools once per computer, into the
plugin's private environment (`${CLAUDE_PLUGIN_DATA}/venv`). When doctor.py
reports something MISSING, the first answer is always: run
`/video-teach-plugin:setup`. The recipes below are for the case where the user
wants only the one missing piece. Every install is offered, never forced:
name the size, get a yes, then install.

- **ffmpeg + ffprobe** missing → `brew install ffmpeg` (Homebrew first if it
  is absent). Verify both binaries answer afterwards.
- **Transcription** missing → `PARAKEET=MISSING` means the private
  environment lacks parakeet-mlx: run `/video-teach-plugin:setup` (it installs
  it into `${CLAUDE_PLUGIN_DATA}/venv`; the weights, about 2.5GB, download
  on first use, not at install). `TRANSCRIBE=MISSING` means the plugin
  folder is damaged: reinstall the plugin. Apple Silicon only — MLX runs on
  Metal. On any other machine, say the skill cannot transcribe here and
  stop; never substitute Whisper or WhisperX. Every pipeline script is
  stdlib-only and runs on any modern Python.
- **Node** present but first caption render ever: `TV_DATA="<data>" node
  "<skill dir>/scripts/render_captions.mjs" --setup` installs Remotion
  (~250MB) and Chrome Headless Shell (~150MB) into
  `${CLAUDE_PLUGIN_DATA}/perfect-clips/renderer` — one-time, mention it
  before it happens. Node missing → the captionless route (MP4s + SRT);
  Node 18+ comes from nodejs.org (the LTS button) or `brew install node`.
- **OpenCV** (layout probe layer) missing → only matters for a recording
  with more than one layout (slides with a camera inset, a screen share).
  Offer to add it to the private environment:
  `"${CLAUDE_PLUGIN_DATA}/venv/bin/pip" install opencv-python-headless`,
  consent first, ~60MB. It belongs in that venv and not in the system
  python: system pythons are often 3.13/3.14 with no cv2 wheels. doctor.py
  looks there first. Declined → legacy eyeball layout flow, said in the
  report.
