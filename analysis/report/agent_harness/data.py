"""The harness series: the harness (models, subagents, context, worktrees, asks, features).

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/agent_harness/data.py   # prints every answer

One function per question; each returns what its answer slide (and breakdown slide)
plots. Weeks run from 1 Jan 2026; session-log series start the week of 9 Aug.
"""
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from record import adoption, changeset_facts, commit_facts, rows, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, category_of  # noqa: E402

LATEST_WEEK = 39
WEEKS = [f"2026-W{w:02d}" for w in range(1, LATEST_WEEK + 1)]
S_WEEKS = [f"2026-W{w:02d}" for w in range(35, LATEST_WEEK + 1)]  # the continuous session log starts 25 Aug
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]

# Model families in release order, newest last.
MODELS = ["Opus 4.5–4.6", "Sonnet 4.6", "Opus 4.7", "Opus 4.8", "Fable 5", "Sonnet 5", "Opus 5", "Fable 5.1",
          "Opus 5.5"]
RELEASE = {"Opus 4.5–4.6": "2025-11-24", "Sonnet 4.6": "2026-02-17", "Opus 4.7": "2026-04-16",
           "Opus 4.8": "2026-05-28", "Fable 5": "2026-06-09", "Sonnet 5": "2026-06-30", "Opus 5": "2026-07-24",
           "Fable 5.1": "2026-09-01", "Opus 5.5": "2026-09-22"}
UNNAMED, NONE = "Claude, model unnamed", "No agent trailer"

TRAILER = re.compile(r"co-authored-by:\s*claude\b([^<\n]*)", re.I)


def family(name):
    """'Opus 4.8 (1M context)' / 'claude-opus-4-8' -> 'Opus 4.8'; None when it names no model."""
    s = (name or "").lower().replace("claude", "").replace("-", " ").replace("(1m context)", "").strip()
    m = re.search(r"(opus|sonnet|fable|haiku)\s*(\d+)(?:[ .](\d+))?", s)
    if not m:
        return None
    fam, v = m.group(1).title(), m.group(2) + (f".{m.group(3)}" if m.group(3) and len(m.group(3)) < 3 else "")
    label = f"{fam} {v}"
    if label in ("Opus 4.5", "Opus 4.6"):
        return "Opus 4.5–4.6"
    return label


def model_of_body(body):
    names = [family(m.group(1)) for m in TRAILER.finditer(body or "")]
    if not names:
        return None
    named = [n for n in names if n]
    return named[0] if named else UNNAMED


def frac_in(day, weeks):
    y, w, wd = date.fromisoformat(day).isocalendar()
    return ((w - int(weeks[0][6:])) + (wd - 1) / 7) / len(weeks)


# ---------------------------------------------------------------- change sets with their model

@lru_cache(maxsize=None)
def set_models(con):
    """Every change set (Dependabot excluded) with the model its commits' co-author trailer names."""
    by_sha = {}
    for c in commit_facts(con):
        by_sha[(c["repo"], c["sha"])] = (model_of_body(c["body"]), c["actor"])
    main_trailer = {(r["repo"], r["sha"]): r["value"] for r in rows(con, """
        SELECT repo, sha, value FROM git.trailers WHERE lower(key)='co-authored-by' AND value LIKE 'Claude%'""")}
    out = []
    for s in changeset_facts(con):
        if s["dependabot"] or s["category"] == "out of scope":
            continue
        ms = []
        for sha in s["shas"]:
            m, actor = by_sha.get((s["repo"], sha), (None, None))
            if m is None and (s["repo"], sha) in main_trailer:
                m = family(main_trailer[(s["repo"], sha)]) or UNNAMED
            if m:
                ms.append(m)
        named = [m for m in ms if m != UNNAMED]
        model = Counter(named).most_common(1)[0][0] if named else (UNNAMED if ms else NONE)
        out.append({**s, "model": model})
    return out


# ---------------------------------------------------------------- Q model-share-over-time

