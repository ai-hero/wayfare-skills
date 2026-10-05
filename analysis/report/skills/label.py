"""Skills and factory evolution's own model labels -> .analysis/data/skills.sqlite. Cached by content hash; a re-run labels only what is new.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/skills/label.py [steps|triggers]

steps     every heading-delimited section of every skill and reference file, at each month-end
          snapshot of the plugin: is it a procedure step, and is its work scripted or judged (Q scripted-step-share)
triggers  every change to the plugin (a merged PR, or a commit pushed straight to main before PRs):
          what set it off (Q plugin-change-triggers)
"""
import hashlib
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "detectors"))
import gitwalk as G  # noqa: E402
from d_shared_labels import run_batches  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "skills.sqlite")
SNAPSHOTS = ["2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-10-01"]
MAX_CHARS = 3500

STEP_HEADER = """You read sections of the instruction files of a coding-agent skills plugin. Each section is one
heading and its body. For each section decide:
- kind: "step" if the section tells the agent to DO something as part of the procedure (a numbered step,
  a phase, a gate, a check to run); "not_step" if it is description, arguments, configuration notes,
  rationale, examples, reference tables, gotchas or a summary.
- mode (steps only; "none" for not_step):
  "scripted"  the work is done by running a named script, shell function or fixed command whose output
              decides what happens next; the agent mainly runs it and reads the result.
  "judgement" the section tells the agent in prose what to inspect, decide, write or ask; no script
              decides the outcome (commands shown only as examples or options still count as judgement).
  "mixed"     both matter: a script or fixed command does part of the work and prose judgement the rest.

Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"kind": "...", "mode": "..."}, ...}

Sections:
"""

TRIGGER_HEADER = """You read changes made to a coding-agent skills plugin (the process a one-person software
factory runs on). For each change decide what SET IT OFF, from its title, description and the owner's first
words in the session that built it (when present):
- owner_feedback: the owner hit a problem or preference while using the factory and asked for this change
  (a correction, complaint, "this keeps happening", a memory or rule they wanted enforced).
- downstream_report: a problem found while working in ANOTHER repo that uses the plugin (a consumer repo's
  run failed, a message or bug report from another repo, "found in <repo>").
- review_or_audit: found by a review, self-review, audit, validator, test or CI of the plugin itself.
- planned: a planned capability or refactor with no incident behind it (new feature, restructure, rename).
- unknown: the text does not say.
Also give "evidence": at most 12 words quoted or paraphrased from the text that decided it.

Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"trigger": "...", "evidence": "..."}, ...}

Changes:
"""


VERDICT_HEADER = """You read the full instructions of one verification skill (or workflow) of a coding-agent plugin.
Answer three questions about it:
- verdict: does the run END with an explicit verdict from a fixed set (e.g. APPROVE / REQUEST_CHANGES,
  PASS / FAIL, a named status), rather than free prose?
- untrusted: does it tell the agent (or model) to treat outside text it reads (PR bodies, comments,
  fetched pages, repo files, tool output) as data and never as instructions?
- bounded: is every retry, poll or wait loop it describes bounded (a maximum count, time limit or
  timeout), with no loop that can run forever?
For each give "yes" or "no" and a "quote": an exact substring of at most 15 words copied verbatim from
the text that shows it ("" when no).

Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"verdict": "...", "verdict_quote": "...", "untrusted": "...", "untrusted_quote": "...",
          "bounded": "...", "bounded_quote": "..."}, ...}

Skill:
"""


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def db():
    d = sqlite3.connect(DB)
    d.execute("CREATE TABLE IF NOT EXISTS step_cache (h TEXT PRIMARY KEY, kind TEXT, mode TEXT)")
    d.execute("CREATE TABLE IF NOT EXISTS trigger_cache (h TEXT PRIMARY KEY, trigger TEXT, evidence TEXT)")
    d.execute("CREATE TABLE IF NOT EXISTS spend (task TEXT, usd REAL, ts TEXT DEFAULT CURRENT_TIMESTAMP)")
    return d


def sections(text):
    return [p for p in re.split(r"(?m)^(?=#{2,4} )", text) if p.startswith("#")]


def procedure_files(tree):
    return sorted(p for p in tree if p.endswith(".md") and (p.startswith("skills/") or p.startswith("references/")))


def step_items():
    """[(hash, text)] for every section at every snapshot, plus the per-snapshot index the data code reads."""
    items, index = {}, []
    for day in SNAPSHOTS:
        sha = G.sha_at(G.PLUGIN, day)
        t = G.tree(G.PLUGIN, sha)
        paths = procedure_files(t)
        txt = G.blobs(G.PLUGIN, [t[p] for p in paths])
        for p in paths:
            for s in sections(txt[t[p]]):
                k = h(s)
                items[k] = s[:MAX_CHARS]
                index.append((day, p, k, len(s)))
    return list(items.items()), index


