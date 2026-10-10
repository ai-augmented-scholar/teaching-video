---
name: video-with-slides
description: Put a lecturer's own slides next to their talking-head video, with each slide coming on screen when they start talking about it. Takes the cut video and the deck they lectured from (PDF from PowerPoint, Keynote, Canva, Google Slides or Beamer, or a .pptx), proposes the slide timing from the transcript, lets the user correct it in a timing table, and renders one 1920x1080 MP4 with the slide beside the speaker, the speaker in a corner box, the slide alone, or the speaker full frame. The alternative to text cards for a lecture that already has slides. Use when the user asks to "add my slides to the video", "put the slides next to me", "sync my slides with my lecture", "make a lecture video with slides", or has a lecture recording plus a slide deck.
---

# Video with slides

The lecturer's own slides, on screen when they talk about them, beside the
lecturer. The transcript proposes when each slide comes up; the user checks
the timing in a table; one ffmpeg pass renders the result.

This skill does not cut. It works on a video that is already cut, and its
output has exactly the length and sound of that cut. So the order is:
`audio-enhance`, then `perfect-cuts`, then this skill. Never merge the two
jobs into one run: a cut changes every time on the timeline, and the slide
timing must be made on the final one.

**Slides or text cards?** For a lecture with a deck, this skill replaces
`text-treatments`: the slides already carry the titles, terms and lists that
text cards would put on screen. Use text cards for a talk without slides.

## What this produces

In the video's folder, under `slides-video/`:

| File | For |
|---|---|
| `<cut name>-with-slides.mp4` | The finished video, 1920x1080, the cut's frame rate and sound. iMovie imports it like any clip. |
| `timing.json` | When each slide comes up. Edit a time and render again to move a slide change. |
| `slides/` | One image per slide. |
| `slides.json` | The text and speaker notes of each slide. |
| `source.json` | Which cut the video was made from (its path, length and frame count) and where the output went. Written by every render. perfect-clips reads it to cut upright clips from the cut, so the user may rename or move the finished video freely. |
| `transcript.json` | The words of the cut, with times. |
| `check/` | Stills for looking at the result. |

Because the sound is the cut's own sound, captions made for the cut fit this
video unchanged.

## Settings

Read `${CLAUDE_PLUGIN_DATA}/config.json` if it exists. Use `videos_root` to
find the video's folder (numbered folders, `NN-slug`). Without the file, use
`~/Movies/teaching-videos` and tell the user once that `/video-teach-plugin:setup`
saves their settings.

Every command below passes the plugin's data folder as `TV_DATA`, so the
scripts find the tools that setup installed. `SK` stands for
`${CLAUDE_PLUGIN_ROOT}/skills/video-with-slides/scripts` and `OUT` for
`<video folder>/slides-video`.

## Step 0 — The two inputs

1. **The cut video.** Normally the MP4 from `perfect-cuts`. If the user hands
   you a raw recording, say once that this skill keeps every second of it,
   retakes included, and offer `perfect-cuts` first. Continue on the raw file
   only if they want that.
2. **The deck the lecturer used**, in the same order they presented it.
   - **PDF** from any app: the best input. Ask for it by app:
     PowerPoint: File > Export > PDF. Canva: Share > Download > PDF Standard.
     Google Slides: File > Download > PDF. Keynote: File > Export To > PDF.
   - **.pptx**: accepted. Its speaker notes are read from the file, and they
     help the matching, because they are close to what the lecturer said.
     Turning the .pptx into images needs LibreOffice. Without it, ask for a
     PDF export too and pass the .pptx with `--notes-from` (Step 1).
   - **Builds and animations** do not survive a PDF export: a slide with
     bullets that appear one by one becomes one page with every bullet
     showing. Tell the user this once if the deck has builds. To keep the
     builds, they can save one page per build step (in PowerPoint, duplicate
     the slide for each step) before exporting.

## Step 1 — Slides to images and text

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$SK/slides_prepare.py" "<deck.pdf or .pptx>" --out "$OUT"
# a PDF exported from a .pptx, keeping the notes:
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$SK/slides_prepare.py" "<deck.pdf>" --notes-from "<deck.pptx>" --out "$OUT"
```

It reads PDFs with pypdfium2 from the plugin's environment, or with poppler
(`pdftoppm`) when that is installed. If it reports that nothing can read a
PDF, offer to add pypdfium2 (about 6 MB) with the command it prints, consent
first, or run `/video-teach-plugin:setup`.

It reports any slide without text. A picture-only slide gives the matcher
nothing to go on, so it is placed by hand in Step 4.

## Step 2 — The transcript of the cut

Transcribe the video this skill works on, not the raw take: the times must be
the cut's times.

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe" "<cut video>" --words "$OUT/transcript.json" --quiet
```

