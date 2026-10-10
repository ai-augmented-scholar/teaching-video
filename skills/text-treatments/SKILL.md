---
name: text-treatments
description: Make animated text cards (hook, title, pull quote, lower third, step list, end card) for an educational video with talking-head footage, written from the speaker's own words in the transcript, and burn them into the user's finished video, each card at the moment its words are spoken. On first use it asks where text can sit in the frame, whether the background is dark enough for white text, and which font to use, and saves the answers. Use when the user asks for text cards, titles, on-screen text, lower thirds, chapter cards or "text treatments" for a video.
---

# Text treatments

Animated text cards for a lecture video, drawn from the transcript and rendered
in the user's own look: white type, in the part of the frame they marked as
free, with a dark plate behind it when the background is too light.

## What this produces

**The user's finished video, with the cards in it.** Each card appears when
the speaker says the words it belongs to, and stays long enough to read. The
user does no placing by hand.

The work has two halves, because the cards go on the user's **final export**
(the video after they have put it together in their editor):

1. Before the edit: write the cards (Step 1). The user approves the wording.
2. After the export: place, render and burn (Steps 2 to 4).

Files, in the video's folder:

| File | What |
|---|---|
| `text-cards/cards.json` | The card text and the words each card belongs to. Edit it and run again to change a word. |
| `text-cards/cards-timed.json` | The same cards with their start, length and row times on the export's clock. |
| `text-cards/text-cards-alpha.mov` | Every card in sequence, with a real alpha channel. The source of the burn. |
| `<export name>-with-cards.mp4` | **The deliverable**: the export with the cards burned in. Sound unchanged. |

A preview on a grey ground (`--modes ground`) is available when the user wants
to read the cards without footage.

## Step 0 — The look (first use, and when the filming setup changes)

Read `${CLAUDE_PLUGIN_DATA}/config.json`. If it has a `look` section, show it in
one line ("Text in the left 40% of the frame, white, no plate, Inter. Same
filming setup as last time?") and continue on a yes.

If there is no `look`, or the user says the setup changed, ask these three
questions, one at a time. The look scripts live in
`${CLAUDE_PLUGIN_ROOT}/scripts/look/`; call each one with
`TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/look/<script>"`.

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
     the same headless browser that draws the cards.
   - If the font is missing, say so. Offer Inter, or a font file the user
     already has: check it with `check_font.py "Font Name" --file PATH` and
     save the path as `look.font_file`.

Save the answers into `${CLAUDE_PLUGIN_DATA}/config.json` under `look`. Read
the file first and change only `look`; keep every other key. This is the only
write this skill makes to the config.

```json
"look": {
  "layout": "column",
  "free_area": {"x": 0.05, "y": 0.15, "w": 0.40, "h": 0.70},
  "background_luminance": 0.129,
  "plate": true,
  "plate_color": "#202020",
  "plate_opacity": 0.7,
  "text_color": "#FFFFFF",
  "font": "Inter"
}
```

## Step 1 — Write the cards from the transcript

Read the video's transcript (from `perfect-cuts`, or made with
`TV_DATA="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe" VIDEO`).
Pull from it:

- the hook: the question or situation the student recognizes in the first
  20 seconds;
- the title of the lecture or of each part;
- a term worth defining on screen;
- a procedure or a set of parallel points, as 3 to 5 items;
- one sentence with weight in it, for the pull quote;
- the close: what comes next, or where the readings are.

Write the cards in the speaker's own words, compressed. Never invent a claim, a
number, a name or a date the video does not say. Keep headlines short.

Give every card the words it belongs to, copied from the transcript:

- `anchor`: the words the speaker says when the card should appear (four to
  six words are enough to be unique).
- `itemAnchors`: for a step list, the words that bring in each item, in order.
  Each item then appears as it is spoken.
- `until`: the words after which the card leaves. Set it on a step list that
  should stay while the speaker talks through it, and on any card whose topic
  runs on.
- `at`: only when the anchor is said twice: about where, in seconds.

**Card length: this is a teaching video, not the news.** Do not write `dur`;
Step 2 computes it. A simple card stays at least 8 seconds, longer when its text
needs more reading time. A step list stays until its last item has been on
screen at least 4 seconds, and stays with the speaker when `until` says so. A
card never leaves in the middle of a sentence and never runs into the next card.

Save them as `<video folder>/text-cards/cards.json`:

```json
{"cards": [
  {"kind": "hook", "eyebrow": "Week 3", "headline": "…", "dek": "…", "anchor": "…"},
  {"kind": "title", "eyebrow": "Part 1", "headline": "…", "anchor": "…"},
  {"kind": "pullQuote", "quote": "…", "attribution": "…", "anchor": "…"},
  {"kind": "lowerThird", "name": "…", "role": "…", "anchor": "…"},
  {"kind": "stepList", "eyebrow": "…", "items": ["…", "…", "…"],
   "anchor": "…", "itemAnchors": ["…", "…", "…"], "until": "…"},
  {"kind": "endCard", "signOff": "…", "cta": "…", "anchor": "…"}
]}
```

- An end card may take `dek` (a second, smaller line), and `markSrc` /
  `markOpacity` for the user's own logo file in `renderer/public/`.
- With `layout: "lower-thirds"`, keep step lists to 3 items and headlines to
  about 6 words: everything has to fit in the bottom band.
- Show the user the card text before going on. It is their wording on screen.

Then the user puts the video together in their editor and exports it **without
cards**. Continue at Step 2 with that export.

## Step 2 — Place the cards on the export

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/text-treatments/scripts/burn_cards.py" \
  plan "<final export>" --cards "<video folder>/text-cards/cards.json" \
  --out-dir "<video folder>/text-cards"
