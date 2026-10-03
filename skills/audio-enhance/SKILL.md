---
name: audio-enhance
description: >
  Clean up the sound of a recorded lecture or other spoken-word recording, for
  educational videos with talking-head footage. Runs noise removal, a 3-band
  EQ, compression and limiting, and delivers to a measured loudness target
  with a guaranteed true-peak ceiling. Accepts audio OR video files: given a
  video, it hands back a new video file with the cleaned track muxed in, the
  original audio dropped and the picture untouched, ready for iMovie or any
  editor. The whole chain is ONE deterministic script; the model runs it and
  relays its report, and never runs the ffmpeg steps by hand. Use when the
  user asks to clean up, enhance, fix or process the audio of a recording, or
  runs /teaching-video:audio-enhance.
allowed-tools:
  - Bash
  - Read
  - Glob
---

# Audio enhancement

Process one or more audio **or video** files through the full chain:

**Working-level normalize (−15 LUFS) → Noise removal (DeepFilterNet) → 3-band EQ → Compressor (−14 dB, 3:1) → Peak limiter (−6 dB) → Delivery normalize (−16 LUFS) → True-peak ceiling (−1 dBFS) → [video inputs] duration gate → remux onto the untouched video**

**Audio in, audio out. Video in, video out.** Given a video file, the run does not end at a WAV: it ends at a new video file carrying the cleaned track, with the original audio dropped and the video stream stream-copied untouched (Step 10). The source file is never modified in place.

The order is the classic one for a voice chain (gain → noise → EQ → compressor → limiter), with the level stage split in two: one at the front to give the fixed-threshold compressor a consistent signal to work on, one at the back to hit the delivery target.

**The loudness target is set at the END of the chain, and a limiter is the last filter after it.** Do not set the level once at the front and assume it survives — EQ boosts, compressor makeup, and the limiter all change loudness downstream of wherever you set it. See "Why the level stage is split" below; this exact mistake once shipped a finished file at −12.7 LUFS / **+0.8 dBTP**.

$ARGUMENTS

## How to run (this is the whole procedure)

The chain is one script. **Run it; do not reproduce its steps by hand.** Every step below the "Reference" banner documents what the script does and why — it is there so a future edit changes the right number for the right reason, not so a session can improvise the chain.

```bash
TV_DATA="${CLAUDE_PLUGIN_DATA}" python3 "${CLAUDE_PLUGIN_ROOT}/skills/audio-enhance/scripts/audio_enhance.py" \
  "<input>" ["<output>"] [--audio-only] [--alternative] [--target-lufs -16] [--ceiling-dbtp -1.5] [--no-eq] [--json report.json]
```

`TV_DATA` tells the script where the plugin keeps its private tools. Always pass it exactly as written above.

### Requirements

The plugin's setup skill installs everything (`/teaching-video:setup`). If the script prints `MISSING ...` and exits 2, tell the user to run setup; do not install tools by hand from inside this skill.

- **ffmpeg** with the `loudnorm`, `ebur128`, `acompressor`, `alimiter`, `lowshelf`, `highshelf`, `equalizer`, `astats`, `ametadata`, `volumedetect` and `silencedetect` filters. The standard Homebrew build has all of them.
- **DeepFilterNet** in the plugin's private environment. It needs **Python 3.11** — its Rust core (`deepfilterlib`) ships no prebuilt wheels for Python 3.12 or newer — and torch/torchaudio below 2.9, plus `soundfile`. The first run downloads the DeepFilterNet3 model (small) into `~/Library/Caches/DeepFilterNet/`.

The script looks for each tool in this order: `DEEPFILTER_BIN` (deepFilter only, a full path), the plugin's environment (`$TV_DATA/venv/bin`), `~/.local/bin`, then PATH, `/opt/homebrew/bin` and `/usr/local/bin`.

What the script does on its own, with no model decision anywhere:

