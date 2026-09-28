"""Toward an architecture series: the factory's components, their order of adoption, and what came with each.

One function per question (q_component_inventory ... q_recommended_adoption_order), each returning what its answer slide and
breakdown slide plot. Reuses record (adoption, change sets, commit facts) and
links.set_item_links; everything specific to this chapter lives here.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/components/data.py   # prints every answer's numbers
"""
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ANALYSIS)
sys.path.insert(0, os.path.dirname(HERE))
from record import STAGES, adoption, changeset_facts, commit_facts, rows, week_of  # noqa: E402

DATA = os.path.join(os.path.dirname(ANALYSIS), ".analysis", "data")
REPO_ROOT = os.path.dirname(ANALYSIS)

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
TODAY = "2026-09-24"
RECENT = "2026-08-26"  # "in use now" = seen in the last 30 days
SESSIONS_FROM = "2026-08-09"
SKILLS_FROM = "2026-08-25"  # first wayfare skill invocation in the session logs (harness.tool_calls)
FOLLOWUP_CUTOFF = "2026-09-17"  # a PR merged later has not had its 7 days to draw a follow-up
# 10-24 Aug (W33-W34): no Claude Code sessions are logged between the one on 9 Aug and 25 Aug; the owner
# confirmed the data is not available. Session-derived series (sessions, tool calls, spend) treat those
# weeks as missing, never zero. Git, GitHub and .plans data are unaffected.
NO_DATA = ("2026-08-10", "2026-08-24")
NO_DATA_WEEKS = {"2026-W33", "2026-W34"}
PRE_DAYS = 28  # an event study needs the component to arrive at least 4 weeks after the repo's first commit
APPS = ("app", "app, no features yet")


def connect():
    from cube.db import connect as cube_connect
    return cube_connect("components")


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], capture_output=True, text=True, check=True).stdout


def mean(v):
    v = [x for x in v if x is not None]
    return round(statistics.mean(v), 3) if v else None


def median(v):
    v = [x for x in v if x is not None]
    return round(statistics.median(v), 1) if v else None


def days(a, b):
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def monday(week):
    return date.fromisocalendar(int(week[:4]), int(week[6:]), 1)


# ---------------------------------------------------------------- the components

# When wayfare shipped each component, from wayfare-skills' own history (the commit that
# introduced it). `signal` is how a repo's own history shows it took the component up:
# a file its first commit touched, or its first work item, goal or message in .plans.
COMPONENTS = [
    dict(key="skills", name="Skills + HERO.md", shipped="2026-03-07", sha="a2bb70d",
         what="hero skills plugin; hero-init writes HERO.md", signal=("file", ["HERO.md"])),
    dict(key="precommit", name="Local gates (pre-commit)", shipped="2026-03-07", sha="327a83e",
         what="hero-init sets up pre-commit", signal=("file", [".pre-commit-config.yaml"])),
    dict(key="autoapprove", name="Auto-approve judge", shipped="2026-03-29", sha="4b6358d",
         what="Claude PR auto-approve workflow; reusable fleet-wide from 18 Jul (93b7f4d)",
         signal=("file", [".github/workflows/auto-approve.yml", ".github/workflows/auto-approve.yaml"])),
    dict(key="review", name="Review loop", shipped="2026-05-04", sha="5548869",
         what="self-review + review-pr, auto-approve gated on prior review", signal=None),
    dict(key="pipeline", name="Build pipeline", shipped="2026-05-09", sha="cea2771",
         what="one-shot pipeline (now wayfare-build-task)", signal=None),
    dict(key="items", name="Work items", shipped="2026-07-05", sha="36786de",
         what="grill emits work items (plan-work/, then .plans/ on 22 Jul)", signal=("plans", "items")),
    dict(key="compliance", name="Compliance register", shipped="2026-07-18", sha="hero-template",
         what="CONSISTENCY.md in hero-template; engine moved into wayfare 13 Sep (bc49826)",
         signal=("file", ["CONSISTENCY.md"])),
    dict(key="agents", name="AGENTS.md standard", shipped="2026-07-20", sha="b8a5765",
         what="AGENTS.md standard (with recomponentize-ui)", signal=("file", ["AGENTS.md"])),
    dict(key="dshook", name="Design-system hook", shipped="2026-07-20", sha="0b4a581",
         what="design-token hook and rule installed into repos",
         signal=("file", [".claude/hooks/check-design-tokens.sh"])),
    dict(key="design_repos", name="-design repos", shipped="2026-07-22", sha="first -design repo",
         what="one -design repo per app; replaced by a claude.ai/design project on 16 Aug (4894f14)",
         signal=None, retired="2026-08-16"),
    dict(key="arch", name="Architecture record", shipped="2026-07-23", sha="f261a88",
         what="ARCHITECTURE.md, superseded by DESIGN.md on 30 Jul (70de941)",
         signal=("file", ["ARCHITECTURE.md", "DESIGN.md"])),
    dict(key="goals", name="Goals", shipped="2026-08-28", sha="6a0c0b6", what="/goal-driven runs",
         signal=("plans", "goals")),
    dict(key="fleet", name="Fleet map (FLEET.md)", shipped="2026-08-29", sha="2e58547",
         what="FLEET.md standard and fleet skill; local and unversioned", signal=None),
    dict(key="messages", name="Messages", shipped="2026-09-13", sha="7181504", what="the mailbox",
         signal=("plans", "messages")),
]
COMP = {c["key"]: c for c in COMPONENTS}
# The components a repo's own history can show it adopting, in the order wayfare shipped them.
REPO_COMPONENTS = [c["key"] for c in COMPONENTS if c["signal"]]


@lru_cache(maxsize=None)
def repo_adoption(con):
    """{repo: {component: first day}} for the in-scope repos."""
    ad = adoption(con)
    files = defaultdict(dict)
    for c in COMPONENTS:
        if c["signal"] and c["signal"][0] == "file":
            ph = ",".join("?" * len(c["signal"][1]))
            for r in rows(con, f"""SELECT c.repo, MIN(c.day) d FROM git.commit_files f
                                   JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha
                                   WHERE f.path IN ({ph}) GROUP BY c.repo""", tuple(c["signal"][1])):
                files[r["repo"]][c["key"]] = r["d"]
    out = {}
    for repo, a in ad.items():
        d = dict(files.get(repo, {}))
        for k in ("items", "goals", "messages"):
            if a[k]:
                d[k] = a[k]
        out[repo] = d
    return out


@lru_cache(maxsize=None)
def skill_invocations(con):
    """(repo, day, skill) for every skill invocation in the session logs (from 9 Aug)."""
    return rows(con, """SELECT s.repo, SUBSTR(t.ts,1,10) day, t.skill_name skill FROM harness.tool_calls t
                        JOIN harness.sessions s ON s.session_id_hash = t.session_id_hash
                        WHERE t.skill_name IS NOT NULL AND t.skill_name != ''""")


