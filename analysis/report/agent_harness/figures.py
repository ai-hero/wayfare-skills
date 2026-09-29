"""Drawn figures for the harness deck's book cards (3.1, 3.2, 3.8), on figure_lib; each returns a PNG path."""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402


def fmt_day(d):
    return date.fromisoformat(d).strftime("%-d %b")


def fixes_by_model(x):
    rows = x["models"] + [x["unnamed"]]
    fig, ax = F.fig()
    F.dot_whisker(ax, [r["label"] for r in rows], [r["rate"] for r in rows], [r["lo"] for r in rows],
                  [r["hi"] for r in rows], n=[r["n"] for r in rows], fmt="{:.1%}", ref=x["overall"]["rate"],
                  ref_label=f"all {x['overall']['n']} PRs: {x['overall']['rate']:.1%}",
                  xlabel=f"Share of merged PRs with an attributable fix within {x['window_days']} days (95% Wilson interval)")
    # The unnamed-trailer row is an inferred category, drawn in grey so it reads as context, not a model.
    ax.plot([x["unnamed"]["rate"]], [0], "o", color=F.GREY_DARK, markersize=8, zorder=4)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, max(r["hi"] for r in rows) * 1.1)
    return F.save(fig, F.asset("3.1"))


def fixes_by_repo_and_type(x):
    fig, (a, b) = F.fig(ncols=2)
    for ax, rows, what in ((a, x["by_repo"], "repository"), (b, x["by_type"], "change type")):
        F.dot_whisker(ax, [r["label"] for r in rows], [r["rate"] for r in rows], [r["lo"] for r in rows],
                      [r["hi"] for r in rows], n=[r["n"] for r in rows], fmt="{:.1%}", ref=x["overall"]["rate"],
                      ref_label=f"all PRs {x['overall']['rate']:.1%}", xlabel=f"Fixed within 14 days, by {what}")
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlim(0, max(r["hi"] for r in rows) * 1.12)
    return F.save(fig, F.asset("3.1", "by-repo-and-type"))


def delegation(x):
    fb, fa = x["fleet"]["before"], x["fleet"]["after"]
    fig, (a, b) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1, 1.25]})
    for r in x["per_repo"]:
        a.plot([0, 1], [r["before"], r["after"]], color=F.GREY, linewidth=1.5, marker="o", markersize=4, zorder=2)
    # Spread the repo labels so neighbours do not overprint; the marks stay where the data put them.
    labels = sorted([(r["after"], f"{r['repo']} ({r['n_before']}/{r['n_after']})", F.MUTED, 8) for r in x["per_repo"]]
                    + [(fa["per_session"], f"fleet {fa['per_session']:.2f}", F.PINK_DARK, 9.5)])
    y_prev = -1
    for y0, text, col, size in labels:
        y = max(y0, y_prev + 0.06)
        a.annotate(text, (1, y0), xytext=(1.08, y), textcoords="data", fontsize=size, color=col, va="center",
                   arrowprops={"arrowstyle": "-", "color": F.GREY_LIGHT, "linewidth": 0.6, "shrinkA": 0, "shrinkB": 2})
        y_prev = y
    a.plot([0, 1], [fb["per_session"], fa["per_session"]], color=F.PINK, linewidth=2.5, marker="o", markersize=8, zorder=5)
    a.annotate(f"fleet {fb['per_session']:.2f}", (0, fb["per_session"]), xytext=(-8, 0), textcoords="offset points",
               ha="right", va="center", fontsize=9.5, color=F.PINK_DARK)
    a.set_xticks([0, 1])
    a.set_xticklabels([f"Before the rule\n25–28 Aug\nn={fb['sessions']} sessions",
                       f"From the rule\n29 Aug–{fmt_day(x['log_end'])}\nn={fa['sessions']} sessions"])
    a.set_xlim(-0.45, 2.1)
    a.set_ylim(-0.02, max(0.9, max(r["after"] for r in x["per_repo"]) + 0.1))
    a.set_ylabel("Explore runs per interactive session")
    a.grid(axis="x", visible=False)
    a.set_title("Explore runs per session (n before/after)", loc="left", fontsize=10)
    for g, col, name in (("before", F.GREY_DARK, "Before"), ("after", F.PINK, "From the rule")):
        ks = x["turn_k"][g]
        q = x["fleet"][g]["turn_q"]
        F.ecdf(b, ks, label=f"{name} (n={len(ks):,} turns; median {q['p50'] // 1000}K, p90 {q['p90'] // 1000}K)",
               color=col, xmax=1000)
    b.set_xlabel("Context per main-thread turn (K tokens)")
    b.legend(loc="lower right", fontsize=8.5)
    b.set_title("Main-thread context per turn", loc="left", fontsize=10)
    return F.save(fig, F.asset("3.2"))


