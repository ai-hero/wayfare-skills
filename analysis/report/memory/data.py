"""Knowledge and memory series: knowledge and memory. One function per question; each returns what
its answer slide (and breakdown slide) plots.

Repo snapshots are read from the bare mirrors in .analysis/data/mirrors (read-only
`git ls-tree` / `git cat-file` at the last default-branch commit of each week or month).
Memory files are read in place under ~/.claude/projects/*/memory (read-only).

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/memory/data.py
"""
import glob
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ANALYSIS)
sys.path.insert(0, os.path.dirname(HERE))
from cube.db import connect  # noqa: E402
import record as F  # noqa: E402

DATA = os.path.join(os.path.dirname(ANALYSIS), ".analysis", "data")
MIRRORS = os.path.join(DATA, "mirrors")
PLUGIN_MIRROR = os.path.join(MIRRORS, "wayfare-skills.git")
LATEST_WEEK = 39
WEEKS = [f"2026-W{w:02d}" for w in range(1, LATEST_WEEK + 1)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
TODAY = "2026-09-24"
# 10-24 Aug: no Claude Code session logs. Only session-derived series (sessions, spend) are
# affected; plan logs, git and memory files are not, so they are charted as recorded.
NO_SESSION_DATA = ("2026-08-10", "2026-08-24")
APPS = ("app", "app, no features yet")


def week_end(w):
    d = date.fromisocalendar(int(w[:4]), int(w[6:]), 7)
    return min(d.isoformat(), TODAY)


def month_end(m):
    y, mo = int(m[:4]), int(m[5:])
    d = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(1)
    return min(d.isoformat(), TODAY)


# ------------------------------------------------------------------ git snapshots

# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, f"{repo}.git"), *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


@lru_cache(maxsize=None)
def blob(repo, oid):
    return git(repo, "cat-file", "-p", oid)


@lru_cache(maxsize=None)
def main_shas(repo):
    """(day, sha) of every default-branch commit, oldest first, from the git ingest."""
    con = _con()
    return [(r[0], r[1]) for r in con.execute(
        "SELECT day, sha FROM git.commits WHERE repo = ? ORDER BY committed_ts", (repo,))]


def sha_at(repo, day):
    last = None
    for d, sha in main_shas(repo):
        if d <= day:
            last = sha
        else:
            break
    return last


@lru_cache(maxsize=None)
def tree(repo, sha):
    """{path: (mode, oid, size)} for the knowledge files at a commit."""
    out = {}
    for line in git(repo, "ls-tree", "-r", "-l", sha, "--", "AGENTS.md", "CLAUDE.md", "HERO.md", "DESIGN.md",
                    ".claude/rules", ".claude/skills", ".github/workflows", ".pre-commit-config.yaml").splitlines():
        meta, path = line.split("\t", 1)
        mode, _, oid, size = meta.split()
        out[path] = (mode, oid, int(size) if size.isdigit() else 0)
    return out


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def description_bytes(text):
    fm, _ = frontmatter(text)
    m = re.search(r"^description:\s*(.*?)(?=^\S|\Z)", fm, re.S | re.M)
    return len(m.group(1).strip().encode()) if m else 0


@lru_cache(maxsize=None)
def loaded(repo, sha):
    """Bytes an agent loads at session start in this repo, and bytes it can load on demand."""
    t = tree(repo, sha)
    always, demand = 0, 0
    claude, agents = t.get("CLAUDE.md"), t.get("AGENTS.md")
    if claude and claude[0] == "120000":
        always += agents[2] if agents else 0
    elif claude:
        text = blob(repo, claude[1])
        always += len(text.encode())
        if agents and "@AGENTS.md" in text:
            always += agents[2]
    for path, (mode, oid, size) in t.items():
        if path.startswith(".claude/rules/") and path.endswith(".md"):
            if re.search(r"^paths:", frontmatter(blob(repo, oid))[0], re.M):
                demand += size
            else:
                always += size
        elif path.startswith(".claude/skills/") and path.endswith("SKILL.md"):
            d = description_bytes(blob(repo, oid))
            always += d
            demand += size - d
    for doc in ("HERO.md", "DESIGN.md"):
        if doc in t:
            demand += t[doc][2]
    return always, demand


@lru_cache(maxsize=None)
def plugin_skills(day):
    """wayfare's skills on a day: (description bytes, on-demand bytes, skill count). On demand is every
    other markdown file under skills/ and references/ (skills' references moved there on 22 Sep)."""
    p = subprocess.run(["git", "-C", PLUGIN_MIRROR, "rev-list", "-1", f"--before={day}T23:59:59", "HEAD"],
                       capture_output=True, text=True)
    sha = p.stdout.strip()
    if not sha:
        return 0, 0, 0
    desc = body = n = 0
    ls = subprocess.run(["git", "-C", PLUGIN_MIRROR, "ls-tree", "-r", "-l", sha, "--", "skills", "references"],
                        capture_output=True, text=True).stdout
    for line in ls.splitlines():
        meta, path = line.split("\t", 1)
        oid, size = meta.split()[2], int(meta.split()[3])
        if not path.endswith("/SKILL.md") or path.count("/") != 2:
            if path.endswith(".md"):
                body += size
            continue
        text = subprocess.run(["git", "-C", PLUGIN_MIRROR, "cat-file", "-p", oid], capture_output=True,
                              text=True).stdout
        d = description_bytes(text)
        desc, body, n = desc + d, body + size - d, n + 1
    return desc, body, n


# ------------------------------------------------------------------ shared

_CON = {}


def _con():
    if "c" not in _CON:
        _CON["c"] = connect("memory")
    return _CON["c"]


def rows(sql, args=()):
    return [dict(r) for r in _con().execute(sql, args).fetchall()]


def repos_in_scope():
    return F.adoption(_con())


def exists_on(repo, day):
    return repos_in_scope()[repo]["first"] <= day


def median(v):
    return round(statistics.median(v), 1) if v else None


# ------------------------------------------------------------------ Q knowledge-stores stores

def first_items():
    """First work item per repo. A repo whose items carry no date counts as present today, date unknown."""
    return {r["repo"]: r["d"] or TODAY for r in rows("SELECT repo, MIN(day) d FROM plans.plan_items GROUP BY repo")}

@lru_cache(maxsize=None)
def session_start():
    import hashlib
    first = {r["h"]: r["d"] for r in rows("SELECT session_id_hash h, SUBSTR(first_ts,1,10) d FROM harness.sessions")}
    out = {}
    base = os.path.expanduser("~/.claude/projects")
    for f in glob.glob(os.path.join(base, "*", "memory", "*.md")):
        m = re.search(r"originSessionId:\s*(\S+)", open(f, errors="replace").read())
        if m:
            out[m.group(1)] = first.get(hashlib.sha256(m.group(1).encode()).hexdigest()[:16])
    return out


@lru_cache(maxsize=None)
def memory_files():
    """Memory files on this machine mapped to fleet repos (MEMORY.md, the index, excluded)."""
    ad = repos_in_scope()
    out = []
    base = os.path.expanduser("~/.claude/projects")
    for d in glob.glob(os.path.join(base, "*")):
        name = os.path.basename(d)
        m = re.match(r"^-Users-[^-]+-workspaces-aihero-(.+)$", name)
        repo = m.group(1) if m else ("wayfare-skills" if re.search(r"claude-plugins-(hero|wayfare)-skills$", name)
                                     else "fleet folder" if name.endswith("-workspaces-aihero") else None)
        if repo == "hero-skills":
            repo = "wayfare-skills"
        if repo is None or (repo not in ad and repo != "fleet folder"):
            continue
        for f in glob.glob(os.path.join(d, "memory", "*.md")):
            if os.path.basename(f) == "MEMORY.md":
                continue
            raw = open(f, errors="replace").read()
            fm, body = frontmatter(raw)
            t = re.search(r"^\s*type:\s*(\w+)", fm, re.M)
            born = datetime.fromtimestamp(os.stat(f).st_birthtime, tz=timezone.utc).date().isoformat()
            # Files are rewritten in bulk, so a whole folder can share one birth time; the earliest of
            # birth, the recorded `modified` and the originating session's start is used.
            mod = re.search(r"^\s*modified:\s*(\d{4}-\d\d-\d\d)", fm, re.M)
            sess = re.search(r"^\s*originSessionId:\s*(\S+)", fm, re.M)
            cands = [born] + ([mod.group(1)] if mod else []) + ([session_start().get(sess.group(1))] if sess else [])
            born = min(c for c in cands if c)
            out.append({"repo": repo, "file": os.path.basename(f), "day": born, "week": F.week_of(born),
                        "month": born[:7], "type": t.group(1) if t else "untyped", "bytes": len(raw.encode()),
                        "why": bool(re.search(r"\*\*Why[:*]", body)),
                        "links": len(re.findall(r"\[[^\]]+\]\([^)]+\)", body)) + len(re.findall(r"\[\[[^\]]+\]\]", body))})
    return out


STORE_KEYS = ["Agent instructions", "HERO.md", "DESIGN.md", "Rules", ".plans (local)", "Memory (local)"]


def q_knowledge_stores_stores():
    ad = repos_in_scope()
    first_item = first_items()
    first_mem = {}
    for m in memory_files():
        if m["day"] < first_mem.get(m["repo"], "9999"):
            first_mem[m["repo"]] = m["day"]
    series = {k: [] for k in STORE_KEYS}
    series["Repos in the fleet"] = []
    grid = {}
    for w in WEEKS:
        day = week_end(w)
        counts = Counter()
        n = 0
        for repo in ad:
            if not exists_on(repo, day):
                continue
            n += 1
            sha = sha_at(repo, day)
            t = tree(repo, sha) if sha else {}
            has = {
                "Agent instructions": "AGENTS.md" in t or "CLAUDE.md" in t,
                "HERO.md": "HERO.md" in t, "DESIGN.md": "DESIGN.md" in t,
                "Rules": any(p.startswith(".claude/rules/") for p in t),
                ".plans (local)": first_item.get(repo, "9999") <= day,
                "Memory (local)": first_mem.get(repo, "9999") <= day,
            }
            for k, v in has.items():
                counts[k] += v
                if v and (repo, k) not in grid:
                    grid[(repo, k)] = day
        for k in STORE_KEYS:
            series[k].append(counts[k])
        series["Repos in the fleet"].append(n)
    now = {k: series[k][-1] for k in series}
    return {"weeks": WEEKS, "series": series, "now": now, "grid": grid, "repos": sorted(ad),
            "n_mem_fleet_folder": sum(m["repo"] == "fleet folder" for m in memory_files())}


# ------------------------------------------------------------------ Q startup-instruction-size standing instructions

def q_startup_instruction_size_loaded():
    ad = repos_in_scope()
    apps = [r for r in ad if ad[r]["category"] in APPS]
    med_always, med_demand, plugin_desc, plugin_body, plugin_n = [], [], [], [], []
    per_repo_week = {r: [] for r in apps}
    per_repo_month = defaultdict(dict)
    for w in WEEKS:
        day = week_end(w)
        pd, pb, pn = plugin_skills(day)
        plugin_desc.append(round(pd / 1024, 1))
        plugin_body.append(round(pb / 1024, 1))
        plugin_n.append(pn)
        a_vals, d_vals = [], []
        for repo in apps:
            if not exists_on(repo, day):
                per_repo_week[repo].append(None)
                continue
            sha = sha_at(repo, day)
            a, d = loaded(repo, sha)
            a_vals.append((a + pd) / 1024)
            per_repo_week[repo].append(round((a + pd) / 1024, 1))
            d_vals.append((d + pb) / 1024)
        med_always.append(median(a_vals))
        med_demand.append(median(d_vals))
    for m in MONTHS:
        day = month_end(m)
        pd = plugin_skills(day)[0]
        for repo in ad:
            if not exists_on(repo, day):
                continue
            a, _ = loaded(repo, sha_at(repo, day))
            per_repo_month[repo][m] = round((a + pd) / 1024, 1)
    now = {repo: loaded(repo, sha_at(repo, TODAY)) for repo in ad}
    return {"weeks": WEEKS, "always": med_always, "demand": med_demand, "plugin_desc": plugin_desc,
            "plugin_body": plugin_body, "plugin_n": plugin_n, "per_repo_month": per_repo_month,
            "per_repo_week": per_repo_week, "rules_scoped": rules_scoped(apps),
            "now": {r: (round(a / 1024, 1), round(d / 1024, 1)) for r, (a, d) in now.items()}}


def rules_scoped(repos):
    """Share of .claude/rules bytes with a `paths:` scope, across repos, at a few dates."""
    out = {}
    for day in ("2026-07-31", "2026-08-28", "2026-09-05", TODAY):
        sc = tot = 0
        for repo in repos:
            if not exists_on(repo, day):
                continue
            for path, (mode, oid, size) in tree(repo, sha_at(repo, day)).items():
                if path.startswith(".claude/rules/") and path.endswith(".md"):
                    tot += size
                    sc += size if re.search(r"^paths:", frontmatter(blob(repo, oid))[0], re.M) else 0
        out[day] = round(sc / tot, 3) if tot else None
    return out


# ------------------------------------------------------------------ Q stale-prose-fixes prose corrections

def comment_rule_arrival():
    return {r["repo"]: r["d"] for r in rows("""
        SELECT c.repo, MIN(c.day) d FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha
        WHERE f.path = '.claude/rules/comments.md' GROUP BY c.repo""")}


def q_stale_prose_fixes_prose():
    lab = {r["cs_key"]: r for r in rows("""SELECT l.cs_key, c.k, c.w, c.z, c.m FROM memory.prose_labels l
                                           JOIN memory.prose_cache c ON c.h = l.h""")}
    facts = [s for s in F.changeset_facts(_con()) if not s["dependabot"]]
    rule = comment_rule_arrival()
    kinds = {"i": "Agent instructions", "d": "Docs", "c": "Code comments"}
    by_kind = {v: defaultdict(int) for v in kinds.values()}
    whole = defaultdict(int)
    rider = defaultdict(int)
    total = defaultdict(int)
    comments_rule = {"with the rule": [defaultdict(int), defaultdict(int)],
                     "without the rule": [defaultdict(int), defaultdict(int)]}
    per_repo = defaultdict(lambda: defaultdict(int))
    per_repo_total = defaultdict(lambda: defaultdict(int))
    misled = 0
    corrections = []
    for s in facts:
        key = f"{s['repo']}|{s['unit_kind']}|{s['unit_id']}|{s['set_idx']}"
        total[s["week"]] += 1
        per_repo_total[s["repo"]][s["month"]] += 1
        grp = "with the rule" if rule.get(s["repo"], "9999") <= s["day"] else "without the rule"
        comments_rule[grp][1][s["week"]] += 1
        l = lab.get(key)
        if not l or l["k"] not in kinds:
            continue
        by_kind[kinds[l["k"]]][s["week"]] += 1
        (whole if l["w"] else rider)[s["week"]] += 1
        per_repo[s["repo"]][s["month"]] += 1
        if l["k"] == "c":
            comments_rule[grp][0][s["week"]] += 1
        misled += l["m"]
        corrections.append({**{k: s[k] for k in ("repo", "day", "label", "pr")}, "k": l["k"], "w": l["w"]})
    per100 = lambda num, den: [round(100 * num[w] / den[w], 1) if den[w] >= 5 else None for w in WEEKS]
    n = len(corrections)
    months_share = {}
    for repo in per_repo_total:
        tot = sum(per_repo_total[repo].values())
        if tot >= 40:
            months_share[repo] = {m: round(100 * per_repo[repo][m] / per_repo_total[repo][m], 1)
                                  if per_repo_total[repo][m] >= 5 else None for m in MONTHS}
    mt, mc = Counter(s["month"] for s in facts), Counter(c["day"][:7] for c in corrections)
    span = lambda keep: round(100 * sum(mc[m] for m in mt if keep(m)) / max(1, sum(mt[m] for m in mt if keep(m))), 1)
    rate_before, rate_after = span(lambda m: m < "2026-07"), span(lambda m: m >= "2026-08")
    self_cite = [c for c in corrections if re.search(r"made false by #\d+|falsified|#\d+ (broke|made)", c["label"] or "", re.I)]
    return {
        "weeks": WEEKS,
        "by_kind": {k: [v[w] for w in WEEKS] for k, v in by_kind.items()},
        "whole": [whole[w] for w in WEEKS], "rider": [rider[w] for w in WEEKS],
        "per100": per100({w: sum(by_kind[k][w] for k in by_kind) for w in WEEKS}, total),
        "comments_per100": {g: per100(v[0], v[1]) for g, v in comments_rule.items()},
        "comments_n": {g: sum(v[0].values()) for g, v in comments_rule.items()},
        "comments_sets": {g: sum(v[1].values()) for g, v in comments_rule.items()},
        "n": n, "n_whole": sum(c["w"] for c in corrections), "n_sets": len(facts),
        "n_kind": Counter(kinds[c["k"]] for c in corrections), "misled": misled,
        "per_repo_month": months_share, "rule": rule, "n_candidates": len(lab),
        "noise_trims": sum(1 for l in lab.values() if l["z"]),
        "self_cite": self_cite, "rate_before_jul": rate_before, "rate_since_aug": rate_after,
        "by_stage": Counter(F.stage_of(_con(), c["repo"], c["day"]) for c in corrections),
        "sets_by_stage": Counter(s["stage"] for s in facts),
    }


# ------------------------------------------------------------------ Q work-item-log-contents item logs

LOG_KINDS = ["note", "mistake", "decision", "turn", "other"]


def q_work_item_log_contents_logs():
    logs = rows("SELECT repo, item_id, SUBSTR(ts,1,10) day, kind FROM plans.item_logs WHERE ts IS NOT NULL")
    ad = repos_in_scope()
    logs = [l for l in logs if l["repo"] in ad]
    by = {k: defaultdict(int) for k in LOG_KINDS}
    items = defaultdict(set)
    for l in logs:
        w = F.week_of(l["day"])
        by[l["kind"] if l["kind"] in LOG_KINDS else "other"][w] += 1
        items[w].add((l["repo"], l["item_id"]))
    per_item = [round(sum(by[k][w] for k in LOG_KINDS) / len(items[w]), 1) if items[w] else None
                for w in WEEKS]
    since = "2026-09-18"
    mistakes = defaultdict(lambda: [0, set()])
    for l in logs:
        if l["day"] >= since:
            mistakes[l["repo"]][1].add(l["item_id"])
            if l["kind"] == "mistake":
                mistakes[l["repo"]][0] += 1
    mist = {r: (v[0], len(v[1])) for r, v in mistakes.items() if len(v[1]) >= 3}
    kinds_all = Counter(l["kind"] for l in logs)
    first = {k: min(l["day"] for l in logs if l["kind"] == k) for k in kinds_all}
    items_logged = len({(l["repo"], l["item_id"]) for l in logs})
    items_total = rows("SELECT COUNT(*) n FROM plans.plan_items")[0]["n"]
    mistake_items = len({(l["repo"], l["item_id"]) for l in logs if l["kind"] == "mistake"})
    items_since = len({(l["repo"], l["item_id"]) for l in logs if l["day"] >= since})
    return {"weeks": WEEKS, "by_kind": {k: [by[k][w] for w in WEEKS] for k in LOG_KINDS}, "per_item": per_item,
            "mistakes_by_repo": mist, "kinds": kinds_all, "first": first, "n": len(logs),
            "items_logged": items_logged, "items_total": items_total, "mistake_items": mistake_items,
            "items_since": items_since}


# ------------------------------------------------------------------ Q memory-growth memory

MEM_TYPES = ["feedback", "project", "reference", "user", "untyped"]


def q_memory_growth_memory():
    mem = memory_files()
    cum = {t: [] for t in MEM_TYPES}
    why_share, link_share = [], []
    for w in WEEKS:
        day = week_end(w)
        upto = [m for m in mem if m["day"] <= day]
        for t in MEM_TYPES:
            cum[t].append(sum(1 for m in upto if (m["type"] if m["type"] in MEM_TYPES else "untyped") == t))
        why_share.append(round(sum(m["why"] for m in upto) / len(upto), 3) if upto else None)
        link_share.append(round(sum(m["links"] > 0 for m in upto) / len(upto), 3) if upto else None)
    by_repo = defaultdict(dict)
    counts = Counter(m["repo"] for m in mem)
    for repo in counts:
        for mo in MONTHS:
            by_repo[repo][mo] = sum(1 for m in mem if m["repo"] == repo and m["month"] <= mo)
    added = defaultdict(int)
    for m in mem:
        added[m["week"]] += 1
    return {"weeks": WEEKS, "cum": cum, "why_share": why_share, "link_share": link_share, "by_repo": by_repo,
            "counts": counts, "n": len(mem), "types": Counter(m["type"] for m in mem),
            "why": sum(m["why"] for m in mem), "links": sum(m["links"] > 0 for m in mem),
            "added": [added[w] for w in WEEKS], "kb": round(sum(m["bytes"] for m in mem) / 1024),
            "ingest_rows": rows("SELECT COUNT(*) n, SUM(type IS NOT NULL) typed FROM harness.memories")[0],
            "first": min(m["day"] for m in mem)}


# ------------------------------------------------------------------ Q work-item-cost-record cost readable

def _items():
    out = []
    for r in rows("SELECT repo, item_id, type, day, origin, raw_frontmatter_json fm FROM plans.plan_items"):
        fm = json.loads(r["fm"] or "{}")
        r["fmd"] = fm
        r["week"] = F.week_of(r["day"]) if r["day"] else None
        out.append(r)
    return out


COST_KEYS = ["Goal with a turn budget", "Item with a PR or commit ledger", "Neither"]


def q_work_item_cost_record_cost():
    items = [i for i in _items() if i["week"]]
    by = {k: defaultdict(int) for k in COST_KEYS}
    repo_share = defaultdict(lambda: [0, 0])
    spend_keys = Counter()
    for i in items:
        fm = i["fmd"]
        for k in fm:
            if re.search(r"cost|spend|usd|token|dollar", k, re.I):
                spend_keys[k] += 1
        if fm.get("budget") is not None or fm.get("budget_max") is not None:
            k = COST_KEYS[0]
        elif fm.get("pr") or fm.get("commits") or fm.get("branch"):
            k = COST_KEYS[1]
        else:
            k = COST_KEYS[2]
        by[k][i["week"]] += 1
        repo_share[i["repo"]][0] += k != COST_KEYS[2]
        repo_share[i["repo"]][1] += 1
    budget_types = Counter(i["type"] for i in items if i["fmd"].get("budget") is not None)
    ss = rows("SELECT attribution_confidence a, COUNT(*) n, SUM(cost_usd) usd FROM detectors.session_spend GROUP BY 1")
    return {"weeks": WEEKS, "by": {k: [v[w] for w in WEEKS] for k, v in by.items()},
            "repo_share": {r: round(v[0] / v[1], 3) for r, v in repo_share.items() if v[1] >= 10},
            "repo_n": {r: v[1] for r, v in repo_share.items()},
            "spend_keys": spend_keys, "budget_types": budget_types, "n": len(items),
            "n_by": {k: sum(v.values()) for k, v in by.items()}, "session_spend": ss}


# ------------------------------------------------------------------ Q plan-store-authors who writes the store

ORIGIN_GROUPS = [
    ("Planning skills", {"wayfare", "wayfare-grill-idea", "think-it-through", "wayfare-sync-plan", "conversation"}),
    ("Security audit", {"harden"}),
    ("One-shot builds", {"one-shot", "wayfare-build-task", "wayfare-run-task", "self-review"}),
    ("Owner by name", {"rahul", "user"}),
    ("Mailbox", {"message"}),
]
OWNER_RE = re.compile(r"\b(by|from) (rahul|the user|the owner)\b|user's (decision|instruction|call|choice)|"
                      r"owner's (decision|instruction|call|choice)|(user|owner|rahul) (approved|asked|said|decided|"
                      r"chose|confirmed|declined|vetoed|wants|instructed|redirected)|on the (user|owner)'s instruction|"
                      r"confirmed by rahul|per (the )?(user|owner|rahul)", re.I)


def origin_group(o):
    for name, keys in ORIGIN_GROUPS:
        if (o or "") in keys:
            return name
    return "Not recorded"


def q_plan_store_authors_writers():
    items = [i for i in _items() if i["week"]]
    groups = [g for g, _ in ORIGIN_GROUPS] + ["Not recorded"]
    by = {g: defaultdict(int) for g in groups}
    for i in items:
        by[origin_group(i["origin"])][i["week"]] += 1
    logs = rows("SELECT repo, SUBSTR(ts,1,10) day, kind, text_redacted t FROM plans.item_logs WHERE ts IS NOT NULL")
    owner = defaultdict(int)
    alllog = defaultdict(int)
    examples = []
    for l in logs:
        w = F.week_of(l["day"])
        alllog[w] += 1
        if OWNER_RE.search(l["t"] or ""):
            owner[w] += 1
            if len(examples) < 400:
                examples.append((l["repo"], l["day"], (l["t"] or "")[:160]))
    share = [round(owner[w] / alllog[w], 3) if alllog[w] >= 20 else None for w in WEEKS]
    per_repo = defaultdict(Counter)
    for i in items:
        per_repo[i["repo"]][origin_group(i["origin"])] += 1
    dropped = rows("SELECT COUNT(*) n FROM plans.plan_items WHERE status IN ('dropped')")[0]["n"]
    return {"weeks": WEEKS, "by": {g: [by[g][w] for w in WEEKS] for g in groups}, "owner_share": share,
            "owner_n": sum(owner.values()), "log_n": sum(alllog.values()), "groups": groups,
            "per_repo": per_repo, "n": len(items), "n_by": {g: sum(v.values()) for g, v in by.items()},
            "dropped": dropped, "examples": examples}


# ------------------------------------------------------------------ Q observable-repo-facts observable signals

HEALTH_RE = r"/(livez|readyz|healthz|health)([^a-zA-Z]|$)"
SIGNALS = ["CI workflows", "Pre-commit gate", "Health endpoint", "HERO.md connections", "Work-item store"]


@lru_cache(maxsize=None)
def has_health(repo, sha):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, f"{repo}.git"), "grep", "-l", "-E", HEALTH_RE, sha,
                        "--", "*.go", "*.ts", "*.tsx", "*.py", "*.js", "*.yaml", "*.yml", "Dockerfile*", "*.tf"],
                       capture_output=True, text=True)
    return bool(p.stdout.strip())


