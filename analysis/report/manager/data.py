"""Manager's thinking series: one function per question, each returning what its slides plot.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/manager/data.py      # prints every answer

Labels this topic made itself (register triggers, gate triggers, plugin-commit reasons, memory
purpose, commit origin) are in manager.sqlite, built by labels.py. Prompt intent is the lead's shared
detectors.prompt_intent.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.dirname(HERE))
from record import changeset_facts, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, REPO_ALIASES, category_of  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
FACTORY_REPOS = ("wayfare-skills", "hero-template")
APP_CATS = ("app", "app, no features yet")


@lru_cache(maxsize=None)
def con_():
    from cube.db import connect
    return connect("manager")


def rows(sql, args=()):
    return [dict(r) for r in con_().execute(sql, args).fetchall()]


def cat(repo):
    """The fleet root's own prompts and files are the factory, not an app."""
    return "allied" if repo in ("fleet", ".fleet") else category_of(repo)


def labels(task):
    return {r["key"]: json.loads(r["label_json"]) for r in rows("SELECT key, label_json FROM manager.labels WHERE task=?",
                                                                 (task,))}


def per_week(items, key, cats):
    """items: [(day, category)] -> {category: [count per week]} over WEEKS."""
    acc = defaultdict(Counter)
    for day, c in items:
        if day and day[:4] == "2026":
            acc[c][week_of(day)] += 1
    return {c: [acc[c].get(w, 0) for w in WEEKS] for c in cats}


def has_table(name):
    db, t = name.split(".")
    return bool(con_().execute(f"SELECT 1 FROM {db}.sqlite_master WHERE name=?", (t,)).fetchone())


# ------------------------------------------------------------------ Q written-reasons where the reasons live

def q_written_reasons_reasons():
    ws = labels("ws_reason")
    ws_day = {r["sha"]: r["day"] for r in rows("SELECT sha, day FROM git.commits WHERE repo='wayfare-skills'")}
    reg = rows("SELECT first_day, why FROM manager.reg_items")
    mem = rows("SELECT created_ts, has_why FROM harness.memories WHERE file != 'MEMORY.md'")
    dec = rows("SELECT first_seen_ts FROM knowledge.design_decisions")
    logs = rows("SELECT ts FROM plans.item_logs WHERE kind='decision'")
    items = ([(r["first_day"], "Register rules (why:)") for r in reg if r["why"]]
             + [(r["created_ts"][:10], "Memories with a why") for r in mem if r["has_why"]]
             + [(ws_day[k], "Plugin commits saying why") for k, v in ws.items() if v.get("reason") and k in ws_day]
             + [(r["first_seen_ts"][:10], "Design decisions") for r in dec if r["first_seen_ts"]]
             + [(r["ts"][:10], "Decision logs (.plans)") for r in logs])
    cats = ["Register rules (why:)", "Memories with a why", "Plugin commits saying why", "Design decisions",
            "Decision logs (.plans)"]
    weekly = per_week(items, lambda x: x, cats)
    share = {
        "Register rules": (sum(1 for r in reg if r["why"]), len(reg)),
        "Memories": (sum(r["has_why"] or 0 for r in mem), len(mem)),
        "Plugin commits": (sum(1 for v in ws.values() if v.get("reason")), len(ws)),
    }
    gate = labels("gate_trigger")
    ws_gate = [k for k in gate if k.startswith("wayfare-skills:")]
    share["Gate changes (plugin)"] = (sum(1 for k in ws_gate if ws.get(k.split(":")[1], {}).get("reason")),
                                      sum(1 for k in ws_gate if k.split(":")[1] in ws))
    first = {c: next((WEEKS[i] for i, v in enumerate(weekly[c]) if v), None) for c in cats}
    totals = {c: sum(v) for c, v in weekly.items()}
    since_jul = sum(1 for d_, _ in items if d_ and d_ >= "2026-07-01")
    return {"weekly": weekly, "share": share, "first": first, "totals": totals,
            "share_since_jul": since_jul / max(1, sum(totals.values()))}


# ------------------------------------------------------------------ Q owner-attention-split attention

def prompt_rows():
    return [r for r in rows("SELECT ts, day, repo, text_redacted t FROM harness.prompts WHERE is_slash_command=0")
            if r["repo"] not in OUT_OF_SCOPE]


def intent_rows():
    """Every typed prompt with the lead's intent label, if the shared table has landed."""
    if not has_table("detectors.prompt_intent"):
        return None
    cols = [r[1] for r in con_().execute("PRAGMA detectors.table_info(prompt_intent)")]
    return rows("SELECT * FROM detectors.prompt_intent"), cols