def q_model_share_over_time_models(con):
    sets = set_models(con)
    by_w = defaultdict(Counter)
    for s in sets:
        by_w[s["week"]][s["model"]] += 1
    cats = [m for m in MODELS if any(s["model"] == m for s in sets)] + [UNNAMED, NONE]
    share = {m: [round(by_w[w][m] / sum(by_w[w].values()), 3) if sum(by_w[w].values()) >= 5 else None
                 for w in WEEKS] for m in cats}
    counts = {m: [by_w[w][m] for w in WEEKS] for m in cats}
    # take-over: first change set, first week as the top model, days from release
    lag = []
    for m in MODELS:
        days = sorted(s["day"] for s in sets if s["model"] == m)
        if not days:
            continue
        top = next((w for w in WEEKS if sum(by_w[w].values()) >= 5 and
                    max(by_w[w].items(), key=lambda kv: kv[1])[0] == m), None)
        top_day = date.fromisocalendar(2026, int(top[6:]), 1).isoformat() if top else None
        rel = date.fromisoformat(RELEASE[m])
        lag.append({"model": m, "release": RELEASE[m], "first": days[0], "n": len(days),
                    "first_lag": (date.fromisoformat(days[0]) - rel).days,
                    "top_week": top, "top_lag": (date.fromisoformat(top_day) - rel).days if top_day else None,
                    "peak_share": max(v or 0 for v in share[m]), "last": days[-1]})
    # main-thread turns by model, from session logs
    t = defaultdict(Counter)
    ss = sessions(con)
    for r in rows(con, """SELECT t.session_id_hash s, t.ts, t.model FROM harness.turns t
                          WHERE t.role='assistant' AND t.model LIKE 'claude-%'"""):
        if r["s"] not in ss:
            continue
        f = family(r["model"])
        if f and not f.startswith("Haiku"):
            t[week_of(r["ts"])][f] += 1
    turn_cats = [m for m in MODELS if any(t[w][m] for w in S_WEEKS)]
    turn_share = {m: [round(t[w][m] / sum(t[w].values()), 3) if sum(t[w].values()) else None for w in S_WEEKS]
                  for m in turn_cats}
    set_share_s = {m: [share[m][WEEKS.index(w)] for w in S_WEEKS] for m in turn_cats}
    n = len(sets)
    named = sum(1 for s in sets if s["model"] in MODELS)
    led = Counter()
    for w in WEEKS:
        if sum(by_w[w].values()) >= 5:
            top = max(by_w[w].items(), key=lambda kv: kv[1])[0]
            led[top] += 1
    opus = sum(1 for s in sets if s["model"].startswith("Opus"))
    diffs = [abs((turn_share[m][i] or 0) - (set_share_s[m][i] or 0)) for m in turn_cats for i in range(len(S_WEEKS))
             if turn_share[m][i] is not None and set_share_s[m][i] is not None]
    top_model_turns = {w: max(t[w].items(), key=lambda kv: kv[1])[0] if t[w] else None for w in S_WEEKS}
    top_model_sets = {w: max(by_w[w].items(), key=lambda kv: kv[1])[0] if by_w[w] else None for w in S_WEEKS}
    return {"weeks": WEEKS, "cats": cats, "share": share, "counts": counts, "lag": lag, "n": n, "named": named,
            "unnamed": sum(1 for s in sets if s["model"] == UNNAMED), "none": sum(1 for s in sets if s["model"] == NONE),
            "s_weeks": S_WEEKS, "turn_share": turn_share, "set_share_s": set_share_s, "weeks_led": dict(led),
            "opus_share": round(opus / named, 3), "turn_set_mean_diff": round(statistics.mean(diffs), 3),
            "top_agree": sum(top_model_turns[w] == top_model_sets[w] for w in S_WEEKS), "s_n": len(S_WEEKS),
            "turn_top": top_model_turns, "set_top": top_model_sets}


# ---------------------------------------------------------------- Q fixes-by-model

NOISE_FILE = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|CHANGELOG\.md|uv\.lock|"
                        r"Cargo\.lock|poetry\.lock)$")
FIX_WINDOW_DAYS = 14
FIX_CUTOFF = "2026-09-10"  # PRs merged later have not had their full 14 days


@lru_cache(maxsize=None)
def pr_models(con):
    """Merged agent PRs with their model (the model of most of their change sets) and whether a later fix
    commit on main (conventional type fix, or a revert) touched half or more of their files within 14 days."""
    by_pr = defaultdict(Counter)
    for s in set_models(con):
        if s["pr"]:
            by_pr[(s["repo"], s["pr"])][s["model"]] += 1
    files = defaultdict(set)
    for r in rows(con, """SELECT c.repo, c.pr_number, f.path FROM git.commits c
                          JOIN git.commit_files f ON f.repo=c.repo AND f.sha=c.sha WHERE c.pr_number IS NOT NULL"""):
        if not NOISE_FILE.search(r["path"]):
            files[(r["repo"], r["pr_number"])].add(r["path"])
    commits = defaultdict(list)
    for r in rows(con, """SELECT repo, sha, committed_ts ts, pr_number, conv_type, is_revert, subject FROM git.commits
                          WHERE is_merge=0 ORDER BY committed_ts"""):
        commits[r["repo"]].append(r)
    cfiles = defaultdict(set)
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        cfiles[(r["repo"], r["sha"])].add(r["path"])
    d5 = {(r["repo"], r["number"]): r["followup_within_14d_days"] for r in rows(con, "SELECT * FROM detectors.followups")}
    prs = {(r["repo"], r["number"]): r for r in rows(con, """SELECT repo, number, merged_ts, additions + deletions lines
                                                              FROM github.prs WHERE merged_ts IS NOT NULL""")}
    try:
        judged = {(r["repo"], r["pr"], r["sha"]): bool(r["fixes"]) for r in rows(con, "SELECT * FROM agent_harness.fix_pairs")}
    except sqlite3.OperationalError as e:
        print(f"agent_harness: {e}; fix-pair judgements skipped", file=sys.stderr)
        judged = {}
    out = []
    for key, models in by_pr.items():
        p = prs.get(key)
        if not p or not files.get(key):
            continue
        model = models.most_common(1)[0][0]
        merged = datetime.fromisoformat(p["merged_ts"].replace("Z", "+00:00"))
        cands = []
        for c in commits[key[0]]:
            ts = datetime.fromisoformat(c["ts"].replace("Z", "+00:00"))
            dd = (ts - merged).total_seconds() / 86400
            if dd <= 0 or c["pr_number"] == key[1]:
                continue
            if dd > FIX_WINDOW_DAYS or len(cands) >= 3:
                break
            if c["conv_type"] != "fix" and not c["is_revert"]:
                continue
            shared = cfiles[(key[0], c["sha"])] & files[key]
            if len(shared) / len(files[key]) >= 0.5:
                cands.append({"sha": c["sha"], "days": round(dd, 2), "subject": c["subject"], "shared": sorted(shared)})
        verdicts = [judged.get((key[0], key[1], c["sha"])) for c in cands]
        hit = next((c for c, v in zip(cands, verdicts) if v), None)
        fixed, fix_subject = (hit["days"], hit["subject"]) if hit else (None, None)
        raw = cands[0]["days"] if cands else None
        day = p["merged_ts"][:10]
        out.append({"repo": key[0], "pr": key[1], "model": model, "day": day, "week": week_of(day),
                    "month": day[:7], "lines": p["lines"] or 0, "sets": sum(models.values()),
                    "fixed_days": fixed, "fix_subject": fix_subject, "candidates": cands, "raw_days": raw,
                    "judged": all(v is not None for v in verdicts), "d5_days": d5.get(key), "complete": day <= FIX_CUTOFF,
                    "category": category_of(key[0])})
    return out


def wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return round(c - h, 3), round(c + h, 3)


def rate(ps, k="fixed_days"):
    return round(sum(p[k] is not None for p in ps) / len(ps), 3) if ps else None


def q_fixes_by_model_fixes(con):
    ps = [p for p in pr_models(con) if p["complete"] and p["model"] in MODELS]
    main = [m for m in MODELS if sum(p["model"] == m for p in ps) >= 80]
    by_m_month = {m: [] for m in main}
    for m in main:
        for mo in MONTHS:
            sel = [p for p in ps if p["model"] == m and p["month"] == mo]
            by_m_month[m].append(rate(sel) if len(sel) >= 10 else None)
    overall = {m: {"n": sum(p["model"] == m for p in ps), "rate": rate([p for p in ps if p["model"] == m]),
                   "d5": rate([p for p in ps if p["model"] == m], "d5_days")} for m in main}
    wk = defaultdict(list)
    for p in ps:
        wk[p["week"]].append(p)
    weekly = [rate(wk[w]) if len(wk[w]) >= 8 else None for w in WEEKS]
    # same weeks: only weeks in which a model shipped next to another, so time is held (roughly) still
    shared = defaultdict(lambda: [0, 0])
    for w, sel in wk.items():
        ms = Counter(p["model"] for p in sel)
        if sum(1 for v in ms.values() if v >= 5) < 2:
            continue
        for p in sel:
            if ms[p["model"]] >= 5:
                shared[p["model"]][0] += 1
                shared[p["model"]][1] += p["fixed_days"] is not None
    same_weeks = {m: {"n": v[0], "k": v[1], "rate": round(v[1] / v[0], 3), "ci": wilson(v[1], v[0])}
                  for m, v in shared.items() if v[0] >= 20}
    for m, o in overall.items():
        k = sum(1 for p in ps if p["model"] == m and p["fixed_days"] is not None)
        o["k"], o["ci"] = k, wilson(k, o["n"])
    # by size: small (< 100 lines) vs larger, per model
    size = {m: {lab: rate([p for p in ps if p["model"] == m and cond(p)])
                for lab, cond in (("< 100 lines", lambda p: p["lines"] < 100), ("100+ lines", lambda p: p["lines"] >= 100))}
            for m in main}
    return {"months": MONTHS, "by_model_month": by_m_month, "overall": overall, "weeks": WEEKS, "weekly": weekly,
            "same_weeks": same_weeks, "size": size, "n": len(ps), "all_rate": rate(ps),
            "d5_rate": rate(ps, "d5_days"), "cutoff": FIX_CUTOFF}


# ---------------------------------------------------------------- session-log helpers

LOG_START = "2026-08-25"  # one session from 9 Aug; the continuous log starts 25 Aug (older transcripts were purged)


def days_between(a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)]


@lru_cache(maxsize=None)
def log_end(con):
    return con.execute("SELECT MAX(substr(ts,1,10)) FROM harness.turns").fetchone()[0]


SCRIPTED = ("You are reviewing a diff", "Return only this exact JSON")  # wayfare-skills' pre-commit `claude -p`


@lru_cache(maxsize=None)
def all_sessions(con):
    return {r["session_id_hash"]: r for r in rows(con, f"""SELECT * FROM harness.sessions
                                                         WHERE first_ts >= '{LOG_START}'""")}


