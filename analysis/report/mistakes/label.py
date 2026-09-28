"""Mistakes and rework model labels (Haiku), cached in .analysis/data/mistakes.sqlite.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/mistakes/label.py [commits|logs|personas|all]

Three passes, each keyed by a hash of the text the model saw, so a re-run pays only for new text:

  commits   every original PR commit after the PR's first: is it a fix-up of earlier work in
            the same PR, what prompted it, and the mistake theme it repairs.  -> commit_labels
  logs      every item_logs `mistake` entry, and every `note` whose wording suggests a mistake:
            is it an agent mistake, its theme, who caught it.                  -> mistake_labels
  personas  per session, the assistant turns that report the review personas' results: each
            distinct finding, which persona raised it, who else did, what happened to it.
                                                                               -> persona_findings

mistake_labels is the chapter's stable output (Chapter 23 reads it); fix-up commits are copied
into it with source='pr_commit' so one table holds every labelled mistake.
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "mistakes.sqlite")
PROMPT_VERSION = "mistakes-v1"
BATCH_CHARS = 38000
BATCH_ITEMS = 45
WORKERS = 6

THEMES = {
    "logic_bug": "the code did the wrong thing (wrong condition, wrong value, wrong behaviour)",
    "incomplete": "a required piece was left out: forgot to wire, missed a case, a file or step not updated",
    "test_gap": "a missing or weak test, or a test/check that passed without exercising the change",
    "format_lint": "lint, formatting, type errors, syntax, invalid JSON/YAML, a pre-commit hook refusing",
    "ci_config": "CI workflow, build, Docker, deploy or environment configuration was wrong",
    "env_assumption": "a wrong assumption about a tool, host, API, library or the repo's state",
    "docs_prose": "docs, comments, PR text or agent instructions were wrong, stale or noisy",
    "plan_gap": "the plan or spec itself was wrong or incomplete",
    "git_process": "a branch, rebase, commit, PR or process step done wrong or skipped",
    "security": "a security weakness: secret exposure, injection, permissions, unsafe default",
    "unverified_claim": "claimed done, passing or verified without having checked",
    "subagent": "a delegated subagent did nothing, stalled, or interfered with other work",
    "other": "none of the above",
}
TRIGGERS = ["review_agent", "copilot", "ci", "judge", "hook", "owner", "self", "none"]

COMMIT_HEADER = f"""You classify commits inside merged pull requests written by coding agents.
Each numbered item is one commit that came AFTER the PR's first commit. You see the PR title,
the subjects of the commits before it in the same PR, and the commit's own subject, body and files.

For each give:
- "fixup": 1 if the commit repairs, corrects or responds to feedback on work made EARLIER IN THE SAME PR
  (a review fix, a CI or lint fix, "address findings", a forgotten piece of what the PR set out to do,
  a correction of an earlier commit). 0 if it is new, planned work (the next feature step, a new test,
  docs for the feature, a merge of main, a rebase conflict resolution).
- "trigger" (who or what prompted it), one of {TRIGGERS}:
  review_agent = the agent's own self-review or review personas (code-reviewer, silent-failure-hunter...);
  copilot = the Copilot reviewer; ci = a failing CI run; judge = the auto-approve verdict or changes requested;
  hook = a pre-commit hook; owner = the human asked for it; self = the agent noticed on its own;
  none = not a fix-up.
- "theme": if fixup=1, the ONE kind of mistake it repairs, from:
{json.dumps(THEMES, indent=1)}
  if fixup=0, "none".

Reply with ONLY a JSON object, no prose, no fence: {{"<item number>": {{"fixup": 0|1, "trigger": ..., "theme": ...}}, ...}}

Items:
"""

LOG_HEADER = f"""You read entries from coding agents' work logs. Each numbered item is one entry an agent
wrote in a work item's log (kind "mistake" or "note").

