# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


"""Cross-repo messaging series: cross-repo context and messaging. One function per question.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/messages/data.py

Inputs beyond the shared databases:
- messages.sqlite `blobs` (report/messages/gitscan.py): every default-branch file change with blob ids,
  read from the mirrors; `labels` (report/messages/label.py): Haiku labels.
- The checkouts under WAYFARE_FLEET_ROOT, read-only: mailbox files (.plans/inbox, .outbox,
  outbox), design-feedback packets (.plans/.feedback), and `git` on the mirrors.
"""
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from record import changeset_facts, rows, stage_of, week_of  # noqa: E402
from evolution import MONTHS, WEEKS  # noqa: E402
from changes import LATEST, UPSTREAM, clusters, commits, days  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, REPO_ALIASES, category_of  # noqa: E402

FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MIRRORS = os.path.join(PLUGIN, ".analysis", "data", "mirrors")
SESSIONS_FROM = "2026-08-09"
# No Claude Code sessions are logged 10-24 Aug (brief: "data not available"). Session-derived series are None
# there, never zero, and a change landing then has no knowable carrier.
GAP = ("2026-08-10", "2026-08-24")
GAP_WEEKS = ("2026-W33", "2026-W34")
in_gap = lambda day: GAP[0] <= day <= GAP[1]


def blank_gap(series, weeks=WEEKS):
    return {k: [None if w in GAP_WEEKS else v for w, v in zip(weeks, vals)] for k, vals in series.items()}
alias = lambda r: REPO_ALIASES.get(r, r)


@lru_cache(maxsize=None)
def con():
    return _connect("messages")


