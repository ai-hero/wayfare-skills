"""Chapter 2 series that evolve over time: weekly from 1 Jan, per repo by month.

Every function returns what one answer slide (and, where useful, its per-repo
breakdown slide) plots. Weeks and months run from 1 Jan 2026 to the latest
commit; the factory's milestones are drawn over them by the deck.
"""
import csv
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from record import (CATEGORIES, STAGES, adoption, changeset_facts, commit_facts,  # noqa: E402
                       rows, week_of, weekly)

LATEST_WEEK = 39
WEEKS = [f"2026-W{w:02d}" for w in range(1, LATEST_WEEK + 1)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
SESSIONS_FROM_WEEK = "2026-W32"
# No Claude Code sessions are logged 10–24 Aug: session-derived weeks are unknown, not zero.
GAP_WEEKS = {"2026-W33", "2026-W34"}
SESSION_GAP = [("2026-08-10", "Session data not available (10–24 Aug)")]
APPS = ("app", "app, no features yet")

# Changes to the factory made to save cost or time, from wayfare-skills' history.
COST_EVENTS = [
    ("2026-08-29", "Scripted gates before the model (#65)"),
    ("2026-08-29", "Concurrent goals, fan-out (#67)"),
    ("2026-09-23", "budget_max is a checkpoint (#116)"),
    ("2026-09-24", "Build every task, verify once (#120)"),
]
FORMAT_EVENTS = [
    ("2026-07-05", "plan-work/ store"),
    ("2026-07-22", ".plans/ store"),
    ("2026-08-30", "Plan file as state (#69)"),
    ("2026-09-20", "Plan standard, schema 1 (#105)"),
]


def median(v):
    return round(statistics.median(v), 1) if v else None


def mean(v):
    return round(statistics.mean(v), 2) if v else None


def per_week(facts, value, weeks=WEEKS):
    by = defaultdict(list)
    for f in facts:
        by[f["week"]].append(value(f))
    return by


def by_repo_month(facts, value, agg, repos=None):
    by = defaultdict(lambda: defaultdict(list))
    for f in facts:
        by[f["repo"]][f["month"]].append(value(f))
    repos = repos or sorted(by, key=lambda r: -sum(len(v) for v in by[r].values()))
    return {r: [agg(by[r][m]) if by[r][m] else None for m in MONTHS] for r in repos}


def app_repos(con, n=None):
    a = adoption(con)
    out = sorted((r for r in a if a[r]["category"] in APPS), key=lambda r: -a[r]["n"])
    return out[:n] if n else out


# ---------------------------------------------------------------- Q design-md-staleness

def q_design_md_staleness_design(con):
    """Weekly: how many repos' DESIGN.md is current, stale or missing (change sets since its last update)."""
    touch = defaultdict(list)
    for r in rows(con, """SELECT c.repo, c.day FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha
                          WHERE f.path='DESIGN.md'"""):
        touch[r["repo"]].append(r["day"])
    sets = defaultdict(list)
    for f in changeset_facts(con):
        if not f["dependabot"]:
            sets[f["repo"]].append(f["day"])
    ad = adoption(con)
    repos = [r for r in ad if ad[r]["category"] in APPS]
    cats = ["Current (0–3 behind)", "Stale (4–20)", "Very stale (20+)", "No DESIGN.md"]
    series = {c: [0] * len(WEEKS) for c in cats}
    behind = {r: [None] * len(WEEKS) for r in repos}
    for i, w in enumerate(WEEKS):
        end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
        for r in repos:
            if ad[r]["first"] > end:
                continue
            last = max((d for d in touch[r] if d <= end), default=None)
            if not last:
                series["No DESIGN.md"][i] += 1
                continue
            n = sum(1 for d in sets[r] if last < d <= end)
            behind[r][i] = n
            series[cats[0] if n <= 3 else cats[1] if n <= 20 else cats[2]][i] += 1
    now = {r: behind[r][-1] for r in repos}
    return {"weeks": WEEKS, "series": series, "behind": behind, "now": now}


# ---------------------------------------------------------------- Q cost-saving-changes

def q_cost_saving_changes(con):
    """Weekly harness spend and spend per change set, from when session logs start."""
    spend = {r["week"]: r["usd"] for r in rows(con, "SELECT week, SUM(cost_usd) usd FROM harness.sessions GROUP BY week")}
    sets = per_week([f for f in changeset_facts(con) if not f["dependabot"]], lambda f: 1)
    per_set = [round(spend[w] / len(sets[w]), 2) if spend.get(w) and sets.get(w) else None for w in WEEKS]
    by_repo = defaultdict(lambda: defaultdict(float))
    for r in rows(con, "SELECT repo, week, cost_usd FROM harness.sessions"):
        by_repo[r["repo"]][r["week"]] += r["cost_usd"] or 0
    top = sorted(by_repo, key=lambda r: -sum(by_repo[r].values()))[:8]
    weeks = [w for w in WEEKS if w >= SESSIONS_FROM_WEEK]
    return {"weeks": WEEKS, "spend": [round(spend.get(w, 0)) for w in WEEKS], "per_set": per_set,
            "total": round(sum(spend.values())), "events": COST_EVENTS,
            "repo_weeks": weeks,
            "by_repo": {r: [None if w in GAP_WEEKS else round(by_repo[r].get(w, 0)) for w in weeks] for r in top}}


# ---------------------------------------------------------------- Q work-item-format

def q_work_item_format(con):
    """Weekly work items created, by the format they were written in."""
    items = rows(con, "SELECT repo, day, schema_era FROM plans.plan_items WHERE day IS NOT NULL AND type != 'goal'")
    ad = adoption(con)
    items = [dict(i, week=week_of(i["day"])) for i in items if i["repo"] in ad]
    series = weekly(items, lambda i: "New format" if i["schema_era"] == "new" else "Old format", weeks=WEEKS,
                    cats=["New format", "Old format"])
    last = {}
    for i in sorted(items, key=lambda i: i["day"]):
        last[i["repo"]] = i["schema_era"]
    return {"weeks": WEEKS, "series": series, "events": FORMAT_EVENTS,
            "still_old": sorted(r for r, e in last.items() if e != "new"),
            "old_items": sum(1 for i in items if i["schema_era"] != "new"), "items": len(items)}


# ---------------------------------------------------------------- Q commit-message-style

def q_commit_message_style(con):
    cf = [c for c in commit_facts(con) if c["actor"] != "bot"]
    wk = per_week(cf, lambda c: c)
    conv = [round(sum(c["conventional"] for c in wk[w]) / len(wk[w]), 3) if len(wk[w]) >= 3 else None for w in WEEKS]
    length = [mean([len(c["subject"]) for c in wk[w]]) if len(wk[w]) >= 3 else None for w in WEEKS]
    body = [mean([len(c["body"]) for c in wk[w]]) if len(wk[w]) >= 3 else None for w in WEEKS]
    sentence = [c for c in cf if not c["conventional"] and c["day"] >= "2026-09-01"]
    repos = [r for r in adoption(con) if adoption(con)[r]["category"] != "out of scope"]
    by_repo = by_repo_month(cf, lambda c: c["conventional"], lambda v: round(sum(v) / len(v), 3),
                            repos=[r for r in app_repos(con, 6)] + ["wayfare-skills", "hero-template"])
    titles = rows(con, "SELECT repo, month, title FROM github.prs WHERE merged_ts IS NOT NULL AND head_ref NOT LIKE 'dependabot/%'")
    from ingest.git import CONV_RE
    title_share = lambda repo_filter: [
        (lambda ts: round(sum(bool(CONV_RE.match(t["title"] or "")) for t in ts) / len(ts), 3) if len(ts) >= 3 else None)(
            [t for t in titles if t["month"] == m and repo_filter(t["repo"])]) for m in MONTHS]
    return {"weeks": WEEKS, "conventional": conv, "subject_len": length, "body_len": body,
            "pr_titles_skills": title_share(lambda r: r == "wayfare-skills"),
            "pr_titles_rest": title_share(lambda r: r != "wayfare-skills" and r in adoption(con)),
            "conv_all": round(sum(c["conventional"] for c in cf) / len(cf), 3),
            "sept_sentence_by_repo": dict(sorted(((r, sum(1 for c in sentence if c["repo"] == r)) for r in
                                                  {c["repo"] for c in sentence}), key=lambda x: -x[1])),
            "by_repo": by_repo}


# ---------------------------------------------------------------- Q change-set-size-over-time

def q_change_set_size_over_time(con):
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    wk = {c: per_week([f for f in cs if f["category"] == c], lambda f: f["lines"]) for c in CATEGORIES}
    series = {c: [median(wk[c][w]) if len(wk[c][w]) >= 5 else None for w in WEEKS] for c in CATEGORIES}
    by_stage = {s: median([f["lines"] for f in cs if f["stage"] == s and f["category"] in APPS]) for s in STAGES}
    return {"weeks": WEEKS, "series": series, "by_stage": by_stage,
            "by_category": {c: median([f["lines"] for f in cs if f["category"] == c]) for c in CATEGORIES},
            "by_repo": by_repo_month([f for f in cs if f["category"] in APPS], lambda f: f["lines"], median,
                                     repos=app_repos(con, 8))}


# ---------------------------------------------------------------- Q weekly-change-sets-by-stage

def q_weekly_change_sets_by_stage(con):
    cs = changeset_facts(con)
    key = lambda f: "Dependabot" if f["dependabot"] else {"app": "Apps", "app, no features yet": "Apps, no features yet",
                                                          "allied": "Allied repos"}[f["category"]]
    cats = ["Apps", "Apps, no features yet", "Allied repos", "Dependabot"]
    series = weekly(cs, key, weeks=WEEKS, cats=cats)
    monthly = defaultdict(lambda: defaultdict(int))
    for f in cs:
        if not f["dependabot"] and f["category"] in APPS:
            monthly[f["repo"]][f["month"]] += 1
    reps = app_repos(con, 8)
    return {"weeks": WEEKS, "series": series, "by_repo": {r: [monthly[r].get(m, 0) for m in MONTHS] for r in reps},
            "by_stage_per_week": {s: round(sum(1 for f in cs if f["stage"] == s and f["category"] == "app" and not f["dependabot"])
                                           / max(1, len({(f["repo"], f["week"]) for f in cs if f["stage"] == s and f["category"] == "app"})), 1)
                                  for s in STAGES}}


# ---------------------------------------------------------------- Q commit-authors

def q_commit_authors(con):
    cf = commit_facts(con)
    series = weekly(cf, lambda c: {"agent": "Agent co-authored", "human": "Human only", "bot": "Bot"}[c["actor"]],
                    weeks=WEEKS, cats=["Agent co-authored", "Human only", "Bot"])
    human = [c for c in cf if c["actor"] != "bot"]
    by_repo = by_repo_month(human, lambda c: c["actor"] == "agent", lambda v: round(sum(v) / len(v), 3),
                            repos=app_repos(con, 6) + ["wayfare-skills", "infrastructure-root"])
    share = lambda xs: round(sum(c["actor"] == "agent" for c in xs) / len(xs), 3) if xs else None
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo,
            "agent_share_by_month": [share([c for c in human if c["month"] == m]) for m in MONTHS]}