1. Checks `ffmpeg`, `ffprobe`, `deepFilter` and prints a hint for anything missing (exit 2).
2. Classifies each input as audio or video (cover art in an MP3 is not video). A video with no audio stream is reported and skipped.
3. Runs the full chain: working normalize → measured noise floor → DeepFilterNet → EQ + compressor + peak limiter → delivery normalize → ceiling.
4. Runs the verification: not silent, loudness within ±1 LU of the target and never below −18 LUFS, true peak under the hard catch and never positive, duration within 50 ms of the source.
5. Video inputs: duration gate, remux with `-c:v copy` and the original audio dropped, then the muxed-file checks (two streams, frame count and rate equal, audio start and duration preserved, AAC 48 kHz).
6. Prints the per-file report table on stdout and, with `--json`, writes the same data as JSON. Exit 0 when every file was delivered, 1 when any file failed, 2 when a tool is missing.
7. Cleans up its temp files under `/tmp/audio-enhance/`. On a failure it keeps them and says where; on a duration or mux failure it also keeps the cleaned WAV next to the output as `<stem>_enhanced-UNVERIFIED.wav`, because a missing video is recoverable and a drifted one is not.

**Your job as the model** is small and fixed:

- Pass the user's flags through. Never add `--no-eq` or `--audio-only` on your own — both exist only for an explicit request.
- Relay the report table and every `WARNING:` line. The warnings are the part a human needs: a dynamic working stage, a noisy room, an unmeasured floor, a true peak between the target and the hard catch.
- On `FAILED`, quote the `ERROR:` line and the paths of the kept evidence. Do not retry with a different flag, do not "fix" a duration mismatch with `-shortest`, `apad`, `atrim` or `atempo`, and do not hand over the WAV as if it were the deliverable.
- If the input name contains `_enhanced`, the script warns; tell the user the chain assumes a raw recording and ask for the original camera or recorder file (see "Calibration", below).

**Model and effort do not matter for this skill.** Every parameter is fixed in the script, and every decision inside it is a table lookup. What a small model can get wrong is procedural — skipping the report, retrying with a changed flag — and the list above is short enough to prevent that.

### Changing the chain

Edit `scripts/audio_enhance.py`, not this file alone. The constants at the top of the script (`EQ_CHAIN`, `COMPRESSOR`, `PEAK_LIMIT`, `CEILING_LIMIT`, `WORKING_LUFS`, `DEFAULT_TARGET_LUFS`, …) are the only place a number lives. Then update the matching Reference section here so the reason travels with the value. Test on a short clip before a batch, with `--json` and a look at the table.

## Arguments (passed straight through to the script)

- `<input>` — a single audio file, a single **video** file, or a folder (every audio and video file inside is processed)
- `<output>` — (optional) output file or folder path; if omitted, write next to each input:
  - audio input → same basename with an `_enhanced` suffix, `.wav` extension
  - video input → same basename with an `_enhanced-audio` suffix, **same container extension as the source** (`.mov` in, `.mov` out)
- `--audio-only` — (optional) for a video input, stop after the WAV and skip the remux. Only when the user explicitly wants the bare audio track. Never assume this.
- `--alternative` — (optional) use the alternative preset instead of the standard preset (see below)
- `--target-lufs <value>` — (optional) override the **delivery** loudness target, default `-16`. The recommended band is **−18 to −16 LUFS**. Do not go above −16: louder than that is not more professional, it is aggressive. Do not go below −18: −22 LUFS reads as too quiet for a finished file.
- `--ceiling-dbtp <value>` — (optional) override the true-peak ceiling, default `-1.5`
- `--no-eq` — (optional) skip the 3-band EQ stage. **The EQ is ON by default and stays on unless this flag is explicitly passed.** Never drop it on your own judgement.

## Calibration: where the numbers come from

Files from this chain were measured twice against a listening review. Those two rounds set the current values; treat them as the calibration reference.

**Round one — a delivered file that was too hot.** Measured: 48 kHz mono, −12.7 LUFS integrated ("usable but hot"), loudness range 5.9 LU (good), noise floor in pauses ≈ −60 dBFS (already clean), peak at 0 dBFS with samples at full scale and a true peak of **+0.8 dBTP** (the one real problem). Four rules this skill follows:

1. **No platform mandates a specific LUFS number for this kind of content.** What matters is clear, undistorted audio, no intrusive background noise, and consistent loudness. The −16 LUFS default is a house standard chosen for headroom — `--target-lufs` is safe to move within the band.
2. **The limiter belongs last in the chain**, and **a limiter is not a substitute for setting the mic gain correctly.** See "Before you hit record" below — the durable fix is upstream of this skill.
3. **Never just turn a finished file down.** A file that is both loud *and* peaking has already been heavily level-manipulated, and attenuating it preserves every artifact. **Always re-run from the original camera or recorder file**, never from a previous `_enhanced` output. This chain assumes raw input.
4. **Keep the EQ.** A leaner chain (noise suppression → compressor → limiter, no EQ) is a reasonable default elsewhere, but the delivered file scored well on speech quality with the EQ in, so it stays on by default. The only way it comes out is an explicit `--no-eq`.

