"""Publication colors, plus a hatch per chart series so series still separate in grayscale print, on
e-ink and for colour-blind readers, applied to the SVG before its PDF and PNG are derived from it."""
import os
import re
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Keys are lowercase because every fill is lowered before lookup; values are uppercase. Outputs such
# as #A5153E and #383D49 are also keys, so a second pass would map them again: see MARKER.
DATA = {
    "#e93a61": ("#BA1B45", ""),
    "#f1839a": ("#AD4964", "/"),
    "#ed5f7e": ("#A52A4C", "-"),
    "#c62249": ("#7D1634", "x"),
    "#a5153e": ("#A5153E", "+"),
    "#383d49": ("#383D49", "\\"),
    "#c6c9d0": ("#6C7380", "."),
    "#a3a8b3": ("#636A78", "="),
    "#7b8290": ("#5A6070", "|"),
    "#edeef1": ("#858B96", "o"),
}
TEXT = {"#666d7b": "#383D49", "#7b8290": "#383D49", "#e93a61": "#A5153E"}
STROKE = {"#c6c9d0": "#666D7B", "#7b8290": "#5A6070", "#e93a61": "#BA1B45"}
# Ink, white and the background tints are left as they are; any other chart fill is reported.
NEUTRAL = {"#0b0d14", "#ffffff", "#f4f5f8", "#fef1f4", "#1a1e29"}
LABEL_INK = {"#0b0d14": "#FFFFFF", "#383d49": "#FFFFFF", "#1a1e29": "#FFFFFF", "#ffffff": "#0B0D14"}
MOTIFS = {"/": "M-1,1 L1,-1 M0,6 L6,0 M5,7 L7,5",
          "\\": "M-1,5 L1,7 M0,0 L6,6 M5,-1 L7,1",
          "-": "M0,3 H6", "=": "M0,1.5 H6 M0,4.5 H6", "|": "M3,0 V6", "+": "M0,3 H6 M3,0 V6",
          "x": "M0,0 L6,6 M0,6 L6,0"}
# Bump when the mapping changes. An SVG carrying an older value cannot be safely mapped again.
MARKER, VERSION = "data-book-artwork", "3"

_motifs = [m for _, m in DATA.values() if m]
if len(set(_motifs)) != len(_motifs) or not set(_motifs) <= {*MOTIFS, ".", "o"}:
    raise ValueError("artwork: every patterned series needs its own known motif")
if any(k != k.lower() for k in (*DATA, *TEXT, *STROKE, *NEUTRAL, *LABEL_INK)):
    raise ValueError("artwork: color keys must be lowercase")