@lru_cache(maxsize=None)
def scripted_sessions():
    """agent_harness's filter: pre-commit `claude -p` diff reviews and sessions with no model turn are not interactive."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("agent_harness_data", os.path.join(os.path.dirname(HERE), "agent_harness", "data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(mod.scripted(con()))


def median(v):
    v = sorted(x for x in v if x is not None)
    return None if not v else v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2


def weekly_counts(events, key, cats, weeks=WEEKS):
    """events: dicts with 'day'; key(e) -> category. {category: [count per week]}."""
    acc = defaultdict(Counter)
    for e in events:
        acc[key(e)][week_of(e["day"])] += 1
    return {c: [acc[c].get(w, 0) for w in weeks] for c in cats}


def labels(task):
    return {r["key"]: json.loads(r["label"]) for r in rows(con(), "SELECT key, label FROM messages.labels WHERE task=?", (task,))}


def spend():
    return {r["task"]: r["usd"] for r in rows(con(), "SELECT task, SUM(usd) usd FROM messages.spend GROUP BY task")}


# ------------------------------------------------------------------ the mailbox and the packets

def frontmatter(path):
    text = open(path, errors="replace").read()
    fm = {}
    if text.startswith("---"):
        for line in text.split("---", 2)[1].splitlines():
            m = re.match(r"^(\w+):\s*(.*?)\s*(#.*)?$", line)
            if m:
                fm[m.group(1)] = m.group(2).strip('"')
    return fm, text


try:
    from messages_hand import MESSAGE_EVENTS, MESSAGE_OUTCOMES, MOVES  # noqa: E402
    HAND_DATA = True
except ImportError:
    # messages_hand.py is hand-checked from the fleet's own records and is never published. Without it the
    # outcome questions report themselves unavailable: empty tables would read as "nothing was acted on".
    MESSAGE_OUTCOMES, MOVES, MESSAGE_EVENTS = {}, [], {}
    HAND_DATA = False
    print("messages: messages_hand.py absent; Q message-delivery, Q message-response-time, Q message-fidelity and Q ownership-handovers are unavailable", file=sys.stderr)
UNAVAILABLE = {"unavailable": "messages_hand.py absent"}


@lru_cache(maxsize=None)
def messages():
    """Every mailbox file in the fleet and the plugin checkout, deduplicated by msg_id."""
    paths = []
    for root in [os.path.join(FLEET, d) for d in os.listdir(FLEET)] + [PLUGIN]:
        for sub in ("inbox", ".outbox", "outbox"):
            paths += glob.glob(os.path.join(root, ".plans", sub, "*.md"))
    out = {}
    for p in sorted(paths):
        fm, text = frontmatter(p)
        repo_dir = os.path.basename(p.split("/.plans/")[0])
        box = p.split("/.plans/")[1].split("/")[0]
        if not fm:
            m = re.search(r"From:\s*([\w-]+)\s*·\s*(\d{4}-\d\d-\d\d)", text)
            title = re.search(r"^#\s*(.+)$", text, re.M)
            fm = dict(msg_id=os.path.basename(p)[:-3], type="signal", sent=m.group(2) if m else None,
                      to=re.search(r"Signal to ([\w-]+)", text).group(1) if "Signal to" in text else None)
            fm["from"] = m.group(1) if m else repo_dir
        sender, to = alias(fm.get("from", "")), alias(fm.get("to", ""))
        holder = alias(repo_dir if repo_dir != os.path.basename(PLUGIN) else "wayfare-skills")
        delivered = box == "inbox" and holder == to
        msg = out.setdefault(fm["msg_id"], dict(id=fm["msg_id"], type=fm.get("type"), sender=sender, to=to,
                                                day=fm.get("sent"), awaited=fm.get("awaited") == "true",
                                                status=fm.get("status"), reply_to=fm.get("reply_to"),
                                                delivered=False, path=p, box=box,
                                                inbox_exists=os.path.isdir(os.path.join(FLEET, to, ".plans", "inbox"))
                                                or (to == "wayfare-skills")))
        msg["delivered"] = msg["delivered"] or delivered
        if delivered:
            msg["path"], msg["status"] = p, fm.get("status", msg["status"])
    for m in out.values():
        m.update(MESSAGE_OUTCOMES.get(m["id"], {}))
        m["state"] = ("Sent outside the mailbox" if m["type"] == "signal" else
                      "Not delivered: no inbox" if not m["delivered"] else
                      "Delivered, acted on" if m.get("shipped") else "Delivered, waiting")
    return sorted(out.values(), key=lambda m: (m["day"] or "", m["id"]))


ROLE = {"auth": "shared service", "design-system": "shared service", "hero-template": "template",
        "wayfare-skills": "plugin"}


def role(repo):
    return ROLE.get(repo, "app")


PROVIDES = {  # who provides what to whom: an ask to a provider travels up
    "auth": {"design-system", "hero-template", "aihero-steadfast", "elevate-commons", "aihero-wayfare", "website", "hiro"},
    "wayfare-skills": {"*"}, "hero-template": {"elevate-commons", "aihero-wayfare", "aihero-steadfast", "ah-cozy",
                                               "aihero-dokyu", "aihero-mehr", "hiro", "website", "auth"},
    "design-system": {"elevate-commons", "aihero-wayfare", "website", "hero-template", "auth", "hiro"},
}


def direction(sender, to):
    up = PROVIDES.get(to, set())
    down = PROVIDES.get(sender, set())
    if "*" in up or sender in up:
        return "up"
    if "*" in down or to in down:
        return "down"
    return "sideways"


@lru_cache(maxsize=None)
def packets():
    out = []
    for p in sorted(glob.glob(os.path.join(FLEET, "*", ".plans", ".feedback", "*.md"))):
        repo = p.split(os.sep)[-4]
        if repo in OUT_OF_SCOPE:
            continue
        m = re.match(r"(\d{4}-\d\d-\d\d)", os.path.basename(p))
        text = open(p, errors="replace").read()
        out.append(dict(repo=repo, day=m.group(1), path=p,
                        undelivered_tags=len(re.findall(r"\[undelivered\]", text)),
                        never=bool(re.search(r"never delivered", text, re.I))))
    return out


@lru_cache(maxsize=None)
def copied_items():
    """Work items with the same title in two repos where one repo owns the fix (not bumps)."""
    out = []
    for r in rows(con(), """SELECT lower(title) t, group_concat(repo, '|') repos, MIN(day) d FROM plans.plan_items
                            WHERE title IS NOT NULL GROUP BY lower(title) HAVING COUNT(DISTINCT repo) >= 2"""):
        if re.match(r"^bump |.*\bbump\b|dependabot|cve", r["t"]):
            continue
        repos = sorted(set(r["repos"].split("|")))
        owners = [x for x in repos if x in UPSTREAM]
        if owners and len(repos) == 2:
            out.append(dict(title=r["t"], repos=repos, owner=owners[0], day=r["d"]))
    return out


def sweeps():
    return [c for c in clusters() if not c["bot"] and c["n_repos"] >= 3 and c["spread_days"] <= 1]


# ------------------------------------------------------------------ A. the channels

def q_message_channels():
    ms = [m for m in messages() if m["day"]]
    ps, sw, ci = packets(), sweeps(), copied_items()
    cats = ["Design-feedback packets", "Items copied into the owning repo", "Mailbox messages", "One-pass sweeps"]
    ev = ([dict(day=p["day"], k=cats[0]) for p in ps] + [dict(day=c["day"], k=cats[1]) for c in ci] +
          [dict(day=m["day"], k=cats[2]) for m in ms] + [dict(day=s["day"], k=cats[3]) for s in sw])
    series = weekly_counts(ev, lambda e: e["k"], cats)
    by_repo = defaultdict(Counter)
    for p in ps:
        by_repo[p["repo"]]["Packets written"] += 1
    for m in ms:
        by_repo[m["sender"]]["Messages sent"] += 1
        by_repo[m["to"]]["Messages received"] += 1
    for c in ci:
        by_repo[c["owner"]]["Items copied in"] += 1
    inboxes = sorted(alias(os.path.basename(os.path.dirname(os.path.dirname(p))))
                     for p in glob.glob(os.path.join(FLEET, "*", ".plans", "inbox"))) + ["wayfare-skills"]
    first = lambda xs: min(x["day"] for x in xs) if xs else None
    return dict(weeks=WEEKS, series=series, totals={c: sum(v) for c, v in series.items()}, by_repo=by_repo,
                first={cats[0]: first(ps), cats[1]: first(ci), cats[2]: first(ms), cats[3]: first(sw)},
                broadcasts=sum(1 for m in ms if m.get("type") == "broadcast"), inboxes=sorted(set(inboxes)),
                n_packets=len(ps), n_messages=len(ms), n_sweeps=len(sw), n_copied=len(ci), copied=ci)


def q_message_direction():
    ms = messages()
    rowsm = [dict(m, dir=("reply" if m["type"] == "reply" else direction(m["sender"], m["to"]))) for m in ms]
    counts = Counter(r["dir"] for r in rowsm)
    sw = sweeps()
    sweep_from = Counter(s["first"]["repo"] if s["first"]["repo"] in UPSTREAM else "an app" for s in sw)
    return dict(messages=rowsm, counts=counts, n_packets=len(packets()), sweep_from=sweep_from, n_sweeps=len(sw))


def q_message_delivery():
    if not HAND_DATA:
        return UNAVAILABLE
    ms = messages()
    states = ["Delivered, acted on", "Delivered, waiting", "Not delivered: no inbox", "Sent outside the mailbox"]
    by_type = defaultdict(Counter)
    for m in ms:
        by_type["Replies" if m["type"] == "reply" else "Asks and bug reports"][m["state"]] += 1
    return dict(messages=ms, states=states, by_type=by_type, counts=Counter(m["state"] for m in ms),
                inboxes=q_message_channels()["inboxes"])


STAGES = ["Created", "In the recipient's inbox", "Acted on", "Shipped", "Acknowledged"]
KINDS = ["Asks", "Bug reports", "Replies"]


def mailbox_events():
    """Each message's dated comment lines, as the files record them: [(msg_id, day, who, text)]."""
    out = []
    for m in messages():
        for line in open(m["path"], errors="replace").read().split("## Comments", 1)[-1].splitlines():
            mm = re.match(r"^- (\d{4}-\d\d-\d\d) \(([^)]*)\):\s*(.*)", line)
            if mm:
                out.append((m["id"], mm.group(1), mm.group(2), mm.group(3)))
    return out


