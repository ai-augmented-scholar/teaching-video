#!/usr/bin/env python3
"""Place text cards on a video's own clock, from the words spoken in it.

Two subcommands:

  place_cards.py words AUDIO_OR_VIDEO --out words.json [--transcribe PATH]
      Word timestamps for a whole file. The audio is cut into windows of about
      20 seconds at pauses, and every window is transcribed with Parakeet in
      one model load. Long files lose whole lines when Parakeet reads them in
      one piece; 20-second windows cut at pauses do not.

  place_cards.py place --cards cards.json --words words.json --out timed.json
                       [--fps 60] [--duration SECONDS] [--timing-json FILE]
      Finds each card's anchor phrase in the words, and sets the card's start,
      its length, and the entry time of each row of a build. Prints a timing
      table for the user to approve.

The card fields this script reads (the renderer ignores them):

  anchor        The words the speaker says when the card should appear.
  at            Optional: about where (seconds, or "m:ss"). Picks between two
                places where the anchor is said.
  itemAnchors   A build (stepList, table): the words that bring in each row.
  until         Optional: the words after which the card leaves.
  fixedDur      true keeps the card's own `dur`.
  overlap       true lets this card share screen time with another card.

Length rules. A teaching video is read, not glanced at:
  - A simple card stays at least 8 seconds, longer when its text needs more
    reading time (2.5 words per second, plus 1.5 seconds).
  - A build stays until its last row has been on screen for at least 4
    seconds (longer for a long row), and never less than 8 seconds in total.
  - `until` makes a card stay until just after those words, but never
    shorter than the two minimums above.
  - Otherwise the card does not leave in the middle of a sentence: it stays to
    the end of the sentence or the next pause, when that comes within 6
    seconds.
  - A card never runs into the next card or past the end of the video. When
    that cuts it short, the table says SHORT.

Shared with the teaching-video plugin's text-treatments skill
(skills/text-treatments/scripts/place_cards.py). Keep the copies identical.

Stdlib only; runs on /usr/bin/python3 (3.9).
"""
import argparse
import difflib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

LEAD = 0.25          # a card starts this long before its anchor word
ITEM_LEAD = 0.1      # a row starts this long before its anchor word
SIMPLE_MIN = 8.0     # minimum seconds on screen, any card
BUILD_HOLD = 4.0     # minimum seconds after the last row of a build enters
WPS = 2.5            # reading speed, words per second
READ_PAD = 1.5       # added to the reading time
SENTENCE_REACH = 6.0 # how far a card may stretch to reach a sentence end
PAUSE = 0.7          # a gap between words this long ends a thought
UNTIL_PAD = 0.6      # a card with `until` leaves this long after the words
GAP = 0.2            # space between one card's end and the next card's start
BUILD_KINDS = {"stepList", "table"}

WINDOW = 20.0        # target window length for transcription
WINDOW_MAX = 40.0    # hard cut when no pause comes
HOMEBREW = "/opt/homebrew/bin"


def die(msg):
    sys.exit("place_cards: " + msg)


# ---------------------------------------------------------------- words

def tool(name):
    for d in (HOMEBREW, "/usr/local/bin"):
        p = Path(d) / name
        if p.is_file():
            return str(p)
    found = shutil.which(name)
    if not found:
        die("%s is missing" % name)
    return found


def find_transcribe(explicit):
    if explicit:
        return Path(explicit).expanduser()
    here = Path(__file__).resolve().parent
    plugin = here.parent.parent.parent / "scripts" / "transcribe"
    if plugin.is_file():
        return plugin
    found = shutil.which("transcribe")
    if found:
        return Path(found)
    die("cannot find the transcribe command (pass --transcribe PATH)")


def to_wav(src, dest):
    """16 kHz mono PCM, the form Parakeet reads without ffmpeg."""
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-i", str(src), "-vn",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
                   check=True)


