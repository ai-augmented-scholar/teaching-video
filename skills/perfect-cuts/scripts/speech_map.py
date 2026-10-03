#!/usr/bin/env python3
"""Build a speech map for a talking-head clip: waveform-accurate speech blocks
with the transcript words that fall inside each block.

Usage:
    python3 speech_map.py <video_path> <transcript_json_path> [--out map.json]

<transcript_json_path> is the word-timestamp JSON (segments[].words[]) written by the bundled
`transcribe` command (Parakeet TDT 0.6b v3):

    transcribe <video> --words <transcript_json_path> --quiet

Output JSON:
{
  "source": "/abs/path.mp4", "fps": 30.0, "width": 1920, "height": 1080,
  "duration": 106.93, "samplerate": 48000,
  "blocks": [
    {"i": 0, "start": 16.387, "end": 19.418, "onset": 16.3878,
     "text": "Canada has joined the AI arms race,",
     "gap_after": 1.30, "words": [[16.31, 16.62, "Canada"], ...]},
    {"i": 1, ..., "split": "filler"},
    ...
  ]
}

start/end come from the sensitive pass (-38dB) — full speech envelope incl. tails.
onset comes from the hard pass (-30dB) — first frame of actual voice, breath-proof.
  A block marked "split" ("filler" or "repeat") was cut out of running speech,
  so no -30dB rise opens it: its onset is the split point, or a rise within
  0.15 s of it, and never later than the start of its first word.
gap_after is the silence between this block and the next (seconds).
words are the transcript words assigned to the block: [start, end, text].
"""
import json
import re
import subprocess
import sys
import os

# Find ffmpeg even under a bare PATH: the plugin's own environment
# (TV_DATA, passed in by the skill), then Homebrew, then the inherited PATH.
_extra = [os.path.join(os.environ.get("TV_DATA", ""), "venv", "bin"),
          "/opt/homebrew/bin", "/usr/local/bin"]
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

MIN_SILENCE = "0.25"     # silences shorter than this stay inside a block

# LOCKED defaults — hand-tuned and frame-verified on reference footage.
# These are absolute and proven; they are ALWAYS tried first.
IN_DB = "-30dB"          # starts: ignores breaths/mouth noise
OUT_DB = "-38dB"         # ends: catches soft word tails

# Rescue calibration (used ONLY when the locked defaults produce a degenerate
# map — see is_degenerate). Thresholds anchor to the speaker's level (p90 of
# windowed RMS). Offsets reproduce -30/-38 on the reference footage.
IN_OFFSET = 14
OUT_OFFSET = 22
FLOOR_GUARD = 10


