#!/usr/bin/env python3
"""Check whether a font will actually render in the text cards.

  check_font.py "Font Name" [--file /path/to/font.otf]

The cards are drawn by a headless Chrome, so the only reliable test is to ask
that browser. The script lays out a test line twice per fallback — once in the
named font with a fallback behind it, once in the fallback alone — and compares
the widths. If the width changes against both a monospace and a serif fallback,
Chrome is using the named font. With --file, it tests that file instead of an
installed font (a font the user has as a file but has not installed).

Prints JSON: {"font", "available", "source", "browser", "detail"}.
"Inter" always counts as available: the plugin ships it.

Browser order: the renderer's own headless Chrome in $TV_DATA/renderer, then
Google Chrome in /Applications.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TEST = "Hamburgefonstiv 0123456789 WMiil &?"


def find_browser():
    data = os.environ.get("TV_DATA")
    if data:
        base = Path(data) / "renderer" / "node_modules" / ".remotion" / "chrome-headless-shell"
        if base.is_dir():
            for p in base.rglob("chrome-headless-shell"):
                if p.is_file() and os.access(str(p), os.X_OK):
                    return str(p)
    for p in (Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
              Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if p.is_file():
            return str(p)
    return None


def page(font, font_file):
    face = ""
    if font_file:
        face = "@font-face{font-family:'%s';src:url('%s');}" % (
            font.replace("'", ""), Path(font_file).resolve().as_uri())
    safe = font.replace("'", "").replace("\\", "")
    return """<!doctype html><html><head><meta charset="utf-8"><style>%s
span{font-size:72px;white-space:nowrap;position:absolute}</style></head><body>
<span id="a" style="font-family:'%s',monospace">%s</span>
<span id="b" style="font-family:monospace">%s</span>
<span id="c" style="font-family:'%s',serif">%s</span>
<span id="d" style="font-family:serif">%s</span>
<pre id="out">pending</pre>
<script>
document.fonts.ready.then(function(){
  setTimeout(function(){
    var w=function(id){return document.getElementById(id).getBoundingClientRect().width;};
    document.getElementById('out').textContent='RESULT '+JSON.stringify({a:w('a'),b:w('b'),c:w('c'),d:w('d')});
  }, 300);
});
</script></body></html>""" % (face, safe, TEST, TEST, safe, TEST, TEST)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__.strip())
    font = argv[0].strip()
    font_file = None
    if "--file" in argv:
        i = argv.index("--file")
        if i + 1 >= len(argv):
            sys.exit("ERROR: --file needs a path.")
        font_file = str(Path(argv[i + 1]).expanduser())
        if not Path(font_file).is_file():
            sys.exit("ERROR: no such font file: %s" % font_file)

    if font.lower() == "inter" and not font_file:
        print(json.dumps({"font": font, "available": True, "source": "bundled",
                          "browser": None, "detail": "Inter ships with the plugin."}, indent=2))
        return

    browser = find_browser()
    if not browser:
        sys.exit("ERROR: no headless Chrome found. Run /teaching-video:setup first.")

    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "font-check.html"
        html.write_text(page(font, font_file), encoding="utf-8")
        r = subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
             "--virtual-time-budget=3000", "--dump-dom", html.as_uri()],
            capture_output=True, text=True, timeout=60)
    m = re.search(r"RESULT (\{.*?\})", r.stdout)
    if not m:
        sys.exit("ERROR: the browser did not report a result. %s" % r.stderr.strip()[-500:])
    w = json.loads(m.group(1))
    differs_mono = abs(w["a"] - w["b"]) > 0.5
    differs_serif = abs(w["c"] - w["d"]) > 0.5
    available = differs_mono and differs_serif
    print(json.dumps({
        "font": font,
        "available": available,
        "source": "file" if font_file else "installed",
        "browser": browser,
        "detail": ("Chrome renders this font." if available else
                   "Chrome does not find this font, so the cards would fall back to Inter."),
        "widths": w,
    }, indent=2))


if __name__ == "__main__":
    main()
