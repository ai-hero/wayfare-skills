"""One drawing per field-guide page, keyed (guide, page). A scene draws in grid units into an `Iso`
that `canvas` sizes to the page's art box, so a scene never hard-codes page coordinates.
Guide 01 draws the factory as it is meant to work; Guide 02 draws what happened. Every study figure a
drawing shows comes from the page's `data["chart"]` in editions/guides.json, which is gitignored with
the other findings: a number written here would ship the finding and drift from the copy.
Guide 02's charts are flat, in the book's chart grammar: ink and rose only, the finding in rose.
"""
import guide_art as A
from guide_art import HAIR, ICON, INK, LINE, PAGE, QUIET, ROSE, ROSE_DARK, SUNK, WASH, Iso

SCENES = {}


def scene(guide, n, full=False):
    def reg(fn):
        fn.full = full
        SCENES[(guide, n)] = fn
        return fn
    return reg


def canvas(extent, box=None, sw=0.9):
    """An Iso placed so the projected extent ((u0, u1), (v0, v1), (z0, z1)) fills `box` at its final
    size, so strokes keep their page weight whatever the scene's scale."""
    from guides import ART
    x0, y0, x1, y1 = box or ART
    g = Iso(0, 0, 10, sw)
    (u0, u1), (v0, v1), (z0, z1) = extent
    pts = [g.p(u, v, z) for u in (u0, u1) for v in (v0, v1) for z in (z0, z1)]
    bx0, bx1 = min(p[0] for p in pts), max(p[0] for p in pts)
    by0, by1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = min((x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0))
    g.ox = x0 + ((x1 - x0) - (bx1 - bx0) * k) / 2 - bx0 * k
    g.oy = y0 + ((y1 - y0) - (by1 - by0) * k) / 2 - by0 * k
    g.s = 10 * k
    return g


def svg(g):
    return "".join(g.out)


def wrapped(*args, **kw):
    from guides import block
    return block(*args, **kw)


def tag(g, u, v, z, dx, dy, label, accent=False):
    """A flat callout from a grid point to a label offset (dx, dy) points away. A label that would
    run off the page or into the copy column turns to the other side of its point."""
    from guides import ART, W, width
    x, y = g.p(u, v, z)
    size = 7
    w = width(label.upper(), size, "Geist Mono") + len(label) * size * 0.14 + 6
    if dx >= 0 and x + dx + w > W - 20:
        dx = -max(abs(dx), 10)
    elif dx < 0 and x + dx - w < ART[0] - 6:
        dx = max(abs(dx), 10)
    return A.callout(x, y, x + dx, y + dy, label, accent)


def key(g, items, top, cols=2, x0=None):
    """Numbered markers on the drawing and their key in a strip below it, for scenes too crowded for
    leader lines: items = [(u, v, z, label, accent)]."""
    from guides import ART
    x0, x1 = (ART[0] if x0 is None else x0), ART[2]
    out = []
    for n, (u, v, z, label, acc) in enumerate(items, 1):
        x, y = g.p(u, v, z)
        out.append(A.circle(x, y, 7, ROSE if acc else INK, PAGE, 1.2))
        out.append(A.text(x, y + 3, str(n), 7.6, "Geist", 500, PAGE, "middle"))
        cw = (x1 - x0) / cols
        kx, ky = x0 + 12 + ((n - 1) % cols) * cw, top + ((n - 1) // cols) * 20
        out.append(A.circle(kx + 7, ky - 3, 7, ROSE if acc else INK, "none"))
        out.append(A.text(kx + 7, ky, str(n), 7.6, "Geist", 500, PAGE, "middle"))
        out.append(A.text(kx + 20, ky + 0.5, label, 9, "Geist", 400, INK))
    return "".join(out)


def control_room(g, u, v, z=3.4, w=4.4, d=3.6, screens=2, content=None):
    """A raised room on legs, glass at the front, its far walls drawn so it reads as a room."""
    for du, dv in ((0, 0), (w - 0.3, 0), (0, d - 0.3), (w - 0.3, d - 0.3)):
        g.box(u + du, v + dv, 0.3, 0.3, z)
    oz = g.oz
    g.oz = oz + z
    A.plate(g, u - 0.2, v - 0.2, w + 0.4, d + 0.4, 0.3)
    g.oz = oz + z + 0.3
    wall = 1.9
    g.poly(g.pts((u, v, 0), (u + w, v, 0), (u + w, v, wall), (u, v, wall)), A.SUNK, ICON)
    g.poly(g.pts((u, v, 0), (u, v + d, 0), (u, v + d, wall), (u, v, wall)), A.SUNK, ICON)
    for k in range(1, 4):
        g.line((u + k * w / 4, v, 0.9), (u + k * w / 4, v, wall), HAIR, g.sw * 0.7)
    A.desk(g, u + 0.5, v + 0.4, w - 1.0, 0.9, 0.6, screens=screens, content=content)
    A.person(g, u + w / 2, v + d - 1.1)
    g.poly(g.pts((u, v + d, 0.7), (u + w, v + d, 0.7), (u + w, v + d, 0), (u, v + d, 0)), PAGE, ICON)
    g.oz = oz


@scene("g1", 1, full=True)
def g1_cover(p, guide):
    from guides import M, H, W, block
    tu, tv = A.fleet_size(4, 2)
    g = canvas(((-7.6, tu), (-1.0, tv), (0, 7.4)), (392, 70, W - 24, H - 34), 0.8)
    A.fleet(g, 4, 2)
    control_room(g, -7.2, 1.0, content=[lambda w, h: A.code_lines(w, h, 4, 1), lambda w, h: A.app_ui(w, h)])
    out = [svg(g), A.mono(M, 112, f"A companion field guide to {guide['book']}", 7, ROSE_DARK)]
    t, y = block(M, 168, p["headline"], 330, 42, "Manrope", 200, INK, 1.04, -0.84)
    s, y = block(M, y + 14, p.get("subhead", ""), 300, 15, "Geist", 300, ICON, 1.4)
    b, y = block(M, y + 22, p["body"], 280, 10.5, "Geist", 300, QUIET, 1.5)
    out += [t, s, b, A.rect(M, H - 92, 22, 0.8, HAIR, "none", 0),
            A.text(M, H - 72, guide["author"], 13, "Geist", 400, INK)]
    return "".join(out)


@scene("g1", 2)
def g1_agents_not_factory(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    mid = (x0 + x1) / 2
    g = canvas(((-1.2, 9.4), (-1.8, 11.2), (0, 3.6)), (x0, y0 + 50, mid - 18, y1 - 40))
    for u, v, k in [(0, 0, 3), (4.4, -1.4, 9), (1.4, 4.4, 5), (5.8, 3.4, 13), (-0.6, 8.2, 18)]:
        A.station(g, u, v, k, accent_done=False)
        A.stack(g, u + 2.7, v + 2.0, 2 + k % 3, 0.7, 0.8, 0.1)
    tu, tv = A.fleet_size(1, 1)
    g2 = canvas(((-1.6, tu + 3.4), (-0.6, tv + 4.0), (0, 3.6)), (mid + 18, y0 + 50, x1, y1 - 40))
    A.fleet(g2, 1, 1)
    g2.box(-0.6, tv - 0.2, tu, 3.6, A.PLATE_Z, top=PAGE, right=SUNK, front=SUNK)
    g2.oz = A.PLATE_Z
    A.belt(g2, -0.2, tv + 0.6, tu - 0.8, 0.8)
    A.gate(g2, 5.4, tv + 0.4, 0.8, 1.2, 1.6, accent=True)
    A.part(g2, 2.0, tv + 0.75, 0.35, 0.5, 3)
    A.part(g2, 8.0, tv + 0.75, 0.35, 0.5, 9)
    g2.oz = 0
    A.screen(g2, tu + 0.4, tv + 0.2, 2.2, 1.4, stand=0.5, content=lambda w, h: A.app_ui(w, h), accent=True)
    g2.path([(tu + 1.6, tv + 3.0, A.PLATE_Z), (-0.9, tv + 3.0, A.PLATE_Z), (-0.9, 2.0, A.PLATE_Z)], ROSE, sw=1.4)
    g2.head((-0.9, 3.0, A.PLATE_Z), (-0.9, 2.0, A.PLATE_Z), ROSE, g2.s * 0.5)
    items = [(1.6, 1.6, 3.4, "A cell of six agents, one per repository", False),
             (5.8, tv + 0.8, 2.2, "Checks the result", True), (tu + 1.5, tv + 0.2, 2.4, "Ships it", True),
             (4.0, tv + 3.0, A.PLATE_Z, "Improves its own process", True)]
    out = [svg(g), svg(g2), A.line(mid, y0 + 30, mid, y1 - 60, HAIR, 0.8),
           A.mono(x0 + 6, y0 + 22, "Agents, one per engineer", 7),
           A.mono(mid + 22, y0 + 22, "Agents inside a factory", 7, ROSE_DARK), key(g2, items, y1 - 44)]
    return "".join(out)


@scene("g1", 3)
def g1_product(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-1, 22.4), (-1, 10.0), (0, 3.6)), (x0, y0, x1, y1 - 80))
    A.plate(g, -1, -1, 23.4, 6.2, 0.3)
    g.oz = 0.3
    A.belt(g, -0.6, 1.6, 15.0, 0.9)
    A.sheet(g, -0.4, 1.7, 0.8, 0.7, 0.4, 3, accent=True)
    A.machine(g, 2.0, -0.8, 7, 0.6)
    A.part(g, 5.6, 1.75, 0.35, 0.6, 7, accent=False)
    A.stack(g, 8.0, 1.65, 3, 0.7, 0.8, 0.1)
    A.gate(g, 10.4, 1.35, 0.9, 1.4, 1.7)
    for k, (u, v) in enumerate(((19.6, 0.4), (19.6, 3.8))):
        A.screen(g, u, v, 1.8, 1.1, stand=0.5, content=lambda w, h: A.app_ui(w, h, False))
    A.screen(g, 15.6, 2.4, 3.0, 1.9, stand=0.7, content=lambda w, h: A.app_ui(w, h), accent=True)
    g.oz = 0
    A.floor_rect(g, 4.6, 6.4, 8.6, 3.0, PAGE, LINE, dash="1.2 1.6")
    for k in range(5):
        A.crate(g, 5.0 + k * 1.6, 7.0, 1.1, 1.1, 0.8 + 0.25 * (k % 2), dash="1.2 1.4")
    items = [(0.0, 2.0, 0.8, "A need, design, observation or decision", True), (3.2, 0.2, 3.4, "Code", False),
             (8.4, 2.0, 1.0, "Pull request", False), (11.2, 1.8, 2.4, "Green merge: passed in a test environment", False),
             (17.1, 2.4, 3.2, "Running in production", True), (20.5, 3.8, 2.0, "Across apps and shared systems", False),
             (8.4, 7.4, 1.4, "Inventory: changes that never leave their branch", False)]
    return svg(g) + key(g, items, y1 - 58)


