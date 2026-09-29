# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


"""Deployment series: deployment and infrastructure.

One function per question (q_platform_history … q_infra_built_like_apps), each returning what its answer slide and its
breakdown slide plot. Weeks run 1 Jan 2026 to now (evolution.WEEKS); every CI series
starts at the repo's first ingested run, because github.ci_runs holds only the 1,000
most recent runs per repo.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/deployment/data.py
"""
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from record import adoption, rows, stage_of, week_of  # noqa: E402
from evolution import MONTHS, WEEKS  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, category_of  # noqa: E402

MIRRORS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", ".analysis", "data", "mirrors")
INFRA = ("infrastructure-root", "infrastructure-environments")
HEALTH = "Health Check - App (Production)"
# Runs that are the approval gate or a review bot, not a check of the code: Auto Approve fails and
# then passes on the same SHA by design (it waits for the other checks and is re-triggered by comment).
GATES = {"Auto Approve", ".github/workflows/auto-approve.yaml", "Claude PR Approve",
         "Running Copilot Code Review", "Copilot code review"}
DEPLOYS = {"deploy (auth)": "auth", "deploy (design)": "design-system", "deploy (commons)": "elevate-commons",
           "deploy (beta)": "website", "deploy to astrum (beta)": "website", "deploy (website)": "website"}
DEPLOYED_APPS = ["auth", "design-system", "elevate-commons", "website"]

# The infrastructure-environments app file each fleet repo is provisioned by.
APP_KEYS = {"auth": "auth", "design-system": "design", "website": "website", "hiro": "hiro",
            "aihero-wayfare": "wayfare", "elevate-commons": "commons", "ah-cozy": "cozy",
            "aihero-dokyu": "dokyu", "aihero-mehr": "mehr", "aihero-steadfast": "contextful|steadfast"}
PLATFORM_EVENTS = [
    ("2026-05-25", "DigitalOcean per-app module"),
    ("2026-07-04", "HCP Terraform + CF tunnels"),
    ("2026-08-21", "EKS retired; deploy-swarm"),
]
DEPLOY_EVENTS = [
    ("2026-08-21", "Shared deploy-swarm (#111)"),
    ("2026-08-22", "deploy-swarm fixes (#113–115)"),
    ("2026-09-23", "Rollback prints logs (#143)"),
]
HEALTH_EVENTS = [
    ("2026-08-20", "EKS half retired (#109)"),
    ("2026-08-26", "Asserts /readyz (#116)"),
    ("2026-09-17", "Hourly → every 6 h (#134)"),
]
# No Claude Code sessions are logged 10–24 Aug (the owner confirmed the gap): a session match there is
# "data not available", never "no session".
SESSION_GAP = ("2026-08-10", "2026-08-24")
CI_GATE_EVENTS = [("2026-08-29", "Auto-approve reads CI (#65)")]
AA_EVENTS = [
    ("2026-08-29", "Scripted gates (#65)"),
    ("2026-09-18", "Revert to 579584f (#102)"),
    ("2026-09-22", "Rename to wayfare (#106, #108)"),
]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def hours(a, b):
    return (ts(b) - ts(a)).total_seconds() / 3600


def median(v):
    return round(statistics.median(v), 1) if v else None


def in_scope(repo):
    return repo not in OUT_OF_SCOPE and category_of(repo) != "out of scope"


def git(repo, *args):
    path = os.path.join(MIRRORS, f"{repo}.git")
    p = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout


@lru_cache(maxsize=None)
def ci_start(con):
    """First ingested run per repo, and whether the repo hit the 1,000-run cap."""
    return {r["repo"]: {"first": r["first"][:10], "n": r["n"], "capped": r["n"] >= 1000}
            for r in rows(con, "SELECT repo, MIN(created_ts) first, COUNT(*) n FROM github.ci_runs GROUP BY repo")}


def weekly_list(items, key=lambda x: x["week"]):
    by = defaultdict(list)
    for i in items:
        by[key(i)].append(i)
    return by


# ---------------------------------------------------------------- Q platform-history platform evolution

def area_of(repo, month, paths):
    c = Counter()
    for p in paths:
        top = p.split("/")[0]
        if top in ("aws", "azure", "gcp", "legacy", "infra", "platform", "environments") or (
                top == "modules" and month < "2026-05"):
            c["AWS / EKS"] += 1
        elif top in ("digitalocean", "astrum", "ansible", "customers", "modules", "templates", "cloudflare"):
            c["DigitalOcean + Cloudflare"] += 1
        elif top == "tfe":
            c["HCP Terraform"] += 1
        else:
            c["CI, docs, gates"] += 1
    return c.most_common(1)[0][0] if c else "CI, docs, gates"


@lru_cache(maxsize=None)
def infra_prs(con):
    """Merged PRs in the two infrastructure repos, with area, author kind and files."""
    files, trailer = defaultdict(list), defaultdict(int)
    for r in rows(con, "SELECT repo, pr_number, files_json, claude_trailer FROM pr_commits.pr_commits "
                       "WHERE repo IN (?, ?) AND is_merge = 0", INFRA):
        for f in json.loads(r["files_json"] or "[]"):
            files[(r["repo"], r["pr_number"])].append(f["path"] if isinstance(f, dict) else f)
        trailer[(r["repo"], r["pr_number"])] += r["claude_trailer"] or 0
    out = []
    for p in rows(con, "SELECT repo, number, title, author, author_is_bot, merged_ts FROM github.prs "
                       "WHERE repo IN (?, ?) AND merged_ts IS NOT NULL", INFRA):
        day = p["merged_ts"][:10]
        k = (p["repo"], p["number"])
        if p["author_is_bot"] or "dependabot" in (p["author"] or ""):
            who = "Dependabot"
        elif p["author"] != "rparundekar":
            who = "Second engineer"
        elif trailer[k]:
            who = "Agent (owner's sessions)"
        else:
            who = "Owner, by hand"
        out.append({"repo": p["repo"], "pr": p["number"], "title": p["title"], "day": day, "week": week_of(day),
                    "month": day[:7], "who": who, "paths": files[k],
                    "area": "Dependabot" if who == "Dependabot" else area_of(p["repo"], day[:7], files[k])})
    return out


