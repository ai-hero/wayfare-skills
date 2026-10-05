"""Drawn figures for the compliance deck's book cards (5.2, 5.6, 5.7, 5.8): matplotlib through figure_lib, each
saved as a PNG for the answer slide with a summary table under .analysis/data/figures/."""
import os
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import figure_lib as F  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import data as D  # noqa: E402

SOURCES_AUDIT = ["hero-template and .fleet: every committed CONSISTENCY.md (report/compliance/register.py audits)",
                 "git.commits (first and last commit per repo)"]


def dd(day):
    return date.fromisoformat(day[:10]).strftime("%-d %b")


def clone_drift(x):
    rows = x["rows"]
    fig, ax = F.fig(F.CHART_W, F.CHART_H)
    labels = [f"{r['repo']}\ncloned {dd(r['cloned'])} · {r['age_days']} d old · n={r['applicable']}" for r in rows]
    ys = list(range(len(rows)))[::-1]
    for y, r in zip(ys, rows):
        ax.plot([r["pre_clone_rules"], r["failed"]], [y, y], color=F.GREY, linewidth=2.5, zorder=2, solid_capstyle="round")
        ax.plot([r["pre_clone_rules"]], [y], "o", color=F.GREY_DARK, markersize=8, zorder=3)
        ax.plot([r["failed"]], [y], "o", color=F.PINK, markersize=8, zorder=3)
        ax.annotate(f"{r['failed']}", (r["failed"], y), xytext=(9, -3), textcoords="offset points", fontsize=9.5, color=F.INK)
    ax.plot([], [], "o", color=F.GREY_DARK, label="Failures of checks that existed when the clone was made")
    ax.plot([], [], "o", color=F.PINK, label="All open failures (the gap is checks written after the clone)")
    ax.axvline(x["template_failed"], color=F.GREY_DARK, linewidth=1, linestyle=(0, (2, 3)))
    ax.text(x["template_failed"], len(rows) - 0.45, f"hero-template: {x['template_failed']}", color=F.GREY_DARK, fontsize=9,
            ha="center", va="bottom")
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xlim(-0.5, max(r["failed"] for r in rows) + 2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"Open failures at the {dd(x['audit_day'])} audit (n = checks that apply to the repo)")
    ax.text(0.99, 0.30, f"Accepted exceptions recorded: {x['exceptions_recorded']}\nClones inactive in the prior 30 days: {len(x['inactive'])}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color=F.MUTED)
    ax.legend(loc="lower right", fontsize=8.5)
    png = F.save(fig, F.asset("5.2"))
    F.summary("5.2", question="For files and controls expected to remain shared, how did clone drift vary with clone age and rule "
                              "vintage after accounting for accepted exceptions, inactive repositories and intentionally local differences?",
              params={"audit": x["audit_day"], "clones": {r["repo"]: r["cloned"] for r in rows}, "template_failed": x["template_failed"],
                      "template_failed_checks": x["template_failed_checks"], "exceptions_recorded": x["exceptions_recorded"],
                      "active_means": "at least one default-branch commit in the 30 days before the audit",
                      "rule_vintage": "a check existed at clone if it appears in an audit table on or before the clone's first commit",
                      "excluded": "cells marked n/a (intentionally local) or manual are outside the denominator"},
              columns=["repo", "cloned", "age_days", "category", "applicable", "not_applicable", "manual", "failed", "pre_clone_rules",
                       "post_clone_rules", "template_fails_too", "commits_30d", "active", "post_clone_checks", "pre_clone_checks"],
              table=[[r[k] for k in ("repo", "cloned", "age_days", "category", "applicable", "not_applicable", "manual", "failed",
                                     "pre_clone_rules", "post_clone_rules", "template_fails_too", "commits_30d", "active",
                                     "post_clone_checks", "pre_clone_checks")] for r in rows],
              notes=f"{x['total_failed']} open failures across six clones, {x['total_post']} of them checks written after the clone; the "
                    f"template fails {x['template_failed']}. The register records no exceptions and every clone was active, so no "
                    "failure is set aside as accepted or dormant.", sources=SOURCES_AUDIT)
    return png


def control_origins(x):
    combos = sorted(x["combos"].items(), key=lambda kv: -kv[1])
    order = ["bug", "audit", "design", "outside"]
    cls_color = {D.CLASSES[0]: F.PINK, D.CLASSES[1]: F.GREY_DARK, D.CLASSES[2]: F.GREY}
    fig = plt.figure(figsize=(F.CHART_W, F.CHART_H), constrained_layout=True)
    F.style()
    gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 3], height_ratios=[2.2, 1], wspace=0.02, hspace=0.02)
    ax_bar = fig.add_subplot(gs[0, 1])
    ax_mat = fig.add_subplot(gs[1, 1], sharex=ax_bar)
    ax_tot = fig.add_subplot(gs[1, 0], sharey=ax_mat)
    xs = list(range(len(combos)))
    for i, (combo, n) in enumerate(combos):
        col = cls_color[D.origin_class(list(combo))]
        ax_bar.bar(i, n, color=col, width=0.6)
        ax_bar.text(i, n + 0.3, str(n), ha="center", va="bottom", fontsize=10, color=F.INK)
    from matplotlib.patches import Patch
    ax_bar.legend(handles=[Patch(color=col, label=c) for c, col in cls_color.items()], loc="upper right", fontsize=9)
    fig.text(0.02, 0.92, f"{x['multi']} of {x['n']} controls carry two origins.\nOrigins read by hand from each control's\n"
                         f"why text; the model's single label sat\ninside the hand set for {x['agree_in_set']} of {x['n']}.",
             fontsize=9, color=F.BODY, va="top")
    ax_bar.set_ylabel(f"Controls (n = {x['n']})")
    ax_bar.set_ylim(0, max(n for _, n in combos) + 3)
    ax_bar.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_bar.grid(axis="x", visible=False)
    for j, o in enumerate(order):
        for i, (combo, n) in enumerate(combos):
            on = o in combo
            ax_mat.plot([i], [j], "o", color=F.INK if on else F.GREY_LIGHT, markersize=9, zorder=3)
        for i, (combo, n) in enumerate(combos):
            idx = [order.index(k) for k in combo]
            if len(idx) > 1:
                ax_mat.plot([i, i], [min(idx), max(idx)], color=F.INK, linewidth=1.5, zorder=2)
    ax_mat.set_yticks(range(len(order)))
    ax_mat.set_yticklabels([D.ORIGIN_NAMES[o] for o in order], fontsize=9)
    ax_mat.set_ylim(-0.6, len(order) - 0.4)
    ax_mat.invert_yaxis()
    ax_mat.grid(False)
    ax_mat.tick_params(axis="x", bottom=False, labelbottom=False)
    for s in ax_mat.spines.values():
        s.set_visible(False)
    tots = [x["origin_totals"][o] for o in order]
    ax_tot.barh(range(len(order)), tots, color=F.GREY, height=0.55)
    for j, t in enumerate(tots):
        ax_tot.text(t + 0.5, j, str(t), va="center", fontsize=9, color=F.INK)
    ax_tot.set_xlim(max(tots) + 6, 0)
    ax_tot.set_xlabel("Controls citing the origin", fontsize=9)
    ax_tot.tick_params(axis="y", left=False, labelleft=False)
    ax_tot.grid(axis="y", visible=False)
    for s in ("top", "right", "left"):
        ax_tot.spines[s].set_visible(False)
    png = F.save(fig, F.asset("5.6"))
    F.summary("5.6", question="What evidence produced each control, allowing more than one origin, which controls were preventive versus "
                              "post-incident and which later detected the problem they were created to stop?",
              params={"origins": D.ORIGIN_NAMES, "classes": D.CLASSES, "labelled_by": "hand, from each control's why text and introducing commit",
                      "haiku_primary_agreement": {"in_hand_set": x["agree_in_set"], "exact_single_origin": x["agree_exact"], "n": x["n"]},
                      "later_detected_means": "a (check, repo) failure first seen in an audit after the check's first audit"},
              columns=["id", "title", "severity", "first_day", "origins", "class", "haiku_primary", "caught_at_write", "later_detected"],
              table=[[r[k] for k in ("id", "title", "severity", "first_day", "origins", "class", "haiku_primary", "caught_at_write", "later_detected")]
                     for r in sorted(x["rows"], key=lambda r: r["id"])],
              notes=f"Origin totals {x['origin_totals']}; combinations {dict(x['combos'])}; {x['multi']} controls carry two origins. "
                    f"{x['later_any']} controls later caught a new failure ({x['later_by_class']}).",
              sources=["hero-template and .fleet CONTROLS.yaml history (report/compliance/register.py register_versions)",
                       "compliance.sqlite control_trigger (the Haiku labels the hand audit was checked against)", "the violation ledger (data.py ledger)"])
    return png


