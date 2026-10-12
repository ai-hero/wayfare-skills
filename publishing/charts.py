"""Draw a deck view's native chart data (the bar and line charts the viewer reads) as print files,
in `figure_lib`'s brand style so these sit beside the drawn figures without a seam."""
import math
import textwrap

import figure_lib as F
from matplotlib.ticker import FuncFormatter

W, ROW_H = F.PRINT_W - 2 * F.PAD, 0.42


def _fmt(fmt):
    if fmt and "%" in fmt:
        return lambda v: f"{v:.0%}"
    return lambda v: f"{v:,.0f}" if abs(v) >= 10 or float(v).is_integer() else f"{v:,.1f}"


def _color(c, i):
    return "#" + c if c else F.CAT[i % len(F.CAT)]


def _bar(ax, c):
    cats, series, fmt = c["cats"], c["series"], _fmt(c.get("fmt"))
    horizontal, stacked = c.get("horizontal"), c.get("stacked")
    n = len(series)
    width = 0.7 if stacked else 0.8 / max(n, 1)
    base = [0.0] * len(cats)
    totals = [sum((s["values"][j] or 0.0) for s in series) for j in range(len(cats))] if stacked else \
        [max((v or 0.0) for s in series for v in s["values"])]
    for i, s in enumerate(series):
        vals = [v or 0.0 for v in s["values"]]
        pos = [j + (0 if stacked else (i - (n - 1) / 2) * width) for j in range(len(cats))]
        kw = dict(color=_color(s.get("color"), i), label=s["name"])
        if horizontal:
            bars = ax.barh(pos, vals, height=width, left=base if stacked else None, **kw)
        else:
            bars = ax.bar(pos, vals, width=width, bottom=base if stacked else None, **kw)
        if c.get("labels"):
            for b, v in zip(bars, vals):
                if not v or (stacked and v < 0.09 * max(totals)):
                    continue
                if True:
                    x, y = (b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2)
                    dark = sum(int(kw["color"][k:k + 2], 16) for k in (1, 3, 5)) < 420
                    ax.text(x, y, fmt(v), ha="center", va="center", fontsize=7.5, fontfamily=F.MONO_FONT,
                            color="white" if dark else F.INK)
        if stacked:
            base = [a + b for a, b in zip(base, vals)]
    ticks = list(range(len(cats)))
    if horizontal:
        ax.set_yticks(ticks, cats)
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
        ax.grid(axis="y", visible=False)
        if c.get("yTitle"):
            ax.set_xlabel(c["yTitle"])
    else:
        ax.set_xticks(ticks, cats, rotation=0 if len(cats) < 8 else 45, ha="center" if len(cats) < 8 else "right")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
        ax.grid(axis="x", visible=False)
        if c.get("yTitle"):
            ax.set_ylabel(c["yTitle"])
        if c.get("xTitle"):
            ax.set_xlabel(c["xTitle"])
    lim = (c.get("min") if c.get("min") is not None else None, c.get("max"))
    (ax.set_xlim if horizontal else ax.set_ylim)(*lim)


