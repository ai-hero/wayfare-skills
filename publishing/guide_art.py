"""The field guides' drawing kit: the cover's isometric projection and machines, plus the props a
factory scene needs (crates, sheets, screens, gates, boards, people) and flat 2D marks for charts.

Every prop draws into an `Iso` (cover.py), so a scene shares the cover's line weights and palette.
Faces facing the viewer are +u (right) and +v (front); text and screen content on a front face go
through `front()`, which maps flat 2D units onto that plane.
"""
import math

from cover import (C30, HAIR, ICON, INK, LINE, PAGE, QUIET, ROSE, ROSE_DARK, SUNK, WASH, Iso, Machine, esc,
                   factory)

__all__ = ["Iso", "factory", "C30", "HAIR", "ICON", "INK", "LINE", "PAGE", "QUIET", "ROSE", "ROSE_DARK", "SUNK",
           "WASH", "esc"]

GREEN = "#3F7D5A"


# ---------- flat 2D marks ----------

def text(x, y, s, size=11, family="Geist", weight=400, fill=INK, anchor="start", spacing=None, extra=""):
    ls = f' letter-spacing="{spacing:.2f}"' if spacing is not None else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{family}" font-weight="{weight}" font-size="{size:.2f}"'
            f' fill="{fill}" text-anchor="{anchor}"{ls}{extra}>{esc(s)}</text>')


def mono(x, y, s, size=7.5, fill=QUIET, anchor="start", weight=400):
    return text(x, y, s.upper(), size, "Geist Mono", weight, fill, anchor, size * 0.14)


def rect(x, y, w, h, fill=PAGE, stroke=ICON, sw=0.9, rx=0, dash=None, extra=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx:.2f}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{sw}"{d}{extra}/>')


def line(x1, y1, x2, y2, stroke=LINE, sw=0.9, dash=None, cap="round"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{sw}"'
            f' stroke-linecap="{cap}"{d}/>')


def poly2(pts, stroke=LINE, sw=0.9, fill="none", dash=None, close=False):
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + (" Z" if close else "")
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round"'
            f' stroke-linejoin="round"{da}/>')


def chevron(x1, y1, x2, y2, stroke=LINE, k=6, sw=0.9):
    ang = math.atan2(y2 - y1, x2 - x1)
    pts = [(x2 - k * math.cos(ang - 0.5), y2 - k * math.sin(ang - 0.5)), (x2, y2),
           (x2 - k * math.cos(ang + 0.5), y2 - k * math.sin(ang + 0.5))]
    return poly2(pts, stroke, sw)


def arrow2(pts, stroke=LINE, sw=0.9, dash=None, k=6):
    return poly2(pts, stroke, sw, dash=dash) + chevron(*pts[-2], *pts[-1], stroke=stroke, k=k, sw=sw)


def circle(cx, cy, r, fill=PAGE, stroke=ICON, sw=0.9, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def arc2(cx, cy, r, a0, a1, stroke=ROSE, sw=1.4, dash=None, head=False):
    pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / 48)),
            cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / 48))) for k in range(49)]
    out = poly2(pts, stroke, sw, dash=dash)
    return out + (chevron(*pts[-3], *pts[-1], stroke=stroke, k=7, sw=sw) if head else "")


def callout(x, y, tx, ty, label, accent=False, size=7, anchor=None):
    """A leader from a point in the art to a mono label, the manual-illustration convention."""
    col = ROSE_DARK if accent else QUIET
    anchor = anchor or ("start" if tx >= x else "end")
    elbow = tx - (8 if anchor == "start" else -8)
    return (circle(x, y, 1.6, ROSE if accent else ICON, "none") +
            poly2([(x, y), (elbow, ty), (tx, ty)], ROSE if accent else LINE, 0.7) +
            mono(tx + (3 if anchor == "start" else -3), ty + 2.5, label, size, col, anchor))