def in_use_now(con):
    """Per component: how many in-scope repos used it in the last 30 days, and the evidence used."""
    ad = adoption(con)
    scope = set(ad)
    head = lambda artifact: {r["repo"] for r in rows(con, "SELECT repo FROM detectors.presence WHERE snapshot='head' "
                                                         "AND artifact=? AND present=1", (artifact,))} & scope
    touched = lambda paths: {r["repo"] for r in rows(con, f"""SELECT DISTINCT c.repo FROM git.commit_files f
        JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha WHERE c.day >= ? AND f.path IN ({','.join('?' * len(paths))})""",
        (RECENT, *paths))} & scope
    inv = lambda pat: {r["repo"] for r in skill_invocations(con) if r["day"] >= RECENT and re.search(pat, r["skill"])} & scope
    aa = {r["repo"] for r in rows(con, "SELECT DISTINCT repo FROM github.pr_reviews WHERE reviewer='github-actions' "
                                       "AND submitted_ts >= ?", (RECENT,))} & scope
    reviewed = {r["repo"] for r in rows(con, "SELECT DISTINCT repo FROM github.pr_reviews WHERE submitted_ts >= ? "
                                             "AND reviewer != 'github-actions'", (RECENT,))} | inv(r"review-pr")
    items = {r["repo"] for r in rows(con, "SELECT DISTINCT repo FROM plans.plan_items WHERE type!='goal' AND day >= ?",
                                     (RECENT,))} & scope
    goals = {r["repo"] for r in rows(con, "SELECT DISTINCT repo FROM plans.plan_items WHERE type='goal' AND day >= ?",
                                     (RECENT,))} & scope
    msgs = set()
    for r in rows(con, "SELECT from_repo, to_repo FROM plans.messages WHERE created_ts >= ?", (RECENT,)):
        msgs |= {r["from_repo"], r["to_repo"]}
    ev = {
        "skills": (inv(r"."), "a skill invoked in a session"),
        "precommit": (head("pre_commit_config"), ".pre-commit-config.yaml at head"),
        "autoapprove": (aa, "an auto-approve verdict posted"),
        "review": (reviewed & scope, "a PR review or a review-pr run"),
        "pipeline": (inv(r"one-shot|run-task|build-task|push-pr"), "a build-pipeline skill invoked"),
        "items": (items, "a work item created"),
        "compliance": (touched(["CONSISTENCY.md"]), "CONSISTENCY.md regenerated"),
        "agents": (head("agents_md"), "AGENTS.md at head"),
        "dshook": (touched([".claude/hooks/check-design-tokens.sh"]) | head("claude_md") & set(), "hook file changed"),
        "design_repos": (set(), "retired 16 Aug"),
        "arch": (touched(["DESIGN.md"]) | inv(r"architecture"), "DESIGN.md changed or an architecture skill run"),
        "goals": (goals, "a goal created"),
        "fleet": (set(), "FLEET.md is local and unversioned: not observable"),
        "messages": (msgs & scope, "a message sent or received"),
    }
    return {k: {"n": len(v[0]), "repos": sorted(v[0]), "evidence": v[1]} for k, v in ev.items()}


# ---------------------------------------------------------------- Q component-inventory

def q_component_inventory_components(con):
    """The components as a swimlane from first ship to retirement or today, and who uses each now."""
    first_design = rows(con, "SELECT MIN(day) d FROM git.commits WHERE repo LIKE '%-design'")[0]["d"]
    use = in_use_now(con)
    lanes = []
    for c in COMPONENTS:
        start = first_design if c["key"] == "design_repos" else c["shipped"]
        lanes.append({**c, "start": start, "end": c.get("retired") or TODAY, "retired": bool(c.get("retired")),
                      "in_use": use[c["key"]]["n"], "evidence": use[c["key"]]["evidence"],
                      "use_repos": use[c["key"]]["repos"]})
    return {"lanes": lanes, "n_scope": len(adoption(con)),
            "n_live": sum(1 for l in lanes if not l["retired"]),
            "n_used": sum(1 for l in lanes if l["in_use"] > 0)}


# ---------------------------------------------------------------- Q adoption-order

ORDER_CATS = ["In a bundle (3+ on one day)", "One at a time, in ship order", "Ahead of an earlier component"]


# Work items are tracked from 23 Jul (.plans); a repo's first item in the first days of tracking
# may stand for plan-work/ items that were never ingested, so it is not evidence of lateness.
TRACKED_FROM = {"items": "2026-07-25"}
TIE_DAYS = 14  # components shipped within two weeks of each other have no order between them


def shipped_before(k1, k2):
    return days(COMP[k1]["shipped"], COMP[k2]["shipped"]) > TIE_DAYS


def later(d, k2, day):
    """True if the repo took k2 up after `day` (or never), as far as the data can tell."""
    if k2 not in d:
        return True
    if d[k2] <= TRACKED_FROM.get(k2, ""):
        return False
    return d[k2] > day


def jumped(d, k, day):
    return [k2 for k2 in REPO_COMPONENTS if shipped_before(k2, k) and later(d, k2, day)]


def adoption_events(con):
    """Every (repo, component, day) adoption, classed as bundled, in order or ahead of order."""
    ra = repo_adoption(con)
    ev = []
    for repo, d in ra.items():
        per_day = Counter(d.values())
        for k, day in d.items():
            if per_day[day] >= 3:
                cls = ORDER_CATS[0]
            elif jumped(d, k, day):
                cls = ORDER_CATS[2]
            else:
                cls = ORDER_CATS[1]
            ev.append({"repo": repo, "comp": k, "day": day, "week": week_of(day), "cls": cls})
    return ev


def skipped(con):
    """Per repo: components shipped while the repo was active that it never took up."""
    ad, ra = adoption(con), repo_adoption(con)
    out = {}
    for repo, a in ad.items():
        out[repo] = [k for k in REPO_COMPONENTS if k not in ra[repo] and COMP[k]["shipped"] <= a["last"]]
    return out


def pair_order(con):
    """Share of adopted component pairs that a repo took up in wayfare's ship order (same-day pairs excluded)."""
    ra = repo_adoption(con)
    rank = {k: i for i, k in enumerate(REPO_COMPONENTS)}
    agree = total = 0
    per_repo = {}
    for repo, d in ra.items():
        a = t = 0
        ks = sorted(d, key=lambda k: rank[k])
        for i, k1 in enumerate(ks):
            for k2 in ks[i + 1:]:
                if d[k1] == d[k2] or not shipped_before(k1, k2) or d[k1] <= TRACKED_FROM.get(k1, ""):
                    continue
                t += 1
                a += d[k1] < d[k2]
        per_repo[repo] = (a, t)
        agree, total = agree + a, total + t
    return round(agree / total, 3) if total else None, per_repo