**Round two — a test file that was too quiet.** Measured: no clipping, peak ≈ −9.6 dBFS, integrated ≈ **−22 LUFS (too quiet — the one real complaint)**, a reported SNR of 0 dB (almost certainly a bad measurement), and a "fake lossless" 18 kHz cutoff (irrelevant for speech). The verdict: clean and understandable, but **the voice should be louder, denser and more present**. Five rules, all in this chain:

1. **Delivery loudness band is −18 to −16 LUFS.** The default stays at −16, the loud end of that band.
2. **Get the density from compression, not from raw gain.** Set the level, compress properly, then add output gain only if still needed. The compressor threshold is −14 dB (Step 5) for this reason.
3. **Keep the peak limiter at −6 dB** (Step 6). Target peaks in the capture are −12 to −6 dB.
4. **A boosted low shelf plus a scooped midrange can make a deep voice sound thick or dull.** Keep the lows at about 0 to +1.5 dB and dip the mids gently. Step 4 uses +1.5 / −2.5 / +2.6 dB for this reason.
5. **Never chase an audio-analyzer score.** A "fake lossless" verdict, an 18 kHz cutoff, or a 0 dB SNR reading is a diagnostic hint, not a defect. What decides quality is speech intelligibility, noise and room sound, clipping, steady loudness, and the listening impression.

**Judge from the original file, never from a copy downloaded back from a video platform.** Platforms apply their own loudness normalization and compression, so a download tells you about the platform, not about the recording.

## Before you hit record

Record on the Mac with whatever the user already uses (QuickTime, Photo Booth, a camera, a USB recorder). Record clean and let this skill process the file afterwards: offline, the chain measures the actual file and applies exact corrections, and a bad decision is undoable because the raw take is untouched. A recording app that bakes noise suppression, EQ and compression into the file at record time is guessing at levels before a word is spoken, and its decisions cannot be undone.

Exactly one thing cannot be fixed later: **input gain at the microphone.** Once a take is clipped at the converter, the samples are gone. So whatever app is recording, before a real take:

- Watch the input meter while speaking normally — aim for peaks around **−18 to −10 dB**
- Louder, emphatic words should reach about **−6 to −3 dB**, no higher
- Nothing should ever touch the top of the meter
- If the meter is pinned, turn the **mic gain** down (interface knob or macOS input level) — do not compensate later

Everything else — noise, tone, compression, final loudness — this skill handles from the raw file. For a new mic or room, record a raw **30–60 second** test (normal voice, a few deliberately loud moments, one quieter passage), run it through this skill, and read the report before recording a full session.

## Presets

Two presets. Default to **standard**; switch to **alternative** only if the user passes `--alternative` or asks for it after reviewing a test clip.

| Stage | Standard (default) | Alternative |
|---|---|---|
| Working level | Normalize to −15 LUFS | same |
| Noise removal | DeepFilterNet, strength from the measured floor | same |
| 3-band EQ | High +2.6 dB / Mid −2.5 dB / Low +1.5 dB | same |
| Compressor | 3:1 ratio, **−14 dB threshold**, **10 ms attack**, 100 ms release, 0 dB makeup, no sidechain | 3:1 ratio, −14 dB threshold, **1 ms attack**, 100 ms release, 0 dB makeup, no sidechain |
| Peak limiter | −6 dB threshold, 60 ms release, **auto-level off** | same |
| Delivery level | Normalize to −16 LUFS, TP −1.5 dBTP | same |
| True-peak ceiling | −1.0 dBFS hard catch, **auto-level off** | same |

**Two values changed after the second calibration round:** the compressor threshold went from −9.8 dB to −14 dB, and the EQ went from +2.6 / −3.3 / +2.6 dB to +2.6 / −2.5 / +1.5 dB. Both changes serve the same complaint — the voice was not present or dense enough, and a lifted low shelf on a deep voice adds weight instead of presence. An older report that quotes −9.8 dB or +2.6 dB of low shelf is from the previous mapping.

**The attack values:** standard uses 10 ms. The usable range for speech is **5–10 ms**; a 1 ms attack clamps down on consonant transients and is what makes speech read as "squashed." The 1 ms setting survives as the alternative preset only for the rare take that genuinely needs it.

