"""Human in the loop series: human in the loop. One function per question, each returning what its slides plot.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/owner/data.py   # prints every answer's numbers

Weeks run from 1 Jan 2026 (ISO W01) to W39. Owner-local times use this machine's zone (the
owner's, PDT). Out-of-scope repos (the deleted -design repos) are dropped everywhere.
"""
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
from record import STAGES, adoption, changeset_facts, rows, stage_of, week_of  # noqa: E402
from links import set_item_links  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE  # noqa: E402
import actors  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
# No Claude Code sessions were logged from 10 to 24 Aug (W33-W34; the owner confirmed an outage). Session-derived
# series (sessions, turns, tool calls, asks) show those weeks as "data not available", never zero, and leave them
# out of averages. Typed prompts come from the prompt history, which continues through the gap.
NA_WEEKS = ("2026-W33", "2026-W34")
SESSION_WEEKS = [w for w in WEEKS if w >= "2026-W33"]
CLOSED_GAP_S = 8 * 3600
OWNER = actors.OWNER

# Changes to where the owner's gate sits, from wayfare-skills' history.
GATE_EVENTS = [
    ("2026-03-29", "Claude auto-approve (4b6358d)"),
    ("2026-07-18", "Approve only on a write-access comment"),
    ("2026-07-22", "Ready-mark gate (#41)"),
    ("2026-09-18", "Goal runs after its gate (#95)"),
]
PERMISSION_EVENTS = [
    ("2026-08-14", "Auto mode default (Claude Code)"),
    ("2026-09-25", "Goal permissions line (#124)"),
]


