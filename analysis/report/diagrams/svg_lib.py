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

Type scale (px on a 1400-wide canvas): title 34, label 28, small 24, mono 24. The book prints the canvas
about 5.65 in wide, so 1 px is about 0.29 pt: label about 8 pt, small and mono about 7 pt, the floor for
print. Nothing goes smaller than SMALL. A box too small for its words is reported by `finish` (OVERFLOW);
the fix is a bigger box, never fewer words.
PNG and PDF come from headless Chrome (the only SVG rasteriser on this machine); fonts are the installed
Geist family, with a system sans fallback in the SVG for a machine without it.
"""
import html
import json
import math
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, ".analysis", "diagrams", "book")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Light-theme values of the design system's tokens (design-system/src/styles.css, ds-version
# 2026.09.26-4). The system has two families only, the ink ramp and one rose ramp (every named hue
# aliases the rose); a third hue here would be off-system, which is why evidence is dark rose, not teal.
INK, BODY, MUTED, RULE = "#0B0D14", "#383D49", "#666D7B", "#C6C9D0"  # ink-figure, -body, -meta, -line
PINK, PINK_TINT, PINK_DARK = "#E93A61", "#FEF1F4", "#A5153E"  # pal-300, accent-tint, pal-500
GREY, GREY_DARK, GREY_LIGHT, GREY_TINT = "#C6C9D0", "#7B8290", "#C6C9D0", "#F4F5F8"  # ink-line, -quiet, -line, -raise
EVIDENCE, EVIDENCE_TINT = INK, "#FFFFFF"  # the system's `success` tone is ink, not a hue
WELL = GREY_TINT  # bg-muted: every diagram sits on the sunken well, groups on white sub-wells
RADIUS = 9  # rounded-sm (4px) at the ~2.3 canvas px per CSS px this canvas prints at
TRACK_EYEBROW, TRACK_LABEL = 0.1, 0.06  # --tracking-eyebrow, --tracking-label, in em
FONT = "Geist, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Geist Mono', Menlo, monospace"
TITLE, LABEL, SMALL, MONO_SIZE = 34, 28, 24, 24
# Arrow labels are tracked mono capitals; caps at 21 px stand as tall as 24 px lowercase, and keep the
# wider mono line from running into the boxes an arrow passes between.
ARROW_LABEL = 21

# Each kind is one of the design system's DiagramNode tones (diagram.tsx `diagramTone`):
#   person accent · agent agentic (dashed: the system's mark for probabilistic, model-driven work)
#   record muted · policy default · check default with the gate glyph · evidence success with a check glyph
#   delivery the solid fill tone.
# fill, stroke, stroke width, title colour, dash
AGENT_DASH = "7 6"
KINDS = {
    "person": (PINK_TINT, PINK, 2, PINK_DARK, None),
    "agent": ("#FFFFFF", PINK, 2, PINK_DARK, AGENT_DASH),
    "record": ("#FFFFFF", GREY, 2, INK, None),
    "policy": ("#FFFFFF", GREY_DARK, 2, INK, None),
    "check": ("#FFFFFF", GREY_DARK, 2, INK, None),
    "delivery": (INK, INK, 2, "#FFFFFF", None),
    "evidence": (EVIDENCE_TINT, EVIDENCE, 2, INK, None),
    "plain": ("none", "none", 0, INK, None),
}
GLYPH = {"check": "gate", "evidence": "tick"}
ARROWS = {  # colour, width, dash: DiagramArrow strokes in muted-foreground; authority keeps the accent
    "flow": (MUTED, 2.5, None),
    "authority": (PINK, 2.5, None),
    "dependency": (GREY_DARK, 2, None),
    "feedback": (MUTED, 2.5, "1 7"),
}
# Proposed work keeps its long dash but takes the muted tone, so it never reads as the agentic short dash.
TARGET_DASH = "12 7"


# Inner padding per kind: the policy bar and the check's angled ends take room the words must not enter.
PAD = {"check": 34, "evidence": 34}

# Boxes whose words do not fit, collected while drawing and reported by `finish`.
OVERFLOW = []
# Clearance an arrow label keeps from a box edge, a group label or another arrow label, in px.
CLEAR = 6


def esc(s):
    return html.escape(str(s), quote=True)


def text_width(s, size, mono=False, tracking=0.0):
    """Geist is about 0.53 em per character, Geist Mono 0.6, plus any tracking; wide enough for wrapping, never trusted for overlap."""
    return len(s) * size * ((0.6 if mono else 0.53) + tracking)


def wrap(s, width, size, mono=False, tracking=0.0):
    """Greedy line breaks at spaces; a single word wider than the line also breaks after its hyphens
    (infrastructure-/environments), so a long repository name stays inside its box."""
    pieces = []  # (text, joins to the previous piece without a space)
    for w in str(s).split():
        parts = re.findall(r"[^-]+-|[^-]+$|-", w) if text_width(w, size, mono, tracking) > width and "-" in w else [w]
        pieces += [(p, i > 0) for i, p in enumerate(parts)]
    lines, cur = [], ""
    for p, glued in pieces:
        t = (cur + ("" if glued else " ") + p).strip()
        if cur and text_width(t, size, mono, tracking) > width:
            lines.append(cur)
            cur = p
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def need(w, label, sub=None, kind="agent", size=None):
    """The height a node of width `w` needs for its words, so a module can size boxes from content."""
    size = size or LABEL
    pad = PAD.get(kind, 16)
    inner = w - 2 * pad
    total = len(wrap(label, inner, size)) * size * 1.15
    if sub:
        total += len(wrap(sub, inner, SMALL)) * SMALL * 1.2 + 6
    # A node with a glyph keeps the glyph's corner free: a word too long to centre clear of it starts below it.
    return total + (28 if kind != "plain" else 4) + (18 if kind in GLYPH else 0)


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
    def __init__(self, w=1400, h=800, background=WELL):
        # Chrome's --window-size takes integers only; a float silently renders a default-sized window.
        self.w, self.h, self.background = math.ceil(w), math.ceil(h), background
        self.body = []
        self.markers = set()
        self.groups = []  # white sub-wells; a label's halo takes the ground it sits on
        # Boxes `collisions` compares: node outlines, the words inside them, group labels, arrow labels and
        # arrow paths. Widths come from `text_width`, an estimate, so the check pads by CLEAR.
        self.nodes, self.words, self.group_labels, self.arrow_labels, self.paths = [], [], [], [], []
        self.glyphs = []

    # ---------------------------------------------------------------- primitives

    def raw(self, s):
        self.body.append(s)

    def ground(self, x, y):
        """The fill under a point: white inside a group's sub-well, the well outside."""
        inside = [g for g in self.groups if g.x <= x <= g.x + g.w and g.y <= y <= g.y + g.h]
        return inside[-1].fill if inside else self.background

    def text(self, x, y, s, size=LABEL, weight=300, anchor="start", color=INK, width=None, mono=False,
             line=1.25, halo=False, baseline="hanging", tracking=0.0, upper=False):
        """Text at (x, y); wrapped to `width` px when given. Returns the height used. `upper` is the
        design system's text-transform, not a change of words."""
        s = str(s).upper() if upper else str(s)
        lines = wrap(s, width, size, mono, tracking) if width else [s]
        fam = MONO if mono else FONT
        extra = (f' stroke="{self.ground(x, y)}" stroke-width="10" paint-order="stroke" stroke-linejoin="round"'
                 if halo else "")
        ls = f' letter-spacing="{tracking}em"' if tracking else ""
        for i, ln in enumerate(lines):
            self.raw(f'<text x="{x:.1f}" y="{y + i * size * line:.1f}" font-family="{fam}" font-size="{size}" '
                     f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}" dominant-baseline="{baseline}"'
                     f'{ls}{extra}>{esc(ln)}</text>')
        used = len(lines) * size * line
        if baseline == "hanging":
            # Text placed after a key that grew must stay on the canvas rather than run off its edge.
            self.h = max(self.h, math.ceil(y + used + 16))
        return used

    def rect(self, x, y, w, h, fill="none", stroke=INK, width=2, r=RADIUS, dash=None):
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
        fill, stroke, sw, color, kdash = KINDS[kind]
        if target:
            fill, color, kdash = "#FFFFFF", MUTED, TARGET_DASH
            stroke = GREY_DARK if kind not in ("plain",) else MUTED
        if kind == "delivery":
            # A pill while short; a tall box keeps its round ends without turning into a circle the words spill out of.
            self.rect(x, y, w, h, fill, stroke, sw, r=min(h / 2, 44), dash=kdash)
        elif kind != "plain":
            self.rect(x, y, w, h, fill, stroke, sw, dash=kdash)
        pad = PAD.get(kind, 16)
        inner = w - 2 * pad
        lines = wrap(label, inner, size)
        subs = wrap(sub, inner, SMALL) if sub else []
        total = len(lines) * size * 1.15 + (len(subs) * SMALL * 1.2 + 6 if subs else 0)
        if total > h - 12 and kind != "plain" or kind == "plain" and total > h + 4:
            OVERFLOW.append(f"{label!r}: needs {total + 12:.0f} px of height, has {h:.0f}")
        ty = y + (h - total) / 2
        ax = x + w / 2 if align == "center" else x + pad
        if GLYPH.get(kind) and not target and lines:
            left = min((ax - text_width(ln, size) / 2) if align == "center" else ax for ln in lines[:1])
            if left < x + 30 and ty < y + 31:
                ty = y + 31
                if ty + total > y + h - 6:
                    OVERFLOW.append(f"{label!r}: needs {ty - y + total + 6:.0f} px of height to clear its glyph, has {h:.0f}")
        anchor = "middle" if align == "center" else "start"
        for i, ln in enumerate(lines):
            lw = text_width(ln, size)
            lx = ax - lw / 2 if align == "center" else ax
            self.words.append((label, (lx, ty + i * size * 1.15, lw, size)))
            self.raw(f'<text x="{ax:.1f}" y="{ty + i * size * 1.15:.1f}" font-family="{FONT}" font-size="{size}" '
                     f'font-weight="400" fill="{color}" text-anchor="{anchor}" dominant-baseline="hanging">{esc(ln)}</text>')
        for i, ln in enumerate(subs):
            self.raw(f'<text x="{ax:.1f}" y="{ty + len(lines) * size * 1.15 + 6 + i * SMALL * 1.2:.1f}" font-family="{FONT}" '
                     f'font-size="{SMALL}" font-weight="300" fill="{MUTED if color != "#FFFFFF" else GREY_LIGHT}" '
                     f'text-anchor="{anchor}" dominant-baseline="hanging">{esc(ln)}</text>')
        g = GLYPH.get(kind)
        if g and not target:
            self.glyph(g, x + 17, y + 17, INK, r=6)
            self.glyphs.append((label, (x + 9, y + 9, 16, 16)))
        n = Node(x, y, w, h, kind, label)
        if kind != "plain":
            self.nodes.append(n)
        return n

    def glyph(self, kind, cx, cy, color, r=9):
        """The two marks the system's diagrams use inside a node: the gate diamond and the success tick."""
        if kind == "gate":
            self.raw(f'<rect x="{cx - r * 0.7:.1f}" y="{cy - r * 0.7:.1f}" width="{r * 1.4:.1f}" height="{r * 1.4:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2" transform="rotate(45 {cx:.1f} {cy:.1f})"/>')
        else:
            self.raw(f'<path d="M{cx - r:.1f},{cy:.1f} L{cx - r * 0.3:.1f},{cy + r * 0.7:.1f} L{cx + r:.1f},{cy - r * 0.8:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')

    def group(self, x, y, w, h, label=None, target=False, fill="#FFFFFF", stroke=GREY, label_x=18, label_w=None):
        """A region holding nodes (a plane, a repository, a boundary): the system's DiagramGroup, a white
        sub-well with a hairline. Label sits inside the top-left corner in the eyebrow style."""
        fill = "#FFFFFF" if fill in ("none", None) else fill
        self.rect(x, y, w, h, fill, GREY_DARK if target else stroke, 2, dash=TARGET_DASH if target else None)
        node = Node(x, y, w, h, "group", label)
        node.fill = fill
        self.groups.append(node)
        if label:
            # `label_x` moves the label along the top edge, clear of arrows that enter the group there.
            lw_max = label_w or w - label_x - 18
            used = self.text(x + label_x, y + 14, label, size=ARROW_LABEL, mono=True, color=MUTED, width=lw_max,
                             tracking=TRACK_LABEL, upper=True)
            lines = wrap(label.upper(), lw_max, ARROW_LABEL, True, TRACK_LABEL)
            lw = max(text_width(ln, ARROW_LABEL, True, TRACK_LABEL) for ln in lines)
            self.group_labels.append((label, (x + label_x, y + 14, lw, used)))
        return node

    def _marker(self, kind, target):
        color, _, _ = ARROWS[kind]
        mid = f"m-{kind}"
        if mid not in self.markers:
            self.markers.add(mid)
        return mid

    def arrow(self, a, b, kind="flow", label=None, target=False, via=(), ports=None, label_at=0.5, label_dy=-14,
              width=None, label_dx=0):
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
        self.paths.append((label or kind, pts))
        if label:
            x, y = self._along(pts, label_at)
            x += label_dx
            self.text(x, y + label_dy, label, size=ARROW_LABEL, anchor="middle", color=MUTED, halo=True,
                      baseline="middle", mono=True, tracking=TRACK_LABEL, upper=True)
            lw = text_width(label.upper(), ARROW_LABEL, True, TRACK_LABEL)
            self.arrow_labels.append((label, (x - lw / 2, y + label_dy - ARROW_LABEL / 2, lw, ARROW_LABEL), pts))

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
        """Key in the system's DiagramLegend style: a 46x32 specimen (box, line) and a tracked mono label.
        Returns the y below its last row, so text placed after a key follows it however many rows it took."""
        items = [("node", k) for k in kinds] + [("arrow", k) for k in arrows] + ([("target", None)] if target else [])
        # A cell fits its widest label; columns drop until the row fits the canvas.
        longest = max((text_width(("Proposed, not yet observed" if t == "target" else k).upper(), ARROW_LABEL, True,
                                  TRACK_LABEL) for t, k in items), default=0)
        cell = max(cell, 58 + longest + 28)
        cols = max(1, min(cols, int((self.w - x - 16) // cell)))
        # Fewer columns can mean another row; the canvas grows to keep it, rather than clip it.
        bottom = y + ((len(items) + cols - 1) // cols) * 46
        self.h = max(self.h, math.ceil(bottom + 20))
        for i, (t, k) in enumerate(items):
            cx, cy = x + (i % cols) * cell, y + (i // cols) * 46
            label = "Proposed, not yet observed" if t == "target" else k
            if t == "node":
                fill, stroke, sw, _, dash = KINDS[k]
                r = 16 if k == "delivery" else RADIUS - 3
                self.rect(cx, cy, 46, 32, fill, stroke, sw, r=r, dash=dash)
                if k in GLYPH:
                    self.glyph(GLYPH[k], cx + 23, cy + 16, INK, r=7)
            elif t == "arrow":
                self.arrow((cx, cy + 16), (cx + 46, cy + 16), k)
            else:
                self.rect(cx, cy, 46, 32, "#FFFFFF", GREY_DARK, 2, r=RADIUS - 3, dash=TARGET_DASH)
            self.text(cx + 58, cy + 16, label, size=ARROW_LABEL, mono=True, color=INK, tracking=TRACK_LABEL, upper=True,
                      baseline="middle")
        return bottom

    # ---------------------------------------------------------------- output

    def collisions(self):
        """Pairs of things that touch: an arrow label against a box, a group label, another arrow label or
        the words of a node; an arrow path through a group label; a glyph against its node's words."""
        def hit(a, b, pad=CLEAR):
            ax, ay, aw, ah = a
            bx, by, bw, bh = b
            return ax < bx + bw + pad and bx < ax + aw + pad and ay < by + bh + pad and by < ay + ah + pad

        def seg_hit(p, q, r):
            # An axis-aligned or diagonal segment against a rectangle, by sampling: paths here are a few long legs.
            n = max(2, int(math.dist(p, q) // 4))
            return any(hit((p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n, 0, 0), r, pad=2)
                       for i in range(n + 1))

        out = []
        boxes = [(n.label, (n.x, n.y, n.w, n.h)) for n in self.nodes]
        for i, (lab, box, pts) in enumerate(self.arrow_labels):
            for other, b in boxes + self.group_labels + self.words:
                if hit(box, b):
                    out.append(f"arrow label {lab!r} touches {other!r}")
            for other, b, _ in self.arrow_labels[i + 1:]:
                if hit(box, b):
                    out.append(f"arrow label {lab!r} touches arrow label {other!r}")
        for i, (lab, box, own) in enumerate(self.arrow_labels):
            for other, pts in self.paths:
                if pts is not own and any(seg_hit(p, q, box) for p, q in zip(pts, pts[1:])):
                    out.append(f"arrow label {lab!r} sits on arrow {other!r}")
        for lab, pts in self.paths:
            for other, b in self.group_labels:
                if any(seg_hit(p, q, b) for p, q in zip(pts, pts[1:])):
                    out.append(f"arrow {lab!r} runs through group label {other!r}")
        for lab, g in self.glyphs:
            if any(hit(g, b, pad=4) for other, b in self.words if other == lab):
                out.append(f"glyph touches the words of {lab!r}")
        return sorted(set(out))

    def svg(self, title=""):
        defs = []
        for mid in sorted(self.markers):
            kind = mid[2:]
            color, _, _ = ARROWS[kind]
            if kind == "dependency":
                defs.append(f'<marker id="{mid}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" '
                            f'orient="auto-start-reverse"><path d="M1,0.5 L7,4 L1,7.5" fill="none" stroke="{color}" '
                            f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></marker>')
            else:
                # DiagramArrow's head: a 7-long, 8-wide triangle on a 1.5 stroke, kept in that proportion.
                defs.append(f'<marker id="{mid}" viewBox="0 0 7 8" refX="6.5" refY="4" markerWidth="4.4" markerHeight="5" '
                            f'orient="auto-start-reverse"><path d="M0,0 L7,4 L0,8 Z" fill="{color}"/></marker>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{esc(title)}">')
        return "\n".join([head, f"<title>{esc(title)}</title>", "<defs>", *defs, "</defs>",
                          f'<rect width="{self.w}" height="{self.h}" fill="#FFFFFF"/>',
                          f'<rect width="{self.w}" height="{self.h}" rx="{RADIUS}" fill="{self.background}"/>', *self.body, "</svg>"])


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
    for o in OVERFLOW:
        print(f"OVERFLOW {name}: {o}")
    for o in canvas.collisions():
        print(f"COLLISION {name}: {o}")
    return svg_path
