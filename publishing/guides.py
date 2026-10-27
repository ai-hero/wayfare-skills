"""Two illustrated field guides, landscape PDFs for LinkedIn document posts.

    ./publish guides      -> $PUBLISH_OUT/dist/guide-01-inside-a-software-factory.pdf
                             $PUBLISH_OUT/dist/guide-02-what-surprised-me.pdf

The copy is `editions/guides.json` (gitignored with the other editions: it carries the findings);
the art is drawn in code by `guide_scenes`, one function per page, with `guide_art`'s kit. A page is
an SVG of W x H points: the copy in a left column, the scene in the rest, except where a scene asks
for the whole page.
"""
import functools
import json
import os

import fitz

import paths
from cover import FONTS, print_page, static_font
from guide_art import INK, LINE, PAGE, QUIET, ROSE, ROSE_DARK, mono, rect, text

MANIFEST = os.path.join(paths.EDITIONS, "guides.json")
W, H = 960.0, 540.0
M = 48.0
COL = 262.0
ART = (M + COL + 34, 44.0, W - M, H - 44.0)
# Each weight is cut to a static instance: Chrome prints a variable font at another weight as Type 3.
WEIGHTS = {"Manrope": (200, 300, 500), "Geist": (300, 400, 500), "Geist Mono": (400, 500)}
FLOWS = {"direction": "Direction flow", "build": "Build flow", "delivery": "Delivery flow",
         "consistency": "Consistency flow", "improvement": "Improvement flow"}


@functools.lru_cache(maxsize=None)
def _metrics(font):
    from fontTools.ttLib import TTFont
    tt = TTFont(FONTS[font])
    return tt.getBestCmap(), tt["hmtx"], tt["head"].unitsPerEm


def width(s, size, font="Geist"):
    cmap, hmtx, upm = _metrics(font)
    return sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in s) * size / upm


def wrap(s, width_pt, size, font="Geist"):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and width(trial, size, font) > width_pt:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def block(x, y, s, w, size, font="Geist", weight=300, fill=INK, lead=1.45, spacing=None):
    """Wrapped lines from baseline y; returns the svg and the y below the last line."""
    out = []
    for ln in wrap(s, w, size, font):
        out.append(text(x, y, ln, size, font, weight, fill, spacing=spacing))
        y += size * lead
    return "".join(out), y


def headline_size(s, w, start=30, floor=22, max_lines=3):
    size = start
    while size > floor and len(wrap(s, w, size, "Manrope")) > max_lines:
        size -= 1
    return size


def chrome(guide, n, total, flow=None):
    out = [rect(M, 30, 22, 2, ROSE, "none", 0),
           mono(M, 22, f"Field guide {guide['number']}", 6.6),
           mono(W - M, 22, f"{n:02d} / {total}", 6.6, anchor="end")]
    if flow:
        label = FLOWS[flow]
        out.append(mono(W - M - 52, 22, label, 6.6, ROSE_DARK, anchor="end"))
    out.append(mono(M, H - 22, guide["footer"], 6, LINE))
    return "".join(out)


def copy_column(p, top=96, x=M, w=COL):
    """Headline, body and the source line, in the left column."""
    size = headline_size(p["headline"], w)
    out, y = block(x, top, p["headline"], w, size, "Manrope", 200, INK, 1.08, -size * 0.02)
    y += 14
    out2, y = block(x, y + 4, p["body"], w, 11.6, "Geist", 300, INK, 1.5)
    if y > H - 72:
        raise SystemExit(f"guides: copy for {p['headline']!r} runs into the source line; shorten it")
    src = ""
    if p.get("source"):
        # block() measures glyphs only; the mono's letter-spacing is extra, so wrap narrower.
        src, _ = block(x, H - 64, p["source"], w * 0.86, 6.2, "Geist Mono", 400, QUIET, 1.5, 0.6)
    return out + out2 + src


def page_svg(guide, p, n, total):
    from guide_scenes import SCENES
    art = SCENES[(guide["key"], n)]
    full = getattr(art, "full", False)
    body = art(p, guide) if full else (copy_column(p) + art(p, guide))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'{rect(0, 0, W, H, PAGE, "none", 0)}{body}{chrome(guide, n, total, p.get("flow"))}</svg>')


def font_css():
    return "".join(f'@font-face{{font-family:"{n}";src:url("file://{static_font(n, w)}") format("truetype");'
                   f'font-weight:{w}}}' for n, ws in WEIGHTS.items() for w in ws)


def print_pdf(svgs, out):
    page = os.path.splitext(out)[0] + ".html"
    with open(page, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}'
                f'@page{{size:{W}pt {H}pt;margin:0}}html,body{{margin:0}}'
                f'svg{{display:block;width:{W}pt;height:{H}pt;page-break-after:always;break-after:page}}'
                f'</style></head><body>{"".join(svgs)}</body></html>')
    print_page(page, out, 6000)
    n = len(svgs)
    with fitz.open(out) as doc:
        # A trailing page break leaves one blank page after the last SVG; any other count means a page
        # split or went missing, and trimming by count would silently drop the real last page.
        blank = len(doc) == n + 1 and not doc[-1].get_text().strip() and not doc[-1].get_drawings()
        if len(doc) != n and not blank:
            raise SystemExit(f"guides: {out} printed {len(doc)} pages for {n} pages of art")
        if blank:
            doc.delete_page(n)
            doc.save(out + ".tmp", garbage=3, deflate=True)
    if blank:
        os.replace(out + ".tmp", out)
    return page


def build(guide, only=None):
    """`only` builds a proof of some pages under a separate name, never over the full guide."""
    from guide_scenes import SCENES
    pages = guide["pages"]
    # Scenes are keyed by page position, so a page added, dropped or moved in guides.json would pair
    # every later page with the wrong drawing.
    drawn = sorted(n for k, n in SCENES if k == guide["key"])
    if drawn != list(range(1, len(pages) + 1)):
        raise SystemExit(f"guides: {guide['key']} has {len(pages)} pages but scenes for {drawn}")
    svgs = [page_svg(guide, p, i + 1, len(pages)) for i, p in enumerate(pages) if not only or i + 1 in only]
    out = os.path.join(paths.DIST, guide["file"])
    if only:
        out = out.replace(".pdf", "-proof.pdf")
    html = print_pdf(svgs, out)
    os.remove(html)
    return out


def main(argv=None):
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    os.makedirs(paths.DIST, exist_ok=True)
    for guide in manifest["guides"]:
        guide["footer"] = manifest["footer"]
        print(f"guides: {build(guide)}")


if __name__ == "__main__":
    main()
