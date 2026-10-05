"""Work items and flow series: work items, flow and wall time.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/work_items/data.py

One function per question (q_backlog_trend..q_change_set_size_vs_pr_time), each returning the series its slides plot plus the
numbers its title and notes quote. Weeks run 2026-W01..W40; a week before a source existed
is None ("not tracked"), never 0.

Item dates are days: ingest/plans.py dates an item by its first log line and its end by the
last log line that mentions done/shipped/merged. `.plans/` is excluded from git in every
repo (.git/info/exclude), so no commit dates an item file; hours come from PRs and sessions.
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect  # noqa: E402
from record import adoption, changeset_facts, gap_range, gap_weeks, rows, stage_of, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, REPO_ALIASES, category_of  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 41)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
ITEMS_FROM = "2026-W30"      # first work item in .plans: 23 Jul
SESSIONS_FROM = "2026-W32"   # first session log: 9 Aug
GOALS_FROM = "2026-W35"      # first goal: 29 Aug
LOCAL = ZoneInfo("America/Los_Angeles")
CLOSED_GAP_H = 8             # brief's session-time rule: a longer gap means the session was closed
WORKING_GAP_MIN = 5          # D6: a gap this short is working time
# Session logs are missing, then partial, over record.gap_range(); those weeks are "data not available", never
# zero or idle.
OUTAGE = (datetime.fromisoformat(gap_range()[0]).replace(tzinfo=ZoneInfo("America/Los_Angeles")),
          datetime.fromisoformat(gap_range()[1]).replace(tzinfo=ZoneInfo("America/Los_Angeles")) + timedelta(days=1))
OUTAGE_WEEKS = tuple(sorted(set().union(*gap_weeks())))
STAGE_ORDER = ["No skills yet", "Skills", "+ work items", "+ goals", "+ messages"]


# ------------------------------------------------------------------ helpers

def d(ts):
    return date.fromisoformat(ts[:10]) if ts else None


def dt_(ts):
    if not ts:
        return None
    x = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)


def med(v):
    v = [x for x in v if x is not None]
    return round(statistics.median(v), 2) if v else None


def pctl(v, p):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 2)


def share(a, b):
    return round(a / b, 3) if b else None


def tracked(series, first):
    """None before the week a source began."""
    return [None if w < first else v for w, v in zip(WEEKS, series)]


def no_outage(series):
    return [None if w in OUTAGE_WEEKS else v for w, v in zip(WEEKS, series)]


def weekly_stat(pairs, fn, first=None, min_n=1):
    """pairs: (week, value). fn over each week's values; None where fewer than min_n."""
    acc = defaultdict(list)
    for w, v in pairs:
        acc[w].append(v)
    out = [fn(acc[w]) if len(acc[w]) >= min_n else None for w in WEEKS]
    return tracked(out, first) if first else out


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    if len(x) < 5:
        return None
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 2) if den else None


def pr_link_key(link):
    m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
    return (REPO_ALIASES.get(m.group(1), m.group(1)), int(m.group(2))) if m else None


TYPE_GROUP = {"feature": "Feature", "polish": "Feature", "bug": "Defect", "security": "Security",
              "chore": "Upkeep", "docs": "Upkeep", "research": "Research / idea", "feedback": "Signal",
              "task": "Upkeep", "unknown": "Unlabelled"}
TYPE_GROUPS = ["Feature", "Defect", "Security", "Upkeep", "Research / idea", "Signal", "Unlabelled"]


def _prs(con):
    out = {}
    for r in rows(con, "SELECT repo, number, head_ref, created_ts, merged_ts, closed_ts, author_is_bot, additions, "
                       "deletions, changed_files, commits FROM github.prs"):
        if r["repo"] in OUT_OF_SCOPE:
            continue
        out[(r["repo"], r["number"])] = r
    return out


def items(con):
    """Every non-goal work item with its dates, grouping and the merged PRs it reaches."""
    prs = _prs(con)
    by_head = defaultdict(list)
    for (repo, n), p in prs.items():
        if p["merged_ts"]:
            by_head[(repo, p["head_ref"])].append(n)
    goal_branch, goal_members = {}, defaultdict(set)
    for r in rows(con, "SELECT repo, item_id, raw_frontmatter_json j FROM plans.plan_items WHERE type='goal'"):
        fm = json.loads(r["j"] or "{}")
        goal_branch[(r["repo"], r["item_id"])] = fm.get("branch")
    for r in rows(con, "SELECT repo, goal_id, members FROM plans.goals"):
        for m in json.loads(r["members"] or "[]"):
            goal_members[(r["repo"], str(m))].add(r["goal_id"])
    goal_prs = {}
    for (repo, gid), br in goal_branch.items():
        got = set(by_head.get((repo, br), [])) if br else set()
        if not got:
            got = {n for (rp, n), p in prs.items() if rp == repo and p["merged_ts"]
                   and re.search(rf"goal-{gid}(\D|$)", p["head_ref"] or "")}
        goal_prs[(repo, gid)] = got
    ref_prs = defaultdict(set)
    for r in rows(con, "SELECT repo, plan_item_ref, pr_number FROM git.commits WHERE plan_item_ref IS NOT NULL "
                       "AND pr_number IS NOT NULL"):
        ref_prs[(r["repo"], str(r["plan_item_ref"]))].add(r["pr_number"])
    # an old-schema discovered_from is often prose ("harden audit, 2026-08-25"): only an edge to a real item is found work
    found = {(r["repo"], r["src_item"]) for r in rows(con, """
        SELECT e.repo, e.src_item FROM plans.item_edges e JOIN plans.plan_items p
        ON p.repo = e.dst_repo AND p.item_id = e.dst_item WHERE e.kind = 'discovered_from'""")}
    out = []
    for r in rows(con, "SELECT * FROM plans.plan_items WHERE type != 'goal'"):
        fm = json.loads(r["raw_frontmatter_json"] or "{}")
        key = (r["repo"], r["item_id"])
        linked, how = set(), None
        for k in ("pr", "merged_pr", "merged_prs"):
            v = fm.get(k)
            for x in (v if isinstance(v, list) else [v]):
                m = re.search(r"(\d+)$", str(x)) if x is not None else None
                if m and (r["repo"], int(m.group(1))) in prs and prs[(r["repo"], int(m.group(1)))]["merged_ts"]:
                    linked.add(int(m.group(1)))
                    how = how or "item records its PR"
        if fm.get("branch"):
            got = set(by_head.get((r["repo"], fm["branch"]), []))
            if got - linked:
                how = how or "item records its branch"
            linked |= got
        goals = ({r["goal_id"]} if r["goal_id"] else set()) | goal_members.get(key, set())
        for g in goals:
            got = goal_prs.get((r["repo"], g), set())
            if got - linked:
                how = how or "its goal's PR"
            linked |= got
        if not linked and key in ref_prs:
            linked |= ref_prs[key]
            how = "a commit names it"
        created, ready, done_ = d(r["created_ts"]), d(r["ready_ts"]), d(r["done_ts"])
        res = fm.get("resolution")
        if r["status"] == "dropped":
            ending = "Dropped"
        elif r["status"] == "done" and res in ("obsolete", "rejected"):
            ending = "Obsolete / rejected"
        elif r["status"] == "done" and res == "delivered" or r["status"] == "delivered":
            ending = "Delivered upstream"
        elif r["status"] == "done":
            ending = "Shipped"
        else:
            ending = None
        # an old-schema "delivered" status has no done_ts; its last log date ends it
        end_day = done_ if ending in ("Shipped", "Obsolete / rejected", "Delivered upstream") else (
            d(r["updated_ts"]) if ending == "Dropped" else None)
        if ending and end_day is None:
            end_day = d(r["updated_ts"])
        merged = sorted(dt_(prs[(r["repo"], n)]["merged_ts"]) for n in linked)
        out.append({
            "repo": r["repo"], "id": r["item_id"], "title": r["title"], "type": r["type"],
            "group": TYPE_GROUP.get(r["type"], "Unlabelled"), "shape": fm.get("shape"),
            "status": r["status"], "ending": ending, "resolution": res, "origin": r["origin"] or "",
            "severity": fm.get("severity"), "era": r["schema_era"],
            "created": created, "ready": ready, "end": end_day,
            "week": week_of(created.isoformat()) if created else None,
            "end_week": week_of(end_day.isoformat()) if end_day else None,
            "prs": linked, "link_how": how, "first_merge": merged[0] if merged else None,
            "goal": sorted(goals)[0] if goals else None, "found": key in found,
            "discovered_note": fm.get("discovered_from") if isinstance(fm.get("discovered_from"), str) else None,
            "body_chars": r["body_chars"], "one_way_door": fm.get("one_way_door"),
            "depends_on": fm.get("depends_on") or [], "category": category_of(r["repo"]),
            "stage": stage_of(con, r["repo"], created.isoformat()) if created and r["repo"] in adoption(con) else None,
            "file": r["file_path"],
        })
    return out


