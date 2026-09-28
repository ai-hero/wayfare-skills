# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


"""Manager's thinking inputs that are not in the shared databases: the register's history read from
git, and the Haiku labels this topic needs. Everything lands in .analysis/data/manager.sqlite.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/manager/labels.py [register|gate|ws|memory|all]

Labels are cached by content hash in `labels`, so a rerun only pays for new texts.
"""
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ANALYSIS)
from detectors.d1_changesets import call_haiku  # noqa: E402

DB = os.path.join(os.path.dirname(ANALYSIS), ".analysis", "data", "manager.sqlite")
FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
PLUGIN = os.path.dirname(ANALYSIS)


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS labels (task TEXT, key TEXT, hash TEXT, label_json TEXT, "
                "PRIMARY KEY (task, key))")
    con.execute("CREATE TABLE IF NOT EXISTS spend (task TEXT, usd REAL)")
    return con


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout


# ------------------------------------------------------------------ register history

ID_RE = re.compile(r"^- id: *(\S+)", re.M)


def blocks(text):
    """{id: block text} for a CONTROLS/CHECKS yaml, without a yaml parser (early versions don't all parse)."""
    out = {}
    starts = [(m.start(), m.group(1)) for m in ID_RE.finditer(text)]
    for i, (pos, cid) in enumerate(starts):
        out[cid] = text[pos: starts[i + 1][0] if i + 1 < len(starts) else len(text)]
    return out


def register_history(con):
    sources = [("hero-template", os.path.join(FLEET, "hero-template"), ""), (".fleet", os.path.join(FLEET, ".fleet"), ""),
               ("wayfare-skills", PLUGIN, "assets/compliance/")]
    first, latest, commits = {}, {}, []
    for name, path, sub in sources:
        log = git(path, "log", "--reverse", "--format=%H%x09%ad%x09%s", "--date=short", "--", sub + "CONTROLS.yaml",
                  sub + "CHECKS.yaml")
        for line in log.splitlines():
            sha, day, subject = line.split("\t", 2)
            added = []
            for fname, kind in (("CONTROLS.yaml", "control"), ("CHECKS.yaml", "check")):
                text = git(path, "show", f"{sha}:{sub}{fname}")
                for cid, blk in blocks(text).items():
                    latest[(kind, cid)] = blk
                    if (kind, cid) not in first:
                        first[(kind, cid)] = (day, name, sha, subject)
                        added.append(cid)
            commits.append((name, sha, day, subject, len(added)))
    con.execute("DROP TABLE IF EXISTS reg_items")
    con.execute("CREATE TABLE reg_items (kind TEXT, id TEXT, first_day TEXT, source TEXT, sha TEXT, subject TEXT, "
                "why TEXT)")
    for (kind, cid), (day, name, sha, subject) in first.items():
        m = re.search(r"^  why: *>?-?\n((?:    .*\n?|\n)+)", latest[(kind, cid)], re.M)
        why = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        con.execute("INSERT INTO reg_items VALUES (?,?,?,?,?,?,?)", (kind, cid, day, name, sha, subject, why))
    con.execute("DROP TABLE IF EXISTS reg_commits")
    con.execute("CREATE TABLE reg_commits (source TEXT, sha TEXT, day TEXT, subject TEXT, ids_added INT)")
    con.executemany("INSERT INTO reg_commits VALUES (?,?,?,?,?)", commits)
    con.commit()
    print(f"register: {len(first)} ids over {len(commits)} commits")


# ------------------------------------------------------------------ labelling

def label(con, task, items, header, batch=40, workers=6):
    """items: [(key, text)]. Labels each text once; returns {key: label dict}."""
    have = {r[0]: (r[1], r[2]) for r in con.execute("SELECT key, hash, label_json FROM labels WHERE task=?", (task,))}
    todo = [(k, t) for k, t in items
            if k not in have or have[k][0] != hashlib.sha1(t.encode()).hexdigest()]
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def one(chunk):
        texts = [f"### ITEM {i + 1}\n{t}" for i, (_, t) in enumerate(chunk)]
        return chunk, call_haiku(texts, model="haiku", header=header)

    spent = 0.0
    with ThreadPoolExecutor(workers) as ex:
        for chunk, (res, cost) in ex.map(one, chunks):
            spent += cost
            got = {int(r.get("item", 0)): r for r in (res if isinstance(res, list) else [])}
            for i, (k, t) in enumerate(chunk):
                if i + 1 in got:
                    con.execute("INSERT OR REPLACE INTO labels VALUES (?,?,?,?)",
                                (task, k, hashlib.sha1(t.encode()).hexdigest(), json.dumps(got[i + 1])))
    if chunks:
        con.execute("INSERT INTO spend VALUES (?,?)", (task, spent))
    con.commit()
    print(f"{task}: {len(todo)} labelled in {len(chunks)} calls, ${spent:.3f}")
    return {r[0]: json.loads(r[1]) for r in con.execute("SELECT key, label_json FROM labels WHERE task=?", (task,))}


