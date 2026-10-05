"""Introduction series: the factory and the fleet, in the numbers every later topic builds on.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/intro/data.py

One function per question. The headline counts (change sets, spend, planned share) call
evolution.py's functions rather than recomputing them, so the two topics print the same
numbers. Weeks run 2026-W01..W40 (evolution.WEEKS); pre-2026 history is folded into the
starting value where a chart is cumulative and otherwise left out.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from record import SESSION_FULL_WEEKS, adoption, changeset_facts, gap_range, gap_weeks, rows, stage_of, week_of  # noqa: E402
from evolution import MONTHS, WEEKS, q_cost_saving_changes, q_weekly_change_sets_by_stage, q_observable_work_share  # noqa: E402
from ingest.fleet import role_of  # noqa: E402

FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CH01_DB = os.path.join(PLUGIN, ".analysis", "data", "intro.sqlite")
LATEST = "2026-10-01"
APPS = ("app", "app, no features yet")
# Session logs are missing, then partial, over record.gap_range() (W33-W34), so those days are left out of every
# session-based average and share.
OUTAGE = gap_range()
OUTAGE_WEEKS = tuple(sorted(set().union(*gap_weeks())))


def in_outage(day):
    return OUTAGE[0] <= day[:10] <= OUTAGE[1]

try:
    from intro_hand import DESCRIPTIONS, GOAL_161_MATCH  # noqa: E402
    HAND_DATA = True
except ImportError:
    # intro_hand.py is hand-checked fleet data (client names, a real goal's items) and is never published.
    # Without it Q change-set-rollup's trace reports itself unavailable: an empty match would call every item Dependabot.
    DESCRIPTIONS, GOAL_161_MATCH = {}, {}
    HAND_DATA = False
    print("intro: intro_hand.py absent; Q change-set-rollup's worked example is unavailable", file=sys.stderr)

# Q codebase-size: what does not count as code the fleet maintains.
LOCKFILE_RE = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|go\.sum|Cargo\.lock|"
                         r"poetry\.lock|uv\.lock|Gemfile\.lock|composer\.lock|[^/]*\.lock|\.terraform\.lock\.hcl)$")
GENERATED_RE = re.compile(r"(^|/)(gen|dist|build|generated|__generated__|public/r|\.next|coverage)/|"
                          r"\.pb\.go$|_pb2?\.(py|ts|js)$|\.connect\.go$|_connect\.ts$|\.min\.(js|css)$|"
                          r"\.gen\.[a-z]+$|_ds_bundle\.js$|(^|/)extracted/|routeTree\.gen\.ts$|\.snap$")
VENDORED_RE = re.compile(r"(^|/)(vendor|node_modules|third_party|_ds)/|(^|/)(CHECKS|CONTROLS)\.yaml$|"
                         r"(^|/)scripts/audit\.py$|(^|/)\.claude/rules/design-system(\.local)?\.md$|"
                         r"(^|/)check-design-tokens(\.test)?\.sh$")


def excluded(repo, path):
    if LOCKFILE_RE.search(path) or GENERATED_RE.search(path):
        return True
    return repo != "wayfare-skills" and bool(VENDORED_RE.search(path))


def connect():
    return _connect("intro")


def week_end(w):
    return date.fromisocalendar(2026, int(w[6:]), 7).isoformat()


def week_start(w):
    return date.fromisocalendar(2026, int(w[6:]), 1).isoformat()


def work(cs):
    return [f for f in cs if not f["dependabot"]]


# ---------------------------------------------------------------- Q fleet-roster

def q_fleet_roster(con):
    """Repos with a change set each week by category, and one roster row per repo."""
    cs = work(changeset_facts(con))
    ad = adoption(con)
    active = defaultdict(set)
    for f in cs:
        active[f["week"]].add((f["category"], f["repo"]))
    cats = ["app", "app, no features yet", "allied"]
    series = {c: [sum(1 for k, _ in active[w] if k == c) for w in WEEKS] for c in cats}
    n = Counter(f["repo"] for f in cs)
    roster = []
    for r, a in ad.items():
        roster.append({"repo": r, "category": a["category"], "role": role_of(r), "first": a["first"],
                       "first_2026": max(a["first"], "2026-01-01"), "change_sets": n[r],
                       "stage": stage_of(con, r, LATEST), "description": DESCRIPTIONS.get(r, "")})
    order = {"app": 0, "app, no features yet": 1, "allied": 2}
    roster.sort(key=lambda x: (order[x["category"]], -x["change_sets"]))
    counts = Counter(x["category"] for x in roster)
    joined = {c: [sum(1 for x in roster if x["category"] == c and x["first"] <= week_end(w)) for w in WEEKS]
              for c in cats}
    return {"weeks": WEEKS, "series": series, "joined": joined, "roster": roster, "counts": dict(counts),
            "n_repos": len(roster), "joined_since_jul": sum(1 for x in roster if x["first"] >= "2026-07-01")}


# ---------------------------------------------------------------- Q repos-in-motion

def q_repos_in_motion(con):
    """Weekly: repos with a change set merged. Per day: repos with a merge, and (from 9 Aug) with a session."""
    cs = work(changeset_facts(con))
    ad = adoption(con)
    wk = defaultdict(set)
    merged_day = defaultdict(set)
    for f in cs:
        wk[f["week"]].add(f["repo"])
        merged_day[f["day"]].add(f["repo"])
    weekly = [len(wk[w]) for w in WEEKS]
    session_day = defaultdict(set)
    for r in rows(con, "SELECT repo, day FROM harness.sessions"):
        if r["repo"] in ad:
            session_day[r["day"]].add(r["repo"])
    sessions_from = min(session_day)
    touched = {d: merged_day.get(d, set()) | session_day.get(d, set())
               for d in set(merged_day) | set(session_day) if d >= sessions_from and not in_outage(d)}
    bins = ["1", "2", "3", "4", "5", "6", "7", "8+"]
    hist = lambda vals: [sum(1 for v in vals if min(v, 8) == i + 1) for i in range(8)]
    before = [len(v) for d, v in merged_day.items() if "2026-01-01" <= d < sessions_from]
    since = [len(v) for v in touched.values() if v]
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    last8 = WEEKS[-8:]
    return {"weeks": WEEKS, "weekly": weekly, "bins": bins,
            "per_day_merges_before": hist(before), "per_day_touched_since": hist(since),
            "median_before": med(before), "median_since": med(since), "max_since": max(since),
            "days_before": len(before), "days_since": len(since), "sessions_from": sessions_from,
            "peak_week": max(zip(weekly, WEEKS)), "mean_last8": round(sum(len(wk[w]) for w in last8) / 8, 1),
            "first_half_mean": round(sum(weekly[:26]) / 26, 1)}


# ---------------------------------------------------------------- Q fleet-throughput

def q_fleet_throughput_volume(con):
    """Change sets per week (evolution.q_weekly_change_sets_by_stage), plus the totals the title needs."""
    t = q_weekly_change_sets_by_stage(con)
    s = t["series"]
    total = sum(sum(v) for v in s.values())
    nondep = sum(sum(v) for k, v in s.items() if k != "Dependabot")
    per_month = defaultdict(int)
    for f in work(changeset_facts(con)):
        if f["day"] >= "2026-01-01":
            per_month[f["month"]] += 1
    cum = defaultdict(lambda: [0] * len(MONTHS))
    for f in work(changeset_facts(con)):
        for i, m in enumerate(MONTHS):
            if f["month"] <= m:
                cum[f["repo"]][i] += 1
    top = sorted(cum, key=lambda r: -cum[r][-1])[:8]
    return {**t, "total_2026": total, "work_2026": nondep, "per_month": [per_month[m] for m in MONTHS],
            "cum_by_repo": {r: cum[r] for r in top}}


# ---------------------------------------------------------------- Q work-by-repo

def q_work_by_repo_where(con):
    """Share of non-Dependabot change sets per month by repo (top six named, the rest grouped)."""
    cs = [f for f in work(changeset_facts(con)) if f["day"] >= "2026-01-01"]
    n = Counter(f["repo"] for f in cs)
    top = [r for r, _ in n.most_common(6)]
    by = defaultdict(Counter)
    for f in cs:
        by[f["month"]][f["repo"] if f["repo"] in top else "Other repos"] += 1
    cats = top + ["Other repos"]
    share = {c: [round(by[m][c] / sum(by[m].values()), 3) if by[m] else 0 for m in MONTHS] for c in cats}
    counts = {c: [by[m][c] for m in MONTHS] for c in cats}
    total = sum(n.values())
    top2 = n.most_common(2)
    return {"months": MONTHS, "share": share, "counts": counts, "total": total,
            "top": [(r, v, round(v / total, 3)) for r, v in n.most_common()],
            "top2_share": round(sum(v for _, v in top2) / total, 3),
            "other_share": [round(by[m]["Other repos"] / sum(by[m].values()), 3) if by[m] else None for m in MONTHS],
            "active_by_month": [len({f["repo"] for f in cs if f["month"] == m}) for m in MONTHS]}


# ---------------------------------------------------------------- Q apps-vs-factory-work

def q_apps_vs_factory_work_factory_share(con):
    """Weekly share of non-Dependabot change sets that went to allied repos (the factory itself)."""
    cs = [f for f in work(changeset_facts(con))]
    allied = defaultdict(int)
    plugin = defaultdict(int)
    total = defaultdict(int)
    for f in cs:
        total[f["week"]] += 1
        if f["category"] == "allied":
            allied[f["week"]] += 1
            if f["repo"] == "wayfare-skills":
                plugin[f["week"]] += 1
    share = [round(allied[w] / total[w], 3) if total[w] else None for w in WEEKS]
    by_repo = defaultdict(lambda: [0] * len(MONTHS))
    for f in cs:
        if f["category"] == "allied" and f["month"] in MONTHS:
            by_repo[f["repo"]][MONTHS.index(f["month"])] += 1
    m_tot = Counter(f["month"] for f in cs)
    m_all = Counter(f["month"] for f in cs if f["category"] == "allied")
    month_share = [round(m_all[m] / m_tot[m], 3) if m_tot[m] else None for m in MONTHS]
    return {"weeks": WEEKS, "share": share, "allied": [allied[w] for w in WEEKS],
            "apps": [total[w] - allied[w] for w in WEEKS], "plugin": [plugin[w] for w in WEEKS],
            "month_share": month_share, "by_repo": dict(by_repo),
            "overall": round(sum(allied.values()) / sum(total.values()), 3),
            "since_jul": round(sum(m_all[m] for m in MONTHS if m >= "2026-07") /
                               sum(m_tot[m] for m in MONTHS if m >= "2026-07"), 3)}


# ---------------------------------------------------------------- Q codebase-size

def head_lines(repo):
    """Lines in the checkout's tracked files, under the same exclusion rule (a cross-check)."""
    path = PLUGIN if repo == "wayfare-skills" else os.path.join(FLEET, repo)
    try:
        files = subprocess.run(["git", "-C", path, "ls-files", "-z"], capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    total = 0
    for f in files.decode(errors="replace").split("\0"):
        if not f or excluded(repo, f):
            continue
        try:
            with open(os.path.join(path, f), "rb") as fh:
                data = fh.read()
        except (IsADirectoryError, FileNotFoundError, PermissionError):
            continue
        if b"\0" in data[:8000]:
            continue
        total += data.count(b"\n")
    return total


def q_codebase_size(con):
    """Cumulative lines added minus removed on the default branch, lockfiles/generated/vendored left out."""
    ad = adoption(con)
    net = defaultdict(lambda: defaultdict(int))
    raw = defaultdict(lambda: defaultdict(int))
    for r in rows(con, """SELECT c.repo, c.day, f.path, COALESCE(f.insertions,0) - COALESCE(f.deletions,0) n
                          FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha"""):
        if r["repo"] not in ad:
            continue
        w = "2026-W01" if r["day"] < "2026-01-01" else week_of(r["day"])
        raw[r["repo"]][w] += r["n"]
        if not excluded(r["repo"], r["path"]):
            net[r["repo"]][w] += r["n"]

    def cumulative(d):
        out, acc = [], 0
        for w in WEEKS:
            acc += d.get(w, 0)
            out.append(acc)
        return out
    per_repo = {r: cumulative(net[r]) for r in net}
    fleet = [sum(per_repo[r][i] for r in per_repo) for i in range(len(WEEKS))]
    fleet_raw = [sum(cumulative(raw[r])[i] for r in raw) for i in range(len(WEEKS))]
    cats = {"Apps": [0] * len(WEEKS), "Allied repos": [0] * len(WEEKS)}
    for r, v in per_repo.items():
        k = "Allied repos" if ad[r]["category"] == "allied" else "Apps"
        cats[k] = [a + b for a, b in zip(cats[k], v)]
    month_idx = [max(i for i, w in enumerate(WEEKS) if week_start(w)[:7] <= m) for m in MONTHS]
    by_repo_month = {r: [per_repo[r][i] for i in month_idx] for r in sorted(per_repo, key=lambda r: -per_repo[r][-1])[:8]}
    head = {r: head_lines(r) for r in per_repo}
    jul = WEEKS.index("2026-W27")
    return {"weeks": WEEKS, "series": cats, "fleet": fleet, "fleet_raw": fleet_raw, "by_repo_month": by_repo_month,
            "now": {r: v[-1] for r, v in per_repo.items()}, "head": head,
            "head_total": sum(v for v in head.values() if v), "total": fleet[-1],
            "at_jul": fleet[jul], "excluded_share": round(1 - fleet[-1] / fleet_raw[-1], 3)}


# ---------------------------------------------------------------- Q weekly-factory-cost

def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


IDLE_CAP_MIN = 8 * 60


def q_weekly_factory_cost(con):
    """Weekly spend (evolution.q_cost_saving_changes), the owner's hours and the hours any session was working.

    Owner time follows the brief's rule: minutes waiting on the owner (D6 waiting_human, gaps up
    to 8 h) plus the owner's reply time (a gap of 5 min or less that ends in a typed prompt).
    Longer gaps with no ask are idle, never owner time; gaps over 8 h mean the session was closed.
    """
    c = q_cost_saving_changes(con)
    known = {r["session_id_hash"] for r in rows(con, "SELECT session_id_hash FROM harness.sessions")}
    owner = defaultdict(float)
    spans = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash, kind, start_ts, end_ts, minutes FROM detectors.session_time_segments "
                       "WHERE kind IN ('working', 'waiting_human') AND minutes <= ?", (IDLE_CAP_MIN,)):
        if r["session_id_hash"] not in known:
            continue
        a, b = _parse(r["start_ts"]), _parse(r["end_ts"])
        w = week_of(a.date().isoformat())
        if r["kind"] == "waiting_human":
            owner[w] += r["minutes"] / 60
        else:
            spans[w].append((a, b))
    user_turn = {(r["session_id_hash"], _parse(r["ts"]).isoformat()) for r in rows(
        con, "SELECT session_id_hash, ts FROM harness.turns WHERE role='user' AND is_synthetic=0")}
    for r in rows(con, "SELECT session_id_hash, start_ts, end_ts, minutes FROM detectors.session_time_segments "
                       "WHERE kind='working'"):
        if r["session_id_hash"] in known and (r["session_id_hash"], r["end_ts"]) in user_turn:
            owner[week_of(r["start_ts"][:10])] += r["minutes"] / 60
    wall = {}
    for w, sp in spans.items():
        sp.sort()
        tot, cur_a, cur_b = 0.0, None, None
        for a, b in sp:
            if cur_b is None or a > cur_b:
                if cur_b is not None:
                    tot += (cur_b - cur_a).total_seconds()
                cur_a, cur_b = a, b
            else:
                cur_b = max(cur_b, b)
        if cur_b is not None:
            tot += (cur_b - cur_a).total_seconds()
        wall[w] = tot / 3600
    sessions = Counter(r["week"] for r in rows(con, "SELECT week FROM harness.sessions"))
    weeks = [w for w in WEEKS if sessions.get(w)]
    full = SESSION_FULL_WEEKS
    avg = lambda d: round(sum(d.get(w, 0) for w in full) / len(full), 1)
    return {**c, "owner_hours": [round(owner.get(w, 0), 1) for w in WEEKS],
            "hours_wall": [round(wall.get(w, 0), 1) for w in WEEKS], "sessions": [sessions.get(w, 0) for w in WEEKS],
            "session_weeks": weeks, "full_weeks": full,
            "mean_spend_full": round(sum(c["spend"][WEEKS.index(w)] for w in full) / len(full)),
            "mean_wall_full": avg(wall), "mean_owner_full": avg(owner),
            "n_sessions": sum(sessions.values())}