def q_platform_history_platform(con):
    prs = infra_prs(con)
    areas = ["AWS / EKS", "DigitalOcean + Cloudflare", "HCP Terraform", "CI, docs, gates", "Dependabot"]
    by = defaultdict(Counter)
    for p in prs:
        by[p["area"]][p["week"]] += 1
    series = {a: [by[a].get(w, 0) for w in WEEKS] for a in areas}
    months = {a: Counter(p["month"] for p in prs if p["area"] == a) for a in areas}
    pre = sum(1 for p in prs if p["day"] < "2026-01-01")
    last_aws = max(p["day"] for p in prs if p["area"] == "AWS / EKS")
    first_do = min(p["day"] for p in prs if p["area"] == "DigitalOcean + Cloudflare")
    era = lambda lo, hi: Counter(p["area"] for p in prs if lo <= p["day"] < hi and p["area"] != "Dependabot")
    return {"weeks": WEEKS, "series": series, "n": len(prs), "pre_2026": pre, "months": months,
            "last_aws": last_aws, "first_do": first_do,
            "eras": {"Jan–May": era("2026-01-01", "2026-05-25"), "25 May–4 Jul": era("2026-05-25", "2026-07-04"),
                     "4 Jul–21 Aug": era("2026-07-04", "2026-08-21"), "21 Aug–now": era("2026-08-21", "2027-01-01")},
            "by_repo": Counter(p["repo"] for p in prs)}


# ---------------------------------------------------------------- Q app-to-infra-time first commit to infrastructure

def app_onboarding(con):
    """Per fleet app: first commit, the infrastructure-environments PR that provisioned it, what it holds."""
    prs = infra_prs(con)
    first = {r["repo"]: r["d"] for r in rows(con, "SELECT repo, MIN(day) d FROM git.commits GROUP BY repo")}
    out = []
    for repo, key in APP_KEYS.items():
        pat = re.compile(rf"customers/[^/]+/[^/]+/app_({key})\.tf$")
        hits = sorted((p for p in prs if p["repo"] == "infrastructure-environments"
                       and any(pat.search(f) for f in p["paths"])), key=lambda p: p["day"])
        onboard = hits[0] if hits else None
        first_mirror = git(repo, "log", "--reverse", "--format=%cs", "HEAD").split("\n")[0] or first.get(repo)
        path = f"{os.path.expanduser(os.environ.get('WAYFARE_FLEET_ROOT', '~/workspaces/aihero'))}/infrastructure-environments/customers"
        tf = ""
        for root, _, fs in os.walk(path):
            for f in fs:
                if re.fullmatch(rf"app_({key})\.tf", f):
                    tf = open(os.path.join(root, f)).read()
        out.append({
            "repo": repo, "first_commit": first_mirror, "onboard_day": onboard["day"] if onboard else None,
            "onboard_pr": onboard["pr"] if onboard else None, "onboard_title": onboard["title"] if onboard else None,
            "onboard_who": onboard["who"] if onboard else None,
            "repo_by_terraform": "modules/github/repository" in tf, "hosting": "modules/digitalocean/droplet" in tf,
            "sentry": "modules/sentry/app" in tf,
            "days": (date.fromisoformat(onboard["day"]) - date.fromisoformat(first_mirror)).days if onboard else None,
        })
    return sorted(out, key=lambda a: a["onboard_day"] or "9999")


def q_app_to_infra_time_onboarding(con):
    apps = app_onboarding(con)
    return {"apps": apps, "same_day": [a["repo"] for a in apps if a["days"] is not None and a["days"] <= 0],
            "by_terraform": [a["repo"] for a in apps if a["repo_by_terraform"]]}


# ---------------------------------------------------------------- Q deploy-on-merge which apps deploy

@lru_cache(maxsize=None)
def deploy_runs(con):
    out = []
    for r in rows(con, "SELECT repo, run_id, workflow_name, event, head_sha, conclusion, created_ts, updated_ts "
                       "FROM github.ci_runs WHERE head_branch = 'main'"):
        if DEPLOYS.get(r["workflow_name"]) == r["repo"]:
            out.append({**r, "day": r["created_ts"][:10], "week": week_of(r["created_ts"]),
                        "month": r["created_ts"][:7]})
    return sorted(out, key=lambda r: r["created_ts"])


def deploy_workflow_added(repo):
    """First commit on main that added a deploy workflow (the mirror, not ci_runs, so the cap doesn't hide it)."""
    out = git(repo, "log", "--first-parent", "--diff-filter=A", "--reverse", "--format=%cs", "HEAD", "--",
              ".github/workflows/deploy.yaml", ".github/workflows/deploy.yml", ".github/workflows/deploy-beta.yaml",
              ".github/workflows/deploy-beta.yml", ".github/workflows/deploy-astrum.yml")
    return out.split("\n")[0] or None


@lru_cache(maxsize=None)
def merged_prs(con):
    return rows(con, "SELECT p.repo, p.number, p.merged_ts, p.author_is_bot, p.author, p.head_ref, p.created_ts, "
                     "c.sha FROM github.prs p LEFT JOIN git.commits c ON c.repo = p.repo AND c.pr_number = p.number "
                     "WHERE p.merged_ts IS NOT NULL")


