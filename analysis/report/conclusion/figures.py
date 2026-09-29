"""The conclusion deck's book figures (9.1 to 9.4): answer views drawn from data.py's fig_* results, and the summary
table each leaves in .analysis/data/figures/<id>.json.

Each `fig_*` returns the fields deck.answers() puts in A[q] (title, points, chart, source, notes, breakdowns), so
deck.py only wires them in. All four are drawn with figure_lib and placed as pictures: two panels, jittered
observations, a hatched gap and a pair of composition bars are not native chart forms.
"""
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import matplotlib.pyplot as plt  # noqa: E402
from pptx.enum.chart import XL_CHART_TYPE  # noqa: E402

import deck_lib as L  # noqa: E402
import figure_lib as F  # noqa: E402
from deck_lib import GREY, GREY_DARK, PINK, PINK_LIGHT, pct  # noqa: E402
import data as D  # noqa: E402
from data import AUTH_94, SOURCES_94, STATE_NAMES  # noqa: E402

CODE = "analysis/report/conclusion/data.py"
SHORT = {"No skills yet": "None yet", "Skills": "Skills", "+ work items": "+ work items", "+ goals": "+ goals", "+ messages": "+ messages"}


def wk(w):
    return L.wlabel(w)


def week_axis(ax, weeks, every=8):
    ax.set_xticks(range(0, len(weeks), every))
    ax.set_xticklabels([wk(w) for w in weeks[::every]])
    ax.set_xlim(-0.7, len(weeks) - 0.3)


# ------------------------------------------------------------------ 9.1 · Q quality-vs-throughput