# ---------------------------------------------------------------- Q work-kind-mix and Q work-by-theme

# The shared label (detectors.cs_worktype, built once by the lead for every topic).
WORK_GROUPS = {"feature": "Feature", "feat": "Feature", "design_ui": "Feature", "fix": "Fix", "security": "Security",
               "refactor": "Refactor, test, docs", "test": "Refactor, test, docs", "docs": "Refactor, test, docs",
               "factory": "Upkeep", "ci_build": "Upkeep", "dependency": "Upkeep", "chore": "Upkeep"}
GROUPS = ["Feature", "Fix", "Security", "Refactor, test, docs", "Upkeep"]
THEME_CHAPTER = {
    "product": ("fleet", "Fleet scope and apps"), "fleet_apps": ("fleet", "Fleet scope and apps"),
    "harness": ("agent_harness", "The harness"), "human_loop": ("owner", "Human in the loop"),
    "skills": ("skills", "Skills and factory evolution"), "connectors": ("connectors", "Connectors"),
    "knowledge": ("memory", "Knowledge and memory"), "architecture": ("architecture", "Architecture and design records"),
    "work_items": ("work_items", "Work items, flow and wall time"), "rework": ("mistakes", "Agent mistakes and rework"),
    "security": ("security", "Security"), "cross_repo": ("messages", "Cross-repo context and messaging"),
    "compliance": ("compliance", "Compliance and drift"), "deploy_infra": ("deployment", "Deployment and infrastructure"),
    "spend": ("spend", "Spend and cost"), "factory": ("agent_harness, skills", "The harness; skills"),
    "dependencies": ("security, compliance", "Security; compliance and drift"),
}
# The shared label sometimes answers with a work type where a theme belongs, and puts Dependabot
# bumps under spend or harness; these fold both back into the topic list.
THEME_FIX = {"ci_build": "deploy_infra", "design_ui": "product", "dependency": "dependencies", "feat": "product"}
THEME_NAME = {"product": "App features", "fleet_apps": "Fleet and apps", "harness": "Harness",
              "human_loop": "Human in the loop", "skills": "Skills", "connectors": "Connectors",
              "knowledge": "Knowledge", "architecture": "Architecture", "work_items": "Work items",
              "rework": "Rework", "security": "Security", "cross_repo": "Cross-repo", "compliance": "Compliance",
              "deploy_infra": "Deploy and infra", "spend": "Spend", "factory": "Factory process",
              "dependencies": "Dependencies"}


