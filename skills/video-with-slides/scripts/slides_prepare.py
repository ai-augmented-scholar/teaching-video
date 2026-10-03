#!/usr/bin/env python3
"""Turn a slide deck into one PNG per slide plus the text of each slide.

Usage:
    python3 slides_prepare.py DECK --out DIR [--width 1920]

DECK is a PDF (from PowerPoint, Keynote, Canva, Google Slides, Beamer, or any
app that exports PDF) or a .pptx file. A .pptx is converted to PDF with
LibreOffice when it is installed; either way its speaker notes are read
straight from the file, because they are the closest thing to what the
lecturer said over each slide.

Writes:
    DIR/slides/slide-001.png ...   one image per page, --width pixels wide
    DIR/slides.json                page count, aspect ratio, text and notes

Rendering backend, first one found wins:
    1. pypdfium2 (Apache-2.0 / BSD-3), in this python or in the plugin's
       environment at $TV_DATA/venv
    2. poppler's pdftoppm + pdftotext on PATH or in Homebrew
Neither present: the script says how to add pypdfium2 and stops.

Stdlib only at the top level, so the macOS system python3 can run it.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TV_DATA = os.environ.get("TV_DATA", "").strip()
EXTRA_BIN = [p for p in (os.path.join(TV_DATA, "venv", "bin") if TV_DATA else "",
                         os.path.expanduser("~/.local/bin"),
                         "/opt/homebrew/bin", "/usr/local/bin") if p]


def which(name):
    for d in EXTRA_BIN:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which(name)


# ---------------------------------------------------------------- pptx text

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _rels(z, part):
    """Relationship id -> target path (resolved inside the zip) for a part."""
    folder, name = part.rsplit("/", 1)
    rels_path = "%s/_rels/%s.rels" % (folder, name)
    out = {}
    if rels_path not in z.namelist():
        return out
    root = ET.fromstring(z.read(rels_path))
    for r in root.findall("rel:Relationship", NS):
        target = r.get("Target", "")
        parts = (folder + "/" + target).split("/")
        resolved = []
        for seg in parts:
            if seg == "..":
                if resolved:
                    resolved.pop()
            elif seg and seg != ".":
                resolved.append(seg)
        out[r.get("Id")] = ("/".join(resolved), r.get("Type", ""))
    return out


def _paragraphs(xml_bytes):
    root = ET.fromstring(xml_bytes)
    lines = []
    for para in root.iter("{%s}p" % NS["a"]):
        text = "".join(t.text or "" for t in para.iter("{%s}t" % NS["a"]))
        if text.strip():
            lines.append(text.strip())
    return lines


def pptx_text(path):
    """Slide text and speaker notes per slide, in presentation order.

    The order comes from presentation.xml, not from the slideN.xml file
    names: after slides are reordered in PowerPoint the two disagree. Hidden
    slides are skipped, because PowerPoint leaves them out of a PDF export.
    """
    z = zipfile.ZipFile(path)
    pres = "ppt/presentation.xml"
    rels = _rels(z, pres)
    root = ET.fromstring(z.read(pres))
    out = []
    for sld in root.findall("p:sldIdLst/p:sldId", NS):
        rid = sld.get("{%s}id" % NS["r"])
        part = rels.get(rid, (None, None))[0]
        if not part or part not in z.namelist():
            continue
        sroot = ET.fromstring(z.read(part))
        if sroot.get("show") == "0":
            continue
        text = _paragraphs(z.read(part))
        notes = []
        for target, typ in _rels(z, part).values():
            if typ.endswith("/notesSlide") and target in z.namelist():
                # A notes page repeats the slide number in a placeholder;
                # drop lines that are only a number.
                notes = [l for l in _paragraphs(z.read(target))
                         if not re.fullmatch(r"\d+", l)]
        out.append({"text": "\n".join(text), "notes": "\n".join(notes)})
    return out


def pptx_to_pdf(path, workdir):
    soffice = which("soffice") or (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        else None)
    if not soffice:
        return None
    subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                    "--outdir", str(workdir), str(path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pdf = Path(workdir) / (Path(path).stem + ".pdf")
    return pdf if pdf.is_file() else None


# ---------------------------------------------------------------- rendering

PDFIUM_WORKER = r'''
import json, subprocess, sys
import pypdfium2 as pdfium
pdf_path, out_dir, width, ffmpeg = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
pdf = pdfium.PdfDocument(pdf_path)
pages = []
for i in range(len(pdf)):
    page = pdf[i]
    w, h = page.get_size()
    bitmap = page.render(scale=width / w, rev_byteorder=True)
    img = "%s/slide-%03d.png" % (out_dir, i + 1)
    # Raw pixels through ffmpeg to PNG keeps Pillow out of the dependencies.
    # PDFium picks the pixel layout per page (RGB for an opaque page).
    fmt = {"RGB": "rgb24", "BGR": "bgr24", "RGBA": "rgba", "BGRA": "bgra",
           "RGBX": "rgb0", "BGRX": "bgr0", "L": "gray"}[bitmap.mode]
    raw = bytes(bitmap.buffer)
    stride, bw, bh = bitmap.stride, bitmap.width, bitmap.height
    row = bw * bitmap.n_channels
    if stride != row:
        raw = b"".join(raw[r * stride:r * stride + row] for r in range(bh))
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "rawvideo",
                    "-pix_fmt", fmt, "-s", "%dx%d" % (bw, bh), "-i", "-",
                    "-frames:v", "1", img], input=raw, check=True)
    text = page.get_textpage().get_text_range()
    pages.append({"w": w, "h": h, "text": text})
print(json.dumps(pages))
'''


def pdfium_python():
    """A python that can import pypdfium2: this one, or the plugin's."""
    candidates = [sys.executable]
    if TV_DATA:
        candidates.insert(0, os.path.join(TV_DATA, "venv", "bin", "python"))
    for py in candidates:
        if not os.path.isfile(py):
            continue
        r = subprocess.run([py, "-c", "import pypdfium2"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return py
    return None


def render_pdfium(py, pdf, out_dir, width, ffmpeg):
    r = subprocess.run([py, "-c", PDFIUM_WORKER, str(pdf), str(out_dir),
                        str(width), ffmpeg], stdout=subprocess.PIPE)
    if r.returncode != 0:
        sys.exit("ERROR: pypdfium2 could not render %s" % pdf)
    return json.loads(r.stdout.decode("utf-8"))


def render_poppler(pdf, out_dir, width):
    pdftoppm, pdftotext, pdfinfo = which("pdftoppm"), which("pdftotext"), which("pdfinfo")
    subprocess.run([pdftoppm, "-png", "-scale-to-x", str(width), "-scale-to-y", "-1",
                    str(pdf), str(Path(out_dir) / "p")], check=True)
    # pdftoppm pads the page number to the page count's width: p-1, p-01 ...
    made = sorted(Path(out_dir).glob("p-*.png"),
                  key=lambda p: int(p.stem.split("-")[-1]))
    pages = []
    info = subprocess.run([pdfinfo, str(pdf)], stdout=subprocess.PIPE).stdout.decode()
    m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
    w, h = (float(m.group(1)), float(m.group(2))) if m else (16.0, 9.0)
    for i, p in enumerate(made, 1):
        p.rename(Path(out_dir) / ("slide-%03d.png" % i))
        txt = subprocess.run([pdftotext, "-f", str(i), "-l", str(i), "-layout",
                              str(pdf), "-"], stdout=subprocess.PIPE).stdout
        pages.append({"w": w, "h": h, "text": txt.decode("utf-8", "replace")})
    return pages


def clean(text):
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.replace("\r", "\n").split("\n")]
    return "\n".join(l for l in lines if l)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("deck", help="PDF or .pptx")
    ap.add_argument("--out", required=True, help="Folder for slides/ and slides.json")
    ap.add_argument("--width", type=int, default=1920,
                    help="Width of each slide image in pixels (default 1920)")
    ap.add_argument("--notes-from", metavar="PPTX", default=None,
                    help="With a PDF deck: read speaker notes from the .pptx "
                         "it was exported from")
    ap.add_argument("--backend", choices=("auto", "pypdfium2", "poppler"),
                    default="auto", help=argparse.SUPPRESS)
    a = ap.parse_args()

    deck = Path(a.deck).expanduser().resolve()
    if not deck.is_file():
        sys.exit("ERROR: no such file: %s" % deck)
    ext = deck.suffix.lower()
    if ext in (".key", ".odp", ".ppt", ".gslides"):
        sys.exit("ERROR: export the deck as PDF first (File > Export or "
                 "Download > PDF in the app that made it), then run this again "
                 "on the PDF.")
    if ext not in (".pdf", ".pptx"):
        sys.exit("ERROR: the deck must be a PDF or a .pptx file, not %s" % ext)

    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        sys.exit("ERROR: ffmpeg is not installed. Run /teaching-video:setup.")

    out = Path(a.out).expanduser().resolve()
    img_dir = out / "slides"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)

    notes_by_page = None
    if a.notes_from:
        src = Path(a.notes_from).expanduser()
        if src.suffix.lower() != ".pptx" or not src.is_file():
            sys.exit("ERROR: --notes-from takes the .pptx file the PDF came from.")
        notes_by_page = pptx_text(src)
    with tempfile.TemporaryDirectory(prefix="vws-") as work:
        pdf = deck
        if ext == ".pptx":
            notes_by_page = pptx_text(deck)
            pdf = pptx_to_pdf(deck, work)
            if pdf is None:
                sys.exit("ERROR: this Mac has no LibreOffice to turn the .pptx "
                         "into a PDF. In PowerPoint, choose File > Export > PDF, "
                         "then run this again on the PDF. (Keep the .pptx: pass "
                         "it with --notes-from to keep the speaker notes.)")

        py = pdfium_python() if a.backend != "poppler" else None
        have_poppler = a.backend != "pypdfium2" and all(
            which(t) for t in ("pdftoppm", "pdftotext", "pdfinfo"))
        if py:
            pages = render_pdfium(py, pdf, img_dir, a.width, ffmpeg)
            backend = "pypdfium2"
        elif have_poppler:
            pages = render_poppler(pdf, img_dir, a.width)
            backend = "poppler"
        else:
            venv_pip = (os.path.join(TV_DATA, "venv", "bin", "pip")
                        if TV_DATA else "<plugin data>/venv/bin/pip")
            sys.exit("ERROR: nothing on this Mac can read a PDF yet.\n"
                     "  Add pypdfium2 (about 6 MB) to the plugin's environment:\n"
                     "    \"%s\" install pypdfium2\n"
                     "  or run /teaching-video:setup." % venv_pip)

    if not pages:
        sys.exit("ERROR: the PDF has no pages.")

    if notes_by_page is not None and len(notes_by_page) != len(pages):
        print("WARNING: the .pptx has %d visible slides but the PDF has %d pages; "
              "speaker notes are left out." % (len(notes_by_page), len(pages)),
              file=sys.stderr)
        notes_by_page = None

    w, h = pages[0]["w"], pages[0]["h"]
    result = {
        "source": str(deck),
        "backend": backend,
        "count": len(pages),
        "aspect": round(w / h, 4),
        "pages": [],
    }
    empty = []
    for i, p in enumerate(pages, 1):
        text = clean(p["text"])
        notes = clean(notes_by_page[i - 1]["notes"]) if notes_by_page else ""
        if not text and not notes:
            empty.append(i)
        result["pages"].append({
            "n": i,
            "image": "slides/slide-%03d.png" % i,
            "title": text.split("\n")[0][:80] if text else "",
            "text": text,
            "notes": notes,
        })
    (out / "slides.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))

    print("%d slides, aspect %.3f (%s), images in %s" % (
        len(pages), result["aspect"], backend, img_dir))
    if notes_by_page:
        print("Speaker notes read from the .pptx.")
    if empty:
        print("No text on slide(s) %s: these are pictures only, so the matcher "
              "has nothing to go on there. Place them by hand in the timing "
              "table." % ", ".join(map(str, empty)))
    odd = [pg["n"] for pg in pages_with_n(pages) if abs(pg["w"] / pg["h"] - w / h) > 0.01]
    if odd:
        print("WARNING: slide(s) %s have a different page size from slide 1." %
              ", ".join(map(str, odd)))


def pages_with_n(pages):
    return [dict(p, n=i) for i, p in enumerate(pages, 1)]


if __name__ == "__main__":
    main()