def clock(cx, cy, r, hours, accent=True):
    out = [circle(cx, cy, r, PAGE, ICON, 1.2), circle(cx, cy, r * 0.86, PAGE, HAIR, 0.6)]
    for k in range(12):
        a = math.radians(k * 30 - 90)
        r0 = r * (0.74 if k % 3 == 0 else 0.8)
        out.append(line(cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r * 0.86 * math.cos(a),
                        cy + r * 0.86 * math.sin(a), ICON, 1.1 if k % 3 == 0 else 0.6))
    if accent:
        a1 = -90 + hours * 30
        pts = [(cx, cy)] + [(cx + r * 0.7 * math.cos(math.radians(-90 + (a1 + 90) * k / 40)),
                            cy + r * 0.7 * math.sin(math.radians(-90 + (a1 + 90) * k / 40))) for k in range(41)]
        out.insert(2, poly2(pts, "none", 0, WASH, close=True))
        out.insert(3, arc2(cx, cy, r * 0.7, -90, a1, ROSE, 1.2))
    a = math.radians(-90 + hours * 30)
    out.append(line(cx, cy, cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a), INK, 2.2))
    out.append(line(cx, cy, cx, cy - r * 0.68, INK, 1.2))
    out.append(circle(cx, cy, 2.2, INK, "none"))
    return "".join(out)


# ---------- isometric props ----------

def front(g, u, v, z):
    """A transform taking flat units (x right, y down; one unit = one grid unit) onto the front face
    plane v = const, origin at (u, v, z)."""
    x, y = g.p(u, v, z)
    s = g.s
    return f"matrix({C30 * s:.3f},{0.5 * s:.3f},0,{s:.3f},{x:.2f},{y:.2f})"




def top(g, u, v, z):
    """Flat units onto the floor plane at height z: x along u, y along v."""
    x, y = g.p(u, v, z)
    s = g.s
    return f"matrix({C30 * s:.3f},{0.5 * s:.3f},{-C30 * s:.3f},{0.5 * s:.3f},{x:.2f},{y:.2f})"


def floor_rect(g, u, v, w, d, fill=SUNK, stroke=HAIR, sw=None, dash=None, z=0):
    g.poly(g.pts((u, v, z), (u + w, v, z), (u + w, v + d, z), (u, v + d, z)), fill, stroke, sw=sw or g.sw * 0.9,
           dash=dash)


def plate(g, u, v, w, d, h=0.35, top_fill=PAGE):
    g.box(u, v, w, d, h, top=top_fill, right=SUNK, front=SUNK)


def floor_text(g, s, u, v, size=0.32, fill=QUIET, z=0, weight=400, family="Geist Mono", anchor="start"):
    """Text lying on the floor along u, `size` in grid units."""
    g.raw(f'<g transform="{top(g, u, v, z)}"><text x="0" y="0" font-family="{family}" font-weight="{weight}"'
          f' font-size="{size}" letter-spacing="{size * 0.12:.3f}" fill="{fill}" text-anchor="{anchor}">'
          f'{esc(s.upper() if family == "Geist Mono" else s)}</text></g>')


def front_text(g, s, u, v, z, size=0.3, fill=QUIET, family="Geist Mono", weight=400, anchor="start"):
    g.raw(f'<g transform="{front(g, u, v, z)}"><text x="0" y="0" font-family="{family}" font-weight="{weight}"'
          f' font-size="{size}" letter-spacing="{size * 0.1 if family == "Geist Mono" else 0:.3f}" fill="{fill}"'
          f' text-anchor="{anchor}">{esc(s.upper() if family == "Geist Mono" else s)}</text></g>')


def machine(g, u, v, shape=0, f=0.6, done=False, ship=False, ticket=False, lift=None):
    m = Machine(g, u, v, shape % 24, 0)
    m.draw(0.5, False, 0, (1.0 if done else f, (0.45 if done else 0.0) if lift is None else lift, ticket, ship))
    return m


