"""The harness model labels -> .analysis/data/agent_harness.sqlite, tables collision_turns and fix_pairs.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/agent_harness/labels.py [collisions|fixes]

collision_turns: a regex picks main-thread turns (owner or agent) that mention another session, a
shared checkout or unexpected changes; Haiku says whether each records a collision between sessions
in one checkout.
fix_pairs: for each merged PR, the fix commits on main within 14 days that touch half or more of
its files; Haiku says whether the fix repairs something that PR shipped (file overlap alone is
mostly unrelated fixes to the same small files).
Both are cached by content hash, so a re-run labels only what is new.
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "detectors"))
import d1_changesets as D1  # noqa: E402
from ingest.fleet import OUT  # noqa: E402

DB = os.path.join(OUT, "agent_harness.sqlite")
HARNESS = os.path.join(OUT, "harness.sqlite")
BATCH = 30

CANDIDATE = re.compile(
    r"another (claude |agent |session|conversation)|other session|other agent|parallel session|concurrent session|"
    r"same (working tree|checkout|worktree)|shared checkout|primary checkout|someone else|not mine|isn.t mine|"
    r"uncommitted changes|unexpected (change|branch|commit)|switched branch|branch (was|got) switched|"
    r"changed underneath|under (me|us)\b|stash", re.I)

HEADER = """You read excerpts from coding-agent sessions. Several agent sessions can work in the same git
checkout of a repo at once. For each excerpt (id given), decide what it records:
  "collision"    - another session's or agent's work in the SAME checkout actually interfered: mixed or
                   foreign uncommitted changes, a branch switched underneath, work overwritten or lost,
                   a commit that picked up another session's files, a conflict caused by a parallel session.
  "avoided"      - the agent noticed another session working in the same checkout (or was told so) and
                   stopped, waited, or isolated itself (e.g. moved to a git worktree) BEFORE interference.
  "own_parallel" - interference among the agent's OWN parallel branches or subagents, not another session.
  "none"         - anything else: generic mentions, documentation or skill text being edited, git stash as a
                   routine step, code review of text that merely contains these words.
Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"kind": "collision|avoided|own_parallel|none", "why": "<at most 12 words>"}, ...}

Excerpts:
"""


def excerpt(text):
    m = CANDIDATE.search(text)
    a = max(0, m.start() - 450)
    return text[a:a + 900].replace("\n", " ")


def build():
    h = sqlite3.connect(HARNESS)
    rows = [(s, ts, role, t) for s, ts, role, t in h.execute(
        "SELECT session_id_hash, ts, role, text_redacted FROM turns WHERE text_redacted IS NOT NULL")
        if CANDIDATE.search(t)]
    d = sqlite3.connect(DB)
    d.execute("CREATE TABLE IF NOT EXISTS collision_cache (h TEXT PRIMARY KEY, kind TEXT, why TEXT)")
    items = {}
    for s, ts, role, t in rows:
        x = f"[{role}] {excerpt(t)}"
        items[hashlib.sha256(x.encode()).hexdigest()] = x
    cached = {r[0] for r in d.execute("SELECT h FROM collision_cache")}
    todo = [(k, v) for k, v in items.items() if k not in cached]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def one(batch):
        ids = {str(i + 1): k for i, (k, _) in enumerate(batch)}
        texts = [f"id {i + 1}: {v}" for i, (_, v) in enumerate(batch)]
        out, cost = D1.call_haiku(texts, model="haiku", header=HEADER)
        return [(ids[i], str(v.get("kind", "none")), str(v.get("why", ""))[:200])
                for i, v in (out or {}).items() if i in ids and isinstance(v, dict)], cost

    total = 0.0
    with ThreadPoolExecutor(6) as ex:
        for labels, cost in ex.map(one, batches):
            total += cost
            d.executemany("INSERT OR REPLACE INTO collision_cache VALUES (?,?,?)", labels)
            d.commit()
    d.execute("DROP TABLE IF EXISTS collision_turns")
    d.execute("CREATE TABLE collision_turns (session_id_hash TEXT, ts TEXT, role TEXT, h TEXT, kind TEXT, why TEXT, "
              "excerpt TEXT)")
    tags = {r[0]: r[1:] for r in d.execute("SELECT * FROM collision_cache")}
    for s, ts, role, t in rows:
        x = f"[{role}] {excerpt(t)}"
        k = hashlib.sha256(x.encode()).hexdigest()
        kind, why = tags.get(k, (None, None))
        d.execute("INSERT INTO collision_turns VALUES (?,?,?,?,?,?,?)", (s, ts, role, k, kind, why, x))
    d.execute("CREATE TABLE IF NOT EXISTS spend (step TEXT PRIMARY KEY, usd REAL)")
    prev = d.execute("SELECT usd FROM spend WHERE step='collisions'").fetchone()
    d.execute("INSERT OR REPLACE INTO spend VALUES ('collisions', ?)", ((prev[0] if prev else 0) + total,))
    d.commit()
    print(f"collision_turns: {len(rows)} candidates, {len(todo)} newly labelled, ${total:.2f}")


FIX_HEADER = """Each item pairs a merged pull request with a later fix commit in the same repo that touched
many of the same files. Decide whether the fix commit repairs a defect, omission or mistake that
the pull request itself introduced or shipped (true), or is an unrelated fix that merely touched
the same files (false). Judge from the titles, bodies and shared files only.
Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"fixes": true|false, "why": "<at most 12 words>"}, ...}

