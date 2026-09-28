"""Chart series for the method topic's Question -> Answer slides.

Each function returns a dict with the numbers one answer slide needs. The
question modules answer at a single point; these add the time axis the
slides plot, and correct three modules whose SQL misreads the detectors
(noted per function, and in the deck's "code issues" slide).
"""
import json
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cube.db import connect  # noqa: E402
from ingest.fleet import BASELINE_CUTOFF, OUT_OF_SCOPE, REPO_ALIASES, category_of  # noqa: E402
from record import STAGES, adoption, stage_of  # noqa: E402

START_2026 = "2026-01-01"
MONTHS_2026 = [f"2026-{m:02d}" for m in range(1, 10)]
PRE_MONTHS = [m for m in MONTHS_2026 if m < BASELINE_CUTOFF[:7]]


def month_range(first, last):
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


IN_SCOPE = "repo NOT IN ({})".format(",".join(f"'{r}'" for r in OUT_OF_SCOPE) or "''")


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def sets_by_sha(con):
    return {(r["repo"], r["sha"]): r["n_sets"] for r in rows(con, """
        SELECT lk.repo, lk.sha, c.n_sets FROM detectors.changesets_by_commit lk
        JOIN detectors.changesets c ON c.content_hash = lk.content_hash""")}


# When wayfare shipped each piece of the factory, from wayfare-skills' own
# history (subject and short sha of the commit that introduced it).
MILESTONES = [
    ("2026-03-07", "Skills", "a2bb70d hero skills plugin, HERO.md"),
    ("2026-05-04", "Review loop", "5548869 self-review + gated auto-approve"),
    ("2026-07-05", "Work items", "36786de grill emits work-items to plan-work/"),
    ("2026-07-22", ".plans + roadmap", "366658b/5662e7e .plans store, wayfare"),
    ("2026-08-16", "Design repos removed", "4894f14 claude.ai/design project"),
    ("2026-08-28", "Goals", "6a0c0b6 /goal-driven runs"),
    ("2026-09-13", "Messages", "7181504 mailbox"),
    ("2026-09-18", "1 commit per feature", "597dd87 a goal is one branch, one PR"),
]
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]


def _items(con):
    """Every work item with the links it records to branches, PRs and commits."""
    out = []
    for r in rows(con, "SELECT repo, item_id, type, goal_id, day, raw_frontmatter_json j FROM plans.plan_items"):
        fm = json.loads(r["j"] or "{}")
        prs = set()
        for key in ("pr", "merged_pr", "merged_prs"):
            v = fm.get(key)
            for x in (v if isinstance(v, list) else [v]):
                m = re.search(r"(\d+)$", str(x)) if x is not None else None
                if m:
                    prs.add(int(m.group(1)))
        out.append({**r, "branch": fm.get("branch"), "prs": prs})
    return out