def _labels(con):
    """{(repo, unit_kind, unit_id, set_idx): (work_type, theme)} from the shared label."""
    try:
        got = rows(con, "SELECT repo, unit_kind, unit_id, set_idx, work_type, theme FROM detectors.cs_worktype")
    except sqlite3.OperationalError as e:
        print(f"intro: {e}; change sets are unlabelled", file=sys.stderr)
        return {}
    return {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): (r["work_type"], r["theme"]) for r in got}


def _lab(f, lab):
    return lab.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))


def q_work_kind_mix_work_type(con):
    lab = _labels(con)
    all_cs = [f for f in changeset_facts(con) if f["day"] >= "2026-01-01"]
    cs = [f for f in all_cs if _lab(f, lab) and _lab(f, lab)[0] in WORK_GROUPS]
    g = lambda f: WORK_GROUPS[_lab(f, lab)[0]]
    series = {t: [0] * len(WEEKS) for t in GROUPS}
    by_month = defaultdict(Counter)
    by_repo = defaultdict(Counter)
    for f in cs:
        if f["week"] in WEEKS:
            series[g(f)][WEEKS.index(f["week"])] += 1
        by_month[f["month"]][g(f)] += 1
        by_repo[f["repo"]][g(f)] += 1
    share = {t: [round(by_month[m][t] / sum(by_month[m].values()), 3) if by_month[m] else None for m in MONTHS]
             for t in GROUPS}
    tot = Counter(g(f) for f in cs)
    raw = Counter(_lab(f, lab)[0] for f in cs)
    n = sum(tot.values())
    q = lambda months, t: round(sum(by_month[m][t] for m in months) / max(1, sum(sum(by_month[m].values()) for m in months)), 3)
    return {"weeks": WEEKS, "series": series, "share_by_month": share, "by_repo": {r: dict(v) for r, v in by_repo.items()},
            "totals": dict(tot), "raw": dict(raw), "n": n, "unlabelled": len(all_cs) - n,
            "share_total": {t: round(tot[t] / n, 3) for t in GROUPS} if n else {},
            "upkeep_before_jul": q(["2026-04", "2026-05", "2026-06"], "Upkeep"),
            "upkeep_since_jul": q(["2026-07", "2026-08", "2026-09"], "Upkeep"),
            "feature_before_jul": q(["2026-04", "2026-05", "2026-06"], "Feature"),
            "feature_since_jul": q(["2026-07", "2026-08", "2026-09"], "Feature"),
            "security_since_jul": q(["2026-07", "2026-08", "2026-09"], "Security")}