def q_owner_attention_split_attention():
    ps = prompt_rows()
    side = lambda r: "Factory (template, plugin, infra, fleet root)" if cat(r["repo"]) == "allied" else "Products"
    cats = ["Products", "Factory (template, plugin, infra, fleet root)"]
    weekly = per_week([(r["day"], side(r)) for r in ps], None, cats)
    share = [(f / (a + f)) if (a + f) >= 10 else None for a, f in zip(weekly[cats[0]], weekly[cats[1]])]
    by_month = defaultdict(Counter)
    for r in ps:
        if r["day"][:4] == "2026":
            by_month[side(r)][r["day"][:7]] += 1
    month_share = {m: by_month[cats[1]][m] / max(1, by_month[cats[0]][m] + by_month[cats[1]][m]) for m in MONTHS}
    repo_month = defaultdict(Counter)
    for r in ps:
        if r["day"][:4] == "2026" and cat(r["repo"]) == "allied":
            repo_month[r["repo"]][r["day"][:7]] += 1
    out = {"weekly": weekly, "share": share, "month_share": month_share, "n": len(ps),
           "factory_repo_month": {k: [v.get(m, 0) for m in MONTHS] for k, v in repo_month.items()}}
    pi = [r for r in rows("SELECT day, repo, target FROM detectors.prompt_intent") if r["repo"] not in OUT_OF_SCOPE]
    tnames = {"app": "About a product", "factory": "About the factory (template, plugin, process)",
              "infra": "About infrastructure", "none": "No target (approvals, answers)"}
    out["target_weekly"] = per_week([(r["day"], tnames[r["target"]]) for r in pi], None, list(tnames.values()))
    tm = defaultdict(Counter)
    for r in pi:
        if r["day"][:4] == "2026":
            tm[r["day"][:7]][r["target"]] += 1
    out["target_month_share"] = {tnames[t]: [tm[m][t] / sum(tm[m].values()) if sum(tm[m].values()) >= 100 else None
                                             for m in MONTHS] for t in ("app", "factory", "infra")}
    out["target_month"] = {m: dict(tm[m]) for m in MONTHS}
    out["n_intent"] = len(pi)
    return out


# ------------------------------------------------------------------ Q correction-kinds-over-time corrections by kind

KINDS = [("error", "Catches an error"), ("taste", "Taste or direction"), ("scope", "Scope (too much, too little)")]


def corrections():
    return [r for r in rows("SELECT ts, day, repo, intent, correction_kind FROM detectors.prompt_intent "
                            "WHERE intent IN ('correction','redirect')") if r["repo"] not in OUT_OF_SCOPE]


def q_correction_kinds_over_time_corrections():
    cs = [r for r in corrections() if r["correction_kind"] in dict(KINDS)]
    names = dict(KINDS)
    weekly = per_week([(r["day"], names[r["correction_kind"]]) for r in cs], None, list(names.values()))
    mc = defaultdict(Counter)
    for r in cs:
        if r["day"][:4] == "2026":
            mc[r["day"][:7]][r["correction_kind"]] += 1
    month_share = {names[k]: [mc[m][k] / sum(mc[m].values()) if sum(mc[m].values()) >= 30 else None for m in MONTHS]
                   for k in names}
    total = Counter(r["correction_kind"] for r in cs)
    by_intent = Counter((r["intent"], r["correction_kind"]) for r in cs)
    return {"weekly": weekly, "month_share": month_share, "month_n": {m: sum(mc[m].values()) for m in MONTHS},
            "total": total, "n": len(cs), "by_intent": by_intent}


# ------------------------------------------------------------------ Q corrections-to-memory memory from correction

MEM_PURPOSE = {"correction": "Records a correction or mistake", "feedback": "Records a correction or mistake",
               "preference": "States a preference", "reference": "Reference (where, how)", "fact": "Project fact"}


# A path a correction's answer lands in when it becomes a rule or a check rather than a memory.
# CI workflows and HERO.md are left out: sessions change them for many other reasons.
RULE_PATH = re.compile(r"(^|/)(skills/|\.claude/rules/|hooks/|\.githooks/|\.fleet/)|"
                       r"(^|/)(\.pre-commit-config\.ya?ml|AGENTS\.md|CLAUDE\.md)$|register")
ROUTES = ["A rule or check", "A memory", "Neither on record"]


def correction_routes():
    """What came of each correction typed while session logs exist: a rule or check changed by a PR the same
    session opened after it and merged, a correction memory written in that repo within a day, or neither on
    record. A rule change in the same session is not proof it answers the correction, so the first route is a
    ceiling."""
    from datetime import datetime, timedelta
    ts = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    sessions = defaultdict(list)
    unparsed = 0
    for r in rows("SELECT repo, first_ts, last_ts, pr_links FROM harness.sessions WHERE first_ts IS NOT NULL"):
        links = []
        for link in json.loads(r["pr_links"] or "[]"):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
            if m:
                links.append((REPO_ALIASES.get(m.group(1), m.group(1)), int(m.group(2))))
            else:
                unparsed += 1
        sessions[r["repo"]].append((ts(r["first_ts"]), ts(r["last_ts"]), links))
    if not sessions:
        return {"unavailable": "harness.sessions has no timed sessions"}
    opened = {(r["repo"], r["number"]): ts(r["created_ts"])
              for r in rows("SELECT repo, number, created_ts FROM github.prs WHERE merged_ts IS NOT NULL")}
    rule_prs = set()
    for r in rows("SELECT repo, pr_number, files_json FROM pr_commits.pr_commits"):
        if any(RULE_PATH.search(p["path"]) for p in json.loads(r["files_json"] or "[]")):
            rule_prs.add((r["repo"], r["pr_number"]))
    lab = labels("mem_purpose")
    corr_mem, unlabelled_mem = defaultdict(list), defaultdict(list)
    for m in rows("SELECT repo, file, created_ts FROM harness.memories WHERE file != 'MEMORY.md'"):
        purpose = MEM_PURPOSE.get(lab.get(f"{m['repo']}:{m['file']}", {}).get("purpose"))
        if purpose is None:
            unlabelled_mem[m["repo"]].append(ts(m["created_ts"]))
        elif purpose == "Records a correction or mistake":
            corr_mem[m["repo"]].append(ts(m["created_ts"]))
    first = min(f for v in sessions.values() for f, _, _ in v)
    out = []
    memory_unlabelled = 0
    for c in corrections():
        t = ts(c["ts"])
        if t < first:
            continue
        prs = {p for f, l, links in sessions.get(c["repo"], []) if f <= t <= l for p in links}
        rule = any(p in rule_prs and p in opened and opened[p] >= t for p in prs)
        memory = any(t <= m <= t + timedelta(days=1) for m in corr_mem.get(c["repo"], []))
        if not rule and not memory and any(t <= m <= t + timedelta(days=1) for m in unlabelled_mem.get(c["repo"], [])):
            memory_unlabelled += 1
            continue
        out.append((c["day"], ROUTES[0] if rule else ROUTES[1] if memory else ROUTES[2]))
    return {"routes": out, "unparsed_pr_links": unparsed, "memory_unlabelled": memory_unlabelled}


