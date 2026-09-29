"""Drawn figures for the components deck's book cards (7.1 component coverage, 7.2 cost by planning depth)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import figure_lib as F  # noqa: E402

WINDOW_TEXT = "25 Aug to 25 Sep 2026"


def _usd(v):
    return f"\\${v:,.2f}"  # escaped: a bare pair of $ is mathtext to matplotlib


def fig_7_1(x):
    """Left: one bar per component on the same population, split into passed / did not / planned but unsaved /
    cannot tell. Right: how the four overlap on the change sets where all four are known."""
    import matplotlib.ticker as mt
    import numpy as np
    fig, (ax, bx) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1.35, 1]})
    rows = x["table"]
    n = x["n"]
    ys = list(range(len(rows)))[::-1]
    parts = [("through", "Passed through", F.PINK), ("not", "Did not pass through", F.GREY_DARK),
             ("planned", "Planned in the session, plan not saved", F.PINK_LIGHT), ("unknown", "Cannot tell: no PR, or no session names it", F.GREY_LIGHT)]
    left = np.zeros(len(rows))
    for key, name, col in parts:
        vals = np.array([r[key] / n for r in rows])
        ax.barh(ys, vals, left=left, color=col, edgecolor="white", linewidth=1.5, height=0.62, label=name)
        for y, v, l in zip(ys, vals, left):
            if v >= 0.07:
                ax.text(l + v / 2, y, f"{v:.0%}", ha="center", va="center", fontsize=9.5,
                        color="white" if col in (F.PINK, F.GREY_DARK) else F.INK)
        left = left + vals
    for y, r in zip(ys, rows):
        ax.text(1.01, y, f"{r['through']} of {n}\n95% CI {r['lo']:.0%} to {r['hi']:.0%}", ha="left", va="center", fontsize=8, color=F.MUTED)
    ax.set_yticks(ys)
    ax.set_yticklabels([r["component"] for r in rows])
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.set_major_formatter(mt.PercentFormatter(1.0))
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"Share of app change sets, {WINDOW_TEXT} (n={n})")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=8.5)
    ax.set_title("Coverage per component", loc="left", fontsize=10.5, color=F.BODY)

    combos = x["combos"][:7]
    short = {"Auto-approve judge": "judge", "Shared skill session": "skill", "Work item": "item", "Goal": "goal"}
    labels = [" + ".join(short.get(p, p) for p in c["combo"].split(" + ")) if c["combo"] != "None of the four" else "none" for c in combos]
    cy = list(range(len(combos)))[::-1]
    bx.barh(cy, [c["share_known"] for c in combos], color=[F.PINK if i == 0 else F.GREY for i in range(len(combos))], height=0.62)
    for y, c in zip(cy, combos):
        bx.text(c["share_known"] + 0.01, y, f"{c['share_known']:.0%}  (n={c['n']})", va="center", fontsize=8.5, color=F.BODY)
    bx.set_yticks(cy)
    bx.set_yticklabels(labels, fontsize=9)
    bx.set_xlim(0, max(c["share_known"] for c in combos) * 1.45)
    bx.xaxis.set_major_formatter(mt.PercentFormatter(1.0))
    bx.grid(axis="y", visible=False)
    bx.set_xlabel(f"Share where all four are known (n={x['n_known']})")
    bx.set_title("How the four overlap", loc="left", fontsize=10.5, color=F.BODY)
    png = F.save(fig, F.asset("7.1"))
    F.summary("7.1", question="On one shared population and window, what proportion of shipped change sets passed through each "
                              "factory component, which overlapped, and how much apparent non-use was missing linkage?",
              params={"window": list(x["window"]), "population": "change sets in app repos (category app or app, no features yet), "
                      "Dependabot excluded, dated by the day the PR merged",
                      "judge": "a github-actions review on the PR; cannot tell = no PR",
                      "skill": "a session log that ran a hero-skills: or wayfare: skill names the PR; cannot tell = no PR or no session names it",
                      "item": "Chapter 2's link (goal commit log, else an item recording the PR or branch); planned-unsaved = no item, "
                              "but a session naming the PR ran a planning or build skill",
                      "goal": "a goal-N branch or an item in a goal; planned-unsaved = no goal, but a session naming the PR ran start-goal or advance-item",
                      "interval": "Wilson 95% for the passed-through share of the whole population"},
              columns=["component", "through", "not", "planned", "unknown", "share", "lo", "hi", "share_known"],
              table=[{k: r[k] for k in ("component", "through", "not", "planned", "unknown", "share", "lo", "hi", "share_known")} for r in rows],
              notes=f"Change sets with no PR: {x['no_pr']}; with a PR no session names: {x['unnamed']}; with a PR and no review at all: "
                    f"{x['judge_only_no_review']}. Overlaps on the {x['n_known']} change sets where all four are known: {x['combos']}.",
              extra={"combos": x["combos"], "by_repo": {"repos": x["repos"], "n": x["repo_n"], "shares": x["by_repo"]}},
              sources=["detectors.cs_sets", "github.prs, github.pr_reviews", "harness.sessions.pr_links, harness.tool_calls.skill_name",
                       "plans.plan_items", "report/links.py set_item_links", "report/components/data.py set_paths"])
    return png


def fig_7_2(x):
    """Dot-and-whisker: median cost per change set by depth of saved plan, IQR and a bootstrap interval, n and coverage
    beside each row; the no-plan stratum split by whether a session shows planning that was not saved."""
    import matplotlib.ticker as mt
    rows = x["table"] + x["no_plan_split"]
    fig, ax = F.fig()
    ys = [4, 3, 2, 1, 0.35][: len(rows)]
    for y, r in zip(ys, rows):
        if not r.get("n"):
            continue
        sub = r["depth"].startswith("No saved plan:")
        ax.plot([r["q1"], r["q3"]], [y, y], color=F.GREY_LIGHT if sub else F.GREY, linewidth=5 if sub else 7, solid_capstyle="butt", zorder=2)
        ax.plot([r["median_lo"], r["median_hi"]], [y, y], color=F.PINK_DARK, linewidth=1.4, zorder=3)
        ax.plot([r["median"]], [y], "o", color=F.PINK_LIGHT if sub else F.PINK, markersize=7 if sub else 9, zorder=4)
        ax.annotate(_usd(r["median"]), (r["median"], y), xytext=(0, 10 if not sub else 8), textcoords="offset points",
                    ha="center", fontsize=10 if not sub else 9, color=F.INK)
    ax.set_yticks(ys)
    ax.set_yticklabels([(("    " if r["depth"].startswith("No saved plan:") else "") + r["depth"].replace("No saved plan: ", "") +
                         f"\n{'    ' if r['depth'].startswith('No saved plan:') else ''}n={r['n']} of {r['n_all']} ({r['coverage']:.0%} costed)")
                        for r in rows], fontsize=9.5)
    ax.set_ylim(-0.3, 4.7)
    ax.set_xscale("log")
    ax.set_xlim(1, 100)
    ax.xaxis.set_major_locator(mt.FixedLocator([1, 3, 10, 30, 100]))
    ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.xaxis.set_minor_locator(mt.NullLocator())
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Reported list-price-equivalent cost per change set (USD, log scale)")
    ax.plot([], [], color=F.GREY, linewidth=7, label="Interquartile range")
    ax.plot([], [], "o", color=F.PINK, label="Median")
    ax.plot([], [], color=F.PINK_DARK, linewidth=1.4, label="95% interval for the median (bootstrap)")
    ax.legend(loc="lower right", fontsize=9)
    adj = x["adjusted"]
    if adj:
        g, i = adj["adjusted"]["Inside a goal"], adj["adjusted"]["Work item only"]
        ax.text(0, -0.13, f"Change sets merged {WINDOW_TEXT}, apps and allied repos. Holding repository, work type, model family and "
                          f"size fixed (n={adj['n']}), goal work costs {g['ratio']:.2f}x no-plan work (95% CI {g['lo']:.2f} to {g['hi']:.2f}) "
                          f"and work-item-only work {i['ratio']:.2f}x ({i['lo']:.2f} to {i['hi']:.2f}): an association, not a cause.",
                transform=ax.transAxes, fontsize=8.5, color=F.MUTED, va="top", wrap=True)
    png = F.save(fig, F.asset("7.2"))
    F.summary("7.2", question="After adjusting for repository, task type, change size and model, how was planning depth associated "
                              "with cost per change set, with sample sizes, attribution coverage and uncertainty shown?",
              params={"window": list(x["window"]), "population": "change sets with a merged PR in app and allied repos, Dependabot excluded",
                      "price_basis": "harness cost_usd, an API list-price equivalent",
                      "attribution": "report/spend/attribution.py (turn-level; default-branch spend in a session that opened PRs is "
                                     "split over those PRs; a PR's cost is split over its change sets by lines + 20)",
                      "depth": "per change set: inside a goal (goal-N branch or member item) > work item only > no saved plan",
                      "adjusted": "OLS of log cost on depth with repository, work type (feature, fix, security, upkeep, design_ui), "
                                  "model family and log(lines + 1) held fixed; ratios are exp(coefficient) against no saved plan",
                      "sensitivity": "branch only = drop default-branch spend linked through the session's PR list; unreached spread = "
                                     "add the window's unmerged, PR-less and default-branch spend evenly over the change sets of the "
                                     "same repo and week"},
              columns=["depth", "n", "n_all", "coverage", "median", "q1", "q3", "median_lo", "median_hi", "mean"],
              table=rows,
              notes=f"Adjusted: {adj}. Median lines per change set by depth: {x['lines_median']}. Model families: {x['families']}. "
                    f"Work types: {x['worktypes']}.",
              extra={"sensitivity": x["sensitivity"], "strata": x["strata"]},
              sources=["harness.sessions, harness.turns, harness.subagent_runs", "github.prs", "detectors.cs_sets, detectors.cs_worktype",
                       "plans.plan_items", "report/components/data.py set_paths, book_sets, q_cost_by_depth_units"])
    return png
