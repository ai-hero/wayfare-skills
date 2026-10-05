"""The book's cover, drawn in code: front, ebook, full print wrap and an animated web version.

    ./publish cover        -> $PUBLISH_OUT/dist/cover-front.{pdf,png}, cover-ebook.png,
                              cover-wrap.pdf, cover-animated.svg

The art is the website's factory line (SoftwareFactoryDiagram.tsx: an isometric software box, an
arm etching a shape, a ticket in and a version out) repeated into a factory: four cells of six
machines on one floor, every machine making a different shape. The arm poses come from the
website's two-link solve, so the tool sits over the point of the outline being etched, and the
animated version turns the same joints through keyframes sampled from that solve. Every word on
the cover is a field of `editions/meta.json`; the back carries the Introduction's first paragraph
until there is back-cover copy.
"""
import html
import json
import math
import os
import subprocess

import fitz

import paths

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DS_FONTS = os.path.join(paths.WORKSPACE, "aihero-design-system-design", "fonts")
FONTS = {
    "Geist": os.path.join(DS_FONTS, "Geist-VariableFont_wght.ttf"),
    "Geist Mono": os.path.join(DS_FONTS, "GeistMono-VariableFont_wght.ttf"),
    "Manrope": os.path.join(paths.OUT, "fonts", "Manrope[wght].ttf"),
}

# Light-theme values of the tokens the website's factory line uses (design-system styles.css).
INK = "#0B0D14"          # ink-figure: the title
ICON = "#383D49"         # icon-neutral: every structural stroke
LINE = "#7B8290"         # line-strong / icon-quiet
QUIET = "#666D7B"        # text-quiet: eyebrows and flow labels
HAIR = "#C6C9D0"         # ink-line
PAGE = "#FFFFFF"         # surface-page
SUNK = "#F4F5F8"         # surface-sunken
ROSE = "#E93A61"         # mark-agent / pal-300: the work and the person
ROSE_DARK = "#A5153E"    # pal-500
WASH = "#FEF1F4"         # surface-selected: pal-300 at 7% on paper

PT = 72
# The book's trim, for the interior (book.css takes it from here) and the cover alike. 7.5 x 9.25 in
# is the Packt technical-book size and a stock KDP and IngramSpark trim; 7 x 10 in had A4's
# proportions and read as an office document rather than a book.
TRIM_IN = (7.5, 9.25)
TRIM_W, TRIM_H, BLEED = TRIM_IN[0] * PT, TRIM_IN[1] * PT, 0.125 * PT
# Uncoated 50# (70 lb text) colour stock, the usual print-on-demand interior: 444 pages per inch.
PAPER_IN_PER_PAGE = 0.002252
BARCODE_W, BARCODE_H = 2 * PT, 1.2 * PT

C30 = math.cos(math.radians(30))


def esc(s):
    return html.escape(s or "", quote=True)


class Iso:
    """Isometric projection: u runs to the lower right, v to the lower left, z up."""

    def __init__(self, ox, oy, s, stroke=0.9):
        self.ox, self.oy, self.s, self.sw = ox, oy, s, stroke
        self.oz = 0.0
        self.out = []

    def p(self, u, v, z=0):
        return (self.ox + (u - v) * self.s * C30, self.oy + (u + v) * self.s * 0.5 - (z + self.oz) * self.s)

    def pts(self, *uvz):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in (self.p(*q) for q in uvz))

    def poly(self, pts, fill, stroke=ICON, sw=None, dash=None, extra=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw or self.sw}"'
                        f' stroke-linejoin="round"{d}{extra}/>')

    def box(self, u, v, w, d, h, top=PAGE, right=PAGE, front=SUNK, stroke=ICON, dash=None, extra=""):
        g = []
        self.out, keep = g, self.out
        self.poly(self.pts((u + w, v, h), (u + w, v + d, h), (u + w, v + d, 0), (u + w, v, 0)), right, stroke, dash=dash)
        self.poly(self.pts((u, v + d, h), (u + w, v + d, h), (u + w, v + d, 0), (u, v + d, 0)), front, stroke, dash=dash)
        self.poly(self.pts((u, v, h), (u + w, v, h), (u + w, v + d, h), (u, v + d, h)), top, stroke, dash=dash)
        self.out = keep
        self.out.append(f'<g{extra}>' + "".join(g) + "</g>")

    def face_matrix(self, u, v, z, edge):
        """Map face units onto the top face centred at (u, v, z), one unit per `edge` grid units."""
        cx, cy = self.p(u, v, z)
        ax, ay = self.p(u + edge, v, z)
        bx, by = self.p(u, v + edge, z)
        return f"matrix({ax - cx:.3f},{ay - cy:.3f},{bx - cx:.3f},{by - cy:.3f},{cx:.2f},{cy:.2f})"

    def line(self, a, b, stroke=LINE, sw=None, dash=None, extra=""):
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}"'
                        f' stroke-width="{sw or self.sw}" stroke-linecap="round"{d}{extra}/>')

    def path(self, pts, stroke=LINE, sw=None, dash=None, extra=""):
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in (self.p(*q) for q in pts))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw or self.sw}"'
                        f' stroke-linecap="round" stroke-linejoin="round"{da}{extra}/>')

    def head(self, a, b, stroke=LINE, size=None):
        """An open chevron at `b`, pointing from `a`: the website's arrowhead."""
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        ang, k = math.atan2(y2 - y1, x2 - x1), size or self.s * 0.22
        pts = [(x2 - k * math.cos(ang - 0.5), y2 - k * math.sin(ang - 0.5)), (x2, y2),
               (x2 - k * math.cos(ang + 0.5), y2 - k * math.sin(ang + 0.5))]
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        self.out.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{self.sw}"'
                        f' stroke-linecap="round" stroke-linejoin="round"/>')

    def label(self, text, u, v, z=0, size=5.6, anchor="start", along="u", fill=QUIET):
        """A mono eyebrow lying on the floor, skewed along an isometric axis like the website's."""
        x, y = self.p(u, v, z)
        m = "0.866,0.5,0,1" if along == "u" else "0.866,-0.5,0,1"
        self.out.append(f'<text transform="matrix({m},{x:.2f},{y:.2f})" font-family="Geist Mono" font-weight="400"'
                        f' font-size="{size}" letter-spacing="{size * 0.12:.2f}" fill="{fill}"'
                        f' text-anchor="{anchor}">{esc(text)}</text>')

    def raw(self, s):
        self.out.append(s)