# ------------------------------------------------------------------ the work items

def q_backlog_trend_backlog(con, its):
    """Items opened and closed per week, and the open count at each week's end."""
    opened = Counter(i["week"] for i in its if i["week"])
    closed = Counter(i["end_week"] for i in its if i["end_week"])
    open_end, by_repo = [], defaultdict(list)
    repos = sorted({i["repo"] for i in its}, key=lambda r: -sum(1 for i in its if i["repo"] == r))
    for w in WEEKS:
        end = date.fromisocalendar(2026, int(w[6:]), 7)
        is_open = [i for i in its if i["created"] and i["created"] <= end and not (i["end"] and i["end"] <= end)]
        open_end.append(len(is_open))
        for r in repos:
            by_repo[r].append(sum(1 for i in is_open if i["repo"] == r))
    today = date(2026, 9, 24)
    now_open = [i for i in its if not i["ending"]]
    ages = [(today - i["created"]).days for i in now_open if i["created"]]
    status_now = Counter(i["status"] for i in now_open)
    since = [w for w in WEEKS if w >= ITEMS_FROM]
    return {
        "weeks": WEEKS,
        "series": {"Opened": tracked([opened.get(w, 0) for w in WEEKS], ITEMS_FROM),
                   "Closed": tracked([closed.get(w, 0) for w in WEEKS], ITEMS_FROM)},
        "open_end": tracked(open_end, ITEMS_FROM),
        "by_repo": {r: tracked(v, ITEMS_FROM) for r, v in by_repo.items()},
        "opened_total": sum(opened.values()), "closed_total": sum(closed.values()),
        "open_now": len(now_open), "open_median_age": med(ages), "open_over_14d": sum(1 for a in ages if a > 14),
        "status_now": dict(status_now.most_common()),
        "peak_open": max(open_end), "peak_week": WEEKS[open_end.index(max(open_end))],
        "weeks_closed_ge_opened": sum(1 for w in since if closed.get(w, 0) >= opened.get(w, 0)), "n_weeks": len(since),
        "open_by_repo_now": Counter(i["repo"] for i in now_open).most_common(),
    }


def q_work_item_kinds(con, its):
    """Share of items created each week by kind; and the mix by the stage the repo had reached."""
    acc = defaultdict(Counter)
    for i in its:
        if i["week"]:
            acc[i["week"]][i["group"]] += 1
    series = {g: tracked([share(acc[w][g], sum(acc[w].values())) if sum(acc[w].values()) else None for w in WEEKS],
                         ITEMS_FROM) for g in TYPE_GROUPS}
    by_stage = defaultdict(Counter)
    for i in its:
        if i["stage"]:
            by_stage[i["stage"]][i["group"]] += 1
    stages = [s for s in STAGE_ORDER if by_stage.get(s)]
    months = defaultdict(Counter)
    for i in its:
        if i["created"]:
            months[i["created"].isoformat()[:7]][i["group"]] += 1
    feat = {m: share(c["Feature"], sum(c.values())) for m, c in sorted(months.items())}
    struct = {m: share(c["Upkeep"] + c["Defect"] + c["Security"], sum(c.values())) for m, c in sorted(months.items())}
    shapes = Counter(i["shape"] or "(old schema)" for i in its)
    total = Counter(i["group"] for i in its)
    return {"weeks": WEEKS, "series": series, "groups": TYPE_GROUPS,
            "stages": stages, "by_stage": {s: [share(by_stage[s][g], sum(by_stage[s].values())) for g in TYPE_GROUPS]
                                           for s in stages},
            "by_stage_n": {s: sum(by_stage[s].values()) for s in stages},
            "feature_share_by_month": feat, "structural_share_by_month": struct,
            "total": dict(total), "n": len(its), "shapes": dict(shapes)}


SOURCE_OF = {"wayfare": "Roadmap sync", "wayfare-sync-plan": "Roadmap sync", "harden": "Security audit",
             "one-shot": "Owner asked", "rahul": "Owner asked", "user": "Owner asked", "conversation": "Owner asked",
             "think-it-through": "Owner asked", "wayfare-grill-idea": "Owner asked", "wayfare-build-task": "Owner asked",
             "wayfare-run-task": "Owner asked", "message": "Another repo's message", "self-review": "Found in other work"}
SOURCES = ["Found in other work", "Roadmap sync", "Owner asked", "Security audit", "Another repo's message", "Not recorded"]


