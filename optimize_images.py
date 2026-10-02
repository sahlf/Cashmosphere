#!/usr/bin/env python3
"""
Cashmosphere: Bilder optimieren (WebP in 5 Größen)
=================================================

Was das Skript macht
  1. Erzeugt aus jedem JPG in assets/imagery/ WebP-Versionen in
     640, 1024, 1600, 2400 und 3200 px Breite.
  2. Prüft, ob wirklich ALLE benötigten Dateien da sind.
  3. Erst dann trägt es die WebP-Versionen in die HTML-Dateien ein.
     Geht vorher etwas schief, bleibt das HTML unverändert, die
     Seite funktioniert also immer.

Nach jedem neuen HTML-Update oder neuen Bildern einfach erneut
ausführen. Bereits erzeugte Bilder werden übersprungen.

Ausführen: siehe Anleitung im Chat (einmalige Einrichtung mit venv).
"""

import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("FEHLER: Pillow ist nicht installiert (bzw. nicht für dieses Python).")
    print("Bitte die Einrichtung aus der Anleitung ausführen und das Skript")
    print("mit  ~/cashmosphere-tools/bin/python optimize_images.py  starten.")
    sys.exit(1)

ROOT    = Path(__file__).resolve().parent
SRC     = ROOT / "assets" / "imagery"
WIDTHS  = [640, 1024, 1600, 2400, 3200]
QUALITY = 80

IMG = re.compile(r'<img\b(?:(?!>).)*?src="(assets/imagery/[^"]+?)\.(jpe?g|png)"(?:(?!>).)*?>', re.S | re.I)

SIZES = {  # context class found shortly before the <img>  ->  sizes attribute
    "cm-mega-menu__img":       "200px",
    "lookbook__card-img-wrap": "(max-width: 768px) 45vw, (min-width: 2560px) 28vw, 30vw",
    "split__tile":             "50vw",
    "about-row__img":          "(max-width: 1024px) 100vw, 50vw",
    "contact-layout__img":     "(max-width: 1024px) 100vw, 50vw",
}


def sizes_for(tag, before):
    if "hero__img" in tag or "banner__img" in tag:
        return "100vw"
    if "collection-grid__photo" in tag:
        return "(max-width: 768px) 50vw, (min-width: 1920px) 25vw, 33vw"
    ctx = before[-400:]
    best = max(SIZES, key=ctx.rfind)
    return SIZES[best] if ctx.rfind(best) >= 0 else "100vw"


def exists_exact(rel):
    """Case-sensitive check (macOS ignores case, Netlify doesn't)."""
    p = ROOT / rel
    return p.parent.is_dir() and p.name in {c.name for c in p.parent.iterdir()}


def human(n):
    return f"{n / 1024 / 1024:.1f} MB"


def convert_images():
    sources = sorted(p for p in SRC.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    print(f"Schritt 1/3: {len(sources)} Bilder gefunden in {SRC}")
    made = 0
    orig = small = 0
    for i, src in enumerate(sources, 1):
        orig += src.stat().st_size
        targets = [SRC / f"{src.stem}-{w}.webp" for w in WIDTHS]
        fresh = all(t.exists() and t.stat().st_mtime >= src.stat().st_mtime for t in targets)
        if not fresh:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
                for w, out in zip(WIDTHS, targets):
                    tw = min(w, im.width)  # never upscale
                    img = im if tw == im.width else im.resize(
                        (tw, round(im.height * tw / im.width)), Image.LANCZOS)
                    img.save(out, "WEBP", quality=QUALITY, method=4)
            made += 1
            print(f"  [{i:>3}/{len(sources)}] {src.name}")
        small += targets[2].stat().st_size
    print(f"  -> {made} neu umgewandelt, {len(sources) - made} waren schon aktuell.")
    print(f"  Originale gesamt: {human(orig)}  |  WebP 1600 px gesamt: {human(small)}\n")


def plan_html():
    """Returns {file: new_html} for every page, or a list of missing files."""
    pages, missing = {}, set()
    for html in sorted(ROOT.glob("*.html")):
        s = html.read_text(encoding="utf-8")
        out, pos = [], 0
        for m in IMG.finditer(s):
            before = s[:m.start()]
            if before.endswith('">') and '<source type="image/webp"' in before[-1200:].split("<img")[-1]:
                continue  # already wrapped
            if before.rstrip().endswith("</picture>") or before[-1200:].rfind("<picture>") > before[-1200:].rfind("</picture>"):
                continue
            stem = m.group(1)
            files = [f"{stem}-{w}.webp" for w in WIDTHS]
            for f in files:
                if not exists_exact(f):
                    missing.add(f)
            srcset = ", ".join(f"{f} {w}w" for f, w in zip(files, WIDTHS))
            out.append(s[pos:m.start()])
            out.append(f'<picture><source type="image/webp" srcset="{srcset}" '
                       f'sizes="{sizes_for(m.group(0), before)}">{m.group(0)}</picture>')
            pos = m.end()
        out.append(s[pos:])
        pages[html] = "".join(out)
        # also verify WebP references that were already in the HTML
        for ref in re.findall(r"(assets/imagery/[^\s\"',]+\.webp)", pages[html]):
            if not exists_exact(ref):
                missing.add(ref)
    return pages, missing


def main():
    if not SRC.is_dir():
        print(f"FEHLER: Ordner nicht gefunden: {SRC}")
        print("Das Skript muss im Projektordner liegen, direkt neben index.html.")
        sys.exit(1)

    convert_images()

    print("Schritt 2/3: Prüfe, ob alle benötigten WebP-Dateien vorhanden sind …")
    pages, missing = plan_html()
    if missing:
        print(f"  ABGEBROCHEN: {len(missing)} Dateien fehlen, z. B.:")
        for f in sorted(missing)[:10]:
            print("    ", f)
        print("  Meist: Groß-/Kleinschreibung im Dateinamen weicht vom HTML ab")
        print("  (z. B. CM-Hero.JPG statt cm-hero.jpg). HTML wurde NICHT verändert.")
        sys.exit(2)
    print("  OK, alles vorhanden.\n")

    print("Schritt 3/3: Trage WebP-Versionen ins HTML ein …")
    changed = 0
    for html, new in pages.items():
        if new != html.read_text(encoding="utf-8"):
            html.write_text(new, encoding="utf-8")
            changed += 1
            print("  aktualisiert:", html.name)
    print(f"  -> {changed} HTML-Dateien aktualisiert.\n\nFertig.")


if __name__ == "__main__":
    main()