# ---------------------------------------------------------------- Q grouping-rater-agreement

def q_grouping_rater_agreement(con):
    try:
        rs = rows(con, "SELECT * FROM detectors.cs_agreement")
    except sqlite3.OperationalError as e:
        print(f"ch2: {e}; Q grouping-rater-agreement agreement unavailable", file=sys.stderr)
        return {"months": MONTHS, "exact": [None] * len(MONTHS), "pairs": [None] * len(MONTHS), "n": 0}
    by = defaultdict(list)
    for r in rs:
        by[r["month"]].append(r)
    exact = [round(sum(r["n_a"] == r["n_b"] for r in by[m]) / len(by[m]), 3) if by[m] else None for m in MONTHS]
    pairs = [round(statistics.mean(r["pair_agreement"] for r in by[m]), 3) if by[m] else None for m in MONTHS]
    return {"months": MONTHS, "exact": exact, "pairs": pairs, "n": len(rs),
            "exact_all": round(sum(r["n_a"] == r["n_b"] for r in rs) / len(rs), 3) if rs else None,
            "pairs_all": round(statistics.mean(r["pair_agreement"] for r in rs), 3) if rs else None,
            "b_more": sum(r["n_b"] > r["n_a"] for r in rs), "a_more": sum(r["n_a"] > r["n_b"] for r in rs),
            "counts": [len(by[m]) for m in MONTHS]}