For each give:
- "mistake": 1 if the entry reports a mistake an agent made (its own or another agent's): something done
  wrong, skipped, overclaimed or broken, even if it was then fixed. 0 if it is only progress, a decision,
  a plan, a finding about pre-existing code, or an external failure nobody in the factory caused.
- "theme": the ONE kind of mistake, from:
{json.dumps(THEMES, indent=1)}
  or "none" if mistake=0.
- "actor": "main" (the agent writing), "subagent" (a delegated agent), "other_agent", or "none".
- "caught_by": who noticed it, one of ["self", "review_agent", "copilot", "ci", "judge", "hook", "test", "owner", "unknown", "none"].
- "overclaim": 1 if the mistake is claiming something was done, passing or verified that was not.
- "green_but_empty": 1 if a test, check or gate reported success without actually checking what it claimed.
- "summary": at most 12 words, the mistake itself; "" if mistake=0.

Reply with ONLY a JSON object, no prose, no fence: {{"<item number>": {{"mistake": 0|1, "theme": ..., "actor": ...,
"caught_by": ..., "overclaim": 0|1, "green_but_empty": 0|1, "summary": ...}}, ...}}

Items:
"""

PERSONAS = ["code-reviewer", "silent-failure-hunter", "pr-test-analyzer", "comment-analyzer",
            "type-design-analyzer", "security", "copilot", "other"]
PERSONA_HEADER = f"""You read a coding agent's messages from one working session in which it ran review
personas (sub-agents) on its own pull request and reported what they found. Each numbered item is one session.

List the DISTINCT findings the personas raised (a finding restated in several messages is one finding).
For each finding give:
- "persona": who raised it, one of {PERSONAS} ("security" = the security pass);
- "also": the list of OTHER personas the text says raised the same finding ([] if none);
- "severity": "high", "medium" or "low" as the text presents it ("low" for nits);
- "disposition": "fixed", "deferred" (filed or left for later), "disputed" (rejected or judged a false positive),
  or "unknown";
- "finding": at most 12 words.
Also give "ran": the list of personas the text says ran in the session, and "clean": the personas that
reported no findings.

Reply with ONLY a JSON object, no prose, no fence:
{{"<item number>": {{"ran": [...], "clean": [...], "findings": [{{"persona": ..., "also": [...], "severity": ...,
"disposition": ..., "finding": ...}}, ...]}}, ...}}

Items:
"""

NOTE_RX = re.compile(r"mistake|forgot|wrong|missed|incorrect|\bbroke|turned out|regress|should have|"
                     r"i had |proving nothing|false[- ]clean|did not actually|didn't actually|overclaim|"
                     r"no-op|stalled|reverted|oversight|my error", re.I)


def call_haiku(texts, header, tries=3):
    """detectors/d1_changesets.call_haiku with thinking off: at low effort Haiku still spent
    two thirds of its output tokens thinking, which doubled the cost of a labelling pass.
    Returns (parsed reply, cost of every attempt, failed ones included)."""
    env = {**os.environ, "MAX_THINKING_TOKENS": "0"}
    usd = 0.0
    for attempt in range(tries):
        try:
            # The labelled text is untrusted (anyone's PR or review), so the model gets no tools and no MCP.
            p = subprocess.run(["claude", "-p", "--model", "haiku", "--effort", "low", "--output-format", "json",
                                "--tools", "", "--strict-mcp-config", "--permission-mode", "dontAsk"],
                               input=header + "\n\n".join(texts), capture_output=True, text=True, cwd="/tmp",
                               timeout=300 + attempt * 120, env=env)
        except subprocess.TimeoutExpired:
            continue
        try:
            outer = json.loads(p.stdout)
        except json.JSONDecodeError:
            continue
        usd += outer.get("total_cost_usd", 0.0) or 0.0
        text = (outer.get("result") or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            return json.loads(text), usd
        except json.JSONDecodeError:
            print(f"  ! unparsable reply (try {attempt + 1})", file=sys.stderr)
    return {}, usd


def h(s):
    return hashlib.sha1((PROMPT_VERSION + s).encode()).hexdigest()


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def db():
    d = sqlite3.connect(DB, timeout=120)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS cache (h TEXT PRIMARY KEY, pass TEXT, reply TEXT);
    CREATE TABLE IF NOT EXISTS spend (pass TEXT, batch_h TEXT PRIMARY KEY, n INTEGER, usd REAL);
    CREATE TABLE IF NOT EXISTS commit_labels (repo TEXT, pr INTEGER, sha TEXT, idx INTEGER, day TEXT,
        fixup INTEGER, trigger TEXT, theme TEXT, method TEXT, PRIMARY KEY (repo, pr, sha));
    CREATE TABLE IF NOT EXISTS mistake_labels (source TEXT, ref TEXT, repo TEXT, day TEXT, item_id TEXT,
        pr INTEGER, is_mistake INTEGER, theme TEXT, actor TEXT, caught_by TEXT, overclaim INTEGER,
        green_but_empty INTEGER, summary TEXT, method TEXT, PRIMARY KEY (source, ref));
    CREATE TABLE IF NOT EXISTS persona_findings (session TEXT, repo TEXT, day TEXT, n INTEGER, persona TEXT,
        also TEXT, severity TEXT, disposition TEXT, finding TEXT, method TEXT, PRIMARY KEY (session, n));
    CREATE TABLE IF NOT EXISTS persona_sessions (session TEXT PRIMARY KEY, repo TEXT, day TEXT, ran TEXT,
        clean TEXT, method TEXT);
    """)
    return d


