---
name: perfect-clips
description: Turn a lecture video into short, ranked clips for course announcements, the course homepage, or a teaser for next week — upright 9:16 for phones, or wide clips of 2-6 minutes for a course page. For educational videos with talking-head footage. The transcript finds the moments that stand on their own, filler is cut from inside each clip, an on-screen headline and one-word captions are burned in, and an optional music bed sits underneath. Hands back plain MP4 files that work in iMovie, or any editor, and on any course site. Use when the user asks for clips, short clips, a teaser, highlights or excerpts from a lecture video, or runs /video-teach-plugin:perfect-clips.
license: MIT — see LICENSE
compatibility: Claude Code on a Mac with Apple Silicon. Needs ffmpeg, the plugin's bundled `transcribe` (Parakeet via parakeet-mlx), and Node for captions (~400MB one-time). Optional OpenCV for recordings with more than one layout. The plugin's setup skill installs all of it.
---

# Perfect Clips

The division of labor is the whole design: **the model decides WHAT
survives, the waveform decides THE FRAME.**

## Paths and tools (read first)

- `<skill dir>` = `${CLAUDE_PLUGIN_ROOT}/skills/perfect-clips`. Always quote
  paths.
- **Every script runs with the plugin data folder passed in:** prefix each
  command with `TV_DATA="${CLAUDE_PLUGIN_DATA}"`. The scripts (through
  `scripts/pc_env.py`) find their tools in this order: the plugin's private
  environment `${CLAUDE_PLUGIN_DATA}/venv/bin`, then `~/.local/bin`, the
  inherited PATH, then Homebrew. Per-user state (settings, the dashboard,
  the package list, the music-folder setting, the face model, the caption
  renderer) lives in `${CLAUDE_PLUGIN_DATA}/perfect-clips/` — called
  `<PC_HOME>` below.
- Plugin settings live in `${CLAUDE_PLUGIN_DATA}/config.json` (written by
  `/video-teach-plugin:setup`). This skill reads `look.font`, `music_folder`
  and `videos_root`, and works with defaults when the file is missing.
- This skill runs in Claude Code on a Mac with Apple Silicon only. Anywhere
  else (claude.ai, another OS), say so plainly and stop — the pipeline
  needs local ffmpeg, Parakeet on MLX and Node renders.

## The locked rules (the product — never soften)

1. **Hook law.** No clip ships unless its ACTUAL OPENING passes the 2-second
   test: would the first 2 seconds make a cold viewer (a student with zero
   context, scrolling past the course announcement) keep watching? Every
   clip gets a `hook_mode`:
   - `natural` — the first line is the hook. Run it straight.
   - `teaser` — the natural open fails, but a hook-adjacent line lives inside
     the clip → extract it as a cold open (1.5-3.5s, complete phrase), play it
     first, then run the full clip INCLUDING that line where it naturally
     lands. The repetition is intentional — loop-close retention.
   - Neither → **skip the clip. No hook, no clip.**