def crate(g, u, v, w=0.9, d=0.9, h=0.7, label=None, accent=False, dash=None, fill=PAGE):
    stroke = ROSE if accent else ICON
    g.box(u, v, w, d, h, top=fill, right=fill, front=SUNK if fill == PAGE else fill, stroke=stroke, dash=dash)
    if label:
        front_text(g, label, u + 0.08, v + d, h * 0.55, size=min(0.2, 0.9 * w / max(4, len(label)) * 1.4),
                   fill=ROSE_DARK if accent else QUIET)


def sheet(g, u, v, w=0.9, d=1.2, z=0.0, lines=4, label=None, accent=False, fill=PAGE):
    g.poly(g.pts((u, v, z), (u + w, v, z), (u + w, v + d, z), (u, v + d, z)), fill, ROSE if accent else ICON)
    for i in range(lines):
        vv = v + 0.25 + i * (d - 0.4) / max(1, lines)
        g.line((u + 0.15, vv, z), (u + w - 0.15 - (0.25 if i % 2 else 0), vv, z), HAIR, g.sw * 0.8)
    if label:
        floor_text(g, label, u + 0.1, v + d - 0.12, size=min(0.22, w / max(5, len(label)) * 1.5), z=z,
                   fill=ROSE_DARK if accent else QUIET)


def stack(g, u, v, n=4, w=0.9, d=1.1, dz=0.12, accent_top=False):
    for i in range(n):
        g.box(u, v, w, d, dz, top=PAGE, right=PAGE, front=PAGE, stroke=ROSE if accent_top and i == n - 1 else LINE)
        g.oz += dz
    g.oz -= n * dz


def screen(g, u, v, w=2.0, h=1.3, z=0.0, stand=0.6, content=None, lit=True, accent=False):
    """A monitor on a stand facing the viewer (front face), with `content(transform)` drawn in flat
    units: x 0..w, y 0..h."""
    z0 = z + stand
    if stand:
        g.box(u + w / 2 - 0.12, v - 0.12, 0.24, 0.12, stand, top=PAGE, right=SUNK, front=SUNK)
        g.box(u + w / 2 - 0.45, v - 0.35, 0.9, 0.5, 0.06)
    g.box(u, v - 0.12, w, 0.12, h, top=PAGE, right=SUNK, front=PAGE, stroke=ROSE if accent else ICON)
    g.raw(f'<g transform="{front(g, u, v, z0 + h)}">'
          + rect(0.08, 0.08, w - 0.16, h - 0.16, WASH if lit and accent else (PAGE if lit else SUNK), HAIR, 0.02)
          + (content(w, h) if content else "") + "</g>")


def app_ui(w, h, accent=True):
    """A tiny product screen in flat units: header bar, a card, a button."""
    s = min(w, h)
    return (rect(0.08, 0.08, w - 0.16, 0.18, SUNK, "none", 0) +
            rect(0.2, 0.36, w * 0.55, 0.08, HAIR, "none", 0) + rect(0.2, 0.5, w * 0.4, 0.06, HAIR, "none", 0) +
            rect(0.2, 0.68, w - 0.4, h - 1.05, PAGE, HAIR, 0.02, 0.03) +
            rect(0.2, h - 0.3, 0.5, 0.14, ROSE if accent else LINE, "none", 0, 0.03) +
            circle(w - 0.3, 0.17, 0.05 * s, ROSE if accent else LINE, "none", 0))


def code_lines(w, h, n=6, accent_row=None):
    out = []
    for i in range(n):
        y = 0.25 + i * (h - 0.4) / n
        ind = 0.15 * (i % 3)
        out.append(rect(0.2 + ind, y, (w - 0.6 - ind) * (0.5 + 0.4 * ((i * 7) % 5) / 5), 0.06,
                        ROSE if i == accent_row else LINE, "none", 0))
    return "".join(out)


