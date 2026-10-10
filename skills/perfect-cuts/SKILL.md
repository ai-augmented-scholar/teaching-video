---
name: perfect-cuts
description: Turn a raw talking-head recording of an educational video (a lecture, an explainer) into a frame-perfect edit — retakes removed, false starts caught, ums and dead air gone. The main output is one finished MP4 that iMovie, or any editor, imports as a normal clip; the package also carries captions (SRT), a cut log, and timeline files for Final Cut, Premiere, Resolve and Avid. No script needed. Use when the user drops a raw clip and asks to "perfect cut this", "clean cut this", "cut the retakes out", "rough cut this footage", "tighten up this recording", or invokes /perfect-cuts.
---

# Perfect Cuts

The transcript decides **which take wins**, the waveform decides **the exact frame to cut**. One run drops a package with every useful format, and the user makes as few decisions as possible.

Made for educational videos with talking-head footage: one person on camera, explaining. Proven on real footage over five iterations. The locked rules were learned from frames the user flagged — don't soften them.

## The three locked rules (the product — never soften these)

1. **Hard threshold in, soft threshold out.** Clip START = first frame voice crosses **-30dB** (breaths and mouth noise live below it — a -38dB start grabs the inhale and reads as 2-4 dead frames; the user flagged exactly this). Clip END = where speech drops below **-38dB** (word tails are quiet; -30dB clips them). These exact values are frame-verified on reference footage and are ALWAYS tried first; the script falls back to per-clip calibration only if they produce a degenerate map (it says so when it happens). The -30dB start applies to blocks a silence opens; a block split out of running speech (after a filler, or at a repeated take) has no rise to find, so its start is the split point (see Sharp edges).
2. **Zero pad in, one frame out.** in_frame = `floor(onset × fps)` — no safety pad; 0.12s of "safety" pad was flagged as "2-4 frames too long." out_frame = `ceil(end × fps) + 1`.
3. **Intra-sentence silence ≥ 0.25s = suspect false start.** The transcript alone hides restarts: Parakeet transcribes literally but gives no marker at the seam. The speech map splits blocks at ≥0.25s silences — when one "sentence" spans two blocks, assume the first block is an aborted attempt unless its text clearly continues into the next. Prefer the later attempt.

## Model and effort (check before you start)

**Run this skill on Sonnet 5 at high effort, or Opus 5 at medium effort.** Steps 0–3 and 5–7 are scripts; the model only runs commands. Step 4, the editorial pass, is the one step the model does itself, and it is the product. The pass rewards deliberation: reading every block to the end, judging whether an earlier take flows into the next line, measuring an empty block with ffmpeg before cutting it, and matching blocks against a script. Small models and low effort cut exactly those corners, and the damage is invisible until the user watches the MP4.

- **Sonnet 5 → high.** At medium, Sonnet skims long block lists.
- **Opus 5 → medium.** Go to high for a scripted shoot (coverage check) or a clip over 20 minutes (300+ blocks).
- **Never low**, on any model. Low effort skips the level check and defaults to "keep the last take" — the two failures the locked rules exist to prevent.
- The cost difference is small. The editorial pass is text only; transcription and rendering run locally, and the model tier does not change their cost.

**If you are a different model or tier — Haiku, a local model, or any Claude model at low effort — stop and alert the user before Step 1:**

> ⚠️ perfect-cuts is running on `<model>` at `<effort>`. The editorial pass (Step 4) is the product, and it is tuned for Sonnet 5 at high effort or Opus 5 at medium. On this model, expect skimmed block lists, empty blocks cut without measurement, and retakes chosen by position instead of flow. Continue anyway, or switch with `/model` and run it again?

Wait for the answer. If the user continues, say so in the Step 7 report, and point at the cut decisions CSV as the file to audit. Do not soften the alert into a footnote — it is the only moment the user can switch models cheaply.

**To check the tier after a run:** run the same clip on both models and compare `4 REVIVE - cut decisions (C).csv`. The reason column shows which run read the words and which one counted takes.

## Workflow