# ---------------------------------------------------------------- Q spend-attribution-chain

def q_spend_attribution_chain(con):
    items = {(r["repo"], r["branch"]) for r in (
        {"repo": x["repo"], "branch": json.loads(x["j"] or "{}").get("branch")}
        for x in rows(con, "SELECT repo, raw_frontmatter_json j FROM plans.plan_items")) if r["branch"]}
    cats = ["Session names its PR", "One branch, an item's", "One branch, no item", "Several branches"]
    acc = defaultdict(lambda: defaultdict(float))
    for s in rows(con, "SELECT repo, week, cost_usd, git_branches, pr_links FROM harness.sessions"):
        branches = [b for b in json.loads(s["git_branches"] or "[]") if b not in ("main", "master", "HEAD")]
        if s["pr_links"] not in (None, "", "[]"):
            c = cats[0]
        elif len(branches) == 1:
            c = cats[1] if (s["repo"], branches[0]) in items else cats[2]
        else:
            c = cats[3]
        acc[c][s["week"]] += s["cost_usd"] or 0
    series = {c: [None if w in GAP_WEEKS else round(acc[c].get(w, 0)) for w in WEEKS] for c in cats}
    tot = {c: sum(v for v in vals if v) for c, vals in series.items()}
    return {"weeks": WEEKS, "series": series, "totals": tot, "total": sum(tot.values())}