def q_work_by_theme_themes(con):
    lab = _labels(con)
    def t(f):
        if f["dependabot"]:
            return "dependencies"
        return THEME_FIX.get(_lab(f, lab)[1], _lab(f, lab)[1])
    labelled = [f for f in changeset_facts(con) if f["day"] >= "2026-01-01" and _lab(f, lab)]
    cs = [f for f in labelled if t(f) in THEME_CHAPTER]
    by_month = defaultdict(Counter)
    for f in cs:
        by_month[f["month"]][t(f)] += 1
    tot = Counter(t(f) for f in cs)
    themes = [x for x, _ in tot.most_common()]
    share = {x: [round(by_month[m][x] / sum(by_month[m].values()), 3) if by_month[m] else 0 for m in MONTHS]
             for x in themes}
    n = sum(tot.values())
    return {"months": MONTHS, "share": share, "themes": themes, "totals": dict(tot), "n": n,
            "refolded": sum(1 for f in labelled if not f["dependabot"] and _lab(f, lab)[1] in THEME_FIX),
            "dependabot_relabelled": sum(1 for f in labelled if f["dependabot"] and _lab(f, lab)[1] != "dependency"),
            "unmapped": len(labelled) - len(cs),
            "table": [(THEME_NAME[x], tot[x], round(tot[x] / n, 3), *THEME_CHAPTER[x]) for x in themes]}