def trigger_items(con):
    """One text per plugin change: merged PRs, and commits pushed straight to main before PR #1."""
    out = []
    for r in con.execute("""SELECT number, title, body_redacted FROM github.prs
                            WHERE repo = 'wayfare-skills' AND merged_ts IS NOT NULL"""):
        first = []
        for s in con.execute("SELECT session_id_hash, pr_links FROM harness.sessions WHERE pr_links LIKE ?",
                             (f"%-skills#{r[0]}\"%",)):
            p = con.execute("""SELECT text_redacted FROM harness.turns WHERE session_id_hash = ? AND role = 'user'
                               AND text_redacted NOT LIKE '<%' ORDER BY idx LIMIT 1""", (s[0],)).fetchone()
            if p and p[0]:
                first.append(p[0][:500])
        text = f"PR #{r[0]}: {r[1]}\n{(r[2] or '')[:1800]}" + (f"\nOwner's first words: {' | '.join(first)[:700]}"
                                                                  if first else "")
        out.append((f"pr:{r[0]}", text))
    for r in con.execute("""SELECT sha, subject, body_redacted FROM git.commits
                            WHERE repo = 'wayfare-skills' AND pr_number IS NULL AND is_merge = 0"""):
        out.append((f"commit:{r[0]}", f"Commit: {r[1]}\n{(r[2] or '')[:1500]}"))
    return out


def run_steps(d):
    items, index = step_items()
    cost = run_batches(d, "step_cache", items, STEP_HEADER, 25, ["kind", "mode"])
    d.execute("DROP TABLE IF EXISTS step_index")
    d.execute("CREATE TABLE step_index (day TEXT, path TEXT, h TEXT, chars INTEGER)")
    d.executemany("INSERT INTO step_index VALUES (?,?,?,?)", index)
    d.execute("INSERT INTO spend (task, usd) VALUES ('steps', ?)", (cost,))
    d.commit()
    print(f"steps: {len(items)} sections, ${cost:.2f}")


def run_triggers(d):
    from cube.db import connect
    con = connect()
    units = trigger_items(con)
    items = [(h(t), t) for _, t in units]
    cost = run_batches(d, "trigger_cache", items, TRIGGER_HEADER, 20, ["trigger", "evidence"])
    d.execute("DROP TABLE IF EXISTS trigger_index")
    d.execute("CREATE TABLE trigger_index (unit TEXT, h TEXT)")
    d.executemany("INSERT INTO trigger_index VALUES (?,?)", [(u, k) for (u, _), (k, _) in zip(units, items)])
    d.execute("INSERT INTO spend (task, usd) VALUES ('triggers', ?)", (cost,))
    d.commit()
    print(f"triggers: {len(items)} changes, ${cost:.2f}")


VERDICT_SKILLS = ["wayfare-review-pr", "wayfare-ship-pr", "wayfare-audit-security", "wayfare-audit-compliance",
                  "wayfare-review-architecture", "wayfare-review-fleet", "wayfare-check-preflight",
                  "wayfare-audit-plugin", "auto-approve workflow"]
VFIELDS = ["verdict", "verdict_quote", "untrusted", "untrusted_quote", "bounded", "bounded_quote"]


def verdict_doc(tree, skill):
    """The skill's SKILL.md and WORKFLOW.md plus every references/ or docs/ file they name, as one text."""
    if skill == "auto-approve workflow":
        paths = sorted(p for p in tree if p.startswith(".github/workflows/") and "approve" in p)
    else:
        paths = [p for p in (f"skills/{skill}/SKILL.md", f"skills/{skill}/WORKFLOW.md") if p in tree]
        body = "\n".join(G.blobs(G.PLUGIN, [tree[p] for p in paths]).values())
        for ref in sorted(set(re.findall(r"(references/[\w.-]+\.md|docs/[A-Z][\w.-]+\.md)", body))):
            if ref in tree and ref not in paths:
                paths.append(ref)
    txt = G.blobs(G.PLUGIN, [tree[p] for p in paths])
    return "\n\n".join(f"<<< {p} >>>\n{txt[tree[p]]}" for p in paths)


def run_verdicts(d):
    d.execute(f"CREATE TABLE IF NOT EXISTS verdict_cache (h TEXT PRIMARY KEY, {', '.join(f + ' TEXT' for f in VFIELDS)})")
    t = G.tree(G.PLUGIN, G.sha_at(G.PLUGIN, SNAPSHOTS[-1]))
    docs = [(s, verdict_doc(t, s)[:120000]) for s in VERDICT_SKILLS]
    items = [(h(x), x) for _, x in docs]
    cost = run_batches(d, "verdict_cache", items, VERDICT_HEADER, 1, VFIELDS)
    d.execute("DROP TABLE IF EXISTS verdict_index")
    d.execute("CREATE TABLE verdict_index (skill TEXT, h TEXT)")
    d.executemany("INSERT INTO verdict_index VALUES (?,?)", [(s, k) for (s, _), (k, _) in zip(docs, items)])
    d.execute("INSERT INTO spend (task, usd) VALUES ('verdicts', ?)", (cost,))
    d.commit()
    print(f"verdicts: {len(items)} skills, ${cost:.2f}")


if __name__ == "__main__":
    d = db()
    for task in sys.argv[1:] or ["steps", "triggers"]:
        {"steps": run_steps, "triggers": run_triggers, "verdicts": run_verdicts}[task](d)