def uptake_lags(x):
    groups = [("MODEL RELEASES", x["models"]),
              ("CLAUDE CODE MODEL DEFAULTS", [f for f in x["features"] if f["group"] == "Claude Code model default"]),
              ("WORKFLOW FEATURES", [f for f in x["features"] if f["group"] == "Workflow feature"])]
    fig, ax = F.fig(h=F.CHART_H + 0.6)
    labels, y = [], 0
    ys = {}
    for name, items in groups:
        labels.append(name)
        y -= 1
        for it in items:
            labels.append(it["label"])
            y -= 1
            ys[id(it)] = y
        y -= 0.4
    xmax = max([it["lag"] or 0 for _, items in groups for it in items] + [it.get("waiting", 0) for _, items in groups for it in items]) * 1.12
    for name, items in groups:
        col = F.PINK if name.startswith("MODEL") else F.PINK_LIGHT if name.startswith("CLAUDE") else F.GREY_DARK
        for it in items:
            yy = ys[id(it)]
            if it["lag"] is None:
                ax.plot([it["waiting"]], [yy], "x", color=F.GREY, markersize=8, markeredgewidth=2)
                ax.annotate(f"not used yet ({it['waiting']} days since release)", (it["waiting"], yy), xytext=(8, 0),
                            textcoords="offset points", va="center", fontsize=8.5, color=F.MUTED)
                continue
            if it["bound"]:
                ax.plot([0, it["lag"]], [yy, yy], color=F.GREY_LIGHT, linewidth=4, solid_capstyle="butt", zorder=1)
                ax.plot([it["lag"]], [yy], "o", markerfacecolor="white", markeredgecolor=col, markeredgewidth=2, markersize=8, zorder=3)
                txt = f"≤ {it['lag']} d"
            else:
                ax.plot([it["lag"]], [yy], "o", color=col, markersize=8, zorder=3)
                txt = f"{it['lag']} d"
            if it.get("dropped"):
                txt += f"; dropped {fmt_day(it['dropped'][0])}"
            ax.annotate(txt, (it["lag"], yy), xytext=(8, 0), textcoords="offset points", va="center", fontsize=8.5)
        if items and name != "CLAUDE CODE MODEL DEFAULTS":
            med = x["median_model"] if name.startswith("MODEL") else x["median_work"]
            top, bot = ys[id(items[0])] + 0.5, ys[id(items[-1])] - 0.5
            ax.plot([med, med], [bot, top], color=col, linewidth=1, linestyle=(0, (2, 3)))
            ax.text(med + 2, bot + 0.1, f"median {med:.0f} d", color=col, fontsize=8.5, ha="left", va="bottom")
    ticks = []
    yy = 0
    for l in labels:
        yy -= 1
        if l.isupper() and ticks:
            yy -= 0.4
        ticks.append(yy)
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels)
    for t, l in zip(ax.get_yticklabels(), labels):
        if l.isupper():
            t.set_color(F.MUTED)
            t.set_fontsize(8)
    ax.set_ylim(min(ticks) - 0.7, 0)
    ax.set_xlim(0, xmax)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Days from public release to the fleet's first dated use (hollow: a bound, first seen the day its record begins)")
    return F.save(fig, F.asset("3.8"))
