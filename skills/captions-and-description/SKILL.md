---
name: captions-and-description
description: Make the captions, a readable transcript and a course-page description for a finished educational video with talking-head footage. Works from the final video the user exported from iMovie or any editor, never from the raw recording. Transcribes locally with Parakeet, recovers speech that a single pass drops, and writes captions.srt, transcript.txt and course-page-description.txt into the video's folder. Use when the user has a final edit and asks for captions, subtitles, a transcript, or a description for the course site, or runs /video-teach-plugin:captions-and-description.
---

# Captions and description

$ARGUMENTS

This is step 09 of the workflow. The user has assembled the video in iMovie or any other editor and exported it. This skill turns that export into three files for the course site:

| File | What it is |
|---|---|
| `captions.srt` | The caption track. Course sites and video tools accept an `.srt` file as captions. |
| `transcript.txt` | The full text in paragraphs, for students who read rather than watch, and for accessibility. |
| `course-page-description.txt` | A short description for the course page: what the student will learn, key points with times, terms and readings the video names, and the length. |

It does not upload anything. The user posts the video and these files on the course site by hand.

## Settings

Read `${CLAUDE_PLUGIN_DATA}/config.json` if it exists, and use `videos_root` to find the video's folder (numbered folders, `NN-slug`). Without the file, use `~/Movies/teaching-videos` and tell the user once that `/video-teach-plugin:setup` saves their settings.

Every command below passes the plugin's data folder as `TV_DATA`, so the scripts find the tools that setup installed.

## Step 1: Find the final video

The input must be the **final edit**: the file the user exported from their editor, with the cuts, text cards and anything else they added. Captions made from the raw recording or from the perfect-cuts MP4 do not match the final video if the user changed anything after the cut.

- **If the user or `make-video` names a file, use it.** Do not second-guess a named file.
- **Otherwise never guess.** "The newest video in the folder" is often a file the plugin wrote on the way to the export: the cleaned-audio take, the perfect-cuts MP4, a text-card render, the slides video, a short clip. List the folder with the script and ask:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/captions-and-description/scripts/find_export.py" "<video folder>"
  ```

  It prints every video file with its size, length and modified time, and labels the ones the plugin wrote (`raw take`, `cleaned audio`, `perfect-cuts cut`, `text cards`, `slides video`, `short clip`, `working file`). Show the user that list and ask which file is the video they exported. The `perfect-cuts cut` or the `slides video` is the right file only if the user changed nothing after it; ask, do not assume.
- If the list has no file the plugin did not write, ask the user to export the final video from their editor first, or to name the file.

Check the file with `ffprobe` (duration, an audio stream present). Tell the user the file and its length in one line before you continue.

If `captions.srt`, `transcript.txt` or `course-page-description.txt` already exists in the folder, ask before replacing it.

## Step 2: Transcribe, and recover dropped speech

The working files go in a hidden folder inside the video's folder: `<video folder>/.captions-work/<stem>/`, where `<stem>` is the video's file name without its extension. If there is no video folder (a loose file), use `${CLAUDE_PLUGIN_DATA}/work/captions/<stem>/`. Never use `/tmp`: the folder holds a full transcript of the user's voice, and it belongs with the video, where the user can see it and delete it. Write the full path into every command; a shell variable does not carry over between commands.

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/captions-and-description/scripts/caption_words.py" "<final video>" --workdir "<video folder>/.captions-work/<stem>" --out "<video folder>/.captions-work/<stem>/words.json"
```

The script runs one Parakeet pass, maps speech from the waveform, and measures every stretch of speech. Parakeet drops whole sentences on noisy audio, even in a 3-minute clip. Two kinds of stretch count as dropped speech: an **empty** one (no words, within 5 dB of the speaker's level, so not a breath), and a **sparse** one (longer than 2 seconds, at speech level, but with fewer than 40% of the speaker's median words per second: Parakeet kept the first words and dropped the rest). When it finds either, the script transcribes the video again in windows of about 20 seconds (`perfect-cuts/scripts/transcribe_windows.py`) and keeps the pass with more words.

It prints one line of JSON. Read it:

- `words_pass1` and `words_final`: tell the user both numbers when they differ ("the first pass missed N words; the second pass recovered them").
- `empty_pass1` and `sparse_pass1`: how many stretches of each kind the first pass found.
- `still_dropped`: stretches that are still empty or sparse after the second pass (each has a `kind`). If the list is not empty, tell the user the times (m:ss) and that the captions may miss words there. Never invent the missing words.

Transcription is Parakeet only. Never fall back to another speech model.

## Step 3: Write the captions and the transcript

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/captions-and-description/scripts/make_captions.py" "<video folder>/.captions-work/<stem>/words.json" --outdir "<video folder>" --outline "<video folder>/.captions-work/<stem>/outline.txt"
```

The script builds the cues by rule and checks them before it exits: at most 2 lines of 42 characters, at most 7 seconds per cue, at least 1 second where the pause after allows it, a new cue at every pause of 0.7 seconds or more, and breaks at sentence ends and commas. It exits 1 and lists the problem if any cue breaks a rule. Fix the cause in the words file or report it; never hand-edit the timings.

## Step 4: Correct the spelling of names and terms

Parakeet spells unfamiliar names and terms by sound. Read `transcript.txt` against the video's beat sheet (`beat-sheet.html` in the same folder) if there is one, and against what the user tells you.

- Correct the spelling of names, technical terms and titles of works, in both `captions.srt` and `transcript.txt`, the same way everywhere.
- Change words only. Never change a timing line, merge cues or split cues.
- Do not tidy the speaker's grammar. Captions show what was said.
- List every correction for the user: "Rousso → Rousseau (6 places)".

## Step 5: Write the course-page description

Read `outline.txt` (each paragraph with its start time) and `transcript.txt`. If the folder holds `first-impression.html`, use its picked title. Write `course-page-description.txt` in plain text, for students:

```
<Title>

<2–3 sentences: what the student will understand or be able to do after watching, and who it is for.>

Key points
<m:ss>  <point>
<m:ss>  <point>
<m:ss>  <point>

Terms and readings
<term or reading the video names, one per line>

Length: about <N> minutes. Captions and a full transcript are available.
```

- 3 to 5 key points. Each time comes from `outline.txt` or the captions, never from a guess.
- Name only terms, people and readings the video actually says. If the user wants a reading listed that the video does not name, they add it.
- Write it plainly: concrete words, short sentences, no hype, no "dive into", "unlock" or "game-changer", no rhetorical questions.
- Where a fact is missing (a reading's full reference, a week number), write `[FILL IN: what is needed]` instead of inventing it.
- Leave out "Terms and readings" when the video names none.

## Step 6 (only if asked): A caption track in a second language

When the user asks for captions in another language, translate `captions.srt` cue by cue into `captions.<language code>.srt` (for example `captions.de.srt`). Keep every number and timing line exactly as it is, keep each cue to 2 lines of 42 characters, and keep names as spoken. Tell the user that a native speaker should read it before students see it.

## Step 7: Hand off

Tell the user, in this order:

1. Where the three files are.
2. How to use them: upload the video to the course site, then add `captions.srt` as the caption track in the site's video tool; post `transcript.txt` beside the video; paste the description into the course page.
3. The word counts from Step 2, any `still_dropped` times, and the spelling corrections from Step 4.

Tell the user they can delete `<video folder>/.captions-work/` once they are happy with the captions; it holds a full transcript of their voice and nothing the course site needs. (It is hidden in the Finder; press Command-Shift-Period to show it.)
