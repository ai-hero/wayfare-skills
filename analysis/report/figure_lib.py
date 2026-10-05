"""Drawn figures for the book's evidence cards, and the summary table each figure leaves behind.

The decks' native charts are bars and lines (that is all the viewer reads back from a .pptx). A figure
whose form is a dot-and-whisker, dumbbell, heatmap, survival curve, scatter or lane timeline is drawn
here with matplotlib in the brand style, saved as a PNG, and placed on the answer slide in the chart box,
where deck_html reads it back as the view's image:

    import figure_lib as F
    png = F.save(fig, F.asset("3.1"))                       # .analysis/diagrams/book/figure-03-01.png
    L.answer_slide(prs, tag, title, points, chart=lambda s, box: F.picture(s, box, png), ...)
    F.summary("3.1", question=..., params={...}, table=[...], notes=..., sources=[...])

`summary` writes `.analysis/data/figures/<id>.json`: the machine-readable table behind the figure, its
parameters and extraction date. It is the reproducible evidence the figures brief asks for; the chart is
drawn from the same rows, so the two cannot drift.

Run with /tmp/pptxenv/bin/python3 (matplotlib, python-pptx, Pillow).
"""
import datetime as _dt
import json
import math
import re
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402
from pptx.util import Inches  # noqa: E402

from record import session_coverage  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, ".analysis", "diagrams", "book")
SUMMARIES = os.path.join(ROOT, ".analysis", "data", "figures")

# deck_lib's design-system tokens as #hex, so a drawn figure and a native chart cannot drift apart.
INK, BODY, MUTED, RULE = "#0B0D14", "#383D49", "#666D7B", "#C6C9D0"
PINK, PINK_LIGHT, PINK_MID, PINK_DARK = "#E93A61", "#F1839A", "#ED5F7E", "#C62249"
GREY, GREY_DARK, GREY_LIGHT = "#C6C9D0", "#383D49", "#EDEEF1"  # ink-line, ink-body, track
INK_STRONG, INK_QUIET, INK_RAISE, TINT = "#1A1E29", "#7B8290", "#F4F5F8", "#FEF1F4"
CONTRAST = INK  # deck_lib.CONTRAST: allied repos, infrastructure, the second family beside rose
OWNER = "#A5153E"  # deck_lib.OWNER: the owner only, and never beside PINK_DARK
CUSTOMER = MUTED  # the example customer fleet (deck_lib.CATEGORY_COLORS)
CODEX = INK_QUIET  # work done with OpenAI Codex rather than Claude Code
# Categorical order, fixed: the thing that matters, then context greys, then the second family.
CAT = [PINK, GREY_DARK, GREY, PINK_LIGHT, CONTRAST, PINK_DARK, GREY_LIGHT]
SEQ = [PINK_LIGHT, PINK_MID, PINK, PINK_DARK, OWNER]  # data-scale-5 .. data-scale-1

CHART_W, CHART_H = 8.35, 5.75
# The book sets a chart this wide (its measure plus the figure's reach into both margins). `save`
# redraws every figure at this width, so a point size in the code is the point size on paper; a
# chart left at CHART_W prints its 7.5 pt labels near 5 pt.
PRINT_W = 5.65
MIN_PT = 7


def named(name, fallback=None):
    """deck_lib's book-wide colour for a repo, category, model, actor, kind of work or time state, as #hex."""
    from deck_lib import named_color
    c = named_color(name)
    return "#" + c if c else fallback


def _fonts():
    for f in ("Geist-Regular.ttf", "Geist-Medium.ttf", "Geist-Light.ttf", "GeistMono-Regular.ttf",
              "GeistMono-Light.ttf"):
        p = os.path.expanduser(f"~/Library/Fonts/{f}")
        if os.path.exists(p):
            font_manager.fontManager.addfont(p)
    names = {f.name for f in font_manager.fontManager.ttflist}
    return "Geist" if "Geist" in names else "DejaVu Sans"