def q_deploy_on_merge_deploying(con):
    runs = [r for r in deploy_runs(con) if r["conclusion"] == "success"]
    by = defaultdict(Counter)
    for r in runs:
        by[r["repo"]][r["week"]] += 1
    series = {a: [by[a].get(w, 0) for w in WEEKS] for a in DEPLOYED_APPS}
    apps = app_onboarding(con)
    status = {}
    for a in apps:
        added = deploy_workflow_added(a["repo"])
        status[a["repo"]] = ("deploys on merge" if added else "hosted, never deployed" if a["hosting"]
                             else "repo + error tracking only")
        a["deploy_added"] = added
    # Merged PRs since each app was provisioned: shipped to a running app, or not.
    shipped, not_shipped = Counter(), Counter()
    for p in merged_prs(con):
        a = next((x for x in apps if x["repo"] == p["repo"]), None)
        if not a or not a["onboard_day"] or p["merged_ts"][:10] < a["onboard_day"]:
            continue
        if status[p["repo"]] == "deploys on merge" and p["merged_ts"][:10] >= (a["deploy_added"] or "9999"):
            shipped[p["repo"]] += 1
        else:
            not_shipped[p["repo"]] += 1
    order = sorted(status, key=lambda r: -(shipped[r] + not_shipped[r]))
    return {"weeks": WEEKS, "series": series, "status": status, "apps": apps, "order": order,
            "shipped": shipped, "not_shipped": not_shipped, "ci_start": {a: ci_start(con)[a]["first"] for a in DEPLOYED_APPS},
            "n_success": len(runs)}


# ---------------------------------------------------------------- Q merge-to-production merge to production

def q_merge_to_production_lag(con):
    runs = deploy_runs(con)
    ok = defaultdict(list)
    for r in runs:
        if r["conclusion"] == "success":
            ok[(r["repo"], r["head_sha"])].append(r)
    # A merge counts only once its repo's deploy runs are in the data: before the first
    # ingested deploy run the lag is either untracked (the 1,000-run cap) or there was no deploy yet.
    starts = {a: min(r["created_ts"] for r in runs if r["repo"] == a) for a in DEPLOYED_APPS}
    facts = []
    for p in merged_prs(con):
        if p["repo"] not in DEPLOYED_APPS or not p["sha"] or p["merged_ts"] < starts[p["repo"]]:
            continue
        own = ok.get((p["repo"], p["sha"]))
        later = [r for r in runs if r["repo"] == p["repo"] and r["conclusion"] == "success"
                 and r["created_ts"] >= p["merged_ts"]]
        if own:
            done = min(r["updated_ts"] for r in own)
            kind = "own deploy"
        elif later:
            done = later[0]["updated_ts"]
            kind = "carried by a later deploy"
        else:
            done, kind = None, "not deployed yet"
        day = p["merged_ts"][:10]
        facts.append({"repo": p["repo"], "pr": p["number"], "day": day, "week": week_of(day), "month": day[:7],
                      "kind": kind, "minutes": round(hours(p["merged_ts"], done) * 60, 1) if done else None})
    lagged = [f for f in facts if f["minutes"] is not None]
    wk = weekly_list(lagged)
    series = {"Median minutes, merge → deployed": [median([f["minutes"] for f in wk[w]]) if wk.get(w) else None
                                                    for w in WEEKS]}
    by_repo = {}
    for a in DEPLOYED_APPS:
        m = defaultdict(list)
        for f in lagged:
            if f["repo"] == a:
                m[f["month"]].append(f["minutes"])
        by_repo[a] = [median(m[x]) if m.get(x) else None for x in MONTHS]
    ok_runs = [r for r in runs if r["conclusion"] == "success"]
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo, "facts": facts,
            "manual": (sum(r["event"] == "workflow_dispatch" for r in ok_runs), len(ok_runs)),
            "median": median([f["minutes"] for f in lagged]),
            "median_own": median([f["minutes"] for f in lagged if f["kind"] == "own deploy"]),
            "kinds": Counter(f["kind"] for f in facts),
            "per_app": {a: median([f["minutes"] for f in lagged if f["repo"] == a]) for a in DEPLOYED_APPS},
            "p90": round(sorted(f["minutes"] for f in lagged)[int(0.9 * len(lagged))], 1) if lagged else None}


# ---------------------------------------------------------------- Q deploy-failures deploy failures

def q_deploy_failures_failures(con):
    runs = [r for r in deploy_runs(con) if r["conclusion"] in ("success", "failure")]
    infra_fix = [p for p in infra_prs(con) if p["repo"] == "infrastructure-environments"
                 and any("deploy-swarm" in f for f in p["paths"])]
    fails = []
    for i, r in enumerate(runs):
        if r["conclusion"] != "failure":
            continue
        nxt = next((x for x in runs[i + 1:] if x["repo"] == r["repo"] and x["conclusion"] == "success"), None)
        if not nxt:
            how = "not green yet"
        elif any(r["created_ts"][:10] <= p["day"] <= nxt["created_ts"][:10] for p in infra_fix):
            how = "shared deploy workflow fixed"
        elif nxt["head_sha"] == r["head_sha"]:
            how = "re-run, same commit"
        else:
            how = "a later app commit"
        fails.append({**r, "how": how, "hours": round(hours(r["created_ts"], nxt["created_ts"]), 1) if nxt else None})
    wk = weekly_list(runs)
    share = [round(sum(r["conclusion"] == "failure" for r in wk[w]) / len(wk[w]), 3) if wk.get(w) else None
             for w in WEEKS]
    per_app = {a: (sum(1 for r in runs if r["repo"] == a and r["conclusion"] == "failure"),
                   sum(1 for r in runs if r["repo"] == a)) for a in DEPLOYED_APPS}
    reverts = rows(con, "SELECT repo, day, subject FROM git.commits WHERE is_revert = 1 AND repo IN (%s)"
                   % ",".join("?" * len(DEPLOYED_APPS)), DEPLOYED_APPS)
    return {"weeks": WEEKS, "series": {"Failed share of deploys": share}, "fails": fails,
            "how": Counter(f["how"] for f in fails), "per_app": per_app, "n": len(runs),
            "n_fail": len(fails), "reverts": reverts,
            "infra_fix": [(p["day"], p["pr"], p["title"]) for p in infra_fix],
            "median_hours": median([f["hours"] for f in fails if f["hours"] is not None])}