REG_HEADER = """You classify why a compliance rule was written. For each ITEM (a rule id, the commit that added it,
and the rule's `why:` text), decide what prompted the rule:
- "fleet_bug": the why describes a concrete failure, violation or bug actually observed in one of the
  owner's own repos (it names a repo, file, or an incident that happened here).
- "outside_incident": it cites an incident, advisory or compromise outside the fleet (e.g. a public
  supply-chain attack) and no observed fleet failure.
- "foreseen": a hazard reasoned about in advance or a design choice, with no observed failure named.
Reply with ONLY a JSON array, one object per item: {"item": N, "trigger": "...", "evidence": "<=12 words"}.

"""

GATE_HEADER = """You classify changes to an automated PR approval gate ("auto-approve": a CI workflow in which a model
judges a PR and approves it). For each ITEM (repo, commit subject and body, and the PR text), say what
prompted the change:
- "incident": a bug, bypass, breakage or wrong verdict of the gate was found and is being fixed.
- "false_block": the gate blocked or failed good work (flaky, too strict, timeouts) and is loosened or fixed.
- "cost": to cut spend, tokens, model calls or CI minutes.
- "capability": a new check, input or behaviour for the gate, not reacting to a failure.
- "adopt": installing, vendoring, re-vendoring, renaming or repointing the gate in a repo.
- "other": docs, tests or refactors with no behavioural motive.
Reply with ONLY a JSON array, one object per item: {"item": N, "trigger": "...", "evidence": "<=12 words"}.

"""

WS_HEADER = """Each ITEM is a commit to a developer-tooling plugin (skills and CI workflows used by coding agents).
For each, answer:
- "reason": true if the message states WHY the change is needed (an observed failure, a problem, a
  motivation or trade-off), false if it only says what changed.
- "incident": true if it names a specific failure that actually happened (a run that broke, a bug seen).
- "cost": true if the change is motivated by spend, tokens, usage limits, model choice or run time.
Reply with ONLY a JSON array, one object per item:
{"item": N, "reason": true/false, "incident": true/false, "cost": true/false}.

"""

MEM_HEADER = """Each ITEM is a memory file a coding agent saved for future sessions. For each, answer:
- "purpose": "correction" (records a mistake to avoid or a correction the user gave), "preference"
  (the user's standing preference or way of working), "reference" (where something is, how to do it),
  or "fact" (project state or a decision's context).
- "rule": the standing rule it states, in at most 8 plain words, generic enough that the same rule
  written in another repo would get the same words (e.g. "rebase before review", "never shift ports").
  Empty string if it states no rule.
Reply with ONLY a JSON array, one object per item: {"item": N, "purpose": "...", "rule": "..."}.

"""


def run_register(con):
    items = [(f"{k}:{i}", f"id: {i} ({k})\nadded by: {s}\nwhy: {w[:1500]}")
             for k, i, s, w in con.execute("SELECT kind, id, subject, why FROM reg_items")]
    label(con, "reg_trigger", items, REG_HEADER)


def cube():
    from cube.db import connect
    return connect()


def run_gate(con):
    c = cube()
    rows = c.execute("""
        SELECT DISTINCT c.repo, c.sha, c.day, c.subject, c.body_redacted, p.title, p.body_redacted pb
        FROM git.commit_files f JOIN git.commits c ON c.repo=f.repo AND c.sha=f.sha
        LEFT JOIN github.prs p ON p.repo=c.repo AND p.number=c.pr_number
        WHERE (f.path LIKE '%auto-approve%' OR f.path LIKE '%auto_approve%') AND c.is_merge=0""").fetchall()
    items = [(f"{r['repo']}:{r['sha']}", f"repo: {r['repo']}\ncommit: {r['subject']}\n{(r['body_redacted'] or '')[:1200]}\n"
              f"PR: {r['title'] or ''}\n{(r['pb'] or '')[:600]}") for r in rows]
    label(con, "gate_trigger", items, GATE_HEADER)


