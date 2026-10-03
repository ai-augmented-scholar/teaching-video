---
name: text-treatments
description: Make animated text cards (hook, title, pull quote, lower third, step list, end card) for an educational video with talking-head footage, written from the speaker's own words in the transcript. One clip holds every card in sequence; the user lifts each card out in iMovie, or any editor. Renders a green-screen file for iMovie and a file with a real alpha channel for editors that read one. On first use it asks where text can sit in the frame, whether the background is dark enough for white text, and which font to use, and saves the answers. Use when the user asks for text cards, titles, on-screen text, lower thirds, chapter cards or "text treatments" for a video.
---

# Text treatments

Animated text cards for a lecture video, drawn from the transcript and rendered
in the user's own look: white type, in the part of the frame they marked as
free, with a dark plate behind it when the background is too light.

## What this produces

**One clip, many cards.** Every card is a self-contained scene, laid end to
end. The user scrubs to a card, cuts it out and places it where it belongs.
Never deliver one file per card.

In the video's folder, under `text-cards/`:

| File | For |
|---|---|
| `text-cards-imovie-green.mov` | iMovie. The cards on pure green, removed with iMovie's Green/Blue Screen overlay. |
| `text-cards-alpha.mov` | Editors that read an alpha channel: Final Cut Pro, Premiere Pro, DaVinci Resolve, and others. ProRes 4444; drops straight on top of the footage. |
| `text-cards-card-times.txt` | Where each card starts and ends in the clip. |
| `cards.json` | The card text. Edit it and render again to change a word. |

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
number, a name or a date the video does not say. Keep headlines short: a card
is read in about four seconds.

Save them as `<video folder>/text-cards/cards.json`:

```json
{"cards": [
  {"kind": "hook", "dur": 4, "eyebrow": "Week 3", "headline": "…", "dek": "…"},
  {"kind": "title", "dur": 4.5, "eyebrow": "Part 1", "headline": "…"},
  {"kind": "pullQuote", "dur": 4.5, "quote": "…", "attribution": "…"},
  {"kind": "lowerThird", "dur": 4, "name": "…", "role": "…"},
  {"kind": "stepList", "dur": 6.5, "eyebrow": "…", "items": ["…", "…", "…"]},
  {"kind": "endCard", "dur": 4.5, "signOff": "…", "cta": "…"}
]}
```

- A step list may take `delays` (seconds from the card's start, one per item),
  so each item lands on the spoken word.
- An end card may take `dek` (a second, smaller line), and `markSrc` /
  `markOpacity` for the user's own logo file in `renderer/public/`.
- With `layout: "lower-thirds"`, keep step lists to 3 items and headlines to
  about 6 words: everything has to fit in the bottom band.
- Show the user the card text before rendering. It is their wording on screen.

## Step 2 — Render

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" node "${CLAUDE_PLUGIN_ROOT}/skills/text-treatments/scripts/render.mjs" \
  --cards "<video folder>/text-cards/cards.json" \
  --out "<video folder>/text-cards" \
  --footage "<the cut video>" \
  --modes alpha,imovie --check
```

- The script copies the renderer into `${CLAUDE_PLUGIN_DATA}/renderer` and
  installs its packages there. The install is large, about 500 MB, and happens
  once; it runs again only when the plugin's renderer packages change. If Node
  is missing, tell the user to run `/teaching-video:setup`.
- It reads the look from the config, and the frame rate from `--footage`, so
  the fades do not judder on the timeline.
- `--check` verifies the cut contract (below) on lossless frames and reports
  any card that does not start and end on the bare ground. A report with pops
  is a defect: fix the scene before delivering.
- A five-card package renders in about a minute per mode.

## Step 3 — Look at it before you hand it over

Take a frame of the user's own footage and put one card over it:

```bash
ffmpeg -v error -y -ss 30 -i "<footage>" -frames:v 1 -vf scale=1920:1080 /tmp/bg.png
ffmpeg -v error -y -i /tmp/bg.png -ss 2.5 -i "<out>/text-cards-alpha.mov" \
  -filter_complex "[1:v]format=rgba[o];[0:v][o]overlay=0:0:format=auto" -frames:v 1 /tmp/card.png
```

View `/tmp/card.png`. Check that the text sits in the free area, clears the
speaker, reads against the background, and shows no text under 24 px. Fix and
re-render before you report.

## Hand-off

Tell the user which file to use, in plain words.

**iMovie:**
1. Import `text-cards-imovie-green.mov` into the project.
2. Open `text-cards-card-times.txt` to see where each card sits in the clip.
3. In the clip, select just the range of one card, and drag it **above** the
   main video, at the moment where it belongs.
4. Leave the playhead on the first frame of that overlay, where it is plain
   green. Click the Video Overlay Settings button, and choose **Green/Blue
   Screen** from the pop-up menu. iMovie removes the colour that fills the
   frame under the playhead, so that frame must be green.
5. If a thin edge shows around the letters, drag the **Softness** slider a
   little. Set softness before using Clean-up: changing softness afterwards
   resets the clean-up.

In iMovie a plate shows as solid dark grey, without the see-through effect:
a keyer cannot cut a half-transparent plate cleanly, so the green-screen file
draws it opaque with hard edges. For the same reason the second-level text
(eyebrows, deks, roles) is drawn in a solid light grey there, mixed over the
plate or over the measured background, rather than as translucent white:
translucent white over green turns pale green, and the key greys it out.

**Final Cut Pro, Premiere Pro, DaVinci Resolve, and other editors that read
alpha:** put `text-cards-alpha.mov` on the track above the footage and blade
out each card. It needs no keying.

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

**Modes.** `alpha` (transparent ground), `imovie` (pure `#00FF00` ground; plate
opaque with hard edges), `ground` (dark grey preview). Compositions are named
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
