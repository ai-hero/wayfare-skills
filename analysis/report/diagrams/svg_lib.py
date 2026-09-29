"""One visual grammar for the book's conceptual diagrams, written as SVG and rendered to PNG and PDF.

Every diagram module in this folder (`d_NN_MM_slug.py`) builds a Canvas and finishes it:

    import svg_lib as S
    c = S.Canvas(1400, 800)
    plane = c.group(40, 40, 1320, 300, "Control plane")
    a = c.node(80, 120, 260, 90, "person", "Owner", "defines value and risk")
    b = c.node(420, 120, 260, 90, "record", "Work item", ".plans/")
    c.arrow(a, b, "authority", "authorizes")
    S.finish(c, id="2.1", name="diagram-02-01-one-piece-of-work", caption="...", alt="...", source="...")

`finish` writes `<name>.svg`, `<name>.pdf` and `<name>.png` (2x) to `.analysis/diagrams/book/` and a
sidecar `<name>.json` with the caption, alt text and source note; `book_place.py` reads the sidecars.

The grammar, which every diagram keeps so the book reads as one set:

  node kinds   person · agent · record · policy · check · delivery · evidence · plain
  arrow kinds  flow (ink, filled head) · authority (pink, filled head) · dependency (grey, open head)
               · feedback (ink, dotted, filled head)
  target       anything proposed rather than observed is drawn `target=True`: dashed outline, muted text.
               Dashes mean "not yet", never a second kind of arrow; dotted is feedback.

Type scale (px on a 1400-wide canvas, printed at 6.5 in): title 30, label 22, small 17, mono 15. At that
width 22 px is about 10 pt in print, the floor the figures brief sets, so nothing goes smaller than SMALL.
PNG and PDF come from headless Chrome (the only SVG rasteriser on this machine); fonts are the installed
Geist family, with a system sans fallback in the SVG for a machine without it.
"""
import html
import json
import math
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, ".analysis", "diagrams", "book")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

INK, BODY, MUTED, RULE = "#0B0D14", "#383D49", "#666D7B", "#E3E5EA"
PINK, PINK_TINT, PINK_DARK = "#E93A61", "#FDE7EC", "#A5153E"
GREY, GREY_DARK, GREY_LIGHT, GREY_TINT = "#C6C9D0", "#383D49", "#DDE0E5", "#F3F4F6"
TEAL, TEAL_TINT = "#1F8A8A", "#E6F4F4"
FONT = "Geist, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Geist Mono', Menlo, monospace"
TITLE, LABEL, SMALL, MONO_SIZE = 30, 22, 17, 15

# fill, stroke, stroke width, text colour
KINDS = {
    "person": (PINK_TINT, PINK, 2, INK),
    "agent": ("#FFFFFF", INK, 2, INK),
    "record": (GREY_TINT, GREY_DARK, 1.5, INK),
    "policy": ("#FFFFFF", GREY_DARK, 1.5, INK),
    "check": ("#FFFFFF", INK, 2, INK),
    "delivery": (GREY_DARK, GREY_DARK, 1.5, "#FFFFFF"),
    "evidence": (TEAL_TINT, TEAL, 1.5, INK),
    "plain": ("none", "none", 0, INK),
}
ARROWS = {  # colour, width, dash
    "flow": (INK, 2, None),
    "authority": (PINK, 2.5, None),
    "dependency": (GREY_DARK, 1.5, None),
    "feedback": (INK, 2, "2 6"),
}
TARGET_DASH = "10 6"


def esc(s):
    return html.escape(str(s), quote=True)


def text_width(s, size, mono=False):
    """Geist is about 0.53 em per character, Geist Mono 0.6; wide enough for wrapping, never trusted for overlap."""
    return len(s) * size * (0.6 if mono else 0.53)