def style():
    """The design system's chart chrome (chart.tsx, "choosing a chart"): Geist Light for text, hairline
    gridlines in ink-line, no axis or tick lines, thin marks; `ds_finish` sets the mono labels at save."""
    plt.rcParams.update({
        "font.family": _fonts(), "font.weight": "light", "font.size": 10.5, "axes.titlesize": 10.5,
        "axes.labelsize": 9, "axes.titleweight": "light", "axes.labelweight": "light",
        "axes.edgecolor": RULE, "axes.linewidth": 0.5, "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "axes.grid": True, "grid.color": RULE, "grid.linewidth": 0.5,
        "axes.axisbelow": True, "xtick.major.size": 0, "ytick.major.size": 0, "xtick.minor.size": 0,
        "ytick.minor.size": 0, "xtick.major.pad": 6, "ytick.major.pad": 6,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "text.color": BODY, "axes.labelcolor": MUTED, "legend.frameon": False, "legend.fontsize": 8.5,
        "legend.handlelength": 0.9, "legend.handleheight": 0.9, "legend.handletextpad": 0.5,
        "legend.labelcolor": BODY, "patch.linewidth": 0, "lines.linewidth": 1.5, "lines.markersize": 4,
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })


MONO_FONT = "Geist Mono"


def ds_finish(figure):
    """Set the chart labels the way the design system's charts do, after a figure is drawn: tick values,
    axis titles and legends in Geist Mono (axis titles as uppercase eyebrows), no chart title baked in,
    since the book's caption carries it, and a panel heading kept only where panels need telling apart."""
    axes = [a for a in figure.axes if a.get_visible() and a.get_label() != "<colorbar>"]
    titled = [a for a in axes if a.get_title(loc="center") or a.get_title(loc="left")]
    if getattr(figure, "_suptitle", None) is not None:
        figure._suptitle.set_visible(False)
    for a in figure.axes:
        for t in a.get_xticklabels() + a.get_yticklabels():
            t.set_fontfamily(MONO_FONT)
            t.set_fontweight("light")
            t.set_fontsize(max(MIN_PT, min(t.get_fontsize(), 7.5)))
        for lab in (a.xaxis.label, a.yaxis.label):
            if lab.get_text():
                # Uppercase mono runs about a third wider than the sans it replaces, so a long axis
                # title that fitted before can run off the canvas; wrap it to the axis instead.
                width = a.get_position().width * figure.get_figwidth() * (72 / 7.5) / 0.62
                lines = [textwrap.fill(line, max(24, int(width))) for line in lab.get_text().split("\n")]
                lab.set_text("\n".join(lines).upper())
                lab.set_fontfamily(MONO_FONT)
                lab.set_fontsize(7.5)
                lab.set_color(MUTED)
        for loc in ("center", "left", "right"):
            text = a.get_title(loc=loc)
            if not text:
                continue
            a.set_title("", loc=loc)
            if len(titled) > 1:
                # Panels side by side each get their own width; an unwrapped heading runs into its neighbour's.
                chars = max(16, int(a.get_position().width * figure.get_figwidth() * 72 / (7.5 * 0.62)))
                a.set_title(textwrap.fill(text.upper(), chars), loc="left", fontfamily=MONO_FONT, fontsize=7.5,
                            color=MUTED, fontweight="light", pad=8)
        leg = a.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                t.set_fontfamily(MONO_FONT)
                t.set_fontweight("light")
                t.set_fontsize(max(MIN_PT, min(t.get_fontsize(), 7.5)))
            if leg.get_title().get_text():
                leg.get_title().set_text(leg.get_title().get_text().upper())
                leg.get_title().set_fontfamily(MONO_FONT)
                leg.get_title().set_fontsize(7.5)
                leg.get_title().set_color(MUTED)
    for t in [t for a in figure.axes for t in a.texts] + list(figure.texts):
        t.set_fontsize(max(MIN_PT, t.get_fontsize()))
        if t.get_fontweight() in ("bold", "semibold", "heavy", "black", 600, 700, 800, 900):
            t.set_fontweight("normal")
    for leg in figure.legends:
        for t in leg.get_texts():
            t.set_fontfamily(MONO_FONT)
            t.set_fontweight("light")
            t.set_fontsize(max(MIN_PT, min(t.get_fontsize(), 7.5)))


def fig(w=CHART_W, h=CHART_H, ncols=1, nrows=1, **kw):
    style()
    return plt.subplots(nrows, ncols, figsize=(w, h), constrained_layout=True, **kw)


def asset(fig_id, suffix=""):
    """`figure-03-01.png` (suffix distinguishes a breakdown: `figure-03-01-by-repo.png`)."""
    ch, n = fig_id.split(".")
    os.makedirs(ASSETS, exist_ok=True)
    return os.path.join(ASSETS, f"figure-{int(ch):02d}-{int(n):02d}{('-' + suffix) if suffix else ''}.png")


# PNGs drawn with the coverage footnote this run; picture() gives each the note as its alt text.
_COVERED = set()


