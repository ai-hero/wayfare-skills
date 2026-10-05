"""The A.I. Hero .potx, opened through `deck_lib.open_template`, and the few things python-pptx
does not do for a template's placeholders: keep the layout's styling while filling them, shrink
text the way PowerPoint's autofit would, carry the slide number, and fill the layout's one
non-placeholder label (the Picture layout's figure label)."""
import copy
import os
import sys
from functools import lru_cache

from PIL import Image, ImageFont
from pptx.util import Emu

import paths

sys.path.insert(0, paths.REPORT)
import deck_lib  # noqa: E402

TEMPLATE = os.path.join(paths.ANALYSIS, "A.I. Hero.potx")
BRAND = "A.I. HERO, INC.  /  ARCHITECTING A SOFTWARE FACTORY"
FONT_DIRS = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts"]
# The theme names Geist Light (text) and Geist Mono Light (labels); measurement needs the files.
FACES = {"Geist Light": "Geist-Light.ttf", "Geist Mono Light": "GeistMono-Light.ttf"}
NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class FitError(Exception):
    pass


def open_deck():
    prs = deck_lib.open_template(TEMPLATE, BRAND)
    for layout in prs.slide_layouts:
        for sh in layout.shapes:
            # Sample text on non-placeholder shapes ("FIGURE LABEL", "List num" 01 to 04) would print
            # on every slide of the layout; each slide gets its own copy of the shape instead
            # (`copy_label`), so a list continued on a second slide numbers on and an empty slot is blank.
            if sh.name == "Figure label" or sh.name.startswith("List num "):
                sh.text_frame.paragraphs[0].runs[0].text = ""
    return prs


def add(prs, name):
    layout = deck_lib.layout(prs, name)
    slide = prs.slides.add_slide(layout)
    for sh in layout.placeholders:
        # python-pptx leaves the slide-number placeholder behind; the template's footer expects it.
        if sh.placeholder_format.type is not None and sh.placeholder_format.idx == 12:
            slide.shapes._spTree.append(copy.deepcopy(sh._element))
    return slide


def ph(slide, idx):
    return deck_lib.ph(slide, idx)


def drop(slide, *idxs):
    for i in idxs:
        deck_lib.drop_placeholder(slide, i)


@lru_cache(maxsize=None)
def _font(face, pt):
    for d in FONT_DIRS:
        p = os.path.join(d, FACES.get(face, FACES["Geist Light"]))
        if os.path.exists(p):
            return ImageFont.truetype(p, size=int(round(pt * 10)))
    raise SystemExit(f"slides: {face} is not installed in {FONT_DIRS}; the template's theme names it")


def _lines(text, face, pt, width_pt, caps):
    f = _font(face, pt)
    n, line = 1, ""
    for word in (text.upper() if caps else text).split():
        trial = f"{line} {word}".strip()
        if f.getlength(trial) / 10 <= width_pt or not line:
            line = trial
        else:
            n, line = n + 1, word
    return n


def _style(layout_ph):
    """Size, line spacing, face and caps from the layout placeholder's first-level style."""
    lvl = layout_ph._element.find(f".//{NS}lstStyle/{NS}lvl1pPr")
    rpr = lvl.find(f"{NS}defRPr")
    spc = lvl.find(f"{NS}lnSpc/{NS}spcPct")
    latin = rpr.find(f"{NS}latin")
    return (int(rpr.get("sz")) / 100, int(spc.get("val")) / 100000 if spc is not None else 1.2,
            latin.get("typeface") if latin is not None else "Geist Light", rpr.get("cap") == "all")


def fill(slide, idx, text, min_scale=0.62, height=None):
    """Set the placeholder's text, inheriting every style from the layout. When it would overflow,
    record the shrink in `normAutofit` as PowerPoint does, so the file opens already fitted."""
    shape = ph(slide, idx)
    if height is not None:
        shape.left, shape.top, shape.width = shape.left, shape.top, shape.width
        shape.height = Emu(int(height * 914400))
    tf = shape.text_frame
    tf.text = text
    size, spacing, face, caps = _style(shape._base_placeholder)
    w = shape.width / 12700 * 0.97
    h = shape.height / 12700
    scale = 1.0
    while _lines(text, face, size * scale, w, caps) * size * scale * spacing * 1.17 > h + 1:
        scale -= 0.02
        if scale < min_scale:
            raise FitError(f"{shape.name}: does not fit at {min_scale:.0%}: {text[:70]}…")
    if scale < 1.0:
        body = tf._txBody.find(f"{NS}bodyPr")
        for child in list(body):
            body.remove(child)
        fit = body.makeelement(f"{NS}normAutofit", {"fontScale": str(int(scale * 100000))})
        body.append(fit)
    return scale


def lines(slide, idx, text):
    shape = ph(slide, idx)
    size, spacing, face, caps = _style(shape._base_placeholder)
    return _lines(text, face, size, shape.width / 12700 * 0.97, caps)


def picture(slide, idx, path):
    """Insert into the picture placeholder, then undo its fill-and-crop: a diagram must show whole,
    so the frame shrinks to the image's aspect inside the placeholder's box, centred."""
    box = ph(slide, idx)
    x, y, w, h = box.left, box.top, box.width, box.height
    pic = box.insert_picture(path)
    pic.crop_left = pic.crop_right = pic.crop_top = pic.crop_bottom = 0
    # The placeholder's dashed sample border is inherited by the picture; a figure has its own frame.
    pic.line.fill.background()
    # Diagrams drawn for print are taller than the placeholder's 2.4:1 box; give them the strip
    # between the top margin and the caption too, so their labels stay legible.
    caption = ph(slide, 0)
    top = min(y, int(0.45 * 914400))
    h = caption.top - int(0.15 * 914400) - top
    y = top
    iw, ih = Image.open(path).size
    s = min(w / iw, h / ih)
    pw, phh = int(iw * s), int(ih * s)
    pic.left, pic.top, pic.width, pic.height = x + (w - pw) // 2, y + (h - phh) // 2, pw, phh
    return pic


def copy_label(slide, name, text):
    """Copy the layout's own non-placeholder shape onto the slide with new text, so it keeps the
    template's position and style."""
    for sh in slide.slide_layout.shapes:
        if sh.name == name:
            slide.shapes._spTree.append(copy.deepcopy(sh._element))
            slide.shapes[-1].text_frame.paragraphs[0].runs[0].text = text
            return
    raise FitError(f"layout {slide.slide_layout.name!r} has no {name!r} shape")


def figure_label(slide, text):
    copy_label(slide, "Figure label", text)


def numbers(slide, prefix, start, count):
    for n in range(1, count + 1):
        copy_label(slide, f"{prefix}{n}", f"{start + n:02d}")