def batches(items):
    """items: [(hash, text)] -> lists sized by chars and count."""
    out, cur, size = [], [], 0
    for it in items:
        if cur and (size + len(it[1]) > BATCH_CHARS or len(cur) >= BATCH_ITEMS):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it[1])
    return out + ([cur] if cur else [])


def run_pass(d, name, header, items):
    """items: [(hash, text)]. Returns {hash: reply dict}, calling the model only for uncached hashes."""
    have = {r[0]: json.loads(r[1]) for r in d.execute("SELECT h, reply FROM cache WHERE pass=?", (name,))}
    todo = [it for it in dict(items).items() if it[0] not in have]
    todo = [(k, v) for k, v in todo]
    bs = batches(todo)
    print(f"{name}: {len(items)} items, {len(todo)} to label in {len(bs)} batches", file=sys.stderr)

    def one(b):
        texts = [f"[{i + 1}] {t}" for i, (_, t) in enumerate(b)]
        reply, usd = call_haiku(texts, header)
        return b, reply, usd

    with ThreadPoolExecutor(WORKERS) as ex:
        for b, reply, usd in ex.map(one, bs):
            got = 0
            for i, (k, _) in enumerate(b):
                r = reply.get(str(i + 1)) if isinstance(reply, dict) else None
                if isinstance(r, dict):
                    d.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (k, name, json.dumps(r)))
                    have[k] = r
                    got += 1
            d.execute("INSERT OR REPLACE INTO spend VALUES (?,?,?,?)", (name, h("".join(k for k, _ in b)), got, usd))
            d.commit()
            print(f"  {name}: batch of {len(b)} -> {got} labels, ${usd:.3f}", file=sys.stderr)
    return have


# ------------------------------------------------------------------ commits

def commit_items(con):
    title = {(r["repo"], r["number"]): r["title"] for r in rows(con, "SELECT repo, number, title FROM github.prs")}
    by_pr = defaultdict(list)
    for r in rows(con, "SELECT repo, pr_number, idx, sha, ts, subject, body_redacted, files_json, author "
                       "FROM pr_commits.pr_commits WHERE is_merge = 0 ORDER BY repo, pr_number, idx"):
        if r["repo"] in OUT_OF_SCOPE:
            continue
        by_pr[(r["repo"], r["pr_number"])].append(r)
    out = []
    for (repo, pr), cs in by_pr.items():
        if any("dependabot" in (c["author"] or "").lower() for c in cs):
            continue
        for j, c in enumerate(cs[1:], 1):
            try:
                files = [f.get("path") if isinstance(f, dict) else str(f) for f in json.loads(c["files_json"] or "[]")]
            except json.JSONDecodeError:
                files = []
            before = "; ".join((p["subject"] or "")[:70] for p in cs[max(0, j - 5):j])
            body = re.sub(r"\s+", " ", (c["body_redacted"] or ""))
            body = re.sub(r"Co-Authored-By:.*$", "", body, flags=re.I)[:350]
            t = (f"repo={repo} | PR: {(title.get((repo, pr)) or '-')[:100]} | before: {before} | "
                 f"THIS: {c['subject'][:160]} | body: {body} | files: {', '.join(files[:5])}")
            out.append(((repo, pr, c["sha"], c["idx"], c["ts"][:10]), t))
    return out


def label_commits(con, d):
    items = commit_items(con)
    keyed = [(h(t), t) for _, t in items]
    got = run_pass(d, "commits", COMMIT_HEADER, keyed)
    for (repo, pr, sha, idx, day), t in items:
        r = got.get(h(t))
        if not r:
            continue
        fix = 1 if str(r.get("fixup")) in ("1", "True", "true") else 0
        trig = r.get("trigger") if r.get("trigger") in TRIGGERS else ("self" if fix else "none")
        theme = r.get("theme") if r.get("theme") in THEMES else ("other" if fix else "none")
        d.execute("INSERT OR REPLACE INTO commit_labels VALUES (?,?,?,?,?,?,?,?,?)",
                  (repo, pr, sha, idx, day, fix, trig if fix else "none", theme if fix else "none", PROMPT_VERSION))
        caught = {"review_agent": "review_agent", "copilot": "copilot", "ci": "ci", "judge": "judge", "hook": "hook",
                  "owner": "owner", "self": "self"}.get(trig, "unknown")
        if fix:
            d.execute("INSERT OR REPLACE INTO mistake_labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      ("pr_commit", f"{repo}#{pr}@{sha[:12]}", repo, day, None, pr, 1, theme, "unknown", caught,
                       1 if theme == "unverified_claim" else 0, 1 if theme == "test_gap" else 0, "", PROMPT_VERSION))
        else:
            d.execute("DELETE FROM mistake_labels WHERE source='pr_commit' AND ref=?", (f"{repo}#{pr}@{sha[:12]}",))
    d.commit()