```

It transcribes the export with Parakeet (about 12 seconds for 7 minutes of
video; the words are kept and reused while the export does not change), finds
each card's words, and prints a table: in, out, length, the words it heard, the
item times. Show the user the table and every `!` note:

- `ANCHOR NOT HEARD` or `ROW n NOT HEARD`: fix the words in `cards.json`
  (copy them from the transcript), and run again.
- `SAID 2x`: add `at` to that card.
- `SHORT`: the next card starts too soon for this one. Move one of them, or
  accept it.

Wait for the user's approval of the times.

## Step 3 — Render

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" node "${CLAUDE_PLUGIN_ROOT}/skills/text-treatments/scripts/render.mjs" \
  --cards "<video folder>/text-cards/cards-timed.json" \
  --out "<video folder>/text-cards" \
  --footage "<final export>" \
  --modes alpha --check
```

- The script copies the renderer into `${CLAUDE_PLUGIN_DATA}/renderer` and
  installs its packages there. The install is large, about 500 MB, and happens
  once; it runs again only when the plugin's renderer packages change. If Node
  is missing, tell the user to run `/video-teach-plugin:setup`.
- It reads the look from the config, and the frame rate from `--footage`, so
  the fades do not judder on the timeline.
- `--check` verifies the cut contract (below) on lossless frames and reports
  any card that does not start and end on the bare ground. A report with pops
  is a defect: fix the scene before delivering.
- Always render from `cards-timed.json`, the file Step 2 wrote. The burn
  checks that the clip and the times come from the same file.
- About 2.5 minutes for 100 seconds of cards at 60 fps.

## Step 4 — Burn the cards in, and look before you hand it over

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/text-treatments/scripts/burn_cards.py" \
  burn "<final export>" --timed "<video folder>/text-cards/cards-timed.json" \
  --clip "<video folder>/text-cards/text-cards-alpha.mov" \
  --out "<video folder>/<export name>-with-cards.mp4" \
  --sheet "<video folder>/text-cards/cards-sheet.png"
```

One ffmpeg pass; the sound is copied unchanged (about 4 minutes for a 7-minute
video). `--sheet` tiles one frame per card, taken when the card's text is
complete. View it. Check that the text sits in the free area, clears the
speaker, reads against the background, and shows no text under 24 px. Fix and
run again before you report.

## Hand-off

Tell the user in plain words: `<export name>-with-cards.mp4` is the finished
video. Their own export stays as it was. To change a word or a time, edit
`cards.json` and run Steps 2 to 4 again; nothing has to be redone in the editor.

## How the renderer works (for changes to it)

The renderer is a Remotion project in `renderer/`. Cards, look and frame rate
arrive as input props, so nothing in `src/` changes per video. Read this before
you edit a scene.

**One design system, built from the look.** `src/design-systems/neutral.ts`
turns `look` into colours, type and layout. Scenes never hardcode a colour, a
font, a size or a weight: they ask for a role (`t.quote`, `t.eyebrow`) and the
design system decides. Type scales with the width of the free area and never
drops below 24 px. Every card keeps at least 80 px from the frame edge.

**The cut contract: what makes cards liftable.** Every scene starts and ends on
the bare ground. Content fades up after the cut and settles back down before
it, so adjacent scenes match frame for frame and any card lifts out with clean
handles at both ends. `Frame` owns this: it applies `close()` to the scene
root, so no scene can forget the second half of the contract.

> **The off-by-one that breaks it.** The last rendered frame is
> `durationInFrames - 1`, so the `close()` ramp must finish there, not at
> `durationInFrames`. Getting this wrong leaves the final frame at roughly 7%
> opacity: invisible in a scrub, a faint ghost on every lifted card. `Frame`
> computes `sceneDur = (durationInFrames - 1) / fps` for exactly this reason.

> **Check boundaries on lossless frames, never on the H.264 file.** Lossy
> compression perturbs a flat frame that follows a busy one, so an exact-hash
> comparison reports a pop that is not there. `render.mjs --check` renders PNG
> frames for this reason.

**Exactly three motion helpers** (`src/motion.ts`), and nothing eases outside
them: `enter()` (fade and rise, per element, staggered in reading order),
`draw()` (lines and rules draw, they never fade), `close()` (whole-frame
opacity back to 0 in the last 0.5 s). Animate only from scene-local time:
inside a Remotion `<Sequence>`, `useCurrentFrame()` already starts at zero, so
local time is `frame / fps`. That lets a card's duration change and its
choreography stretch instead of clip.

> **`PlatedBlock` puts the caller's `style` on its inner wrapper.** Putting it
> on the outer wrapper leaves the children in a plain block div, so a scene
> asking for `display: flex` silently gets block flow, and the accent rules of
> the pull quote, lower third and end card collapse to zero size. If you add a
> wrapper, keep the layout styles on the element that holds the children.

**Modes.** `alpha` (transparent ground; the source of the burn), `imovie` (pure
`#00FF00` ground; plate opaque with hard edges; kept for a user who wants to
place cards by hand in iMovie), `ground` (dark grey preview).

**Placement** is `scripts/place_cards.py`, called by `burn_cards.py plan`. Compositions are named
`neutral-<mode>`.

**Fonts.** Inter ships in `renderer/public/fonts/` (SIL Open Font License,
`OFL.txt` beside it) and is loaded by `src/fonts.ts`, so the default renders the
same on every Mac. An installed font is found by name; a font file
(`look.font_file`) is copied into the renderer by `render.mjs` and loaded under
its name. Inter is always the fallback.

**Scenes.** Hook, Title, Pull quote, Lower third, Step list and End card are
built. To add one, write `renderer/src/scenes/<Name>.tsx`, wrap it in `Frame`,
add its card type and case to `TreatmentPackage.tsx`, and run a render with
`--check`.
