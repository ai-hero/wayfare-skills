"""Compliance and drift data: compliance and drift. One function per question; each returns the series its slides plot.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/compliance/data.py     # print every answer

The audit series comes from register.py (committed CONSISTENCY.md versions, read with git show).
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import register as R  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
NOW = "2026-09-24"
SEVS = ["high", "medium", "low"]
# `critical` has a deadline although no control carries it, so a control raised to it is scored, not dropped.
DEADLINES = {"critical": 3, "high": 14, "medium": 30, "low": 90}
FOUNDING = ["hero-template", "auth", "website", "hiro", "design-system"]
CLONES = {"aihero-wayfare": "2026-07-21", "elevate-commons": "2026-07-21", "ah-cozy": "2026-08-01",
          "aihero-dokyu": "2026-08-02", "aihero-mehr": "2026-08-02", "aihero-steadfast": "2026-09-13"}


def week_of(day):
    y, w, _ = date.fromisoformat(day[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def days(a, b):
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def carry(points, weeks=WEEKS, until=NOW):
    """points: [(day, value)] -> weekly series holding the last value seen; None before the first and after `until`."""
    pts = sorted(points)
    out, last, i = [], None, 0
    for w in weeks:
        wk_end = date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()
        while i < len(pts) and pts[i][0] <= wk_end:
            last = pts[i][1]
            i += 1
        wk_start = date.fromisocalendar(int(w[:4]), int(w[6:]), 1).isoformat()
        out.append(last if wk_start <= until else None)
    return out


@lru_cache(maxsize=None)
def con():
    from cube.db import connect
    return connect("compliance")


def audit_days():
    """One audit per day: the day's last committed CONSISTENCY.md (same-day regenerations collapse)."""
    by_day = {}
    for a in R.audits():
        by_day[a["day"]] = a
    return [by_day[d] for d in sorted(by_day)]


def applicable(cells):
    return [m for m in cells.values() if m in ("pass", "fail")]


def is_manual(row):
    return not applicable(row["cells"]) and any(m == "manual" for m in row["cells"].values())


# ------------------------------------------------------------------ Q register-growth register growth

def q_register_growth():
    vs = R.register_versions()
    au = audit_days()
    ctl = carry([(v["day"], len(v["controls"])) for v in vs])
    chk = carry([(v["day"], len(v["checks"])) for v in vs])
    repos = carry([(a["day"], len(a["repos"])) for a in au])
    first, last = au[0], au[-1]

    def mix(a):
        out = {s: Counter() for s in SEVS}
        for r in a["rows"]:
            out[r["severity"]]["human" if is_manual(r) else "machine"] += 1
        return out
    new_per_week = Counter()
    seen = set()
    for v in vs:
        for c in v["checks"]:
            if c not in seen:
                seen.add(c)
                new_per_week[week_of(v["day"])] += 1
    # A 17 Jul check set that never grew would be one bar; bursts show as tall bars.
    manual_results = lambda a: sum(1 for r in a["rows"] for m in r["cells"].values() if m == "manual")
    all_results = lambda a: sum(1 for r in a["rows"] for m in r["cells"].values() if m != "na")
    return {
        "weeks": WEEKS, "controls": ctl, "checks": chk, "repos": repos,
        "new_checks": [new_per_week.get(w, 0) for w in WEEKS],
        "first": {"day": first["day"], "controls": first["header"][3], "checks": first["header"][2], "repos": len(first["repos"])},
        "last": {"day": last["day"], "controls": last["header"][3], "checks": last["header"][2], "repos": len(last["repos"])},
        "mix_first": mix(first), "mix_last": mix(last),
        "manual_share_first": manual_results(first) / all_results(first),
        "manual_share_last": manual_results(last) / all_results(last),
        "n_versions": len(vs), "n_audits": len(R.audits()), "n_audit_days": len(au),
        "checks_ever": len(seen),
        "top_week": max(new_per_week.items(), key=lambda kv: kv[1]),
    }


# ------------------------------------------------------------------ Q control-origins what prompted each control

TRIGGERS = ["Bug in a fleet repo", "Outside incident or advisory", "Design ahead of failure", "Audit sweep finding"]
TRIGGER_PROMPT = """You classify why a compliance control was created in a small software fleet (a template repo and its clones, all built by coding agents).
For each control below you get its id, title, its "why" text and the commit message that introduced it.
Pick the PRIMARY trigger, one of:
  bug   - a concrete failure or defect already observed in one of the fleet's own repos (names a repo, a broken build, a leak, a bug that happened)
  outside - an incident, advisory or compromise outside the fleet (a CVE, a supply-chain attack on a public action, an industry event)
  design - a rule adopted ahead of any failure: a standard, a convention, a design decision, a "so the first X inherits it"
  audit  - found by comparing repos in an audit sweep: drift between repos, one repo lagging the others, with no failure named
Also say whether the text names a concrete failure in a fleet repo at all (true/false), even if it is not the primary trigger.
Reply with JSON only: [{"id": "...", "trigger": "bug|outside|design|audit", "names_fleet_failure": true|false, "evidence": "<= 12 words"}]

"""


def control_catalog():
    """Every control ever in the canonical register: id, first day, first commit subject, last block."""
    cat = {}
    for v in R.register_versions():
        for cid, blk in v["controls"].items():
            if cid not in cat:
                cat[cid] = {"id": cid, "first_day": v["day"], "first_subject": v["subject"], "where": v["where"]}
            cat[cid]["block"] = blk
            cat[cid]["last_day"] = v["day"]
    last = R.register_versions()[-1]["controls"]
    for c in cat.values():
        c["title"] = R.field(c["block"], "title")
        c["severity"] = R.field(c["block"], "severity")
        c["why"] = R.field(c["block"], "why") or ""
        c["current"] = c["id"] in last
    return cat


def ensure_labels(table, items, prompt, key, text_of, batch=10, by_key=False):
    """Label items with Haiku once, cached in compliance.sqlite by content hash. Returns ({key: label}, spend)."""
    import hashlib
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from detectors.d1_changesets import call_haiku
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "compliance.sqlite")
    c = sqlite3.connect(db)
    c.execute(f"CREATE TABLE IF NOT EXISTS {table} (k TEXT PRIMARY KEY, hash TEXT, label_json TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS spend (tbl TEXT, usd REAL, ts TEXT DEFAULT CURRENT_TIMESTAMP)")
    have = {k: (h, j) for k, h, j in c.execute(f"SELECT k, hash, label_json FROM {table}")}
    todo = []
    for it in items:
        if by_key and key(it) in have:
            continue
        t = text_of(it)
        h = hashlib.sha1((prompt + t).encode()).hexdigest()
        if have.get(key(it), (None,))[0] != h:
            todo.append((it, t, h))
    spend = 0.0
    if os.environ.get("CH14_FROZEN"):
        todo = []
    if todo:
        chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
        with ThreadPoolExecutor(6) as ex:
            results = list(ex.map(lambda ch: call_haiku([t for _, t, _ in ch], header=prompt), chunks))
        for ch, (res, usd) in zip(chunks, results):
            spend += usd
            got = {str(r.get("id")): r for r in (res if isinstance(res, list) else [])}
            for it, t, h in ch:
                r = got.get(str(key(it)))
                if r:
                    c.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?)", (key(it), h, json.dumps(r)))
        c.execute("INSERT INTO spend(tbl, usd) VALUES (?,?)", (table, spend))
        c.commit()
    out = {k: json.loads(j) for k, h, j in c.execute(f"SELECT k, hash, label_json FROM {table}")}
    return out, spend