def fig_9_1(x):
    p = x["primary"]
    weeks = x["weeks"]
    ci = f"95% CI {p['r_lo']:+.2f} to {p['r_hi']:+.2f}"

    def chart(s, box):
        F.style()
        fig = plt.figure(figsize=(F.CHART_W, F.CHART_H), constrained_layout=True)
        gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1])
        a1, a2, a3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[:, 1])
        a1.bar(range(len(weeks)), p["throughput"], color=F.GREY_DARK, width=0.75)
        a1.set_ylabel("Change sets merged / week")
        a1.set_title("Output", loc="left", fontsize=10.5, color=F.BODY)
        week_axis(a1, weeks)
        a1.tick_params(labelbottom=False)
        ys = [v if v is not None else float("nan") for v in p["rework"]]
        a2.plot(range(len(weeks)), ys, "-o", color=F.PINK, markersize=4, linewidth=1.6)
        a2.set_ylabel("Rework / 100 change sets")
        a2.set_title("Short-term rework (weeks with 5+ change sets)", loc="left", fontsize=10.5, color=F.BODY)
        a2.set_xlabel("Week of 2026")
        week_axis(a2, weeks)
        xs, ys2 = [q[0] for q in p["pairs"]], [q[1] for q in p["pairs"]]
        F.scatter(a3, xs, ys2, xlabel="Change sets merged that week", ylabel="Rework / 100 change sets, same week")
        a3.text(0.98, 0.89, ci, transform=a3.transAxes, ha="right", va="top", fontsize=9, color=F.MUTED)
        a3.set_title("Week by week", loc="left", fontsize=10.5, color=F.BODY)
        png = F.save(fig, F.asset("9.1"))
        F.picture(s, box, png)

    variants = x["variants"]
    F.summary("9.1", question="Across comparable repository-weeks, what relationship existed between completed change sets "
                              "and short-term rework under several repair windows and lags, and how sensitive was it to "
                              "repository mix and work type?",
              params={"unit": "fleet-week (ISO week, all in-scope repos), weeks with 5 or more change sets",
                      "output": "non-Dependabot change sets by the week their PR merged",
                      "rework": "PRs repaired by a later fix change set within the window (Chapter 10's SZZ trace, "
                                "mistakes.szz, dated by the PR's merge unless the variant says otherwise) plus gate catches "
                                "(CHANGES_REQUESTED reviews and CI 'caught'), per 100 change sets",
                      "correlation": "Pearson r across weeks with a 2,000-draw bootstrap interval; Spearman rho beside it",
                      "halves": "W01–W26 vs W27–W39"},
              columns=["variant", "r", "r_lo", "r_hi", "rho", "n_weeks", "rework_h1", "rework_h2", "sets_h1", "sets_h2", "rework_events"],
              table=[[n, v["r"], v["r_lo"], v["r_hi"], v["rho"], v["n_weeks"], v["h1"], v["h2"], v["sets_h"][0], v["sets_h"][1], v["events"]]
                     for n, v in variants],
              notes=f"Primary weekly series: throughput {p['throughput']}; rework per 100 {p['rework']}; rework events {p['rework_n']}. "
                    f"{x['fixes_7d']} PRs fixed forward within 7 days, {x['gate_events']} gate catches, {x['n_sets']} change sets.",
              sources=["detectors.cs_sets", "mistakes.szz", "detectors.gate_firings", "detectors.cs_worktype", "github.prs"])
    nogate = variants[3][1]
    apps = variants[5][1]
    return dict(
        q="Across comparable weeks, how did completed change sets relate to short-term rework, under several repair "
          "windows and lags, and was that sensitive to the repository mix and the kind of work?",
        how="Weekly change sets and rework per 100 change sets (PRs fixed within 7 days plus gate catches), as two "
            "time-series panels and a week-by-week scatter with Pearson r and its bootstrap interval; then the same r "
            "under 14- and 30-day windows, fix-dated rework, no gate catches, apps only and product change sets only.",
        title=(f"Output grew {x['grow']:.1f}× between the halves of the year and rework rose from {p['h1']} to {p['h2']} per "
               f"100 change sets, but week to week the two did not move together: r = {p['r']:+.2f} ({ci}, n = {p['n_weeks']} weeks)"),
        points=[f"Windows of 14 and 30 days give r = {variants[1][1]['r']:+.2f} and {variants[2][1]['r']:+.2f}; dating rework by the fix "
                f"gives {variants[4][1]['r']:+.2f}; apps only {apps['r']:+.2f}; product change sets only {variants[6][1]['r']:+.2f}.",
                f"Fix-forwards alone, without gate catches, do rise with volume: r = {nogate['r']:+.2f} ({nogate['r_lo']:+.2f} to "
                f"{nogate['r_hi']:+.2f}), on {nogate['events']} events.",
                f"{x['fixes_7d']} PRs fixed within 7 days and {x['gate_events']} gate catches over {x['n_sets']:,} change sets; defects nobody caught are not visible."],
        source="change sets · Chapter 10 fix-forwards (SZZ) · review and CI gates · work-type labels",
        chart=chart,
        notes=["Figure 9.1. Top left: change sets merged per week. Bottom left: rework per 100 change sets, weeks with at "
               "least 5 change sets. Right: the same weeks as points, with a least-squares line, Pearson r and a "
               "2,000-draw bootstrap 95% interval; Spearman rho for the primary series is "
               f"{p['rho']:+.2f}. No dual axis: the two series share a week, not a scale.",
               "Sensitivity (r, interval, n weeks): " + "; ".join(
                   f"{n}: {v['r']:+.2f} ({v['r_lo']:+.2f} to {v['r_hi']:+.2f}), n {v['n_weeks']}, halves {v['h1']} → {v['h2']}"
                   for n, v in variants) + ".",
               "Reading: the combined rework measure is dominated by gate catches, which scale with reviews rather than "
               "with defects; fix-forwards alone (rare, 114 events) do rise with volume, so 'quality held' is a claim about "
               "the combined measure and its two halves, not about every rework definition. Coincided with, never caused.",
               "Chapter 10 owns rework; this figure sets it beside throughput. Work-type labels: detectors.cs_worktype "
               f"({x['typed']:,} of {x['n_sets']:,} change sets labelled).",
               f"Code: {CODE}:q_quality_vs_throughput_variants · szz_fixes"],
        breakdowns=[dict(
            tag="Sensitivity",
            title=(f"The correlation stays near zero under every window and mix except fix-forwards alone "
                   f"(r {nogate['r']:+.2f}); rework per 100 rises between the halves under every variant"),
            points=["Each dot is Pearson r across weeks with 5+ change sets; the bar is its bootstrap 95% interval.",
                    "Intervals are wide: 21 to 26 weeks each."],
            chart=lambda s, b: _r_chart(s, b, variants),
            note="Variants defined in the notes of the answer slide. Code: " + CODE + ":q_quality_vs_throughput_variants")])


def _r_chart(s, box, variants):
    fig, ax = F.fig(8.35, 5.4)
    labels = [n.replace(" (primary)", "") for n, _ in variants]
    F.dot_whisker(ax, labels, [v["r"] for _, v in variants], [v["r_lo"] for _, v in variants], [v["r_hi"] for _, v in variants],
                  n=[v["n_weeks"] for _, v in variants], fmt="{:+.2f}", ref=0, xlabel="Pearson r, weekly change sets vs rework per 100 (n = weeks)")
    ax.set_xlim(-0.6, 0.9)
    png = F.save(fig, F.asset("9.1", "sensitivity"))
    F.picture(s, box, png)


