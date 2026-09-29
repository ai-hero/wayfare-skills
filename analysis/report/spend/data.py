"""Spend and cost series: spend and cost. One function per question; the deck plots what they return.

Spend runs from 9 Aug (session logs), so spend charts use SPEND_WEEKS (W32 on); CI minutes
run from November 2025, so CI charts use every week of 2026. Dollars are the harness's
API-equivalent cost, never what was billed.
"""
import json
import os
import re
import statistics
from datetime import date
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from record import STAGES, adoption, changeset_facts, rows, week_of  # noqa: E402
from links import _items, set_item_links  # noqa: E402
from spend.attribution import spend_by_changeset, spend_by_pr, spend_rows  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
SPEND_WEEKS = [w for w in WEEKS if w >= "2026-W32"]
# No sessions are logged 10-24 Aug: those weeks are "data not available", never zero spend, and
# stay out of every weekly average and median.
NA_WEEKS = {"2026-W33", "2026-W34"}
FULL_WEEKS = ["2026-W35", "2026-W36", "2026-W37", "2026-W38"]  # fully logged: W32 has one session, W39 ends 25 Sep
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
APPS = ("app", "app, no features yet")
HUNG_DAY = "2026-08-26"

CI_EVENTS = [
    ("2026-07-18", "Shared auto-approve caller (6 repos)"),
    ("2026-08-04", "Shared caller, rest of fleet"),
    ("2026-08-26", "28 runs hang 50-58 h"),
    ("2026-08-29", "Scripted gates before the model"),
    ("2026-09-17", "Cut Actions spend"),
]


def median(v):
    return round(statistics.median(v), 2) if v else None


def mean(v):
    return round(statistics.mean(v), 2) if v else None


def category(con, repo):
    a = adoption(con).get(repo)
    return a["category"] if a else "other"


# ---------------------------------------------------------------- Q weekly-spend

def q_weekly_spend(con):
    by_cat, by_repo, tot = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float)), defaultdict(float)
    for r in rows(con, "SELECT repo, week, cost_usd FROM harness.sessions"):
        c = category(con, r["repo"])
        name = {"app": "Apps", "app, no features yet": "Apps, no features yet", "allied": "Allied repos"}.get(c, "Fleet folder")
        by_cat[name][r["week"]] += r["cost_usd"] or 0
        by_repo[r["repo"]][r["week"]] += r["cost_usd"] or 0
        tot[r["repo"]] += r["cost_usd"] or 0
    cats = ["Apps", "Apps, no features yet", "Allied repos"]
    top = sorted(tot, key=lambda r: -tot[r])[:6]
    n = con.execute("SELECT COUNT(*), SUM(cost_usd), MIN(day), MAX(day) FROM harness.sessions").fetchone()
    week_tot = {w: sum(by_cat[c].get(w, 0) for c in by_cat) for w in WEEKS}
    return {"series": {c: [round(by_cat[c].get(w, 0)) for w in WEEKS] for c in cats},
            "by_repo": {r: [round(by_repo[r].get(w, 0)) for w in SPEND_WEEKS] for r in top},
            "repo_total": {r: round(tot[r]) for r in sorted(tot, key=lambda r: -tot[r])},
            "sessions": n[0], "total": round(n[1]), "first": n[2], "last": n[3],
            "cat_total": {c: round(sum(by_cat[c].values())) for c in by_cat},
            "peak_week": max(SPEND_WEEKS, key=lambda w: week_tot[w]), "week_tot": {w: round(week_tot[w]) for w in SPEND_WEEKS}}


# ---------------------------------------------------------------- Q traceable-spend

TARGETS = [("pr", "Its branch's merged PR"), ("pr_linked", "A PR the session opened (spent on main)"),
           ("dependabot", "Dependabot PRs"), ("unmerged", "A PR never merged"), ("no_pr", "A branch with no PR"),
           ("default", "Main, no PR (planning, questions)")]


def q_traceable_spend(con):
    wk, repo = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for r in spend_rows(con):
        wk[r["target"]][r["week"]] += r["usd"]
        repo[r["repo"]][r["target"]] += r["usd"]
    tot = {t: sum(wk[t].values()) for t, _ in TARGETS}
    all_ = sum(tot.values())
    week_all = {w: sum(wk[t].get(w, 0) for t, _ in TARGETS) for w in SPEND_WEEKS}
    series = {name: [wk[t].get(w, 0) / week_all[w] if week_all[w] else None for w in SPEND_WEEKS] for t, name in TARGETS}
    repos = sorted(repo, key=lambda r: -sum(repo[r].values()))[:10]
    reached = lambda d: (d["pr"] + d["pr_linked"] + d["dependabot"]) / sum(d.values())
    by_repo = {name: [repo[r][t] / sum(repo[r].values()) for r in repos] for t, name in TARGETS}
    bp = spend_by_pr(con)
    merged = rows(con, "SELECT repo, number, author FROM github.prs WHERE merged_ts >= '2026-08-10'")
    own = [m for m in merged if "dependabot" not in (m["author"] or "")]
    multi = con.execute("SELECT SUM(cost_usd) FROM detectors.session_spend WHERE attribution_confidence='multi_branch'").fetchone()[0]
    return {"series": series, "share": {t: tot[t] / all_ for t, _ in TARGETS}, "usd": {t: round(tot[t]) for t, _ in TARGETS},
            "total": round(all_), "reached": (tot["pr"] + tot["pr_linked"] + tot["dependabot"]) / all_,
            "repos": repos, "by_repo": by_repo, "reached_by_repo": {r: round(reached(repo[r]), 3) for r in repos},
            "prs_since": len(own), "prs_with_spend": sum((m["repo"], m["number"]) in bp for m in own),
            "multi_branch_usd": round(multi or 0)}