def q_control_origins():
    cat = control_catalog()
    items = sorted(cat.values(), key=lambda c: c["id"])
    text = lambda c: (f"id: {c['id']}\ntitle: {c['title']}\nwhy: {c['why'][:1800]}\n"
                      f"introduced by commit: {c['first_subject']}")
    labels, spend = ensure_labels("control_trigger", items, TRIGGER_PROMPT, lambda c: c["id"], text)
    code = {"bug": TRIGGERS[0], "outside": TRIGGERS[1], "design": TRIGGERS[2], "audit": TRIGGERS[3]}
    rows = []
    for c in items:
        lab = labels.get(c["id"], {})
        rows.append({**{k: c[k] for k in ("id", "title", "severity", "first_day", "current")},
                     "trigger": code.get(lab.get("trigger"), "Unlabelled"),
                     "names_fleet_failure": bool(lab.get("names_fleet_failure")), "evidence": lab.get("evidence", "")})
    cum = {t: carry(sorted((r["first_day"], None) for r in rows if r["trigger"] == t)) for t in TRIGGERS}
    for t in TRIGGERS:
        firsts = sorted(r["first_day"] for r in rows if r["trigger"] == t)
        cum[t] = [None if v is None and not firsts else sum(1 for d in firsts if d <= date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat())
                  for w, v in zip(WEEKS, [0] * len(WEEKS))]
    by_sev = {t: [sum(1 for r in rows if r["trigger"] == t and r["severity"] == s) for s in SEVS] for t in TRIGGERS}
    return {"rows": rows, "cum": cum, "by_sev": by_sev, "n": len(rows),
            "counts": Counter(r["trigger"] for r in rows), "names_fleet": sum(r["names_fleet_failure"] for r in rows),
            "spend": spend}


# ------------------------------------------------------------------ Q rule-change-review who changes the rules, through what gate

def q_rule_change_review_changes():
    """Every commit that changed the canonical register (or the plugin baseline), by path and by agent trailer."""
    ch = []
    for v in R.register_versions():
        pr = re.search(r"\(#(\d+)\)\s*$", v["subject"])
        path = ("Reviewed PR · hero-template" if v["where"] == "hero-template" and pr else
                "Direct commit · hero-template" if v["where"] == "hero-template" else "Direct commit · .fleet (no remote)")
        ch.append({"day": v["day"], "sha": v["sha"], "subject": v["subject"], "path": path, "claude": v["claude"],
                   "pr": int(pr.group(1)) if pr else None, "repo": "hero-template" if v["where"] == "hero-template" else ".fleet"})
    for sha, ts, subj, author, claude, text in R.file_versions("assets/compliance/CHECKS.yaml", R.SKILLS) + \
            R.file_versions("assets/compliance/CONTROLS.yaml", R.SKILLS):
        if any(c["sha"] == sha[:7] for c in ch):
            continue
        pr = re.search(r"\(#(\d+)\)\s*$", subj)
        ch.append({"day": ts[:10], "sha": sha[:7], "subject": subj, "path": "Reviewed PR · wayfare-skills baseline",
                   "claude": claude, "pr": int(pr.group(1)) if pr else None, "repo": "wayfare-skills"})
    ch.sort(key=lambda c: c["day"])
    paths = ["Reviewed PR · hero-template", "Reviewed PR · wayfare-skills baseline", "Direct commit · hero-template",
             "Direct commit · .fleet (no remote)"]
    weekly = {p: [sum(1 for c in ch if c["path"] == p and week_of(c["day"]) == w) for w in WEEKS] for p in paths}
    # Was each PR approved by a review before merge? (Reviews post under the owner's account; owner/actors.py tells agent from human.)
    reviewed = {}
    for c in ch:
        if c["pr"] and c["repo"] in ("hero-template", "wayfare-skills"):
            r = con().execute("SELECT COUNT(*) n, SUM(state='APPROVED') a FROM github.pr_reviews WHERE repo=? AND number=?",
                              (c["repo"], c["pr"])).fetchone()
            reviewed[(c["repo"], c["pr"])] = (r["n"] or 0, r["a"] or 0)
    remote = R.git(os.path.join(R.FLEET, ".fleet"), "remote", "-v").strip()
    since = [c for c in ch if c["day"] >= "2026-09-13"]
    return {"changes": ch, "paths": paths, "weekly": weekly, "reviewed": reviewed, "fleet_remote": remote or None,
            "n": len(ch), "by_path": Counter(c["path"] for c in ch), "claude": sum(c["claude"] for c in ch),
            "since_move": len(since), "since_move_direct": sum(1 for c in since if c["path"].startswith("Direct")),
            "approved_prs": sum(1 for v in reviewed.values() if v[1]), "prs": len(reviewed)}


# ------------------------------------------------------------------ Q audit-frequency audit cadence

