#!/usr/bin/env python3
"""Propose when each slide comes on screen, from the transcript and the slide text.

Two commands:

    python3 match_slides.py propose --slides slides.json --words transcript.json \
        --out timing.json [--duration SECONDS]
    python3 match_slides.py table --timing timing.json --words transcript.json \
        --slides slides.json

`propose` writes a first timing.json and prints the timing table.
`table` prints the table again after timing.json was edited by hand.

How the proposal works. The transcript is cut into short spoken units (a
sentence, or about 12 s at most). Each unit is scored against every slide by
the words they share, weighted so that a word on only one slide counts most
and a word on every slide counts least. A dynamic-programming pass then picks
one slide per unit, moving forward through the deck: staying on a slide is
free, advancing costs a little, skipping slides costs more, going back is not
allowed. A slide change goes where the chosen slide changes.

The proposal is a draft. It cannot hear "let me go back to the table", see a
picture-only slide, or know that the opening minute should show the speaker
alone. That is the model's pass and the user's check, which the skill file
describes. Each row of the table carries the words spoken at the change and
a confidence, so both can be judged quickly.

The transcript is the `segments[].words[]` JSON that the plugin's
`transcribe --words` writes. Stdlib only.
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

UNIT_MAX = 12.0     # seconds: a longer sentence is split at its widest pause
UNIT_GAP = 0.7      # seconds: a pause this long inside a sentence may split it
ADVANCE = 0.35      # cost of moving to the next slide
SKIP = 0.6          # extra cost for each slide jumped over
GAP_WARN = 20.0     # seconds without a word: report it

# Function words in English and German, the languages the plugin's users
# mostly lecture in. Words of 1-2 letters are dropped anyway.
STOP = set("""
the and for are but not you your yours with this that these those there their
they them then than what when where which who whom why how was were been being
have has had having does did doing done can could should would will shall may
might must from into onto over under about above below after before again
also just only very really more most much many some such each every both any
all one two three our ours out off its it's i'm i've we're you're that's
don't doesn't didn't can't won't isn't aren't let's here now well yes yeah okay
like get got gonna want going say said see seen know think thing things way
lot kind sort mean actually basically right so too because while if or as at
by in on of to up an a is be do go me my we us he she him her his
der die das den dem des ein eine einen einem einer eines und oder aber nicht
mit von zu zum zur auf aus bei für fur ist sind war waren wird werden hat
haben hatte ich du er sie es wir ihr ihnen sich auch noch nur schon so wie
was wenn dann dass daß als also mal doch denn hier jetzt ganz sehr mehr man
""".split())


def norm_tokens(text):
    text = unicodedata.normalize("NFKC", text).lower()
    out = []
    for tok in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text):
        if len(tok) < 3 or tok in STOP:
            continue
        out.append(stem(tok))
    return out


def stem(tok):
    """A crude suffix strip, enough to match 'policies' with 'policy'."""
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""),
                     ("s", ""), ("en", ""), ("er", "")):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: len(tok) - len(suf)] + rep
    return tok


def load_words(path):
    data = json.loads(Path(path).read_text())
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            text = w.get("word", "")
            if text.strip():
                words.append((float(w["start"]), float(w["end"]), text))
    words.sort()
    return words


def units_from(words):
    """Cut the word stream into short spoken units."""
    units, cur = [], []

    def flush():
        if cur:
            units.append(cur[:])
            del cur[:]

    for i, w in enumerate(words):
        if cur:
            gap = w[0] - cur[-1][1]
            ends_sentence = cur[-1][2].rstrip().endswith((".", "?", "!"))
            too_long = w[1] - cur[0][0] > UNIT_MAX
            if ends_sentence or gap >= 2.0 or (too_long and gap >= 0.25) \
                    or (w[1] - cur[0][0] > UNIT_MAX * 1.6):
                flush()
            elif gap >= UNIT_GAP and w[1] - cur[0][0] > UNIT_MAX / 2:
                flush()
        cur.append(w)
    flush()
    out = []
    for u in units:
        text = "".join(w[2] for w in u).strip()
        out.append({"start": u[0][0], "end": u[-1][1], "text": text,
                    "tokens": set(norm_tokens(text))})
    return out


def slide_tokens(slides):
    toks = []
    for p in slides["pages"]:
        toks.append(set(norm_tokens(p.get("text", "") + "\n" + p.get("notes", ""))))
    n = len(toks)
    df = {}
    for s in toks:
        for t in s:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1.0) / (d + 0.5)) for t, d in df.items()}
    return toks, idf


def emissions(units, toks, idf):
    """Score of each unit against each slide, scaled to 0..1 per unit."""
    em = []
    for u in units:
        row = []
        for s in toks:
            shared = u["tokens"] & s
            score = sum(idf[t] for t in shared)
            row.append(score / math.sqrt(len(u["tokens"]) + 1.0))
        top = max(row) if row else 0.0
        em.append([r / top if top > 0 else 0.0 for r in row])
    return em


def viterbi(em, n):
    """Best forward-only path of slides through the units."""
    neg = float("-inf")
    T = len(em)
    best = [[neg] * n for _ in range(T)]
    back = [[0] * n for _ in range(T)]
    for k in range(n):
        best[0][k] = em[0][k] - (ADVANCE + SKIP * (k - 1) if k > 0 else 0.0)
    for t in range(1, T):
        # Running max over earlier slides, each charged for its jump size.
        for k in range(n):
            b, arg = best[t - 1][k], k
            for j in range(k):
                d = k - j
                c = best[t - 1][j] - ADVANCE - SKIP * (d - 1)
                if c > b:
                    b, arg = c, j
            best[t][k] = b + em[t][k]
            back[t][k] = arg
    k = max(range(n), key=lambda i: best[T - 1][i])
    path = [k]
    for t in range(T - 1, 0, -1):
        k = back[t][k]
        path.append(k)
    return settle(path[::-1], em)


def settle(path, em):
    """Move each slide change later, to the first unit that points at it.

    The path is indifferent to where a change falls among units that share
    no words with either slide ("So, let's move on."), and it breaks such
    ties early. A lecturer usually finishes the old point first, so the
    units that do not favour the new slide stay with the old one.
    """
    path = path[:]
    i = 1
    while i < len(path):
        if path[i] != path[i - 1]:
            old, new = path[i - 1], path[i]
            j = i
            while j < len(path) and path[j] == new and em[j][new] <= em[j][old]:
                j += 1
            if j < len(path) and path[j] == new:
                for m in range(i, j):
                    path[m] = old
                i = j
        i += 1
    return path


def fmt(t):
    m, s = divmod(max(t, 0.0), 60)
    return "%d:%04.1f" % (m, s)


def spoken_at(words, t, n=14):
    """The first few words spoken from time t on."""
    after = [w for w in words if w[1] > t][:n]
    return "".join(w[2] for w in after).strip()


def print_table(timing, slides, words):
    pages = {p["n"]: p for p in slides["pages"]}
    segs = timing["segments"]
    print("%-4s %-9s %-8s %-6s %-34s %s" % ("#", "starts", "shows", "conf",
                                           "slide title", "spoken at the change"))
    for i, s in enumerate(segs, 1):
        if "slide" in s:
            shows = "slide %d" % s["slide"]
            title = pages.get(s["slide"], {}).get("title", "")[:34]
        else:
            shows, title = s.get("show", "?"), "(speaker, full frame)"
        lay = s.get("layout")
        if lay:
            shows += "*"
        conf = s.get("confidence", "")
        print("%-4d %-9s %-8s %-6s %-34s %s" % (
            i, fmt(s["start"]), shows, conf, title,
            spoken_at(words, s["start"])[:70]))
    used = {s["slide"] for s in segs if "slide" in s}
    missing = [n for n in sorted(pages) if n not in used]
    if missing:
        print("\nNot shown at all: slide(s) %s" % ", ".join(map(str, missing)))
    if any(s.get("layout") for s in segs):
        print("* = this segment overrides the layout (%s by default)" %
              timing.get("layout", "side-by-side"))


def cmd_propose(a):
    slides = json.loads(Path(a.slides).read_text())
    words = load_words(a.words)
    if not words:
        sys.exit("ERROR: the transcript has no words.")
    n = len(slides["pages"])
    units = units_from(words)
    toks, idf = slide_tokens(slides)
    em = emissions(units, toks, idf)
    path = viterbi(em, n)

    segs = []
    run_start = 0
    for i in range(1, len(units) + 1):
        if i == len(units) or path[i] != path[run_start]:
            k = path[run_start]
            run = range(run_start, i)
            mean = sum(em[j][k] for j in run) / len(run)
            # Confidence: did the first unit on the new slide point at it?
            first = em[run_start][k]
            conf = "high" if first >= 0.99 and mean >= 0.5 else \
                   "mid" if mean >= 0.35 else "low"
            start = units[run_start]["start"]
            if segs:
                # Change in the pause before the first word of the new slide,
                # a quarter of a second early, never before the last word ends.
                prev_end = units[run_start - 1]["end"]
                start = max(prev_end, start - 0.25)
            segs.append({"start": round(start, 3), "slide": k + 1,
                         "confidence": conf})
            run_start = i
    segs[0]["start"] = 0.0

    timing = {
        "_comment": "Edit freely: each segment runs from its start to the next "
                    "segment's start. A segment shows {\"slide\": N} or "
                    "{\"show\": \"speaker\"}; an optional \"layout\" overrides "
                    "the default for that segment only.",
        "layout": "side-by-side",
        "speaker_side": "right",
        "speaker_x": None,
        "background": None,
        "segments": segs,
    }
    if a.duration:
        timing["duration"] = a.duration
    Path(a.out).write_text(json.dumps(timing, indent=1, ensure_ascii=False))

    print_table(timing, slides, words)

    gaps = [(words[i - 1][1], words[i][0]) for i in range(1, len(words))
            if words[i][0] - words[i - 1][1] >= GAP_WARN]
    if gaps:
        print("\nNo words for %d stretch(es) over %d s: %s. If the speaker "
              "talks there, the transcript dropped it; a slide change inside "
              "is invisible to the matcher." % (
                  len(gaps), GAP_WARN,
                  ", ".join("%s-%s" % (fmt(x), fmt(y)) for x, y in gaps)))
    if a.duration and a.duration - words[-1][1] > GAP_WARN:
        print("\nThe last word ends at %s but the video runs to %s." % (
            fmt(words[-1][1]), fmt(a.duration)))

    # Hints for the model's pass: a unit that matches an earlier slide much
    # better than the one the path chose may be a return to that slide.
    hints = []
    for j, u in enumerate(units):
        k = path[j]
        for e in range(k):
            if em[j][e] >= 0.99 and em[j][k] <= 0.3 and len(u["tokens"]) >= 4:
                hints.append("%s  sounds like slide %d (on slide %d): %s" % (
                    fmt(u["start"]), e + 1, k + 1, u["text"][:80]))
                break
    if hints:
        print("\nPossible returns to an earlier slide (check, do not assume):")
        for h in hints[:12]:
            print("  " + h)


def cmd_table(a):
    timing = json.loads(Path(a.timing).read_text())
    slides = json.loads(Path(a.slides).read_text())
    words = load_words(a.words)
    segs = timing.get("segments", [])
    bad = [i + 1 for i in range(1, len(segs))
           if segs[i]["start"] <= segs[i - 1]["start"]]
    if bad:
        print("WARNING: segment(s) %s start no later than the one before." %
              ", ".join(map(str, bad)))
    print_table(timing, slides, words)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--slides", required=True)
    p.add_argument("--words", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--duration", type=float, default=None,
                   help="Video length in seconds, for the end-of-video check")
    t = sub.add_parser("table")
    t.add_argument("--timing", required=True)
    t.add_argument("--words", required=True)
    t.add_argument("--slides", required=True)
    a = ap.parse_args()
    cmd_propose(a) if a.cmd == "propose" else cmd_table(a)


if __name__ == "__main__":
    main()