def q_change_set_work_item_links(con):
    """How each change set on the default branch reaches a work item and a goal, by week."""
    sets = sets_by_sha(con)
    items = _items(con)
    by_branch = {(i["repo"], i["branch"]): i for i in items if i["branch"]}
    by_pr = {(i["repo"], n): i for i in items for n in i["prs"]}
    by_id = {(i["repo"], i["item_id"]): i for i in items}
    goal_ids = {(r["repo"], r["goal_id"]) for r in rows(con, "SELECT repo, goal_id FROM plans.goals")}
    cats = ["Goal", "Work item, no goal", "One-shot task (no work item)", "Dependabot", "Pushed straight to main"]
    session_prs = set()
    for r in rows(con, "SELECT pr_links FROM harness.sessions WHERE pr_links NOT IN ('', '[]')"):
        for link in json.loads(r["pr_links"]):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
            if m:
                session_prs.add((REPO_ALIASES.get(m.group(1), m.group(1)), int(m.group(2))))
    sessions_from = rows(con, "SELECT MIN(day) d FROM harness.sessions")[0]["d"]
    oneshot, traced = 0, 0
    weekly = {c: defaultdict(float) for c in cats}
    mech = defaultdict(float)
    for r in rows(con, """SELECT c.repo, c.sha, c.day, c.week, c.pr_number, c.plan_item_ref, c.is_bot, p.head_ref
                          FROM git.commits c LEFT JOIN github.prs p ON p.repo=c.repo AND p.number=c.pr_number
                          WHERE c.day >= ? AND c.{IN_SCOPE}""".format(IN_SCOPE=IN_SCOPE), (START_2026,)):
        n = sets.get((r["repo"], r["sha"]), 1)
        head = r["head_ref"] or ""
        gm = re.search(r"goal-(\d+)", head)
        item = None
        if r["pr_number"]:
            item = by_pr.get((r["repo"], r["pr_number"])) or by_branch.get((r["repo"], head))
        if not item and r["plan_item_ref"]:
            item = by_id.get((r["repo"], str(r["plan_item_ref"])))
        if r["pr_number"] is None:
            cat = "Pushed straight to main"
        elif head.startswith("dependabot/") or r["is_bot"]:
            cat = "Dependabot"
        elif gm and (r["repo"], gm.group(1)) in goal_ids or (item and item["goal_id"]):
            cat = "Goal"
            mech["goal branch" if gm else "item in a goal"] += n
        elif item:
            cat = "Work item, no goal"
            mech["item records PR" if (r["repo"], r["pr_number"]) in by_pr else
                 "item records branch" if (r["repo"], head) in by_branch else "commit names item"] += n
        else:
            cat = "One-shot task (no work item)"
            if r["day"] >= sessions_from and not ("2026-08-10" <= r["day"] <= "2026-08-24"):
                oneshot += n
                traced += n if (r["repo"], r["pr_number"]) in session_prs else 0
        weekly[cat][r["week"]] += n
    since = lambda d: sum(v for w, v in d.items() if w >= "2026-W30")
    total_since = sum(since(weekly[c]) for c in cats)
    # Goal PRs squash to one commit, so D1 sees one message for several features.
    goals = {(r["repo"], r["goal_id"]): len(json.loads(r["members"] or "[]"))
             for r in rows(con, "SELECT repo, goal_id, members FROM plans.goals")}
    pairs = []
    for r in rows(con, """SELECT p.repo, p.head_ref, SUM(cs.n_sets) n FROM github.prs p
                          JOIN git.commits c ON c.repo=p.repo AND c.pr_number=p.number
                          JOIN detectors.changesets_by_commit bc ON bc.repo=c.repo AND bc.sha=c.sha
                          JOIN detectors.changesets cs ON cs.content_hash=bc.content_hash
                          WHERE p.head_ref LIKE '%goal-%' AND p.merged_ts IS NOT NULL GROUP BY p.repo, p.number"""):
        m = re.search(r"goal-(\d+)", r["head_ref"])
        if m and goals.get((r["repo"], m.group(1))):
            pairs.append((goals[(r["repo"], m.group(1))], r["n"]))
    ledger = []
    for r in rows(con, "SELECT repo, raw_frontmatter_json j FROM plans.plan_items"):
        entries = json.loads(r["j"] or "{}").get("commits")
        ledger += [(r["repo"], e) for e in (entries if isinstance(entries, list) else []) if isinstance(e, str)]
    main = defaultdict(set)
    for r in rows(con, "SELECT repo, sha FROM git.commits"):
        main[r["repo"]].add(r["sha"][:7])
    on_main = sum(1 for repo, e in ledger if e[:7] in main[repo])
    pr_shas = defaultdict(set)
    for r in rows(con, "SELECT repo, sha FROM pr_commits.pr_commits"):
        pr_shas[r["repo"]].add(r["sha"][:7])
    return {"weeks": WEEKS, "cats": cats,
            "series": {c: [round(weekly[c].get(w, 0)) for w in WEEKS] for c in cats},
            "share_since_w30": {c: round(since(weekly[c]) / total_since, 3) for c in cats},
            "mechanisms": dict(mech),
            "goal_merges": len(pairs), "d1_matches": sum(a == b for a, b in pairs),
            "d1_under": sum(b < a for a, b in pairs), "d1_single_for_3plus": sum(1 for a, b in pairs if a >= 3 and b == 1),
            "features_in_goal_merges": sum(a for a, _ in pairs), "d1_sets_in_goal_merges": sum(b for _, b in pairs),
            "ledger_entries": len(ledger), "ledger_on_main": on_main,
            "ledger_in_pr_commits": sum(1 for repo, e in ledger if e[:7] in pr_shas[repo]),
            "oneshot_since_sessions": oneshot, "oneshot_traced_to_session": traced, "sessions_from": sessions_from}


