"""Drawn figures for the owner deck's book cards (Figures 2.2 and 2.5), on report/figure_lib.py."""
import os
import sys
import textwrap
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
from deck_lib import MILESTONES, wlabel  # noqa: E402


def _wrap(s, n=34):
    return "\n".join(textwrap.wrap(s, n))


def draw_direction_vs_planning(x):
    """Five shares of one population as paired dots (first logged week against the last four), their Wilson
    intervals as whiskers; beneath, the three shares week by week with the unlogged span hatched."""
    fig, (ax, axt) = F.fig(F.CHART_W, F.CHART_H, nrows=2, gridspec_kw={"height_ratios": [2.6, 1.6]})
    ms = x["measures"]
    first, last = x["table"]["first"], x["table"]["last4"]
    n1, n2 = x["n"]["first"], x["n"]["last4"]
    w1 = x["logged_weeks"][0]
    lab1 = f"{wlabel(w1)}–{(date.fromisocalendar(2026, int(w1[6:]), 7)).strftime('%-d %b')} (first logged week, n={n1})"
    w4 = x["last4_weeks"]
    lab2 = f"{wlabel(w4[0])}–{(date.fromisocalendar(2026, int(w4[-1][6:]), 7)).strftime('%-d %b')} (last four weeks, n={n2})"
    ys = list(range(len(ms)))[::-1]
    for y, a, b in zip(ys, first, last):
        ax.plot([a["lo"], a["hi"]], [y + 0.12] * 2, color=F.GREY, linewidth=1.5, solid_capstyle="round", zorder=2)
        ax.plot([b["lo"], b["hi"]], [y - 0.12] * 2, color=F.PINK_LIGHT, linewidth=1.5, solid_capstyle="round", zorder=2)
        ax.plot([a["share"]], [y + 0.12], "o", color=F.GREY_DARK, markersize=7, zorder=3)
        ax.plot([b["share"]], [y - 0.12], "o", color=F.PINK, markersize=7, zorder=3)
        ax.annotate(f"{a['share']:.0%}", (a["share"], y + 0.12), xytext=(0, 7), textcoords="offset points", ha="center",
                    fontsize=8.5, color=F.GREY_DARK)
        ax.annotate(f"{b['share']:.0%}", (b["share"], y - 0.12), xytext=(0, -13), textcoords="offset points", ha="center",
                    fontsize=8.5, color=F.PINK_DARK)
    ax.plot([], [], "o", color=F.GREY_DARK, label=lab1)
    ax.plot([], [], "o", color=F.PINK, label=lab2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.2), ncol=1, fontsize=8.5)
    ax.set_yticks(ys)
    ax.set_yticklabels([_wrap(m) for m in ms], fontsize=8.5)
    ax.set_ylim(-0.7, len(ms) - 0.3)
    ax.set_xlim(0, 1.04)
    ax.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel(f"Share of the window's change sets (Dependabot excluded; whiskers: 95% Wilson interval)")
    ax.grid(axis="y", visible=False)

    weeks = x["weeks"]
    start = weeks.index("2026-W30")
    xs = list(range(start, len(weeks)))
    styles = {ms[0]: (F.PINK, "-"), ms[1]: (F.PINK_LIGHT, (0, (3, 2))), ms[2]: (F.GREY_DARK, "-")}
    for m, (col, ls) in styles.items():
        vals = [x["trend"][m][i] if x["trend"][m][i] is not None else float("nan") for i in xs]
        axt.plot(xs, vals, color=col, linewidth=1.8, linestyle=ls, marker="o", markersize=3.5,
                 label={ms[0]: "Decision identifiable", ms[1]: "Decision, unlogged one-shots as instructed", ms[2]: "Written intent"}[m])
    g0, g1 = weeks.index("2026-W33") - 0.5, weeks.index("2026-W34") + 0.5
    axt.axvspan(g0, g1, color=F.GREY_LIGHT, alpha=0.5, hatch="//", linewidth=0)
    axt.text((g0 + g1) / 2, 0.5, "Session logs:\none day (9 Aug),\nnone 10–24 Aug", ha="center", va="center", fontsize=7.5, color=F.MUTED)
    for day, name, *_ in MILESTONES:
        y, w, wd = date.fromisoformat(day).isocalendar()
        px = (w - 1) + (wd - 1) / 7
        if px >= start - 0.5:
            axt.axvline(px, color=F.GREY_DARK, linewidth=0.7, linestyle=(0, (1, 3)))
            axt.text(px + 0.1, 1.0, name, rotation=90, ha="left", va="top", fontsize=7, color=F.GREY_DARK,
                     transform=axt.get_xaxis_transform())
    axt.set_ylim(0, 1.02)
    axt.set_xlim(start - 0.5, len(weeks) - 0.5)
    axt.set_xticks(xs)
    axt.set_xticklabels([wlabel(weeks[i]) for i in xs], fontsize=8)
    axt.yaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    axt.set_ylabel("Share, by week")
    axt.set_xlabel("Week of 2026 (weeks with 10+ change sets)")
    axt.grid(axis="x", visible=False)
    axt.legend(loc="lower left", bbox_to_anchor=(0.0, 0.08), fontsize=7.5, ncol=1)
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
        txt = "white" if col in (F.PINK, F.GREY_DARK, F.PINK_DARK) else F.INK
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
    fig, (ax, axr) = F.fig(F.CHART_W, F.CHART_H, ncols=2, gridspec_kw={"width_ratios": [1.45, 1]})
    n = x["n"]
    I, D = x["identity_cats"], x["indep_cats"]
    id_cols = [F.PINK, F.PINK_LIGHT, F.PINK_DARK, F.GREY, F.GREY_LIGHT]
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
    for y, name in zip([3.3, 1.3], names):
        s = side[name]
        axr.text(0, y + 0.36, f"{name}: independence  (n={s['n']:,})", fontsize=9, color=F.INK, va="bottom")
        _layer_bar(axr, y, {c: s["counts"][c] for c in D}, in_cols, s["n"], width_chars=48)
    axr.set_xlim(0, 1)
    axr.set_ylim(0.2, 6.0)
    axr.set_yticks([])
    axr.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    axr.grid(axis="y", visible=False)
    axr.set_xlabel("Share of merged PRs, by kind of change")
    axr.spines["left"].set_visible(False)
    return F.save(fig, F.asset("2.5"))