# ---------------------------------------------------------------- Q reviewer-disagreement

def q_reviewer_disagreement(con):
    prs = defaultdict(lambda: {"a": 0, "c": 0})
    for r in rows(con, "SELECT p.repo, p.number, p.week, r.state FROM github.prs p JOIN github.pr_reviews r "
                       "ON r.repo=p.repo AND r.number=p.number WHERE p.head_ref NOT LIKE 'dependabot/%'"):
        k = (r["repo"], r["number"], r["week"])
        prs[k]["a"] += r["state"] == "APPROVED"
        prs[k]["c"] += r["state"] == "CHANGES_REQUESTED"
    wk = defaultdict(list)
    for (repo, n, w), v in prs.items():
        if repo in adoption(con):
            wk[w].append(v["a"] > 0 and v["c"] > 0)
    disagree = [round(sum(wk[w]) / len(wk[w]), 3) if len(wk[w]) >= 5 else None for w in WEEKS]
    try:
        tags = rows(con, "SELECT t.*, p.week FROM detectors.review_topics t JOIN github.prs p "
                         "ON p.repo=t.repo AND p.number=t.number")
    except sqlite3.OperationalError as e:
        print(f"ch2: {e}; review-topic shares unavailable", file=sys.stderr)
        tags = []
    tw = defaultdict(list)
    for t in tags:
        tw[t["week"]].append(t)
    security = [round(sum(t["security"] for t in tw[w]) / len(tw[w]), 3) if len(tw[w]) >= 5 else None for w in WEEKS]
    return {"weeks": WEEKS, "disagree": disagree, "security": security, "tagged": len(tags),
            "security_n": sum(t["security"] for t in tags),
            "security_blocking": sum(t["security"] and t["state"] == "CHANGES_REQUESTED" for t in tags),
            "security_severity": dict(sorted(((s, sum(1 for t in tags if t["security"] and t["severity"] == s))
                                              for s in {t["severity"] for t in tags if t["security"]}), key=lambda x: -x[1])),
            "disagree_all": round(sum(sum(v) for v in wk.values()) / max(1, sum(len(v) for v in wk.values())), 3)}


# ---------------------------------------------------------------- Q inferred-link-accuracy