def q_message_delivery_funnel():
    """Stage reached by each message, by kind, with the failures at the delivery step and the days between stages."""
    if not HAND_DATA:
        return UNAVAILABLE
    ms = {m["id"]: m for m in messages()}
    rows_ = []
    for mid, ev in MESSAGE_EVENTS.items():
        m = ms.get(mid, {})
        kind = {"ask": KINDS[0], "bug": KINDS[1], "reply": KINDS[2]}.get(ev["type"], "Signal (outside the mailbox)")
        stages = [True, ev["delivered"] is not None, ev["accepted"] is not None, ev["shipped"] is not None,
                  ev["acknowledged"] is not None]
        rows_.append(dict(id=mid, kind=kind, sender=m.get("sender"), to=m.get("to"), **ev, stages=stages,
                          file_delivered=m.get("delivered"),
                          to_delivery=days(ev["created"], ev["delivered"]) if ev["delivered"] else None,
                          to_accept=days(ev["created"], ev["accepted"]) if ev["accepted"] else None,
                          to_ship=days(ev["created"], ev["shipped"]) if ev["shipped"] else None,
                          to_ack=days(ev["created"], ev["acknowledged"]) if ev["acknowledged"] else None))
    # cross-check the hand table against the files: a delivered message is one whose file sits in the recipient's inbox
    disagree = [r["id"] for r in rows_ if r["kind"] != "Signal (outside the mailbox)" and bool(r["delivered"]) != bool(r["file_delivered"])]
    funnel = {k: [sum(1 for r in rows_ if r["kind"] == k and r["stages"][i]) for i in range(len(STAGES))] for k in KINDS}
    failures = [(r["id"], r["kind"], r["failure"]) for r in rows_ if r["failure"]]
    lat = {k: {f: median([r[f] for r in rows_ if r["kind"] == k and r[f] is not None])
               for f in ("to_delivery", "to_accept", "to_ship", "to_ack")} for k in KINDS}
    return dict(rows=rows_, stages=STAGES, kinds=KINDS, funnel=funnel, failures=failures, latency=lat,
                n=len(rows_), n_mailbox=sum(1 for r in rows_ if r["kind"] in KINDS),
                undelivered=[r for r in rows_ if r["kind"] == KINDS[2] and not r["delivered"]],
                delayed=[r for r in rows_ if r["to_delivery"]],
                disagree=disagree, comments=len(mailbox_events()), duplicates=0, retries=0,
                asof=max(r["created"] for r in rows_))


def q_message_response_time():
    if not HAND_DATA:
        return UNAVAILABLE
    cases = [m for m in messages() if m.get("shipped")]
    for m in cases:
        m["to_first"] = days(m["day"], m["first"])
        m["to_ship"] = days(m["day"], m["shipped"])
    return dict(cases=cases, awaited=[m for m in cases if m["awaited"]], not_awaited=[m for m in cases if not m["awaited"]])


def q_cross_repo_finds():
    lab = labels("needs")
    day = {f"{r['repo']}#{r['item_id']}": r["day"] for r in rows(con(), "SELECT repo, item_id, day FROM plans.plan_items")}
    acts = ["message", "tracked", "changed", "handoff", "none"]
    names = {"message": "Message or packet (sent or planned)", "tracked": "Tracked it here", "changed": "Changed the other repo",
             "handoff": "Filed in its tracker", "none": "Stated, nothing done"}
    ev = []
    for k, v in lab.items():
        if v.get("need") and day.get(k):
            a = v.get("action") if v.get("action") in acts else "none"
            ev.append(dict(day=day[k], key=k, repo=k.split("#")[0], other=v.get("other"), action=names[a]))
    cats = [names[a] for a in acts]
    by_repo = defaultdict(Counter)
    for e in ev:
        by_repo[e["repo"]][e["action"]] += 1
    since = [e for e in ev if e["day"] >= "2026-09-13"]
    return dict(weeks=WEEKS, series=weekly_counts(ev, lambda e: e["action"], cats), cats=cats, events=ev,
                n=len(ev), n_items=len(lab), counts=Counter(e["action"] for e in ev), by_repo=by_repo,
                since_mailbox=Counter(e["action"] for e in since))


