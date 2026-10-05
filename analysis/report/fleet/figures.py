"""Drawn figures for the fleet deck's book cards (Figures 2.1 and 6.1), on report/figure_lib.py.

Each function takes the dict its data.py function returns and writes the PNG figure_lib.asset names.
"""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
from deck_lib import MILESTONES, wlabel  # noqa: E402

MODEL_EVENTS = [("2026-04-16", "Opus 4.7"), ("2026-06-30", "Sonnet 5"), ("2026-07-24", "Opus 5"), ("2026-09-22", "Opus 5.5")]


def week_x(day, weeks):
    """A day's position on an axis whose integer ticks are the ISO weeks' Mondays."""
    y, w, wd = date.fromisoformat(day).isocalendar()
    return (w - int(weeks[0][6:])) + (wd - 1) / 7


def week_axis(ax, weeks, every=4):
    ax.set_xlim(-0.5, len(weeks) - 0.5)
    ax.set_xticks(range(0, len(weeks), every))
    ax.set_xticklabels([wlabel(weeks[i]) for i in range(0, len(weeks), every)])
    ax.set_xlabel("Week of 2026")


def milestones(ax, weeks, events=(), above=False):
    """The factory's milestones as dotted verticals, named along the top (or above the axes); question events in pink."""
    y, va = (1.01, "bottom") if above else (1.0, "top")
    marks = [(week_x(day, weeks), name, F.GREY_DARK) for day, name, *_ in MILESTONES]
    marks += [(week_x(day, weeks), name, F.PINK) for day, name in events]
    for x, _, color in marks:
        ax.axvline(x, color=color, linewidth=0.7, linestyle=(0, (1, 3)), zorder=1)
    # Two lines a few days apart put their rotated names on top of each other; walk the names left to
    # right and push each one at least a line of type past the last, so close events stay legible.
    fig = ax.figure
    # The position is the pre-layout one and `save` narrows the canvas to print width, so the plot
    # ends up narrower than this says; the 0.8 keeps names apart at the width they print.
    width_in = ax.get_position().width * min(fig.get_figwidth(), F.PRINT_W) * 0.8
    sep = (7 * 1.35 / 72) / width_in * (ax.get_xlim()[1] - ax.get_xlim()[0])
    last = None
    for x, name, color in sorted(marks):
        at = x + 0.15 if last is None else max(x + 0.15, last + sep)
        ax.text(at, y, name, rotation=90, ha="left", va=va, fontsize=7, color=color,
                transform=ax.get_xaxis_transform())
        last = at


def draw_features_vs_structure(x):
    """Weekly 100% stacked area of app change sets by mix, the customer-facing share's interval on its edge, and the
    weekly sample size beneath."""
    weeks = x["weeks"]
    cats = [c for c in x["cats"] if sum(x["weekly"][c]) > 0]
    colors = {c: F.named(c, F.GREY_LIGHT) for c in x["cats"]}
    fig, (ax, axn) = F.fig(F.CHART_W, F.CHART_H, nrows=2, sharex=True, gridspec_kw={"height_ratios": [3.2, 1.1]})
    xs = list(range(len(weeks)))
    valid = [s is not None for s in x["share"]]
    # A week with no change set has no share, so the stack breaks there rather than drawing a 0% that never happened.
    i = 0
    while i < len(weeks):
        if not valid[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(weeks) and valid[j + 1]:
            j += 1
        run = list(range(i, j + 1))
        base = [0.0] * len(run)
        for c in cats:
            vals = [x["shares"][c][k] or 0 for k in run]
            ax.fill_between([xs[k] for k in run], base, [b + v for b, v in zip(base, vals)], color=colors[c],
                            linewidth=0, alpha=0.95, label=c if i == next(k for k in range(len(weeks)) if valid[k]) else None)
            base = [b + v for b, v in zip(base, vals)]
        lo = [x["lo"][k] for k in run]
        hi = [x["hi"][k] for k in run]
        ax.fill_between([xs[k] for k in run], lo, hi, color=F.INK, alpha=0.12, linewidth=0)
        ax.plot([xs[k] for k in run], [x["share"][k] for k in run], color=F.INK, linewidth=1.2)
        i = j + 1
    pw, ps, pn = x["peak"]
    pi = weeks.index(pw)
    ax.annotate(f"Peak {ps:.0%} (week of {wlabel(pw)}, n={pn})", (pi, ps), xytext=(-150, 62), textcoords="offset points",
                fontsize=9, color=F.INK, bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.85},
                arrowprops={"arrowstyle": "-", "color": F.INK, "linewidth": 0.8})
    s0, s1 = weeks.index(x["sept"]["weeks"][0]), weeks.index(x["sept"]["weeks"][-1])
    ax.annotate(f"Sept {x['sept']['lo']:.0%}–{x['sept']['hi']:.0%}", ((s0 + s1) / 2, x["sept"]["hi"]), xytext=(-10, 40),
                textcoords="offset points", ha="center", fontsize=9, color=F.INK,
                bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.85},
                arrowprops={"arrowstyle": "-", "color": F.INK, "linewidth": 0.8})
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Share of the week's app\nand infra change sets")
    ax.grid(axis="x", visible=False)
    milestones(ax, weeks, MODEL_EVENTS, above=True)
    fig.align_ylabels([ax, axn])
    first = weeks.index(x["first_app_week"])
    ax.text((first - 1) / 2, 0.28, "Before the factory:\nwork was in ai-hero/studio,\noutside the fleet", ha="center", va="center",
            fontsize=8.5, color=F.MUTED)
    n_app = [n - i for n, i in zip(x["n_week"], x["n_infra"])]
    axn.bar(xs, n_app, color=F.named("app"), width=0.8, label="app change sets")
    axn.bar(xs, x["n_infra"], bottom=n_app, color=F.named("infra change sets"), width=0.8, label="infra change sets")
    axn.add_artist(axn.legend(loc="upper left", fontsize=7.5, frameon=False))
    axn.set_ylabel("Change sets (n)")
    axn.grid(axis="x", visible=False)
    axn.legend(*ax.get_legend_handles_labels(), ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.55), fontsize=8.5)
    week_axis(axn, weeks)
    return F.save(fig, F.asset("2.1"))