Items:
"""


def fixes():
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.dirname(HERE))
    from cube.db import connect
    import data as D
    con = connect()
    pairs = []
    for p in D.pr_models(con):
        if not p["candidates"]:
            continue
        pr = con.execute("SELECT title, body_redacted FROM github.prs WHERE repo=? AND number=?",
                         (p["repo"], p["pr"])).fetchone()
        for c in p["candidates"]:
            body = con.execute("SELECT body_redacted FROM git.commits WHERE repo=? AND sha=?",
                               (p["repo"], c["sha"])).fetchone()[0] or ""
            text = (f"PR: {pr['title']}\nPR body: {(pr['body_redacted'] or '')[:600]}\n"
                    f"Fix commit ({c['days']} days later): {c['subject']}\nFix body: {body[:500]}\n"
                    f"Shared files: {', '.join(c['shared'][:8])}").replace("\n", " | ")
            pairs.append((p["repo"], p["pr"], c["sha"], text))
    d = sqlite3.connect(DB)
    d.execute("CREATE TABLE IF NOT EXISTS fix_cache (h TEXT PRIMARY KEY, fixes INTEGER, why TEXT)")
    key = lambda t: hashlib.sha256(t.encode()).hexdigest()
    cached = {r[0] for r in d.execute("SELECT h FROM fix_cache")}
    todo = list({key(t): t for *_, t in pairs if key(t) not in cached}.items())
    batches = [todo[i:i + 20] for i in range(0, len(todo), 20)]

    def one(batch):
        ids = {str(i + 1): k for i, (k, _) in enumerate(batch)}
        out, cost = D1.call_haiku([f"id {i + 1}: {t}" for i, (_, t) in enumerate(batch)], model="haiku",
                                  header=FIX_HEADER)
        return [(ids[i], int(bool(v.get("fixes"))), str(v.get("why", ""))[:200])
                for i, v in (out or {}).items() if i in ids and isinstance(v, dict)], cost

    total = 0.0
    with ThreadPoolExecutor(6) as ex:
        for labels, cost in ex.map(one, batches):
            total += cost
            d.executemany("INSERT OR REPLACE INTO fix_cache VALUES (?,?,?)", labels)
            d.commit()
    tags = {r[0]: r[1:] for r in d.execute("SELECT * FROM fix_cache")}
    d.execute("DROP TABLE IF EXISTS fix_pairs")
    d.execute("CREATE TABLE fix_pairs (repo TEXT, pr INTEGER, sha TEXT, fixes INTEGER, why TEXT)")
    d.executemany("INSERT INTO fix_pairs VALUES (?,?,?,?,?)",
                  [(r, n, sha, *tags[key(t)]) for r, n, sha, t in pairs if key(t) in tags])
    d.execute("CREATE TABLE IF NOT EXISTS spend (step TEXT PRIMARY KEY, usd REAL)")
    prev = d.execute("SELECT usd FROM spend WHERE step='fixes'").fetchone()
    d.execute("INSERT OR REPLACE INTO spend VALUES ('fixes', ?)", ((prev[0] if prev else 0) + total,))
    d.commit()
    print(f"fix_pairs: {len(pairs)} pairs, {len(todo)} newly judged, ${total:.2f}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("collisions", "all"):
        build()
    if step in ("fixes", "all"):
        fixes()