@scene("g1", 4)
def g1_fleet(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    order = ["Applications", "Shared services", "Template", "Plugin", "Infrastructure"]
    kinds = {k["kind"].split(" (")[0]: k for k in p["data"]["kinds"]}
    layers = [dict(kinds[o], kind=o) for o in order if o in kinds]
    gap, pw, pd = 5.6, 6.6, 3.6
    g = canvas(((0, pw), (0, pd), (0, gap * (len(layers) - 1) + 1.6)), (x0, y0 + 6, x0 + 250, y1 - 6))
    flat = []
    n = len(layers)
    for i, layer in enumerate(reversed(layers)):
        z = i * gap
        g.oz = z
        if i:
            for du, dv in ((pw - 0.3, 0.3), (0.3, pd - 0.3), (pw - 0.3, pd - 0.3)):
                g.line((du, dv, -gap + 0.25), (du, dv, 0), HAIR, g.sw * 0.8, "1.2 1.6")
        A.plate(g, 0, 0, pw, pd, 0.25, PAGE if i < n - 1 else WASH)
        g.oz = z + 0.25
        repos = layer["repos"]
        cols = min(5, len(repos))
        for k in reversed(range(len(repos))):
            A.crate(g, 0.4 + (k % cols) * 1.22, 0.4 + (k // cols) * 1.5, 0.85, 0.95, 0.55 + 0.15 * (k % 3),
                    accent=i == n - 1)
        x, y = g.p(pw, pd, 0)
        lx = x0 + 280
        flat.append(A.poly2([(x + 6, y - 6), (lx - 8, y - 6)], HAIR, 0.6))
        flat.append(A.mono(lx, y - 9, f"{layer['kind']} · {len(repos)}", 7.4, ROSE_DARK if i == n - 1 else ICON))
        b, _ = wrapped(lx, y + 4, ", ".join(r.split(" (")[0] for r in repos), x1 - lx, 7.4,
                                          "Geist Mono", 400, QUIET, 1.45)
        flat.append(b)
    g.oz = 0
    return svg(g) + "".join(flat)


@scene("g1", 5)
def g1_floor_and_control(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    tu, tv = A.fleet_size(4, 2)
    g = canvas(((-7.6, tu), (-1.0, tv), (0, 7.6)), (x0, y0, x1, y1 - 64))
    A.fleet(g, 4, 2)
    control_room(g, -7.2, 1.0, content=[lambda w, h: A.app_ui(w, h, False), lambda w, h: A.code_lines(w, h, 5, 2)])
    items = [(-5.0, 2.4, 6.0, "Control room: intent, goals, policy, fleet map, evidence", False),
             (-7.2, 4.6, 1.6, "Today: I start every session", True),
             (4.9, 2.8, 0.45, "A cell: six agents, each on its own repository", False),
             (15.6, 10.6, 0.45, "The factory floor: the whole fleet", False)]
    return svg(g) + key(g, items, y1 - 44) + \
        A.text(x1, y0 + 10, "An independent control plane is proposed, not built.", 8, "Geist", 300, QUIET, "end")


@scene("g1", 6)
def g1_five_flows(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    cu, cv = A.fleet_size(1, 1)
    build_u = 6.0
    g = canvas(((-1.4, build_u + cu + 11.0), (-1, cv + 6.4), (0, 3.4)), (x0, y0, x1, y1 - 64))
    total = build_u + cu + 10.4
    g.box(-1.0, -1.0, total + 1.0, cv + 7.0, 0.35, top=PAGE, right=SUNK, front=SUNK)
    g.oz = 0.35
    A.floor_rect(g, 0, 0, 4.6, cv - 1.0, SUNK, HAIR)
    for i, (lab, acc) in enumerate((("feedback", False), ("alert", True))):
        A.crate(g, 0.6 + i * 2.0, 0.8, 1.3, 1.1, 0.8 + 0.3 * i, None, acc)
    A.fleet(g, 1, 1, plate=False, u0=build_u + A.PAD, v0=A.PAD)
    A.belt(g, 0.2, cv + 0.4, total - 0.6, 0.8)
    A.gate(g, build_u + cu + 2.0, cv + 0.1, 0.8, 1.3, 1.8)
    A.screen(g, build_u + cu + 5.6, cv - 0.6, 2.8, 1.8, stand=0.7, content=lambda w, h: A.app_ui(w, h), accent=True)
    A.floor_rect(g, -0.4, cv + 2.0, total - 0.2, 1.8, PAGE, ROSE)
    for k in range(8):
        A.part(g, 1.0 + k * 2.6, cv + 2.4, 0.0, 0.8, 4 + k, accent=k != 4)
    ru = total - 0.2
    g.path([(ru, cv + 2.9, 0), (ru, cv + 5.4, 0), (-0.6, cv + 5.4, 0), (-0.6, 1.8, 0)], ROSE, sw=1.6)
    g.head((-0.6, 2.8, 0), (-0.6, 1.8, 0), ROSE, g.s * 0.5)
    items = [(1.6, 1.0, 1.6, "Direction: signals become authorized work", False),
             (build_u + 5.0, 2.6, 3.4, "Build: a cell of agents plans, builds, tests and records", True),
             (build_u + cu + 2.6, cv + 0.4, 2.4, "Delivery: review, merge, deploy, observe", False),
             (12.0, cv + 2.9, 1.0, "Consistency: across the whole fleet", True),
             (10.0, cv + 5.4, 0.0, "Improvement: back into the factory", True)]
    return svg(g) + key(g, items, y1 - 44)


@scene("g1", 7)
def g1_direction(p, guide):
    d = p["data"]
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-1, 17), (-1, 11), (0, 7.2)), (x0, y0, x1, y1 - 64))
    A.plate(g, -1, -1, 18, 12, 0.3)
    g.oz = 0.3
    A.floor_rect(g, -0.4, 3.6, 6.4, 7.2, SUNK, HAIR)
    crates = [("Customers", 0.0, 4.0, 1.1, False), ("Designs", 2.2, 4.0, 0.9, False), ("Scanners", 4.4, 4.0, 1.0, False),
              ("Alerts", 0.0, 7.2, 1.0, True), ("Audits", 2.2, 7.2, 1.1, False), ("Agents", 4.4, 7.2, 0.9, False)]
    for lab, u, v, h, acc in crates:
        A.crate(g, u, v, 1.2, 1.0, h, None, acc)
    A.machine(g, 6.6, 4.6, 12, 0.6)
    A.belt(g, 9.6, 6.0, 7.0, 0.9)
    for k in range(4):
        A.sheet(g, 10.0 + k * 1.6, 6.1, 0.9, 0.7, 0.35, 3, accent=k == 0)
    g.oz = 0
    control_room(g, 9.4, -0.6, 3.6, 5.0, 3.6, screens=1, content=lambda w, h: A.code_lines(w, h, 4, 0))
    flat = []
    for lab, u, v, h, acc in crates:
        x, y = g.p(u + 0.6, v + 1.0, 0.3)
        flat.append(A.mono(x, y + 12, lab, 6.4, ROSE_DARK if acc else ICON, "middle"))
    c = d["chart"]
    items = [(7.6, 5.4, 3.6, f"Found by agents mid-task: {c['found']:,} of {c['items']:,} work items "
              f"({c['found_pct']}%)", True),
             (14.0, 6.4, 0.9, f"Authorized work · open backlog {c['backlog_from']} → {c['backlog_to']}", True),
             (11.2, 1.6, 6.8, "Purpose, priority and risk stay with people", False)]
    return svg(g) + "".join(flat) + key(g, items, y1 - 44)


@scene("g1", 8)
def g1_blueprint(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-2, 13), (-2, 10), (0, 4.2)), (x0, y0, x1, y1 - 64))
    A.floor_rect(g, -2, -2, 15, 12, SUNK, HAIR)
    g.box(0, 0, 8, 6, 1.1, top=PAGE, right=SUNK, front=SUNK)
    z = 1.1
    rows = ("PROBLEM", "OUTCOME", "CONSTRAINTS", "DONE WHEN")
    g.raw(f'<g transform="{A.top(g, 0.4, 0.4, z)}">'
          + A.rect(0, 0, 7.2, 5.2, WASH, ROSE, 0.04)
          + "".join(A.line(0, k * 1.3, 7.2, k * 1.3, ROSE, 0.015, "0.08 0.1") for k in (1, 2, 3))
          + "".join(A.text(0.25, 0.85 + k * 1.3, lab, 0.42, "Geist Mono", 500, ROSE_DARK, spacing=0.05)
                    for k, lab in enumerate(rows))
          + "".join(A.rect(3.6, 0.45 + k * 1.3 + j * 0.28, 3.0 - j * 0.9, 0.08, LINE, "none", 0)
                    for k in range(4) for j in range(2)) + "</g>")
    A.person(g, 3.0, 7.3, 0)
    A.machine(g, 8.8, 1.2, 9, 0.5)
    A.sheet(g, 10.4, 6.6, 1.6, 1.2, 0.0, 3, accent=True)
    g.path([(8.2, 5.4, 1.1), (10.6, 6.8, 0.1)], ROSE, dash="1.2 1.6")
    items = [(3.0, 7.3, 1.9, "Settled early: product and risk decisions", True),
             (10.2, 2.6, 3.6, "Left to the agent: function boundaries, tests, libraries", False),
             (11.2, 7.2, 0.1, "The agreed plan goes to the floor", True)]
    return svg(g) + key(g, items, y1 - 44)