def q_audit_frequency():
    au = audit_days()
    ds = [a["day"] for a in au]
    gaps = [days(a, b) for a, b in zip(ds, ds[1:])] + [days(ds[-1], NOW)]
    stale = []
    for w in WEEKS:
        end = date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()
        end = min(end, NOW)
        prior = [d for d in ds if d <= end]
        stale.append(days(prior[-1], end) if prior and date.fromisocalendar(int(w[:4]), int(w[6:]), 1).isoformat() <= NOW else None)
    runs = [dict(r) for r in con().execute(
        "SELECT substr(ts,1,10) day, skill_name FROM harness.tool_calls WHERE skill_name LIKE '%consistency%' "
        "OR skill_name LIKE '%audit-compliance%' OR skill_name LIKE '%sync-plan%' OR skill_name LIKE '%wayfare%sync%' ORDER BY ts")]
    in_ci = []
    for repo in ("hero-template",):
        for sha in [a["sha"] for a in R.audits() if a["where"] == "hero-template"][-1:]:
            out = R.git(os.path.join(R.FLEET, repo), "grep", "-l", "-E", r"scripts/audit\.py|consistency\.py", sha, "--",
                        ".github/workflows", ".pre-commit-config.yaml")
            in_ci += [l for l in out.splitlines() if l]
    hist = Counter(min(g, 15) // 3 for g in gaps)
    bins = ["0–2", "3–5", "6–8", "9–11", "12–14", "15+"]
    return {"weeks": WEEKS, "stale": stale, "audit_days": ds, "gaps": gaps, "longest": max(gaps),
            "longest_from": ds[gaps.index(max(gaps))] if max(gaps) in gaps else None,
            "median_gap": median(gaps), "skill_runs": runs, "in_ci": in_ci, "n_commits": len(R.audits()),
            "gap_bins": bins, "gap_hist": [hist.get(i, 0) for i in range(len(bins))]}


# ------------------------------------------------------------------ Q audit-pass-rate pass share at each audit

def tally(a, repos=None):
    c = Counter(m for r in a["rows"] for rp, m in r["cells"].items() if repos is None or rp in repos)
    return c


def q_audit_pass_rate():
    au = audit_days()
    share = lambda c: c["pass"] / (c["pass"] + c["fail"]) if c["pass"] + c["fail"] else None
    allrep = [(a["day"], share(tally(a))) for a in au]
    founding = [(a["day"], share(tally(a, set(FOUNDING) - {"hiro"}))) for a in au]
    fails = [(a["day"], tally(a)["fail"]) for a in au]
    repos = sorted({r for a in au for r in a["repos"]})
    by_repo = {}
    for rp in repos:
        pts = [(a["day"], share(tally(a, {rp}))) for a in au if rp in a["repos"]]
        by_repo[rp] = carry(pts, until=NOW if rp in au[-1]["repos"] else pts[-1][0])
    last = au[-1]
    den = {rp: tally(last, {rp}) for rp in last["repos"]}
    # RQ-h3-018: are pass rates comparable across repos? Denominator = checks that apply and a machine can run.
    return {"weeks": WEEKS, "all": carry(allrep), "founding": carry(founding), "fails": carry(fails),
            "points": [(a["day"], share(tally(a)), share(tally(a, set(FOUNDING) - {"hiro"})), tally(a)["fail"], len(a["repos"]))
                       for a in au], "by_repo": by_repo, "den": den, "last_day": last["day"]}


# ------------------------------------------------------------------ Q new-check-violations / 07 / 08: the violation ledger

@lru_cache(maxsize=None)
def ledger():
    """One row per (check, repo) violation ever seen: when first seen, how, when (if) it first passed after."""
    au = audit_days()
    first_seen = {}
    sev, ctl = {}, {}
    for a in au:
        for r in a["rows"]:
            sev[r["check"]], ctl[r["check"]] = r["severity"], r["control"]
            first_seen.setdefault(r["check"], a["day"])
    rows = {}
    for i, a in enumerate(au):
        for r in a["rows"]:
            k = r["check"]
            caught = r["broken_in"] if first_seen[k] == a["day"] and r["broken_in"] else set()
            for rp in caught:
                if (k, rp) not in rows:
                    rows[(k, rp)] = {"check": k, "repo": rp, "opened": a["day"], "how": "caught when the check was written"}
            for rp, m in r["cells"].items():
                if m == "fail" and (k, rp) not in rows:
                    rows[(k, rp)] = {"check": k, "repo": rp, "opened": a["day"], "how": "seen failing in a later audit"}
    for (k, rp), v in rows.items():
        v["severity"], v["control"] = sev[k], ctl[k]
        v["closed"], v["outcome"] = None, "still failing"
        opened_audit = next(a for a in au if a["day"] == v["opened"])
        cell = next(r["cells"].get(rp) for r in opened_audit["rows"] if r["check"] == k)
        if cell == "pass":
            v["closed"], v["outcome"] = v["opened"], "fixed in the same sweep"
            continue
        last_state = None
        for a in au:
            if a["day"] <= v["opened"]:
                continue
            row = next((r for r in a["rows"] if r["check"] == k), None)
            st = row["cells"].get(rp) if row else None
            if st == "pass":
                v["closed"], v["outcome"] = a["day"], "fixed later"
                break
            last_state = st if row else "check retired"
        if v["closed"] is None:
            final = au[-1]
            row = next((r for r in final["rows"] if r["check"] == k), None)
            if row is None:
                v["outcome"] = "check retired"
            elif rp not in row["cells"]:
                v["outcome"] = "repo left the audit"
            elif row["cells"][rp] in ("na", "manual"):
                v["outcome"] = "check no longer applies"
    return list(rows.values())


def repo_first_day():
    return {r["repo"]: r["d"] for r in con().execute("SELECT repo, MIN(day) d FROM git.commits GROUP BY repo")} | \
           {"wayfare-skills": R.git(R.SKILLS, "log", "--reverse", "--format=%aI").split("\n")[0][:10]}


def q_new_check_violations():
    L = [v for v in ledger() if v["how"] == "caught when the check was written"]
    first = repo_first_day()
    per_week = {s: [sum(1 for v in L if v["severity"] == s and week_of(v["opened"]) == w) for w in WEEKS] for s in SEVS}
    ages = defaultdict(list)
    for v in L:
        if v["repo"] in first:
            v["repo_age"] = days(first[v["repo"]], v["opened"])
            ages[v["severity"]].append(v["repo_age"])
    au = audit_days()
    first_seen = {}
    for a in au:
        for r in a["rows"]:
            first_seen.setdefault(r["check"], (a["day"], r["broken_in"]))
    n_checks_with = sum(1 for d, b in first_seen.values() if b)
    n_checks_known = sum(1 for d, b in first_seen.values() if b is not None)
    bins = ["< 30 days", "30–59", "60–89", "90–179", "180+"]
    edges = [30, 60, 90, 180, 10 ** 6]
    hist = {s: [0] * len(bins) for s in SEVS}
    for s in SEVS:
        for a_ in ages[s]:
            hist[s][next(i for i, e in enumerate(edges) if a_ < e)] += 1
    all_ages = [a_ for s in SEVS for a_ in ages[s]]
    return {"weeks": WEEKS, "per_week": per_week, "n": len(L), "n_checks_with": n_checks_with,
            "n_checks_known": n_checks_known, "median_age": median(all_ages) if all_ages else None,
            "median_by_sev": {s: median(ages[s]) if ages[s] else None for s in SEVS}, "bins": bins, "hist": hist,
            "first_sweep": sum(1 for v in L if v["opened"] == au[0]["day"]),
            "by_repo": Counter(v["repo"] for v in L)}


OUTCOMES = ["fixed in the same sweep", "fixed later", "still failing", "check retired", "repo left the audit",
            "check no longer applies"]


def q_violation_fix_time():
    L = ledger()
    opened = [sum(1 for v in L if week_of(v["opened"]) == w and v["outcome"] != "fixed in the same sweep") for w in WEEKS]
    closed = [sum(1 for v in L if v["closed"] and week_of(v["closed"]) == w and v["outcome"] == "fixed later") for w in WEEKS]
    later = [v for v in L if v["outcome"] == "fixed later"]
    dd = {s: [days(v["opened"], v["closed"]) for v in later if v["severity"] == s] for s in SEVS}
    out_by_sev = {o: [sum(1 for v in L if v["outcome"] == o and v["severity"] == s) for s in SEVS] for o in OUTCOMES}
    open_now = [v for v in L if v["outcome"] == "still failing"]
    au = audit_days()
    regress = []
    for v in [v for v in L if v["closed"]]:
        for a in au:
            if a["day"] > v["closed"]:
                row = next((r for r in a["rows"] if r["check"] == v["check"]), None)
                if row and row["cells"].get(v["repo"]) == "fail":
                    regress.append({**v, "reopened": a["day"]})
                    break
    return {"weeks": WEEKS, "regressions": regress, "opened": opened, "closed": closed, "n": len(L), "outcomes": Counter(v["outcome"] for v in L),
            "out_by_sev": out_by_sev, "days_by_sev": {s: median(dd[s]) if dd[s] else None for s in SEVS},
            "days_all": median([x for s in SEVS for x in dd[s]]) if later else None, "n_later": len(later),
            "n_open": len(open_now),
            "open_age_median": median([days(v["opened"], NOW) for v in open_now]) if open_now else None}


def q_open_violations():
    au = audit_days()
    sev_of = {}
    for a in au:
        for r in a["rows"]:
            sev_of[r["check"]] = r["severity"]
    per = {s: carry([(a["day"], sum(1 for r in a["rows"] if r["severity"] == s for m in r["cells"].values() if m == "fail"))
                     for a in au]) for s in SEVS}
    last = au[-1]
    L = ledger()
    ever_failed = {v["check"] for v in L}
    checks_last = {r["check"]: r for r in last["rows"]}
    never = [k for k, r in checks_last.items() if k not in ever_failed and applicable(r["cells"])]
    manual_only = [k for k, r in checks_last.items() if is_manual(r)]
    open_now = [v for v in L if v["outcome"] == "still failing"]
    share_checks = Counter(r["severity"] for r in last["rows"] if applicable(r["cells"]))
    share_open = Counter(r["severity"] for r in last["rows"] for m in r["cells"].values() if m == "fail")
    age = {s: median([days(v["opened"], NOW) for v in open_now if v["severity"] == s]) if share_open[s] else None for s in SEVS}
    ctl_text = R.register_versions()[-1]["controls"]
    with_deadline = sum(1 for b in ctl_text.values() if re.search(r"(?m)^  (deadline|due|due_by|priority):", b))
    open_by_repo = defaultdict(lambda: Counter())
    for v in open_now:
        open_by_repo[v["repo"]][v["severity"]] += 1
    overdue = Counter(v["severity"] for v in open_now if days(v["opened"], NOW) > DEADLINES[v["severity"]])
    fixed = [v for v in L if v["outcome"] == "fixed later"]
    in_time = {s: (sum(1 for v in fixed if v["severity"] == s and days(v["opened"], v["closed"]) <= DEADLINES[s]),
                   sum(1 for v in fixed if v["severity"] == s)) for s in SEVS}
    return {"weeks": WEEKS, "per": per, "never": never, "overdue": overdue, "in_time": in_time, "manual_only": manual_only, "n_checks": len(checks_last),
            "share_checks": share_checks, "share_open": share_open, "age": age, "n_open": len(open_now),
            "with_deadline": with_deadline, "n_controls": len(ctl_text), "open_by_repo": dict(open_by_repo),
            "last_fail_cells": tally(last)["fail"]}


# ------------------------------------------------------------------ Q clone-compliance-drift does a clone start compliant

def q_clone_compliance_drift():
    au = audit_days()
    share = lambda c: c["pass"] / (c["pass"] + c["fail"]) if c["pass"] + c["fail"] else None
    lines = {}
    for rp in ["hero-template"] + list(CLONES):
        pts = [(a["day"], share(tally(a, {rp}))) for a in au if rp in a["repos"]]
        lines[rp] = carry(pts)
    first_seen = {}
    for a in au:
        for r in a["rows"]:
            first_seen.setdefault(r["check"], a["day"])
    last = au[-1]
    split = {}
    tmpl_fails = {r["check"] for r in last["rows"] if r["cells"].get("hero-template") == "fail"}
    for rp, born in CLONES.items():
        f = [r["check"] for r in last["rows"] if r["cells"].get(rp) == "fail"]
        split[rp] = {"existed at clone": sum(1 for k in f if first_seen[k] <= born),
                     "added after clone": sum(1 for k in f if first_seen[k] > born),
                     "template fails too": sum(1 for k in f if k in tmpl_fails), "total": len(f)}
    first_audit = {rp: next(a["day"] for a in au if rp in a["repos"]) for rp in CLONES}
    at_entry = {rp: share(tally(next(a for a in au if rp in a["repos"]), {rp})) for rp in CLONES}
    tmpl_at_entry = {rp: share(tally(next(a for a in au if rp in a["repos"]), {"hero-template"})) for rp in CLONES}
    return {"weeks": WEEKS, "lines": lines, "split": split, "first_audit": first_audit, "at_entry": at_entry,
            "tmpl_at_entry": tmpl_at_entry, "tmpl_fails_now": tally(last, {"hero-template"})["fail"],
            "clone_fails_now": {rp: tally(last, {rp})["fail"] for rp in CLONES}}


# ------------------------------------------------------------------ Q register-copy-drift register copies

def q_register_copy_drift():
    canon = [(v["day"], v["controls"]) for v in R.register_versions()]

    def canon_on(d):
        cur = canon[0][1]
        for day, c in canon:
            if day <= d:
                cur = c
        return cur
    copies = R.copies()
    lines, rows = {}, []
    for rp, vs in copies.items():
        pts = []
        start = vs[0][0]
        removed = next((d for d, s, subj, x in vs if x is None), None)
        for w in WEEKS:
            ws = date.fromisocalendar(int(w[:4]), int(w[6:]), 1).isoformat()
            we = min(date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat(), NOW)
            if we < start or ws > NOW or (removed and ws > removed):
                pts.append(None)
                continue
            cur = None
            for d, s, subj, x in vs:
                if d <= we:
                    cur = x
            if cur is None:
                pts.append(None)
                continue
            c = canon_on(we)
            pts.append(len(set(c) - cur))
        lines[rp] = pts
        last_copy = [x for d, s, subj, x in vs if x is not None][-1]
        end = removed or NOW
        cblk = canon_on(end)
        copy_text = None
        for sha_, ts_, subj_, a_, cl_, text_ in R.file_versions("CONTROLS.yaml", R.repo_dir(rp)):
            if text_.strip():
                copy_text = text_
        blocks = R.yaml_blocks(copy_text or "")
        changed = sum(1 for k, b in blocks.items() if k in cblk and b.strip() != cblk[k].strip())
        rows.append({"repo": rp, "from": start, "removed": removed, "days": days(start, end),
                     "missing_at_end": len(set(cblk) - last_copy), "changed_at_end": changed,
                     "edits_to_copy": sum(1 for d, s, subj, x in vs[1:] if x is not None),
                     "edit_subjects": [subj for d, s, subj, x in vs[1:] if x is not None]})
    reg01 = None
    for v in R.register_versions():
        if "REG-01" in v["checks"]:
            reg01 = v["day"]
            break
    au = audit_days()
    reg01_now = {rp: next((r["cells"].get(rp) for r in au[-1]["rows"] if r["check"] == "REG-01"), None) for rp in copies}
    reg01_first_audit = next((a["day"] for a in au if any(r["check"] == "REG-01" for r in a["rows"])), None)
    return {"weeks": WEEKS, "lines": lines, "rows": rows, "reg01_added": reg01, "reg01_first_audit": reg01_first_audit,
            "reg01_now": reg01_now, "still_carried": [r["repo"] for r in rows if not r["removed"]]}


# ------------------------------------------------------------------ change sets, shared by Q compliance-work-share to Q gate-loosening

MIRRORS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "mirrors")