def q_message_fidelity():
    if not HAND_DATA:
        return UNAVAILABLE
    cases = q_message_response_time()["cases"]
    sets = Counter()
    for r in rows(con(), "SELECT repo, unit_id FROM detectors.cs_sets WHERE unit_kind IN ('pr','pr-squash')"):
        sets[(r["repo"], r["unit_id"])] += 1
    pr_of = {"m-ac7553": ("wayfare-skills", "119"), "m-f263bd": ("wayfare-skills", "119"), "m-a003ca": ("auth", "360"),
             "m-cc20e4": ("auth", "379"), "m-46d4a1": ("auth", None),
             "signal-auth-workspace-type-matching": ("auth", "364")}
    for m in cases:
        repo, pr = pr_of[m["id"]]
        m["sets"] = sets.get((repo, pr)) if pr else None
    return dict(cases=cases, outcomes=Counter(m["outcome"] for m in cases))


# ------------------------------------------------------------------ B. context across repos

SIB = "auth|design-system|hero-template|wayfare-skills|hero-skills|elevate-commons|aihero-wayfare|aihero-steadfast|" \
      "website|hiro|saga|infrastructure-environments|infrastructure-root|ah-cozy|aihero-dokyu|aihero-mehr|pterodactyl"
PATH_RE = re.compile(r"(?:\.\./|workspaces/aihero/|ai-hero/|plugins/)(" + SIB + r")\b")
FLEET_RE = re.compile(r"FLEET\.md")
BOX_RE = re.compile(r"\.plans/inbox|\bmailbox\b|hero_msg_|\bmsg_id\b")


def q_sibling_awareness():
    skip = scripted_sessions()
    sess = {r["session_id_hash"]: r for r in rows(con(), "SELECT session_id_hash, repo, day FROM harness.sessions")
            if r["session_id_hash"] not in skip}
    flags = defaultdict(set)
    for r in con().execute("SELECT session_id_hash s, text_redacted t FROM harness.turns WHERE text_redacted IS NOT NULL"):
        s = sess.get(r["s"])
        if not s:
            continue
        if any(alias(m) != s["repo"] for m in PATH_RE.findall(r["t"])):
            flags[r["s"]].add("Names a sibling's path")
        if FLEET_RE.search(r["t"]):
            flags[r["s"]].add("Reads the fleet map")
        if BOX_RE.search(r["t"]):
            flags[r["s"]].add("Uses the mailbox")
    cats = ["Names a sibling's path", "Reads the fleet map", "Uses the mailbox"]
    wk = defaultdict(lambda: Counter())
    n = Counter()
    for sid, s in sess.items():
        if not s["day"] or s["repo"] in OUT_OF_SCOPE:
            continue
        w = week_of(s["day"])
        n[w] += 1
        for f in flags.get(sid, ()):
            wk[w][f] += 1
        if flags.get(sid):
            wk[w]["any"] += 1
    share = {c: [(wk[w][c] / n[w]) if n[w] >= 5 and w not in GAP_WEEKS else None for w in WEEKS]
             for c in cats + ["any"]}
    by_repo = defaultdict(lambda: [0, 0])
    for sid, s in sess.items():
        by_repo[s["repo"]][1] += 1
        by_repo[s["repo"]][0] += bool(flags.get(sid))
    total = sum(n.values())
    return dict(weeks=WEEKS, share=share, cats=cats, n_sessions=total, n_scripted=len(skip), n_flagged=sum(1 for v in flags.values() if v),
                counts=Counter(f for v in flags.values() for f in v),
                by_repo={r: v for r, v in by_repo.items() if v[1] >= 5 and r not in OUT_OF_SCOPE})


def pr_links():
    """PR links from interactive sessions only (agent_harness's scripted filter)."""
    out = []
    skip = scripted_sessions()
    for r in rows(con(), "SELECT session_id_hash, repo, day, first_ts, last_ts, pr_links FROM harness.sessions"):
        if r["session_id_hash"] in skip:
            continue
        for l in json.loads(r["pr_links"] or "[]"):
            m = re.match(r"[\w.-]+/([\w.-]+)#(\d+)", l)
            if m:
                out.append(dict(session=r["session_id_hash"], repo=r["repo"], day=r["day"], first=r["first_ts"],
                                last=r["last_ts"], target=alias(m.group(1)), pr=int(m.group(2))))
    return out


def q_cross_repo_edits():
    created = {(r["repo"], r["number"]): r["created_ts"] for r in rows(con(), "SELECT repo, number, created_ts FROM github.prs")}
    by_session = defaultdict(lambda: dict(targets=set(), created=set()))
    for l in pr_links():
        if l["target"] == l["repo"] or l["target"] in OUT_OF_SCOPE:
            continue
        s = by_session[l["session"]]
        s.update(repo=l["repo"], day=l["day"])
        s["targets"].add(l["target"])
        c = created.get((l["target"], l["pr"]))
        if c and l["first"] and l["last"] and l["first"][:10] <= c[:10] <= l["last"][:10]:
            s["created"].add(l["target"])
    ev = []
    for sid, s in by_session.items():
        if not s["created"]:
            continue
        kind = "Fan-out: 3+ other repos" if len(s["created"]) >= 3 else "Direct: 1–2 other repos"
        ev.append(dict(day=s["day"], repo=s["repo"], targets=sorted(s["created"]), kind=kind, sid=sid))
    cats = ["Direct: 1–2 other repos", "Fan-out: 3+ other repos"]
    pairs = Counter((e["repo"], t) for e in ev for t in e["targets"])
    direct = [e for e in ev if e["kind"] == cats[0]]
    series = weekly_counts(ev, lambda e: e["kind"], cats)
    series = blank_gap({k: [v if w >= "2026-W32" else None for w, v in zip(WEEKS, vals)] for k, vals in series.items()})
    return dict(weeks=WEEKS, series=series, cats=cats, events=ev,
                n_sessions=len(rows(con(), "SELECT 1 FROM harness.sessions")) - len(scripted_sessions()),
                n_scripted=len(scripted_sessions()),
                direct_before=sum(1 for e in direct if e["day"] < "2026-09-13"),
                direct_after=sum(1 for e in direct if e["day"] >= "2026-09-13"),
                fan_before=sum(1 for e in ev if e["kind"] == cats[1] and e["day"] < "2026-09-13"),
                fan_after=sum(1 for e in ev if e["kind"] == cats[1] and e["day"] >= "2026-09-13"),
                pairs=pairs, linked_only=sum(1 for s in by_session.values() if not s["created"]))