@lru_cache(maxsize=None)
def scripted(con):
    """Sessions a script started (the plugin's pre-commit diff review), and sessions with no model turn."""
    s = {r["s"] for r in rows(con, "SELECT DISTINCT session_id_hash s, text_redacted t FROM harness.turns WHERE role='user'")
         if (r["t"] or "").startswith(SCRIPTED)}
    return s | {k for k, v in all_sessions(con).items() if not v["assistant_turns"]}


@lru_cache(maxsize=None)
def sessions(con):
    """Interactive sessions from 25 Aug: the owner (or a goal turn) driving the agent."""
    skip = scripted(con)
    return {k: v for k, v in all_sessions(con).items() if k not in skip}


def lweeks(con):
    return [w for w in WEEKS if w >= "2026-W35"]


# Plugin changes (wayfare-skills history) drawn as pink marks on the session-log charts.
SUBAGENT_EVENTS = [
    ("2026-08-29", "Fan-out goals, a worktree each (#67)"),
    ("2026-09-18", "One branch per goal; no fork fan-out (#88, #94)"),
    ("2026-09-24", "Fan-out waits for every agent (#123)"),
]
EXPLORE_EVENTS = [("2026-08-29", "Investigate in an Explore subagent (#66)")]
WORKTREE_EVENTS = [("2026-08-29", "Goal features each in a worktree (#67)"),
                   ("2026-09-18", "Goals stop using worktrees (#88)")]


def day_frac(day, days):
    return (days.index(day) + 0.5) / len(days) if day in days else None


# ---------------------------------------------------------------- Q subagent-launches

KINDS = ["General-purpose", "Reviewer personas", "Explore", "Fork", "Launched by a subagent", "Type not recorded"]


def kind_of(t):
    if not t:
        return None
    if t.startswith("pr-review-toolkit:"):
        return "Reviewer personas"
    return {"general-purpose": "General-purpose", "Explore": "Explore", "fork": "Fork"}.get(t, "General-purpose")


@lru_cache(maxsize=None)
def runs(con):
    ss = sessions(con)
    rs = [r for r in rows(con, "SELECT * FROM harness.subagent_runs") if r["session_id_hash"] in ss]
    typed = defaultdict(list)
    for r in rs:
        if r["subagent_type"]:
            typed[r["session_id_hash"]].append((r["ts_start"], r["ts_end"]))
    for r in rs:
        k = kind_of(r["subagent_type"])
        if not k:
            inside = any(a < r["ts_start"] and b >= r["ts_end"] for a, b in typed[r["session_id_hash"]])
            k = "Launched by a subagent" if inside else "Type not recorded"
        r["kind"] = k
        r["day"] = r["ts_start"][:10]
        r["week"] = week_of(r["ts_start"])
        r["repo"] = ss[r["session_id_hash"]]["repo"]
    return rs


def q_subagent_launches_subagents(con):
    rs, ss = runs(con), sessions(con)
    days = days_between(LOG_START, log_end(con))
    daily = {k: [sum(1 for r in rs if r["kind"] == k and r["day"] == d) for d in days] for k in KINDS}
    ws = lweeks(con)
    main_calls = Counter(week_of(r["ts"]) for r in rows(con, "SELECT ts FROM harness.tool_calls")
                         if r["ts"] >= LOG_START)
    sub_calls = defaultdict(int)
    for r in rs:
        sub_calls[r["week"]] += r["tool_calls"] or 0
    sess_w = Counter(s["week"] for s in ss.values())
    per_session = [round(sum(1 for r in rs if r["week"] == w) / sess_w[w], 1) if sess_w[w] else None for w in ws]
    sub_share = [round(sub_calls[w] / (sub_calls[w] + main_calls[w]), 3) if main_calls[w] else None for w in ws]
    with_any = [round(sum(1 for s in ss.values() if s["week"] == w and s["subagent_count"]) / sess_w[w], 3)
                if sess_w[w] else None for w in ws]
    # by repo: runs per session, by kind
    by_repo = defaultdict(Counter)
    n_sess = Counter(s["repo"] for s in ss.values())
    for r in rs:
        by_repo[r["repo"]][r["kind"]] += 1
    repos = [r for r in sorted(by_repo, key=lambda r: -sum(by_repo[r].values())) if r and n_sess[r] >= 5][:10]
    repo_series = {k: [round(by_repo[r][k] / n_sess[r], 1) for r in repos] for k in KINDS}
    repo_total = [round(sum(by_repo[r].values()) / n_sess[r], 1) for r in repos]
    small = sum(1 for r in rs if family(r["model"] or "") and family(r["model"]).split()[0] in ("Sonnet", "Haiku"))
    return {"days": days, "daily": daily, "weeks": ws, "per_session": per_session, "sub_share": sub_share,
            "with_any": with_any, "total": len(rs), "by_kind": {k: sum(daily[k]) for k in KINDS},
            "sessions": len(ss), "repos": repos, "repo_series": repo_series, "repo_total": repo_total, "small_model_share": round(small / len(rs), 3),
            "events": SUBAGENT_EVENTS, "main_calls": sum(main_calls.values()), "sub_calls": sum(sub_calls.values())}


