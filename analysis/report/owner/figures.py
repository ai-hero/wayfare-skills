"""Drawn figures for the owner deck's book cards (Figures 2.2 and 2.5), on report/figure_lib.py."""
import os
import sys
import textwrap
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
from deck_lib import MILESTONES  # noqa: E402
from record import SESSION_WINDOW_LABEL  # noqa: E402


def _wrap(s, n=34):
    return "\n".join(textwrap.wrap(s, n))


def draw_direction_vs_planning(x):
    """One point: most change sets trace to an owner decision, far fewer to a plan written down, fewer still to one
    written before the work began. Three bars over the logged window."""
    fig, ax = F.fig(F.CHART_W, 2.9)
    since, n = x["table"]["since"], x["n"]["since"]
    bars = [("Traced to a decision of mine", since[0]["share"], F.OWNER),
            ("Had a work item", since[2]["share"], F.GREY_DARK),
            ("Had one written before the work began", since[3]["share"], F.GREY)]
    ys = list(range(len(bars)))[::-1]
    for y, (label, v, col) in zip(ys, bars):
        ax.barh(y, v, color=col, height=0.6)
        ax.text(v + 0.015, y, f"{v:.0%}", va="center", fontsize=13, color=F.INK, fontweight="bold")
    ax.set_yticks(ys)
    ax.set_yticklabels([b[0] for b in bars], fontsize=10.5)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel(f"Share of the {n:,} change sets merged {SESSION_WINDOW_LABEL} (complete session logs)")
    ax.grid(axis="y", visible=False)
    F.coverage(fig)
    return F.save(fig, F.asset("2.2"))


SHORT = {"Reviewed": "Reviewed", "No review": "No review", "The owner (a person)": "The owner",
         "Unclear: owner-account reply, no agent command near it": "Unclear (owner account)",
         "An agent on the owner's account": "Agent on the owner's account", "Bots only (auto-approve, Copilot)": "Bots only",
         "Independent human review (a person other than the author)": "Independent human review",
         "Possibly a person (unclear owner-account replies)": "Possibly a person",
         "A person wrote it; automated review only": "A person wrote it, automated review",
         "Agent-built; automated review only": "Agent-built, automated review"}


def _layer_bar(ax, y, parts, colors, n, width_chars=70, named=0.3):
    """One 100% bar: parts {name: count}. A segment at least `named` wide carries its name; the rest are listed
    beneath the bar with their counts, so nothing under 1% is invisible."""
    left = 0.0
    small = []
    for (name, k), col in zip(parts.items(), colors):
        v = k / n
        ax.barh(y, v, left=left, height=0.5, color=col, edgecolor="white", linewidth=1)
        txt = "white" if col in (F.PINK, F.GREY_DARK, F.PINK_DARK, F.OWNER) else F.INK
        if v >= named:
            ax.text(left + v / 2, y, f"{SHORT.get(name, name)}\n{v:.0%}", ha="center", va="center", fontsize=8, color=txt)
        elif v >= 0.08:
            ax.text(left + v / 2, y, f"{v:.0%}", ha="center", va="center", fontsize=8, color=txt)
        if v < named:
            small.append(f"{SHORT.get(name, name)}: {k:,} ({v:.1%})")
        left += v
    if small:
        ax.text(0, y - 0.36, "\n".join(textwrap.wrap("  ·  ".join(small), width_chars)), ha="left", va="top", fontsize=7.3,
                color=F.MUTED, linespacing=1.15)


def draw_review_layers(x):
    """Left: one 100% bar per layer (coverage, reviewer identity, independence) for every merged PR. Right: the
    independence layer for one-way-door PRs against the rest."""
    # Stacked, not side by side: at print width two panels abreast leave each too narrow for its labels.
    fig, (ax, axr) = F.fig(F.CHART_W, 11.5, nrows=2, gridspec_kw={"height_ratios": [1.45, 1.35]})
    n = x["n"]
    I, D = x["identity_cats"], x["indep_cats"]
    id_cols = [F.OWNER, F.PINK_LIGHT, F.PINK, F.GREY, F.GREY_LIGHT]
    in_cols = [F.PINK, F.PINK_LIGHT, F.GREY_DARK, F.GREY, F.GREY_LIGHT]
    rows = [("Coverage: was there any review?", x["coverage"], [F.GREY, F.GREY_LIGHT]),
            ("Reviewer identity: who posted the reviews?", {c: x["identity"][c] for c in I}, id_cols),
            ("Independence: did someone other than the builder look?", {c: x["independence"][c] for c in D}, in_cols)]
    ys = [5.3, 3.3, 1.3]
    for y, (name, parts, cols) in zip(ys, rows):
        ax.text(0, y + 0.36, f"{name}  (n={n:,})", fontsize=9, color=F.INK, va="bottom")
        _layer_bar(ax, y, parts, cols, n)
    ax.set_xlim(0, 1)
    ax.set_ylim(0.2, 6.0)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Share of merged PRs (Dependabot excluded)")
    ax.spines["left"].set_visible(False)

    side = x["side"]
    names = list(side)
    a, b = side[names[0]], side[names[1]]
    axr.text(0, 5.66, "\n".join(textwrap.wrap(
        f"Independent human review: {a['counts'][D[0]]} of {a['n']:,} one-way-door PRs ({a['shares'][D[0]]:.1%}, "
        f"95% interval {a['human_lo']:.1%}–{a['human_hi']:.1%}) against {b['counts'][D[0]]} of {b['n']:,} other PRs "
        f"({b['shares'][D[0]]:.1%}, {b['human_lo']:.1%}–{b['human_hi']:.1%}).", 46)), fontsize=8, color=F.INK, va="top",
        linespacing=1.2)
    # Each bar's notes run three or four lines at print width; the spacing leaves them room above the
    # next bar's title and above the axis.
    for y, name in zip([3.5, 1.4], names):
        s = side[name]
        axr.text(0, y + 0.36, f"{name}: independence  (n={s['n']:,})", fontsize=9, color=F.INK, va="bottom")
        _layer_bar(axr, y, {c: s["counts"][c] for c in D}, in_cols, s["n"], width_chars=48)
    axr.set_xlim(0, 1)
    axr.set_ylim(-0.5, 6.0)
    axr.set_yticks([])
    axr.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    axr.grid(axis="y", visible=False)
    axr.set_xlabel("Share of merged PRs, by kind of change")
    axr.spines["left"].set_visible(False)
    return F.save(fig, F.asset("2.5"))
