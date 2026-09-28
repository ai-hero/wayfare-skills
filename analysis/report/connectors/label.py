"""Connectors model labels (Haiku), cached in .analysis/data/connectors.sqlite.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/connectors/label.py [items|prompts|all]

items   every work item: is it design work, does it say code and design disagree, how did
        that end, and does its definition of done need a person with access the agent lacks.
prompts owner prompts that mention a login, credential or access: is it a credential wait,
        and for which system.

Each label is keyed by a hash of the text the model saw, so a re-run only pays for new rows.
The label never stores the text itself (prompts can carry secrets); only the verdict.
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
from cube.db import connect as _connect  # noqa: E402
from detectors.d1_changesets import call_haiku  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "connectors.sqlite")

ITEM_HEADER = """You label work items from a fleet of software repos. Each numbered entry is one item:
its repo, frontmatter fields and an excerpt of its body (start and end).

"The design" means the product's visual/UX design source (a claude.ai/design project, a Figma file,
design exports, mockups, a design reconciliation) or the shared design system (@aihero registry,
tokens, theme). For each item give:
- "design": "product-design" if the item is about making the app match, or reconcile with, its product
  design; "design-system" if about the shared design system / registry / tokens / theme; "none" otherwise.
- "divergence": true only if the item states that the code and the design (or design system) currently
  disagree, or that the design and the code must be reconciled on a specific point; else false.
- "outcome": only when divergence is true, how it ended, one of: "fixed-in-code" (code changed to match,
  done), "decided-to-diverge" (a recorded decision to keep the difference, or the design was judged wrong
  and the code kept), "asked-design" (sent back to the design as a question or ask, no code change yet),
  "duplicate", "dropped", "open" (not finished). Else null.
- "human_check": true only if the item's definition of done / verification needs a PERSON because the
  agent lacks access: a signed-in browser session, a cloud or infra console/login (AWS, Terraform, DNS,
  Cloudflare), an OAuth client or third-party account, secrets/credentials, a real device, a paid
  service. Ordinary code review or "owner approves" is NOT a human_check. Else false.
- "access": when human_check is true, one of "signed-in-ui", "cloud-infra", "oauth-third-party",
  "credentials", "device", "other"; else null.

Reply with JSON only: a list of objects {"i": <number>, "design": ..., "divergence": ..., "outcome": ...,
"human_check": ..., "access": ...}, one per entry, in order.

"""

PROMPT_HEADER = """You label messages the owner of a software fleet typed to a coding agent. Each numbered
line is one message (truncated). Decide whether it is a CREDENTIAL EVENT: the owner reports that they
logged in / refreshed a login / re-authenticated / supplied or rotated a credential, token or key, or
tells the agent to wait or retry because a login or credential had expired or was missing, or pastes
an auth error the agent hit. Merely discussing auth features in the product (building a login page,
OAuth code, token handling code) is NOT a credential event.

For each, give "cred": true/false and "system": one of "aws-terraform" (AWS, SSO, Terraform/OpenTofu,
EKS/kubectl, cloud), "github" (gh, GitHub tokens/apps), "secrets-manager" (1Password, vaults),
"design-account" (claude.ai / DesignSync / Figma account), "third-party" (other SaaS: Atlas, Stripe,
Sentry, email/SMS providers, registries), "browser-signin" (signing in to the app in a browser),
"other"; null when cred is false.

Reply with JSON only: a list of objects {"i": <number>, "cred": ..., "system": ...}, in order.