# ---------------------------------------------------------------- Q subagent-delegation

def q_subagent_delegation(con):
    ss = sessions(con)
    days = days_between(LOG_START, log_end(con))
    ctx = defaultdict(list)
    ctx_repo = defaultdict(list)
    for r in rows(con, """SELECT session_id_hash s, ts, input_tokens + cache_read_tokens + cache_write_tokens c
                          FROM harness.turns WHERE role='assistant' AND model LIKE 'claude-%'"""):
        if r["s"] in ss:
            ctx[r["ts"][:10]].append(r["c"])
            ctx_repo[ss[r["s"]]["repo"]].append(r["c"])
    calls = rows(con, f"SELECT session_id_hash s, ts, tool, subagent_type FROM harness.tool_calls WHERE ts >= '{LOG_START}'")
    explore = Counter(c["ts"][:10] for c in calls if c["subagent_type"] == "Explore")
    reads = Counter(c["ts"][:10] for c in calls if c["tool"] in ("Read", "Grep", "Glob"))
    sess_day = Counter(s["day"] for s in ss.values())
    med = [round(statistics.median(ctx[d]) / 1000) if len(ctx[d]) >= 50 else None for d in days]
    all_ctx = [c for d in days for c in ctx[d]]
    before = [d for d in days if d < EXPLORE_EVENTS[0][0]]
    after = [d for d in days if d >= EXPLORE_EVENTS[0][0]]
    per = lambda cnt, ds: round(sum(cnt[d] for d in ds) / max(1, sum(sess_day[d] for d in ds)), 2)
    ex_sessions = {c["s"] for c in calls if c["subagent_type"] == "Explore"}
    repos = sorted((r for r in ctx_repo if r and len(ctx_repo[r]) >= 500), key=lambda r: -len(ctx_repo[r]))[:10]
    return {"days": days, "median_k": med, "explore": [explore[d] for d in days], "reads": [reads[d] for d in days],
            "overall_median_k": round(statistics.median(all_ctx) / 1000),
            "share_over_500k": round(sum(c > 500000 for c in all_ctx) / len(all_ctx), 3),
            "share_over_200k": round(sum(c > 200000 for c in all_ctx) / len(all_ctx), 3),
            "turns": len(all_ctx), "explore_total": sum(explore.values()),
            "explore_per_session_before": per(explore, before), "explore_per_session_after": per(explore, after),
            "sessions_with_explore": len(ex_sessions), "sessions": len(ss),
            "main_reads": sum(reads.values()),
            "main_bash": sum(1 for c in calls if c["tool"] == "Bash"),
            "repos": repos, "repo_median_k": [round(statistics.median(ctx_repo[r]) / 1000) for r in repos],
            "repo_share_500k": [round(sum(c > 500000 for c in ctx_repo[r]) / len(ctx_repo[r]), 3) for r in repos],
            "events": EXPLORE_EVENTS}


# ---------------------------------------------------------------- Q context-compaction

CONT = "This session is being continued from a previous conversation"


@lru_cache(maxsize=None)
def compactions(con):
    """(session, ts) of each compaction: the continuation marker, or a fall from 300K+ to under 40% of it."""
    ss = sessions(con)
    found, prev = {}, {}
    for r in rows(con, """SELECT session_id_hash s, ts, role, input_tokens + cache_read_tokens + cache_write_tokens c,
                                 text_redacted t FROM harness.turns
                          WHERE role='user' OR model LIKE 'claude-%' ORDER BY session_id_hash, ts, idx"""):
        if r["s"] not in ss:
            continue
        if r["role"] == "user":
            if (r["t"] or "").startswith(CONT):
                found[(r["s"], r["ts"][:13])] = (r["ts"], "marker")
            continue
        p = prev.get(r["s"])
        if p and p[1] >= 300000 and r["c"] < 0.4 * p[1]:
            key = (r["s"], r["ts"][:13])
            if key not in found and (r["s"], p[0][:13]) not in found:
                found[key] = (r["ts"], "context fell")
        prev[r["s"]] = (r["ts"], r["c"])
    return sorted((s, ts, how) for (s, _), (ts, how) in found.items())