**Why offline beats a live chain here:**

- **Level** is measured, not guessed. A live chain applies a fixed gain boost before anyone speaks; offline, the chain measures the file first and normalizes to LUFS targets, so a gain that clips on one mic and is too quiet on another cannot happen.
- **Noise removal** is DeepFilterNet in both presets — higher quality than real-time suppressors, and CPU load doesn't matter in a batch job.
- **A second level stage plus a final ceiling**: a delivered file needs a measured number, so the chain ends with a measured delivery normalize and a hard ceiling below it.
- **Denoising strength is measured, not fixed**: the chain measures the noise floor first and backs off when the recording is already clean — see Step 3.

### Why the level stage is split

The compressor threshold (−14 dB) is an **absolute** level, not a relative one. Feed it a quiet take and it barely engages; feed it a hot take and it squashes. So the front normalize is not about delivery loudness at all — it exists to put every take at the same working level so the compressor does the same job every time. −15 LUFS at that point is a working number, not the deliverable.

Everything after it changes the loudness again: the EQ adds shelf gain, the compressor's makeup shifts the average, and the limiter moves the peaks. Whatever loudness you set at the front is gone by the end. That is why the delivery normalize has to come last, and why the only thing allowed after it is a limiter that can lower peaks but never raise them.

---

# Reference: what the script does, and why

**Do not run these steps by hand.** They are the script's documentation. Each section names the ffmpeg filter the script uses and the reason for its value.

## Step 1: Prepare input

**First classify the input as audio or video** — this decides whether the run ends at Step 9 (audio) or Step 10 (video):

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_type,duration,nb_frames,r_frame_rate \
  -of default=noprint_wrappers=1 "input.ext"
```

- **No video stream** → audio input. Deliverable is the WAV from Step 9; skip Step 10.
- **A video stream** → video input. The deliverable is a *video* file (Step 10), not the WAV. The WAV is an intermediate. Never hand the user a bare WAV for a video input and call it done.
- **A video stream but no audio stream** → report and stop. There is nothing to enhance.
- A cover-art image stream in an audio file (`.mp3` with embedded artwork) reads as a video stream on some probes. If `codec_type=video` but the codec is `mjpeg`/`png` with no frame rate, treat it as audio.

**Record the source stream durations and start times now** (video input only). The duration gate (Step 10a) compares against the extracted WAV, and the remux (Step 10b) restores the audio's start offset relative to the video.

Then convert the audio to mono 48 kHz WAV. For a video, this extracts the audio track:

```bash
ffmpeg -i input.ext -vn -ar 48000 -ac 1 /tmp/<basename>_48k.wav -y
```

`-vn` is there so a video input can't drag its video stream into the WAV.

## Step 2: Working-level normalization (two-pass)

Sets the consistent input level the fixed-threshold compressor needs. Target is always **−15 LUFS** here regardless of `--target-lufs` — that flag controls the *delivery* target in Step 8, not this one.

ffmpeg's `loudnorm` runs in its two-pass form — measure first, then apply the exact correction — rather than a single-pass estimate.

**2a. Measure:**

```bash
ffmpeg -i /tmp/<basename>_48k.wav -af loudnorm=I=-15:TP=-1.5:LRA=11:print_format=json -f null - 2>&1
```

Parse the trailing JSON block from stderr for `input_i`, `input_tp`, `input_lra`, `input_thresh`, and `target_offset`. `input_i` and `input_tp` are the "before" numbers for the report.

**2b. Apply**, feeding the measured values back in so `loudnorm` makes one precise linear correction:

```bash
ffmpeg -i /tmp/<basename>_48k.wav -af \
  "loudnorm=I=-15:TP=-1.5:LRA=11:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>:linear=true" \
  -ar 48000 /tmp/<basename>_normalized.wav -y
