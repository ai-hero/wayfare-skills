"""Connectors series: connectors. One function per question, each returning what its slides plot.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/connectors/data.py   # prints a summary

Sources beyond the cube: every historical HERO.md, registry.json, VERSION.md and component tree
is read from the read-only mirrors in .analysis/data/mirrors (git show / ls-tree / grep, never a
write). Model labels (items, prompts) come from connectors.sqlite, written by report/connectors/label.py.
"""
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from record import rows, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, category_of, path_of  # noqa: E402

ANALYSIS = os.path.dirname(os.path.dirname(HERE))
MIRRORS = os.path.join(os.path.dirname(ANALYSIS), ".analysis", "data", "mirrors")
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
TODAY = "2026-09-25"
# No Claude Code sessions are logged 10-24 Aug (W33-W34): session, tool and
# turn series leave these weeks blank and out of every average, never zero.
NA_WEEKS = {"2026-W33", "2026-W34"}
SESSIONS_FROM = "2026-W32"  # the first logged Claude Code session is 9 Aug
KINDS = ["design", "design-system", "issues", "infrastructure", "reference", "architecture"]
CONSUMERS = ["ah-cozy", "aihero-dokyu", "aihero-mehr", "aihero-steadfast", "aihero-wayfare", "auth",
             "elevate-commons", "hero-template", "hiro", "website"]
DS = "design-system"
EVENTS = [("2026-07-21", "First -design repos"), ("2026-09-22", "Connections standard")]
OWNER_ORIGINS = {"one-shot", "rahul", "user", "conversation", "wayfare-grill-idea", "think-it-through"}
AGENT_ORIGINS = {"wayfare", "wayfare-sync-plan", "harden", "self-review", "message", "wayfare-build-task",
                 "wayfare-run-task"}


def who(origin):
    return "Owner-instructed" if origin in OWNER_ORIGINS else "Agent-found" if origin in AGENT_ORIGINS else "Not recorded"


def week_end(w):
    return date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()


def month_end(m):
    y, mo = int(m[:4]), int(m[5:])
    return (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(1)).isoformat()


def median(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, f"{repo}.git"), *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


def repos_in_scope():
    return sorted(f[:-4] for f in os.listdir(MIRRORS) if f.endswith(".git") and f[:-4] not in OUT_OF_SCOPE)


@lru_cache(maxsize=None)
def main_log(repo, path=None):
    """[(day, sha, subject)] oldest first, first-parent history of the default branch."""
    args = ["log", "--first-parent", "--reverse", "--format=%ad\t%H\t%s", "--date=short", "HEAD"]
    if path:
        args += ["--", path]
    return [tuple(l.split("\t", 2)) for l in git(repo, *args).splitlines() if l.count("\t") >= 2]


def sha_at(repo, day):
    """The default branch's head at the end of `day`, or None before the repo existed."""
    last = None
    for d, sha, _ in main_log(repo):
        if d > day:
            break
        last = sha
    return last


# ------------------------------------------------------------------ HERO.md connections

def _sections(text):
    """{(h2, h3): {key: value}} for every `- key: value` line; value keeps its comment."""
    out, h2, h3 = defaultdict(dict), "", ""
    for line in text.splitlines():
        if line.startswith("## "):
            h2, h3 = line[3:].strip(), ""
        elif line.startswith("### "):
            h3 = line[4:].strip()
        else:
            m = re.match(r"^\s*- ([A-Za-z_-]+):\s*(.*)", line)
            if m:
                out[(h2, h3 if h2 == "Connections" else "")].setdefault(m.group(1), m.group(2).strip())
    return out


def _val(v):
    return (v or "").split(" #")[0].split("  ")[0].strip().strip("<>")


def _absent(v):
    return _val(v).lower() in ("none", "") or _val(v).lower().startswith("none")


# How each kind was written before the Connections standard (22 Sep). A kind with a structured
# block is read from it; otherwise from these legacy spellings, in this order.
LEGACY = {
    "design": [("Wayfare", "design-project"), ("Wayfare", "target-repo")],
    "design-system": [("Design System", "role"), ("Design System", "registry-url"), ("Wayfare", "design-system-repo")],
    "issues": [("Project Management", "tool"), ("Project Management", "issue-tracker")],
    "infrastructure": [("Deployment", "platform")],
    "reference": [],
    "architecture": [],
}
MAPPING_NOTE = (
    "Old HERO.md spellings mapped to the six kinds: design = `## Wayfare` design-project (from 16 Aug) or "
    "target-repo (a -design repo, 21 Jul to 16 Aug); design-system = the `## Design System` section (role, "
    "registry-url) or `## Wayfare` design-system-repo; issues = `## Project Management` tool / issue-tracker; "
    "infrastructure = `## Deployment` platform (where it deploys, the nearest old field to an IaC repo; a "
    "judgement call); reference and architecture had no old spelling, so they exist only in the block. A value "
    "of none is 'looked, none'.")


def parse_connections(text):
    """{kind: {"state": declared|self|none, "form": block|free-form, "value": str, "reach": str}}."""
    sec = _sections(text)
    out = {}
    for kind in KINDS:
        blk = sec.get(("Connections", kind))
        if blk and "type" in blk:
            t = _val(blk["type"]).lower()
            out[kind] = {"state": "none" if t.startswith("none") else "self" if t == "self" else "declared",
                         "form": "block", "value": _val(blk.get("at")), "reach": _val(blk.get("reach")),
                         "type": t}
            continue
        for h2, key in LEGACY[kind]:
            v = sec.get((h2, ""), {}).get(key)
            if v is None:
                continue
            reach = ""
            if kind == "design":
                reach = _val(sec.get(("Wayfare", ""), {}).get("design-transport")) if key == "design-project" else "checkout"
            out[kind] = {"state": "none" if _absent(v) else "declared", "form": "free-form", "value": _val(v),
                         "reach": reach, "type": key}
            break
    return out


@lru_cache(maxsize=None)
def hero_versions(repo):
    """[(day, sha, {kind: ...})] for every HERO.md on the default branch."""
    out = []
    for d, sha, _ in main_log(repo, "HERO.md"):
        text = git(repo, "show", f"{sha}:HERO.md")
        if text:
            out.append((d, sha, parse_connections(text)))
    return out


def conns_at(repo, day):
    last = None
    for d, _, c in hero_versions(repo):
        if d > day:
            break
        last = c
    return last


