"""The field series: the field, and what generalizes.

One function per question, each returning what its answer slide (and breakdown slide) plots.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/field/data.py   # prints every result
"""
import csv
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.dirname(HERE)
ANALYSIS = os.path.dirname(REPORT)
PLUGIN = os.path.dirname(ANALYSIS)
sys.path.insert(0, REPORT)
from deck_lib import TOPICS  # noqa: E402
from record import STAGES, adoption, changeset_facts, rows, week_of  # noqa: E402

DATA = os.path.join(PLUGIN, ".analysis", "data")
FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
APPS = ("app", "app, no features yet")


def connect():
    sys.path.insert(0, ANALYSIS)
    from cube.db import connect as cube_connect
    return cube_connect()


def wk(ts):
    return week_of(ts[:10]) if ts else None


def parse_ts(ts):
    ts = ts.replace("Z", "+00:00")
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def owner_prompts(con):
    """The owner's typed prompts (Claude Code's prompt history), by repo; session housekeeping excluded."""
    out = []
    for r in rows(con, "SELECT ts, repo, is_slash_command s, command, text_redacted t FROM harness.prompts"):
        cmd = (r["command"] or "").split(":")[-1]
        if r["s"] and cmd in HOUSEKEEPING:
            continue
        out.append({"ts": r["ts"], "t": parse_ts(r["ts"]), "repo": r["repo"], "slash": bool(r["s"]), "cmd": cmd,
                    "text": r["t"] or ""})
    return out


HOUSEKEEPING = {"clear", "model", "compact", "login", "logout", "resume", "rate-limit-options", "plugins", "mcp",
                "effort", "reload-plugins", "cler", "remote-control", "btw", "config", "status", "cost", "exit",
                "help", "doctor", "permissions", "context", "usage", "ide", "fast", "add-dir", "agents", "hooks",
                "memory", "init", "rename", "export", "terminal-setup", "upgrade", "release-notes", "theme"}


# ------------------------------------------------------------------ Q portable-questions

FLEET_TERMS = (r"wayfare|\bhero\b|hero-skills|HERO\.md|\.plans\b|FLEET\.md|DESIGN\.md|CONSISTENCY\.md|CONTROLS\.yaml|"
               r"CHECKS\.yaml|AGENTS\.md|CLAUDE\.md|\bD\d{1,2}\b|\bgrill\w*|sync-plan|auto-approve|recalibrate|"
               r"ship-pr|review-pr|build-task|start-goal|one-shot|mailbox|\bch2_\w+|cs_sets|changeset_facts|"
               r"harness\.\w+|plans\.\w+|git\.\w+|github\.\w+|detectors\.\w+|knowledge\.\w+")
VENDOR_TERMS = r"\bClaude\b|Haiku|Sonnet|\bOpus\b|Fable|Anthropic|GitHub|Dependabot|Copilot|Trivy|\bScout\b|shadcn"
# Repo names that are also English words are left out: "drift", "research", "website" match ordinary prose.
WORD_REPOS = {"drift", "research", "website", "patches", "checklists", "agentic", "weave", "saga", "auth",
              "design-system", "fleet"}


