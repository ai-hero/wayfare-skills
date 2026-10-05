"""One row per change set and one per original commit, for the method charts.

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

# The one session-log window every question measured on the session logs uses: complete from 25 Aug and
# frozen through 1 Oct. Before it the logs hold one session on 9 Aug, none 10-19 Aug, and 20-24 Aug only in
# part: transcript cleanup deletes by last-modified date, so those days kept whatever happened to be touched
# later. Do not move the start back to 20 Aug for the extra sessions; a partial span reads as a quiet one.
# ISO weeks start on Monday, so W35 (from 24 Aug) and W40 (to 1 Oct) are partial: shares and totals may use
# the whole window, but per-week averages take SESSION_FULL_WEEKS, or the short W40 drags the average down.
SESSION_WINDOW = ("2026-08-25", "2026-10-01")
SESSION_WINDOW_LABEL = "25 Aug–1 Oct"
SESSION_FULL_WEEKS = ["2026-W36", "2026-W37", "2026-W38", "2026-W39"]

# A chart's source line names where its numbers come from; one naming the session logs (or what is derived
# from them: turns, asks, subagent runs, D6 segments, D9 spend, limit events) carries SESSION_COVERAGE.
# "prompt history" is ~/.claude/history.jsonl, which reaches back to 2025 and is not session data.
SESSION_SOURCE_RE = re.compile(r"\bsessions?\b|\bturns\b|\basks\b|subagent|tool[ _]calls|\bD[69]\b|time segments"
                               r"|limit (events|messages)|\bspend\b|list price|Claude Code logs", re.I)


def in_session_window(day):
    return SESSION_WINDOW[0] <= str(day)[:10] <= SESSION_WINDOW[1]


def is_session_source(source):
    return bool(source and SESSION_SOURCE_RE.search(source))


def _day(d):
    return f"{d.day} {d:%b}"


def _span(a, b):
    if a == b:
        return _day(a)
    return f"{a.day}–{_day(b)}" if a.month == b.month else f"{_day(a)}–{_day(b)}"


@lru_cache(maxsize=None)
def session_gap():
    """What the logs hold before SESSION_WINDOW, split at the longest run of days with no session: the early
    sessions [(day, n)], the span with none (missing) and the partly kept span after it (partial), as date pairs."""
    import sqlite3
    from datetime import timedelta
    from ingest.fleet import OUT
    start = date.fromisoformat(SESSION_WINDOW[0])
    con = sqlite3.connect(os.path.join(OUT, "harness.sqlite"))
    pre = [(date.fromisoformat(d), n) for d, n in con.execute(
        "SELECT day, COUNT(*) FROM sessions WHERE day < ? GROUP BY day ORDER BY day", (SESSION_WINDOW[0],))]
    con.close()
    if not pre:
        return {"early": [], "missing": None, "partial": None}
    days = [d for d, _ in pre] + [start]
    cut = max(range(1, len(days)), key=lambda i: (days[i] - days[i - 1]).days)
    early, partial = pre[:cut], days[cut:-1]
    gap_from, gap_to = early[-1][0] + timedelta(1), (partial[0] if partial else start) - timedelta(1)
    return {"early": early, "missing": (gap_from, gap_to) if gap_from <= gap_to else None,
            "partial": (partial[0], start - timedelta(1)) if partial else None}


def gap_span(kind):
    """'10–19 Aug' for kind 'missing', '20–24 Aug' for 'partial'."""
    sp = session_gap()[kind]
    return _span(*sp) if sp else ""


def gap_days(kind):
    """The (first, last) ISO days of the missing or partial span."""
    sp = session_gap()[kind]
    return (sp[0].isoformat(), sp[1].isoformat()) if sp else None


def gap_range():
    """(first missing day, last partial day): the whole stretch whose session-derived values are unknown."""
    m, p = gap_days("missing"), gap_days("partial")
    return (m[0], (p or m)[1]) if m else None


def gap_note():
    return f"{gap_span('missing')} has no session logs and {gap_span('partial')} is only partly kept"


def gap_short():
    return f"none logged {gap_span('missing')}, partial {gap_span('partial')}"


def gap_weeks():
    """(missing, partial) ISO weeks before the window's first week: a week in the gap with no session is missing,
    one with some is partial. The window's own first week is left to the window."""
    from datetime import timedelta
    g = session_gap()
    if not g["missing"]:
        return set(), set()
    first = week_of(SESSION_WINDOW[0])
    have = {week_of(d.isoformat()) for d, _ in g["early"]} | {week_of((g["partial"] or g["missing"])[0].isoformat())}
    lo, hi = g["missing"][0], (g["partial"] or g["missing"])[1]
    weeks = sorted({week_of((lo + timedelta(i)).isoformat()) for i in range((hi - lo).days + 1)} - {first})
    missing = {w for w in weeks if w not in have}
    return missing, set(weeks) - missing