def q_context_compaction(con):
    ss = sessions(con)
    cs = compactions(con)
    days = days_between(LOG_START, log_end(con))
    daily = [sum(1 for _, ts, _ in cs if ts[:10] == d) for d in days]
    peak = {}
    for r in rows(con, """SELECT session_id_hash s, MAX(input_tokens + cache_read_tokens + cache_write_tokens) m
                          FROM harness.turns WHERE role='assistant' GROUP BY 1"""):
        if r["s"] in ss:
            peak[r["s"]] = r["m"]
    bins = [("< 200K", 0, 2e5), ("200–500K", 2e5, 5e5), ("500–900K", 5e5, 9e5), ("900K+", 9e5, 1e9)]
    peak_hist = {b[0]: sum(1 for v in peak.values() if b[1] <= v < b[2]) for b in bins}
    # owner corrections before vs after each session's first compaction, from the shared prompt_intent labels
    source = "detectors.prompt_intent"
    try:
        intent = rows(con, "SELECT ts, repo, intent FROM detectors.prompt_intent")
    except sqlite3.OperationalError as e:
        print(f"agent_harness: {e}; falling back to detectors.prompt_kind", file=sys.stderr)
        source = "detectors.prompt_kind (regex-flagged prompts only)"
        kind = {r["content_hash"]: r["kind"] for r in rows(con, "SELECT content_hash, kind FROM detectors.prompt_kind")}
        intent = [{"ts": r["ts"], "repo": r["repo"], "intent": kind.get(r["content_hash"]) if r["flagged"] else None}
                  for r in rows(con, "SELECT ts, repo, content_hash, flagged FROM detectors.prompt_kind_by_prompt")]
    by_repo = defaultdict(list)
    for p in intent:
        by_repo[p["repo"]].append(p)
    uts = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts FROM harness.turns WHERE role='user'"):
        uts[r["s"]].append(datetime.fromisoformat(r["ts"].replace("Z", "+00:00")))

    def prompts_of(s):
        """The owner's typed prompts in session s: same repo, within 5 seconds of one of its user turns."""
        out = []
        for p in by_repo[ss[s]["repo"]]:
            pt = datetime.fromisoformat(p["ts"].replace("Z", "+00:00"))
            if pt.tzinfo is None:
                pt = pt.replace(tzinfo=timezone.utc)
            if any(abs((pt - u).total_seconds()) <= 5 for u in uts[s]):
                out.append((pt.isoformat()[:19], p["intent"] in ("correction", "redirect")))
        return sorted(out)

    first = {}
    for s, ts, _ in cs:
        first.setdefault(s, ts[:19])
    per_session = []
    for s, t in first.items():
        ps = prompts_of(s)
        b_, a_ = [x for x in ps if x[0] < t], [x for x in ps if x[0] >= t]
        per_session.append({"before": len(b_), "cb": sum(x[1] for x in b_), "after": len(a_), "ca": sum(x[1] for x in a_)})
    # baseline: long sessions (peak 500K+) that never compacted, first two-thirds of prompts vs the last third
    base = [0, 0, 0, 0]
    for s in ss:
        if s in first or (peak.get(s) or 0) < 500000:
            continue
        ps = prompts_of(s)
        if len(ps) < 6:
            continue
        k = len(ps) * 2 // 3
        base = [base[0] + k, base[1] + sum(x[1] for x in ps[:k]), base[2] + len(ps) - k, base[3] + sum(x[1] for x in ps[k:])]
    before = sum(p["before"] for p in per_session)
    after = sum(p["after"] for p in per_session)
    cb = sum(p["cb"] for p in per_session)
    ca = sum(p["ca"] for p in per_session)
    carriers = sorted((p["ca"] for p in per_session), reverse=True)
    return {"days": days, "daily": daily, "n": len(cs), "sessions_with": len({s for s, _, _ in cs}),
            "sessions": len(ss), "by_method": dict(Counter(h for _, _, h in cs)), "peak_hist": peak_hist,
            "intent_source": source, "prompts_before": before, "prompts_after": after,
            "corrections_before": cb, "corrections_after": ca, "sessions_rising": sum(p["ca"] / p["after"] > (p["cb"] / p["before"] if p["before"] else 0)
                                                                                for p in per_session if p["after"]),
            "sessions_with_after": sum(1 for p in per_session if p["after"]),
            "top3_after": sum(carriers[:3]), "baseline": base, "per_session": per_session}


# ---------------------------------------------------------------- Q worktree-use

BUCKET_MIN = 10


def overlaps(con):
    """Per repo, the 10-minute buckets in which two or more interactive sessions were both active."""
    ss = sessions(con)
    active = defaultdict(set)
    for r in rows(con, "SELECT session_id_hash s, ts FROM harness.turns"):
        if r["s"] in ss and ss[r["s"]]["repo"] not in (None, "", "fleet"):
            t = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            active[(ss[r["s"]]["repo"], t.strftime("%Y-%m-%dT%H:") + f"{t.minute // BUCKET_MIN * BUCKET_MIN:02d}")].add(r["s"])
    return {k: v for k, v in active.items() if len(v) >= 2}