@scene("g1", 9)
def g1_work_cell(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-4.4, 10.4), (-3.6, 9.4), (0, 4.4)), (x0, y0, x1, y1 - 64))
    A.floor_rect(g, -4.0, -3.2, 14.0, 12.2, SUNK, HAIR)
    A.floor_rect(g, -1.6, -1.2, 9.0, 8.0, WASH, ROSE)
    A.machine(g, 1.4, 1.2, 9, 0.65)
    mods = [("Tools", -1.2, 3.0), ("Context", 2.0, -0.8), ("Subagents", 5.6, -0.8), ("Checks", 5.6, 4.6)]
    flat = []
    for name, u, v in mods:
        A.crate(g, u, v, 1.5, 1.3, 0.8)
    for name, u, v in mods:
        x, y = g.p(u + 0.75, v + 0.65, 1.0)
        flat.append(A.mono(x, y - 10, name, 7.2, ICON, "middle"))
    items = [(3.1, 2.4, 3.6, "The model, innermost", True),
             (7.0, 6.4, 0, "The harness: what the model sees, tools, compaction", True),
             (9.4, 8.4, 0, "Repository + agent environment = one work cell", False)]
    return svg(g) + "".join(flat) + key(g, items, y1 - 44)


@scene("g1", 10)
def g1_context(p, guide):
    g = canvas(((-1, 15), (-1, 7), (0, 5.6)), None)
    A.floor_rect(g, -1, -1, 16, 8, SUNK, HAIR)
    g.box(0, 0, 9.6, 2.6, 2.0, top=PAGE, right=SUNK, front=PAGE)
    drawers = ["AGENTS.md", "HERO.md", "DESIGN.md", "skills", "plans", "design", "memory", ""]
    for k, lab in enumerate(drawers):
        col, row = k % 4, k // 4
        g.raw(f'<g transform="{A.front(g, 0.2 + col * 2.35, 2.6, 1.85 - row * 0.9)}">'
              + A.rect(0, 0, 2.15, 0.75, PAGE, ICON, 0.035) + A.rect(0.8, 0.52, 0.55, 0.07, LINE, "none", 0)
              + A.text(0.14, 0.36, lab, 0.3, "Geist Mono", 500, ROSE_DARK if k in (0, 1, 2) else ICON) + "</g>")
    A.sheet(g, 1.0, 0.4, 1.2, 1.0, 2.0, 3, accent=True)
    A.sheet(g, 6.8, 0.6, 1.2, 1.0, 2.0, 3)
    A.machine(g, 11.0, 0.8, 4, 0.55)
    g.path([(1.6, 0.9, 2.1), (6.0, 0.0, 4.6), (12.0, 1.8, 2.2)], ROSE, dash="1.4 1.8")
    g.path([(7.4, 1.1, 2.1), (9.0, 0.6, 3.6), (12.0, 1.8, 2.2)], ROSE, dash="1.4 1.8")
    from guides import ART
    x0, y0, x1, y1 = ART
    bx, by = x0, y1 - 60
    c = p["data"]["chart"]
    before, after = c["startup_kb_before"], c["startup_kb_after"]
    bars = [(f"{before} KB", before, LINE), (f"{after} KB", after, ROSE)]
    out = [A.mono(bx, by - 8, "Median app start-up text", 6.6, ROSE_DARK)]
    for k, (lab, v, col) in enumerate(bars):
        out.append(A.rect(bx, by + k * 20, 150 * v / before, 14, col, "none", 0))
        out.append(A.text(bx + 150 * v / before + 6, by + k * 20 + 10.5, lab, 8.4, "Geist", 500, INK))
    return svg(g) + "".join(out) + \
        tag(g, 6.0, 0.0, 4.6, 10, -30, "Load what this task needs, when it needs it", True) + \
        tag(g, 3.0, 2.6, 0.0, -20, 50, "Records that outlive the session")


@scene("g1", 11)
def g1_messages(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-1, 21), (-1, 9.4), (0, 4.2)), (x0, y0, x1, y1 - 64))
    for k, (u, s, name) in enumerate(((0, 3, "Repository A"), (12.6, 14, "Repository B"))):
        A.floor_rect(g, u - 0.6, -0.6, 8.0, 6.8, SUNK, HAIR)
        A.machine(g, u + 0.4, 0.4, s, 0.6)
        A.floor_text(g, name, u, 5.9, 0.42, QUIET)
    A.belt(g, 6.8, 2.6, 6.2, 0.8)
    A.crate(g, 8.6, 2.55, 1.2, 0.9, 0.8, None, True)
    A.crate(g, 12.8, 4.4, 1.4, 1.2, 1.0, None, False)
    g.path([(16.0, 6.2, 0), (16.0, 7.6, 0), (7.2, 7.6, 0)], ROSE, sw=1.6)
    g.path([(5.6, 7.6, 0), (3.4, 7.6, 0), (3.4, 6.4, 0)], ROSE, sw=1.6, dash="1.2 1.6")
    items = [(9.2, 3.0, 1.2, "Request: evidence, outcome, urgency, origin, reply-to", True),
             (13.5, 5.0, 1.3, "The owner's inbox", False),
             (6.4, 7.6, 0, "Requests arrived; several replies never did", True)]
    return svg(g) + key(g, items, y1 - 44)


@scene("g1", 12)
def g1_delivery(p, guide):
    g = canvas(((-1, 24), (-1, 7), (0, 4.0)))
    A.plate(g, -1, -1, 25, 7, 0.3)
    g.oz = 0.3
    stations = ["Local + CI", "Review", "Merge policy", "Production"]
    for k, name in enumerate(stations):
        A.floor_rect(g, k * 5.6, 0, 5.0, 5.0, WASH if k == 3 else SUNK, ROSE if k == 3 else HAIR)
        A.floor_text(g, name, k * 5.6 + 0.3, 4.8, 0.48, ROSE_DARK if k == 3 else QUIET)
    A.belt(g, 0.4, 2.0, 15.2, 0.8)
    A.machine(g, 0.4, -0.6, 2, 0.6)
    A.part(g, 3.4, 2.1, 0.35, 0.55, 2)
    A.gate(g, 6.4, 1.8, 0.8, 1.2, 1.6)
    A.part(g, 9.0, 2.1, 0.35, 0.55, 2)
    A.sheet(g, 11.8, 0.8, 1.6, 1.2, 0, 3, accent=False)
    A.part(g, 14.6, 2.1, 0.35, 0.55, 2)
    g.poly(g.pts((16.5, -1, 0), (16.5, 6, 0), (16.5, 6, 3.4), (16.5, -1, 3.4)), WASH, ROSE, sw=g.sw * 1.4)
    A.screen(g, 18.0, 2.4, 3.6, 2.2, stand=0.6, content=lambda w, h: A.app_ui(w, h), accent=True)
    mins = p["data"]["median_merge_to_production_minutes"]
    return svg(g) + tag(g, 16.5, -1.0, 3.4, -10, -40, "Merge hands the change to delivery", True) + \
        tag(g, 21.0, 4.6, 0.3, -10, 50, f"Deploy, then health checks · median {mins} min", True)