def q_work_sources(con, its):
    """Where items come from, weekly share; discovery chain depth and fan-out."""
    def source(i):
        if i["found"]:
            return "Found in other work"
        # Old-schema items carry the audit as prose ("hero-skills:harden audit, 2026-08-25 (Part C)") with no
        # origin; the figure-2.3 audit found every such item to be a hardening finding, not an unrecorded source.
        if not i["origin"] and re.search(r"harden", i["discovered_note"] or "", re.I):
            return "Security audit"
        return SOURCE_OF.get(i["origin"], "Not recorded" if not i["origin"] else "Owner asked")
    for i in its:
        i["source"] = source(i)
    acc = defaultdict(Counter)
    for i in its:
        if i["week"]:
            acc[i["week"]][i["source"]] += 1
    series = {s: tracked([share(acc[w][s], sum(acc[w].values())) if sum(acc[w].values()) else None for w in WEEKS],
                         ITEMS_FROM) for s in SOURCES}
    fw = rows(con, "SELECT * FROM detectors.found_work")
    depth = Counter(r["depth"] for r in fw)
    roots = {}
    for r in fw:
        roots[(r["root_repo"], r["root_item_id"])] = r["root_fan_out"]
    tree = Counter()
    for r in fw:
        tree[(r["root_repo"], r["root_item_id"])] += 1
    deepest = max(fw, key=lambda r: r["depth"]) if fw else None
    chain = []
    if deepest:
        parent = {(r["repo"], r["src_item"]): (r["dst_repo"], r["dst_item"]) for r in rows(
            con, "SELECT repo, src_item, dst_repo, dst_item FROM plans.item_edges WHERE kind='discovered_from'")}
        title = {(r["repo"], r["item_id"]): r["title"] for r in rows(con, "SELECT repo, item_id, title FROM plans.plan_items")}
        k = (deepest["repo"], deepest["item_id"])
        while k and len(chain) < 10:
            chain.append(f"{k[0]} #{k[1]}: {title.get(k, '(not an item: ' + str(k[1]) + ')')}")
            k = parent.get(k)
    total = Counter(i["source"] for i in its)
    months = defaultdict(Counter)
    for i in its:
        if i["created"]:
            months[i["created"].isoformat()[:7]][i["source"]] += 1
    found_by_month = {m: share(c["Found in other work"], sum(c.values())) for m, c in sorted(months.items())}
    # does found work ship as often as the rest?
    def shipped_share(sel):
        ended = [i for i in its if sel(i) and i["created"] and i["created"] <= date(2026, 9, 10)]
        return share(sum(1 for i in ended if i["ending"] == "Shipped"), len(ended))
    # Figure 2.3: what became of each source's items (completed = shipped or delivered upstream).
    outcome_of = lambda i: ("Completed" if i["ending"] in ("Shipped", "Delivered upstream") else
                            "Abandoned" if i["ending"] else "Still open")
    outcomes = {s: Counter(outcome_of(i) for i in its if i["source"] == s) for s in SOURCES}
    return {"weeks": WEEKS, "series": series, "sources": SOURCES, "total": dict(total), "n": len(its),
            "outcomes": {s: dict(c) for s, c in outcomes.items()}, "outcome_names": ["Completed", "Still open", "Abandoned"],
            "backlog": q_backlog_trend_backlog(con, its),
            "depth": dict(sorted(depth.items())), "n_found": len(fw), "roots": len(roots),
            "max_depth": max(depth) if depth else 0, "tree_sizes": sorted(tree.values(), reverse=True)[:10],
            "biggest_tree": max(tree.items(), key=lambda kv: kv[1]) if tree else None,
            "deep_share": share(sum(v for k, v in depth.items() if k >= 2), len(fw)),
            "chain_example": list(reversed(chain)), "found_by_month": found_by_month,
            "found_shipped": shipped_share(lambda i: i["source"] == "Found in other work"),
            "other_shipped": shipped_share(lambda i: i["source"] != "Found in other work")}


def shipped(its):
    out = [i for i in its if i["ending"] == "Shipped" and i["created"] and i["end"]]
    for i in out:
        i["lead"] = (i["end"] - i["created"]).days
    return out


LEAD_BUCKETS = [("Same day", 0), ("Next day", 1), ("2–3 days", 3), ("4–7 days", 7), ("Over a week", 10 ** 6)]


def mean(v):
    v = [x for x in v if x is not None]
    return round(statistics.mean(v), 2) if v else None


def q_item_lead_time(con, its):
    """Days from filed to shipped, per week of shipping; by stage and by repo."""
    s = shipped(its)
    pairs = [(i["end_week"], i["lead"]) for i in s]
    by_stage = defaultdict(list)
    for i in s:
        by_stage[stage_of(con, i["repo"], i["end"].isoformat()) if i["repo"] in adoption(con) else "?"].append(i["lead"])
    by_repo = defaultdict(list)
    for i in s:
        by_repo[i["repo"]].append(i["lead"])
    repos = sorted([r for r in by_repo if len(by_repo[r]) >= 5], key=lambda r: -len(by_repo[r]))
    # a PR merge gives the end to the hour: same-day items still took hours
    same_day = [i for i in s if i["lead"] == 0]
    hist = Counter(min(i["lead"], 15) for i in s)
    months = defaultdict(list)
    for i in s:
        months[i["end"].isoformat()[:7]].append(i["lead"])
    acc = defaultdict(Counter)
    for i in s:
        acc[i["end_week"]][next(b for b, hi in LEAD_BUCKETS if i["lead"] <= hi)] += 1
    buckets = {b: tracked([share(acc[w][b], sum(acc[w].values())) if sum(acc[w].values()) else None for w in WEEKS],
                          ITEMS_FROM) for b, _ in LEAD_BUCKETS}
    return {"weeks": WEEKS, "buckets": buckets,
            "within_1d": share(sum(1 for i in s if i["lead"] <= 1), len(s)),
            "over_7d": share(sum(1 for i in s if i["lead"] > 7), len(s)),
            "series": {"Median days": weekly_stat(pairs, med, ITEMS_FROM),
                       "80th percentile": weekly_stat(pairs, lambda v: pctl(v, 0.8), ITEMS_FROM)},
            "n": len(s), "median": med([i["lead"] for i in s]), "p80": pctl([i["lead"] for i in s], 0.8),
            "mean": round(statistics.mean(i["lead"] for i in s), 1),
            "same_day_share": share(len(same_day), len(s)),
            "by_stage": {k: {"n": len(v), "median": med(v), "p80": pctl(v, 0.8)} for k, v in by_stage.items()},
            "by_repo": [(r, len(by_repo[r]), med(by_repo[r]), pctl(by_repo[r], 0.8)) for r in repos],
            "by_month": {m: (len(v), med(v), pctl(v, 0.8)) for m, v in sorted(months.items())},
            "hist": [hist.get(k, 0) for k in range(16)]}


def q_ready_mark_wait(con, its):
    """Created -> ready (the owner's gate) and ready -> shipped, in days."""
    s = [i for i in shipped(its) if i["ready"]]
    for i in s:
        i["to_ready"] = (i["ready"] - i["created"]).days
        i["after_ready"] = (i["end"] - i["ready"]).days
    marked = [i for i in its if i["ready"] and i["created"]]
    for i in marked:
        i["to_ready"] = (i["ready"] - i["created"]).days
    by_repo = defaultdict(list)
    for i in marked:
        by_repo[i["repo"]].append(i["to_ready"])
    repos = sorted([r for r in by_repo if len(by_repo[r]) >= 5], key=lambda r: -len(by_repo[r]))
    neg = sum(1 for i in marked if i["to_ready"] < 0)
    long_plans = [i for i in marked if i["body_chars"]]
    cut = med([i["body_chars"] for i in long_plans])
    ready_week = [(week_of(i["ready"].isoformat()), i["to_ready"]) for i in marked]
    n_shipped = len(shipped(its))
    no_mark = [i for i in shipped(its) if not i["ready"]]
    return {"weeks": WEEKS,
            "series": {"Filed → ready": weekly_stat([(w, max(v, 0)) for w, v in ready_week], mean, ITEMS_FROM),
                       "Ready → shipped": weekly_stat([(i["end_week"], max(i["after_ready"], 0)) for i in s], mean,
                                                      ITEMS_FROM)},
            "mean_to_ready": mean([max(i["to_ready"], 0) for i in marked]),
            "mean_after_ready": mean([max(i["after_ready"], 0) for i in s]),
            "n_marked": len(marked), "n_shipped_marked": len(s), "n_shipped": n_shipped,
            "shipped_without_mark": len(no_mark),
            "no_mark_by_era": dict(Counter(i["era"] for i in no_mark)),
            "median_to_ready": med([i["to_ready"] for i in marked]),
            "median_after_ready": med([i["after_ready"] for i in s]),
            "same_day_ready": share(sum(1 for i in marked if i["to_ready"] <= 0), len(marked)),
            "ready_before_created": neg,
            "owner_share_of_lead": share(sum(max(i["to_ready"], 0) for i in s),
                                         sum(max(i["to_ready"], 0) + max(i["after_ready"], 0) for i in s)),
            "by_repo": [(r, len(by_repo[r]), share(sum(1 for v in by_repo[r] if v <= 0), len(by_repo[r])),
                         med(by_repo[r])) for r in repos],
            "long_vs_short": {"cut_chars": cut,
                              "long": med([i["to_ready"] for i in long_plans if i["body_chars"] > cut]),
                              "short": med([i["to_ready"] for i in long_plans if i["body_chars"] <= cut])},
            "one_way": med([i["to_ready"] for i in marked if i["one_way_door"] is True]),
            "one_way_n": sum(1 for i in marked if i["one_way_door"] is True)}