def wav_seconds(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def pause_points(wav):
    """Middles of the pauses in a WAV, in seconds."""
    proc = subprocess.run(
        [tool("ffmpeg"), "-v", "info", "-i", str(wav), "-af",
         "silencedetect=noise=-40dB:d=0.25", "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = proc.stderr.decode("utf-8", "replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", text)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def windows(total, pauses):
    """Cut [0, total] at the first pause after each WINDOW seconds."""
    cuts, cursor = [0.0], 0.0
    while total - cursor > WINDOW_MAX:
        later = [p for p in pauses if cursor + WINDOW <= p <= cursor + WINDOW_MAX]
        cursor = later[0] if later else cursor + WINDOW_MAX
        cuts.append(cursor)
    cuts.append(total)
    return list(zip(cuts[:-1], cuts[1:]))


def load_transcribe_module(path):
    loader = importlib.machinery.SourceFileLoader("tt_transcribe", str(path))
    spec = importlib.util.spec_from_loader("tt_transcribe", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def words_for(src, transcribe_path, quiet=False):
    """Word timestamps for a whole audio or video file, on its own clock."""
    tr = load_transcribe_module(transcribe_path)
    with tempfile.TemporaryDirectory(prefix="place-cards-") as work:
        work = Path(work)
        wav = work / "all.wav"
        if Path(src).suffix.lower() == ".wav":
            shutil.copyfile(src, wav)
        else:
            to_wav(src, wav)
        total = wav_seconds(wav)
        spans = windows(total, pause_points(wav))
        parts = []
        with wave.open(str(wav)) as w:
            rate, width = w.getframerate(), w.getsampwidth()
            for i, (a, b) in enumerate(spans):
                w.setpos(int(round(a * rate)))
                frames = w.readframes(int(round((b - a) * rate)))
                part = work / ("w%03d.wav" % i)
                with wave.open(str(part), "wb") as o:
                    o.setnchannels(1)
                    o.setsampwidth(width)
                    o.setframerate(rate)
                    o.writeframes(frames)
                parts.append(part)
        if not quiet:
            sys.stderr.write("place_cards: transcribing %.0f s in %d windows\n"
                             % (total, len(parts)))
        out = work / "json"
        out.mkdir()
        results = tr.run_parakeet(tr.find_cli(), parts, out)
        words = []
        for (part, result), (a, _b) in zip(results, spans):
            for w in tr.to_words(result):
                words.append({"word": w["word"].strip(), "start": round(w["start"] + a, 3),
                              "end": round(w["end"] + a, 3)})
    return {"duration": round(total, 3), "words": words}


# ---------------------------------------------------------------- placing

def load_words(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "words" in data:
        raw = data["words"]
    elif isinstance(data, dict) and "segments" in data:
        raw = [w for s in data["segments"] for w in s.get("words", [])]
    elif isinstance(data, list):
        raw = data
    else:
        die("cannot read words from %s" % path)
    duration = data.get("duration") if isinstance(data, dict) else None
    words = []
    for w in raw:
        text = w.get("word", w.get("text", ""))
        words.append({"text": text.strip(), "tok": norm(text),
                      "start": float(w["start"]), "end": float(w["end"])})
    return words, duration


def norm(text):
    t = text.lower().replace("’", "'")
    return re.sub(r"[^0-9a-zÀ-ɏ]+", "", t)


def tokens(phrase):
    return [t for t in (norm(x) for x in phrase.split()) if t]


def seconds(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def find(words, phrase, lo=0.0, hi=None, hint=None):
    """Where a phrase is spoken. Returns (start, end, how, n_matches) or None."""
    want = tokens(phrase)
    if not want:
        return None
    toks = [w["tok"] for w in words]
    n = len(want)
    hits = []
    for i in range(len(toks) - n + 1):
        if toks[i:i + n] == want:
            hits.append((i, i + n - 1, 1.0))
    how = "exact"
    if not hits:
        how = "close"
        target = " ".join(want)
        for size in (n - 1, n, n + 1):
            if size < 1:
                continue
            for i in range(len(toks) - size + 1):
                r = difflib.SequenceMatcher(None, target, " ".join(toks[i:i + size])).ratio()
                if r >= 0.8:
                    hits.append((i, i + size - 1, r))
        # keep the best window around each place
        hits.sort(key=lambda h: -h[2])
        kept = []
        for h in hits:
            if all(abs(h[0] - k[0]) > n for k in kept):
                kept.append(h)
        hits = sorted(kept)
    hits = [h for h in hits if words[h[0]]["start"] >= lo - 0.01
            and (hi is None or words[h[0]]["start"] <= hi)]
    if not hits:
        return None
    if hint is not None:
        best = min(hits, key=lambda h: abs(words[h[0]]["start"] - hint))
    else:
        best = hits[0]
    return (words[best[0]]["start"], words[best[1]]["end"],
            how if how == "exact" else "close %.2f" % best[2], len(hits))


def card_text(card):
    out = []
    for key in ("eyebrow", "headline", "dek", "quote", "attribution", "name",
                "role", "signOff", "cta"):
        if isinstance(card.get(key), str):
            out.append(card[key])
    for item in card.get("items", []) or []:
        out.append(str(item))
    for col in card.get("columns", []) or []:
        out.append(str(col))
    for row in card.get("rows", []) or []:
        if isinstance(row, dict):
            out.extend(str(v) for v in row.values())
        else:
            out.append(str(row))
    return " ".join(out)


def read_time(text):
    return len(text.split()) / WPS + READ_PAD


def row_texts(card):
    if card.get("items"):
        return [str(x) for x in card["items"]]
    rows = card.get("rows") or []
    return [" ".join(str(v) for v in r.values()) if isinstance(r, dict) else str(r)
            for r in rows]


def natural_end(words, t):
    """The end of the sentence or thought running at time t, if close."""
    for i, w in enumerate(words):
        if w["end"] < t:
            continue
        if w["end"] > t + SENTENCE_REACH:
            return None
        nxt = words[i + 1] if i + 1 < len(words) else None
        if re.search(r"[.?!]$", w["text"]) or nxt is None or nxt["start"] - w["end"] >= PAUSE:
            return w["end"] + 0.4
    return None


def label_of(card):
    for key in ("headline", "quote", "name", "signOff", "eyebrow"):
        if card.get(key):
            return str(card[key])
    rows = row_texts(card)
    return rows[0] if rows else ""


def place(cards, words, duration, fps):
    duration = duration or ((words[-1]["end"] + 2.0) if words else 0.0)
    snap = (lambda x: round(x * fps) / fps) if fps else (lambda x: x)
    placed = []

    for idx, card in enumerate(cards):
        notes, c = [], dict(card)
        anchor = c.get("anchor")
        hint = seconds(c.get("at"))
        start, heard = None, ""
        if anchor:
            m = find(words, anchor, hint=hint)
            if m:
                start = max(0.0, m[0] - LEAD)
                heard = "%s (%s)" % (anchor, m[2])
                if m[3] > 1 and hint is None:
                    notes.append("SAID %dx, took the first; add `at`" % m[3])
            else:
                notes.append("ANCHOR NOT HEARD")
        elif hint is not None:
            start = hint
            heard = "(at %s)" % c.get("at")
        else:
            notes.append("NO ANCHOR")
        c["_heard"] = heard
        c["_notes"] = notes
        c["start"] = start
        placed.append(c)
        if start is None:
            continue

        # rows of a build
        if c.get("kind") in BUILD_KINDS and c.get("itemAnchors"):
            delays, lo = [], start
            for j, phrase in enumerate(c["itemAnchors"]):
                m = find(words, phrase, lo=lo, hi=start + 180) if phrase else None
                if m:
                    d = max(0.0, m[0] - ITEM_LEAD - start)
                    lo = m[0]
                else:
                    prev = delays[-1] if delays else 0.6
                    d = prev + 1.0
                    notes.append("ROW %d NOT HEARD" % (j + 1))
                delays.append(round(d, 2))
            c["delays"] = delays

        # minimum length
        if c.get("fixedDur"):
            want = float(c["dur"])
        elif c.get("kind") in BUILD_KINDS:
            entries = c.get("delays") or []
            rows = row_texts(c)
            last = max(entries) if entries else 0.0
            last_row = rows[-1] if rows else ""
            want = max(SIMPLE_MIN, last + max(BUILD_HOLD, read_time(last_row)),
                       read_time(card_text(c)))
        else:
            want = max(SIMPLE_MIN, read_time(card_text(c)))

        end = start + want
        if c.get("until") and not c.get("fixedDur"):
            m = find(words, c["until"], lo=start)
            if m:
                # `until` stretches a card; it never cuts below the reading minimum
                end = max(start + want, m[1] + UNTIL_PAD)
                if m[1] + UNTIL_PAD < start + want:
                    notes.append("until-words come at %.1f s; kept the %.1f s minimum"
                                 % (m[1] + UNTIL_PAD - start, want))
            else:
                notes.append("UNTIL NOT HEARD")
        elif not c.get("fixedDur"):
            nat = natural_end(words, end)
            if nat:
                end = max(end, nat)
        c["_want"] = want
        c["end"] = end

    # caps: the next card, the end of the video
    timed = sorted([c for c in placed if c["start"] is not None], key=lambda c: c["start"])
    for i, c in enumerate(timed):
        cap = duration
        if not c.get("overlap"):
            for nxt in timed[i + 1:]:
                if not nxt.get("overlap"):
                    cap = min(cap, nxt["start"] - GAP)
                    break
        if c["end"] > cap:
            c["end"] = cap
            if cap - c["start"] < c["_want"] - 0.05:
                c["_notes"].append("SHORT: next card or video end")
        c["start"] = snap(c["start"])
        c["dur"] = snap(max(1.0, c["end"] - c["start"]))
        c["end"] = c["start"] + c["dur"]
        if c.get("delays") and c["delays"][-1] > c["dur"] - 1.0:
            c["_notes"].append("LAST ROW ENTERS LATE")

    return placed, duration


def tc(t):
    if t is None:
        return "--"
    m = int(t // 60)
    return "%d:%05.2f" % (m, t - m * 60)


def table(placed):
    lines = [" #  in        out       dur   kind        card / heard", ""]
    for i, c in enumerate(placed, 1):
        lines.append("%2d  %-8s  %-8s  %4s  %-10s  %s" % (
            i, tc(c["start"]), tc(c.get("end")),
            ("%.1f" % c["dur"]) if c["start"] is not None else "--",
            c.get("kind", ""), label_of(c)[:56]))
        if c["_heard"]:
            lines.append("%44s heard: %s" % ("", c["_heard"][:60]))
        if c.get("delays") and c["start"] is not None:
            lines.append("%44s rows at +%s s" % ("", ", +".join("%.1f" % d for d in c["delays"])))
        for n in c["_notes"]:
            lines.append("%44s ! %s" % ("", n))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("words", help="word timestamps for a file")
    w.add_argument("media")
    w.add_argument("--out", required=True)
    w.add_argument("--transcribe", default=None)

    p = sub.add_parser("place", help="place cards on the words")
    p.add_argument("--cards", required=True)
    p.add_argument("--words", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--fps", type=float, default=None)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--timing-json", default=None,
                   help="also write {cards:[{dur,delays}]} for a renderer")
    a = ap.parse_args()

    if a.cmd == "words":
        data = words_for(Path(a.media).expanduser(), find_transcribe(a.transcribe))
        Path(a.out).expanduser().write_text(json.dumps(data, ensure_ascii=False))
        print("%d words, %.1f s -> %s" % (len(data["words"]), data["duration"], a.out))
        return

    raw = json.loads(Path(a.cards).expanduser().read_text())
    cards = raw["cards"] if isinstance(raw, dict) else raw
    words, wdur = load_words(Path(a.words).expanduser())
    placed, duration = place(cards, words, a.duration or wdur, a.fps)

    out = []
    for c in placed:
        d = {k: v for k, v in c.items() if not k.startswith("_")}
        d["place"] = {"heard": c["_heard"], "notes": c["_notes"]}
        if d["start"] is not None:
            d["start"] = round(d["start"], 4)
            d["end"] = round(d["end"], 4)
        out.append(d)
    result = {"fps": a.fps, "duration": duration, "cards": out}
    Path(a.out).expanduser().write_text(json.dumps(result, ensure_ascii=False, indent=1))
    if a.timing_json:
        timing = {"cards": [({"dur": d["dur"], "delays": d.get("delays")}
                             if d["start"] is not None else None) for d in out]}
        Path(a.timing_json).expanduser().write_text(json.dumps(timing, indent=1) + "\n")
    print(table(placed))
    bad = sum(1 for c in placed if c["_notes"])
    print("\n%d cards, %d with notes. Timed cards -> %s" % (len(placed), bad, a.out))


if __name__ == "__main__":
    main()