# ---------------------------------------------------------------- Q change-set-cost-trend

def _sets(con):
    return [f for f in spend_by_changeset(con) if not f["dependabot"] and f["week"] in SPEND_WEEKS]


def q_change_set_cost_trend_per_set(con):
    cs = _sets(con)
    by = defaultdict(list)
    for f in cs:
        by[f["week"]].append(f["usd"])
    ok = lambda w: len(by[w]) >= 10
    stage = {s: [f["usd"] for f in cs if f["stage"] == s] for s in STAGES}
    stage = {s: v for s, v in stage.items() if len(v) >= 20}
    repo = defaultdict(list)
    for f in cs:
        repo[f["repo"]].append(f["usd"])
    repos = sorted((r for r in repo if len(repo[r]) >= 15), key=lambda r: -median(repo[r]))
    first = [w for w in SPEND_WEEKS if ok(w)]
    return {"median": [median(by[w]) if ok(w) else None for w in SPEND_WEEKS],
            "mean": [mean(by[w]) if ok(w) else None for w in SPEND_WEEKS],
            "n": {w: len(by[w]) for w in SPEND_WEEKS},
            "overall_median": median([f["usd"] for f in cs]), "overall_mean": mean([f["usd"] for f in cs]),
            "n_sets": len(cs), "usd": round(sum(f["usd"] for f in cs)),
            "first_week": first[0], "last_week": first[-1],
            "stage_median": {s: median(v) for s, v in stage.items()}, "stage_n": {s: len(v) for s, v in stage.items()},
            "repos": repos, "repo_median": [median(repo[r]) for r in repos], "repo_n": [len(repo[r]) for r in repos],
            "p90": round(sorted(f["usd"] for f in cs)[int(0.9 * len(cs))], 1)}


# ---------------------------------------------------------------- Q cost-rollup

def q_cost_rollup_rollup(con):
    cs = _sets(con)
    links, _ = set_item_links(con)
    goal_of = {(i["repo"], i["item_id"]): i["goal_id"] for i in _items(con) if i["type"] != "goal"}
    goal_ids = {(r["repo"], r["item_id"]) for r in rows(con, "SELECT repo, item_id FROM plans.plan_items WHERE type='goal'")}
    heads = {(r["repo"], r["number"]): r["head_ref"] or "" for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    pr, item, goal = defaultdict(lambda: [0.0, "", 0]), defaultdict(lambda: [0.0, ""]), defaultdict(lambda: [0.0, ""])
    kind = {}
    for f in cs:
        k = (f["repo"], f["pr"])
        pr[k][0] += f["usd"]
        pr[k][1] = max(pr[k][1], f["week"])
        pr[k][2] += 1
        its = links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])) or set()
        gm = re.search(r"goal[-/](\d+)", heads.get(k, ""))
        goals = {(f["repo"], gm.group(1))} if gm and (f["repo"], gm.group(1)) in goal_ids else set()
        for it in its:
            item[(f["repo"], it)][0] += f["usd"] / len(its)
            item[(f["repo"], it)][1] = max(item[(f["repo"], it)][1], f["week"])
            g = goal_of.get((f["repo"], it))
            if g:
                goals.add((f["repo"], str(g)))
        for g in goals:
            goal[g][0] += f["usd"] / len(goals)
            goal[g][1] = max(goal[g][1], f["week"])
        kind[k] = "Goal PR" if goals else "Work-item PR" if its else kind.get(k, "One-shot PR")
    def wk(d, min_n=3):
        by = defaultdict(list)
        for usd, w, *_ in d.values():
            by[w].append(usd)
        return [median(by[w]) if len(by[w]) >= min_n else None for w in SPEND_WEEKS]
    by_set = defaultdict(list)
    for f in cs:
        by_set[f["week"]].append(f["usd"])
    kinds = ["One-shot PR", "Work-item PR", "Goal PR"]
    kusd = {k: [pr[p][0] for p in pr if kind[p] == k] for k in kinds}
    ksets = {k: [pr[p][2] for p in pr if kind[p] == k] for k in kinds}
    return {"series": {"Per change set": [median(by_set[w]) if len(by_set[w]) >= 10 else None for w in SPEND_WEEKS],
                       "Per PR": wk(pr), "Per work item": wk(item), "Per goal": wk(goal)},
            "medians": {"set": median([f["usd"] for f in cs]), "pr": median([v[0] for v in pr.values()]),
                        "item": median([v[0] for v in item.values()]), "goal": median([v[0] for v in goal.values()])},
            "n": {"set": len(cs), "pr": len(pr), "item": len(item), "goal": len(goal)},
            "kinds": kinds, "kind_median": [median(kusd[k]) for k in kinds], "kind_n": [len(kusd[k]) for k in kinds],
            "kind_share": [sum(kusd[k]) / sum(sum(v) for v in kusd.values()) for k in kinds],
            "kind_sets": [mean(ksets[k]) for k in kinds]}


# Book figure 6.5: one window (session logging resumes 25 Aug; change sets end 25 Sep), one price basis.
UNIT_WINDOW = ("2026-08-25", "2026-09-25")