def q_pickup_wait(con, its):
    """Ready -> first original commit of its PR; a dependency's end -> the dependent's first commit."""
    first_commit = {}
    for r in rows(con, "SELECT repo, pr_number, MIN(ts) t FROM pr_commits.pr_commits WHERE is_merge=0 GROUP BY repo, pr_number"):
        first_commit[(r["repo"], r["pr_number"])] = dt_(r["t"])
    def start(i):
        ts = [first_commit[(i["repo"], n)] for n in i["prs"] if (i["repo"], n) in first_commit]
        return min(ts) if ts else None
    for i in its:
        i["start"] = start(i)
    local_day = lambda t: t.astimezone(LOCAL).date()
    pick = [i for i in its if i["ready"] and i["start"]]
    for i in pick:
        i["pickup"] = (local_day(i["start"]) - i["ready"]).days
    # the item was built before its ready mark: the mark followed the work
    early = [i for i in pick if i["pickup"] < 0]
    ok = [i for i in pick if i["pickup"] >= 0]
    by_key = {(i["repo"], str(i["id"])): i for i in its}
    unblock = []
    for i in its:
        if not i["start"]:
            continue
        ends = []
        for dep in i["depends_on"]:
            dp = by_key.get((i["repo"], str(dep)))
            if dp and dp["end"]:
                ends.append(dp["end"])
        if ends:
            unblock.append((i, (local_day(i["start"]) - max(ends)).days))
    waited = [v for _, v in unblock if v >= 0]
    by_stage = defaultdict(list)
    for i in ok:
        by_stage[i["stage"]].append(i["pickup"])
    hist = Counter(min(i["pickup"], 10) for i in ok)
    return {"weeks": WEEKS,
            "series": {"Ready → first commit": weekly_stat([(week_of(i["ready"].isoformat()), i["pickup"]) for i in ok],
                                                          mean, ITEMS_FROM),
                       "Dependency done → first commit": weekly_stat(
                           [(week_of(i["start"].date().isoformat()), v) for i, v in unblock if v >= 0], mean, ITEMS_FROM)},
            "mean_pickup": mean([i["pickup"] for i in ok]), "mean_unblock": mean(waited),
            "n_ready_with_start": len(pick), "n_marked": sum(1 for i in its if i["ready"]),
            "started_before_ready": len(early), "median_pickup": med([i["pickup"] for i in ok]),
            "p80_pickup": pctl([i["pickup"] for i in ok], 0.8),
            "same_day_pickup": share(sum(1 for i in ok if i["pickup"] == 0), len(ok)),
            "n_unblock": len(unblock), "median_unblock": med(waited), "p80_unblock": pctl(waited, 0.8),
            "built_before_dep_done": sum(1 for _, v in unblock if v < 0),
            "hist": [hist.get(k, 0) for k in range(11)], "by_stage": {k: (len(v), med(v)) for k, v in by_stage.items()},
            "n_items_with_prs": sum(1 for i in its if i["prs"])}


def q_security_work_speed(con, its):
    """Filed-to-shipped days for security vs defect vs feature; the hardening audit's ending."""
    s = shipped(its)
    months = {g: defaultdict(list) for g in ("Security", "Defect", "Feature")}
    for i in s:
        if i["group"] in months:
            months[i["group"]][i["end"].isoformat()[:7]].append(i["lead"])
    sec = [i for i in its if i["group"] == "Security" or i["origin"] == "harden"]
    by_repo = defaultdict(Counter)
    for i in sec:
        by_repo[i["repo"]][i["ending"] or "Open"] += 1
    sev = defaultdict(list)
    for i in s:
        if i in sec and i["severity"]:
            sev[str(i["severity"]).lower()].append(i["lead"])
    open_sec = [i for i in sec if not i["ending"]]
    today = date(2026, 9, 24)
    wk = {g: weekly_stat([(i["end_week"], 1 if i["lead"] <= 1 else 0) for i in s if i["group"] == g],
                         lambda v: share(sum(v), len(v)), ITEMS_FROM, min_n=3) for g in months}
    mo = ["2026-07", "2026-08", "2026-09"]
    monthly = {g: [share(sum(1 for v in months[g].get(m, []) if v <= 1), len(months[g].get(m, [])))
                   if len(months[g].get(m, [])) >= 3 else None for m in mo] for g in months}
    return {"weeks": WEEKS, "series": wk, "months3": mo, "monthly": monthly,
            "monthly_n": {g: [len(months[g].get(m, [])) for m in mo] for g in months},
            "within_1d": {g: share(sum(1 for i in s if i["group"] == g and i["lead"] <= 1),
                                   sum(1 for i in s if i["group"] == g)) for g in months},
            "n": {g: sum(len(v) for v in months[g].values()) for g in months},
            "median": {g: med([x for v in months[g].values() for x in v]) for g in months},
            "p80": {g: pctl([x for v in months[g].values() for x in v], 0.8) for g in months},
            "sec_total": len(sec), "sec_shipped": sum(1 for i in sec if i["ending"] == "Shipped"),
            "sec_open": len(open_sec), "sec_dropped": sum(1 for i in sec if i["ending"] in ("Dropped", "Obsolete / rejected")),
            "open_ages": sorted((today - i["created"]).days for i in open_sec if i["created"]),
            "open_list": [(i["repo"], i["id"], i["status"], i["severity"], i["title"]) for i in open_sec],
            "by_repo": {r: dict(c) for r, c in sorted(by_repo.items(), key=lambda kv: -sum(kv[1].values()))},
            "by_severity": {k: (len(v), med(v)) for k, v in sev.items()}}


ENDINGS = ["Shipped", "Delivered upstream", "Obsolete / rejected", "Dropped"]


def q_work_item_endings(con, its):
    """Closures per week by how they ended; open items by age at each week's end."""
    acc = defaultdict(Counter)
    for i in its:
        if i["end_week"]:
            acc[i["end_week"]][i["ending"]] += 1
    series = {e: tracked([acc[w][e] for w in WEEKS], ITEMS_FROM) for e in ENDINGS}
    ages = {"Open under a week": [], "Open 1–2 weeks": [], "Open over 2 weeks": []}
    for w in WEEKS:
        end = date.fromisocalendar(2026, int(w[6:]), 7)
        a = [(end - i["created"]).days for i in its if i["created"] and i["created"] <= end
             and not (i["end"] and i["end"] <= end)]
        ages["Open under a week"].append(sum(1 for x in a if x < 7))
        ages["Open 1–2 weeks"].append(sum(1 for x in a if 7 <= x <= 14))
        ages["Open over 2 weeks"].append(sum(1 for x in a if x > 14))
    ages = {k: tracked(v, ITEMS_FROM) for k, v in ages.items()}
    abandoned = [i for i in its if i["ending"] in ("Dropped", "Obsolete / rejected")]
    logs = defaultdict(list)
    for r in rows(con, "SELECT repo, item_id, ts, kind, text_redacted FROM plans.item_logs ORDER BY ts"):
        logs[(r["repo"], r["item_id"])].append(r["text_redacted"] or "")
    ab = [{"repo": i["repo"], "id": i["id"], "ending": i["ending"], "type": i["type"], "title": i["title"],
           "last_log": (logs.get((i["repo"], i["id"])) or [""])[-1][:300]} for i in abandoned]
    tot = Counter(i["ending"] or "Open" for i in its)
    return {"weeks": WEEKS, "series": series, "ages": ages, "abandoned": ab, "totals": dict(tot), "n": len(its),
            "ended": sum(v for k, v in tot.items() if k != "Open")}