```

**Known ffmpeg quirk — do not drop the `-ar 48000`:** with `linear=true`, `loudnorm` silently upsamples its output to 192 kHz instead of preserving the 48 kHz input. That is the confirmed root cause of an enhanced track that ended up seconds shorter or longer than its source video. The explicit `-ar 48000` on the output pins it, and the script checks the sample rate and duration after every stage.

**`linear=true` is a request, not a guarantee — check whether it held.** When the gain needed to reach −15 LUFS would push the true peak past `TP`, `loudnorm` silently switches to **dynamic** mode and compresses the loudness range instead. It does not say so in the log. A quiet source is where this bites: on one quiet test file (−25.95 LUFS, −4.73 dBTP, LRA 5.60) the stage needed +10.95 dB, could not apply it linearly, and returned −15.71 LUFS at **LRA 3.20** — it had flattened the range by 2.4 LU before the compressor ran.

The script detects it by measuring LRA before and after this stage. If LRA fell, the stage went dynamic. **That is usually acceptable** — it evens out level differences between passages. Report it; do not treat the output as linear. Do **not** try to force linearity with a plain `volume` gain: on that same file a true +10.95 dB linear gain put 76 % of the audio above −6 dBFS and 23 % above 0 dBFS, so the Step 6 limiter would have become a loudness maximizer. A source with a peak-to-loudness ratio near 20 dB cannot reach a −15 LUFS working level linearly, and that is a capture-gain problem, not a chain problem.

## Step 3: Noise removal (DeepFilterNet)

**First measure the noise floor**, so the amount of denoising matches the recording instead of being applied blind. Noise suppression is applied only as hard as the recording needs it; a floor around −60 dBFS needs almost nothing.

The script samples a pause — a stretch with no speech — and reads its level:

```bash
ffmpeg -nostdin -hide_banner -ss <pause_start> -to <pause_end> -i /tmp/<basename>_normalized.wav \
  -af volumedetect -f null - 2>&1 | grep max_volume
```

**A gap-removed cut has no pause to sample.** A file that has been through `perfect-cuts` (or any gap-removal tool) contains no silence at all — `silencedetect` at −38 dB / 0.35 s returns nothing. The script falls back to the quietest short windows instead, which is an upper bound on the floor:

```bash
ffmpeg -i /tmp/<basename>_normalized.wav \
  -af "astats=metadata=1:reset=6,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" \
  -f null - 2>/dev/null | sed -n 's/.*RMS_level=//p' | sort -g | head -8
```

It takes the **median of the 8 quietest windows** as the floor. `reset` counts **frames, not samples**. A value like `reset=24000` never fires, so every line prints the cumulative overall figure and the numbers look implausibly uniform — that is the tell. `reset=6` gives roughly 0.085 s windows. The report says the floor is an upper bound from inter-word gaps, not a measured room tone.

| Measured floor | `--atten-lim` | Rationale |
|---|---|---|
| below −55 dBFS | `12` | already clean; heavy attenuation only costs naturalness |
| −55 to −40 dBFS | `20` | the default |
| above −40 dBFS | `30` | audibly noisy room — and say so in the report |

```bash
deepFilter /tmp/<basename>_normalized.wav \
  --atten-lim <ATTEN> \
  -m DeepFilterNet3 \
  --no-suffix \
  -o /tmp/
```

Report the measured floor and the chosen `--atten-lim` — a floor above −40 dBFS is a room or mic problem this skill can only paper over, and the user should hear about it rather than have it silently scrubbed.

Never add a noise **gate**: gating chops the tails off speech pauses and sounds worse than the noise it removes. A gentle expander is the fallback if anything is ever needed here, not a gate.

Notes:
- Delay compensation is on by default in DeepFilterNet — do not pass `--compensate-delay`, it doesn't exist as a flag.
- `--no-suffix` keeps the output filename identical to the input so the next step can find it.
- If `deepFilter` isn't found, the script prints a hint and exits 2 rather than silently skipping noise removal.
- `deepfilternet` alone is not enough: it needs `torch`, `torchaudio` **and `soundfile`**. Without `soundfile`, torchaudio 2.8 has no audio I/O backend and `deepFilter` exits 1 with `RuntimeError: Couldn't find appropriate backend to handle uri … and format None`.

## Step 4: 3-band EQ

A low shelf, a broad mid dip, and a high shelf at standard vocal crossover points. The low shelf and the mid dip are deliberately soft (+1.5 and −2.5 dB), because lifted lows plus scooped mids make a deep voice sound thick and slightly dull. The high shelf gets the full +2.6 dB, since that band carries presence:

```
lowshelf=f=200:g=1.5,equalizer=f=1000:width_type=o:width=2:g=-2.5,highshelf=f=4000:g=2.6
```

Do not use `equalizer` with `width_type=s` for shelf-like moves — it can produce silent output. Always use `lowshelf`/`highshelf` for the outer bands.