@lru_cache(maxsize=None)
def cs_all():
    """Change sets (record) with their shared work-type label, files and commit text."""
    from record import changeset_facts
    c = con()
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): (r["work_type"], r["theme"])
          for r in c.execute("SELECT * FROM detectors.cs_worktype")}
    files, text = {}, {}
    for r in c.execute("SELECT repo, sha, subject, body_redacted, files_json FROM pr_commits.pr_commits"):
        files[(r["repo"], r["sha"])] = [f["path"] for f in json.loads(r["files_json"] or "[]")]
        text[(r["repo"], r["sha"])] = f"{r['subject']}\n{r['body_redacted'] or ''}"
    mf = defaultdict(list)
    for r in c.execute("SELECT repo, sha, path FROM git.commit_files"):
        mf[(r["repo"], r["sha"])].append(r["path"])
    for r in c.execute("SELECT repo, sha, subject, body_redacted FROM git.commits"):
        text.setdefault((r["repo"], r["sha"]), f"{r['subject']}\n{r['body_redacted'] or ''}")
    prs = {(r["repo"], r["number"]): f"{r['title']}\n{r['body_redacted'] or ''}"
           for r in c.execute("SELECT repo, number, title, body_redacted FROM github.prs")}
    out = []
    for s in changeset_facts(c):
        k = (s["repo"], s["unit_kind"], s["unit_id"], s["set_idx"])
        f = []
        for sha in s["shas"]:
            f += files.get((s["repo"], sha)) or mf.get((s["repo"], sha), [])
        work_type, theme = wt.get(k, (None, None))
        out.append({**s, "work_type": work_type, "theme": theme, "files": f,
                    "text": "\n".join(text.get((s["repo"], sha), "") for sha in s["shas"]),
                    "pr_text": prs.get((s["repo"], s["pr"]), "") if s["pr"] else ""})
    return out