def q_declared_connections_declared():
    repos = repos_in_scope()
    series = {k: [] for k in KINDS}
    none_s, block_s = [], []
    for w in WEEKS:
        e = week_end(w)
        cnt, nn, blk = Counter(), 0, 0
        for r in repos:
            c = conns_at(r, e) or {}
            for k, v in c.items():
                if v["state"] in ("declared", "self"):
                    cnt[k] += 1
                    blk += v["form"] == "block"
                else:
                    nn += 1
        for k in KINDS:
            series[k].append(cnt[k])
        none_s.append(nn)
        block_s.append(blk)
    first = {}
    grid = []
    for r in repos:
        for d, _, c in hero_versions(r):
            for k, v in c.items():
                first.setdefault((r, k), (d, v["state"], v["form"]))
        now = conns_at(r, TODAY) or {}
        grid.append({"repo": r, "category": category_of(r),
                     "block": sum(1 for v in now.values() if v["form"] == "block" and v["state"] != "none"),
                     "free": sum(1 for v in now.values() if v["form"] == "free-form" and v["state"] != "none"),
                     "none": sum(1 for v in now.values() if v["state"] == "none"),
                     "unset": sum(1 for k in KINDS if k not in now),
                     "kinds": {k: (now[k]["state"], now[k]["form"]) for k in now}})
    now_total = sum(series[k][-1] for k in KINDS)
    return {"weeks": WEEKS, "series": series, "none": none_s, "block": block_s, "grid": grid,
            "first": {f"{r}|{k}": v for (r, k), v in first.items()}, "now_total": now_total,
            "now_block": block_s[-1], "repos": repos, "mapping": MAPPING_NOTE,
            "by_kind_now": {k: series[k][-1] for k in KINDS},
            "first_any": min(v[0] for v in first.values()) if first else None}


# ------------------------------------------------------------------ Q connections-read-by-skills readers in the plugin

READERS = {
    "design": r"design-project|target-repo|design-transport|hero_connection(_compat|_repo)? design( |\"|$)",
    "design-system": r"registry-url|design-system-repo|## Design System|hero_connection(_compat|_repo)? design-system",
    "issues": r"issue-prefix|issue-tracker|## Project Management|hero_connection(_compat|_repo)? issues",
    "infrastructure": r"## Deployment|hero_connection(_compat|_repo)? infrastructure",
    "reference": r"hero_connection(_compat|_repo)? reference",
    "architecture": r"hero_connection(_compat|_repo)? architecture",
}


def q_connections_read_by_skills_readers():
    repo = "wayfare-skills"
    series = {k: [] for k in KINDS}
    first_reader = {}
    for w in WEEKS:
        sha = sha_at(repo, week_end(w))
        for k in KINDS:
            n = 0
            if sha:
                out = git(repo, "grep", "-l", "-E", READERS[k], sha, "--", "skills", "references")
                n = len([l for l in out.splitlines() if l.strip() and not l.endswith(".test.sh")])
            series[k].append(n)
            if n and k not in first_reader:
                first_reader[k] = week_end(w)
    decl = q_declared_connections_declared()["first"]
    first_decl = {}
    for key, (d, state, _) in decl.items():
        r, k = key.split("|")
        if state != "none" and (k not in first_decl or d < first_decl[k]):
            first_decl[k] = d
    return {"weeks": WEEKS, "series": series, "first_reader": first_reader, "first_declared": first_decl,
            "now": {k: series[k][-1] for k in KINDS}}


# ------------------------------------------------------------------ Q connection-reach-in-use / Q wrong-declared-reach reach in use

def _tool_rows(con):
    return rows(con, """SELECT t.ts, t.tool, t.is_error, s.repo FROM harness.tool_calls t
                        JOIN harness.sessions s USING (session_id_hash)
                        WHERE t.tool = 'DesignSync' OR t.tool LIKE 'mcp__claude_ai_Linear%'
                           OR t.tool LIKE 'mcp__%figma%' OR t.tool = 'WebFetch'""")


def design_reach_at(repo, day):
    c = (conns_at(repo, day) or {}).get("design")
    if not c:
        return "unset"
    r = (c["reach"] or "").lower()
    if c["type"] == "target-repo":
        return "declared none" if c["state"] == "none" else "-design repo"
    # `design-project: none` with transport `manual` means "a project exists but sits on another
    # account": that is a manual reach, not a declared absence.
    if r.startswith("manual"):
        return "manual"
    if c["state"] == "none":
        return "declared none"
    return "designsync" if r.startswith("designsync") else "auto"


def q_connection_reach_in_use_reach(con):
    rs = _tool_rows(con)
    ds = [r for r in rs if r["tool"] == "DesignSync"]
    cats = ["designsync", "auto", "manual", "declared none", "unset"]
    series = {c: [0] * len(WEEKS) for c in cats}
    for r in ds:
        w = week_of(r["ts"])
        if w in WEEKS:
            series[design_reach_at(r["repo"], r["ts"][:10])][WEEKS.index(w)] += 1
    for c in cats:
        for i, w in enumerate(WEEKS):
            if w in NA_WEEKS or w < SESSIONS_FROM:
                series[c][i] = None
    by_repo = defaultdict(lambda: [0] * len(MONTHS))
    for r in ds:
        m = r["ts"][:7]
        if m in MONTHS:
            by_repo[r["repo"]][MONTHS.index(m)] += 1
    per_repo = Counter(r["repo"] for r in ds)
    mismatch = sum(1 for r in ds if design_reach_at(r["repo"], r["ts"][:10]) in ("manual", "declared none", "unset"))
    linear = sum(1 for r in rs if r["tool"].startswith("mcp__claude_ai_Linear"))
    figma = sum(1 for r in rs if "figma" in r["tool"].lower())
    # Bash commands are not recorded in tool_calls, so gh/terraform/kubectl use is only visible in
    # the assistant's own words: a lower bound, not a count of calls.
    text = rows(con, """SELECT SUM(text_redacted LIKE '%gh pr %' OR text_redacted LIKE '%gh api%' OR text_redacted LIKE '%`gh %')
                            AS gh, SUM(LOWER(text_redacted) LIKE '%terraform%' OR LOWER(text_redacted) LIKE '%tofu %') AS tf,
                            SUM(LOWER(text_redacted) LIKE '%kubectl%') AS k8s, COUNT(*) AS n
                        FROM harness.turns WHERE role = 'assistant' AND text_redacted != ''""")[0]
    declared_now = {r: design_reach_at(r, TODAY) for r in per_repo}
    first_call = min(r["ts"][:10] for r in ds) if ds else None
    return {"weeks": WEEKS, "series": series, "by_repo": dict(by_repo), "per_repo": dict(per_repo),
            "total": len(ds), "errors": sum(r["is_error"] for r in ds), "mismatch": mismatch, "linear": linear,
            "figma": figma, "text": dict(text), "declared_now": declared_now, "first_call": first_call}