def flag(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def calibrate(path):
    """Measure windowed RMS (0.1s @ 48k) and derive thresholds from the
    speaker's level. Returns (in_db, out_db) as strings like '-30dB'."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    subprocess.run(
        ["ffmpeg", "-nostdin", "-i", path,
         "-af", f"asetnsamples=n=4800,astats=metadata=1:reset=1,"
                f"ametadata=print:key=lavfi.astats.Overall.RMS_level:file={tmp}",
         "-f", "null", "-"], capture_output=True)
    vals = sorted(float(m) for m in
                  re.findall(r"RMS_level=(-?[\d.]+)", open(tmp).read()))
    if len(vals) < 20:
        return "-30dB", "-38dB"  # too short to calibrate; reference defaults
    speech = vals[int(len(vals) * 0.90)]
    floor = vals[int(len(vals) * 0.10)]
    out_db = max(speech - OUT_OFFSET, floor + FLOOR_GUARD)
    in_db = max(speech - IN_OFFSET, out_db + 6)
    return f"{in_db:.0f}dB", f"{out_db:.0f}dB"


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,r_frame_rate,width,height,sample_rate:format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    meta = {"duration": float(info["format"]["duration"])}
    for s in info["streams"]:
        if s["codec_type"] == "video":
            # FIRST video stream only. A camera or editor .mov can carry a
            # timecode track that also reports codec_type=video, at
            # r_frame_rate 90000/1; letting the loop run on overwrites fps
            # with 90000 and breaks every frame calculation downstream.
            if "fps" in meta:
                continue
            num, den = s["r_frame_rate"].split("/")
            meta["fps"] = int(num) / int(den)
            meta["width"], meta["height"] = s["width"], s["height"]
        elif s["codec_type"] == "audio":
            meta["samplerate"] = int(s.get("sample_rate", 48000))
    return meta


def silences(path, noise):
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", path,
         "-af", f"silencedetect=noise={noise}:d={MIN_SILENCE}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", out)]
    return starts, ends


def is_degenerate(blocks, duration):
    """True when a block map can't be real speech structure: everything is one
    giant block (thresholds below the noise floor) or speech is shredded into
    confetti (thresholds above the speaker's level)."""
    if not blocks:
        return True
    speech = sum(e - s for s, e in blocks)
    if speech > 0.95 * duration:        # silences never detected
        return True
    tiny = sum(1 for s, e in blocks if e - s < 0.4)
    return len(blocks) > 10 and tiny / len(blocks) > 0.7   # fragment confetti


def assign_words(words, blocks):
    """Partition the transcript across blocks: every word lands in exactly one.

    A fixed time window around each block loses words, because a transcript
    starts a word up to ~0.3s before the waveform onset it belongs to — wider than any
    safe window, since widening it far enough to catch those also steals words
    from the neighbouring block. So match on OVERLAP instead: each word goes to
    the block its [start, end] span overlaps most. A word sitting entirely
    inside a silence (timestamp padding, or a near-inaudible word) goes to the
    nearest block, preferring the FOLLOWING one on a tie — transcripts pad
    starts early, so such a word is usually the beginning of the speech to come.

    Returns one joined string per block, in block order.
    """
    return [" ".join(w[2] for w in b) for b in assign_word_lists(words, blocks)]


def assign_word_lists(words, blocks):
    """The same overlap partition as assign_words, but each block keeps its
    (start, end, text) word tuples, so later steps can use word timings."""
    buckets = [[] for _ in blocks]
    if not blocks:
        return []
    for start, end, text in words:
        if not text:
            continue
        best, best_overlap = None, 0.0
        for i, (bs, be) in enumerate(blocks):
            overlap = min(end, be) - max(start, bs)
            if overlap > best_overlap:
                best, best_overlap = i, overlap
        if best is None:
            # No overlap with any block. Fall back to distance; the -i in the
            # key makes the later block win a tie.
            best = min(range(len(blocks)),
                       key=lambda i: (max(blocks[i][0] - end,
                                          start - blocks[i][1], 0.0), -i))
        buckets[best].append((start, end, text))
    return buckets


REPEAT_MIN_WORDS = 4     # a repeated run this long inside one block = two takes
SNAP_RADIUS = 0.15       # search ±this many seconds for the quietest 10 ms


def norm(text):
    return re.sub(r"[^\w']", "", text.lower())


def find_repeat(block_words):
    """Index of the first word where a second delivery starts, or None.

    Two takes of one line can sit in one block when the speaker restarts
    without a pause of MIN_SILENCE (0.25 s): the waveform never splits them,
    and the editorial pass cannot keep only one. A run of REPEAT_MIN_WORDS
    normalised words that occurs twice, the second copy starting after the
    first copy's start word plus REPEAT_MIN_WORDS, marks the restart."""
    toks = [norm(w[2]) for w in block_words]
    k = REPEAT_MIN_WORDS
    for j in range(k, len(toks) - k + 1):
        run = toks[j:j + k]
        if not all(run) or len(set(run)) < 2:  # skip a stammer of one word
            continue
        for i in range(0, j - k + 1):
            if toks[i:i + k] == run:
                # The restart often opens with a word or two that the first
                # copy's match leaves out ("…each color? So | in this video…"
                # when the first take's "So" sits in the block before). If a
                # sentence ends 1-2 words before j, split right after it.
                for back in (1, 2):
                    p = j - back - 1
                    if p >= i + k - 1 and re.search(r"[.?!]$", block_words[p][2]):
                        return j - back
                return j
    return None


def quietest_point(path, t0, lo, hi):
    """Centre of the quietest 10 ms within [t0 - SNAP_RADIUS, t0 + SNAP_RADIUS],
    clamped to [lo, hi]. Falls back to t0 when the audio cannot be read."""
    import array
    import math
    a, b = max(lo, t0 - SNAP_RADIUS), min(hi, t0 + SNAP_RADIUS)
    if b - a < 0.02:
        return t0
    sr = 16000
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{a:.4f}", "-t",
         f"{b - a:.4f}", "-i", path, "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"], capture_output=True).stdout
    pcm = array.array("h", raw[: len(raw) // 2 * 2])
    win = sr // 100  # 10 ms
    if len(pcm) < win:
        return t0
    best_i, best_rms = 0, None
    for i in range(0, len(pcm) - win + 1, win // 2):
        rms = math.sqrt(sum(x * x for x in pcm[i:i + win]) / win)
        if best_rms is None or rms < best_rms:
            best_i, best_rms = i, rms
    return a + (best_i + win / 2) / sr


def split_repeats(path, blocks, words, split_origin):
    """Split every block that holds two deliveries of the same words.

    The split goes at the word boundary where the repeat starts, snapped to
    the quietest 10 ms near it. Loops, so a block with three takes splits
    twice. Blocks without a repeat are untouched. The second half's start is
    recorded in split_origin as "repeat" (see split_onset)."""
    for _ in range(50):  # guard against a pathological loop
        lists = assign_word_lists(words, blocks)
        done = True
        for i, bw in enumerate(lists):
            j = find_repeat(bw)
            if j is None:
                continue
            bs, be = blocks[i]
            prev_end, next_start = bw[j - 1][1], bw[j][0]
            # Parakeet pads word ends, so the previous word's end can run past
            # the next word's start; then the start is the better boundary.
            t0 = (prev_end + next_start) / 2 if prev_end < next_start else next_start
            cut = quietest_point(path, t0, bs + 0.05, be - 0.05)
            if not (bs + 0.05 < cut < be - 0.05):
                continue
            first = " ".join(w[2] for w in bw[:j])
            second = " ".join(w[2] for w in bw[j:])
            print(f"split: two takes in one block at {cut:.3f}s "
                  f"({bs:.2f}-{be:.2f}): \"{first[:50]}\" | \"{second[:50]}\"")
            blocks[i:i + 1] = [[bs, cut], [cut, be]]
            split_origin[skey(cut)] = "repeat"
            done = False
            break
        if done:
            return blocks
    return blocks


def skey(t):
    """Dictionary key for a block start time."""
    return round(t, 6)


def split_onset(bs, be, onsets, block_words):
    """Onset of a block that starts at a SPLIT point, not at a silence.

    A block cut out of running speech (after a filler word, or at the restart
    of a repeated take) has no -30 dB rise at its start: the voice is already
    above the threshold. The ordinary rule, "first -30 dB rise inside the
    block", then finds the next rise somewhere mid-block, and the editorial
    in-point skips every word before it. So a split block takes the first
    rise between its start and the start of its first word, otherwise the
    split point itself, and never an onset later than that first word.

    The search must reach the first word, not stop a fixed 0.15 s after the
    split: a filler's end is set 0.15 s early, so the filler's tail and the
    pause after it can lie between the split and the real rise. A 0.15 s
    window then fell back to the split point and put about 0.6 s of "uh" tail
    and pause back into the cut."""
    starts = [w[0] for w in block_words if bs - 0.05 <= w[0] < be]
    near = [o for o in onsets if bs - 0.05 <= o <= min([be] + starts)]
    onset = near[0] if near else bs
    if starts and onset > max(bs, min(starts)):
        onset = bs
    return onset


def speech_blocks(sil_starts, sil_ends, duration):
    """Invert the silence list into speech intervals."""
    blocks, cursor = [], 0.0
    events = sorted([(t, "s") for t in sil_starts] + [(t, "e") for t in sil_ends])
    in_silence = False
    for t, kind in events:
        if kind == "s" and not in_silence:
            if t - cursor > 0.05:
                blocks.append([cursor, t])
            in_silence = True
        elif kind == "e":
            cursor = t
            in_silence = False
    if not in_silence and duration - cursor > 0.05:
        blocks.append([cursor, duration])
    return blocks


def main():
    video, transcript_json = sys.argv[1], sys.argv[2]
    out_path = flag("--out", "speech_map.json")
    in_db = flag("--in-db", IN_DB)
    out_db = flag("--out-db", OUT_DB)

    meta = ffprobe(video)
    sens_starts, sens_ends = silences(video, out_db)
    hard_starts, hard_ends = silences(video, in_db)
    blocks = speech_blocks(sens_starts, sens_ends, meta["duration"])

    if is_degenerate(blocks, meta["duration"]) and "--in-db" not in sys.argv:
        in_db, out_db = calibrate(video)
        print(f"locked thresholds produced a degenerate map — "
              f"rescue calibration: in {in_db} / out {out_db}")
        sens_starts, sens_ends = silences(video, out_db)
        hard_starts, hard_ends = silences(video, in_db)
        blocks = speech_blocks(sens_starts, sens_ends, meta["duration"])
    else:
        print(f"thresholds: in {in_db} / out {out_db} (locked defaults)")
    onsets = sorted(hard_ends)  # -30dB silence_end == voice onset

    words = []
    filler_times = []
    FILLER_WORDS = {"ähm", "ämm", "ahm", "äh", "um", "uh", "uhm", "ah", "er"}
    
    tx = json.load(open(transcript_json, encoding="utf-8"))
    for seg in tx.get("segments", []):
        for w in seg.get("words", []):
            if "start" in w:
                start = w["start"]
                end = max(w.get("end", start), start)
                text = w.get("word", "").strip()
                words.append((start, end, text))
                
                clean_text = text.lower().strip(".,?!;:-")
                if clean_text in FILLER_WORDS:
                    # Parakeet pads word ends; compensate slightly to avoid cutting next word
                    filler_times.append((start, max(start + 0.1, end - 0.15), text))
                    
    words.sort()
    filler_times.sort()

    # Isolate filler words into their own blocks so they can be cut.
    # Every sub-block that starts anywhere but at the original block's start
    # (which a silence opened) starts at a SPLIT point: record it, because
    # its onset follows split_onset(), not the ordinary -30 dB rule.
    split_origin = {}
    split_blocks = []
    for b_start, b_end in blocks:
        current_start = b_start
        for r_start, r_end, _ in filler_times:
            if r_end <= current_start:
                continue
            if r_start >= b_end:
                break

            split_start = max(current_start, r_start)
            split_end = min(b_end, r_end)

            if split_start > current_start:
                split_blocks.append([current_start, split_start])

            split_blocks.append([split_start, split_end])
            current_start = split_end

        if current_start < b_end:
            split_blocks.append([current_start, b_end])
    for bs, be in split_blocks:
        if bs != next(b0 for b0, b1 in blocks if b0 <= bs < b1):
            split_origin[skey(bs)] = "filler"

    # Reassign blocks and filter tiny fragments
    blocks = [b for b in split_blocks if b[1] - b[0] > 0.05]

    # Two takes of one line with no 0.25 s pause between them share a block;
    # split them so the editorial pass can keep only one.
    blocks = split_repeats(video, blocks, words, split_origin)

    texts = assign_words(words, blocks)
    word_lists = assign_word_lists(words, blocks)

    result = []
    for i, (bs, be) in enumerate(blocks):
        origin = split_origin.get(skey(bs))
        if origin:
            onset = split_onset(bs, be, onsets, word_lists[i])
        else:
            # LOCKED: an ordinary block opens at a silence, so its onset is
            # the first -30 dB rise inside it (rule 1).
            onset = next((o for o in onsets if bs - 0.05 <= o <= be), bs)
        text = texts[i]
        gap = round(blocks[i + 1][0] - be, 3) if i + 1 < len(blocks) else None
        entry = {"i": i, "start": round(bs, 4), "end": round(be, 4),
                 "onset": round(onset, 4), "text": text, "gap_after": gap,
                 # Word times let build_package check that no word falls
                 # outside a clip's in/out points, and cut caption text to a
                 # trimmed clip.
                 "words": [[round(ws, 3), round(we, 3), wt]
                           for ws, we, wt in word_lists[i]]}
        if origin:
            entry["split"] = origin
        result.append(entry)

    meta.update({"source": video, "blocks": result})
    json.dump(meta, open(out_path, "w", encoding="utf-8"), indent=1)
    print(f"{len(result)} speech blocks -> {out_path}")
    for b in result:
        print(f"  [{b['i']:2d}] {b['start']:8.2f}-{b['end']:8.2f}  {b['text'][:80]}")


if __name__ == "__main__":
    main()