def q_worktree_use_worktrees(con):
    ss = sessions(con)
    ws = lweeks(con)
    days = days_between(LOG_START, log_end(con))
    wt_branch = {r["s"] for r in rows(con, "SELECT DISTINCT session_id_hash s FROM harness.turns WHERE branch LIKE 'worktree-%'")}
    enter = rows(con, "SELECT session_id_hash s, ts FROM harness.tool_calls WHERE tool='EnterWorktree'")
    wt_sessions = (wt_branch | {e["s"] for e in enter}) & set(ss)
    ov = overlaps(con)
    ov_sessions = set().union(*ov.values()) if ov else set()
    ov_hours = defaultdict(float)
    ov_by_repo = Counter()
    for (repo, b), v in ov.items():
        ov_hours[week_of(b[:10])] += BUCKET_MIN / 60
        ov_by_repo[repo] += BUCKET_MIN / 60
    labs = rows(con, "SELECT session_id_hash s, ts, kind, why FROM agent_harness.collision_turns WHERE kind IS NOT NULL")
    incidents = defaultdict(set)
    for l in labs:
        if l["s"] in ss:
            incidents[l["kind"]].add((l["s"], l["ts"][:10]))
    sess_w = Counter(s["week"] for s in ss.values())
    series = {
        "Collision recorded": [sum(1 for s, d in incidents["collision"] if week_of(d) == w) for w in ws],
        "Noticed and avoided": [sum(1 for s, d in incidents["avoided"] if week_of(d) == w) for w in ws],
    }
    share_ov = [round(sum(1 for s in ov_sessions if ss[s]["week"] == w) / sess_w[w], 3) if sess_w[w] else None for w in ws]
    coll_repo = Counter(ss[s]["repo"] for s, d in incidents["collision"])
    avoid_repo = Counter(ss[s]["repo"] for s, d in incidents["avoided"])
    repos = [r for r, _ in ov_by_repo.most_common(10)]
    # worktree mentions in the work-item logs, per week (the goal fan-out's own record)
    log_wt = Counter(week_of(r["ts"]) for r in rows(con, """SELECT ts FROM plans.item_logs
                     WHERE (text_redacted LIKE '%worktree%') AND ts >= '2026-07-01'""") if r["ts"])
    return {"weeks": ws, "series": series, "share_overlapping": share_ov,
            "overlap_hours": [round(ov_hours[w]) for w in ws], "overlap_total_h": round(sum(ov_hours.values())),
            "overlap_sessions": len(ov_sessions), "sessions": len(ss), "buckets": len(ov),
            "worktree_sessions": len(wt_sessions), "enter_worktree": len(enter),
            "collisions": len(incidents["collision"]), "avoided": len(incidents["avoided"]),
            "own_parallel": len(incidents["own_parallel"]),
            "collision_sessions": len({s for s, _ in incidents["collision"]}),
            "collisions_from_16sep": sum(1 for _, d in incidents["collision"] if d >= "2026-09-16"),
            "repos": repos, "repo_overlap_h": [round(ov_by_repo[r]) for r in repos],
            "repo_collisions": [coll_repo[r] for r in repos], "repo_avoided": [avoid_repo[r] for r in repos],
            "log_worktree_weeks": {w: log_wt[w] for w in WEEKS if log_wt[w]}, "events": WORKTREE_EVENTS,
            "examples": [(l["ts"][:10], l["why"]) for l in labs if l["kind"] == "collision"]}


# ---------------------------------------------------------------- Q agent-stops-per-hour

def q_agent_stops_per_hour(con):
    ss = sessions(con)
    ws = lweeks(con)
    work = defaultdict(float)
    for r in rows(con, "SELECT session_id_hash s, minutes FROM detectors.session_time_segments WHERE kind='working'"):
        if r["s"] in ss:
            work[ss[r["s"]]["week"]] += r["minutes"] / 60
    calls = [c for c in rows(con, f"""SELECT session_id_hash s, ts, tool, was_rejected, question_count
                                       FROM harness.tool_calls WHERE ts >= '{LOG_START}'""") if c["s"] in ss]
    asks, qs, rej = Counter(), Counter(), Counter()
    for c in calls:
        w = ss[c["s"]]["week"]
        if c["tool"] == "AskUserQuestion":
            asks[w] += 1
            qs[w] += c["question_count"] or 1
        if c["was_rejected"] and c["tool"] != "AskUserQuestion":
            rej[w] += 1
    per_h = lambda cnt: [round(cnt[w] / work[w], 2) if work[w] else None for w in ws]
    by_repo_asks, by_repo_work = Counter(), defaultdict(float)
    for c in calls:
        if c["tool"] == "AskUserQuestion":
            by_repo_asks[ss[c["s"]]["repo"]] += 1
    for r in rows(con, "SELECT session_id_hash s, minutes FROM detectors.session_time_segments WHERE kind='working'"):
        if r["s"] in ss:
            by_repo_work[ss[r["s"]]["repo"]] += r["minutes"] / 60
    repos = [r for r in sorted(by_repo_work, key=lambda r: -by_repo_work[r]) if r and by_repo_work[r] >= 3][:10]
    rej_tools = Counter(c["tool"] for c in calls if c["was_rejected"] and c["tool"] != "AskUserQuestion")
    return {"weeks": ws, "asks_per_h": per_h(asks), "questions_per_h": per_h(qs), "rejections_per_h": per_h(rej),
            "work_h": [round(work[w]) for w in ws], "asks": sum(asks.values()), "questions": sum(qs.values()),
            "rejections": sum(rej.values()), "work_total_h": round(sum(work.values())),
            "overall_asks_per_h": round(sum(asks.values()) / sum(work.values()), 2),
            "overall_rej_per_h": round(sum(rej.values()) / sum(work.values()), 2),
            "repos": repos, "repo_asks_per_h": [round(by_repo_asks[r] / by_repo_work[r], 2) for r in repos],
            "rejected_tools": rej_tools.most_common(6),
            "sessions_with_ask": sum(1 for s in ss if any(c["s"] == s and c["tool"] == "AskUserQuestion" for c in calls)),
            "sessions": len(ss)}


