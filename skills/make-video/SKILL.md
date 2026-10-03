---
name: make-video
description: Run the whole teaching-video workflow for an educational video with talking-head footage, from beat sheet to finished video and short clips, in 14 steps. Claude does the sound, the cut, the text cards or slides, the captions and the clips; the user drafts, films, reviews, assembles in iMovie (or any editor) and publishes by hand. Keeps a status file in the video's folder, stops with a Mac notification at every step that is the user's, and picks up where it left off after a break. Use when the user says "make a video", "start a new lecture video", "continue my video", "where was I", or runs /teaching-video:make-video.
---

# make-video: the whole workflow, one step at a time

$ARGUMENTS

This skill runs the other skills of the plugin in the right order and keeps track
of where each video stands. It does no editing of its own. For each step it
calls one skill, or it stops and tells the user what to do.

The plugin is made for **educational videos with talking-head footage**: one
person on camera, explaining. Any video editor works; iMovie stands for "iMovie,
or any editor".

Throughout this file:

```bash
MV="${CLAUDE_PLUGIN_ROOT}/skills/make-video/scripts"
export TV_DATA="${CLAUDE_PLUGIN_DATA}"
```

Pass `TV_DATA` on every command, as written. The scripts read the settings
(`$TV_DATA/config.json`) through it.

## The status file

Each video has a folder `NN-slug` under `videos_root` (from the settings;
default `~/Movies/teaching-videos`), and in it a file `make-video-status.json`
that records each step's state (`pending`, `running`, `waiting-for-you`,
`done`, `skipped`), its input and output files, the choices made, and times.

**Only `status.py` reads and writes that file. Never edit the JSON by hand.**

```bash
TV_DATA="$TV_DATA" python3 "$MV/status.py" new --title "<title>"     # new video: makes the next NN-slug folder, prints its path
TV_DATA="$TV_DATA" python3 "$MV/status.py" find [words]              # list videos and where each stands
TV_DATA="$TV_DATA" python3 "$MV/status.py" show "<video folder>"     # the 14 steps, with the next one marked
TV_DATA="$TV_DATA" python3 "$MV/status.py" set "<video folder>" 03 running --input "<raw take>"
TV_DATA="$TV_DATA" python3 "$MV/status.py" set "<video folder>" 03 done --output "<cleaned file>"
TV_DATA="$TV_DATA" python3 "$MV/status.py" set "<video folder>" 06 done --choice path=slides --output "<file>"
TV_DATA="$TV_DATA" python3 "$MV/status.py" reopen "<video folder>" 04   # send 04 and every later step back to pending
TV_DATA="$TV_DATA" python3 "$MV/status.py" look                     # the saved look in one line, or "none"
```

`set` refuses to start or finish a step while an earlier one is still open, and
refuses `done` with an output file that does not exist. Mark a step `running`
before you start it and `done` with its output when it is finished, so a break
in the middle leaves an honest record.

## Start

1. **Which video?** If the user names a video, or says "continue", run `find`
   and pick the match (ask if two match). If they start a new one, ask for a
   working title and run `new`. For an existing folder that has no status file
   yet, run `init "<folder>" --title "<title>"`.
2. **Resume.** Run `show`. Continue at the step marked `->`. A step left
   `running` was interrupted: check whether its output exists and is complete
   before you redo it.
3. **New video only: the filming setup.** Run `look`.
   - It prints a look: show that line and ask **"Same filming setup as last
     time?"** On a yes, go on. On a no, run the look questions of
     `text-treatments` (its Step 0) before step 01.
   - It prints `none`, or there is no settings file at all: the computer has not
     been set up. If `/teaching-video:setup` has never run (no settings file),
     ask the user to run it first; it installs the tools and asks these
     questions. If only the look is missing, ask the three look questions now,
     through `text-treatments` Step 0.
4. **Say once which steps need a strong model.** Step 04 (the cut) needs Sonnet
   at high effort or Opus at medium effort; `perfect-cuts` checks this itself
   and stops otherwise. Steps 06, 08 and 11 also read the transcript closely and
   do best on the same models. The other steps are scripts and run on any model.

## The 14 steps

Run them in order. "You" steps belong to the user (see "A step that is yours").