def q_adoption_order_order(con):
    ev = adoption_events(con)
    ev26 = [e for e in ev if e["day"] >= "2026-01-01"]
    series = {c: [sum(1 for e in ev26 if e["week"] == w and e["cls"] == c) for w in WEEKS] for c in ORDER_CATS}
    ad = adoption(con)
    sk = skipped(con)
    share, per_pair = pair_order(con)
    order = sorted(ad, key=lambda r: (ad[r]["category"] != "app", ad[r]["category"], ad[r]["first"]))
    by_repo = {c: [sum(1 for e in ev if e["repo"] == r and e["cls"] == c) for r in order] for c in ORDER_CATS}
    by_repo["Never taken up"] = [len(sk[r]) for r in order]
    ahead = Counter((e["comp"]) for e in ev if e["cls"] == ORDER_CATS[2])
    # what each out-of-order adoption jumped ahead of
    ra, rank = repo_adoption(con), {k: i for i, k in enumerate(REPO_COMPONENTS)}
    jumps = Counter()
    for e in ev:
        if e["cls"] == ORDER_CATS[2]:
            for k2 in jumped(ra[e["repo"]], e["comp"], e["day"]):
                jumps[(e["comp"], k2)] += 1
    skipped_counts = Counter(k for r in sk for k in sk[r])
    return {"weeks": WEEKS, "series": series, "totals": {c: sum(1 for e in ev if e["cls"] == c) for c in ORDER_CATS},
            "n_events": len(ev), "repos": order, "by_repo": by_repo, "pair_share": share,
            "per_repo_pairs": per_pair, "ahead_by_comp": dict(ahead), "jumps": dict(jumps.most_common(12)),
            "skipped": {r: v for r, v in sk.items() if v}, "skipped_counts": dict(skipped_counts),
            "bundle_repos": sorted({e["repo"] for e in ev if e["cls"] == ORDER_CATS[0]})}


# ---------------------------------------------------------------- Q adoption-lag

LAG_COMPONENTS = ["skills", "autoapprove", "items", "compliance", "agents", "arch", "goals", "messages"]


def q_adoption_lag_lag(con):
    """Share of in-scope repos (that existed that week) having each component; days from ship to uptake."""
    ad, ra = adoption(con), repo_adoption(con)
    series = {}
    for k in LAG_COMPONENTS:
        vals = []
        for w in WEEKS:
            end = (monday(w) + timedelta(days=6)).isoformat()
            if end < COMP[k]["shipped"]:
                vals.append(None)
                continue
            exist = [r for r in ad if ad[r]["first"] <= end]
            vals.append(round(sum(1 for r in exist if ra[r].get(k) and ra[r][k] <= end) / len(exist), 3) if exist else None)
        series[COMP[k]["name"]] = vals
    lags = {}
    for k in LAG_COMPONENTS:
        ls, never, before = [], 0, 0
        for r, a in ad.items():
            if a["last"] < COMP[k]["shipped"]:
                continue
            start = max(COMP[k]["shipped"], a["first"], {"items": "2026-07-23"}.get(k, ""))
            if k in ra[r]:
                lag = days(start, ra[r][k])
                before += lag < 0
                ls.append(max(0, lag))
            else:
                never += 1
        lags[k] = {"median": median(ls), "max": max(ls) if ls else None, "n": len(ls), "never": never,
                   "before_ship": before, "within_7": sum(1 for x in ls if x <= 7)}
    return {"weeks": WEEKS, "series": series, "lags": lags}


# ---------------------------------------------------------------- Q retired-components

# What became of each skill directory git shows deleted without a rename; read from the
# commit that deleted it. Git's own rename detection covers the rest.
SKILL_FATES = {
    "hero-reflect": ("merged", "hero-update", "422787b replaced by hero-update the same day"),
    "hero-pr-create": ("merged", "hero-push", "984b92f draft support moved into hero-push"),
    "hero-update": ("merged", "hero-init", "d137046 'hero-init --update covers this'"),
    "hero-implement": ("merged", "hero-plan", "8bb6040 consolidate plan+implement"),
    "hero-cicd": ("merged", "check-ci", "21b62c5 hero-cicd + hero-health -> check"),
    "hero-health": ("merged", "check-ci", "21b62c5 hero-cicd + hero-health -> check"),
    "hero-review-pr": ("merged", "review-pr", "21b62c5 hero-self-review + hero-review-pr -> review"),
    "hero-self-review": ("merged", "review-pr", "21b62c5 hero-self-review + hero-review-pr -> review"),
    "check-ci": ("merged", "push-pr", "cb9cc2a push-pr absorbs CI-status reporting"),
    "commit-changes": ("merged", "push-pr", "cb9cc2a push-pr absorbs commit"),
    "create-branch": ("merged", "push-pr", "cb9cc2a push-pr absorbs branch-off-default"),
    "plan-work": ("merged", "one-shot", "cb9cc2a one-shot inlines the plan"),
    "smoke-ui": ("merged", "test-changes", "cb9cc2a test-changes absorbs smoke-ui"),
    "reset-branch": ("renamed", "abandon-branch", "45bb50c 'rename reset-branch' to abandon-branch"),
    "document-arch": ("merged", "think-it-through", "b6ee8c3 merge document-arch into think-it-through"),
    "scan-vulns": ("merged", "harden", "b6ee8c3 harden replaces scan-vulns, read-only by contract"),
    "test-changes": ("merged", "push-pr", "b6ee8c3 merge test-changes into push-pr"),
    "abandon": ("merged", "wayfare (drop)", "6124e58 'drop ID absorbs abandon'"),
    "create-project": ("merged", "wayfare (init)", "6124e58 'init absorbs init-hero and create-project'"),
    "init-hero": ("merged", "wayfare (init)", "6124e58 'init absorbs init-hero and create-project'"),
    "wayfare": ("split", "six wayfare-* skills", "1c785e1 one skill per verb: init, sync, next, do, drop, recalibrate"),
}
FATE_CATS = ["Still live", "Renamed", "Merged into another", "Split into several", "Removed outright"]


def skill_history():
    """Every skill directory name ever, with the day it appeared and what became of it."""
    out = git("log", "--reverse", "--format=@%h %ad", "--date=short", "-M30%", "--name-status", "--",
              "skills/*/SKILL.md")
    names, events = {}, []
    sha = day = None
    name_of = lambda p: p.split("/")[1]
    for line in out.splitlines():
        if line.startswith("@"):
            sha, day = line[1:].split()
            continue
        parts = line.split("\t")
        if not parts[0]:
            continue
        st = parts[0][0]
        if st == "A":
            n = name_of(parts[1])
            names.setdefault(n, {"born": day, "fate": None})
            events.append({"day": day, "sha": sha, "kind": "New skill", "name": n})
        elif st == "R":
            old, new = name_of(parts[1]), name_of(parts[2])
            names.setdefault(new, {"born": day, "fate": None})
            names[old].update(fate="Renamed", died=day, into=new, sha=sha)
            events.append({"day": day, "sha": sha, "kind": "Renamed", "name": old})
        elif st == "D":
            n = name_of(parts[1])
            kind, into, why = SKILL_FATES.get(n, ("removed", None, ""))
            fate = {"renamed": "Renamed", "merged": "Merged into another", "split": "Split into several",
                    "removed": "Removed outright"}[kind]
            names[n].update(fate=fate, died=day, into=into, sha=sha, why=why)
            events.append({"day": day, "sha": sha, "kind": fate, "name": n})
    for n, v in names.items():
        if not v["fate"]:
            v["fate"] = "Still live"
    return names, events