def draw_repos_in_motion(x):
    """Repos active each week against the repos that existed, the two window means as reference lines, and the
    change sets each active repo shipped beneath."""
    weeks = x["weeks"]
    fig, (ax, axb) = F.fig(F.CHART_W, F.CHART_H, nrows=2, sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    xs = list(range(len(weeks)))
    ax.step(xs, x["eligible"], where="mid", color=F.GREY_DARK, linewidth=1.5, label="Repos in the fleet that week")
    ax.step(xs, x["active"], where="mid", color=F.PINK, linewidth=2, label="Repos with a change set merged")
    ax.fill_between(xs, x["active"], step="mid", color=F.PINK, alpha=0.12, linewidth=0)
    h1, l8 = x["h1"], x["last8"]
    ax.plot([0, 25], [h1["active_per_week"]] * 2, color=F.INK, linewidth=1, linestyle=(0, (3, 2)))
    ax.text(12.5, h1["active_per_week"] + 0.4, f"First half: {h1['active_per_week']} a week", ha="center", fontsize=9, color=F.INK)
    ax.plot([len(weeks) - 8, len(weeks) - 1], [l8["active_per_week"]] * 2, color=F.INK, linewidth=1, linestyle=(0, (3, 2)))
    ax.text(len(weeks) - 4.5, l8["active_per_week"] - 0.5, f"Last eight weeks: {l8['active_per_week']:.0f}", ha="center",
            va="top", fontsize=9, color=F.INK)
    pk_n, pk_w = x["peak"]
    ax.annotate(f"{pk_n} of {x['eligible'][weeks.index(pk_w)]}", (weeks.index(pk_w), pk_n), xytext=(-4, 6),
                textcoords="offset points", ha="right", fontsize=9, color=F.PINK_DARK)
    ax.set_ylim(0, max(x["eligible"]) + 3)
    ax.set_ylabel("Repos")
    ax.grid(axis="x", visible=False)
    milestones(ax, weeks, above=True)
    ax.legend(loc="upper left", fontsize=9)
    ys = [v if v is not None else float("nan") for v in x["per_active"]]
    axb.plot(xs, ys, color=F.GREY_DARK, linewidth=1.5, marker="o", markersize=3)
    for lo, hi, w in ((0, 25, h1), (len(weeks) - 8, len(weeks) - 1, l8)):
        axb.plot([lo, hi], [w["sets_per_active_repo"]] * 2, color=F.INK, linewidth=1, linestyle=(0, (3, 2)))
        axb.text((lo + hi) / 2, w["sets_per_active_repo"] + 2, f"{w['sets_per_active_repo']:.1f}", ha="center", fontsize=8.5, color=F.INK)
    axb.set_ylabel("Change sets per\nactive repo")
    axb.set_ylim(0, max(v for v in x["per_active"] if v is not None) + 8)
    axb.grid(axis="x", visible=False)
    week_axis(axb, weeks)
    return F.save(fig, F.asset("6.1"))