def coverage(figure, note=None):
    """Footnote a figure drawn from the session logs with how many days of them it has. A figure's own note
    goes in the same footer: two notes placed separately land on top of each other once `save` narrows
    the canvas to print width."""
    text = f"{note}\n{session_coverage()}" if note else session_coverage()
    figure.text(0.0, 0.0, text, ha="left", va="top", fontsize=8.5, color=MUTED, wrap=True)
    figure._session_coverage = True


# A tick a reader can drop and still read the axis: a number, or a date by day or month ("29 Dec",
# "Aug", "2026-W35"). A category that happens to carry a count ("None yet\nn = 32") is not one.
_NUMERIC_TICK = re.compile(r"^([−\-$]?[\d.,]+%?[KM]?|\d{1,2} [A-Z][a-z]{2}|[A-Z][a-z]{2}( \d{1,2})?|\d{4}-W\d{2}|"
                           r"\d{1,2}:\d{2}|\d+ ?[dhm])$")


def _thin_ticks(figure):
    """Hide date and number tick labels that overlap their neighbour. At print width a weekly axis
    has more labels than room; a category name (a repo, a component) is never dropped, because the
    bar beside it would lose its meaning."""
    renderer = figure.canvas.get_renderer()
    for a in figure.axes:
        for axis, horiz in ((a.xaxis, True), (a.yaxis, False)):
            labels = [t for t in axis.get_ticklabels() if t.get_visible() and t.get_text()]
            if len(labels) < 3 or not all(_NUMERIC_TICK.match(t.get_text().split("\n")[0].strip()) for t in labels):
                continue
            boxes = [t.get_window_extent(renderer) for t in labels]
            order = sorted(range(len(labels)), key=lambda i: boxes[i].x0 if horiz else boxes[i].y0)
            step = 1
            while step < len(labels):
                kept = order[::step]
                if all(not boxes[i].expanded(1.0, 1.0).overlaps(boxes[j].padded(2)) for i, j in zip(kept, kept[1:])):
                    break
                step += 1
            for k, i in enumerate(order):
                labels[i].set_visible(k % step == 0)


PAD = 0.15


def _outside(leg):
    """Whether a legend is anchored outside its axes (below, beside, above)."""
    anchor = leg._bbox_to_anchor
    if anchor is None or not hasattr(anchor, "_bbox"):
        return False
    x0, y0, x1, y1 = anchor._bbox.extents
    return min(x0, y0) < 0 or max(x1, y1) > 1


def _stack_below(figure, handles, labels):
    """Lay the plots out without the legend, freeze that layout, then set the legend and any footnote
    one under the other below everything, from the left edge of the plots' labels. Placed by the layout
    engine instead, a legend below the figure lands on the footnote, and one beside the axes squeezes them."""
    renderer = figure.canvas.get_renderer()
    figure.canvas.draw()
    figure.set_layout_engine("none")
    W, H = figure.bbox.width, figure.bbox.height
    boxes = [a.get_tightbbox(renderer) for a in figure.axes if a.get_visible()]
    left = max(0.0, min(b.x0 for b in boxes))
    y = min(b.y0 for b in boxes) - 4
    longest = max(len(t) for t in labels)
    ncol = max(1, min(len(labels), int((W - left) / (longest * 7.5 * 0.62 * figure.dpi / 72 + 30))))
    leg = figure.legend(handles, labels, loc="upper left", bbox_to_anchor=(left / W, y / H),
                        bbox_transform=figure.transFigure, ncol=ncol, fontsize=7.5, frameon=False, borderaxespad=0)
    for t in leg.texts:
        t.set_fontfamily(MONO_FONT)
        t.set_fontweight("light")
    figure.canvas.draw()
    y = leg.get_window_extent(renderer).y0 - 6
    for t in figure.texts:
        if t.get_position()[1] <= 0.02 and t.get_visible() and t.get_text():
            t.set_position((left / W, y / H))
            t.set_va("top")
            figure.canvas.draw()
            y = t.get_window_extent(renderer).y0 - 4