def q_corrections_to_memory_memory():
    lab = labels("mem_purpose")
    if not lab:
        return {"unavailable": "no mem_purpose labels: run report/manager/labels.py"}
    purpose = lambda m: MEM_PURPOSE.get(lab.get(f"{m['repo']}:{m['file']}", {}).get("purpose"))
    all_mem = rows("SELECT repo, file, created_ts FROM harness.memories WHERE file != 'MEMORY.md'")
    mem = [m for m in all_mem if purpose(m)]
    if not mem:
        return {"unavailable": "no labelled memories"}
    cats = list(dict.fromkeys(MEM_PURPOSE.values()))
    items = [(m["created_ts"][:10], purpose(m)) for m in mem]
    weekly = per_week(items, None, cats)
    counts = Counter(c for _, c in items)
    from datetime import datetime
    ts = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    corr = defaultdict(list)
    for r in corrections():
        corr[r["repo"]].append(ts(r["ts"]))
    for v in corr.values():
        v.sort()
    buckets = ["Within an hour", "Same day", "Within a week", "Later", "No earlier correction"]
    lat = {True: Counter(), False: Counter()}
    for m in mem:
        is_corr = purpose(m) == cats[0]
        t = ts(m["created_ts"])
        prev = [c for c in corr.get(m["repo"], []) if c <= t]
        h = (t - prev[-1]).total_seconds() / 3600 if prev else None
        lat[is_corr][buckets[4] if h is None else buckets[0] if h < 1 else buckets[1] if h < 24 else
                     buckets[2] if h < 168 else buckets[3]] += 1
    first_mem = min(m["created_ts"][:10] for m in all_mem)
    n_corr_since = sum(1 for r in corrections() if r["day"] >= first_mem)
    cr = correction_routes()
    out = {"weekly": weekly, "counts": counts, "n": len(mem), "unlabelled": len(all_mem) - len(mem),
           "latency": lat, "buckets": buckets, "corrections_since_first_memory": n_corr_since,
           "first_memory": first_mem}
    if "unavailable" in cr:
        return {**out, "routes": cr}
    routes = cr["routes"]
    return {**out, "routes": Counter(r for _, r in routes), "routes_weekly": per_week(routes, None, ROUTES),
            "routes_from": min(d for d, _ in routes) if routes else None,
            "unparsed_pr_links": cr["unparsed_pr_links"], "routes_memory_unlabelled": cr["memory_unlabelled"]}


# ------------------------------------------------------------------ Q auto-approve-changes the auto-approve gate

GATE_CATS = [("incident", "Fixes a failure of the gate"), ("false_block", "Fixes a false block"),
             ("cost", "Cuts cost"), ("capability", "New check or behaviour"),
             ("adopt", "Install, re-vendor, rename"), ("other", "Docs, tests, refactor")]


def gate_changes():
    """One row per distinct change to the gate: the same subject landing in several repos on one day
    (a fan-out of one decision) counts once, under the repo that carries the logic when it is among them."""
    lab = labels("gate_trigger")
    meta = {f"{r['repo']}:{r['sha']}": r for r in rows("SELECT repo, sha, day, subject FROM git.commits")}
    norm = lambda s: re.sub(r"\s*\(#\d+\)\s*$", "", (s or "").strip().lower())
    groups = defaultdict(list)
    for k, v in lab.items():
        m = meta.get(k)
        if m and m["repo"] not in OUT_OF_SCOPE:
            groups[(m["day"], norm(m["subject"]))].append((k, v))
    out = []
    for (d, subj), members in groups.items():
        k, v = next(((k, v) for k, v in members if k.startswith("wayfare-skills:")), members[0])
        out.append({"day": d, "subject": subj, "key": k, "trigger": v.get("trigger"), "repos": len(members),
                    "evidence": v.get("evidence", "")})
    return sorted(out, key=lambda r: r["day"])