def spotcheck(con, n=30, seed=1):
    """A fixed random sample of labelled change sets, for checking by hand."""
    import random
    lab = _labels(con)
    cs = [f for f in changeset_facts(con) if _lab(f, lab)]
    random.Random(seed).shuffle(cs)
    return [(f["repo"], f["unit_id"], f["label"], *_lab(f, lab)) for f in cs[:n]]


# ---------------------------------------------------------------- Q change-set-rollup



def q_change_set_rollup_example(con):
    if not HAND_DATA:
        return {"unavailable": "intro_hand.py absent", "levels": _q109_levels(con)}
    goal = rows(con, "SELECT * FROM plans.goals WHERE repo='auth' AND goal_id='161'")[0]
    items = {r["item_id"]: r for r in rows(con, "SELECT item_id, title, type, status FROM plans.plan_items "
                                                "WHERE repo='auth' AND goal_id='161'")}
    pr = rows(con, "SELECT number, title, head_ref, created_ts, merged_ts, commits, additions, deletions "
                   "FROM github.prs WHERE repo='auth' AND number=370")[0]
    commits = rows(con, "SELECT idx, sha, ts, subject, insertions + deletions churn FROM pr_commits.pr_commits "
                        "WHERE repo='auth' AND pr_number=370 ORDER BY idx")
    sets = [f for f in changeset_facts(con) if f["repo"] == "auth" and f["unit_id"] == "370"]
    sets.sort(key=lambda f: f["set_idx"])
    idx_of = {c["sha"]: c["idx"] for c in commits}
    trace = [{"set": f["set_idx"] + 1, "label": f["label"], "commits": sorted(idx_of[s] + 1 for s in f["shas"]),
              "lines": f["lines"], "item": GOAL_161_MATCH.get(f["set_idx"]),
              "item_title": items.get(GOAL_161_MATCH.get(f["set_idx"]), {}).get("title")} for f in sets]
    dep = [i for i, r in items.items() if i not in GOAL_161_MATCH.values()]
    dep_prs = rows(con, "SELECT number, title, merged_ts FROM github.prs WHERE repo='auth' AND number BETWEEN 348 AND 351")
    sess = rows(con, "SELECT COUNT(*) n, ROUND(SUM(cost_usd), 2) usd, MIN(first_ts) a, MAX(last_ts) b FROM harness.sessions "
                     "WHERE repo='auth' AND (pr_links LIKE '%auth#370%' OR git_branches LIKE '%goal-161%')")[0]
    logs = rows(con, "SELECT kind, COUNT(*) n FROM plans.item_logs WHERE repo='auth' AND item_id IN ({}) GROUP BY kind"
                .format(",".join(f"'{i}'" for i in items)))
    return {"levels": _q109_levels(con), "goal": goal, "items": items, "pr": pr, "commits": commits, "trace": trace,
            "dependabot_items": dep, "dependabot_prs": dep_prs, "session": sess, "logs": {r["kind"]: r["n"] for r in logs}}