def t(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def local(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()


def med(v):
    return round(statistics.median(v), 1) if v else None


def share(a, b):
    return round(a / b, 3) if b else None


def in_scope(repo):
    return repo and repo not in OUT_OF_SCOPE


def series(counter_by_cat, cats, weeks=WEEKS, na=False):
    """{cat: [value per week]}; with na, the weeks with no session data are None rather than 0."""
    return {c: [None if na and w in NA_WEEKS else round(counter_by_cat[c].get(w, 0), 2) for w in weeks] for c in cats}


def blank_na(values, weeks=WEEKS):
    return [None if w in NA_WEEKS else v for v, w in zip(values, weeks)]


@lru_cache(maxsize=None)
def work_sets(con):
    """Change sets that are work: Dependabot excluded."""
    return [f for f in changeset_facts(con) if not f["dependabot"]]


@lru_cache(maxsize=None)
def prompts(con):
    out = []
    for r in rows(con, "SELECT ts, repo, text_redacted txt, is_slash_command slash, command FROM harness.prompts"):
        if not in_scope(r["repo"]) or r["ts"] < "2026-01-01":
            continue
        r["day"] = r["ts"][:10]
        r["week"] = week_of(r["day"])
        out.append(r)
    return out


@lru_cache(maxsize=None)
def session_repo(con):
    return {r["session_id_hash"]: r["repo"] for r in rows(con, "SELECT session_id_hash, repo FROM harness.sessions")}


# ---------------------------------------------------------------- asks: kind, phase, answer

ASK_LABELS = {"ready": "Approve a plan", "go": "Go: start or continue", "ship": "A PR step: fix, ready, merge",
              "access": "Something only the owner has", "design": "Design choice", "scope": "Scope or priority",
              "clarify": "What did you mean?"}
ASK_KINDS = list(ASK_LABELS.values())
UNLABELLED = "Unlabelled"
PHASES = {"Planning": r"grill|think-it-through|architecture|harden|sync-plan|sync-arch|review-arch|wayfare$|wayfare-skills:wayfare$|recalibrate|init|handoff|"
                      r"audit|sync-fleet|review-fleet",
          "Building": r"build|one-shot|goal|advance|run-task|task-runner",
          "Shipping": r"push|review-pr|respond|ship|reset|drop"}


@lru_cache(maxsize=None)
def haiku_ask_kinds(con):
    """Haiku's label per ask (report/owner/label_asks.py), keyed by the question's content hash."""
    try:
        return {r[0]: r[1] for r in con.execute("SELECT h, kind FROM owner.ask_kind")}
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        print("owner: owner.ask_kind not built (run report/owner/label_asks.py); every ask is Unlabelled", file=sys.stderr)
        return {}


def ask_kind(con, q):
    import hashlib
    k = haiku_ask_kinds(con).get(hashlib.sha256(q.encode()).hexdigest()[:16])
    return ASK_LABELS.get(k, UNLABELLED)


def _pairs(answer):
    return re.findall(r'"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"', answer or "")


@lru_cache(maxsize=None)
def asks(con):
    """Every ask with its repo, kind, phase (skill running), the owner's answer and how long it took."""
    repo_of = session_repo(con)
    turns = defaultdict(list)
    for r in con.execute("SELECT session_id_hash, ts, role, branch FROM harness.turns WHERE is_synthetic = 0 AND ts IS NOT NULL"):
        turns[r[0]].append((t(r[1]), r[2], r[3]))
    for v in turns.values():
        v.sort()
    skills = defaultdict(list)
    for r in con.execute("SELECT session_id_hash, ts, skill_name FROM harness.tool_calls WHERE skill_name IS NOT NULL"):
        skills[r[0]].append((t(r[1]), r[2]))
    for r in con.execute("SELECT session_id_hash, ts, text_redacted FROM harness.turns WHERE role = 'user' "
                         "AND text_redacted LIKE '%<command-name>%'"):
        m = re.search(r"<command-name>/?([^<]+)</command-name>", r[2] or "")
        if m and not re.search(r"^(clear|model|compact|login|status|cost|context|resume|exit)$", m.group(1).strip()):
            skills[r[0]].append((t(r[1]), m.group(1).strip()))
    for v in skills.values():
        v.sort()
    out = []
    for r in rows(con, "SELECT * FROM harness.asks"):
        repo = repo_of.get(r["session_id_hash"])
        if not in_scope(repo):
            continue
        ts = t(r["ts"])
        nxt = next((x for x in turns[r["session_id_hash"]] if x[0] > ts), None)
        wait = nxt[0] - ts if nxt else None
        prev = [x for x in turns[r["session_id_hash"]] if x[0] <= ts]
        branch = prev[-1][2] if prev else None
        sk = [s for s in skills[r["session_id_hash"]] if s[0] <= ts]
        skill = sk[-1][1] if sk else None
        phase = "No skill"
        for p, rx in PHASES.items():
            if skill and re.search(rx, skill):
                phase = p
                break
        opts = json.loads(r["options_json"] or "[]")
        n_q = len([q for q in (r["question_redacted"] or "").split(" | ") if q.strip()])
        rec = [o["label"] for o in opts if re.search(r"recommended", o.get("label") or "", re.I)]
        ans = r["answer_redacted"] or ""
        pairs = _pairs(ans)
        if n_q == 1 and rec:
            a = pairs[0][1] if pairs else ""
            if not pairs:
                took = "Declined or answered in chat"
            elif re.search(r"recommended", a, re.I):
                took = "Took the recommendation"
            elif any(a.strip() == (o["label"] or "").strip() for o in opts):
                took = "Picked another option"
            else:
                took = "Wrote their own answer"
        else:
            took = None
        out.append({"repo": repo, "ts": r["ts"], "day": r["ts"][:10], "week": week_of(r["ts"][:10]),
                    "question": r["question_redacted"] or "", "kind": ask_kind(con, r["question_redacted"] or ""),
                    "n_questions": n_q, "skill": skill, "phase": phase, "branch": branch,
                    "on_default": branch in ("main", "master"),
                    "wait_s": wait if wait is not None and wait <= CLOSED_GAP_S else None,
                    "closed": wait is not None and wait > CLOSED_GAP_S, "has_rec": bool(rec),
                    "took": took, "answer": pairs[0][1] if pairs else ans[:160]})
    return out


# ---------------------------------------------------------------- Q owner-wait-points gates on record

def q_owner_wait_points_gates(con):
    ev = defaultdict(Counter)
    for r in rows(con, "SELECT repo, ready_ts FROM plans.plan_items WHERE ready_ts IS NOT NULL AND type != 'goal'"):
        if in_scope(r["repo"]):
            ev["Ready-marks"][week_of(r["ready_ts"][:10])] += 1
    for a in asks(con):
        ev["Asks"][a["week"]] += 1
    repo_of = session_repo(con)
    for r in rows(con, "SELECT session_id_hash, ts FROM harness.tool_calls WHERE was_rejected = 1"):
        if in_scope(repo_of.get(r["session_id_hash"])):
            ev["Tool-call denials"][week_of(r["ts"][:10])] += 1
    for r in rows(con, "SELECT repo, day, interrupted_count n FROM harness.sessions WHERE interrupted_count > 0"):
        if in_scope(r["repo"]):
            ev["Interrupts"][week_of(r["day"])] += r["n"]
    for r in actors.review_actors(con):
        if r["actor"] == "owner":
            ev["Owner's own GitHub reviews"][week_of(r["submitted_ts"][:10])] += 1
    cats = ["Ready-marks", "Asks", "Tool-call denials", "Interrupts", "Owner's own GitHub reviews"]
    first = {c: min((w for w in WEEKS if ev[c].get(w)), default=None) for c in cats}
    ser = series(ev, cats)
    for c in ("Asks", "Tool-call denials", "Interrupts"):
        ser[c] = blank_na(ser[c])
    return {"weeks": WEEKS, "cats": cats, "series": ser, "totals": {c: sum(ev[c].values()) for c in cats},
            "first_week": first,
            "table": [
                ("Question in a session (ask)", "harness.asks", "yes", "yes: the agent's next turn", "9 Aug (none logged 10–24 Aug)"),
                ("Ready-mark on a work item", "plans.plan_items.ready_ts", "no", "day only", "23 Jul"),
                ("Go: authorize a goal", "an ask ('Authorize goal N…')", "yes", "yes", "28 Aug"),
                ("Go: a typed instruction", "harness.prompts (text only)", "no", "yes: the prompt", "Nov 2025"),
                ("Tool-call permission", "harness.tool_calls.was_rejected (denials only)", "no", "denials only", "9 Aug (none logged 10–24 Aug)"),
                ("Interrupt", "harness.sessions.interrupted_count", "no", "count per session", "9 Aug (none logged 10–24 Aug)"),
                ("PR review or merge", "github.pr_reviews / pr_timeline", "no", "yes, but the actor is ambiguous", "Mar"),
                ("Reading a plan", "none", "no", "no", "never")]}


# ---------------------------------------------------------------- Q owner-typing prompt volume

CMD_GROUPS = [("/clear", r"^clear$"), ("Ship, review, push, respond", r"ship|review|push|respond|reset"),
              ("Goal, one-shot, wayfare", r"goal|one-shot|wayfare|build|advance|grill|sync|plan"),
              ("Other commands", r".")]


def q_owner_typing_prompts(con):
    ps = prompts(con)
    wk = defaultdict(Counter)
    for p in ps:
        wk["Slash commands" if p["slash"] else "Typed prompts"][p["week"]] += 1
    cs_wk = Counter(f["week"] for f in work_sets(con))
    typed_wk = wk["Typed prompts"]
    per_cs = [share(typed_wk.get(w, 0) + wk["Slash commands"].get(w, 0), cs_wk.get(w, 0)) if cs_wk.get(w, 0) >= 5 else None
              for w in WEEKS]
    ad = adoption(con)
    st_p, st_cs = Counter(), Counter()
    for p in ps:
        if p["repo"] in ad:
            st_p[stage_of(con, p["repo"], p["day"])] += 1
    for f in work_sets(con):
        st_cs[f["stage"]] += 1
    stages = [s for s in STAGES if st_cs[s]]
    cmd = defaultdict(Counter)
    for p in ps:
        if p["slash"]:
            name = (p["command"] or "").split(":")[-1].lstrip("/")
            g = next(g for g, rx in CMD_GROUPS if re.search(rx, name))
            cmd[g][p["day"][:7]] += 1
    months = [m for m in MONTHS]
    ok = lambda w, lo, hi: lo <= w <= hi
    tot = lambda lo, hi: (sum(v for w, v in typed_wk.items() if ok(w, lo, hi)) + sum(v for w, v in wk["Slash commands"].items() if ok(w, lo, hi)),
                          sum(v for w, v in cs_wk.items() if ok(w, lo, hi)))
    early, late = tot("2026-W01", "2026-W26"), tot("2026-W27", "2026-W39")
    p_m, cs_m = Counter(p["day"][:7] for p in ps), Counter(f["month"] for f in work_sets(con))
    return {"weeks": WEEKS, "series": series(wk, ["Typed prompts", "Slash commands"]), "per_cs": per_cs,
            "per_cs_month": [share(p_m[m], cs_m[m]) for m in MONTHS], "p_month": [p_m[m] for m in MONTHS],
            "cs_month": [cs_m[m] for m in MONTHS],
            "cs_week": [cs_wk.get(w, 0) for w in WEEKS],
            "stages": stages, "per_cs_stage": [share(st_p[s], st_cs[s]) for s in stages],
            "stage_n": {s: (st_p[s], st_cs[s]) for s in stages},
            "months": months, "cmd": {g: [cmd[g].get(m, 0) for m in months] for g, _ in CMD_GROUPS},
            "n": len(ps), "typed": sum(typed_wk.values()), "slash": sum(wk["Slash commands"].values()),
            "per_cs_h1": share(*early), "per_cs_h2": share(*late), "h1": early, "h2": late,
            "clear": sum(cmd["/clear"].values())}


# ---------------------------------------------------------------- Q owner-keyboard-hours owner hours vs fleet

def q_owner_keyboard_hours_hours(con):
    ps = prompts(con)
    hours = defaultdict(set)
    by_hour = defaultdict(Counter)
    by_dow = defaultdict(Counter)
    ad = adoption(con)
    for p in ps:
        lt = local(p["ts"])
        hours[p["week"]].add((lt.date(), lt.hour))
        era = ("Before work items" if p["repo"] in ad and STAGES.index(stage_of(con, p["repo"], p["day"])) < 2
               else "With work items or goals")
        by_hour[era][lt.hour] += 1
        by_dow[era][lt.weekday()] += 1
    repos = defaultdict(set)
    for f in work_sets(con):
        repos[f["week"]].add(f["repo"])
    act = [len(hours.get(w, ())) for w in WEEKS]
    rep = [len(repos.get(w, ())) for w in WEEKS]
    eras = ["Before work items", "With work items or goals"]
    hour_share = {e: [share(by_hour[e][h], sum(by_hour[e].values())) for h in range(24)] for e in eras}
    wkend = {e: share(by_dow[e][5] + by_dow[e][6], sum(by_dow[e].values())) for e in eras}
    night = {e: share(sum(by_hour[e][h] for h in (0, 1, 2, 3, 4, 5)), sum(by_hour[e].values())) for e in eras}
    late = [i for i, w in enumerate(WEEKS) if w >= "2026-W27"]
    early = [i for i, w in enumerate(WEEKS) if "2026-W14" <= w <= "2026-W26"]
    avg = lambda v, idx: round(sum(v[i] for i in idx) / len(idx), 1)
    return {"weeks": WEEKS, "active_hours": act, "active_repos": rep, "hour_share": hour_share, "eras": eras,
            "weekend": wkend, "night": night,
            "hours_q2": avg(act, early), "hours_q3": avg(act, late), "repos_q2": avg(rep, early), "repos_q3": avg(rep, late),
            "max_hours": max(act), "max_week": WEEKS[act.index(max(act))]}


# ---------------------------------------------------------------- Q owner-gates-per-item gates per work item

ITEM_RX = re.compile(r"\bitems?\s+#?(\d+(?:\s*(?:,|and|&|–|-)\s*#?\d+)*)", re.I)
GOAL_RX = re.compile(r"\bgoals?\s+#?(\d+(?:\s*(?:,|and|&)\s*#?\d+)*)", re.I)


def _nums(s):
    out = set()
    for a, b in re.findall(r"(\d+)\s*[–-]\s*(\d+)", s):
        if int(b) - int(a) < 40:
            out |= {str(x) for x in range(int(a), int(b) + 1)}
    return out | set(re.findall(r"\d+", s))


def _norm(i):
    return str(int(i)) if str(i).isdigit() else str(i)


@lru_cache(maxsize=None)
def item_decisions(con):
    """Done work items (not goals) with the owner decisions on record for each."""
    items = rows(con, "SELECT repo, item_id, goal_id, ready_ts, done_ts, created_ts, day, origin FROM plans.plan_items "
                      "WHERE type != 'goal'")
    members = defaultdict(set)
    for g in rows(con, "SELECT repo, goal_id, members FROM plans.goals"):
        for m in json.loads(g["members"] or "[]"):
            members[(g["repo"], _norm(g["goal_id"]))].add(_norm(m))
    item_asks, goal_asks = Counter(), Counter()
    for a in asks(con):
        for m in ITEM_RX.finditer(a["question"]):
            for n in _nums(m.group(1)):
                item_asks[(a["repo"], n)] += 1
        for m in GOAL_RX.finditer(a["question"]):
            for n in _nums(m.group(1)):
                goal_asks[(a["repo"], n)] += 1
    goal_of = {}
    for (repo, gid), ms in members.items():
        for m in ms:
            goal_of[(repo, m)] = gid
    out = []
    for i in items:
        if not in_scope(i["repo"]) or not i["done_ts"]:
            continue
        key = (i["repo"], _norm(i["item_id"]))
        gid = _norm(i["goal_id"]) if i["goal_id"] else goal_of.get(key)
        d = {"ready": int(bool(i["ready_ts"])), "go": int(bool(gid and goal_asks.get((i["repo"], gid)))),
             "asks": item_asks.get(key, 0)}
        day = i["done_ts"][:10]
        out.append({**i, **d, "in_goal": bool(gid), "total": d["ready"] + d["go"] + d["asks"],
                    "done_day": day, "week": week_of(day), "month": day[:7]})
    return out


def q_owner_gates_per_item_gates_per_item(con):
    its = [i for i in item_decisions(con) if i["done_day"] >= "2026-07-01"]
    wk = defaultdict(lambda: defaultdict(list))
    for i in its:
        for k in ("ready", "go", "asks"):
            wk[k][i["week"]].append(i[k])
    cats = {"ready": "Ready-mark", "go": "Go (goal authorized)", "asks": "Asks naming the item"}
    ser = {cats[k]: [None if w in NA_WEEKS else round(sum(wk[k][w]) / len(wk[k][w]), 2) if len(wk[k][w]) >= 3 else 0
                     for w in WEEKS] for k in cats}
    zero = defaultdict(list)
    for i in its:
        zero[i["month"]].append(i["total"] == 0)
    months = [m for m in MONTHS if m >= "2026-07"]
    since_ask = [i for i in its if i["done_day"] >= "2026-08-25"]
    dist = Counter(min(i["total"], 4) for i in since_ask)
    return {"weeks": WEEKS, "series": ser, "n": len(its),
            "months": months, "zero_share": [share(sum(zero[m]), len(zero[m])) for m in months],
            "mean_since_asks": round(sum(i["total"] for i in since_ask) / len(since_ask), 2) if since_ask else None,
            "n_since_asks": len(since_ask), "dist": [dist.get(k, 0) for k in range(5)],
            "two_plus": share(sum(1 for i in since_ask if i["total"] >= 2), len(since_ask)),
            "none_since": share(sum(1 for i in since_ask if i["total"] == 0), len(since_ask)),
            "ready_share": share(sum(i["ready"] for i in since_ask), len(since_ask)),
            "go_share": share(sum(i["go"] for i in since_ask), len(since_ask)),
            "events": GATE_EVENTS}


# ---------------------------------------------------------------- Q ready-mark-batching ready-mark batches (day level)

def q_ready_mark_batching_ready(con):
    its = [r for r in rows(con, "SELECT repo, item_id, created_ts, ready_ts FROM plans.plan_items "
                                "WHERE ready_ts IS NOT NULL AND type != 'goal'") if in_scope(r["repo"])]
    batch = Counter((r["repo"], r["ready_ts"][:10]) for r in its)
    wk_items, wk_batches, wk_wait = Counter(), defaultdict(list), defaultdict(list)
    for (repo, d), n in batch.items():
        wk_batches[week_of(d)].append(n)
    waits = []
    for r in its:
        w = week_of(r["ready_ts"][:10])
        wk_items[w] += 1
        if r["created_ts"]:
            dd = (date.fromisoformat(r["ready_ts"][:10]) - date.fromisoformat(r["created_ts"][:10])).days
            if dd >= 0:
                wk_wait[w].append(dd)
                waits.append(dd)
    bins = ["1", "2–3", "4–6", "7–10", "11+"]
    bin_of = lambda n: bins[0] if n == 1 else bins[1] if n <= 3 else bins[2] if n <= 6 else bins[3] if n <= 10 else bins[4]
    items_in = Counter()
    wk_bin = defaultdict(Counter)
    for (repo, d), n in batch.items():
        items_in[bin_of(n)] += n
        wk_bin[bin_of(n)][week_of(d)] += n
    return {"weeks": WEEKS, "items": [wk_items.get(w, 0) for w in WEEKS],
            "median_batch": [med(wk_batches[w]) for w in WEEKS], "median_wait": [med(wk_wait[w]) for w in WEEKS],
            "bins": bins, "by_bin": series(wk_bin, bins), "items_by_batch": [items_in[b] for b in bins], "n_items": len(its), "n_batches": len(batch),
            "median_batch_all": med(list(batch.values())),
            "share_in_4plus": share(sum(n for n in batch.values() if n >= 4), len(its)),
            "same_day": share(sum(1 for w in waits if w == 0), len(waits)), "median_wait_all": med(waits),
            "biggest": max(batch.values())}


# ---------------------------------------------------------------- Q owner-decision-share owner decision behind shipped work

DECISION_CATS = ["Goal the owner authorized", "Work item marked ready", "Work item, no ready-mark on record",
                 "One-shot task the owner instructed", "Pushed to main", "Dependabot (no decision)"]


def q_owner_decision_share_decisions(con):
    links, _ = set_item_links(con)
    meta = {(r["repo"], _norm(r["item_id"])): r for r in rows(con, "SELECT repo, item_id, goal_id, ready_ts FROM plans.plan_items")}
    goal_members = set()
    for g in rows(con, "SELECT repo, members FROM plans.goals"):
        for m in json.loads(g["members"] or "[]"):
            goal_members.add((g["repo"], _norm(m)))
    wk = defaultdict(Counter)
    cat_by_repo = defaultdict(Counter)
    for f in changeset_facts(con):
        ids = links.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]), set())
        its = [meta.get((f["repo"], _norm(i))) for i in ids]
        its = [i for i in its if i]
        if f["dependabot"]:
            c = DECISION_CATS[5]
        elif any(i["goal_id"] or (f["repo"], _norm(i["item_id"])) in goal_members for i in its):
            c = DECISION_CATS[0]
        elif any(i["ready_ts"] for i in its):
            c = DECISION_CATS[1]
        elif its:
            c = DECISION_CATS[2]
        elif f["unit_kind"] == "push":
            c = DECISION_CATS[4]
        else:
            c = DECISION_CATS[3]
        wk[c][f["week"]] += 1
        cat_by_repo[f["category"]][c] += 1
    tot = lambda lo: {c: sum(v for w, v in wk[c].items() if w >= lo) for c in DECISION_CATS}
    since = tot("2026-W30")
    n_since = sum(since.values())
    return {"weeks": WEEKS, "cats": DECISION_CATS, "series": series(wk, DECISION_CATS),
            "since_w30": {c: share(v, n_since) for c, v in since.items()}, "n_since": n_since,
            "by_category": {k: dict(v) for k, v in cat_by_repo.items()},
            "all": {c: sum(wk[c].values()) for c in DECISION_CATS}}


