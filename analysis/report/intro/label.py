"""Label every change set with a work type and a study theme (Haiku), cached in intro.sqlite.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/intro/label.py

Dependabot change sets are labelled without the model (upkeep / dependencies). Each label
is keyed by a hash of the text the model saw, so a re-run only pays for new change sets.
"""
import hashlib
import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from record import changeset_facts, rows  # noqa: E402
from detectors.d1_changesets import call_haiku  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "intro.sqlite")
BATCH = 100
WORK_TYPES = ["feature", "fix", "refactor", "test", "docs", "upkeep"]
THEMES = {
    "product": "the app's own features, UI, API or data model",
    "harness": "agent tooling: skills, hooks, agent instructions, Claude Code config, the plugin itself",
    "gates": "human-in-the-loop gates: approval, auto-approve, review workflow, merge rules",
    "connectors": "integrations with outside services: Sentry, GitHub apps, MCP servers, email/SMS providers, analytics",
    "knowledge": "documentation and records: README, AGENTS.md, DESIGN.md, handbooks, memory",
    "planning": "work items, plans, roadmap, goals, the .plans store",
    "quality": "tests, CI, lint, type checks, fixing review findings",
    "security": "security hardening, auth checks, secrets, vulnerabilities, audits",
    "cross-repo": "syncing with other repos: re-vendoring assets, template sync, fleet messages",
    "compliance": "compliance register, controls, checks, conformance to the fleet baseline",
    "infrastructure": "deployment, containers, Terraform, environments, hosting, release pipeline",
    "dependencies": "dependency bumps and lockfile changes",
}
HEADER = f"""You label units of software work from a fleet of repos. Each numbered line is one change set:
its repo, a short label, the PR title and some commit subjects.

For each, give:
- "type": one of {WORK_TYPES}. feature = new user- or developer-facing capability; fix = corrects a bug or
  a finding; refactor = restructures without changing behaviour; test = adds or changes tests only; docs = prose
  only; upkeep = dependency bumps, CI/config tweaks, re-vendoring, formatting, renames, housekeeping.
- "theme": the ONE study theme it mainly belongs to, from:
{json.dumps(THEMES, indent=1)}

Reply with JSON only: a list of objects {{"i": <number>, "type": ..., "theme": ...}}, one per line, in order.

"""


def texts(con):
    title = {(r["repo"], r["number"]): r["title"] for r in rows(con, "SELECT repo, number, title FROM github.prs")}
    subj = {(r["repo"], r["sha"]): r["subject"] for r in rows(con, "SELECT repo, sha, subject FROM pr_commits.pr_commits")}
    subj.update({(r["repo"], r["sha"]): r["subject"] for r in rows(con, "SELECT repo, sha, subject FROM git.commits")})
    out = []
    for f in changeset_facts(con):
        subs = [subj.get((f["repo"], s), "") for s in f["shas"][:3]]
        t = (f"repo={f['repo']} | label: {f['label']} | PR: {title.get((f['repo'], f['pr']), '-')} | "
             f"commits: {'; '.join(s for s in subs if s)}")[:600]
        out.append((f, t, hashlib.sha1(t.encode()).hexdigest()))
    return out


def key(f):
    return f"{f['repo']}|{f['unit_kind']}|{f['unit_id']}|{f['set_idx']}"


def main():
    con = _connect()
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS cs_labels (key TEXT PRIMARY KEY, repo TEXT, text_hash TEXT, "
               "work_type TEXT, theme TEXT, method TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS spend (batch TEXT PRIMARY KEY, n INTEGER, usd REAL)")
    done = {r[0]: r[1] for r in db.execute("SELECT key, text_hash FROM cs_labels")}
    todo = []
    for f, t, h in texts(con):
        if done.get(key(f)) == h:
            continue
        if f["dependabot"]:
            db.execute("INSERT OR REPLACE INTO cs_labels VALUES (?,?,?,?,?,?)",
                       (key(f), f["repo"], h, "upkeep", "dependencies", "rule"))
        else:
            todo.append((f, t, h))
    db.commit()
    todo = todo[:int(os.environ.get("LIMIT", len(todo)))]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{len(todo)} change sets to label in {len(batches)} batches", file=sys.stderr)

    def run(batch):
        lines = [f"[{i + 1}] {t}" for i, (_, t, _) in enumerate(batch)]
        return batch, *call_haiku(lines, model="haiku", header=HEADER)

    with ThreadPoolExecutor(8) as ex:
        for batch, reply, usd in ex.map(run, batches):
            got = {int(r["i"]): r for r in reply if isinstance(r, dict) and str(r.get("i", "")).isdigit()} \
                if isinstance(reply, list) else {}
            for i, (f, t, h) in enumerate(batch):
                r = got.get(i + 1)
                if r and r.get("type") in WORK_TYPES and r.get("theme") in THEMES:
                    db.execute("INSERT OR REPLACE INTO cs_labels VALUES (?,?,?,?,?,?)",
                               (key(f), f["repo"], h, r["type"], r["theme"], "haiku"))
            bh = hashlib.sha1("".join(h for _, _, h in batch).encode()).hexdigest()
            db.execute("INSERT OR REPLACE INTO spend VALUES (?,?,?)", (bh, len(batch), usd))
            db.commit()
            print(f"  batch of {len(batch)}: {len(got)} labels, ${usd:.3f}", file=sys.stderr)
    n, usd = db.execute("SELECT COUNT(*), (SELECT ROUND(SUM(usd), 3) FROM spend) FROM cs_labels").fetchone()
    print(f"{n} labelled; model spend ${usd}")


if __name__ == "__main__":
    main()