def q_repo_stage_at_work(con):
    """Weekly commits by what the repo had adopted when the commit landed."""
    cats = STAGES
    weekly = {c: defaultdict(int) for c in cats}
    for r in rows(con, f"SELECT repo, day, week FROM git.commits WHERE day >= ? AND {IN_SCOPE}", (START_2026,)):
        weekly[stage_of(con, r["repo"], r["day"])][r["week"]] += 1
    return {"weeks": WEEKS, "series": {c: [weekly[c].get(w, 0) for w in WEEKS] for c in cats},
            "totals": {c: sum(weekly[c].values()) for c in cats},
            "adoption": sorted(adoption(con).values(), key=lambda a: a["first"])}


def q_active_repo_dates(con):
    """When each repo was actively developed: first and last commit since 1 Jan, commits per month."""
    latest = rows(con, "SELECT MAX(day) d FROM git.commits")[0]["d"]
    months = month_range("2026-01", latest[:7])
    out = []
    for r in rows(con, "SELECT repo, MIN(day) first, MAX(day) last, COUNT(*) n FROM git.commits "
                       f"WHERE day >= ? AND {IN_SCOPE} GROUP BY repo ORDER BY first", (START_2026,)):
        per = {x["month"]: x["n"] for x in rows(con, "SELECT month, COUNT(*) n FROM git.commits WHERE repo=? "
                                                     "GROUP BY month", (r["repo"],))}
        out.append({**r, "months": [per.get(m, 0) for m in months],
                    "before_2026": rows(con, "SELECT COUNT(*) n FROM git.commits WHERE repo=? AND day < ?",
                                        (r["repo"], START_2026))[0]["n"],
                    "category": category_of(r["repo"])})
    order = {"app": 0, "app, no features yet": 1, "allied": 2}
    out.sort(key=lambda r: (order.get(r["category"], 3), r["first"]))
    return {"repos": out, "months": months, "latest": latest}


def q_counting_units_compared_two_passes(con):
    """Three counts of the same history per repo: commits on main, original commits, change sets."""
    main = {r["repo"]: r["n"] for r in rows(con, f"SELECT repo, COUNT(*) n FROM git.commits WHERE is_merge=0 AND {IN_SCOPE} GROUP BY repo")}
    orig = defaultdict(int)
    for r in rows(con, "SELECT repo, SUM(n_commits) n FROM detectors.cs_units GROUP BY repo"):
        orig[r["repo"]] = r["n"]
    sets = {r["repo"]: r["n"] for r in rows(con, "SELECT repo, SUM(n_sets) n FROM detectors.cs_units GROUP BY repo")}
    out = [{"repo": r, "main": main[r], "original": orig[r], "sets": sets.get(r, 0),
            "ratio": round(sets.get(r, 0) / main[r], 2)} for r in main]
    return sorted(out, key=lambda x: -x["main"])