def q_wrong_declared_reach_corrections(con):
    """Every change to a design connection's reach, with how long the previous value stood."""
    out = []
    for repo in repos_in_scope():
        prev = None
        for d, sha, c in hero_versions(repo):
            cur = c.get("design")
            key = (design_reach_at(repo, d), cur["value"] if cur else None)
            if prev and key != prev[0]:
                comment = ""
                text = git(repo, "show", f"{sha}:HERO.md")
                m = re.search(r"(design-transport|reach):.*?#\s*(.*)", text)
                if m:
                    comment = m.group(2)[:200]
                out.append({"repo": repo, "from": prev[0][0], "to": key[0], "since": prev[1], "on": d,
                            "days": (date.fromisoformat(d) - date.fromisoformat(prev[1])).days, "comment": comment})
            if not prev or key != prev[0]:
                prev = (key, d)
    wrong = [c for c in out if c["from"] == "manual" and c["to"] in ("designsync", "auto")]
    ds = [r for r in _tool_rows(con) if r["tool"] == "DesignSync"]
    repos = sorted({c["repo"] for c in wrong})
    series = {r: [0] * len(WEEKS) for r in repos}
    for r in ds:
        w = week_of(r["ts"])
        if r["repo"] in series and w in WEEKS:
            series[r["repo"]][WEEKS.index(w)] += 1
    for r in repos:
        for i, w in enumerate(WEEKS):
            if w in NA_WEEKS or w < SESSIONS_FROM:
                series[r][i] = None
    before = sum(1 for r in ds if r["repo"] in repos and design_reach_at(r["repo"], r["ts"][:10]) == "manual")
    return {"changes": out, "wrong": wrong, "weeks": WEEKS, "series": series, "calls_while_manual": before,
            "days_wrong": [c["days"] for c in wrong]}


# ------------------------------------------------------------------ Q copied-connector-values copies

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VER = re.compile(r"20\d\d\.\d\d\.\d\d(?:-\d+)?")


def ver_key(v):
    base, _, n = v.partition("-")
    return (base, int(n or 0))


@lru_cache(maxsize=None)
def ds_pins():
    """[(day, version)] the design-system's conformance cache was pinned at, oldest first."""
    out = []
    for d, sha, subj in main_log(DS):
        m = re.search(r"(?:adopt design surface|design surface|re-pin .*? to design surface)\s+(" + VER.pattern + ")", subj)
        if m and re.search(r"pin|adopt", subj, re.I):
            out.append((d, m.group(1)))
    return out


def ds_pin_at(day):
    last = None
    for d, v in ds_pins():
        if d <= day:
            last = v
    return last


def q_copied_connector_values_copies():
    ds_ids = set()
    for _, _, c in hero_versions(DS):
        v = (c.get("design") or {}).get("value") or ""
        ds_ids |= set(UUID.findall(v))
    series = {"Registry URL copies (source never moved)": [], "Version pins, current": [],
              "Version pins, stale": [], "Design project id copied from another repo": []}
    cases = []
    for w in WEEKS:
        e = week_end(w)
        reg = cur = stale = wrong = 0
        pin = ds_pin_at(e)
        for r in CONSUMERS:
            c = conns_at(r, e) or {}
            if (c.get("design-system") or {}).get("state") == "declared":
                reg += 1
            if sha_at(r, e) and "@aihero" in git(r, "show", f"{sha_at(r, e)}:ui/components.json"):
                reg += 1
            dv = (c.get("design") or {}).get("value") or ""
            if r != DS and set(UUID.findall(dv)) & ds_ids:
                wrong += 1
            sha = sha_at(r, e)
            if sha:
                txt = git(r, "show", f"{sha}:ui/design-contract.json")
                m = re.search(r'"version":\s*"(' + VER.pattern + ')"', txt)
                if m and pin:
                    if ver_key(m.group(1)) < ver_key(pin):
                        stale += 1
                    else:
                        cur += 1
        series["Registry URL copies (source never moved)"].append(reg)
        series["Version pins, current"].append(cur)
        series["Version pins, stale"].append(stale)
        series["Design project id copied from another repo"].append(wrong)
    for r in CONSUMERS:
        prev = None
        for d, _, c in hero_versions(r):
            dv = (c.get("design") or {}).get("value") or ""
            hit = bool(set(UUID.findall(dv)) & ds_ids)
            if hit and not prev:
                prev = d
            elif prev and not hit:
                cases.append({"repo": r, "what": "design-system's project id held as its own design", "from": prev,
                              "to": d, "days": (date.fromisoformat(d) - date.fromisoformat(prev)).days})
                prev = None
        if prev:
            cases.append({"repo": r, "what": "design-system's project id held as its own design", "from": prev,
                          "to": None, "days": (date.fromisoformat(TODAY) - date.fromisoformat(prev)).days})
        vlog = [(d, sha) for d, sha, _ in main_log(r, "ui/design-contract.json")]
        for i, (d, sha) in enumerate(vlog):
            m = re.search(r'"version":\s*"(' + VER.pattern + ')"', git(r, "show", f"{sha}:ui/design-contract.json"))
            if not m:
                continue
            v = m.group(1)
            end = vlog[i + 1][0] if i + 1 < len(vlog) else TODAY
            newer = [(pd, pv) for pd, pv in ds_pins() if ver_key(pv) > ver_key(v) and pd < end]
            if newer:
                since = max(d, newer[0][0])
                cases.append({"repo": r, "what": f"design-contract.json pinned at {v} after design-system moved to "
                                                 f"{newer[-1][1]}", "from": since,
                              "to": vlog[i + 1][0] if i + 1 < len(vlog) else None,
                              "days": (date.fromisoformat(end) - date.fromisoformat(since)).days})
    return {"weeks": WEEKS, "series": series, "cases": cases, "ds_ids": len(ds_ids)}


# ------------------------------------------------------------------ Q design-snapshot-lag / Q design-system-release-reach / Q registry-component-share design system

@lru_cache(maxsize=None)
def surface_versions():
    """{version: first day it is named in design-system's history}; the name carries its source date."""
    first = {}
    cur = None
    for line in git(DS, "log", "--first-parent", "--reverse", "-p", "--format=@@C %ad", "--date=short", "HEAD", "--",
                    "VERSION.md", "DESIGN.md", "HERO.md", "AGENTS.md", "README.md", "src/styles.css",
                    "design-cache").splitlines():
        if line.startswith("@@C "):
            cur = line[4:].strip()
        elif line.startswith("+") and not line.startswith("+++"):
            for v in VER.findall(line):
                first.setdefault(v, cur)
    return first


# 2026.09.17 is named only as the date of a second copy of the design project (a "ladder shift"
# in its bundle.css), not a release of the project design-system is pinned to.
NOT_RELEASES = {"2026.09.17"}


