# teaching-video

A free Claude Code plugin for educational videos with talking-head footage:
one person on camera, explaining. You draft the lecture and film it. Claude
does the editing work that used to take three or four times the length of
the video.

## What it does

The plugin follows one workflow, from a beat sheet to a finished video, in
14 steps.

**You make it**

1. You and Claude draft a beat sheet: bullet points per section, never a
   word-for-word script.
2. You film. Restarts are fine; the cut catches them.
3. Claude cleans the sound: noise removal, EQ, compression, and a steady
   loudness.
4. Claude cuts the retakes, false starts, ums and pauses, and hands you one
   finished video file.
5. You watch the cut once and send back any changes.

**You finish it**

6. Claude makes animated text cards from your own words: a title, step
   cards, a pull quote, a lower third, an end card. If your lecture has a
   slide deck, Claude puts the slides beside you instead, timed to what you
   say (`video-with-slides`).
7. You put the cut and the cards together in iMovie, or any video editor.
8. You make a thumbnail in Canva or any image app. Claude suggests the
   title, the thumbnail idea and the opening as one promise.
9. Claude writes the captions file, a full transcript and a description
   for your course page.
10. You upload the video to your course site.

**You reuse it**

11. Claude finds the moments that stand on their own and cuts them into
    short clips with captions.
12. You keep the best ones.
13. You polish them in your editor.
14. You post them on your course site.

Everything runs on your own Mac. Your footage stays on your computer; Claude works from the transcript text.

You do not need a script. A recording is enough. If you filmed from a
script, Claude also checks that every planned line made it into the cut.

## What you need

- A Mac with Apple Silicon (M1 or later) and macOS 14 (Sonoma) or later
- About 8 GB of free disk space for the tools
- [Claude Code](https://claude.com/claude-code)
- A paid Claude plan: Pro or Max. The free plan does not include Claude
  Code. The step that cuts the retakes needs a strong model (Sonnet at high
  effort, or Opus), and both paid plans include it.

## Install

In Claude Code, type these two commands:

```
/plugin marketplace add ai-augmented-scholar/teaching-video
/plugin install teaching-video@teaching-video
```

Then run setup once on each computer:

```
/teaching-video:setup
```

Setup checks your Mac first and stops with a plain message if the plugin
cannot run on it. Then it installs what is missing: Homebrew (you paste one
command it gives you, because Homebrew asks for your Mac password), ffmpeg,
Node and uv, then the Parakeet transcription model, DeepFilterNet for noise
removal, and the renderer for text cards (about 500 MB). The tools go into a
private folder inside the plugin, so your own Python stays as it is. Setup
asks before every large download. It also asks where your videos live, which
editor you use, and the three questions below. It ends with a 10-second test
clip that runs through sound cleanup, transcription, one cut and a sound
check, with a pass or fail for each step.

The first transcription downloads the speech model (about 2.5 GB), so the
first test takes a few minutes. Running setup again is safe: it checks what is
already in place and skips it.

## Three questions on first use

Before your first video, Claude asks three questions about your filming
setup and your look, and saves the answers.

1. **Where can text sit?** Is part of your frame empty, such as the wall
   beside you? Describe it, share a screenshot, or let Claude take
   frames from your recording. With no free area, the text goes into lower
   thirds along the bottom of the frame.
2. **Is that area dark enough for white text?** Claude measures it. On a
   light background, the white text gets a dark grey plate behind it.
3. **Which font?** The default is Inter, which comes with the plugin. Name
   another font and Claude checks that your Mac has it.

Each later video starts with one line: same filming setup as last time?

## Prompts to remember

- `/teaching-video:make-video` runs the whole workflow in order. It stops
  and sends a Mac notification whenever a step is yours, and it picks up
  where you left off after a break.
- `/teaching-video:setup` runs once per computer.
- `/teaching-video:beatsheet` drafts a beat sheet for a lecture on any topic.

Plain sentences work too:

- "Clean up the sound on this recording."
- "Cut the retakes out of this take."
- "Make text cards from this transcript."
- "Put my slides next to me in this video."
- "Make short clips from this lecture."
- "Is this audio good enough to publish?"

## What it does not do

- It does not publish to your course site. Steps 10 and 14 are yours.
- It does not run on Windows or on an Intel Mac.
- It runs in Claude Code only, not in the other Claude apps.

## License and credits

MIT. See [LICENSE](LICENSE). The plugin passes on work by Vic Laranja,
Shane Hummus and Hardik Pandya; [CREDITS.md](CREDITS.md) names them and the
licenses of the tools it installs.

## Questions and feedback

Write to The AI-Augmented Scholar at aiaugmentedscholar@gmail.com.