def is_compliance(s):
    return s["work_type"] == "security" or s["theme"] == "compliance"


def q_compliance_work_share_share():
    from spend.attribution import spend_by_changeset
    cs = [s for s in cs_all() if s["category"] != "out of scope"]
    comp = [s for s in cs if is_compliance(s)]
    tot_w = Counter(s["week"] for s in cs)
    comp_w = Counter(s["week"] for s in comp)
    kind = lambda s: "Compliance theme" if s["theme"] == "compliance" else "Security work"
    stacked = {k: [sum(1 for s in comp if s["week"] == w and kind(s) == k) for w in WEEKS]
               for k in ["Security work", "Compliance theme"]}
    share = [comp_w[w] / tot_w[w] if tot_w[w] >= 5 else None for w in WEEKS]
    months = [f"2026-{m:02d}" for m in range(1, 10)]
    by_repo = {}
    for rp in sorted({s["repo"] for s in comp}):
        tm = Counter(s["month"] for s in cs if s["repo"] == rp)
        cm = Counter(s["month"] for s in comp if s["repo"] == rp)
        by_repo[rp] = [cm[m] / tm[m] if tm[m] >= 3 else None for m in months]
    sp = spend_by_changeset(con())
    sp = [s for s in sp if s["day"] >= "2026-08-09"]
    ck = {(s["repo"], s["unit_kind"], s["unit_id"], s["set_idx"]) for s in comp}
    usd_all = sum(s["usd"] for s in sp)
    usd_comp = sum(s["usd"] for s in sp if (s["repo"], s["unit_kind"], s["unit_id"], s["set_idx"]) in ck)
    sets_since = [s for s in cs if s["day"] >= "2026-08-09"]
    comp_since = [s for s in sets_since if is_compliance(s)]
    # NEW-C08-H: compliance change sets per repo against the repo's open failures at the last audit.
    last = audit_days()[-1]
    scatter = [(rp, sum(1 for s in comp if s["repo"] == rp), tally(last, {rp})["fail"]) for rp in last["repos"]]
    return {"weeks": WEEKS, "stacked": stacked, "share": share, "months": months, "by_repo": by_repo,
            "n": len(comp), "n_all": len(cs), "usd_comp": usd_comp, "usd_all": usd_all,
            "sets_share_since": len(comp_since) / len(sets_since), "scatter": scatter,
            "by_theme": Counter(kind(s) for s in comp),
            "since_jul": (sum(1 for s in comp if s["day"] >= "2026-07-17"), sum(1 for s in cs if s["day"] >= "2026-07-17"))}


# ------------------------------------------------------------------ Q changes-name-controls citations

@lru_cache(maxsize=None)
def register_ids():
    ids_ = set()
    for v in R.register_versions():
        ids_ |= set(v["controls"]) | set(v["checks"])
    for sha, ts, subj, a, cl, text in R.file_versions("assets/compliance/CHECKS.yaml", R.SKILLS) + \
            R.file_versions("assets/compliance/CONTROLS.yaml", R.SKILLS):
        ids_ |= set(R.ids(text))
    return ids_


def cites(text):
    ids_ = register_ids()
    return sorted({m for m in re.findall(r"\b(C-[A-Z][A-Z0-9-]*[A-Z0-9]|[A-Z]{2,7}-\d{2})\b", text) if m in ids_})


def q_changes_name_controls_citations():
    cs = [s for s in cs_all() if s["category"] != "out of scope"]
    for s in cs:
        s["cites"] = cites(s["text"] + "\n" + s["pr_text"])
    comp = [s for s in cs if is_compliance(s)]
    since = [s for s in cs if s["day"] >= "2026-07-17"]
    cited = [s for s in since if s["cites"]]
    comp_since = [s for s in comp if s["day"] >= "2026-07-17"]
    months = [f"2026-{m:02d}" for m in range(7, 10)]
    weekly = {"Compliance change sets citing an id": [sum(1 for s in comp if s["week"] == w and s["cites"]) for w in WEEKS],
              "Compliance change sets, no id": [sum(1 for s in comp if s["week"] == w and not s["cites"]) for w in WEEKS]}
    top = Counter(i for s in cs for i in s["cites"]).most_common(10)
    by_repo = Counter(s["repo"] for s in cited)
    return {"weeks": WEEKS, "weekly": weekly, "n_cited": len(cited), "n_since": len(since),
            "comp_cited": sum(1 for s in comp_since if s["cites"]), "comp_since": len(comp_since),
            "noncomp_cited": sum(1 for s in cited if not is_compliance(s)), "top": top, "by_repo": by_repo,
            "ids_known": len(register_ids())}


# ------------------------------------------------------------------ Q gate-loosening gates tighten or loosen

GATE = re.compile(r"(^|/)\.pre-commit-config\.ya?ml$|^\.github/workflows/|(^|/)\.golangci\.ya?ml$|"
                  r"(^|/)eslint[^/]*\.config\.[cm]?[jt]s$|(^|/)\.eslintrc|^scripts/check-[^/]+\.sh$|(^|/)\.semgrep|"
                  r"(^|/)\.gitleaks|(^|/)\.trivyignore|(^|/)\.secrets\.baseline$")
GATE_PROMPT = """You label changes to the quality and security gates of a software repo (pre-commit hooks, CI workflows, linter configs, check scripts, secret-scan baselines).
For each change you get its id, commit messages and the diff of its gate files (possibly truncated).
Label the net effect on what the gates enforce:
  tighten - adds or strengthens a check (new hook, new rule, stricter threshold, a job now blocking, pinning, removing an exemption)
  loosen  - removes or weakens a check (drops a hook or job, adds an exclusion, ignore, allowlist entry, skip, continue-on-error, lower threshold, makes blocking advisory)
  neutral - no change to what is enforced (renames, version bumps, refactors, deploy or build steps, caching, formatting)
  mixed   - clearly both
For loosen or mixed, give the stated or evident reason in <= 12 words.
Reply with JSON only: [{"id": "...", "effect": "tighten|loosen|neutral|mixed", "reason": "..."}]

"""


def gate_diff(repo, shas, files):
    mirror = os.path.join(MIRRORS, f"{repo}.git")
    paths = sorted({f for f in files if GATE.search(f)})
    out = []
    for sha in shas:
        d = R.git(mirror, "show", "--format=", "--unified=1", sha, "--", *paths)
        out.append(d)
    return "\n".join(out)


def q_gate_loosening_gates():
    cs = [s for s in cs_all() if s["category"] != "out of scope" and not s["dependabot"]
          and any(GATE.search(f) for f in s["files"])]
    items = []
    for s in cs:
        k = f"{s['repo']}|{s['unit_kind']}|{s['unit_id']}|{s['set_idx']}"
        items.append({"id": k, "s": s})
    text = lambda it: (f"id: {it['id']}\nmessages: {it['s']['text'][:600]}\ndiff:\n"
                       f"{gate_diff(it['s']['repo'], tuple(it['s']['shas']), tuple(it['s']['files']))[:1800]}")
    # by_key: the diff text costs a git show per commit, and a merged change set's diff never changes.
    labels, spend = ensure_labels("gate_effect", items, GATE_PROMPT, lambda it: it["id"], text, batch=8, by_key=True)
    rows = []
    for it in items:
        lab = labels.get(it["id"], {})
        rows.append({**{k: it["s"][k] for k in ("repo", "week", "month", "day", "pr", "label", "category")},
                     "id": it["id"], "effect": {"tightening": "tighten", "loosening": "loosen"}.get(lab.get("effect"), lab.get("effect", "unlabelled")),
                     "reason": lab.get("reason", "")})
    effects = ["tighten", "loosen", "mixed"]
    weekly = {e: [sum(1 for r in rows if r["effect"] == e and r["week"] == w) for w in WEEKS] for e in effects}
    by_repo = {rp: Counter(r["effect"] for r in rows if r["repo"] == rp) for rp in sorted({r["repo"] for r in rows})}
    return {"weeks": WEEKS, "weekly": weekly, "rows": rows, "counts": Counter(r["effect"] for r in rows),
            "by_repo": by_repo, "spend": spend, "loosen": [r for r in rows if r["effect"] in ("loosen", "mixed")]}