# Components (not skills) that were built and later replaced or removed, from wayfare-skills' history.
RETIRED = [
    ("-design repos", "2026-07-21", "2026-08-16", "a claude.ai/design project (4894f14)"),
    ("plan-work/ and my-work/ stores", "2026-07-05", "2026-07-22", ".plans/ (366658b)"),
    ("Control-plane machinery", "2026-07-22", "2026-07-23", "a feature roadmap lifecycle (836aafc)"),
    ("ARCHITECTURE.md", "2026-07-23", "2026-07-30", "DESIGN.md (70de941)"),
    ("Moving v1 tag for auto-approve", "2026-08-04", "2026-08-06", "callers track main (b2fe713)"),
    ("The hero-skills name", "2026-03-07", "2026-09-21", "wayfare (1c785e1, 27829f3)"),
]


def q_retired_components_retired():
    names, events = skill_history()
    kinds = ["New skill", "Renamed", "Merged into another", "Split into several", "Removed outright"]
    ev26 = [e for e in events]
    series = {k: [sum(1 for e in ev26 if week_of(e["day"]) == w and e["kind"] == k) for w in WEEKS] for k in kinds}
    fates = Counter(v["fate"] for v in names.values())
    lifetimes = {n: days(v["born"], v.get("died", TODAY)) for n, v in names.items() if v["fate"] != "Still live"}
    live_now = sorted(n for n, v in names.items() if v["fate"] == "Still live")
    # a lineage: follow renames and merges forward; count the distinct functions ever built
    return {"weeks": WEEKS, "series": series, "fates": {k: fates.get(k, 0) for k in FATE_CATS},
            "n_names": len(names), "live_now": live_now, "median_life_gone": median(list(lifetimes.values())),
            "retired": [dict(name=n, born=b, died=d, into=i, days=days(b, d)) for n, b, d, i in RETIRED],
            "names": names}


# ---------------------------------------------------------------- Q component-traffic

@lru_cache(maxsize=None)
def set_paths(con):
    """Per change set (non-Dependabot, in scope): which components it passed through."""
    from links import set_item_links
    links, _ = set_item_links(con)
    goal_items = {(r["repo"], r["item_id"]) for r in rows(con, "SELECT repo, item_id FROM plans.plan_items "
                                                                "WHERE goal_id IS NOT NULL AND goal_id != ''")}
    heads = {(r["repo"], r["number"]): r["head_ref"] or "" for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    human_review = {(r["repo"], r["number"]) for r in rows(con, "SELECT DISTINCT repo, number FROM github.pr_reviews "
                                                                 "WHERE reviewer != 'github-actions'")}
    judge = {(r["repo"], r["number"]) for r in rows(con, "SELECT DISTINCT repo, number FROM github.pr_reviews "
                                                          "WHERE reviewer = 'github-actions'")}
    skill_sessions = {r["session_id_hash"] for r in rows(con, "SELECT DISTINCT session_id_hash FROM harness.tool_calls "
                                                              "WHERE skill_name LIKE 'hero-skills:%' OR skill_name LIKE 'wayfare:%'")}
    skill_prs = set()
    for r in rows(con, "SELECT session_id_hash, pr_links FROM harness.sessions WHERE pr_links NOT IN ('', '[]')"):
        if r["session_id_hash"] in skill_sessions:
            for link in json.loads(r["pr_links"]):
                m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
                if m:
                    skill_prs.add((m.group(1).replace("hero-skills", "wayfare-skills"), int(m.group(2))))
    out = []
    for f in changeset_facts(con):
        if f["dependabot"]:
            continue
        items = links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]), set())
        key = (f["repo"], f["pr"])
        in_goal = bool(re.search(r"goal-\d+", heads.get(key, ""))) or any((f["repo"], i) in goal_items for i in items)
        out.append({**f, "item": bool(items), "goal": in_goal, "reviewed": key in human_review or key in judge,
                    "judge": key in judge, "skill": key in skill_prs if f["day"] >= SKILLS_FROM else None,
                    "oneshot": f["pr"] is not None and not items})
    return out


REACH = [("item", "Planned in a work item"), ("goal", "Inside a goal"), ("judge", "Passed the auto-approve judge"),
         ("skill", "Built in a session that ran a wayfare skill")]


def q_component_traffic_reach(con):
    sp = [s for s in set_paths(con) if s["category"] in APPS]
    wk = defaultdict(list)
    for s in sp:
        wk[s["week"]].append(s)
    series = {}
    for k, name in REACH:
        vals = []
        for w in WEEKS:
            xs = [s[k] for s in wk[w] if s[k] is not None]
            vals.append(round(sum(xs) / len(xs), 3) if len(xs) >= 5 else None)
        series[name] = vals
    recent = [s for s in sp if s["day"] >= "2026-08-01"]
    by_repo_names = sorted({s["repo"] for s in recent}, key=lambda r: -sum(1 for s in recent if s["repo"] == r))[:9]
    by_repo = {}
    for k, name in REACH:
        vals = []
        for r in by_repo_names:
            xs = [s[k] for s in recent if s["repo"] == r and s[k] is not None]
            vals.append(round(sum(xs) / len(xs), 3) if xs else 0)
        by_repo[name] = vals
    since = [s for s in sp if s["day"] >= SKILLS_FROM]
    none = [s for s in since if not s["item"] and not s["goal"] and not s["skill"]]
    share = {name: round(sum(1 for s in since if s[k]) / len(since), 3) for k, name in REACH}
    return {"weeks": WEEKS, "series": series, "repos": by_repo_names, "by_repo": by_repo, "share_since": share,
            "n_since": len(since), "bypass_since": round(len(none) / len(since), 3) if since else None,
            "bypass_by_judge": round(sum(1 for s in none if s["judge"]) / len(none), 3) if none else None}


# ---------------------------------------------------------------- Q output-after-adoption to Q owner-share-after-adoption: event studies

REL = list(range(-6, 7))
EVENT_COMPONENTS = ["items", "agents", "arch", "goals"]


def aligned(con, per_repo_week, comps=EVENT_COMPONENTS, cats=APPS, agg=mean, min_n=3):
    """For each component: the outcome averaged over app repos, in weeks relative to each repo's own adoption.
    per_repo_week(repo, week) -> value or None (None = no activity that week)."""
    ad, ra = adoption(con), repo_adoption(con)
    out, n = {}, {}
    for k in comps:
        vals = defaultdict(list)
        repos = [r for r in ad if ad[r]["category"] in cats and ra[r].get(k) and ra[r][k] >= "2026-01-01"
                 and days(ad[r]["first"], ra[r][k]) >= PRE_DAYS]
        for r in repos:
            y, w0, _ = date.fromisoformat(ra[r][k]).isocalendar()
            for rel in REL:
                d = date.fromisocalendar(y, w0, 1) + timedelta(weeks=rel)
                y2, w2, _ = d.isocalendar()
                if ad[r]["first"] <= (d + timedelta(days=6)).isoformat() and d.isoformat() <= ad[r]["last"]:
                    v = per_repo_week(r, f"{y2}-W{w2:02d}")
                    if v is not None:
                        vals[rel].append(v)
        out[COMP[k]["name"]] = [agg(vals[x]) if len(vals[x]) >= min_n else None for x in REL]
        n[COMP[k]["name"]] = len(repos)
    return out, n