# ------------------------------------------------------------------ C. changes that go fleet-wide

ORIGINS = ["One-pass sweep", "Upstream first, adopted later", "App first, upstream later", "App to app, no upstream",
           "Dependabot, each repo on its own"]


def origin_of(c):
    if c["bot"]:
        return ORIGINS[4]
    if c["n_repos"] >= 3 and c["spread_days"] <= 1:
        return ORIGINS[0]
    if c["first"]["repo"] in UPSTREAM:
        return ORIGINS[1]
    if any(r in UPSTREAM for r in c["repos"]):
        return ORIGINS[2]
    return ORIGINS[3]


def q_upstream_vs_local_changes_same_change():
    cs = clusters()
    for c in cs:
        c["kind"] = origin_of(c)
    series = weekly_counts(cs, lambda c: c["kind"], ORIGINS)
    counts = Counter(c["kind"] for c in cs)
    commits_by = Counter()
    for c in cs:
        commits_by[c["kind"]] += len(c["arrival"])
    top = sorted((c for c in cs if not c["bot"]), key=lambda c: (-c["n_repos"], c["day"]))[:12]
    d3 = rows(con(), "SELECT lag_hours FROM detectors.propagation")
    return dict(weeks=WEEKS, series=series, counts=counts, repo_landings=commits_by, top=top, n=len(cs),
                d3_n=len(d3), d3_under_day=sum(1 for r in d3 if r["lag_hours"] < 24),
                d7_clusters=rows(con(), "SELECT COUNT(DISTINCT cluster_id) n FROM detectors.duplicate_fixes")[0]["n"])


def q_upstream_change_reach_lag():
    arrivals = []
    for c in clusters():
        k = origin_of(c)
        if k not in (ORIGINS[0], ORIGINS[1]) or c["first"]["repo"] not in UPSTREAM:
            continue
        for repo, m in c["arrival"].items():
            if repo == c["first"]["repo"]:
                continue
            arrivals.append(dict(day=c["day"], month=c["day"][:7], repo=repo, lag=days(c["day"], m["day"]), kind=k,
                                 subject=c["first"]["subject"]))
    later = [a for a in arrivals if a["kind"] == ORIGINS[1]]
    buckets = ["Same or next day", "2–7 days", "8+ days"]
    bucket = lambda a: buckets[0] if a["lag"] <= 1 else buckets[1] if a["lag"] <= 7 else buckets[2]
    weekly = weekly_counts(arrivals, bucket, buckets)
    med = {m: median([a["lag"] for a in later if a["month"] == m]) for m in MONTHS}
    mx = {m: max([a["lag"] for a in later if a["month"] == m], default=None) for m in MONTHS}
    same_day = sum(1 for a in arrivals if a["lag"] <= 1)
    by_repo = defaultdict(list)
    for a in later:
        by_repo[a["repo"]].append(a["lag"])
    v = q_vendored_file_staleness()
    return dict(months=MONTHS, median=[med[m] for m in MONTHS], max=[mx[m] for m in MONTHS], arrivals=arrivals,
                weeks=WEEKS, weekly=weekly, buckets=buckets, bucket_counts=Counter(bucket(a) for a in arrivals),
                max_lag=max((a["lag"] for a in arrivals), default=None),
                later=later, n=len(arrivals), same_day=same_day, overall_median=median([a["lag"] for a in later]),
                by_repo={r: median(l) for r, l in by_repo.items()}, by_repo_n={r: len(l) for r, l in by_repo.items()},
                never=v["never"])


VENDORED = {  # asset: (source paths in wayfare-skills, consumer paths)
    "comments rule": (["/.claude/rules/comments.md"], [".claude/rules/comments.md"]),
    "design-system rule": (["assets/design-system/rules/design-system.md"], [".claude/rules/design-system.md"]),
    "design-token hook": (["assets/design-system/hooks/check-design-tokens.sh"], [".claude/hooks/check-design-tokens.sh"]),
    "design-token hook test": (["assets/design-system/hooks/check-design-tokens.test.sh"],
                               [".claude/hooks/check-design-tokens.test.sh"]),
    "auto-approve workflow": ([".github/workflows/auto-approve.yml", "assets/auto-approve/caller.yml",
                               "assets/auto-approve/caller.yaml"],
                              [".github/workflows/auto-approve.yml", ".github/workflows/auto-approve.yaml"]),
}
def D_utc(ts):
    from datetime import datetime, timezone
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


VSTATES = ["Current", "Stale: an older fleet version", "Own copy: edited or pre-dates the source"]