def _ngon(n, r=0.28, rot=-90.0):
    return [(r * math.cos(math.radians(rot + 360 * k / n)), r * math.sin(math.radians(rot + 360 * k / n)))
            for k in range(n)]


def _star(n, r1=0.3, r2=0.13):
    return [((r1 if k % 2 == 0 else r2) * math.cos(math.radians(-90 + 180 * k / n)),
             (r1 if k % 2 == 0 else r2) * math.sin(math.radians(-90 + 180 * k / n))) for k in range(2 * n)]


def _arc(cx, cy, r, a0, a1, n=24):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


# The website's three components first, then simple solids of the same family: every machine on
# the floor makes something different. Each is a list of closed outlines in face units (one unit
# is the box edge, so +/-0.3 fills about half the top).
_W = 0.1
SHAPES = [
    [[(-0.26, -0.26), (0.26, -0.26), (0.26, 0.26), (-0.26, 0.26)]],
    [[(0, -0.3), (0.3, 0.24), (-0.3, 0.24)]],
    [_ngon(40)],
    [[(0, -0.32), (0.24, 0), (0, 0.32), (-0.24, 0)]],
    [_ngon(6)],
    [_ngon(5, 0.3)],
    [[(-_W, -0.3), (_W, -0.3), (_W, -_W), (0.3, -_W), (0.3, _W), (_W, _W), (_W, 0.3), (-_W, 0.3), (-_W, _W),
      (-0.3, _W), (-0.3, -_W), (-_W, -_W)]],
    [_ngon(40, 0.29), _ngon(30, 0.14)],
    [[(-0.28, -0.18), (0, 0.06), (0.28, -0.18), (0.28, 0.06), (0, 0.3), (-0.28, 0.06)]],
    [_star(5)],
    [_ngon(8, 0.29, -67.5)],
    [[(-0.3, -0.22), (-0.22, -0.3), (0, -0.08), (0.22, -0.3), (0.3, -0.22), (0.08, 0), (0.3, 0.22), (0.22, 0.3),
      (0, 0.08), (-0.22, 0.3), (-0.3, 0.22), (-0.08, 0)]],
    [_arc(0, 0.1, 0.3, 180, 360)],
    [[(-0.3, 0.2), (-0.16, -0.2), (0.16, -0.2), (0.3, 0.2)]],
    [[(-0.3, 0.18), (-0.12, -0.18), (0.3, -0.18), (0.12, 0.18)]],
    [[(0, -0.32), (0.26, -0.04), (0.1, -0.04), (0.1, 0.3), (-0.1, 0.3), (-0.1, -0.04), (-0.26, -0.04)]],
    [[(-0.26, -0.3), (-0.06, -0.3), (-0.06, 0.1), (0.26, 0.1), (0.26, 0.3), (-0.26, 0.3)]],
    [[(-0.3, -0.3), (0.3, -0.3), (0.3, -0.1), (0.1, -0.1), (0.1, 0.3), (-0.1, 0.3), (-0.1, -0.1), (-0.3, -0.1)]],
    [_arc(0, -0.15, 0.3, 30, 150, 16) + _arc(0, 0.15, 0.3, 210, 330, 16)[1:-1]],
    [[(0, 0.3), (0.3, -0.24), (-0.3, -0.24)]],
    [[(-0.26, -0.26), (0.26, -0.26), (0.26, 0.26), (-0.26, 0.26)], [(-0.12, -0.12), (0.12, -0.12), (0.12, 0.12),
                                                                     (-0.12, 0.12)]],
    [_ngon(3, 0.32, -90), _ngon(3, 0.32, 90)],
    [_ngon(40, 0.29), _ngon(12, 0.05)],
    [_star(4, 0.32, 0.1)],
]


def _segments(loops):
    for loop in loops:
        pts = loop + [loop[0]]
        for a, b in zip(pts, pts[1:]):
            yield a, b