A single Parakeet pass can drop whole sentences on a long or noisy file.
Step 3 reports every stretch of more than 20 s without a word. If one sits
where the lecturer is talking, or the video runs over about 20 minutes,
transcribe in windows with the perfect-cuts scripts and use that transcript:

```bash
PC="${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts"
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$PC/speech_map.py" "<cut video>" "$OUT/transcript.json" --out "$OUT/map.json"
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$PC/transcribe_windows.py" "<cut video>" "$OUT/map.json" --out "$OUT/transcript.json"
```

## Step 3 — Propose the timing

```bash
python3 "$SK/match_slides.py" propose --slides "$OUT/slides.json" --words "$OUT/transcript.json" \
  --out "$OUT/timing.json" --duration <length of the cut in seconds>
```

The script scores every sentence against every slide by the words they
share, then picks a path through the deck that only moves forward. It prints
a timing table: when each slide comes up, a confidence, the slide title, and
the words spoken at the change. After the table it may list "possible
returns to an earlier slide" and stretches without words.

On a 10-slide test lecture it placed 9 of 10 changes within a sentence of
the right moment. The tenth was in its list of possible returns. Treat the
proposal as a draft for Step 4, not as a result.

## Step 4 — Your pass over the timing

Read `slides.json` (the text of each slide) next to the table. Then correct
`timing.json` by hand where the evidence says so:

- **Low and mid confidence rows.** Read the transcript around the change in
  `transcript.json` and put the change at the sentence that starts the
  slide's topic.
- **Possible returns.** A lecturer who says "back to the table" goes back to
  an earlier slide. The script only moves forward, so add the return as its
  own segment, and a segment for the slide after it.
- **Spoken cues.** "Next slide", "as you can see here", "on this chart" mark
  a change, even when the slide text and the words share nothing.
- **Picture-only slides** and slides marked "not shown at all": place them
  from the context, or leave them out if the lecturer skipped them.
- **The opening and the close.** A lecture usually opens with a greeting and
  ends with a sign-off. Propose `{"start": 0, "show": "speaker"}` for the
  opening until the first slide's topic starts, and a speaker segment for
  the sign-off. Full frame on the face is what a viewer expects there.
- **Change in the pause.** The script puts each change a quarter second
  before the first word of the new topic. Keep that when you move a change.

The format of a segment: `{"start": 95.2, "slide": 4}`, or
`{"start": 0, "show": "speaker"}`, with an optional `"layout"` for that
segment only. Each segment runs until the next one starts. Then print the
table again:

```bash
python3 "$SK/match_slides.py" table --timing "$OUT/timing.json" --words "$OUT/transcript.json" --slides "$OUT/slides.json"
```

## Step 5 — The user checks the timing

