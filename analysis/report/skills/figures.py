"""Drawn figure for the skills deck's book card 5.5: the rename incident as a lane timeline, one lane per consumer."""
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

PLUGIN_EVENTS = [("2026-09-22T00:07:48", "wayfare-skills #108 merged\n(the rename)"),
                 ("2026-09-22T03:08:58", "wayfare-skills #115\n(caller asset fixed)")]


def rename_timeline(x):
    fig, ax = F.fig(F.CHART_W, F.CHART_H + 0.45)
    lanes = sorted(x["lanes"], key=lambda l: (l["recovered"] or "", l["repo"]))
    names = [l["repo"] for l in lanes]
    ys = list(range(len(names)))[::-1]
    T = datetime.fromisoformat
    for y, l in zip(ys, lanes):
        if l["first_fail"] and l["recovered"]:
            ax.barh(y, mdates.date2num(T(l["recovered"])) - mdates.date2num(T(l["first_fail"])), left=mdates.date2num(T(l["first_fail"])),
                    height=0.6, color=F.PINK_LIGHT, alpha=0.35, edgecolor="none")
        for r in l["runs"]:
            t = T(r["ts"])
            if r["conclusion"] == "failure":
                ax.plot([t], [y], "|", color=F.PINK, markersize=13, markeredgewidth=1.8, zorder=4)
            elif r["conclusion"] == "success":
                ax.plot([t], [y], "o", color=F.GREY_DARK, markersize=4, zorder=3)
        if "caller re-pointed" in l:
            ax.plot([T(l["caller re-pointed"]["merged"])], [y], "D", color=F.INK, markersize=6, zorder=5)
        if "caller re-vendored" in l:
            ax.plot([T(l["caller re-vendored"]["merged"])], [y], "D", markerfacecolor="white", markeredgecolor=F.INK, markersize=6, zorder=5)
    for ts, lab in PLUGIN_EVENTS:
        ax.axvline(T(ts), color=F.GREY_DARK, linewidth=0.9, linestyle=(0, (2, 3)))
        ax.text(T(ts), len(names) - 0.35, lab, fontsize=7.5, color=F.GREY_DARK, ha="center", va="bottom")
    ax.plot([], [], "|", color=F.PINK, markersize=12, markeredgewidth=1.8, label="Auto-approve run failed at startup")
    ax.plot([], [], "o", color=F.GREY_DARK, markersize=4, label="Auto-approve run succeeded")
    ax.plot([], [], "D", color=F.INK, markersize=6, label="Caller re-pointed at wayfare-skills (PR merged)")
    ax.plot([], [], "D", markerfacecolor="white", markeredgecolor=F.INK, markersize=6, label="Caller re-vendored (PR merged)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=8, ncol=2)
    ax.set_yticks(ys)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_ylim(-0.7, len(names) + 0.9)
    ax.set_xlim(T(x["t0"]), T(x["t1"]))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel(f"UTC, 21–22 Sep 2026 · {x['n_consumers']} consumer repos, all calling the shared workflow at @main before the rename")
    ax.grid(axis="y", visible=False)
    png = F.save(fig, F.asset("5.5"))
    cols = ["repo", "state_before", "last_ok_before", "failed_runs", "startup_failures", "first_fail", "last_fail", "recovered",
            "caller re-pointed", "caller re-vendored"]
    F.summary("5.5", question="What reach did the shared workflow have immediately before the rename, what exact downstream breakage followed, how "
                              "quickly was it detected and repaired and which canary would have exposed it before fleet-wide use?",
              params={"window": [x["t0"], x["t1"]], "runs": "github.ci_runs whose workflow name contains 'approve', consumers only",
                      "startup_failure": "a failed run recorded under the workflow's file path with no jobs: the workflow could not be resolved",
                      "reach": "each consumer's auto-approve workflow on its default branch in the week before (Q plugin-uptake-and-rename)",
                      "repairs": list(x.get("repair_titles", {"caller re-pointed": "chore: hero-skills is wayfare, and the caller points at the renamed repo",
                                                              "caller re-vendored": "ci(auto-approve): re-vendor the caller"}).values())},
              columns=cols, table=[[l.get(k) for k in cols] for l in lanes],
              extra={"runs": {l["repo"]: l["runs"] for l in lanes}},
              notes=f"{x['at_main_before']} of {x['n_consumers']} consumers at @main. First failure {x['first_fail']}; all {x['n_broken']} failed within "
                    f"{x['spread_s']} s; {x['failed_runs']} failed runs in all. {x['repointed_within_60']} callers re-pointed within 60 min "
                    f"(13th at {x['minutes_to_13th_repoint']} min); last failure at {x['minutes_to_last_fail']} min; last caller re-pointed at "
                    f"{x['minutes_to_last_repoint']} min; last recovery {x['recovered_last']}. Failures after the re-point: {x['repos_failing_after_repoint']}.",
              sources=["github.ci_runs", "github.prs", "each consumer's default-branch history (mirrors)"])
    return png