def src_day(v):
    return f"{v[:4]}-{v[5:7]}-{v[8:10]}"


def q_design_snapshot_lag_snapshot():
    vers = {v: d for v, d in surface_versions().items() if v not in NOT_RELEASES}
    pins = ds_pins()
    pinned = {v: d for d, v in reversed(pins)}
    start = date(2026, 8, 24)
    days, behind, newest_s, pinned_s = [], [], [], []
    d = start
    while d.isoformat() <= TODAY:
        day = d.isoformat()
        released = [v for v in vers if src_day(v) <= day]
        pin = ds_pin_at(day)
        if released and pin:
            newest = max(released, key=ver_key)
            days.append(day)
            behind.append((date.fromisoformat(src_day(newest)) - date.fromisoformat(src_day(pin))).days)
            newest_s.append(newest)
            pinned_s.append(pin)
        d += timedelta(1)
    weekly = []
    for w in WEEKS:
        vals = [b for dd, b in zip(days, behind) if week_of(dd) == w]
        weekly.append(max(vals) if vals else None)
    table = []
    for v in sorted(vers, key=ver_key):
        pd = pinned.get(v)
        table.append({"version": v, "released": src_day(v), "named": vers[v][:10] if vers[v] else None,
                      "pinned": pd, "days": (date.fromisoformat(pd) - date.fromisoformat(src_day(v))).days if pd else None})
    unpinned = [t for t in table if not t["pinned"]]
    return {"weeks": WEEKS, "behind_weekly": weekly, "days": days, "behind": behind, "table": table, "pins": pins,
            "n_versions": len(table), "n_pinned": len(pins), "unpinned": unpinned,
            "pin_lags": [t["days"] for t in table if t["days"] is not None],
            "behind_now": behind[-1] if behind else None, "newest_now": newest_s[-1] if newest_s else None,
            "pin_now": pinned_s[-1] if pinned_s else None}


def _touches(repo, pred):
    """[(day, sha, subject)] default-branch commits whose changed files satisfy pred(path)."""
    out = []
    cur = None
    for line in git(repo, "log", "--first-parent", "--reverse", "--name-only", "--format=@@C %ad\t%H\t%s",
                    "--date=short", "HEAD").splitlines():
        if line.startswith("@@C "):
            cur = tuple(line[4:].split("\t", 2))
            cur_hit = False
        elif line.strip() and cur and pred(line.strip()):
            if not out or out[-1][1] != cur[1]:
                out.append(cur)
    return out


@lru_cache(maxsize=None)
def ds_publishes():
    return _touches(DS, lambda p: p == "registry.json" or p.startswith("src/components/") or p == "src/styles.css")


@lru_cache(maxsize=None)
def registry_declared(repo):
    """First day the consumer's components.json names the @aihero registry."""
    for d, sha, _ in main_log(repo, "ui/components.json"):
        if "@aihero" in git(repo, "show", f"{sha}:ui/components.json"):
            return d
    return None


@lru_cache(maxsize=None)
def consumer_pulls(repo):
    """Changes to where the registry installs, once the repo consumes the registry (earlier ones were stock shadcn)."""
    since = registry_declared(repo) or "9999"
    return [c for c in _touches(repo, lambda p: p.startswith(("ui/src/components/ui/", "ui/src/components/blocks/")))
            if c[0] >= since]


def version_entries():
    """Dated VERSION.md entries: (day, breaking, title), from the 'Registry behavior changes' half only."""
    text = git(DS, "show", "HEAD:VERSION.md")
    head = text.split("# Notes for the design project")[0]
    return [(m.group(1), "BREAKING" in m.group(2), m.group(2)) for m in
            re.finditer(r"^## (\d{4}-\d\d-\d\d) — (.*)$", head, re.M)]


def q_design_system_release_reach_adoption():
    pubs = ds_publishes()
    pub_w = Counter(week_of(d) for d, _, _ in pubs)
    pull_w = Counter()
    for r in CONSUMERS:
        for d, _, _ in consumer_pulls(r):
            pull_w[week_of(d)] += 1
    series = {"Registry publishes (design-system)": [pub_w.get(w, 0) for w in WEEKS],
              "Pulls by consumers": [pull_w.get(w, 0) for w in WEEKS]}

    def stale_at(r, day):
        pulls = [d for d, _, _ in consumer_pulls(r) if d <= day]
        if not pulls:
            return None
        last = pulls[-1]
        after = [d for d, _, _ in pubs if last < d <= day]
        return (date.fromisoformat(day) - date.fromisoformat(after[0])).days if after else 0

    by_repo = {}
    for r in CONSUMERS:
        vals = [stale_at(r, month_end(m)) if m >= "2026-07" else None for m in MONTHS]
        vals[-1] = stale_at(r, TODAY)
        if any(v is not None for v in vals):
            by_repo[r] = vals
    ver = version_entries()
    table = []
    for r in CONSUMERS:
        pulls = consumer_pulls(r)
        last = pulls[-1][0] if pulls else None
        missed = [v for v in ver if last and v[0] > last]
        table.append({"repo": r, "pulls": len(pulls), "last_pull": last, "stale_days": stale_at(r, TODAY),
                      "entries_since": len(missed), "breaking_since": sum(1 for v in missed if v[1])})
    now = [t["stale_days"] for t in table if t["stale_days"] is not None]
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo, "table": table, "median_stale_now": median(now),
            "n_publishes": len(pubs), "n_pulls": sum(len(consumer_pulls(r)) for r in CONSUMERS),
            "version_entries": len(ver), "breaking": sum(1 for v in ver if v[1]),
            "pulls_since_sep": sum(1 for r in CONSUMERS for d, _, _ in consumer_pulls(r) if d >= "2026-09-01"),
            "pubs_since_sep": sum(1 for d, _, _ in pubs if d >= "2026-09-01")}


# ---------------------------------------------------------------- Q design-system-release-reach, by content

INSTALL_DIRS = ("ui/src/components/ui/", "ui/src/components/blocks/")
FRESH_DAYS = 21  # the chapter's "three weeks"; no consumer or the registry states a freshness threshold
# The template and the products with feature work; the three "app, no features yet" clones and the
# deprecated hiro take fleet sweeps but no UI work of their own, so a lag there is inactivity, not neglect.
INACTIVE_CONSUMERS = {"ah-cozy", "aihero-dokyu", "aihero-mehr", "hiro"}


def norm_hash(text):
    """Content identity of a component file across the registry's rewrite: shadcn drops the licence header and
    rewrites the import lines on install, so those and blank lines are left out before hashing."""
    keep = []
    for line in text.splitlines():
        t = line.strip()
        if not t or t.startswith("//") or t.startswith("import ") or t.startswith("} from ") or t.startswith("export * from"):
            continue
        keep.append(t)
    return hashlib.sha1("\n".join(keep).encode()).hexdigest()