def _line(ax, c):
    cats, fmt = c["cats"], _fmt(c.get("fmt"))
    xs = list(range(len(cats)))
    for i, s in enumerate(c["series"]):
        pts = [(x, v) for x, v in zip(xs, s["values"]) if v is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=_color(s.get("color"), i), label=s["name"],
                marker="o", markersize=3)
    marks = sorted(c.get("marks") or [], key=lambda m: m["at"])
    named = [m for m in marks if m["name"].strip()]
    for m in marks:
        ax.axvline(m["at"], color=_color(m.get("color"), 0), linestyle=":", linewidth=1)
    # A rotated label is one line tall; marks closer than that put their labels on top of each other.
    # A pair takes opposite sides of its lines; three or more close together share one label.
    gap = 10 / (W * 0.8 * 72 / max(1, len(cats)))
    clusters = []
    for m in named:
        if clusters and m["at"] - clusters[-1][-1]["at"] < 2 * gap:
            clusters[-1].append(m)
        else:
            clusters.append([m])
    per_unit = W * 0.8 * 72 / max(1, len(cats))  # points per category, as printed
    level_end, level_pt = None, 3
    for group in clusters:
        if len(group) > 2:
            # Three or more names joined run longer than the plot is tall; they go level above it, and a
            # second such label that would reach the first sits a line set higher.
            text = textwrap.fill(" · ".join(m["name"].strip() for m in group).upper(), 34)
            lines = text.count("\n") + 1
            # A label starting in the right part of the plot ends at its last mark instead, so it stays
            # over the plot rather than running off the page.
            right = group[0]["at"] > 0.55 * len(cats)
            start = group[-1]["at"] - 34 * 7 * 0.6 / per_unit if right else group[0]["at"]
            if level_end is not None and start < level_end:
                level_pt += lines * 7 * 1.25 + 2
            ax.annotate(text, (group[-1]["at"] if right else group[0]["at"], 1.0), xycoords=ax.get_xaxis_transform(),
                        xytext=(0, level_pt), textcoords="offset points", va="bottom", ha="right" if right else "left",
                        multialignment="right" if right else "left", fontsize=7, fontfamily=F.MONO_FONT, color=F.MUTED)
            level_end = group[-1]["at"] if right else group[0]["at"] + 34 * 7 * 0.6 / per_unit
            continue
        sides = [(group[0], "right"), (group[1], "left")] if len(group) == 2 else [(group[0], "right")]
        for m, ha in sides:
            ax.text(m["at"], 1.0, " " + m["name"].upper() + " ", transform=ax.get_xaxis_transform(), rotation=90,
                    va="top", ha=ha, fontsize=7, fontfamily=F.MONO_FONT, color=F.MUTED)
    step = max(1, math.ceil(len(cats) / 10))
    ax.set_xticks(xs[::step], cats[::step], rotation=45, ha="right")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
    ax.grid(axis="x", visible=False)
    if c.get("yTitle"):
        ax.set_ylabel(c["yTitle"])
    if c.get("xTitle"):
        ax.set_xlabel(c["xTitle"])
    if c.get("min") is not None or c.get("max") is not None:
        ax.set_ylim(c.get("min"), c.get("max"))


def _height(c):
    if c["kind"] == "bar" and c.get("horizontal"):
        return 1.2 + ROW_H * len(c["cats"]) * (1 if c.get("stacked") else max(1, len(c["series"])) * 0.6)
    return 3.4


def draw(charts, base):
    """Every chart in the view, stacked top to bottom; returns {ext: filename}."""
    heights = [_height(c) + (0.28 * math.ceil(len(c["series"]) / 2) if len(c["series"]) > 1 else 0) for c in charts]
    fig, axes = F.fig(W, sum(heights), nrows=len(charts), gridspec_kw={"height_ratios": heights})
    axes = axes if len(charts) > 1 else [axes]
    for ax, c in zip(axes, charts):
        (_line if c["kind"] == "line" else _bar)(ax, c)
        if len(c["series"]) > 1:
            # Legend names are set in mono, which runs wide; a column count that fits the slide's width
            # spills past the print width, so the columns follow the longest name.
            longest = max(len(s["name"]) for s in c["series"])
            ncol = 1 if longest > 26 else 2 if longest > 14 else 3
            ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=min(ncol, len(c["series"])), fontsize=7.5)
    crop = F.finalize(fig, base.rsplit("/", 1)[-1])
    files = {}
    for ext in ("svg", "pdf", "png"):
        fig.savefig(f"{base}.{ext}", dpi=300, bbox_inches=crop)
        files[ext] = f"{base.rsplit('/', 1)[-1]}.{ext}"
    F.plt.close(fig)
    return files