### 0. Setup check (run silently before anything)

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
which ffmpeg ffprobe || echo MISSING-FFMPEG
ls "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe" || echo MISSING-TRANSCRIBE
ls "${CLAUDE_PLUGIN_DATA}/venv/bin/parakeet-mlx" 2>/dev/null || ls ~/.local/bin/parakeet-mlx 2>/dev/null || echo MISSING-PARAKEET
```

**Transcription is Parakeet TDT 0.6b v3, run locally through the plugin's `transcribe` command.** Not Whisper, not WhisperX — see "Why Parakeet" below before you reach for either.

`transcribe` ships with this plugin at `${CLAUDE_PLUGIN_ROOT}/scripts/transcribe`. It is a small front end for `parakeet-mlx`; its `--words` flag writes exactly the `segments[].words[]` JSON that `speech_map.py` reads. Video in, blocks out, no intermediate audio extraction needed.

If something is missing, tell the user to run `/video-teach-plugin:setup`, which installs ffmpeg and Parakeet into the plugin's own environment. Parakeet runs on Apple Silicon only, through MLX on Metal. The first transcription downloads the model (about 2.3 GB) from Hugging Face.

On a machine that is not Apple Silicon, say so plainly and stop rather than falling back to Whisper. The cut quality depends on the transcript, and a silent engine swap is the kind of change that shows up three steps later in the editorial pass.

**Why Parakeet, not Whisper.** Whisper merges restarted sentences, which is exactly what rule 3 has to work around. It also needs a language flag, and a wrong one silently produces a garbage transcript — a real risk for anyone who records in more than one language. Parakeet auto-detects across 25 European languages with no flag and no 30-second window, transcribes more literally, and runs about 30x faster than real time on an M-series laptop (measured: 174 seconds of audio in 5.4 seconds). Don't reintroduce Whisper or WhisperX as a fallback.

### 1. Intake — ONE AskUserQuestion call, then no more questions

Required: **the clip path** (usually arrives with the request; include in the call only if missing). When `make-video` runs this skill, it passes the answers it already has; ask only what is still open.

**Cut the cleaned-audio file, not the raw recording.** If the folder holds the output of `audio-enhance` (step 03 of the workflow), use that file as the source. On raw audio, room-noise peaks cross the -38dB line inside short pauses, so the speech map cannot split there and a restart stays glued to the line before it ("…two flavors. One is" in one block). After noise removal the same pauses split cleanly. If only the raw recording exists, say once that running `audio-enhance` first gives a cleaner cut, then continue if the user wants to.

- **Q1 — Script:** "Did you film from a script?" → **Exact script** (paste it or give a path) / **Rough script** (wrote one, ad-libbed wording; a beat sheet counts as rough) / **Freestyled** (no script). No script is needed: freestyled footage cuts the same way, and a script only adds the coverage check.
- **Q2 — MP4:** "Include a rendered MP4 in the package?" → **Yes (default)** / **No, timeline files only**. The MP4 is the only large or slow file; everything else is KB-sized and always included. iMovie can only use the MP4, so if the user answers No, remind them once that iMovie then has nothing to import.
- **Q3 — Save location:** "Where should the package go?" → **Next to the source clip (default)** — that is the video's own folder when the clip came from `make-video` / **Downloads** / custom.

That's the whole interview. Language is auto-detected by Parakeet, with no flag to pass and nothing to ask about. Thresholds are auto-calibrated.

**Filler words (um, uh, ähm, äh, and the like) MUST be systematically removed.** The `speech_map.py` script automatically isolates filler words into their own blocks. When you see these blocks in the editorial pass, you MUST cut them.

### 2. Transcribe

```bash
WORK="<video folder>/.perfect-cuts-work/<stem>"   # or "${CLAUDE_PLUGIN_DATA}/work/<stem>" when no video folder is known
mkdir -p "$WORK"
TV_DATA="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe" "<video>" --words "$WORK/transcript.json" --quiet
```

- **Working files live in the video's own folder**, in the hidden `.perfect-cuts-work/<stem>/`; with no video folder (a clip handed over on its own), in `${CLAUDE_PLUGIN_DATA}/work/<stem>/`. Never in `/tmp`. `$WORK` in this file stands for that folder; a shell variable does not survive from one command to the next, so write the full path into every command. The transcript, the speech map and cuts.json are kept there so a revival never needs a new transcription. Tell the user once, in the report, that the folder can be deleted after the review.
- `--words` is REQUIRED — it is what emits the `segments[].words[]` array. Parakeet's own `--json` output has sentences and sub-word tokens instead, and `speech_map.py` reads nothing from it, so every block comes back with empty text and the editorial pass is silently gutted.
- **One input file per `--words` call.** It refuses more.
- `TV_DATA` tells the script where the plugin's own Parakeet lives. Keep it on every call.
- Always quote paths — recording filenames often contain spaces.
- Pass the video straight in. `parakeet-mlx` shells out to ffmpeg for anything that is not already a plain WAV, so there is no audio-extraction step to do yourself.
- **No language flag, and none to invent.** Parakeet auto-detects across 25 European languages.
- Fast: about 30x real time on an M-series laptop, so a 30-minute clip lands in roughly a minute. No background run needed at ordinary lengths.
- Read the first lines of the transcript before moving on. Parakeet reports no language and no confidence summary, so a look at the words is the only check that it heard the right thing.
- **Long or noisy takes drop speech.** One Parakeet pass over a whole file can silently lose whole sentences; chunks of 75–110 s recover only a little, windows of about 20 s cut at block gaps recover them. It happens on short clips too: a 3-minute test take lost about a third of its words. So after Step 3, measure every empty block with the script (never by hand):
  ```bash
  TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/measure_blocks.py" "$WORK/map.json" "<video>"
  ```
  It lists every block without words (and every long block at speech level with too few words) with its level against the speech median and a verdict: `dropped`, `quiet`, `noise` or `short`, plus `sparse`. Add `--json` for data. It exits 1 when any block is `dropped` or `sparse`. Then re-transcribe in windows, rebuild the map, and run it again:
  ```bash
  TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/transcribe_windows.py" "<video>" "$WORK/map.json" --out "$WORK/transcript-windows.json"
  TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/speech_map.py" "<video>" "$WORK/transcript-windows.json" --out "$WORK/map.json"
  ```
  The blocks stay the same (they come from the waveform); only their words fill in. For a take over about 20 minutes, go straight to the windowed pass after the first map. `--quiet` prints nothing, so never use it for a snippet test where you need to see the words.

### 3. Build the speech map

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/speech_map.py" "<video>" "$WORK/transcript.json" --out "$WORK/map.json"
```