def q_auto_approve_changes_gate():
    lab = labels("gate_trigger")
    day = {f"{r['repo']}:{r['sha']}": r["day"] for r in rows("SELECT repo, sha, day FROM git.commits")}
    names = dict(GATE_CATS)
    changes = gate_changes()
    items = [(c["day"], names.get(c["trigger"], names["other"])) for c in changes]
    weekly = per_week(items, None, [n for _, n in GATE_CATS])
    own = Counter(names.get(v.get("trigger"), names["other"]) for k, v in lab.items() if k.startswith("wayfare-skills:"))
    copies = Counter(names.get(v.get("trigger"), names["other"]) for k, v in lab.items()
                     if not k.startswith("wayfare-skills:") and k.split(":")[0] not in OUT_OF_SCOPE)
    incidents = sorted((day.get(k), k) for k, v in lab.items() if v.get("trigger") == "incident")
    # the logic lives in the plugin from 2 May; before that each repo carried its own copy
    behav = {"Fixes a failure of the gate", "Fixes a false block", "Cuts cost", "New check or behaviour"}
    ws_b = sum(v for k, v in own.items() if k in behav)
    ws_react = own["Fixes a failure of the gate"] + own["Fixes a false block"]
    distinct = Counter(n for _, n in items)
    fanouts = [c for c in changes if c["repos"] >= 5]
    return {"weekly": weekly, "own": own, "copies": copies, "n": len(items), "n_commits": len(lab), "ws_behav": ws_b,
            "ws_react": ws_react, "incidents": incidents, "distinct": distinct, "fanouts": fanouts,
            "changes": changes}


# ------------------------------------------------------------------ Q controls-after-incidents controls after incidents

REG_CATS = [("fleet_bug", "Seen in a fleet repo"), ("outside_incident", "Outside incident"),
            ("foreseen", "Foreseen, nothing broke yet")]


def q_controls_after_incidents_controls():
    lab = labels("reg_trigger")
    names = dict(REG_CATS)
    reg = rows("SELECT kind, id, first_day, sha FROM manager.reg_items")
    items = [(r["first_day"], names.get(lab.get(f"{r['kind']}:{r['id']}", {}).get("trigger"), names["foreseen"]))
             for r in reg]
    weekly = per_week(items, None, [n for _, n in REG_CATS])
    by_kind = {k: Counter(names.get(lab.get(f"{k}:{r['id']}", {}).get("trigger")) for r in reg if r["kind"] == k)
               for k in ("control", "check")}
    first_sha = Counter(r["sha"] for r in reg).most_common(1)[0]
    total = Counter(c for _, c in items)
    later = Counter(c for (d, c), r in zip(items, reg) if r["sha"] != first_sha[0])
    return {"weekly": weekly, "by_kind": by_kind, "total": total, "n": len(reg), "first_commit_ids": first_sha[1],
            "later": later}


# ------------------------------------------------------------------ Q register-origin the register

def q_register_origin_register():
    commits = rows("SELECT source, day, subject, ids_added FROM manager.reg_commits")
    homes = {"hero-template": "In hero-template", ".fleet": "In the fleet register (.fleet)",
             "wayfare-skills": "Baseline in the plugin"}
    weekly = per_week([(c["day"], homes[c["source"]]) for c in commits], None, list(homes.values()))
    ids = per_week([(c["day"], "ids") for c in commits for _ in range(c["ids_added"])], None, ["ids"])["ids"]
    repo_first = {r["repo"]: r["d"] for r in rows("SELECT repo, MIN(day) d FROM git.commits GROUP BY repo")
                  if r["repo"] not in OUT_OF_SCOPE}
    active = lambda d: sum(1 for v in repo_first.values() if v <= d)
    clones = {r["repo"]: r["d"] for r in rows("""SELECT repo, MIN(day) d FROM git.commits WHERE repo NOT IN
              ('hero-template','wayfare-skills','infrastructure-root','infrastructure-environments')
              AND day >= '2026-07-14' GROUP BY repo""")}
    return {"weekly": weekly, "ids": ids, "n_commits": len(commits),
            "repos_at_start": active("2026-07-17"), "repos_at_move": active("2026-09-13"),
            "repos_before_template": sum(1 for v in repo_first.values() if v < "2026-07-14"),
            "first": min(c["day"] for c in commits), "commits": commits}


# ------------------------------------------------------------------ Q restated-rules rules restated

def q_restated_rules_restated():
    lab = labels("mem_purpose")
    groups = rows("SELECT grp, rule, key FROM manager.mem_rule_groups")
    created = {f"{r['repo']}:{r['file']}": r["created_ts"][:10]
               for r in rows("SELECT repo, file, created_ts FROM harness.memories")}
    by_grp = defaultdict(list)
    for g in groups:
        by_grp[(g["grp"], g["rule"])].append(g["key"])
    restating = set()
    for keys in by_grp.values():
        restating.update(sorted(keys, key=lambda k: created.get(k, ""))[1:])
    items = []
    for k, v in lab.items():
        c = ("Restates a rule saved elsewhere" if k in restating else
             "States a rule" if v.get("rule", "").strip() else "No standing rule")
        items.append((created.get(k), c))
    cats = ["States a rule", "Restates a rule saved elsewhere", "No standing rule"]
    weekly = per_week(items, None, cats)
    top = sorted(((rule, len(keys), sorted({k.split(':')[0] for k in keys})) for (g, rule), keys in by_grp.items()),
                 key=lambda x: -x[1])
    return {"weekly": weekly, "groups": top, "n_rules": sum(1 for v in lab.values() if v.get("rule", "").strip()),
            "n": len(lab), "n_restating": len(restating), "n_grouped": sum(len(k) for k in by_grp.values())}


# ------------------------------------------------------------------ Q plugin-restructures restructures

