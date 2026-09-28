"""Harness spend attributed turn by turn to the PR, and from the PR to its change sets.

    from report.spend.attribution import spend_rows, spend_by_session, spend_by_pr, spend_by_changeset

Session-level attribution does not work: a session that touched several branches
(detectors.session_spend puts it in `multi_branch`) has no one PR to charge. Every assistant turn
carries the branch it ran on, so the session's reported cost is split over its pieces:

1. Pieces are the session's main-loop assistant turns and its subagent runs. Each gets a
   weight = its token-priced estimate (the ingest's price table, copied below).
2. The session's reported `cost_usd` is split in proportion to those weights. The total is
   therefore exactly the harness total; only its distribution is estimated.
3. A subagent run inherits the branch of the last main-loop turn before it started (its own
   branch, e.g. a worktree's, is not recorded).
4. A branch maps to the merged PR in the session's repo with that head branch, the first one
   merged at or after the turn (a turn up to 24 h after the merge still counts: post-merge
   cleanup). Other repos that merged a PR from the same branch name within 7 days share the
   cost evenly (a fleet-wide change pushed from one checkout). Failing both, a merged PR with
   that head branch in exactly one other repo.
5. A PR's cost is split over its change sets by lines (+20 so a one-line change set is not free).

Targets: `pr` (reached a merged PR by its branch), `pr_linked` (ran on the default branch in
a session that opened merged PRs: split evenly over those PRs; this is how a goal's fan-out
from main, and edits in sibling checkouts, reach their PRs), `default` (main/master/no
branch in a session that opened no merged PR: planning, questions, one-shot work never
shipped by PR), `dependabot`, `unmerged` (a branch
whose PR was closed or is still open), `no_pr` (a branch no PR was ever opened from).

Limits, for the notes: the price table is the ingest's rough one, so the split between
models within a session is approximate; the harness's cost-state total and the token-priced
estimate differ by session, so the scale factor between them is applied per session, not globally.
A session resumed on another day keeps its dollars on the days its turns ran.
"""
import json
import os
import sys
from bisect import bisect_left
from collections import defaultdict
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from record import changeset_facts, rows, week_of  # noqa: E402

IN_PRICE = {"opus-5-5": 4, "opus-5": 5, "opus-4": 5, "sonnet": 2, "fable": 10, "haiku": 1}
DEFAULT_BRANCHES = {None, "", "main", "master", "HEAD"}
# pr_links written before the 21 Sep rename name the old repo; github.prs files them under the new one.
ALIASES = {"hero-skills": "wayfare-skills"}
POST_MERGE_GRACE = 24 * 3600
FANOUT_WINDOW = 7 * 24 * 3600


def estimate(i, o, cr, cw, model):
    p = next((v for k, v in IN_PRICE.items() if k in (model or "")), 5)
    return ((i or 0) + 1.25 * (cw or 0) + 0.1 * (cr or 0) + 5 * (o or 0)) * p / 1e6


def model_family(model):
    m = model or ""
    for k, name in (("opus-5-5", "Opus 5.5"), ("opus-5", "Opus 5"), ("fable-5-1", "Fable 5.1"), ("fable-5", "Fable 5"),
                    ("sonnet", "Sonnet 5"), ("haiku", "Haiku")):
        if k in m:
            return name
    return "other"


def _epoch(ts):
    from datetime import datetime
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


@lru_cache(maxsize=None)
def _pr_index(con):
    by_repo, by_branch, unmerged = defaultdict(list), defaultdict(list), set()
    for r in rows(con, "SELECT repo, number, head_ref, author, merged_ts, created_ts FROM github.prs"):
        if not r["head_ref"]:
            continue
        if r["merged_ts"]:
            e = (_epoch(r["merged_ts"]), r["repo"], r["number"], r["author"] or "")
            by_repo[(r["repo"], r["head_ref"])].append(e)
            by_branch[r["head_ref"]].append(e)
        else:
            unmerged.add(r["head_ref"])
    for d in (by_repo, by_branch):
        for v in d.values():
            v.sort()
    return by_repo, by_branch, unmerged