def _fit_legends(figure):
    """Make every legend fit the print width without squeezing the plot.

    A legend anchored outside its axes counts as part of that axes for the layout, so one that runs
    past the canvas (long tick labels push its left edge in, mono type widens it) makes the layout
    shrink the plot to almost nothing. Each such legend becomes one figure legend below the whole
    figure, with only as many columns as fit; a legend inside its axes only loses columns."""
    room = figure.get_figwidth() * figure.dpi * 0.98
    renderer = figure.canvas.get_renderer()
    moved = []
    for a in figure.axes:
        leg = a.get_legend()
        # A legend wider than half the figure crowds its plot wherever it sits, inside or out.
        if leg is not None and (_outside(leg) or leg.get_window_extent(renderer).width > room * 0.55):
            moved += list(zip(leg.legend_handles, [t.get_text() for t in leg.texts]))
            leg.remove()
    if moved:
        _stack_below(figure, *zip(*moved))
    owners = [(a, a.get_legend()) for a in figure.axes if a.get_legend() is not None]
    owners += [(figure, leg) for leg in figure.legends if not getattr(leg, "_outside_loc", None)]
    for owner, leg in owners:
        ncols = leg._ncols
        if ncols <= 1 or leg.get_window_extent(renderer).width <= room:
            continue
        handles, labels = list(leg.legend_handles), [t.get_text() for t in leg.texts]
        size, title = leg.texts[0].get_fontsize(), leg.get_title().get_text()
        anchor = leg._bbox_to_anchor
        kw = dict(loc=leg._loc, fontsize=size, frameon=leg.get_frame_on(), title=title or None)
        if anchor is not None and hasattr(anchor, "_bbox"):
            kw.update(bbox_to_anchor=anchor._bbox.bounds, bbox_transform=anchor._transform)
        while ncols > 1:
            ncols -= 1
            leg.remove()
            leg = owner.legend(handles, labels, ncol=ncols, **kw)
            for t in leg.texts:
                t.set_fontfamily(MONO_FONT)
                t.set_fontweight("light")
            figure.canvas.draw()
            if leg.get_window_extent(renderer).width <= room:
                break


def _texts(figure):
    """Every visible, non-empty text on the figure: ticks, axis labels, titles, notes and legends."""
    out = []
    for a in figure.axes:
        if not a.get_visible():
            continue
        for axis in (a.xaxis, a.yaxis):
            lo, hi = sorted(axis.get_view_interval())
            # Matplotlib keeps labels for ticks outside the view; they are never drawn.
            out += [t for t, loc in zip(axis.get_ticklabels(), axis.get_ticklocs())
                    if lo - 1e-9 * abs(hi - lo) <= loc <= hi + 1e-9 * abs(hi - lo)]
        out += [a.xaxis.label, a.yaxis.label]
        out += [a.title, a._left_title, a._right_title] + list(a.texts)
        if a.get_legend() is not None:
            out += list(a.get_legend().texts) + [a.get_legend().get_title()]
    for leg in figure.legends:
        out += list(leg.texts) + [leg.get_title()]
    out += list(figure.texts)
    return [t for t in out if t.get_visible() and t.get_text().strip()]


def _wrap_to(lab, room, renderer, vertical=False):
    """Wrap a label to `room` pixels along its reading direction, from its unwrapped text."""
    flat = " ".join(lab.get_text().split())
    lab.set_text(flat)
    full = lab.get_window_extent(renderer)
    length = full.height if vertical else full.width
    if length <= room or not flat:
        return False
    per_char = length / len(flat)
    chars = max(10, int(room / per_char))
    for _ in range(6):
        lab.set_text(textwrap.fill(flat, chars))
        box = lab.get_window_extent(renderer)
        if (box.height if vertical else box.width) <= room or chars <= 10:
            break
        chars -= 2
    return True


def _fit_labels(figure):
    """Wrap axis titles and panel headings by their measured size once the layout has placed the axes:
    an x title to its axes (and to the room either side of its centre, so it stays on the canvas), a
    y title to its axes' height. Wrapping by a character count before layout used the axes' default
    width, and a tight crop leaves an axis title's overhang out of the picture."""
    renderer = figure.canvas.get_renderer()
    W = figure.bbox.width
    changed = False
    for a in figure.axes:
        if not a.get_visible():
            continue
        span = a.get_window_extent(renderer)
        lab = a.xaxis.label
        if lab.get_text():
            c = (span.x0 + span.x1) / 2
            room = min(max(span.width * 1.15, 160), 2 * min(c, W - c) - 6)
            changed |= _wrap_to(lab, room, renderer)
        lab = a.yaxis.label
        if lab.get_text():
            changed |= _wrap_to(lab, max(span.height * 1.05, 80), renderer, vertical=True)
        lab = a._left_title
        if lab.get_text():
            # A panel with a neighbour to its right keeps its heading over itself.
            beside = any(o is not a and o.get_visible() and o.get_window_extent(renderer).x0 >= span.x1 - 5
                         and o.get_window_extent(renderer).y1 > span.y0 and o.get_window_extent(renderer).y0 < span.y1
                         for o in figure.axes)
            room = span.width * 1.02 if beside else min(max(span.width * 1.1, W * 0.45), W - span.x0 - 6)
            changed |= _wrap_to(lab, room, renderer)
    for lab in (getattr(figure, "_supxlabel", None), getattr(figure, "_supylabel", None)):
        if lab is not None and lab.get_text():
            changed |= _wrap_to(lab, (figure.bbox.height if lab is getattr(figure, "_supylabel", None) else W) - 12,
                                renderer, vertical=lab is getattr(figure, "_supylabel", None))
    if changed:
        figure.canvas.draw()