# ------------------------------------------------------------------ 9.2 · Q stage-comparison

def fig_9_2(x):
    st = x["stages"]

    def chart(s, box):
        import random
        rnd = random.Random(3)
        fig, (a1, a2) = F.fig(F.CHART_W, F.CHART_H, ncols=2, gridspec_kw={"width_ratios": [1.3, 1]})
        for i, r in enumerate(st):
            xs = [i + rnd.uniform(-0.22, 0.22) for _ in r["values"]]
            a1.plot(xs, r["values"], "o", color=F.GREY, markersize=3.5, alpha=0.55, zorder=2)
            if r["mean_lo"] is not None:
                a1.plot([i, i], [r["mean_lo"], r["mean_hi"]], color=F.PINK_DARK, linewidth=2.2, zorder=3)
            a1.plot([i], [r["mean"]], "o", color=F.PINK, markersize=9, zorder=4)
            a1.annotate(f"{r['mean']:.1f}", (i, r["mean"]), xytext=(9, 0), textcoords="offset points", va="center", fontsize=9.5, color=F.INK)
            if r["rework100"] is not None:
                a2.plot([i, i], [r["rework_lo"], r["rework_hi"]], color=F.GREY, linewidth=2.2, zorder=2)
                a2.plot([i], [r["rework100"]], "o", color=F.PINK, markersize=9, zorder=3)
                a2.annotate(f"{r['rework100']:.1f}", (i, r["rework100"]), xytext=(9, 0), textcoords="offset points", va="center", fontsize=9.5, color=F.INK)
        ticks = [f"{SHORT[r['stage']]}\nn = {r['n_weeks']}" for r in st]
        for ax in (a1, a2):
            ax.set_xticks(range(len(st)))
            ax.set_xticklabels(ticks, fontsize=8.5)
            ax.set_xlim(-0.6, len(st) - 0.4)
            ax.grid(axis="x", visible=False)
        a1.set_ylabel("Change sets per repo-week")
        a1.set_title("Output: repo-weeks (grey), mean and 95% CI (pink)", loc="left", fontsize=10, color=F.BODY)
        a1.set_yscale("symlog", linthresh=10)
        a1.set_yticks([0, 5, 10, 20, 50, 100, 200])
        a1.set_yticklabels(["0", "5", "10", "20", "50", "100", "200"])
        a2.set_ylabel("Rework per 100 change sets")
        a2.set_title("Rework, with 95% Wilson interval", loc="left", fontsize=10, color=F.BODY)
        a2.set_ylim(0, max(r["rework_hi"] or 0 for r in st) * 1.15)
        fig.supxlabel("Stage the repo had reached that week (n = repo-weeks; repos per stage: "
                      + ", ".join(str(r["n_repos"]) for r in st) + ")", fontsize=10, color=F.BODY)
        png = F.save(fig, F.asset("9.2"))
        F.picture(s, box, png)

    ev = x["event"]
    F.summary("9.2", question="Within repositories, how did throughput and rework change around adoption of skills, work "
                              "items, goals and messaging, with event-time observations, sample sizes and concurrent "
                              "calendar changes exposed?",
              params={"unit": "repo-week inside the repo's active span (first to last commit), all in-scope repos",
                      "stage": "record.stage_of on the week's Thursday", "output": "non-Dependabot change sets merged that week",
                      "interval": "2,000-draw bootstrap of the mean over repo-weeks; Wilson interval on rework events / change sets",
                      "rework": "PRs fixed forward within 7 days (SZZ) plus gate catches, at the stage the repo had on that day",
                      "event_time": "change sets per week at offsets -4..+4 weeks around each repo's first work item and first goal"},
              columns=["stage", "repo_weeks", "repos", "mean", "mean_lo", "mean_hi", "median", "mean_apps_only", "app_weeks",
                       "change_sets", "rework_events", "rework_per_100", "rework_lo", "rework_hi", "first_week", "last_week"],
              table=[[r["stage"], r["n_weeks"], r["n_repos"], r["mean"], r["mean_lo"], r["mean_hi"], r["median"], r["mean_apps"],
                      r["n_app_weeks"], r["sets"], r["rework_events"], r["rework100"], r["rework_lo"], r["rework_hi"], r["from"], r["to"]]
                     for r in st],
              notes="Observational: stages arrived while the fleet, the models and Claude Code all changed; calendar spans "
                    "overlap (see first_week/last_week). Event time: " + "; ".join(
                        f"{k}: offsets {v['offsets']}, mean {v['mean']}, n {v['n']}" for k, v in ev.items()) + ".",
              sources=["detectors.cs_sets", "git.commits", "plans.plan_items", "mistakes.szz", "detectors.gate_firings"],
              extra={"event": ev})
    g = lambda name: next(r for r in st if r["stage"] == name)
    sk, wi, gl, ms = g("Skills"), g("+ work items"), g("+ goals"), g("+ messages")
    wi_ev = ev["work items"]
    before = statistics.mean(v for v in wi_ev["mean"][:4] if v is not None)
    after = statistics.mean(v for v in wi_ev["mean"][4:] if v is not None)
    return dict(
        q="Within repos, how did output per repo-week and rework move as repos took on skills, work items, goals and "
          "messages, with the repo-weeks, the intervals and the overlapping calendar shown?",
        how="Every in-scope repo-week is a grey dot at the stage its repo had reached; the pink dot is the stage mean "
            "with a bootstrap 95% interval, beside rework per 100 change sets with a Wilson interval; then output per "
            "week at -4..+4 weeks around each repo's first work item and first goal.",
        title=(f"Output per repo-week coincided with each stage: {sk['mean']:.1f} with skills ({sk['n_weeks']} repo-weeks), "
               f"{wi['mean']:.1f} with work items ({wi['n_weeks']}), {ms['mean']:.1f} in the {ms['n_weeks']}-repo-week mailbox period; "
               f"rework per 100 was {sk['rework100']}, {wi['rework100']} and {ms['rework100']}, intervals overlapping"),
        points=[f"Intervals: skills {sk['mean_lo']:.1f}–{sk['mean_hi']:.1f}, work items {wi['mean_lo']:.1f}–{wi['mean_hi']:.1f}, "
                f"goals {gl['mean']:.1f} ({gl['mean_lo']:.1f}–{gl['mean_hi']:.1f}, {gl['n_weeks']} repo-weeks, rework {gl['rework100']:.1f} per 100), "
                f"messages {ms['mean_lo']:.1f}–{ms['mean_hi']:.1f}.",
                f"Within repos, output in the 4 weeks after the first work item averaged {after:.1f} a week against {before:.1f} in "
                f"the 4 before ({wi_ev['repos']} repos, fewer at each edge).",
                f"Observational, not causal: the later stages sit in Aug–Sep alongside model releases and the busiest repos; "
                f"apps-only means are {sk['mean_apps']:.1f}, {wi['mean_apps']:.1f}, {ms['mean_apps']:.1f}."],
        source="change sets · HERO.md history · .plans · Chapter 10 fix-forwards · gates",
        chart=chart,
        notes=["Figure 9.2. Left: every repo-week (a repo between its first and last commit, by ISO week) as a grey dot at "
               "the stage the repo had reached on that week's Thursday; y is symlog above 10 so the many zero and "
               "single-digit weeks stay visible beside the 200-plus weeks. Pink: the mean with a 2,000-draw bootstrap 95% "
               "interval. Right: rework events (PRs fixed forward within 7 days, gate catches) per 100 change sets at "
               "that stage, with a Wilson 95% interval; stages under 20 change sets are not rated.",
               "Calendar overlap: " + "; ".join(f"{r['stage']} {wk(r['from'])}–{wk(r['to'])}, {r['n_repos']} repos" for r in st) +
               ". Stages are not periods: a repo-week at 'Skills' in September sits beside one at '+ messages'.",
               "Event time (mean change sets per week, n repos): work items " +
               ", ".join(f"{o:+d}: {m} ({n})" for o, m, n in zip(wi_ev["offsets"], wi_ev["mean"], wi_ev["n"])) + "; goals " +
               ", ".join(f"{o:+d}: {m} ({n})" for o, m, n in zip(ev["goals"]["offsets"], ev["goals"]["mean"], ev["goals"]["n"])) + ".",
               "Spend and owner minutes per change set (the earlier scorecard) are kept as the 'Scorecard' view; they exist "
               "only from 25 Aug. Chapter 21 compares the stages with model and Claude Code releases.",
               f"Code: {CODE}:q_stage_comparison_dots · repo_weeks"],
        breakdowns=[dict(
            tag="Event time",
            title=(f"Around the first work item, output rose from {before:.1f} to {after:.1f} change sets a week within the same repos; "
                   f"around the first goal, from {statistics.mean(v for v in ev['goals']['mean'][:4] if v is not None):.1f} to "
                   f"{statistics.mean(v for v in ev['goals']['mean'][4:] if v is not None):.1f}, on {ev['goals']['repos']} repos"),
            points=["Week 0 is the week the repo's first work item (or goal) was created.",
                    "n repos falls at the edges: recent adopters have no +4 week yet."],
            chart=lambda s, b: L.chart(s, XL_CHART_TYPE.LINE_MARKERS,
                                       [f"{o:+d} ({n}/{m})" for o, n, m in zip(wi_ev["offsets"], wi_ev["n"], ev["goals"]["n"])],
                                       {"First work item": wi_ev["mean"], "First goal": ev["goals"]["mean"]}, [PINK, GREY_DARK], box=b,
                                       x_title="Weeks from adoption (n repos: work items / goals)", y_title="Mean change sets per repo-week"),
            note="Mean over repos active at that offset, up to the latest logged week. Code: " + CODE + ":q_stage_comparison_dots")])