def ratio(a, b):
    def lum(color):
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return sum(w * (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
                   for w, v in zip((0.2126, 0.7152, 0.0722), rgb))
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def properties(el):
    return dict(re.findall(r"([\w-]+):\s*([^;]+)", el.get("style", "")))


def put(el, name, value):
    style = properties(el)
    if name in style:
        style[name] = str(value)
        el.set("style", "; ".join(f"{k}: {v}" for k, v in style.items()))
    else:
        el.set(name, str(value))


def pattern(defs, color, motif, key):
    ident = "book-fill-" + key.removeprefix("#")
    el = ET.SubElement(defs, f"{{{SVG}}}pattern", id=ident, patternUnits="userSpaceOnUse",
                       width="6", height="6")
    ET.SubElement(el, f"{{{SVG}}}rect", width="6", height="6", fill=color)
    if motif == ".":
        ET.SubElement(el, f"{{{SVG}}}circle", cx="3", cy="3", r="0.85", fill="#FFFFFF")
    elif motif == "o":
        ET.SubElement(el, f"{{{SVG}}}circle", cx="3", cy="3", r="1.6", fill="none", stroke="#0B0D14",
                      attrib={"stroke-width": "0.7"})
    else:
        ET.SubElement(el, f"{{{SVG}}}path", d=MOTIFS[motif], fill="none", stroke="#FFFFFF",
                      attrib={"stroke-width": "0.8"})
    return f"url(#{ident})"


def box(el):
    if el.tag.endswith("}rect"):
        x, y, w, h = (float(el.get(k, "0")) for k in ("x", "y", "width", "height"))
        return x, y, x + w, y + h
    # Matplotlib draws a bar as `M x y L x y L x y L x y z`; any other outline is not a bar.
    values = re.findall(r"[-+]?[\d.]+", el.get("d", ""))
    if len(values) != 8:
        return None
    xs, ys = [float(x) for x in values[::2]], [float(y) for y in values[1::2]]
    return min(xs), min(ys), max(xs), max(ys)


def label_backgrounds(root, bars):
    """bars: (box, color, patterned). A label needs a chip on a hatch, or on a solid bar it fails."""
    for parent in list(root.iter()):
        for el in list(parent):
            if not el.tag.endswith("}text") or not el.get("x") or not el.get("y"):
                continue
            style = properties(el)
            fill = (style.get("fill") or el.get("fill", "")).lower()
            if fill not in LABEL_INK:
                continue
            x, y = float(el.get("x")), float(el.get("y"))
            under = [(color, patterned) for (a, b, c, d), color, patterned in bars if a <= x <= c and b <= y <= d]
            if not under or not any(p or ratio(fill.upper(), color) < 4.5 for color, p in under):
                continue
            size = re.match(r"[\d.]+", style.get("font-size") or el.get("font-size", ""))
            if not size:
                continue
            size = float(size[0])
            # 0.62em per character is Geist Mono's advance; a proportional estimate clips digits.
            width = len("".join(el.itertext())) * size * 0.62 + 4
            anchor = style.get("text-anchor") or el.get("text-anchor", "start")
            left = x - {"middle": width / 2, "end": width - 2}.get(anchor, 2)
            chip = ET.Element(f"{{{SVG}}}rect", x=str(left), y=str(y - size), width=str(width),
                              height=str(size * 1.3), rx="1", fill=LABEL_INK[fill])
            if el.get("transform"):
                chip.set("transform", el.get("transform"))
            # Before the text: SVG paints in document order, so a later chip would cover the label.
            parent.insert(list(parent).index(el), chip)


def recolor(svg, unmapped=None):
    """The SVG mapped to the book's palette. Chart fills outside the palette are added to `unmapped`."""
    root = ET.fromstring(svg)
    if root.get(MARKER) == VERSION:
        return svg
    if root.get(MARKER) or root.get("data-book-contrast"):
        raise ValueError("artwork: SVG was prepared by an older palette; re-export it from its source")
    # Matplotlib's SVG backend always writes <g id="figure_1">; nothing else tells a chart from a drawing.
    chart = any(el.get("id") == "figure_1" for el in root.iter())
    if not chart and not any(c in svg.lower() for c in (*TEXT, *STROKE)):
        return svg
    original_patterns = {}
    for el in root.iter(f"{{{SVG}}}pattern"):
        rect = el.find(f"{{{SVG}}}rect")
        if rect is not None:
            original_patterns[f"url(#{el.get('id')})"] = (properties(rect).get("fill") or rect.get("fill", "")).lower()
    defs = root.find(f"{{{SVG}}}defs")
    if defs is None:
        defs = ET.SubElement(root, f"{{{SVG}}}defs")
    fills, bars = {}, []
    for el in list(root.iter()):
        tag = el.tag.rsplit("}", 1)[-1]
        style = properties(el)
        fill = (style.get("fill") or el.get("fill", "")).lower()
        stroke = (style.get("stroke") or el.get("stroke", "")).lower()
        if tag in ("text", "tspan"):
            if fill in TEXT:
                put(el, "fill", TEXT[fill])
            weight = style.get("font-weight") or el.get("font-weight", "400")
            if weight in ("light", "200", "300"):
                put(el, "font-weight", "400")
        elif chart and tag in ("path", "rect", "circle", "use", "polygon"):
            base = original_patterns.get(fill, fill)
            if base in DATA:
                color, motif = DATA[base]
                if motif and base not in fills:
                    fills[base] = pattern(defs, color, motif, base)
                put(el, "fill", fills[base] if motif else color)
                put(el, "stroke", "#0B0D14")
                put(el, "stroke-width", "0.65")
                stroke = ""
                edges = box(el) if tag in ("path", "rect") else None
                if edges:
                    bars.append((edges, color, bool(motif)))
            elif re.fullmatch(r"#[0-9a-f]{6}", base) and base not in NEUTRAL and unmapped is not None:
                unmapped.add(base)
        elif fill in TEXT:
            put(el, "fill", TEXT[fill])
        if stroke in STROKE:
            put(el, "stroke", "#858B96" if chart and stroke == "#c6c9d0" else STROKE[stroke])
    if chart:
        label_backgrounds(root, bars)
    root.set(MARKER, VERSION)
    return ET.tostring(root, encoding="unicode") + "\n"


def dimensions(svg):
    root = ET.fromstring(svg)
    values = []
    for name in ("width", "height"):
        m = re.fullmatch(r"([\d.]+)(pt|px|in|cm|mm)?", root.get(name, ""))
        if not m:
            raise ValueError(f"artwork: SVG needs an absolute {name}")
        values.append(float(m[1]) * {None: 0.75, "px": 0.75, "pt": 1, "in": 72,
                                     "cm": 72 / 2.54, "mm": 72 / 25.4}[m[2]])
    return values


def warn_stderr(msg):
    print(f"warn: {msg}", file=sys.stderr)


def prepare(files, folder, raster=True, warn=warn_stderr):
    """When the SVG is recolored, derive its PDF (and PNG when `raster`) from it: kindle.py prefers
    the PNG, so a stale one would ship the old colors in the EPUB. The SVG is written last, so a
    failed render never leaves a marked SVG beside stale companions."""
    if not files.get("svg"):
        return files
    path = os.path.join(folder, files["svg"])
    with open(path, encoding="utf-8") as f:
        original = f.read()
    unmapped = set()
    svg = recolor(original, unmapped)
    if unmapped:
        warn(f"artwork: {files['svg']} has chart fills outside the book palette, left unpatterned: "
             + ", ".join(sorted(unmapped)))
    if svg == original and MARKER not in original:
        return files
    import fitz
    import book

    width, height = dimensions(svg)
    stem = os.path.splitext(files["svg"])[0]
    out = {**files, "pdf": stem + ".pdf"}
    markup = (f'<html><style>{book.font_faces()}@page{{size:{width}pt {height}pt;margin:0}}'
              f'html,body{{margin:0}}svg{{display:block;width:{width}pt;height:{height}pt}}'
              f'</style><body>{svg}</body></html>')
    refused = set(book.REFUSED)
    pdf_path = os.path.join(folder, out["pdf"])
    book.weasy_html()(string=markup).write_pdf(pdf_path)
    if book.REFUSED - refused:
        raise ValueError(f"artwork: {files['svg']} refused resources: " + ", ".join(sorted(book.REFUSED - refused)))
    if raster:
        out["png"] = stem + ".png"
        with fitz.open(pdf_path) as pdf:
            zoom = 1800 / pdf[0].rect.width
            pdf[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(os.path.join(folder, out["png"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out