@lru_cache(maxsize=None)
def q_vendored_file_staleness():
    """Per asset and repo, each week-end's state. A 'fleet version' is any blob the source held, plus any blob
    three or more consumers adopted on one day (a sweep that re-vendored a transformed copy)."""
    blobs = rows(con(), "SELECT repo, ts, day, path, new_blob, status FROM messages.blobs WHERE day <= ? ORDER BY ts", (LATEST,))
    week_end = {w: (date.fromisocalendar(int(w[:4]), int(w[6:]), 7)).isoformat() for w in WEEKS}
    series = {s: [0] * len(WEEKS) for s in VSTATES}
    stale_by_asset = {a: [0] * len(WEEKS) for a in VENDORED}
    per_repo = defaultdict(lambda: Counter())
    never, events, now = [], [], []
    for asset, (src, dst) in VENDORED.items():
        src = [s.lstrip("/") for s in src]
        # From 4 Aug consumers carry the caller, not the plugin's own workflow, so the plugin's workflow stops being
        # a version they should hold.
        versions = [(b["ts"], b["new_blob"]) for b in blobs if b["repo"] == "wayfare-skills" and b["path"] in src
                    and b["status"] != "D" and not (b["path"].startswith(".github/") and b["day"] >= "2026-08-04")]
        adopt, adopt_ts = defaultdict(set), {}
        for b in blobs:
            if b["repo"] != "wayfare-skills" and b["path"] in dst and b["status"] != "D":
                adopt[(b["day"], b["new_blob"])].add(b["repo"])
                adopt_ts[(b["day"], b["new_blob"])] = min(adopt_ts.get((b["day"], b["new_blob"]), b["ts"]), b["ts"])
        versions += [(adopt_ts[k], k[1]) for k, rs in adopt.items() if len(rs) >= 3]
        versions.sort(key=lambda v: D_utc(v[0]))
        first_ts = {}
        for t, bl in versions:
            first_ts.setdefault(bl, t)
        first_seen = {bl: t[:10] for bl, t in first_ts.items()}
        order = sorted(first_ts, key=lambda bl: D_utc(first_ts[bl]))
        for d, bl in sorted(first_seen.items(), key=lambda t: t[1]):
            events.append((d, asset))
        repos = {b["repo"] for b in blobs if b["repo"] != "wayfare-skills" and b["path"] in dst}
        for repo in sorted(repos):
            if repo in OUT_OF_SCOPE:
                continue
            hist = [(b["day"], None if b["status"] == "D" else b["new_blob"]) for b in blobs
                    if b["repo"] == repo and b["path"] in dst]
            for i, w in enumerate(WEEKS):
                end = week_end[w]
                cur = None
                for d, bl in hist:
                    if d <= end:
                        cur = bl
                if cur is None:
                    continue
                known = [bl for bl in order if first_seen[bl] <= end]
                if not known:
                    continue
                st = VSTATES[0] if cur == known[-1] else VSTATES[1] if cur in known else VSTATES[2]
                series[st][i] += 1
                stale_by_asset[asset][i] += st == VSTATES[1]
                per_repo[repo][st] += 1
            latest = order[-1]
            if hist and hist[-1][1] is not None:
                cur = hist[-1][1]
                now.append(dict(asset=asset, repo=repo,
                                state=VSTATES[0] if cur == latest else VSTATES[1] if cur in order else VSTATES[2],
                                behind_since=first_seen[latest] if cur != latest else None))
        latest = order[-1] if order else None
        missing = [n["repo"] for n in now if n["asset"] == asset and n["state"] != VSTATES[0]]
        if latest:
            never.append(dict(asset=asset, since=first_seen[latest], missing=missing,
                              holders=sum(1 for n in now if n["asset"] == asset)))
    return dict(weeks=WEEKS, series=series, stale_by_asset=stale_by_asset, now=now, never=never, per_repo=per_repo, source_changes=events,
                now_counts=Counter(n["state"] for n in now))


def q_fan_out_method_carrier():
    links = defaultdict(set)
    for l in pr_links():
        links[(l["target"], l["pr"])].add((l["session"], l["repo"]))
    items = defaultdict(set)
    for r in rows(con(), "SELECT repo, lower(title) t FROM plans.plan_items WHERE title IS NOT NULL"):
        items[r["t"]].add(r["repo"])
    cats = ["One session carried it", "Several sessions, one per repo", "No session linked", "Before session logs",
            "Session data not available"]
    out = []
    for c in clusters():
        if c["bot"]:
            continue
        prs = [(m["repo"], m["pr"]) for m in c["arrival"].values() if m["pr"]]
        ss = [links.get(p, set()) for p in prs]
        if c["day"] < SESSIONS_FROM:
            k = cats[3]
        elif in_gap(c["day"]):
            k = cats[4]
        elif not any(ss):
            k = cats[2]
        else:
            allS = set().union(*ss)
            best = max(allS, key=lambda s: sum(s in x for x in ss))
            share = sum(best in x for x in ss) / len(prs)
            k = cats[0] if share >= 0.6 else cats[1]
            c["hub"] = best[1] if k == cats[0] else None
        c["carrier"] = k
        out.append(c)
    series = weekly_counts(out, lambda c: c["carrier"], cats)
    spread = {k: median([c["spread_days"] for c in out if c["carrier"] == k]) for k in cats}
    hubs = Counter(c.get("hub") for c in out if c.get("hub"))
    fanned_items = [(t, rs) for t, rs in items.items() if len(rs) >= 3 and not re.search(r"\bbump\b", t)]
    return dict(weeks=WEEKS, series=series, cats=cats, counts=Counter(c["carrier"] for c in out), spread=spread,
                hubs=hubs, n=len(out), fanned_items=fanned_items,
                repos_by={k: median([c["n_repos"] for c in out if c["carrier"] == k]) for k in cats})