@lru_cache(maxsize=None)
def has_connections(repo, sha):
    t = tree(repo, sha)
    return "HERO.md" in t and "## Connections" in blob(repo, t["HERO.md"][1])


def q_observable_repo_facts_signals():
    ad = repos_in_scope()
    first_item = first_items()
    series = {s: [] for s in SIGNALS}
    series["Repos in the fleet"] = []
    grid = {}
    for m in MONTHS:
        day = month_end(m)
        n = 0
        c = Counter()
        for repo in ad:
            if not exists_on(repo, day):
                continue
            n += 1
            sha = sha_at(repo, day)
            t = tree(repo, sha)
            has = {"CI workflows": any(p.startswith(".github/workflows/") for p in t),
                   "Pre-commit gate": ".pre-commit-config.yaml" in t,
                   "Health endpoint": has_health(repo, sha),
                   "HERO.md connections": has_connections(repo, sha),
                   "Work-item store": first_item.get(repo, "9999") <= day}
            for k, v in has.items():
                c[k] += v
                if m == MONTHS[-1]:
                    grid[(repo, k)] = v
        for s in SIGNALS:
            series[s].append(c[s])
        series["Repos in the fleet"].append(n)
    return {"months": MONTHS, "series": series, "grid": grid, "repos": sorted(ad)}


# ------------------------------------------------------------------ all

def all_data():
    return {"knowledge-stores": q_knowledge_stores_stores(), "startup-instruction-size": q_startup_instruction_size_loaded(), "stale-prose-fixes": q_stale_prose_fixes_prose(), "work-item-log-contents": q_work_item_log_contents_logs(),
            "memory-growth": q_memory_growth_memory(), "work-item-cost-record": q_work_item_cost_record_cost(), "plan-store-authors": q_plan_store_authors_writers(), "observable-repo-facts": q_observable_repo_facts_signals()}


if __name__ == "__main__":
    import pprint
    d = all_data()
    for k, v in d.items():
        print("=" * 20, k)
        pprint.pprint({a: b for a, b in v.items() if a not in ("examples", "grid")}, width=160, compact=True)