def person(g, u, v, z=0.0, accent=True, scale=1.0, seated=False):
    """An operator as the website draws people: a rounded body and a head, in the person colour."""
    x, y = g.p(u, v, z)
    s = g.s * scale
    col = ROSE if accent else ICON
    bh = (0.75 if seated else 1.15) * s
    g.raw(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{0.36 * s:.2f}" ry="{0.18 * s:.2f}" fill="{SUNK}" stroke="none"/>'
          f'<path d="M{x - 0.3 * s:.2f},{y:.2f} L{x - 0.3 * s:.2f},{y - bh + 0.3 * s:.2f} Q{x - 0.3 * s:.2f},{y - bh:.2f}'
          f' {x:.2f},{y - bh:.2f} Q{x + 0.3 * s:.2f},{y - bh:.2f} {x + 0.3 * s:.2f},{y - bh + 0.3 * s:.2f}'
          f' L{x + 0.3 * s:.2f},{y:.2f} Z" fill="{PAGE}" stroke="{col}" stroke-width="{g.sw * 1.2:.2f}"/>'
          f'<circle cx="{x:.2f}" cy="{y - bh - 0.32 * s:.2f}" r="{0.24 * s:.2f}" fill="{PAGE}" stroke="{col}"'
          f' stroke-width="{g.sw * 1.2:.2f}"/>')


def desk(g, u, v, w=2.2, d=1.0, h=0.75, screens=1, content=None, accent=False):
    g.box(u, v, w, d, h, top=PAGE, right=SUNK, front=SUNK)
    sw = (w - 0.3) / screens
    for i in range(screens):
        screen(g, u + 0.15 + i * sw, v + 0.35, sw - 0.12, 0.8, z=h, stand=0.25,
               content=content[i] if isinstance(content, list) else content, accent=accent and i == 0)


def gate(g, u, v, w=1.6, d=0.5, h=2.2, accent=False):
    """An inspection arch the line passes under."""
    col = ROSE if accent else ICON
    g.box(u, v, 0.3, d, h, stroke=col)
    g.box(u + 0.3 + w, v, 0.3, d, h, stroke=col)
    g.oz += h
    g.box(u, v, w + 0.6, d, 0.32, stroke=col)
    g.oz -= h




def belt(g, u, v, length, w=0.9, h=0.35, along="u"):
    """A conveyor: a low slab with rollers drawn across its top."""
    if along == "u":
        g.box(u, v, length, w, h, top=PAGE, right=SUNK, front=SUNK)
        for k in range(int(length / 0.5)):
            g.line((u + 0.25 + k * 0.5, v + 0.08, h), (u + 0.25 + k * 0.5, v + w - 0.08, h), HAIR, g.sw * 0.8)
    else:
        g.box(u, v, w, length, h, top=PAGE, right=SUNK, front=SUNK)
        for k in range(int(length / 0.5)):
            g.line((u + 0.08, v + 0.25 + k * 0.5, h), (u + w - 0.08, v + 0.25 + k * 0.5, h), HAIR, g.sw * 0.8)


def part(g, u, v, z=0.0, s=0.6, shape=0, accent=True, dash=None):
    """A product: a small box with its shape etched on top."""
    from cover import SHAPES, screen_d
    g.box(u, v, s, s, s * 0.8, dash=dash, stroke=LINE if dash else ICON)
    d = screen_d(g, SHAPES[shape % 24], lambda x, y: (u + s / 2 + x * s * 1.1, v + s / 2 + y * s * 1.1, z + s * 0.8))
    g.raw(f'<path d="{d}" fill="none" stroke="{ROSE if accent else LINE}" stroke-width="{g.sw * 1.3:.2f}"'
          f' stroke-linejoin="round"/>')


