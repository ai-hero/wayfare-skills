"""Haiku labels for Chapter 15, cached in messages.sqlite by a hash of the text the model saw.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/messages/label.py [needs|breaks|names|decisions]

needs      Q cross-repo-finds  work items that name another fleet repo: does another repo need to change, and what
                    did this repo do about it
breaks     Q upstream-breaks  fix and security change sets outside the upstream repos: did an upstream change cause it
names      Q upstream-impact-notes  upstream PRs: does it change something consumers use, and does it name them
decisions  Q cross-repo-decision-agreement  DESIGN.md decisions grouped by topic across repos (one call per batch of topics)
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect  # noqa: E402
from record import changeset_facts, rows  # noqa: E402
from detectors.d1_changesets import call_haiku  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, REPO_ALIASES  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "messages.sqlite")
UPSTREAM = ("wayfare-skills", "hero-template", "design-system", "auth")
FLEET_REPOS = ["auth", "design-system", "hero-template", "wayfare-skills", "elevate-commons", "aihero-wayfare",
               "aihero-steadfast", "website", "hiro", "saga", "infrastructure-environments", "infrastructure-root",
               "ah-cozy", "aihero-dokyu", "aihero-mehr", "pterodactyl"]
# "auth", "website", "saga" and "hiro" are ordinary words too; only these spellings count as naming the repo.
NAME_RE = re.compile(r"(?<![\w-])(?:\.\./|ai-hero/)?(" + "|".join(sorted(FLEET_REPOS + ["hero-skills"], key=len, reverse=True)) +
                     r")(?![\w-])")

HEADERS = {
    "needs": """You read work items from a fleet of sibling repos, one agent per repo. Each numbered block is one
work item: the repo it lives in, its title, and an excerpt of its body.