def set_item_links(con):
    """Change set -> work items. A goal's commit log ("035d500 129") ties branch commits to the
    feature they built; otherwise every change set in a PR belongs to the items recording that PR."""
    items = _items(con)
    ledger = defaultdict(set)
    for r in rows(con, "SELECT repo, item_id, raw_frontmatter_json j FROM plans.plan_items"):
        entries = json.loads(r["j"] or "{}").get("commits")
        for e in entries if isinstance(entries, list) else []:
            m = re.match(r"([0-9a-f]{7,40})\s+#?(\d+)\b", str(e))
            if m:
                ledger[(r["repo"], m.group(1)[:7])].add(m.group(2))
    heads = {(r["repo"], r["head_ref"]): r["number"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    by_pr = defaultdict(set)
    for it in items:
        if it["type"] == "goal":
            continue
        for n in set(it["prs"]) | ({heads[(it["repo"], it["branch"])]} if (it["repo"], it["branch"]) in heads else set()):
            by_pr[(it["repo"], n)].add(it["item_id"])
    links, via = {}, defaultdict(int)
    for r in rows(con, "SELECT repo, unit_kind, unit_id, set_idx, shas_json FROM detectors.cs_sets"):
        shas = json.loads(r["shas_json"])
        from_ledger = set().union(*(ledger.get((r["repo"], s[:7]), set()) for s in shas))
        if from_ledger:
            got, how = from_ledger, "goal commit log"
        elif r["unit_kind"] in ("pr", "pr-squash"):
            got, how = by_pr.get((r["repo"], int(r["unit_id"])), set()), "item records the PR"
        else:
            got, how = set(), None
        links[(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"])] = got
        if got:
            via[how] += 1
    return links, dict(via)


def q_commits_per_change_set_distribution(con):
    """Change sets per original commit, per PR, per work item and per goal; commits per change set."""
    bins = ["1", "2", "3", "4", "5+"]
    hist = lambda vals: [sum(1 for v in vals if (min(v, 5) if v else 0) == k) for k in range(1, 6)]
    sets = rows(con, f"SELECT repo, unit_kind, unit_id, shas_json FROM detectors.cs_sets WHERE {IN_SCOPE}")
    per_set = [len(json.loads(r["shas_json"])) for r in sets]
    member = defaultdict(int)
    for r in sets:
        for sha in json.loads(r["shas_json"]):
            member[(r["repo"], sha)] += 1
    per_pr = {(r["repo"], int(r["unit_id"])): r["n_sets"] for r in rows(
        con, f"SELECT repo, unit_id, n_sets FROM detectors.cs_units WHERE unit_kind IN ('pr', 'pr-squash') AND {IN_SCOPE}")}
    per_goal = []
    for r in rows(con, "SELECT repo, number, head_ref FROM github.prs WHERE head_ref LIKE '%goal-%' AND merged_ts IS NOT NULL"):
        if (r["repo"], r["number"]) in per_pr:
            per_goal.append(per_pr[(r["repo"], r["number"])])
    links, via = set_item_links(con)
    items_per_set = [len(v) for v in links.values() if v]
    sets_of_item = defaultdict(int)
    for (repo, *_), v in links.items():
        for item in v:
            sets_of_item[(repo, item)] += 1
    per_item = list(sets_of_item.values())
    multi_commits = sum(1 for v in member.values() if v > 1)
    mean = lambda v: round(statistics.mean(v), 2) if v else None
    return {"bins": bins,
            "commits_per_set": hist(per_set), "sets_per_commit": hist(list(member.values())),
            "sets_per_pr": hist(list(per_pr.values())), "sets_per_item": hist(per_item), "sets_per_goal": hist(per_goal),
            "items_per_set": hist(items_per_set), "link_via": via, "multi_set_commits": multi_commits,
            "sets_linked": len(items_per_set),
            "mean": {"commits_per_set": mean(per_set), "sets_per_commit": mean(list(member.values())),
                     "sets_per_pr": mean(list(per_pr.values())), "sets_per_item": mean(per_item), "sets_per_goal": mean(per_goal),
                     "items_per_set": mean(items_per_set)},
            "n": {"sets": len(per_set), "commits": len(member), "prs": len(per_pr), "items": len(per_item), "goals": len(per_goal)}}


def all_data():
    from evolution import all_evolving
    con = connect("mistakes")
    out = {name: fn(con) for name, fn in globals().items() if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__}
    spot = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        ".analysis", "spotcheck_links.csv")
    out.update(all_evolving(con, spot))
    return out


if __name__ == "__main__":
    print(json.dumps(all_data(), indent=1, default=str))