def _legends_clear(figure):
    """A legend drawn inside its plot that lands on a note or a label moves below the figure."""
    renderer = figure.canvas.get_renderer()
    moved = []
    for a in figure.axes:
        leg = a.get_legend()
        if leg is None or _outside(leg):
            continue
        box = leg.get_window_extent(renderer)
        own = set(leg.texts) | {leg.get_title()}
        others = [t for t in _texts(figure) if t not in own]
        if any(box.overlaps(t.get_window_extent(renderer)) for t in others):
            moved += list(zip(leg.legend_handles, [t.get_text() for t in leg.texts]))
            leg.remove()
    if moved:
        _stack_below(figure, *zip(*moved))


def _crop(figure, extra):
    """The saved area in inches: the tight box of the plots unioned with the extent of every visible
    text, so nothing is cut at the canvas edge, padded by PAD."""
    renderer = figure.canvas.get_renderer()
    boxes = [figure.get_tightbbox(renderer, bbox_extra_artists=extra).transformed(figure.dpi_scale_trans)]
    boxes += [t.get_window_extent(renderer) for t in _texts(figure)]
    u = Bbox.union(boxes)
    inches = Bbox.from_extents(u.x0, u.y0, u.x1, u.y1).transformed(figure.dpi_scale_trans.inverted())
    return inches.padded(PAD)


ISSUES = []


def _check(figure, name, crop):
    """Warn when a text runs off the canvas (the crop then grows and the chart prints smaller), when two
    texts overlap, or when the smallest text prints under MIN_PT at the book's figure width."""
    renderer = figure.canvas.get_renderer()
    texts = _texts(figure)
    # The text alone: an annotation's own extent includes its arrow, which may cross a label by design.
    boxes = [(t, Text.get_window_extent(t, renderer)) for t in texts]
    W = figure.bbox.width
    saved = crop.transformed(figure.dpi_scale_trans)
    for t, b in boxes:
        if not (saved.x0 - 1 <= b.x0 and b.x1 <= saved.x1 + 1 and saved.y0 - 1 <= b.y0 and b.y1 <= saved.y1 + 1):
            ISSUES.append(f"CLIP {name}: {t.get_text()[:40]!r} is cut by the saved area")
        elif (b.x0 < -2 or b.x1 > W + 2) and crop.width > PRINT_W + 0.03:
            ISSUES.append(f"CLIP {name}: {t.get_text()[:40]!r} runs past the canvas and shrinks the print")
    def parallel_clear(t, u):
        """Two labels set at the same slant overlap only if their lines are closer than a line of type;
        their rectangular boxes overlap whenever they are neighbours, so the boxes alone cannot tell."""
        r = t.get_rotation() % 180
        if r in (0, 90) or abs(r - u.get_rotation() % 180) > 0.5:
            return False
        p1 = t.get_transform().transform(t.get_position())
        p2 = u.get_transform().transform(u.get_position())
        n = math.sin(math.radians(r)), -math.cos(math.radians(r))
        gap = abs((p2[0] - p1[0]) * n[0] + (p2[1] - p1[1]) * n[1])
        lines = max(t.get_text().count("\n"), u.get_text().count("\n")) + 1
        return gap >= t.get_fontsize() * figure.dpi / 72 * 1.05 * lines

    for i, (t, b) in enumerate(boxes):
        for u, c in boxes[i + 1:]:
            if parallel_clear(t, u):
                continue
            ix = min(b.x1, c.x1) - max(b.x0, c.x0)
            iy = min(b.y1, c.y1) - max(b.y0, c.y0)
            # Rotated labels have generous rectangular boxes; corners that merely touch are not a clash.
            if ix > 0 and iy > 0 and ix * iy > 0.1 * min(b.width * b.height, c.width * c.height):
                ISSUES.append(f"OVERLAP {name}: {t.get_text()[:30]!r} / {u.get_text()[:30]!r}")
    scale = min(1.0, PRINT_W / crop.width)
    smallest = min((t.get_fontsize() for t in texts), default=MIN_PT) * scale
    if os.environ.get("FIGURE_SIZES"):
        print(f"SIZE {name} {smallest:.2f}")
    if smallest < MIN_PT - 0.05:
        ISSUES.append(f"SMALL {name}: smallest text prints at {smallest:.1f} pt")
    for msg in ISSUES:
        if name in msg:
            print(msg)
    return smallest