# ---------------------------------------------------------------- Q deploy-failures, per deployment

DEPLOY_WF = (".github/workflows/deploy.yaml", ".github/workflows/deploy.yml", ".github/workflows/deploy-beta.yaml",
             ".github/workflows/deploy-beta.yml", ".github/workflows/deploy-astrum.yml")
FIXES = ["Retry of the same commit", "App's deploy workflow fixed", "Shared deploy workflow fixed",
         "Later app commit (fix forward)", "Rollback (revert)", "Unresolved"]


@lru_cache(maxsize=None)
def deploy_workflow_commits(repo):
    """[(iso ts, sha)] of default-branch commits that changed the app's own deploy workflow."""
    out = git(repo, "log", "--first-parent", "--format=%cI %H", "HEAD", "--", *DEPLOY_WF)
    # git prints the committer's own offset; ci_runs is UTC, so compare in UTC or a same-day fix sorts wrong
    return [(datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat(), sha)
            for ts, sha in (l.split() for l in out.splitlines() if l.strip())]


def q_deploy_failures_recovery(con):
    """Deployments (one per commit on main), their attempts, what cleared each failure and how long it took."""
    runs = [r for r in deploy_runs(con) if r["conclusion"] in ("success", "failure", "startup_failure", "cancelled")]
    by_sha = defaultdict(list)
    for r in runs:
        by_sha[(r["repo"], r["head_sha"])].append(r)
    infra_fix = [p for p in infra_prs(con) if p["repo"] == "infrastructure-environments"
                 and any("deploy-swarm" in f for f in p["paths"])]
    reverts = rows(con, "SELECT repo, day, sha, subject FROM git.commits WHERE is_revert = 1")
    deployments = []
    for (repo, sha), atts in by_sha.items():
        atts.sort(key=lambda r: r["created_ts"])
        concl = [a["conclusion"] for a in atts]
        failed = [a for a in atts if a["conclusion"] in ("failure", "startup_failure")]
        tried = [a for a in atts if a["conclusion"] != "cancelled"]
        # a deployment failed when its first real attempt did; a re-run that fails after the commit already
        # shipped is a repeat attempt, not a failed deployment
        if not tried:
            outcome = "Cancelled only"
        elif tried[0]["conclusion"] == "success":
            outcome = "Succeeded" + (", a later re-run failed" if failed else "")
        elif atts[-1]["conclusion"] == "success":
            outcome = "Failed, then succeeded on retry"
        else:
            outcome = "Failed"
        deployments.append(dict(repo=repo, sha=sha, first=atts[0]["created_ts"], attempts=len(atts),
                                failed_attempts=len(failed), failed=bool(tried) and tried[0]["conclusion"] != "success",
                                repeat_failures=sum(1 for a in failed if a is not tried[0]),
                                outcome=outcome, week=atts[0]["week"], month=atts[0]["month"], event=atts[0]["event"]))
    deployments.sort(key=lambda d: d["first"])
    # what cleared each failed deployment: the app's next successful deploy run and what landed in between
    succ = [r for r in runs if r["conclusion"] == "success"]
    for d in deployments:
        if not d["failed"]:
            d["fix"], d["hours"] = None, None
            continue
        t0 = next(a["created_ts"] for a in by_sha[(d["repo"], d["sha"])] if a["conclusion"] in ("failure", "startup_failure"))
        nxt = next((r for r in succ if r["repo"] == d["repo"] and r["created_ts"] > t0), None)
        if nxt is None:
            d["fix"], d["hours"] = FIXES[5], None
            continue
        t1 = nxt["created_ts"]
        d["hours"] = round(hours(t0, t1), 1)
        if any(r["repo"] == d["repo"] and t0[:10] <= r["day"] <= t1[:10] for r in reverts):
            d["fix"] = FIXES[4]
        elif nxt["head_sha"] == d["sha"]:
            d["fix"] = FIXES[0]
        elif any(t0 <= ts <= t1 for ts, _sha in deploy_workflow_commits(d["repo"])):
            d["fix"] = FIXES[1]
        elif any(t0[:10] <= p["day"] <= t1[:10] for p in infra_fix):
            d["fix"] = FIXES[2]
        else:
            d["fix"] = FIXES[3]
    # episodes: consecutive failed deployments of one app until it is green again
    episodes = []
    for repo in DEPLOYED_APPS:
        cur = None
        for d in [x for x in deployments if x["repo"] == repo and x["outcome"] != "Cancelled only"]:
            if d["failed"]:
                if cur is None:
                    cur = dict(repo=repo, start=d["first"], n=0, hours=d["hours"], fix=d["fix"])
                cur["n"] += 1
            elif cur:
                episodes.append(cur)
                cur = None
        if cur:
            episodes.append(cur)
    per_app = {}
    for a in DEPLOYED_APPS:
        ds = [d for d in deployments if d["repo"] == a and d["outcome"] != "Cancelled only"]
        k = sum(1 for d in ds if d["failed"])
        att = [r for r in runs if r["repo"] == a and r["conclusion"] != "cancelled"]
        per_app[a] = dict(deployments=len(ds), failed=k, attempts=len(att),
                          failed_attempts=sum(1 for r in att if r["conclusion"] != "success"),
                          repeat_failures=sum(d["repeat_failures"] for d in ds),
                          hours=sorted(d["hours"] for d in ds if d["hours"] is not None),
                          fixes=Counter(d["fix"] for d in ds if d["fix"]),
                          by_month=Counter(d["month"] for d in ds if d["failed"]),
                          cancelled=sum(1 for d in deployments if d["repo"] == a and d["outcome"] == "Cancelled only"))
    failed = [d for d in deployments if d["failed"]]
    live = [d for d in deployments if d["outcome"] != "Cancelled only"]
    wk = weekly_list([r for r in runs if r["conclusion"] != "cancelled"])
    share = [round(sum(r["conclusion"] != "success" for r in wk[w]) / len(wk[w]), 3) if wk.get(w) else None for w in WEEKS]
    return {"weeks": WEEKS, "series": {"Failed share of deploy attempts": share}, "deployments": deployments,
            "episodes": episodes, "per_app": per_app, "fixes": FIXES,
            "n_deployments": len(live), "n_failed": len(failed), "n_attempts": sum(1 for r in runs if r["conclusion"] != "cancelled"),
            "n_failed_attempts": sum(1 for r in runs if r["conclusion"] in ("failure", "startup_failure")),
            "n_repeat": sum(d["repeat_failures"] for d in deployments), "n_cancelled": sum(1 for d in deployments if d["outcome"] == "Cancelled only"),
            "how": Counter(d["fix"] for d in failed), "hours": sorted(d["hours"] for d in failed if d["hours"] is not None),
            "median_hours": median([d["hours"] for d in failed if d["hours"] is not None]),
            "episode_hours": sorted(e["hours"] for e in episodes if e["hours"] is not None),
            "reverts": [r for r in reverts if r["repo"] in DEPLOYED_APPS],
            "infra_fix": [(p["day"], p["pr"], p["title"]) for p in infra_fix]}