def partial(loops, f):
    """The first fraction `f` of the outline, as open polylines, and the point where the laser is."""
    total = sum(math.dist(a, b) for a, b in _segments(loops))
    left, out, at = f * total, [], loops[0][0]
    for loop in loops:
        pts, cur = loop + [loop[0]], [loop[0]]
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if left <= 0:
                break
            if L <= left:
                cur.append(b)
                left -= L
                at = b
            else:
                t = left / L
                at = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                cur.append(at)
                left = 0
        if len(cur) > 1:
            out.append(cur)
        if left <= 0:
            break
    return out, at


def screen_d(g, polylines, to_uvz, closed=True):
    """Outlines in face units projected to page coordinates, so stroke and dash lengths are real."""
    d = []
    for pl in polylines:
        pts = [g.p(*to_uvz(x, y)) for x, y in pl]
        d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + (" Z" if closed else ""))
    return "".join(d)


# One machine, in grid units from its corner: the pedestal behind, the software box in front of it
# and the arm reaching across, as the website's line has them.
PED = (0.55, 0.5)
BOX = (1.3, 0.95, 1.1, 0.95)  # u, v, edge, height
ARM_SHOULDER, ARM_UPPER, ARM_FORE = 1.95, 1.55, 1.3
PITCH_U, PITCH_V = 3.35, 3.15
CYCLE_S = 9.0
GAP, PAD = 0.9, 0.55
# The etched product's size on the box top, past the website's: on a cover it is what the eye reads.
MARK = 1.25
# The floor fills this share of the trim width, its back corner this far down the page.
FLOOR_WIDTH, FLOOR_TOP = 0.9, 0.455