# ---------------------------------------------------------------- Q owner-wait-share waiting on the owner

def q_owner_wait_share_wait(con):
    """Per session, walk the turn clock. A gap over 8 h means the session was closed and is dropped.
    Otherwise the gap belongs to whoever the work was waiting on:
      - an ask fell inside it and the agent's next turn ended it: waiting on the owner's answer;
      - the agent's turn ended and the owner's next prompt ended it: waiting on the owner's next instruction;
      - else (agent turn to agent turn): the agent, its tools and CI working."""
    repo_of = session_repo(con)
    ask_ts = defaultdict(list)
    for r in con.execute("SELECT session_id_hash, ts FROM harness.asks"):
        ask_ts[r[0]].append(t(r[1]))
    turns = defaultdict(list)
    for r in con.execute("SELECT session_id_hash, ts, role FROM harness.turns WHERE is_synthetic = 0 AND ts IS NOT NULL"):
        turns[r[0]].append((t(r[1]), r[2], r[1][:10]))
    wk = defaultdict(Counter)
    closed = 0
    for sid, ts in turns.items():
        if not in_scope(repo_of.get(sid)):
            continue
        ts.sort()
        a = sorted(ask_ts.get(sid, []))
        for (t0, r0, _), (t1, r1, d1) in zip(ts, ts[1:]):
            gap = t1 - t0
            if gap > CLOSED_GAP_S:
                closed += 1
                continue
            w = week_of(d1)
            if r1 == "user":
                wk["Waiting for the owner's next instruction"][w] += gap / 3600
            elif any(t0 <= x < t1 for x in a):
                wk["Waiting for the owner's answer to an ask"][w] += gap / 3600
            else:
                wk["Agent, tools and CI working"][w] += gap / 3600
    cats = ["Agent, tools and CI working", "Waiting for the owner's answer to an ask", "Waiting for the owner's next instruction"]
    tot = {c: sum(wk[c].values()) for c in cats}
    wait_share = [share(wk[cats[1]].get(w, 0) + wk[cats[2]].get(w, 0), sum(wk[c].get(w, 0) for c in cats)) for w in SESSION_WEEKS]
    A = asks(con)
    lat = defaultdict(list)
    for x in A:
        if x["wait_s"] is not None:
            lat[x["kind"]].append(x["wait_s"] / 60)
    allw = [x["wait_s"] / 60 for x in A if x["wait_s"] is not None]
    wk_lat = defaultdict(list)
    for x in A:
        if x["wait_s"] is not None:
            wk_lat[x["week"]].append(x["wait_s"] / 60)
    return {"weeks": SESSION_WEEKS, "cats": cats, "series": series(wk, cats, SESSION_WEEKS, na=True), "totals": tot,
            "wait_share": wait_share, "share_all": share(tot[cats[1]] + tot[cats[2]], sum(tot.values())),
            "ask_share": share(tot[cats[1]], sum(tot.values())),
            "closed_gaps": closed, "ask_median_min": med(allw), "ask_p90_min": round(sorted(allw)[int(0.9 * len(allw))], 1) if allw else None,
            "ask_over_1h": share(sum(1 for v in allw if v > 60), len(allw)), "n_asks": len(allw),
            "closed_asks": sum(1 for x in A if x["closed"]),
            "lat_kinds": [k for k in ASK_KINDS + [UNLABELLED] if lat[k]], "lat_by_kind": [med(lat[k]) for k in ASK_KINDS + [UNLABELLED] if lat[k]],
            "lat_n": [len(lat[k]) for k in ASK_KINDS + [UNLABELLED] if lat[k]],
            "week_median": [med(wk_lat[w]) for w in SESSION_WEEKS]}