# ------------------------------------------------------------------ 9.3 · Q binding-constraint

def fig_9_3(x):
    weeks, ser = x["weeks"], x["series"]
    order = [STATE_NAMES["working"], STATE_NAMES["waiting_human"], STATE_NAMES["limited"], STATE_NAMES["away"]]
    colors = {STATE_NAMES["working"]: F.GREY_LIGHT, STATE_NAMES["waiting_human"]: F.PINK, STATE_NAMES["limited"]: F.PINK_DARK,
              STATE_NAMES["away"]: F.GREY}

    def chart(s, box):
        fig, ax = F.fig(F.CHART_W, F.CHART_H)
        bottom = [0.0] * len(weeks)
        for name in order:
            vals = [v or 0 for v in ser[name]]
            ax.bar(range(len(weeks)), vals, bottom=bottom, color=colors[name], width=0.7, label=name, edgecolor="white", linewidth=0.8)
            bottom = [b + v for b, v in zip(bottom, vals)]
        top = max(bottom) * 1.12
        ax.set_ylim(0, top)
        for i, w in enumerate(weeks):
            if w in x["missing"]:
                ax.axvspan(i - 0.5, i + 0.5, color=F.GREY_LIGHT, alpha=0.5, hatch="//", linewidth=0)
        if x["missing"]:
            i0, i1 = weeks.index(x["missing"][0]), weeks.index(x["missing"][-1])
            ax.text((i0 + i1) / 2, top * 0.5, "Session data\nnot available", ha="center", va="center", fontsize=9, color=F.MUTED)
        pk = weeks.index(x["peak_week"])
        ax.annotate(f"usage limits {x['peak_limited']:.0f} h", (pk, bottom[pk]), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=9, color=F.PINK_DARK)
        for i in (len(weeks) - 2, len(weeks) - 1):
            ax.annotate(f"owner {ser[STATE_NAMES['waiting_human']][i]:.0f} h\nlimits {ser[STATE_NAMES['limited']][i]:.0f} h",
                        (i, bottom[i]), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8.5, color=F.INK)
        ax.set_xticks(range(len(weeks)))
        ax.set_xticklabels([f"{wk(w)}\n{n} sess." if n else f"{wk(w)}\n–" for w, n in zip(weeks, x["sessions"])], fontsize=8.5)
        ax.set_xlabel("Week of 2026 (sessions logged that week, scripted ones excluded)")
        ax.set_ylabel("Hours in the state, summed across sessions")
        ax.legend(loc="upper left", fontsize=8.5)
        ax.grid(axis="x", visible=False)
        png = F.save(fig, F.asset("9.3"))
        F.picture(s, box, png)

    F.summary("9.3", question="Across the complete observable window, how many hours of work were blocked each week by usage "
                              "limits, owner wait, missing triggers and other states, and did the dominant recorded constraint genuinely shift?",
              params={"window": f"every ISO week with a logged session, {weeks[0]} to {weeks[-1]}; W33 and W34 hold none",
                      "state": "one definition, D6 session_time_segments: a gap of 5 minutes or less between turns is working; "
                               "a longer gap with an ask open is waiting on the owner; with a usage-limit event is blocked by a "
                               "limit; otherwise idle with no trigger; a gap over 8 hours is a closed session and no time at all",
                      "exclusions": "scripted sessions (pre-commit reviews, no model turn)",
                      "unobserved": "owner work outside Claude Code (GitHub, reading, thinking) leaves no segment and is not counted"},
              columns=["week", "sessions"] + order + ["limit_events", "asks", "owner_prompts", "ci_hours", "dominant_wait"],
              table=[[w, x["sessions"][i]] + [ser[n][i] for n in order] + [x["limit_events"][i], x["asks"][i], x["prompts"][i], x["ci_hours"][i], x["dominant"][i]]
                     for i, w in enumerate(weeks)],
              notes=f"Peak limit week {x['peak_week']}: {x['peak_limited']} h limited, {x['peak_waiting']} h waiting. Last two weeks: {x['last2']}. "
                    f"Last four: {x['last4']}. Idle (no trigger) is the largest blocked state in every logged week but the peak.",
              sources=["detectors.session_time_segments", "harness.sessions", "harness.limit_events", "harness.asks", "harness.prompts", "github.ci_runs"])
    l2 = x["last2"]
    return dict(
        q="Across the whole logged window, how many hours a week was the factory blocked by usage limits, by waiting on "
          "the owner, or by having no trigger at all, and did the binding constraint really move?",
        how="Every logged week from 9 Aug: hours per state from the session segments under one definition (working, "
            "waiting on the owner, blocked by a limit, idle with no trigger), stacked; the two unlogged weeks hatched; "
            "sessions per week on the axis; owner work outside Claude Code reported as unobserved.",
        title=(f"Usage limits blocked {x['peak_limited']:.0f} h in the week of {wk(x['peak_week'])}; in the last two weeks the "
               f"factory waited {l2['waiting_human']:.0f} h on the owner and {l2['limited']:.0f} h on limits, and sat idle with "
               f"no trigger for {l2['away']:.0f} h"),
        points=[f"Idle with no trigger, not owner wait, is the largest blocked state in every logged week except the limit week: "
                f"{x['last4']['away']:.0f} h in four weeks against {x['last4']['waiting_human']:.0f} h waiting on an answer.",
                f"Sessions per week: {', '.join(f'{wk(w)} {n}' for w, n in zip(weeks, x['sessions']))}; 10–24 Aug holds none.",
                "Owner work outside Claude Code is unobserved: a session idle for an hour may be the owner reading a PR on GitHub."],
        source=f"session logs (D6 segments, limit events, asks) · GitHub CI runs; {STATE_NAMES['waiting_human'].lower()} = an ask open in a gap over 5 min",
        chart=chart,
        notes=["Figure 9.3. Hours per state per week, summed across concurrent sessions, every ISO week with a logged "
               "session. One state definition (D6): turn gaps of 5 minutes or less are working; a longer gap with an "
               "AskUserQuestion open is waiting on the owner; with a usage-limit event inside is blocked by a limit; "
               "otherwise idle with no trigger. Gaps over 8 hours are a closed session. Scripted sessions are excluded.",
               f"The logs hold one session on 9 Aug ({x['first']['working']} h working) and none from 10 to 24 Aug: hatched, "
               "not zero. From 25 Aug they run continuously.",
               "Unobserved human work: owner time on GitHub, in the browser or away from the terminal leaves no segment, so "
               "'idle, no trigger' contains an unknown amount of owner work and 'waiting on the owner' is a floor. CI runner "
               f"hours ({', '.join(f'{wk(w)} {h}' for w, h in zip(weeks, x['ci_hours']))}) overlap agent work and are context, not a wait state.",
               "Limit events per week: " + ", ".join(f"{wk(w)} {n}" for w, n in zip(weeks, x["limit_events"])) +
               ". Asks per week: " + ", ".join(f"{wk(w)} {n}" for w, n in zip(weeks, x["asks"])) + ".",
               "Did the constraint shift? Yes for the provider: limits fell from 108 h to under 4 h a week. The human side "
               "is two things: answers the factory waited for (measured) and work it never started (idle; a session open "
               "with nothing running). Spend capped no week (Q binding-constraint's earlier view).",
               f"Code: {CODE}:q_binding_constraint_window · time_states"])