class Machine:
    def __init__(self, g, u, v, shape, phase):
        self.g, self.u, self.v, self.loops, self.phase = g, u, v, SHAPES[shape], phase

    def face(self, x, y):
        """A face-unit point on the box top, as (u, v, z)."""
        box_u, box_v, e, h = BOX
        return self.u + box_u + e / 2 + x * e * MARK, self.v + box_v + e / 2 + y * e * MARK, h

    def pose(self, f, lift):
        """Shoulder, elbow, wrist and the point under the tool, by the website's two-link solve."""
        g, s = self.g, self.g.s
        bx, by = g.p(self.u + PED[0], self.v + PED[1], 0)
        sh = (bx, by - ARM_SHOULDER * s)
        cx, cy = g.p(*self.face(*partial(self.loops, f)[1]))
        tx, ty = cx, cy - (1.05 + lift) * s
        L1, L2 = ARM_UPPER * s, ARM_FORE * s
        dx, dy = tx - sh[0], ty - sh[1]
        reach = max(abs(L1 - L2) + 1, min(L1 + L2 - 1, math.hypot(dx, dy)))
        aim = math.atan2(dy, dx)
        spread = math.acos((L1 ** 2 + reach ** 2 - L2 ** 2) / (2 * L1 * reach))
        th = aim - spread if math.sin(aim - spread) < math.sin(aim + spread) else aim + spread
        el = (sh[0] + L1 * math.cos(th), sh[1] + L1 * math.sin(th))
        wr = (sh[0] + reach * math.cos(aim), sh[1] + reach * math.sin(aim))
        return sh, el, wr, (cx, cy), th, math.atan2(wr[1] - el[1], wr[0] - el[0])

    @staticmethod
    def timeline(t):
        """Phase t in [0, 1): the ticket arrives, the arm etches, lifts, and the version ships."""
        etch = min(1.0, max(0.0, (t - 0.22) / 0.5))
        lift = 0.5 * max(min(1.0, max(0.0, (0.3 - t) / 0.1)), min(1.0, max(0.0, (t - 0.72) / 0.08)))
        return etch, lift

    def draw(self, t, animated=False, idx=0, still=None):
        """`still` freezes the machine for print: (etched fraction, lift, ticket waiting, version shipped)."""
        g, s, sw = self.g, self.g.s, self.g.sw
        box_u, box_v, e, h = BOX
        u, v = self.u, self.v
        f, lift = self.timeline(t)
        ticket, shipped = animated, animated
        if still:
            f, lift, ticket, shipped = still
        cls = (lambda c: f' class="{c} m{idx}"') if animated else (lambda c: "")
        # The inbound ticket on the floor in front of the box, and the shipped version past it.
        tu, tv = u + 0.2, v + box_v + e / 2 + 0.05
        if ticket:
            g.raw(f'<g{cls("ticket")}>')
            g.poly(g.pts((tu - 0.32, tv - 0.32, 0), (tu + 0.32, tv - 0.32, 0), (tu + 0.32, tv + 0.32, 0),
                         (tu - 0.32, tv + 0.32, 0)), PAGE, LINE)
            tk = screen_d(g, self.loops, lambda x, y: (tu + x * 0.64, tv + y * 0.64, 0))
            g.raw(f'<path d="{tk}" fill="none" stroke="{LINE}" stroke-width="{sw * 0.8:.2f}"'
                  f' stroke-linejoin="round"/></g>')
        # Pedestal.
        bx, by = g.p(u + PED[0], v + PED[1], 0)
        rx, ry, hb = 0.5 * s, 0.25 * s, 0.85 * s
        g.raw(f'<path d="M{bx - rx:.2f},{by - hb:.2f} L{bx - rx:.2f},{by:.2f} A{rx:.2f},{ry:.2f} 0 0 0 {bx + rx:.2f},{by:.2f}'
              f' L{bx + rx:.2f},{by - hb:.2f}" fill="{PAGE}" stroke="{ICON}" stroke-width="{sw}"/>'
              f'<ellipse cx="{bx:.2f}" cy="{by - hb:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{PAGE}" stroke="{ICON}"'
              f' stroke-width="{sw}"/>')
        nx = 0.2 * s
        top = by - ARM_SHOULDER * s
        g.raw(f'<rect x="{bx - nx:.2f}" y="{top:.2f}" width="{2 * nx:.2f}" height="{by - hb - top:.2f}" fill="{PAGE}"/>'
              f'<line x1="{bx - nx:.2f}" y1="{top:.2f}" x2="{bx - nx:.2f}" y2="{by - hb:.2f}" stroke="{ICON}" stroke-width="{sw}"/>'
              f'<line x1="{bx + nx:.2f}" y1="{top:.2f}" x2="{bx + nx:.2f}" y2="{by - hb:.2f}" stroke="{ICON}" stroke-width="{sw}"/>')
        # The software box and what is being etched on it.
        g.box(u + box_u, v + box_v, e, e, h)
        cu, cv, _ = self.face(0, 0)
        g.raw(f'<ellipse{cls("wash")} cx="{g.p(cu, cv, h)[0]:.2f}" cy="{g.p(cu, cv, h)[1]:.2f}" rx="{0.55 * e * s:.2f}"'
              f' ry="{0.27 * e * s:.2f}" fill="{WASH}"/>')
        on_top = lambda x, y: (cu + x * e * MARK, cv + y * e * MARK, h)  # noqa: E731
        if animated:
            d, extra = screen_d(g, self.loops, on_top), ' pathLength="100"'
        else:
            d, extra = screen_d(g, partial(self.loops, f)[0] if f < 0.999 else self.loops, on_top, f >= 0.999), ""
        g.raw(f'<path{cls("trace")} d="{d}" fill="none" stroke="{ROSE}" stroke-width="{sw * 1.6:.2f}"{extra}'
              f' stroke-linejoin="round" stroke-linecap="round"/>')
        # The shipped version, a dashed copy of the box carrying the finished shape.
        if shipped:
            su = u + box_u + e + 0.6
            g.raw(f'<g{cls("ship")}>')
            g.box(su, v + box_v + 0.15, 0.8, 0.8, 0.7, top=PAGE, right=PAGE, front=PAGE, stroke=LINE, dash="1.6 1.8")
            sd = screen_d(g, self.loops, lambda x, y: (su + 0.4 + x * 0.8, v + box_v + 0.55 + y * 0.8, 0.7))
            g.raw(f'<path d="{sd}" fill="none" stroke="{ROSE}" stroke-width="{sw * 1.3:.2f}"'
                  f' stroke-linejoin="round"/></g>')
        self.draw_arm(f, lift, animated, idx)

    def draw_arm(self, f, lift, animated, idx):
        """Drawn as an upper arm and forearm hinged at the elbow, so the animated version can turn
        each about its joint instead of re-solving geometry the browser cannot compute."""
        g, s, sw = self.g, self.g.s, self.g.sw
        sh, el, wr, (cx, cy), th, ph = self.pose(f, lift)
        L1, L2 = ARM_UPPER * s, ARM_FORE * s
        w1, w2 = 0.24 * s, 0.2 * s
        a = (lambda c: f' class="{c} m{idx}"') if animated else (lambda c: "")
        an = (lambda n: f";animation-name:{n}{idx}") if animated else (lambda n: "")
        # Built in a frame where both links lie flat, then turned into the pose; the animated
        # version swaps these rotations for keyframes.
        r1, r2 = math.degrees(th), math.degrees(ph - th)
        tube = lambda x2, w: (f'<line x1="0" y1="0" x2="{x2:.2f}" y2="0" stroke="{ICON}" stroke-width="{w:.2f}" stroke-linecap="round"/>'  # noqa: E731
                              f'<line x1="0" y1="0" x2="{x2:.2f}" y2="0" stroke="{PAGE}" stroke-width="{w - 2 * sw:.2f}" stroke-linecap="round"/>')
        joint = lambda r: (f'<circle r="{r:.2f}" fill="{PAGE}" stroke="{ICON}" stroke-width="{sw}"/>'  # noqa: E731
                           f'<circle r="{0.04 * s:.2f}" fill="{LINE}"/>')
        hw, ht = 0.18 * s, 0.3 * s
        tool = (f'<circle r="{0.12 * s:.2f}" fill="{PAGE}" stroke="{ICON}" stroke-width="{sw}"/>'
                f'<path d="M{-hw:.2f},{0.1 * s:.2f} L{hw:.2f},{0.1 * s:.2f} L{hw * 0.45:.2f},{0.1 * s + ht:.2f}'
                f' L{-hw * 0.45:.2f},{0.1 * s + ht:.2f} Z" fill="{PAGE}" stroke="{ICON}" stroke-width="{sw}" stroke-linejoin="round"/>'
                f'<line{a("beam")} x1="0" y1="{0.1 * s + ht + 0.08 * s:.2f}" x2="0" y2="{(1.05 + lift) * s - 0.1 * s:.2f}"'
                f' stroke="{ROSE}" stroke-width="{sw * 1.1:.2f}" stroke-dasharray="{0.06 * s:.2f} {0.08 * s:.2f}"'
                f' stroke-linecap="round" opacity="{0 if lift > 0.2 and not animated else 1}"/>'
                f'<circle{a("glow")} cy="{0.1 * s + ht + 0.06 * s:.2f}" r="{0.14 * s:.2f}" fill="{ROSE}" opacity=".24"/>'
                f'<circle cy="{0.1 * s + ht + 0.06 * s:.2f}" r="{0.07 * s:.2f}" fill="{ROSE}"/>')
        g.raw(f'<g transform="translate({sh[0]:.2f},{sh[1]:.2f})">'
              f'<g{a("upper")} style="transform:rotate({r1:.2f}deg){an("u")}">{tube(L1, w1)}'
              f'<g transform="translate({L1:.2f},0)"><g{a("fore")} style="transform:rotate({r2:.2f}deg){an("f")}">{tube(L2, w2)}'
              f'<g transform="translate({L2:.2f},0)"><g{a("tool")} style="transform:rotate({-r1 - r2:.2f}deg){an("t")}">{tool}</g></g>'
              f'{joint(0.17 * s)}</g></g>{joint(0.2 * s)}</g></g>')