def _component(path):
    return path.endswith(".tsx") and ".test." not in path and ".stories." not in path and "/examples/" not in path


@lru_cache(maxsize=None)
def ds_component_history():
    """Every version of every design-system component file: {path: [(day, sha, hash)]} in order, one entry per
    content change, and the reverse index {hash: [(path, first_day, superseded_day)]}."""
    blob_hash, hist = {}, {}
    log = git(DS, "log", "--first-parent", "--reverse", "--format=%cs %H", "HEAD", "--", "src/components")
    for line in log.splitlines():
        day, sha = line.split()
        for row in git(DS, "ls-tree", "-r", sha, "src/components").splitlines():
            meta, path = row.split("\t")
            if not _component(path):
                continue
            blob = meta.split()[2]
            if blob not in blob_hash:
                blob_hash[blob] = norm_hash(git(DS, "cat-file", "-p", blob))
            h = blob_hash[blob]
            lst = hist.setdefault(path, [])
            if not lst or lst[-1][2] != h:
                lst.append((day, sha, h))
    by_hash = defaultdict(list)
    for path, lst in hist.items():
        for i, (day, sha, h) in enumerate(lst):
            by_hash[h].append((path, day, lst[i + 1][0] if i + 1 < len(lst) else None))
    return hist, by_hash


def ds_releases():
    """[(day, sha, {paths whose content changed})]: a design-system commit that changes a component's content is a
    release, because the registry serves main."""
    hist, _ = ds_component_history()
    changed = defaultdict(set)
    for path, lst in hist.items():
        for day, sha, _h in lst[1:]:
            changed[(day, sha)].add(path)
    return sorted((day, sha, ps) for (day, sha), ps in changed.items())


@lru_cache(maxsize=None)
def installed_at(repo, sha):
    """{installed path: content hash} of the consumer's registry directories at a commit."""
    out = {}
    for row in git(repo, "ls-tree", "-r", sha, *INSTALL_DIRS).splitlines():
        meta, path = row.split("\t")
        if path.endswith(".tsx"):
            out[path] = norm_hash(git(repo, "cat-file", "-p", meta.split()[2]))
    return out


def _version_of(h, by_hash):
    """(first published day, superseded day or None) of a content hash, or None when no registry version matches."""
    if h not in by_hash:
        return None
    first = min(d for _, d, _n in by_hash[h])
    nxts = [n for _, _d, n in by_hash[h]]
    return first, (None if any(n is None for n in nxts) else max(nxts))


def q_design_system_release_reach_versions():
    """Adoption read from content: which registry version each installed file is, per consumer and per day."""
    hist, by_hash = ds_component_history()
    releases = ds_releases()
    today = date.fromisoformat(TODAY)
    consumers = {}
    for r in CONSUMERS:
        since = registry_declared(r)
        if not since:
            continue
        snaps = []  # (day, sha, {path: (first, superseded) | None}, kind)
        prev = None
        for day, sha, subj in consumer_pulls(r):
            inst = installed_at(r, sha)
            vers = {p: _version_of(h, by_hash) for p, h in inst.items()}
            newer = [p for p, v in vers.items() if v and (prev is None or p not in prev or prev[p] is None or v[0] > prev[p][0])]
            kind = "Registry pull" if newer else "Local edit"
            snaps.append((day, sha, vers, kind, len(newer)))
            prev = vers
        head_sha = main_log(r)[-1][1]
        head = {p: _version_of(h, by_hash) for p, h in installed_at(r, head_sha).items()}
        # lag on each day: days since the oldest publish that superseded something installed and was not taken
        lag_days, d = [], date.fromisoformat(since)
        while d <= today:
            day = d.isoformat()
            cur = next((s for s in reversed(snaps) if s[0] <= day), None)
            vers = cur[2] if cur else {}
            due = [v[1] for v in vers.values() if v and v[1] and v[1] <= day]
            lag_days.append((day, (d - date.fromisoformat(min(due))).days if due else 0))
            d += timedelta(1)
        matched = {p: v for p, v in head.items() if v}
        lags = [(today - date.fromisoformat(v[1])).days if v[1] else 0 for v in matched.values()]
        consumers[r] = dict(
            repo=r, since=since, snaps=[(s[0], s[3], s[4]) for s in snaps], lag_days=lag_days,
            n_installed=len(head), n_matched=len(matched), n_unmatched=len(head) - len(matched),
            n_current=sum(1 for l in lags if l == 0), lags=sorted(lags),
            median_lag=median(lags) if lags else None, max_lag=max(lags) if lags else None,
            group="Inactive product" if r in INACTIVE_CONSUMERS else "Active",
            pulls=sum(1 for s in snaps if s[3] == "Registry pull"), edits=sum(1 for s in snaps if s[3] == "Local edit"))
    # adoption of each release by each consumer that had one of its files installed on the day
    pairs = []
    for day, sha, paths in releases:
        for r, c in consumers.items():
            snaps = [s for s in consumer_pulls(r)]
            before = [s for s in snaps if s[0] <= day]
            if not before:
                continue
            inst = installed_at(r, before[-1][1])
            hits = {p for p in inst if any(os.path.basename(p) == os.path.basename(q) for q in paths)}
            if not hits:
                continue
            adopted = None
            for s in snaps:
                if s[0] < day:
                    continue
                vers = {p: _version_of(h, by_hash) for p, h in installed_at(r, s[1]).items() if p in hits}
                if vers and all(v and v[0] >= day for v in vers.values()):
                    adopted = s[0]
                    break
            pairs.append(dict(release=day, consumer=r, files=len(hits), adopted=adopted,
                              days=(date.fromisoformat(adopted) - date.fromisoformat(day)).days if adopted else None,
                              censored_at=(today - date.fromisoformat(day)).days if not adopted else None,
                              group=c["group"]))
    done = [p for p in pairs if p["days"] is not None]
    within = sum(1 for p in pairs if p["days"] is not None and p["days"] <= FRESH_DAYS)
    # only pairs old enough to have had the whole threshold can say whether they met it
    eligible = [p for p in pairs if (today - date.fromisoformat(p["release"])).days >= FRESH_DAYS]
    within_eligible = sum(1 for p in eligible if p["days"] is not None and p["days"] <= FRESH_DAYS)
    return dict(consumers=consumers, releases=[(d, s, sorted(ps)) for d, s, ps in releases], pairs=pairs,
                n_releases=len(releases), n_pairs=len(pairs), n_adopted=len(done), n_within=within,
                n_eligible=len(eligible), n_within_eligible=within_eligible,
                n_censored=sum(1 for p in pairs if p["days"] is None),
                adoption_median=median([p["days"] for p in done]) if done else None,
                releases_sep=sum(1 for d, _s, _p in releases if d >= "2026-09-01"),
                pulls_sep=sum(1 for c in consumers.values() for s in c["snaps"] if s[0] >= "2026-09-01" and s[1] == "Registry pull"),
                fresh_days=FRESH_DAYS, today=TODAY, n_paths=len(hist))