# ---------------------------------------------------------------- Q production-uptime production health

def q_production_uptime_health(con):
    runs = rows(con, "SELECT created_ts, conclusion FROM github.ci_runs WHERE repo = 'infrastructure-environments' "
                     "AND workflow_name = ? AND conclusion IN ('success', 'failure') ORDER BY created_ts", (HEALTH,))
    for r in runs:
        r["week"] = week_of(r["created_ts"])
    wk = weekly_list(runs)
    fails = [r for r in runs if r["conclusion"] == "failure"]
    deploys = [r for r in deploy_runs(con)]
    near = []
    for f in fails:
        before = [d for d in deploys if 0 <= hours(d["created_ts"], f["created_ts"]) <= 6]
        near.append(bool(before))
    # Baseline: how often any check (pass or fail) had a deploy in the 6 hours before it.
    base = [any(0 <= hours(dd["created_ts"], r["created_ts"]) <= 6 for dd in deploys) for r in runs
            if r["created_ts"][:10] <= fails[-1]["created_ts"][:10]]
    # Consecutive failing checks are one outage.
    outages, prev = [], None
    for r in runs:
        if r["conclusion"] == "failure" and (prev is None or prev["conclusion"] != "failure"):
            outages.append({"start": r["created_ts"], "checks": 0})
        if r["conclusion"] == "failure":
            outages[-1]["checks"] += 1
            outages[-1]["end"] = r["created_ts"]
        prev = r
    return {"weeks": WEEKS,
            "series": {"Passed": [sum(r["conclusion"] == "success" for r in wk.get(w, [])) for w in WEEKS],
                       "Failed": [sum(r["conclusion"] == "failure" for r in wk.get(w, [])) for w in WEEKS]},
            "n": len(runs), "n_fail": len(fails), "first": runs[0]["created_ts"][:10] if runs else None,
            "after_deploy": sum(near), "outages": outages, "base": round(sum(base) / len(base), 3)}


# ---------------------------------------------------------------- Q ci-red-rate / Q ci-red-to-green PR checks

@lru_cache(maxsize=None)
def pr_checks(con):
    """PR-check runs (pull_request event, not a gate or bot) joined to their PR by branch and time."""
    runs = rows(con, "SELECT repo, workflow_name, head_branch, head_sha, conclusion, created_ts, updated_ts "
                     "FROM github.ci_runs WHERE event = 'pull_request' AND conclusion IN ('success', 'failure') "
                     "ORDER BY created_ts")
    by_branch = defaultdict(list)
    for r in runs:
        if r["workflow_name"] not in GATES:
            by_branch[(r["repo"], r["head_branch"])].append(r)
    prs = rows(con, "SELECT repo, number, head_ref, created_ts, merged_ts, closed_ts, author_is_bot, author "
                    "FROM github.prs WHERE created_ts IS NOT NULL")
    starts = ci_start(con)
    out = []
    for p in prs:
        if not in_scope(p["repo"]) or p["repo"] not in starts or p["created_ts"][:10] < starts[p["repo"]]["first"]:
            continue
        end = p["merged_ts"] or p["closed_ts"] or "9999"
        rs = [r for r in by_branch.get((p["repo"], p["head_ref"]), []) if p["created_ts"] <= r["created_ts"] <= end]
        if not rs:
            continue
        out.append({**p, "runs": rs, "bot": bool(p["author_is_bot"]) or "dependabot" in (p["author"] or ""),
                    "red": any(r["conclusion"] == "failure" for r in rs)})
    return out


def q_ci_red_rate_red(con):
    prs = [p for p in pr_checks(con) if p["merged_ts"] and not p["bot"]]
    for p in prs:
        p["day"] = p["merged_ts"][:10]
        p["week"], p["month"] = week_of(p["day"]), p["day"][:7]
        p["stage"] = stage_of(con, p["repo"], p["day"]) if p["repo"] in adoption(con) else None
    wk = weekly_list(prs)
    share = [round(sum(p["red"] for p in wk[w]) / len(wk[w]), 3) if len(wk.get(w, [])) >= 5 else None for w in WEEKS]
    by_stage = defaultdict(list)
    for p in prs:
        by_stage[p["stage"]].append(p["red"])
    fails = Counter(r["workflow_name"] for p in prs for r in p["runs"] if r["conclusion"] == "failure")
    repos = sorted({p["repo"] for p in prs}, key=lambda r: -sum(1 for p in prs if p["repo"] == r))[:8]
    by_repo = {}
    for r in repos:
        m = defaultdict(list)
        for p in prs:
            if p["repo"] == r:
                m[p["month"]].append(p["red"])
        by_repo[r] = [round(sum(m[x]) / len(m[x]), 3) if len(m.get(x, [])) >= 5 else None for x in MONTHS]
    before = [p["red"] for p in prs if p["day"] < "2026-08-29"]
    after = [p["red"] for p in prs if p["day"] >= "2026-08-29"]
    return {"weeks": WEEKS, "series": {"Merged PRs whose checks went red": share}, "n": len(prs),
            "red": sum(p["red"] for p in prs), "by_stage": {k: (sum(v), len(v)) for k, v in by_stage.items()},
            "by_repo": by_repo, "top_failing": fails.most_common(8),
            "before": (sum(before), len(before)), "after": (sum(after), len(after))}