def _match(con, repo, branch, t):
    """The merged PRs a turn on `branch` worked toward: a list of (merged_t, repo, number, author)."""
    by_repo, by_branch, unmerged = _pr_index(con)
    first = lambda cands: next((c for c in cands if c[0] >= t - POST_MERGE_GRACE), None)
    own = first(by_repo.get((repo, branch), []))
    # A fleet-wide change runs from one checkout and pushes the same branch name to several
    # repos; the turn's recorded branch is only the checkout it sat in.
    fan = {}
    for c in by_branch.get(branch, []):
        if c[1] != repo and t - POST_MERGE_GRACE <= c[0] <= t + FANOUT_WINDOW and c[1] not in fan:
            fan[c[1]] = c
    hits = ([own] if own else []) + list(fan.values())
    if hits:
        return hits
    if own is None and by_branch.get(branch):
        later = [c for c in by_branch[branch] if c[0] >= t - POST_MERGE_GRACE]
        if later and len({c[1] for c in later}) == 1:
            return [later[0]]
    return "unmerged" if branch in unmerged else None


@lru_cache(maxsize=None)
def spend_rows(con):
    """One row per costed piece: a main-loop turn or a subagent run, with its share of the session cost."""
    sessions = {r["session_id_hash"]: r for r in rows(con, "SELECT session_id_hash, repo, cost_usd, cost_method FROM harness.sessions")}
    turns = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts, model, branch, input_tokens i, output_tokens o, cache_read_tokens cr, "
                       "cache_write_tokens cw FROM harness.turns WHERE role='assistant' AND is_synthetic=0 AND ts IS NOT NULL "
                       "ORDER BY session_id_hash, ts"):
        turns[r["s"]].append(r)
    subs = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts_start ts, subagent_type, model, cost_usd_est FROM harness.subagent_runs "
                       "WHERE ts_start IS NOT NULL"):
        subs[r["s"]].append(r)
    out = []
    for sid, s in sessions.items():
        ts = turns.get(sid, [])
        pieces = [{"ts": t["ts"], "model": t["model"], "branch": t["branch"], "kind": "main", "subagent_type": None,
                   "w": estimate(t["i"], t["o"], t["cr"], t["cw"], t["model"])} for t in ts]
        times = [t["ts"] for t in ts]
        for r in subs.get(sid, []):
            k = bisect_left(times, r["ts"]) - 1
            pieces.append({"ts": r["ts"], "model": r["model"], "branch": ts[k]["branch"] if k >= 0 else (ts[0]["branch"] if ts else None),
                           "kind": "subagent", "subagent_type": r["subagent_type"] or "general-purpose", "w": r["cost_usd_est"] or 0})
        total_w = sum(p["w"] for p in pieces)
        if not total_w or not s["cost_usd"]:
            continue
        k = s["cost_usd"] / total_w
        for p in pieces:
            day = p["ts"][:10]
            out.append({"session": sid, "repo": s["repo"], "day": day, "week": week_of(day), "month": day[:7],
                        "branch": p["branch"], "model": p["model"], "family": model_family(p["model"]),
                        "kind": p["kind"], "subagent_type": p["subagent_type"], "usd": p["w"] * k,
                        "t": _epoch(p["ts"]), "cost_method": s["cost_method"]})
    res = []
    for r in out:
        b = r["branch"]
        if b in DEFAULT_BRANCHES:
            res.append({**r, "target": "default", "pr_repo": None, "pr": None})
            continue
        m = _match(con, r["repo"], b, r["t"])
        if isinstance(m, list):
            tgt = "dependabot" if b.startswith("dependabot/") else "pr"
            res.extend({**r, "usd": r["usd"] / len(m), "target": tgt, "pr_repo": c[1], "pr": c[2], "fanout": len(m)}
                       for c in m)
        else:
            tgt = "dependabot" if b.startswith("dependabot/") else "unmerged" if m == "unmerged" else "no_pr"
            res.append({**r, "target": tgt, "pr_repo": None, "pr": None})
    out = res
    return _link_default(con, out)