def q_prs_per_work_item(con, its):
    """PRs per shipped item, and items per PR, by week the item shipped."""
    s = shipped(its)
    acc = defaultdict(Counter)
    for i in s:
        k = "No PR found" if not i["prs"] else "One PR" if len(i["prs"]) == 1 else "Two or more PRs"
        i["pr_bucket"] = k
        acc[i["end_week"]][k] += 1
    cats = ["One PR", "Two or more PRs", "No PR found"]
    series = {c: tracked([acc[w][c] for w in WEEKS], ITEMS_FROM) for c in cats}
    per_pr = defaultdict(set)
    for i in s:
        for n in i["prs"]:
            per_pr[(i["repo"], n)].add(i["id"])
    prs = _prs(con)
    ipp = defaultdict(list)
    for (repo, n), ids in per_pr.items():
        m = prs[(repo, n)]["merged_ts"]
        ipp[week_of(m[:10])].append(len(ids))
    items_per_pr = tracked([round(statistics.mean(ipp[w]), 2) if ipp.get(w) else None for w in WEEKS], ITEMS_FROM)
    # item days vs its PR's hours
    pair = []
    for i in s:
        if len(i["prs"]) == 1:
            p = prs[(i["repo"], next(iter(i["prs"])))]
            h = (dt_(p["merged_ts"]) - dt_(p["created_ts"])).total_seconds() / 3600
            pair.append((i, (i["end"] - i["created"]).days, h))
    by_stage = defaultdict(lambda: ([], []))
    for i, days, h in pair:
        st = stage_of(con, i["repo"], i["end"].isoformat()) if i["repo"] in adoption(con) else "?"
        by_stage[st][0].append(days)
        by_stage[st][1].append(h / 24)
    how = Counter(i["link_how"] or "none" for i in s)
    before = [i for i in s if i["end"] < date(2026, 9, 18)]
    after = [i for i in s if i["end"] >= date(2026, 9, 18)]
    ipp_before = [len(v) for (repo, n), v in per_pr.items() if prs[(repo, n)]["merged_ts"][:10] < "2026-09-18"]
    ipp_after = [len(v) for (repo, n), v in per_pr.items() if prs[(repo, n)]["merged_ts"][:10] >= "2026-09-18"]
    return {"weeks": WEEKS, "series": series, "items_per_pr": items_per_pr, "n": len(s),
            "ipp_dist": {"before": dict(Counter(ipp_before)), "after": dict(Counter(ipp_after))},
            "totals": {c: sum(1 for i in s if i["pr_bucket"] == c) for c in cats}, "link_how": dict(how),
            "one_pr_share_linked": share(sum(1 for i in s if i["pr_bucket"] == "One PR"),
                                         sum(1 for i in s if i["prs"])),
            "no_pr_before_after": (share(sum(1 for i in before if not i["prs"]), len(before)),
                                   share(sum(1 for i in after if not i["prs"]), len(after))),
            "ipp_before_after": (round(statistics.mean(ipp_before), 2) if ipp_before else None,
                                 round(statistics.mean(ipp_after), 2) if ipp_after else None,
                                 len(ipp_before), len(ipp_after)),
            "item_vs_pr": {k: (len(v[0]), med(v[0]), med(v[1])) for k, v in by_stage.items()},
            "median_item_days": med([p[1] for p in pair]), "median_pr_days": med([p[2] / 24 for p in pair]),
            "n_pair": len(pair)}


# ------------------------------------------------------------------ goals

def goals(con, its):
    """Every goal with its members, merged PRs, original commits, budget and scope growth."""
    prs = _prs(con)
    commits = defaultdict(int)
    for r in rows(con, "SELECT repo, pr_number, COUNT(*) n FROM pr_commits.pr_commits WHERE is_merge=0 GROUP BY repo, pr_number"):
        commits[(r["repo"], r["pr_number"])] = r["n"]
    by_item = {(i["repo"], str(i["id"])): i for i in its}
    members = defaultdict(set)
    for r in rows(con, "SELECT repo, goal_id, members FROM plans.goals"):
        members[(r["repo"], r["goal_id"])] |= {str(m) for m in json.loads(r["members"] or "[]")}
    for i in its:
        if i["goal"]:
            members[(i["repo"], i["goal"])].add(str(i["id"]))
    logs = defaultdict(list)
    for r in rows(con, "SELECT repo, item_id, ts, kind, text_redacted t FROM plans.item_logs ORDER BY ts"):
        logs[(r["repo"], r["item_id"])].append(r)
    out = []
    for r in rows(con, "SELECT * FROM plans.plan_items WHERE type='goal'"):
        fm = json.loads(r["raw_frontmatter_json"] or "{}")
        key = (r["repo"], r["item_id"])
        br = fm.get("branch")
        gp = {n for (rp, n), p in prs.items() if rp == r["repo"] and p["merged_ts"] and (
            (br and p["head_ref"] == br) or re.search(rf"goal-{r['item_id']}(\D|$)", p["head_ref"] or ""))}
        created, done_ = d(r["created_ts"]), d(r["done_ts"])
        mem = [by_item[(r["repo"], m)] for m in members[key] if (r["repo"], m) in by_item]
        later = [m for m in mem if m["created"] and created and m["created"] > created]
        text = [x["t"] or "" for x in logs.get(key, [])]
        raises = [t for t in text if re.search(r"budget_max raised|raised budget_max|budget_max \S+ ?(→|->) ?\d", t)]
        stops = [t for t in text if re.search(r"stopped at budget_max|budget_max reached|reached budget_max", t)]
        joined = [t for t in text if re.search(r"\bjoined\b|\badded to (the )?(goal|covers)\b|re-cut|\bcut \d+ into\b", t)]
        ledger = fm.get("commits") if isinstance(fm.get("commits"), list) else None
        merged = sorted(prs[(r["repo"], n)]["merged_ts"] for n in gp)
        out.append({
            "repo": r["repo"], "id": r["item_id"], "title": r["title"], "status": r["status"],
            "created": created, "done": done_ if r["status"] == "done" else None,
            "days": (done_ - created).days if done_ and created and r["status"] == "done" else None,
            "members": len(mem), "later_members": len(later), "prs": len(gp),
            "commits": sum(commits[(r["repo"], n)] for n in gp) if gp else None,
            "ledger": len(ledger) if ledger else None,
            "budget": fm.get("budget"), "budget_max": fm.get("budget_max"),
            "raises": len(raises), "stops": len(stops), "joined_logs": len(joined),
            "turns": sum(1 for x in logs.get(key, []) if x["kind"] == "turn"),
            "first_merge": merged[0][:10] if merged else None,
            "week": week_of(done_.isoformat()) if done_ and r["status"] == "done" else None,
        })
    return out