def _fleet_re():
    repos = [d for d in os.listdir(FLEET) if os.path.isdir(os.path.join(FLEET, d)) and d not in WORD_REPOS
             and not d.startswith(".")]
    names = "|".join(re.escape(r) for r in sorted(repos, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{names})(?![\w-])|{FLEET_TERMS}", re.I), re.compile(VENDOR_TERMS)


def chapter_rewrites():
    """{topic: [question text]}: each topic's questions as the decks ask them, from analysis/QUESTIONS.md."""
    out, topic = {}, None
    for line in open(os.path.join(ANALYSIS, "QUESTIONS.md"), encoding="utf-8"):
        m = re.match(r"^## .*\(`report/([a-z_]+)/`\)", line)
        if m:
            topic = m.group(1)
            continue
        m = re.match(r"^- \*\*Q [a-z0-9-]+\*\* (.+)$", line.strip())
        if m and topic:
            out.setdefault(topic, []).append(m.group(1))
    return out


def q_portable_questions_generic(con=None):
    fleet, vendor = _fleet_re()
    bank = [r for r in csv.DictReader(open(os.path.join(ANALYSIS, "bank", "questions.csv")))]
    by_ch = defaultdict(lambda: {"bank": [], "rewrite": []})
    for r in bank:
        if r["chapter"].strip():
            by_ch[r["chapter"].strip()]["bank"].append(r["question"])
    rewrites = chapter_rewrites()
    for ch, qs in rewrites.items():
        by_ch[ch]["rewrite"] = qs
    chapters = sorted(by_ch, key=list(TOPICS).index)
    share = lambda qs, rx: (sum(1 for q in qs if rx.search(q)) / len(qs)) if qs else None
    terms, vterms = Counter(), Counter()
    for ch in chapters:
        for q in by_ch[ch]["rewrite"]:
            terms.update({m.lower() for m in fleet.findall(q)})
            vterms.update(set(vendor.findall(q)))
    all_bank = [q for c in chapters for q in by_ch[c]["bank"]]
    all_rw = [q for c in chapters for q in by_ch[c]["rewrite"]]
    # bank/groundings.csv holds fleet observations and stays local; without it this share is None.
    gpath = os.path.join(ANALYSIS, "bank", "groundings.csv")
    groundings = [r["groundings"] for r in csv.DictReader(open(gpath))] if os.path.exists(gpath) else []
    examples = [q for q in all_rw if fleet.search(q)][:6]
    return {
        "chapters": chapters,
        "bank_fleet": [share(by_ch[c]["bank"], fleet) for c in chapters],
        "rewrite_fleet": [share(by_ch[c]["rewrite"], fleet) for c in chapters],
        "n_bank": len(all_bank), "n_rewrite": len(all_rw),
        "bank_fleet_all": share(all_bank, fleet), "rewrite_fleet_all": share(all_rw, fleet),
        "bank_vendor_all": share(all_bank, vendor), "rewrite_vendor_all": share(all_rw, vendor),
        "groundings_fleet": share(groundings, fleet), "n_groundings": len(groundings),
        "terms": terms.most_common(12), "vendor_terms": vterms.most_common(6), "examples": examples,
        **({} if rewrites else {"rewrites_unavailable": "analysis/QUESTIONS.md lists no questions"}),
    }


# ------------------------------------------------------------------ Q git-only-measurability

TIERS = ["git and GitHub", "+ agent transcripts", "+ work items and goals", "+ wayfare's own records",
         "owner's judgement only"]
# Most specialised data each source needs. model_releases/cc_releases are public release notes: stock.
SOURCE_TIER = {
    "git": 0, "github": 0, "pr_commits": 0, "commits": 0, "prs": 0, "ci_runs": 0, "ci_jobs": 0, "pr_reviews": 0,
    "pr_timeline": 0, "commit_files": 0, "trailers": 0, "repos": 0, "repo_files": 0, "git (file snapshots)": 0,
    ".github/workflows": 0, "model_releases": 0, "cc_releases": 0,
    "harness": 1, "sessions": 1, "turns": 1, "tool_calls": 1, "prompts": 1, "asks": 1, "subagent_runs": 1,
    "memories": 1, "limit_events": 1, "repo .claude dirs": 1,
    "plans": 2, "plan_items": 2, "item_logs": 2, "item_edges": 2, "goals": 2, "plan_docs": 2,
    "plans.plan_items(schema_era)": 2,
    "messages": 3, "knowledge": 3, "doc_versions": 3, "design_decisions": 3, "controls": 3, "checks": 3,
    "check_results": 3, "register_history": 3, "instruction_files": 3, "skills": 3, "skill_versions": 3,
    "plugin_versions": 3, "HERO.md per repo": 3, "FLEET.md": 3, "wayfare-skills repo (code allowed)": 3,
}
# D1 groups git commits (plus a model label); D5/D7/D8 read git and GitHub; D6/D9 read transcripts; D4 reads
# work items; D2/D3/D10 compare repos against the template, the plugin and wayfare's own files.
DETECTOR_TIER = {"D1": 0, "D5": 0, "D7": 0, "D8": 0, "D6": 1, "D9": 1, "D4": 2, "D2": 3, "D3": 3, "D10": 3}
# When each source's data begins (the first day it holds anything), computed below from the data.
START_SQL = {
    "git": "SELECT MIN(day) FROM git.commits", "github": "SELECT MIN(day) FROM github.prs",
    "transcripts": "SELECT MIN(day) FROM harness.sessions WHERE day > '2026-08-24'",
    "first_session": "SELECT MIN(day) FROM harness.sessions", "prompts": "SELECT MIN(day) FROM harness.prompts",
    "plans": "SELECT MIN(SUBSTR(ts,1,10)) FROM plans.item_logs", "goals": "SELECT MIN(SUBSTR(created_ts,1,10)) FROM plans.goals",
    "messages": "SELECT MIN(SUBSTR(created_ts,1,10)) FROM plans.messages",
    "register": "SELECT MIN(SUBSTR(ts,1,10)) FROM knowledge.register_history",
    "design": "SELECT MIN(day) FROM knowledge.doc_versions",
}


def _source_key(s):
    s = s.strip()
    if "." in s and s.split(".")[0] in ("git", "github", "plans", "harness", "knowledge", "detectors"):
        db, t = s.split(".", 1)
        return t.split("(")[0]
    return s


def _start_of(key, starts):
    if key in ("prompts",):
        return starts["prompts"]
    if key in ("harness", "sessions", "turns", "tool_calls", "asks", "subagent_runs", "memories", "limit_events",
               "repo .claude dirs"):
        return starts["transcripts"]
    if key == "goals":
        return starts["goals"]
    if key == "messages":
        return starts["messages"]
    if key in ("controls", "checks", "check_results", "register_history"):
        return starts["register"]
    if key in ("plans", "plan_items", "item_logs", "item_edges", "plan_docs"):
        return starts["plans"]
    return None


def bank_tiers(con):
    starts = {k: con.execute(v).fetchone()[0] for k, v in START_SQL.items()}
    out = []
    for r in csv.DictReader(open(os.path.join(ANALYSIS, "bank", "questions.csv"))):
        if not r["chapter"].strip():
            continue
        srcs = [_source_key(s) for s in r["sources"].split(";") if s.strip()]
        dets = [d.strip() for d in r["detectors"].split(";") if d.strip()]
        dets += re.findall(r"D\d+", r["method"])
        tiers = [SOURCE_TIER.get(s, 3) for s in srcs] + [DETECTOR_TIER.get(d, 0) for d in dets]
        method = r["method"]
        if not tiers:
            tier = 4 if ("human" in method or "deferred" in method or not method) else 0
        else:
            tier = max(tiers)
        begin = [_start_of(s, starts) for s in srcs] + [starts["transcripts"] for d in dets if d in ("D6", "D9")]
        begin += [starts["plans"] for d in dets if d == "D4"]
        begin = max([b for b in begin if b] or ["2026-01-01"])
        out.append({"rq": r["rq_id"], "chapter": r["chapter"].strip(), "tier": tier, "begins": begin,
                    "model": "haiku" in method or "D1" in dets, "owner": "human" in method,
                    "unspecified": not srcs and not dets})
    return out, starts


def q_git_only_measurability_tiers(con):
    qs, starts = bank_tiers(con)
    counted = [q for q in qs if q["tier"] < 4]
    series = {}
    for t in range(4):
        series[TIERS[t]] = []
        for w in WEEKS:
            end = (date.fromisocalendar(2026, int(w[6:]), 7)).isoformat()
            series[TIERS[t]].append(sum(1 for q in counted if q["tier"] == t and q["begins"] <= end))
    chapters = sorted({q["chapter"] for q in qs}, key=list(TOPICS).index)
    by_ch = {TIERS[t]: [sum(1 for q in qs if q["chapter"] == c and q["tier"] == t) / max(1, sum(1 for q in qs if q["chapter"] == c))
                        for c in chapters] for t in range(5)}
    n = Counter(q["tier"] for q in qs)
    return {"weeks": WEEKS, "series": series, "chapters": chapters, "by_chapter": by_ch,
            "n": {TIERS[t]: n[t] for t in range(5)}, "total": len(qs), "starts": starts,
            "model_labels": sum(1 for q in qs if q["model"]),
            "stock_share": n[0] / len(qs), "unspecified": sum(1 for q in qs if q["unspecified"]),
            "answerable_jan": sum(1 for q in counted if q["begins"] <= "2026-01-07"),
            "answerable_now": len(counted)}


# ------------------------------------------------------------------ Q unified-timeline

def _resolution(values):
    """Share of timestamps that carry a time of day (not exactly midnight)."""
    vals = [v for v in values if v]
    timed = sum(1 for v in vals if not re.search(r"T00:00:00(\.0+)?([+-]00:00|Z)?$", v))
    return timed, len(vals)


EVENT_SOURCES = [
    # name, family, sql returning ts, has actor, has repo, has item id
    ("Commits on main", "git and GitHub", "SELECT authored_ts ts FROM git.commits", True, True, "some"),
    ("Original PR commits", "git and GitHub", "SELECT ts FROM pr_commits.pr_commits", True, True, "no"),
    ("PR opened / merged", "git and GitHub", "SELECT created_ts ts FROM github.prs UNION ALL SELECT merged_ts FROM github.prs WHERE merged_ts IS NOT NULL", True, True, "no"),
    ("PR reviews", "git and GitHub", "SELECT submitted_ts ts FROM github.pr_reviews", True, True, "no"),
    ("PR timeline events", "git and GitHub", "SELECT ts FROM github.pr_timeline", True, True, "no"),
    ("CI runs", "git and GitHub", "SELECT created_ts ts FROM github.ci_runs", False, True, "no"),
    ("Owner prompts", "Agent transcripts", "SELECT ts FROM harness.prompts", True, True, "no"),
    ("Session turns", "Agent transcripts", "SELECT ts FROM harness.turns", True, True, "no"),
    ("Tool calls", "Agent transcripts", "SELECT ts FROM harness.tool_calls", True, True, "no"),
    ("Work items created / ready / done", ".plans store", "SELECT created_ts ts FROM plans.plan_items UNION ALL SELECT ready_ts FROM plans.plan_items UNION ALL SELECT done_ts FROM plans.plan_items", False, True, "yes"),
    ("Work-item log entries", ".plans store", "SELECT ts FROM plans.item_logs", False, True, "yes"),
    ("Goals created", ".plans store", "SELECT created_ts ts FROM plans.goals", False, True, "yes"),
    ("Mailbox messages", ".plans store", "SELECT created_ts ts FROM plans.messages", False, True, "some"),
]


def q_unified_timeline_timeline(con):
    res = []
    weekly_fam = defaultdict(lambda: defaultdict(int))
    for name, fam, sql, actor, repo, item in EVENT_SOURCES:
        ts = [r[0] for r in con.execute(sql)]
        timed, n = _resolution(ts)
        res.append({"source": name, "family": fam, "n": n, "timed": timed, "share": timed / n if n else 0,
                    "actor": actor, "repo": repo, "item": item})
        for t in ts:
            if t and t[:4] == "2026":
                weekly_fam[fam][wk(t)] += 1
    fams = ["git and GitHub", "Agent transcripts", ".plans store"]
    series = {f: [weekly_fam[f].get(w, 0) for w in WEEKS] for f in fams}
    # Work-item log entries that share a day with a commit or PR event in the same repo: those cannot be ordered.
    busy = {(r["repo"], r["d"]) for r in rows(con, "SELECT repo, day d FROM git.commits UNION SELECT repo, SUBSTR(merged_ts,1,10) FROM github.prs WHERE merged_ts IS NOT NULL")}
    logs = rows(con, "SELECT repo, SUBSTR(ts,1,10) d FROM plans.item_logs")
    same_day = sum(1 for l in logs if (l["repo"], l["d"]) in busy)
    ready_before = con.execute("SELECT COUNT(*) FROM plans.plan_items WHERE ready_ts < created_ts").fetchone()[0]
    items = con.execute("SELECT COUNT(*) FROM plans.plan_items WHERE ready_ts IS NOT NULL").fetchone()[0]
    return {"sources": res, "weeks": WEEKS, "series": series, "logs": len(logs), "logs_same_day": same_day,
            "ready_before_created": ready_before, "items_with_ready": items}


# ------------------------------------------------------------------ Q comparable-units / Q no-human-merges

GATE_BOTS = ("github-actions",)


def merged_prs(con):
    ad = adoption(con)
    prs = rows(con, """SELECT repo, number, author, author_is_bot, created_ts, merged_ts FROM github.prs
                       WHERE merged_ts IS NOT NULL AND merged_ts >= '2026-01-01'""")
    return [p for p in prs if p["repo"] in ad and not p["author_is_bot"] and "dependabot" not in (p["author"] or "")]


def pr_autonomy(con):
    """Per merged PR: who acted on it, under each definition of 'no human action'."""
    ad = adoption(con)
    prs = merged_prs(con)
    reviews = defaultdict(list)
    for r in rows(con, "SELECT repo, number, reviewer, reviewer_is_bot bot, state FROM github.pr_reviews"):
        reviews[(r["repo"], r["number"])].append(r)
    mergers = {(r["repo"], r["number"]): r["actor"] for r in rows(con, "SELECT repo, number, actor FROM github.pr_timeline WHERE event='merged'")}
    prompts = defaultdict(list)
    for p in owner_prompts(con):
        prompts[p["repo"]].append(p["t"])
    for v in prompts.values():
        v.sort()
    import bisect
    sets = Counter((f["repo"], f["pr"]) for f in changeset_facts(con) if f["pr"] is not None and not f["dependabot"])
    out = []
    for p in prs:
        k = (p["repo"], p["number"])
        rv = reviews.get(k, [])
        human_review = any(not r["bot"] for r in rv)
        gate_approved = any(r["bot"] and r["reviewer"] in GATE_BOTS and r["state"] == "APPROVED" for r in rv)
        owner_approved = any(not r["bot"] and r["state"] == "APPROVED" for r in rv)
        merger = mergers.get(k) or ""
        opened, merged = parse_ts(p["created_ts"]), parse_ts(p["merged_ts"])
        ts = prompts.get(p["repo"], [])
        n_prompts = bisect.bisect_right(ts, merged) - bisect.bisect_left(ts, opened)
        owner_pr = p["author"] == "rparundekar"
        human_account = (not owner_pr) or human_review or (merger and "bot" not in merger and merger != "github-actions")
        if owner_approved or not owner_pr:
            cat = "A person approved (or authored)"
        elif not gate_approved:
            cat = "No approval recorded"
        elif n_prompts:
            cat = "Gate approved; owner prompted while open"
        else:
            cat = "Gate approved; no owner prompt while open"
        out.append({**p, "week": wk(p["merged_ts"]), "month": p["merged_ts"][:7], "cat": cat,
                    "human_account": bool(human_account), "gate_only": gate_approved and not owner_approved and owner_pr,
                    "prompts": n_prompts, "sets": sets.get(k, 1), "category": ad[p["repo"]]["category"],
                    "day": p["merged_ts"][:10]})
    return out


AUTONOMY_CATS = ["Gate approved; no owner prompt while open", "Gate approved; owner prompted while open",
                 "A person approved (or authored)", "No approval recorded"]


def q_no_human_merges_autonomy(con):
    prs = pr_autonomy(con)
    tot = Counter(p["week"] for p in prs)
    series = {c: [sum(1 for p in prs if p["week"] == w and p["cat"] == c) / tot[w] if tot[w] else None for w in WEEKS]
              for c in AUTONOMY_CATS}
    ad = adoption(con)
    apps = sorted({p["repo"] for p in prs if ad[p["repo"]]["category"] in APPS}, key=lambda r: -sum(1 for p in prs if p["repo"] == r))[:6]
    by_repo = {}
    for r in apps:
        vals = []
        for m in MONTHS:
            ps = [p for p in prs if p["repo"] == r and p["month"] == m]
            vals.append(sum(1 for p in ps if p["cat"] == AUTONOMY_CATS[0]) / len(ps) if len(ps) >= 5 else None)
        by_repo[r] = vals
    period = lambda a, b: [p for p in prs if a <= p["day"] <= b]
    share = lambda ps: sum(1 for p in ps if p["cat"] == AUTONOMY_CATS[0]) / len(ps) if ps else None
    gate = lambda ps: sum(1 for p in ps if p["cat"].startswith("Gate")) / len(ps) if ps else None
    return {"weeks": WEEKS, "series": series, "by_repo": by_repo, "n": len(prs),
            "share_all": share(prs), "share_sep": share(period("2026-09-01", "2026-12-31")),
            "share_h1": share(period("2026-01-01", "2026-06-30")),
            "gate_sep": gate(period("2026-09-01", "2026-12-31")), "gate_h1": gate(period("2026-01-01", "2026-06-30")),
            "n_sep": len(period("2026-09-01", "2026-12-31"))}


def q_comparable_units_definitions(con):
    prs = pr_autonomy(con)
    since = [p for p in prs if p["day"] >= "2026-07-01"]
    s_all = sum(p["sets"] for p in since)
    defs = [
        ("No action by a person's GitHub account", sum(1 for p in since if not p["human_account"]) / len(since)),
        ("Approved only by the review gate", sum(1 for p in since if p["gate_only"]) / len(since)),
        ("... and no owner prompt while open (per PR)", sum(1 for p in since if p["cat"] == AUTONOMY_CATS[0]) / len(since)),
        ("... the same, per change set", sum(p["sets"] for p in since if p["cat"] == AUTONOMY_CATS[0]) / s_all),
    ]
    mergers = Counter(r["actor"] for r in rows(con, """SELECT t.actor FROM github.pr_timeline t JOIN github.prs p
        ON p.repo=t.repo AND p.number=t.number WHERE t.event='merged' AND p.merged_ts >= '2026-07-01'"""))
    reviewers = Counter((r["reviewer"], r["state"]) for r in rows(con, "SELECT reviewer, state FROM github.pr_reviews WHERE reviewer_is_bot=0 AND submitted_ts >= '2026-07-01'"))
    return {"defs": defs, "n_prs": len(since), "n_sets": s_all, "mergers": mergers.most_common(4),
            "owner_reviews": reviewers.most_common(4)}


# ------------------------------------------------------------------ Q review-load-vs-volume

def q_review_load_vs_volume_review(con):
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["unit_kind"] != "push"]
    sets_w = Counter(f["week"] for f in cs)
    prompts = owner_prompts(con)
    ad = adoption(con)
    p_w = Counter(wk(p["ts"]) for p in prompts if p["repo"] in ad)
    gate_w = Counter(wk(r["submitted_ts"]) for r in rows(con, "SELECT submitted_ts FROM github.pr_reviews WHERE reviewer_is_bot=1"))
    per = lambda c: [round(c.get(w, 0) / sets_w[w], 2) if sets_w.get(w, 0) >= 5 else None for w in WEEKS]
    series = {"Owner prompts per merged change set": per(p_w), "Bot review events per merged change set": per(gate_w)}
    buckets = [("under 25", 0, 25), ("25–74", 25, 75), ("75–149", 75, 150), ("150+", 150, 10 ** 6)]
    by_b = {}
    for name, lo, hi in buckets:
        ws = [w for w in WEEKS if lo <= sets_w.get(w, 0) < hi and sets_w.get(w, 0) >= 5]
        s = sum(sets_w[w] for w in ws)
        by_b[name] = {"weeks": len(ws), "prompts": sum(p_w.get(w, 0) for w in ws) / s if s else None,
                      "gate": sum(gate_w.get(w, 0) for w in ws) / s if s else None}
    half = lambda a, b, c: (sum(c.get(w, 0) for w in WEEKS[a:b]) / max(1, sum(sets_w.get(w, 0) for w in WEEKS[a:b])))
    return {"weeks": WEEKS, "series": series, "volume": [sets_w.get(w, 0) for w in WEEKS], "buckets": by_b,
            "prompts_h1": half(0, 26, p_w), "prompts_q3": half(26, 39, p_w), "gate_h1": half(0, 26, gate_w),
            "gate_q3": half(26, 39, gate_w)}


