"""The Software Factory Readiness Worksheet: a two-page printable scorecard on the five flows, the
offer both field guides close on.

    ./publish worksheet   -> $PUBLISH_OUT/dist/software-factory-readiness-worksheet.pdf

The copy is `editions/worksheet.json`, beside the guides' copy; the drawing uses the guides' type and
marks, on US Letter portrait so it prints and fills by hand.
"""
import json
import os

import fitz

import paths
from cover import print_page
from guide_art import HAIR, INK, LINE, PAGE, QUIET, ROSE, ROSE_DARK, SUNK, WASH, circle, line, mono, rect, text
from guides import block, font_css, width

MANIFEST = os.path.join(paths.EDITIONS, "worksheet.json")
W, H = 612.0, 792.0
M = 44.0
REQUIRED = ("file", "title", "subtitle", "how", "scale", "flows", "before", "gap_prompts", "source", "cta")


def head(n, title):
    return (rect(M, 30, 22, 2, ROSE, "none", 0) + mono(M, 22, "Readiness worksheet", 6.6) +
            mono(W - M, 22, f"{n} / 2", 6.6, anchor="end") + mono(M, H - 22, title, 6, LINE))


def flow_table(k, flow, y, scale):
    """One flow: its name and question, three statements with score boxes and an evidence line, and
    a subtotal box."""
    out = [circle(M + 9, y - 4, 9, ROSE, "none"), text(M + 9, y - 0.5, str(k), 9.5, "Geist", 500, PAGE, "middle"),
           text(M + 26, y, flow["name"], 14, "Manrope", 300, INK),
           text(M + 26 + width(flow["name"], 14, "Manrope") + 10, y, flow["question"], 9, "Geist", 300, QUIET)]
    sx = W - M - 3 * 26 - 4
    for j, lab in enumerate(scale):
        out.append(mono(sx + j * 26 + 9, y, lab.split()[0], 6.4, QUIET, "middle"))
    y += 12
    for st in flow["statements"]:
        lines, yy = block(M + 26, y + 11, st, sx - M - 40, 8.6, "Geist", 400, INK, 1.32)
        out.append(lines)
        for j in range(3):
            out.append(rect(sx + j * 26 + 2, y + 3, 14, 14, PAGE, LINE, 0.8, 2))
        ey = max(yy, y + 22) + 4
        out.append(mono(M + 26, ey + 2, "Evidence", 5.6, QUIET))
        out.append(line(M + 70, ey + 3, sx - 12, ey + 3, HAIR, 0.7))
        y = ey + 10
    out.append(rect(W - M - 118, y - 2, 118, 20, WASH, ROSE, 0.8, 3))
    out.append(text(W - M - 112, y + 11.5, f"{flow['name']} total", 7.6, "Geist", 500, ROSE_DARK))
    out.append(text(W - M - 8, y + 11.5, "/ 6", 7.6, "Geist", 400, QUIET, "end"))
    return "".join(out), y + 32


def page_one(c):
    out = [head(1, c["title"])]
    t, y = block(M, 78, c["title"], W - 2 * M, 26, "Manrope", 200, INK, 1.1, -0.5)
    s, y = block(M, y + 4, c["subtitle"], W - 2 * M, 11.5, "Geist", 300, QUIET, 1.4)
    out += [t, s, rect(M, y + 6, W - 2 * M, 0.8, HAIR, "none", 0)]
    h, y = block(M, y + 26, c["how"], W - 2 * M, 9, "Geist", 300, INK, 1.45)
    out.append(h)
    y += 18
    for k, flow in enumerate(c["flows"][:3], 1):
        tb, y = flow_table(k, flow, y, c["scale"])
        out.append(tb)
    return out


def page_two(c):
    out = [head(2, c["title"])]
    y = 70
    for k, flow in enumerate(c["flows"][3:], 4):
        tb, y = flow_table(k, flow, y, c["scale"])
        out.append(tb)
    out.append(mono(M, y, "Your scores", 7, ROSE_DARK))
    y += 12
    bw = (W - 2 * M - 4 * 10) / 5
    for k, flow in enumerate(c["flows"]):
        x = M + k * (bw + 10)
        out.append(rect(x, y, bw, 58, SUNK, "none", 0, 3))
        out.append(text(x + 8, y + 16, flow["name"], 8.6, "Geist", 500, INK))
        for i in range(6):
            out.append(rect(x + 8 + i * ((bw - 16) / 6), y + 28, (bw - 16) / 6 - 3, 18, PAGE, LINE, 0.7, 1.5))
    y += 80
    half = (W - 2 * M - 16) / 2
    out.append(rect(M, y, half, 150, PAGE, ROSE, 0.9, 4))
    out.append(mono(M + 12, y + 18, "Your first gap", 7, ROSE_DARK))
    yy = y + 38
    for prompt in c["gap_prompts"]:
        out.append(text(M + 12, yy, prompt, 8.4, "Geist", 400, INK))
        out.append(line(M + 12, yy + 14, M + half - 12, yy + 14, HAIR, 0.7))
        yy += 28
    bx = M + half + 16
    out.append(rect(bx, y, half, 150, SUNK, "none", 0, 4))
    out.append(mono(bx + 12, y + 18, "Before you speed it up", 7, QUIET))
    yy = y + 36
    for ln in c["before"]:
        b, yy = block(bx + 12, yy, ln, half - 24, 8.4, "Geist", 300, INK, 1.35)
        out.append(b)
        yy += 6
    y += 172
    out.append(text(M, y, c["cta"], 11, "Manrope", 300, INK))
    out.append(text(M, y + 16, c["source"], 7.6, "Geist", 300, QUIET))
    return out


def svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}" width="{W:g}" height="{H:g}">'
            f'{rect(0, 0, W, H, PAGE, "none", 0)}{"".join(body)}</svg>')


def main(argv=None):
    with open(MANIFEST, encoding="utf-8") as f:
        c = json.load(f)
    missing = [k for k in REQUIRED if k not in c]
    if missing or len(c["flows"]) != 5 or any(len(f["statements"]) != 3 for f in c["flows"]):
        raise SystemExit(f"worksheet.json: needs {', '.join(REQUIRED)}, five flows of three statements each"
                         + (f"; missing {', '.join(missing)}" if missing else ""))
    os.makedirs(paths.DIST, exist_ok=True)
    out = os.path.join(paths.DIST, c["file"])
    page = os.path.splitext(out)[0] + ".html"
    with open(page, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}'
                f'@page{{size:{W:g}pt {H:g}pt;margin:0}}html,body{{margin:0}}'
                f'svg{{display:block;width:{W:g}pt;height:{H:g}pt;break-after:page}}</style></head>'
                f'<body>{svg(page_one(c))}{svg(page_two(c))}</body></html>')
    print_page(page, out, 6000)
    os.remove(page)
    with fitz.open(out) as doc:
        # A trailing page break leaves one blank page; any other count means the layout overflowed.
        blank = len(doc) == 3 and not doc[-1].get_text().strip() and not doc[-1].get_drawings()
        if len(doc) != 2 and not blank:
            raise SystemExit(f"worksheet: printed {len(doc)} pages for 2; a section overflowed its page")
        if blank:
            doc.delete_page(2)
            doc.save(out + ".tmp", garbage=3, deflate=True)
    if blank:
        os.replace(out + ".tmp", out)
    print(f"worksheet: {out}")


if __name__ == "__main__":
    main()