def aligned_ratio(con, pairs, comps=EVENT_COMPONENTS, min_den=5):
    """Like aligned, for a rate: pairs(repo, week) -> (numerator, denominator), pooled over repos.
    Returns the rate per relative week, and pooled before (weeks -6..-1) and after (+1..+6)."""
    ad, ra = adoption(con), repo_adoption(con)
    series, pooled, n = {}, {}, {}
    for k in comps:
        num, den = defaultdict(float), defaultdict(float)
        repos = [r for r in ad if ad[r]["category"] in APPS and ra[r].get(k) and ra[r][k] >= "2026-01-01"
                 and days(ad[r]["first"], ra[r][k]) >= PRE_DAYS]
        for r in repos:
            y, w0, _ = date.fromisoformat(ra[r][k]).isocalendar()
            for rel in REL:
                d = date.fromisocalendar(y, w0, 1) + timedelta(weeks=rel)
                y2, w2, _ = d.isocalendar()
                a, b = pairs(r, f"{y2}-W{w2:02d}")
                num[rel] += a
                den[rel] += b
        name = COMP[k]["name"]
        series[name] = [round(num[x] / den[x], 3) if den[x] >= min_den else None for x in REL]
        pre_n, pre_d = sum(num[x] for x in REL if x < 0), sum(den[x] for x in REL if x < 0)
        post_n, post_d = sum(num[x] for x in REL if x > 0), sum(den[x] for x in REL if x > 0)
        pooled[name] = (round(pre_n / pre_d, 3) if pre_d >= min_den else None,
                        round(post_n / post_d, 3) if post_d >= min_den else None, int(pre_d), int(post_d))
        n[name] = len(repos)
    return series, pooled, n


def pre_post(v):
    pre = [x for x in v[:6] if x is not None]
    post = [x for x in v[7:] if x is not None]
    return (round(statistics.mean(pre), 3) if pre else None, round(statistics.mean(post), 3) if post else None)


def weekly_by_stage(facts, value, min_n=5):
    by = defaultdict(list)
    for f in facts:
        by[(f["stage"], f["week"])].append(value(f))
    return {s: [mean(by[(s, w)]) if len(by[(s, w)]) >= min_n else None for w in WEEKS] for s in STAGES}


def q_output_after_adoption_output(con):
    """Change sets per active app-week around each component's adoption (Q crediting-factory-changes did items and goals)."""
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    per = Counter((f["repo"], f["week"]) for f in cs)
    ad = adoption(con)
    series, n = aligned(con, lambda r, w: per.get((r, w), 0))
    pp = {k: pre_post(v) for k, v in series.items()}
    # the calendar: the same weeks' output in apps that had not adopted yet (a naive control)
    ra = repo_adoption(con)
    control = {}
    for k in EVENT_COMPONENTS:
        diffs = []
        for r in ad:
            if ad[r]["category"] not in APPS or not ra[r].get(k) or ra[r][k] < "2026-01-01" \
                    or days(ad[r]["first"], ra[r][k]) < PRE_DAYS:
                continue
            y, w0, _ = date.fromisoformat(ra[r][k]).isocalendar()
            base = date.fromisocalendar(y, w0, 1)
            for rel in REL:
                d = base + timedelta(weeks=rel)
                y2, w2, _ = d.isocalendar()
                wk = f"{y2}-W{w2:02d}"
                others = [per.get((o, wk), 0) for o in ad if o != r and ad[o]["category"] in APPS
                          and ad[o]["first"] <= d.isoformat() <= ad[o]["last"]
                          and (not ra[o].get(k) or ra[o][k] > (d + timedelta(days=6)).isoformat())]
                if others and ad[r]["first"] <= d.isoformat() <= ad[r]["last"]:
                    diffs.append((rel, per.get((r, wk), 0) - statistics.mean(others)))
        pre = [v for rel, v in diffs if rel < 0]
        post = [v for rel, v in diffs if rel > 0]
        control[COMP[k]["name"]] = (mean(pre), mean(post), len(pre), len(post))
    wk_stage = defaultdict(set)
    for f in cs:
        if f["category"] in APPS:
            wk_stage[(f["stage"], f["week"])].add(f["repo"])
    by_stage = {s: [round(sum(1 for f in cs if f["category"] in APPS and f["stage"] == s and f["week"] == w)
                          / len(wk_stage[(s, w)]), 2) if wk_stage[(s, w)] else None for w in WEEKS] for s in STAGES}
    return {"rel": REL, "series": series, "n_repos": n, "pre_post": pp, "control": control, "weeks": WEEKS,
            "by_stage": by_stage}


def q_fixes_after_adoption_followups(con):
    """Share of merged app PRs followed by a same-files fix within 7 days, around each adoption."""
    fu = {(r["repo"], r["number"]): r["followup_within_7d_days"] is not None
          for r in rows(con, "SELECT repo, number, followup_within_7d_days FROM detectors.followups")}
    merged = rows(con, "SELECT repo, number, SUBSTR(merged_ts,1,10) d FROM github.prs WHERE merged_ts IS NOT NULL "
                       "AND head_ref NOT LIKE 'dependabot/%' AND author_is_bot = 0 AND SUBSTR(merged_ts,1,10) <= ?",
                  (FOLLOWUP_CUTOFF,))
    ad = adoption(con)
    from record import stage_of
    prs = []
    for m in merged:
        if m["repo"] in ad and (m["repo"], m["number"]) in fu:
            prs.append({"repo": m["repo"], "week": week_of(m["d"]), "day": m["d"], "fu": fu[(m["repo"], m["number"])],
                        "stage": stage_of(con, m["repo"], m["d"]), "category": ad[m["repo"]]["category"]})
    per = defaultdict(list)
    for p in prs:
        per[(p["repo"], p["week"])].append(p["fu"])
    series, pooled, n = aligned_ratio(con, lambda r, w: (sum(per.get((r, w), [])), len(per.get((r, w), []))))
    apps = [p for p in prs if p["category"] in APPS]
    stage = weekly_by_stage(apps, lambda p: p["fu"], min_n=5)
    overall = {s: mean([p["fu"] for p in apps if p["stage"] == s]) for s in STAGES}
    counts = {s: sum(1 for p in apps if p["stage"] == s) for s in STAGES}
    return {"rel": REL, "series": series, "n_repos": n, "pre_post": pooled,
            "weeks": WEEKS, "by_stage": stage, "overall_by_stage": overall, "counts_by_stage": counts,
            "n_prs": len(apps), "rate_all": mean([p["fu"] for p in apps])}


