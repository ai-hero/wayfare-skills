"""The field deck's book figures (8.1 to 8.4): the answer views drawn from data.py's fig_* results, and the summary
table each leaves in .analysis/data/figures/<id>.json.

Each `fig_*` returns the dict `deck.ask` expects (question, title, points, chart, source, note, breakdowns) so deck.py
only wires it in. Charts that are bars or lines are native (deck_lib); the rest are drawn with figure_lib and
placed as a picture.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from pptx.enum.chart import XL_CHART_TYPE  # noqa: E402

import deck_lib as L  # noqa: E402
import figure_lib as F  # noqa: E402
from deck_lib import GREY, GREY_DARK, GREY_LIGHT, PINK, PINK_DARK, PINK_LIGHT, pct  # noqa: E402
from data import AUTONOMY_CATS_81, CLASSES_83, DEFINITIONS_81, INPUT_CATS, ITEM_STORE_FROM, MONTHS  # noqa: E402

CODE = "analysis/report/field/data.py"


def dm(d):
    from datetime import date
    return date.fromisoformat(d).strftime("%-d %b")


def notes(*parts):
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------ 8.1 · Q no-human-merges

def fig_8_1(x):
    months = [m for m, n in zip(x["months"], x["n_month"]) if n]
    idx = [x["months"].index(m) for m in months]
    cats = [f"{L.mlabel(m)} ({x['n_month'][i]})" for m, i in zip(months, idx)]
    series = {c: [x["shares"][c][i] for i in idx] for c in AUTONOMY_CATS_81 if any(x["counts"][c])}
    colors = {AUTONOMY_CATS_81[0]: PINK, AUTONOMY_CATS_81[1]: PINK_LIGHT, AUTONOMY_CATS_81[2]: GREY_DARK,
              AUTONOMY_CATS_81[3]: GREY, AUTONOMY_CATS_81[4]: GREY_LIGHT}
    p, h1, sep = x["prior"], x["h1"], x["sep"]

    def chart(s, box):
        L.chart(s, XL_CHART_TYPE.COLUMN_STACKED, cats, series, [colors[c] for c in series], box=box,
                x_title="Month merged (merged non-bot PRs that month)", y_title="Share of merged PRs", pct_axis=True,
                stacked=True, gap=40)
        L.draw_milestones(s, box, lambda d: L.month_frac(d, months))

    F.summary("8.1", question="Under several explicit definitions of human involvement, what share of eligible pull requests "
                              "merged without owner action while open, and how many still had prior human direction or authorization?",
              params={"population": "merged PRs in in-scope repos, 2026, authored by a person's account (Dependabot and bot "
                                    "authors excluded)", "excluded_bot_prs": x["excluded_bot"], "gate": "github-actions approval",
                      "owner_prompt": "typed prompt in the same repo between the PR opening and its merge (housekeeping commands excluded)",
                      "prior_direction": "an owner prompt in the repo in the 7 days before the PR opened",
                      "authorization": "a ready-marked or goal-member work item naming the PR or its branch"},
              columns=["month", "merged_prs"] + AUTONOMY_CATS_81 + DEFINITIONS_81,
              table=[[m, x["n_month"][i]] + [x["counts"][c][i] for c in AUTONOMY_CATS_81] + [x["defs"][d][i] for d in DEFINITIONS_81]
                     for i, m in enumerate(x["months"])],
              notes=f"Hands-off (definition 3) PRs: {p['hands_off']}; with an owner prompt in the repo in the prior 7 days "
                    f"{p['prompt_7d']}; linked to a work item {p['item']} (authorized {p['item_authorized']}); neither {p['neither']}. "
                    f"September: {p['sep_hands_off']} hands-off, {p['sep_prompt_7d']} with a prior prompt, {p['sep_item']} linked, "
                    f"{p['sep_neither']} neither. Unknown (merged with no merge event in the timeline): {x['unknown']}.",
              sources=["github.prs", "github.pr_reviews", "github.pr_timeline", "harness.prompts", "plans.plan_items"],
              extra={"h1": h1, "sep": sep, "prior": p})
    return dict(
        question="Under several explicit definitions of human involvement, what share of merged PRs reached main with no "
                 "owner action while open, and how many of those still had prior human direction or authorization?",
        title=(f"Gate-approved with no owner prompt while open: {pct(h1['hands_off'])} of merged PRs in the first half of the "
               f"year, {pct(sep['hands_off'])} in September; {pct(p['sep_prompt_7d'] / p['sep_hands_off'])} of September's had "
               f"an owner prompt in that repo in the week before they opened"),
        points=[f"With an owner prompt while open, the gate approved another {pct(h1['with_prompt'])} → {pct(sep['with_prompt'])}. "
                f"Under a person's account: {pct(x['shares'][AUTONOMY_CATS_81[2]][5])} in June, none in September.",
                f"No input while open is not no direction: of {p['hands_off']} hands-off PRs all year, {p['item']} name a work "
                f"item ({p['item_authorized']} of them ready-marked or in a goal) and {p['neither']} had neither a prior prompt nor an item.",
                f"{x['unknown']} PR merged with no merge event in the timeline is kept as unknown; {x['excluded_bot']} bot-authored PRs are out of scope."],
        chart=chart,
        source="GitHub PRs, reviews and timeline · Claude Code prompt history · .plans work items",
        note=notes("Figure 8.1. Monthly composition under definition (3) of Q comparable-units, with the unknown case kept: "
                   "a merged PR whose timeline holds no 'merged' event. 'A person's account' approved means a non-bot "
                   "GitHub account approved or authored the PR; agents post under the owner's account, so this is an "
                   f"upper bound on human approval (Chapter 5). Merged non-bot PRs by month: {dict(zip(x['months'], x['n_month']))}. "
                   "Months with none are left out.",
                   "Prior direction and authorization, for hands-off PRs: an owner prompt in the same repo in the 7 days "
                   f"before the PR opened ({p['prompt_7d']} of {p['hands_off']}); a work item that names the PR URL or its "
                   f"branch in its frontmatter ({p['item']}; {p['item_authorized']} ready-marked or goal members); neither "
                   f"({p['neither']}). Work items link to PRs only from late August, so the item count is a lower bound.",
                   "Hypothesis: held on direction only, as before; the new cut shows that most hands-off merges follow "
                   "recent owner direction in the repo.",
                   f"Code: {CODE}:q_no_human_merges_monthly · pr_autonomy"),
        breakdowns=[
            dict(eyebrow="By definition",
                 title=(f"Four definitions, one September: {pct(x['def_shares'][DEFINITIONS_81[0]][8])} by GitHub identity, "
                        f"{pct(x['def_shares'][DEFINITIONS_81[1]][8])} by the gate alone, {pct(x['def_shares'][DEFINITIONS_81[2]][8])} "
                        f"with no prompt in the repo, {pct(x['def_shares'][DEFINITIONS_81[3]][8])} with no prompt anywhere in the fleet"),
                 points=["Each line is the same merged PRs under a stricter test of 'no human involvement'.",
                         "Identity says a person touched every PR: the agent acts under the owner's account.",
                         "The fleet-wide test is the lower bound; the owner prompts in another repo most hours."],
                 chart=lambda s, box: L.month_lines(s, box, {d: x["def_shares"][d] for d in DEFINITIONS_81},
                                                    [GREY, GREY_DARK, PINK, PINK_DARK], y_title="Share of merged PRs", pct_axis=True),
                 note="Per month: PRs meeting each definition ÷ merged non-bot PRs. Months with no merged PR are blank. "
                      f"Code: {CODE}:q_no_human_merges_monthly"),
            dict(eyebrow="Prior direction",
                 title=(f"Of the {p['hands_off']} hands-off PRs, {pct(p['prompt_7d'] / p['hands_off'])} followed an owner prompt in the "
                        f"repo within 7 days and {pct(p['item'] / p['hands_off'])} name a work item; {pct(p['neither'] / p['hands_off'])} had neither"),
                 points=["No input while open is not the same as no prior human direction.",
                         "Work items only record their PR from late August, so the linked share is a floor.",
                         f"September alone: {p['sep_prompt_7d']} of {p['sep_hands_off']} with a prior prompt, {p['sep_neither']} with neither."],
                 chart=lambda s, box: L.bars(s, box, ["Owner prompt in the repo, prior 7 days", "Names a work item",
                                                      "Ready-marked or goal-member item", "Neither prompt nor item"],
                                             {"All 2026": [p["prompt_7d"] / p["hands_off"], p["item"] / p["hands_off"],
                                                           p["item_authorized"] / p["hands_off"], p["neither"] / p["hands_off"]],
                                              "September": [p["sep_prompt_7d"] / p["sep_hands_off"], p["sep_item"] / p["sep_hands_off"],
                                                            None, p["sep_neither"] / p["sep_hands_off"]]},
                                             [GREY_DARK, PINK], x_title="Evidence of prior direction", y_title="Share of hands-off PRs",
                                             pct_axis=True),
                 note="Hands-off = gate approved, no owner prompt in the repo while open. Prior prompt: any typed prompt in that "
                      "repo in the 7 days before the PR opened. Work item: frontmatter pr URL or branch equals the PR's head. "
                      f"Code: {CODE}:q_no_human_merges_monthly")])


# ------------------------------------------------------------------ 8.2 · Q human-reading-points

INPUT_COLORS = [F.PINK_DARK, F.PINK, F.PINK_LIGHT, "#7B8290", "#C6C9D0", F.GREY_DARK, "#666D7B", F.CONTRAST, F.GREY, F.GREY_LIGHT, "#F4F5F8"]
AUDIT_82 = ("Validation: a random sample of labelled free-text prompts was judged by hand from their text against the "
            "shared intent label, and every prompt the PR/merge text rule caught was read; the agreement counts are in "
            "the chapter's summary.")


def fig_8_2(x):
    per = x["per"]
    rows_ = [f"{p}\n(n = {per[p]['n']:,})" for p in x["periods"]]
    parts = {c: [per[p]["shares"][c] or 0 for p in x["periods"]] for c in INPUT_CATS}

    def chart(s, box):
        fig, ax = F.fig(8.35, 5.4)
        F.stacked100(ax, rows_, parts, colors=INPUT_COLORS, horizontal=True, min_label=0.05,
                     xlabel="Share of the owner's inputs in the period (typed prompts, ready-marks)")
        for i, p in enumerate(x["periods"]):
            pr = sum(per[p]["shares"][k] or 0 for k in ("PR and review handling", "Merge and ship commands"))
            plan = sum(per[p]["shares"][k] or 0 for k in ("Planning commands", "Approving a plan or step", "Work item marked ready"))
            ax.text(1.01, i, f"plan + approve {plan:.0%}\nPR + merge {pr:.0%}", va="center", ha="left", fontsize=8.5, color=F.BODY)
        ax.set_xlim(0, 1)
        ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14), fontsize=8.5)
        png = F.save(fig, F.asset("8.2"))
        F.picture(s, box, png)

    F.summary("8.2", question="How did the composition of owner attention change across factory stages after normalizing for "
                              "total prompts, especially between planning, approval, pull-request handling, correction and operational intervention?",
              params={"population": "owner inputs in 2026 in fleet repos: typed prompts (housekeeping commands excluded) and "
                                    "work items marked ready", "periods": x["periods"],
                      "classifier": "slash commands by name (STAGE_OF_CMD); free text by the shared intent label "
                                    "(detectors.prompt_intent), except a push/ship/merge order, which is PR handling (PR_TEXT_RE)",
                      "normalization": "share of all inputs in the period"},
              columns=["period", "n"] + INPUT_CATS,
              table=[[p, per[p]["n"]] + [per[p]["counts"][c] for c in INPUT_CATS] for p in x["periods"]],
              notes=AUDIT_82 + f" Unlabelled free text: {x['unlabelled']} of {x['n_text']} prompts (the label table stops on 25 Sep). "
                    f"Ready-marks exist only from {dm(ITEM_STORE_FROM)}.",
              sources=["harness.prompts", "detectors.prompt_intent", "plans.plan_items"],
              extra={"pr_first": x["pr_first"], "pr_last": x["pr_last"], "plan_first": x["plan_first"], "plan_last": x["plan_last"],
                     "corr_first": x["corr_first"], "corr_last": x["corr_last"]})
    return dict(
        question="How did the composition of the owner's inputs change across the factory's stages, once normalized by "
                 "total inputs: planning and approval, PR handling, correction, questions and operations?",
        title=(f"PR and merge handling fell from {pct(x['pr_first'])} of the owner's inputs with skills alone to "
               f"{pct(x['pr_last'])} with goals; planning, approving and ready-marking rose from {pct(x['plan_first'])} to "
               f"{pct(x['plan_last'])}, and corrections halved ({pct(x['corr_first'])} → {pct(x['corr_last'])})"),
        points=[f"Questions and answers stay the largest block in every period "
                f"({pct(per[x['periods'][0]]['shares']['Questions and answers'])} → {pct(per[x['periods'][-1]]['shares']['Questions and answers'])}).",
                f"{x['n']:,} inputs: {x['n_cmd']:,} commands, {x['n_text']:,} free-text prompts, {x['n_ready']} ready-marks. "
                f"Free text is classed by the shared intent label; {x['pr_text']} push/ship/merge orders in free text count as PR handling.",
                "Validation: a random sample of intent labels and every PR-text match were checked by hand; the counts are in the chapter's summary."],
        chart=chart,
        source="Claude Code prompt history · shared intent labels (prompt_intent) · .plans ready-marks",
        note=notes("Figure 8.2. Composition of owner inputs by period, each bar summing to 100%. Categories: planning "
                   "commands (grill, sync-plan, wayfare, architecture, harden, init, recalibrate); approving a plan or step "
                   "(free text the shared classifier labels approve); work item marked ready (.plans ready_marked, dates "
                   "only, tracked from 23 Jul); new work and instructions (new_work); build commands (one-shot, goal, "
                   "start-goal, build-task); PR and review handling (push-pr, review-pr, respond commands, plus free-text "
                   "push/ship/merge orders); merge and ship commands (ship-pr, auto-approve, reset); corrections and "
                   "redirects (correction, redirect); questions and answers; operational (continue, meta, other); "
                   "unlabelled free text (no intent label).",
                   AUDIT_82,
                   "Normalizing by total inputs, not by change sets, changes the reading from the earlier card: the "
                   "earlier answer counted touches per merged change set (kept as the 'Per change set' view).",
                   "Owner time outside Claude Code (reading PRs on GitHub) leaves no input here. Hypothesis: held on "
                   "direction; the PR-to-plan shift survives the wider category set.",
                   f"Code: {CODE}:q_human_reading_points_composition · owner_inputs"))


# ------------------------------------------------------------------ 8.3 · Q git-only-measurability

def fig_8_3(x):
    tb = x["table"]
    labels = [t["combination"] for t in tb]
    colors = [PINK if t["classes"] == ["Git/GitHub"] else GREY_DARK if "Factory records" in t["classes"]
              else GREY_LIGHT if not t["classes"] else GREY for t in tb]
    n, only, tot = x["needs"], x["only"], x["total"]

    def chart(s, box):
        c = L.bars(s, box, labels[::-1], {"Questions": [t["n"] for t in tb][::-1]}, [GREY], horizontal=True,
                   y_title=f"Bank questions (n = {tot}), by the sources each needs")
        L.point_colors(c, colors[::-1])

    F.summary("8.3", question="Which analytical questions can be answered from Git/GitHub alone, which require factory records, "
                              "live-system evidence or human testimony, and which require combinations of those sources?",
              params={"population": f"the question bank's {tot} chapter questions (analysis/bank/questions.csv)",
                      "rules": "each source table or detector maps to Git/GitHub (git, github, pr_commits, public release "
                               "notes; D1, D5, D7, D8), agent transcripts (harness; D6, D9) or factory records (plans, "
                               "knowledge, mailbox, HERO.md, FLEET.md, the plugin repo; D2, D3, D4, D10); a method that "
                               "names a person adds human testimony; a deferred question about a live check adds live "
                               "system; a question is counted under its full set of classes"},
              columns=["combination", "n"], table=[[t["combination"], t["n"]] for t in tb],
              notes=f"Needs (alone or combined): {n}. Alone: {only}. Multi-source: {x['multi']}. "
                    f"No source listed: {x['unlisted']}. {x['model_labels']} questions also need a model label (Haiku) as a method.",
              sources=["analysis/bank/questions.csv"], extra={"needs": n, "only": only, "multi": x["multi"]})
    return dict(
        question="Which of the study's questions can be answered from Git/GitHub alone, which need factory records, agent "
                 "transcripts, live-system evidence or human testimony, and which need a combination?",
        title=(f"{only['Git/GitHub']} of {tot} questions ({pct(only['Git/GitHub'] / tot)}) need Git/GitHub alone; "
               f"{n['Factory records']} ({pct(n['Factory records'] / tot)}) need the factory's own records, "
               f"{only['Factory records']} of them nothing else, and {x['multi']} need two or more sources"),
        points=[f"Agent transcripts enter {n['Agent transcripts']} questions; {n['Human testimony']} need the owner's testimony, "
                f"{only['Human testimony']} of them nothing else; {n['Live system']} need a live check of a running system.",
                "Needing testimony or a live system is not being unanswerable: it names the evidence to collect.",
                f"{x['unlisted']} questions list no source; {x['model_labels']} also need a model label (Haiku) as a method."],
        chart=chart,
        source="question bank: sources, detectors, method columns",
        note=notes("Figure 8.3. Every chapter question in the bank, by the set of evidence classes its sources, detectors "
                   "and method imply, one bar per combination. Rules: Git/GitHub = git, github and pr_commits tables, "
                   "public model and Claude Code release notes, detectors D1, D5, D7, D8; agent transcripts = harness "
                   "tables, D6, D9; factory records = .plans (work items, goals, mailbox), knowledge (DESIGN.md, register, "
                   "skills, instruction files), HERO.md, FLEET.md, the plugin repo, D2, D3, D4, D10; human testimony = a "
                   "method naming a person (human, or deferred with no source); live system = a deferred question about "
                   "a live check, revocation, network exposure or boot configuration. Pink: Git/GitHub suffices; dark "
                   "grey: factory records are among the sources.",
                   f"Compared with the earlier tiering (highest tier wins): Git/GitHub alone was 55, now {only['Git/GitHub']}, "
                   "because seven of those also need the owner's judgement; 'wayfare's own records' (155) becomes "
                   f"factory records in any combination ({n['Factory records']}), a wider class that includes work items and goals.",
                   "Hypothesis: held, with the prerequisite list longer than drafted. What another factory needs, class by "
                   "class: a PR-based workflow; transcripts kept, not rotated; a work-item store with dates and the PR each "
                   "item produced; a design record, a control register and a mailbox in git; and an hour of the owner's time.",
                   f"Code: {CODE}:q_git_only_measurability_sources · question_sources"),
        breakdowns=[
            dict(eyebrow="By class",
                 title=(f"Factory records are needed by {n['Factory records']} questions and suffice for {only['Factory records']}; "
                        f"Git/GitHub is needed by {n['Git/GitHub']} and suffices for {only['Git/GitHub']}"),
                 points=["Left bar: the class appears among the question's sources; right bar: it is the only one.",
                         "The gap between the bars is the multi-source share of each class."],
                 chart=lambda s, box: L.bars(s, box, CLASSES_83, {"Needed, alone or combined": [n[c] for c in CLASSES_83],
                                                                   "Sufficient alone": [only[c] for c in CLASSES_83]},
                                             [GREY_DARK, PINK], x_title="Evidence class", y_title=f"Bank questions (n = {tot})"),
                 note=f"Counts over the same {tot} questions; a question with two classes is counted under both in the left "
                      f"bars. Code: {CODE}:q_git_only_measurability_sources")])


# ------------------------------------------------------------------ 8.4 · Q onboarding-speed

def fig_8_4(x):
    reps = x["repos"]
    store = ITEM_STORE_FROM

    def chart(s, box):
        from datetime import date
        fig, ax = F.fig(8.35, 5.6)
        ys = list(range(len(reps)))[::-1]
        for y, r in zip(ys, reps):
            if r["first"] < store:
                gap = (date.fromisoformat(store) - date.fromisoformat(r["first"])).days
                ax.barh(y, gap, left=0, height=0.62, color=F.GREY_LIGHT, alpha=0.6, hatch="////",
                        edgecolor="white", linewidth=0, zorder=1)
            xi = r["item_real"]
            if xi is not None:
                ax.plot([r["skills"], xi], [y, y], color=F.GREY, linewidth=2, zorder=2)
                ax.plot([xi], [y], "o", color=F.PINK, markersize=8, zorder=4)
                ax.annotate(f"{xi} d", (xi, y), xytext=(7, -3), textcoords="offset points", fontsize=8.5, color=F.BODY)
            else:
                ax.plot([r["skills"], r["age"]], [y, y], color=F.GREY, linewidth=1.2, linestyle=(0, (2, 3)), zorder=2)
                ax.plot([r["age"]], [y], marker=">", color=F.PINK, markersize=8, markerfacecolor="white", zorder=4)
                ax.annotate(f"none yet ({r['age']} d so far)", (r["age"], y), xytext=(7, -3), textcoords="offset points",
                            fontsize=8.5, color=F.MUTED)
            ax.plot([r["skills"]], [y], "o", color=F.GREY_DARK, markersize=8, zorder=5)
        ax.plot([], [], "o", color=F.GREY_DARK, label="Shared skills (HERO.md)")
        ax.plot([], [], "o", color=F.PINK, label="First work item (not a dependency bump)")
        ax.plot([], [], marker=">", color=F.PINK, markerfacecolor="white", linestyle="none", label="No work item yet (censored)")
        ax.barh([], [], color=F.GREY_LIGHT, hatch="////", label=f"Work-item store did not exist yet (before {dm(store)})")
        ax.legend(loc="lower right", fontsize=8.5)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{r['repo']} · {dm(r['first'])}" for r in reps])
        ax.set_ylim(-0.7, len(reps) - 0.3)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel(f"Days since the repo's first commit (n = {len(reps)} repos created after skills existed, 7 Mar)")
        png = F.save(fig, F.asset("8.4"))
        F.picture(s, box, png)

    after = [r for r in reps if r["first"] >= "2026-07-05"]
    F.summary("8.4", question="For each new repository, how long elapsed from creation to mandatory factory setup and to the first "
                              "meaningful planned work, including censored cases, and which mechanism explains the gap?",
              params={"population": f"repos with a first commit on or after 7 Mar 2026 (skills existed), n = {x['n']}",
                      "origin": "the repo's first commit on main", "setup": "first commit that adds HERO.md",
                      "planned_work": "first work item that is not a Dependabot bump (frontmatter bot absent)",
                      "censoring": f"no work item yet = right-censored at the repo's age on {x['today']}; repos created before the "
                                   f"store began ({dm(store)}) are marked, since their first item could not precede it",
                      "median": "middle of the ordered values with censored repos placed at their age (Kaplan–Meier on 9 rows)"},
              columns=["repo", "created", "category", "days_to_skills", "hero_in_first_commit", "days_to_first_item", "days_to_first_non_bump_item",
                       "first_item_origin", "age_days", "censored"],
              table=[[r["repo"], r["first"], r["category"], r["skills"], r["hero_in_first_commit"], r["item_any"], r["item_real"],
                      r["item_origin"], r["age"], r["censored"]] for r in reps],
              notes=f"Skills within {x['skills_max']} days for all {x['n']}; {x['skills_in_first_commit']} had HERO.md in the first "
                    f"commit (cloned from the template). Repos created after work items existed (5 Jul): {x['n_after_store']}, "
                    f"{x['censored_after_store']} with no item yet; median days to first item {x['median_item_days']}"
                    f"{' (censored)' if x['median_is_censored'] else ''}; observed IQR {x['observed_iqr']}. First-item origins: {dict(x['origins'])}.",
              sources=["git.commits", "git.commit_files", "plans.plan_items"])
    return dict(
        question="For each repo created after the factory existed, how many days passed from its first commit to the shared "
                 "skills and to its first planned work item, with the repos that have none yet shown, and what explains the gap?",
        title=(f"All {x['n']} repos created after March had the shared skills within {x['skills_max']} days ({x['skills_in_first_commit']} "
               f"in their first commit); the first work item took a median {x['median_item_days']} days in the {x['n_after_store']} repos "
               f"created after the store existed, and {x['censored_after_store']} has none after {max(r['age'] for r in after if r['item_real'] is None)} days"),
        points=[f"Skills arrive with the clone: HERO.md was in the first commit of {x['skills_in_first_commit']} of {x['n']} repos.",
                f"Work items arrive when the owner runs a planning skill there: {x['origins'].get('wayfare', 0)} first items were written by "
                f"plan-sync, {x['origins'].get('harden', 0)} by the audit, {x['origins'].get('one-shot', 0)} by a one-shot task.",
                f"Hatched: the store did not exist before {dm(store)}, so the {sum(1 for r in reps if r['first'] < store)} older repos' "
                f"first-item lag is a lower bound. Observed lags range {x['observed_iqr'][0]} to {x['observed_iqr'][1]} days (IQR)."],
        chart=chart,
        source="git: first commit and HERO.md history · .plans work items (origin, Dependabot flag)",
        note=notes("Figure 8.4. One row per repo created on or after 7 Mar 2026 (the day the skills plugin existed), oldest at "
                   "the top; x is days since the repo's first commit. Dark grey: the commit that added HERO.md (0 = in the "
                   "first commit). Pink: the first work item that is not a Dependabot bump. A hollow arrow is a repo with "
                   "no work item yet, drawn at its age today (right-censored). The hatched span is the time before the "
                   "work-item store existed (23 Jul), during which no item could be written.",
                   "The mechanism: skills are part of the template, so a clone has them at creation; work items are written "
                   "only when the owner runs sync-plan, the audit or a one-shot task in that repo, so they wait for the "
                   "owner's attention. Undeployed apps are deliberate (owner, 24 Sep): the clones' idle weeks are a choice.",
                   "Days measured from creation, not from the day the capability existed (the earlier card), so older "
                   f"repos read as slower here and are marked. Repos created before {dm(store)}: "
                   + ", ".join(r["repo"] for r in reps if r["first"] < store) + ".",
                   "Hypothesis (new): held for the first stage only.",
                   f"Code: {CODE}:q_onboarding_speed_dumbbell"))
