"""Floor efficiency series: factory floor efficiency.

One function per question, each returning what its answer slide (and breakdown, where it has
one) plots. Git and PR series run weekly from 1 Jan 2026. Session series run weekly from W35:
the Claude Code logs start 9 Aug but hold a single session before 25 Aug. Totals include that
session. Weeks with no log are None ("not tracked"), never zero.

The brief's session rule: a gap over 8 hours inside a session means the session closed, so it
is no time at all. D6's `away` gaps up to 8 hours are idle time, never owner time. Owner time is
waiting on the human (D6 `waiting_human`) plus reply time (a gap of 5 minutes or less ending in
a prompt the owner typed). Chapter 23 uses this same definition, so the two stay comparable.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/efficiency/data.py   # prints every series
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.dirname(HERE)
ANALYSIS = os.path.dirname(REPORT)
sys.path.insert(0, ANALYSIS)
sys.path.insert(0, REPORT)
from record import STAGES, adoption, changeset_facts, rows, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, category_of  # noqa: E402

LATEST_WEEK = 39
WEEKS = [f"2026-W{w:02d}" for w in range(1, LATEST_WEEK + 1)]
# 10-24 Aug (W33-W34): no sessions are logged ("data not available", owner-confirmed), so those weeks
# are unobserved in session-derived data, never zero, idle or downtime. Session charts label them; every
# session measure starts 25 Aug (W35). The lone logged session before it (9 Aug) is left out too. Typed
# prompts continue through the gap, so prompt-based series keep those weeks.
OUTAGE_WEEKS = ("2026-W33", "2026-W34")
OUTAGE = ("2026-08-17", "No session data, 10-24 Aug")
SESSIONS_FROM_WEEK = "2026-W35"
SESSION_WEEKS = [w for w in WEEKS if w >= OUTAGE_WEEKS[0]]
ITEM_WEEKS = [w for w in WEEKS if w >= "2026-W30"]
DATA_END = "2026-09-24"
CLOSED_GAP_MIN = 8 * 60
# The owner works in US Pacific time (UTC-7 in the study window).
LOCAL = timezone(timedelta(hours=-7))
AWAY_AFTER_MIN = 30
CEILING = 6
APPS = ("app", "app, no features yet")
RENAMES = {"hero-skills": "wayfare-skills"}
TERMINAL_ITEM = {"done", "dropped", "rejected", "delivered", "superseded", "wontfix", "cancelled", "abandoned"}
SHIPPED_ITEM = {"done", "delivered"}
AUTOMATED_RE = re.compile(r"^(You are reviewing a diff|This session is being continued|<command-message>loop<|"
                          r"<bash-stdout>|<bash-stderr>|<local-command|Caveat:)")
REVERT_RE = re.compile(r"^(revert\b|Revert \")", re.I)

# Events drawn in pink, from wayfare-skills' history and the session logs.
FANOUT = ("2026-08-29", "Concurrent goals, fan-out (#67)")
SCRIPTED_GATES = ("2026-08-29", "Scripted gates before the model (#65)")
BATCH_VERIFY = ("2026-09-24", "Build every task, verify once (#120)")


def connect():
    from cube.db import connect as cube_connect
    return cube_connect()


def parse_ts(ts):
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def repo_name(r):
    return RENAMES.get(r, r)


def median(v):
    return round(statistics.median(v), 1) if v else None


def pctile(v, p):
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, int(p * len(v)))], 1)


def share(a, b, min_n=1):
    return round(a / b, 3) if b and b >= min_n else None


def in_scope(repo):
    return repo and repo not in OUT_OF_SCOPE and category_of(repo) != "out of scope"


def session_weeks_with_logs(con):
    return {r["week"] for r in rows(con, "SELECT DISTINCT week FROM harness.sessions") if r["week"] >= SESSIONS_FROM_WEEK}


def observed(ts_or_day):
    return week_of(str(ts_or_day)[:10]) >= SESSIONS_FROM_WEEK


# ------------------------------------------------------------------ sessions and time

@lru_cache(maxsize=None)
def sessions(con):
    return {r["session_id_hash"]: {**r, "repo": repo_name(r["repo"] or "")}
            for r in rows(con, "SELECT * FROM harness.sessions")}


@lru_cache(maxsize=None)
def session_turns(con):
    by = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts, role, is_synthetic, text_redacted t FROM harness.turns "
                       "WHERE ts IS NOT NULL ORDER BY session_id_hash, ts"):
        by[r["s"]].append((parse_ts(r["ts"]), r["role"], r["is_synthetic"], r["t"] or ""))
    return by


def _ch03():
    import importlib.util
    spec = importlib.util.spec_from_file_location("agent_harness_data", os.path.join(REPORT, "agent_harness", "data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=None)
def headless(con):
    """Scripted sessions, excluded from every session count, share, concurrency and clock measure.

    Chapter 3's filter (report/agent_harness/data.py scripted): the pre-commit hook's single-prompt `claude -p`
    diff reviews plus sessions with no model turn. They hold almost no spend and link to no PR, so
    counting them would make half the "sessions" look like scrap."""
    out = set(_ch03().scripted(con))
    for s, turns in session_turns(con).items():
        first = next((t for t in turns if t[1] == "user"), None)
        if first and first[3].startswith("You are reviewing a diff"):
            out.add(s)
    return frozenset(out)


def is_owner_prompt(turn):
    return turn[1] == "user" and not turn[2] and not AUTOMATED_RE.match(turn[3])


@lru_cache(maxsize=None)
def segments(con):
    """D6 segments of interactive sessions, with the 8-hour rule applied: longer gaps are dropped as 'closed'."""
    skip = headless(con)
    out = []
    for r in rows(con, "SELECT session_id_hash s, kind, start_ts, end_ts, minutes FROM detectors.session_time_segments"):
        a, b = parse_ts(r["start_ts"]), parse_ts(r["end_ts"])
        if not observed(r["start_ts"]) or r["s"] in skip:
            continue
        out.append({"s": r["s"], "kind": "closed" if r["minutes"] > CLOSED_GAP_MIN else r["kind"],
                    "start": a, "end": b, "minutes": r["minutes"], "week": week_of(a.date().isoformat())})
    return tuple(out)


@lru_cache(maxsize=None)
def reply_minutes(con):
    """{(session, week): minutes} of gaps of 5 min or less that end in an owner-typed prompt."""
    out = defaultdict(float)
    skip = headless(con)
    for s, turns in session_turns(con).items():
        if s in skip:
            continue
        for prev, cur in zip(turns, turns[1:]):
            if is_owner_prompt(cur) and observed(cur[0].date()):
                gap = (cur[0] - prev[0]).total_seconds() / 60
                if gap <= 5:
                    out[(s, week_of(cur[0].date().isoformat()))] += gap
    return dict(out)


def union_hours(spans):
    spans = sorted(spans)
    tot, a0, b0 = 0.0, None, None
    for a, b in spans:
        if b0 is None or a > b0:
            if b0 is not None:
                tot += (b0 - a0).total_seconds()
            a0, b0 = a, b
        else:
            b0 = max(b0, b)
    if b0 is not None:
        tot += (b0 - a0).total_seconds()
    return tot / 3600


# ------------------------------------------------------------------ Q session-clock where the clock goes

KINDS = [("working", "Agent working"), ("waiting_human", "Waiting on the owner"), ("limited", "Stopped by a limit"),
         ("away", "Idle")]


def q_session_clock_clock(con):
    logged = session_weeks_with_logs(con)
    wk = defaultdict(lambda: defaultdict(float))
    by_repo = defaultdict(lambda: defaultdict(float))
    work_spans = defaultdict(list)
    closed = 0.0
    ses = sessions(con)
    for g in segments(con):
        if g["kind"] == "closed":
            closed += g["minutes"] / 60
            continue
        wk[g["week"]][g["kind"]] += g["minutes"] / 60
        by_repo[ses.get(g["s"], {}).get("repo", "")][g["kind"]] += g["minutes"] / 60
        if g["kind"] == "working":
            work_spans[g["week"]].append((g["start"], g["end"]))
    reply = defaultdict(float)
    for (s, w), m in reply_minutes(con).items():
        reply[w] += m / 60
    series = {label: [round(wk[w][k], 1) if w in logged else None for w in SESSION_WEEKS] for k, label in KINDS}
    tot = {k: sum(wk[w][k] for w in wk) for k, _ in KINDS}
    all_h = sum(tot.values())
    wall = {w: round(union_hours(work_spans[w]), 1) for w in work_spans}
    owner = {w: round(wk[w]["waiting_human"] + reply[w], 1) for w in wk}
    repos = sorted((r for r in by_repo if in_scope(r)), key=lambda r: -sum(by_repo[r].values()))[:10]
    repo_share = {label: [round(by_repo[r][k] / sum(by_repo[r].values()), 3) for r in repos] for k, label in KINDS}
    return {"weeks": SESSION_WEEKS, "series": series, "totals": {k: round(v) for k, v in tot.items()},
            "shares": {k: round(v / all_h, 3) for k, v in tot.items()}, "hours": round(all_h),
            "closed_hours": round(closed), "wall_working": [wall.get(w) if w in logged else None for w in SESSION_WEEKS],
            "working_sum": [round(wk[w]["working"], 1) if w in logged else None for w in SESSION_WEEKS],
            "owner_hours": [owner.get(w) if w in logged else None for w in SESSION_WEEKS],
            "owner_total": round(sum(owner.values())), "reply_total": round(sum(reply.values()), 1),
            "wall_total": round(sum(wall.values())), "repos": repos, "repo_share": repo_share,
            "repo_hours": [round(sum(by_repo[r].values())) for r in repos]}


# ------------------------------------------------------------------ Q usage-limit-stops usage limits

def limit_stops(con):
    """Limit events grouped into stops: one stop per session per burst (events within 30 min).

    A stop lasts from its first event to the session's next assistant turn; a stop with no later
    turn, or one longer than the 8-hour rule, ended the session."""
    turns = session_turns(con)
    ev = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts, kind, org FROM harness.limit_events WHERE ts IS NOT NULL"):
        ev[r["s"]].append((parse_ts(r["ts"]), r["kind"], r["org"] or ""))
    stops = []
    for s, es in ev.items():
        es.sort()
        group = [es[0]]
        for e in es[1:] + [None]:
            if e is not None and (e[0] - group[-1][0]).total_seconds() <= 1800:
                group.append(e)
                continue
            t0 = group[0][0]
            nxt = next((t[0] for t in turns.get(s, []) if t[1] == "assistant" and t[0] > group[-1][0] and not t[2]), None)
            mins = (nxt - t0).total_seconds() / 60 if nxt else None
            stops.append({"s": s, "start": t0, "week": week_of(t0.date().isoformat()),
                          "kind": Counter(g[1] for g in group).most_common(1)[0][0], "org": group[0][2],
                          "events": len(group), "minutes": mins})
            group = [e] if e else []
    return stops


LIMIT_KINDS = [("session", "Session (5-hour) limit"), ("weekly", "Weekly limit"), ("spend", "Spend cap"),
               ("credits", "Out of credits")]
STOP_BINS = [("under 15 min", 0, 15), ("15-60 min", 15, 60), ("1-3 h", 60, 180), ("3-8 h", 180, 480),
             ("session ended", 480, None)]


def q_usage_limit_stops_limits(con):
    logged = session_weeks_with_logs(con)
    ev = rows(con, "SELECT ts, kind, org FROM harness.limit_events")
    wk = defaultdict(Counter)
    for r in ev:
        wk[week_of(r["ts"][:10])][r["kind"]] += 1
    stops = limit_stops(con)
    lim_h = defaultdict(float)
    for g in segments(con):
        if g["kind"] == "limited":
            lim_h[g["week"]] += g["minutes"] / 60
    bins = Counter()
    for s in stops:
        m = s["minutes"]
        for name, lo, hi in STOP_BINS:
            if (m is None and hi is None) or (m is not None and m >= lo and (hi is None or m < hi)):
                bins[name] += 1
                break
    stop_wk = Counter(s["week"] for s in stops)
    finite = [s["minutes"] for s in stops if s["minutes"] is not None and s["minutes"] <= CLOSED_GAP_MIN]
    orgs = {}
    for r in rows(con, "SELECT org, MIN(first_ts) f, MAX(last_ts) l, COUNT(*) n FROM harness.sessions GROUP BY org"):
        orgs[r["org"] or "default"] = (r["f"][:10], r["l"][:10], r["n"])
    by_kind = Counter(r["kind"] for r in ev)
    first = min(r["ts"] for r in ev)[:10]
    return {"weeks": SESSION_WEEKS,
            "series": {label: [wk[w][k] if w in logged else None for w in SESSION_WEEKS] for k, label in LIMIT_KINDS},
            "hours_limited": [round(lim_h[w], 1) if w in logged else None for w in SESSION_WEEKS],
            "stops_per_week": [stop_wk.get(w, 0) if w in logged else None for w in SESSION_WEEKS],
            "n_events": len(ev), "by_kind": dict(by_kind), "n_stops": len(stops),
            "bins": [n for n, _, _ in STOP_BINS], "bin_counts": [bins[n] for n, _, _ in STOP_BINS],
            "median_stop_min": median(finite), "hours_limited_total": round(sum(lim_h.values())),
            "first_event": first, "orgs": orgs,
            "events_by_org": dict(Counter((r["org"] or "default") for r in ev))}


# ------------------------------------------------------------------ Q owner-wait-length waiting on the owner

def pr_ready_waits(con):
    """Non-bot merged PRs: hours from the last ready_for_review before merge (else creation) to merge."""
    ready = defaultdict(list)
    for r in rows(con, "SELECT repo, number, ts FROM github.pr_timeline WHERE event='ready_for_review'"):
        ready[(r["repo"], r["number"])].append(r["ts"])
    out = []
    for p in rows(con, "SELECT repo, number, created_ts, merged_ts, is_draft FROM github.prs "
                       "WHERE merged_ts IS NOT NULL AND author_is_bot = 0"):
        if not in_scope(p["repo"]):
            continue
        rs = [t for t in ready.get((p["repo"], p["number"]), []) if t <= p["merged_ts"]]
        start = max(rs) if rs else p["created_ts"]
        h = (parse_ts(p["merged_ts"]) - parse_ts(start)).total_seconds() / 3600
        out.append({"repo": p["repo"], "number": p["number"], "ready": parse_ts(start), "hours": max(0.0, h),
                    "had_ready": bool(rs), "week": week_of(p["merged_ts"][:10])})
    return out


def ask_waits(con):
    """Minutes from each ask to the next owner turn in its session (up to the 8-hour rule)."""
    turns = session_turns(con)
    out = []
    for r in rows(con, "SELECT session_id_hash s, ts FROM harness.asks WHERE ts IS NOT NULL"):
        t0 = parse_ts(r["ts"])
        if not observed(t0.date()):
            continue
        nxt = next((t[0] for t in turns.get(r["s"], []) if t[0] > t0 and t[1] == "user" and not t[2]), None)
        if nxt is None:
            continue
        m = (nxt - t0).total_seconds() / 60
        if m <= CLOSED_GAP_MIN:
            out.append({"week": week_of(t0.date().isoformat()), "minutes": m})
    return out


def q_owner_wait_length_waits(con):
    logged = session_weeks_with_logs(con)
    pw = pr_ready_waits(con)
    by_w = defaultdict(list)
    for p in pw:
        by_w[p["week"]].append(p["hours"])
    aw = ask_waits(con)
    ask_w = defaultdict(list)
    for a in aw:
        ask_w[a["week"]].append(a["minutes"])
    hours = defaultdict(list)
    for p in pw:
        if p["had_ready"]:
            hours[p["ready"].astimezone(LOCAL).hour // 3].append(p["hours"])
    bands = [f"{h * 3:02d}-{h * 3 + 3:02d}" for h in range(8)]
    recent = [p["hours"] for p in pw if p["week"] >= "2026-W35"]
    early = [p["hours"] for p in pw if p["week"] < "2026-W19"]
    return {"weeks": WEEKS,
            "pr_median_h": [median(by_w[w]) if len(by_w[w]) >= 3 else None for w in WEEKS],
            "pr_p75_h": [pctile(by_w[w], 0.75) if len(by_w[w]) >= 3 else None for w in WEEKS],
            "ask_median_min": [median(ask_w[w]) if w in logged and ask_w[w] else None for w in SESSION_WEEKS],
            "ask_weeks": SESSION_WEEKS, "n_prs": len(pw), "n_ready": sum(p["had_ready"] for p in pw),
            "n_asks": len(aw), "ask_median_all": median([a["minutes"] for a in aw]),
            "ask_p75_all": pctile([a["minutes"] for a in aw], 0.75),
            "pr_median_all": median([p["hours"] for p in pw]),
            "pr_median_recent": median(recent), "pr_median_early": median(early),
            "band_labels": bands, "band_median_h": [median(hours[i]) for i in range(8)],
            "band_n": [len(hours[i]) for i in range(8)],
            "pr_over_24h_recent": share(sum(h > 24 for h in recent), len(recent))}


# ------------------------------------------------------------------ Q concurrent-sessions concurrent sessions

BUCKET_MIN = 5


@lru_cache(maxsize=None)
def active_buckets(con):
    """{bucket_start: (owner sessions active, headless sessions active)} over 5-minute buckets with a turn."""
    skip = headless(con)
    act = defaultdict(lambda: [set(), set()])
    for s, turns in session_turns(con).items():
        for t in turns:
            if not observed(t[0].date()):
                continue
            b = t[0].replace(second=0, microsecond=0)
            b = b - timedelta(minutes=b.minute % BUCKET_MIN)
            act[b][1 if s in skip else 0].add(s)
    return {b: (len(v[0]), len(v[1])) for b, v in act.items()}


def subagent_buckets(con):
    out = Counter()
    for r in rows(con, "SELECT ts_start, ts_end FROM harness.subagent_runs WHERE ts_start IS NOT NULL AND ts_end IS NOT NULL"):
        a, b = parse_ts(r["ts_start"]), parse_ts(r["ts_end"])
        if (b - a).total_seconds() > CLOSED_GAP_MIN * 60 or b < a:
            continue
        t = a.replace(second=0, microsecond=0)
        t = t - timedelta(minutes=t.minute % BUCKET_MIN)
        while t <= b:
            out[t] += 1
            t += timedelta(minutes=BUCKET_MIN)
    return out


def q_concurrent_sessions_concurrency(con):
    logged = session_weeks_with_logs(con)
    ab = active_buckets(con)
    sub = subagent_buckets(con)
    wk = defaultdict(list)
    wk_all = defaultdict(list)
    wk_sub = defaultdict(list)
    for b, (o, h) in ab.items():
        w = week_of(b.date().isoformat())
        if o:
            wk[w].append(o)
        wk_all[w].append(o + h)
        wk_sub[w].append(sub.get(b, 0))
    owner = [n for b, (n, _) in ab.items() if n]
    hour = defaultdict(list)
    for b, (o, _) in ab.items():
        if o:
            hour[b.astimezone(LOCAL).hour].append(o)
    top = Counter(owner)
    return {"weeks": SESSION_WEEKS,
            "median": [median(wk[w]) if w in logged and wk[w] else None for w in SESSION_WEEKS],
            "p90": [pctile(wk[w], 0.9) if w in logged and wk[w] else None for w in SESSION_WEEKS],
            "max": [max(wk[w]) if w in logged and wk[w] else None for w in SESSION_WEEKS],
            "with_headless_max": [max(wk_all[w]) if w in logged and wk_all[w] else None for w in SESSION_WEEKS],
            "subagents_p90": [pctile([x for x in wk_sub[w] if x], 0.9) if w in logged and any(wk_sub[w]) else None
                              for w in SESSION_WEEKS],
            "ceiling": [CEILING if w in logged else None for w in SESSION_WEEKS],
            "n_buckets": len(owner), "median_all": median(owner), "p90_all": pctile(owner, 0.9), "max_all": max(owner),
            "share_at_ceiling": share(sum(n >= CEILING for n in owner), len(owner)),
            "share_single": share(sum(n == 1 for n in owner), len(owner)),
            "hist": [top.get(k, 0) for k in range(1, 9)] + [sum(v for k, v in top.items() if k > 8)],
            "hour_mean": [round(statistics.mean(hour[h]), 2) if hour[h] else 0 for h in range(24)],
            "hours_at_ceiling": round(sum(n >= CEILING for n in owner) * BUCKET_MIN / 60, 1),
            "n_headless": len(headless(con))}


# ------------------------------------------------------------------ Q work-in-progress work in progress

def week_end(w):
    return datetime.combine(date.fromisocalendar(int(w[:4]), int(w[6:]), 7), datetime.max.time()).replace(tzinfo=timezone.utc)


@lru_cache(maxsize=None)
def items(con):
    out = []
    for r in rows(con, "SELECT repo, item_id, type, status, created_ts, updated_ts, ready_ts, done_ts, day, "
                       "raw_frontmatter_json FROM plans.plan_items WHERE type != 'goal'"):
        if not in_scope(r["repo"]) or not (r["created_ts"] or r["day"]):
            continue
        c = parse_ts(r["created_ts"] if r["created_ts"] and len(r["created_ts"]) > 10 else (r["created_ts"] or r["day"]) + "T12:00:00+00:00")
        end = None
        if (r["status"] or "") in TERMINAL_ITEM:
            e = r["done_ts"] or r["updated_ts"]
            end = parse_ts(e if len(e) > 10 else e + "T12:00:00+00:00") if e else c
        out.append({**r, "created": c, "end": end})
    return tuple(out)


def q_work_in_progress_wip(con):
    prs = [p for p in rows(con, "SELECT repo, author_is_bot, created_ts, merged_ts, closed_ts FROM github.prs")
           if in_scope(p["repo"])]
    it = items(con)
    first_item = min(i["created"] for i in it)
    open_pr = {"Apps": [], "Allied repos": [], "Dependabot": []}
    open_items = []
    for w in WEEKS:
        t = week_end(min(w, week_of(DATA_END)))
        t = min(t, parse_ts(DATA_END + "T23:59:59+00:00"))
        cnt = Counter()
        for p in prs:
            if parse_ts(p["created_ts"]) > t:
                continue
            end = p["merged_ts"] or p["closed_ts"]
            if end and parse_ts(end) <= t:
                continue
            k = "Dependabot" if p["author_is_bot"] else "Apps" if category_of(p["repo"]) in APPS else "Allied repos"
            cnt[k] += 1
        for k in open_pr:
            open_pr[k].append(cnt[k])
        if t < first_item:
            open_items.append(None)
        else:
            open_items.append(sum(1 for i in it if i["created"] <= t and (i["end"] is None or i["end"] > t)))
    now = defaultdict(Counter)
    for i in it:
        if i["end"] is None:
            st = i["status"] or "unknown"
            st = {"todo": "new", "accepted": "ready", "queued": "ready", "committed": "in progress",
                  "active": "in progress", "planning": "planning"}.get(st, st)
            now[i["repo"]][st if st in ("new", "planning", "ready", "in progress") else "other"] += 1
    repos = sorted(now, key=lambda r: -sum(now[r].values()))[:10]
    statuses = ["new", "planning", "ready", "in progress", "other"]
    stale = [i for i in it if i["end"] is None and i["created"] < parse_ts("2026-08-25T00:00:00+00:00")]
    return {"weeks": WEEKS, "open_pr": open_pr, "open_items": open_items,
            "repos": repos, "by_status": {s: [now[r][s] for r in repos] for s in statuses},
            "open_items_now": sum(sum(v.values()) for v in now.values()),
            "open_prs_now": {k: v[-1] for k, v in open_pr.items()}, "stale_open_items": len(stale),
            "peak_items": max(x for x in open_items if x is not None),
            "peak_items_week": WEEKS[open_items.index(max(x for x in open_items if x is not None))]}


# ------------------------------------------------------------------ Q pr-vs-item-lead-time cycle time

def q_pr_vs_item_lead_time_cycle(con):
    """PR hours from opened to merged (non-bot); work-item days from written to done.

    Item dates carry the day only, so an item written and done on the same day reads 0 days."""
    pr = defaultdict(list)
    for p in rows(con, "SELECT repo, merged_ts, hours_to_merge FROM github.prs WHERE merged_ts IS NOT NULL "
                       "AND author_is_bot = 0 AND hours_to_merge IS NOT NULL"):
        if in_scope(p["repo"]):
            pr[week_of(p["merged_ts"][:10])].append(p["hours_to_merge"])
    it = [i for i in items(con) if i["end"] is not None and i["status"] in SHIPPED_ITEM]
    days = defaultdict(list)
    for i in it:
        d = (i["end"].date() - i["created"].date()).days
        if d >= 0:
            days[week_of(i["end"].date().isoformat())].append(d)
    all_pr = [h for v in pr.values() for h in v]
    all_d = [x for v in days.values() for x in v]
    ms = lambda d, w, n=3: median(d[w]) if len(d[w]) >= n else None
    return {"weeks": WEEKS, "pr_median": [ms(pr, w) for w in WEEKS],
            "pr_p75": [pctile(pr[w], 0.75) if len(pr[w]) >= 3 else None for w in WEEKS],
            "item_mean_days": [round(statistics.mean(days[w]), 1) if w in ITEM_WEEKS and len(days[w]) >= 5 else None for w in WEEKS],
            "item_same_day": [share(sum(x == 0 for x in days[w]), len(days[w]), 5) if w in ITEM_WEEKS else None for w in WEEKS],
            "pr_median_all": median(all_pr), "pr_p75_all": pctile(all_pr, 0.75), "n_pr": len(all_pr),
            "n_item": len(all_d), "item_median_days": median(all_d), "item_mean_all": round(statistics.mean(all_d), 1),
            "item_same_day_all": share(sum(x == 0 for x in all_d), len(all_d)),
            "item_over_7d": share(sum(x > 7 for x in all_d), len(all_d)),
            "pr_median_h1": median([h for w, v in pr.items() if w < "2026-W27" for h in v]),
            "pr_median_h2": median([h for w, v in pr.items() if w >= "2026-W27" for h in v]),
            "pr_p75_h1": pctile([h for w, v in pr.items() if w < "2026-W27" for h in v], 0.75),
            "pr_p75_h2": pctile([h for w, v in pr.items() if w >= "2026-W27" for h in v], 0.75),
            "pr_hist_bins": ["< 15 min", "15-60 min", "1-4 h", "4-24 h", "1-7 days", "> 7 days"],
            "pr_hist": [sum(lo <= h < hi for h in all_pr) for lo, hi in
                        ((0, .25), (.25, 1), (1, 4), (4, 24), (24, 168), (168, 1e9))],
            "item_hist_bins": ["same day", "1 day", "2-7 days", "8-30 days", "> 30 days"],
            "item_hist": [sum(lo <= x <= hi for x in all_d) for lo, hi in ((0, 0), (1, 1), (2, 7), (8, 30), (31, 10 ** 6))]}


# ------------------------------------------------------------------ Q work-while-away work while the owner is away

@lru_cache(maxsize=None)
def owner_prompt_times(con):
    ts = [parse_ts(r["ts"]) for r in rows(con, "SELECT ts, text_redacted FROM harness.prompts WHERE ts IS NOT NULL")
          if not AUTOMATED_RE.match(r["text_redacted"] or "")]
    return tuple(sorted(ts))


def minutes_since_prompt(prompts, t):
    import bisect
    i = bisect.bisect_right(prompts, t)
    return (t - prompts[i - 1]).total_seconds() / 60 if i else None


def q_work_while_away_unattended(con):
    prompts = owner_prompt_times(con)
    logged = session_weeks_with_logs(con)
    work = defaultdict(lambda: [0.0, 0.0])
    alt = {15: defaultdict(lambda: [0.0, 0.0]), 60: defaultdict(lambda: [0.0, 0.0])}
    for g in segments(con):
        if g["kind"] != "working":
            continue
        m = minutes_since_prompt(prompts, g["start"])
        away = m is None or m > AWAY_AFTER_MIN
        work[g["week"]][0] += g["minutes"]
        work[g["week"]][1] += g["minutes"] if away else 0
        for th, d in alt.items():
            d[g["week"]][0] += g["minutes"]
            d[g["week"]][1] += g["minutes"] if (m is None or m > th) else 0
    merges = defaultdict(lambda: [0, 0])
    night = defaultdict(lambda: [0, 0])
    first_prompt_month = prompts[0].date().isoformat()
    for p in rows(con, "SELECT repo, merged_ts FROM github.prs WHERE merged_ts IS NOT NULL AND author_is_bot = 0"):
        if not in_scope(p["repo"]):
            continue
        t = parse_ts(p["merged_ts"])
        m = minutes_since_prompt(prompts, t)
        w = week_of(p["merged_ts"][:10])
        merges[w][0] += 1
        merges[w][1] += 1 if (m is None or m > AWAY_AFTER_MIN) else 0
        goals_on = p["merged_ts"][:10] >= "2026-08-28"
        night[goals_on][0] += 1
    hour_before, hour_after = Counter(), Counter()
    for p in rows(con, "SELECT repo, merged_ts FROM github.prs WHERE merged_ts IS NOT NULL AND author_is_bot = 0"):
        if in_scope(p["repo"]):
            h = parse_ts(p["merged_ts"]).astimezone(LOCAL).hour
            (hour_after if p["merged_ts"][:10] >= "2026-08-28" else hour_before)[h] += 1
    tw = [work[w] for w in work]
    tot = sum(x[0] for x in tw)
    return {"weeks": WEEKS,
            "merge_share": [share(merges[w][1], merges[w][0], 5) for w in WEEKS],
            "work_share": [share(work[w][1], work[w][0]) if w in logged and w in work else None for w in WEEKS],
            "work_share_all": share(sum(x[1] for x in tw), tot),
            "work_share_15": share(sum(v[1] for v in alt[15].values()), sum(v[0] for v in alt[15].values())),
            "work_share_60": share(sum(v[1] for v in alt[60].values()), sum(v[0] for v in alt[60].values())),
            "merge_share_by_period": {
                "Jan-Apr": share(sum(merges[w][1] for w in WEEKS if w < "2026-W19"), sum(merges[w][0] for w in WEEKS if w < "2026-W19")),
                "May-Jul": share(sum(merges[w][1] for w in WEEKS if "2026-W19" <= w < "2026-W31"), sum(merges[w][0] for w in WEEKS if "2026-W19" <= w < "2026-W31")),
                "Aug-Sep": share(sum(merges[w][1] for w in WEEKS if w >= "2026-W31"), sum(merges[w][0] for w in WEEKS if w >= "2026-W31"))},
            "hour_before": [hour_before[h] / max(1, sum(hour_before.values())) for h in range(24)],
            "hour_after": [hour_after[h] / max(1, sum(hour_after.values())) for h in range(24)],
            "n_before": sum(hour_before.values()), "n_after": sum(hour_after.values()),
            "first_prompt": first_prompt_month, "n_prompts": len(prompts)}


# ------------------------------------------------------------------ Q unshipped-work-share yield and session-level scrap

def q_unshipped_work_share_yield(con):
    pr = defaultdict(lambda: [0, 0])
    bot = defaultdict(lambda: [0, 0])
    for p in rows(con, "SELECT repo, author_is_bot, state, merged_ts, closed_ts FROM github.prs WHERE state != 'OPEN'"):
        if not in_scope(p["repo"]):
            continue
        end = p["merged_ts"] or p["closed_ts"]
        if not end:
            continue
        d = bot if p["author_is_bot"] else pr
        w = week_of(end[:10])
        d[w][0] += 1
        d[w][1] += 1 if p["merged_ts"] else 0
    it = defaultdict(lambda: [0, 0])
    ended = Counter()
    for i in items(con):
        if i["end"] is None:
            continue
        w = week_of(i["end"].date().isoformat())
        it[w][0] += 1
        it[w][1] += 1 if i["status"] in SHIPPED_ITEM else 0
        ended[i["status"]] += 1
    reverts = Counter()
    n_rev = 0
    for c in rows(con, "SELECT repo, day, subject FROM git.commits WHERE is_merge = 0"):
        if in_scope(c["repo"]) and REVERT_RE.match(c["subject"] or ""):
            reverts[week_of(c["day"])] += 1
            n_rev += 1
    # session level: does the session link to a merged PR?
    merged = rows(con, "SELECT repo, number, head_ref FROM github.prs WHERE merged_ts IS NOT NULL")
    merged_nums = {(repo_name(p["repo"]), p["number"]) for p in merged}
    merged_refs = {p["head_ref"] for p in merged if p["head_ref"]}
    logged = session_weeks_with_logs(con)
    sw = defaultdict(lambda: {"n": 0, "usd": 0.0, "none_n": 0, "none_usd": 0.0, "branch_usd": 0.0, "main_usd": 0.0,
                              "review_n": 0, "review_usd": 0.0})
    skip = headless(con)
    for s in sessions(con).values():
        if s["week"] < SESSIONS_FROM_WEEK:
            continue
        links = json.loads(s["pr_links"] or "[]")
        branches = [b for b in json.loads(s["git_branches"] or "[]") if b not in ("main", "master", "HEAD")]
        hit = any((repo_name(l.split("/", 1)[-1].split("#")[0]), int(l.split("#")[1])) in merged_nums
                  for l in links if "#" in l and l.split("#")[1].isdigit())
        hit = hit or any(b in merged_refs for b in branches)
        d = sw[s["week"]]
        usd = s["cost_usd"] or 0
        if s["session_id_hash"] in skip:
            d["review_n"] += 1
            d["review_usd"] += usd
            continue
        d["n"] += 1
        d["usd"] += usd
        if not hit:
            d["none_n"] += 1
            d["none_usd"] += usd
            d["branch_usd" if branches else "main_usd"] += usd
    T = {k: sum(v[k] for v in sw.values()) for k in ("n", "usd", "none_n", "none_usd", "branch_usd", "main_usd", "review_n", "review_usd")}
    return {"weeks": WEEKS,
            "pr_yield": [share(pr[w][1], pr[w][0], 5) for w in WEEKS],
            "bot_yield": [share(bot[w][1], bot[w][0], 5) for w in WEEKS],
            "item_yield": [share(it[w][1], it[w][0], 5) if w in ITEM_WEEKS else None for w in WEEKS],
            "reverts": [reverts.get(w, 0) for w in WEEKS], "n_reverts": n_rev,
            "pr_totals": [sum(v[1] for v in pr.values()), sum(v[0] for v in pr.values())],
            "bot_totals": [sum(v[1] for v in bot.values()), sum(v[0] for v in bot.values())],
            "item_totals": [sum(v[1] for v in it.values()), sum(v[0] for v in it.values())],
            "items_ended": dict(ended),
            "session_weeks": SESSION_WEEKS,
            "scrap_usd_share": [share(sw[w]["none_usd"], sw[w]["usd"]) if w in logged else None for w in SESSION_WEEKS],
            "scrap_n_share": [share(sw[w]["none_n"], sw[w]["n"]) if w in logged else None for w in SESSION_WEEKS],
            "scrap_branch_share": [share(sw[w]["branch_usd"], sw[w]["usd"]) if w in logged else None for w in SESSION_WEEKS],
            "scrap_main_share": [share(sw[w]["main_usd"], sw[w]["usd"]) if w in logged else None for w in SESSION_WEEKS],
            "scrap_totals": {k: round(v) for k, v in T.items()}}


# ------------------------------------------------------------------ Q right-first-time first-pass yield

BOOKKEEPING_RE = re.compile(r"(^|/)(\.plans/|PLAN\.md$|CHANGELOG|package-lock\.json$|pnpm-lock\.yaml$|uv\.lock$|"
                            r"go\.sum$|CONSISTENCY\.md$|HERO\.md$)")


@lru_cache(maxsize=None)
def fix_followups(con):
    """{(repo, main_sha): days to the first later fix aimed at it, or None}.

    A later commit on main is a fix aimed at an earlier one when (a) it lands within 7 days,
    (b) one of its change sets is labelled `fix` in the shared detectors.cs_worktype, and
    (c) at least half of its files (bookkeeping files such as .plans/ and lockfiles left out)
    were touched by the earlier commit. D5's raw signal (any later commit on half the same
    files) also counts planned iteration, so it is reported beside this one in the notes."""
    fix_units = set()
    for r in rows(con, "SELECT repo, unit_kind, unit_id FROM detectors.cs_worktype WHERE work_type = 'fix'"):
        fix_units.add((r["repo"], r["unit_kind"], r["unit_id"]))
    unit_of = {(r["repo"], r["main_sha"]): (r["repo"], r["unit_kind"], r["unit_id"])
               for r in rows(con, "SELECT repo, unit_kind, unit_id, main_sha FROM detectors.cs_units")}
    files = defaultdict(set)
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        if not BOOKKEEPING_RE.search(r["path"]):
            files[(r["repo"], r["sha"])].add(r["path"])
    by_repo = defaultdict(list)
    for c in rows(con, "SELECT repo, sha, committed_ts, is_bot FROM git.commits WHERE is_merge = 0 ORDER BY committed_ts"):
        if in_scope(c["repo"]) and c["committed_ts"]:
            by_repo[c["repo"]].append((parse_ts(c["committed_ts"]), c["sha"], bool(c["is_bot"])))
    out = {}
    for repo, cs in by_repo.items():
        for i, (t, sha, bot) in enumerate(cs):
            mine = files.get((repo, sha), set())
            hit = None
            for t2, sha2, bot2 in cs[i + 1:]:
                if (t2 - t).days >= 7:
                    break
                if bot2 or unit_of.get((repo, sha2)) not in fix_units:
                    continue
                theirs = files.get((repo, sha2), set())
                if mine and theirs and len(theirs & mine) * 2 >= len(theirs):
                    hit = round((t2 - t).total_seconds() / 86400, 2)
                    break
            out[(repo, sha)] = hit
    return out


def q_right_first_time_first_pass(con):
    fx = fix_followups(con)
    d5 = {(r["repo"], r["number"]): r["followup_within_7d_days"] for r in
          rows(con, "SELECT repo, number, followup_within_7d_days FROM detectors.followups")}
    main_sha = {(r["repo"], r["unit_kind"], r["unit_id"]): r["main_sha"]
                for r in rows(con, "SELECT repo, unit_kind, unit_id, main_sha FROM detectors.cs_units")}
    cutoff = (date.fromisoformat(DATA_END) - timedelta(days=7)).isoformat()
    cs = []
    for f in changeset_facts(con):
        if f["dependabot"] or f["day"] > cutoff:
            continue
        sha = main_sha.get((f["repo"], f["unit_kind"], f["unit_id"]))
        if (f["repo"], sha) in fx:
            cs.append((f, fx[(f["repo"], sha)] is None))
    wk = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    stage = defaultdict(lambda: [0, 0])
    repo = defaultdict(lambda: [0, 0])
    d5n = [0, 0]
    for f, ok in cs:
        k = "Apps" if f["category"] in APPS else "Allied repos"
        for kk in (k, "All"):
            wk[kk][f["week"]][0] += 1
            wk[kk][f["week"]][1] += ok
        stage[f["stage"]][0] += 1
        stage[f["stage"]][1] += ok
        repo[f["repo"]][0] += 1
        repo[f["repo"]][1] += ok
        if f["pr"] is not None and (f["repo"], f["pr"]) in d5:
            d5n[0] += 1
            d5n[1] += d5[(f["repo"], f["pr"])] is None
    series = {k: [share(wk[k][w][1], wk[k][w][0], 10) for w in WEEKS] for k in ("Apps", "Allied repos")}
    n = len(cs)
    ok = sum(o for _, o in cs)
    examples = []
    for (r, sha), days in sorted(fx.items(), key=lambda kv: kv[0]):
        if days is not None and len(examples) < 400:
            examples.append((r, sha, days))
    return {"weeks": WEEKS, "series": series, "all": [share(wk["All"][w][1], wk["All"][w][0], 10) for w in WEEKS],
            "stages": STAGES, "by_stage": [share(stage[s][1], stage[s][0], 20) for s in STAGES],
            "stage_n": [stage[s][0] for s in STAGES], "n": n, "first_pass": share(ok, n), "cutoff": cutoff,
            "d5_first_pass": share(d5n[1], d5n[0]), "d5_n": d5n[0],
            "by_repo": {r: share(v[1], v[0], 20) for r, v in repo.items()},
            "n_fixed_commits": sum(1 for v in fx.values() if v is not None), "n_commits": len(fx)}


# ------------------------------------------------------------------ Q wasted-session-effort wasted effort

def q_wasted_session_effort_waste(con):
    logged = session_weeks_with_logs(con)
    wk = defaultdict(lambda: [0, 0, 0])
    tool = defaultdict(lambda: [0, 0, 0])
    sub = {True: [0, 0], False: [0, 0]}
    skip = headless(con)
    for r in rows(con, "SELECT session_id_hash s, ts, tool, subagent_type, is_error, was_rejected FROM harness.tool_calls "
                       "WHERE ts IS NOT NULL"):
        w = week_of(r["ts"][:10])
        if w < SESSIONS_FROM_WEEK or r["s"] in skip:
            continue
        wk[w][0] += 1
        wk[w][1] += r["is_error"] or 0
        wk[w][2] += r["was_rejected"] or 0
        tool[r["tool"]][0] += 1
        tool[r["tool"]][1] += r["is_error"] or 0
        tool[r["tool"]][2] += r["was_rejected"] or 0
    top = sorted(tool, key=lambda t: -tool[t][0])[:9]
    stops = limit_stops(con)
    ended = {s["s"] for s in stops if (s["minutes"] is None or s["minutes"] > CLOSED_GAP_MIN) and s["week"] >= SESSIONS_FROM_WEEK}
    ses = sessions(con)
    cut_usd = sum(ses[s]["cost_usd"] or 0 for s in ended if s in ses)
    T = [sum(v[i] for v in wk.values()) for i in range(3)]
    return {"weeks": SESSION_WEEKS,
            "error_share": [share(wk[w][1], wk[w][0], 50) if w in logged else None for w in SESSION_WEEKS],
            "reject_share": [share(wk[w][2], wk[w][0], 50) if w in logged else None for w in SESSION_WEEKS],
            "tools": top, "tool_n": [tool[t][0] for t in top],
            "tool_error": [share(tool[t][1], tool[t][0]) for t in top],
            "tool_reject": [share(tool[t][2], tool[t][0]) for t in top],
            "totals": T, "error_all": share(T[1], T[0]), "reject_all": share(T[2], T[0]),
            "limit_ended_sessions": len(ended), "limit_ended_usd": round(cut_usd),
            "total_usd": round(sum((s["cost_usd"] or 0) for s in ses.values() if s["week"] >= SESSIONS_FROM_WEEK))}


# ------------------------------------------------------------------ Q output-vs-agent-hours output per working hour

def q_output_vs_agent_hours_rate(con):
    logged = session_weeks_with_logs(con)
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    sets = Counter(f["week"] for f in cs)
    sets_repo = Counter(f["repo"] for f in cs if f["week"] in logged)
    work = defaultdict(float)
    work_repo = defaultdict(float)
    ses = sessions(con)
    for g in segments(con):
        if g["kind"] == "working":
            work[g["week"]] += g["minutes"] / 60
            work_repo[ses.get(g["s"], {}).get("repo", "")] += g["minutes"] / 60
    conc = q_concurrent_sessions_concurrency(con)
    full = [w for w in SESSION_WEEKS if w in logged and work[w] >= 5]
    rate = {w: sets[w] / work[w] for w in full}
    roll = {}
    for i, w in enumerate(SESSION_WEEKS):
        pair = [x for x in SESSION_WEEKS[max(0, i - 1):i + 1] if x in rate]
        if w in rate and pair:
            roll[w] = sum(sets[x] for x in pair) / sum(work[x] for x in pair)
    repos = [r for r in sorted(work_repo, key=lambda r: -work_repo[r]) if in_scope(r) and work_repo[r] >= 3][:10]
    return {"weeks": SESSION_WEEKS, "rate": [round(rate[w], 2) if w in rate else None for w in SESSION_WEEKS],
            "rolling": [round(roll[w], 2) if w in roll else None for w in SESSION_WEEKS],
            "sets": [sets.get(w, 0) if w in logged else None for w in SESSION_WEEKS],
            "work_h": [round(work[w], 1) if w in logged else None for w in SESSION_WEEKS],
            "conc_median": conc["median"], "conc_p90": conc["p90"],
            "rate_all": round(sum(sets[w] for w in full) / sum(work[w] for w in full), 2),
            "ref_rate": round(max(rate.values()), 2), "ref_week": max(rate, key=rate.get),
            "repos": repos, "repo_rate": [round(sets_repo[r] / work_repo[r], 2) for r in repos],
            "repo_hours": [round(work_repo[r]) for r in repos], "repo_sets": [sets_repo[r] for r in repos]}


# ------------------------------------------------------------------ Q oee-score OEE (draft)

def q_oee_score_oee(con):
    clock = q_session_clock_clock(con)
    rate = q_output_vs_agent_hours_rate(con)
    fp = q_right_first_time_first_pass(con)
    idx = {w: i for i, w in enumerate(SESSION_WEEKS)}
    A, A_idle, P, Q, O, O_idle = [], [], [], [], [], []
    ref = rate["ref_rate"]
    fp_all = dict(zip(WEEKS, fp["all"]))
    for w in SESSION_WEEKS:
        i = idx[w]
        s = {k: clock["series"][lab][i] for k, lab in KINDS}
        if s["working"] is None or not s["working"] or s["working"] < 5:
            A.append(None), A_idle.append(None), P.append(None), Q.append(None), O.append(None), O_idle.append(None)
            continue
        a = s["working"] / (s["working"] + s["waiting_human"] + s["limited"])
        ai = s["working"] / (s["working"] + s["waiting_human"] + s["limited"] + s["away"])
        p = min(1.0, rate["rate"][i] / ref) if rate["rate"][i] is not None else None
        q = fp_all.get(w)
        A.append(round(a, 3)), A_idle.append(round(ai, 3)), P.append(round(p, 3) if p is not None else None)
        Q.append(q)
        O.append(round(a * p * q, 3) if None not in (p, q) else None)
        O_idle.append(round(ai * p * q, 3) if None not in (p, q) else None)
    tot = clock["totals"]
    a_all = tot["working"] / (tot["working"] + tot["waiting_human"] + tot["limited"])
    ai_all = tot["working"] / sum(tot.values())
    p_all = rate["rate_all"] / ref
    q_all = fp["first_pass"]
    return {"weeks": SESSION_WEEKS, "A": A, "A_idle": A_idle, "P": P, "Q": Q, "OEE": O, "OEE_idle": O_idle,
            "a_all": round(a_all, 3), "ai_all": round(ai_all, 3), "p_all": round(p_all, 3), "q_all": q_all,
            "oee_all": round(a_all * p_all * q_all, 3), "oee_idle_all": round(ai_all * p_all * q_all, 3),
            "ref_rate": ref, "ref_week": rate["ref_week"]}


# ------------------------------------------------------------------ Q change-set-traceability traceability

def q_change_set_traceability_trace(con):
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    fu = {(r["repo"], r["number"]) for r in rows(con, "SELECT repo, number FROM detectors.followups")}
    prs = {(r["repo"], r["number"]): r for r in rows(con, "SELECT repo, number, head_ref, created_ts, merged_ts FROM github.prs")}
    linked_pr, linked_ref = set(), defaultdict(set)
    conf = Counter()
    for s in sessions(con).values():
        for l in json.loads(s["pr_links"] or "[]"):
            if "#" in l and l.split("#")[1].isdigit():
                linked_pr.add((repo_name(l.split("/", 1)[-1].split("#")[0]), int(l.split("#")[1])))
        for b in json.loads(s["git_branches"] or "[]"):
            if b not in ("main", "master", "HEAD"):
                linked_ref[s["repo"]].add(b)
    for r in rows(con, "SELECT attribution_confidence c, SUM(cost_usd) usd FROM detectors.session_spend GROUP BY 1"):
        conf[r["c"]] = round(r["usd"] or 0)
    logged = session_weeks_with_logs(con)
    wk = defaultdict(lambda: [0, 0, 0, 0])
    for f in cs:
        k = (f["repo"], f["pr"]) if f["pr"] is not None else None
        p = prs.get(k) if k else None
        timed = bool(p and p["created_ts"] and p["merged_ts"])
        defect = bool(k and k in fu)
        cost = bool(p and (k in linked_pr or (p["head_ref"] and p["head_ref"] in linked_ref.get(f["repo"], set()))))
        d = wk[f["week"]]
        d[0] += 1
        d[1] += timed
        d[2] += defect
        d[3] += cost
    s_weeks = [w for w in WEEKS if w in logged]
    T = [sum(wk[w][i] for w in WEEKS) for i in range(4)]
    Ts = [sum(wk[w][i] for w in s_weeks) for i in range(4)]
    return {"weeks": WEEKS,
            "series": {"Wall time (PR opened, merged)": [share(wk[w][1], wk[w][0], 5) for w in WEEKS],
                       "Follow-up check (D5)": [share(wk[w][2], wk[w][0], 5) for w in WEEKS],
                       "Cost (a session names its PR or branch)": [share(wk[w][3], wk[w][0], 5) if w in logged else None
                                                                   for w in WEEKS]},
            "n": T[0], "timed": share(T[1], T[0]), "defect": share(T[2], T[0]),
            "since_logs": {"n": Ts[0], "timed": share(Ts[1], Ts[0]), "defect": share(Ts[2], Ts[0]), "cost": share(Ts[3], Ts[0])},
            "attribution_usd": dict(conf)}


def all_data(con=None):
    con = con or connect()
    return {"q_change_set_traceability": q_change_set_traceability_trace(con), "q_session_clock": q_session_clock_clock(con), "q_usage_limit_stops": q_usage_limit_stops_limits(con),
            "q_owner_wait_length": q_owner_wait_length_waits(con), "q_concurrent_sessions": q_concurrent_sessions_concurrency(con), "q_work_in_progress": q_work_in_progress_wip(con),
            "q_pr_vs_item_lead_time": q_pr_vs_item_lead_time_cycle(con), "q_work_while_away": q_work_while_away_unattended(con), "q_unshipped_work_share": q_unshipped_work_share_yield(con),
            "q_right_first_time": q_right_first_time_first_pass(con), "q_wasted_session_effort": q_wasted_session_effort_waste(con), "q_output_vs_agent_hours": q_output_vs_agent_hours_rate(con),
            "q_oee_score": q_oee_score_oee(con)}


if __name__ == "__main__":
    d = all_data()
    for k, v in d.items():
        print("=" * 20, k)
        for kk, vv in v.items():
            if kk == "weeks":
                continue
            s = json.dumps(vv, default=str)
            print(f"  {kk}: {s[:600]}")