def q_owner_share_after_adoption_owner(con):
    """The owner's hands-on share: original commits authored by the human alone (not co-authored by the agent)."""
    cf = [c for c in commit_facts(con) if c["actor"] != "bot" and c["category"] in APPS]
    per = defaultdict(list)
    for c in cf:
        per[(c["repo"], c["week"])].append(c["actor"] == "human")
    series, pooled, n = aligned_ratio(con, lambda r, w: (sum(per.get((r, w), [])), len(per.get((r, w), []))))
    stage = weekly_by_stage(cf, lambda c: c["actor"] == "human", min_n=5)
    fleet = []
    for w in WEEKS:
        xs = [c["actor"] == "human" for c in cf if c["week"] == w]
        fleet.append(round(sum(xs) / len(xs), 3) if len(xs) >= 5 else None)
    return {"rel": REL, "series": series, "n_repos": n, "pre_post": pooled,
            "weeks": WEEKS, "fleet": fleet, "by_stage": stage,
            "overall_by_stage": {s: mean([c["actor"] == "human" for c in cf if c["stage"] == s]) for s in STAGES},
            "human_share_h1": mean([c["actor"] == "human" for c in cf if c["day"] < "2026-07-01"]),
            "human_share_since_aug": mean([c["actor"] == "human" for c in cf if c["day"] >= "2026-08-01"])}


# ---------------------------------------------------------------- Q cost-by-architecture-depth

PATHS = ["One-shot (no work item)", "Work item, no goal", "Work item inside a goal"]