def q_goal_duration_and_scope(con, its):
    """Goal duration, size, and scope that joined after the goal was created."""
    gs = goals(con, its)
    done = [g for g in gs if g["days"] is not None]
    wk = lambda k: weekly_stat([(g["week"], g[k]) for g in done], med, GOALS_FROM)
    by_repo = defaultdict(list)
    for g in done:
        by_repo[g["repo"]].append(g)
    grew = [g for g in gs if g["later_members"] or g["joined_logs"]]
    return {"weeks": WEEKS, "series": {"Median days to done": wk("days"), "Median work items": wk("members")},
            "days_dist": dict(Counter(g["days"] for g in done)), "members_dist": dict(Counter(g["members"] for g in gs)),
            "median_members_all": med([g["members"] for g in gs]),
            "later_dist": dict(Counter(g["later_members"] for g in gs)),
            "grew_how": {"Items filed after the goal": sum(1 for g in grew if g["later_members"] and not g["joined_logs"]),
                         "Log says items joined": sum(1 for g in grew if g["joined_logs"] and not g["later_members"]),
                         "Both": sum(1 for g in grew if g["later_members"] and g["joined_logs"])},
            "n": len(gs), "n_done": len(done), "median_days": med([g["days"] for g in done]),
            "p80_days": pctl([g["days"] for g in done], 0.8), "median_members": med([g["members"] for g in done]),
            "mean_members": round(statistics.mean(g["members"] for g in done), 1) if done else None,
            "with_pr": sum(1 for g in done if g["prs"]), "multi_pr": sum(1 for g in done if g["prs"] > 1),
            "no_members": sum(1 for g in gs if not g["members"]),
            "by_repo": [(r, len(v), med([g["days"] for g in v]), med([g["members"] for g in v]))
                        for r, v in sorted(by_repo.items(), key=lambda kv: -len(kv[1]))],
            "grew": len(grew), "grew_share": share(len(grew), len(gs)),
            "later_members": sum(g["later_members"] for g in gs), "all_members": sum(g["members"] for g in gs),
            "grew_by_week": weekly_stat([(week_of(g["created"].isoformat()), 1 if (g["later_members"] or g["joined_logs"])
                                          else 0) for g in gs if g["created"]], lambda v: share(sum(v), len(v)), GOALS_FROM),
            "median_turns_logged": med([g["turns"] for g in done if g["turns"]]),
            "turn_logged": sum(1 for g in done if g["turns"])}


def q_goal_budgets(con, its):
    """Actual original commits in the goal's merged PRs against budget and budget_max."""
    gs = [g for g in goals(con, its) if g["commits"] and g["budget"]]
    for g in gs:
        g["ratio"] = g["commits"] / g["budget"]
        g["over"] = g["commits"] > g["budget"]
        g["over_max"] = bool(g["budget_max"]) and g["commits"] > g["budget_max"]
    week = lambda g: week_of(g["first_merge"])
    series = {"Over budget": weekly_stat([(week(g), 1 if g["over"] else 0) for g in gs], lambda v: share(sum(v), len(v)),
                                         GOALS_FROM),
              "Over budget_max": weekly_stat([(week(g), 1 if g["over_max"] else 0) for g in gs],
                                             lambda v: share(sum(v), len(v)), GOALS_FROM)}
    counts = weekly_stat([(week(g), 1) for g in gs], len, GOALS_FROM)
    all_g = goals(con, its)
    return {"weeks": WEEKS, "series": series, "counts": counts, "n": len(gs), "n_goals": len(all_g),
            "with_budget": sum(1 for g in all_g if g["budget"]), "with_max": sum(1 for g in all_g if g["budget_max"]),
            "over": sum(g["over"] for g in gs), "over_max": sum(g["over_max"] for g in gs),
            "median_ratio": med([g["ratio"] for g in gs]), "p80_ratio": pctl([g["ratio"] for g in gs], 0.8),
            "raises": sum(g["raises"] for g in all_g), "goals_raised": sum(1 for g in all_g if g["raises"]),
            "stops": sum(1 for g in all_g if g["stops"]),
            "scatter": [(g["budget"], g["commits"], g["repo"], g["id"]) for g in gs],
            "by_budget": {b: (len(v), med(v)) for b, v in sorted(
                {b: [g["commits"] for g in gs if g["budget"] == b] for b in {g["budget"] for g in gs}}.items())},
            "ledger_vs_commits": [(g["ledger"], g["commits"]) for g in gs if g["ledger"]],
            "worst": sorted(((g["repo"], g["id"], g["budget"], g["budget_max"], g["commits"]) for g in gs),
                            key=lambda x: -(x[4] / x[2]))[:5]}


# ------------------------------------------------------------------ PRs and wall time

def pr_facts(con):
    """Merged, non-bot PRs with hours open, change-set count, size and the stage on merge day."""
    sets = {(r["repo"], int(r["unit_id"])): r["n_sets"] for r in rows(
        con, "SELECT repo, unit_id, n_sets FROM detectors.cs_units WHERE unit_kind IN ('pr', 'pr-squash')")}
    ad = adoption(con)
    out = []
    for (repo, n), p in _prs(con).items():
        if not p["merged_ts"] or p["author_is_bot"] or (p["head_ref"] or "").startswith("dependabot/") or repo not in ad:
            continue
        c, m = dt_(p["created_ts"]), dt_(p["merged_ts"])
        day = p["merged_ts"][:10]
        out.append({"repo": repo, "number": n, "head": p["head_ref"], "created": c, "merged": m,
                    "hours": (m - c).total_seconds() / 3600, "sets": sets.get((repo, n)),
                    "lines": (p["additions"] or 0) + (p["deletions"] or 0), "files": p["changed_files"] or 0,
                    "day": day, "week": week_of(day), "month": day[:7], "stage": stage_of(con, repo, day),
                    "category": ad[repo]["category"], "goal": bool(re.search(r"goal-\d+", p["head_ref"] or ""))})
    return out


HOUR_BINS = [("<10m", 1 / 6), ("10–30m", 0.5), ("30–60m", 1), ("1–3h", 3), ("3–8h", 8),
             ("8–24h", 24), ("1–3d", 72), ("3–7d", 168), (">7d", 1e9)]


def q_pr_open_time(con):
    """Hours open-to-merge per week from 1 Jan; distribution and by change-set count."""
    ps = [p for p in pr_facts(con) if p["day"] >= "2026-01-01"]
    pairs = [(p["week"], p["hours"]) for p in ps]
    hist = Counter()
    for p in ps:
        hist[next(k for k, (_, hi) in enumerate(HOUR_BINS) if p["hours"] < hi)] += 1
    by_sets = defaultdict(list)
    for p in ps:
        if p["sets"]:
            by_sets[min(p["sets"], 4)].append(p["hours"])
    by_stage = defaultdict(list)
    for p in ps:
        by_stage[p["stage"]].append(p["hours"])
    by_month = defaultdict(list)
    for p in ps:
        by_month[p["month"]].append(p["hours"])
    goal = [p["hours"] for p in ps if p["goal"]]
    return {"weeks": WEEKS,
            "series": {"Median hours": weekly_stat(pairs, med, min_n=10),
                       "75th percentile": weekly_stat(pairs, lambda v: pctl(v, 0.75), min_n=10)},
            "n": len(ps), "median": med([p["hours"] for p in ps]), "p75": pctl([p["hours"] for p in ps], 0.75),
            "p90": pctl([p["hours"] for p in ps], 0.9),
            "hist_labels": [b[0] for b in HOUR_BINS], "hist": [hist.get(k, 0) for k in range(len(HOUR_BINS))],
            "by_sets": {k: (len(v), med(v), pctl(v, 0.75)) for k, v in sorted(by_sets.items())},
            "by_stage": {k: (len(v), med(v), pctl(v, 0.75)) for k, v in by_stage.items()},
            "by_month": {k: (len(v), med(v)) for k, v in sorted(by_month.items())},
            "goal": (len(goal), med(goal)), "under_1h": share(sum(1 for p in ps if p["hours"] < 1), len(ps)),
            "over_1d": share(sum(1 for p in ps if p["hours"] >= 24), len(ps))}