def factory(g, animated=False):
    """Four cells of six machines on one floor: the factory the book is about."""
    sw = g.sw
    cell_u, cell_v, gap, pad = 3 * PITCH_U, 2 * PITCH_V, GAP, PAD
    total_u, total_v = 2 * cell_u + gap + 2 * pad, 2 * cell_v + gap + 2 * pad
    g.box(-pad, -pad, total_u, total_v, 0.45, top=PAGE, right=SUNK, front=SUNK)
    machines, k = [], 0
    for cj in range(2):
        for ci in range(2):
            cu, cv = ci * (cell_u + gap), cj * (cell_v + gap)
            g.poly(g.pts((cu, cv, 0.45), (cu + cell_u, cv, 0.45), (cu + cell_u, cv + cell_v, 0.45),
                         (cu, cv + cell_v, 0.45)), SUNK, HAIR, sw=sw * 0.9)
            for j in range(2):
                for i in range(3):
                    machines.append((cu + i * PITCH_U + 0.1, cv + j * PITCH_V + 0.05, k))
                    k += 1
    g.oz = 0.45
    for u, v, k in sorted(machines, key=lambda m: m[0] + m[1]):
        phase = (k * 0.618034) % 1.0
        m = Machine(g, u, v, k, phase)
        m.index = k
        # For print every machine shows its product: most mid-etch at different points of the
        # outline (so no two arms share a pose), one in four finished with the version shipping.
        done = k % 4 == 2
        still = None if animated else (1.0 if done else 0.45 + 0.5 * ((k * 0.381966) % 1.0),
                                       0.45 if done else 0.0, k % 3 == 1, done)
        g.raw(f'<g class="machine" style="--d:{-phase * CYCLE_S:.2f}s">' if animated else "<g>")
        m.draw(0.5, animated, k, still)
        g.raw("</g>")
        g.machines = getattr(g, "machines", []) + [m]


# The weights the cover sets. Chrome prints a variable font at a non-default weight as Type 3, which
# print services reject, so each weight is cut to a static TrueType instance first.
WEIGHTS = {"Manrope": (200, 300), "Geist": (300, 400), "Geist Mono": (400,)}


def static_font(family, weight):
    out = os.path.join(paths.BUILD, "fonts", f"{family.replace(' ', '')}-{weight}.ttf")
    if not os.path.exists(out):
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
        os.makedirs(os.path.dirname(out), exist_ok=True)
        instantiateVariableFont(TTFont(FONTS[family]), {"wght": weight}).save(out)
    return out


def font_css(fmt="truetype"):
    return "".join(f'@font-face{{font-family:"{n}";src:url("file://{static_font(n, w)}") format("{fmt}");'
                   f'font-weight:{w}}}' for n, ws in WEIGHTS.items() for w in ws)


def front_art(w, h, animated=False):
    """The scene sized for a page of w x h points, floor centred in the lower two-thirds."""
    cell_u, cell_v = 3 * PITCH_U, 2 * PITCH_V
    span_u, span_v = 2 * cell_u + GAP + 2 * PAD, 2 * cell_v + GAP + 2 * PAD
    s = FLOOR_WIDTH * w / ((span_u + span_v) * C30)
    # The floor's left corner is (-PAD, span_v - PAD); centre the whole rhombus on the page.
    left = (-PAD - (span_v - PAD)) * C30 * s
    ox = (w - FLOOR_WIDTH * w) / 2 - left
    g = Iso(ox=ox, oy=h * FLOOR_TOP + PAD * s, s=s, stroke=max(0.55, s * 0.045))
    factory(g, animated)
    return g