def finalize(figure, name):
    """Fit, check and measure a drawn figure; returns the crop to save with. `save` and the
    publisher's chart redraw share it so both apply the same rules."""
    ds_finish(figure)
    for a in figure.axes:
        for t in a.texts:
            t.set_in_layout(False)
    figure.canvas.draw()
    _fit_labels(figure)
    _fit_legends(figure)
    _legends_clear(figure)
    _thin_ticks(figure)
    extra = figure.get_default_bbox_extra_artists() + [t for a in figure.axes for t in a.texts] + list(figure.texts)
    # Notes that run past the plot widen the crop and shrink everything on paper. They are out of the
    # layout, so the layout is told to leave their overhang free: the plot narrows and the type keeps
    # its print size. A figure laid out by hand (no engine) narrows its canvas instead.
    for _ in range(4):
        renderer = figure.canvas.get_renderer()
        W = figure.bbox.width
        boxes = [t.get_window_extent(renderer) for t in _texts(figure)]
        left = max([0.0] + [-b.x0 for b in boxes]) / W
        right = max([0.0] + [b.x1 - W for b in boxes]) / W
        if left + right <= 0.005:
            break
        engine = figure.get_layout_engine()
        if engine is not None and hasattr(engine, "set") and "rect" in engine.get():
            x0, y0, w0, h0 = engine.get()["rect"]
            engine.set(rect=(x0 + left, y0, max(0.4, w0 - left - right), h0))
        elif any(a.get_visible() for a in figure.axes):
            # Laid out by hand (a legend set below froze the layout): squeeze the plots horizontally.
            xs = [a.get_position() for a in figure.axes if a.get_visible()]
            lo, hi = min(p.x0 for p in xs), max(p.x1 for p in xs)
            k = max(0.4, (hi - lo - left - right) / (hi - lo))
            for a in figure.axes:
                p = a.get_position()
                a.set_position([lo + left + (p.x0 - lo) * k, p.y0, p.width * k, p.height])
        else:
            over = _crop(figure, extra).width - PRINT_W
            w, h = figure.get_size_inches()
            if over <= 0.03 or w - over < 4.2:
                break
            figure.set_size_inches(w - over, h)
        figure.canvas.draw()
        _fit_labels(figure)
        _thin_ticks(figure)
    crop = _crop(figure, extra)
    _check(figure, name, crop)
    return crop


def save(figure, path, dpi=300):
    # The crop's padding is part of the picture the book scales to PRINT_W, so the canvas is that much narrower.
    w, h = figure.get_size_inches()
    if w > PRINT_W - 2 * PAD:
        figure.set_size_inches(PRINT_W - 2 * PAD, h * (PRINT_W - 2 * PAD) / w)
    crop = finalize(figure, os.path.basename(path))
    figure.savefig(path, dpi=dpi, bbox_inches=crop)
    if getattr(figure, "_session_coverage", False):
        _COVERED.add(os.path.abspath(path))
    plt.close(figure)
    return path


def picture(slide, box, path):
    """Place a drawn figure in the slide's chart box, scaled to fit and centred."""
    from PIL import Image
    x, y, w, h = box
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    pic = slide.shapes.add_picture(path, Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
    pic.name = os.path.splitext(os.path.basename(path))[0]
    if os.path.abspath(path) in _COVERED:
        pic._element.nvPicPr.cNvPr.set("descr", session_coverage())
    return pic


def summary(fig_id, question, params, table, notes="", sources=(), columns=None, extra=None):
    """The figure's evidence: rows drawn, parameters, sources, extraction date. Returns the path."""
    os.makedirs(SUMMARIES, exist_ok=True)
    path = os.path.join(SUMMARIES, f"{fig_id}.json")
    doc = {"figure": fig_id, "question": question, "extracted": _dt.date.today().isoformat(),
           "params": params, "columns": columns, "table": table, "notes": notes, "sources": list(sources)}
    if extra:
        doc["extra"] = extra
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False, default=str)
        f.write("\n")
    return path


# ------------------------------------------------------------------ statistics