"""

CRED_KW = re.compile(r"log ?in|logged|sso|expired|credential|token|password|1password|\baws\b|terraform|\btofu\b|"
                     r"kubeconfig|gh auth|re-?auth|api key|secret|oauth|sign(ed)? in|permission denied|unauthori|"
                     r"\b403\b|\b401\b", re.I)


def db():
    d = sqlite3.connect(DB)
    d.execute("CREATE TABLE IF NOT EXISTS item_labels (repo TEXT, item_id TEXT, text_hash TEXT, design TEXT, "
              "divergence INTEGER, outcome TEXT, human_check INTEGER, access TEXT, PRIMARY KEY (repo, item_id))")
    d.execute("CREATE TABLE IF NOT EXISTS prompt_labels (prompt_key TEXT PRIMARY KEY, text_hash TEXT, cred INTEGER, "
              "system TEXT)")
    d.execute("CREATE TABLE IF NOT EXISTS spend (batch TEXT PRIMARY KEY, n INTEGER, usd REAL)")
    return d


def item_text(r):
    fm = json.loads(r["raw_frontmatter_json"] or "{}")
    try:
        body = open(r["file_path"]).read()
    except OSError:
        body = ""
    body = re.sub(r"^---\n.*?\n---\n", "", body, flags=re.S).strip()
    keep = {k: fm.get(k) for k in ("type", "shape", "origin", "status", "resolution", "channel", "success")
            if fm.get(k)}
    excerpt = body[:900] + (" … " + body[-350:] if len(body) > 1250 else body[900:])
    return (f"repo={r['repo']} | title: {r['title']} | {json.dumps(keep, ensure_ascii=False)[:500]} | "
            f"body: {excerpt}").replace("\n", " ")[:1800]


def prompt_key(r):
    return f"{r['ts']}|{r['repo']}"


def run_batches(d, todo, header, size, write, name):
    batches = [todo[i:i + size] for i in range(0, len(todo), size)]

    def one(b):
        texts = [f"{k + 1}. {t}" for k, (_, t, _) in enumerate(b)]
        return b, *call_haiku(texts, model="haiku", header=header)

    total = 0.0
    with ThreadPoolExecutor(6) as ex:
        for b, res, usd in ex.map(one, batches):
            total += usd
            got = {int(x.get("i", 0)): x for x in res if isinstance(x, dict)} if isinstance(res, list) else {}
            for k, (key, _, h) in enumerate(b):
                if k + 1 in got:
                    write(key, h, got[k + 1])
            d.execute("INSERT OR REPLACE INTO spend VALUES (?,?,?)", (f"{name}:{b[0][2]}", len(b), usd))
            d.commit()
            print(f"  {name}: {len(b)} labelled, ${usd:.3f}", file=sys.stderr)
    return total


def label_items(con, d):
    done = {(r[0], r[1]): r[2] for r in d.execute("SELECT repo, item_id, text_hash FROM item_labels")}
    todo = []
    for r in con.execute("SELECT repo, item_id, title, raw_frontmatter_json, file_path FROM plans.plan_items "
                         "WHERE type != 'goal'"):
        t = item_text(r)
        h = hashlib.sha1(t.encode()).hexdigest()
        if done.get((r["repo"], r["item_id"])) != h:
            todo.append(((r["repo"], r["item_id"]), t, h))
    print(f"items to label: {len(todo)}", file=sys.stderr)

    def write(key, h, x):
        d.execute("INSERT OR REPLACE INTO item_labels VALUES (?,?,?,?,?,?,?,?)",
                  (key[0], key[1], h, x.get("design"), int(bool(x.get("divergence"))), x.get("outcome"),
                   int(bool(x.get("human_check"))), x.get("access")))
    return run_batches(d, todo, ITEM_HEADER, 30, write, "items")


def label_prompts(con, d):
    done = {r[0]: r[1] for r in d.execute("SELECT prompt_key, text_hash FROM prompt_labels")}
    todo = []
    for r in con.execute("SELECT ts, repo, text_redacted FROM harness.prompts WHERE text_redacted IS NOT NULL"):
        if not CRED_KW.search(r["text_redacted"]):
            continue
        t = f"repo={r['repo']} | {r['text_redacted'][:450]}".replace("\n", " ")
        h = hashlib.sha1(t.encode()).hexdigest()
        if done.get(prompt_key(r)) != h:
            todo.append((prompt_key(r), t, h))
    print(f"prompts to label: {len(todo)}", file=sys.stderr)

    def write(key, h, x):
        d.execute("INSERT OR REPLACE INTO prompt_labels VALUES (?,?,?,?)",
                  (key, h, int(bool(x.get("cred"))), x.get("system")))
    return run_batches(d, todo, PROMPT_HEADER, 40, write, "prompts")


def main(what):
    con, d = _connect(), db()
    usd = 0.0
    if what in ("items", "all"):
        usd += label_items(con, d)
    if what in ("prompts", "all"):
        usd += label_prompts(con, d)
    total = d.execute("SELECT SUM(usd) FROM spend").fetchone()[0] or 0
    print(f"this run ${usd:.2f}; chapter total ${total:.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