# ---------------------------------------------------------------- Q agent-questions asks

def q_agent_questions_asks(con):
    A = asks(con)
    wk = defaultdict(Counter)
    for a in A:
        wk[a["kind"]][a["week"]] += 1
    cs_wk = Counter(f["week"] for f in work_sets(con))
    live = [w for w in SESSION_WEEKS if w not in NA_WEEKS]
    n_cs = sum(cs_wk[w] for w in live)
    ph = Counter(a["phase"] for a in A)
    phases = ["Planning", "Building", "Shipping", "No skill"]
    kinds = Counter(a["kind"] for a in A)
    shown = ASK_KINDS + ([UNLABELLED] if kinds[UNLABELLED] else [])
    return {"weeks": SESSION_WEEKS, "kinds": shown, "series": series(wk, shown, SESSION_WEEKS, na=True), "n": len(A),
            "per_cs": share(len([a for a in A if a["week"] in live]), n_cs), "n_cs": n_cs,
            "phases": phases, "by_phase": [ph[p] for p in phases], "by_kind": {k: kinds[k] for k in shown},
            "multi": share(sum(1 for a in A if a["n_questions"] > 1), len(A)),
            "questions": sum(a["n_questions"] for a in A),
            "on_feature_branch": share(sum(1 for a in A if a["branch"] and not a["on_default"]), sum(1 for a in A if a["branch"])),
            "sessions": len({a["ts"][:13] + a["repo"] for a in A}),
            "per_week_last4": round(sum(len([a for a in A if a["week"] == w]) for w in SESSION_WEEKS[-4:]) / 4, 1)}