All `scripts/` references in this file mean `${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/`.

The script ALWAYS tries the locked -30dB/-38dB first — the first printed line confirms which thresholds were used. Only if the locked values produce a degenerate map (one giant block, or speech shredded into confetti — bad mic, untreated room) does it fall back to measuring the speaker's level and deriving thresholds, and it announces that loudly. If you see the rescue-calibration line, tell the user their audio is unusual and the cut deserves extra scrutiny.

**Two takes with no pause between them.** A speaker can restart a line with no 0.25 s silence before the restart, so the waveform never splits the two takes and one block holds both ("So in this video, what goes in each color? So in this video, what goes in each color?"). The editorial pass could then not keep only one. The script finds a run of 4 or more words that occurs twice in one block and splits the block where the second copy starts, at the quietest 10 ms within ±0.15 s of that word boundary. It prints a `split: two takes in one block at …` line for each one. Treat the two halves like any other retake pair.

Sanity-check the printed blocks: they should read like sentences with believable boundaries. If they don't, investigate (music bed, two speakers, clipped audio) before cutting — never push a suspicious map through the editorial pass.

### 4. Editorial pass (the judgment step — this is yours)

**This step IS the product.** Everything before it is plumbing and everything after it is packaging — if time or attention is constrained, it comes out of the packaging, never out of this pass. Work the block list line by line; do not skim.

Read the block list and decide which blocks survive:

