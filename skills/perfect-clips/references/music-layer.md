# Music folder (optional layer, off by default)

## Turning it on

No tracks ship with this skill, and the layer stays off until the user
names a folder of their own. Never ask about music in the intake round.
When the user asks for music ("use music from ~/Music/beds", "add a quiet
bed under the clips"), write the folder path into the plugin config
(`${CLAUDE_PLUGIN_DATA}/config.json`, key `music_folder`) — or, when that
config file does not exist yet, as one line into
`${CLAUDE_PLUGIN_DATA}/perfect-clips/music-folder.txt`. The literal value
`disabled` in either place turns the layer off for good.

In the report of a run without music, one line is enough: "No music bed.
To add one, name a folder of tracks you have the rights to."

## Runtime resolution + conventions

doctor.py resolves the folder and prints it as `MUSIC=` / `MUSIC_SOURCE=`,
first hit wins: config `music_folder` → `<PC_HOME>/music-folder.txt` →
`<PC_HOME>/music/` when it holds audio → OFF. With a folder set, its
CONTENTS are the switch: tracks present → beds on; empty → clips ship
music-free, silently.

- **Filenames name the mood family in plain words, first.** The leading
  words are the mood family; whatever follows (a number, a track name)
  is flavor. Mood-matching reads the whole filename. Examples:
  - `upbeat-hip-hop-beat-5-hype-workout.mp3`
  - `lofi-chill-wave-beat-2-late-night-cozy.mp3`
  - `intense-suspense-2-villain-moves.mp3`
  - `sad-emotional-piano-1-sincere-moments.mp3`
  - `relaxed-happy-1-happy-tails.mp3`
- **Formats:** mp3, wav, m4a, ogg, aif.
- **Pre-trim your tracks.** t=0 of the file is where the bed enters — the
  engine lays every track at clip start, no offset logic. Cut intro dead
  air before dropping a track in.
- Mood-matching examples: "upbeat-hip-hop-beat-5-hype-workout.mp3" →
  energetic; "lofi-chill-wave-beat-2-late-night-cozy.mp3" → reflective;
  "intense-suspense-2-villain-moves.mp3" → tense.

## Runtime behavior notes (add_music.py)

- Video is stream-copied — frames and burned captions come out
  bit-identical; only the audio re-encodes.
- A track longer than the clip is cut at clip end; shorter leaves
  silence after — both by design (amix duration=first).

## The source-music gate (why a clip can refuse a bed)

A clip whose source already carries music ships on its own audio — a bed
on top of existing music just clashes. music_gate.py decides per clip, from
measurement: in a clean recording the gaps BETWEEN speech blocks sit near
silence, while a scored recording never drops there. The gate takes the
clip's keep-ranges, finds the inter-speech gaps (speech map blocks),
measures the audio floor in just those gaps, and verdicts on the number:
gap floor louder than -38dB (the boundary law's own out-threshold) →
`bed=skip`. Too little gap time to measure (wall-to-wall speech) → it
falls back to the speech map's rescue-calibration flag, which fires exactly
when muxed music defeated the locked thresholds → `bed=skip`. The verdict
is final either way — never argue with the number, and say in the report
when a clip shipped on its own audio.

A noisy room can trip the same gate (a floor above -38dB with no music in
it). That is the gate working as designed: a bed over room noise sounds
worse, not better. Running `audio-enhance` on the lecture first lowers the
floor.