| Step | Who | What | Skill / input → output |
|---|---|---|---|
| 01 | You + Claude | Draft the beat sheet | `beatsheet` → `beat-sheet.html` in the video folder |
| 02 | You | Film | the raw take, placed in the video folder |
| 03 | Claude | Clean the sound | `audio-enhance` on the **raw take** → `<stem>_enhanced-audio.<ext>` |
| 04 | Claude | Cut the retakes | `perfect-cuts` on the **cleaned file from 03**, never the raw take → `1 WATCH - final video (C).mp4`; then the audio gate |
| 05 | You | Review the cut | watch the MP4 once; changes go back to 04 |
| 06 | Claude | Text cards **or** slides | ask about a slide deck → `video-with-slides` or `text-treatments` |
| 07 | You | Assemble | iMovie, or any editor |
| 08 | Claude + You | Title, opening, thumbnail | `first-impression` → `first-impression.html`; the user makes the thumbnail |
| 09 | Claude | Captions and description | `captions-and-description` on the user's **final export**; then the audio gate |
| 10 | You | Publish | upload by hand to the course site |
| 11 | Claude | Short clips | `perfect-clips` on the final export; upright clips come from the speaker cut |
| 12 | You | Pick the clips | keep the best |
| 13 | You | Polish the clips | iMovie, or any editor |
| 14 | You | Publish the clips | upload by hand |

### 01 Beat sheet

Run the `beatsheet` skill for this video folder (pass the folder, so it does not
make a second one). It asks for topic, audience, length and whether the user
films from a script. When `beat-sheet.html` exists: `set 01 done --output
"<folder>/beat-sheet.html"`. The user may skip the beat sheet (they already
filmed, or work from their own notes): `set 01 skipped --note "<why>"`.

### 02 Film

A "you" step. Tell the user: film the lecture, one take per section, restarts
are fine, then put the recording (the camera or recorder file, not an export)
into the video folder, or tell you where it is. When the file is there, check it
with `ffprobe` (duration, a video and an audio stream), then
`set 02 done --output "<raw take>"`.

### 03 Clean the sound

`set 03 running --input "<raw take>"`, then run the `audio-enhance` skill on the
raw take, as its SKILL.md says (it is one script; relay its table and every
`WARNING:` line). Its output for a video is `<stem>_enhanced-audio.<ext>` next to
the raw take. `set 03 done --output "<that file>"`. If it prints `MISSING`, the
tools are not installed: point the user to `/teaching-video:setup` and stop.

### 04 Cut the retakes

`set 04 running --input "<cleaned file from 03>"`. Run `perfect-cuts` on the
**cleaned file**, never the raw take: on raw audio, room noise keeps restarts
glued to the line before them. Give it the answers you already have, so it asks
only what is open: the clip path, Q1 (script) from the beat sheet or step 01's
answer, Q2 = yes (the MP4), Q3 = next to the source clip (the video folder).

Step 04 has three parts:

1. **The analysis and the editorial pass**, as `perfect-cuts`' SKILL.md
   describes them: transcription, the speech map, the check for dropped speech,
   and the editorial pass. Their product is `cuts.json`.
2. **One call builds the whole package** from `cuts.json` (the MP4, the timeline
   files, the captions, the cut log):

   ```bash
   TV_DATA="$TV_DATA" python3 "${CLAUDE_PLUGIN_ROOT}/skills/perfect-cuts/scripts/build_package.py" \
     --source "<cleaned file from 03>" --cuts "<cuts.json>" \
     --out "<video folder>/<stem> perfect cut (C)" [--title "<video title>"]
   ```

   It prints a JSON summary. Take the MP4 path from that summary; do not
   rebuild the path by hand. A non-zero exit means the package is incomplete:
   relay the error and stop.
3. **The audio gate on that MP4:**

   ```bash
   python3 "$MV/aqc_gate.py" "<MP4 from the summary>" --cleaned
   ```

   `--cleaned` because this MP4 came from the cleaned file of step 03. On a
   cleaned file the gate's advice is about the next recording, never "run
   audio-enhance again", which could not help.

Relay the gate's first lines: its verdict ("Sound check: OK to continue." or
"Sound check: STOP ...") and any advice. The table below them is detail; it has
no verdict of its own in gate mode. Exit 0 = continue (warnings are advice: the level spread and
the noise floor often warn on a tight cut, and that is fine). Exit 2 = loudness
or true peak failed: stop, say which, and do not go on to 05. Exit 3 = the gate
could not find its checks in the result: stop and report it as a plugin fault;
never treat it as a pass. Run the gate on the finished cut only, never on the
uncut cleaned file: there the retake pauses and the floor after noise removal
make other checks fail that the cut does not have.

`set 04 done --output "<MP4 from the summary>"`.

### 05 Review the cut

A "you" step: notify, then tell the user to watch `1 WATCH - final video
(C).mp4` once, start to end, and to say "looks good" or name what to change
("bring back the sentence about Kant", "cut the second example").

- Changes: `reopen 04`, then fix the named block decisions in `cuts.json` and
  run `build_package.py` again with the same arguments (never redo the
  transcription), then the audio gate, then come back to 05.
- Approved: `set 05 done`.