def q_inferred_link_accuracy_links(con, spotcheck_path=None):
    from links import set_item_links
    main = rows(con, "SELECT repo, week, pr_number FROM git.commits WHERE is_merge=0")
    ad = adoption(con)
    wk = defaultdict(list)
    for m in main:
        if m["repo"] in ad:
            wk[m["week"]].append(m["pr_number"] is not None)
    commit_pr = [round(sum(wk[w]) / len(wk[w]), 3) if wk[w] else None for w in WEEKS]
    links, _ = set_item_links(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    wk2 = defaultdict(list)
    for f in cs:
        wk2[f["week"]].append(bool(links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))))
    set_item = [round(sum(wk2[w]) / len(wk2[w]), 3) if wk2[w] else None for w in WEEKS]
    wk3 = defaultdict(list)
    for s in rows(con, "SELECT week, pr_links FROM harness.sessions"):
        wk3[s["week"]].append(s["pr_links"] not in (None, "", "[]"))
    sess_pr = [round(sum(wk3[w]) / len(wk3[w]), 3) if len(wk3[w]) >= 3 else None for w in WEEKS]
    if spotcheck_path:
        import random
        rnd = random.Random(7)
        sample = [f for f in cs if links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))]
        with open(spotcheck_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["link_type", "repo", "pr", "change_set", "linked_items", "correct (y/n)"])
            for f in rnd.sample(sample, min(30, len(sample))):
                w.writerow(["change set -> work item", f["repo"], f["pr"], f["label"],
                            " ".join(sorted(links[(f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])])), ""])
    return {"weeks": WEEKS, "series": {"Commit on main → PR": commit_pr, "Change set → work item": set_item,
                                       "Session → PR": sess_pr}}


# ---------------------------------------------------------------- Q counting-units-compared (evolving counts)

def q_counting_units_compared_counts(con):
    cf = commit_facts(con)
    main = rows(con, "SELECT repo, week FROM git.commits WHERE is_merge=0")
    ad = adoption(con)
    m = defaultdict(int)
    for r in main:
        if r["repo"] in ad:
            m[r["week"]] += 1
    orig = defaultdict(int)
    for c in cf:
        orig[week_of(c["merged_day"])] += 1
    sets = defaultdict(int)
    for f in changeset_facts(con):
        sets[f["week"]] += 1
    return {"weeks": WEEKS, "series": {"Commits on main": [m.get(w, 0) for w in WEEKS],
                                       "Original commits": [orig.get(w, 0) for w in WEEKS],
                                       "Change sets": [sets.get(w, 0) for w in WEEKS]}}


# ---------------------------------------------------------------- Q reviewer-by-stage

