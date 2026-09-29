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
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from pptx.util import Inches  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, ".analysis", "diagrams", "book")
SUMMARIES = os.path.join(ROOT, ".analysis", "data", "figures")

INK, BODY, MUTED, RULE = "#0B0D14", "#383D49", "#666D7B", "#E3E5EA"
PINK, PINK_LIGHT, PINK_DARK = "#E93A61", "#F1839A", "#A5153E"
GREY, GREY_DARK, GREY_LIGHT = "#C6C9D0", "#383D49", "#DDE0E5"
TEAL = "#1F8A8A"
# Categorical order, fixed: the thing that matters, then context greys, then the second accent.
CAT = [PINK, GREY_DARK, GREY, PINK_LIGHT, TEAL, PINK_DARK, GREY_LIGHT]
SEQ = ["#FDE7EC", "#F7B7C6", "#F1839A", "#E93A61", "#A5153E"]

CHART_W, CHART_H = 8.35, 5.75


def _fonts():
    for f in ("Geist-Regular.ttf", "Geist-Medium.ttf", "Geist-Light.ttf", "GeistMono-Regular.ttf"):
        p = os.path.expanduser(f"~/Library/Fonts/{f}")
        if os.path.exists(p):
            font_manager.fontManager.addfont(p)
    names = {f.name for f in font_manager.fontManager.ttflist}
    return "Geist" if "Geist" in names else "DejaVu Sans"


def style():
    """Brand rcParams: recessive axes and grid, thin marks, text in ink tokens."""
    plt.rcParams.update({
        "font.family": _fonts(), "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 10.5,
        "axes.edgecolor": RULE, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": RULE, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
        "text.color": BODY, "axes.labelcolor": BODY, "legend.frameon": False, "legend.fontsize": 9.5,
        "lines.linewidth": 2, "lines.markersize": 6, "figure.facecolor": "white", "savefig.facecolor": "white",
    })


def fig(w=CHART_W, h=CHART_H, ncols=1, nrows=1, **kw):
    style()
    return plt.subplots(nrows, ncols, figsize=(w, h), constrained_layout=True, **kw)


def asset(fig_id, suffix=""):
    """`figure-03-01.png` (suffix distinguishes a breakdown: `figure-03-01-by-repo.png`)."""
    ch, n = fig_id.split(".")
    os.makedirs(ASSETS, exist_ok=True)
    return os.path.join(ASSETS, f"figure-{int(ch):02d}-{int(n):02d}{('-' + suffix) if suffix else ''}.png")


def save(figure, path, dpi=200):
    figure.savefig(path, dpi=dpi)
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
            ax.text(ref, len(labels) - 0.4, ref_label, color=GREY_DARK, fontsize=9, ha="center", va="bottom")
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{l}  (n={k})" if n else l for l, k in zip(labels, n or labels)])
    ax.set_ylim(-0.7, len(labels) - 0.3)
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
    ax.set_ylim(-0.7, len(labels) - 0.3)
    ax.grid(axis="y", visible=False)
    if xlabel:
        ax.set_xlabel(xlabel)


def heatmap(ax, rows, cols, values, cmap=None, vmax=None, label_every=4, cbar_label=None, missing=None):
    """Rows by columns, one hue light to dark; `missing` marks cells with no data (None) in light grey."""
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    cm = cmap or LinearSegmentedColormap.from_list("brand", ["#FFFFFF"] + SEQ)
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
                txt = "white" if col in (PINK, GREY_DARK, PINK_DARK, TEAL) else INK
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
