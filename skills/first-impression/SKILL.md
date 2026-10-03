---
name: first-impression
description: Plan what a student sees before pressing play on a lecture video — the title, a poster frame (thumbnail) concept, and two or three ways to open the first 30 seconds — so all three make the same promise. For educational videos with talking-head footage that live on a course site or LMS page. Works from the video's transcript or its beat sheet and writes first-impression.html in the video folder. Use when the user asks what to call a lecture video, wants a thumbnail or poster-frame idea, wants a stronger opening, or says "first impression".
---

# first-impression

A student meets a lecture video on a course page in three steps: the small image, the title beside it, then the first half minute of the video. Each step either confirms what the one before it suggested or makes the student doubt it. This skill plans those three pieces together, around one sentence that says what the student will understand or be able to do after watching.

The output is a page for the user to choose from. The user makes the image (in Canva, Preview or any image app) and films or re-records the opening. This skill writes no video and no image.

## Inputs

1. **Find the video folder.** Read `${CLAUDE_PLUGIN_DATA}/config.json` if it exists and take `videos_root` (default `~/Movies/teaching-videos`). Each video has its own numbered folder there. If the user named a folder or a file, use that. If more than one video could be meant, list the candidates and ask.
2. **Find the source**, in this order:
   - a transcript of the finished cut (a `.txt` or `.srt` from `perfect-cuts`, or one made with the bundled transcriber),
   - the beat sheet, if the video is not filmed yet,
   - the user's own description, as a last resort.

   If only a video file exists, transcribe it locally:

   ```bash
   TV_DATA="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe" "<video file>" --txt --outdir "<video folder>"
   ```

   Read the first lines of the result before you go on. Parakeet reports no language and no confidence score, so a look at the words is the only check.
3. **Ask only what the source cannot answer**, in one short message, and only if it is missing:
   - Who watches? (course level, field, required or optional viewing)
   - Where does the video sit? (week, unit, before or after a reading)

   If the source answers both, do not ask.

Write everything in the lecture's own language, and capitalize titles the way that language does. A capital on every word of a title is English style; a German or Spanish reader sees it as a mistake.

## Step 1 — The promise

Write one sentence that names what the student gets: a concept they will be able to explain, a distinction they will be able to draw, a method they will be able to apply, a mistake they will stop making. Take it from what the lecture says, not from what it could have said. Everything below serves this sentence.

Then choose **one** way in, and keep it for all three pieces:

| Angle | The promise reads as |
|---|---|
| how | how to do or read something |
| why | why something happened or works the way it does |
| compare | how two things differ (two periods, two theories, two methods) |
| mistake | the common misreading and the better one |
| question | a question students ask, answered |

Mixing angles is a common failure: a poster frame that warns, a title that explains, and an opening that tells a story leave the student unsure why they should watch.

## Step 2 — Title, three options

- Put the subject term near the front; course pages and LMS lists cut long titles off at the end.
- Stay at 60 characters or fewer when the meaning survives. The page counts them for you.
- Say what the student gets. "Romantic and neoclassical gardens: what each design says about its owner" tells a student more than "Gardens, part 2".
- No unit numbers or dates in the title; the course page already shows where the video sits.
- Add a short note to each option on what it does better than the other two. The three options read the promise in three different ways; three word swaps of one title are one option.
- Mark one option as the pick.

## Step 3 — Poster frame concept

The poster frame is the still image a course page shows before playback. Many platforms let the user upload one; otherwise it is a frame chosen from the video.

- **Text:** three or four words at most, large enough to read at the size of a course-page tile. Include the subject term or the closest short form of it. Give two alternates.
- **Focal image:** one thing — an object, a map, a painting, a diagram, a page of the source text. One clear image reads at small size; three do not.
- **Speaker:** expression and position in the frame (for example "left third, looking at the object, curious"). Match the expression to the angle: a mistake-angle video can look puzzled; a how-angle video looks ready to show something.
- The text and the image must tell the student the subject on their own, before the title is read.
- Use digits for numbers. Keep the text and the title on the same angle.

## Step 4 — The first 30 seconds, two or three openings

Write each opening as **beats**: short bullets the user turns into their own words on camera. Never write a script to read aloud; read text sounds wooden on camera.

- The promise appears in the first two beats, in the title's terms.
- About 30 seconds of speech each (roughly 60 to 90 words when spoken).
- The mood follows the poster frame and the title. A puzzled poster frame opens with the puzzle.
- Make the openings differ in kind, for example:
  - one that opens with the outcome ("by the end you can …"),
  - one that opens with the question or confusion students bring,
  - one that opens with a concrete case from the lecture itself (a quote, an object, a date, an example).
- Mark one opening as the pick and say why in the consistency note.

## Rule for facts

Never invent a number, a name, a quote, a date or a source. Where the lecture does not supply one, write `[FILL IN: what is needed]` and keep going. The page lists every open item at the end.

## Step 5 — Consistency check

Before writing the page, read the picked title, the poster text and the picked opening side by side. They must make the same promise, on the same angle, in the same mood. If one drifts, fix it, then write one short paragraph that says how the three line up.

## Step 6 — Write the page

Write the plan as JSON (the shape is documented at the top of the script), then render it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/first-impression/scripts/build_page.py" "<video folder>/first-impression.json" "<video folder>/first-impression.html"
open "<video folder>/first-impression.html"
```

The script counts the title characters, flags any title over 60 characters, labels the picks with the word "Picked" (never by color alone), and refuses a plan without exactly one picked title and one picked opening. If `first-impression.html` already exists, ask before replacing it.

Writing rules for everything on the page: plain words, active sentences with a person doing the action, no adverbs such as "really" or "simply", no stock openers such as "Here's the thing", no "not X, but Y" contrasts, no slogans.

## Report

Tell the user, in a few lines: the picked title, the poster text, which opening you picked and why, the path of the page, and any `[FILL IN]` items they still have to supply.

---

Method after Shane Hummus's Holy Trifecta (youtube.com/@ShaneHummus).