@lru_cache(maxsize=None)
def registry_index(day):
    """(install targets, item names) of the registry design-system served on `day`."""
    sha = sha_at(DS, day)
    if not sha:
        return frozenset(), frozenset()
    try:
        its = json.loads(git(DS, "show", f"{sha}:registry.json") or "{}").get("items", [])
    except json.JSONDecodeError:
        return frozenset(), frozenset()
    targets, names = set(), set()
    for it in its:
        names.add(it.get("name", ""))
        for f in it.get("files", []):
            if f.get("target"):
                targets.add(f["target"])
            names.add(os.path.splitext(os.path.basename(f.get("path", "")))[0])
    return frozenset(targets), frozenset(n for n in names if n)


def ui_census(repo, day):
    """Components in a consumer: installed where the registry puts them, a local primitive in
    components/ui, a local file named like a registry item but elsewhere (a re-implementation
    candidate), or a product component."""
    sha = sha_at(repo, day)
    targets, names = registry_index(day)
    if not sha or not names:
        return None
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", sha, "ui/src/components").splitlines()
             if f.endswith(".tsx") and not re.search(r"\.(test|stories)\.tsx$", f)]
    if not files:
        return None
    c = Counter()
    for f in files:
        rel = f[len("ui/src/"):]
        stem = os.path.splitext(os.path.basename(f))[0]
        if rel in targets:
            c["registry"] += 1
        elif rel.startswith("components/ui/"):
            c["local primitive"] += 1
        else:
            c["shadow" if stem in names else "product"] += 1
    return c


def q_registry_component_share_registry():
    cats = ["registry", "local primitive", "shadow", "product"]
    series = {k: [] for k in cats}
    for w in WEEKS:
        tot = Counter()
        if w >= "2026-W27":
            for r in CONSUMERS:
                c = ui_census(r, week_end(w))
                if c:
                    tot += c
        for k in cats:
            series[k].append(tot[k] if w >= "2026-W27" else None)
    by_repo = {}
    for r in CONSUMERS:
        vals = []
        for m in MONTHS:
            c = ui_census(r, min(month_end(m), TODAY)) if m >= "2026-07" else None
            prim = (c["registry"] + c["local primitive"] + c["shadow"]) if c else 0
            vals.append(c["registry"] / prim if c and prim else None)
        if any(v is not None for v in vals):
            by_repo[r] = vals
    now = {r: ui_census(r, TODAY) for r in CONSUMERS}
    first_decl = {}
    for r in CONSUMERS:
        log = main_log(r, "ui/components.json")
        for d, sha, _ in log:
            if "@aihero" in git(r, "show", f"{sha}:ui/components.json"):
                first_decl[r] = d
                break
    tot = Counter()
    for c in now.values():
        if c:
            tot += c
    prim = tot["registry"] + tot["local primitive"] + tot["shadow"]
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo, "now": {r: dict(c) if c else None for r, c in now.items()},
            "share_now": tot["registry"] / prim if prim else None, "tot": dict(tot), "first_declared": first_decl}


# ------------------------------------------------------------------ Q design-work-finders / Q design-divergence / Q divergence-outcomes / Q design-feedback-loop / Q human-only-verification items

def items(con):
    out = rows(con, """SELECT i.repo, i.item_id, i.title, i.type_raw, i.status, i.origin, i.created_ts, i.done_ts,
                              i.updated_ts, i.ready_ts, l.design, l.divergence, l.outcome, l.human_check, l.access
                       FROM plans.plan_items i JOIN connectors.item_labels l USING (repo, item_id)
                       WHERE i.type != 'goal'""")
    return [i for i in out if i["repo"] not in OUT_OF_SCOPE]


def closed_day(i):
    if i["status"] in ("done", "dropped", "delivered", "rejected"):
        return (i["done_ts"] or i["updated_ts"] or i["created_ts"] or "")[:10] or None
    return None


def connected_day(repo):
    """First day the repo's design connection named a claude.ai/design project read by a tool (not none, not manual)."""
    for d, _, c in hero_versions(repo):
        v = c.get("design")
        if v and v["state"] == "declared" and v["type"] != "target-repo" and design_reach_at(repo, d) in ("designsync", "auto"):
            return d
    return None


def q_design_work_finders_origin(con):
    its = [i for i in items(con) if i["design"] != "none" and i["created_ts"]]
    cats = ["Owner-instructed", "Agent-found", "Not recorded"]
    series = {c: [0] * len(WEEKS) for c in cats}
    for i in its:
        w = week_of(i["created_ts"])
        if w in WEEKS:
            series[who(i["origin"])][WEEKS.index(w)] += 1
    table = []
    for r in sorted({i["repo"] for i in its}):
        cd = connected_day(r)
        mine = [i for i in its if i["repo"] == r]
        pre = [i for i in mine if cd and i["created_ts"][:10] < cd]
        post = [i for i in mine if cd and i["created_ts"][:10] >= cd]
        share = lambda xs: (sum(1 for i in xs if who(i["origin"]) == "Agent-found") / len(xs)) if xs else None
        table.append({"repo": r, "connected": cd, "n": len(mine), "pre": len(pre), "post": len(post),
                      "agent_pre": share(pre), "agent_post": share(post),
                      "agent_all": share(mine)})
    allpre = [i for i in its if connected_day(i["repo"]) and i["created_ts"][:10] < connected_day(i["repo"])]
    allpost = [i for i in its if connected_day(i["repo"]) and i["created_ts"][:10] >= connected_day(i["repo"])]
    share = lambda xs: (sum(1 for i in xs if who(i["origin"]) == "Agent-found") / len(xs)) if xs else None
    return {"weeks": WEEKS, "series": series, "table": table, "n": len(its), "pre": len(allpre), "post": len(allpost),
            "agent_pre": share(allpre), "agent_post": share(allpost),
            "unconnected": sum(1 for i in its if not connected_day(i["repo"]))}