def title_block(meta, x, top, width, scale=1.0):
    """Eyebrow, the title over two lines, the subtitle: the hierarchy that has to read at 200 px."""
    t = meta["title"].split(" ")
    # The two-line break that keeps the longer line shortest: "Architecting a / Software Factory".
    cut = min(range(1, len(t)), key=lambda i: max(len(" ".join(t[:i])), len(" ".join(t[i:])))) if len(t) > 1 else 1
    lines = [" ".join(t[:cut]), " ".join(t[cut:])] if len(t) > 1 else t
    size = 50 * scale
    out = [f'<rect x="{x:.2f}" y="{top:.2f}" width="{28 * scale:.2f}" height="{2.2 * scale:.2f}" fill="{ROSE}"/>',
           f'<text x="{x:.2f}" y="{top + 20 * scale:.2f}" font-family="Geist Mono" font-size="{7.5 * scale:.2f}"'
           f' letter-spacing="{7.5 * scale * 0.14:.2f}" fill="{QUIET}">{esc(meta["affiliation"].upper())}</text>']
    y = top + 20 * scale + size * 1.18
    for ln in lines:
        out.append(f'<text x="{x - 2 * scale:.2f}" y="{y:.2f}" font-family="Manrope" font-weight="200"'
                   f' font-size="{size:.2f}" letter-spacing="{-size * 0.02:.2f}" fill="{INK}">{esc(ln)}</text>')
        y += size * 1.04
    if meta.get("subtitle"):
        out.append(f'<text x="{x:.2f}" y="{y + 10 * scale:.2f}" font-family="Geist" font-weight="300"'
                   f' font-size="{15 * scale:.2f}" fill="{ICON}">{esc(meta["subtitle"])}</text>')
    return "".join(out)


def author_block(meta, x, bottom, scale=1.0):
    return (f'<text x="{x:.2f}" y="{bottom - 14 * scale:.2f}" font-family="Geist" font-weight="400"'
            f' font-size="{14 * scale:.2f}" fill="{INK}">{esc(meta["author"])}</text>'
            f'<line x1="{x:.2f}" y1="{bottom - 36 * scale:.2f}" x2="{x + 28 * scale:.2f}" y2="{bottom - 36 * scale:.2f}"'
            f' stroke="{HAIR}" stroke-width="{0.8 * scale:.2f}"/>')


def front_svg(meta, bleed=BLEED, animated=False, w=TRIM_W, h=TRIM_H, css=""):
    """The front at trim w x h with `bleed` on every side; the fleet runs off into the bleed."""
    W, H = w + 2 * bleed, h + 2 * bleed
    k = w / TRIM_W
    art = front_art(w, h, animated)
    margin = 0.75 * PT * k
    body = (f'<rect width="{W:.2f}" height="{H:.2f}" fill="{PAGE}"/>'
            f'<g transform="translate({bleed:.2f},{bleed:.2f})">'
            f'<g>{"".join(art.out)}</g>'
            + title_block(meta, margin, 0.95 * PT * k, w - 2 * margin, k)
            + author_block(meta, margin, h - 0.55 * PT * k, k)
            + "</g>")
    style = f"<style>{css}</style>" if css else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} {H:.2f}" width="{W:.2f}" height="{H:.2f}">'
            f'{style}{body}</svg>'), art


def chrome_pdf(svg, w_pt, h_pt, out):
    """Print an SVG to a w x h pt PDF through headless Chrome, with the design system's fonts."""
    page = os.path.splitext(out)[0] + ".html"
    with open(page, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}'
                f'@page{{size:{w_pt}pt {h_pt}pt;margin:0}}html,body{{margin:0}}svg{{display:block;'
                f'width:{w_pt}pt;height:{h_pt}pt}}</style></head><body>{svg}</body></html>')
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                    "--virtual-time-budget=4000", f"--print-to-pdf={out}", f"file://{page}"],
                   check=True, capture_output=True)
    os.remove(page)
    # Chrome rounds the page up to a whole CSS pixel, so a wrap comes out up to 1/96 in wider than
    # its spine calls for and a print service rejects it; trim the sliver back to the exact size.
    doc = fitz.open(out)
    if any(abs(pg.rect.width - w_pt) > 0.01 or abs(pg.rect.height - h_pt) > 0.01 for pg in doc):
        for pg in doc:
            pg.set_cropbox(fitz.Rect(0, 0, w_pt, h_pt))
            pg.set_mediabox(fitz.Rect(0, 0, w_pt, h_pt))
        doc.save(out + ".tmp", garbage=3, deflate=True)
        doc.close()
        os.replace(out + ".tmp", out)


def raster(pdf, out, dpi=None, size=None):
    page = fitz.open(pdf)[0]
    z = (size[0] / page.rect.width) if size else dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(z * 1.001, z * 1.001), alpha=False)
    if size and (pix.width, pix.height) != size:
        from PIL import Image
        Image.frombytes("RGB", (pix.width, pix.height), pix.samples).resize(size, Image.LANCZOS).save(out)
    else:
        pix.save(out)