def wilson(k, n, z=1.96):
    """Wilson score interval for a share; (lo, hi), or (None, None) when n is 0."""
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - r), min(1.0, c + r)


def quantiles(xs, qs=(0.25, 0.5, 0.75)):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return [None] * len(qs)
    out = []
    for q in qs:
        i = (len(xs) - 1) * q
        lo, hi = math.floor(i), math.ceil(i)
        out.append(xs[lo] + (xs[hi] - xs[lo]) * (i - lo))
    return out


def bootstrap_median(xs, n=2000, seed=1):
    """95% interval for the median by resampling; (lo, hi)."""
    import random
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None, None
    rnd = random.Random(seed)
    meds = sorted(quantiles([rnd.choice(xs) for _ in xs], (0.5,))[0] for _ in range(n))
    return meds[int(0.025 * n)], meds[int(0.975 * n) - 1]


# ------------------------------------------------------------------ forms

def dot_whisker(ax, labels, est, lo, hi, n=None, fmt="{:.0%}", ref=None, ref_label=None, color=PINK, xlabel=None):
    """Estimates with intervals, one row each, the count beside the label; a reference line if given."""
    ys = list(range(len(labels)))[::-1]
    for y, e, a, b in zip(ys, est, lo, hi):
        if a is not None and b is not None:
            ax.plot([a, b], [y, y], color=GREY, linewidth=2, solid_capstyle="round", zorder=2)
        ax.plot([e], [y], "o", color=color, markersize=8, zorder=3)
        ax.annotate(fmt.format(e), (e, y), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=9.5)
    if ref is not None:
        ax.axvline(ref, color=GREY_DARK, linewidth=1, linestyle=(0, (2, 3)))
        if ref_label:
            # Above the plot: inside it the label sat on the top row's value.
            ax.text(ref, 1.01, ref_label, color=GREY_DARK, fontsize=9, ha="center", va="bottom",
                    transform=ax.get_xaxis_transform())
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{l}  (n={k})" if n else l for l, k in zip(labels, n or labels)])
    # Headroom for the top row's value, which sits above its dot.
    ax.set_ylim(-0.7, len(labels) + 0.05)
    ax.grid(axis="y", visible=False)
    if xlabel:
        ax.set_xlabel(xlabel)


def dumbbell(ax, labels, a, b, names=("before", "after"), fmt="{:,.0f}", xlabel=None):
    """Two values per row joined by a line: the change reads as its length and direction."""
    ys = list(range(len(labels)))[::-1]
    for y, x0, x1 in zip(ys, a, b):
        ax.plot([x0, x1], [y, y], color=GREY, linewidth=2, zorder=2)
        ax.plot([x0], [y], "o", color=GREY_DARK, markersize=8, zorder=3)
        ax.plot([x1], [y], "o", color=PINK, markersize=8, zorder=3)
    ax.plot([], [], "o", color=GREY_DARK, label=names[0])
    ax.plot([], [], "o", color=PINK, label=names[1])
    ax.legend(loc="lower right")
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    # Headroom for the top row's value, which sits above its dot.
    ax.set_ylim(-0.7, len(labels) + 0.05)
    ax.grid(axis="y", visible=False)
    if xlabel:
        ax.set_xlabel(xlabel)


def heatmap(ax, rows, cols, values, cmap=None, vmax=None, label_every=4, cbar_label=None, missing=None):
    """Rows by columns, one hue light to dark; `missing` marks cells with no data (None) in light grey."""
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    cm = cmap or LinearSegmentedColormap.from_list("brand", ["#FFFFFF", TINT] + SEQ)
    arr = np.array([[np.nan if v is None else v for v in r] for r in values], dtype=float)
    cm.set_bad(GREY_LIGHT if missing else "white")
    im = ax.imshow(np.ma.masked_invalid(arr), aspect="auto", cmap=cm, vmin=0, vmax=vmax, interpolation="nearest")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows)
    ax.set_xticks(range(0, len(cols), label_every))
    ax.set_xticklabels([cols[i] for i in range(0, len(cols), label_every)])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.outline.set_visible(False)
    if cbar_label:
        cb.set_label(cbar_label)
    return im


