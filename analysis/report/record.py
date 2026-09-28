"""One row per change set and one per original commit, for the chapter 2 charts.

Every row carries its repo's category (app, app with no features yet, allied)
and the stage the repo had reached on that day (skills, work items, goals,
messages), so any chart can be cut by either without re-deriving them.
Out-of-scope repos are dropped here, once.
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import OUT_OF_SCOPE, category_of  # noqa: E402
from ingest.git import CONV_RE  # noqa: E402

STAGES = ["No skills yet", "Skills", "+ work items", "+ goals", "+ messages"]
CATEGORIES = ["app", "app, no features yet", "allied"]


def week_of(day):
    y, w, _ = date.fromisoformat(day[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


@lru_cache(maxsize=None)
def adoption(con):
    first_file = lambda path: {r["repo"]: r["d"] for r in rows(con, """
        SELECT c.repo, MIN(c.day) d FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha
        WHERE f.path = ? GROUP BY c.repo""", (path,))}
    hero = first_file("HERO.md")
    first_item = lambda goal: {r["repo"]: r["d"] for r in rows(con, f"""
        SELECT repo, MIN(day) d FROM plans.plan_items WHERE type {'=' if goal else '!='} 'goal' AND day IS NOT NULL
        GROUP BY repo""")}
    items, goals = first_item(False), first_item(True)
    msgs = {}
    for r in rows(con, "SELECT from_repo, to_repo, SUBSTR(created_ts,1,10) d FROM plans.messages"):
        for repo in (r["from_repo"], r["to_repo"]):
            if repo and r["d"] and r["d"] < msgs.get(repo, "9999"):
                msgs[repo] = r["d"]
    out = {}
    for r in rows(con, "SELECT repo, MIN(day) first, MAX(day) last, COUNT(*) n FROM git.commits GROUP BY repo"):
        if r["repo"] in OUT_OF_SCOPE:
            continue
        out[r["repo"]] = {**r, "skills": hero.get(r["repo"]), "items": items.get(r["repo"]),
                          "goals": goals.get(r["repo"]), "messages": msgs.get(r["repo"]),
                          "category": category_of(r["repo"])}
    return out


def stage_of(con, repo, day):
    a = adoption(con)[repo]
    on = lambda k: a[k] is not None and a[k] <= day
    return (STAGES[4] if on("messages") else STAGES[3] if on("goals") else STAGES[2] if on("items")
            else STAGES[1] if on("skills") else STAGES[0])


@lru_cache(maxsize=None)
def merged_via(con):
    """(repo, sha) -> PR for the commits a merge-commit PR brought onto main. On main only the merge
    commit carries the PR number, so without this those commits read as direct pushes."""
    return {(r["repo"], r["sha"]): r["pr_number"] for r in rows(con, """
        SELECT c.repo, c.sha, MIN(p.pr_number) pr_number FROM git.commits c
        JOIN pr_commits.pr_commits p ON p.repo = c.repo AND p.sha = c.sha
        JOIN git.commits m ON m.repo = p.repo AND m.pr_number = p.pr_number AND m.is_merge = 1
        WHERE c.is_merge = 0 AND c.pr_number IS NULL GROUP BY c.repo, c.sha""")}


@lru_cache(maxsize=None)
def merge_day(con):
    """(repo, PR) -> the day its merge commit landed. A merge-commit PR's own commits keep their
    authored day on main, so that day says nothing about when the PR landed."""
    return {(r["repo"], r["pr_number"]): r["d"] for r in rows(con, """
        SELECT repo, pr_number, MIN(day) d FROM git.commits
        WHERE is_merge = 1 AND pr_number IS NOT NULL GROUP BY repo, pr_number""")}


@lru_cache(maxsize=None)
def commit_facts(con):
    """Original commits, each (repo, sha) once: a squash-merged PR's own commits, the commits a
    merge-commit PR brought onto main, and direct pushes. A squash commit is never work: a PR whose
    own commits weren't recovered is left out rather than counted by its squash."""
    ad = adoption(con)
    via, landed = merged_via(con), merge_day(con)
    main = rows(con, "SELECT repo, sha, day, subject, body_redacted, claude_trailer, is_bot, pr_number, "
                     "insertions + deletions churn FROM git.commits WHERE is_merge = 0 ORDER BY day, committed_ts, sha")
    pr_commits = defaultdict(list)
    for r in rows(con, "SELECT repo, pr_number, sha, ts, subject, body_redacted, claude_trailer, author, "
                       "insertions + deletions churn FROM pr_commits.pr_commits WHERE is_merge = 0"):
        pr_commits[(r["repo"], r["pr_number"])].append(r)
    seen, out = set(), []
    for m in main:
        if m["repo"] not in ad:
            continue
        pr = m["pr_number"] or via.get((m["repo"], m["sha"]))
        if m["pr_number"]:
            src = pr_commits.get((m["repo"], pr))
            if not src:
                continue
        else:
            src = [m]
        for c in src:
            # Stacked PRs list a commit under each PR that carried it; it counts in the first to land.
            if (m["repo"], c["sha"]) in seen:
                continue
            seen.add((m["repo"], c["sha"]))
            day = (c.get("ts") or c.get("day"))[:10]
            bot = bool(m["is_bot"]) or "dependabot" in (c.get("author") or "").lower()
            out.append({
                "repo": m["repo"], "sha": c["sha"], "day": day, "week": week_of(day), "month": day[:7],
                "pr": pr, "subject": c["subject"],
                "merged_day": m["day"] if m["pr_number"] else landed.get((m["repo"], pr), m["day"]),
                "body": c["body_redacted"] or "", "churn": c["churn"] or 0,
                "actor": "bot" if bot else "agent" if c["claude_trailer"] else "human",
                "conventional": bool(CONV_RE.match(c["subject"])),
                "category": ad[m["repo"]]["category"], "stage": stage_of(con, m["repo"], day),
                "original": True,
            })
    return out