def q_plugin_restructures_restructures():
    sv = rows("SELECT skill, ts, day, change_type, subject, old_path FROM knowledge.skill_versions ORDER BY ts")
    live, weekly_live = set(), {}
    by_day = defaultdict(list)
    for v in sv:
        by_day[v["day"]].append(v)
    for v in sv:
        if v["change_type"] == "add":
            live.add(v["skill"])
        elif v["change_type"] == "delete":
            live.discard(v["skill"])
        elif v["change_type"] == "rename":
            live.discard((v["old_path"] or "/").split("/")[1])
            live.add(v["skill"])
        weekly_live[week_of(v["day"])] = len(live)
    cur, series = None, []
    for w in WEEKS:
        cur = weekly_live.get(w, cur)
        series.append(cur)
    moves = Counter(v["day"] for v in sv if v["change_type"] in ("rename", "delete"))
    events = sorted(d for d, n in moves.items() if n >= 4)
    ws = labels("ws_reason")
    ws_rows = rows("SELECT sha, day, subject FROM git.commits WHERE repo='wayfare-skills'")
    table = []
    for d in events:
        end = (date.fromisoformat(d) + timedelta(days=14)).isoformat()
        subj = next(v["subject"] for v in by_day[d] if v["change_type"] in ("rename", "delete"))
        fixes = [r for r in ws_rows if d < r["day"] <= end and ws.get(r["sha"], {}).get("incident")]
        table.append({"day": d, "subject": subj,
                      "renamed": sum(1 for v in by_day[d] if v["change_type"] == "rename"),
                      "deleted": sum(1 for v in by_day[d] if v["change_type"] == "delete"),
                      "added": sum(1 for v in by_day[d] if v["change_type"] == "add"),
                      "fixes_14d": len(fixes), "fix_subjects": [f["subject"] for f in fixes]})
    after_rename = rows("""SELECT repo, day, subject FROM git.commits WHERE day BETWEEN '2026-09-21' AND '2026-10-05'
                           AND repo != 'wayfare-skills' AND (subject LIKE '%wayfare%' OR subject LIKE '%re-vendor%')""")
    return {"live": series, "events": table, "consumer_fixes_after_rename": after_rename,
            "now": len(live)}


# ------------------------------------------------------------------ Q limit-driven-changes spend and limits

# Plugin commits whose body states a cost motive, confirmed by hand; the model label alone over-counts.
COST_CHANGES = [("2026-03-28", "194cd43", "skip Claude on irrelevant commits"),
                ("2026-04-01", "f0e7fd8", "Haiku for pre-commit"),
                ("2026-08-28", "db701b7", "scripted gates before the judge"),
                ("2026-09-18", "597dd87", "builds on a cheaper subagent"),
                ("2026-09-24", "52864af", "verify once per goal")]


def q_limit_driven_changes_spend():
    s = rows("SELECT day, main_model, cost_usd, subagent_count FROM harness.sessions WHERE day IS NOT NULL")
    fam = lambda m: ("Opus" if "opus" in (m or "") else "Sonnet" if "sonnet" in (m or "") else
                     "Fable" if "fable" in (m or "") else "Other")
    acc = defaultdict(Counter)
    for r in s:
        acc[fam(r["main_model"])][week_of(r["day"])] += r["cost_usd"] or 0
    cats = ["Opus", "Fable", "Sonnet", "Other"]
    weekly = {c: [round(acc[c].get(w, 0)) for w in WEEKS] for c in cats}
    limits = rows("SELECT substr(ts,1,10) d, kind FROM harness.limit_events ORDER BY ts")
    mems = rows("""SELECT repo, name, created_ts FROM harness.memories WHERE name LIKE '%cost%' OR name LIKE '%limit%'
                   OR name LIKE '%spend%' OR name LIKE '%budget%'""")
    return {"weekly": weekly, "changes": COST_CHANGES, "first_limit": limits[0]["d"] if limits else None,
            "limits": len(limits), "cost_memories": mems,
            "first_session": min(r["day"] for r in s)}


# ------------------------------------------------------------------ Q owner-as-go-between the go-between

def q_owner_as_go_between_gobetween():
    ps = prompt_rows()
    repos = {r["repo"] for r in rows("SELECT DISTINCT repo FROM git.commits")} - OUT_OF_SCOPE
    pats = {r: re.compile(r"(?<![\w/-])" + re.escape(r) + r"(?![\w-])", re.I) for r in repos
            if r not in ("website", "auth")}
    relay = []
    for r in ps:
        other = [n for n, p in pats.items() if n != r["repo"] and p.search(r["t"] or "")]
        if other:
            relay.append((r, other))
    total = per_week([(r["day"], "all") for r in ps], None, ["all"])["all"]
    rel = per_week([(r["day"], "relay") for r, _ in relay], None, ["relay"])["relay"]
    msgs = per_week([(r["created_ts"][:10], "m") for r in rows("SELECT created_ts FROM plans.messages")], None,
                    ["m"])["m"]
    by_repo = Counter(r["repo"] for r, _ in relay)
    by_month = defaultdict(lambda: [0, 0])
    for r in ps:
        by_month[r["day"][:7]][1] += 1
    for r, _ in relay:
        by_month[r["day"][:7]][0] += 1
    return {"relay": rel, "total": total, "messages": msgs, "n_relay": len(relay), "n": len(ps),
            "by_repo": by_repo, "by_month": {m: v for m, v in by_month.items()},
            "rate": [(a / b) if b >= 20 else None for a, b in zip(rel, total)],
            "examples": [(r["day"], r["repo"], o, (r["t"] or "")[:140]) for r, o in relay[-40:]]}