def q_fan_out_review_review():
    rv = defaultdict(list)
    for r in rows(con(), "SELECT repo, number, reviewer, reviewer_is_bot, state FROM github.pr_reviews"):
        rv[(r["repo"], r["number"])].append(r)
    prs = rows(con(), "SELECT repo, number, day, author_is_bot FROM github.prs WHERE merged_ts IS NOT NULL")
    fu = {(r["repo"], r["number"]): r for r in rows(con(), "SELECT * FROM detectors.followups")}
    sweep_prs = {}
    for c in clusters():
        if c["bot"] or c["n_repos"] < 3:
            continue
        for m in c["arrival"].values():
            if m["pr"]:
                sweep_prs[(m["repo"], m["pr"])] = c
    kinds = ["Owner's account reviewed", "Auto-approve only", "No review recorded"]

    def kind(key):
        rs = rv.get(key, [])
        if any(r["reviewer"] == "rparundekar" for r in rs):
            return kinds[0]
        if any(r["reviewer"] == "github-actions" for r in rs):
            return kinds[1]
        return kinds[2]

    groups = {"PRs in a multi-repo change": Counter(), "Other PRs": Counter()}
    ev = []
    for p in prs:
        if p["author_is_bot"] or p["repo"] in OUT_OF_SCOPE or p["day"] < "2026-07-01":
            continue
        key = (p["repo"], p["number"])
        g = "PRs in a multi-repo change" if key in sweep_prs else "Other PRs"
        k = kind(key)
        groups[g][k] += 1
        if g == "PRs in a multi-repo change":
            ev.append(dict(day=p["day"], kind=k))
    # a corrective change: another multi-repo change within 7 days touching the same paths
    _, files = commits()
    multi = [c for c in clusters() if not c["bot"] and c["n_repos"] >= 3]
    def core(c):
        # the paths most of its repos touched: a shared package.json or AGENTS.md alone does not make two changes one
        n = Counter(p for r, m in c["arrival"].items() for p in {p for p, _ in files[(m["repo"], m["sha"])]})
        return {p for p, k in n.items() if k >= max(2, c["n_repos"] / 2)}

    corrected = []
    for c in multi:
        nxt = [d for d in multi if d is not c and 0 < days(c["day"], d["day"]) <= 7 and core(c) & core(d)]
        if nxt:
            corrected.append((c, nxt[0], sorted(core(c) & core(nxt[0]))))
    fu_rate = {}
    for g, keys in (("PRs in a multi-repo change", [k for k in sweep_prs]),
                    ("Other PRs", [(p["repo"], p["number"]) for p in prs if (p["repo"], p["number"]) not in sweep_prs
                                   and not p["author_is_bot"] and p["day"] >= "2026-07-01"])):
        have = [fu[k] for k in keys if k in fu]
        fu_rate[g] = (sum(1 for f in have if f["followup_within_7d_days"] is not None) / len(have), len(have)) if have else (None, 0)
    return dict(groups=groups, kinds=kinds, weeks=WEEKS, series=weekly_counts(ev, lambda e: e["kind"], kinds),
                n_multi=len(multi), corrected=corrected, fu_rate=fu_rate)


# ------------------------------------------------------------------ D. shared references

REF_KINDS = ["Local copy of the workflow", "Pinned to a commit", "Tag (can move)", "Branch @main (moves)"]


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, repo + ".git"), *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout


def q_shared_piece_references():
    repos = [os.path.basename(p)[:-4] for p in glob.glob(os.path.join(MIRRORS, "*.git"))]
    weeks = WEEKS
    series = {k: [0] * len(weeks) for k in REF_KINDS}
    targets = defaultdict(lambda: Counter())
    for repo in repos:
        if repo == "wayfare-skills" or repo in OUT_OF_SCOPE:
            continue
        for i, w in enumerate(weeks):
            end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
            rev = git(repo, "rev-list", "-1", "--first-parent", f"--before={end}T23:59:59", "HEAD").strip()
            if not rev:
                continue
            files = [f for f in git(repo, "ls-tree", "-r", "--name-only", rev, ".github/workflows").split("\n") if f]
            for f in files:
                text = git(repo, "show", f"{rev}:{f}")
                uses = re.findall(r"uses:\s*ai-hero/([\w.-]+)/([^@\s]+)@(\S+)", text)
                for tgt, path, ref in uses:
                    k = (REF_KINDS[1] if re.fullmatch(r"[0-9a-f]{40}", ref) else
                         REF_KINDS[3] if ref in ("main", "master") else REF_KINDS[2])
                    series[k][i] += 1
                    if w == weeks[-1]:
                        targets[f"{alias(tgt)}: {os.path.basename(path)}"][k] += 1
                if re.search(r"auto-approve\.ya?ml$", f) and not uses and "anthropic" in text.lower():
                    series[REF_KINDS[0]][i] += 1
                    if w == weeks[-1]:
                        targets["wayfare-skills: auto-approve (copied)"][REF_KINDS[0]] += 1
    return dict(weeks=weeks, series=series, targets=targets, now={k: v[-1] for k, v in series.items()})