def _link_default(con, out):
    """Default-branch spend in a session that opened PRs goes to those PRs, split evenly (`pr_linked`)."""
    merged = {(r["repo"], r["number"]) for r in rows(con, "SELECT repo, number FROM github.prs WHERE merged_ts IS NOT NULL")}
    links = {}
    for r in rows(con, "SELECT session_id_hash, pr_links FROM harness.sessions"):
        prs = []
        for l in json.loads(r["pr_links"] or "[]"):
            repo, _, n = l.rpartition("#")
            repo = ALIASES.get(repo.split("/")[-1], repo.split("/")[-1])
            if n.isdigit() and (repo, int(n)) in merged:
                prs.append((repo, int(n)))
        links[r["session_id_hash"]] = sorted(set(prs))
    res = []
    for r in out:
        prs = links.get(r["session"]) if r["target"] == "default" else None
        if not prs:
            res.append(r)
            continue
        for repo, n in prs:
            res.append({**r, "usd": r["usd"] / len(prs), "target": "pr_linked", "pr_repo": repo, "pr": n})
    return res


def spend_by_session(con):
    acc = defaultdict(lambda: defaultdict(float))
    for r in spend_rows(con):
        acc[r["session"]][r["target"]] += r["usd"]
    return {s: dict(v) for s, v in acc.items()}


@lru_cache(maxsize=None)
def spend_by_pr(con):
    """{(repo, pr): {"usd", "main", "subagent", "review", "sessions", "first_day"}} for merged PRs that drew spend."""
    acc = {}
    for r in spend_rows(con):
        if r["pr"] is None:
            continue
        key = (r["pr_repo"], r["pr"])
        a = acc.setdefault(key, {"usd": 0.0, "main": 0.0, "subagent": 0.0, "review": 0.0, "sessions": set(),
                                 "first_day": r["day"], "by_family": defaultdict(float)})
        a["usd"] += r["usd"]
        a[r["kind"]] += r["usd"]
        if r["kind"] == "subagent" and "review" in (r["subagent_type"] or ""):
            a["review"] += r["usd"]
        a["sessions"].add(r["session"])
        a["first_day"] = min(a["first_day"], r["day"])
        a["by_family"][r["family"]] += r["usd"]
    return acc


@lru_cache(maxsize=None)
def spend_by_changeset(con):
    """Change-set facts (record.changeset_facts) for PRs with attributed spend, each with its `usd` share."""
    by_pr = spend_by_pr(con)
    sets = defaultdict(list)
    for f in changeset_facts(con):
        if f["pr"] is not None:
            sets[(f["repo"], f["pr"])].append(f)
    out = []
    for key, a in by_pr.items():
        fs = sets.get(key)
        if not fs:
            continue
        w = [f["lines"] + 20 for f in fs]
        for f, wi in zip(fs, w):
            fam = max(a["by_family"], key=a["by_family"].get)
            out.append({**f, "usd": a["usd"] * wi / sum(w), "pr_usd": a["usd"], "pr_sets": len(fs),
                        "review_usd": a["review"] * wi / sum(w), "subagent_usd": a["subagent"] * wi / sum(w),
                        "family": fam})
    return out


if __name__ == "__main__":
    from cube.db import connect
    con = connect()
    rs = spend_rows(con)
    tot = defaultdict(float)
    for r in rs:
        tot[r["target"]] += r["usd"]
    print({k: round(v) for k, v in tot.items()}, round(sum(tot.values())))
    cs = spend_by_changeset(con)
    print(len(spend_by_pr(con)), "PRs;", len(cs), "change sets; $", round(sum(c["usd"] for c in cs)))