def q_design_divergence_backlog(con):
    its = [i for i in items(con) if i["divergence"] and i["created_ts"]]
    cats = ["Owner-instructed", "Agent-found", "Not recorded"]
    series = {c: [] for c in cats}
    for w in WEEKS:
        e = week_end(w)
        cnt = Counter(who(i["origin"]) for i in its if i["created_ts"][:10] <= e and
                      not (closed_day(i) and closed_day(i) <= e))
        for c in cats:
            series[c].append(cnt[c])
    by_repo = {}
    for r in sorted({i["repo"] for i in its}):
        vals = []
        for m in MONTHS:
            e = min(month_end(m), TODAY)
            vals.append(sum(1 for i in its if i["repo"] == r and i["created_ts"][:10] <= e and
                            not (closed_day(i) and closed_day(i) <= e)))
        by_repo[r] = vals
    who_n = Counter(who(i["origin"]) for i in its)
    per_repo = {r: Counter(who(i["origin"]) for i in its if i["repo"] == r) for r in by_repo}
    ages = [(date.fromisoformat(closed_day(i)) - date.fromisoformat(i["created_ts"][:10])).days
            for i in its if closed_day(i)]
    open_now = sum(1 for i in its if not closed_day(i))
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo, "who": dict(who_n), "per_repo": per_repo,
            "n": len(its), "open_now": open_now, "median_days_to_close": median(ages),
            "peak": max(sum(series[c][k] for c in cats) for k in range(len(WEEKS)))}


OUTCOMES = ["fixed-in-code", "decided-to-diverge", "asked-design", "duplicate", "dropped", "open"]


def q_divergence_outcomes_outcomes(con):
    its = [i for i in items(con) if i["divergence"] and i["created_ts"]]
    norm = lambda i: i["outcome"] if i["outcome"] in OUTCOMES else ("dropped" if i["outcome"] == "rejected" else "open")
    series = {o: [0] * len(WEEKS) for o in OUTCOMES if o != "open"}
    for i in its:
        cd = closed_day(i)
        o = norm(i)
        if cd and o in series and week_of(cd) in WEEKS:
            series[o][WEEKS.index(week_of(cd))] += 1
    shares = Counter(norm(i) for i in its)
    per_repo = {r: Counter(norm(i) for i in its if i["repo"] == r) for r in sorted({i["repo"] for i in its})}
    # a closed item the model called "open" (or an open one called closed) is reported, not hidden
    mismatch = sum(1 for i in its if bool(closed_day(i)) != (norm(i) != "open"))
    return {"weeks": WEEKS, "series": series, "shares": dict(shares), "per_repo": per_repo, "n": len(its),
            "mismatch": mismatch,
            "decided_examples": [i["title"] for i in its if norm(i) == "decided-to-diverge"][:6]}


SIGNAL_TYPES = ("signal", "design-feedback", "design-system-feedback", "architecture-feedback")


def feedback_packets():
    out = []
    for r in CONSUMERS + [DS]:
        d = os.path.join(path_of(r), ".plans", ".feedback")
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                m = re.match(r"(\d{4}-\d\d-\d\d)", f)
                if m and f.endswith(".md"):
                    out.append({"repo": r, "day": m.group(1)})
    return out


def design_notes():
    text = git(DS, "show", "HEAD:VERSION.md")
    tail = text.split("# Notes for the design project")[1] if "# Notes for the design project" in text else ""
    return [m.group(1) for m in re.finditer(r"^## (\d{4}-\d\d-\d\d) — ", tail, re.M)]


def q_design_feedback_loop_feedback(con):
    sig = rows(con, "SELECT repo, type_raw, status, created_ts, done_ts, updated_ts FROM plans.plan_items "
                    "WHERE type_raw IN (%s)" % ",".join(f"'{t}'" for t in SIGNAL_TYPES))
    closed = lambda s: s["status"] in ("done", "delivered")
    cats = ["Signal item, closed or delivered", "Signal item, still waiting", "Packet gathered", "Note in VERSION.md"]
    series = {c: [0] * len(WEEKS) for c in cats}
    for s in sig:
        if s["created_ts"] and week_of(s["created_ts"]) in WEEKS:
            series[cats[0] if closed(s) else cats[1]][WEEKS.index(week_of(s["created_ts"]))] += 1
    packets = feedback_packets()
    for p in packets:
        if week_of(p["day"]) in WEEKS:
            series[cats[2]][WEEKS.index(week_of(p["day"]))] += 1
    notes = design_notes()
    for d in notes:
        if week_of(d) in WEEKS:
            series[cats[3]][WEEKS.index(week_of(d))] += 1
    days = [(date.fromisoformat((s["done_ts"] or s["updated_ts"])[:10]) - date.fromisoformat(s["created_ts"][:10])).days
            for s in sig if closed(s) and (s["done_ts"] or s["updated_ts"]) and s["created_ts"]]
    per_repo = {}
    for s in sig:
        pr = per_repo.setdefault(s["repo"], {"n": 0, "closed": 0})
        pr["n"] += 1
        pr["closed"] += closed(s)
    for p in packets:
        per_repo.setdefault(p["repo"], {"n": 0, "closed": 0})
        per_repo[p["repo"]]["packets"] = per_repo[p["repo"]].get("packets", 0) + 1
    return {"weeks": WEEKS, "series": series, "n_signals": len(sig), "closed": sum(closed(s) for s in sig),
            "median_days": median(days), "packets": len(packets), "notes": len(notes), "per_repo": per_repo,
            "waiting": sum(not closed(s) for s in sig)}


def q_human_only_verification_human(con):
    its = [i for i in items(con) if i["created_ts"]]
    done = [i for i in its if i["status"] == "done" and i["done_ts"]]
    share = []
    for w in WEEKS:
        wk = [i for i in done if week_of(i["done_ts"]) == w]
        share.append(sum(i["human_check"] for i in wk) / len(wk) if len(wk) >= 3 else None)
    cnt = {"Needs a person with access": [0] * len(WEEKS), "Agent can verify": [0] * len(WEEKS)}
    for i in done:
        w = week_of(i["done_ts"])
        if w in WEEKS:
            cnt["Needs a person with access" if i["human_check"] else "Agent can verify"][WEEKS.index(w)] += 1

    def cycle(i):
        start = (i["ready_ts"] or i["created_ts"])[:10]
        return (date.fromisoformat(i["done_ts"][:10]) - date.fromisoformat(start)).days

    by_access = {}
    for i in done:
        if i["human_check"]:
            by_access.setdefault(i["access"] or "other", []).append(cycle(i))
    others = [cycle(i) for i in done if not i["human_check"]]
    hc = [i for i in its if i["human_check"]]
    return {"weeks": WEEKS, "counts": cnt, "share": share, "n": len(hc), "n_items": len(its),
            "done_share": sum(i["human_check"] for i in done) / len(done) if done else None,
            "by_access": {k: {"n": len(v), "median": median(v)} for k, v in by_access.items()},
            "median_human": median([cycle(i) for i in done if i["human_check"]]), "median_other": median(others),
            "open_human": sum(1 for i in hc if i["status"] not in ("done", "dropped")),
            "per_repo": Counter(i["repo"] for i in hc)}


