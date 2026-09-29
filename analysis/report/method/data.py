"""Series for the method deck's evidence figures (book figures 1.5, 4.1, 4.2, 6.4).

One function per figure, each recomputed from the sqlite data through record.py's facts. The
figures brief's rules apply: one common population per figure, missing links and uncertain
links as their own category, sample sizes returned beside every share.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero /tmp/pptxenv/bin/python3 report/method/data.py
"""
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ingest.fleet import REPO_ALIASES  # noqa: E402
from record import adoption, changeset_facts, commit_facts, rows, week_of  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
DATA_END = "2026-09-24"
# Sessions are logged continuously from 25 Aug (W35); 9 Aug holds one session and 10-24 Aug none.
COMPLETE_LOG_WEEKS = [w for w in WEEKS if w >= "2026-W35"]
FROM_JULY = "2026-07-01"
ACTIVE_MIN_SETS = 1
MEANINGFUL_MIN_SETS = 3
CATEGORY_ORDER = {"app": 0, "app, no features yet": 1, "allied": 2}
CATEGORY_TAG = {"allied": " (allied)", "app, no features yet": " (no features yet)"}


def mean(v):
    return sum(v) / len(v) if v else None


# ---------------------------------------------------------------- 1.5 Q active-repo-dates

def q_active_repo_heatmap(con):
    """Change sets per repo per ISO week (zeros kept), the active-repo count, and the split of output
    growth between more active repos and more change sets per active repo."""
    ad = adoption(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    grid = defaultdict(lambda: defaultdict(int))
    for f in cs:
        grid[f["repo"]][f["week"]] += 1
    created = {r["repo"]: r["d"] for r in rows(con, "SELECT repo, MIN(day) d FROM git.commits GROUP BY repo")}
    repos = []
    for repo in grid:
        weeks_active = [w for w in WEEKS if grid[repo][w] >= ACTIVE_MIN_SETS]
        meaningful = next((w for w in WEEKS if grid[repo][w] >= MEANINGFUL_MIN_SETS), None)
        repos.append({"repo": repo, "category": ad[repo]["category"], "created": created[repo],
                      "created_week": week_of(created[repo]) if created[repo] >= "2026-01-01" else None,
                      "first_active": weeks_active[0] if weeks_active else None,
                      "first_meaningful": meaningful, "weeks_active": len(weeks_active),
                      "sets": sum(grid[repo].values()), "cells": [grid[repo][w] for w in WEEKS]})
    repos.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], r["first_active"] or "9", r["repo"]))
    active = [sum(1 for r in repos if r["cells"][i] >= ACTIVE_MIN_SETS) for i in range(len(WEEKS))]
    output = [sum(r["cells"][i] for r in repos) for i in range(len(WEEKS))]
    per_active = [round(o / a, 2) if a else None for o, a in zip(output, active)]
    ever = set()
    seventh = None
    for i, w in enumerate(WEEKS):
        ever |= {r["repo"] for r in repos if r["cells"][i] >= ACTIVE_MIN_SETS}
        if len(ever) > 6 and seventh is None:
            seventh = w
    # W39 runs only to 24 Sep, so the growth split compares complete weeks: W01-W26 against W27-W38.
    h1 = [i for i, w in enumerate(WEEKS) if w <= "2026-W26"]
    h2 = [i for i, w in enumerate(WEEKS) if "2026-W27" <= w <= "2026-W38"]
    a1, a2 = mean([active[i] for i in h1]), mean([active[i] for i in h2])
    o1, o2 = mean([output[i] for i in h1]), mean([output[i] for i in h2])
    p1, p2 = o1 / a1, o2 / a2
    growth = o2 / o1
    from_repos = math.log(a2 / a1) / math.log(growth) if growth > 1 else None
    return {"weeks": WEEKS, "repos": repos, "active": active, "output": output, "per_active": per_active,
            "seventh_repo_week": seventh, "n_sets": len(cs),
            "before_july": sorted(r["repo"] for r in repos if r["first_active"] and r["first_active"] < "2026-W27"),
            "split": {"h1_weeks": "W01-W26", "h2_weeks": "W27-W38", "active_h1": round(a1, 1), "active_h2": round(a2, 1),
                      "output_h1": round(o1, 1), "output_h2": round(o2, 1), "per_active_h1": round(p1, 1),
                      "per_active_h2": round(p2, 1), "growth": round(growth, 2),
                      "share_from_more_repos": round(from_repos, 2) if from_repos is not None else None},
            "thresholds": {"active": ACTIVE_MIN_SETS, "meaningful": MEANINGFUL_MIN_SETS}}