def gap_events():
    """The gap as two chart event marks: where the days with no logs start, and where the partial ones start."""
    return [(d[0], label) for d, label in ((gap_days("missing"), f"No session logs {gap_span('missing')}"),
                                           (gap_days("partial"), f"Partial session logs {gap_span('partial')}")) if d]


@lru_cache(maxsize=None)
def session_coverage():
    """The note every chart built on the session logs carries, read from the logs themselves: the window,
    then what the logs hold before it."""
    start, end = (date.fromisoformat(d) for d in SESSION_WINDOW)
    note = f"Session data: {_span(start, end)} ({(end - start).days + 1} days)."
    g = session_gap()
    early = g["early"]
    if not early:
        return note + " Nothing is logged before it."
    words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    n = sum(k for _, k in early)
    parts = [f"{words[n] if n < 10 else n} logged session{'s' if n != 1 else ''} on "
             f"{_span(early[0][0], early[-1][0]) if len(early) > 1 else _day(early[0][0])}"]
    if g["missing"]:
        parts.append(f"none on {gap_span('missing')}")
    if g["partial"]:
        parts.append(f"only partial records for {gap_span('partial')}")
    return note + " Before it: " + ", ".join(parts[:-1]) + (", and " if len(parts) > 2 else " and ") + parts[-1] + "."


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
    for (repo, pr), merged in offmain_prs(con).items():
        if repo not in ad:
            continue
        for c in pr_commits.get((repo, pr), []):
            if (repo, c["sha"]) in seen:
                continue
            seen.add((repo, c["sha"]))
            day = c["ts"][:10]
            out.append({
                "repo": repo, "sha": c["sha"], "day": day, "week": week_of(day), "month": day[:7],
                "pr": pr, "subject": c["subject"], "merged_day": merged,
                "body": c["body_redacted"] or "", "churn": c["churn"] or 0,
                "actor": "bot" if "dependabot" in (c.get("author") or "").lower() else "agent" if c["claude_trailer"] else "human",
                "conventional": bool(CONV_RE.match(c["subject"])),
                "category": ad[repo]["category"], "stage": stage_of(con, repo, day),
                "original": True,
            })
    return out


@lru_cache(maxsize=None)
def offmain_prs(con):
    """(repo, PR) -> merge day, for the PR units d1_changesets built with no commit on main (a branch
    rewritten after the merge): neither main's history nor merge_day can date them."""
    return {(r["repo"], int(r["unit_id"])): r["merged_ts"][:10] for r in rows(con, """
        SELECT u.repo, u.unit_id, p.merged_ts FROM detectors.cs_units u
        JOIN github.prs p ON p.repo = u.repo AND p.number = CAST(u.unit_id AS INTEGER)
        WHERE u.unit_kind = 'pr' AND u.main_sha IS NULL""")}


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
    offmain = offmain_prs(con)
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
        day = main_day.get((s["repo"], u["main_sha"])) or offmain.get((s["repo"], int(s["unit_id"]))) \
            if s["unit_kind"] == "pr" else main_day.get((s["repo"], u["main_sha"]))
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