def board(g, u, v, w, h, cells, z=0.0, colors=None, label=None):
    """A vertical board on the front plane with a grid of cell states: cells[r][c] in
    {'ok', 'fail', 'ex', 'na', 'warn', ''}; 'ex' is an accepted exception, struck through."""
    colors = colors or {"ok": SUNK, "fail": ROSE, "warn": WASH, "na": PAGE, "": PAGE}
    rows, cols = len(cells), len(cells[0])
    g.box(u, v - 0.15, w, 0.15, h, top=PAGE, right=SUNK, front=PAGE)
    pad, lab = 0.2, 0.0
    cw, ch = (w - 2 * pad) / cols, (h - 2 * pad - lab) / rows
    out = []
    for r, row in enumerate(cells):
        for c, st in enumerate(row):
            cx, cy, cwi, chi = pad + c * cw + 0.03, pad + lab + r * ch + 0.03, cw - 0.06, ch - 0.06
            out.append(rect(cx, cy, cwi, chi, colors.get(st, PAGE),
                            ROSE if st == "fail" else (ICON if st == "ex" else HAIR), 0.02))
            if st == "ex":
                out.append(line(cx + 0.08, cy + chi - 0.08, cx + cwi - 0.08, cy + 0.08, ICON, 0.03))
    g.raw(f'<g transform="{front(g, u, v, z + h)}">{"".join(out)}</g>')
    return pad, cw, ch






# ---------- the fleet, in the cover's grammar ----------
# One arm is one agent on one repository; six stations (3 x 2) make a cell; cells sit on the
# factory floor. Every station uses the cover's machine, so the pedestal, the arm and the assembly
# box keep the same size and offsets in every drawing.

from cover import BOX, GAP, PAD, PITCH_U, PITCH_V  # noqa: E402

CELL_U, CELL_V = 3 * PITCH_U, 2 * PITCH_V
PLATE_Z = 0.45


def station(g, u, v, k, filled=True, accent_done=None):
    """One station of a cell at its grid origin: an arm at work, or an empty slot drawn dashed."""
    if not filled:
        box_u, box_v, e, h = BOX
        g.box(u + box_u, v + box_v, e, e, h, top=PAGE, right=PAGE, front=PAGE, stroke=LINE, dash="1.2 1.6")
        return
    done = (k % 4 == 2) if accent_done is None else accent_done
    m = Machine(g, u, v, k % 24, 0)
    m.draw(0.5, False, 0, (1.0 if done else 0.45 + 0.5 * ((k * 0.381966) % 1.0), 0.45 if done else 0.0,
                           k % 3 == 1, done))


def fleet_size(cells, cols):
    rows = (cells + cols - 1) // cols
    return cols * CELL_U + (cols - 1) * GAP + 2 * PAD, rows * CELL_V + (rows - 1) * GAP + 2 * PAD


def fleet(g, cells=4, cols=2, filled=None, start=0, plate=True, u0=0.0, v0=0.0):
    """Cells of six on a floor plate, as on the cover. `filled` arms are placed cell by cell (the
    rest of the stations show as empty slots); it defaults to every station."""
    total_u, total_v = fleet_size(cells, cols)
    filled = cells * 6 if filled is None else filled
    oz = g.oz
    if plate:
        g.box(u0 - PAD, v0 - PAD, total_u, total_v, PLATE_Z, top=PAGE, right=SUNK, front=SUNK)
        g.oz = oz + PLATE_Z
    slots = []
    for c in range(cells):
        ci, cj = c % cols, c // cols
        cu, cv = u0 + ci * (CELL_U + GAP), v0 + cj * (CELL_V + GAP)
        g.poly(g.pts((cu, cv, 0), (cu + CELL_U, cv, 0), (cu + CELL_U, cv + CELL_V, 0), (cu, cv + CELL_V, 0)),
               SUNK, HAIR, sw=g.sw * 0.9)
        for j in range(2):
            for i in range(3):
                slots.append((cu + i * PITCH_U + 0.1, cv + j * PITCH_V + 0.05, len(slots)))
    order = sorted(slots, key=lambda s: s[0] + s[1])
    for u, v, k in order:
        station(g, u, v, start + k, k < filled)
    g.oz = oz
    return slots