def _q109_levels(con):
    levels = {"Change sets": [0] * len(WEEKS), "PRs merged": [0] * len(WEEKS),
              "Work items done": [0] * len(WEEKS), "Goals done": [0] * len(WEEKS)}
    for f in work(changeset_facts(con)):
        if f["week"] in WEEKS:
            levels["Change sets"][WEEKS.index(f["week"])] += 1
    ad = adoption(con)
    for r in rows(con, "SELECT repo, week FROM github.prs WHERE merged_ts IS NOT NULL AND author_is_bot = 0"):
        if r["repo"] in ad and r["week"] in WEEKS:
            levels["PRs merged"][WEEKS.index(r["week"])] += 1
    for r in rows(con, "SELECT repo, type, done_ts FROM plans.plan_items WHERE status='done' AND done_ts IS NOT NULL"):
        w = week_of(r["done_ts"][:10])
        if r["repo"] in ad and w in WEEKS:
            levels["Goals done" if r["type"] == "goal" else "Work items done"][WEEKS.index(w)] += 1
    return levels


# ---------------------------------------------------------------- Q planned-in-writing

def q_planned_in_writing_planned(con):
    """evolution.q_observable_work_share, with the shares the title needs."""
    o = q_observable_work_share(con)
    s = o["series"]
    planned = s["Planned: a work item"]
    tot = [sum(s[c][i] for c in s if c != "Dependabot") for i in range(len(WEEKS))]
    share = [round(p / t, 3) if t else None for p, t in zip(planned, tot)]
    last4 = WEEKS[-4:]
    idx = [WEEKS.index(w) for w in last4]
    from links import set_item_links
    links, _ = set_item_links(con)
    per_repo = defaultdict(lambda: [0, 0])
    for f in changeset_facts(con):
        if f["week"] >= "2026-W32" and f["week"] not in OUTAGE_WEEKS and not f["dependabot"]:
            per_repo[f["repo"]][1] += 1
            if links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])):
                per_repo[f["repo"]][0] += 1
    by_repo = {r: round(a / b, 3) for r, (a, b) in per_repo.items() if b >= 10}
    logged = [i for i, w in enumerate(WEEKS) if w >= "2026-W32" and w not in OUTAGE_WEEKS]
    cats = [c for c in s if c != "Dependabot"]
    n_logged = sum(s[c][i] for c in cats for i in logged)
    share_logged = {c: round(sum(s[c][i] for i in logged) / n_logged, 3) for c in cats}
    return {**o, "planned_share": share, "share_logged": share_logged, "by_repo": dict(sorted(by_repo.items(), key=lambda kv: -kv[1])),
            "planned_last4": round(sum(planned[i] for i in idx) / sum(tot[i] for i in idx), 3)}