def q_cost_by_architecture_depth_spend(con):
    """Harness spend per change set, by the path the work took, from 9 Aug."""
    spend = defaultdict(float)
    heads = {(r["repo"], r["head_ref"]): r["number"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    total = attributed = 0.0
    for r in rows(con, "SELECT s.repo, s.branch, s.cost_usd, h.week FROM detectors.session_spend s "
                       "JOIN harness.sessions h ON h.session_id_hash = s.session_id_hash"):
        total += r["cost_usd"] or 0
        pr = heads.get((r["repo"], r["branch"]))
        if pr is not None:
            spend[(r["repo"], pr)] += r["cost_usd"] or 0
            attributed += r["cost_usd"] or 0
    sp = [s for s in set_paths(con) if s["day"] >= SKILLS_FROM and s["pr"] is not None]
    per_pr = defaultdict(list)
    for s in sp:
        per_pr[(s["repo"], s["pr"])].append(s)
    prs = []
    for k, ss in per_pr.items():
        if k not in spend:
            continue
        path = PATHS[2] if any(s["goal"] for s in ss) else PATHS[1] if any(s["item"] for s in ss) else PATHS[0]
        prs.append({"repo": k[0], "pr": k[1], "week": ss[0]["week"], "path": path, "usd": spend[k], "sets": len(ss),
                    "category": ss[0]["category"]})
    series = {}
    for p in PATHS:
        vals = []
        for w in WEEKS:
            xs = [x for x in prs if x["path"] == p and x["week"] == w]
            vals.append(round(sum(x["usd"] for x in xs) / sum(x["sets"] for x in xs), 2)
                        if len(xs) >= 3 and w not in NO_DATA_WEEKS else None)
        series[p] = vals
    summary = {}
    for p in PATHS:
        xs = [x for x in prs if x["path"] == p]
        summary[p] = {"prs": len(xs), "sets": sum(x["sets"] for x in xs),
                      "usd_per_set": round(sum(x["usd"] for x in xs) / sum(x["sets"] for x in xs), 2) if xs else None,
                      "median_pr_per_set": median([x["usd"] / x["sets"] for x in xs])}
    repos = sorted({x["repo"] for x in prs}, key=lambda r: -sum(x["sets"] for x in prs if x["repo"] == r))[:8]
    by_repo = {p: [(lambda xs: round(sum(x["usd"] for x in xs) / sum(x["sets"] for x in xs), 2) if xs else 0)(
        [x for x in prs if x["repo"] == r and x["path"] == p]) for r in repos] for p in PATHS}
    return {"weeks": WEEKS, "series": series, "summary": summary, "repos": repos, "by_repo": by_repo,
            "attributed_share": round(attributed / total, 3) if total else None, "total_usd": round(total),
            "attributed_usd": round(attributed)}


# ---------------------------------------------------------------- Q component-dependencies dependencies

# Each skill name (any era) -> the component it serves, for rolling the skill graph up.
SKILL_COMPONENT = [
    (r"grill|relentless|think-it-through|plan-work|hero-plan|hero-implement|^wayfare$|sync-plan|advance-item|start-goal|"
     r"drop-item|abandon|handoff|reset-branch", "Planning: work items and goals"),
    (r"one-shot|run-task|build-task|push-pr|hero-push|commit|test-changes|hero-test|create-branch|hero-branch|check-ci|"
     r"hero-cicd|hero-health|smoke-ui|pr-create", "Build pipeline"),
    (r"review-pr|pr-review|self-review|respond|ship-pr|auto-approve", "Review and auto-approve"),
    (r"arch", "Architecture record"),
    (r"secure|scan-vulns|harden|audit-security", "Security audit"),
    (r"recomponentize|design", "Design system"),
    (r"compliance", "Compliance register"),
    (r"fleet", "Fleet and messages"),
    (r".", "Skills platform and config"),
]
ARTIFACTS = [("HERO.md", r"HERO\.md", "Skills platform and config"),
             (".plans", r"\.plans/|plan-work/|my-work/", "Planning: work items and goals"),
             ("DESIGN.md", r"DESIGN\.md|ARCHITECTURE\.md", "Architecture record"),
             ("Compliance register", r"CONSISTENCY\.md|CONTROLS\.yaml|CHECKS\.yaml|compliance register", "Compliance register"),
             ("FLEET.md", r"FLEET\.md", "Fleet and messages"),
             ("Mailbox", r"mailbox|\.plans/messages|MESSAGES\.md", "Fleet and messages"),
             ("Auto-approve workflow", r"auto-approve\.ya?ml", "Review and auto-approve"),
             ("AGENTS.md", r"AGENTS\.md", "Skills platform and config")]
TOP_REFS = {"init.md": "Skills platform and config", "configuration.md": "Skills platform and config",
            "loading.md": "Skills platform and config", "scaffold.md": "Skills platform and config",
            "improve.md": "Compliance register"}


def component_of_skill(name):
    for pat, comp in SKILL_COMPONENT:
        if re.search(pat, name):
            return comp


def graph_at(sha):
    """Skill -> skill and skill -> artifact edges in the plugin at one commit."""
    listing = git("ls-tree", "-r", "--name-only", sha).splitlines()
    skills = sorted({p.split("/")[1] for p in listing if re.match(r"skills/[^/]+/SKILL\.md$", p)})
    docs = defaultdict(str)
    for p in listing:
        if not p.endswith(".md"):
            continue
        m = re.match(r"skills/([^/]+)/", p)
        owner = m.group(1) if m else None
        if not owner and p.startswith("references/"):
            owner = "@" + TOP_REFS.get(os.path.basename(p), "Planning: work items and goals")
        if owner:
            docs[owner] += git("show", f"{sha}:{p}")
    edges = set()
    for owner, text in docs.items():
        src = owner[1:] if owner.startswith("@") else component_of_skill(owner)
        for s in skills:
            if s == owner:
                continue
            if re.search(r"(?<![\w-])(?:[\w-]+:)?/?" + re.escape(s) + r"(?![\w-])", text):
                edges.add(("skill", owner, s, src, component_of_skill(s)))
        for art, pat, comp in ARTIFACTS:
            if re.search(pat, text):
                edges.add(("artifact", owner, art, src, comp))
    return skills, edges


def q_component_dependencies_dependencies(con):
    shas = {}
    for line in git("log", "--format=%h %ad", "--date=short", "main").splitlines():
        sha, day = line.split()
        shas.setdefault(day[:7], sha)  # newest commit of each month
    months = [m for m in MONTHS if m in shas]
    per_month = {}
    for m in months:
        skills, edges = graph_at(shas[m])
        ss = [e for e in edges if e[0] == "skill"]
        comp_edges = {(e[3], e[4]) for e in edges if e[3] != e[4]}
        per_month[m] = {"skills": len(skills), "skill_edges": len(ss), "artifact_edges": len(edges) - len(ss),
                        "per_skill": round(len(ss) / len(skills), 2) if skills else None,
                        "component_edges": len(comp_edges)}
    skills, edges = graph_at("HEAD")
    comps = sorted({component_of_skill(s) for s in skills} | {a[2] for a in ARTIFACTS})
    out_deg, in_deg = Counter(), Counter()
    pairs = Counter()
    for e in edges:
        if e[3] != e[4]:
            pairs[(e[3], e[4])] += 1
    for (a, b) in pairs:
        out_deg[a] += 1
        in_deg[b] += 1
    series = {"Skills": [per_month.get(m, {}).get("skills") for m in MONTHS],
              "Skill → skill references": [per_month.get(m, {}).get("skill_edges") for m in MONTHS],
              "Component → component links": [per_month.get(m, {}).get("component_edges") for m in MONTHS]}
    used_by = defaultdict(set)
    for (a, b) in pairs:
        used_by[b].add(a)
    return {"months": MONTHS, "series": series, "per_month": per_month, "components": comps,
            "in_deg": dict(in_deg), "out_deg": dict(out_deg), "pairs": {f"{a} -> {b}": n for (a, b), n in pairs.items()},
            "used_by": {k: sorted(v) for k, v in used_by.items()}, "n_skills": len(skills)}


# ---------------------------------------------------------------- Q skipped-components out of order

# (later, earlier, whether the later one's skills reference the earlier one's component in Q component-dependencies)
OOO_RULES = [("items", "skills", True), ("goals", "items", True), ("goals", "arch", True), ("messages", "goals", True),
             ("goals", "compliance", False), ("goals", "dshook", False), ("items", "agents", False),
             ("arch", "items", False)]


def q_skipped_components_out_of_order(con):
    """Active repo-weeks where a later component was in use without an earlier one, and how those weeks went."""
    ad, ra = adoption(con), repo_adoption(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    per = Counter((f["repo"], f["week"]) for f in cs)
    fu = {(r["repo"], r["number"]): r["followup_within_7d_days"] is not None
          for r in rows(con, "SELECT repo, number, followup_within_7d_days FROM detectors.followups")}
    prw = defaultdict(list)
    for r in rows(con, "SELECT repo, number, SUBSTR(merged_ts,1,10) d FROM github.prs WHERE merged_ts IS NOT NULL "
                       "AND head_ref NOT LIKE 'dependabot/%' AND author_is_bot = 0 AND SUBSTR(merged_ts,1,10) <= ?",
                  (FOLLOWUP_CUTOFF,)):
        if (r["repo"], r["number"]) in fu:
            prw[(r["repo"], week_of(r["d"]))].append(fu[(r["repo"], r["number"])])
    weekly, outcome = {}, {}
    for a, b, dep in OOO_RULES:
        name = f"{COMP[a]['name']} without {COMP[b]['name']}"
        ser = [0] * len(WEEKS)
        oo, io, repos = [], [], set()
        for r in ad:
            da, db_ = ra[r].get(a), ra[r].get(b)
            if not da:
                continue
            for i, w in enumerate(WEEKS):
                end = (monday(w) + timedelta(days=6)).isoformat()
                if monday(w).isoformat() > ad[r]["last"] or end < da or not per.get((r, w)):
                    continue
                row = (per[(r, w)], prw.get((r, w), []))
                if not db_ or db_ > end:
                    ser[i] += 1
                    oo.append(row)
                    repos.add(r)
                else:
                    io.append(row)
        fr = lambda xs: (lambda f: round(sum(f) / len(f), 3) if f else None)([x for _, fl in xs for x in fl])
        weekly[name] = ser
        outcome[name] = {"dependency": dep, "out_weeks": len(oo), "in_weeks": len(io),
                         "out_sets": mean([x for x, _ in oo]), "in_sets": mean([x for x, _ in io]),
                         "out_fu": fr(oo), "in_fu": fr(io), "out_prs": sum(len(f) for _, f in oo),
                         "repos": sorted(repos)}
    return {"weeks": WEEKS, "series": {k: v for k, v in weekly.items() if any(v)}, "outcome": outcome,
            "dep_violations": sum(o["out_weeks"] for o in outcome.values() if o["dependency"]),
            "nondep_weeks": sum(o["out_weeks"] for o in outcome.values() if not o["dependency"])}


# ---------------------------------------------------------------- Q template-vs-plugin-components template vs plugin

CHANNEL_ARTIFACTS = [("hero_md", "HERO.md"), ("pre_commit_config", "pre-commit"), ("github_workflows", "CI workflows"),
                     ("agents_md", "AGENTS.md"), ("claude_md", "CLAUDE.md"), ("design_md", "DESIGN.md"),
                     ("env_example", ".env.example"), ("plans_dir", ".plans/")]


def q_template_vs_plugin_components_channels(con):
    """Per artifact: present in the repo's first commit (a clone or init) or added later."""
    ad = adoption(con)
    pres = defaultdict(dict)
    for r in rows(con, "SELECT repo, snapshot, ts, artifact, present FROM detectors.presence"):
        if r["repo"] in ad:
            pres[(r["repo"], r["artifact"])][r["snapshot"]] = (r["present"], r["ts"])
    # when each artifact first arrived, from git history where it is a single file
    first_file = {}
    for path, art in (("HERO.md", "hero_md"), (".pre-commit-config.yaml", "pre_commit_config"), ("AGENTS.md", "agents_md"),
                      ("CLAUDE.md", "claude_md"), ("DESIGN.md", "design_md"), (".env.example", "env_example")):
        for r in rows(con, "SELECT c.repo, MIN(c.day) d FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo "
                           "AND c.sha=f.sha WHERE f.path=? GROUP BY c.repo", (path,)):
            first_file[(r["repo"], art)] = r["d"]
    cats = ["In the first commit", "Added later", "Never"]
    per_art = {c: [] for c in cats}
    monthly = {c: [0] * len(MONTHS) for c in cats[:2]}
    for art, label in CHANNEL_ARTIFACTS:
        counts = Counter()
        for repo in ad:
            snaps = pres.get((repo, art), {})
            first = snaps.get("first_commit", (0, None))[0]
            head = snaps.get("head", (0, None))[0]
            if first:
                cls = cats[0]
            elif head or any(v[0] for v in snaps.values()):
                cls = cats[1]
            else:
                cls = cats[2]
            counts[cls] += 1
            d = first_file.get((repo, art))
            if cls != cats[2] and d and d[:7] in MONTHS:
                monthly[cls][MONTHS.index(d[:7])] += 1
        for c in cats:
            per_art[c].append(counts[c])
    tmpl = rows(con, "SELECT MIN(day) d FROM git.commits WHERE repo='hero-template'")[0]["d"]
    clones = sorted(r for r in ad if ad[r]["first"] >= tmpl and all(
        pres.get((r, a), {}).get("first_commit", (0,))[0] for a in ("hero_md", "agents_md", "pre_commit_config")))
    return {"arts": [l for _, l in CHANNEL_ARTIFACTS], "per_art": per_art, "months": MONTHS, "monthly": monthly,
            "template_first": tmpl, "clones": clones, "n_repos": len(ad)}


# ---------------------------------------------------------------- Q milestones-vs-releases releases

# Model and Claude Code releases from May, when the fleet was active (harness.model_releases,
# harness.cc_releases); same-week releases are merged into one mark.
def releases(con, since="2026-05-01"):
    rs = rows(con, "SELECT date, name FROM harness.model_releases WHERE date >= ? UNION ALL "
                   "SELECT date, name FROM harness.cc_releases WHERE date >= ? ORDER BY date", (since, since))
    out = []
    for r in rs:
        name = re.sub(r"\s*\(.*?\)", "", r["name"])
        if out and days(out[-1][0], r["date"]) <= 3:
            out[-1] = (out[-1][0], out[-1][1] + " + " + name)
        else:
            out.append((r["date"], name))
    return out


def q_milestones_vs_releases_releases(con, control=None):
    """Change sets per active app-week, with releases; the output change around each release (the calendar)
    against the change around each app's own adoption, net of same-week apps that had not adopted (Q output-after-adoption)."""
    ad = adoption(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["category"] in APPS]
    per = Counter((f["repo"], f["week"]) for f in cs)
    apps = [r for r in ad if ad[r]["category"] in APPS]
    active = lambda r, d: ad[r]["first"] <= d.isoformat() and (d - timedelta(days=6)).isoformat() <= ad[r]["last"]
    weekly = []
    for w in WEEKS:
        act = [r for r in apps if active(r, monday(w) + timedelta(days=6))]
        weekly.append(round(sum(per.get((r, w), 0) for r in act) / len(act), 2) if act else None)

    def window(day, k=4):
        """Mean change sets per app-week in the k weeks before and after, over apps active on both sides."""
        y, w0, _ = date.fromisocalendar(*date.fromisoformat(day).isocalendar()).isocalendar()
        base = date.fromisocalendar(y, w0, 1)
        both = [r for r in apps if active(r, base - timedelta(weeks=k)) and active(r, base + timedelta(weeks=k))]
        pre, post = [], []
        for r in both:
            for rel in range(-k, k + 1):
                if rel:
                    d = base + timedelta(weeks=rel)
                    y2, w2, _ = d.isocalendar()
                    (pre if rel < 0 else post).append(per.get((r, f"{y2}-W{w2:02d}"), 0))
        return mean(pre), mean(post), len(both)
    rel_rows = []
    for d, name in releases(con):
        if d > "2026-08-27":
            continue
        a, b, n = window(d)
        if n >= 2:
            rel_rows.append({"what": name, "day": d, "pre": a, "post": b, "change": round(b - a, 2), "n": n})
    from links import MILESTONES
    rel = releases(con)
    near = []
    for d, name, _ in MILESTONES:
        close = [(r[1], days(d, r[0])) for r in rel if abs(days(d, r[0])) <= 10]
        near.append({"milestone": name, "day": d, "releases_within_10d": close})
    adopt_rows = []
    for name, (pre, post, npre, npost) in (control or {}).items():
        if pre is not None and post is not None:
            adopt_rows.append({"what": name, "pre": pre, "post": post, "change": round(post - pre, 2),
                               "n_pre": npre, "n_post": npost})
    return {"weeks": WEEKS, "weekly": weekly, "releases": rel, "release_rows": rel_rows, "adopt_rows": adopt_rows,
            "near": near, "n_near": sum(1 for x in near if x["releases_within_10d"])}


# ---------------------------------------------------------------- Q recommended-adoption-order a proposed order

def q_recommended_adoption_order_order(con, parts):
    """One row per component, from the answers above, and an adoption order derived from them."""
    d1, d3, d6, d7, d8, d10 = (parts[k] for k in ("q_component_inventory", "q_adoption_lag", "q_output_after_adoption", "q_fixes_after_adoption", "q_owner_share_after_adoption", "q_component_dependencies"))
    rows_ = []
    comp_map = {"skills": "Skills platform and config", "autoapprove": "Review and auto-approve",
                "review": "Review and auto-approve", "pipeline": "Build pipeline",
                "items": "Planning: work items and goals", "goals": "Planning: work items and goals",
                "arch": "Architecture record", "compliance": "Compliance register", "dshook": "Design system",
                "fleet": "Fleet and messages", "messages": "Fleet and messages"}
    for l in d1["lanes"]:
        k = l["key"]
        name = l["name"]
        pp = d6["pre_post"].get(name)
        fp = d7["pre_post"].get(name)
        op = d8["pre_post"].get(name)
        dep = comp_map.get(k)
        rows_.append({"key": k, "name": name, "shipped": l["start"], "retired": l["retired"], "in_use": l["in_use"],
                      "median_lag": d3["lags"].get(k, {}).get("median"),
                      "output": pp, "followups": fp, "owner": op,
                      "used_by": len(d10["used_by"].get(dep, [])) if dep else None})
    return rows_


def all_data():
    con = connect()
    out = {"q_component_inventory": q_component_inventory_components(con), "q_adoption_order": q_adoption_order_order(con), "q_adoption_lag": q_adoption_lag_lag(con),
           "q_retired_components": q_retired_components_retired(), "q_component_traffic": q_component_traffic_reach(con), "q_output_after_adoption": q_output_after_adoption_output(con),
           "q_fixes_after_adoption": q_fixes_after_adoption_followups(con), "q_owner_share_after_adoption": q_owner_share_after_adoption_owner(con), "q_cost_by_architecture_depth": q_cost_by_architecture_depth_spend(con),
           "q_component_dependencies": q_component_dependencies_dependencies(con), "q_skipped_components": q_skipped_components_out_of_order(con), "q_template_vs_plugin_components": q_template_vs_plugin_components_channels(con),
           }
    out["q_milestones_vs_releases"] = q_milestones_vs_releases_releases(con, out["q_output_after_adoption"]["control"])
    out["q_recommended_adoption_order"] = q_recommended_adoption_order_order(con, out)
    out["releases"] = releases(con)
    return out


if __name__ == "__main__":
    import pprint
    d = all_data()
    for k, v in d.items():
        if k in ("q_retired_components",):
            v = {kk: vv for kk, vv in v.items() if kk != "names"}
        print("=" * 20, k)
        pprint.pprint(v, width=160, compact=True)
