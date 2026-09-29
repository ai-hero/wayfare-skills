"""Drawn figures for the security deck's book cards (5.3, 5.4): matplotlib through figure_lib, each saved as a PNG
for the answer slide and a summary table beside it."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import data as D  # noqa: E402

XMAX = 150  # days; the one flaw beyond it is named on the chart rather than stretching the axis for a single point


def flaw_lifetimes(x):
    fig = plt.figure(figsize=(F.CHART_W, F.CHART_H), constrained_layout=True)
    F.style()
    gs = fig.add_gridspec(1, 2, width_ratios=[2.4, 1])
    ax = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    cols = [F.PINK, F.GREY_DARK, F.GREY]
    for g, col in zip(D.AUTHOR_GROUPS, cols):
        v = x["groups"][g]
        F.ecdf(ax, v, label=f"{g} (n={len(v)}, median {x['median'][g]:g} d)", color=col, xmax=XMAX)
    beyond = [r for r in x["rows"] if r["days"] > XMAX]
    if beyond:
        ax.text(XMAX - 2, 0.13, f"{len(beyond)} beyond {XMAX} d: " + ", ".join(f"{r['days']} d ({r['group'].split()[-1]})" for r in beyond),
                ha="right", fontsize=8.5, color=F.MUTED)
    ax.axvline(30, color=F.GREY_DARK, linewidth=0.8, linestyle=(0, (2, 3)))
    ax.text(31, 0.02, f"{x['over30']} of {x['n_traced']} past 30 d", fontsize=8.5, color=F.MUTED)
    ax.set_xlabel(f"Days from introducing commit to merged fix (n = {x['n_traced']}, all fixed by 24 Sep)")
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.42), fontsize=8.5)
    ax.set_title("Time on main before the fix", fontsize=11, loc="left", color=F.BODY)
    import numpy as np
    names = x["expo_names"]
    ecols = [F.PINK, F.GREY_LIGHT, F.GREY]
    short = ["agent, this repo", "inherited", "a person"]
    bottom = np.zeros(len(D.AUTHOR_GROUPS))
    for e, col in zip(names, ecols):
        vals = np.array([x["exposure"][g][e] for g in D.AUTHOR_GROUPS], dtype=float)
        ax2.bar(short, vals, bottom=bottom, color=col, edgecolor="white", linewidth=1.5, label=e)
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v >= 3:
                ax2.text(i, b + v / 2, f"{int(v)}", ha="center", va="center", fontsize=8.5, color="white" if col == F.PINK else F.INK)
        bottom += vals
    ax2.set_ylabel("Traceable flaws")
    ax2.set_title("Exposure while on main", fontsize=11, loc="left", color=F.BODY)
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=7.5, ncol=1)
    ax2.tick_params(axis="x", labelsize=8.5)
    ax2.grid(axis="x", visible=False)
    png = F.save(fig, F.asset("5.3"))
    cols_ = ["repo", "pr", "fix_day", "label", "kind", "intro_day", "intro_pr", "group", "agent", "inherited", "days", "shipped",
             "ci_tracked", "detected", "finder", "intro_to_detect", "detect_to_fix"]
    F.summary("5.3", question="For traceable security flaws, how long elapsed from introduction to detection and from detection to fix, with "
                              "correct censoring, and how did those intervals vary by author type, severity and known production exposure?",
              params={"population": "security change sets (not dependency CVEs) merged through a PR whose fix rewrote or removed lines; "
                                    "git blame at the fix's parent names the commit owning most of those lines",
                      "censoring": "none possible from this side: a flaw is only visible once fixed, so every interval is complete and the "
                                   "curve is conditional on a fix by 24 Sep 2026; flaws still on main are not in the population",
                      "groups": D.AUTHOR_GROUPS, "severity": "not recorded for change sets; none shown",
                      "exposure": "a successful deploy or main-branch build between the introducing and fixing merges (github.ci_runs, from July)",
                      "detection": "creation date of the work item linked to the fix PR, where one is linked", "xmax": XMAX},
              columns=cols_, table=[[r.get(k) for k in cols_] for r in x["rows"]],
              notes=f"{x['n_traced']} of {x['n_fixes']} fixes traceable ({x['untraceable']} only add lines). Medians {x['median']}; {x['shipped']} "
                    f"deployed before the fix; {x['over30']} past 30 days; max {x['max_days']}. {x['linked']} fixes link to a work item: "
                    f"intro-to-detect {x['intro_to_detect']}, detect-to-fix {x['detect_to_fix']}.",
              sources=["git blame on the default-branch mirrors", "detectors.cs_sets + cs_worktype (security change sets)",
                       "github.ci_runs (deploys)", "plans.plan_items (detection dates where linked)"])
    return png


def item_closure(x, flaws):
    fig, ax = F.fig()
    n = F.ecdf(ax, x["days"], label=f"Security work items, filing to close (n={x['n_done']} closed; {x['n_open']} open, censored at {x['end'][-2:]} Sep)",
               color=F.PINK, censored=x["open_ages"], xmax=XMAX)
    fl = [r["days"] for r in flaws["rows"]]
    F.ecdf(ax, fl, label=f"Traceable flaws, introduction to fix, from 5.3 (n={len(fl)})", color=F.GREY_DARK, xmax=XMAX)
    ax.annotate(f"{x['same_day']} of {x['n_done']} closed the same day ({x['same_day'] / x['n_done']:.0%})", (0.3, x["same_day"] / n),
                xytext=(78, 0.5), textcoords="data", fontsize=9.5, color=F.INK, arrowprops=dict(arrowstyle="-", color=F.MUTED, linewidth=0.8))
    ax.annotate(f"{x['within_3']} within 3 days ({x['within_3'] / x['n_done']:.0%})", (3.3, x["within_3"] / n), xytext=(78, 0.58),
                textcoords="data", fontsize=9, color=F.BODY, arrowprops=dict(arrowstyle="-", color=F.MUTED, linewidth=0.8))
    beyond = sum(1 for d in fl if d > XMAX)
    if beyond:
        ax.text(XMAX - 2, 0.42, f"{beyond} flaw beyond {XMAX} d", ha="right", fontsize=8.5, color=F.MUTED)
    ax.set_xlabel(f"Days (items dropped as superseded: {x['n_dropped']}, kept out; duplicates marked in the store: {x['duplicates_marked']})")
    ax.legend(loc="lower right", fontsize=8.5)
    png = F.save(fig, F.asset("5.4"))
    cols = ["repo", "item", "status", "finder", "created", "closed", "days", "title"]
    F.summary("5.4", question="How quickly did recorded security items reach merge, how does that compare with flaw introduction-to-fix time and "
                              "which items remained open, duplicate, superseded or censored?",
              params={"population": "work items the Haiku label marks as security or of type security (report/security/label.py)",
                      "closed": "status done, delivered, committed or accepted, dated by done_ts else updated_ts",
                      "censoring": f"open items carry their age at {x['end']} and are drawn as a rug at the curve's top",
                      "dropped": "status dropped (superseded), listed but not on the curve", "comparison": "figure 5.3's introduction-to-fix days",
                      "xmax": XMAX},
              columns=cols, table=[[r.get(k) for k in cols] for r in x["done"]] + [[r["repo"], r["item"], r["status"], r["finder"], r["created"],
                                                                                    None, None, r["title"]] for r in x["open"] + x["dropped"]],
              extra={"open_ages": x["open_ages"], "open_by_status": dict(x["open_by_status"]), "dropped": x["dropped"]},
              notes=f"{x['n']} items from {x['first']}: {x['n_done']} closed (median {x['median']:g} d, p90 {x['p90']} d, max {x['max']} d; "
                    f"{x['same_day']} same day), {x['n_open']} open (ages {x['open_ages'][0]}–{x['open_ages'][-1]} d), {x['n_dropped']} dropped. "
                    f"{x['accepted']} closed as accepted. The store has no duplicate marker; Dependabot PRs closed as superseded are PRs, not items.",
              sources=["plans.plan_items", "security.item_sec (Haiku security label, finder)", ".analysis/data/figures/5.3.json"])
    return png