**This stage is part of the default chain — always run it unless `--no-eq` was explicitly passed.** Do not treat a quiet-sounding take or a "cleaner is better" instinct as grounds for skipping it.

## Step 5: Compressor

```
acompressor=threshold=-14dB:ratio=3:attack=<ATTACK>:release=100:makeup=1
```

Where `<ATTACK>` is `10` (standard) or `1` (alternative) — see the preset note above. `makeup=1` is ffmpeg's linear no-change value (0 dB output gain). No sidechain or ducking input is used.

The −14 dB threshold replaced −9.8 dB after the second calibration round. A threshold of about −18 dB is common for a raw mic signal, but this chain has already normalized to −15 LUFS before the compressor, so the same absolute threshold would mean far heavier compression here. At −14 dB the compressor engages on normal speech instead of only on peaks, so the voice reads as denser and more present, and the delivery normalize in Step 8 lifts a steadier signal to the target.

Density comes from this stage, never from raw gain. If a voice still needs more presence, lower this threshold by 1–2 dB at a time and listen; do not raise the ratio, and do not raise `--target-lufs` above −16.

## Step 6: Peak limiter

−6 dB as a linear amplitude value is `0.501` (10^(−6/20)):

```
alimiter=level=disabled:limit=0.501:attack=5:release=60
```

ffmpeg's `alimiter` needs an attack value; 5 ms is its fast default.

**`level=disabled` is mandatory and is the single most important flag in this skill.** ffmpeg's `alimiter` defaults to `level=true`, which auto-normalizes the limited signal *back up to full scale*. With the default, `alimiter` is not a limiter at all — it is a loudness maximizer that pins output to 0 dBTP and undoes every level decision made earlier in the chain. Measured on a 60 s speech excerpt:

| `alimiter=limit=0.501:attack=5:release=60` | Integrated | True peak |
|---|---|---|
| source (no limiter) | −21.4 LUFS | −3.2 dBTP |
| with ffmpeg's default `level=true` | −15.6 LUFS | **+0.0 dBTP** |
| with `level=disabled` | −21.6 LUFS | −6.0 dBTP |

Every `alimiter` instance in this chain carries `level=disabled`. If you ever add another one, it carries it too.

## Step 7: Combined EQ + compressor + limiter pass

Steps 4–6 run in a single ffmpeg call on the denoised output from Step 3:

```bash
ffmpeg -i /tmp/<basename>_denoised.wav \
  -af "lowshelf=f=200:g=1.5,equalizer=f=1000:width_type=o:width=2:g=-2.5,highshelf=f=4000:g=2.6,acompressor=threshold=-14dB:ratio=3:attack=<ATTACK>:release=100:makeup=1,alimiter=level=disabled:limit=0.501:attack=5:release=60" \
  -ar 48000 /tmp/<basename>_processed.wav -y
```

This is an intermediate file, not the deliverable. Its loudness is wherever the EQ and compressor left it.

## Step 8: Delivery normalization + true-peak ceiling (two-pass)

The final level stage. Measure the *processed* file — not the source, not the Step 2 output — and normalize it to the delivery target, then catch anything left over with a hard ceiling.

**8a. Measure:**

```bash
ffmpeg -i /tmp/<basename>_processed.wav -af loudnorm=I=<TARGET_LUFS>:TP=<CEILING_DBTP>:LRA=11:print_format=json -f null - 2>&1
```

**8b. Apply, with the ceiling limiter as the last filter in the chain:**

```bash
ffmpeg -i /tmp/<basename>_processed.wav -af \
  "loudnorm=I=<TARGET_LUFS>:TP=<CEILING_DBTP>:LRA=11:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>:linear=true,alimiter=level=disabled:limit=0.891:attack=5:release=60" \
  -ar 48000 <output>.wav -y
```

`<TARGET_LUFS>` is `-16` by default, or the `--target-lufs` override. `<CEILING_DBTP>` is `-1.5` by default, or `--ceiling-dbtp`.

**The limiter goes after the normalization, not before it.** Normalization applies gain; any gain applied after a ceiling can push peaks straight back through it. `loudnorm`'s `TP` parameter predicts and prevents true-peak overs, and with `linear=true` that prediction is reliable — so `limit=0.891` (−1.0 dBFS) should almost never engage. It is a guarantee, not a sound-shaping stage. If the report shows it engaging hard, something upstream is wrong; investigate rather than lowering it.

## Step 9: Save output

