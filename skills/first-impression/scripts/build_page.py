#!/usr/bin/env python3
"""Render first-impression.html from a JSON plan.

The model decides the content (titles, poster frame, openings, the pick).
This script only does the mechanical part: character counts, escaping,
the word label on the picked option, and the page layout.

Usage:
  build_page.py plan.json first-impression.html

Stdlib only, so the macOS system python3 can run it.

Plan shape (all strings unless noted):
{
  "working_title": "...",            # what the user calls the video
  "language": "en",                  # BCP 47 tag of the spoken language
  "source": "path of the transcript or beat sheet",
  "audience": "who watches, e.g. second-year students in a survey course",
  "promise": "one sentence: what the student understands or can do after",
  "angle": "how | why | compare | mistake | question",
  "titles": [{"text": "...", "why": "...", "pick": true}],
  "poster": {"text": "...", "alternates": ["..."], "focal": "...",
             "face": "...", "notes": "..."},
  "openings": [{"name": "...", "beats": ["...", "..."], "seconds": 30,
                "pick": false}],
  "check": "one paragraph: do the three pieces make the same promise?",
  "fill_in": ["each [FILL IN: ...] item the user still has to supply"]
}
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

FILL = re.compile(r"\[FILL IN:[^\]]*\]")


def esc(text):
    """Escape, then mark every [FILL IN: ...] so it stands out in print too."""
    out, last = [], 0
    for m in FILL.finditer(text or ""):
        out.append(html.escape(text[last:m.start()]))
        out.append('<mark class="fill">%s</mark>' % html.escape(m.group(0)))
        last = m.end()
    out.append(html.escape((text or "")[last:]))
    return "".join(out)


def pick_flag(item):
    return ' <span class="flag">Picked</span>' if item.get("pick") else ""


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_page.py plan.json first-impression.html")
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    titles = plan.get("titles") or []
    openings = plan.get("openings") or []
    if not titles or not openings or not plan.get("poster"):
        sys.exit("ERROR: the plan needs titles, poster and openings.")
    if sum(1 for t in titles if t.get("pick")) != 1:
        sys.exit("ERROR: mark exactly one title with \"pick\": true.")
    if sum(1 for o in openings if o.get("pick")) != 1:
        sys.exit("ERROR: mark exactly one opening with \"pick\": true.")

    title_rows = []
    for t in titles:
        n = len(t["text"])
        warn = ' <span class="warn">over 60</span>' if n > 60 else ""
        title_rows.append(
            '<li class="%s"><p class="opt">%s%s</p>'
            '<p class="why">%s <span class="count">%d characters</span>%s</p></li>'
            % ("pick" if t.get("pick") else "", esc(t["text"]), pick_flag(t),
               esc(t.get("why", "")), n, warn))

    p = plan["poster"]
    alts = " · ".join(esc(a) for a in p.get("alternates", []))
    poster = (
        '<dl class="spec">'
        '<dt>Text</dt><dd><b>%s</b> <span class="count">%d words</span>%s</dd>'
        '<dt>Focal image</dt><dd>%s</dd>'
        '<dt>Speaker</dt><dd>%s</dd>%s</dl>'
        % (esc(p["text"]), len(p["text"].split()),
           ("<br><span class=\"muted\">Alternates: %s</span>" % alts) if alts else "",
           esc(p.get("focal", "")), esc(p.get("face", "")),
           ("<dt>Notes</dt><dd>%s</dd>" % esc(p["notes"])) if p.get("notes") else ""))

    opening_blocks = []
    for o in openings:
        beats = "".join("<li>%s</li>" % esc(b) for b in o.get("beats", []))
        opening_blocks.append(
            '<div class="take %s"><p class="takehead">%s%s '
            '<span class="count">about %s seconds</span></p><ul>%s</ul></div>'
            % ("pick" if o.get("pick") else "", esc(o["name"]), pick_flag(o),
               esc(str(o.get("seconds", 30))), beats))

    fills = plan.get("fill_in") or []
    fill_block = ""
    if fills:
        fill_block = (
            '<section><h2>Still to fill in</h2><ul>%s</ul></section>'
            % "".join("<li>%s</li>" % esc(f) for f in fills))

    page = TEMPLATE.format(
        lang=html.escape(plan.get("language", "en")),
        working=esc(plan.get("working_title", "")),
        promise=esc(plan.get("promise", "")),
        audience=esc(plan.get("audience", "")),
        angle=esc(plan.get("angle", "")),
        source=esc(plan.get("source", "")),
        titles="".join(title_rows),
        poster=poster,
        openings="".join(opening_blocks),
        check=esc(plan.get("check", "")),
        fills=fill_block,
        today=date.today().isoformat(),
    )
    Path(sys.argv[2]).write_text(page, encoding="utf-8")
    print("wrote %s" % sys.argv[2])


TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>First Impression</title>
<style>
  :root{{color-scheme:light;--ground:#FAFAF7;--ink:#1F1F1F;--line:#DDDAD2;
    --accent:#2F5D8A;--muted:#5C5A55;--font:'Inter',system-ui,-apple-system,sans-serif}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--font);
    font-size:1.125rem;line-height:1.55}}
  .wrap{{max-width:900px;margin:0 auto;padding:3rem 16px 5rem}}
  .eyebrow{{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;font-weight:600;
    color:var(--accent);margin:0}}
  h1{{font-size:clamp(1.8rem,5vw,2.6rem);line-height:1.15;margin:.4rem 0 1rem}}
  h2{{font-size:1.3rem;margin:0 0 1rem}}
  section{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--line)}}
  .facts{{display:grid;grid-template-columns:auto 1fr;gap:.4rem 1.2rem;margin:0}}
  .facts dt,.spec dt{{font-size:.8rem;letter-spacing:.06em;text-transform:uppercase;
    font-weight:600;color:var(--muted);padding-top:.25rem}}
  .facts dd,.spec dd{{margin:0}}
  .spec{{display:grid;grid-template-columns:auto 1fr;gap:.6rem 1.2rem;margin:0}}
  ol.titles{{margin:0;padding-left:1.4rem;display:grid;gap:1.1rem}}
  ol.titles li.pick{{border-left:3px solid var(--accent);padding-left:.8rem;margin-left:-.8rem}}
  .opt{{font-size:1.35rem;font-weight:700;margin:0;line-height:1.3}}
  .why{{margin:.25rem 0 0;color:var(--muted)}}
  .count{{font-size:.85rem;font-weight:600;color:var(--muted);white-space:nowrap}}
  .warn{{font-size:.85rem;font-weight:700;color:var(--ink);border:1px solid var(--ink);padding:0 .3rem}}
  .flag{{font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;font-weight:700;
    color:var(--accent);border:1px solid var(--accent);padding:.05rem .4rem;vertical-align:middle}}
  .muted{{color:var(--muted)}}
  .take{{border-left:1px solid var(--line);padding-left:1rem;margin-bottom:1.6rem}}
  .take.pick{{border-left:3px solid var(--accent)}}
  .takehead{{font-weight:700;margin:0 0 .3rem}}
  .take ul{{margin:0;padding-left:1.2rem}}
  .take li{{margin-bottom:.3rem}}
  mark.fill{{background:none;color:var(--ink);font-weight:700;border-bottom:2px dotted var(--ink)}}
  footer{{margin-top:3rem;font-size:.9rem;color:var(--muted)}}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">First impression</p>
  <h1>{working}</h1>
  <dl class="facts">
    <dt>Promise</dt><dd>{promise}</dd>
    <dt>Audience</dt><dd>{audience}</dd>
    <dt>Angle</dt><dd>{angle}</dd>
    <dt>Source</dt><dd>{source}</dd>
  </dl>

  <section>
    <h2>Title</h2>
    <ol class="titles">{titles}</ol>
  </section>

  <section>
    <h2>Poster frame</h2>
    {poster}
  </section>

  <section>
    <h2>First 30 seconds</h2>
    {openings}
  </section>

  <section>
    <h2>One promise, three times</h2>
    <p>{check}</p>
  </section>

  {fills}

  <footer>Made {today} by the first-impression skill.</footer>
</div>
</body>
</html>
"""

if __name__ == "__main__":
    main()