def first_paragraph():
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = json.load(f)
    for s in doc["chapters"][0]["sections"]:
        for b in s["blocks"]:
            if b["kind"] == "p":
                from inline import md_plain
                return md_plain(b["md"])
    return ""


def wrap_lines(text, width_pt, size, font="Geist"):
    """Greedy wrap measured with the face's own advance widths."""
    from fontTools.ttLib import TTFont
    tt = TTFont(FONTS[font])
    cmap, hmtx, upm = tt.getBestCmap(), tt["hmtx"], tt["head"].unitsPerEm
    adv = lambda t: sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in t) * size / upm  # noqa: E731
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and adv(trial) > width_pt:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def wrap_svg(meta, pages):
    spine = pages * PAPER_IN_PER_PAGE * PT
    W, H = 2 * TRIM_W + spine + 2 * BLEED, TRIM_H + 2 * BLEED
    front, _ = front_svg(meta, bleed=0)
    inner = front[front.index(">") + 1:front.rindex("</svg>")]
    fx = BLEED + TRIM_W + spine
    m = 0.75 * PT
    text = first_paragraph()
    lines = wrap_lines(text, TRIM_W - 2 * m - 0.4 * PT, 10.5)
    back = [f'<rect x="{BLEED + m:.2f}" y="{BLEED + 0.95 * PT:.2f}" width="28" height="2.2" fill="{ROSE}"/>']
    y = BLEED + 0.95 * PT + 34
    for ln in lines:
        back.append(f'<text x="{BLEED + m:.2f}" y="{y:.2f}" font-family="Geist" font-weight="300" font-size="10.5"'
                    f' fill="{ICON}">{esc(ln)}</text>')
        y += 16.5
    back.append(f'<text x="{BLEED + m:.2f}" y="{BLEED + TRIM_H - 0.55 * PT - 14:.2f}" font-family="Geist Mono"'
                f' font-size="7.5" letter-spacing="1.05" fill="{QUIET}">{esc(meta["affiliation"].upper())}</text>')
    bx, by = BLEED + TRIM_W - m - BARCODE_W, BLEED + TRIM_H - 0.55 * PT - BARCODE_H
    back.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{BARCODE_W:.2f}" height="{BARCODE_H:.2f}" fill="{PAGE}"'
                f' stroke="{HAIR}" stroke-width="0.6" stroke-dasharray="2 2"/>')
    sx, cy = BLEED + TRIM_W + spine / 2, H / 2
    fs = min(9.0, spine * 0.42)
    spine_text = (f'<g transform="translate({sx:.2f},{cy:.2f}) rotate(90)">'
                  f'<text x="{-TRIM_H / 2 + 0.6 * PT:.2f}" y="{fs * 0.36:.2f}" font-family="Manrope" font-weight="300"'
                  f' font-size="{fs:.2f}" fill="{INK}">{esc(meta["title"])}</text>'
                  f'<text x="{TRIM_H / 2 - 0.6 * PT:.2f}" y="{fs * 0.36:.2f}" text-anchor="end" font-family="Geist Mono"'
                  f' font-size="{fs * 0.78:.2f}" letter-spacing="{fs * 0.08:.2f}" fill="{QUIET}">'
                  f'{esc(meta["author"].upper())}</text></g>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} {H:.2f}" width="{W:.2f}" height="{H:.2f}">'
           f'<rect width="{W:.2f}" height="{H:.2f}" fill="{PAGE}"/>'
           f'<rect x="{BLEED + TRIM_W:.2f}" y="0" width="{spine:.2f}" height="{H:.2f}" fill="{SUNK}"/>'
           f'{"".join(back)}{spine_text}'
           f'<g transform="translate({fx:.2f},{BLEED:.2f})">{inner}</g></svg>')
    return svg, W, H, spine


ANIMATION_CSS = """
.machine * { animation-duration: %(cycle)ss; animation-iteration-count: infinite; animation-delay: var(--d); }
.upper, .fore, .tool { animation-timing-function: linear; }
.trace { stroke-dasharray: 0 100; animation-name: etch; animation-timing-function: linear; }
.ticket { opacity: 0; animation-name: ticket; animation-timing-function: ease-out; }
.ship { opacity: 0; animation-name: ship; animation-timing-function: ease-in-out; }
.beam { animation-name: beam; animation-timing-function: step-end; }
.glow { animation-name: glow; }
@keyframes etch { 0%%, 22%% { stroke-dasharray: 0 100; opacity: 1; } 72%% { stroke-dasharray: 100 100; opacity: 1; }
  92%% { stroke-dasharray: 100 100; opacity: 1; } 100%% { stroke-dasharray: 100 100; opacity: 0; } }
@keyframes ticket { 0%% { opacity: 0; transform: translate(%(tx)spx, %(ty)spx); } 6%% { opacity: 1; }
  20%% { opacity: 1; transform: translate(0, 0); } 24%%, 100%% { opacity: 0; transform: translate(0, 0); } }
@keyframes ship { 0%%, 74%% { opacity: 0; transform: translate(%(sx)spx, %(sy)spx); } 78%% { opacity: 1; }
  94%% { opacity: 1; transform: translate(0, 0); } 100%% { opacity: 0; transform: translate(0, 0); } }
@keyframes beam { 0%% { opacity: 0; } 22%% { opacity: 1; } 72%% { opacity: 0; } }
@keyframes glow { 0%%, 100%% { opacity: .1; } 50%% { opacity: .35; } }
%(arms)s
@media (prefers-reduced-motion: reduce) {
  .machine * { animation: none !important; }
  .trace { stroke-dasharray: none; }
}
"""