Write the final WAV to the resolved output path (see Arguments).

- **Audio input:** this WAV is the deliverable. Clean up temp files and go to Verification.
- **Video input:** this WAV is an intermediate. Continue to Step 10 — the run is not done. Keep the WAV until Step 10 has passed its duration gate; if the gate fails, the WAV is the evidence.

## Step 10: Remux into the video (video inputs only)

Put the cleaned track back on the original video and **drop the original audio entirely**, under a new filename. The source file is never modified in place.

### 10a. Duration gate — run this BEFORE the mux

The cleaned WAV must be the same length as the track that went in. Muxing a drifted track produces a file that goes out of sync partway through, and that is invisible in an ffprobe summary of the *output*, because the container will happily report the video's duration while the audio ends early.

**Compare against the extracted WAV from Step 1 (`<basename>_48k.wav`), not against the container duration.** On a macOS camera capture (QuickTime Player, Continuity Camera) the container runs longer than both streams, and the audio stream starts tens of ms after the video — 51 and 87 ms on two measured captures. Measured against the container, a chain that had not drifted at all (every intermediate WAV identical to the millisecond) failed twice at 94 ms and 135 ms. The gate's question is "did the chain change the length?", and only the extracted WAV answers it. A second check at extraction time refuses a WAV more than 200 ms away from the source audio stream's declared duration, so a broken extraction cannot hide behind the new reference.

| Difference | Action |
|---|---|
| ≤ 50 ms | **Pass.** Mux. Report the exact delta anyway. |
| > 50 ms | **Hard failure. Do not mux.** |

On a failure, stop and report the two durations and the delta. **Never fix a length mismatch with `-shortest`, `apad`, `atrim`, or an `atempo` stretch.** Those hide the bug and ship a file that drifts against picture. The known cause is the `loudnorm` `linear=true` 192 kHz upsample (Step 2), so check the sample rate on the output of *both* normalize stages first.

### 10b. Mux

```bash
ffmpeg -i "<source video>" -itsoffset <audio start − video start> -i /tmp/<basename>_final.wav \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart \
  "<basename>_enhanced-audio.<source ext>" -y
```

Why each part matters:

- **`-itsoffset` puts the cleaned track back where the original one started.** A WAV carries no timestamps, so an audio stream that began 87 ms after the video in the source would come back 87 ms *early* without it — 2.6 frames at 30 fps, a visible lip-sync error. The script reads `start_time` of both source streams and passes the difference; it omits the flag when the difference is under 1 ms.
- **`-map 0:v:0 -map 1:a:0` is what removes the original audio.** It selects exactly one video stream from the source and exactly one audio stream from the WAV, and nothing else. Do **not** write `-map 0` — that carries every original stream through, so the file ends up with the raw audio track still on it and an editor may well play that one instead of the cleaned one.
- **`-c:v copy` is mandatory.** The video is not re-encoded, so there is no generation loss and no change to resolution, frame rate, frame count, or colour. If ffmpeg refuses to stream-copy into the chosen container, change the container rather than re-encoding the video.
- Keep the **source container extension**. A `.mov` from a Mac capture stays `.mov`. iMovie and the other common editors import `.mov` and `.mp4` alike.
- `-movflags +faststart` is harmless for local editing and helps if the file is ever uploaded.

### 10c. Verify the muxed file

All six must hold, or the file is not deliverable:

1. **Exactly two streams** — one video, one audio. A third stream means the mapping was wrong.
2. **Video frame count and frame rate identical to the source.**
3. **Video stream duration equal to the source video stream** (within 5 ms) — a stream copy cannot change it.
4. **Audio stream duration within 50 ms of the extracted WAV** (`<basename>_48k.wav`) — AAC may add a few ms of padding, nothing more.
5. **Audio starts where the source audio started**, relative to the video, within 25 ms.
6. **Audio codec is AAC at 48 kHz.**

**"Audio duration equals video duration" is deliberately not a check.** A camera capture's own streams differ by tens of ms, and the remux preserves that difference; it does not repair it. The A/V delta is still printed, as information.

---

## Verification

The script runs all three checks on every output file and does not report a file as done until it passes all three.

**1. Not silent:** `mean_volume` below roughly −80 dB is a failure (denoising or filtering wiped the signal).

**2. Loudness and true peak hit the target:**