def q_upstream_breaks_breaks():
    lab = labels("breaks")
    facts = {f"{f['repo']}|{f['unit_kind']}|{f['unit_id']}|{f['set_idx']}": f for f in changeset_facts(con())}
    ev = []
    for k, v in lab.items():
        f = facts.get(k)
        if not f or v.get("cause") != "upstream_change":
            continue
        ev.append(dict(day=f["day"], repo=f["repo"], upstream=v.get("upstream") or "unclear", via=v.get("via") or "other",
                       label=f["label"], pr=f["pr"]))
    # CI-workflow breakage belongs to report/deployment, third-party dependency fixes are not a fleet upstream, and the plugin's
    # auto-approve workflow is CI whatever the model called it.
    non_ci = [e for e in ev if e["via"] not in ("ci_workflow", "dependency") and e["upstream"] != "unclear"
              and not re.search(r"auto-approve", e["label"], re.I)]
    ups = ["auth", "design-system", "hero-template", "wayfare-skills"]
    by_repo = defaultdict(Counter)
    for e in non_ci:
        by_repo[e["repo"]][e["upstream"]] += 1
    same_day = Counter((e["day"], e["upstream"]) for e in non_ci)
    return dict(weeks=WEEKS, series=weekly_counts(non_ci, lambda e: e["upstream"], ups), max_same_day=max(same_day.values(), default=0),
                ups=ups, n_labelled=len(lab), n=len(non_ci), n_excluded=len(ev) - len(non_ci), events=non_ci,
                by_up=Counter(e["upstream"] for e in non_ci), via=Counter(e["via"] for e in non_ci), by_repo=by_repo)


def q_upstream_impact_notes_names():
    lab = labels("names")
    pr = {f"{r['repo']}#{r['number']}": r for r in rows(con(), "SELECT repo, number, day, month, title FROM github.prs")}
    ev = []
    for k, v in lab.items():
        p = pr.get(k)
        if p and v.get("affects"):
            ev.append(dict(day=p["day"], month=p["month"], repo=p["repo"], breaking=bool(v.get("breaking")),
                           names=bool(v.get("names")), title=p["title"], number=p["number"]))
    share = {}
    for up in UPSTREAM:
        share[up] = [None if (n := [e for e in ev if e["repo"] == up and e["month"] == m]).__len__() < 3
                     else sum(e["names"] for e in n) / len(n) for m in MONTHS]
    by = {up: dict(affects=sum(1 for e in ev if e["repo"] == up),
                   breaking=sum(1 for e in ev if e["repo"] == up and e["breaking"]),
                   names=sum(1 for e in ev if e["repo"] == up and e["names"]),
                   total=sum(1 for k in lab if k.startswith(up + "#"))) for up in UPSTREAM}
    br = [e for e in ev if e["breaking"]]
    return dict(months=MONTHS, share=share, by=by, n=len(lab), n_affects=len(ev),
                named=sum(e["names"] for e in ev), breaking=len(br), breaking_named=sum(e["names"] for e in br),
                events=ev)


# ------------------------------------------------------------------ E. shared knowledge

def q_cross_repo_decision_agreement():
    lab = labels("decisions").get("all") or []
    ds = {r["id"]: r for r in rows(con(), "SELECT rowid AS id, repo, heading, first_seen_ts FROM knowledge.design_decisions")}
    topics = []
    for t in lab if isinstance(lab, list) else []:
        ids = [i for i in t.get("ids", []) if i in ds]
        repos = sorted({ds[i]["repo"] for i in ids})
        if len(repos) < 2:
            continue
        first = sorted((ds[i]["first_seen_ts"] or "")[:10] for i in ids)
        topics.append(dict(topic=t.get("topic"), verdict=t.get("verdict"), why=t.get("why"), repos=repos,
                           ids=ids, first=first[0], last=first[-1], headings=[f"[{ds[i]['repo']}] {ds[i]['heading']}" for i in ids]))
    per_repo = Counter(r["repo"] for r in ds.values())
    ev = [dict(day=(ds[i]["first_seen_ts"] or "")[:10], verdict=t["verdict"]) for t in topics for i in t["ids"]
          if ds[i]["first_seen_ts"]]
    held = Counter(r for t in topics for r in t["repos"])
    return dict(topics=topics, held=held, weeks=WEEKS,
                series=weekly_counts(ev, lambda e: e["verdict"].capitalize(), ["Agree", "Partly", "Conflict"]), verdicts=Counter(t["verdict"] for t in topics), n_decisions=len(ds), per_repo=per_repo,
                repos=len(per_repo))




def q_ownership_handovers():
    if not HAND_DATA:
        return UNAVAILABLE
    return dict(moves=MOVES, both=sum(1 for m in MOVES if m["old_says"] == "yes" and m["new_says"] == "yes"),
                new_only=sum(1 for m in MOVES if m["new_says"] == "yes" and m["old_says"] != "yes"),
                neither=sum(1 for m in MOVES if m["new_says"] != "yes" and m["old_says"] != "yes"))


def all_data():
    return {f.__name__: f() for f in (q_message_channels, q_message_direction, q_message_delivery, q_message_delivery_funnel, q_message_response_time, q_cross_repo_finds,
                                       q_message_fidelity, q_sibling_awareness, q_cross_repo_edits, q_upstream_vs_local_changes_same_change, q_upstream_change_reach_lag,
                                       q_vendored_file_staleness, q_fan_out_method_carrier, q_fan_out_review_review, q_shared_piece_references, q_upstream_breaks_breaks,
                                       q_upstream_impact_notes_names, q_cross_repo_decision_agreement, q_ownership_handovers)}


if __name__ == "__main__":
    import pprint
    names = sys.argv[1:]
    for name, fn in list(globals().items()):
        if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__ and (not names or name in names):
            x = fn()
            slim = {k: v for k, v in x.items() if k not in ("weeks", "months", "events", "members")}
            print(f"== {name}")
            pprint.pprint(slim, width=160, compact=True, depth=3)
