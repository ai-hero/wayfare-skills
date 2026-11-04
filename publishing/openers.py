"""Chapter-opener art: one unlabelled factory scene per chapter, drawn with the field guides' kit.

The print book sets it above the chapter number, where it takes most of the opener's top padding
but still pushes the first page's text down (it added four pages to the book); the ebook sets it at
the head of the chapter file. Where a scene lays a plain floor it is white with a hairline edge, not
the guides' grey: beside real figures the art has to read lighter than they do. Chapter 8 draws its
proposals dashed, as the book does everywhere a thing is not built.
"""
import math
import os

import guide_art as A
from guide_art import HAIR, PAGE, ROSE, WASH, Iso

W, H = 374.0, 236.0


def _canvas(extent, sw=0.8):
    (u0, u1), (v0, v1), (z0, z1) = extent
    g = Iso(0, 0, 10, sw)
    pts = [g.p(u, v, z) for u in (u0, u1) for v in (v0, v1) for z in (z0, z1)]
    bx0, bx1 = min(p[0] for p in pts), max(p[0] for p in pts)
    by0, by1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = min(W / (bx1 - bx0), H / (by1 - by0))
    g.ox = (W - (bx1 - bx0) * k) / 2 - bx0 * k
    g.oy = (H - (by1 - by0) * k) / 2 - by0 * k
    g.s = 10 * k
    return g


def _floor(g, u, v, w, d, z=0):
    A.floor_rect(g, u, v, w, d, PAGE, HAIR, z=z)


def _room(g, u, v, z=3.4, w=4.4, d=3.6):
    from guide_scenes import control_room
    control_room(g, u, v, z, w, d, screens=2,
                 content=[lambda cw, ch: A.code_lines(cw, ch, 4, 1), lambda cw, ch: A.app_ui(cw, ch)])


def ch1():
    tu, tv = A.fleet_size(1, 1)
    g = _canvas(((-1.4, 14.0 + tu), (-1.8, 11.2), (0, 3.6)))
    for u, v, k in [(0, 0, 3), (4.4, -1.4, 9), (1.4, 4.4, 5), (5.8, 3.4, 13), (-0.6, 8.2, 18)]:
        A.station(g, u, v, k, accent_done=False)
        A.stack(g, u + 2.7, v + 2.0, 2 + k % 3, 0.7, 0.8, 0.1)
    A.fleet(g, 1, 1, u0=14.0, v0=1.0)
    return g


def ch2():
    g = _canvas(((-1, 17), (-1, 11), (0, 7.2)))
    _floor(g, -1, -1, 18, 12)
    for u, v, h, acc in [(0.0, 4.0, 1.1, False), (2.2, 4.0, 0.9, False), (4.4, 4.0, 1.0, False),
                         (0.0, 7.2, 1.0, True), (2.2, 7.2, 1.1, False), (4.4, 7.2, 0.9, False)]:
        A.crate(g, u, v, 1.2, 1.0, h, None, acc)
    A.machine(g, 6.6, 4.6, 12, 0.6)
    A.belt(g, 9.6, 6.0, 7.0, 0.9)
    for k in range(4):
        A.sheet(g, 10.0 + k * 1.6, 6.1, 0.9, 0.7, 0.35, 3, accent=k == 0)
    _room(g, 9.4, -0.6, 3.6, 5.0, 3.6)
    return g


def ch3():
    g = _canvas(((-2.4, 9.0), (-1.8, 7.4), (0, 4.0)))
    A.floor_rect(g, -1.6, -1.2, 9.0, 8.0, WASH, ROSE)
    for u, v in ((-1.2, 3.0), (2.0, -0.8), (5.6, -0.8), (5.6, 4.6)):
        A.crate(g, u, v, 1.5, 1.3, 0.8)
    A.machine(g, 1.4, 1.2, 9, 0.65)
    return g


def ch4():
    g = _canvas(((-1, 24), (-1, 7), (0, 4.0)))
    _floor(g, -1, -1, 25, 7)
    for k in range(4):
        A.floor_rect(g, k * 5.6, 0, 5.0, 5.0, WASH if k == 3 else PAGE, ROSE if k == 3 else HAIR)
    A.belt(g, 0.4, 2.0, 15.2, 0.8)
    A.machine(g, 0.4, -0.6, 2, 0.6)
    A.part(g, 3.4, 2.1, 0.35, 0.55, 2)
    A.gate(g, 6.4, 1.8, 0.8, 1.2, 1.6)
    A.part(g, 9.0, 2.1, 0.35, 0.55, 2)
    A.sheet(g, 11.8, 0.8, 1.6, 1.2, 0, 3)
    A.part(g, 14.6, 2.1, 0.35, 0.55, 2)
    g.poly(g.pts((16.5, -1, 0), (16.5, 6, 0), (16.5, 6, 3.4), (16.5, -1, 3.4)), WASH, ROSE, sw=g.sw * 1.4)
    A.screen(g, 18.0, 2.4, 3.6, 2.2, stand=0.6, content=lambda w, h: A.app_ui(w, h), accent=True)
    return g