### 06 Text cards or slides

Ask one question: **"Does this lecture have a slide deck you want on screen?"**

- **Yes** → run `video-with-slides` on the finished cut (`1 WATCH - final video
  (C).mp4`) with the deck. Its output has the cut's sound and length, so it
  becomes the video the user assembles. `set 06 done --choice path=slides
  --output "<cut name>-with-slides.mp4"`.
- **No** → run `text-treatments` with the cut video as `--footage`. It writes
  the cards from the transcript, shows the wording first, renders, and checks one
  card over the footage. `set 06 done --choice path=text-cards --output
  "<video folder>/text-cards/text-cards-imovie-green.mov"` (add the alpha file
  as a second `--output` when it was rendered).
- The user wants neither: `set 06 skipped`.

### 07 Assemble

A "you" step. Notify, then give the hand-off in plain words:

- **With text cards, in iMovie:** import the cut MP4 and
  `text-cards-imovie-green.mov`; for each card, select its range (times in
  `text-cards-card-times.txt`), drag it above the main video, and set the
  overlay to **Green/Blue Screen** with the playhead on a plain green frame.
  In Final Cut, Premiere or Resolve, use `text-cards-alpha.mov` on the track
  above instead; it needs no keying.
- **With slides:** the `-with-slides.mp4` already is the video; import it and
  add anything else they want.
- Then: export the finished video into the video folder (in iMovie: File >
  Share > File) and say "done".

Never guess the export: the newest video in the folder is often a file the
plugin wrote. If the user names the file, use it. Otherwise list the folder and
ask which file they exported:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/captions-and-description/scripts/find_export.py" "<video folder>"
```

Check the chosen file with `ffprobe`, and `set 07 done --output "<final export>"`.
Every later step takes the export from step 07's output in the status file.

### 08 Title, opening and thumbnail

Run `first-impression` on the final export or the beat sheet. Then a "you"
step: notify, and tell the user to make the thumbnail in Canva or any image app
from the picked poster-frame idea, and to use the picked title on the course
page. `set 08 done --output "<video folder>/first-impression.html"` once they
say it is done (or `skipped` if they do not want a thumbnail).

### 09 Captions and description

Run `captions-and-description` on the **final export from 07**, never the raw
take or the cut MP4 (the captions must match the video students see). **Name
the file to it explicitly**: read the path from step 07's output in the status
file and pass it as the input, so the skill does not search the folder. Then the
audio gate on the same file:

```bash
python3 "$MV/aqc_gate.py" "<final export>" --cleaned
```

`--cleaned` because the export was assembled from the cleaned cut of step 04.

Exit 2 means the export lost loudness or clips: tell the user, and suggest
re-exporting from the editor without volume changes. Exit 3 is a plugin fault:
stop and report it. `set 09 done --output
"<folder>/captions.srt" --output "<folder>/course-page-description.txt"`.

### 10 Publish

A "you" step. **The plugin never publishes anything.** Tell the user which
three files go to the course site: the final export, `captions.srt` (upload it
as the caption track, not as a download), and the text of
`course-page-description.txt`. `set 10 done` when they say so.

### 11 Short clips

Ask whether they want short clips for announcements or the course homepage. If
yes, run `perfect-clips` on the final export (upright for phones, or wide for a
course page; the skill asks). Upright clips are cut from the speaker cut, not the
export: perfect-clips finds that cut in the video folder by itself, so a text
card burned into the export is never sliced in half by the upright crop. Wide
clips use the export as it is. `set 11 done --output "<clips package folder>"`.
If no, `set 11 skipped` and also skip 12–14.

### 12, 13, 14 Pick, polish, publish the clips

"You" steps, one at a time: pick the best clips (12), polish them in iMovie or
any editor (13), upload them by hand (14). `set NN done` after each.

## A step that is yours

At every "you" step, in this order:

1. `set <step> waiting-for-you`.
2. Send the notification:
   ```bash
   bash "$MV/notify.sh" "Step <NN>: <what to do, 3-6 words>" "<the file to use>"
   ```
3. Tell the user exactly: what to do, which file to use (full name, and the
   folder), and how to come back: **"When you are done, say 'continue', or run
   /teaching-video:make-video."**
4. Stop. Do not start the next step in the same turn.

When the user comes back, run `show` and continue at the waiting step: confirm
it is done (check the file it should have produced), mark it `done`, and go on.

## Prompts to remember

- `/teaching-video:make-video` - start a new video, or continue the last one.
- "Continue my video." / "Where was I?" - shows the 14 steps and picks up.
- "Start a new lecture video about <topic>."
- "Go back to the cut." - reopens step 04.
- "Skip the text cards." / "This lecture has slides." - steers step 06.
