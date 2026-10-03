#!/usr/bin/env python3
"""Turn word timestamps into captions.srt, transcript.txt and an outline.

Caption rules (checked again at the end; any break is printed and exits 1):
  - at most 2 lines per cue, at most 42 characters per line
  - a word timed longer than 1.2 s is cut back to 1.2 s (Parakeet stretches
    the last word before a pause across the pause)
  - 1 to 7 seconds per cue (a cue shorter than 1 s is extended into the
    silence after it, never into the next cue)
  - a cue never spans a pause: a gap of 0.7 s or more between two words
    starts a new cue
  - a cue ends at a sentence end once it holds 20+ characters, and at a
    comma once it holds 40+

Usage:
    python3 make_captions.py <words.json> --outdir <video folder>
        [--outline <file>]

<words.json> is segments[].words[] as `transcribe --words` writes it.
Writes captions.srt and transcript.txt into --outdir. --outline writes a
paragraph list with start times, for choosing the key points of the
description. Stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path

LINE = 42
MAX_CHARS = 2 * LINE
MAX_DUR = 7.0
MIN_DUR = 1.0
PAUSE = 0.7          # a gap this long ends a cue
PARA_PAUSE = 1.2     # a sentence end followed by this long a gap ends a paragraph
PARA_SENTENCES = 5   # or a paragraph this long
MAX_WORD = 1.2       # Parakeet can stretch the last word before a pause
                     # across the whole pause; such a word is cut back to
                     # this length, keeping its start


def load_words(path):
    data = json.load(open(path))
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            text = w.get("word", "").strip()
            if text:
                s, e = float(w["start"]), float(w["end"])
                words.append({"t": text, "s": s, "e": min(e, s + MAX_WORD)})
    words.sort(key=lambda w: w["s"])
    return words


def ends_sentence(text):
    return text.rstrip('"\')]').endswith((".", "?", "!"))


def build_cues(words):
    cues, cur = [], []
    for i, w in enumerate(words):
        if cur:
            text = " ".join(x["t"] for x in cur + [w])
            gap = w["s"] - cur[-1]["e"]
            if (gap >= PAUSE or not fits(text)
                    or w["e"] - cur[0]["s"] > MAX_DUR):
                cues.append(cur)
                cur = []
        cur.append(w)
        joined = " ".join(x["t"] for x in cur)
        if ((ends_sentence(w["t"]) and len(joined) >= 20)
                or (w["t"].endswith(",") and len(joined) >= 40)):
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)

    out = []
    for n, c in enumerate(cues):
        start, end = c[0]["s"], c[-1]["e"]
        nxt = cues[n + 1][0]["s"] if n + 1 < len(cues) else end + MIN_DUR
        if end - start < MIN_DUR:
            end = min(start + MIN_DUR, nxt - 0.05)
        end = max(end, c[-1]["e"])
        out.append({"start": start, "end": end,
                    "text": " ".join(x["t"] for x in c)})
    return out


def fits(text):
    return len(text) <= MAX_CHARS and all(len(l) <= LINE for l in wrap(text))


def wrap(text):
    if len(text) <= LINE:
        return [text]
    words = text.split(" ")
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        score = (max(len(a), len(b)) > LINE, abs(len(a) - len(b)))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


def stamp(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def clock(t):
    m, s = divmod(int(t), 60)
    return "%d:%02d" % (m, s)


def paragraphs(words):
    paras, cur, sentences = [], [], 0
    for i, w in enumerate(words):
        cur.append(w)
        if ends_sentence(w["t"]):
            sentences += 1
            gap = words[i + 1]["s"] - w["e"] if i + 1 < len(words) else 99
            if gap >= PARA_PAUSE or sentences >= PARA_SENTENCES:
                paras.append(cur)
                cur, sentences = [], 0
    if cur:
        paras.append(cur)
    return paras


def check(cues):
    problems = []
    for n, c in enumerate(cues, 1):
        lines = wrap(c["text"])
        dur = c["end"] - c["start"]
        if len(lines) > 2 or any(len(l) > LINE for l in lines):
            problems.append("cue %d: lines too long: %r" % (n, lines))
        if dur > MAX_DUR + 0.01:
            problems.append("cue %d: %.2f s is longer than %.0f s" % (n, dur, MAX_DUR))
        if n < len(cues) and c["end"] > cues[n]["start"]:
            problems.append("cue %d overlaps the next cue" % n)
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--outline")
    a = ap.parse_args()
    words = load_words(a.words)
    if not words:
        sys.exit("ERROR: no words in %s" % a.words)
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    cues = build_cues(words)
    with open(out / "captions.srt", "w", encoding="utf-8") as f:
        for n, c in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (
                n, stamp(c["start"]), stamp(c["end"]), "\n".join(wrap(c["text"]))))

    paras = paragraphs(words)
    with open(out / "transcript.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(" ".join(w["t"] for w in p) for p in paras) + "\n")

    if a.outline:
        with open(a.outline, "w", encoding="utf-8") as f:
            for p in paras:
                text = " ".join(w["t"] for w in p)
                f.write("[%s] %s\n" % (clock(p[0]["s"]), text))

    problems = check(cues)
    short = sum(1 for c in cues if c["end"] - c["start"] < MIN_DUR - 0.01)
    print(json.dumps({"words": len(words), "cues": len(cues),
                      "paragraphs": len(paras), "cues_under_1s": short,
                      "length": clock(words[-1]["e"]), "problems": problems}))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