Decide whether the item says ANOTHER repo of the fleet (not the item's own repo) needs to change or answer
something: a fix, a feature, a contract, a convention, a reply. Merely using or mentioning another repo
(e.g. "sign in through auth") is NOT a need.

For each item give:
- "need": true/false
- "other": the other repo's name as written (null when need is false)
- "action": what this repo did about it, one of:
  "message"  sent or drafted a message, signal or ask to that repo (inbox, outbox, mailbox)
  "tracked"  recorded it here: a dependency, a blocked-on, a follow-up or a note to raise it later
  "changed"  this repo's own work edited the other repo directly
  "handoff"  filed an issue or a handoff in the other repo's tracker
  "none"     the need is stated but nothing was done about it
  (null when need is false)

Reply with JSON only: a list of {"i": <number>, "need": ..., "other": ..., "action": ...}, one per block, in order.

""",
    "breaks": """You read fix and security change sets from app repos in a fleet. The fleet's shared repos are:
auth (the identity service every app signs in through, its API and tokens), design-system (a component registry
the apps pull UI from), hero-template (the template the apps were cloned from), and wayfare-skills (the agent
plugin: skills, vendored rules and hooks, the auto-approve workflow).

For each numbered change set decide whether the fix was needed BECAUSE a shared repo changed something this repo
relies on (its API, a component, a vendored rule or hook, a template file, a workflow) and broke or changed
behaviour here. A bug this repo wrote itself, or a bug that was always there, is "own". Adopting an upstream
improvement that did not break anything is "own".

Give:
- "cause": "upstream_change" or "own"
- "upstream": "auth" | "design-system" | "hero-template" | "wayfare-skills" | null
- "via": "api" | "registry" | "vendored_rule_or_hook" | "template_file" | "ci_workflow" | "dependency" | null

Reply with JSON only: a list of {"i": <number>, "cause": ..., "upstream": ..., "via": ...}, one per line, in order.

""",
    "names": """You read merged PRs from the shared repos of a fleet: auth (identity service the apps call),
design-system (component registry the apps pull), hero-template (the template apps were cloned from and keep
syncing with), wayfare-skills (agent plugin whose skills, rules, hooks and workflows every repo uses).

For each numbered PR give:
- "affects": true when the change alters something OTHER repos consume or copy: an API or token contract,
  a registry component or theme, a template file clones are expected to adopt, a vendored rule/hook/workflow,
  a skill's behaviour in other repos. Internal refactors, tests, docs about this repo alone, dependency bumps: false.
- "breaking": true when a consumer must change something or will behave differently without acting.
- "names": true when the PR text names the specific consuming repos affected, or says which repos must act
  (a list, "every clone", "the apps" counts only with an explicit list or an explicit fleet-wide instruction).

Reply with JSON only: a list of {"i": <number>, "affects": ..., "breaking": ..., "names": ...}, one per line, in order.

""",
    "decisions": """Below are dated decisions from the DESIGN.md files of several repos in one fleet (a template,
apps cloned from it, an identity service "auth", a component registry "design-system").

Find TOPICS on which two or more repos each recorded a decision: the same question decided (for example how
tenancy is scoped, where tokens are validated, how cookies are named, what happens on a failed dependency).
For each topic give the decision ids involved and whether the repos AGREE (same answer), CONFLICT (different
answers to the same question) or PARTLY (one repo's answer is narrower or older but compatible).

Only include topics with decisions from at least two different repos. Reply with JSON only:
[{"topic": "...", "ids": [<numbers>], "verdict": "agree"|"conflict"|"partly", "why": "<one short sentence>"}]

""",
}


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS labels (task TEXT, key TEXT, hash TEXT, label TEXT, PRIMARY KEY (task, key))")
    con.execute("CREATE TABLE IF NOT EXISTS spend (task TEXT, usd REAL)")
    return con


def h(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def plan_files():
    """(repo, key, created day, text) for every work item file, from the checkouts."""
    con = connect()
    out = []
    for r in rows(con, "SELECT repo, item_id, title, day, file_path FROM plans.plan_items WHERE file_path IS NOT NULL"):
        if r["repo"] in OUT_OF_SCOPE or not os.path.exists(r["file_path"]):
            continue
        body = open(r["file_path"], errors="replace").read()
        out.append((r["repo"], f"{r['repo']}#{r['item_id']}", r["day"], r["title"] or "", body))
    return out


def mentions_other(repo, text):
    return {REPO_ALIASES.get(m, m) for m in NAME_RE.findall(text)} - {repo, "wayfare-skills" if repo == "hero-skills" else repo}


def needs_inputs():
    out = []
    for repo, key, day, title, body in plan_files():
        if not mentions_other(repo, body.replace("auth.", "")):
            continue
        out.append((key, f"repo={repo} | title: {title}\n{body[:2500]}"))
    return out


def breaks_inputs():
    con = connect()
    title = {(r["repo"], r["number"]): r["title"] for r in rows(con, "SELECT repo, number, title FROM github.prs")}
    subj = {(r["repo"], r["sha"]): r["subject"] for r in rows(con, "SELECT repo, sha, subject FROM pr_commits.pr_commits")}
    subj.update({(r["repo"], r["sha"]): r["subject"] for r in rows(con, "SELECT repo, sha, subject FROM git.commits")})
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): r["work_type"]
          for r in rows(con, "SELECT * FROM detectors.cs_worktype")}
    out = []
    for f in changeset_facts(con):
        if f["repo"] in ("wayfare-skills", "auth", "design-system") or f["dependabot"]:
            continue
        if wt.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])) not in ("fix", "security"):
            continue
        subs = "; ".join(subj.get((f["repo"], s), "") for s in f["shas"][:4])
        out.append((f"{f['repo']}|{f['unit_kind']}|{f['unit_id']}|{f['set_idx']}",
                    f"repo={f['repo']} | {f['label']} | PR: {title.get((f['repo'], f['pr']), '-')} | commits: {subs}"[:700]))
    return out


def names_inputs():
    con = connect()
    out = []
    for r in rows(con, "SELECT repo, number, title, body_redacted, author_is_bot FROM github.prs "
                       "WHERE merged_ts IS NOT NULL AND repo IN (?,?,?,?)", UPSTREAM):
        if r["author_is_bot"]:
            continue
        out.append((f"{r['repo']}#{r['number']}", f"repo={r['repo']} | PR: {r['title']}\n{(r['body_redacted'] or '')[:700]}"))
    return out


def run_batches(task, items, batch):
    con = db()
    have = {k: hsh for k, hsh in con.execute("SELECT key, hash FROM labels WHERE task=?", (task,))}
    todo = [(k, t) for k, t in items if have.get(k) != h(t)]
    print(f"{task}: {len(items)} items, {len(todo)} to label")
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def one(chunk):
        texts = [f"{i + 1}. {t}" if task != "needs" else f"=== {i + 1} ===\n{t}" for i, (_, t) in enumerate(chunk)]
        res, usd = call_haiku(texts, model="haiku", header=HEADERS[task])
        got = {}
        for x in res if isinstance(res, list) else []:
            try:
                got[int(x["i"]) - 1] = x
            except (KeyError, ValueError, TypeError):
                pass
        return chunk, got, usd

    total = 0.0
    with ThreadPoolExecutor(6) as ex:
        for chunk, got, usd in ex.map(one, chunks):
            total += usd
            c = db()
            for i, (k, t) in enumerate(chunk):
                if i in got:
                    c.execute("INSERT OR REPLACE INTO labels VALUES (?,?,?,?)", (task, k, h(t), json.dumps(got[i])))
            c.execute("INSERT INTO spend VALUES (?,?)", (task, usd))
            c.commit()
    print(f"{task}: ${total:.3f}")


def run_decisions():
    con = connect()
    ds = rows(con, "SELECT rowid AS id, repo, heading, date_in_text, first_seen_ts, text_redacted FROM knowledge.design_decisions")
    ds = [d for d in ds if d["repo"] not in OUT_OF_SCOPE]
    text = [f"{d['id']}. [{d['repo']}] {d['heading']}: {(d['text_redacted'] or '')[:220]}" for d in ds]
    key = h("\n".join(text))
    c = db()
    if c.execute("SELECT 1 FROM labels WHERE task='decisions' AND hash=?", (key,)).fetchone():
        print("decisions: cached")
        return
    res, usd = call_haiku(text, model="haiku", header=HEADERS["decisions"])
    c.execute("DELETE FROM labels WHERE task='decisions'")
    c.execute("INSERT INTO labels VALUES ('decisions', 'all', ?, ?)", (key, json.dumps(res)))
    c.execute("INSERT INTO spend VALUES ('decisions', ?)", (usd,))
    c.commit()
    print(f"decisions: {len(res) if isinstance(res, list) else 0} topics, ${usd:.3f}")


if __name__ == "__main__":
    tasks = sys.argv[1:] or ["needs", "breaks", "names", "decisions"]
    for t in tasks:
        if t == "needs":
            run_batches("needs", needs_inputs(), 12)
        elif t == "breaks":
            run_batches("breaks", breaks_inputs(), 60)
        elif t == "names":
            run_batches("names", names_inputs(), 60)
        elif t == "decisions":
            run_decisions()