def q_ci_red_to_green_green(con):
    sessions = rows(con, "SELECT repo, first_ts, last_ts, git_branches FROM harness.sessions WHERE git_branches IS NOT NULL")
    sess = defaultdict(list)
    for s in sessions:
        try:
            branches = json.loads(s["git_branches"] or "[]")
        except ValueError:
            branches = []
        for b in branches:
            sess[(s["repo"], b)].append(s)
    episodes = []
    for p in pr_checks(con):
        if p["bot"]:
            continue
        by_wf = defaultdict(list)
        for r in p["runs"]:
            by_wf[r["workflow_name"]].append(r)
        for wf, rs in by_wf.items():
            i = 0
            while i < len(rs):
                if rs[i]["conclusion"] != "failure":
                    i += 1
                    continue
                f = rs[i]
                j = next((k for k in range(i + 1, len(rs)) if rs[k]["conclusion"] == "success"), None)
                if j is None:
                    path = "merged without a green run" if p["merged_ts"] else "PR closed, never green"
                    g = None
                else:
                    g = rs[j]
                    path = "re-run, same commit" if g["head_sha"] == f["head_sha"] else "fixed by a new commit"
                who = None
                if path == "fixed by a new commit" and SESSION_GAP[0] <= f["created_ts"][:10] <= SESSION_GAP[1]:
                    who = "session data not available"
                elif path == "fixed by a new commit" and f["created_ts"] >= "2026-08-09":
                    ss = sess.get((p["repo"], p["head_ref"]), [])
                    fix_t = g["created_ts"]
                    if any(s["first_ts"] <= f["updated_ts"] and s["last_ts"] >= fix_t for s in ss):
                        who = "same session"
                    elif any(s["first_ts"] <= fix_t <= s["last_ts"] or s["first_ts"] > f["updated_ts"] for s in ss):
                        who = "a later session"
                    else:
                        who = "no session on the branch"
                day = f["created_ts"][:10]
                episodes.append({"repo": p["repo"], "pr": p["number"], "workflow": wf, "path": path, "who": who,
                                 "day": day, "week": week_of(day),
                                 "hours": round(hours(f["created_ts"], g["created_ts"]), 2) if g else None})
                i = (j + 1) if j is not None else len(rs)
    paths = ["fixed by a new commit", "re-run, same commit", "merged without a green run", "PR closed, never green"]
    by = defaultdict(Counter)
    for e in episodes:
        by[e["path"]][e["week"]] += 1
    return {"weeks": WEEKS, "series": {p: [by[p].get(w, 0) for w in WEEKS] for p in paths}, "n": len(episodes),
            "paths": Counter(e["path"] for e in episodes),
            "hours": {p: median([e["hours"] for e in episodes if e["path"] == p and e["hours"] is not None]) for p in paths},
            "who": Counter(e["who"] for e in episodes if e["who"]),
            "who_hours": {w: median([e["hours"] for e in episodes if e["who"] == w]) for w in
                          ("same session", "a later session", "no session on the branch", "session data not available")},
            "merged_red": {"before": sum(1 for e in episodes if e["path"] == "merged without a green run" and e["day"] < "2026-08-29"),
                           "after": sum(1 for e in episodes if e["path"] == "merged without a green run" and e["day"] >= "2026-08-29")},
            "episodes": episodes}


# ---------------------------------------------------------------- Q flaky-checks flaky checks

def q_flaky_checks_flaky(con):
    runs = rows(con, "SELECT repo, workflow_name, event, head_sha, conclusion, created_ts FROM github.ci_runs "
                     "WHERE conclusion IN ('success', 'failure') AND event NOT IN ('schedule', 'dynamic', 'issue_comment') "
                     "ORDER BY created_ts")
    grp = defaultdict(list)
    for r in runs:
        if r["workflow_name"] in GATES or not in_scope(r["repo"]):
            continue
        grp[(r["repo"], r["workflow_name"], r["head_sha"])].append(r)
    fails = []
    for (repo, wf, sha), rs in grp.items():
        for i, r in enumerate(rs):
            if r["conclusion"] == "failure":
                flaked = any(x["conclusion"] == "success" for x in rs[i + 1:])
                fails.append({"repo": repo, "workflow": wf, "week": week_of(r["created_ts"]), "flaked": flaked,
                              "deploy": wf in DEPLOYS})
                if flaked:
                    break
    wk = weekly_list(fails)
    share = [round(sum(f["flaked"] for f in wk[w]) / len(wk[w]), 3) if len(wk.get(w, [])) >= 5 else None for w in WEEKS]
    top = Counter(f"{f['repo']} · {f['workflow']}" for f in fails if f["flaked"]).most_common(8)
    tot = Counter(f"{f['repo']} · {f['workflow']}" for f in fails)
    # A re-run keeps its run_id and overwrites the row, so the only trace of one is a start time
    # later than the creation time. Over 30 minutes is a re-run; shorter gaps can be a concurrency queue.
    reruns = [r for r in rows(con, "SELECT repo, workflow_name, conclusion, created_ts, run_started_ts FROM github.ci_runs "
                                   "WHERE (julianday(run_started_ts) - julianday(created_ts)) * 24 > 0.5")
              if r["workflow_name"] not in GATES and in_scope(r["repo"])]
    rr = Counter(week_of(r["created_ts"]) for r in reruns if r["conclusion"] == "success")
    counts = {"Failed, not passed on the same commit": [sum(not f["flaked"] for f in wk.get(w, [])) for w in WEEKS],
              "Failed, then passed on the same commit": [sum(f["flaked"] for f in wk.get(w, [])) for w in WEEKS],
              "Re-run later, ended green": [rr.get(w, 0) for w in WEEKS]}
    return {"weeks": WEEKS, "series": {"Failures that passed on the same commit": share}, "counts": counts,
            "n": len(fails),
            "reruns": [(r["repo"], r["workflow_name"], r["conclusion"], r["created_ts"][:10],
                        round(hours(r["created_ts"], r["run_started_ts"]), 1)) for r in reruns],
            "flaked": sum(f["flaked"] for f in fails), "top": [(k, v, tot[k]) for k, v in top],
            "deploy_flakes": sum(f["flaked"] for f in fails if f["deploy"])}


