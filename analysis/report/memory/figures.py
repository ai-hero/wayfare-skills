"""Drawn figure for the memory deck's book card 3.3 (startup and on-demand text per repo), on figure_lib."""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402


def fmt_day(d):
    return date.fromisoformat(d).strftime("%-d %b")


def standardisation(x):
    rows = sorted(x["rows"], key=lambda r: r["start_before"])
    labels = [r["repo"] + ("" if r["category"] in ("app", "app, no features yet") else " (allied)") for r in rows]
    names = (fmt_day(x["before"]), fmt_day(x["day"]))
    fig, (a, b) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1.15, 1]})
    F.dumbbell(a, labels, [r["start_before"] for r in rows], [r["start_after"] for r in rows], names=names,
               xlabel="KB loaded at session start")
    F.dumbbell(b, labels, [r["own_demand_before"] for r in rows], [r["own_demand_after"] for r in rows], names=names,
               xlabel="KB the repo holds for loading on demand")
    b.set_yticklabels([])
    ys = list(range(len(rows)))[::-1]
    for ax, key in ((a, "start_now"), (b, "own_demand_now")):
        ax.plot([r[key] for r in rows], ys, "o", markerfacecolor="white", markeredgecolor=F.PINK_DARK, markeredgewidth=1.4,
                markersize=6, zorder=4, label=fmt_day(x["now"]))
        ax.legend(loc="lower right", fontsize=8.5)
    m = x["medians"]
    a.set_title(f"Median app repo {m['start_before']['apps']:.0f} → {m['start_after']['apps']:.0f} KB "
                f"(now {m['start_now']['apps']:.0f})", loc="left", fontsize=10)
    b.set_title(f"Median app repo {m['own_demand_before']['apps']:.0f} → {m['own_demand_after']['apps']:.0f} KB "
                f"(now {m['own_demand_now']['apps']:.0f}), repo's own", loc="left", fontsize=10)
    return F.save(fig, F.asset("3.3"))