def q_reviewer_by_stage(con):
    """Merged PRs by who reviewed them. A review under the owner's account is often an agent's;
    Chapter 5's actors.human_reviews tells a person's review from an agent's."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "owner_actors", os.path.join(os.path.dirname(os.path.abspath(__file__)), "owner", "actors.py"))
    actors = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(actors)
    human = actors.human_reviews(con)
    rs = rows(con, """SELECT p.repo, p.number, p.merged_ts, p.week, p.head_ref, COUNT(r.number) n_reviews
                      FROM github.prs p LEFT JOIN github.pr_reviews r ON r.repo=p.repo AND r.number=p.number
                      WHERE p.merged_ts IS NOT NULL GROUP BY p.repo, p.number""")
    ad = adoption(con)
    rs = [r for r in rs if r["repo"] in ad and not (r["head_ref"] or "").startswith("dependabot/")]
    cat = lambda r: ("A person reviewed" if human.get((r["repo"], r["number"])) else
                     "Agents or bots only" if r["n_reviews"] else "No review")
    series = weekly(rs, cat, weeks=WEEKS, cats=["A person reviewed", "Agents or bots only", "No review"])
    return {"weeks": WEEKS, "series": series, "n": len(rs),
            "human": sum(1 for r in rs if cat(r) == "A person reviewed"),
            "none": sum(1 for r in rs if cat(r) == "No review")}


# ---------------------------------------------------------------- Q commits-per-change-set (evolving)

def q_commits_per_change_set_evolving(con):
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    wk = per_week(cs, lambda f: f["n_commits"])
    member = defaultdict(int)
    for f in cs:
        for sha in f["shas"]:
            member[(f["repo"], sha)] += 1
    cf = [c for c in commit_facts(con) if c["actor"] != "bot"]
    multi = per_week(cf, lambda c: member.get((c["repo"], c["sha"]), 0) > 1)
    return {"weeks": WEEKS,
            "commits_per_set": [mean(wk[w]) if len(wk[w]) >= 3 else None for w in WEEKS],
            "multi_share": [round(sum(multi[w]) / len(multi[w]), 3) if len(multi[w]) >= 5 else None for w in WEEKS]}


# ---------------------------------------------------------------- Q change-sets-per-pr

def q_change_sets_per_pr(con):
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["pr"]]
    per_pr = defaultdict(int)
    meta = {}
    for f in cs:
        per_pr[(f["repo"], f["pr"])] += 1
        meta[(f["repo"], f["pr"])] = f
    prs = [dict(meta[k], sets=v) for k, v in per_pr.items()]
    series = {}
    for c, name in (("app", "Apps"), ("app, no features yet", "Apps, no features yet"), ("allied", "Allied repos")):
        wk = per_week([p for p in prs if p["category"] == c], lambda p: p["sets"])
        series[name] = [mean(wk[w]) if len(wk[w]) >= 3 else None for w in WEEKS]
    by_stage = {s: mean([p["sets"] for p in prs if p["stage"] == s and p["category"] in APPS]) for s in STAGES}
    return {"weeks": WEEKS, "series": series, "by_stage": by_stage,
            "by_repo": by_repo_month([p for p in prs if p["category"] in APPS], lambda p: p["sets"], mean,
                                     repos=app_repos(con, 8)),
            "one_share": round(sum(1 for p in prs if p["sets"] == 1) / len(prs), 3)}


# ---------------------------------------------------------------- Q observable-work-share (observability)

def q_observable_work_share(con):
    from links import set_item_links
    links, _ = set_item_links(con)
    session_prs = set()
    for r in rows(con, "SELECT pr_links FROM harness.sessions WHERE pr_links NOT IN ('', '[]')"):
        for link in json.loads(r["pr_links"]):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
            if m:
                session_prs.add((m.group(1).replace("hero-skills", "wayfare-skills"), int(m.group(2))))
    cats = ["Planned: a work item", "One-shot, session logged", "One-shot, no record", "Pushed to main", "Dependabot"]

    def kind(f):
        if f["dependabot"]:
            return cats[4]
        if links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])):
            return cats[0]
        if f["unit_kind"] == "push":
            return cats[3]
        return cats[1] if (f["repo"], f["pr"]) in session_prs else cats[2]
    cs = changeset_facts(con)
    series = weekly(cs, kind, weeks=WEEKS, cats=cats)
    since = [f for f in cs if f["week"] >= SESSIONS_FROM_WEEK and not f["dependabot"] and f["week"] not in GAP_WEEKS]
    share = {c: round(sum(1 for f in since if kind(f) == c) / len(since), 3) for c in cats[:4]} if since else {}
    return {"weeks": WEEKS, "series": series, "share_since_sessions": share}


# ---------------------------------------------------------------- Q crediting-factory-changes

def q_crediting_factory_changes(con):
    """Change sets per repo-week, aligned on the week each repo took up work items and goals."""
    ad = adoption(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    per = defaultdict(int)
    for f in cs:
        per[(f["repo"], f["week"])] += 1
    rel = list(range(-6, 7))
    out, n_repos = {}, {}
    for piece, name in (("items", "Took up work items"), ("goals", "Took up goals")):
        vals = defaultdict(list)
        repos = [r for r in ad if ad[r][piece] and ad[r]["category"] in APPS]
        for r in repos:
            y, w0, _ = date.fromisoformat(ad[r][piece]).isocalendar()
            for k in rel:
                d = date.fromisocalendar(2026, w0, 1) + timedelta(weeks=k)
                if ad[r]["first"] <= d.isoformat() <= ad[r]["last"]:
                    y2, w2, _ = d.isocalendar()
                    vals[k].append(per.get((r, f"{y2}-W{w2:02d}"), 0))
        out[name] = [mean(vals[k]) for k in rel]
        n_repos[name] = len(repos)
    return {"rel": rel, "series": out, "n_repos": n_repos}


# ---------------------------------------------------------------- Q app-ranking-by-unit

def q_app_ranking_by_unit(con):
    """Monthly: how closely the app ranking by lines, commits and PRs follows the ranking by change sets."""
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["category"] in APPS]
    main = rows(con, "SELECT repo, month, insertions + deletions churn, pr_number FROM git.commits WHERE is_merge = 0")
    ad = adoption(con)

    def rank_corr(a, b):
        keys = [k for k in a if k in b]
        if len(keys) < 4:
            return None
        ra = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -a[k]))}
        rb = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -b[k]))}
        n = len(keys)
        return round(1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in keys) / (n * (n * n - 1)), 2)
    out = {"Lines": [], "Commits": [], "PRs": []}
    for m in MONTHS:
        sets = defaultdict(int)
        for f in cs:
            if f["month"] == m:
                sets[f["repo"]] += 1
        lines, commits, prs = defaultdict(int), defaultdict(int), defaultdict(set)
        for r in main:
            if r["month"] == m and r["repo"] in ad and ad[r["repo"]]["category"] in APPS:
                lines[r["repo"]] += r["churn"] or 0
                commits[r["repo"]] += 1
                if r["pr_number"]:
                    prs[r["repo"]].add(r["pr_number"])
        out["Lines"].append(rank_corr(lines, sets))
        out["Commits"].append(rank_corr(commits, sets))
        out["PRs"].append(rank_corr({k: len(v) for k, v in prs.items()}, sets))
    return {"months": MONTHS, "series": out}


# ---------------------------------------------------------------- Q where-rework-is-caught

FIXUP_RE = re.compile(r"\b(address|review|self-review|copilot|lint|format|nit|fixup|typo|feedback|findings)\b", re.I)


def q_where_rework_is_caught(con):
    """Per 100 change sets per week: fix-up commits inside the PR (Chapter 10's labels), catches by a
    gate, and PRs whose lines a later fix repaired within 7 days of merge (Chapter 10's SZZ trace)."""
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    sets_wk = per_week(cs, lambda f: 1)
    ad = adoption(con)
    in_pr = defaultdict(int)
    for r in rows(con, "SELECT repo, day FROM mistakes.commit_labels WHERE fixup = 1"):
        if r["repo"] in ad and r["day"]:
            in_pr[week_of(r["day"])] += 1
    gate = defaultdict(int)
    for r in rows(con, "SELECT g.ts, g.repo FROM detectors.gate_firings g WHERE g.verdict IN ('CHANGES_REQUESTED','caught')"):
        if r["ts"] and r["repo"] in ad:
            gate[week_of(r["ts"][:10])] += 1
    fixed_in = {}
    for r in rows(con, "SELECT repo, intro_unit, lifetime_days FROM mistakes.szz WHERE outcome = 'traced'"):
        if r["intro_unit"] and r["intro_unit"].startswith("pr:") and r["repo"] in ad:
            k = (r["repo"], int(r["intro_unit"][3:]))
            fixed_in[k] = min(fixed_in.get(k, 1e9), r["lifetime_days"])
    merged = {(r["repo"], r["number"]): r["merged_ts"][:10] for r in rows(
        con, "SELECT repo, number, merged_ts FROM github.prs WHERE merged_ts IS NOT NULL")}
    after = defaultdict(int)
    for k, days in fixed_in.items():
        if days <= 7 and k in merged:
            after[week_of(merged[k])] += 1
    rate = lambda d: [round(100 * d.get(w, 0) / len(sets_wk[w]), 1) if len(sets_wk[w]) >= 5 else None for w in WEEKS]
    return {"weeks": WEEKS, "series": {"Fix-up commits inside the PR": rate(in_pr),
                                       "Caught by a gate": rate(gate),
                                       "PR fixed within 7 days of merge": rate(after)},
            "totals": {"in_pr": sum(in_pr.values()), "gate": sum(gate.values()), "after": sum(after.values()),
                       "sets": len(cs)}}


def all_evolving(con, spotcheck_path=None):
    out = {}
    for name, fn in list(globals().items()):
        if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__:
            out[name] = fn(con, spotcheck_path) if name.startswith("q_inferred_link_accuracy") else fn(con)
    return out