# ------------------------------------------------------------------ Q fix-or-silence suppressions

SUPPRESS = {
    "nolint": r"//\s*nolint", "eslint-disable": r"eslint-disable", "noqa": r"#\s*noqa", "nosemgrep": r"nosemgrep",
    "allowlist secret": r"pragma:\s*allowlist secret", "ts-ignore/expect-error": r"@ts-(ignore|expect-error|nocheck)",
    "type: ignore": r"#\s*type:\s*ignore", "nosec": r"#\s*nosec|//\s*#nosec", "gitleaks:allow": r"gitleaks:allow",
    "trivy/checkov skip": r"trivy:ignore|checkov:skip|tfsec:ignore",
}


SUPPRESS_VERDICTS = ["test or fixture value", "false positive, reason given", "real finding, no reason on the line", "unclear"]
SUPPRESS_PROMPT = """You judge suppression comments added to a codebase built by coding agents (nolint, eslint-disable, nosemgrep, pragma: allowlist secret, @ts-expect-error, nosec...).
For each you get an id, the file, the commit subject and the line (long tokens are redacted).
Pick one verdict:
  fixture   - the flagged thing is a test value, example, placeholder or documentation, not real code or a real secret
  justified - a real code path, and the line or context states why the finding is a false positive or acceptable
  silences  - the suppression hides a finding that looks real, or it is a blanket disable with no reason (e.g. a whole-file eslint-disable, @ts-ignore, a bare nolint)
  unclear   - cannot tell from the line
Reply with JSON only: [{"id": "...", "verdict": "fixture|justified|silences|unclear"}]

"""


def q_fix_or_silence_suppress():
    from record import adoption
    rx = re.compile("|".join(f"(?P<g{i}>{p})" for i, p in enumerate(SUPPRESS.values())))
    names = list(SUPPRESS)
    rows = []
    for repo in sorted(adoption(con())):
        mirror = os.path.join(MIRRORS, f"{repo}.git")
        if not os.path.isdir(mirror):
            continue
        log = R.git(mirror, "log", "HEAD", "--no-merges", "-p", "--unified=0", "--format=@@@%H%x1f%aI%x1f%s",
                    "-E", "-G", "nolint|eslint-disable|noqa|nosemgrep|allowlist secret|@ts-|type: *ignore|nosec|gitleaks:allow|trivy:ignore|checkov:skip|tfsec:ignore")
        sha = day = subj = None
        path = ""
        for ln in log.splitlines():
            if ln.startswith("@@@"):
                sha, ts, subj = ln[3:].split("\x1f", 2)
                day = ts[:10]
                continue
            if ln.startswith("+++ "):
                path = ln[6:] if ln.startswith("+++ b/") else ""
                continue
            if not ln or ln[0] not in "+-" or ln.startswith(("+++", "---")):
                continue
            m = rx.search(ln)
            if not m or re.search(r"(^|/)(node_modules|vendor|dist|gen|generated)/|\.lock$|\.snap$", path):
                continue
            marker = names[int(next(k for k, v in m.groupdict().items() if v)[1:])]
            after = ln[m.end():]
            reason = bool(re.search(r"(--|//|#)?\s*[A-Za-z]{3,}.*\s[A-Za-z]{3,}", re.sub(r"[:(,]?\s*[\w/@.-]+(,\s*[\w/@.-]+)*", "", after, count=1)))
            rows.append({"repo": repo, "sha": sha[:7], "day": day, "week": week_of(day), "subject": subj, "path": path,
                         "op": "added" if ln[0] == "+" else "removed", "marker": marker, "line": ln[1:].strip()[:200],
                         "reason": reason})
    # A moved line shows as one removal and one addition in the same commit: net them out per (commit, marker).
    net = Counter()
    for r in rows:
        net[(r["repo"], r["sha"], r["marker"], r["line"])] += 1 if r["op"] == "added" else -1
    kept = []
    seen = Counter()
    for r in rows:
        k = (r["repo"], r["sha"], r["marker"], r["line"])
        want = net[k]
        if (want > 0 and r["op"] == "added") or (want < 0 and r["op"] == "removed"):
            if seen[k] < abs(want):
                seen[k] += 1
                kept.append(r)
    added = [r for r in kept if r["op"] == "added"]
    for i, r in enumerate(added):
        r["id"] = f"{r['repo']}|{r['sha']}|{r['path']}|{i}"
    redact = lambda t: re.sub(r"[A-Za-z0-9+/=_-]{16,}", "<REDACTED>", t)
    text = lambda r: (f"id: {r['id']}\nfile: {r['path']}\ncommit: {r['subject'][:160]}\n"
                      f"suppression line: {redact(r['line'])[:220]}")
    labels, spend = ensure_labels("suppression", added, SUPPRESS_PROMPT, lambda r: r["id"], text, batch=15)
    for r in added:
        code = labels.get(r["id"], {}).get("verdict")
        r["verdict"] = dict(zip(["fixture", "justified", "silences", "unclear"], SUPPRESS_VERDICTS)).get(code, "unclear")
    weekly_v = {v: [sum(1 for r in added if r["week"] == w and r["verdict"] == v) for w in WEEKS] for v in SUPPRESS_VERDICTS}
    weekly = {"Added": [sum(1 for r in added if r["week"] == w) for w in WEEKS],
              "Removed": [sum(1 for r in kept if r["op"] == "removed" and r["week"] == w) for w in WEEKS]}
    return {"weeks": WEEKS, "weekly": weekly, "rows": kept, "n_added": len(added),
            "n_removed": sum(1 for r in kept if r["op"] == "removed"),
            "by_marker": Counter(r["marker"] for r in added), "by_repo": Counter(r["repo"] for r in added),
            "with_reason": sum(1 for r in added if r["reason"]),
            "since_jul": sum(1 for r in added if r["day"] >= "2026-07-17"), "weekly_v": weekly_v,
            "verdicts": Counter(r["verdict"] for r in added), "spend": spend,
            "verdict_by_marker": {m: Counter(r["verdict"] for r in added if r["marker"] == m) for m in SUPPRESS}}


# ------------------------------------------------------------------ Q rule-files-self-check the rule files against their own rules

SCRATCH = os.environ.get("CH14_SCRATCH", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                                                      ".analysis", "scratch", "compliance", "agentsmd"))


