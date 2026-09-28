"""Haiku labels for Q stale-prose-fixes: which change sets correct prose that had gone false.

Candidates are change sets that touch a markdown file or whose label or commit subjects
mention docs, comments, instructions or staleness; the rest cannot be prose corrections.
Labels go to .analysis/data/memory.sqlite (prose_labels), cached by content hash.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/memory/label_prose.py
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
sys.path.insert(0, os.path.dirname(HERE))
from cube.db import connect  # noqa: E402
from detectors.d1_changesets import call_haiku  # noqa: E402
import record as F  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "memory.sqlite")
VERSION = "prose-v2"
BATCH = 150
KW = re.compile(r"comment|\bdocs?\b|readme|agents\.md|claude\.md|design\.md|hero\.md|instruction|stale|outdated|"
                r"\bfalse|wording|prose|typo", re.I)

HEADER = """You read change sets from software repos built by coding agents. For each one decide
whether it CORRECTS PROSE THAT HAD GONE FALSE: an edit to text (a markdown file or a code
comment) because the text stated something untrue about the code or process as it already was:
a stale instruction, a wrong doc statement, a comment describing old behaviour, a dead pointer.

It is NOT a correction (answer "n") when:
- the change fixes code or config and only updates docs to match the new behaviour;
- it adds new docs, new instructions or a new section;
- it renames or moves things and updates references as part of that;
- it rewords for style or adopts a template/standard layout without saying the old text was wrong.
Most change sets are "n". Say "i", "d" or "c" only when the commit text shows the old words were wrong.

Answer per change set with four fields:
- "k": where the false prose was: "i" = agent instructions (AGENTS.md, CLAUDE.md, .claude/rules,
  SKILL.md, HERO.md), "d" = docs (README, DESIGN.md, docs/, other .md), "c" = code comments, "n" = none.
- "w": 1 if correcting the prose is the whole change set; 0 if it rides inside other work (or k is "n").
- "z": 1 if the change set deletes or trims code comments as noise (narration, restated code, history); else 0.
- "m": 1 only if the text explicitly says someone or some agent ACTED on the false prose (followed it,
  was misled, a run broke because of it); else 0.

Reply with ONLY a JSON object, no prose, no fence: {"<id>": {"k": "n", "w": 0, "z": 0, "m": 0}, ...}

Change sets:
"""


def candidates(con):
    files = {}
    for r in con.execute("SELECT repo, sha, files_json FROM pr_commits.pr_commits"):
        files[(r[0], r[1])] = [f["path"] for f in json.loads(r[2] or "[]")]
    for r in con.execute("SELECT repo, sha, path FROM git.commit_files"):
        files.setdefault((r[0], r[1]), [])
        if r[2] not in files[(r[0], r[1])]:
            files[(r[0], r[1])].append(r[2])
    commits = {(c["repo"], c["sha"]): c for c in F.commit_facts(con)}
    out = []
    for s in F.changeset_facts(con):
        if s["dependabot"]:
            continue
        fs = sorted({p for sha in s["shas"] for p in files.get((s["repo"], sha), [])})
        cs = [commits[(s["repo"], sha)] for sha in s["shas"] if (s["repo"], sha) in commits]
        subjects = [c["subject"] for c in cs]
        if not (any(p.endswith(".md") for p in fs) or KW.search(s["label"] or "") or any(KW.search(x) for x in subjects)):
            continue
        md = [p for p in fs if p.endswith(".md")][:6]
        other = [p for p in fs if not p.endswith(".md")][:6]
        body = " / ".join(l.strip() for c in cs[:3] for l in c["body"].splitlines()
                          if l.strip() and not l.lower().startswith(("co-authored-by", "signed-off-by")))[:400]
        text = (f"label: {s['label']}\ncommits: {' | '.join(subjects[:6])}\nbody: {body}\n"
                f"md files: {', '.join(md) or '-'}\nother files: {', '.join(other) or '-'}"
                f"{' (+more)' if len(fs) > 12 else ''}")
        key = f"{s['repo']}|{s['unit_kind']}|{s['unit_id']}|{s['set_idx']}"
        out.append((key, hashlib.sha256((VERSION + text).encode()).hexdigest(), text))
    return out


def main():
    con = connect()
    cands = candidates(con)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS prose_cache (h TEXT PRIMARY KEY, k TEXT, w INTEGER, z INTEGER, m INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS prose_labels (cs_key TEXT PRIMARY KEY, h TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS spend (task TEXT, usd REAL)")
    done = {r[0] for r in db.execute("SELECT h FROM prose_cache")}
    todo = list({h: (h, t) for _, h, t in cands if h not in done}.values())
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)][:int(os.environ.get("LIMIT", 10 ** 6))]
    print(f"{len(cands)} candidates, {len(todo)} to label in {len(batches)} batches")

    def one(batch):
        texts = [f"=== {i} ===\n{t}" for i, (_, t) in enumerate(batch, 1)]
        res, cost = call_haiku(texts, header=HEADER)
        rows = []
        for i, (h, _) in enumerate(batch, 1):
            v = res.get(str(i)) if isinstance(res, dict) else None
            if isinstance(v, dict) and v.get("k") in ("i", "d", "c", "n"):
                rows.append((h, v["k"], int(bool(v.get("w"))), int(bool(v.get("z"))), int(bool(v.get("m")))))
        return rows, cost

    total = 0.0
    with ThreadPoolExecutor(6) as ex:
        for rows, cost in ex.map(one, batches):
            db.executemany("INSERT OR REPLACE INTO prose_cache VALUES (?,?,?,?,?)", rows)
            total += cost
            db.commit()
    db.execute("INSERT INTO spend VALUES (?, ?)", ("prose", total))
    db.execute("DELETE FROM prose_labels")
    db.executemany("INSERT INTO prose_labels VALUES (?,?)", [(k, h) for k, h, _ in cands])
    db.commit()
    print(f"spent ${total:.3f}; labelled {db.execute('SELECT COUNT(*) FROM prose_cache').fetchone()[0]}")


if __name__ == "__main__":
    main()