# ---------------------------------------------------------------- Q never-failed-checks checks that never failed

def q_never_failed_checks_never(con):
    runs = rows(con, "SELECT repo, workflow_name, conclusion, created_ts FROM github.ci_runs "
                     "WHERE conclusion IN ('success', 'failure') AND event NOT IN ('dynamic') ORDER BY created_ts")
    runs = [r for r in runs if r["workflow_name"] not in GATES and in_scope(r["repo"])]
    first_fail, seen = {}, defaultdict(list)
    for r in runs:
        k = (r["repo"], r["workflow_name"])
        seen[k].append(r)
        if r["conclusion"] == "failure" and k not in first_fail:
            first_fail[k] = r["created_ts"]
    active = defaultdict(set)
    for r in runs:
        active[week_of(r["created_ts"])].add((r["repo"], r["workflow_name"]))
    proven = [sum(1 for k in active.get(w, ()) if k in first_fail and first_fail[k][:10] <= date.fromisocalendar(
        int(w[:4]), int(w[6:]), 7).isoformat()) for w in WEEKS]
    total = [len(active.get(w, ())) for w in WEEKS]
    never = sorted(((k, len(v)) for k, v in seen.items() if k not in first_fail and len(v) >= 10), key=lambda x: -x[1])
    return {"weeks": WEEKS,
            "series": {"Seen failing by then": proven, "Not yet seen failing": [t - p for t, p in zip(total, proven)]},
            "never": never, "n_checks": len(seen), "n_proven": len(first_fail)}


# ---------------------------------------------------------------- Q shared-workflow-breaks shared-workflow breakage

def q_shared_workflow_breaks_shared(con):
    runs = rows(con, "SELECT repo, workflow_name, conclusion, created_ts FROM github.ci_runs "
                     "WHERE workflow_name IN ('Auto Approve', '.github/workflows/auto-approve.yaml') ORDER BY created_ts")
    broken = [r for r in runs if r["conclusion"] == "startup_failure" or
              (r["workflow_name"].startswith(".github") and r["conclusion"] == "failure")]
    incidents = {"26 Aug": ("2026-08-26", "2026-08-27"), "29 Aug": ("2026-08-28", "2026-08-31"),
                 "18 Sep": ("2026-09-18", "2026-09-19"), "22 Sep": ("2026-09-21", "2026-09-24")}
    grid = {}
    for name, (lo, hi) in incidents.items():
        inc = [r for r in broken if lo <= r["created_ts"][:10] <= hi]
        per = {}
        for repo in sorted({r["repo"] for r in inc}):
            last_bad = max(r["created_ts"] for r in inc if r["repo"] == repo)
            first_bad = min(r["created_ts"] for r in inc if r["repo"] == repo)
            ok = next((r["created_ts"] for r in runs if r["repo"] == repo and r["conclusion"] == "success"
                       and r["created_ts"] > last_bad), None)
            per[repo] = {"first": first_bad, "green": ok, "hours": round(hours(first_bad, ok), 1) if ok else None,
                         "runs": sum(1 for r in inc if r["repo"] == repo)}
        grid[name] = per
    by = defaultdict(Counter)
    for r in broken:
        kind = "Failed at startup" if r["conclusion"] == "startup_failure" else "Workflow not found (path-named run)"
        by[kind][week_of(r["created_ts"])] += 1
    return {"weeks": WEEKS, "series": {k: [by[k].get(w, 0) for w in WEEKS] for k in
                                       ("Failed at startup", "Workflow not found (path-named run)")},
            "grid": grid, "n": len(broken), "repos": len({r["repo"] for r in broken})}


# ---------------------------------------------------------------- Q action-pin-spread pins

USES = re.compile(r"uses:\s*['\"]?([\w.-]+/[\w.-]+)(?:/[\w./-]+)?@([\w.-]+)['\"]?\s*(?:#\s*(\S+))?")
TRACKED = ["actions/checkout", "actions/setup-node", "actions/setup-python", "actions/setup-go",
           "docker/build-push-action", "docker/login-action"]


@lru_cache(maxsize=None)
def pin_history():
    """Per repo, the workflow `uses:` refs on main after every commit that touched .github/workflows."""
    repos = sorted(f[:-4] for f in os.listdir(MIRRORS) if f.endswith(".git") and in_scope(f[:-4]))
    out = {}
    for repo in repos:
        hist = []
        for line in git(repo, "log", "--first-parent", "--reverse", "--format=%H %cs", "HEAD", "--",
                        ".github/workflows").splitlines():
            sha, day = line.split()
            refs = []
            for m in USES.finditer(git(repo, "grep", "-h", "uses:", sha, "--", ".github/workflows")):
                action, ref, comment = m.group(1), m.group(2), m.group(3)
                pinned = bool(re.fullmatch(r"[0-9a-f]{40}", ref))
                ver = (comment if pinned and comment else ref).lstrip("v")
                refs.append((action, ver, pinned))
            hist.append((day, refs))
        out[repo] = hist
    return out


