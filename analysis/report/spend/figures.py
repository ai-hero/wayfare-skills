"""Drawn figures for the spend deck's book cards (6.5 cost per unit, 6.6 CI minutes), with their summaries.

Each `fig_*` takes what its data.py function returns, draws the PNG into .analysis/diagrams/book/, writes the
figure's summary table under .analysis/data/figures/ and returns the PNG path for `F.picture` on the answer slide.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import figure_lib as F  # noqa: E402
from record import SESSION_WINDOW_LABEL  # noqa: E402
from deck_lib import wlabel  # noqa: E402

WINDOW_TEXT = f"{SESSION_WINDOW_LABEL} 2026"


def _usd(v):
    return (f"\\${v:,.2f}" if v < 100 else f"\\${v:,.0f}")  # escaped: a bare pair of $ is mathtext to matplotlib


def fig_6_5(x):
    """Dot plot: median and IQR of reported list-price-equivalent cost per change set, PR, work item and goal."""
    import matplotlib.ticker as mt
    rows = x["table"]
    fig, ax = F.fig()
    ys = list(range(len(rows)))[::-1]
    for y, r in zip(ys, rows):
        ax.plot([r["q1"], r["q3"]], [y, y], color=F.GREY, linewidth=7, solid_capstyle="butt", zorder=2)
        ax.plot([r["median_lo"], r["median_hi"]], [y, y], color=F.PINK_DARK, linewidth=1.4, zorder=3)
        ax.plot([r["median"]], [y], "o", color=F.PINK, markersize=9, zorder=4)
        ax.annotate(_usd(r["median"]), (r["median"], y), xytext=(0, 11), textcoords="offset points", ha="center",
                    fontsize=10, color=F.INK)
        ax.annotate(f"IQR {_usd(r['q1'])} to {_usd(r['q3'])}", (r["q3"], y), xytext=(8, -3), textcoords="offset points",
                    ha="left", va="center", fontsize=8.5, color=F.MUTED)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{r['unit']}\nn={r['n_costed']} of {r['n_units']} ({r['coverage']:.0%} costed)" for r in rows])
    ax.set_ylim(-1.9, len(rows) - 0.3)  # the band under the last row holds the legend
    ax.set_xscale("log")
    ax.set_xlim(1, 400)
    ax.xaxis.set_major_locator(mt.FixedLocator([1, 3, 10, 30, 100, 300]))
    ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.xaxis.set_minor_locator(mt.NullLocator())
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Reported list-price-equivalent cost per unit (USD, log scale)")
    ax.plot([], [], color=F.GREY, linewidth=7, label="Interquartile range")
    ax.plot([], [], "o", color=F.PINK, label="Median")
    ax.plot([], [], color=F.PINK_DARK, linewidth=1.4, label="95% interval for the median (bootstrap)")
    ax.legend(loc="lower right")
    F.coverage(fig, f"Units merged or closed {WINDOW_TEXT}; costed = reached any attributed session spend. "
                    f"{x['unreached_share']:.0%} of the window's spend (\\${x['unreached_usd']:,}) reached no merged PR and is "
                    "reported, not spread over units.")
    png = F.save(fig, F.asset("6.5"))
    F.summary("6.5", question="What were the distributions and attribution coverage of list-price-equivalent cost per change set, "
                              "pull request, work item and goal, with failed, shared and unshipped work attributed consistently?",
              params={"window": list(x["window"]), "price_basis": "harness cost_usd: API list-price equivalent, not what was billed",
                      "attribution": "report/spend/attribution.py: session cost split over turns and subagent runs by token-priced "
                                     "weight, each piece to the merged PR of its branch (same-name branches merged in other repos "
                                     "within 7 days share it evenly); default-branch spend in a session that opened merged PRs is split "
                                     "evenly over those PRs; a PR's cost is split over its change sets by lines (+20)",
                      "unreached": "spend on unmerged branches, PR-less branches and default-branch sessions that opened no PR is "
                                   "reported as a share and never spread over units",
                      "work_item_population": "items with a change set merged in the window, plus items closed in the window that no "
                                              "change set links to (in any window)",
                      "goal_population": "goals with a member item's change set or a goal-N branch PR merged in the window"},
              columns=["unit", "n_costed", "n_units", "coverage", "median", "q1", "q3", "median_lo", "median_hi", "mean", "total"],
              table=rows,
              notes=f"Spend logged in the window: ${x['spend_total']:,}; by target: {x['spend_by_target']}. Unreached: "
                    f"${x['unreached_usd']:,} ({x['unreached_share']:.1%}): {x['unreached']}. Change sets with no PR: {x['sets_no_pr']}. "
                    f"Work items linked to a change set in the window: {x['items_linked']}; closed in the window with no linked change "
                    f"set ever: {x['items_never_linked']}.",
              sources=["harness.sessions, harness.turns, harness.subagent_runs", "github.prs", "detectors.cs_sets, detectors.cs_units",
                       "plans.plan_items (frontmatter ledgers)", "report/links.py set_item_links"])
    return png


def fig_6_6(x, weeks):
    """Left: Pareto of runs by wall-clock minutes (rank on a log axis). Right: weekly minutes, normal against hung, with
    the incident, the fix and the cut marked and the before/after-fix baselines drawn."""
    import matplotlib.ticker as mt
    fig, (ax, bx) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1, 1.25]})
    cum = x["cum"]
    ranks = list(range(1, len(cum) + 1))
    ax.plot(ranks, cum, color=F.GREY_DARK, linewidth=1.8)
    k = x["hung_n"]
    ax.plot([k], [cum[k - 1]], "o", color=F.PINK, markersize=9, zorder=4)
    ax.fill_between(ranks[:k], 0, cum[:k], color=F.PINK, alpha=0.15, step="pre")
    # Three short lines below and right of the point: on two lines it ran into the next panel, and above
    # and to the left it ran into the axis.
    ax.annotate(f"{k} hung runs\n= {cum[k - 1]:.0%} of all\nminutes", (k, cum[k - 1]), xytext=(12, -40), ha="left",
                textcoords="offset points", fontsize=9.5, color=F.INK,
                arrowprops=dict(arrowstyle="-", color=F.MUTED, linewidth=0.8))
    ax.set_xscale("log")
    ax.set_xlim(1, len(cum) * 1.1)
    ax.set_ylim(0, 1.02)
    ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_major_formatter(mt.PercentFormatter(1.0))
    ax.set_xlabel(f"Runs ranked by wall-clock minutes (n={len(cum):,}, log scale)")
    ax.set_ylabel("Cumulative share of wall-clock CI minutes")
    ax.set_title("Pareto of runs", loc="left", fontsize=10.5, color=F.BODY)

    wk = x["weekly"]
    weeks = [w for w in weeks if w >= "2026-W27"]  # January to June total 456 minutes: invisible on this axis, stated in notes
    labels = [wlabel(w) for w in weeks]
    idx = range(len(weeks))
    bx.bar(idx, [wk[w]["normal"] for w in weeks], color=F.GREY_DARK, width=0.7, label="Normal runs")
    bx.bar(idx, [wk[w]["hung"] for w in weeks], bottom=[wk[w]["normal"] for w in weeks], color=F.PINK, width=0.7,
           label="Hung runs (26 Aug)")
    bx.set_yscale("symlog", linthresh=5000, linscale=1.2)
    bx.set_ylim(0, 150000)
    bx.yaxis.set_major_locator(mt.FixedLocator([0, 2000, 4000, 10000, 30000, 100000]))
    bx.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    bx.set_xticks(list(idx))
    bx.set_xticklabels(labels, rotation=60, ha="right", fontsize=8.5)
    bx.set_xlabel("Week of 2026, from July (Jan to Jun: under 500 in all)")
    bx.set_ylabel("Wall-clock CI minutes per week (symlog above 5,000)")
    for name, key, col, va in (("before hang", "before", F.GREY_DARK, "top"), ("after fix", "after_fix", F.CONTRAST, "bottom")):
        v = x[key]["per_week"]
        bx.axhline(v, color=col, linewidth=1, linestyle=(0, (3, 3)))
        bx.text(-0.4, v, f"{name}: {v:,} a week", ha="left", va=va, fontsize=8.5, color=col,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    hung_i = weeks.index("2026-W35")
    # To the right of the hung bar, above the ordinary weeks: to its left the note ran over the axis.
    bx.annotate(f"26 Aug: {k} runs hang\n{x['hung_hours'][0]}-{x['hung_hours'][1]} h, cancelled\n28 Aug",
                (hung_i, 40000), xytext=(10, 0), textcoords="offset points", va="center",
                fontsize=9, color=F.INK, arrowprops=dict(arrowstyle="-", color=F.MUTED, linewidth=0.8))
    for day, txt, dx in ((x["fix_day"], "fix 29 Aug", -3), (x["cut_day"], "cut 17 Sep", 3)):
        y, w, wd = date.fromisoformat(day).isocalendar()
        i = weeks.index(f"{y}-W{w:02d}") + (wd - 1) / 7 - 0.5
        bx.axvline(i, color=F.PINK_DARK, linewidth=0.8, linestyle=(0, (2, 3)))
        bx.annotate(txt, (i, 12000), xytext=(dx, 0), textcoords="offset points", rotation=90,
                    ha="right" if dx < 0 else "left", va="center", fontsize=8, color=F.PINK_DARK)
    bx.legend(loc="upper left", fontsize=9)
    bx.set_title("Minutes per week", loc="left", fontsize=10.5, color=F.BODY)
    png = F.save(fig, F.asset("6.6"))
    F.summary("6.6", question="How much CI consumption came from normal runs versus hung runs, in billable and wall-clock minutes, "
                              "what caused the outliers and what baseline remained after the fix?",
              params={"window": ["2026-01-01", "2026-10-01"], "wall_clock": "github.ci_runs.duration_s (created to updated)",
                      "billable": "not in the data: ci_jobs.billable_ms is 0 on every row; billable_lb_min = per-run minutes rounded up, "
                                  "a lower bound on GitHub's per-job whole-minute billing",
                      "hung": "created 26 Aug, ran over 6 h, ended cancelled (no other 2026 run exceeded 1 h)",
                      "fix_day": x["fix_day"], "cut_day": x["cut_day"]},
              columns=["group", "runs", "wall_min", "billable_lb_min", "share_wall"], table=x["table"],
              notes=f"Hung runs by workflow: {x['hung_workflow_groups']}; cancelled {x['hung_cancelled'][0]} to {x['hung_cancelled'][1]} UTC. "
                    f"Baselines (normal runs, wall-clock minutes per week): before {x['before']}; after fix {x['after_fix']}; "
                    f"after cut {x['after_cut']}. Monthly: {x['months']}. Runs over an hour outside the hang day: {x['long_other']}.",
              extra={"weekly": x["weekly"]},
              sources=["github.ci_runs", "github.ci_jobs (billable_ms all zero)", "wayfare-skills history: db701b7 (29 Aug), 17 Sep CI cut"])
    return png


def fig_4_7(x):
    """Left: weekly CI minutes against weekly change sets, July to September, with the fit. Right: minutes per change set
    by month, with what drove it (repos running CI, build minutes per run)."""
    fig, (ax, bx) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1.35, 1]})
    colors = {"07": F.GREY, "08": F.GREY_DARK, "09": F.PINK}
    for w, cs, m in zip(x["weeks"], x["change_sets"], x["ci_min"]):
        mon = date.fromisocalendar(int(w[:4]), int(w[-2:]), 1).strftime("%m")  # the label is the Monday
        ax.plot([cs], [m], "o", color=colors[mon], markersize=8, zorder=3)
        # The rightmost point's label goes on its left, or it runs into the next panel.
        right = cs == max(x["change_sets"])
        ax.annotate(wlabel(w), (cs, m), xytext=(-5 if right else 5, 4), textcoords="offset points", fontsize=8,
                    color=F.MUTED, ha="right" if right else "left")
    lo, hi = min(x["change_sets"]), max(x["change_sets"])
    ax.plot([lo, hi], [x["intercept"] + x["slope"] * lo, x["intercept"] + x["slope"] * hi], color=F.GREY_DARK, linewidth=1.2)
    # Headroom above the points: at print width the note would otherwise sit on the top-left points.
    ax.set_ylim(top=ax.get_ylim()[1] * 1.22)
    ax.text(0.02, 0.98, f"r = {x['r_sets']:.2f} (rank {x['rho_sets']:.2f}), n = {len(x['weeks'])} weeks\n"
                        f"about {x['slope']:.0f} more minutes a week\nper added change set",
            transform=ax.transAxes, ha="left", va="top", fontsize=8, color=F.MUTED)
    for mon, name in (("07", "July"), ("08", "August"), ("09", "September")):
        ax.plot([], [], "o", color=colors[mon], label=name)
    ax.legend(loc="lower right")
    ax.set_xlabel("Change sets merged in the week")
    ax.set_ylabel("Wall-clock CI minutes in the week")
    ax.set_title("Each week, Jul to Sep", loc="left", fontsize=10.5, color=F.BODY)

    ms = x["months"]
    idx = range(len(ms))
    bx.bar(idx, [m["min_per_set"] for m in ms], color=[F.GREY, F.GREY_DARK, F.PINK], width=0.6)
    for i, m in zip(idx, ms):
        bx.annotate(f"{m['min_per_set']:.1f}", (i, m["min_per_set"]), xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=10, color=F.INK)
    bx.set_xticks(list(idx))
    bx.set_xticklabels([f"{n}\n{m['change_sets']:,} sets\n{m['ci_min']:,} min\n{m['repos_with_ci']} repos\n"
                        f"{m['build_min_per_run']:.1f} min a build"
                        for n, m in zip(("Jul", "Aug", "Sep"), ms)], fontsize=8.5)
    bx.set_ylabel("CI minutes per change set")
    bx.grid(axis="x", visible=False)
    bx.set_title("Per change set, by month", loc="left", fontsize=10.5, color=F.BODY)
    png = F.save(fig, F.asset("4.7"))
    F.summary("4.7", question="Do GitHub Actions minutes rise with the number of change sets the factory ships, and does the "
                              "cost of one change set stay flat as volume grows?",
              params={"weeks": [x["weeks"][0], x["weeks"][-1]], "measure": "wall-clock minutes (github.ci_runs.duration_s); "
                      "billed minutes are not in the data", "excluded": "the 26 Aug hung runs; W40 (partial, ends 1 Oct)",
                      "change_sets": "every change set including Dependabot's, since its CI minutes count"},
              columns=["month", "change_sets", "prs", "ci_min", "min_per_set", "repos_with_ci", "build_min_per_run",
                       "deploy_min_per_run", "by_group"], table=ms,
              notes=f"Weekly r with change sets {x['r_sets']}, with merged PRs {x['r_prs']}; fit {x['intercept']} + "
                    f"{x['slope']} x change sets. July to September: change sets x{x['sets_growth']}, CI minutes x{x['min_growth']}.",
              extra={"weekly": dict(zip(x["weeks"], zip(x["change_sets"], x["prs"], x["ci_min"])))},
              sources=["github.ci_runs", "github.prs", "detectors.cs_sets, detectors.cs_units"])
    return png