# ---------------------------------------------------------------- Q recommendation-uptake recommendation taken (+ RQ-h6-048)

TOOK = ["Took the recommendation", "Picked another option", "Wrote their own answer", "Declined or answered in chat"]


def q_recommendation_uptake_recommend(con):
    A = [a for a in asks(con) if a["took"]]
    wk = defaultdict(Counter)
    for a in A:
        wk[a["took"]][a["week"]] += 1
    rate = [share(wk[TOOK[0]].get(w, 0), sum(wk[c].get(w, 0) for c in TOOK)) if sum(wk[c].get(w, 0) for c in TOOK) >= 5 else None
            for w in SESSION_WEEKS]
    by_kind = {k: Counter(a["took"] for a in A if a["kind"] == k) for k in ASK_KINDS + [UNLABELLED]}
    kinds = [k for k in ASK_KINDS + [UNLABELLED] if sum(by_kind[k].values())]
    overturned = [a for a in A if a["took"] in TOOK[1:3]]
    return {"weeks": SESSION_WEEKS, "series": series(wk, TOOK, SESSION_WEEKS, na=True), "rate": rate, "n": len(A),
            "counts": {c: sum(1 for a in A if a["took"] == c) for c in TOOK},
            "took_share": share(sum(1 for a in A if a["took"] == TOOK[0]), len(A)),
            "kinds": kinds, "kind_share": [share(by_kind[k][TOOK[0]], sum(by_kind[k].values())) for k in kinds],
            "kind_n": [sum(by_kind[k].values()) for k in kinds],
            "with_rec_any": sum(1 for a in asks(con) if a["has_rec"]),
            "examples": [(a["day"], a["repo"], a["question"][:150], a["answer"][:120]) for a in overturned[:8]]}


