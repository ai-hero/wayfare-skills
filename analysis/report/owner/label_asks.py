"""Label every ask (an agent's AskUserQuestion) by what it asks the owner for -> .analysis/data/owner.sqlite, ask_kind.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/owner/label_asks.py

Cached by content hash of the question text, so a re-run only labels new asks.
"""
import hashlib
import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from detectors.d1_changesets import call_haiku  # noqa: E402
from ingest.fleet import OUT  # noqa: E402

DB = os.path.join(OUT, "owner.sqlite")
BATCH = 40
KINDS = ["ready", "go", "ship", "access", "design", "scope", "clarify"]
HEADER = """You are labelling questions a coding agent asked its human owner mid-session (one question, or several joined by " | ").
For each numbered question pick the ONE kind that best describes what the agent needs from the owner:
  "ready"   - approve a plan or work items: mark items ready, write/accept planned items or goals, deliver or file them
  "go"      - permission to start or continue running: authorize a goal or turn, proceed, what next, retry
  "ship"    - a PR step: apply review fixes, convert a draft to ready-for-review, merge, auto-approve, how to land
  "access"  - something only the owner has: credentials, sign-in, API keys, billing, production access, a human action outside the repo
  "design"  - a product or technical design choice between alternatives (how should X work, which option)
  "scope"   - what to include or leave out, sequencing, priority, splitting or grouping work
  "clarify" - the agent did not understand the owner's request and asks what they meant
Reply with ONLY a JSON object mapping each id to its kind, e.g. {"1": "ship", "2": "design"}.

Questions:
"""


def h(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main():
    src = sqlite3.connect(os.path.join(OUT, "harness.sqlite"))
    qs = {h(q): q for (q,) in src.execute("SELECT question_redacted FROM asks") if q}
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS ask_kind (h TEXT PRIMARY KEY, kind TEXT, method TEXT)")
    done = {r[0] for r in db.execute("SELECT h FROM ask_kind")}
    todo = [(k, q) for k, q in qs.items() if k not in done]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    def run(b):
        texts = [f"{i + 1}. {q[:600]}" for i, (_, q) in enumerate(b)]
        out, cost = call_haiku(texts, model="haiku", header=HEADER)
        return b, out, cost

    total, written = 0.0, 0
    with ThreadPoolExecutor(6) as ex:
        for b, out, cost in ex.map(run, batches):
            total += cost
            for i, (k, _) in enumerate(b):
                kind = str(out.get(str(i + 1), "")).strip().lower() if isinstance(out, dict) else ""
                if kind in KINDS:
                    db.execute("INSERT OR REPLACE INTO ask_kind VALUES (?, ?, 'haiku')", (k, kind))
                    written += 1
            db.commit()
    print(f"labelled {written} of {len(todo)} asks in {len(batches)} batches, ${total:.3f}")
    print(json.dumps(dict(db.execute("SELECT kind, COUNT(*) FROM ask_kind GROUP BY kind").fetchall())))


if __name__ == "__main__":
    main()