# ---------------------------------------------------------------- 4.1 Q counting-units-compared

def _item_links(con):
    from links import _items, set_item_links
    links, via = set_item_links(con)
    items = {(it["repo"], it["item_id"]): it for it in _items(con)}
    goal_of = {}
    for r in rows(con, "SELECT repo, goal_id, members FROM plans.goals"):
        for m in json.loads(r["members"] or "[]"):
            goal_of[(r["repo"], str(m))] = r["goal_id"]
    for k, it in items.items():
        if it["goal_id"]:
            goal_of.setdefault(k, it["goal_id"])
    return links, via, items, goal_of


def q_counting_units(con):
    """The same history since 1 Jul counted five ways: commits on main, original commits, change sets,
    merged PRs, work items and goals, with Dependabot's part separate; and the grouping's agreement."""
    ad = adoption(con)
    links, via, items, goal_of = _item_links(con)
    main = rows(con, "SELECT repo, is_bot FROM git.commits WHERE is_merge = 0 AND day >= ?", (FROM_JULY,))
    main = [r for r in main if r["repo"] in ad]
    orig = [c for c in commit_facts(con) if c["merged_day"] >= FROM_JULY]
    cs = [f for f in changeset_facts(con) if f["day"] >= FROM_JULY]
    heads = {(r["repo"], r["number"]): r["head_ref"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    prs, prs_bot, item_ids, goal_ids = set(), set(), set(), set()
    for f in cs:
        if f["pr"]:
            (prs_bot if f["dependabot"] else prs).add((f["repo"], f["pr"]))
        got = links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]), set())
        for i in got:
            item_ids.add((f["repo"], i))
            g = goal_of.get((f["repo"], i))
            if g:
                goal_ids.add((f["repo"], g))
        if f["pr"]:
            m = re.match(r"goal-(\d+)$", heads.get((f["repo"], f["pr"]), "") or "")
            if m:
                goal_ids.add((f["repo"], m.group(1)))
    units = ["Commits on main", "Original commits", "Change sets", "Merged PRs", "Work items", "Goals"]
    work = [sum(1 for r in main if not r["is_bot"]), sum(1 for c in orig if c["actor"] != "bot"),
            sum(1 for f in cs if not f["dependabot"]), len(prs), len(item_ids), len(goal_ids)]
    bot = [sum(1 for r in main if r["is_bot"]), sum(1 for c in orig if c["actor"] == "bot"),
           sum(1 for f in cs if f["dependabot"]), len(prs_bot), 0, 0]
    agree = rows(con, "SELECT n_commits, n_a, n_b, pair_agreement FROM detectors.cs_agreement")
    ncs = [f for f in cs if not f["dependabot"]]
    sets_with_item = sum(1 for f in ncs if links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])))
    pushes = sum(1 for f in ncs if f["unit_kind"] == "push")
    return {"units": units, "work": work, "dependabot": bot, "total": [a + b for a, b in zip(work, bot)],
            "since": FROM_JULY, "linked_via": via,
            "ratios": {"original_per_pr": round(work[1] / work[3], 2), "sets_per_pr": round((work[2] - pushes) / work[3], 2),
                       "sets_per_item": round(sets_with_item / work[4], 2) if work[4] else None,
                       "items_per_goal": round(sum(1 for k in item_ids if goal_of.get(k)) / work[5], 2) if work[5] else None,
                       "sets_with_item_share": round(sets_with_item / len(ncs), 3), "pushes": pushes},
            "agreement": {"prs": len(agree), "commits": sum(a["n_commits"] for a in agree),
                          "pair": round(mean([a["pair_agreement"] for a in agree]), 3),
                          "same_count": round(sum(1 for a in agree if a["n_a"] == a["n_b"]) / len(agree), 3)},
            "methods": {r["method"]: r["n"] for r in rows(con, "SELECT method, COUNT(*) n FROM detectors.cs_units GROUP BY method")},
            "audit": grouping_audit()}


# ---------------------------------------------------------------- 4.2 Q where-rework-is-caught

STAGES = ["Fixed by the builder inside the PR", "Fixed after review inside the PR", "Caught by a gate",
          "Fixed after merge (within 7 days)", "No rework observed"]