# ------------------------------------------------------------------ Q throughput-by-stage

def q_throughput_by_stage_throughput(con):
    ad = adoption(con)
    apps = [r for r in ad if ad[r]["category"] in APPS]
    cs = [f for f in changeset_facts(con) if not f["dependabot"] and f["repo"] in apps]
    per = Counter((f["repo"], f["week"]) for f in cs)
    live = lambda r, w: ad[r]["first"] <= date.fromisocalendar(2026, int(w[6:]), 7).isoformat() and ad[r]["last"] >= date.fromisocalendar(2026, int(w[6:]), 1).isoformat()
    series, n_live = [], []
    for w in WEEKS:
        rs = [r for r in apps if live(r, w)]
        n_live.append(len(rs))
        series.append(round(sum(per.get((r, w), 0) for r in rs) / len(rs), 2) if rs else None)
    from record import stage_of
    by_stage = defaultdict(list)
    moved = {}
    for r in apps:
        for w in WEEKS:
            if live(r, w):
                st = stage_of(con, r, date.fromisocalendar(2026, int(w[6:]), 4).isoformat())
                by_stage[st].append(per.get((r, w), 0))
    stage_mean = {s: (sum(by_stage[s]) / len(by_stage[s]) if by_stage[s] else None) for s in STAGES}
    stage_repos = {}
    for s in STAGES:
        stage_repos[s] = len({r for r in apps for w in WEEKS if live(r, w)
                              and stage_of(con, r, date.fromisocalendar(2026, int(w[6:]), 4).isoformat()) == s})
    # For each app and each stage it entered, mean change sets a week in the 4 weeks before and after.
    for key, name in (("items", "work items"), ("goals", "goals")):
        up = down = 0
        for r in apps:
            d0 = ad[r][key]
            if not d0:
                continue
            w0 = date.fromisoformat(d0)
            before = [per.get((r, week_of((w0 - timedelta(weeks=k)).isoformat())), 0) for k in range(1, 5)]
            after = [per.get((r, week_of((w0 + timedelta(weeks=k)).isoformat())), 0) for k in range(0, 4)]
            if sum(after) > sum(before):
                up += 1
            elif sum(after) < sum(before):
                down += 1
        moved[name] = (up, down)
    releases = rows(con, "SELECT date, name FROM harness.model_releases WHERE kind='model' AND date >= '2026-01-01'")
    return {"weeks": WEEKS, "series": series, "n_live": n_live, "stage_mean": stage_mean, "stage_repos": stage_repos,
            "moved": moved, "releases": [(r["date"], r["name"]) for r in releases]}