@scene("g1", 13)
def g1_sensors(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    g = canvas(((-1, 22), (-1, 8), (0, 4.4)), (x0, y0, x1, y1 - 80))
    A.floor_rect(g, -1, -1, 23, 9, SUNK, HAIR)
    A.belt(g, -0.6, 2.4, 22.2, 1.0)
    labels = ["Tests", "CI", "Review agents", "Merge policy"]
    for k in range(4):
        A.gate(g, 3.0 + k * 4.4, 2.1, 1.0, 1.6, 2.0)
    A.part(g, 0.2, 2.55, 0.35, 0.7, 10, dash="1.2 1.4")
    A.part(g, 20.2, 2.55, 0.35, 0.7, 10)
    g.path([(4.6, 3.4, 0.35), (4.6, 5.6, 0)], ROSE, sw=1.2)
    g.head((4.6, 4.8, 0.1), (4.6, 5.6, 0), ROSE, g.s * 0.4)
    A.crate(g, 3.9, 5.7, 1.4, 1.4, 0.6, None, True)
    hc = p["data"]["hollow_checks"]["total"]
    items = [(0.55, 2.9, 1.2, "A known-bad case the check must reject", True)]
    items += [(3.8 + k * 4.4, 2.9, 2.6, lab, False) for k, lab in enumerate(labels)]
    items += [(4.6, 6.4, 1.0, f"Rejected. My factory found {hc} checks that could not fail", True)]
    return svg(g) + key(g, items, y1 - 58)


@scene("g1", 14)
def g1_production(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    out = []
    ux, uy, uw, uh = x0 + 10, y0 + 70, 180, 300
    out.append(A.rect(ux, uy, uw, uh, PAGE, ICON, 1.0, 10))
    out.append(A.rect(ux + 14, uy + 16, uw - 28, 18, A.SUNK, "none", 0, 3))
    out.append(A.text(ux + 18, uy + 76, "Sign in", 16, "Manrope", 300, INK))
    for k in range(2):
        out.append(A.rect(ux + 18, uy + 96 + k * 44, uw - 36, 28, PAGE, HAIR, 0.8, 4))
    out.append(A.rect(ux + 18, uy + 196, uw - 36, 30, ROSE, "none", 0, 4))
    out.append(A.text(ux + uw / 2, uy + 216, "Continue", 10, "Geist", 500, PAGE, "middle"))
    out.append(A.mono(ux, uy - 12, "What the user sees", 7, ROSE_DARK))
    tx = ux + uw + 30
    tw = x1 - tx
    out.append(A.mono(tx, uy - 12, "What the factory should know", 7))
    out.append(A.rect(tx, uy, tw, uh, PAGE, ICON, 1.0, 6))
    rows = [("Version", "v2.14.3 · sha 9f3c1e"), ("Deployment", "succeeded"), ("Responds", "sign-in returns 200"),
            ("Health", ""), ("Follow-up", "1 open item")]
    for k, (a, b) in enumerate(rows):
        y = uy + 28 + k * 28
        out.append(A.mono(tx + 14, y, a, 6.6))
        out.append(A.text(tx + 96, y, b, 9, "Geist Mono", 400, INK))
    hy = uy + 28 + 3 * 28 - 3
    pts = [(tx + 96 + i * 9, hy - 3 * ((i * 7) % 3)) for i in range(14)]
    out.append(A.poly2(pts, ROSE, 1.2))
    cy = uy + 210
    chain = ["Goal", "Change set", "Review", "Merge", "Deploy", "Health"]
    cw = (tw - 20) / len(chain)
    for k, c in enumerate(chain):
        cx = tx + 10 + k * cw
        out.append(A.rect(cx, cy, cw - 8, 26, WASH if k == 0 else PAGE, ROSE if k == 0 else ICON, 0.9, 4))
        out.append(A.text(cx + (cw - 8) / 2, cy + 16.5, c, 7.4, "Geist", 400, INK, "middle"))
        if k:
            out.append(A.arrow2([(cx - 1, cy + 13), (cx - 7, cy + 13)], ROSE, 0.9, k=3.5))
    out.append(A.mono(tx + 10, cy - 12, "Trace a failure back to the change behind it", 6.6, ROSE_DARK))
    out.append(A.text(tx + 10, cy + 56, "Illustrative values", 7.4, "Geist", 300, QUIET))
    return "".join(out)


@scene("g1", 15)
def g1_drift(p, guide):
    g = canvas(((-4, 20), (-1, 9), (0, 4.0)))
    A.floor_rect(g, -4, -1, 24, 10, SUNK, HAIR)
    A.sheet(g, -3.4, 1.4, 2.2, 2.6, 0, 4, accent=True)
    flat = [tag(g, -2.3, 1.4, 0, -10, -40, "A shared source changes", True)]
    kinds = ["same", "intended", "drift", "same", "drift"]
    words = {2: "Unnoticed, no owner", 4: "No recorded decision"}
    for k, kind in enumerate(kinds):
        u = 0.8 + k * 3.6
        g.box(u, 1.0, 2.4, 2.4, 1.2, stroke=ROSE if kind == "drift" else ICON)
        g.oz = 1.2
        if kind == "intended":
            g.box(u + 0.4, 1.4, 1.2, 1.2, 0.8, dash="1.2 1.4", stroke=LINE)
        elif kind == "drift":
            g.box(u + 0.3 + 0.4 * (k % 2), 1.3, 1.0, 1.6, 0.6 + 0.3 * (k % 3), stroke=ROSE)
        else:
            g.box(u + 0.6, 1.6, 1.2, 1.2, 0.6)
        g.oz = 0
        g.line((-1.2, 2.7, 0), (u, 2.2, 0), HAIR, g.sw * 0.7, "1 1.6")
        if kind == "intended":
            flat.append(tag(g, u + 1.0, 1.4, 2.0, 6, -50, "Deliberate and versioned"))
        elif kind == "drift":
            flat.append(tag(g, u + 1.2, 1.0, 2.0, 6, -40 - 14 * (k % 3), words[k], True))
    A.machine(g, 5.6, 5.0, 21, 0.4)
    return svg(g) + "".join(flat)


@scene("g1", 16)
def g1_rules(p, guide):
    import random
    from guides import ART
    x0, y0, x1, y1 = ART
    rnd = random.Random(7)
    rows, cols = 6, 9
    cells = [["fail" if rnd.random() < 0.1 else "ok" for _ in range(cols)] for _ in range(rows)]
    cells[2][5], cells[4][1], cells[0][7] = "fail", "ex", "ex"
    g = canvas(((-1, 13), (-1, 6), (0, 6.6)), (x0, y0 + 20, x0 + 360, y1 - 40))
    A.floor_rect(g, -1, -1, 14, 7, SUNK, HAIR)
    A.board(g, 0, 2.0, 11.0, 6.0, cells)
    A.machine(g, 9.6, 3.4, 0, 0.5)
    out = [svg(g)]
    lx, ly = x0 + 380, y0 + 70
    for k, (lab, fill, stroke) in enumerate((("Conforms", SUNK, HAIR), ("Needs work", ROSE, ROSE),
                                            ("Accepted exception", PAGE, ICON))):
        y = ly + k * 22
        out.append(A.rect(lx, y - 9, 12, 12, fill, stroke, 0.8, 1))
        if k == 2:
            out.append(A.line(lx + 2, y + 1, lx + 10, y - 7, ICON, 0.9))
        out.append(A.text(lx + 20, y + 1, lab, 9, "Geist", 400, INK))
    cy = ly + 90
    out.append(A.mono(lx, cy - 8, "One rule in the register", 6.6, ROSE_DARK))
    out.append(A.rect(lx, cy, x1 - lx, 150, PAGE, ICON, 1.0, 6))
    for k, f in enumerate(p["data"]["register_rule_fields"]):
        out.append(A.mono(lx + 12, cy + 22 + k * 21, f, 6.6))
        out.append(A.rect(lx + 100, cy + 16 + k * 21, (x1 - lx - 120) * (0.8 - 0.1 * (k % 3)), 6,
                          ROSE if f == "executable check" else HAIR, "none", 0))
    out.append(A.text(x0, y1 - 22, "Rows are rules, columns are repositories. Illustrative layout.", 8, "Geist", 300,
                      QUIET))
    return "".join(out)


@scene("g1", 17)
def g1_improve(p, guide):
    import math
    g = canvas(((-7, 7), (-7, 7), (0, 4.0)))
    A.floor_rect(g, -7, -7, 14, 14, SUNK, HAIR)
    A.machine(g, -1.8, -1.6, 13, 0.5)
    pts = [(6.2 * math.cos(math.radians(a)), 6.2 * math.sin(math.radians(a)), 0) for a in range(-150, 170, 5)]
    g.path(pts, ROSE, sw=2.0)
    g.head(pts[-2], pts[-1], ROSE, g.s * 0.6)
    A.part(g, 4.4, 3.4, 0, 0.9, 13, dash="1.2 1.4")

    def on(a, z=0):
        return 6.2 * math.cos(math.radians(a)), 6.2 * math.sin(math.radians(a)), z
    flat = [tag(g, *on(30), 30, 20, "1 Measure waiting, cost, defects, drift"),
            tag(g, *on(100), -10, 40, "2 A failure recurs", True),
            tag(g, *on(172), 10, -70, "3 Change a guide and a sensor", True),
            tag(g, *on(-100), 30, -60, "4 Ship it as versioned software")]
    return svg(g) + "".join(flat)


@scene("g1", 18)
def g1_attention(p, guide):
    from guides import ART
    x0, y0, x1, y1 = ART
    out = [A.rect(x0, y0 + 30, x1 - x0 - 30, y1 - y0 - 60, PAGE, ICON, 1.0, 8)]
    gx, gy = x0 + 24, y0 + 60
    for k, lab in enumerate(("Tokens", "CI minutes", "Compute")):
        val = (0.42, 0.66, 0.3)[k]
        cx, cy, r = gx + 50 + k * 100, gy + 70, 36
        out.append(A.arc2(cx, cy, r, 180, 360, HAIR, 6))
        out.append(A.arc2(cx, cy, r, 180, 180 + 180 * val, ICON, 6))
        out.append(A.mono(cx, cy + 18, lab, 6.8, anchor="middle"))
    qy = gy + 135
    out.append(A.mono(gx, qy, "Where changes wait", 7))
    for k, (lab, v, acc) in enumerate((("For a person", 0.92, True), ("For a dependent repository", 0.46, False),
                                       ("For a stuck pipeline", 0.3, False))):
        y = qy + 14 + k * 30
        out.append(A.rect(gx, y, 290, 16, A.SUNK, "none", 0, 3))
        out.append(A.rect(gx, y, 290 * v, 16, ROSE if acc else LINE, "none", 0, 3))
        out.append(A.text(gx + 6, y + 11.5, lab, 8, "Geist", 500, PAGE))
    ax = x1 - 30 - 190
    out.append(A.mono(ax, gy + 4, "Autonomy can grow where", 6.8, ROSE_DARK))
    for k, lab in enumerate(("impact is limited", "rollback is reliable", "failures are noticed quickly",
                             "evidence is independent")):
        y = gy + 24 + k * 24
        out.append(A.rect(ax, y - 9, 11, 11, WASH, ROSE, 0.9, 2))
        out.append(A.poly2([(ax + 2.5, y - 3.5), (ax + 5, y - 1), (ax + 9, y - 7)], ROSE_DARK, 1.1))
        out.append(A.text(ax + 18, y + 0.5, lab, 9, "Geist", 400, INK))
    cx = x1 - 12
    out.append(A.line(cx, y0 + 20, cx, y1 - 110, ROSE, 1.4))
    out.append(A.rect(cx - 7, y1 - 110, 14, 26, ROSE, "none", 0, 4))
    out.append(A.mono(cx - 26, y1 - 92, "Stop the line (proposed)", 6.6, ROSE_DARK, "end"))
    out.append(A.text(gx, y1 - 44, "Illustrative values", 7.4, "Geist", 300, QUIET))
    return "".join(out)


@scene("g1", 19, full=True)
def g1_questions(p, guide):
    from guides import M, block
    out = []
    t, y = block(M, 96, p["headline"], 300, 30, "Manrope", 200, INK, 1.08, -0.6)
    b, y = block(M, y + 16, p["body"], 300, 11.2, "Geist", 300, INK, 1.5)
    out += [t, b]
    px, py, pw, ph = 392, 60, 520, 420
    out.append(A.rect(px, py, pw, ph, PAGE, ICON, 1.2, 4))
    zones = [("Direction", 0.04, 0.06, 0.28, 0.4), ("Build", 0.36, 0.06, 0.28, 0.4),
             ("Delivery", 0.68, 0.06, 0.28, 0.4), ("Consistency", 0.04, 0.52, 0.92, 0.19),
             ("Improvement", 0.04, 0.76, 0.92, 0.19)]
    for k, (name, zx, zy, zw, zh) in enumerate(zones):
        x, y, w, h = px + zx * pw, py + zy * ph, zw * pw, zh * ph
        out.append(A.rect(x, y, w, h, A.SUNK, HAIR, 0.8, 2))
        out.append(A.mono(x + 8, y + 14, name, 6.6))
        cx, cy = x + w - 16, y + 16
        out.append(A.circle(cx, cy, 10, ROSE, "none"))
        out.append(A.text(cx, cy + 3.6, str(k + 1), 10, "Geist", 500, PAGE, "middle"))
        qs = p["data"]["checklist"][k]["question"]
        lines, yy = block(x + 8, y + 36, qs, w - 40, 10, "Geist", 400, INK, 1.4)
        out.append(lines)
        for j, opt in enumerate(("Yes", "Partly", "No")):
            bx = x + 8 + j * 46
            out.append(A.rect(bx, y + h - 22, 9, 9, PAGE, ICON, 0.8, 1.5))
            out.append(A.text(bx + 14, y + h - 14.5, opt, 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g1", 20, full=True)
def g1_close(p, guide):
    from guides import H, M, W, block
    tu, tv = A.fleet_size(4, 2)
    g = canvas(((-7.6, tu), (-1.0, tv), (0, 7.4)), (392, 120, 790, H - 60), 0.7)
    A.fleet(g, 4, 2)
    control_room(g, -7.2, 1.0, content=[lambda w, h: A.code_lines(w, h, 4, 1), lambda w, h: A.app_ui(w, h)])
    out = [svg(g)]
    t, y = block(M, 110, p["headline"], 300, 32, "Manrope", 200, INK, 1.08, -0.64)
    b, y = block(M, y + 16, p["body"], 300, 11.6, "Geist", 300, INK, 1.5)
    out += [t, b, cover_thumb(W - 150, 92, 104), cta(M, H - 150, p["data"]["cta"])]
    return "".join(out)


def cover_thumb(x, y, w):
    """The book's front cover, small, from the cover module's own drawing."""
    import json
    import cover
    import paths
    with open(paths.META, encoding="utf-8") as f:
        meta = json.load(f)
    front, _ = cover.front_svg(meta, bleed=0)
    h = w * cover.TRIM_H / cover.TRIM_W
    inner = front.replace("<svg ", f'<svg x="{x:.2f}" y="{y:.2f}" ', 1).replace(
        f'width="{cover.TRIM_W:.2f}" height="{cover.TRIM_H:.2f}"', f'width="{w:.2f}" height="{h:.2f}"', 1)
    return A.rect(x - 0.5, y - 0.5, w + 1, h + 1, "none", HAIR, 1.0) + inner


def cta(x, y, items):
    out = []
    for k, item in enumerate(items):
        head, _, sub = item.partition(": ")
        yy = y + k * 46
        out.append(A.rect(x, yy, 300, 38, WASH if k == 0 else PAGE, ROSE if k == 0 else HAIR, 0.9, 4))
        out.append(A.text(x + 14, yy + 16, head, 10.5, "Geist", 500, INK))
        out.append(A.text(x + 14, yy + 29, sub, 8.4, "Geist", 300, QUIET))
    return "".join(out)


def art_box():
    from guides import ART
    return ART


def big(x, y, value, label, size=54, accent=True, anchor="start"):
    return (A.text(x, y, value, size, "Manrope", 200, ROSE if accent else INK, anchor, -size * 0.03) +
            A.mono(x, y + 18, label, 7, ROSE_DARK if accent else QUIET, anchor))


def hbar(x, y, w, h, parts, labels=True, size=7.6):
    """A stacked horizontal bar: parts = [(label, value, color)], each labelled below its segment."""
    total = sum(v for _, v, _ in parts)
    out, cx = [], x
    for k, (lab, v, col) in enumerate(parts):
        sw = w * v / total
        out.append(A.rect(cx, y, max(sw - 1.5, 0.5), h, col, "none", 0))
        if labels and sw > 18:
            out.append(A.text(cx + 2, y + h + 13, f"{v:g}" if isinstance(v, (int, float)) else str(v), size + 1.4,
                              "Geist", 500, ROSE_DARK if col == ROSE else INK))
            b, _ = wrapped(cx + 2, y + h + 25, lab, max(sw - 6, 40), size, "Geist", 300, QUIET, 1.3)
            out.append(b)
        cx += sw
    return "".join(out)


def waffle(x, y, n, cols, cell, hot, hot_color=ROSE, base=HAIR, gap=1.2):
    """n squares, the first `hot` (or a set of indexes) in the accent."""
    hot = set(range(hot)) if isinstance(hot, int) else set(hot)
    return "".join(A.rect(x + (k % cols) * (cell + gap), y + (k // cols) * (cell + gap), cell, cell,
                          hot_color if k in hot else base, "none", 0) for k in range(n))


@scene("g2", 1, full=True)
def g2_cover(p, guide):
    from guides import H, M, W, block
    tu, tv = A.fleet_size(3, 3)
    g = canvas(((-7.6, tu), (-1.0, tv), (0, 7.4)), (420, 70, W - 24, H - 34), 0.8)
    slots = A.fleet(g, 3, 3, filled=15)
    for k in (4, 9, 13):
        u, v, _ = slots[k]
        x, y = g.p(u + 2.4, v + 0.4, A.PLATE_Z + 2.4)
        g.raw(A.circle(x, y, 3.2, ROSE, "none") + A.circle(x, y, 6.5, "none", ROSE, 0.6))
    control_room(g, -7.2, 1.0, 3.4, 4.0, 3.4, screens=1, content=lambda w, h: A.code_lines(w, h, 5, 2))
    out = [svg(g), A.mono(M, 112, f"A companion field guide to {guide['book']}", 7, ROSE_DARK)]
    t, y = block(M, 168, p["headline"], 350, 38, "Manrope", 200, INK, 1.06, -0.76)
    s, y = block(M, y + 14, p.get("subhead", ""), 320, 15, "Geist", 300, ICON, 1.4)
    b, y = block(M, y + 22, p["body"], 300, 12, "Geist", 400, ROSE_DARK, 1.5)
    out += [t, s, b, A.rect(M, H - 92, 22, 0.8, HAIR, "none", 0),
            A.text(M, H - 72, guide["author"], 13, "Geist", 400, INK)]
    return "".join(out)


@scene("g2", 2)
def g2_sabbatical(p, guide):
    tu, tv = A.fleet_size(4, 2)
    g = canvas(((-8.0, tu), (-1.0, tv), (0, 5.0)))
    g.box(-A.PAD, -A.PAD, tu, tv, A.PLATE_Z, top=PAGE, right=PAGE, front=PAGE, stroke=HAIR, dash="1.2 1.8")
    g.oz = A.PLATE_Z
    for c in range(4):
        cu, cv = (c % 2) * (A.CELL_U + A.GAP), (c // 2) * (A.CELL_V + A.GAP)
        g.poly(g.pts((cu, cv, 0), (cu + A.CELL_U, cv, 0), (cu + A.CELL_U, cv + A.CELL_V, 0), (cu, cv + A.CELL_V, 0)),
               PAGE, HAIR, sw=g.sw * 0.8, dash="1.2 1.8")
    A.floor_rect(g, -0.1, -0.1, A.PITCH_U + 0.1, A.PITCH_V + 0.1, WASH, ROSE)
    A.station(g, 0.1, 0.05, 5, accent_done=False)
    g.oz = 0
    g.box(-7.6, 2.0, 5.0, 2.8, 1.4, top=PAGE, right=SUNK, front=SUNK)
    g.oz = 1.4
    A.screen(g, -6.6, 3.4, 2.4, 1.5, stand=0.0, content=lambda w, h: A.code_lines(w, h, 5, 1))
    g.oz = 0
    d = p["data"]
    items = [(1.6, 1.6, 3.4 + A.PLATE_Z, " · ".join(d["start"]).capitalize(), True),
             (tu - 4.0, tv - 4.0, A.PLATE_Z, "What it might grow into: cells of agents", False)]
    from guides import ART
    return svg(g) + key(g, items, ART[3] - 44)


@scene("g2", 3)
def g2_timeline(p, guide):
    import datetime
    x0, y0, x1, y1 = art_box()
    rows = [r for r in p["data"]["rows"] if r.get("first_repository") or r["capability"].startswith("Register")][:7]
    lx = x0
    ax0, ax1 = x0 + 150, x1 - 70
    start, end = datetime.date(2026, 3, 1), datetime.date(2026, 10, 1)

    def X(s):
        d = datetime.datetime.strptime(f"{s} 2026", "%d %b %Y").date()
        return ax0 + (ax1 - ax0) * (d - start).days / (end - start).days
    out = []
    for m in ("Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"):
        x = X(f"1 {m}")
        out.append(A.line(x, y0 + 30, x, y1 - 40, HAIR, 0.6))
        out.append(A.mono(x + 3, y0 + 26, m, 6.6))
    out.append(A.mono(x1, y0 + 26, "By end Sep", 6.6, anchor="end"))
    rh = (y1 - y0 - 120) / (len(rows) + 1)
    for k, r in enumerate(rows):
        y = y0 + 60 + k * rh
        cap = r["capability"].split(":")[0]
        never = r.get("half_fleet") == "not reached"
        out.append(A.text(lx, y + 3, cap, 9, "Geist", 500 if never else 400, ROSE_DARK if never else INK))
        intro, first = r.get("introduced_in_plugin"), r.get("first_repository")
        half = r.get("half_fleet") if r.get("half_fleet") not in (None, "not reached") else None
        xs = [X(t) for t in (intro, first, half) if t]
        if len(xs) > 1:
            out.append(A.line(min(xs), y, max(xs), y, HAIR, 1.6))
        if never and xs:
            out.append(A.line(max(xs), y, ax1, y, ROSE, 1.0, "2 2"))
        if half:
            out.append(A.circle(X(half), y, 4, PAGE, INK, 1.2))
            out.append(A.text(X(half), y + 14, half, 6.8, "Geist", 400, QUIET, "middle"))
        if intro:
            out.append(A.circle(X(intro), y, 3.8, ROSE, "none"))
            out.append(A.text(X(intro), y - 8, intro, 6.8, "Geist", 500, ROSE_DARK, "middle"))
        if first:
            out.append(A.circle(X(first), y, 2.6, INK, "none"))
            if first != intro:
                out.append(A.text(X(first), y + 14, first, 6.8, "Geist", 400, QUIET, "middle"))
        out.append(A.text(x1, y + 3, r.get("by_end_sept", "").split(";")[0], 9, "Geist", 500,
                          ROSE_DARK if never else INK, "end"))
    y = y0 + 60 + len(rows) * rh
    out.append(A.text(lx, y + 3, "Trigger: start work without me", 9, "Geist", 500, ROSE_DARK))
    out.append(A.line(ax0, y, ax1, y, ROSE, 1.0, "2 2"))
    out.append(A.text(x1, y + 3, "not built", 9, "Geist", 500, ROSE_DARK, "end"))
    ly = y1 - 18
    for j, (lab, fill, stroke, r) in enumerate((("Introduced in the plugin", ROSE, "none", 3.8),
                                                ("First repository", INK, "none", 2.6),
                                                (f"Half the fleet ({p['data']['chart']['half_fleet']} of "
                                                 f"{p['data']['chart']['fleet_size']})", PAGE, INK, 4))):
        lxx = ax0 + j * 130
        out.append(A.circle(lxx, ly - 3, r, fill, stroke, 1.2))
        out.append(A.text(lxx + 8, ly, lab, 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 4)
def g2_fleet(p, guide):
    x0, y0, x1, y1 = art_box()
    repos = p["data"]["repositories"]
    by = {}
    for r in repos:
        by.setdefault(r["kind"].split(" (")[0], []).append(r)
    out = []
    col = {"plugin": (x0, y0 + 40), "template": (x0 + 190, y0 + 40), "shared service": (x0 + 380, y0 + 40)}
    pills = {}

    def pill(x, y, r, w=170, accent=False):
        dead = "stopped" in r.get("note", "") or "winding" in r.get("note", "")
        out.append(A.rect(x, y, w, 22, WASH if accent else PAGE, ROSE if accent else (HAIR if dead else ICON),
                          0.9, 11, "2 2" if dead else None))
        out.append(A.text(x + 10, y + 14.5, r["name"], 8.4, "Geist Mono", 400, QUIET if dead else INK))
        pills[r["name"]] = (x, y, w)
    for kind, (x, y) in col.items():
        out.append(A.mono(x, y - 8, kind + ("s" if len(by.get(kind, [])) > 1 else ""), 6.6, ROSE_DARK))
        for k, r in enumerate(by.get(kind, [])):
            pill(x, y + k * 28, r, accent=True)
    ay = y0 + 158
    out.append(A.mono(x0, ay - 8, f"Applications · {len(by['application'])}", 6.6))
    for k, r in enumerate(by["application"]):
        pill(x0 + (k % 3) * 190, ay + (k // 3) * 28, r)
    for name, lab in (("skills-plugin", "process"), ("app-template", "template"), ("design-system", "runtime")):
        x, y, w = pills[name]
        out.append(A.line(x + w / 2, y + 22, x + w / 2, ay - 16, ROSE, 0.9, "1.5 2"))
        out.append(A.mono(x + w / 2 + 5, (y + 22 + ay - 16) / 2 + 3, lab, 6.2, ROSE_DARK))
    iy = ay + 3 * 28 + 34
    out.append(A.mono(x0, iy - 8, f"Infrastructure · {len(by['infrastructure'])}", 6.6))
    for k, r in enumerate(by["infrastructure"]):
        pill(x0 + k * 190, iy, r)
    x, y, w = pills["infrastructure-environments"]
    out.append(A.arrow2([(x + w, y + 11), (x + w + 18, y + 11)], ICON, 0.9, k=4))
    env = next(r for r in repos if r["name"] == "infrastructure-environments")
    b, _ = wrapped(x + w + 24, y + 8, "delivery: " + env["what"].removeprefix("the environment definitions; "),
                   x1 - (x + w + 24), 7.6, "Geist", 300, QUIET, 1.35)
    out.append(b)
    out.append(A.text(x0, y1 - 26, "Dashed pills: stopped or winding down. Every repository also runs the plugin's "
                      "process; design comes from Claude Design.", 7.6, "Geist", 300, QUIET))
    out.append(big(x1 - 4, y1 - 70, str(len(repos)), "repositories", 56, True, "end"))
    return "".join(out)


@scene("g2", 5)
def g2_output(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    out = []
    tu, tv = A.fleet_size(3, 3)
    for k, (key_, title) in enumerate((("before_july", "Before July"), ("july_to_late_sept", "July to late September"))):
        bx = x0 + k * 290
        act = d[key_]["active_repos_per_week"]
        out.append(A.mono(bx, y0 + 30, f"{title} · {d[key_]['weeks']}", 7, ROSE_DARK if k else QUIET))
        g = canvas(((-0.6, tu), (-0.6, tv), (0, 3.4)), (bx, y0 + 40, bx + 250, y0 + 240), 0.6)
        A.fleet(g, 3, 3, filled=round(act))
        out.append(svg(g))
        out.append(big(bx, y0 + 300, f"{act:g}", "active repositories a week (arms at work)", 46, bool(k)))
        out.append(big(bx, y0 + 380, f"{d[key_]['change_sets_per_active_repo_per_week']:g}",
                       "change sets per active repository a week", 30, False))
    out.append(A.text(x0, y1 - 22, f"Weekly output grew {d['output_growth'].split()[0]}; {d['unit']}. Each arm is "
                      "one repository; empty stations were idle that week.", 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 6)
def g2_adoption(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]["adoption_by_end_sept_of_15"]
    size = p["data"]["chart"]["fleet_size"]
    out = []
    rh = 56
    for k, (cap, n) in enumerate(d.items()):
        y = y0 + 40 + k * rh
        out.append(A.text(x0, y + 12, cap.split(" (")[0], 10, "Geist", 400, INK))
        for i in range(size):
            out.append(A.rect(x0 + 190 + i * 22, y, 18, 18, (ICON if n >= size else ROSE) if i < n else PAGE,
                              "none" if i < n else HAIR, 0.8, 2))
        out.append(A.text(x1, y + 14, f"{n} of {size}", 14, "Manrope", 300, ROSE if n < size else INK, "end"))
    t = p["data"]["component_traffic"]
    y = y0 + 40 + len(d) * rh + 20
    out.append(A.mono(x0, y, "In everyday use: share of " + t["population"].split(" merged")[0], 6.8, ROSE_DARK))
    parts = [("Passed automated approval", t["auto_approve_judge"]), ("Came from a shared-skill session",
              t["shared_skill_session"]), ("Had a work item", t["work_item"]), ("Had a goal", t["goal"])]
    for k, (lab, v) in enumerate(parts):
        bx = x0 + k * 140
        out.append(A.text(bx, y + 40, v, 28, "Manrope", 200, ROSE if k < 2 else INK))
        b, _ = wrapped(bx, y + 56, lab, 120, 8, "Geist", 300, QUIET, 1.3)
        out.append(b)
    return "".join(out)


@scene("g2", 7)
def g2_no_plan(p, guide):
    x0, y0, x1, y1 = art_box()
    c = p["data"]["composition"]
    noplan = {"One-shot, session logged", "One-shot, no record"}
    order = [k for k in c if k not in noplan] + [k for k in c if k in noplan]
    parts = [(k, c[k], ROSE if k in noplan else (ICON if k.startswith("Goal") else LINE)) for k in order]
    ns = p["data"]["no_saved_plan"]
    out = [big(x0, y0 + 90, ns.split("(")[1].rstrip(")"), ns.split(" (")[0] + " had no saved plan", 72)]
    out.append(hbar(x0, y0 + 160, x1 - x0, 46, parts))
    total = sum(c.values())
    nx = x0 + (x1 - x0) * (total - sum(c[k] for k in noplan)) / total
    out.append(A.poly2([(nx, y0 + 150), (nx, y0 + 142), (x1, y0 + 142), (x1, y0 + 150)], ROSE, 1))
    out.append(A.mono(nx, y0 + 134, "No saved plan", 7, ROSE_DARK))
    out.append(A.text(x0, y1 - 40, p["data"]["population"], 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 8)
def g2_yes(p, guide):
    x0, y0, x1, y1 = art_box()
    out = []
    cw, chh = 98, 170
    for k in range(5):
        x, y = x0 + k * (cw + 14), y0 + 110
        acc = k < 4
        out.append(A.rect(x, y, cw, chh, PAGE, ICON if acc else ROSE, 1.0, 6))
        out.append(A.mono(x + 10, y + 18, "Agent asks", 6.2))
        for j in range(3):
            out.append(A.rect(x + 10, y + 32 + j * 12, cw - 30 - 10 * (j % 2), 5, HAIR, "none", 0))
        for j, lab in enumerate(("Recommended", "Other option")):
            oy = y + 82 + j * 30
            sel = acc and j == 0
            out.append(A.rect(x + 10, oy, cw - 20, 22, WASH if sel else PAGE, ROSE if sel else HAIR, 0.9, 4))
            out.append(A.text(x + 18, oy + 14.5, lab, 7.6, "Geist", 500 if j == 0 else 300, INK if sel else QUIET))
        out.append(A.text(x + cw / 2, y + chh - 14, "Accepted" if acc else "Chose otherwise", 8, "Geist", 500,
                          ROSE_DARK if acc else INK, "middle"))
    c = p["data"]["chart"]
    out.append(big(x0, y0 + 60, f"{c['accepted_pct']}%", f"of {c['asks']} asks with a recommended option", 60))
    out.append(A.text(x0, y1 - 30, "Uptake measures reliance, not whether the advice was right.", 9, "Geist", 300,
                      QUIET))
    return "".join(out)


@scene("g2", 9)
def g2_reviews(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    n = d["reviewed"] + d["no_review"]
    cols, cell, gap = 56, 6.6, 1.4
    import random
    rnd = random.Random(9)
    idx = rnd.sample(range(n), d["reviewed_by_a_person"] + d["no_review"])
    people, none = set(idx[:d["reviewed_by_a_person"]]), set(idx[d["reviewed_by_a_person"]:])
    out = []
    for k in range(n):
        x, y = x0 + (k % cols) * (cell + gap), y0 + 90 + (k // cols) * (cell + gap)
        if k in none:
            out.append(A.rect(x + 0.4, y + 0.4, cell - 0.8, cell - 0.8, PAGE, ICON, 0.7))
        else:
            out.append(A.rect(x, y, cell, cell, ROSE if k in people else HAIR, "none", 0))
    out.append(big(x0, y0 + 60, str(d["reviewed_by_a_person"]), "pull requests reviewed by a person", 60))
    out.append(big(x0 + 260, y0 + 60, f"{n:,}", "merged in 2026, Dependabot excluded", 34, False))
    ly = y1 - 44
    for k, (lab, fill, stroke) in enumerate(((f"Reviewed by a person ({d['reviewed_by_a_person']})", ROSE, "none"),
                                            (f"Reviewed by bots or agents ({d['reviewed'] - d['reviewed_by_a_person']:,})",
                                             HAIR, "none"), (f"No review ({d['no_review']})", PAGE, ICON))):
        lx = x0 + k * 190
        out.append(A.rect(lx, ly - 7, 8, 8, fill, stroke, 0.7))
        out.append(A.text(lx + 13, ly, lab, 8, "Geist", 300, QUIET))
    out.append(A.text(x0, y1 - 22, f"{d['agent_on_owner_account']} of the reviews under my account were written by "
                      "an agent.", 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 10)
def g2_done_not_done(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    out = []
    c = d["chart"]
    rows = [("The approval check sent back", c["sent_back"], c["ruled"], "pull requests it ruled on"),
            ("Agents logged calling work done when it wasn't", c["overclaims"], c["mistakes"], "recorded mistakes")]
    for k, (lab, a, b, unit) in enumerate(rows):
        y = y0 + 70 + k * 120
        out.append(A.text(x0, y, lab, 11, "Geist", 400, INK))
        out.append(A.rect(x0, y + 14, x1 - x0, 22, A.SUNK, "none", 0, 2))
        out.append(A.rect(x0, y + 14, (x1 - x0) * a / b, 22, ROSE, "none", 0, 2))
        out.append(A.text(x0, y + 62, f"{a:g}", 26, "Manrope", 200, ROSE))
        out.append(A.text(x0 + 56, y + 58, f"of {b:,.0f} {unit}", 9, "Geist", 300, QUIET))
    y = y0 + 330
    out.append(A.circle(x0 + 40, y, 34, PAGE, ICON, 1.0))
    out.append(A.circle(x0 + 86, y, 34, PAGE, ROSE, 1.0))
    both, of = c["overlap"], c["overlap_of"]
    out.append(A.text(x0 + 63, y + 6, f"{both:g}", 18, "Manrope", 300, ROSE_DARK, "middle"))
    out.append(A.text(x0 + 140, y - 4, f"Overlap: of {of:g} overclaims traceable to a merged PR,", 10, "Geist", 400,
                      INK))
    out.append(A.text(x0 + 140, y + 12, f"the check had sent back {both:g}.", 10, "Geist", 400, INK))
    out.append(A.text(x0 + 140, y + 32, "Different denominators: the two bars aren't comparable.", 8, "Geist", 300,
                      QUIET))
    return "".join(out)


@scene("g2", 11)
def g2_session_clock(p, guide):
    x0, y0, x1, y1 = art_box()
    sh = p["data"]["shares"]
    parts = [("Agent working, or its tools and subagents", sh["Agent working, combined"], ROSE),
             ("Waiting for my answer", sh["Waiting on me, combined"], ICON),
             ("Stopped by a usage limit", sh["Stopped by a usage limit"], LINE),
             ("Me reading or away", sh["Reading or away (ended by a typed prompt)"], HAIR)]
    out = [big(x0, y0 + 110, f"{sh['Agent working, combined']:g}%", "of open-session time with an agent at work", 96)]
    out.append(hbar(x0, y0 + 180, x1 - x0, 56, parts))
    out.append(A.text(x0, y1 - 30, p["data"]["population"] + ". Hours add across overlapping sessions.", 8,
                      "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 12)
def g2_nine_hours(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]["pauses_between_sessions"]
    out = [A.clock(x0 + 120, y0 + 170, 105, d["median_hours"])]
    out.append(big(x0 + 120, y0 + 325, f"{d['median_hours']:g} h", "median pause between sessions", 40, True,
                   "middle"))
    g = canvas(((-1, 9), (-1, 7), (0, 4.4)), (x0 + 270, y0 + 50, x1, y0 + 290))
    A.floor_rect(g, -1, -1, 10, 8, SUNK, HAIR)
    A.machine(g, 0.4, 0.2, 7, 0.0, lift=0.5)
    A.sheet(g, 4.4, 3.6, 1.6, 1.4, 0, 4, accent=True)
    g.box(4.6, -0.6, 3.6, 1.6, 1.0)
    out.append(svg(g))
    out.append(tag(g, 5.2, 4.3, 0, 10, 30, "Ready plan in the queue", True))
    share = p["data"]["chart"]["no_session_pct"]
    bx, by = x0 + 290, y0 + 320
    out.append(A.mono(bx, by, "PR open time with no session running", 6.6, ROSE_DARK))
    out.append(A.rect(bx, by + 8, 260, 16, A.SUNK, "none", 0, 2))
    out.append(A.rect(bx, by + 8, 260 * share / 100, 16, ROSE, "none", 0, 2))
    out.append(A.text(bx + 6, by + 19.5, f"{share}%", 9, "Geist", 500, PAGE))
    out.append(A.text(bx, y1 - 50, f"{d['after_usage_limit']} of {d['count']} pauses followed a usage limit.", 11,
                      "Geist", 400, INK))
    out.append(A.text(bx, y1 - 32, "The others ended when I started the next session.", 11, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 13)
def g2_banner(p, guide):
    x0, y0, x1, y1 = art_box()
    c = p["data"]["chart"]
    w = (x1 - x0 - 40) / 3
    out = []
    heads = ["1 · Two notices overlap", "2 · The design system decides", "3 · The answer doesn't come back"]
    for k, h in enumerate(heads):
        x = x0 + k * (w + 20)
        out.append(A.mono(x, y0 + 40, h, 6.8, ROSE_DARK if k == 2 else QUIET))
        out.append(A.rect(x, y0 + 54, w, 250, PAGE, ICON, 1.0, 6))
    x = x0
    out.append(A.rect(x + 12, y0 + 70, w - 24, 210, A.SUNK, "none", 0, 3))
    out.append(A.rect(x + 12, y0 + 70, w - 24, 26, WASH, ROSE, 0.9, 2))
    out.append(A.text(x + 20, y0 + 87, c["notices"][0], 7.6, "Geist", 400, ROSE_DARK))
    out.append(A.rect(x + 26, y0 + 90, w - 34, 26, PAGE, ICON, 0.9, 2))
    out.append(A.text(x + 34, y0 + 107, c["notices"][1], 7.6, "Geist", 400, INK))
    for j in range(4):
        out.append(A.rect(x + 24, y0 + 140 + j * 16, (w - 60) * (0.9 - 0.15 * (j % 3)), 6, HAIR, "none", 0))
    x = x0 + w + 20
    out.append(A.mono(x + 14, y0 + 76, "New order", 6.4))
    for j, lab in enumerate(c["new_order"]):
        acc = j == 0
        out.append(A.rect(x + 14, y0 + 84 + j * 38, w - 28, 30, WASH if acc else PAGE, ROSE if acc else HAIR, 0.9, 4))
        out.append(A.text(x + 24, y0 + 103 + j * 38, f"{j + 1}  {lab}", 9, "Geist", 400, INK))
    out.append(A.text(x + 14, y0 + 180, c["decided"][0], 9, "Geist", 500, INK))
    out.append(A.text(x + 14, y0 + 194, c["decided"][1], 9, "Geist", 300, QUIET))
    x = x0 + 2 * (w + 20)
    bw = 44
    lx, rx = x + 12, x + w - 12 - bw
    for bx, lab in ((lx, "website"), (rx, "design system")):
        out.append(A.rect(bx, y0 + 100, bw, 80, PAGE, ICON, 0.9, 4))
        out.append(A.text(bx + bw / 2, y0 + 196, lab, 7, "Geist Mono", 400, QUIET, "middle"))
    mx = (lx + rx + bw) / 2
    out.append(A.arrow2([(lx + bw + 4, y0 + 122), (rx - 4, y0 + 122)], ICON, 1.1, k=5))
    out.append(A.text(mx, y0 + 115, "request", 7.4, "Geist", 400, QUIET, "middle"))
    out.append(A.line(rx - 4, y0 + 160, mx + 7, y0 + 160, ROSE, 1.2, "2 2.5"))
    out.append(A.line(mx - 7, y0 + 160, lx + bw + 4, y0 + 160, ROSE, 1.2, "2 2.5"))
    out.append(A.text(mx, y0 + 153, "fix ready", 7.4, "Geist", 500, ROSE_DARK, "middle"))
    out.append(A.text(mx, y0 + 174, "no reply", 7.4, "Geist", 400, ROSE_DARK, "middle"))
    for j, ln in enumerate(c["outcome"]):
        out.append(A.text(x + 14, y0 + 226 + j * 14, ln, 9, "Geist", 400, INK))
    out.append(A.text(x0, y1 - 40, c["lesson"], 9, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 14)
def g2_fan_out(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    n, named = d["prs_requiring_consumer_action"], d["named_affected_repos"]
    out = []
    sx, sy = x0 + 40, y0 + 210
    out.append(A.rect(sx - 30, sy - 30, 60, 60, WASH, ROSE, 1.0, 6))
    out.append(A.mono(sx, sy + 46, "Upstream", 6.6, ROSE_DARK, "middle"))
    cols, top = 6, y0 + 50
    rows = (n + cols - 1) // cols
    for k in range(n):
        r, c = k // cols, k % cols
        tx, ty = x0 + 320 + c * 12, top + r * (300 / rows)
        hot = k % (n // named) == 0 and k // (n // named) < named
        out.append(A.line(sx + 30, sy, tx, ty, ROSE if hot else HAIR, 0.9 if hot else 0.4))
        out.append(A.circle(tx, ty, 2.2, ROSE if hot else PAGE, ROSE if hot else LINE, 0.6))
    out.append(big(x0 + 420, y0 + 110, f"{named}", f"of {n} named who had to act", 60))
    v = d["vendored_copies"]
    vy = y0 + 300
    out.append(A.mono(x0 + 420, vy, f"{v['total']} vendored copies", 6.8))
    out.append(waffle(x0 + 420, vy + 10, v["total"], 14, 9, v["older_than_source"], ROSE, HAIR, 2))
    out.append(A.text(x0 + 420, vy + 60, f"{v['older_than_source']} older than their source, "
                      f"{v['locally_edited']} edited locally", 8.4, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 15)
def g2_tenancy(p, guide):
    x0, y0, x1, y1 = art_box()
    tl = p["data"]["timeline"]
    out = [A.line(x0, y0 + 80, x1, y0 + 80, ICON, 1.0)]
    xs = [x0 + 10, x0 + 70, x0 + 190, x0 + 260, x0 + 360, x0 + 470]
    for k, ev in enumerate(tl[:6]):
        x = xs[k]
        hot = k >= 2
        out.append(A.circle(x, y0 + 80, 4, ROSE if hot else PAGE, ROSE if hot else ICON, 1.0))
        out.append(A.text(x, y0 + 66, ev["date"], 9, "Geist", 500, ROSE_DARK if hot else INK))
        b, _ = wrapped(x, y0 + 100 + (k % 2) * 70, ev["event"], 100, 7.6, "Geist", 300, QUIET, 1.35)
        out.append(b)
    out.append(A.line(x0 + 120, y0 + 80, x0 + 190, y0 + 80, PAGE, 3))
    out.append(A.line(x0 + 120, y0 + 80, x0 + 190, y0 + 80, ICON, 1.0, "2 3"))
    c = p["data"]["chart"]
    adopters = c["adopters"]
    ty = y0 + 270
    out.append(A.mono(x0, ty - 12, f"From the template, {c['template_date']}", 6.6, ROSE_DARK))
    out.append(A.rect(x0, ty, 150, 24, WASH, ROSE, 0.9, 12))
    out.append(A.text(x0 + 12, ty + 15.5, "app-template", 8.4, "Geist Mono", 400, INK))
    px = x0 + 200
    for k, a in enumerate([x["repo"] for x in adopters] + [c["not_adopted"]]):
        y = ty - 36 + k * 30
        miss = k == len(adopters)
        out.append(A.line(x0 + 150, ty + 12, px, y + 12, HAIR if miss else ROSE, 0.9, "2 2" if miss else None))
        out.append(A.rect(px, y, 190, 24, PAGE, ROSE if miss else ICON, 0.9, 12, "2 2" if miss else None))
        out.append(A.text(px + 12, y + 15.5, a, 8.4, "Geist Mono", 400, ROSE_DARK if miss else INK))
        out.append(A.text(px + 200, y + 15.5, "not adopted, no exception" if miss else f"adopted {adopters[k]['date']}",
                          8, "Geist", 500 if miss else 300, ROSE_DARK if miss else QUIET))
    return "".join(out)


@scene("g2", 16)
def g2_compliance(p, guide):
    x0, y0, x1, y1 = art_box()
    part = p["data"]["partition"]
    still = ["Fixed, then reopened; open at last audit", "Never fixed; open at last audit"]
    parts = [(k, v, ICON if k.startswith("Fixed in the") else LINE) for k, v in part.items() if v and k not in still]
    parts += [(k, part[k], ROSE) for k in still]
    c = p["data"]["chart"]
    left = c["still_failing"]
    total = sum(part.values())
    out = [big(x0, y0 + 90, str(left), f"of {total} violations still failing at the last audit", 72)]
    out.append(hbar(x0, y0 + 160, x1 - x0, 40, parts, size=7))
    sx = x0 + (x1 - x0) * (total - left) / total
    out.append(A.poly2([(sx, y0 + 152), (sx, y0 + 144), (x1, y0 + 144), (x1, y0 + 152)], ROSE, 1))
    out.append(A.mono(x1, y0 + 137, f"{left} still failing: {c['reopened_open']} reopened + {c['never_fixed']} never "
                      "fixed", 6.6, ROSE_DARK, "end"))
    ty = y0 + 330
    out.append(A.mono(x0, ty - 14, f"Audit days, {c['audit_period']}", 6.8))
    out.append(A.line(x0, ty, x0 + 330, ty, HAIR, 1))
    days = c["audit_days"]
    for k in range(days):
        x = x0 + 8 + k * (320 / days) + (k % 3) * 2
        out.append(A.rect(x, ty - 7, 4, 14, ICON, "none", 0))
    bx = x1 - 120
    out.append(A.rect(bx, ty - 30, 110, 54, PAGE, ICON, 1.0, 6))
    out.append(A.rect(bx + 14, ty - 12, 36, 18, PAGE, ICON, 1.0, 9))
    out.append(A.circle(bx + 23, ty - 3, 6, ROSE, "none"))
    out.append(A.text(bx + 58, ty, "Manual audit", 8, "Geist", 400, INK))
    out.append(A.text(bx, ty + 40, c["ci_note"], 8, "Geist", 300, ROSE_DARK))
    return "".join(out)


@scene("g2", 17)
def g2_deploys(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    c = d["chart"]
    run = c["identity_run"]
    out = [big(x0, y0 + 90, f"{d['median_merge_to_production_minutes']} min", "median from merge to production", 64,
               False)]
    out.append(A.mono(x0, y0 + 150, f"{d['deployments']} deployments · {d['failed']} failed", 6.8, ROSE_DARK))
    block = set(range(150, 150 + run))
    spread = [i for i in range(7, d["deployments"], 29) if i not in block][:d["failed"] - run]
    hot = block | set(spread)
    if len(hot) != d["failed"]:
        raise ValueError(f"g2 page 17: drew {len(hot)} failed deployments for {d['failed']}")
    out.append(waffle(x0, y0 + 162, d["deployments"], 41, 10, hot, ROSE, HAIR, 2.4))
    out.append(A.text(x0, y0 + 300, f"{d['failed']} failed; {c['identity_failed']} ({run} in one three-day run) in "
                      f"the identity service. {d['rollbacks']} rollbacks.", 9, "Geist", 400, INK))
    my = y0 + 340
    out.append(A.mono(x0, my - 10, "Outages found by health checks", 6.6))
    for k, (m, n) in enumerate(c["outages"].items()):
        mx = x0 + k * 110
        out.append(A.rect(mx, my, 104, 16, A.SUNK, "none", 0, 2))
        out.append(A.mono(mx + 4, my + 30, m, 6.4))
        for j in range(n):
            out.append(A.rect(mx + 14 + j * 22, my + 2, 6, 12, ROSE, "none", 0))
    out.append(A.text(x0 + 350, my + 12, c["health_line"], 9, "Geist", 400, INK))
    out.append(A.text(x0, y1 - 26, "Deploy on merge: " + ", ".join(d["deploy_on_merge_apps"]) + ".", 8, "Geist",
                      300, QUIET))
    return "".join(out)


@scene("g2", 18)
def g2_shared_failure(p, guide):
    import math
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    out = []
    cx, cy, R = x0 + 170, y0 + 210, 150
    for k in range(d["max_repos_at_once"]):
        a = math.radians(-160 + k * 320 / (d["max_repos_at_once"] - 1))
        tx, ty = cx + R * math.cos(a), cy + R * math.sin(a)
        out.append(A.line(cx, cy, tx, ty, ROSE, 1.1))
        out.append(A.rect(tx - 9, ty - 9, 18, 18, WASH, ROSE, 1.0, 3))
    out.append(A.circle(cx, cy, 30, ROSE, "none"))
    out.append(A.text(cx, cy + 4, "approve", 8.6, "Geist", 500, PAGE, "middle"))
    c = d["chart"]
    steps = [("Rename", "0"), (f"All {d['max_repos_at_once']} failing", f"{c['all_failing_s']} s"),
             (f"{c['callers_repointed']} callers repointed", c["repointed_after"]), ("Green again", c["green_after"])]
    tx = x0 + 380
    out.append(A.mono(tx, y0 + 60, f"The plugin rename, {c['rename_date']}", 6.8, ROSE_DARK))
    for k, (lab, t) in enumerate(steps):
        y = y0 + 90 + k * 46
        out.append(A.circle(tx + 6, y, 4, ROSE if k < 2 else ICON, "none"))
        if k:
            out.append(A.line(tx + 6, y - 42, tx + 6, y - 4, HAIR, 1))
        out.append(A.text(tx + 20, y + 4, t, 15, "Manrope", 300, INK))
        out.append(A.text(tx + 90, y + 3, lab, 9, "Geist", 300, QUIET))
    out.append(A.text(tx, y0 + 300, f"{d['fleet_wide_breaks']} fleet-wide breaks; {d['breaks_after_workflow_change']}"
                      " followed a change", 9, "Geist", 400, INK))
    out.append(A.text(tx, y0 + 314, "to the workflow itself.", 9, "Geist", 400, INK))
    out.append(A.rect(tx, y0 + 340, 150, 40, PAGE, LINE, 0.9, 4, "2 2"))
    out.append(A.text(tx + 10, y0 + 364, "Canary first (proposed)", 9, "Geist", 400, QUIET))
    return "".join(out)


@scene("g2", 19)
def g2_cost(p, guide):
    x0, y0, x1, y1 = art_box()
    d = p["data"]
    med = d["cost_medians_list_price_25aug_1oct"]
    out = [big(x0, y0 + 80, med["per_change_set"], "median per change set, at API list prices", 56, False)]
    for k, (lab, key) in enumerate((("per PR", "per_pull_request"), ("per work item", "per_work_item"),
                                    ("per goal", "per_goal"))):
        out.append(A.text(x0 + k * 90, y0 + 130, med[key], 15, "Manrope", 300, INK))
        out.append(A.mono(x0 + k * 90, y0 + 144, lab, 6.4))
    y = y0 + 190
    out.append(A.mono(x0, y, "Not the same measurement", 6.8, ROSE_DARK))
    out.append(A.rect(x0, y + 10, 4, 18, ICON, "none", 0))
    c = d["chart"]
    out.append(A.text(x0 + 12, y + 23, f"{c['subscription_week']}, subscription", 9, "Geist", 400, INK))
    out.append(A.rect(x0, y + 36, 240, 18, LINE, "none", 0))
    out.append(A.text(x0 + 248, y + 49, f"{c['list_week']} at list price, a full week", 9, "Geist", 400, INK))
    y = y0 + 290
    out.append(A.mono(x0, y, "CI wall-clock minutes", 6.8))
    out.append(A.rect(x0, y + 10, x1 - x0, 30, HAIR, "none", 0))
    share = c["hung_share_of_minutes_pct"] / 100
    out.append(A.rect(x0, y + 10, (x1 - x0) * share, 30, ROSE, "none", 0))
    out.append(A.text(x0 + 8, y + 30, f"{share:.0%} from {c['hung_runs']} hung runs", 10, "Geist", 500, PAGE))
    out.append(A.text(x0, y + 60, c["runs_note"], 8, "Geist", 300, QUIET))
    return "".join(out)


@scene("g2", 20, full=True)
def g2_next(p, guide):
    from guides import H, M, W, block
    tu, tv = A.fleet_size(1, 1)
    g = canvas(((-7.6, tu), (-1.0, tv + 4.6), (0, 7.4)), (392, 110, 800, H - 100), 0.8)
    A.fleet(g, 1, 1)
    g.box(-A.PAD, tv - A.PAD + 0.4, tu, 4.0, A.PLATE_Z, top=PAGE, right=PAGE, front=PAGE, stroke=ROSE,
          dash="1.4 1.6")
    g.oz = A.PLATE_Z
    for k in range(4):
        g.box(0.2 + k * 2.6, tv + 0.6, 1.8, 1.8, 1.2, top=PAGE, right=PAGE, front=PAGE, stroke=ROSE, dash="1.4 1.6")
    g.oz = 0
    control_room(g, -7.2, 1.0, 3.4, 4.0, 3.4, screens=1, content=lambda w, h: A.code_lines(w, h, 5, 2))
    props = ("Control loop off my laptop", "Shared space for intent", "Live view of the fleet",
             "Policy that starts authorized work")
    items = [(1.1 + k * 2.6, tv + 1.5, A.PLATE_Z + 1.4, lab, True) for k, lab in enumerate(props)]
    out = [svg(g), key(g, items, H - 66, x0=392)]
    t, y = block(M, 110, p["headline"], 290, 32, "Manrope", 200, INK, 1.08, -0.64)
    b, y = block(M, y + 16, p["body"], 290, 11.2, "Geist", 300, INK, 1.5)
    out += [t, b, A.mono(392, 92, "Solid: built.  Dashed: proposed, not tested", 6.8, ROSE_DARK)]
    out.append(cover_thumb(W - 150, 92, 104))
    out.append(cta(M, H - 140, p["data"]["cta"]))
    return "".join(out)