Show the user the table, in a code block, and ask for corrections in plain
words ("slide 8 comes at 5:35", "keep me full screen for the first 20
seconds"). Make the changes, print the table again, and ask again until they
approve it. Do not render before they approve: a render takes about a third
of the video's length, and the table takes a second.

## Step 6 — The look (first use, and when the user asks)

Read the `slides` section of `${CLAUDE_PLUGIN_DATA}/config.json`. If it has
one, show it in one line ("Slide left, you on the right, the bundled
background. Same as last time?") and continue on a yes. Otherwise agree on
these, with stills to look at:

1. **Layout.** `side-by-side` (default): the slide large, the lecturer in a
   tall box beside it. `pip`: the slide nearly full frame, the lecturer in a
   small box inside its bottom corner; it can cover slide content there, so
   use it only for decks that keep that corner empty. `slide`: the slide
   alone. Any segment can override the default, for example a dense table
   shown as `slide`.
2. **Which side the lecturer is on**: `right` (default) or `left`.
3. **Where the lecturer sits in the frame**, as `speaker_x`: the centre of
   the speaker, as a fraction of the frame width. Without it the script uses
   the free area saved for text cards (the speaker is in the rest of the
   frame), else the middle. Take frames with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/look/grab_frames.py" "<cut video>" "$OUT/check"`,
   look at them, and estimate the speaker's centre yourself.
4. **Background.** The bundled background (a dark purple-to-teal gradient,
   `assets/background.png`), the user's own image (any size; it is scaled
   and cropped to fill 1920x1080), or a plain colour such as `#1e1b3a`.

Make stills of the result without rendering:

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$SK/compose.py" --video "<cut video>" --work "$OUT" \
  --timing "$OUT/timing.json" --preview [--at 75,190,400]
```

Look at every still yourself before showing it. Check that the lecturer's
head and hands are inside the box, the slide is sharp and readable, and
nothing important sits under a `pip` box. Use `--at` with times from the
table to check a close-up shot or a moment when the lecturer moves. Adjust
`speaker_x` and run it again.

Save the approved choices in `${CLAUDE_PLUGIN_DATA}/config.json` under
`slides`. Read the file first and change only `slides`; keep every other key.

```json
"slides": {
  "layout": "side-by-side",
  "speaker_side": "right",
  "speaker_x": 0.59,
  "background": null
}
```

`background: null` means the bundled one. Options on the command line beat
`timing.json`, which beats the saved `slides` section.

## Step 7 — Render

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "$SK/compose.py" --video "<cut video>" --work "$OUT" \
  --timing "$OUT/timing.json" --out "$OUT/<cut name>-with-slides.mp4"
```

Measured: a 7 min 49 s lecture at 60 fps, 11 segments, rendered in 2 min
45 s on an Apple Silicon laptop. Tell the user the expected time before you
start.

The script checks the result itself: the length must match the cut within
one frame, and the sound must be there. It writes one still per layout to
`$OUT/check/`, and `$OUT/source.json` with the cut's path, length and frame
count and the output's path. Leave `source.json` in place: perfect-clips
finds the cut through it. A folder rendered before this file existed is
still found through the old name rule, `<cut name>-with-slides.mp4`.

## Step 8 — Look at it before you hand it over

1. View every still the render wrote. Compare with the approved previews.
2. Check two slide changes on the frame: the frame before a change shows the
   old slide, the frame at the change the new one. The frame number is the
   start time times the frame rate.

   ```bash
   ffmpeg -v error -y -i "<output>" -vf "select='eq(n\,<N-1>)+eq(n\,<N>)',scale=640:360,tile=2x1" \
     -frames:v 1 -fps_mode passthrough "$OUT/check/change.png"
   ```
3. Play 5 seconds around a change in QuickTime if the user wants to see the
   lip sync. The sound is copied from the cut, so a lip-sync fault means a
   frame-rate problem in the source: report it, do not hide it.

Fix and render again before you report.

## Hand-off

Tell the user, in plain words:

- which file to use, and that it imports into iMovie, or any editor, as one
  clip;
- that `timing.json` is the place to move a slide change, and that you can
  render again in a few minutes;
- that captions for the cut fit this video, so `captions-and-description`
  can run on it directly;
- that the file can be renamed or moved within the video folder; short clips
  still find the cut it was made from.

## How compose.py works (for changes to it)

- **Plates.** Each segment shows a still plate: the background, the soft
  shadow, the slide, and the shadow of the speaker box, drawn once per slide
  and layout into `$OUT/plates/`. ffmpeg cannot draw text on these Macs (the
  Homebrew build has no freetype), so everything on screen comes from images.
- **Exact frames.** Each plate is looped and trimmed to its segment's frame
  count, the plates are concatenated, and the speaker video is overlaid with
  `enable` expressions on the frame number `n`. Times become frame numbers
  once, in `load_segments`, so a change never drifts by a frame.
- **The frame rate** is the nominal rate of the cut (`r_frame_rate`). The
  average rate drifts on edited files: a 60 fps cut from perfect-cuts reports
  an average of 59.953, and rounding that to 59.94 drops a frame in a
  thousand.
- **The speaker crop** keeps 1% clear of the top and bottom of the source
  frame. Camera files often carry a dark row at the edge, which shows as a
  line along the top of the box.
- **Layout geometry** is in `geometry()`: side-by-side gives a 16:9 slide
  1280x720 and a 488x720 speaker box; a 4:3 slide gets a narrower box, and the
  pair is centred.