# ---------------------------------------------------------------- Q toolkit-growth

def q_toolkit_growth_toolkit(con):
    """Live skills and their total SKILL.md lines per week; wayfare-skills change sets per week."""
    live, lines = {}, {}
    ev = rows(con, "SELECT skill, day, change_type, lines FROM knowledge.skill_versions ORDER BY ts")
    n_live, n_lines = [], []
    i = 0
    for w in WEEKS:
        end = week_end(w)
        while i < len(ev) and ev[i]["day"] <= end:
            e = ev[i]
            if e["change_type"] == "delete":
                live.pop(e["skill"], None)
            else:
                live[e["skill"]] = e["lines"] or 0
            i += 1
        n_live.append(len(live))
        n_lines.append(sum(live.values()))
    plugin = [0] * len(WEEKS)
    for f in changeset_facts(con):
        if f["repo"] == "wayfare-skills" and f["week"] in WEEKS and not f["dependabot"]:
            plugin[WEEKS.index(f["week"])] += 1
    touched = Counter(e["skill"] for e in ev)
    return {"weeks": WEEKS, "live": n_live, "lines": n_lines, "plugin_sets": plugin,
            "skills_ever": len(touched), "live_now": n_live[-1], "lines_now": n_lines[-1],
            "versions": len(ev), "plugin_total": sum(plugin)}


def all_data():
    con = connect()
    return {name: fn(con) for name, fn in globals().items() if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__}


if __name__ == "__main__":
    d = all_data()
    for k, v in d.items():
        print("==", k)
        print(json.dumps({a: b for a, b in v.items() if not isinstance(b, (list, dict)) or a in (
            "counts", "top", "totals", "share_total", "now", "head", "trace", "session", "logs", "table",
            "share_since_sessions", "peak_week", "per_day_merges_before", "per_day_touched_since", "month_share",
            "per_month", "tokens")}, default=str)[:3000])
