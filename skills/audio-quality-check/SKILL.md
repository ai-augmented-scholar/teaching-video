---
name: audio-quality-check
description: >
  Run a six-point quality check on the audio of an educational talking-head
  video (or any spoken-word recording, audio or video file) and report
  pass/warn/fail per check with a recommended fix. Measures integrated loudness
  (LUFS), true peak, background noise floor, long silences, level consistency,
  and clarity (signal-to-noise, sample rate, DC offset). Everything runs
  locally with ffmpeg: no upload, no API key, no cost. Use after a recording
  session to catch a bad mic setup, after audio-enhance to confirm it hit its
  targets, or before the finished video goes to students. Works with footage
  from any camera and for any video editor (iMovie, or any editor). Triggers on
  "check this audio", "is this good enough to publish", "analyze this
  recording", "what is wrong with my audio", "check my mic".
allowed-tools:
  - Bash
  - Read
  - Glob
---

# Audio Quality Check

Diagnostic only. **This skill never modifies a file.** It measures, judges, and
tells the user what to fix. The fixing is `/teaching-video:audio-enhance`'s job.

$ARGUMENTS

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/audio-quality-check/scripts/analyze.py" "<input>" [options]
```

`<input>` is an audio file, a video file, or a folder (every audio and video
file inside is analyzed). Multiple inputs are allowed. The script needs only
the macOS system `python3` (3.9 or newer, standard library) plus `ffmpeg` and
`ffprobe`; it finds Homebrew's copies even when they are not on PATH. If ffmpeg
is missing, tell the user to run `/teaching-video:setup`.

| Option | Effect |
|---|---|
| `--json` | Machine-readable output, including every raw measurement |
| `--quiet` | One verdict line per file, nothing else |
| `--no-verdict` | The table without its VERDICT line, for a caller that prints its own verdict (make-video's audio gate) |
| `--target-lufs <n>` | Loudness target, default `-16` |
| `--ceiling-dbtp <n>` | True-peak ceiling, default `-1.5` |

Exit code: `0` all pass, `1` at least one warn, `2` at least one fail. Use it in
a shell condition; do not re-parse the text.

**Report the table to the user as the script prints it.** Do not summarize the
six checks into prose, and do not drop the passing rows — a row that passed is
the evidence that the check ran.

## The six checks

| # | Check | `id` | Pass | Warn | Fail |
|---|---|---|---|---|---|
| 1 | Integrated loudness | `loudness` | within 1.5 LU of target | within 3.0 LU | outside 3.0 LU |
| 2 | True peak | `true_peak` | at or below ceiling | ceiling to 0 dBTP | 0 dBTP or above |
| 3 | Noise floor | `noise_floor` | −60 dBFS or lower | −60 to −50 | above −50 |
| 4 | Long silences | `silences` | none over 2 s | 1–3 | 4 or more |
| 5 | Level consistency | `level_consistency` | 8 dB spread or less | 8–13 dB | over 13 dB |
| 6 | Clarity | `clarity` | SNR 40 dB+, 44.1 kHz+, no DC offset | SNR 30–40 dB | SNR under 30 dB, or under 44.1 kHz |

**Every check in the `--json` output carries a stable `id`** (the column above).
Other scripts match on the `id`, never on the printed name: `make-video`'s
audio gate stops the workflow only on a `loudness` or `true_peak` fail, and it
stops with an error when either `id` is missing. So a check's printed name may
change; its `id` may not, unless `make-video/scripts/aqc_gate.py` changes with it.
The gate also rewrites the advice per `id` for a file that is already cleaned
(it never says "run audio-enhance" there), so a new check needs a line in its
`cleaned_advice()` too.

The defaults match the `audio-enhance` delivery spec (−16 LUFS, −1.5 dBTP
true-peak ceiling). A noise floor around −60 dBFS is the reference for a clean
spoken-word recording. Change the target with the flags, never by editing the
script.

**A raw take is expected to warn or fail.** Loudness, peak and noise are what
`audio-enhance` fixes, so judge a raw recording for what it says about the room
and the mic, and judge the enhanced file for whether it is ready.

## How the measurements are taken

Five ffmpeg passes per file, no temporary files written:

1. `ffprobe` — codec, sample rate, channels, bit depth, duration.
2. `ebur128=peak=true` — integrated loudness, loudness range, true peak.
3. `astats` over the whole file — peak level, DC offset, RMS trough.
4. `asetnsamples` + `astats` with reset — RMS per 0.05 s window.
5. `silencedetect` — gaps at or under −45 dBFS lasting 2 s or more.

**The noise floor is the 5th percentile of the 0.05 s windows.** The window
length matters and is not arbitrary: a short window falls inside the gaps
between words, which is the only place room noise stands alone. Measured
against fixtures with a known injected floor, 0.05 s windows land within about
1 dB of the truth, while 0.25 s windows miss by 20 dB — at that length every
window still contains speech. Do not lengthen `FLOOR_WINDOW_SAMPLES`.

**Level consistency uses 0.25 s blocks**, built by averaging five short windows
in the power domain. A block that short would read syllable-to-syllable
variation instead of delivery.

**Digital silence is filtered out before every statistic.** A window at −inf
dBFS is an edit artifact — a gate, a splice, or padding — not room tone.
Counting it would drag the floor to −120 dBFS and the level spread to nonsense.
The fraction of gated windows is reported as `gated_fraction` in the JSON.

## What each failure means

| Check fails | Cause | Fix |
|---|---|---|
| Loudness | normalized at the wrong point in the chain | Run `/teaching-video:audio-enhance`; it normalizes last, then limits |
| True peak | no limiter, or the limiter sits before the gain | Run `/teaching-video:audio-enhance`; its last stage is a true-peak limiter |
| Noise floor | room, fan, AC, computer, or mic gain too high | `/teaching-video:audio-enhance` runs DeepFilterNet; better still, fix the room |
| Long silences | dead air left in the take | `/teaching-video:perfect-cuts` removes it |
| Level consistency | moving toward and away from the mic | Hold a fixed mic distance; `audio-enhance` compresses before it normalizes |
| Clarity | too little voice over too much room | Raise gain, lower noise, record at 48 kHz |

## Scope

This skill answers "is the recording technically clean enough to publish."
It does not measure musical qualities such as frequency balance, stereo width,
mono compatibility, or tonal profile.