# A fix-up commit's trigger (mistakes.commit_labels, Chapter 10's Haiku labels) names the stage that caught it.
TRIGGER_STAGE = {"self": 0, "review_agent": 1, "copilot": 1, "judge": 1, "owner": 1, "ci": 2, "hook": 2}


def q_rework_first_catch(con):
    """Each eligible change set assigned to the one stage that first caught rework in it, with the rate
    per eligible change set and the raw count for every stage, overall and by work type."""
    ad = adoption(con)
    cutoff = (date.fromisoformat(DATA_END) - timedelta(days=7)).isoformat()
    # Eligible: the PR's own commits were recovered (unit_kind pr), so an in-PR fix-up can be seen at all,
    # and it landed 7 or more days before the data ends, so the post-merge window is complete.
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["unit_kind"] == "pr" and f["day"] <= cutoff]
    labels = {}
    for r in rows(con, "SELECT repo, sha, idx, trigger FROM mistakes.commit_labels WHERE fixup = 1"):
        labels[(r["repo"], r["sha"])] = (r["idx"], r["trigger"])
    gate_prs = defaultdict(set)
    for r in rows(con, "SELECT repo, ref, gate_kind, verdict FROM detectors.gate_firings "
                       "WHERE verdict IN ('CHANGES_REQUESTED', 'caught')"):
        m = re.search(r"(\d+)$", r["ref"] or "")
        if m:
            gate_prs[(r["repo"], int(m.group(1)))].add(r["gate_kind"])
    after = {}
    for r in rows(con, "SELECT repo, intro_unit, lifetime_days FROM mistakes.szz WHERE outcome = 'traced'"):
        if r["intro_unit"] and r["intro_unit"].startswith("pr:"):
            k = (r["repo"], int(r["intro_unit"][3:]))
            after[k] = min(after.get(k, 1e9), r["lifetime_days"])
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): r["work_type"]
          for r in rows(con, "SELECT repo, unit_kind, unit_id, set_idx, work_type FROM detectors.cs_worktype")}
    per_set, overlap = [], defaultdict(int)
    for f in cs:
        fix = sorted(labels[(f["repo"], s)] for s in f["shas"] if (f["repo"], s) in labels)
        k = (f["repo"], f["pr"])
        gated, post = k in gate_prs, after.get(k, 1e9) <= 7
        if fix:
            stage = TRIGGER_STAGE.get(fix[0][1], 1)
        elif gated:
            stage = 2
        elif post:
            stage = 3
        else:
            stage = 4
        if stage < 3 and post:
            overlap["caught in the PR and fixed again after merge"] += 1
        if fix and gated:
            overlap["fix-up commit and a gate firing"] += 1
        per_set.append({"stage": stage, "type": wt.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]), "unlabelled"),
                        "week": f["week"], "n_fixups": len(fix)})
    n = len(per_set)
    counts = [sum(1 for s in per_set if s["stage"] == i) for i in range(len(STAGES))]
    by_type = defaultdict(lambda: [0] * len(STAGES))
    for s in per_set:
        by_type[s["type"]][s["stage"]] += 1
    types = sorted(by_type, key=lambda t: -sum(by_type[t]))
    ineligible = {"squash only (PR commits not recovered)": sum(1 for f in changeset_facts(con) if f["unit_kind"] == "pr-squash" and not f["dependabot"]),
                  "pushed to main": sum(1 for f in changeset_facts(con) if f["unit_kind"] == "push" and not f["dependabot"]),
                  "landed in the last 7 days": sum(1 for f in changeset_facts(con) if f["unit_kind"] == "pr" and not f["dependabot"] and f["day"] > cutoff),
                  "Dependabot": sum(1 for f in changeset_facts(con) if f["dependabot"])}
    return {"stages": STAGES, "counts": counts, "rates": [round(c / n, 3) for c in counts], "n": n,
            "fixup_commits": sum(s["n_fixups"] for s in per_set),
            "by_type": {t: {"counts": by_type[t], "rates": [round(c / sum(by_type[t]), 3) for c in by_type[t]], "n": sum(by_type[t])} for t in types},
            "overlap": dict(overlap), "ineligible": ineligible, "cutoff": cutoff,
            "gate_prs_total": len(gate_prs), "post_merge_prs_total": sum(1 for v in after.values() if v <= 7),
            # The same records counted as events over every PR, the way the chapter's paragraph quotes them.
            "events_all": {"fix-up commits inside PRs": len(labels),
                           "gate catches": rows(con, "SELECT COUNT(*) AS n FROM detectors.gate_firings "
                                                     "WHERE verdict IN ('CHANGES_REQUESTED', 'caught')")[0]["n"],
                           "PRs fixed within 7 days": sum(1 for v in after.values() if v <= 7)}}