def audit_staleness(x):
    fig = plt.figure(figsize=(F.CHART_W, F.CHART_H), constrained_layout=True)
    F.style()
    gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.15])
    ax = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ts = [datetime.fromisoformat(d) for d, _ in x["daily"]]
    ax.step(ts, [s for _, s in x["daily"]], where="post", color=F.PINK, linewidth=2)
    ax.fill_between(ts, [s for _, s in x["daily"]], step="post", color=F.PINK, alpha=0.08)
    ymax = x["max_stale"] + 6
    for a in x["audits"]:
        t = datetime.fromisoformat(a["day"])
        ax.plot([t], [0], marker="^", color=F.PINK if a["full"] else F.GREY_DARK, markersize=8, zorder=4, clip_on=False)
    # Coverage reads as covered/alive per group of audit days, each label above its spike; the July ticks are too
    # dense to label one by one.
    A = x["audits"]
    for d0, d1, y, lab in [(A[0]["day"], A[8]["day"], 6, f"{A[0]['covered']} of {A[0]['alive']}–{A[8]['alive']} repos"),
                           (A[9]["day"], None, 26.6, f"{A[9]['covered']} of {A[9]['alive']}"),
                           (A[10]["day"], None, 15.6, f"{A[10]['covered']} of {A[10]['alive']}, one missing"),
                           (A[11]["day"], None, 9.6, f"{A[11]['covered']} of {A[11]['alive']}")]:
        t0, t1 = datetime.fromisoformat(d0), datetime.fromisoformat(d1 or d0)
        ax.text(t0 + (t1 - t0) / 2, y, lab, ha="center", va="bottom", fontsize=8, color=F.MUTED)
    for d in x["uncommitted_runs"]:
        ax.plot([datetime.fromisoformat(d)], [0], marker="^", markerfacecolor="white", markeredgecolor=F.GREY_DARK, markersize=8, zorder=4, clip_on=False)
    peak = datetime.fromisoformat(x["max_stale_day"])
    ax.annotate(f"{x['max_stale']:.0f} days old on {dd(x['max_stale_day'])}", (peak, x["max_stale"]), xytext=(-8, 6),
                textcoords="offset points", ha="right", fontsize=9.5, color=F.INK)
    ax.plot([], [], "^", color=F.PINK, label="Audit covering every family repo alive that day")
    ax.plot([], [], "^", color=F.GREY_DARK, label="Audit covering part of the fleet (covered/alive)")
    ax.plot([], [], "^", markerfacecolor="white", markeredgecolor=F.GREY_DARK, label="Audit skill run, results not committed")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_ylim(-1, ymax)
    ax.set_xlim(datetime.fromisoformat(x["daily"][0][0]), datetime.fromisoformat(x["end"]))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d %b"))
    ax.set_ylabel("Age of the latest committed fleet audit (days)")
    ax.set_xlabel(f"2026 · {x['n_days']} days from the first audit to {dd(x['end'])}")
    ax.grid(axis="x", visible=False)
    ax2.hist(x["waits"], bins=range(0, x["wait_max"] + 4, 3), color=F.GREY_DARK, edgecolor="white")
    ax2.axvline(x["wait_median"], color=F.PINK, linewidth=1.5)
    ax2.text(x["wait_median"] + 0.6, ax2.get_ylim()[1] * 0.95, f"median {x['wait_median']} d\np90 {x['wait_p90']} d", fontsize=9, va="top", color=F.INK)
    ax2.set_xlabel(f"Days until the next audit,\nfor each day (n = {len(x['waits'])})")
    ax2.set_ylabel("Days")
    ax2.grid(axis="x", visible=False)
    F.coverage(fig)
    png = F.save(fig, F.asset("5.7"))
    F.summary("5.7", question="How current was the fleet's conformance view on every day of the study, distinguishing full and partial audits, "
                              "and what was the distribution of time between a violation becoming detectable and the next applicable audit?",
              params={"end": x["end"], "audit": "a commit that changed CONSISTENCY.md (hero-template until 13 Sep, then .fleet); same-day commits count once",
                      "full": "covers every family repo alive that day (family = every repo an audit ever covered; hiro not alive after its 21 Aug deprecation)",
                      "wait": "for each calendar day from the first audit to the last, days until the next committed audit: the wait a violation appearing that day faced",
                      "uncommitted_runs": "harness.tool_calls skill runs of consistency-audit, audit-compliance or sync-plan on a day with no committed table (sessions logged from 9 Aug)"},
              columns=["day", "where", "covered", "alive", "missing", "extra", "full"],
              table=[[a[k] for k in ("day", "where", "covered", "alive", "missing", "extra", "full")] for a in x["audits"]],
              extra={"daily_age": x["daily"], "waits": x["waits"], "uncommitted_runs": x["uncommitted_runs"]},
              notes=f"{x['n_audit_days']} audit days, {x['n_full']} covering the whole alive family. Age peaked at {x['max_stale']} days on "
                    f"{x['max_stale_day']}; {x['days_over_7']} of {x['n_days']} days were more than a week stale; {x['stale_at_end']} days at the end. "
                    f"Wait to the next audit: median {x['wait_median']}, p90 {x['wait_p90']}, max {x['wait_max']} days.",
              sources=SOURCES_AUDIT + ["harness.tool_calls (skill runs)"])
    return png