- Integrated must be within **±1.0 LU** of `<TARGET_LUFS>`, and never below **−18 LUFS**. Below −18 the file is too quiet for a finished video, whatever the flags said.
- True peak: the **hard bar is the −1.0 dBFS ceiling limiter** (the script allows −0.7 dBTP, i.e. 0.3 dB of inter-sample overshoot a sample-peak limiter cannot see), and the peak must never be positive. `<CEILING_DBTP>` (−1.5 by default) is `loudnorm`'s *prediction target*, and the script reports a peak between the target and the hard catch as a **WARNING**, not a failure. A stricter "at or below −1.5" bar would fail outputs the chain cannot guarantee, because the chain's own last filter sits at −1.0.

A positive true peak is a hard failure — do not hand the file over, and check that every `alimiter` in the chain has `level=disabled` before anything else.

**3. Duration matches the source**, so the audio still lines up with the video it came from; the pass bar is the same 50 ms as the Step 10a gate. Any drift means the 192 kHz `loudnorm` quirk got through — check the sample rate on both normalize stages.

**For a video input, all three checks run on the intermediate WAV, and then Step 10's checks run on the muxed video.** A video run is not done until both sets pass. Report the video file as the deliverable, with its absolute path — that is the file that goes into iMovie or any other editor.

## Reporting

The script prints a per-file summary table with the numbers a reviewer would ask for (relay it as-is; `--json` gives the same fields as data):

| Column | Source |
|---|---|
| Input integrated (LUFS) | Step 2a `input_i` |
| Input true peak (dBTP) | Step 2a `input_tp` |
| Noise floor (dBFS) | Step 3 measurement |
| Denoise strength | Step 3 `--atten-lim` |
| Preset | standard / alternative, EQ on/off |
| Target (LUFS) | `<TARGET_LUFS>` |
| **Output integrated (LUFS)** | Verification check 2 |
| **Output true peak (dBTP)** | Verification check 2 |
| Duration match | Verification check 3 (delta in ms, against the source) |
| Deliverable | the WAV path (audio input) or the muxed video path (video input) |

The last three columns are the deliverable spec — always state them explicitly rather than saying the file "sounds fine." Run this skill on one short test file before batch-processing a full recording session.

## Error handling

- Missing `ffmpeg` or `deepFilter`: the script prints a hint and exits 2. Tell the user to run `/teaching-video:setup`; don't guess a workaround.
- Input file not found, or folder contains no audio or video files: report and stop.
- Video input with no audio stream: report and stop (Step 1).
- Duration gate failure on a video input (Step 10a): report both durations and the delta, keep the WAV, and do not produce a video file. A missing video file is a recoverable problem; a silently out-of-sync one is not.
- `-c:v copy` refused for the chosen container: change the container, never re-encode the video to work around it.
- If a file fails at any step, the script reports the error and continues with the remaining files rather than aborting the whole batch.

## Notes

- This chain assumes mono voice recordings (talking head, lecture, narration) — not tuned for music or stereo content. Don't use it on music performances.
- The EQ crossover points in Step 4 are standard vocal values, not a per-file spectral analysis.
- If the voice sounds "squashed," that is usually the attack clamping transients — the standard preset's 10 ms is the gentler setting, so a file processed with `--alternative` (1 ms) is the one to re-run on standard, not the reverse. If it still sounds dull or unclear after the EQ, that's expected — the EQ is a blunt, generic correction. Keep it on rather than reaching for `--no-eq`.
- **The regression this chain exists to prevent:** an early output was delivered at −12.7 LUFS with a **+0.8 dBTP** true peak — too hot, and clipping. Two causes, both fixed: the loudness target was set at the *front* of the chain where the EQ and compressor downstream could undo it, and the limiter ran with ffmpeg's default `level=true`, which pushed everything back to full scale. If a future output is hot again, check those two things first.
- **The −6 dB peak limiter in Step 6 stays at −6 dB.** Target peaks at the microphone are −12 to −6 dB.
- **Do not tune this chain to satisfy an audio analyzer.** Tools that report "Fake Lossless", brick-wall cutoffs at 18 kHz, or an SNR of 0 dB do not decide quality for speech, and an 18 kHz cutoff is inaudible. Judge by intelligibility, noise and room sound, clipping, steady loudness, and listening.

## If something fails

If the script fails and one honest attempt at a fix (for example, running setup again) does not solve it, tell the user plainly what failed, quote the `ERROR:` line, and point them to the feedback address in the plugin's README.