@lru_cache(maxsize=None)
def changeset_facts(con):
    """Change sets, dated by the day their PR (or pushed commit) landed on main."""
    ad = adoption(con)
    via, landed = merged_via(con), merge_day(con)
    # A change set grouped from a squash (its PR's own commits weren't recovered) lists the squash
    # sha, which commit_facts omits; its lines come from main.
    churn, main_day = {}, {}
    for r in rows(con, "SELECT repo, sha, day, insertions + deletions churn FROM git.commits"):
        churn[(r["repo"], r["sha"])], main_day[(r["repo"], r["sha"])] = r["churn"] or 0, r["day"]
    churn.update({(c["repo"], c["sha"]): c["churn"] for c in commit_facts(con)})
    units = {(r["repo"], r["unit_kind"], r["unit_id"]): r for r in rows(con, "SELECT * FROM detectors.cs_units")}
    sets = rows(con, "SELECT * FROM detectors.cs_sets")
    member = defaultdict(int)
    for s in sets:
        for sha in json.loads(s["shas_json"]):
            member[(s["repo"], sha)] += 1
    out = []
    for s in sets:
        if s["repo"] not in ad:
            continue
        u = units[(s["repo"], s["unit_kind"], s["unit_id"])]
        day = main_day.get((s["repo"], u["main_sha"]))
        if not day:
            continue
        shas = json.loads(s["shas_json"])
        if s["unit_kind"] in ("pr", "pr-squash"):
            pr = int(s["unit_id"])
        else:
            pr = via.get((s["repo"], shas[0]))
            day = landed.get((s["repo"], pr), day) if pr else day
        out.append({
            "repo": s["repo"], "unit_kind": s["unit_kind"], "unit_id": s["unit_id"], "set_idx": s["set_idx"],
            "label": s["label"], "shas": shas, "n_commits": len(shas), "method": u["method"],
            "pr": pr,
            "day": day, "week": week_of(day), "month": day[:7],
            "lines": round(sum(churn.get((s["repo"], sha), 0) / member[(s["repo"], sha)] for sha in shas)),
            "category": ad[s["repo"]]["category"], "stage": stage_of(con, s["repo"], day),
            "dependabot": u["method"] == "dependabot",
        })
    return out


def weekly(facts, key, value=lambda f: 1, weeks=None, cats=None):
    """{category: [sum per week]} for facts grouped by key(f)."""
    acc = defaultdict(lambda: defaultdict(float))
    for f in facts:
        acc[key(f)][f["week"]] += value(f)
    cats = cats or sorted(acc)
    return {c: [round(acc[c].get(w, 0), 3) for w in weeks] for c in cats}