def ecdf(ax, values, label=None, color=PINK, censored=None, xlabel=None, xmax=None):
    """Cumulative share of observations at or below x; censored observations, if given, are drawn as ticks
    at their own x, with their count at the right edge, so the curve is read as a lower bound where they sit."""
    xs = sorted(v for v in values if v is not None)
    n = len(xs) + (len(censored) if censored else 0)
    ys = [(i + 1) / n for i in range(len(xs))]
    ax.step([0] + xs, [0] + ys, where="post", color=color, label=label)
    if censored:
        top = xmax or max(xs + list(censored))
        ax.plot(censored, [ys[-1] if ys else 0] * len(censored), "|", color=color, markersize=10, alpha=0.7)
        ax.text(top, (ys[-1] if ys else 0) + 0.02, f"{len(censored)} still open", ha="right", fontsize=9, color=MUTED)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Cumulative share")
    if xmax:
        ax.set_xlim(0, xmax)
    if xlabel:
        ax.set_xlabel(xlabel)
    return n


def lanes(ax, names, spans, points=None, xlim=None, xlabel=None, colors=None):
    """One lane per name: spans [(start, end, color, label)] as bars; points [(x, color, marker)] as marks."""
    ys = list(range(len(names)))[::-1]
    for y, name in zip(ys, names):
        for s in (spans or {}).get(name, []):
            x0, x1, col, lab = s
            ax.barh(y, x1 - x0, left=x0, height=0.55, color=col or GREY_LIGHT, edgecolor="white", linewidth=1)
            if lab:
                ax.text(x0 + (x1 - x0) / 2, y, lab, ha="center", va="center", fontsize=8.5, color=INK)
        for p in (points or {}).get(name, []):
            x, col, mk = p
            ax.plot([x], [y], mk or "o", color=col or PINK, markersize=7, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels(names)
    ax.set_ylim(-0.7, len(names) - 0.3)
    ax.grid(axis="y", visible=False)
    if xlim:
        ax.set_xlim(*xlim)
    if xlabel:
        ax.set_xlabel(xlabel)


def stacked100(ax, cats, parts, colors=None, horizontal=True, fmt="{:.0%}", min_label=0.06, xlabel=None):
    """Composition bars summing to one; `parts` is {name: [share per cat]}, drawn in the given order."""
    import numpy as np
    cols = colors or CAT
    left = np.zeros(len(cats))
    for (name, vals), col in zip(parts.items(), cols):
        v = np.array([x or 0 for x in vals], dtype=float)
        if horizontal:
            ax.barh(cats, v, left=left, color=col, edgecolor="white", linewidth=2, label=name)
        else:
            ax.bar(cats, v, bottom=left, color=col, edgecolor="white", linewidth=2, label=name)
        for i, (x, l) in enumerate(zip(v, left)):
            if x >= min_label:
                txt = "white" if col in (PINK, GREY_DARK, PINK_DARK, CONTRAST, OWNER, INK_STRONG) else INK
                if horizontal:
                    ax.text(l + x / 2, i, fmt.format(x), ha="center", va="center", fontsize=9, color=txt)
                else:
                    ax.text(i, l + x / 2, fmt.format(x), ha="center", va="center", fontsize=9, color=txt)
        left = left + v
    if horizontal:
        ax.set_xlim(0, 1)
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.grid(axis="y", visible=False)
    else:
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.grid(axis="x", visible=False)
    ax.legend(ncol=min(4, len(parts)), loc="upper center", bbox_to_anchor=(0.5, -0.12 if horizontal else -0.08))
    if xlabel:
        ax.set_xlabel(xlabel)


def scatter(ax, xs, ys, labels=None, color=PINK, xlabel=None, ylabel=None, fit=True):
    """Points with an optional least-squares line and the Pearson r in the corner."""
    ax.plot(xs, ys, "o", color=color, alpha=0.8, markersize=6)
    if labels:
        for x, y, l in zip(xs, ys, labels):
            ax.annotate(l, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8, color=MUTED)
    if fit and len(xs) > 2:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        syy = sum((y - my) ** 2 for y in ys)
        if sxx and syy:
            b = sxy / sxx
            a = my - b * mx
            lo, hi = min(xs), max(xs)
            ax.plot([lo, hi], [a + b * lo, a + b * hi], color=GREY_DARK, linewidth=1.2)
            r = sxy / math.sqrt(sxx * syy)
            ax.text(0.98, 0.95, f"r = {r:.2f}, n = {n}", transform=ax.transAxes, ha="right", va="top",
                    fontsize=9.5, color=MUTED)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)


def shade_missing(ax, x0, x1, label="Data not available"):
    """The unlogged span, hatched: missing data, not zero."""
    ax.axvspan(x0, x1, color=GREY_LIGHT, alpha=0.5, hatch="//", linewidth=0)
    ax.text((x0 + x1) / 2, ax.get_ylim()[1], label, ha="center", va="top", fontsize=8.5, color=MUTED, rotation=90)