# ------------------------------------------------------------------ Q care-vs-speed speed vs care

FIX_RE = re.compile(r"^(fix|revert|hotfix)\b|\bfix(es|ed)?\b", re.I)


def q_care_vs_speed_speed(fast_hours=0.5):
    prs = rows("""SELECT repo, number, merged_ts, hours_to_merge FROM github.prs
                  WHERE merged_ts IS NOT NULL AND hours_to_merge IS NOT NULL""")
    files = defaultdict(set)
    for r in rows("""SELECT c.repo, c.pr_number, f.path FROM git.commits c JOIN git.commit_files f
                     ON f.repo=c.repo AND f.sha=c.sha WHERE c.pr_number IS NOT NULL"""):
        files[(r["repo"], r["pr_number"])].add(r["path"])
    commits = defaultdict(list)
    cfiles = defaultdict(set)
    for r in rows("SELECT c.repo, c.sha, c.committed_ts ts, c.subject, c.is_bot FROM git.commits c"):
        commits[r["repo"]].append(r)
    for r in rows("SELECT repo, sha, path FROM git.commit_files"):
        cfiles[(r["repo"], r["sha"])].add(r["path"])
    for v in commits.values():
        v.sort(key=lambda r: r["ts"] or "")
    out = []
    from datetime import datetime
    parse = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    for p in prs:
        if p["repo"] in OUT_OF_SCOPE or p["merged_ts"][:4] != "2026":
            continue
        base = files.get((p["repo"], p["number"]))
        if not base:
            continue
        m = parse(p["merged_ts"])
        fix = False
        for c in commits[p["repo"]]:
            if not c["ts"]:
                continue
            dd = (parse(c["ts"]) - m).total_seconds() / 86400
            if dd <= 0:
                continue
            if dd > 7:
                break
            cf = cfiles.get((p["repo"], c["sha"]), set())
            if cf and len(cf & base) / len(base) >= 0.5 and FIX_RE.search(c["subject"] or "") and not c["is_bot"]:
                fix = True
                break
        out.append({"repo": p["repo"], "day": p["merged_ts"][:10], "fast": p["hours_to_merge"] < fast_hours,
                    "fix": fix, "cat": cat(p["repo"])})
    def rate(sel):
        return (sum(o["fix"] for o in sel) / len(sel)) if len(sel) >= 15 else None
    fast_m = [rate([o for o in out if o["day"][:7] == m and o["fast"]]) for m in MONTHS]
    slow_m = [rate([o for o in out if o["day"][:7] == m and not o["fast"]]) for m in MONTHS]
    share_fast = []
    for w in WEEKS:
        sel = [o for o in out if week_of(o["day"]) == w]
        share_fast.append(sum(o["fast"] for o in sel) / len(sel) if len(sel) >= 5 else None)
    by_cat = {}
    for c in ("app", "allied"):
        sel = [o for o in out if (o["cat"] in APP_CATS if c == "app" else o["cat"] == c)]
        by_cat[c] = (rate([o for o in sel if o["fast"]]), rate([o for o in sel if not o["fast"]]),
                     sum(o["fast"] for o in sel) / max(1, len(sel)), len(sel))
    n_fast = sum(o["fast"] for o in out)
    return {"fast_month": fast_m, "slow_month": slow_m, "share_fast": share_fast, "by_cat": by_cat,
            "n": len(out), "n_fast": n_fast, "fast_rate": rate([o for o in out if o["fast"]]),
            "slow_rate": rate([o for o in out if not o["fast"]])}


# ------------------------------------------------------------------ Q incident-bursts incidents

INCIDENTS = [("2026-07-23", "Dependabot merge reverted (2 repos)"),
             ("2026-08-26", "CI failure peak (35 failed runs)"),
             ("2026-08-30", "First usage-limit crunch"),
             ("2026-09-18", "Auto-approve reverted to last good"),
             ("2026-09-21", "Rename breaks auto-approve fleet-wide")]


LAST_DAY = date(2026, 9, 24)


def q_incident_bursts_incidents():
    cs = [c for c in changeset_facts(con_()) if c["repo"] in FACTORY_REPOS]
    weekly = {r: [sum(1 for c in cs if c["repo"] == r and c["week"] == w) for w in WEEKS] for r in FACTORY_REPOS}
    out = []
    for d, name in INCIDENTS:
        d0 = date.fromisoformat(d)
        days_after = min(14, (LAST_DAY - d0).days + 1)
        before = sum(1 for c in cs if d0 - timedelta(days=14) <= date.fromisoformat(c["day"]) < d0)
        after = sum(1 for c in cs if d0 <= date.fromisoformat(c["day"]) < d0 + timedelta(days=days_after))
        out.append({"day": d, "name": name, "before": before, "after": after, "days_after": days_after,
                    "per_day_before": before / 14, "per_day_after": after / days_after})
    return {"weekly": weekly, "incidents": out, "n": len(cs)}


# ------------------------------------------------------------------ Q practice-flow-direction up or down