def wrap(s, width, size):
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and text_width(t, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


class Node:
    def __init__(self, x, y, w, h, kind, label):
        self.x, self.y, self.w, self.h, self.kind, self.label = x, y, w, h, kind, label

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def port(self, side):
        return {"left": (self.x, self.cy), "right": (self.x + self.w, self.cy),
                "top": (self.cx, self.y), "bottom": (self.cx, self.y + self.h)}[side]


class Canvas:
    def __init__(self, w=1400, h=800, background="#FFFFFF"):
        self.w, self.h, self.background = w, h, background
        self.body = []
        self.markers = set()

    # ---------------------------------------------------------------- primitives

    def raw(self, s):
        self.body.append(s)

    def text(self, x, y, s, size=LABEL, weight=400, anchor="start", color=INK, width=None, mono=False,
             line=1.25, halo=False, baseline="hanging"):
        """Text at (x, y); wrapped to `width` px when given. Returns the height used."""
        lines = wrap(s, width, size) if width else [str(s)]
        fam = MONO if mono else FONT
        extra = f' stroke="{self.background}" stroke-width="6" paint-order="stroke" stroke-linejoin="round"' if halo else ""
        for i, ln in enumerate(lines):
            self.raw(f'<text x="{x:.1f}" y="{y + i * size * line:.1f}" font-family="{fam}" font-size="{size}" '
                     f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}" dominant-baseline="{baseline}"'
                     f'{extra}>{esc(ln)}</text>')
        return len(lines) * size * line

    def rect(self, x, y, w, h, fill="none", stroke=INK, width=1.5, r=8, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{width}"{d}/>')

    def line(self, x1, y1, x2, y2, stroke=RULE, width=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
                 f'stroke-width="{width}"{d} stroke-linecap="round"/>')

    def circle(self, cx, cy, r, fill=PINK, stroke="none", width=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{d}/>')

    # ---------------------------------------------------------------- grammar

    def node(self, x, y, w, h, kind, label, sub=None, target=False, size=LABEL, align="center"):
        """A box of one grammar kind, its label centred (or left-aligned), an optional muted second line."""
        fill, stroke, sw, color = KINDS[kind]
        if target:
            fill, color = "none", MUTED
            stroke = stroke if stroke != "none" else MUTED
            sw = max(sw, 1.5)
        dash = f' stroke-dasharray="{TARGET_DASH}"' if target else ""
        if kind == "check":
            k = min(18, h / 3)
            pts = f"{x + k},{y} {x + w - k},{y} {x + w},{y + h / 2} {x + w - k},{y + h} {x + k},{y + h} {x},{y + h / 2}"
            self.raw(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash} stroke-linejoin="round"/>')
        elif kind == "record":
            f = 16
            path = (f"M{x},{y} H{x + w - f} L{x + w},{y + f} V{y + h} H{x} Z")
            self.raw(f'<path d="{path}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash} stroke-linejoin="round"/>')
            self.raw(f'<path d="M{x + w - f},{y} V{y + f} H{x + w}" fill="none" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
        elif kind == "delivery":
            self.rect(x, y, w, h, fill, stroke, sw, r=h / 2, dash=TARGET_DASH if target else None)
        elif kind == "person":
            self.rect(x, y, w, h, fill, stroke, sw, r=22, dash=TARGET_DASH if target else None)
        elif kind == "plain":
            pass
        else:
            self.rect(x, y, w, h, fill, stroke, sw, r=8, dash=TARGET_DASH if target else None)
        if kind == "policy" and not target:
            self.raw(f'<rect x="{x:.1f}" y="{y:.1f}" width="6" height="{h:.1f}" fill="{GREY_DARK}"/>')
        pad = 14 if kind != "policy" else 20
        inner = w - 2 * pad
        lines = wrap(label, inner, size)
        subs = wrap(sub, inner, SMALL) if sub else []
        total = len(lines) * size * 1.2 + (len(subs) * SMALL * 1.25 + 6 if subs else 0)
        ty = y + (h - total) / 2
        ax = x + w / 2 if align == "center" else x + pad
        anchor = "middle" if align == "center" else "start"
        for i, ln in enumerate(lines):
            self.raw(f'<text x="{ax:.1f}" y="{ty + i * size * 1.2:.1f}" font-family="{FONT}" font-size="{size}" '
                     f'font-weight="500" fill="{color}" text-anchor="{anchor}" dominant-baseline="hanging">{esc(ln)}</text>')
        for i, ln in enumerate(subs):
            self.raw(f'<text x="{ax:.1f}" y="{ty + len(lines) * size * 1.2 + 6 + i * SMALL * 1.25:.1f}" font-family="{FONT}" '
                     f'font-size="{SMALL}" fill="{MUTED if color != "#FFFFFF" else GREY_LIGHT}" text-anchor="{anchor}" '
                     f'dominant-baseline="hanging">{esc(ln)}</text>')
        return Node(x, y, w, h, kind, label)

    def group(self, x, y, w, h, label=None, target=False, fill="none", stroke=GREY):
        """A region holding nodes: a plane, a repository, a boundary. Label sits inside the top-left corner."""
        self.rect(x, y, w, h, fill, stroke, 1.5, r=14, dash=TARGET_DASH if target else None)
        if label:
            self.text(x + 16, y + 12, label.upper(), size=MONO_SIZE, mono=True, color=MUTED)
        return Node(x, y, w, h, "group", label)

    def _marker(self, kind, target):
        color, _, _ = ARROWS[kind]
        mid = f"m-{kind}"
        if mid not in self.markers:
            self.markers.add(mid)
        return mid

    def arrow(self, a, b, kind="flow", label=None, target=False, via=(), ports=None, label_at=0.5, label_dy=-10,
              width=None):
        """From node (or (x, y)) a to b, through `via` corner points. Ports pick the side each end leaves
        from; by default the nearest sides. The label sits on the line with a background halo."""
        pa = a if isinstance(a, tuple) else None
        pb = b if isinstance(b, tuple) else None
        if pa is None or pb is None:
            # A bare point stands in for a node at that point, so a node-to-point arrow picks its side too.
            na = a if pa is None else Node(a[0], a[1], 0, 0, "plain", "")
            nb = b if pb is None else Node(b[0], b[1], 0, 0, "plain", "")
            sa, sb = ports or self._sides(na, nb, via)
            pa = pa or a.port(sa)
            pb = pb or b.port(sb)
        pts = [pa, *via, pb]
        color, w, dash = ARROWS[kind]
        w = width or w
        d = dash if dash else (TARGET_DASH if target else None)
        dd = f' stroke-dasharray="{d}"' if d else ""
        path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.raw(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{w}"{dd} stroke-linecap="round" '
                 f'stroke-linejoin="round" marker-end="url(#{self._marker(kind, target)})"/>')
        if label:
            x, y = self._along(pts, label_at)
            self.text(x, y + label_dy, label, size=SMALL, anchor="middle", color=MUTED if target else BODY, halo=True,
                      baseline="middle")

    @staticmethod
    def _sides(a, b, via):
        tx, ty = (via[0] if via else (b.cx, b.cy))
        dx, dy = tx - a.cx, ty - a.cy
        sa = ("right" if dx > 0 else "left") if abs(dx) * (a.h or 1) > abs(dy) * (a.w or 1) else ("bottom" if dy > 0 else "top")
        fx, fy = (via[-1] if via else (a.cx, a.cy))
        dx, dy = fx - b.cx, fy - b.cy
        sb = ("right" if dx > 0 else "left") if abs(dx) * (b.h or 1) > abs(dy) * (b.w or 1) else ("bottom" if dy > 0 else "top")
        return sa, sb

    @staticmethod
    def _along(pts, t):
        segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        total = sum(segs) or 1
        want = t * total
        for i, ((x1, y1), (x2, y2), s) in enumerate(zip(pts, pts[1:], segs)):
            if want <= s or i == len(segs) - 1:
                f = (want / s) if s else 0
                return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
            want -= s
        return pts[-1]

    def legend(self, x, y, kinds=(), arrows=(), target=False, cols=4, cell=300):
        """Small key: node kinds as swatches, arrow kinds as short lines, and the dashed 'proposed' mark."""
        items = [("node", k) for k in kinds] + [("arrow", k) for k in arrows] + ([("target", None)] if target else [])
        for i, (t, k) in enumerate(items):
            cx, cy = x + (i % cols) * cell, y + (i // cols) * 34
            if t == "node":
                fill, stroke, sw, _ = KINDS[k]
                self.rect(cx, cy, 34, 22, fill, stroke, sw, r=6 if k != "person" else 11)
                self.text(cx + 44, cy + 3, k.capitalize(), size=SMALL, color=BODY)
            elif t == "arrow":
                self.arrow((cx, cy + 11), (cx + 40, cy + 11), k)
                self.text(cx + 52, cy + 3, k.capitalize(), size=SMALL, color=BODY)
            else:
                self.rect(cx, cy, 34, 22, "none", MUTED, 1.5, r=6, dash=TARGET_DASH)
                self.text(cx + 44, cy + 3, "Proposed, not yet observed", size=SMALL, color=BODY)

    # ---------------------------------------------------------------- output

    def svg(self, title=""):
        defs = []
        for mid in sorted(self.markers):
            kind = mid[2:]
            color, _, _ = ARROWS[kind]
            if kind == "dependency":
                defs.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
                            f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="{color}" '
                            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker>')
            else:
                defs.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
                            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="{color}"/></marker>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{esc(title)}">')
        return "\n".join([head, f"<title>{esc(title)}</title>", "<defs>", *defs, "</defs>",
                          f'<rect width="{self.w}" height="{self.h}" fill="{self.background}"/>', *self.body, "</svg>"])


def render(svg_path, png_path, pdf_path, w, h):
    """PNG at 2x and a page-sized PDF, through headless Chrome; the HTML wrapper sets the page to the canvas."""
    html_path = svg_path[:-4] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{w}px {h}px;margin:0}}'
                f'html,body{{margin:0;background:#fff}}img{{display:block;width:{w}px;height:{h}px}}</style></head>'
                f'<body><img src="{os.path.basename(svg_path)}"></body></html>')
    base = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run"]
    subprocess.run(base + ["--force-device-scale-factor=2", f"--window-size={w},{h}", f"--screenshot={png_path}",
                           f"file://{html_path}"], check=True, capture_output=True)
    subprocess.run(base + ["--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
                   check=True, capture_output=True)
    os.remove(html_path)


def finish(canvas, id, name, caption, alt, source, kind="diagram"):
    """Write the assets and the sidecar the placement script reads. Returns the SVG path."""
    os.makedirs(OUT, exist_ok=True)
    svg_path = os.path.join(OUT, f"{name}.svg")
    if canvas.body:
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(canvas.svg(alt))
        render(svg_path, svg_path[:-4] + ".png", svg_path[:-4] + ".pdf", canvas.w, canvas.h)
    with open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"id": id, "kind": kind, "name": name, "caption": caption, "alt": alt, "source": source,
                   "width": canvas.w, "height": canvas.h}, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(svg_path if canvas.body else os.path.join(OUT, f"{name}.json"))
    return svg_path