# ---------------------------------------------------------------- Q owner-interrupts interrupts

def q_owner_interrupts_interrupts(con):
    s = [r for r in rows(con, "SELECT repo, day, user_turns, assistant_turns, interrupted_count n, subagent_count "
                             "FROM harness.sessions") if in_scope(r["repo"])]
    wk_i, wk_u, wk_sub, wk_s = Counter(), Counter(), Counter(), Counter()
    for r in s:
        w = week_of(r["day"])
        wk_i[w] += r["n"]
        wk_u[w] += r["user_turns"]
        wk_sub[w] += r["subagent_count"]
        wk_s[w] += 1
    rate = [share(wk_i[w] * 100, wk_u[w]) if wk_u[w] >= 20 else None for w in SESSION_WEEKS]
    buckets = [("1–5", 1, 5), ("6–20", 6, 20), ("21+", 21, 10 ** 9)]
    by_b = []
    for name, lo, hi in buckets:
        g = [r for r in s if lo <= r["user_turns"] <= hi]
        by_b.append((name, share(sum(1 for r in g if r["n"]), len(g)), len(g)))
    return {"weeks": SESSION_WEEKS, "rate": rate, "subagents_per_session": [share(wk_sub[w], wk_s[w]) for w in SESSION_WEEKS],
            "n": sum(r["n"] for r in s), "sessions": len(s), "sessions_with": sum(1 for r in s if r["n"]),
            "user_turns": sum(r["user_turns"] for r in s), "per100": share(100 * sum(r["n"] for r in s), sum(r["user_turns"] for r in s)),
            "buckets": by_b, "max_in_session": max(r["n"] for r in s)}


# ---------------------------------------------------------------- Q tool-call-denials denials

def q_tool_call_denials_denials(con):
    repo_of = session_repo(con)
    tc = [r for r in rows(con, "SELECT session_id_hash sid, ts, tool, was_rejected rej FROM harness.tool_calls")
          if in_scope(repo_of.get(r["sid"]))]
    wk_n, wk_r = Counter(), Counter()
    by_tool, by_tool_n = Counter(), Counter()
    by_repo = Counter()
    for r in tc:
        w = week_of(r["ts"][:10])
        wk_n[w] += 1
        wk_r[w] += r["rej"]
        by_tool_n[r["tool"]] += 1
        if r["rej"]:
            by_tool[r["tool"]] += 1
            by_repo[repo_of[r["sid"]]] += 1
    rate = [round(1000 * wk_r[w] / wk_n[w], 2) if wk_n[w] >= 200 else None for w in SESSION_WEEKS]
    top = [k for k, _ in by_tool.most_common(6)]
    return {"weeks": SESSION_WEEKS, "rate": rate, "n": sum(wk_r.values()), "calls": sum(wk_n.values()),
            "per1000": round(1000 * sum(wk_r.values()) / sum(wk_n.values()), 2),
            "tools": top, "tool_n": [by_tool[k] for k in top], "tool_rate": [round(1000 * by_tool[k] / by_tool_n[k], 1) for k in top],
            "repos": by_repo.most_common(6), "first4": [r for r in rate[:4] if r is not None],
            "last4": [r for r in rate[-4:] if r is not None], "events": PERMISSION_EVENTS}


# ---------------------------------------------------------------- Q who-really-reviews who reviews

REVIEW_CATS = ["A person reviewed", "An agent, on the owner's account", "Bots only (auto-approve, Copilot)", "No review"]


def q_who_really_reviews_reviews(con):
    ra = actors.review_actors(con)
    by_pr = defaultdict(set)
    for r in ra:
        by_pr[(r["repo"], r["number"])].add(r["actor"])
    prs = [r for r in rows(con, "SELECT repo, number, merged_ts, head_ref, author, hours_to_merge FROM github.prs WHERE merged_ts IS NOT NULL")
           if r["repo"] in adoption(con)]
    work = [p for p in prs if not (p["head_ref"] or "").startswith("dependabot/")]
    wk = defaultdict(Counter)
    ch2_style = 0
    hours = defaultdict(list)
    for p in work:
        a = by_pr.get((p["repo"], p["number"]), set())
        c = (REVIEW_CATS[0] if a & {"owner", "human"} else REVIEW_CATS[1] if a & {"agent", "unclear"}
             else REVIEW_CATS[2] if "bot" in a else REVIEW_CATS[3])
        ch2_style += bool(a & {"owner", "human", "agent", "unclear"})
        wk[c][week_of(p["merged_ts"][:10])] += 1
        if p["hours_to_merge"] is not None:
            hours[c].append(p["hours_to_merge"])
    owner_acct = defaultdict(Counter)
    for r in ra:
        if r["reviewer"] == OWNER:
            lab = {"skill template body": "Agent: review or verdict text", "thread reply after an agent command": "Agent: reply in a comment thread",
                   "empty, after an agent command": "Agent: reply in a comment thread",
                   "thread reply, no agent command in 3 h": "Unclear: reply, no agent command near it",
                   "empty, on a bot PR": "Unclear: reply, no agent command near it",
                   "empty review on another person's PR": "The owner: approve button, no text"}[r["why"]]
            owner_acct[lab][r["submitted_ts"][:7]] += 1
    labs = ["Agent: review or verdict text", "Agent: reply in a comment thread", "Unclear: reply, no agent command near it",
            "The owner: approve button, no text"]
    months = [m for m in MONTHS if m >= "2026-03"]
    h = actors.human_reviews(con)
    hu = actors.human_reviews_upper(con)
    in_work = {(p["repo"], p["number"]) for p in work}
    person_prs = sorted({(r["repo"], r["number"], r["author"]) for r in ra if r["actor"] in ("owner", "human") and r["merged_ts"]})
    return {"weeks": WEEKS, "cats": REVIEW_CATS, "series": series(wk, REVIEW_CATS), "n": len(work),
            "counts": {c: sum(wk[c].values()) for c in REVIEW_CATS},
            "person": sum(1 for k in in_work if h.get(k)), "person_upper": sum(1 for k in in_work if hu.get(k)),
            "ch2_style": ch2_style, "all_merged": len(h), "all_person": sum(h.values()), "all_upper": sum(hu.values()),
            "months": months, "labs": labs, "owner_acct": {l: [owner_acct[l].get(m, 0) for m in months] for l in labs},
            "owner_acct_total": sum(sum(v.values()) for v in owner_acct.values()),
            "owner_acct_agent": sum(sum(owner_acct[l].values()) for l in labs[:2]),
            "owner_acct_unclear": sum(owner_acct[labs[2]].values()), "owner_acct_owner": sum(owner_acct[labs[3]].values()),
            "median_hours": {c: med(hours[c]) for c in REVIEW_CATS}, "person_prs": person_prs}


