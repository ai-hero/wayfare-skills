"""Render built editions to images for visual review: `./publish qa [book|technical|slides] [pages]`.

Pages land in `$PUBLISH_OUT/qa/<edition>/`: `p012.png` for page 12, `s012-013.png` for the book's
facing pages (even on the left, as bound). With no page list the sample is the opening pages, every
chapter opening, and a page holding a figure and one holding a table where the PDF has them.
"""
import os
import sys

import fitz

import paths

DPI = 110


def pdf_for(edition):
    return os.path.join(paths.DIST, {"slides": "slides.pdf"}.get(edition, f"{edition}.pdf"))


def sample(doc):
    """Front matter, the first page of each outline entry, and the first pages with an image or a table."""
    pages = {0, 1, 2, 3, 4, 5}
    for level, _, page in doc.get_toc():
        if level == 1 and page > 0:
            pages.add(page - 1)
    with_img = [i for i in range(len(doc)) if doc[i].get_images()]
    pages.update(with_img[:3] + with_img[len(with_img) // 2: len(with_img) // 2 + 1])
    for i in range(len(doc)):
        if doc[i].find_tables().tables:
            pages.add(i)
            break
    pages.add(len(doc) - 1)
    return sorted(p for p in pages if p < len(doc))


def render(edition, wanted=None, spreads=None):
    path = pdf_for(edition)
    doc = fitz.open(path)
    out = os.path.join(paths.QA, edition)
    os.makedirs(out, exist_ok=True)
    pages = [p for p in wanted if p < len(doc)] if wanted else (range(len(doc)) if edition == "slides" else sample(doc))
    files = []
    for i in pages:
        f = os.path.join(out, f"p{i + 1:03d}.png")
        doc[i].get_pixmap(dpi=DPI).save(f)
        files.append(f)
    if spreads if spreads is not None else edition == "book":
        for i in sorted({p - (p % 2 == 0) for p in pages if p > 0}):
            if i + 1 < len(doc):
                files.append(spread(doc, i, out))
    print(f"qa: {edition}: {len(doc)} pages, {len(files)} images in {out}")
    return files


def spread(doc, left, out):
    """Pages `left` (even page number, 0-based odd) and `left + 1` side by side."""
    a, b = doc[left], doc[left + 1]
    w, h = a.rect.width, a.rect.height
    page = fitz.open().new_page(width=w * 2 + 12, height=h)
    page.draw_rect(page.rect, fill=(0.85, 0.85, 0.85), color=None)
    page.show_pdf_page(fitz.Rect(0, 0, w, h), doc, left)
    page.show_pdf_page(fitz.Rect(w + 12, 0, w * 2 + 12, h), doc, left + 1)
    f = os.path.join(out, f"s{left + 1:03d}-{left + 2:03d}.png")
    page.get_pixmap(dpi=DPI).save(f)
    return f


def main(argv=None):
    argv = argv if argv is not None else sys.argv[2:]
    editions = [a for a in argv if not a.replace(",", "").replace("-", "").isdigit()] or ["book", "technical", "slides"]
    nums = [a for a in argv if a not in editions]
    wanted = None
    if nums:
        wanted = []
        for part in ",".join(nums).split(","):
            lo, _, hi = part.partition("-")
            wanted += list(range(int(lo) - 1, int(hi or lo)))
    for e in editions:
        if os.path.exists(pdf_for(e)):
            render(e, wanted)
        else:
            print(f"qa: {e}: no {pdf_for(e)} yet")


if __name__ == "__main__":
    main(sys.argv[1:])