# ------------------------------------------------------------------ 9.4 · Q new-work-sources

SRC_COLORS = {"Owner, entered directly": F.GREY_DARK, "Plan-sync from a dependency alert": F.SEQ[1], "Plan-sync, its own proposal": F.PINK,
              "Plan-sync, carved from an existing item": F.PINK_LIGHT, "Audit (harden, self-review)": F.PINK_DARK,
              "Agent, discovered while building": F.TEAL, "One-shot task (owner's instruction in a session)": "#9DA3AE",
              "Message from another repo": F.GREY, "Unknown": F.GREY_LIGHT}
SHORT_SRC = {"Owner, entered directly": "Owner", "Plan-sync from a dependency alert": "Sync: dependency alert",
             "Plan-sync, its own proposal": "Sync: own proposal", "Plan-sync, carved from an existing item": "Sync: carved out",
             "Audit (harden, self-review)": "Audit", "Agent, discovered while building": "Agent, while building",
             "One-shot task (owner's instruction in a session)": "One-shot", "Message from another repo": "Message", "Unknown": "Unknown"}
AUTH_COLORS = {AUTH_94[0]: F.PINK, AUTH_94[1]: F.PINK_LIGHT, AUTH_94[2]: F.GREY_DARK, AUTH_94[3]: F.GREY_LIGHT}
AUDIT_94 = ("Validation: 26 items drawn at random from the window and read by hand (title, frontmatter, log). Five were "
            "re-created by the 19–22 Sep schema migration and are not new work; the rule now excludes them. On the other "
            "21 the rule's class matched the hand reading in 21 (100%).")