def q_action_pin_spread_pins(con):
    hist = pin_history()
    first_seen = defaultdict(dict)
    for repo, h in hist.items():
        for day, refs in h:
            for action, ver, _ in refs:
                if action in TRACKED:
                    first_seen[(action, ver)].setdefault(repo, day)

    def state(repo, day):
        cur = None
        for d, refs in hist[repo]:
            if d <= day:
                cur = refs
        return cur or []

    series = {a: [] for a in TRACKED[:4]}
    unpinned = []
    for w in WEEKS:
        end = date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()
        live = defaultdict(set)
        n_ref = n_unpinned = 0
        for repo in hist:
            for action, ver, pinned in state(repo, end):
                if action in TRACKED:
                    live[action].add(ver.split(".")[0] + "." + (ver.split(".") + ["0"])[1] if ver[:1].isdigit() else ver)
                n_ref += 1
                n_unpinned += not pinned
        for a in series:
            series[a].append(len(live[a]) or None)
        unpinned.append(round(n_unpinned / n_ref, 3) if n_ref else None)
    lags = []
    for (action, ver), repos in first_seen.items():
        if len(repos) < 3 or not ver[:1].isdigit():
            continue
        d0 = min(repos.values())
        ds = sorted((date.fromisoformat(d) - date.fromisoformat(d0)).days for d in repos.values())
        lags.append({"action": action, "version": ver, "first": d0, "repos": len(ds),
                     "median": statistics.median(ds[1:]), "max": ds[-1]})
    lags.sort(key=lambda x: x["first"])
    return {"weeks": WEEKS, "series": series, "unpinned": unpinned, "lags": lags,
            "median_lag": median([l["median"] for l in lags]), "median_max": median([l["max"] for l in lags]),
            "n_repos": len(hist)}


# ---------------------------------------------------------------- Q infra-built-like-apps infra built like the apps

def q_infra_built_like_apps_infra_authors(con):
    prs = infra_prs(con)
    kinds = ["Owner, by hand", "Second engineer", "Agent (owner's sessions)", "Dependabot"]
    by = defaultdict(Counter)
    for p in prs:
        by[p["who"]][p["month"]] += 1
    months = MONTHS
    series = {k: [by[k].get(m, 0) for m in months] for k in kinds}
    # Agent share of human-and-agent PRs, infra vs apps, by month.
    trailer = defaultdict(int)
    for r in rows(con, "SELECT repo, pr_number, claude_trailer FROM pr_commits.pr_commits WHERE is_merge = 0"):
        trailer[(r["repo"], r["pr_number"])] += r["claude_trailer"] or 0
    share = {"Infrastructure repos": defaultdict(list), "App repos": defaultdict(list)}
    for p in merged_prs(con):
        if p["author_is_bot"] or "dependabot" in (p["author"] or "") or not in_scope(p["repo"]):
            continue
        cat = category_of(p["repo"])
        grp = "Infrastructure repos" if p["repo"] in INFRA else "App repos" if cat.startswith("app") else None
        if grp:
            share[grp][p["merged_ts"][:7]].append(p["author"] == "rparundekar" and trailer[(p["repo"], p["number"])] > 0)
    lines = {g: [round(sum(v[m]) / len(v[m]), 3) if len(v.get(m, [])) >= 5 else None for m in months]
             for g, v in share.items()}
    return {"months": months, "series": series, "lines": lines, "n": len(prs),
            "who": Counter(p["who"] for p in prs),
            "by_repo_who": {r: Counter(p["who"] for p in prs if p["repo"] == r) for r in INFRA},
            "second_span": (min(p["day"] for p in prs if p["who"] == "Second engineer"),
                            max(p["day"] for p in prs if p["who"] == "Second engineer"))}


def hung_gate_runs(con):
    """Approval-gate runs that ran over an hour: left out of every duration here."""
    r = rows(con, "SELECT COUNT(*) n, MAX(duration_s) mx, SUM(duration_s) tot, MIN(week) w0, MAX(week) w1 "
                  "FROM github.ci_runs WHERE workflow_name = 'Auto Approve' AND duration_s > 3600")[0]
    return {"n": r["n"], "max_h": round(r["mx"] / 3600), "hours": round(r["tot"] / 3600), "weeks": (r["w0"], r["w1"])}


def all_data():
    from cube.db import connect
    con = connect("deployment")
    return {"con": con, "ci_start": ci_start(con), "hung": hung_gate_runs(con), "q_platform_history": q_platform_history_platform(con), "q_app_to_infra_time": q_app_to_infra_time_onboarding(con),
            "q_deploy_on_merge": q_deploy_on_merge_deploying(con), "q_merge_to_production": q_merge_to_production_lag(con), "q_deploy_failures": q_deploy_failures_failures(con), "q_deploy_failures_recovery": q_deploy_failures_recovery(con), "q_production_uptime": q_production_uptime_health(con),
            "q_ci_red_rate": q_ci_red_rate_red(con), "q_ci_red_to_green": q_ci_red_to_green_green(con), "q_flaky_checks": q_flaky_checks_flaky(con), "q_never_failed_checks": q_never_failed_checks_never(con),
            "q_shared_workflow_breaks": q_shared_workflow_breaks_shared(con), "q_action_pin_spread": q_action_pin_spread_pins(con), "q_infra_built_like_apps": q_infra_built_like_apps_infra_authors(con)}


if __name__ == "__main__":
    d = all_data()
    for k, v in d.items():
        if k == "con":
            continue
        slim = {kk: vv for kk, vv in (v.items() if isinstance(v, dict) else [])
                if kk not in ("weeks", "series", "facts", "episodes", "apps", "fails", "months", "by_repo")}
        print(f"== {k}", json.dumps(slim if slim else v, default=str)[:1800])