def q_cost_rollup_units(con):
    """Per unit of work (change set, PR, work item, goal): median and IQR of the reported list-price-equivalent cost,
    with the unit's coverage (share of the window's units that reached any attributed spend) and the window's
    spend that reached no merged PR, reported rather than spread."""
    import figure_lib as F
    lo, hi = UNIT_WINDOW
    in_win = lambda d: d is not None and lo <= d[:10] <= hi
    facts = [f for f in changeset_facts(con) if not f["dependabot"] and in_win(f["day"])]
    usd_of = {(f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]): f["usd"]
              for f in spend_by_changeset(con) if not f["dependabot"] and in_win(f["day"])}
    key = lambda f: (f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])
    links, _ = set_item_links(con)
    items = {(i["repo"], i["item_id"]): i for i in _items(con)}
    goal_ids = {(r["repo"], r["item_id"]) for r in rows(con, "SELECT repo, item_id FROM plans.plan_items WHERE type='goal'")}
    heads = {(r["repo"], r["number"]): r["head_ref"] or "" for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    item_usd, item_seen, goal_usd, goal_seen = defaultdict(float), set(), defaultdict(float), set()
    for f in facts:
        usd = usd_of.get(key(f))
        its = links.get(key(f)) or set()
        gm = re.search(r"goal[-/](\d+)", heads.get((f["repo"], f["pr"]), ""))
        goals = {(f["repo"], gm.group(1))} if gm and (f["repo"], gm.group(1)) in goal_ids else set()
        for it in its:
            item_seen.add((f["repo"], it))
            g = (items.get((f["repo"], it)) or {}).get("goal_id")
            if g:
                goals.add((f["repo"], str(g)))
            if usd is not None:
                item_usd[(f["repo"], it)] += usd / len(its)
        for g in goals:
            goal_seen.add(g)
            if usd is not None:
                goal_usd[g] += usd / len(goals)
    # Items closed in the window that no change set links to, in any window: a coverage gap, not a free item.
    # (An item whose change sets merged before the window is counted in that window, not here.)
    ever_linked = {(k[0], it) for k, v in links.items() for it in v}
    done = {(r["repo"], r["item_id"]) for r in rows(con, "SELECT repo, item_id, done_ts FROM plans.plan_items WHERE type != 'goal' "
                                                         "AND status IN ('done', 'delivered', 'accepted')")
            if in_win(r["done_ts"])} - ever_linked
    prs_all = [(r["repo"], r["number"]) for r in rows(con, "SELECT repo, number, merged_ts FROM github.prs WHERE author NOT LIKE '%dependabot%'")
               if in_win(r["merged_ts"]) and category(con, r["repo"]) != "other"]
    bp = spend_by_pr(con)
    pr_vals = [bp[k]["usd"] for k in prs_all if k in bp]
    set_vals = [usd_of[key(f)] for f in facts if key(f) in usd_of]
    units = [("Change set", set_vals, len(facts)),
             ("Pull request", pr_vals, len(prs_all)),
             ("Work item", list(item_usd.values()), len(item_seen) + len(done)),
             ("Goal", list(goal_usd.values()), len(goal_seen))]
    table = []
    for name, vals, n_all in units:
        q1, med, q3 = F.quantiles(vals)
        lo_m, hi_m = F.bootstrap_median(vals)
        table.append({"unit": name, "n_costed": len(vals), "n_units": n_all, "coverage": round(len(vals) / n_all, 3) if n_all else None,
                      "median": round(med, 2), "q1": round(q1, 2), "q3": round(q3, 2), "median_lo": round(lo_m, 2), "median_hi": round(hi_m, 2),
                      "mean": round(sum(vals) / len(vals), 2), "total": round(sum(vals))})
    # Where the window's spend went: what reached a merged PR, and what did not (never spread over units).
    tgt = defaultdict(float)
    for r in spend_rows(con):
        if in_win(r["day"]):
            tgt[r["target"]] += r["usd"]
    total = sum(tgt.values())
    unreached = {"unmerged": tgt["unmerged"], "no_pr": tgt["no_pr"], "default": tgt["default"]}
    return {"window": UNIT_WINDOW, "table": table, "spend_total": round(total),
            "spend_by_target": {k: round(v) for k, v in tgt.items()},
            "unreached_usd": round(sum(unreached.values())), "unreached_share": round(sum(unreached.values()) / total, 3),
            "unreached": {k: round(v) for k, v in unreached.items()},
            "items_never_linked": len(done), "items_linked": len(item_seen),
            "sets_no_pr": sum(1 for f in facts if f["pr"] is None)}


# ---------------------------------------------------------------- Q paid-vs-reported-cost

FAMILIES = ["Opus 5", "Opus 5.5", "Fable 5", "Fable 5.1", "Sonnet 5", "Haiku"]


def q_paid_vs_reported_cost(con):
    wk, tot, sub = defaultdict(lambda: defaultdict(float)), defaultdict(float), defaultdict(float)
    for r in spend_rows(con):
        wk[r["family"]][r["week"]] += r["usd"]
        tot[r["family"]] += r["usd"]
        if r["kind"] == "subagent":
            sub[r["family"]] += r["usd"]
    fams = [f for f in FAMILIES if tot.get(f, 0) > 1]
    cs = _sets(con)
    per = {f: [c["usd"] for c in cs if c["family"] == f] for f in fams}
    per = {f: v for f, v in per.items() if len(v) >= 15}
    first_seen = {f: min((w for w in SPEND_WEEKS if wk[f].get(w, 0) > 1), default=None) for f in fams}
    all_ = sum(tot.values())
    return {"series": {f: [round(wk[f].get(w, 0)) for w in SPEND_WEEKS] for f in fams},
            "share": {f: tot[f] / all_ for f in fams}, "usd": {f: round(tot[f]) for f in fams},
            "sub_share": {f: sub[f] / tot[f] for f in fams if tot[f]},
            "per_set_median": {f: median(v) for f, v in per.items()}, "per_set_n": {f: len(v) for f, v in per.items()},
            "first_seen": first_seen}


# ---------------------------------------------------------------- Q spend-by-model

def sub_kind(t):
    t = t or ""
    if "review" in t or "analyzer" in t or "silent-failure" in t or "simplifier" in t:
        return "Review agents"
    if t in ("Explore", "Plan"):
        return "Explore / Plan"
    if t in ("general-purpose", "claude", "fork", ""):
        return "General-purpose (build, fan-out)"
    return "Other subagents"


SUB_KINDS = ["Main loop", "General-purpose (build, fan-out)", "Review agents", "Explore / Plan", "Other subagents"]


def q_spend_by_model_subagents(con):
    wk, tot = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    for r in spend_rows(con):
        k = "Main loop" if r["kind"] == "main" else sub_kind(r["subagent_type"])
        wk[k][r["week"]] += r["usd"]
        tot[k] += r["usd"]
    week_all = {w: sum(wk[k].get(w, 0) for k in SUB_KINDS) for w in SPEND_WEEKS}
    runs = rows(con, "SELECT subagent_type, COUNT(*) n FROM harness.subagent_runs GROUP BY 1")
    by_type = defaultdict(int)
    for r in runs:
        by_type[r["subagent_type"] or "general-purpose"] += r["n"]
    typ_usd = defaultdict(float)
    for r in spend_rows(con):
        if r["kind"] == "subagent":
            typ_usd[r["subagent_type"]] += r["usd"]
    top = sorted(typ_usd, key=lambda t: -typ_usd[t])[:8]
    all_ = sum(tot.values())
    return {"series": {k: [wk[k].get(w, 0) / week_all[w] if week_all[w] else None for w in SPEND_WEEKS] for k in SUB_KINDS},
            "share": {k: tot[k] / all_ for k in SUB_KINDS}, "usd": {k: round(tot[k]) for k in SUB_KINDS},
            "sub_share_week": {w: 1 - wk["Main loop"].get(w, 0) / week_all[w] for w in SPEND_WEEKS if week_all[w]},
            "types": top, "type_usd": [round(typ_usd[t]) for t in top],
            "type_per_run": [round(typ_usd[t] / by_type[t], 2) if by_type[t] else None for t in top],
            "type_runs": [by_type[t] for t in top], "runs": sum(by_type.values())}


# ---------------------------------------------------------------- Q subagent-spend

def q_subagent_spend(con):
    bp = spend_by_pr(con)
    info = {(r["repo"], r["number"]): r for r in rows(
        con, "SELECT repo, number, additions + deletions churn, merged_ts, author FROM github.prs WHERE merged_ts IS NOT NULL")}
    sec = {(r["repo"], r["number"]) for r in rows(con, "SELECT DISTINCT repo, number FROM detectors.review_topics WHERE security=1")}
    sets = defaultdict(int)
    for f in _sets(con):
        sets[(f["repo"], f["pr"])] += 1
    prs = []
    for k, a in bp.items():
        i = info.get(k)
        if not i or "dependabot" in (i["author"] or "") or not sets.get(k):
            continue
        prs.append({"key": k, "week": week_of(i["merged_ts"][:10]), "review": a["review"], "usd": a["usd"],
                    "churn": i["churn"] or 0, "sets": sets[k], "sec": k in sec})
    prs = [p for p in prs if p["week"] in SPEND_WEEKS]
    reviewed = [p for p in prs if p["review"] > 0.01]
    by = defaultdict(list)
    share = defaultdict(lambda: [0.0, 0.0])
    for p in prs:
        share[p["week"]][0] += p["review"]
        share[p["week"]][1] += p["usd"]
    for p in reviewed:
        by[p["week"]].append(p["review"] / p["sets"])
    buckets = [("< 100 lines", 0, 100), ("100-499", 100, 500), ("500-1,999", 500, 2000), ("2,000+", 2000, 10 ** 9)]
    bsz = {b: [p["review"] for p in reviewed if lo <= p["churn"] < hi] for b, lo, hi in buckets}
    bsz_set = {b: [p["review"] / p["sets"] for p in reviewed if lo <= p["churn"] < hi] for b, lo, hi in buckets}
    return {"per_set": [median(by[w]) if len(by[w]) >= 5 else None for w in SPEND_WEEKS],
            "share": [share[w][0] / share[w][1] if share[w][1] else None for w in SPEND_WEEKS],
            "reviewed_share": len(reviewed) / len(prs) if prs else 0, "n_prs": len(prs), "n_reviewed": len(reviewed),
            "median_pr": median([p["review"] for p in reviewed]), "median_set": median([p["review"] / p["sets"] for p in reviewed]),
            "total_review": round(sum(p["review"] for p in prs)), "total": round(sum(p["usd"] for p in prs)),
            "buckets": [b for b, *_ in buckets], "bucket_median": [median(bsz[b]) for b, *_ in buckets],
            "bucket_set_median": [median(bsz_set[b]) for b, *_ in buckets], "bucket_n": [len(bsz[b]) for b, *_ in buckets],
            "sec_median": median([p["review"] for p in reviewed if p["sec"]]),
            "nosec_median": median([p["review"] for p in reviewed if not p["sec"]]),
            "sec_n": sum(1 for p in reviewed if p["sec"])}


# ---------------------------------------------------------------- Q review-cost

def q_review_cost_worktype(con):
    have = con.execute("SELECT COUNT(*) FROM detectors.sqlite_master WHERE name='cs_worktype'").fetchone()[0]
    if not have:
        return None
    cols = [r[1] for r in con.execute("PRAGMA detectors.table_info(cs_worktype)")]
    key = [c for c in ("repo", "unit_kind", "unit_id", "set_idx") if c in cols]
    wt = {tuple(r[c] for c in key): r["work_type"] for r in rows(con, f"SELECT {', '.join(key)}, work_type FROM detectors.cs_worktype")}
    cs = [f for f in spend_by_changeset(con) if f["week"] in SPEND_WEEKS]
    kinds, wk, tot = set(), defaultdict(lambda: defaultdict(float)), defaultdict(float)
    per = defaultdict(list)
    missing = 0
    for f in cs:
        k = tuple(str(f[c]) if c == "unit_id" else f[c] for c in key)
        t = wt.get(k) or ("upkeep" if f["dependabot"] else None)
        if t is None:
            missing += 1
            t = "unlabelled"
        kinds.add(t)
        wk[t][f["week"]] += f["usd"]
        tot[t] += f["usd"]
        per[t].append(f["usd"])
    order = sorted(kinds, key=lambda t: -tot[t])
    week_all = {w: sum(wk[t].get(w, 0) for t in order) for w in SPEND_WEEKS}
    all_ = sum(tot.values())
    return {"order": order, "series": {t: [wk[t].get(w, 0) / week_all[w] if week_all[w] else None for w in SPEND_WEEKS] for t in order},
            "share": {t: tot[t] / all_ for t in order}, "usd": {t: round(tot[t]) for t in order},
            "per_set_median": {t: median(per[t]) for t in order}, "n": {t: len(per[t]) for t in order}, "missing": missing}


# ---------------------------------------------------------------- Q spend-by-work-kind

PLAN_PER_MONTH = 200.0


def q_spend_by_work_kind_paid(con):
    wk = defaultdict(float)
    for r in rows(con, "SELECT week, cost_usd FROM harness.sessions"):
        wk[r["week"]] += r["cost_usd"] or 0
    plan_week = PLAN_PER_MONTH * 12 / 52
    api = [round(wk.get(w, 0)) for w in SPEND_WEEKS]
    full = FULL_WEEKS
    lim = rows(con, "SELECT kind, COUNT(*) n FROM harness.limit_events GROUP BY 1")
    return {"api": api, "plan": [round(plan_week)] * len(SPEND_WEEKS), "plan_week": round(plan_week),
            "ratio_full_weeks": round(sum(wk[w] for w in full) / (plan_week * len(full)), 1),
            "median_week": round(statistics.median([wk[w] for w in full])),
            "limits": {r["kind"]: r["n"] for r in lim}}


# ---------------------------------------------------------------- CI

def ci_group(r):
    n, ev, br = r["workflow_name"] or "", r["event"] or "", r["head_branch"] or ""
    if r["hung"]:
        return "Hung 26 Aug, cancelled 28 Aug"
    if "Copilot" in n:
        return "Copilot review"
    if br.startswith("dependabot/") or ev == "dynamic":
        return "Dependency updates"
    if n == "Auto Approve":
        return "Auto Approve"
    if n.lower().startswith("deploy") or "Push" in n:
        return "Deploy"
    if ev == "schedule":
        return "Scheduled"
    return "Build, test, checks"


CI_GROUPS = ["Build, test, checks", "Auto Approve", "Deploy", "Dependency updates", "Copilot review", "Scheduled",
             "Hung 26 Aug, cancelled 28 Aug"]


@__import__("functools").lru_cache(maxsize=None)
def ci_runs(con):
    out = []
    for r in rows(con, "SELECT repo, run_id, workflow_name, event, head_branch, head_sha, conclusion, created_ts, updated_ts, "
                       "duration_s FROM github.ci_runs WHERE created_ts >= '2026-01-01'"):
        r["min"] = (r["duration_s"] or 0) / 60
        r["hung"] = r["created_ts"][:10] == HUNG_DAY and r["min"] > 6 * 60 and r["conclusion"] == "cancelled"
        r["day"] = r["created_ts"][:10]
        r["week"] = week_of(r["day"])
        r["month"] = r["day"][:7]
        r["group"] = ci_group(r)
        r["category"] = category(con, r["repo"])
        out.append(r)
    return out


def q_ci_minutes(con):
    runs = ci_runs(con)
    wk = defaultdict(lambda: defaultdict(float))
    for r in runs:
        wk[r["group"]][r["week"]] += r["min"]
    tot = {g: sum(wk[g].values()) for g in CI_GROUPS}
    hung = [r for r in runs if r["hung"]]
    sets = defaultdict(int)
    for f in changeset_facts(con):
        if not f["dependabot"]:
            sets[(f["repo"], f["month"])] += 1
    by_rm = defaultdict(float)
    for r in runs:
        if not r["hung"]:
            by_rm[(r["repo"], r["month"])] += r["min"]
    repos = sorted({r["repo"] for r in runs if r["category"] in APPS or r["repo"] == "hero-template"},
                   key=lambda x: -sum(v for (rp, _), v in by_rm.items() if rp == x))[:7]
    per_set = {rp: [round(by_rm[(rp, m)] / sets[(rp, m)], 1) if sets[(rp, m)] >= 5 else None for m in MONTHS] for rp in repos}
    all_ = sum(tot.values())
    ex = sum(v for g, v in tot.items() if not g.startswith("Hung"))
    return {"series": {g: [round(wk[g].get(w, 0)) for w in WEEKS] for g in CI_GROUPS},
            "usd": {g: round(tot[g]) for g in CI_GROUPS}, "total": round(all_), "excl_hung": round(ex),
            "hung_n": len(hung), "hung_min": round(sum(r["min"] for r in hung)), "hung_repos": len({r["repo"] for r in hung}),
            "hung_events": sorted({r["event"] for r in hung}), "hung_hours": (round(min(r["min"] for r in hung) / 60),
                                                                              round(max(r["min"] for r in hung) / 60)),
            "hung_workflows": {w: sum(1 for r in hung if r["workflow_name"] == w) for w in {r["workflow_name"] for r in hung}},
            "per_set": per_set, "runs": len(runs),
            "month_ex_hung": {m: round(sum(r["min"] for r in runs if r["month"] == m and not r["hung"])) for m in MONTHS}}


# Book figure 6.6. The hang: every run created on 26 Aug that sat over six hours and ended cancelled; no run on
# any other day of 2026 ran over an hour, so the rule isolates the incident. `FIX_DAY` is the first day the
# auto-approve caller ran scripted gates before the model (wayfare-skills db701b7, 29 Aug).
FIX_DAY = "2026-08-29"
CUT_DAY = "2026-09-17"


def q_ci_minutes_pareto(con):
    """Wall-clock run minutes, normal runs against the hung ones: the Pareto of runs by minutes, the monthly split,
    and the baseline after the fix. Billable minutes are not in the data (ci_jobs.billable_ms is 0 on every row and
    only some runs have a job row), so the second measure is a per-run minute rounding: GitHub bills each job in
    whole minutes rounded up, so with at least one job per run it is a lower bound on the bill."""
    import math
    runs = ci_runs(con)
    wall = lambda rs: sum(r["min"] for r in rs)
    billable_lb = lambda rs: sum(math.ceil(r["min"]) for r in rs if r["min"] > 0)
    hung = [r for r in runs if r["hung"]]
    normal = [r for r in runs if not r["hung"]]
    ordered = sorted(runs, key=lambda r: -r["min"])
    total = wall(runs)
    cum, acc = [], 0.0
    for r in ordered:
        acc += r["min"]
        cum.append(acc / total)
    # Runs over an hour outside the hang day: the check that the rule does not catch ordinary runs.
    long_other = [r for r in runs if not r["hung"] and r["min"] > 60]
    months = {m: {"normal": round(wall([r for r in normal if r["month"] == m])),
                  "hung": round(wall([r for r in hung if r["month"] == m])),
                  "runs": sum(1 for r in runs if r["month"] == m)} for m in MONTHS}
    def week_span(a, b):
        rs = [r for r in normal if a <= r["day"] < b]
        days = (date.fromisoformat(b) - date.fromisoformat(a)).days
        return {"from": a, "to": b, "days": days, "runs": len(rs), "minutes": round(wall(rs)),
                "per_week": round(wall(rs) / days * 7), "runs_per_week": round(len(rs) / days * 7)}
    before = week_span("2026-07-29", HUNG_DAY)          # the four weeks before the hang
    after_fix = week_span(FIX_DAY, CUT_DAY)             # from the fix to the deliberate cut
    after_cut = week_span(CUT_DAY, "2026-09-25")        # after the cut, to the last full day
    table = [{"group": "Normal runs", "runs": len(normal), "wall_min": round(wall(normal)), "billable_lb_min": billable_lb(normal),
              "share_wall": round(wall(normal) / total, 3)},
             {"group": "Hung runs (26 Aug, cancelled 28 Aug)", "runs": len(hung), "wall_min": round(wall(hung)),
              "billable_lb_min": billable_lb(hung), "share_wall": round(wall(hung) / total, 3)}]
    return {"table": table, "total_wall": round(total), "total_billable_lb": billable_lb(runs), "runs": len(runs),
            "hung_n": len(hung), "hung_share_runs": round(len(hung) / len(runs), 4), "hung_share_wall": round(wall(hung) / total, 3),
            "hung_hours": (round(min(r["min"] for r in hung) / 60), round(max(r["min"] for r in hung) / 60)),
            "hung_cancelled": (min(r["updated_ts"] for r in hung)[:16], max(r["updated_ts"] for r in hung)[:16]),
            "hung_workflows": dict(sorted(((w, sum(1 for r in hung if r["workflow_name"] == w)) for w in {r["workflow_name"] for r in hung}),
                                          key=lambda kv: -kv[1])),
            "hung_workflow_groups": {"Auto Approve": sum(1 for r in hung if r["workflow_name"] == "Auto Approve"),
                                     "Dependabot": sum(1 for r in hung if r["event"] == "dynamic"),
                                     "Build or deploy": sum(1 for r in hung if r["workflow_name"] != "Auto Approve" and r["event"] != "dynamic")},
            "long_other": len(long_other), "cum": cum, "top_minutes": [round(r["min"]) for r in ordered[:60]],
            "months": months, "before": before, "after_fix": after_fix, "after_cut": after_cut,
            "weekly": {w: {"normal": round(wall([r for r in normal if r["week"] == w])),
                           "hung": round(wall([r for r in hung if r["week"] == w]))} for w in WEEKS},
            "fix_day": FIX_DAY, "cut_day": CUT_DAY,
            "job_rows": list(con.execute("SELECT COUNT(*), SUM(billable_ms > 0) FROM github.ci_jobs").fetchone())}


def q_wasted_ci_minutes(con):
    runs = ci_runs(con)
    last = {}
    for r in sorted(runs, key=lambda r: r["created_ts"]):
        if r["event"] != "issue_comment" and r["head_sha"]:
            last[(r["repo"], r["workflow_name"], r["head_sha"])] = r["run_id"]
    cats = ["Hung or cancelled", "Superseded re-run on the same commit", "Rounded up to a full minute", "Skipped (not billed)"]
    wk = defaultdict(lambda: defaultdict(float))
    tot_min = defaultdict(float)
    skipped = defaultdict(int)
    for r in runs:
        tot_min[r["week"]] += r["min"]
        if r["conclusion"] == "cancelled":
            wk[cats[0]][r["week"]] += r["min"]
        elif r["event"] != "issue_comment" and r["head_sha"] and last.get((r["repo"], r["workflow_name"], r["head_sha"])) != r["run_id"]:
            wk[cats[1]][r["week"]] += r["min"]
        if r["conclusion"] == "skipped":
            skipped[r["week"]] += 1
        elif 0 < r["min"]:
            wk[cats[2]][r["week"]] += (-(-r["min"] // 1)) - r["min"]
    tot = {c: sum(wk[c].values()) for c in cats[:3]}
    all_ = sum(tot_min.values())
    billed_proxy = all_ + tot[cats[2]]
    by_event = defaultdict(lambda: [0, 0.0, 0])
    for r in runs:
        e = by_event[r["event"]]
        e[0] += 1
        e[1] += r["min"]
        e[2] += r["conclusion"] == "skipped"
    ev = sorted(by_event, key=lambda e: -by_event[e][0])[:6]
    no_hung = sum(r["min"] for r in runs if r["conclusion"] == "cancelled" and not r["hung"])
    ex_all = sum(r["min"] for r in runs if not r["hung"])
    return {"series": {c: [round(wk[c].get(w, 0)) for w in WEEKS] for c in cats[:3]},
            "share": {c: tot[c] / billed_proxy for c in cats[:3]}, "min": {c: round(tot[c]) for c in cats[:3]},
            "total": round(all_), "billed_proxy": round(billed_proxy),
            "waste_share": sum(tot.values()) / billed_proxy,
            "waste_share_ex_hung": (sum(tot.values()) - (tot[cats[0]] - no_hung)) / (ex_all + tot[cats[2]]),
            "skipped_runs": sum(skipped.values()),
            "events": ev, "event_runs": [by_event[e][0] for e in ev], "event_min": [round(by_event[e][1]) for e in ev],
            "event_skipped": [by_event[e][2] for e in ev]}


def q_dependency_update_cost_dependency(con):
    prs = rows(con, "SELECT repo, number, author, merged_ts FROM github.prs WHERE merged_ts IS NOT NULL")
    dep = lambda a: "dependabot" in (a or "")
    pr_wk = defaultdict(lambda: [0, 0])
    for p in prs:
        w = week_of(p["merged_ts"][:10])
        pr_wk[w][0] += dep(p["author"])
        pr_wk[w][1] += 1
    runs = ci_runs(con)
    ci_wk = defaultdict(lambda: [0.0, 0.0])
    ci_day = defaultdict(float)
    for r in runs:
        if r["hung"]:
            continue
        ci_wk[r["week"]][1] += r["min"]
        if r["group"] == "Dependency updates":
            ci_wk[r["week"]][0] += r["min"]
            ci_day[r["day"]] += r["min"]
    sp_wk = defaultdict(lambda: [0.0, 0.0])
    for r in spend_rows(con):
        sp_wk[r["week"]][1] += r["usd"]
        if r["target"] == "dependabot" or (r["branch"] or "").startswith("dependabot/"):
            sp_wk[r["week"]][0] += r["usd"]
    # Early-year weeks hold a handful of PRs and runs, so their shares swing between 0 and 100%.
    share = lambda d, w, lo: d[w][0] / d[w][1] if d[w][1] >= lo else None
    dep_prs = sum(1 for p in prs if dep(p["author"]))
    since = [p for p in prs if p["merged_ts"] >= "2026-08-10"]
    top_days = sorted(ci_day, key=lambda d: -ci_day[d])[:8]
    tot_sp = sum(v[1] for v in sp_wk.values())
    return {"series": {"Merged PRs": [share(pr_wk, w, 10) for w in WEEKS],
                       "CI minutes": [share(ci_wk, w, 300) for w in WEEKS],
                       "Agent spend": [share(sp_wk, w, 1) if w in SPEND_WEEKS else None for w in WEEKS]},
            "pr_share": dep_prs / len(prs), "pr_share_since": sum(1 for p in since if dep(p["author"])) / len(since),
            "ci_share": sum(v[0] for v in ci_wk.values()) / sum(v[1] for v in ci_wk.values()),
            "spend_share": sum(v[0] for v in sp_wk.values()) / tot_sp, "spend_usd": round(sum(v[0] for v in sp_wk.values())),
            "dep_prs": dep_prs, "top_days": top_days, "top_day_min": [round(ci_day[d]) for d in top_days]}


def q_ci_change_effect_ci_changes(con):
    runs = [r for r in ci_runs(con) if not r["hung"]]
    merged = defaultdict(int)
    for f in changeset_facts(con):
        if not f["dependabot"]:
            merged[f["week"]] += 1
    aa, other = defaultdict(float), defaultdict(float)
    aa_runs = defaultdict(int)
    for r in runs:
        if r["group"] == "Auto Approve":
            aa[r["week"]] += r["min"]
            aa_runs[r["week"]] += 1
        elif r["group"] in ("Build, test, checks", "Deploy", "Copilot review", "Scheduled"):
            other[r["week"]] += r["min"]
    per = lambda d: [round(d[w] / merged[w], 2) if merged[w] >= 10 else None for w in WEEKS]
    aa_per_run = [round(aa[w] / aa_runs[w], 2) if aa_runs[w] >= 20 else None for w in WEEKS]
    pick = lambda s, lo, hi: [v for w, v in zip(WEEKS, s) if lo <= w <= hi and v is not None]
    s_aa, s_ot = per(aa), per(other)
    return {"series": {"Auto Approve minutes per change set": s_aa, "Build, test, deploy minutes per change set": s_ot},
            "aa_per_run": aa_per_run,
            "before_cut": (mean(pick(s_aa, "2026-W33", "2026-W37")), mean(pick(s_ot, "2026-W33", "2026-W37"))),
            "after_cut": (mean(pick(s_aa, "2026-W38", "2026-W39")), mean(pick(s_ot, "2026-W38", "2026-W39"))),
            "aa_run_before": mean(pick(aa_per_run, "2026-W31", "2026-W35")), "aa_run_after": mean(pick(aa_per_run, "2026-W36", "2026-W39"))}


# ---------------------------------------------------------------- Q multi-repo-change-cost

def q_multi_repo_change_cost_repeated(con):
    """Cost of the same change made in several repos: fleet-wide branches and duplicate-fix clusters."""
    rs = spend_rows(con)
    by_branch = defaultdict(lambda: {"usd": 0.0, "prs": set(), "week": ""})
    for r in rs:
        if r["target"] == "pr" and r.get("fanout", 1) > 1:
            b = by_branch[r["branch"]]
            b["usd"] += r["usd"]
            b["prs"].add((r["pr_repo"], r["pr"]))
            b["week"] = max(b["week"], r["week"])
    fleet = {k: v for k, v in by_branch.items() if len({p[0] for p in v["prs"]}) >= 3}
    bp = spend_by_pr(con)
    pr_of = {(r["repo"], r["sha"]): r["pr_number"] for r in rows(con, "SELECT repo, sha, pr_number FROM git.commits WHERE day >= '2026-08-09'")}
    clusters = defaultdict(list)
    for r in rows(con, "SELECT cluster_id, signature, repo, sha, ts FROM detectors.duplicate_fixes WHERE ts >= '2026-08-09'"):
        pr = pr_of.get((r["repo"], r["sha"]))
        usd = bp.get((r["repo"], pr), {}).get("usd", 0.0) if pr else 0.0
        clusters[r["cluster_id"]].append({**r, "usd": usd, "pr": pr})
    cl = [{"id": c, "sig": v[0]["signature"], "n": len(v), "usd": sum(x["usd"] for x in v),
           "first": sorted(v, key=lambda x: x["ts"])[0]["usd"], "week": week_of(max(x["ts"] for x in v)[:10])}
          for c, v in clusters.items() if len(v) >= 2]
    spent = [c for c in cl if c["usd"] > 0]
    wk_fleet, wk_all = defaultdict(float), defaultdict(float)
    for r in rs:
        wk_all[r["week"]] += r["usd"]
        if r["target"] == "pr" and r["branch"] in fleet:
            wk_fleet[r["week"]] += r["usd"]
    top = sorted(fleet, key=lambda b: -fleet[b]["usd"])[:8]
    per_copy = [fleet[b]["usd"] / len(fleet[b]["prs"]) for b in fleet]
    return {"series": {"Fleet-wide changes (same branch in 3+ repos)": [round(wk_fleet.get(w, 0)) for w in SPEND_WEEKS],
                       "Everything else": [round(wk_all.get(w, 0) - wk_fleet.get(w, 0)) for w in SPEND_WEEKS]},
            "fleet_n": len(fleet), "fleet_usd": round(sum(v["usd"] for v in fleet.values())),
            "fleet_prs": sum(len(v["prs"]) for v in fleet.values()), "per_copy_median": median(per_copy),
            "top": top, "top_usd": [round(fleet[b]["usd"]) for b in top], "top_repos": [len({p[0] for p in fleet[b]["prs"]}) for b in top],
            "share": sum(v["usd"] for v in fleet.values()) / sum(wk_all.values()),
            "clusters": len(cl), "clusters_spent": len(spent), "cluster_usd": round(sum(c["usd"] for c in spent)),
            "cluster_copies": sum(c["n"] for c in spent),
            "repeat_usd": round(sum(c["usd"] - c["first"] for c in spent))}


def all_data(con):
    return {name: fn(con) for name, fn in globals().items() if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__}


if __name__ == "__main__":
    from cube.db import connect
    import pprint
    con = connect()
    for k, v in all_data(con).items():
        print("=" * 20, k)
        if v is None:
            print(None)
            continue
        pprint.pprint({kk: vv for kk, vv in v.items() if kk not in ("series", "by_repo", "per_set")} , width=160, compact=True)
