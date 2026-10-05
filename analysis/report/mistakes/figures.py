"""Drawn figures for the book's Chapter 4 cards in this deck: 4.3 (Q done-not-done) and 4.6 (Q fix-forwards).

Each function takes the question's data, draws with figure_lib, writes the summary table and returns the PNG
the answer slide places with F.picture. Run through deck.py with /tmp/pptxenv/bin/python3.
"""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import deck_lib as L  # noqa: E402
import figure_lib as F  # noqa: E402

MIN_MONTH = 50   # a month enters the rate panel only with this many PRs whose window is complete


def _two_bars(ax, labels, values, title, xlabel, share_note):
    ys = [1, 0]
    ax.barh(ys, values, color=[F.GREY, F.PINK], height=0.55)
    for y, v, extra in zip(ys, values, ["", share_note]):
        ax.text(v + max(values) * 0.015, y, f"{v:,}{extra}", va="center", fontsize=10, color=F.INK)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.set_xlim(0, max(values) * 1.45)
    ax.set_ylim(-0.6, 1.6)
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel, fontsize=9)
    ax.grid(axis="y", visible=False)


def fig_4_3(x):
    """Two records of 'done that was not done', each against its own denominator, never summed."""
    # Stacked, not side by side: at print width two panels abreast leave each too narrow for its labels.
    fig, (a, b) = F.fig(h=5.6, nrows=2)
    lo, hi = F.wilson(x["prs_back"], x["prs_judged"])
    _two_bars(a, ["PRs the judge ruled on", "Sent back at least once"], [x["prs_judged"], x["prs_back"]],
              "The final judge (auto-approve), Apr–Sep",
              f"PRs with a verdict, merged or not\n({x['n_judge']} send-back verdicts among {x['judged']:,})",
              f"  ({x['prs_back'] / x['prs_judged']:.1%}; 95% CI {lo:.1%}–{hi:.1%})")
    lo2, hi2 = F.wilson(x["n_lm"], x["n_all_lm"])
    _two_bars(b, ["Mistakes agents logged", "Work described as done\nwhen it was not"], [x["n_all_lm"], x["n_lm"]],
              f"The agents' own logs, from {date.fromisoformat(x['lm_first_day']).strftime('%-d %b')}",
              f"Mistake-log entries and work-item notes\n({x['lm_linked']} of {x['n_lm']} trace to a merged PR; "
              f"{x['lm_overlap']} of those were sent back)",
              f"  ({x['n_lm'] / x['n_all_lm']:.0%}; 95% CI {lo2:.0%}–{hi2:.0%})")
    png = F.save(fig, F.asset("4.3"))
    F.summary("4.3", question="How often did a builder's completion claim conflict with the final judge, acceptance criteria "
                              "or later evidence, how much overlap existed among those records and what kinds of overclaim recurred?",
              params={"judge": "github-actions reviews in state APPROVED or CHANGES_REQUESTED, in-scope repos",
                      "overclaim": "mistake_labels.is_mistake with overclaim=1 or theme unverified_claim, sources mistake_log and note",
                      "overlap": "overclaim's work item -> its recorded PR, branch or goal branch -> judge send-back on that PR"},
              columns=["record", "numerator", "denominator", "share", "ci95_lo", "ci95_hi"],
              table=[["PRs sent back by the judge", x["prs_back"], x["prs_judged"], round(x["prs_back"] / x["prs_judged"], 4), round(lo, 4), round(hi, 4)],
                     ["Agent-logged overclaims", x["n_lm"], x["n_all_lm"], round(x["n_lm"] / x["n_all_lm"], 4), round(lo2, 4), round(hi2, 4)]],
              extra={"send_back_verdicts": x["n_judge"], "verdicts": x["judged"], "overclaims_linked_to_pr": x["lm_linked"],
                     "overclaims_on_sent_back_prs": x["lm_overlap"], "themes": x["themes"], "caught_by": x["lm_caught_by"],
                     "judge_reasons": x["reasons"], "fixups_of_unverified_claim": x["n_fx"]},
              notes="The two bars have different denominators and are never combined: the judge sees every PR, the log holds only "
                    "what an agent chose to write down, and the log exists since 24 Jul (the dedicated mistake log since 18 Sep). "
                    "Acceptance-criteria overclaims are not in the data (no per-criterion tick history).",
              sources=["github.pr_reviews", "mistakes.mistake_labels", "plans.plan_items", "github.prs"])
    return png