def agents_md_errors(repo, rev):
    """Run the current check-agents-md.sh over the instruction files a repo had at `rev`. None if it had none."""
    import shutil
    import subprocess
    import tarfile
    import io
    mirror = os.path.join(MIRRORS, f"{repo}.git")
    tree = R.git(mirror, "ls-tree", "-r", "--name-only", rev)
    want = [p for p in tree.splitlines() if p in ("AGENTS.md", "CLAUDE.md") or (p.startswith(".claude/rules/") and p.endswith(".md"))]
    if not any(p in ("AGENTS.md", "CLAUDE.md") for p in want):
        return None
    d = os.path.join(SCRATCH, repo)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    tar = subprocess.run(["git", "-C", mirror, "archive", rev, *want], capture_output=True).stdout
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(d)
    p = subprocess.run(["bash", os.path.join(R.SKILLS, "scripts", "check-agents-md.sh"), d], capture_output=True, text=True)
    errs = re.findall(r"ERROR: (R\d+)", p.stdout + p.stderr)
    return errs


def q_rule_files_self_check():
    from record import adoption
    months = [f"2026-{m:02d}" for m in range(1, 10)]
    ends = [date(2026, m + 1, 1).isoformat() if m < 12 else "2027-01-01" for m in range(1, 10)]
    ends[-1] = "2026-09-25"
    per_month, rule_now, repo_now = [], Counter(), {}
    for m, end in zip(months, ends):
        n_ok = n = 0
        for repo in sorted(adoption(con())):
            if not os.path.isdir(os.path.join(MIRRORS, f"{repo}.git")):
                continue
            rev = R.git(os.path.join(MIRRORS, f"{repo}.git"), "rev-list", "-1", f"--before={end}T00:00:00", "HEAD").strip()
            if not rev:
                continue
            e = agents_md_errors(repo, rev)
            if e is None:
                continue
            n += 1
            n_ok += not e
            if m == months[-1]:
                rule_now.update(set(e))
                repo_now[repo] = e
        per_month.append((m, n, n_ok))
    au = audit_days()
    skills = [(a["day"], tally(a, {"wayfare-skills"})) for a in au if "wayfare-skills" in a["repos"]]
    last = au[-1]
    skills_fails = [(r["check"], r["control"]) for r in last["rows"] if r["cells"].get("wayfare-skills") == "fail"]
    std_day = R.git(R.SKILLS, "log", "--reverse", "--format=%aI", "--", "scripts/check-agents-md.sh").split("\n")[0][:10]
    return {"months": months, "per_month": per_month, "rule_now": rule_now, "repo_now": repo_now,
            "skills_audits": [(d, c["pass"], c["fail"]) for d, c in skills], "skills_fails": skills_fails,
            "standard_day": std_day}


if __name__ == "__main__":
    import pprint
    for f in [q_register_growth, q_rule_change_review_changes, q_audit_frequency, q_audit_pass_rate, q_new_check_violations, q_violation_fix_time, q_open_violations, q_clone_compliance_drift, q_register_copy_drift]:
        r = f()
        print("=====", f.__name__)
        pprint.pprint({k: v for k, v in r.items() if k not in ("weeks",)}, width=160, compact=True)


# ------------------------------------------------------------------ book figures 5.2, 5.6, 5.7, 5.8

# The register's family: every repo an audit ever covered. saga and the deleted design repos were never in it.
FAMILY_LEFT = {"hiro": "2026-08-21"}  # deprecated; audits after this day should not count it as alive


def family_alive(day):
    au = audit_days()
    fam = {r for a in au for r in a["repos"]}
    first = repo_first_day()
    return {r for r in fam if first.get(r, "9999") <= day and not (r in FAMILY_LEFT and FAMILY_LEFT[r] <= day)}


def fig_clone_drift():
    """5.2: each clone's open failures at the last audit, split by whether the check predates the clone."""
    from ingest.fleet import category_of
    au = audit_days()
    last = au[-1]
    first_seen = {}
    for a in au:
        for r in a["rows"]:
            first_seen.setdefault(r["check"], a["day"])
    tmpl_fails = {r["check"] for r in last["rows"] if r["cells"].get("hero-template") == "fail"}
    active = {r["repo"]: (r["last"], r["n30"]) for r in con().execute(
        "SELECT repo, MAX(day) last, SUM(day >= date(?, '-30 days')) n30 FROM git.commits GROUP BY repo", (last["day"],))}
    rows = []
    for rp, born in sorted(CLONES.items(), key=lambda kv: kv[1]):
        cells = {r["check"]: r["cells"].get(rp) for r in last["rows"]}
        fails = [k for k, m in cells.items() if m == "fail"]
        pre = [k for k in fails if first_seen[k] <= born]
        post = [k for k in fails if first_seen[k] > born]
        rows.append({"repo": rp, "cloned": born, "age_days": days(born, last["day"]), "category": category_of(rp),
                     "applicable": sum(1 for m in cells.values() if m in ("pass", "fail")),
                     "not_applicable": sum(1 for m in cells.values() if m == "na"),
                     "manual": sum(1 for m in cells.values() if m == "manual"),
                     "failed": len(fails), "pre_clone_rules": len(pre), "post_clone_rules": len(post),
                     "template_fails_too": sum(1 for k in fails if k in tmpl_fails),
                     "pre_clone_checks": sorted(pre), "post_clone_checks": sorted(post),
                     "last_commit": active[rp][0], "commits_30d": active[rp][1],
                     "active": active[rp][1] > 0, "exceptions": 0})
    tmpl = {r["check"]: r["cells"].get("hero-template") for r in last["rows"]}
    return {"rows": rows, "audit_day": last["day"], "template_failed": len(tmpl_fails),
            "template_applicable": sum(1 for m in tmpl.values() if m in ("pass", "fail")),
            "template_failed_checks": sorted(tmpl_fails), "total_failed": sum(r["failed"] for r in rows),
            "total_post": sum(r["post_clone_rules"] for r in rows), "total_pre": sum(r["pre_clone_rules"] for r in rows),
            "inactive": [r["repo"] for r in rows if not r["active"]],
            "exceptions_recorded": sum(1 for b in R.register_versions()[-1]["controls"].values()
                                       if re.search(r"(?m)^  (exceptions?|waivers?|exempt):", b))}


# Origins read by hand from every control's `why` and the commit that introduced it (28 Sep 2026). More than one
# origin is allowed. bug = a failure or unsafe state observed in a fleet repo; audit = drift found by comparing
# repos, nothing failed; design = a decision ahead of any failure; outside = an incident or advisory elsewhere.
ORIGINS_BY_HAND = {
    "C-AGENT": ["audit"], "C-APPROVAL": ["bug"], "C-ARCH": ["design"], "C-AUTHN": ["audit", "design"],
    "C-BUILD": ["bug"], "C-CICONF": ["bug", "audit"], "C-CICOST": ["bug", "audit"], "C-CIHYG": ["audit"],
    "C-COPYRIGHT": ["audit"], "C-DATA": ["design", "audit"], "C-DOCS": ["audit", "bug"], "C-EDITOR": ["design", "audit"],
    "C-GATES": ["bug"], "C-HEALTH": ["design", "bug"], "C-LAYOUT": ["audit"], "C-LIVEDEV": ["design", "audit"],
    "C-PORTS": ["audit", "design"], "C-PRECOMMIT": ["audit"], "C-PRGATE": ["audit"], "C-PROCESS": ["bug", "audit"],
    "C-READPATH": ["design"], "C-REGISTER": ["bug", "audit"], "C-RELEASE": ["audit", "design"], "C-REPO": ["design"],
    "C-RUNNER": ["audit"], "C-SCHEMA": ["audit", "design"], "C-SECRETS": ["audit"], "C-SENTRY": ["audit"],
    "C-STACK": ["design"], "C-SUPPLY": ["outside", "audit"], "C-TEMPLATE": ["bug"], "C-TENANT": ["bug", "design"],
    "C-TOOLCHAIN": ["audit"], "C-TS": ["audit"], "C-VENDORED": ["audit"], "C-VERSION": ["design", "audit"],
}
ORIGIN_NAMES = {"bug": "Failure seen in a fleet repo", "audit": "Drift found comparing repos",
                "design": "Design decision, nothing had failed", "outside": "Incident or advisory outside the fleet"}