2. **Word-index contract.** Never emit seconds when selecting — return word
   INDICES into words.jsonl (models are bad at millisecond arithmetic; the
   measured timestamps are ground truth). Every candidate carries a verbatim
   `hook_quote` of its opening words; the compiler verifies it and rejects
   mismatches. Clips may not open on a continuation token (and/but/so/
   because/then/like/i mean/you know/uh/um/yeah/okay/well...). "If" and
   "When" may open a clip when they start a sentence ("If you're new
   here..."); mid-sentence they are refused like the rest.
3. **Filler removal is core, not optional.** A lecture carries dead weight
   between the points: asides, restarts, "where was I". Use multi-segment
   keep-ranges to cut it from INSIDE a clip: clear point (10s) + aside (8s)
   + example that lands it (12s) = 2 segments, 22s. Each segment starts and
   ends on a complete thought. A tight clip with zero dead weight beats a
   60s clip with fluff.
4. **Boundary law.** Segment edges on speech-block boundaries get waveform
   frames (block onset -30dB in, block end -38dB +1 frame out). Mid-block
   edges (internal filler cuts) get force-aligned word times — the ONE place
   word timestamps rule. compile_clips.py enforces this; never override it.
5. **One-word captions, SUBTLE.** Exactly one word on screen at a time,
   uppercase, on a colour chip at 73% height, sized 7.6% of the frame's
   SHORT edge (identical to width on 9:16 output; rule 11 relies on this
   on wide clips).
   **Placement is safe-zone law:** on a 1080×1920 upright clip, phone video
   apps and players cover the top ~250px, the bottom ~420px, ~70px each
   side, and a ~193px right rail over the lower half with their own
   buttons and text. Lower-third chips at 73% clear the bottom band; the
   split-region seam position (50%) is safe by construction; never park a
   chip below ~76% or above ~15% on upright output. Wide clips (rule 11)
   are measured against a web player's control bar instead and sit at
   86%; that is rule 11's number, not a violation of this one.
   Gentle ease-in (0.96→1.0 over 3 frames, NO overshoot); a word HOLDS on
   screen until the next word starts whenever the gap is under 1.0s — no
   dead air between words (inter-word fading reads as flashing — a
   production-run lesson); fade-out (~6 frames) only into a real pause;
   never shrink on exit.
6. **Count floor.** Production data from a large open-source clipping
   service (429 jobs): users who got 1-3 clips returned 0.4% of the time;
   4-9 clips → 16.1%. The skip rules above are not a licence to return two
   clips and stop. Work every shortlisted window; fall short of the target
   only when the material truly lacks it — and say so.
7. **Diversity.** Never two clips making the same point or landing the same
   example — keep the stronger, drop the other. Same broad topic is fine
   when each lands its own moment.
8. **Frame-exact layout law.** Layout may change ONLY on scene-scan
   boundaries; regions tile the keep-segments exactly, and the renderer
   hard-fails on any gap or overlap rather than render it. One frame of
   layout bleed across a cut is a defect, not a rounding error. Layout
   doctrine: `split` is 50/50 — content (slides, a shared screen) on TOP,
   the speaker on the BOTTOM; `zoom` only when the area of focus is
   unmistakable (any doubt → `full`); the blurred backdrop stays subtle
   (half luminance) — it is never the show. Captions follow the layout on
   the same exact frames: the pane seam over split regions, the lower third
   everywhere else — always pass the layout plan to the caption renderer.
   **Rects are measured and verified, never trusted from an eyeball.** The
   mode call stays categorical and stays the model's, but every rect
   behind it comes from the layout probe (faces, camera inset,
   active-content panel), and no split/zoom/crop region renders
   unverified: verify_plan.py expands every pane rect to EXACT pane aspect
   (expansion reveals more, never trims), rebuilds the speaker pane
   face-anchored, and asserts the face actually sits in the rendered pane
   and the content pane actually holds the content. A region that can't be
   made honest DEMOTES to `full` — the verifier never promotes, never
   guesses. Camera insets move and resize BETWEEN scenes — the probe
   measures per region, so never copy a rect across regions by hand. A
   screen where nothing but the camera inset moves is a VOID — a split
   content pane there renders near-black; the honest calls are
   zoom-on-cam (the speaker IS the show) or `full`. Geometry verification
   alone is not enough: every split/zoom pane also passes a FRESH-EYES
   gate — a second reviewer with zero context says what it sees, and an
   unclear pane ships as `full` (the editor never argues with the fresh
   eyes).
   A plain talking-head lecture (one camera, one framing) has one layout
   and skips all of this — see step 8. So does a slide-deck lecture made
   with `video-with-slides`: its approved slide timing IS the layout plan
   (slide on top, speaker below), built by `slides_plan.py` — see step 8.
9. **Headline law (upright clips).** Every upright clip opens with an
   on-screen HEADLINE that names the moment in THIRD PERSON, present tense —
   a scene caption, not a quote: subject + strong verb + object, 3-5 words,
   ALL-CAPS ("PROFESSOR TESTS A FAMOUS MYTH", "SHE COMPARES TWO
   REVOLUTIONS", "HE DRAWS THE DIVIDING LINE", "WHY THE DATES MISLEAD").
   The subject is who the cold viewer is watching (PROFESSOR / HE / SHE /
   the speaker's name if students know it); never first person — the
   headline is the narrator's voice, the captions are the speaker's.
   Writing rules: name the moment, sell the watch — the kind of moment may
   be named (a myth falls, two ideas meet), its conclusion and punchline
   may not; concrete verbs beat adjectives; wording a student gets
   instantly; no trailing punctuation. Render: same chip system as the
   captions (same font, same colour, auto text-contrast), 1.35× caption
   size, pinned top-center (18% height — the whole chip sits below the
   ~250px top band, safe-zone law), on screen for the hook window only
   (~3s) then a quiet fade — it never moves with the layout, and the
   subtle-motion law applies to it like any caption. The headline and the
   one-word captions share the screen during the hook — two different
   elements; never merge them.
   **Never cover the speaker's eyes.** The 9:16 crop of a talking head
   puts the eyes at about 20–28% of the frame height, so the default 18%
   can sit on the forehead or the eyes. Before the first render of a run,
   look at one framed frame; if the chip at 18% would touch the face, pass
   `--title-y` with a larger value (the chip's CENTRE; 0.43 puts it on the
   chest, below the chin and well above the caption chips at 73%). Never
   raise it above 18%.
10. **Music law (optional, off by default).** A music bed exists only when
    the user has set a music folder that holds tracks — see
    references/music-layer.md for the resolution order (config
    `music_folder` → `<PC_HOME>/music-folder.txt` → `<PC_HOME>/music/`)
    and how to turn it on. Never ask about music in the intake; no folder,
    a `disabled` setting, or an empty folder means skip silently. The
    filename's leading words name the mood family in plain language
    ("lofi-chill-wave-beat-2-late-night-cozy.mp3"); mood-match the whole
    filename against each clip's register, then pick at random among the
    fits — and never repeat a track within one package unless the shortlist
    makes it unavoidable. Music sits at -20dB under the speech and NEVER
    louder by default — the bed supports, it never competes. Tracks are
    pre-trimmed by the folder owner: t=0 of the file IS the entry point, so
    the engine lays them at clip start with zero offset logic. NO copyright
    scanning of any kind — every music right and clearance is the user's
    own responsibility (see Liability).
11. **Mode law.** Every run is `upright` (the default — everything above) or
    `wide`, decided at intake and stated in the report. Wide ships **the
    frame as shot**: source resolution, source aspect, no scene scan, no
    layout probe, no verify, no split/zoom/crop, no headline, no music bed.
    Only the CUTS change — that is the whole product: a full explanation
    with the dead weight removed, not a moment reframed for a phone.
    (Internally the scripts call this mode `--longform` / `--mode wide`.)
    - **Substance, not moments.** One complete explanation, argument or
      worked example per clip, 2-6 minutes, that a student could land on
      cold on the course page and watch to the end. An upright clip is a
      moment; a wide clip has a beginning, a middle and a payoff.
    - **Fewer clips.** Target one per 15 minutes of source, never under
      2, never over 6. The count floor (rule 6) is an upright-clip number
      and does not apply here — an hour of lecture holds three or four
      real explanations, not eight.
    - **Diversity is by STORY.** No two wide clips may draw on the same
      stretch of source; overlapping ranges are the same video twice. Same
      topic from a genuinely different segment is fine.
    - **No teaser.** `hook_mode` is `natural` or the clip is skipped. The
      cold-open repeat is a phone-feed device that closes its loop seconds
      later; at three minutes the repeat lands as a mistake, not a hook.
      The 2-second test still gates every opening — a weak open gets a
      better START, or it does not ship.
    - **Filler removal is the point.** Multi-segment keep-ranges (rule 3)
      matter MORE at this length, not less. Same boundary law (rule 4),
      same waveform frames.
    - **Captions stay, static.** One-word chips (rule 5), same font and
      colour, centred at 86% height and never moving — no layout to track,
      no seam to follow. 86% is measured: a web player's bottom control bar
      is a fixed ~59px, so at large and fullscreen sizes it starts at ~93%
      of the frame, and a chip centred at 86% puts its bottom edge at ~91%.
      The controls auto-hide during playback, so a small embedded player
      with controls up is a transient overlap, not the design constraint.
    - **Chip size follows the SHORT edge** of the frame (7.6% of
      min(width, height)), so a caption on a 1920x1080 clip reads at the
      same physical size as one on a 1080x1920 clip. render_captions.mjs
      does this itself.
12. **One file per clip.** Each clip is ONE finished MP4 with its captions
    (and, upright, its headline) burned in — plain H.264, so iMovie or any
    editor and any course site or learning management system takes it.
    Upright clips get no SRT: their words are already on screen. Wide clips
    also get a cleaned SRT beside the MP4, for a course site that takes a
    caption upload (step 9).

## Workflow

**Package folder + workdir.** The package folder is created at intake for
EVERY run: `<save location>/<stem> perfect clips/` — `<stem>` is the source
filename without its extension, and the suffix ` perfect clips` is fixed.
ALL intermediates live in `<package folder>/work/` — never a system temp
dir — and stay after the run: "revive clip N" days later reuses them
without re-transcribing.

**Before the first render step of any run, read references/sharp-edges.md
in full — do not proceed to step 8 without it.** It carries the failure
modes that cost real productions.

### 0. Setup check (silent)

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/doctor.py"
```

Read its output: set `$TRANSCRIBE`, `$WINDOWS`, `$PYCV` and `$FONT` from its
`TRANSCRIBE=` / `WINDOWS=` / `PYCV=` / `FONT=` lines, and note `MUSIC=` for
step 8.7. **Anything it reports MISSING → read references/setup-installs.md
and follow its consent-gated recipe — the first answer is always
`/video-teach-plugin:setup`; do not improvise an install.** Standing rules:

- Transcription is Parakeet TDT 0.6b v3 through the plugin's bundled
  `transcribe` — never Whisper or WhisperX. Apple Silicon only: on any other
  machine say so and stop rather than substituting another engine.
- Node missing → captions can't burn — offer the captionless route (MP4s
  + SRT) rather than blocking.
- `$PYCV` (layout probe layer) matters only for recordings with more than
  one layout: slides with a camera inset, a screen share, a recorded
  meeting. Missing and the install declined → legacy eyeball layout flow,
  said in the report. A plain talking-head lecture never needs it, and
  neither do wide runs (rule 11) — that mode has no layout to probe; never
  offer the install on one.

### 0.5 Dashboard (silent, never blocks)

Right after the setup check, refresh and open the local dashboard — any
failure here is ignorable (one line, move on):

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/dashboard.py"
```

Last stdout line is the page's absolute path — open it with `open "<path>"`.
It is ONE static file at `<PC_HOME>/dashboard.html`: settings pills plus a
browser of every registered package with copy-path buttons. No server, no
ports, nothing runs between sessions.

**Settings paste contract:** a message containing a line that starts with
`perfect-clips settings ` followed by JSON is the dashboard's [Copy for
Claude] button — write that JSON object to `<PC_HOME>/settings.json`
(keys: caption_color, caption_font, default_mode, clip_count; drop unknown
keys), rerun dashboard.py, and confirm in one line. That paste IS the
consent for the write.

**The dashboard changes DEFAULTS, never consent:** settings.json values
pre-fill the intake round below — they pick which option is recommended
and pre-filled, and the questions still run. Skipping intake because a
settings file exists is a violation of the one-round law, not a shortcut.

### 1. Intake — ONE question round, then no more

The source is a local video file — usually the finished lecture (the
`perfect-cuts` MP4) or the cleaned recording. A file path is the only
input; this skill does not download.

**Source check (silent, before the round).** Run
`TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/pick_source.py" "<video folder>" --source "<file the user named>"`.
It decides from the files which video each mode is cut from, and prints
`upright`, `wide`, `case` and a one-line `say`:
- **`slides`** — the folder holds `video-with-slides` output (the same check
  as `slides_plan.py detect`): upright clips come from the SPEAKER cut and
  step 8 takes the slide-deck path below; wide clips come from the
  slides MP4 as it is. The check reads `slides-video/source.json`, which
  video-with-slides writes on every render, so the slides MP4 may have been
  renamed or moved; older folders without it are found by the
  `-with-slides` name.
- **`cut+export`** — a perfect-cuts package is in the folder and the user's
  export has the same length: **upright clips come from the clean cut**,
  because the export carries burned-in text cards and a 9:16 crop would cut
  a card near the centre in half; wide clips come from the export, cards and
  all.
- **`cut`** / **`plain`** — one file for both.
- **Exit 2, `"ask": true`** — the files cannot settle it (an export edited to
  a different length than the cut; a slides video whose cut is missing). Ask
  the user the question in `note`; do not guess.
Say the `say` line in the round. No extra question. Use the chosen file as
`<video>` in every later step of that mode, and pass `--cut-source` to
speech_map.py (step 3) whenever that file is a cut or an export.

Run the intake as ONE multiple-choice round. With a
`<PC_HOME>/settings.json` present, its values move the recommended tag:
saved caption_color / caption_font / default_mode / clip_count become each
question's first, recommended option. The questions still fire — defaults,
not consent.

- **Q1 — Caption colour:** "What colour for the caption chip?" →
  **Electric purple #7C5CFF (recommended)** / **Classic yellow #FFD400** /
  **Clean white #FFFFFF** / any other hex.
- **Q2 — What am I making:** "Upright clips, or wide ones?" → **Upright —
  auto count (recommended)** (9:16 for phones, target 6, floor 4 — the
  count-floor rule) / **Upright — 3-5** / **Upright — 6-10** / **Wide — 2-6
  min, source shape** (mode law, rule 11: the frame as shot, no headline,
  no music, count comes from the material). Exactly these four options —
  the question tool adds its own free-text choice; never list a fifth. The
  request usually answers this before the round ever fires ("a few
  minute-long excerpts for the course page"): request says WIDE → drop Q2
  entirely, the count comes from the material (rule 11), never ask it;
  request says UPRIGHT or "for phones" → Q2 keeps only the three count
  options.
- **Q3 — Caption font:** "Font for captions?" → when doctor.py printed a
  `FONT=` from the config's `look.font` (setup's default, Inter, resolves to
  the plugin's bundled Inter, so it is always there): **The font from setup
  — <name> (recommended)** / **Montserrat ExtraBold (ships with the skill)**
  / a font file path (.ttf, .otf or .woff2). Otherwise: **Montserrat
  ExtraBold (recommended, ships with the skill)** / a font file path. Pass
  the chosen file as `--font`; the caption renderer takes all four formats.
- **Q4 — Save location:** → **This video's folder (recommended)** — the
  folder that holds the source video / **Downloads** / another folder.

### 2. Transcribe

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" "$TRANSCRIBE" "<video>" --words "<package folder>/work/<stem>.json"
```

`--words` is REQUIRED — it writes the `segments[].words[]` JSON that
speech_map.py and windows.py both read. Parakeet's own `--json` output has
sentences and sub-word tokens instead, and neither script can use it.
Don't pass `--quiet` on a first run: the printed words are the first check
that Parakeet heard the right thing.

No language flag, and none to invent: Parakeet auto-detects across 25
European languages.

Fast: about 30x real time on an M-series machine, so even a 2-hour lecture
lands in a few minutes. Still say so before a long one starts.

### 3. Speech map + analysis layer

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/speech_map.py" "<video>" "<package folder>/work/<stem>.json" --out "<package folder>/work/map.json" [--cut-source]
```

**Check for dropped speech before going on.** One Parakeet pass over a
whole file can silently lose whole sentences on a noisy or long recording —
it has happened on a 3-minute clip, not only on long ones. They show up as
blocks with no text, or as long blocks with far too few words. Measure them
with perfect-cuts' script (one call; never a hand-written ffmpeg loop):

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/measure_blocks.py" "<package folder>/work/map.json" "<video>"
```

It compares every empty block with the median level of the blocks that
carry words and prints a verdict per block: `dropped` (at least 0.4 s and
within 5 dB of speech: lost speech), `quiet` (5-15 dB under: a soft word, a
murmur or a laugh), `noise` (more than 15 dB under: a breath or room tone),
`short` (under 0.4 s), plus `sparse` (a block of 2 s or more at speech level
with under 40% of the median word rate). Add `--json` for data. It exits 1
when anything is `dropped` or `sparse`, 0 otherwise.

On exit 1, re-transcribe in ~20s windows and rebuild the map (the blocks
come from the waveform and stay the same; only their words fill in), then
run the measurement once more:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$WINDOWS" "<video>" "<package folder>/work/map.json" --out "<package folder>/work/<stem>-windows.json"
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/speech_map.py" "<video>" "<package folder>/work/<stem>-windows.json" --out "<package folder>/work/map.json" [--cut-source]
```

Use the windowed transcript as `<stem>.json` from here on. For a recording
over about 20 minutes, go straight to the windowed pass after the first map.
Whatever the second measurement still calls `dropped`, transcribe on its own
before treating it as content: it is usually one short word or a non-word
sound. On a source that is already cut, `quiet` and `short` blocks are
mostly the dips between words, not a problem.

Then build the analysis layer:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/windows.py" "<package folder>/work/<stem>.json" "<package folder>/work/map.json" --outdir "<package folder>/work"
```

Sanity-check the speech map (blocks should read like sentences; a
rescue-calibration line printed = warn the user and scrutinize every
boundary in that run). **Exception: a source that is already cut.** A
finished cut or export has its pauses removed, so the locked thresholds find
no gaps and the script calibrates — expected, not a sound problem. The script
recognises this when a perfect-cuts package sits beside the source or when
you pass `--cut-source` (pass it whenever the source is the user's cut or
export), and then prints "this source is already cut … not a sound problem".
Do not tell the user their audio is unusual in that case; still check the
boundaries. windows.py emits:
- `words.jsonl` — **line N is word index N** (1-based). To read words A..B,
  read that line range of the file (offset/limit).
- `windows.json` — segment-snapped ~90s windows (30s overlap) with text and a
  density score.

### 4. Score pass (you) — cheap triage

Read `windows.json` (in chunks on long lectures). Under ~20 minutes of
footage: read every window. Longer: read in density order, but state
coverage in the report — density orders reading, it never judges.

Score each window 0-100 with a short reason. **The 2-second test is the main
criterion.** Prefer a surprising claim, a myth corrected, a vivid example,
a question students actually ask, a clear distinction, a number that
sticks, a complete payoff. Ignore housekeeping (deadlines, "last time we"),
outros, rambling transitions. Shortlist ≈ 2× the clip target, minimum
score 55.

**Wide runs read for ARCS, not moments** (rule 11). A 2-6 minute
explanation spans two to four of these windows, so score NEIGHBOURHOODS:
where does a thing start, build and land? A window that scores 90 on its
own but has no before and no after is an upright clip, not a wide one —
note it in the REVIVE sheet and move on. Shortlist ≈ 2× the wide target
(source minutes / 15).

### 5. Detail pass (you) — the judgment step. This IS the product.

For each shortlisted window, read its words.jsonl slice and build
candidates. Work the words, not your memory of them.

**In wide mode, four things change here** (rule 11) — read the whole arc's
words, not one window's: the unit is a complete EXPLANATION of 2-6
minutes, not a moment; `hook_mode` is `natural` or the clip is skipped (no
teaser at this length); no `headline` field (nothing burns one in this
mode); and no two candidates may draw on the same stretch of source — the
compiler keeps the higher-scoring one. Filler removal carries more weight,
not less: an opening you would keep in a 40-second clip is often two
segments in a four-minute one. Everything else below applies unchanged.

Per clip decide, in order:
1. **The moment** — one focused idea, fully delivered. Standalone: no "as I
   mentioned", no "last week we", no answers to unheard questions. Fix
   context problems by moving the START earlier, never by cutting the
   payoff.
2. **Keep-ranges** — cut filler/tangents inside the clip (rule 3). Each
   segment opens and closes on a complete thought. Watch the merge trap: a
   transcript sentence spanning two speech blocks usually hides an aborted
   restart — keep the later attempt.
3. **Hook decision** — apply the hook law. For `teaser`: pick the single
   most attention-stopping phrase INSIDE one kept segment, 1.5-3.5s,
   complete phrase.
4. **Self-tests** before finalizing boundaries:
   - *Stop early:* cut 5s before your end — viewer already got the point?
     Your end is too late.
   - *Continue:* does the next sentence continue the thought? You ended
     mid-explanation.
   - *Title delivers:* the title's concrete noun/number/reveal must be SPOKEN
     inside the clip — else extend, retitle, or skip.
5. **Score** hook/engagement/value/shareability, 1-25 each. Be harsh and use
   the whole range — flat 80s are useless for ranking. Don't downgrade
   difficult or contested topics; downgrade weak transcripts. Selection is
   EDITORIAL, never a content-policy or legal review — this skill ships no
   topic gates. Users who have their own content rules carry them in their
   own instructions, and those apply at runtime like any other user
   instruction.
   Also tag each clip's **emotional register** — one word: energetic /
   reflective / tense / warm / comedic / other. The music bed (step 8.7)
   matches tracks against it.
6. **Copy** — **before writing ANY copy, read references/style-rules/core.md
   and apply it — do not draft titles, headlines, or descriptions without
   it.** `title` ≤38 chars, phrased as what a student would TYPE INTO a
   course-site search (concrete nouns and names beat emotion words);
   `headline` per rule 9 — third person, present tense, subject + verb +
   object, 3-5 words, ALL-CAPS, punchline unspoken (a "HOW HE..." clause is
   not a headline); `descriptions` — an `announcement` (1-2 sentences for a
   course announcement or message, teasing the payoff) and a `course_page`
   (one plain sentence saying what the clip explains). Every claim grounded
   in what the clip actually says.

Write `<package folder>/work/candidates.json` — word indices 1-BASED and
INCLUSIVE (= line numbers in words.jsonl); every field below is required,
extra fields pass through to the manifest untouched:

```json
{"clips": [{
  "title": "Why the Enlightenment looked forward",
  "headline": "SHE FLIPS THE GOLDEN AGE",
  "hook_mode": "teaser",
  "teaser": {"start_word": 1481, "end_word": 1490},
  "segments": [{"start_word": 1440, "end_word": 1497},
               {"start_word": 1512, "end_word": 1568}],
  "hook_quote": "the golden age was not",
  "register": "reflective",
  "scores": {"hook": 21, "engagement": 17, "value": 22, "shareability": 16},
  "why": "one clean contrast with a dated example, payoff at the end",
  "descriptions": {"announcement": "...", "course_page": "..."}
}]}
```

`hook_quote` = verbatim first words of the OUTPUT (the teaser text when
hook_mode=teaser, else the first segment's opening) — the compiler
matches the first ~3 words, mismatch = reject. `teaser` must sit INSIDE
one kept segment. `segments` ordered, no overlaps, each one opening AND
closing on a complete thought — in-points land on a phrase-initial word
after a real pause, never mid-sentence; cut filler from INSIDE with a
second segment rather than shrinking the range. `why` — one clause,
≤80 chars (editing notes belong in the report). `register` drives the
music bed.

### 6. Compile + fix rejects

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/compile_clips.py" "<package folder>/work/candidates.json" "<package folder>/work/words.jsonl" "<package folder>/work/map.json" --outdir "<package folder>/work" --min-dur 15 --max-dur 60
```

**Wide** (rule 11): add `--longform` — it enforces the law mechanically:
teaser candidates are refused, and of two candidates drawing on the same
stretch of source only the higher-scoring one survives (greedy by score,
after validation — the loser's cuts file is removed). `--longform` alone
already defaults the window to 120/360s; `--min-dur`/`--max-dur` still
override.

Rejects come back with reasons (hook_quote mismatch, banned opener, teaser
outside its segment, duration, wide overlap). Fix candidates.json and
re-run — never hand-edit the emitted cuts files. Output: per-clip
`clip NN cuts.json` + `manifest.json` (ranked).

### 7. No plan gate — render every compiled clip

Do not show the slate and wait. A written table of selections is an
abstraction most people have no use for; they judge clips by watching
them. So go straight from a clean compile to step 8 and render EVERY
compiled clip. The selection happens after the render, in the report (step
11): the user watches the package and says which clips to drop or change.
A dropped clip is deleted from the package and marked `dropped` in the
REVIVE sheet; a changed clip is a repair (sharp-edges §Repairs), never a
full re-run.

### 8. Per-clip render

**WIDE RUNS TAKE THE SHORT PATH** (rule 11). Steps 8.1-8.4 — scene scan,
layout probe, layout call, verify, fresh-eyes gate — do not run at all:
there is no reframing to measure, so there is nothing to verify. One
command replaces all four:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/render_clip.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN wide.mp4" --mode wide
```

Source resolution, source aspect, one filter_complex, one encode —
frame-exact trim and concat, never a stream-copy concat. It refuses
`--plan`: a layout plan in wide mode is a category error. Then go straight
to 8.5 (caption words) and 8.6 (burn), and skip 8.7 (music) entirely.

**PLAIN TALKING-HEAD LECTURES TAKE THE ONE-LAYOUT PATH** (upright). A
recording with one camera and one framing all the way through has nothing
to scan or probe. Skip 8.1-8.4 and frame with the legacy single mode:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/render_clip.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN framed.mp4" --mode crop --face-x <0..1>
```

`--face-x` is the speaker's horizontal centre as a fraction of the frame
width. Measure it from one extracted frame (`ffmpeg -ss <t> -frames:v 1`)
rather than assuming 0.5 — a speaker who stands off-centre to leave room
for text gets cut in half by a centred crop. `--mode canvas` (the whole
frame, scaled, over a blurred copy) is the honest fallback when the speaker
moves too much for one crop. Then continue with 8.5.

**SLIDE-DECK LECTURES TAKE THE SLIDE-SPLIT PATH** (upright, when the intake
check found `video-with-slides` output). The approved slide timing already
says what is on screen at every frame, so 8.1-8.4 (scan, probe, verify,
fresh eyes) do not run and OpenCV is not needed. Wherever the timing shows
a slide, the upright frame is split horizontally: the slide itself on the
TOP panel (sharp, fitted whole into the panel's safe box, never stretched,
on the slides video's background), the speaker's head and shoulders on the
BOTTOM panel. Where the timing shows the speaker alone, the clip is the
normal single-speaker crop. Measure the speaker's face centre (x and y,
fractions of the source frame) from one extracted frame, then:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/slides_plan.py" plan --clip "<package folder>/work/clip NN cuts.json" --slides-dir "<video folder>/slides-video" --out "<package folder>/work/clip NN layout plan.json" --face-x <0..1> --face-y <0..1>
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/render_clip.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN framed.mp4" --plan "<package folder>/work/clip NN layout plan.json"
```

The plan script turns each slide change into a frame exactly as
video-with-slides does (`round(start × fps)` on the cut's own rate), so the
upright clip changes slide on the same frame as the wide video; a change
inside a kept segment splits that segment there (rule 8), and a sliver
under 0.4 s at a segment edge joins its neighbour rather than flash. It
prints the region table and writes one 1080x960 panel image per slide used
to `work/panels/`. A slide with wide empty margins (a uniform background
around the text) is cropped to its content plus 4% padding before it is
fitted, so its text reads larger in the upright panel (a 3-bullet test slide
grew 37%); the script prints the gain per slide. It never cuts content, and
it leaves photo slides and slides with no margin as they are. `--head` (default 0.60 of the source height) sets how
much of the speaker the bottom panel shows. Then continue with 8.5 and
pass the same plan to the caption renderer: captions sit on the seam over
the split regions and on the lower third over the speaker-only ones.
Before the report, look at three frames: just before a slide change, just
after it, and in a speaker-only stretch. Check that the slide is sharp, the
head sits whole in the bottom panel, and the caption chip covers neither the
slide text nor the face.

For each compiled clip of a multi-layout recording (upright):

1. **Frame-exact scene scan** — find every hard cut inside the keep-segments:
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/scene_scan.py" "<package folder>/work/clip NN cuts.json" --outdir "<package folder>/work"
   ```
   The emitted regions are the ONLY places layout may change. Busy animated
   slides throwing false cuts: raise `--threshold` to 0.4.
2. **Layout probe (measure before judging):**
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" "$PYCV" "<skill dir>/scripts/layout_probe.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN cuts scenes.json" --outdir "<package folder>/work"
   ```
   Per region it measures faces, the camera-inset rect, the active-content
   rect, full-frame face-x (person-only scenes) and a VOID flag (nothing
   but the camera inset moves). Output: `clip NN probe.json` + one
   annotated still per region. No cv2 → legacy eyeball flow (estimate rects
   from each probe still; drawbox-verify when unsure, max 2 iterations) and
   say so in the report.
3. **Layout call PER REGION (categorical — the mode is yours, the rects
   are measured).** Read each region's ANNOTATED probe still plus the
   probe JSON and pick ONE mode:
   - `crop` — a full-frame person. Use the probe's `full_face_x`.
   - `split` — slides or a shared screen WITH a camera inset. Inset = the
     probe's cam rect; content = the probe's content rect — override it
     only when the still shows the measurement missed the content (dark
     modals defeat the panel detector; a static portrait on a slide can
     outrank the real camera — `cam_choice` in the probe JSON says which
     face it picked and why). Hand-drawn rects need
     `"rects_from": "still"` on the region — without it the verifier
     overrules them (sharp-edges has the rules).
   - `zoom` — ONE unmistakable area of focus. A VOID region with a live
     camera inset is the classic case: zone = the cam rect (zoom-on-cam —
     the speaker is the show). Prefer zones wider than tall. Doubt → `full`.
   - `full` — dynamic shots, mixed screens, low confidence. The honest
     fallback, and a good look on motion.
   Write `clip NN layout plan.json`: `{"regions": [...]}` carrying
   each region's `in_frame`/`out_frame` from the scan plus its mode
   fields.
4. **Verify (mandatory when the probe ran), fresh-eyes gate, then frame:**
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" "$PYCV" "<skill dir>/scripts/verify_plan.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN layout plan.json" --probe "<package folder>/work/clip NN probe.json" --fix --panes "<package folder>/work/panes"
   ```
   The verifier enforces rule 8 (aspect-expand, face-anchor — bottom-
   pinned for corner cams — snap zoom-on-cam zones, demote-never-promote).
   A DEMOTED region is the verifier doing its job, not an error. Plan
   backed up to `*.pre-verify`; frame boundaries never touched. Exit 2 =
   probe and plan disagree structurally — re-probe, re-decide.
   **Fresh-eyes gate (MANDATORY after verify, before framing): read
   references/sharp-edges.md §The fresh-eyes gate NOW and run it
   exactly.** Then frame:
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/render_clip.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/clip NN framed.mp4" --plan "<package folder>/work/clip NN layout plan.json"
   ```
5. **Caption words:**
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/clip_words.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/words.jsonl"
   ```
6. **Burn captions + headline (layout-aware). SERIAL — one clip at a time.**
   The renderer stages every job through one shared Remotion project, so two
   concurrent runs silently swap each other's video and headline while both
   report success. See references/sharp-edges.md §Never caption two clips at
   the same time.
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" node "<skill dir>/scripts/render_captions.mjs" "<package folder>/work/clip NN framed.mp4" "<package folder>/work/clip NN cuts words.json" "<final>.mp4" --color "<Q1 colour>" --font "<Q3 font file>" --plan "<package folder>/work/clip NN layout plan.json" --title "<headline from candidates.json>" --title-sec 3 [--title-y <value>]
   ```
   Pass the SAME layout plan used for framing: the chip follows the layout,
   switching position on the exact region frames — the pane seam over
   `split` regions, the lower third over `crop`/`full`/`zoom`. No plan
   (one-layout clips) → flat `--caption-y` (0.73 default, phone-safe).
   `--title` burns the headline chip (rule 9); omit it ONLY if the user
   explicitly asked for headline-free clips. `--title-y` per rule 9's
   eyes check. `--text-color HEX`, `--radius 0` and `--no-shadow` exist
   for a user who wants square, flat chips.
   **Wide** (rule 11) burns the same chips onto the wide render with no
   plan, no title and a static lower position:
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" node "<skill dir>/scripts/render_captions.mjs" "<package folder>/work/clip NN wide.mp4" "<package folder>/work/clip NN cuts words.json" "<final>.mp4" --color "<Q1 colour>" --font "<Q3 font file>" --caption-y 0.86
   ```
   0.86 clears a web player's control bar at large and fullscreen sizes and
   is not a preference — do not raise it toward the frame edge. The chip
   sizes itself off the frame's short edge, so nothing else changes.
7. **Music bed (upright only, and only when the music layer is live).**
   Wide runs skip this step entirely (rule 11) — a bed under a three-minute
   explanation fights the talking, and the mode ships the source audio.
   Otherwise resolve per rule 10; `MUSIC=` OFF, DISABLED or EMPTY → skip
   this step silently. Otherwise, FIRST run the source-music gate per clip:
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/music_gate.py" "<package folder>/work/clip NN cuts.json" "<package folder>/work/map.json"
   ```
   Last stdout line: `bed=skip` → the clip ships on its own audio (say
   so in the report, never argue with the number); `bed=ok` → proceed.
   Then list the tracks once per run. Per clip: match by filename mood
   family against its `register` (rule 10 — decide the register now from
   the clip's content if a candidate lacks one), ONE random pick from the
   fits, no repeats within the package unless the shortlist leaves no
   choice; no fit → no bed (a mismatched bed is worse than none).
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/add_music.py" "<final>.mp4" "<music folder>/<track>" "<package folder>/work/clip NN music tmp.mp4" --gain-db -20
   ```
   then replace `<final>.mp4` with the temp file only on success
   (behavior notes: references/music-layer.md §Runtime).
8. **Premiere/Resolve XML:** set the cuts JSON `output` field to the
   **.xml timeline path — NOT the clip MP4** (the exporter writes XML to
   exactly this path; non-.xml targets are refused), then export:
   ```
   TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/export_fcp7.py" "<package folder>/work/clip NN cuts.json"
   ```

### 9. Caption file — WIDE RUNS ONLY

Upright clips get no SRT: their words are burned in (rule 12). Wide clips
get one cleaned caption file each, saved beside the MP4 with the same name
and `.srt`, for a course site that takes a caption upload:

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/srt_clean.py" "<package folder>/work/clip NN cuts.srt" \
  --dur "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "<final>.mp4")" \
  --out "<package folder>/<same name as the MP4>.srt"
```

The cleaner drops the trailing word fragment the waveform padding catches
and clamps any cue that runs past the clip; it never moves a timing.

### 10. Package

Finalize into `<package folder>` (created at intake — never a second one):

| File | Source |
|---|---|
| `README.txt` | `scripts/readme_template.txt` verbatim — wide runs use `scripts/readme_template_longform.txt` instead (the upright one promises vertical reframing, headlines and music beds a wide package does not have) |
| `1 CLIP 87 - <kebab-title>.mp4` ... ranked, score in the name | captioned upright renders — ONE file per clip (rule 12) |
| `1 WIDE 80 - <kebab-title>.mp4` + `.srt` ... same, wide runs (rule 11) | captioned wide renders and their cleaned caption files |
| `TITLES + DESCRIPTIONS.txt` | manifest copy fields (title, headline, announcement, course_page), style-rules applied |
| `REVIVE - candidates.csv` | every candidate, kept AND rejected/skipped: `clip,mode,status,score,dur,hook_mode,title,reason` — `mode` is `upright` or `wide`, so a revived row rebuilds in the mode it was cut for |
| `clip data/` | per-clip cuts JSON, words JSON, XML + `manifest.json` + `candidates.json` |

The `work/` folder stays in the package — it is what makes "revive" work
later without re-transcribing. Register the package so the dashboard's
browser shows it (silent, failure ignorable):

```
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "<skill dir>/scripts/dashboard.py" --register "<package folder>"
```

Open the folder for the user (`open "<package folder>"`). "Revive clip N" =
compile/render that one candidate into the same folder — never redo
transcription or analysis.

### 11. Report

- Name the mode in the first line — `upright` or `wide` (rule 11) — with
  the output geometry for wide runs ("three 16:9 clips at 1920x1080, source
  untouched"). A user who expected 9:16 needs to know immediately.
- Ranked list: score, duration, hook mode, title + headline. Lead with
  "watch CLIP 1." End by asking which clips to keep and which to drop or
  change — this is the selection step (step 7 has no gate).
- Per clip: segments kept (filler cuts count) and what got cut from inside.
- Teaser clips flagged: the line plays twice on purpose — say it before
  they ask.
- Wide runs: say how many explanations the material actually held. Fewer
  than the target is an honest result, not a failure — the count floor is
  an upright rule. Name the arcs you rejected for being moments rather than
  explanations; they are upright candidates and the REVIVE sheet keeps
  them. Point at the `.srt` beside each wide clip.
- Music: say which clips carry a bed, or say in one line that there is none
  and how to add a folder (references/music-layer.md).
- Coverage: on long lectures, which windows were never read (density
  order) — honest gaps, never silent ones.
- Point at the REVIVE sheet for skipped candidates.
- Hand-off in one line: the MP4s go straight into iMovie, or any editor, or
  onto the course site.

## Liability

This is a production tool. It runs no copyright scanning, no licensing
checks, and no rights verification of any kind — not on music, not on
footage. Every right and clearance behind what you share — music licenses,
permission from anyone else who appears in the recording, your
institution's rules on recorded teaching — is your responsibility alone. If
you don't have the rights to a track, don't put it in the music folder.

## When to use

Explicit invocation always works: `/video-teach-plugin:perfect-clips` or naming
the skill. Typical asks: "make clips from this lecture", "cut a teaser for
next week", "pull three short clips for the course announcement", "find
the best moments in this video", "make phone-sized clips from this".
Wide asks route here too: "pull the full explanations out of this lecture
for the course page", "make a few minute-long excerpts" (rule 11 — wide,
minutes-long).

## Credit

Built by Vic Laranja (Systems by Vic, youtube.com/@systemsbyvic), MIT
License — see LICENSE and CREDITS.md. Adapted for lecture videos in this
plugin.