def session_links(con, ps):
    """Merged PR -> the sessions that name it (pr_links) or worked on its branch."""
    by_pr = {(p["repo"], p["number"]): p for p in ps}
    by_head = defaultdict(list)
    for p in ps:
        if p["head"] and p["head"] not in ("main", "master"):
            by_head[p["head"]].append(p)
    out = defaultdict(set)
    for s in rows(con, "SELECT session_id_hash sid, repo, git_branches, pr_links FROM harness.sessions"):
        for link in json.loads(s["pr_links"] or "[]"):
            k = pr_link_key(link)
            if k in by_pr:
                out[k].add(s["sid"])
        for b in json.loads(s["git_branches"] or "[]"):
            for p in by_head.get(b, []):
                out[(p["repo"], p["number"])].add(s["sid"])
    return out


def session_turns(con):
    t = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash sid, ts, role, is_synthetic FROM harness.turns WHERE ts IS NOT NULL ORDER BY ts"):
        t[r["sid"]].append((dt_(r["ts"]), r["role"] == "user" and not r["is_synthetic"]))
    return t


def gap_kind(a, b, asks, limits):
    """The brief's session-time rule on top of D6: > 8 h is a closed session, not time spent."""
    mins = (b - a).total_seconds() / 60
    if mins <= WORKING_GAP_MIN:
        return "Agent working"
    if mins > CLOSED_GAP_H * 60:
        return None
    if any(a <= x <= b for x in asks):
        return "Waiting on the owner"
    if any(a <= x <= b for x in limits):
        return "Usage limit"
    return "Idle"


SPLIT = ["Agent working", "Waiting on the owner", "Usage limit", "CI running", "Idle", "No session open"]