- **Retakes** (same/near-same line repeated): keep ONE. Default to the LAST take — but if an earlier take flows grammatically into the following content, that one wins. Read the words, don't count takes.
- **False starts**: drop the fragment, keep the complete delivery.
- **Mid-sentence restarts**: cut at the restart point — the block boundary is already there.
- **Filler words (um, uh, ähm, äh)**: these are automatically split into their own short blocks by the script. Drop them. This will create jump cuts, which is expected and requested.
- **Sound checks, throat clears, dead air, direction-to-camera ("okay let me redo that")**: drop.
- **Merging blocks:** consecutive blocks with `gap_after` < 0.6s forming one continuous thought may merge into a single clip (first block's onset → last block's end). When in doubt, keep separate clips.
- **Restart trap (rule 3):** transcript sentence spans two blocks → first block is probably an aborted attempt.
- **A block with EMPTY text is not automatically silence — measure before cutting it.** The transcript only labels words the model heard; a long drawn-out word can be split by the -38dB pass into a block that gets no text, and cutting it punches a hole through the middle of the word. Check two things: whether any transcribed word's `[start, end]` span covers the block (the neighbouring blocks' `words` show it), and the block's level, from the script's verdict:
  ```bash
  TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/measure_blocks.py" "$WORK/map.json" "<video>"
  ```
  `noise` and `short` are breaths, clicks and room tone. **Loud but untranscribed is usually an inhale — cut it. Covered by a word is speech — keep it.** Both mistakes were made on a reference clip before this rule existed. A `dropped` block (speech level, longer than a breath) still left after the windowed pass, and a `quiet` one you are unsure of, gets its own snippet transcription before you cut it: cut the snippet out with `ffmpeg -nostdin -ss <start> -to <end> -i "<video>" "$WORK/snip.wav"` and run `transcribe` on it.
- **Split blocks (`"split": "filler"` or `"repeat"` in the map) start in running speech.** Their onset is the split point itself, not a later -30 dB rise, because no rise opens them. Keep such a block whole; do not trim its start.