def q_practice_flow_direction_origin():
    lab = labels("origin")
    day = {f"{r['repo']}:{r['sha']}": r["day"] for r in rows(
        "SELECT repo, sha, day FROM git.commits WHERE repo IN ('hero-template','wayfare-skills')")}
    def kind(v):
        named = [x.strip() for x in (v.get("repo") or "").split(",") if x.strip()]
        from_product = any(cat(n) in APP_CATS for n in named)
        if v.get("origin") == "product" and from_product:
            return "Brought up from a product"
        if v.get("origin") == "report" and from_product:
            return "Answers a product's report"
        return "The factory's own idea"
    cats = ["Brought up from a product", "Answers a product's report", "The factory's own idea"]
    items = [(day.get(k), kind(v)) for k, v in lab.items()]
    weekly = per_week(items, None, cats)
    by_repo = defaultdict(Counter)
    for k, v in lab.items():
        kk = kind(v)
        if kk != cats[2]:
            for n in [x.strip() for x in (v.get("repo") or "").split(",") if x.strip()]:
                if cat(n) in APP_CATS:
                    by_repo[n][kk] += 1
    by_shared = {r: Counter(kind(v) for k, v in lab.items() if k.startswith(r + ":")) for r in FACTORY_REPOS}
    prop = rows("""SELECT p.upstream_repo u, p.downstream_repo d, p.lag_hours lag, p.upstream_subject s
                   FROM detectors.propagation p""")
    same_day = sum(1 for p in prop if (p["lag"] or 0) < 24)
    dependabot = sum(1 for p in prop if re.search(r"\bbump|deps", p["s"] or "", re.I))
    return {"weekly": weekly, "by_repo": {k: dict(v) for k, v in by_repo.items()}, "by_shared": by_shared,
            "n": len(items), "prop_n": len(prop), "prop_same_day": same_day, "prop_deps": dependabot}


def all_data():
    return {"written-reasons": q_written_reasons_reasons(), "owner-attention-split": q_owner_attention_split_attention(), "correction-kinds-over-time": q_correction_kinds_over_time_corrections(), "corrections-to-memory": q_corrections_to_memory_memory(), "auto-approve-changes": q_auto_approve_changes_gate(),
            "controls-after-incidents": q_controls_after_incidents_controls(), "register-origin": q_register_origin_register(), "restated-rules": q_restated_rules_restated(), "plugin-restructures": q_plugin_restructures_restructures(),
            "limit-driven-changes": q_limit_driven_changes_spend(), "owner-as-go-between": q_owner_as_go_between_gobetween(), "care-vs-speed": q_care_vs_speed_speed(), "incident-bursts": q_incident_bursts_incidents(),
            "practice-flow-direction": q_practice_flow_direction_origin(), "plugin-restructures-blast": q_plugin_restructures_blast()}


if __name__ == "__main__":
    import pprint
    names = sys.argv[1:] or None
    for k, fn in [("written-reasons", q_written_reasons_reasons), ("owner-attention-split", q_owner_attention_split_attention), ("correction-kinds-over-time", q_correction_kinds_over_time_corrections), ("corrections-to-memory", q_corrections_to_memory_memory), ("auto-approve-changes", q_auto_approve_changes_gate),
                  ("controls-after-incidents", q_controls_after_incidents_controls), ("register-origin", q_register_origin_register), ("restated-rules", q_restated_rules_restated), ("plugin-restructures", q_plugin_restructures_restructures),
                  ("limit-driven-changes", q_limit_driven_changes_spend), ("owner-as-go-between", q_owner_as_go_between_gobetween), ("care-vs-speed", q_care_vs_speed_speed), ("incident-bursts", q_incident_bursts_incidents),
                  ("practice-flow-direction", q_practice_flow_direction_origin)]:
        if names and k not in names:
            continue
        d = fn()
        print(f"==== Q 18.{k}")
        pprint.pprint({a: b for a, b in d.items() if a not in ("weekly", "examples", "commits")}, width=140,
                      compact=True)


# ------------------------------------------------------------------ Book figure 7.3: restructures and their blast radius

RESTRUCTURE_MIN = 4   # skills renamed or removed on one day
REPAIR_DAYS = 14
# The rename's own PRs: the plugin's rename (#106), the repository's (#108), the caller fix (#115), and the two waves
# of consumer PRs (by title), so the incident lane timeline can be drawn from github.prs alone.
RENAME_WAVES = [("chore: hero-skills is wayfare, and the caller points at the renamed repo", "Point the caller at the renamed repo"),
                ("ci(auto-approve): re-vendor the caller", "Re-vendor the caller")]


def _plugin_terms(day, by_day):
    """The names a consumer's PR title would carry when it changes what points at the plugin: the plugin's
    repository names, every multi-word skill renamed or removed that day (old and new directory name), the
    caller and a re-vendor. Single-word skill names (wayfare, fleet, harden) are ordinary words and are left out;
    bodies are not searched because agent commits name the skill they ran, which is use, not repair."""
    terms = {"hero-skills", "wayfare-skills", "is wayfare", "wayfare plugin", "re-vendor", "the caller", "shared workflow"}
    for v in by_day[day]:
        if v["change_type"] in ("rename", "delete"):
            for name in (v["skill"], (v["old_path"] or "/").split("/")[1]):
                if "-" in name:
                    terms.add(name)
    return {t.lower() for t in terms}