def _unwrap(angles):
    out = [angles[0]]
    for a in angles[1:]:
        while a - out[-1] > 180:
            a -= 360
        while a - out[-1] < -180:
            a += 360
        out.append(a)
    return out


def arm_keyframes(m, k, steps=36):
    """Each joint's angle through one cycle, sampled from the same two-link solve as the print pose."""
    th, rel, tool = [], [], []
    for i in range(steps + 1):
        f, lift = Machine.timeline(i / steps)
        _, _, _, _, a, p = m.pose(f, lift)
        th.append(math.degrees(a))
        rel.append(math.degrees(p - a))
    th, rel = _unwrap(th), _unwrap(rel)
    tool = [-(x + y) for x, y in zip(th, rel)]
    css = []
    for name, vals in (("u", th), ("f", rel), ("t", tool)):
        frames = " ".join(f"{100 * i / steps:.1f}% {{transform:rotate({v:.1f}deg)}}" for i, v in enumerate(vals))
        css.append(f"@keyframes {name}{k} {{{frames}}}")
    return "\n".join(css)


def animated_svg(meta, w=TRIM_W, h=TRIM_H):
    """The factory floor with every machine running, each on its own phase so the floor hums. Art
    only, cropped to the floor: as an <img> it cannot reach the page's fonts, and the page sets the
    title in its own type anyway."""
    g = front_art(w, h, animated=True)
    span_u = 2 * 3 * PITCH_U + GAP + 2 * PAD
    span_v = 2 * 2 * PITCH_V + GAP + 2 * PAD
    corners = [g.p(-PAD, -PAD, -g.oz), g.p(span_u - PAD, -PAD, -g.oz), g.p(span_u - PAD, span_v - PAD, -g.oz),
               g.p(-PAD, span_v - PAD, -g.oz)]
    x0 = min(c[0] for c in corners) - 6
    x1 = max(c[0] for c in corners) + 6
    y0 = min(c[1] for c in corners) - (ARM_SHOULDER + ARM_UPPER + 0.6) * g.s
    y1 = max(c[1] for c in corners) + 0.6 * g.s
    tx, ty = (g.p(-0.9, 0)[i] - g.p(0, 0)[i] for i in (0, 1))
    sx, sy = (g.p(-0.6, 0)[i] - g.p(0, 0)[i] for i in (0, 1))
    arms = "\n".join(arm_keyframes(m, m.index) for m in g.machines)
    css = ANIMATION_CSS % {"cycle": f"{CYCLE_S:g}", "tx": f"{tx:.1f}", "ty": f"{ty:.1f}", "sx": f"{sx:.1f}",
                           "sy": f"{sy:.1f}", "arms": arms}
    label = esc(f"{meta['title']}: four cells of six machines on one floor, each etching and shipping a different shape.")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}"'
            f' role="img" aria-label="{label}"><style>{css}</style>{"".join(g.out)}</svg>')


def main():
    with open(paths.META, encoding="utf-8") as f:
        meta = json.load(f)
    os.makedirs(paths.DIST, exist_ok=True)
    d = paths.DIST
    W, H = TRIM_W + 2 * BLEED, TRIM_H + 2 * BLEED
    svg, _ = front_svg(meta)
    chrome_pdf(svg, W, H, os.path.join(d, "cover-front.pdf"))
    raster(os.path.join(d, "cover-front.pdf"), os.path.join(d, "cover-front.png"), dpi=300)
    trim, _ = front_svg(meta, bleed=0)
    chrome_pdf(trim, TRIM_W, TRIM_H, os.path.join(paths.BUILD, "cover-trim.pdf"))
    # Store covers are 1:1.6, taller than the 7 x 10 trim: the same layout recomposed, not stretched.
    eh = TRIM_W * 2560 / 1600
    ebook, _ = front_svg(meta, bleed=0, h=eh)
    chrome_pdf(ebook, TRIM_W, eh, os.path.join(paths.BUILD, "cover-ebook.pdf"))
    raster(os.path.join(paths.BUILD, "cover-ebook.pdf"), os.path.join(d, "cover-ebook.png"), size=(1600, 2560))
    book = os.path.join(d, "book-interior.pdf")
    if not os.path.exists(book):
        book = os.path.join(d, "book.pdf")
    pages = len(fitz.open(book)) if os.path.exists(book) else 0
    wsvg, ww, wh, spine = wrap_svg(meta, pages)
    chrome_pdf(wsvg, ww, wh, os.path.join(d, "cover-wrap.pdf"))
    with open(os.path.join(d, "cover-animated.svg"), "w", encoding="utf-8") as f:
        f.write(animated_svg(meta))
    print(f"cover: front, ebook, wrap ({pages} pages, spine {spine / PT:.3f} in), animated -> {d}")


if __name__ == "__main__":
    main()