def q_pr_time_breakdown(con):
    """Minute by minute inside each PR's open window: what the linked sessions and CI were doing."""
    ps = [p for p in pr_facts(con) if p["day"] >= "2026-08-10"]
    links = session_links(con, ps)
    turns = session_turns(con)
    asks, limits = defaultdict(list), defaultdict(list)
    for r in rows(con, "SELECT session_id_hash sid, ts FROM harness.asks"):
        asks[r["sid"]].append(dt_(r["ts"]))
    for r in rows(con, "SELECT session_id_hash sid, ts FROM harness.limit_events"):
        limits[r["sid"]].append(dt_(r["ts"]))
    ci = defaultdict(list)
    for r in rows(con, "SELECT repo, head_branch, run_started_ts, created_ts, duration_s FROM github.ci_runs "
                       "WHERE duration_s IS NOT NULL AND duration_s > 0"):
        st = dt_(r["run_started_ts"] or r["created_ts"])
        ci[(r["repo"], r["head_branch"])].append((st, st + timedelta(seconds=r["duration_s"])))
    rank = {k: i for i, k in enumerate(SPLIT)}
    per_pr = []
    for p in ps:
        sids = links.get((p["repo"], p["number"]))
        if not sids:
            continue
        start, end = p["created"], p["merged"]
        n = max(1, int((end - start).total_seconds() // 60))
        lab = [rank["No session open"]] * n
        o0 = max(0, int((OUTAGE[0] - start).total_seconds() // 60))
        o1 = min(n, int((OUTAGE[1] - start).total_seconds() // 60))
        for i in range(o0, o1):
            lab[i] = len(SPLIT)  # data not available: counted in no share
        if all(v == len(SPLIT) for v in lab):
            continue
        def paint(a, b, k):
            i0 = max(0, int((a - start).total_seconds() // 60))
            i1 = min(n, int((b - start).total_seconds() // 60) + 1)
            for i in range(i0, i1):
                if rank[k] < lab[i]:
                    lab[i] = rank[k]
        for a, b in ci.get((p["repo"], p["head"]), []):
            if b > start and a < end:
                paint(a, b, "CI running")
        for sid in sids:
            ts = [t for t, _ in turns.get(sid, [])]
            for a, b in zip(ts, ts[1:]):
                if b <= start or a >= end:
                    continue
                k = gap_kind(a, b, asks[sid], limits[sid])
                if k:
                    paint(a, b, k)
        c = Counter(lab)
        per_pr.append({**p, "minutes": {k: c.get(rank[k], 0) for k in SPLIT}, "total": n - c.get(len(SPLIT), 0)})
    acc = defaultdict(Counter)
    for x in per_pr:
        for k, v in x["minutes"].items():
            acc[x["week"]][k] += v
    series = {k: no_outage(tracked([share(acc[w][k], sum(acc[w].values())) if sum(acc[w].values()) else None
                                    for w in WEEKS], SESSIONS_FROM)) for k in SPLIT}
    tot = Counter()
    for x in per_pr:
        tot.update(x["minutes"])
    by_repo = defaultdict(Counter)
    for x in per_pr:
        by_repo[x["repo"]].update(x["minutes"])
    repos = sorted(by_repo, key=lambda r: -sum(by_repo[r].values()))[:8]
    med_share = {k: med([x["minutes"][k] / x["total"] for x in per_pr]) for k in SPLIT}
    short = [x for x in per_pr if x["hours"] < 8]
    tot_short = Counter()
    for x in short:
        tot_short.update(x["minutes"])
    return {"weeks": WEEKS, "series": series, "cats": SPLIT, "n": len(per_pr), "n_prs": len(ps),
            "total_hours": round(sum(tot.values()) / 60), "share": {k: share(tot[k], sum(tot.values())) for k in SPLIT},
            "share_short": {k: share(tot_short[k], sum(tot_short.values())) for k in SPLIT}, "n_short": len(short),
            "median_share": med_share,
            "by_repo": {r: [share(by_repo[r][k], sum(by_repo[r].values())) for k in SPLIT] for r in repos}}


def q_sessions_per_pr(con):
    """Sessions (split at > 8 h gaps) that worked on each merged PR, and the pauses between them."""
    ps = [p for p in pr_facts(con) if p["day"] >= "2026-08-10"]
    links = session_links(con, ps)
    turns = session_turns(con)
    limits = defaultdict(list)
    all_limits = sorted(dt_(r["ts"]) for r in rows(con, "SELECT ts FROM harness.limit_events"))
    for r in rows(con, "SELECT session_id_hash sid, ts FROM harness.limit_events"):
        limits[r["sid"]].append(dt_(r["ts"]))
    spans_of = {}
    for sid, ts in turns.items():
        spans, cur = [], [ts[0][0], ts[0][0]]
        for (a, _), (b, _) in zip(ts, ts[1:]):
            if (b - a).total_seconds() > CLOSED_GAP_H * 3600:
                spans.append(tuple(cur))
                cur = [b, b]
            else:
                cur[1] = b
        spans.append(tuple(cur))
        spans_of[sid] = spans
    first_commit = {(r["repo"], r["pr_number"]): dt_(r["t"]) for r in rows(
        con, "SELECT repo, pr_number, MIN(ts) t FROM pr_commits.pr_commits WHERE is_merge=0 GROUP BY repo, pr_number")}
    per_pr, pauses = [], []
    skipped_outage = 0
    def night(a, b):
        la, lb = a.astimezone(LOCAL), b.astimezone(LOCAL)
        x = la.replace(hour=2, minute=0, second=0, microsecond=0)
        if x < la:
            x += timedelta(days=1)
        return x < lb
    for p in ps:
        sids = links.get((p["repo"], p["number"]))
        if not sids:
            continue
        lo = min(filter(None, [p["created"], first_commit.get((p["repo"], p["number"]))])) - timedelta(hours=12)
        if lo < OUTAGE[1] and p["merged"] > OUTAGE[0]:
            skipped_outage += 1
            continue
        spans = sorted(s for sid in sids for s in spans_of.get(sid, []) if s[1] >= lo and s[0] <= p["merged"])
        if not spans:
            continue
        # overlapping spans are parallel sessions, not a pause
        merged_spans = []
        for a, b in spans:
            if merged_spans and a <= merged_spans[-1][1]:
                merged_spans[-1][1] = max(merged_spans[-1][1], b)
            else:
                merged_spans.append([a, b])
        for (a0, b0), (a1, b1) in zip(merged_spans, merged_spans[1:]):
            gap_h = (a1 - b0).total_seconds() / 3600
            lim = any(b0 - timedelta(minutes=15) <= x <= a1 for x in all_limits)
            cause = "Usage limit" if lim else "Overnight" if night(b0, a1) else "Daytime"
            pauses.append({"hours": gap_h, "cause": cause, "week": p["week"]})
        per_pr.append({**p, "sessions": len(spans), "stretches": len(merged_spans), "sids": len(sids)})
    wk = no_outage(weekly_stat([(x["week"], x["sessions"]) for x in per_pr], lambda v: round(statistics.mean(v), 2),
                               SESSIONS_FROM))
    multi = weekly_stat([(x["week"], 1 if x["stretches"] > 1 else 0) for x in per_pr],
                        lambda v: share(sum(v), len(v)), SESSIONS_FROM)
    bins = [("< 1 h", 1), ("1–3 h", 3), ("3–8 h", 8), ("8–24 h", 24), ("1–3 days", 72), ("> 3 days", 1e9)]
    causes = ["Overnight", "Daytime", "Usage limit"]
    hist = {c: [sum(1 for x in pauses if x["cause"] == c and (bins[k - 1][1] if k else 0) <= x["hours"] < hi)
                for k, (_, hi) in enumerate(bins)] for c in causes}
    dist = Counter(min(x["sessions"], 5) for x in per_pr)
    return {"weeks": WEEKS, "series": {"Sessions per PR (mean)": wk}, "multi_share": multi,
            "n": len(per_pr), "n_prs": len(ps), "skipped_outage": skipped_outage, "mean_sessions": round(statistics.mean(x["sessions"] for x in per_pr), 2),
            "median_sessions": med([x["sessions"] for x in per_pr]),
            "one_session": share(sum(1 for x in per_pr if x["sessions"] == 1), len(per_pr)),
            "one_stretch": share(sum(1 for x in per_pr if x["stretches"] == 1), len(per_pr)),
            "dist": [dist.get(k, 0) for k in range(1, 6)],
            "n_pauses": len(pauses), "pause_median_h": med([x["hours"] for x in pauses]),
            "pause_by_cause": {c: (sum(1 for x in pauses if x["cause"] == c),
                                   med([x["hours"] for x in pauses if x["cause"] == c])) for c in causes},
            "bins": [b[0] for b in bins], "hist": hist,
            "goal_vs_other": (med([x["sessions"] for x in per_pr if x["goal"]]),
                              med([x["sessions"] for x in per_pr if not x["goal"]]),
                              sum(1 for x in per_pr if x["goal"]))}


def q_when_work_lands(con):
    """Change sets merged by local hour and weekday; weekly share landing at night or on a weekend."""
    ps = [p for p in pr_facts(con) if p["day"] >= "2026-01-01"]
    wk = []
    by_hour = {"Weekday": [0] * 24, "Weekend": [0] * 24}
    by_dow = [0] * 7
    for p in ps:
        n = p["sets"] or 1
        lt = p["merged"].astimezone(LOCAL)
        off = lt.weekday() >= 5 or lt.hour < 7 or lt.hour >= 22
        wk.append((p["week"], (n, n if off else 0, n if lt.weekday() >= 5 else 0, n if (lt.hour < 7 or lt.hour >= 22) else 0)))
        by_hour["Weekend" if lt.weekday() >= 5 else "Weekday"][lt.hour] += n
        by_dow[lt.weekday()] += n
    acc = defaultdict(lambda: [0, 0, 0, 0])
    for w, v in wk:
        for k in range(4):
            acc[w][k] += v[k]
    f = lambda k: [share(acc[w][k], acc[w][0]) if acc[w][0] >= 20 else None for w in WEEKS]
    tot = [sum(acc[w][k] for w in acc) for k in range(4)]
    after = [sum(acc[w][k] for w in acc if w >= "2026-W35") for k in range(4)]
    before = [sum(acc[w][k] for w in acc if w < "2026-W35") for k in range(4)]
    return {"weeks": WEEKS, "series": {"Weekend": f(2), "Night (22:00–07:00)": f(3)},
            "by_hour": by_hour, "by_dow": by_dow, "n_sets": tot[0],
            "off_share": share(tot[1], tot[0]), "weekend_share": share(tot[2], tot[0]), "night_share": share(tot[3], tot[0]),
            "off_before_goals": share(before[1], before[0]), "off_since_goals": share(after[1], after[0]),
            "weekend_before": share(before[2], before[0]), "weekend_since": share(after[2], after[0]),
            "night_before": share(before[3], before[0]), "night_since": share(after[3], after[0]),
            "peak_hour": max(range(24), key=lambda h: by_hour["Weekday"][h] + by_hour["Weekend"][h])}


def q_change_set_size_vs_pr_time_size(con):
    """For one-change-set PRs: does size (lines, files) track hours open? Monthly rank correlation."""
    ps = [p for p in pr_facts(con) if p["day"] >= "2026-01-01" and p["sets"] == 1]
    by_month = defaultdict(list)
    for p in ps:
        by_month[p["month"]].append(p)
    rho_lines = [spearman([p["lines"] for p in by_month[m]], [p["hours"] for p in by_month[m]])
                 if len(by_month[m]) >= 15 else None for m in MONTHS]
    rho_files = [spearman([p["files"] for p in by_month[m]], [p["hours"] for p in by_month[m]])
                 if len(by_month[m]) >= 15 else None for m in MONTHS]
    buckets = [("< 20", 20), ("20–99", 100), ("100–299", 300), ("300–999", 1000), ("1,000+", 1e12)]
    by_b = defaultdict(list)
    for p in ps:
        by_b[next(k for k, (_, hi) in enumerate(buckets) if p["lines"] < hi)].append(p["hours"])
    allsets = [p for p in pr_facts(con) if p["day"] >= "2026-01-01" and p["sets"]]
    return {"months": MONTHS, "series": {"Lines vs hours (ρ)": rho_lines, "Files vs hours (ρ)": rho_files},
            "n": len(ps), "n_month": {m: len(by_month[m]) for m in MONTHS},
            "rho_lines": spearman([p["lines"] for p in ps], [p["hours"] for p in ps]),
            "rho_files": spearman([p["files"] for p in ps], [p["hours"] for p in ps]),
            "rho_sets_all": spearman([p["sets"] for p in allsets], [p["hours"] for p in allsets]),
            "buckets": [b[0] for b in buckets],
            "by_bucket": [(len(by_b[k]), med(by_b[k]), pctl(by_b[k], 0.75)) for k in range(len(buckets))]}


def all_data():
    con = connect()
    its = items(con)
    out = {}
    for name, fn in sorted(globals().items()):
        if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__:
            out[name] = fn(con, its) if fn.__code__.co_argcount == 2 else fn(con)
    return out


if __name__ == "__main__":
    data = all_data()
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("weeks", "series", "by_repo", "ages")}
                      for k, v in data.items()}, indent=1, default=str))