def q_plugin_restructures_blast():
    sv = rows("SELECT skill, ts, day, change_type, subject, old_path FROM knowledge.skill_versions ORDER BY ts")
    by_day = defaultdict(list)
    for v in sv:
        by_day[v["day"]].append(v)
    moves = Counter(v["day"] for v in sv if v["change_type"] in ("rename", "delete"))
    events = sorted(d for d, n in moves.items() if n >= RESTRUCTURE_MIN)
    ws = labels("ws_reason")
    ws_rows = rows("SELECT sha, day, subject, conv_type FROM git.commits WHERE repo='wayfare-skills' AND is_merge=0")
    # Merged PRs, not git commits: one consumer's mirror (saga) stops before the rename, GitHub's record does not.
    consumers = rows("SELECT repo, number, substr(merged_ts, 1, 10) day, title subject, created_ts, merged_ts FROM github.prs "
                     "WHERE repo != 'wayfare-skills' AND merged_ts >= '2026-03-01'")
    consumers = [c for c in consumers if cat(c["repo"]) in APP_CATS + ("allied",)]
    hero_first = {r["repo"]: r["d"] for r in rows("SELECT c.repo, MIN(c.day) d FROM git.commit_files f JOIN git.commits c "
                                                   "ON c.repo=f.repo AND c.sha=f.sha WHERE f.path='HERO.md' GROUP BY c.repo")}
    caller_first = {r["repo"]: r["d"] for r in rows("SELECT c.repo, MIN(c.day) d FROM git.commit_files f JOIN git.commits c "
                                                     "ON c.repo=f.repo AND c.sha=f.sha WHERE f.path LIKE '.github/workflows/auto-approve.y%' "
                                                     "GROUP BY c.repo")}
    table = []
    for d in events:
        end = (date.fromisoformat(d) + timedelta(days=REPAIR_DAYS)).isoformat()
        subj = next(v["subject"] for v in by_day[d] if v["change_type"] in ("rename", "delete"))
        fixes = [r for r in ws_rows if d < r["day"] <= end and ws.get(r["sha"], {}).get("incident")]
        terms = _plugin_terms(d, by_day)
        repairs = [c for c in consumers if d < c["day"] <= end and any(t in (c["subject"] or "").lower() for t in terms)]
        exposed_skills = sorted(r for r, first in hero_first.items() if first <= d and cat(r) in APP_CATS + ("allied",) and r != "wayfare-skills")
        exposed_caller = sorted(r for r, first in caller_first.items() if first <= d and cat(r) in APP_CATS + ("allied",) and r != "wayfare-skills")
        repo_days = Counter((c["repo"], c["day"]) for c in repairs)
        burst_day = Counter(c["day"] for c in repairs).most_common(1)
        table.append({"day": d, "subject": subj,
                      "renamed": sum(1 for v in by_day[d] if v["change_type"] == "rename"),
                      "deleted": sum(1 for v in by_day[d] if v["change_type"] == "delete"),
                      "added": sum(1 for v in by_day[d] if v["change_type"] == "add"),
                      "plugin_fixes_14d": len(fixes), "fix_subjects": [f["subject"] for f in fixes],
                      "repair_commits_14d": len(repairs), "repair_repos": len({c["repo"] for c in repairs}),
                      "exposed_skills_repos": len(exposed_skills), "exposed_caller_repos": len(exposed_caller),
                      "unrepaired_caller_repos": sorted(set(exposed_caller) - {c["repo"] for c in repairs}),
                      "repairs_first_day": burst_day[0] if burst_day else None,
                      "repos_repaired_within_1d": len({r for (r, dd) in repo_days if dd <= (date.fromisoformat(d) + timedelta(days=1)).isoformat()}),
                      "repair_subjects": Counter(c["subject"] for c in repairs).most_common(6)})
    # The 21 Sep incident, hour by hour, from the PRs themselves.
    prs = rows("SELECT repo, number, title, created_ts, merged_ts FROM github.prs WHERE merged_ts BETWEEN '2026-09-21' AND '2026-09-25' ORDER BY created_ts")
    plugin = [p for p in prs if p["repo"] == "wayfare-skills" and p["number"] in (106, 108, 115)]
    waves = {}
    for title, label in RENAME_WAVES:
        waves[label] = [p for p in prs if p["repo"] != "wayfare-skills" and p["title"].startswith(title)]
    wave_repos = [sorted({p["repo"] for p in v}) for v in waves.values()]
    fixes_after = [r for r in ws_rows if "2026-09-21" < r["day"] <= "2026-10-05" and ws.get(r["sha"], {}).get("incident")]
    runs = rows("SELECT day, conclusion, COUNT(*) n FROM github.ci_runs WHERE workflow_name='Auto Approve' AND day BETWEEN '2026-09-21' "
                "AND '2026-09-23' GROUP BY day, conclusion")
    return {"events": table, "plugin_prs": plugin, "waves": waves, "wave_repos": wave_repos,
            "consumers_both_waves": sorted(set(wave_repos[0]) & set(wave_repos[1])) if len(wave_repos) == 2 else [],
            "fixes_after_rename": [(f["day"], f["subject"]) for f in fixes_after], "aa_runs": runs,
            "incident_audit": [(r["sha"][:7], r["day"], r["subject"]) for r in ws_rows
                               if any(e < r["day"] <= (date.fromisoformat(e) + timedelta(days=REPAIR_DAYS)).isoformat() for e in events)
                               and r["sha"] in ws]}