# ---------------------------------------------------------------- 6.4 Q observable-work-share

PLAN_CATS = ["Goal", "Work item, no goal", "One-shot, session names the PR", "One-shot, session on the branch (inferred)",
             "No observable plan", "Pushed to main"]


def q_observable_plan(con):
    """Every non-Dependabot change set that landed in the complete logging window (25 Aug to 24 Sep; W35 is
    its Tuesday to Sunday), by
    what records its plan; the uncertain link (a session on the PR's branch, not naming the PR) is its own
    category. Weekly rows and one row for the window."""
    ad = adoption(con)
    links, via, items, goal_of = _item_links(con)
    heads = {(r["repo"], r["number"]): r["head_ref"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    named, on_branch = set(), set()
    for r in rows(con, "SELECT repo, git_branches, pr_links FROM harness.sessions WHERE first_ts >= '2026-08-09'"):
        repo = REPO_ALIASES.get(r["repo"] or "", r["repo"] or "")
        for link in json.loads(r["pr_links"] or "[]"):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
            if m:
                named.add((REPO_ALIASES.get(m.group(1), m.group(1)), int(m.group(2))))
        for b in json.loads(r["git_branches"] or "[]"):
            if b != "main":
                on_branch.add((repo, b))

    def kind(f):
        got = links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]), set())
        head = heads.get((f["repo"], f["pr"])) if f["pr"] else None
        if got and (any(goal_of.get((f["repo"], i)) for i in got) or re.match(r"goal-\d+$", head or "")):
            return 0
        if got:
            return 1
        if f["unit_kind"] == "push":
            return 5
        if (f["repo"], f["pr"]) in named:
            return 2
        if head and (f["repo"], head) in on_branch:
            return 3
        return 4
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    window = [f for f in cs if f["day"] >= "2026-08-25"]
    kinds = [kind(f) for f in window]
    counts = [kinds.count(i) for i in range(len(PLAN_CATS))]
    weekly = {w: [0] * len(PLAN_CATS) for w in COMPLETE_LOG_WEEKS}
    for f, k in zip(window, kinds):
        weekly[f["week"]][k] += 1
    # The card's earlier population, for the notes: ISO weeks from W32 with the unlogged weeks (10-24 Aug) left
    # out. W32 is 3-9 Aug, of which only 9 Aug has a session, so that cut kept a week of unlogged work.
    earlier = [kind(f) for f in cs if f["week"] >= "2026-W32" and f["week"] not in ("2026-W33", "2026-W34")]
    return {"cats": PLAN_CATS, "counts": counts, "n": len(window), "rates": [round(c / len(window), 3) for c in counts],
            "weeks": COMPLETE_LOG_WEEKS, "weekly": weekly,
            "since_9aug": {"n": len(earlier), "rates": [round(earlier.count(i) / len(earlier), 3) for i in range(len(PLAN_CATS))]},
            "window": ("2026-08-25", DATA_END), "linked_via": via}


def grouping_audit():
    """The hand audit of the change-set grouping (audit_changesets.json): PRs judged and the share agreed."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_changesets.json")
    # The audit is hand-checked from the fleet's own PRs and never published. Without it the grouping check
    # reports itself unavailable: a zero here would read as "nothing was judged".
    if not os.path.exists(path):
        print("method: audit_changesets.json absent; the grouping audit is unavailable", file=sys.stderr)
        return {"unavailable": "audit_changesets.json absent"}
    with open(path, encoding="utf-8") as f:
        a = json.load(f)
    n = len(a["prs"])
    agree = sum(1 for p in a["prs"] if p["verdict"] == "agree")
    return {"n": n, "agree": agree, "share": round(agree / n, 2),
            "disagreements": [f'{p["repo"]} #{p["pr"]}: {p["note"]}' for p in a["prs"] if p["verdict"] != "agree"]}


def all_data(con=None):
    if con is None:
        from cube.db import connect
        con = connect("mistakes")
    return {n: fn(con) for n, fn in globals().items() if n.startswith("q_") and callable(fn) and fn.__module__ == __name__}


if __name__ == "__main__":
    print(json.dumps(all_data(), indent=1, default=str))