# ---------------------------------------------------------------- Q one-way-door-changes one-way doors

INFRA = ("infrastructure-root", "infrastructure-environments")
ONEWAY_PATH = re.compile(r"(^|/)(migrations?|migrate)/|\.sql$|auto-approve\.ya?ml$|(^|/)terraform/|\.tf$")
ONEWAY_TITLE = re.compile(r"!:|breaking|migrat", re.I)
GATE_CATS = ["A person reviewed or wrote it", "Auto-approve (Claude on CI)", "Agent review only", "No review"]


def q_one_way_door_changes_oneway(con):
    files = defaultdict(list)
    for r in con.execute("SELECT c.repo, c.pr_number, f.path FROM git.commits c JOIN git.commit_files f "
                         "ON f.repo = c.repo AND f.sha = c.sha WHERE c.pr_number IS NOT NULL"):
        files[(r[0], r[1])].append(r[2])
    ra = actors.review_actors(con)
    by_pr = defaultdict(set)
    approved_by_ci = set()
    for r in ra:
        by_pr[(r["repo"], r["number"])].add(r["actor"])
        if r["reviewer"] == "github-actions" and r["state"] == "APPROVED":
            approved_by_ci.add((r["repo"], r["number"]))
    prs = [p for p in rows(con, "SELECT repo, number, title, author, merged_ts, head_ref, hours_to_merge FROM github.prs "
                                "WHERE merged_ts IS NOT NULL") if p["repo"] in adoption(con)
           and not (p["head_ref"] or "").startswith("dependabot/")]
    wk = defaultdict(Counter)
    cmp = {True: Counter(), False: Counter()}
    hrs = {True: [], False: []}
    why = Counter()
    for p in prs:
        k = (p["repo"], p["number"])
        fs = files.get(k, [])
        infra = p["repo"] in INFRA
        path = any(ONEWAY_PATH.search(f) for f in fs)
        title = bool(ONEWAY_TITLE.search(p["title"] or ""))
        oneway = infra or path or title
        a = by_pr.get(k, set())
        g = (GATE_CATS[0] if a & {"owner", "human"} or p["author"] not in (OWNER,) and not (p["author"] or "").endswith("[bot]")
             and p["author"] != "app/dependabot"
             else GATE_CATS[1] if k in approved_by_ci else GATE_CATS[2] if a & {"agent", "unclear"} else GATE_CATS[3])
        cmp[oneway][g] += 1
        if p["hours_to_merge"] is not None:
            hrs[oneway].append(p["hours_to_merge"])
        if oneway:
            wk[g][week_of(p["merged_ts"][:10])] += 1
            why["infrastructure repo" if infra else "migration, terraform or auto-approve file" if path else "title says breaking or migration"] += 1
    n1, n0 = sum(cmp[True].values()), sum(cmp[False].values())
    return {"weeks": WEEKS, "cats": GATE_CATS, "series": series(wk, GATE_CATS), "n_oneway": n1, "n_other": n0,
            "share_oneway": {c: share(cmp[True][c], n1) for c in GATE_CATS},
            "share_other": {c: share(cmp[False][c], n0) for c in GATE_CATS},
            "hours": {"One-way door": med(hrs[True]), "Other": med(hrs[False])}, "why": dict(why)}


# ---------------------------------------------------------------- Q other-humans the second person

def q_other_humans_people(con):
    humans = {r[0] for r in con.execute("SELECT DISTINCT author FROM github.prs WHERE author_is_bot = 0")} - {OWNER}
    humans = {h for h in humans if h and not h.startswith("app/")}
    wk = defaultdict(Counter)
    repo = defaultdict(Counter)
    for r in rows(con, "SELECT repo, number, author, created_ts, merged_ts FROM github.prs"):
        if r["author"] in humans and in_scope(r["repo"]):
            wk["PRs opened"][week_of(r["created_ts"][:10])] += 1
            repo[r["repo"]]["opened"] += 1
    for r in rows(con, "SELECT repo, number, actor, ts FROM github.pr_timeline WHERE event = 'merged'"):
        if r["actor"] in humans and in_scope(r["repo"]):
            wk["PRs merged"][week_of(r["ts"][:10])] += 1
            repo[r["repo"]]["merged"] += 1
    rev = Counter()
    for r in actors.review_actors(con):
        if r["author"] in humans and r["merged_ts"]:
            rev[r["actor"]] += 1
    reviewed_by_owner = {(r["repo"], r["number"]) for r in actors.review_actors(con) if r["actor"] == "owner"}
    theirs = [r for r in rows(con, "SELECT repo, number, merged_ts FROM github.prs") if r["repo"] and in_scope(r["repo"])
              and (r["repo"], r["number"]) in {(x["repo"], x["number"]) for x in rows(con, "SELECT repo, number FROM github.prs WHERE author IN ({})".format(
                  ",".join("?" * len(humans))), tuple(humans))}]
    trailer = rows(con, "SELECT SUM(claude_trailer) t, COUNT(*) n FROM pr_commits.pr_commits c JOIN github.prs p "
                        "ON p.repo = c.repo AND p.number = c.pr_number WHERE p.author IN ({})".format(",".join("?" * len(humans))), tuple(humans))[0]
    active = sorted(w for w in WEEKS if wk["PRs opened"].get(w) or wk["PRs merged"].get(w))
    top = sorted(repo, key=lambda k: -repo[k]["merged"] - repo[k]["opened"])
    fleet_merged = rows(con, "SELECT COUNT(*) n FROM github.prs WHERE merged_ts IS NOT NULL")[0]["n"]
    return {"weeks": WEEKS, "people": sorted(humans), "series": series(wk, ["PRs opened", "PRs merged"]),
            "repos": top, "repo_opened": [repo[k]["opened"] for k in top], "repo_merged": [repo[k]["merged"] for k in top],
            "opened": sum(wk["PRs opened"].values()), "merged": sum(wk["PRs merged"].values()), "fleet_merged": fleet_merged,
            "reviews_on_theirs": dict(rev), "owner_reviewed": len({(r["repo"], r["number"]) for r in theirs} & reviewed_by_owner),
            "trailer": trailer, "first": active[0] if active else None, "last": active[-1] if active else None,
            "infra_share": share(sum(repo[k]["merged"] for k in INFRA), sum(r["merged"] for r in repo.values()))}


