"""Publication colors and redundant chart fills, applied before SVG, PDF and PNG editions diverge."""
import os
import re
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

DATA = {
    "#e93a61": ("#BA1B45", ""),
    "#f1839a": ("#AD4964", "/"),
    "#ed5f7e": ("#A52A4C", "-"),
    "#c62249": ("#7D1634", "x"),
    "#a5153e": ("#A5153E", "+"),
    "#383d49": ("#383D49", "\\"),
    "#c6c9d0": ("#6C7380", "."),
    "#7b8290": ("#5A6070", "+"),
    "#edeef1": ("#858B96", "o"),
}
TEXT = {"#666d7b": "#383D49", "#7b8290": "#383D49", "#e93a61": "#A5153E"}
STROKE = {"#c6c9d0": "#666D7B", "#7b8290": "#5A6070", "#e93a61": "#BA1B45"}


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
    ink = "#FFFFFF" if motif != "o" else "#0B0D14"
    if motif in (".", "o"):
        ET.SubElement(el, f"{{{SVG}}}circle", cx="3", cy="3", r="0.85", fill=ink)
    else:
        paths = {"/": "M-1,1 L1,-1 M0,6 L6,0 M5,7 L7,5",
                 "\\": "M-1,5 L1,7 M0,0 L6,6 M5,-1 L7,1",
                 "-": "M0,3 H6", "+": "M0,3 H6 M3,0 V6",
                 "x": "M0,0 L6,6 M0,6 L6,0"}
        ET.SubElement(el, f"{{{SVG}}}path", d=paths[motif], fill="none", stroke=ink,
                      attrib={"stroke-width": "0.8"})
    return f"url(#{ident})"


def label_backgrounds(root):
    bars = []
    for el in root.iter():
        fill = properties(el).get("fill") or el.get("fill", "")
        if not fill.startswith("url(#book-fill-"):
            continue
        if el.tag.endswith("}path"):
            values = re.findall(r"[-+]?[\d.]+", el.get("d", ""))
            if len(values) != 8:
                continue
            xs, ys = [float(x) for x in values[::2]], [float(y) for y in values[1::2]]
            bars.append((min(xs), min(ys), max(xs), max(ys)))
        elif el.tag.endswith("}rect"):
            x, y, w, h = (float(el.get(k, "0")) for k in ("x", "y", "width", "height"))
            bars.append((x, y, x + w, y + h))
    for parent in list(root.iter()):
        for el in list(parent):
            if not el.tag.endswith("}text") or not el.get("x") or not el.get("y"):
                continue
            style = properties(el)
            fill = (style.get("fill") or el.get("fill", "")).lower()
            if fill not in ("#0b0d14", "#383d49", "#ffffff"):
                continue
            x, y = float(el.get("x")), float(el.get("y"))
            if not any(a <= x <= c and b <= y <= d for a, b, c, d in bars):
                continue
            size = re.match(r"[\d.]+", style.get("font-size") or el.get("font-size", ""))
            if not size:
                continue
            size = float(size[0])
            width = len("".join(el.itertext())) * size * 0.62 + 4
            anchor = style.get("text-anchor") or el.get("text-anchor", "start")
            left = x - {"middle": width / 2, "end": width - 2}.get(anchor, 2)
            chip = ET.Element(f"{{{SVG}}}rect", x=str(left), y=str(y - size), width=str(width),
                              height=str(size * 1.3), rx="1", fill="#0B0D14" if fill == "#ffffff" else "#FFFFFF")
            if el.get("transform"):
                chip.set("transform", el.get("transform"))
            parent.insert(list(parent).index(el), chip)
    root.set("data-book-labels", "1")


def recolor(svg):
    root = ET.fromstring(svg)
    chart = any(el.get("id") == "figure_1" for el in root.iter())
    if root.get("data-book-contrast") == "1":
        if not chart or root.get("data-book-labels") == "1":
            return svg
        label_backgrounds(root)
        return ET.tostring(root, encoding="unicode") + "\n"
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
    fills = {}
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
        elif fill in TEXT:
            put(el, "fill", TEXT[fill])
        if stroke in STROKE:
            put(el, "stroke", "#858B96" if chart and stroke == "#c6c9d0" else STROKE[stroke])
    root.set("data-book-contrast", "1")
    if chart:
        label_backgrounds(root)
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


def prepare(files, folder):
    """Keep every companion synchronized; an old PNG would silently undo the SVG fix in the EPUB."""
    if not files.get("svg"):
        return files
    path = os.path.join(folder, files["svg"])
    with open(path, encoding="utf-8") as f:
        original = f.read()
    svg = recolor(original)
    if svg == original:
        return files
    import fitz
    import book

    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    width, height = dimensions(svg)
    stem = os.path.splitext(files["svg"])[0]
    pdf_path = os.path.join(folder, stem + ".pdf")
    markup = (f'<html><style>{book.font_faces()}@page{{size:{width}pt {height}pt;margin:0}}'
              f'html,body{{margin:0}}svg{{display:block;width:{width}pt;height:{height}pt}}'
              f'</style><body>{svg}</body></html>')
    book.weasy_html()(string=markup).write_pdf(pdf_path)
    with fitz.open(pdf_path) as pdf:
        zoom = 1800 / pdf[0].rect.width
        pdf[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(os.path.join(folder, stem + ".png"))
    if book.REFUSED:
        raise ValueError("artwork: refused resources: " + ", ".join(sorted(book.REFUSED)))
    return {**files, "pdf": stem + ".pdf", "png": stem + ".png"}