def ch5():
    g = _canvas(((-4, 20), (-1, 9), (0, 4.0)))
    _floor(g, -4, -1, 24, 10)
    A.sheet(g, -3.4, 1.4, 2.2, 2.6, 0, 4, accent=True)
    for k, kind in enumerate(["same", "intended", "drift", "same", "drift"]):
        u = 0.8 + k * 3.6
        g.box(u, 1.0, 2.4, 2.4, 1.2, stroke=ROSE if kind == "drift" else A.ICON)
        g.oz = 1.2
        if kind == "intended":
            g.box(u + 0.4, 1.4, 1.2, 1.2, 0.8, dash="1.2 1.4", stroke=A.LINE)
        elif kind == "drift":
            g.box(u + 0.3 + 0.4 * (k % 2), 1.3, 1.0, 1.6, 0.6 + 0.3 * (k % 3), stroke=ROSE)
        else:
            g.box(u + 0.6, 1.6, 1.2, 1.2, 0.6)
        g.oz = 0
        g.line((-1.2, 2.7, 0), (u, 2.2, 0), HAIR, g.sw * 0.7, "1 1.6")
    A.machine(g, 5.6, 5.0, 21, 0.4)
    return g


def ch6():
    g = _canvas(((-7, 7), (-7, 7), (0, 4.0)))
    _floor(g, -7, -7, 14, 14)
    A.machine(g, -1.8, -1.6, 13, 0.5)
    pts = [(6.2 * math.cos(math.radians(a)), 6.2 * math.sin(math.radians(a)), 0) for a in range(-150, 170, 5)]
    g.path(pts, ROSE, sw=1.8)
    g.head(pts[-2], pts[-1], ROSE, g.s * 0.6)
    A.part(g, 4.4, 3.4, 0, 0.9, 13, dash="1.2 1.4")
    return g


def ch7():
    tu, tv = A.fleet_size(4, 2)
    g = _canvas(((-7.6, tu), (-1.0, tv), (0, 7.4)))
    A.fleet(g, 4, 2)
    _room(g, -7.2, 1.0)
    return g


def ch8():
    tu, tv = A.fleet_size(1, 1)
    g = _canvas(((-7.6, tu), (-1.0, tv + 4.6), (0, 7.4)))
    A.fleet(g, 1, 1)
    g.box(-A.PAD, tv - A.PAD + 0.4, tu, 4.0, A.PLATE_Z, top=PAGE, right=PAGE, front=PAGE, stroke=ROSE,
          dash="1.4 1.6")
    g.oz = A.PLATE_Z
    for k in range(4):
        g.box(0.2 + k * 2.6, tv + 0.6, 1.8, 1.8, 1.2, top=PAGE, right=PAGE, front=PAGE, stroke=ROSE, dash="1.4 1.6")
    g.oz = 0
    _room(g, -7.2, 1.0, 3.4, 4.0, 3.4)
    return g


SCENES = {1: ch1, 2: ch2, 3: ch3, 4: ch4, 5: ch5, 6: ch6, 7: ch7, 8: ch8}


def svg(n, cls="opener-art"):
    """The chapter's opener as an inline SVG, or "" for a chapter with none."""
    if n not in SCENES:
        return ""
    g = SCENES[n]()
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}" '
            f'role="img" aria-hidden="true">{"".join(g.out)}</svg>')


def standalone(n):
    """The opener as a standalone SVG file's text, sized in points, or "" for a chapter with none."""
    body = svg(n, "")
    return body.replace(' class=""', f' width="{W:g}" height="{H:g}"', 1) + "\n" if body else ""


def write_png(n, folder, width_px=1200):
    """The opener as a PNG, for an edition that needs an image file. Printed through Chrome, not
    MuPDF: MuPDF ignores the CSS transforms that pose the arms and draws them straight. The art has
    no text, so it is printed without fonts."""
    body = standalone(n)
    if not body:
        return None
    from cover import chrome_pdf, raster
    os.makedirs(folder, exist_ok=True)
    pdf = os.path.join(folder, f"opener-chapter-{n}.pdf")
    path = pdf[:-4] + ".png"
    chrome_pdf(body, W, H, pdf, fonts=False)
    raster(pdf, path, size=(width_px, round(width_px * H / W)))
    return path