# ---------------------------------------------------------------- Q owner-corrections corrections (the lead's detectors.prompt_intent)

STEER = ("correction", "redirect")


def q_owner_corrections_corrections(con):
    try:
        pi = rows(con, "SELECT ts, day, repo, intent, target, correction_kind FROM detectors.prompt_intent")
    except sqlite3.OperationalError as e:
        print(f"owner: {e}; Q owner-corrections skipped", file=sys.stderr)
        return None
    pi = [r for r in pi if in_scope(r["repo"]) and r["day"] >= "2026-01-01"]
    wk = defaultdict(Counter)
    for r in pi:
        if r["intent"] in STEER:
            wk["Corrections" if r["intent"] == "correction" else "Redirects"][week_of(r["day"])] += 1
    cs_wk = Counter(f["week"] for f in work_sets(con))
    cs_m = Counter(f["month"] for f in work_sets(con))
    m_steer, m_all = Counter(), Counter()
    for r in pi:
        m_all[r["day"][:7]] += 1
        m_steer[r["day"][:7]] += r["intent"] in STEER
    per_cs_m = [share(m_steer[m], cs_m[m]) for m in MONTHS]
    share_m = [share(m_steer[m], m_all[m]) for m in MONTHS]
    ad = adoption(con)
    kinds = ["error", "taste", "scope"]
    by_stage = defaultdict(Counter)
    st_cs = Counter(f["stage"] for f in work_sets(con))
    for r in pi:
        if r["intent"] in STEER and r["repo"] in ad:
            if r["correction_kind"] in kinds:
                by_stage[stage_of(con, r["repo"], r["day"])][r["correction_kind"]] += 1
    stages = [st for st in STAGES if st_cs[st] and sum(by_stage[st].values())]
    per_cs_stage = {k: [share(by_stage[st][k], st_cs[st]) for st in stages] for k in kinds}
    half = lambda lo, hi: (sum(v for c in wk for w, v in wk[c].items() if lo <= w <= hi),
                           sum(v for w, v in cs_wk.items() if lo <= w <= hi))
    h1, h2 = half("2026-W01", "2026-W26"), half("2026-W27", "2026-W39")
    steer = [r for r in pi if r["intent"] in STEER]
    tgt = Counter(r["target"] for r in steer)
    kind_all = Counter(r["correction_kind"] for r in steer)
    intents = Counter(r["intent"] for r in pi)
    judg = sum(1 for r in steer if r["correction_kind"] in ("taste", "scope"))
    return {"weeks": WEEKS, "series": series(wk, ["Corrections", "Redirects"]), "per_cs_month": per_cs_m,
            "share_month": share_m, "months": MONTHS, "stages": stages, "per_cs_stage": per_cs_stage, "kinds": kinds,
            "n": len(pi), "steer": len(steer), "corrections": intents["correction"], "redirects": intents["redirect"],
            "h1": h1, "h2": h2, "per_cs_h1": share(*h1), "per_cs_h2": share(*h2),
            "share_all": share(len(steer), len(pi)), "targets": dict(tgt), "kind_all": dict(kind_all),
            "judgment": judg, "intents": dict(intents), "months_per_cs": dict(zip(MONTHS, per_cs_m)),
            "share_h1": share(sum(1 for r in steer if r["day"] < "2026-07-01"), sum(1 for r in pi if r["day"] < "2026-07-01")),
            "share_h2": share(sum(1 for r in steer if r["day"] >= "2026-07-01"), sum(1 for r in pi if r["day"] >= "2026-07-01"))}


def all_data(con):
    return {k: f(con) for k, f in [("q_owner_wait_points", q_owner_wait_points_gates), ("q_owner_typing", q_owner_typing_prompts), ("q_owner_keyboard_hours", q_owner_keyboard_hours_hours), ("q_owner_gates_per_item", q_owner_gates_per_item_gates_per_item),
                                   ("q_ready_mark_batching", q_ready_mark_batching_ready), ("q_owner_decision_share", q_owner_decision_share_decisions), ("q_owner_wait_share", q_owner_wait_share_wait), ("q_agent_questions", q_agent_questions_asks),
                                   ("q_recommendation_uptake", q_recommendation_uptake_recommend), ("q_owner_corrections", q_owner_corrections_corrections), ("q_owner_interrupts", q_owner_interrupts_interrupts), ("q_tool_call_denials", q_tool_call_denials_denials),
                                   ("q_who_really_reviews", q_who_really_reviews_reviews), ("q_one_way_door_changes", q_one_way_door_changes_oneway), ("q_other_humans", q_other_humans_people)]}


if __name__ == "__main__":
    from cube.db import connect
    con = connect("owner")
    only = sys.argv[1:]
    for k, v in all_data(con).items() if not only else [(k, globals()[k](con)) for k in only]:
        brief = {a: b for a, b in v.items() if not isinstance(b, (list, dict)) or a in (
            "totals", "counts", "since_w30", "share_oneway", "share_other", "hours", "why", "by_kind", "median_hours",
            "stage_n", "weekend", "night", "first_week", "reviews_on_theirs", "trailer", "all", "by_category",
            "per_cs_stage", "stages", "dist", "zero_share", "months", "buckets", "tools", "tool_n", "tool_rate", "repos",
            "kinds", "kind_share", "kind_n", "lat_kinds", "lat_by_kind", "lat_n", "phases", "by_phase", "first4", "last4",
            "h1", "h2", "items_by_batch", "person_prs", "repo_opened", "repo_merged", "people")}
        print(k, json.dumps(brief, default=str)[:2500])