# ------------------------------------------------------------------ logs

def log_items(con):
    out = []
    seen = defaultdict(int)
    for r in rows(con, "SELECT repo, item_id, ts, kind, text_redacted FROM plans.item_logs "
                       "WHERE kind IN ('mistake', 'note') ORDER BY repo, item_id, ts"):
        if r["repo"] in OUT_OF_SCOPE:
            continue
        text = r["text_redacted"] or ""
        if r["kind"] == "note" and not NOTE_RX.search(text):
            continue
        k = (r["repo"], r["item_id"], r["kind"])
        seen[k] += 1
        ref = f"{r['repo']}/{r['item_id']}/{r['kind']}/{seen[k]}"
        t = f"repo={r['repo']} | kind={r['kind']} | {re.sub(r'\\s+', ' ', text)[:700]}"
        out.append(((ref, r["repo"], (r["ts"] or "")[:10], r["item_id"], r["kind"]), t))
    return out


def label_logs(con, d):
    items = log_items(con)
    got = run_pass(d, "logs", LOG_HEADER, [(h(t), t) for _, t in items])
    for (ref, repo, day, item, kind), t in items:
        r = got.get(h(t))
        if not r:
            continue
        flag = lambda k: 1 if str(r.get(k)) in ("1", "True", "true") else 0
        theme = r.get("theme") if r.get("theme") in THEMES else "other"
        d.execute("INSERT OR REPLACE INTO mistake_labels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("mistake_log" if kind == "mistake" else "note", ref, repo, day, item, None, flag("mistake"),
                   theme if flag("mistake") else "none", r.get("actor") or "unknown", r.get("caught_by") or "unknown",
                   flag("overclaim"), flag("green_but_empty"), (r.get("summary") or "")[:200], PROMPT_VERSION))
    d.commit()


# ------------------------------------------------------------------ personas

PERSONA_RX = re.compile(r"silent-failure|code-reviewer|pr-test-analyzer|comment-analyzer|type-design|"
                        r"review personas?|review agents?", re.I)


def persona_items(con):
    sess = {r["session_id_hash"]: r for r in rows(con, "SELECT session_id_hash, repo, day FROM harness.sessions")}
    ran = {r["s"] for r in rows(con, "SELECT DISTINCT session_id_hash s FROM harness.subagent_runs "
                                     "WHERE subagent_type LIKE 'pr-review-toolkit:%'")}
    by = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, idx, text_redacted t FROM harness.turns WHERE role='assistant' "
                       "AND length(text_redacted) > 200 ORDER BY session_id_hash, idx"):
        if r["s"] in ran and PERSONA_RX.search(r["t"] or ""):
            by[r["s"]].append(re.sub(r"\s+", " ", r["t"])[:3000])
    out = []
    for s, turns in by.items():
        info = sess.get(s) or {"repo": None, "day": None}
        if info["repo"] in OUT_OF_SCOPE:
            continue
        text = " || ".join(turns)[:12000]
        out.append(((s, info["repo"], info["day"]), f"repo={info['repo']} | {text}"))
    return out


def label_personas(con, d):
    items = persona_items(con)
    got = run_pass(d, "personas", PERSONA_HEADER, [(h(t), t) for _, t in items])
    for (s, repo, day), t in items:
        r = got.get(h(t))
        if not r:
            continue
        d.execute("INSERT OR REPLACE INTO persona_sessions VALUES (?,?,?,?,?,?)",
                  (s, repo, day, json.dumps(r.get("ran") or []), json.dumps(r.get("clean") or []), PROMPT_VERSION))
        d.execute("DELETE FROM persona_findings WHERE session=?", (s,))
        for n, f in enumerate(r.get("findings") or []):
            if not isinstance(f, dict):
                continue
            d.execute("INSERT OR REPLACE INTO persona_findings VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (s, repo, day, n, f.get("persona") if f.get("persona") in PERSONAS else "other",
                       json.dumps(f.get("also") or []), f.get("severity") or "unknown",
                       f.get("disposition") or "unknown", (f.get("finding") or "")[:200], PROMPT_VERSION))
    d.commit()


def main(which):
    con, d = _connect(), db()
    if which in ("commits", "all"):
        label_commits(con, d)
    if which in ("logs", "all"):
        label_logs(con, d)
    if which in ("personas", "all"):
        label_personas(con, d)
    for p, n, usd in d.execute("SELECT pass, SUM(n), SUM(usd) FROM spend GROUP BY pass"):
        print(f"spend {p}: {n} labels, ${usd:.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