def fig_9_4(x):
    n = x["n"]

    def bar(ax, y, parts, colors):
        left = 0.0
        for name, v in parts.items():
            share = v / n
            ax.barh([y], [share], left=left, height=0.55, color=colors[name], edgecolor="white", linewidth=1.5,
                    label=f"{name} ({v})", hatch="//" if name == "Unknown" else None)
            if share >= 0.045:
                txt = "white" if colors[name] in (F.PINK, F.GREY_DARK, F.PINK_DARK, F.TEAL) else F.INK
                ax.text(left + share / 2, y, f"{share:.0%}", ha="center", va="center", fontsize=9, color=txt)
            left += share

    def chart(s, box):
        fig, ax = F.fig(F.CHART_W, F.CHART_H)
        bar(ax, 1, x["by_source"], SRC_COLORS)
        bar(ax, 0, x["by_auth"], AUTH_COLORS)
        ax.set_xlim(0, 1)
        ax.set_ylim(-0.5, 1.5)
        ax.set_yticks([1, 0])
        ax.set_yticklabels([f"Proposed by\n(n = {n})", f"Authorized by\n(n = {n})"])
        ax.xaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1.0))
        ax.grid(axis="y", visible=False)
        ax.set_xlabel(f"Share of work items created in the final four weeks ({wk(x['weeks'][0])} to {wk(x['weeks'][-1])})")
        ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8.5)
        png = F.save(fig, F.asset("9.4"))
        F.picture(s, box, png)

    tb = x["table"]
    F.summary("9.4", question="What originated each new work item, allowing multiple and unknown sources, who authorized it "
                              "and how did priority, completion and time-to-start differ between owner, plan-sync, audit, "
                              "production and agent-discovered work?",
              params={"population": f"work items (not goals) in in-scope repos created in {x['weeks'][0]}–{x['weeks'][-1]}, n = {n}; "
                                    f"{x['migrated']} items whose first log line is the schema migration have no creation date and are excluded",
                      "proposal": "frontmatter origin, discovered_from and bot: owner origins (rahul, user, conversation, "
                                  "think-it-through, grill); plan-sync (wayfare, wayfare-sync-plan), split into its own "
                                  "proposal, carved from an existing item (discovered_from) and from a Dependabot alert (bot); "
                                  "audit (harden, self-review); one-shot or build-task origins with discovered_from are "
                                  "agent-discovered while building, without it a one-shot task; message; else unknown",
                      "authorization": "goal member (parent or goal_id: the owner started the goal at a gate); else "
                                       "ready-marked; else done without either; else open"},
              columns=["source", "n", "share", "share_done", "share_ranked", "share_in_goal", "share_open", "median_days_to_ready", "n_ready"],
              table=[[t["source"], t["n"], t["share"], t["done"], t["ranked"], t["in_goal"], t["open"], t["median_days_to_ready"], t["n_ready"]] for t in tb],
              notes=AUDIT_94 + f" Authorization: {x['by_auth']}. Weekly by source: {x['weekly']}.",
              sources=["plans.plan_items", "plans.item_logs"],
              extra={"by_source": x["by_source"], "by_auth": x["by_auth"], "sync_share": x["sync_share"], "audit_share": x["audit_share"],
                     "owner_share": x["owner_share"]})
    auth = x["by_auth"]
    src = x["by_source"]
    return dict(
        q="What proposed each new work item in the final four weeks, allowing several sources and unknown ones, who "
          "authorized it, and how did completion, ranking and time to start differ by source?",
        how="Every work item created in the last four weeks, classed by what proposed it (owner entry, plan-sync in three "
            "kinds, audit, agent discovery while building, a message, unknown) and separately by what authorized it (a "
            "goal the owner started, a ready-mark, neither); items re-created by the September schema migration excluded.",
        title=(f"Plan-sync proposed {pct(x['sync_share'])} of the {n} new work items in the final four weeks ({pct(x['dep_share'])} "
               f"from dependency alerts) and the audits {pct(x['audit_share'])}; the owner entered {pct(x['owner_share'])} directly; "
               f"{pct(auth[AUTH_94[0]] / n)} were authorized through a goal the owner started"),
        points=[f"Agents discovered {pct(x['agent_share'])} while building; {pct(x['unknown_share'])} have no recorded source; "
                f"{x['migrated']} items re-created by the 19–22 Sep migration are not counted as new.",
                f"Authorization: {pct(auth[AUTH_94[1]] / n)} ready-marked outside a goal, {pct(auth[AUTH_94[2]] / n)} built with no "
                f"recorded authorization, {pct(auth[AUTH_94[3]] / n)} still open.",
                f"Audit items finish most often ({pct(next(t['done'] for t in tb if t['source'].startswith('Audit')))} done) and owner "
                f"items least ({pct(next(t['done'] for t in tb if t['source'].startswith('Owner')))}); every source's median time to ready is the same day."],
        source=".plans work items: origin, discovered_from, bot, parent, ready_marked · item logs",
        chart=chart,
        notes=["Figure 9.4. Two 100% bars over the same items. 'Proposed by' reads the frontmatter: origin names the "
               "skill or person that wrote the item; discovered_from marks an item carved out of another (by plan-sync) "
               "or found while building (by a one-shot or build task); bot marks a Dependabot alert plan-sync turned into "
               "an item. Multi-source cases are their own segments rather than forced into one origin. 'Authorized by': "
               "membership of a goal (the owner starts every goal at a gate, wayfare-start-goal), else a ready-mark, else "
               "done with neither, else open.",
               AUDIT_94,
               "Excluded: " + f"{x['migrated']} items whose first log line is 'migrated to schema 1' (auth 63, design-system 20, "
               "elevate-commons 13, hero-template 6): their created date is the migration day, and 38 of them were "
               "ready-marked before it. The earlier card counted them, which is why its total was 601 and 'not recorded' 12%.",
               "By source (n, done, ranked, in a goal, open, median days to ready): " + "; ".join(
                   f"{t['source']}: {t['n']}, {pct(t['done'])}, {pct(t['ranked'])}, {pct(t['in_goal'])}, {pct(t['open'])}, "
                   f"{t['median_days_to_ready'] if t['median_days_to_ready'] is not None else '–'}" for t in tb) + ".",
               "Caveat: plan-sync and the audits are started by the owner, so 'proposed by the factory' means the item "
               "was written by a skill run, not that nobody asked for the work. Days to ready are dates only.",
               f"Code: {CODE}:q_new_work_sources_provenance · provenance"],
        breakdowns=[dict(
            tag="By source",
            title=(f"Audit items were {pct(next(t['in_goal'] for t in tb if t['source'].startswith('Audit')))} goal members and "
                   f"{pct(next(t['done'] for t in tb if t['source'].startswith('Audit')))} done; owner-entered items "
                   f"{pct(next(t['in_goal'] for t in tb if t['source'].startswith('Owner')))} and {pct(next(t['done'] for t in tb if t['source'].startswith('Owner')))}"),
            points=["Share of each source's items done, ranked (a priority set) and inside a goal.",
                    "Sources with under 10 items are left out."],
            chart=lambda s, b: L.bars(s, b, [SHORT_SRC[t["source"]] for t in tb if t["n"] >= 10],
                                      {"Done": [t["done"] for t in tb if t["n"] >= 10], "Ranked": [t["ranked"] for t in tb if t["n"] >= 10],
                                       "In a goal": [t["in_goal"] for t in tb if t["n"] >= 10]},
                                      [PINK, GREY, GREY_DARK], x_title="Proposed by (n in the notes)", y_title="Share of the source's items",
                                      pct_axis=True),
            note="Code: " + CODE + ":q_new_work_sources_provenance")])