**With a script (exact or rough):**
- Match blocks to script lines — the script is the intent; takes are attempts at it. Keep the take closest to the script (exact mode) or the latest fluent take (rough mode).
- Fix transcription mishears in clip `text` using script wording (never edit the transcript JSON — it's the timing source of truth).
- **Coverage check:** any script line with NO matching block = never cleanly delivered. Flag prominently — that's a reshoot warning, most valuable BEFORE the set is torn down.
- Script order wins when takes were filmed out of order.

### 5. Write the decisions: cuts.json

Write the editorial pass to `$WORK/cuts.json`. It holds decisions by block number, never frames; the build script turns them into frames.

```json
{
  "map": "<full path to $WORK/map.json>",
  "script": "freestyled",
  "clips": [
    {"blocks": [6], "reason": "take 4 of 4, flows into the next line"},
    {"blocks": [8, 9], "reason": "one thought, gap 0.3 s", "text": "script-corrected words, if any"},
    {"blocks": [12], "start": 41.20, "end": 44.05, "reason": "trimmed tail"}
  ],
  "cut": {
    "2": "retake 1 of 4",
    "7": "filler: um",
    "26": "false start, restarted at block 27"
  }
}
```

- `clips` is the timeline, in playback order. One entry per clip; consecutive blocks merged into one clip go in one `blocks` list (merge rule in Step 4). `reason` is optional for a kept clip and goes into the cut log.
- `cut` gives **every block that is not in a clip** a one-line reason. The build refuses to run while any block has no decision, or has two.
- `text` is optional; leave it out and the block text from the map is used. Give it when a script fixes a mishearing (never edit the transcript JSON — it is the timing source of truth). SRT and the preview player read it.
- `start` / `end` are optional seconds that override the clip's in and out. Leave them out: in is the first block's `onset` (the -30 dB voice onset, never `start`), out is the last block's `end` plus one frame (rule 2). Use them only for a deliberate trim inside a block.
- Two cameras: add the `angles` map and a per-clip `"angle"` (see Two-camera interviews); the build passes both through.

### 6. Build the package: one command

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/build_package.py" \
  --source "<video>" --cuts "$WORK/cuts.json" --out "<save location>/<stem> perfect cut (C)"
```

`<video>` is the same file the speech map was built on (the cleaned-audio file when there is one); the script refuses a source whose length does not match the map. Add `--title "<text>"` to name the timeline in the editors, and `--no-mp4` only if the user said no at Q2. The script writes every file below, verifies the MP4 (audio and video streams, length equal to the sum of the clips within one frame), and prints a JSON summary: `ok`, `package`, `expected_duration`, `mp4_duration`, `clips`, `blocks_kept`, `blocks_cut`, `files`, `warnings`, `trimmed_words`, `loudness_lufs`, `true_peak_dbtp`, `audio_gain_db`. On any problem it prints `"ok": false` with the error and exits 1; fix cuts.json and run it again. Never assemble the package by hand.

**Read `warnings` before you report.** The build checks every kept clip against the word times in the map: a word inside a kept block that the in- or out-point would cut off is listed there as "these words will be MISSING from the cut". That is never fine. Fix the cause (a wrong `start`/`end` in cuts.json, or a block that should be merged) and build again. Words cut by a deliberate `start`/`end` trim are listed under `trimmed_words` instead; check that each one is the trim you meant. A map built before blocks carried word times needs `--transcript "$WORK/transcript-windows.json"` (or `transcript.json`) for this check.

**True peak.** The AAC encoder adds inter-sample peaks, so a source delivered at -1.5 dBTP comes back at about -1.4. When the encoded MP4 is over -1.5 dBTP, the build encodes the audio once more with a small gain cut (the overshoot plus 0.1 dB) and copies the video untouched; `audio_gain_db` shows the cut (0.0 when none was needed). Loudness moves by the same fraction of a dB.

**Trimmed clips get trimmed captions.** When a clip has `start` or `end` and no `text`, its caption is the words whose middle lies inside the kept range, not the whole block.

Filenames are purpose-first and numbered by importance, so a non-technical user knows what each file is for without opening it:

| File in package | What it is |
|---|---|
| `README (C).txt` | Explains every file in plain words. Generic. |
| `1 WATCH - final video (C).mp4` | **The main output.** Frame-accurate single-pass re-encode. This is what the user imports into iMovie or any editor. |
| `2 EDIT - Final Cut Pro (C).fcpxml` | Final Cut: **File > Import > XML…** (menu path verified against FCP 12.3). Lands as a project in an event named "Perfect Cuts". Import the XML ONLY — it carries the media reference, so importing the source clip first just makes a duplicate. |
| `3 EDIT - Premiere + Resolve (C).xml` | Premiere: File→Import. Resolve: File→Import Timeline. |
| `4 REVIVE - cut decisions (C).csv` | The revival sheet: every block, kept and cut, with its reason. |
| `5 OPEN IN REMOTION - Mac (C).command` | Double-click → Remotion Studio. |
| `6 CAPTIONS (C).srt` | Captions on the EDITED timeline. Pairs with the MP4. |
| `7 AVID + LEGACY (C).edl` | CMX3600. |
| `cut data (C).json` | The cut points in frames — powers the Remotion launcher + automation. |
| `_remotion-launcher (C).mjs` | Engine behind the launcher. Self-contained: embeds the whole Remotion project template, needs only Node on the target machine. Falls back to a video dropped into the package folder when the original source path is gone. |

Keep `cuts.json` itself in `$WORK`, not in the package: the launcher reads the first JSON file in the package whose name contains "cut", so a second one there confuses it.

**iMovie, and most simple editors, read no timeline file** — none of the XML files or the EDL. The hand-off for them is the MP4: in iMovie, import `1 WATCH - final video (C).mp4` as media and put it on the timeline. Captions go up next to the video on the course site as `6 CAPTIONS (C).srt`; they are timed to the edited video, so they line up from frame 0. The Final Cut, Premiere/Resolve and EDL files cost nothing to generate; keep them in the package for anyone who opens the edit in an editor that reads them.

No HTML preview — browser video seeking can't be gapless, and a preview with gaps undermines the product (it was tried and removed after it visibly stuttered; the MP4 is the preview).

When the package is complete, **open the folder for the user**: `open "<package dir>"`.

What the script does for you, so you never redo it by hand:

- **Frames.** In = `floor(onset × fps)` of the clip's first block; out = `ceil(end × fps) + 1` of its last block (rule 2). Source fps comes from the first video stream only: a `.mov` timecode track also reports itself as video, at 90000 fps.
- **The Premiere/Resolve exporter takes no output argument**; it reads the destination from the `output` field of the spec. The script sets it. Called with `output` empty, that exporter dies on `FileNotFoundError: [Errno 2] No such file or directory: ''`, which reads like a missing input file.
- **The cut log is UTF-8 WITH a BOM.** Excel on macOS assumes MacRoman for a BOM-less CSV, so every accented character turns to mojibake — `ü` renders as `√º`, an em dash as `‚Äî`. Em dashes and curly quotes in your own reason column break the same way.

**Cut log format** — every block, kept AND cut, with the reason:

```csv
block,status,source_in,source_out,timeline_position,text,reason
6,KEPT,00:00:16:11,00:00:19:14,1,"The Enlightenment starts with a question,",take 4 of 4 — flows into next line
2,CUT,00:00:05:04,00:00:07:18,,"The Enlightenment starts with a question.",retake 1 of 4
26,CUT,00:01:28:07,00:01:29:06,,"and that first",false start — restarted at block 27
```

Timecodes at source fps. Any cut line can be revived — "revive block 26": move block 26 from `cut` into `clips` at its natural position in cuts.json, then run the build command again into the same folder. Never redo transcription.

### 7. Report

- Package path (folder is already open on their screen), raw → edited duration.
- **Lead with the MP4:** "watch `1 WATCH - final video` first." Then the editor step in one line: import that MP4 into iMovie, or any editor, as a normal clip.
- What was cut, one tight list: retakes ×N, false starts ×N, dead air total.
- **Script coverage warnings first** if any line never got a clean take.
- Point at `4 REVIVE - cut decisions (C).csv` for revivals.
- If the user flags a wrong cut: fix that single block decision in cuts.json and run the build command again. Never redo the pipeline.
- The working folder `.perfect-cuts-work/` in the video folder can be deleted once the user is happy with the cut; a revival after that needs a new transcription.

## Two-camera interviews

The pipeline stays single-source: cut on a **master** (the camera whose audio
is the audio, muxed with the approved audio track), then hang the second
camera on top. `cuts.json` takes an optional `angles` map and a per-clip
`"angle": "<key>"`; `export_fcpxml.py` and `render_mp4.py` both honour it
(schema in the exporter's docstring). `render_mp4.py` fits the angle into
the master frame with padding, conforms fps, and always takes the audio from
the master — **so the rendered MP4 already carries the camera switches**, and
the SRT still lines up. The FCPXML keeps the master as the primary storyline
and adds the other camera as a connected clip on lane 1, video only, so the
audio never switches and one delete in Final Cut reverts a clip to the master
picture.

- Sync first, by audio cross-correlation of the two camera tracks. If the
  second camera has no usable sound (an envelope correlation peak near zero
  means it has none), ask the user to line the two clips up by a visible
  event (a clap, a door) in their editor and read the offset off the
  timeline. Store it once as `offset_frames` in the angle's own fps; nothing
  is re-encoded, so changing it later is free.
- Editorial rules shift for a guest: retakes are rare; the cuts are pre-roll,
  interruptions, the host's restarts, and dead air. Cut a guest's filler only
  when it sits at a natural pause (a gap of at least 0.3 s on one side);
  mid-flow fillers stay, because a jump cut on a guest reads as manipulation.
- Angle = who is speaking, from hand-read speaker ranges (ask the user, or
  read them off the transcript). A host clip under 2.5 s between two guest
  clips shows the guest (reaction).
- Parakeet can drop a whole exchange from a long file. An empty block that
  measures at speech level (within ~5 dB of neighbouring speech) gets its own
  snippet transcription before it is cut — one such block in a long interview
  held two sentences the full pass never emitted. Cut the snippet out with
  ffmpeg and run `transcribe` on it.

## Sharp edges (learned the hard way)

- `ffmpeg` inside a shell `while read` loop eats stdin — always `-nostdin`.
- Never stream-copy (`-c copy`) concat of separately encoded segments — timestamps glitch, frames freeze. `render_mp4.py` does it right (single filter_complex, one re-encode).
- Source fps comes from ffprobe — never assume 30. NTSC rates (23.976/29.97/59.94) are handled by the exporter; all frame math uses the real rate.
- Transcript word timestamps are fine for WHICH words exist, unreliable for WHERE to cut — Parakeet pads word ends (0.24s on a reference clip). Never cut on transcript times; the waveform decides, always.
- **Words are attached to blocks by maximum OVERLAP, never by a time window** (`assign_words` in `speech_map.py`). A transcribed word can start up to ~0.3s before the waveform onset it belongs to — wider than any window that doesn't also steal words from the neighbouring block. An old time-window version silently dropped sentence-opening words (80 of 83 words kept on a test clip). That damage is invisible in the cut points and lands squarely on the editorial pass — a block whose opening words vanished reads like a false start, and a good take gets cut. Overlap matching keeps 83/83. Don't revert it to a window.
- No transcript marks a restart — the waveform blocks are the truth about how speech actually flowed.
- **A block split out of running speech has no -30 dB rise at its start.** Filler splits ("um", "uh") and repeat splits cut a block where the voice is already above the threshold. Rule 1's "first -30 dB rise inside the block" then lands on the next rise mid-block, and every word before it is lost at the jump cut: a test cut lost "the yellow" after an "um" (onset 1.36 s into the block) and "AI use is strictly prohibited" after an "uh" (2.84 s in). The frame count stays correct, so nothing else catches it. `speech_map.py` marks such blocks `"split"` and gives them the first -30 dB rise between the split and their first word as onset (else the split point; never later than the first word — a fixed 0.15 s window put a filler's tail and the pause after it back into the cut); `build_package.py` lists any word the in- or out-point would still cut off. Ordinary blocks, opened by a silence, keep rule 1 unchanged.
- **Don't swap the transcription engine to Whisper or WhisperX.** Both are slower here (CTranslate2 has no Metal support), both need a language flag that can be wrong, and Whisper merges restarted sentences, which works directly against rule 3.
- **Final Cut Pro reads NEITHER the FCP7 XML nor the EDL.** FCPX dropped `xmeml` and never had EDL import — it takes `.fcpxml` only. That's what `export_fcpxml.py` is for; always ship it alongside the FCP7 XML rather than telling a Final Cut user to convert. **Confirmed by a real import into FCP 12.3**: a 9-clip test timeline landed gapless at the expected 34.00s, clip names intact, media linked without a relink prompt. Its output is validated against Apple's own `FCPXMLv1_9.dtd` (shipped inside Final Cut Pro at `Contents/Frameworks/Interchange.framework/Versions/A/Resources/`) — copy the DTD somewhere without spaces in the path first, or libxml2 fails to resolve it.
- **FCPXML time is rational, not decimal.** Frame N is `N*frameDuration`, e.g. `1337/60s` at 60p and `N*1001/30000s` at 29.97. Writing decimal seconds is what lands third-party FCPXML a frame off; `export_fcpxml.py` keeps integer fractions throughout.
- **Clamp the last clip to the source's final frame for FCPXML.** Rule 2's `+1 frame out` can push the final clip one frame past the end of the media, and Final Cut rejects a clip that runs past its asset (Premiere tolerates it). `export_fcpxml.py` clamps and says so.
- The XML files, EDL, and Remotion launcher all reference the ORIGINAL source clip — if the user moves or renames it, those break (the launcher's fallback: drop the raw clip into the package folder). The MP4 (and the SRT that pairs with it) is the only standalone-forever artifact; the README says all this.
- No browser-based preview, ever — HTML5 video seeking has per-seek latency, so segment-skip playback always stutters at cut points. It was tried and removed; don't re-add it.

## Credit

`perfect-cuts` is by Vic Laranja, Systems by Vic ([youtube.com/@systemsbyvic](https://www.youtube.com/@systemsbyvic), [systemsbyvic.com](https://systemsbyvic.com)), MIT License — see `LICENSE` in this folder. This copy uses Parakeet for transcription and adds the Final Cut exporter.