# ------------------------------------------------------------------ Q human-reading-points

STAGE_OF_CMD = {
    "Idea and plan": {"wayfare", "grill", "grill-idea", "wayfare-grill-idea", "think-it-through", "plan-work", "hero-plan",
                      "sync-plan", "wayfare-sync-plan", "architecture", "harden", "scan-vulns", "init-hero", "hero-init",
                      "wayfare-init-repo", "recalibrate", "wayfare-recalibrate-config", "design-login", "wayfare-write-handoff"},
    "Build": {"one-shot", "goal", "wayfare-start-goal", "build-task", "wayfare-build-task", "advance-item",
              "wayfare-advance-item", "loop", "recomponentize-ui"},
    "PR and review": {"push-pr", "hero-push", "commit-changes", "hero-commit", "review-pr", "wayfare-review-pr",
                      "respond-to-pr", "respond-to-comments", "hero-respond-to-pr", "hero-pr-respond", "hero-self-review",
                      "test-changes", "review", "wayfare-respond-pr", "wayfare-push-pr"},
    "Merge": {"ship-pr", "wayfare-ship-pr", "hero-auto-approve", "reset-branch", "hero-reset"},
}
TOUCH_STAGES = ["Idea and plan", "Work item marked ready", "Build", "PR and review", "Merge", "Free-text reply or steer"]


def q_human_reading_points_touches(con):
    ad = adoption(con)
    cmd_stage = {c: s for s, cs in STAGE_OF_CMD.items() for c in cs}
    touches = []
    for p in owner_prompts(con):
        if p["repo"] not in ad or p["ts"][:4] != "2026":
            continue
        if p["slash"]:
            st = cmd_stage.get(p["cmd"])
            if st is None:
                continue
        else:
            st = "Free-text reply or steer"
        touches.append((wk(p["ts"]), st, p["ts"][:10]))
    for r in rows(con, "SELECT repo, ready_ts FROM plans.plan_items WHERE ready_ts IS NOT NULL AND type != 'goal'"):
        if r["repo"] in ad and r["ready_ts"][:4] == "2026":
            touches.append((wk(r["ready_ts"]), "Work item marked ready", r["ready_ts"][:10]))
    cs = Counter(f["week"] for f in changeset_facts(con) if not f["dependabot"])
    per_w = defaultdict(Counter)
    for w, st, _ in touches:
        per_w[w][st] += 1
    series = {s: [round(per_w[w][s] / cs[w], 2) if cs.get(w, 0) >= 5 else None for w in WEEKS] for s in TOUCH_STAGES}
    periods = [("Before goals (to 27 Aug)", "2026-01-01", "2026-08-27"), ("With goals (from 28 Aug)", "2026-08-28", "2026-12-31")]
    csd = [f for f in changeset_facts(con) if not f["dependabot"]]
    split = {}
    for name, a, b in periods:
        n_cs = sum(1 for f in csd if a <= f["day"] <= b)
        split[name] = [sum(1 for _, st, d in touches if st == s and a <= d <= b) / n_cs for s in TOUCH_STAGES]
    share = {name: [v / sum(vals) for v in vals] for name, vals in split.items()}
    asks = con.execute("SELECT COUNT(*) FROM harness.asks").fetchone()[0]
    return {"weeks": WEEKS, "series": series, "split": split, "share": share, "n_touches": len(touches),
            "asks": asks}