OUTCOME_COLORS = [F.GREY_DARK, F.GREY, F.GREY_LIGHT, F.PINK_LIGHT, F.PINK, F.CONTRAST, "#F4F5F8"]


def violation_outcomes(x):
    fig = plt.figure(figsize=(F.CHART_W, F.CHART_H), constrained_layout=True)
    F.style()
    gs = fig.add_gridspec(1, 2, width_ratios=[2.6, 1])
    ax = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    cats = [f"All (n={x['n']})"] + [f"{s.capitalize()} (n={n})" for s, n in zip(D.SEVS, x["sev_n"])]
    parts = {}
    for f in D.FINAL:
        allv = x["totals"].get(f, 0) / x["n"]
        parts[f"{f} ({x['totals'].get(f, 0)})"] = [allv] + [c / n if n else 0 for c, n in zip(x["by_sev"][f], x["sev_n"])]
    F.stacked100(ax, cats, parts, colors=OUTCOME_COLORS, min_label=0.07)
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=8)
    ax.set_xlabel(f"Share of violations, state at the {dd(x['census'])} audit")
    ax2.hist(x["later_days"], bins=range(0, max(x["later_days"]) + 8, 7), color=F.GREY, edgecolor="white")
    ax2.axvline(x["later_median"], color=F.PINK, linewidth=1.5)
    ax2.text(x["later_median"] + 1.5, ax2.get_ylim()[1] * 0.95, f"median {x['later_median']:g} d", fontsize=9, va="top", color=F.INK)
    ax2.set_xlabel(f"Days to the later fix\n(n = {len(x['later_days'])}, weekly bins)")
    ax2.set_ylabel("Violations")
    ax2.grid(axis="x", visible=False)
    png = F.save(fig, F.asset("5.8"))
    cols = ["check", "repo", "control", "severity", "opened", "how", "closed", "reopened", "census_cell", "final", "repair_days"]
    F.summary("5.8", question="What happened to each conformance violation (fixed in the finding sweep, fixed later, accepted as an exception, reopened "
                              "or still unresolved) and how did outcome and repair time vary by severity and rule?",
              params={"census": x["census"], "unit": "one (check, repo) pair ever seen failing", "outcomes": D.FINAL,
                      "repair_days": "audit that first saw the violation to the first later audit where it passed (bounded by audit cadence)",
                      "exceptions": "the register carries no exception or waiver field, so none can be recorded"},
              columns=cols, table=[[r[k] for k in cols] for r in x["rows"]],
              extra={"by_severity": x["by_sev"], "by_control": x["by_control"], "later_by_severity": x["later_by_sev"]},
              notes=f"{x['n']} violations: {dict(x['totals'])}. {x['reopened_n']} were fixed and later seen failing again. "
                    f"Later repairs took a median {x['later_median']:g} days. {x['open_at_census']} cells fail at the census.",
              sources=SOURCES_AUDIT)
    return png