CLASSES = ["After a failure in the fleet", "After observed drift, no failure", "Ahead of any failure"]


def origin_class(origins):
    if "bug" in origins:
        return CLASSES[0]
    if "audit" in origins:
        return CLASSES[1]
    return CLASSES[2]


def fig_control_origins():
    """5.6: every control's origins (multi-origin, read by hand), its class, and whether it later caught a failure."""
    x = q_control_origins()
    L = ledger()
    later = Counter(v["control"] for v in L if v["how"] == "seen failing in a later audit")
    at_write = Counter(v["control"] for v in L if v["how"] == "caught when the check was written")
    code = {"Bug in a fleet repo": "bug", "Outside incident or advisory": "outside", "Design ahead of failure": "design",
            "Audit sweep finding": "audit"}
    rows = []
    for r in x["rows"]:
        hand = ORIGINS_BY_HAND[r["id"]]
        hk = code.get(r["trigger"])
        rows.append({**{k: r[k] for k in ("id", "title", "severity", "first_day")}, "origins": hand,
                     "class": origin_class(hand), "haiku_primary": hk, "haiku_in_hand": hk in hand,
                     "haiku_exact": hand == [hk], "caught_at_write": at_write[r["id"]], "later_detected": later[r["id"]]})
    missing = set(ORIGINS_BY_HAND) ^ {r["id"] for r in rows}
    assert not missing, missing
    combos = Counter(tuple(sorted(r["origins"])) for r in rows)
    return {"rows": rows, "n": len(rows), "combos": combos,
            "origin_totals": {k: sum(1 for r in rows if k in r["origins"]) for k in ORIGIN_NAMES},
            "classes": Counter(r["class"] for r in rows), "multi": sum(1 for r in rows if len(r["origins"]) > 1),
            "agree_in_set": sum(r["haiku_in_hand"] for r in rows), "agree_exact": sum(r["haiku_exact"] for r in rows),
            "later_any": sum(1 for r in rows if r["later_detected"]),
            "later_by_class": {c: sum(1 for r in rows if r["class"] == c and r["later_detected"]) for c in CLASSES},
            "by_sev_class": {c: [sum(1 for r in rows if r["class"] == c and r["severity"] == s) for s in SEVS] for c in CLASSES}}


def fig_audit_staleness(end=NOW):
    """5.7: the fleet picture's age on every day, audits marked full or partial, and the wait a violation faced."""
    from datetime import timedelta
    au = audit_days()
    start = date.fromisoformat(au[0]["day"])
    audits = []
    for a in au:
        alive = family_alive(a["day"])
        covered = set(a["repos"])
        audits.append({"day": a["day"], "where": a["where"], "covered": len(covered), "alive": len(alive),
                       "missing": sorted(alive - covered), "extra": sorted(covered - alive),
                       "full": alive <= covered})
    ds = [a["day"] for a in audits]
    # Age is measured from the audit commit's timestamp to the end of each day (UTC), so a gap of 24 days and
    # 23 hours reads as 25, not 24, which a whole-day subtraction would give.
    from datetime import datetime, timezone
    ts_of = {a["day"]: datetime.fromisoformat(a["ts"]).astimezone(timezone.utc) for a in au}
    runs = [r["day"] for r in con().execute(
        "SELECT DISTINCT substr(ts,1,10) day FROM harness.tool_calls WHERE skill_name LIKE '%consistency-audit%' "
        "OR skill_name LIKE '%audit-compliance%' OR skill_name LIKE '%sync-plan%' ORDER BY 1") if r["day"] <= end]
    uncommitted = [d for d in runs if d not in ds]
    daily = []
    d = start
    while d.isoformat() <= end:
        prior = [x for x in ds if x <= d.isoformat()]
        day_end = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)
        daily.append((d.isoformat(), round((day_end - ts_of[prior[-1]]).total_seconds() / 86400, 2)))
        d += timedelta(days=1)
    waits = []
    d = start
    while d.isoformat() <= ds[-1]:
        nxt = next(x for x in ds if x >= d.isoformat())
        waits.append(days(d.isoformat(), nxt))
        d += timedelta(days=1)
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))]
    stale = [s for _, s in daily]
    return {"daily": daily, "audits": audits, "uncommitted_runs": uncommitted, "end": end,
            "n_audit_days": len(ds), "n_full": sum(a["full"] for a in audits),
            "max_stale": max(stale), "max_stale_day": daily[stale.index(max(stale))][0],
            "stale_at_end": stale[-1], "days_over_7": sum(1 for s in stale if s > 7), "n_days": len(stale),
            "waits": waits, "wait_median": q(waits, 0.5), "wait_p90": q(waits, 0.9), "wait_max": max(waits),
            "wait_same_day": sum(1 for w in waits if w == 0)}


FINAL = ["Fixed in the finding sweep", "Fixed in a later sweep", "Fixed, then reopened and fixed again",
         "Fixed, then reopened; open at the census", "Never fixed; open at the census", "Accepted exception",
         "No longer applicable"]


def fig_violation_outcomes():
    """5.8: every (check, repo) violation's state at the last audit, reopenings included, with later repair times."""
    au = audit_days()
    census = au[-1]
    L = ledger()
    reopened = {(r["check"], r["repo"]): r for r in q_violation_fix_time()["regressions"]}
    final_cell = {(r["check"], rp): m for r in census["rows"] for rp, m in r["cells"].items()}
    rows = []
    for v in L:
        k = (v["check"], v["repo"])
        cell = final_cell.get(k)
        if v["outcome"] == "still failing":
            f = FINAL[4]
        elif v["outcome"] in ("check retired", "repo left the audit", "check no longer applies"):
            f = FINAL[6]
        elif k in reopened:
            f = FINAL[3] if cell == "fail" else FINAL[2]
        else:
            f = FINAL[0] if v["outcome"] == "fixed in the same sweep" else FINAL[1]
        rows.append({**v, "final": f, "census_cell": cell, "reopened": reopened[k]["reopened"] if k in reopened else None,
                     "repair_days": days(v["opened"], v["closed"]) if v["outcome"] == "fixed later" else None})
    by_sev = {f: [sum(1 for r in rows if r["final"] == f and r["severity"] == s) for s in SEVS] for f in FINAL}
    totals = Counter(r["final"] for r in rows)
    later = [r["repair_days"] for r in rows if r["repair_days"] is not None]
    by_ctl = defaultdict(Counter)
    for r in rows:
        by_ctl[r["control"]][r["final"]] += 1
    open_now = sum(1 for r in rows if r["census_cell"] == "fail")
    return {"rows": rows, "n": len(rows), "totals": totals, "by_sev": by_sev, "sev_n": [sum(1 for r in rows if r["severity"] == s) for s in SEVS],
            "later_days": sorted(later), "later_median": median(later) if later else None,
            "later_by_sev": {s: sorted(r["repair_days"] for r in rows if r["repair_days"] is not None and r["severity"] == s) for s in SEVS},
            "reopened_n": len(reopened), "open_at_census": open_now, "census": census["day"],
            "exceptions": 0, "by_control": {c: dict(v) for c, v in by_ctl.items()}}