# ---------------------------------------------------------------- Q feature-uptake-lag

def first_prompt(con, command):
    r = con.execute("SELECT MIN(substr(ts,1,10)) FROM harness.prompts WHERE is_slash_command=1 AND command=?",
                    (command,)).fetchone()
    return r[0]


def first_tool(con, tool=None, subagent=None):
    if subagent:
        r = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM harness.tool_calls WHERE subagent_type=?",
                        (subagent,)).fetchone()
    else:
        r = con.execute("SELECT MIN(substr(ts,1,10)), MAX(substr(ts,1,10)) FROM harness.tool_calls WHERE tool=?",
                        (tool,)).fetchone()
    return r[0], r[1]


def q_feature_uptake_lag(con):
    rel = {r["name"]: r["date"] for r in rows(con, "SELECT name, date FROM harness.cc_releases")}
    trailer_1m = con.execute("""SELECT MIN(substr(ts,1,10)) FROM pr_commits.pr_commits
                                WHERE body_redacted LIKE '%(1M context)%'""").fetchone()[0]
    opus55 = con.execute("""SELECT MIN(substr(ts,1,10)) FROM pr_commits.pr_commits
                            WHERE body_redacted LIKE '%Claude Opus 5.5%'""").fetchone()[0]
    fork = first_tool(con, subagent="fork")
    wt = first_tool(con, tool="EnterWorktree")
    fork_after_ban = con.execute("SELECT COUNT(*) FROM harness.tool_calls WHERE subagent_type='fork' AND ts >= '2026-09-19'").fetchone()[0]
    art = first_tool(con, tool="Artifact")
    mon = first_tool(con, tool="Monitor")
    feats = [
        # label, release name, first use, where seen, lower bound?, dropped (date, how) or None
        ("Plugins and skills", "Plugins (v2.0.12)", "2026-03-07", "wayfare-skills a2bb70d, the hero skills plugin", False, None),
        ("Explore subagent", "Explore subagent (v2.0.17)", "2026-03-09", "plugin tells hero-init to use it (ec52230)", False, None),
        ("Worktrees", "Worktrees (2.1.49)", min(wt[0], "2026-08-29"), "EnterWorktree in the logs; #67 builds goal features in them", True,
         ("2026-09-18", "goals stop using worktrees (#88)")),
        ("/loop", "/loop (2.1.71)", first_prompt(con, "loop"), "prompt history", False, None),
        ("Opus 1M context", "Opus 1M default (2.1.75)", trailer_1m, "first '(1M context)' co-author trailer", False, None),
        ("Monitor tool", "Monitor tool (2.1.98)", mon[0], "session logs (start 25 Aug)", True, None),
        ("/goal", "/goal + agent view (2.1.139)", first_prompt(con, "goal"), "prompt history; plugin runs on it from #63",
         False, None),
        ("Dynamic workflows", "Dynamic workflows (2.1.154)", None, "never seen", False, None),
        ("Artifacts", "Artifacts in Claude Code", art[0], "session logs (start 25 Aug)", True, None),
        ("Fork subagents", "Fork subagents on (2.1.232)", fork[0], "session logs (start 25 Aug)", True,
         ("2026-09-18", "fan-out subagent is never a fork (#94)")),
        ("/skill-doctor", "/skill-doctor (2.1.261)", first_prompt(con, "skill-doctor"), "prompt history", False, None),
        ("Opus 5.5 default", "Opus 5.5 default (2.1.280)", opus55, "first Opus 5.5 trailer", False, None),
    ]
    out = []
    for label, name, first, where, lower, dropped in feats:
        r = rel.get(name)
        out.append({"feature": label, "release": r, "first": first, "where": where, "lower_bound": lower,
                    "lag": (date.fromisoformat(first) - date.fromisoformat(r)).days if first and r else None,
                    "dropped": dropped})
    work = [f for f in out if f["lag"] is not None and not f["feature"].startswith("Opus")]
    return {"features": out, "median_lag": statistics.median(f["lag"] for f in work),
            "work_features": len(work),
            "never": [f["feature"] for f in out if not f["first"]],
            "fork_last": fork[1], "worktree_calls": wt, "fork_after_ban": fork_after_ban}


if __name__ == "__main__":
    from cube.db import connect
    con = connect("agent_harness")
    fns = [fn for name, fn in sorted(globals().items()) if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__]
    for f in (fns if len(sys.argv) < 2 else [globals()[a] for a in sys.argv[1:]]):
        print("==", f.__name__)
        print(json.dumps(f(con), default=str))