def fig_4_6(x):
    """Left: monthly share of merged PRs repaired within 7, 14 and 30 days, each on the PRs whose window is complete.
    Right: cumulative share repaired by day, PRs with a full 30-day window."""
    fig, (a, b) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1.15, 1]})
    months = [m for m in x["monthly"][7] if x["monthly"][7][m][1] >= MIN_MONTH]
    cols = {7: F.PINK, 14: F.GREY_DARK, 30: F.GREY}
    for w in (30, 14, 7):
        pts = [(i, x["monthly"][w][m][0] / x["monthly"][w][m][1]) for i, m in enumerate(months)
               if m in x["monthly"][w] and x["monthly"][w][m][1] >= MIN_MONTH]
        a.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=4.5, color=cols[w], linewidth=1.6,
               label=f"within {w} days")
        for i, v in pts:
            if w == 7:
                a.annotate(f"{v:.0%}", (i, v), xytext=(9, 4), textcoords="offset points", ha="left", fontsize=8.5,
                           color=F.PINK_DARK)
    a.set_xticks(range(len(months)))
    a.set_xticklabels([f"{L.mlabel(m)}\n(n={x['monthly'][7][m][1]})" for m in months])
    a.yaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    a.set_ylim(0, max(v[0] / v[1] for w in (7, 14, 30) for m, v in x["monthly"][w].items() if m in months and v[1] >= MIN_MONTH) * 1.3)
    a.set_ylabel("Share of the month's merged PRs")
    a.set_xlabel("Month merged (n = PRs with a complete 7-day window)")
    a.set_title("PRs needing a fix, by observation window", loc="left")
    a.legend(loc="upper left")
    a.grid(axis="x", visible=False)

    n = x["n_elig30"]
    lts = x["lifetimes30"]
    xs = list(range(0, 31))
    ys = [sum(1 for l in lts if l <= d) / n for d in xs]
    b.step(xs, ys, where="post", color=F.PINK, linewidth=2)
    for d in (3, 7, 14, 30):
        v = ys[d]
        b.plot([d], [v], "o", color=F.GREY_DARK, markersize=5, zorder=3)
        b.annotate(f"{d}d: {v:.1%}", (d, v), xytext=(6, -2 if d != 30 else 6), textcoords="offset points", fontsize=8.5,
                   color=F.GREY_DARK, ha="left" if d < 30 else "right")
    b.yaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    b.set_xlim(0, 31)
    b.set_ylim(0, max(ys) * 1.25)
    b.set_xlabel(f"Days from merge to the first repairing change set\n(n={n:,} PRs with a complete 30-day window)")
    b.set_ylabel("Cumulative share of merged PRs")
    b.set_title("Time to repair, cumulative", loc="left")
    b.grid(axis="x", visible=False)
    png = F.save(fig, F.asset("4.6"))
    W = x["windows"]
    F.summary("4.6", question="What share of merged pull requests needed an attributable corrective change within 7, 14 and 30 "
                              "days, how quickly were they repaired and how did the rate vary by repository, change type, severity "
                              "and user exposure?",
              params={"data_end": x["data_end"], "population": "merged, non-bot, non-Dependabot PRs in in-scope repos",
                      "eligibility": "merged at least `window` days before data_end", "attribution": "SZZ over the mirrors: the "
                      "PR owning most of the lines a later fix change set deleted or rewrote; a PR counts once, at its shortest delay"},
              columns=["window_days", "eligible_prs", "fixed_prs", "share", "ci95_lo", "ci95_hi"],
              table=[[w, W[w]["eligible"], W[w]["fixed"], round(W[w]["fixed"] / W[w]["eligible"], 4),
                      *(round(v, 4) for v in F.wilson(W[w]["fixed"], W[w]["eligible"]))] for w in (3, 7, 14, 30)],
              extra={"monthly": {str(w): x["monthly"][w] for w in (7, 14, 30)}, "cumulative_days": dict(zip(xs, [round(v, 4) for v in ys])),
                     "lifetimes_30": lts, "by_repo_7d": x["repo7"], "by_category_7d": x["cat7"], "by_period_7d": x["periods"],
                     "u7_within_3": x["u7_within_3"], "u7_within_1": x["u7_within_1"],
                     "all_prs_7d_uncensored": [x["n7"], x["n_prs"]], "all_prs_3d_uncensored": [x["n3"], x["n_prs"]]},
              notes="Severity is not recorded on fix change sets, and no repo has a recorded launch date, so user exposure is "
                    f"approximated by repo category (app / app with no features yet / allied). Months with fewer than {MIN_MONTH} "
                    "eligible PRs are left out of the left panel.",
              sources=["mistakes.szz", "detectors.cs_sets (fix change sets)", "github.prs", "pr_commits.pr_commits", "git.commits"])
    return png


def fig_4_6_by_repo(x, png_suffix="by-repo"):
    """7-day rate per repo with a Wilson interval; repos with 20+ eligible PRs."""
    repos = [(r, k, n) for r, (k, n) in x["repo7"].items() if n >= 20]
    fig, ax = F.fig()
    est = [k / n for _, k, n in repos]
    lo, hi = zip(*[F.wilson(k, n) for _, k, n in repos])
    W = x["windows"][7]
    F.dot_whisker(ax, [r for r, _, _ in repos], est, lo, hi, n=[n for _, _, n in repos], fmt="{:.0%}",
                  ref=W["fixed"] / W["eligible"], ref_label=f"all repos {W['fixed'] / W['eligible']:.1%}",
                  xlabel="Share of merged PRs repaired within 7 days (95% Wilson interval); repos with 20+ PRs")
    ax.xaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlim(0, max(hi) * 1.15)
    return F.save(fig, F.asset("4.6", png_suffix))
