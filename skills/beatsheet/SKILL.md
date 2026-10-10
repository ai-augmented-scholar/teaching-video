---
name: beatsheet
description: Write a beat sheet for an educational video with talking-head footage, such as a recorded lecture or a short explainer for a course. A beat sheet is brief bullet points per beat, never a word-for-word script, and it ends with a list of every screen insert and graphic to make before the edit. Saves a self-contained HTML page, beat-sheet.html, in the video's numbered folder and opens it in the browser; optionally mirrors it to Notion. Use when the user asks for a beat sheet, an outline to film from, a plan for a lecture video, or runs /video-teach-plugin:beatsheet.
---

# beatsheet

Write a beat sheet for one educational video with talking-head footage. The user reads it on set, between takes, and turns each bullet into their own words. Save it as an HTML page in the video's folder and open it.

**A beat sheet is never a script.** Scripted lines read wooden on camera. Every beat is a short bullet that carries the content; the user supplies the wording while filming. This holds for every section, the hook included, even when the user films from a script of their own.

## 1. Read the settings

Read `${CLAUDE_PLUGIN_DATA}/config.json` if it exists. The keys this skill uses:

- `videos_root`: the folder that holds one numbered folder per video. Default when missing: `~/Movies/teaching-videos`.
- `signoff`: a closing line the user says at the end of every video. Empty or missing means no sign-off.
- `notion.enabled` and `notion.parent_page_id`: the optional Notion mirror (step 7).

If the file does not exist, use the defaults and say in one line that `/video-teach-plugin:setup` saves these settings.

## 2. Find or make the video folder

Video folders are named `NN-slug` under `videos_root`: a two-digit number, then a short kebab-case slug of the title (`03-enlightenment-vs-renaissance`).

- If the user names an existing video (by number, slug or title), use that folder. If two folders match, list them and ask.
- If this is a new video, list `videos_root`, take the next free number, and create the folder. Create `videos_root` itself if it is missing.

If the folder already holds a `beat-sheet.html` with real content, ask before replacing it.

## 3. Ask only what is missing

Collect these four facts. Take what the user already said from the conversation; ask in one message for the rest.

1. **Topic** and the one point the viewer should leave with.
2. **Audience**, in words: "first-year students in an introductory survey", "graduate seminar", "colleagues at a workshop". Never a course number.
3. **Target length** in minutes.
4. **Script**: does the user film from notes, a rough script, or an exact script? Record the answer on the sheet; the cutting step later asks the same question. If the user has a script or notes, read them and build the beats from them, still as bullets.

Ask for the material the beats need, too: readings, slides, the user's notes, the examples they want to use. Never invent a fact, a date, a quotation or a number. Where one is missing, write a shoot note `[Check: …]` and keep going.

## 4. Build the beats

Structure for a lecture video:

- **Hook** (the first 30–60 seconds): the question, puzzle or situation the viewer recognizes, and what the video answers.
- **Part 1 … Part N**: one section per idea, in teaching order. Each section label carries its timing (`Part 2 · 3:00–5:30`); each heading carries the content (`Reason, not rebirth`). Size the parts to the target length; a 10-minute video usually has 3–4 parts.
- **Close**: the one point again, in a new form, and what to do or read next. Then the sign-off from the config, verbatim, if there is one. No sign-off otherwise.

Inside each section:

- **Beats** are bullets. Each one is a short statement of content the user can say in their own words.
- **Stage directions** sit in square brackets and describe the shot: `[Medium shot. Direct to camera.]`, `[Hold up the book.]`.
- **Shoot notes** are notes to the user, not beats: a screen insert to record, a graphic to make, a fact to check before filming. Give each insert or graphic an ID (`S1` for a screen insert or still, `G1` for a graphic, `B1` for B-roll, `C1` for a fact to check) and use the same ID in the assets table.

Enough beats to fill the target length at speaking pace. Count beats, not words: one beat is about 15–20 seconds of speech, so 3–4 beats per minute of video is a full sheet.

### A beat states the content, never the beat's job

The user reads a beat on set and turns it into speech in one pass. A bullet that describes what the beat is *for* makes them stop and decode it, and the content is not there to recover.

- Cut stage-management verbs: *say it here*, *give the number early*, *name it on camera*, *point back to*, *say it plainly*, *worth saying on camera*, *the beat for this section is*.
- Cut labels that name a beat's role instead of its content. "The contrast that makes the difference clear" says nothing a person can speak. "Renaissance scholars looked back to ancient texts; Enlightenment writers looked forward to progress" says it.
- Cut the reason a beat exists. A reason, if it must survive, is a shoot note, not a beat.
- **The test:** strike every word about the beat and read what is left. If a speakable statement remains, the bullet is right. If nothing remains, it was a description; rewrite it as the thing to say.

Shoot notes, stage directions and asset rows are exempt: those are instructions on purpose.

### Voice

Check every bullet against these before saving:

- No business jargon: *dive into, leverage, navigate, unpack, game-changer, moving forward*.
- No throat-clearing openers: *Here's the thing, The truth is, Let me be clear*.
- No emphasis crutches: *Full stop, Let that sink in, Make no mistake*.
- No vague declaratives: *The implications are significant, The stakes are high*.
- No "Not X. Y." contrasts; state Y directly.
- Adverbs sparingly: *really, just, literally, genuinely, honestly, simply*.
- Concrete over abstract: a named example, a date, a place, a text.

## 5. Production assets

End the sheet with the production-assets table: one row per item that has to exist before the edit. Every insert or graphic named in a shoot note gets a row, with its ID, its kind (screen insert, graphic, still, B-roll, fact to check), the section it belongs to, and what to make: what to record and roughly how long, what to hide in a screen recording (names, emails, student data), what a graphic shows. The table is the complete list; nothing appears in a beat that is missing here.

## 6. Write the page and open it

Copy `${CLAUDE_PLUGIN_ROOT}/skills/beatsheet/template/beat-sheet-template.html` to `<video folder>/beat-sheet.html`, then fill it:

- Set `--video-no` in the template slot to the folder's two-digit number. The badge and the footer read it from there; never type the number anywhere else.
- Replace every `{{...}}` placeholder. Copy one `<section class="part">` per section and one `<div class="beat">` per beat; delete the example blocks you do not use.
- Beat bullets go in `<li>`; a shoot note goes inside its beat as `<span class="note"><b>S1</b> …</span>`; a stage direction as `<p class="dir">[…]</p>`.
- Delete the `.signoff` paragraph when there is no sign-off.
- Leave the type sizes alone. The sheet is read at arm's length on set.

Check that no `{{` is left in the file. Then open it: `open "<video folder>/beat-sheet.html"`.

## 7. Optional: mirror to Notion

Only when `notion.enabled` is true in the config **and** a Notion tool that creates pages is available in this session (the Notion connector). Otherwise skip this step and say in one line where the HTML page is.

When both hold, create one page under `notion.parent_page_id`, titled `Video NN Beat Sheet: <title>`, with a plain mirror of the sheet: each section as a heading, stage directions as italic paragraphs, beats as bullets with their shoot notes inline in square brackets, the sign-off, then the assets as one bullet each. If a page with that title already exists there, replace its content instead of making a second page. The HTML page stays the main copy; add a first line to the Notion page naming its path.

Tip for users without Notion: Notion's free education plan is enough for this.

## 8. Report

Tell the user, briefly:

- where the page is, and that it is open;
- the section list with timings;
- the production-assets list, repeated as short bullets, so they see what to record or make without opening the page;
- any `[Check: …]` notes they must settle before filming;
- the Notion page, if one was written.