# ------------------------------------------------------------------ Q onboarding-speed

CAPABILITY = {"skills": "2026-03-07", "items": "2026-07-05", "goals": "2026-08-28", "messages": "2026-09-13"}
STAGE_NAMES = {"skills": "Skills (HERO.md)", "items": "First work item", "goals": "First goal", "messages": "First message"}


def q_onboarding_speed_learning(con):
    ad = adoption(con)
    repos = sorted(ad, key=lambda r: ad[r]["first"])
    rows_ = []
    for r in repos:
        a = ad[r]
        row = {"repo": r, "first": a["first"], "category": a["category"]}
        for k in CAPABILITY:
            start = max(a["first"], CAPABILITY[k])
            row[k] = (date.fromisoformat(a[k]) - date.fromisoformat(start)).days if a[k] else None
        rows_.append(row)
    # Repos that joined after the capability existed, in order of creation.
    halves = {}
    for k in CAPABILITY:
        born_after = [x for x in rows_ if x["first"] >= CAPABILITY[k] and x[k] is not None]
        born_before = [x for x in rows_ if x["first"] < CAPABILITY[k] and x[k] is not None]
        med = lambda v: sorted(v)[len(v) // 2] if v else None
        halves[k] = {"before": med([x[k] for x in born_before]), "after": med([x[k] for x in born_after]),
                     "n_before": len(born_before), "n_after": len(born_after),
                     "never": sum(1 for x in rows_ if x[k] is None)}
    return {"repos": rows_, "halves": halves}


# ------------------------------------------------------------------ Q minimal-register

def _lines(p):
    try:
        return sum(1 for _ in open(p))
    except OSError:
        return 0


def _ids(p):
    try:
        return len(re.findall(r"^\s*- id:", open(p).read(), re.M))
    except OSError:
        return 0


def q_minimal_register_register(con):
    hist = rows(con, "SELECT file, ts, controls, checks FROM knowledge.register_history ORDER BY ts")
    fleet_w, clone_w = {}, {}
    for h in hist:
        repo, f = h["file"].split(":")
        w = wk(parse_ts(h["ts"]).astimezone(timezone.utc).isoformat())
        target = fleet_w if repo == "fleet" else clone_w
        if f == "CHECKS.yaml" and h["checks"]:
            target[w] = h["checks"]
    carry = lambda d: [d.get(w) for w in WEEKS]
    res = Counter(r["result"] for r in rows(con, "SELECT result FROM knowledge.check_results"))
    base = os.path.join(PLUGIN, "assets", "compliance")
    over = os.path.join(FLEET, ".fleet")
    parts = {
        "Engine (audit.py, consistency.py)": (_lines(os.path.join(PLUGIN, "scripts", "audit.py")) + _lines(os.path.join(PLUGIN, "scripts", "consistency.py")), "generic"),
        "Baseline controls and checks": (_lines(os.path.join(base, "CONTROLS.yaml")) + _lines(os.path.join(base, "CHECKS.yaml")), "generic"),
        "Fleet controls and checks": (_lines(os.path.join(over, "CONTROLS.yaml")) + _lines(os.path.join(over, "CHECKS.yaml")), "fleet"),
        "Fleet checkers (checkers.py)": (_lines(os.path.join(over, "checkers.py")), "fleet"),
    }
    ids = {"baseline_controls": _ids(os.path.join(base, "CONTROLS.yaml")), "baseline_checks": _ids(os.path.join(base, "CHECKS.yaml")),
           "fleet_controls": _ids(os.path.join(over, "CONTROLS.yaml")), "fleet_checks": _ids(os.path.join(over, "CHECKS.yaml"))}
    total = sum(res.values())
    names = {"✅": "Pass", "❌": "Fail", "–": "Not applicable", "?": "Cannot tell"}
    split = {names.get(k, k): v / total for k, v in res.items()}
    repos = con.execute("SELECT COUNT(DISTINCT repo) FROM knowledge.check_results").fetchone()[0]
    asof = con.execute("SELECT MAX(as_of) FROM knowledge.check_results").fetchone()[0]
    return {"weeks": WEEKS, "fleet_checks": carry(fleet_w), "clone_checks": carry(clone_w), "parts": parts, "ids": ids,
            "split": split, "counts": {names.get(k, k): v for k, v in res.items()}, "repos": repos, "as_of": asof,
            "versions": len(hist)}


# ------------------------------------------------------------------ Q practices-after-failures

def _git_day(sha):
    return subprocess.run(["git", "-C", PLUGIN, "log", "-1", "--format=%ad", "--date=short", sha],
                          capture_output=True, text=True).stdout.strip()


# Practice, the wayfare-skills commit that introduced it, the failure its message names, and the signal that
# failure would show up in. The failure is taken from the commit message (item logs of kind `mistake` start 18 Sep).
PRACTICES = [
    ("5548869", "Prior-review gate", "Gate approval on a prior review and resolved threads", "auto-approve could approve itself and override unanswered review", "followup"),
    ("db701b7", "Scripted gates", "Scripted gates before the model", "lockfiles and generated code filled the diff; 'diff truncated' false positives", "gate_cr"),
    ("2e58547", "Rebase first", "Rebase before any review, approval or merge", "PRs were judged on heads behind the base; approvals dismissed on push", "dismissed"),
    ("a0e0a00", "Workflow lint", "Lint workflows so one GitHub cannot start fails first", "a workflow GitHub rejected at startup: zero jobs, no verdict, fleet-wide", "startup"),
]
SIGNALS = {"followup": "Same-file follow-up within 7 days", "gate_cr": "Gate asked for changes",
           "dismissed": "Approval dismissed", "startup": "Auto-approve run that failed to start or failed"}


def q_practices_after_failures_practices(con):
    prs = merged_prs(con)
    pr_w = Counter(wk(p["merged_ts"]) for p in prs)
    ours = {(p["repo"], p["number"]) for p in prs}
    fu = Counter(wk(r["merged_ts"]) for r in rows(con, "SELECT repo, number, merged_ts FROM detectors.followups WHERE followup_within_7d_days IS NOT NULL")
                 if (r["repo"], r["number"]) in ours)
    cr = Counter(wk(r["ts"]) for r in rows(con, "SELECT repo, ref, ts FROM detectors.gate_firings WHERE gate_kind='review' AND verdict='CHANGES_REQUESTED'")
                 if (r["repo"], int(r["ref"])) in ours)
    dis = Counter(wk(r["submitted_ts"]) for r in rows(con, "SELECT submitted_ts FROM github.pr_reviews WHERE state='DISMISSED'"))
    st = Counter(wk(r["created_ts"]) for r in rows(con, "SELECT created_ts FROM github.ci_runs WHERE lower(workflow_name) LIKE '%approve%' AND conclusion IN ('startup_failure','failure')"))
    counts = {"followup": fu, "gate_cr": cr, "dismissed": dis, "startup": st}
    per100 = lambda c, w: 100 * c.get(w, 0) / pr_w[w] if pr_w.get(w, 0) >= 5 else None
    series = {SIGNALS[k]: [per100(counts[k], w) for w in WEEKS] for k in ("followup", "gate_cr")}
    table = []
    for sha, short, name, failure, sig in PRACTICES:
        d = _git_day(sha)
        w0 = date.fromisoformat(d)
        before = [week_of((w0 - timedelta(weeks=k)).isoformat()) for k in range(1, 5)]
        after = [week_of((w0 + timedelta(weeks=k)).isoformat()) for k in range(1, 5)]
        after = [w for w in after if w <= week_of(date.today().isoformat())]
        rate = lambda ws: (100 * sum(counts[sig].get(w, 0) for w in ws) / max(1, sum(pr_w.get(w, 0) for w in ws))) if ws else None
        table.append({"sha": sha, "day": d, "short": short, "practice": name, "failure": failure, "signal": SIGNALS[sig],
                      "before": rate(before), "after": rate(after), "weeks_after": len(after),
                      "n_before": sum(counts[sig].get(w, 0) for w in before), "n_after": sum(counts[sig].get(w, 0) for w in after)})
    return {"weeks": WEEKS, "series": series, "table": table}


# ------------------------------------------------------------------ Q coordination-limits

def q_coordination_limits_coordination(con):
    ad = adoption(con)
    live_w = defaultdict(set)
    for r in rows(con, "SELECT repo, week FROM git.commits WHERE day >= '2026-01-01'"):
        if r["repo"] in ad:
            live_w[r["week"]].add(r["repo"])
    prompt_days = defaultdict(set)
    for p in owner_prompts(con):
        if p["repo"] in ad and p["ts"][:4] == "2026":
            prompt_days[p["ts"][:10]].add(p["repo"])
    peak = defaultdict(int)
    for d, rs in prompt_days.items():
        peak[week_of(d)] = max(peak[week_of(d)], len(rs))
    prs = rows(con, "SELECT repo, number, created_ts, merged_ts, closed_ts, author FROM github.prs WHERE created_ts >= '2025-12-01'")
    prs = [p for p in prs if p["repo"] in ad]
    open_peak = []
    for w in WEEKS:
        mid = date.fromisocalendar(2026, int(w[6:]), 4).isoformat() + "T12:00:00"
        open_peak.append(sum(1 for p in prs if p["created_ts"] <= mid and ((p["closed_ts"] or p["merged_ts"] or "9999") > mid)))
    fp = Counter(wk(r["ts"]) for r in rows(con, "SELECT ts FROM github.pr_timeline WHERE event='head_ref_force_pushed'"))
    series = {"Repos committed to": [len(live_w.get(w, ())) for w in WEEKS],
              "Most repos the owner prompted in one day": [peak.get(w, 0) for w in WEEKS],
              "Open PRs midweek": open_peak}
    merged = [p for p in prs if p["merged_ts"] and p["merged_ts"] >= "2026-01-01" and "dependabot" not in (p["author"] or "") and "[bot]" not in (p["author"] or "")]
    authors = Counter(p["author"] for p in merged)
    second = [a for a, _ in authors.most_common() if a != "rparundekar"]
    other = second[0] if second else None
    by_repo = defaultdict(Counter)
    for p in merged:
        by_repo[p["repo"]]["owner" if p["author"] == "rparundekar" else "other"] += 1
    shared = {r: c for r, c in by_repo.items() if c["other"]}
    other_span = [p["merged_ts"][:10] for p in merged if p["author"] == other]
    return {"weeks": WEEKS, "series": series, "force_push": [fp.get(w, 0) for w in WEEKS],
            "shared_repos": {r: (c["owner"], c["other"]) for r, c in sorted(shared.items(), key=lambda x: -x[1]["other"])},
            "other_author_prs": authors.get(other, 0), "other_span": (min(other_span), max(other_span)) if other_span else None,
            "peak_repos": max(peak.values()) if peak else 0, "peak_open": max(open_peak), "repos_now": len(live_w.get(WEEKS[-2], ()))}


# ------------------------------------------------------------------ Figure 8.1 · Q no-human-merges, monthly and by definition

AUTONOMY_CATS_81 = ["Gate approved; no owner prompt in the repo while open", "Gate approved; owner prompted in the repo while open",
                    "Approved or authored under a person's account", "No approval recorded", "Unknown (no merge event)"]
DEFINITIONS_81 = ["No non-bot GitHub account acted", "Approved by the gate, by no person's account",
                  "... and no owner prompt in that repo while open", "... and no owner prompt anywhere in the fleet while open"]


def pr_items(con):
    """Two maps, (repo, PR number) and (repo, branch), each to {item, authorized} for the work item whose
    frontmatter names that PR URL or branch."""
    out = {}
    branches = {}
    for r in rows(con, "SELECT repo, item_id, ready_ts, goal_id, raw_frontmatter_json fm FROM plans.plan_items WHERE type != 'goal'"):
        fm = json.loads(r["fm"] or "{}")
        auth = bool(r["ready_ts"]) or bool(r["goal_id"])
        pr = fm.get("pr")
        m = re.search(r"/pull/(\d+)", str(pr or ""))
        if m:
            out[(r["repo"], int(m.group(1)))] = {"item": r["item_id"], "authorized": auth}
        if fm.get("branch"):
            branches[(r["repo"], fm["branch"])] = {"item": r["item_id"], "authorized": auth}
    return out, branches


def q_no_human_merges_monthly(con):
    """Merged non-bot PRs by month under the primary definition, the four definitions side by side, and, for the
    hands-off PRs, whether a prior owner prompt or an authorized work item stands behind them."""
    import bisect
    prs = pr_autonomy(con)
    merged_events = {(r["repo"], r["number"]) for r in rows(con, "SELECT repo, number FROM github.pr_timeline WHERE event='merged'")}
    prompts_all = sorted(p["t"] for p in owner_prompts(con))
    prompts_repo = defaultdict(list)
    for p in owner_prompts(con):
        prompts_repo[p["repo"]].append(p["t"])
    for v in prompts_repo.values():
        v.sort()
    heads = {(r["repo"], r["number"]): r["head_ref"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    by_pr, by_branch = pr_items(con)
    months = MONTHS
    counts = {c: [0] * len(months) for c in AUTONOMY_CATS_81}
    defs = {d: [0] * len(months) for d in DEFINITIONS_81}
    n_month = [0] * len(months)
    prior = Counter()
    for p in prs:
        k = (p["repo"], p["number"])
        if p["month"] not in months:
            continue
        i = months.index(p["month"])
        n_month[i] += 1
        cat = "Unknown (no merge event)" if k not in merged_events else {
            AUTONOMY_CATS[0]: AUTONOMY_CATS_81[0], AUTONOMY_CATS[1]: AUTONOMY_CATS_81[1],
            AUTONOMY_CATS[2]: AUTONOMY_CATS_81[2], AUTONOMY_CATS[3]: AUTONOMY_CATS_81[3]}[p["cat"]]
        counts[cat][i] += 1
        opened, merged = parse_ts(p["created_ts"]), parse_ts(p["merged_ts"])
        fleet_prompts = bisect.bisect_right(prompts_all, merged) - bisect.bisect_left(prompts_all, opened)
        if not p["human_account"]:
            defs[DEFINITIONS_81[0]][i] += 1
        if p["gate_only"]:
            defs[DEFINITIONS_81[1]][i] += 1
        if p["cat"] == AUTONOMY_CATS[0]:
            defs[DEFINITIONS_81[2]][i] += 1
            if fleet_prompts == 0:
                defs[DEFINITIONS_81[3]][i] += 1
            # Prior direction: an owner prompt in the repo in the 7 days before the PR opened; authorization: a
            # ready-marked or goal-member work item names the PR or its branch.
            ts = prompts_repo.get(p["repo"], [])
            before = bisect.bisect_left(ts, opened) - bisect.bisect_left(ts, opened - timedelta(days=7))
            item = by_pr.get(k) or by_branch.get((p["repo"], heads.get(k)))
            prior["hands_off"] += 1
            prior["prompt_7d"] += bool(before)
            prior["item"] += bool(item)
            prior["item_authorized"] += bool(item and item["authorized"])
            prior["neither"] += not (before or item)
            if p["day"] >= "2026-09-01":
                prior["sep_hands_off"] += 1
                prior["sep_prompt_7d"] += bool(before)
                prior["sep_item"] += bool(item)
                prior["sep_neither"] += not (before or item)
    shares = {c: [counts[c][i] / n_month[i] if n_month[i] else None for i in range(len(months))] for c in AUTONOMY_CATS_81}
    def_shares = {d: [defs[d][i] / n_month[i] if n_month[i] else None for i in range(len(months))] for d in DEFINITIONS_81}
    h1 = [p for p in prs if p["day"] <= "2026-06-30"]
    sep = [p for p in prs if p["day"] >= "2026-09-01"]
    share = lambda ps, cat: sum(1 for p in ps if p["cat"] == cat) / len(ps) if ps else None
    excluded = con.execute("""SELECT COUNT(*) FROM github.prs WHERE merged_ts >= '2026-01-01'
                              AND (author_is_bot = 1 OR author LIKE '%dependabot%')""").fetchone()[0]
    return {"months": months, "n_month": n_month, "counts": counts, "shares": shares, "defs": defs, "def_shares": def_shares,
            "n": len(prs), "excluded_bot": excluded, "prior": dict(prior),
            "h1": {"n": len(h1), "hands_off": share(h1, AUTONOMY_CATS[0]), "with_prompt": share(h1, AUTONOMY_CATS[1])},
            "sep": {"n": len(sep), "hands_off": share(sep, AUTONOMY_CATS[0]), "with_prompt": share(sep, AUTONOMY_CATS[1])},
            "unknown": sum(counts["Unknown (no merge event)"])}


# ------------------------------------------------------------------ Figure 8.2 · Q human-reading-points, composition of owner input

INPUT_CATS = ["Planning commands", "Approving a plan or step", "Work item marked ready", "New work and instructions",
              "Build commands", "PR and review handling", "Merge and ship commands", "Corrections and redirects",
              "Questions and answers", "Operational (continue, meta, other)", "Unlabelled free text"]
PERIODS_82 = [("Skills only (to 22 Jul)", "2026-01-01", "2026-07-22"), ("Work items (23 Jul–27 Aug)", "2026-07-23", "2026-08-27"),
              ("Goals (from 28 Aug)", "2026-08-28", "2026-12-31")]
# Free text that gives a PR or merge order is PR handling, whatever intent the classifier gave it.
PR_TEXT_RE = re.compile(r"^\W*(ship( it)?|merge( it)?|push( it)?|rebase|review and ship|ship [0-9a-f]{7,}|"
                        r"(please )?(push|ship|merge)\b.*(pr|pull request|change|branch|main)|"
                        r".*\b(ship|merge) (the |this |that )?(pr|pull request|changes?)\b)\W*$", re.I | re.S)
INTENT_CAT = {"approve": "Approving a plan or step", "new_work": "New work and instructions",
              "correction": "Corrections and redirects", "redirect": "Corrections and redirects",
              "question": "Questions and answers", "answer": "Questions and answers",
              "continue": "Operational (continue, meta, other)", "meta": "Operational (continue, meta, other)",
              "other": "Operational (continue, meta, other)"}
CMD_CAT = {"Idea and plan": "Planning commands", "Build": "Build commands", "PR and review": "PR and review handling",
           "Merge": "Merge and ship commands"}


def owner_inputs(con):
    """Every owner input in 2026 in a fleet repo with its category: typed prompts (slash commands by name, free text
    by the shared intent label, D-prompt_intent) and ready-marks from the plan store."""
    ad = adoption(con)
    intents = {(r["ts"], r["repo"]): r["intent"] for r in rows(con, "SELECT ts, repo, intent FROM detectors.prompt_intent")}
    cmd_stage = {c: s for s, cs in STAGE_OF_CMD.items() for c in cs}
    out = []
    for p in owner_prompts(con):
        if p["repo"] not in ad or p["ts"][:4] != "2026":
            continue
        if p["slash"]:
            st = cmd_stage.get(p["cmd"])
            if st is None:
                continue
            cat = CMD_CAT[st]
        elif PR_TEXT_RE.match(p["text"].strip()[:200]):
            cat = "PR and review handling"
        else:
            it = intents.get((p["ts"], p["repo"]))
            cat = INTENT_CAT.get(it, "Unlabelled free text") if it else "Unlabelled free text"
        out.append({"day": p["ts"][:10], "repo": p["repo"], "cat": cat, "kind": "command" if p["slash"] else "text",
                    "text": p["text"], "intent": None if p["slash"] else intents.get((p["ts"], p["repo"]))})
    for r in rows(con, "SELECT repo, ready_ts FROM plans.plan_items WHERE ready_ts IS NOT NULL AND type != 'goal'"):
        if r["repo"] in ad and r["ready_ts"][:4] == "2026":
            out.append({"day": r["ready_ts"][:10], "repo": r["repo"], "cat": "Work item marked ready", "kind": "ready",
                        "text": "", "intent": None})
    return out


def q_human_reading_points_composition(con):
    inputs = owner_inputs(con)
    per = {}
    for name, a, b in PERIODS_82:
        xs = [x for x in inputs if a <= x["day"] <= b]
        c = Counter(x["cat"] for x in xs)
        per[name] = {"n": len(xs), "counts": {k: c.get(k, 0) for k in INPUT_CATS},
                     "shares": {k: (c.get(k, 0) / len(xs) if xs else None) for k in INPUT_CATS}}
    grp = lambda name, keys: sum(per[name]["shares"][k] or 0 for k in keys)
    pr_keys = ("PR and review handling", "Merge and ship commands")
    plan_keys = ("Planning commands", "Approving a plan or step", "Work item marked ready")
    first, last = PERIODS_82[0][0], PERIODS_82[-1][0]
    labelled = [x for x in inputs if x["kind"] == "text"]
    return {"periods": [p[0] for p in PERIODS_82], "cats": INPUT_CATS, "per": per, "n": len(inputs),
            "pr_first": grp(first, pr_keys), "pr_last": grp(last, pr_keys),
            "plan_first": grp(first, plan_keys), "plan_last": grp(last, plan_keys),
            "corr_first": grp(first, ("Corrections and redirects",)), "corr_last": grp(last, ("Corrections and redirects",)),
            "pr_text": sum(1 for x in labelled if x["cat"] == "PR and review handling"),
            "unlabelled": sum(1 for x in labelled if x["cat"] == "Unlabelled free text"), "n_text": len(labelled),
            "n_ready": sum(1 for x in inputs if x["kind"] == "ready"), "n_cmd": sum(1 for x in inputs if x["kind"] == "command")}


# ------------------------------------------------------------------ Figure 8.3 · Q git-only-measurability, source combinations

SOURCE_CLASS = {0: "Git/GitHub", 1: "Agent transcripts", 2: "Factory records", 3: "Factory records"}
CLASSES_83 = ["Git/GitHub", "Agent transcripts", "Factory records", "Live system", "Human testimony"]
LIVE_RE = re.compile(r"\blive\b|revocation|network exposure|boot configuration|blast radius held|running (service|environment)", re.I)


def question_sources(con):
    """Each bank question's set of evidence classes, by explicit rules: a source table or detector maps to Git/GitHub,
    agent transcripts or factory records (SOURCE_TIER, DETECTOR_TIER); a method naming a person adds human testimony;
    a question that asks about a live check or a running system adds live system; no source and no rule is unknown."""
    out = []
    for r in csv.DictReader(open(os.path.join(ANALYSIS, "bank", "questions.csv"))):
        if not r["chapter"].strip():
            continue
        srcs = [_source_key(s) for s in r["sources"].split(";") if s.strip()]
        dets = [d.strip() for d in r["detectors"].split(";") if d.strip()] + re.findall(r"D\d+", r["method"])
        classes = {SOURCE_CLASS[SOURCE_TIER.get(s, 3)] for s in srcs} | {SOURCE_CLASS[DETECTOR_TIER.get(d, 0)] for d in dets}
        method = r["method"]
        if "human" in method or (method == "deferred" and not srcs):
            classes.add("Human testimony")
        if LIVE_RE.search(r["question"]) and (method == "deferred" or not srcs):
            classes.add("Live system")
        out.append({"rq": r["rq_id"], "chapter": r["chapter"].strip(), "classes": frozenset(classes),
                    "model": "haiku" in method or "D1" in dets, "method": method})
    return out


def q_git_only_measurability_sources(con):
    qs = question_sources(con)
    combos = Counter(q["classes"] for q in qs)
    name = lambda fs: " + ".join(c for c in CLASSES_83 if c in fs) if fs else "No source listed"
    table = [{"combination": name(fs), "classes": sorted(fs, key=CLASSES_83.index), "n": n} for fs, n in combos.most_common()]
    needs = {c: sum(1 for q in qs if c in q["classes"]) for c in CLASSES_83}
    only = {c: sum(1 for q in qs if q["classes"] == {c}) for c in CLASSES_83}
    git_plus_records = sum(1 for q in qs if q["classes"] == {"Git/GitHub", "Factory records"})
    multi = sum(1 for q in qs if len(q["classes"]) > 1)
    chapters = sorted({q["chapter"] for q in qs}, key=list(TOPICS).index)
    by_ch = {c: [sum(1 for q in qs if q["chapter"] == ch and c in q["classes"]) / max(1, sum(1 for q in qs if q["chapter"] == ch))
                 for ch in chapters] for c in CLASSES_83}
    return {"table": table, "needs": needs, "only": only, "total": len(qs), "multi": multi,
            "git_plus_records": git_plus_records, "unlisted": combos.get(frozenset(), 0),
            "model_labels": sum(1 for q in qs if q["model"]), "chapters": chapters, "by_chapter": by_ch,
            "without_git": sum(1 for q in qs if q["classes"] and "Git/GitHub" not in q["classes"]),
            "records_any": needs["Factory records"] + needs["Agent transcripts"] - sum(1 for q in qs if {"Factory records", "Agent transcripts"} <= q["classes"])}


# ------------------------------------------------------------------ Figure 8.4 · Q onboarding-speed, dumbbell per repo

ITEM_STORE_FROM = "2026-07-23"


def q_onboarding_speed_dumbbell(con, today=None):
    """Per repo created after the skills existed: days from its first commit to HERO.md and to its first work item
    (any, and the first that is not a Dependabot bump), with censoring made explicit."""
    today = today or con.execute("SELECT MAX(day) FROM git.commits").fetchone()[0]
    ad = adoption(con)
    items = defaultdict(list)
    for r in rows(con, "SELECT repo, item_id, day, origin, raw_frontmatter_json fm FROM plans.plan_items WHERE type != 'goal' AND day IS NOT NULL"):
        fm = json.loads(r["fm"] or "{}")
        items[r["repo"]].append((r["day"], r["origin"] or "", bool(fm.get("bot")), r["item_id"]))
    hero_first = {r["repo"]: r["n"] for r in rows(con, """SELECT c.repo, COUNT(*) n FROM git.commit_files f JOIN git.commits c
        ON c.repo=f.repo AND c.sha=f.sha WHERE f.path='HERO.md' AND c.day = (SELECT MIN(day) FROM git.commits g WHERE g.repo=c.repo) GROUP BY c.repo""")}
    out = []
    for r in sorted(ad, key=lambda k: ad[k]["first"]):
        a = ad[r]
        if a["first"] < CAPABILITY["skills"]:
            continue
        d0 = date.fromisoformat(a["first"])
        days = lambda d: (date.fromisoformat(d) - d0).days if d else None
        its = sorted(items.get(r, []))
        first_any = its[0] if its else None
        first_real = next((i for i in its if not i[2]), None)
        row = {"repo": r, "first": a["first"], "category": a["category"], "skills": days(a["skills"]),
               "hero_in_first_commit": bool(hero_first.get(r)),
               "item_any": days(first_any[0]) if first_any else None, "item_real": days(first_real[0]) if first_real else None,
               "item_origin": first_real[1] if first_real else None, "item_id": first_real[3] if first_real else None,
               "age": days(today), "store_after_creation": a["first"] < ITEM_STORE_FROM,
               "censored": "none yet" if not first_real else ("store began later" if a["first"] < ITEM_STORE_FROM else None)}
        out.append(row)
    born_after_store = [x for x in out if x["first"] >= CAPABILITY["items"]]
    # Median with right-censoring: censored repos count as at least their age (Kaplan–Meier median on so few rows
    # reduces to the middle of the ordered values with censored ones placed at their age).
    ordered = sorted([(x["item_real"] if x["item_real"] is not None else x["age"], x["item_real"] is None) for x in born_after_store])
    med = ordered[len(ordered) // 2] if ordered else (None, False)
    observed = sorted(x["item_real"] for x in born_after_store if x["item_real"] is not None)
    return {"repos": out, "today": today, "n": len(out), "skills_max": max(x["skills"] for x in out if x["skills"] is not None),
            "skills_in_first_commit": sum(1 for x in out if x["hero_in_first_commit"]),
            "n_after_store": len(born_after_store), "censored_after_store": sum(1 for x in born_after_store if x["item_real"] is None),
            "median_item_days": med[0], "median_is_censored": med[1], "observed_median": observed[len(observed) // 2] if observed else None,
            "observed_iqr": (observed[len(observed) // 4], observed[(3 * len(observed)) // 4]) if observed else None,
            "origins": Counter(x["item_origin"] for x in out if x["item_origin"] is not None)}


def all_data():
    con = connect()
    return {name: fn(con) for name, fn in [
        ("q_portable_questions", q_portable_questions_generic), ("q_git_only_measurability", q_git_only_measurability_tiers), ("q_unified_timeline", q_unified_timeline_timeline), ("q_comparable_units", q_comparable_units_definitions),
        ("q_no_human_merges", q_no_human_merges_autonomy), ("q_review_load_vs_volume", q_review_load_vs_volume_review), ("q_throughput_by_stage", q_throughput_by_stage_throughput), ("q_human_reading_points", q_human_reading_points_touches),
        ("q_onboarding_speed", q_onboarding_speed_learning), ("q_minimal_register", q_minimal_register_register), ("q_practices_after_failures", q_practices_after_failures_practices), ("q_coordination_limits", q_coordination_limits_coordination),
        ("fig_8_1", q_no_human_merges_monthly), ("fig_8_2", q_human_reading_points_composition),
        ("fig_8_3", q_git_only_measurability_sources), ("fig_8_4", q_onboarding_speed_dumbbell)]}


if __name__ == "__main__":
    import pprint
    con = connect()
    names = sys.argv[1:] or [name for name, fn in globals().items() if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__]
    for n in names:
        fn = getattr(sys.modules[__name__], n)
        print("=" * 20, n)
        pprint.pprint(fn(con), width=160, compact=True)