def run_ws(con):
    c = cube()
    rows = c.execute("SELECT sha, subject, body_redacted FROM git.commits WHERE repo='wayfare-skills' AND is_merge=0")
    items = [(r["sha"], f"{r['subject']}\n{(r['body_redacted'] or '')[:1500]}") for r in rows]
    label(con, "ws_reason", items, WS_HEADER)


def memory_files():
    """{file name: text} for every memory file on disk (read-only), MEMORY.md indexes excluded."""
    out = {}
    for p in glob.glob(os.path.expanduser("~/.claude/projects/*/memory/*.md")):
        if os.path.basename(p) != "MEMORY.md":
            out.setdefault(os.path.basename(p), open(p, errors="replace").read())
    return out


def run_memory(con):
    files = memory_files()
    h = sqlite3.connect(os.path.join(os.path.dirname(DB), "harness.sqlite"))
    rows = h.execute("SELECT repo, file FROM memories WHERE file != 'MEMORY.md'").fetchall()
    items = [(f"{repo}:{f}", files[f][:1500]) for repo, f in rows if f in files]
    print(f"memory: {len(items)} of {len(rows)} memories found on disk")
    label(con, "mem_purpose", items, MEM_HEADER)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    con = db()
    if what in ("register", "all"):
        register_history(con)
        run_register(con)
    if what in ("gate", "all"):
        run_gate(con)
    if what in ("ws", "all"):
        run_ws(con)
    if what in ("memory", "all"):
        run_memory(con)


CLUSTER_HEADER = """Below is a numbered list of standing rules that coding agents saved to memory in different repos.
Group the rules that state the SAME underlying rule (same behaviour asked for, even if worded differently
or applied to a different tool). Only group genuine restatements; most rules will be alone.
Reply with ONLY a JSON array of groups with two or more members:
[{"rule": "<the shared rule, at most 8 words>", "items": [N, N, ...]}].

"""


def run_clusters(con):
    """Groups memories that restate the same rule. One call over every non-empty rule."""
    rows = [(k, json.loads(l)["rule"]) for k, l in
            con.execute("SELECT key, label_json FROM labels WHERE task='mem_purpose'")]
    rows = [(k, r) for k, r in rows if r.strip()]
    texts = [f"{i + 1}. {r}" for i, (_, r) in enumerate(rows)]
    res, cost = call_haiku(["\n".join(texts)], model="sonnet", header=CLUSTER_HEADER)
    con.execute("DROP TABLE IF EXISTS mem_rule_groups")
    con.execute("CREATE TABLE mem_rule_groups (grp INT, rule TEXT, key TEXT)")
    for g, grp in enumerate(res if isinstance(res, list) else []):
        for n in grp.get("items", []):
            if isinstance(n, int) and 1 <= n <= len(rows):
                con.execute("INSERT INTO mem_rule_groups VALUES (?,?,?)", (g, grp.get("rule", ""), rows[n - 1][0]))
    con.execute("INSERT INTO spend VALUES ('mem_clusters', ?)", (cost,))
    con.commit()
    print(f"clusters: {len(res) if isinstance(res, list) else 0} groups, ${cost:.3f}")


ORIGIN_HEADER = """Each ITEM is a commit to a shared repo that other repos build on: a project template ("hero-template")
or a tooling plugin ("wayfare-skills"). Product repos in this fleet include: auth, hiro, saga, website,
design-system, elevate-commons, aihero-wayfare, aihero-steadfast, ah-cozy, aihero-dokyu, aihero-mehr,
infrastructure-environments, infrastructure-root. For each ITEM decide where the change's idea came from:
- "product": the message says the practice, code or fix was first built, found or proven in a named
  product repo and is being brought into the shared repo (e.g. "hiro already had X; this is that file
  adapted", "backport from auth", "consumer ahead").
- "report": a product repo reported a bug or need that this change answers (an issue or message from it).
- "own": the shared repo's own design or fix, with no product named as the source.
Reply with ONLY a JSON array, one object per item: {"item": N, "origin": "...", "repo": "<named product or empty>"}.

"""


def run_origin(con):
    c = cube()
    rows = c.execute("SELECT repo, sha, subject, body_redacted FROM git.commits "
                     "WHERE repo IN ('hero-template', 'wayfare-skills') AND is_merge=0")
    items = [(f"{r['repo']}:{r['sha']}", f"repo: {r['repo']}\n{r['subject']}\n{(r['body_redacted'] or '')[:1500]}")
             for r in rows]
    label(con, "origin", items, ORIGIN_HEADER)