# ------------------------------------------------------------------ Q unreachable-connections unreachable connections

def q_unreachable_connections_failures(con):
    errs = rows(con, """SELECT t.session_id_hash sid, t.ts, s.repo FROM harness.tool_calls t
                        JOIN harness.sessions s USING (session_id_hash)
                        WHERE t.tool = 'DesignSync' AND t.is_error = 1 ORDER BY t.ts""")
    cases = []
    for e in errs:
        nxt = rows(con, """SELECT text_redacted FROM harness.turns WHERE session_id_hash = ? AND ts > ? AND role = 'assistant'
                           AND text_redacted != '' ORDER BY ts LIMIT 2""", (e["sid"], e["ts"]))
        later_ok = rows(con, """SELECT COUNT(*) n FROM harness.tool_calls WHERE session_id_hash = ? AND tool = 'DesignSync'
                                AND ts > ? AND is_error = 0""", (e["sid"], e["ts"]))[0]["n"]
        text = " ".join(n["text_redacted"] for n in nxt).lower()
        if later_ok:
            what = "Retried and read it"
        elif re.search(r"unauthori|not authori|isn't authori|dropped the design|failed target read|can't verify|"
                       r"design authorization|/design-login", text):
            what = "Said so, went on without it"
        elif re.search(r"design-project|config gate|no design", text):
            what = "Asked to set the connection up"
        elif not text:
            what = "Nothing logged after"
        else:
            what = "Carried on silently"
        cases.append({"day": e["ts"][:10], "repo": e["repo"], "what": what,
                      "login_cause": "/login" in text})
    total = rows(con, "SELECT COUNT(*) n FROM harness.tool_calls WHERE tool = 'DesignSync'")[0]["n"]
    return {"cases": cases, "n": len(cases), "total_calls": total, "by_what": Counter(c["what"] for c in cases),
            "login_cause": sum(c["login_cause"] for c in cases)}


# ------------------------------------------------------------------ Q expired-logins credential waits

MONTHS_LONG = ["2025-11", "2025-12"] + MONTHS


def q_expired_logins_credentials(con):
    lab = rows(con, """SELECT p.ts, p.day, p.repo, l.system FROM connectors.prompt_labels l
                       JOIN harness.prompts p ON l.prompt_key = p.ts || '|' || p.repo WHERE l.cred = 1""")
    systems = ["aws-terraform", "github", "secrets-manager", "third-party", "browser-signin", "design-account", "other"]
    monthly = {s: [0] * len(MONTHS_LONG) for s in systems}
    for r in lab:
        m = r["day"][:7]
        if m in MONTHS_LONG:
            monthly[r["system"] if r["system"] in systems else "other"][MONTHS_LONG.index(m)] += 1
    turns = rows(con, """SELECT t.session_id_hash sid, t.ts, t.role, s.repo FROM harness.turns t
                         JOIN harness.sessions s USING (session_id_hash)
                         WHERE t.is_synthetic = 0 ORDER BY t.ts""")
    to_dt = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
    by_sid, by_repo_a, users = defaultdict(list), defaultdict(list), []
    for t in turns:
        if t["role"] == "assistant":
            by_sid[t["sid"]].append(t["ts"])
            by_repo_a[t["repo"]].append(t["ts"])
        else:
            users.append((to_dt(t["ts"]), t["sid"], t["ts"]))
    import bisect
    waits = []
    for r in lab:
        if r["ts"] < "2026-08-09" or week_of(r["day"]) in NA_WEEKS:
            continue
        b = to_dt(r["ts"])
        # the typed prompt, matched to its logged user turn (same moment) to find its session;
        # a slash command (/login) is not logged as a turn, so it falls back to the repo's last turn
        sid = next((u[1] for u in users if abs((u[0] - b).total_seconds()) < 5), None)
        pool = by_sid.get(sid) if sid else by_repo_a.get(r["repo"])
        if not pool:
            continue
        k = bisect.bisect_left(pool, b.strftime("%Y-%m-%dT%H:%M:%S")) - 1
        if k < 0:
            continue
        h = (b - to_dt(pool[k])).total_seconds() / 3600
        # a gap over 8 hours means the session was closed, not that work waited (brief's session rule)
        if 0 <= h <= 8:
            waits.append({"system": r["system"], "hours": h, "repo": r["repo"], "matched": bool(sid)})
    per_repo = Counter(r["repo"] for r in lab)
    by_sys_wait = defaultdict(list)
    for w in waits:
        by_sys_wait[w["system"]].append(w["hours"])
    return {"months": MONTHS_LONG, "monthly": monthly, "n": len(lab), "per_repo": dict(per_repo),
            "waits": waits, "median_wait_min": median([w["hours"] * 60 for w in waits]),
            "by_system": dict(Counter(r["system"] for r in lab)),
            "wait_by_system": {s: {"n": len(v), "median_min": median([x * 60 for x in v])} for s, v in by_sys_wait.items()},
            "since_aug": sum(1 for r in lab if r["day"] >= "2026-08-09")}


def all_data(con):
    return {
        "q_declared_connections": q_declared_connections_declared(), "q_connections_read_by_skills": q_connections_read_by_skills_readers(), "q_connection_reach_in_use": q_connection_reach_in_use_reach(con), "q_wrong_declared_reach": q_wrong_declared_reach_corrections(con),
        "q_copied_connector_values": q_copied_connector_values_copies(), "q_design_work_finders": q_design_work_finders_origin(con), "q_design_snapshot_lag": q_design_snapshot_lag_snapshot(), "q_design_system_release_reach": q_design_system_release_reach_adoption(),
        "q_design_system_release_reach_versions": q_design_system_release_reach_versions(),
        "q_registry_component_share": q_registry_component_share_registry(), "q_design_divergence": q_design_divergence_backlog(con), "q_divergence_outcomes": q_divergence_outcomes_outcomes(con), "q_design_feedback_loop": q_design_feedback_loop_feedback(con),
        "q_unreachable_connections": q_unreachable_connections_failures(con), "q_expired_logins": q_expired_logins_credentials(con), "q_human_only_verification": q_human_only_verification_human(con),
    }


if __name__ == "__main__":
    from cube.db import connect
    con = connect("connectors")
    d = all_data(con)

    def slim(x):
        if isinstance(x, dict):
            return {k: slim(v) for k, v in x.items() if k not in ("weeks", "series", "by_repo", "days", "behind",
                                                                   "monthly", "counts", "share", "behind_weekly", "months")}
        if isinstance(x, list) and len(x) > 12:
            return x[:12] + [f"... {len(x)} total"]
        return x
    print(json.dumps(slim(d), indent=1, default=str))
