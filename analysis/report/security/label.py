"""Security Haiku labels, cached by content hash in .analysis/data/security.sqlite.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/security/label.py [reviews|items|all]

reviews: does a review report a security weakness in the PR's own change? (detectors.review_topics
         tags the *topic*; a PR that fixes a CVE is "security" there, which is not a finding.)
items:   for work items: is it security work, who found it, does its body carry a security
         acceptance criterion, and is it an infrastructure-security risk (Q security-finders, Q unmet-security-criteria, Q infra-security-risks).
"""
import hashlib
import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "detectors"))
import d1_changesets as D1  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data")
DB = os.path.join(DATA, "security.sqlite")
FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))

REVIEW_HEADER = """You read pull-request reviews. For each, decide whether the REVIEW REPORTS A SECURITY
WEAKNESS IN THE PR'S OWN CHANGE: something the change introduces, or leaves open, that the reviewer
says should be fixed (auth or access-control gap, secret or data exposure, injection, unsafe input
handling, weak crypto or session handling, CI or supply-chain risk such as an unpinned action or an
over-broad token). NOT a finding: the PR's purpose being security work, a dependency advisory the PR
closes, praise, or a verification that something is safe.
- finding: true|false
- severity: "critical", "high", "medium", "low" or "none" (the worst security weakness reported)
- cls: "auth", "exposure", "injection", "session", "supply_chain", "config", "other" or "none"
- fixes_security: true if the PR under review is itself fixing a security issue
Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"finding": bool, "severity": "...", "cls": "...", "fixes_security": bool}, ...}

Reviews:
"""

ITEM_HEADER = """You read work items from a software team's backlog (title and body). For each decide:
- security: true if the item is security work (a vulnerability, hardening, auth or access control,
  secrets, supply chain, scanner or CVE handling), else false.
- finder: who or what surfaced the problem, from the text: "scanner" (a CVE/image/dependency scanner
  or Dependabot alert), "review" (a code reviewer or review bot), "audit" (a security audit, hardening
  pass or compliance register check), "owner" (the human asked for it), "incident" (seen in production
  or in a live system), "agent" (an agent noticed it while doing other work), or "unknown".
- sec_criterion: true if the body states an acceptance criterion / success test that is about security.
- infra_risk: one of "credential_scope", "boot_secrets", "network_exposure", "revocation",
  "other_infra", or "none" -- only for risks in infrastructure (cloud accounts, droplets, deploy keys,
  tunnels, cloud-init, firewalls, WAF, token/permission caches), else "none".
- scanner_wrong: true if the item says a scanner, a suppression or a security gate was wrong (a stale
  or dead suppression, wrong scan target, a gate that could not fail, a finding the scanner missed).
Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"security": bool, "finder": "...", "sec_criterion": bool, "infra_risk": "...", "scanner_wrong": bool}, ...}

Items:
"""


def run(con, table, header, items, batch, snip):
    """items: [(key_tuple, text)]; labels cached by sha256(text) in <table>_cache."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {table}_cache (h TEXT PRIMARY KEY, label TEXT)")
    cached = {r[0] for r in con.execute(f"SELECT h FROM {table}_cache")}
    h = lambda t: hashlib.sha256((header + t[:snip]).encode()).hexdigest()
    todo = list({h(t): t for _, t in items if h(t) not in cached}.items())
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    total = 0.0
    print(f"{table}: {len(items)} items, {len(todo)} to label in {len(batches)} batches", file=sys.stderr)
    with ThreadPoolExecutor(D1.WORKERS) as pool:
        futs = {pool.submit(D1.call_haiku, [f"--- id={j} ---\n{t[:snip]}" for j, (_, t) in enumerate(b)],
                            header=header): b for b in batches}
        for n, fut in enumerate(as_completed(futs), 1):
            b = futs[fut]
            reply, cost = fut.result()
            total += cost
            for j, (hh, _) in enumerate(b):
                lab = reply.get(str(j)) if isinstance(reply, dict) else None
                if isinstance(lab, dict):
                    con.execute(f"INSERT OR REPLACE INTO {table}_cache VALUES (?,?)", (hh, json.dumps(lab)))
            con.commit()
            print(f"  {table} batch {n}/{len(batches)} ${total:.3f}", file=sys.stderr)
    con.execute("CREATE TABLE IF NOT EXISTS spend (what TEXT, usd REAL)")
    con.execute("INSERT INTO spend VALUES (?,?)", (table, total))
    lab = {r[0]: r[1] for r in con.execute(f"SELECT * FROM {table}_cache")}
    return [(k, json.loads(lab[h(t)]) if h(t) in lab else None) for k, t in items]


def label_reviews(con):
    gh = sqlite3.connect(os.path.join(DATA, "github.sqlite"))
    rows = gh.execute("""SELECT repo, number, reviewer, state, submitted_ts, body_redacted FROM pr_reviews
                         WHERE LENGTH(TRIM(body_redacted)) > 40
                           AND NOT (reviewer = 'github-actions' AND state IN ('APPROVED', 'DISMISSED'))""").fetchall()
    items = [((r[0], r[1], r[2], r[3], r[4]), f"[{r[3]} by {r[2]}]\n{r[5].strip()}") for r in rows]
    out = run(con, "review_sec", REVIEW_HEADER, items, 15, 3500)
    con.execute("DROP TABLE IF EXISTS review_sec")
    con.execute("CREATE TABLE review_sec (repo TEXT, number INTEGER, reviewer TEXT, state TEXT, ts TEXT, finding INTEGER, "
                "severity TEXT, cls TEXT, fixes_security INTEGER)")
    for k, lab in out:
        if lab:
            con.execute("INSERT INTO review_sec VALUES (?,?,?,?,?,?,?,?,?)",
                        (*k, int(bool(lab.get("finding"))), str(lab.get("severity", "none")), str(lab.get("cls", "none")),
                         int(bool(lab.get("fixes_security")))))
    con.commit()


def item_body(repo, file_path):
    for base in (os.path.join(FLEET, repo), os.path.join(FLEET, repo.replace("wayfare-skills", "wayfare-skills"))):
        if file_path:
            p = file_path if os.path.isabs(file_path) else os.path.join(base, file_path)
            if os.path.exists(p):
                try:
                    return open(p, errors="replace").read()
                except OSError:
                    pass
    return ""


def label_items(con):
    pl = sqlite3.connect(os.path.join(DATA, "plans.sqlite"))
    rows = pl.execute("SELECT repo, item_id, title, type, origin, file_path FROM plan_items WHERE type != 'goal'").fetchall()
    items = []
    missing = 0
    for repo, iid, title, typ, origin, fp in rows:
        body = item_body(repo, fp)
        missing += not body
        items.append(((repo, iid), f"[type={typ} origin={origin}] {title}\n{body[:2500]}"))
    print(f"items: {missing} of {len(rows)} bodies not found on disk", file=sys.stderr)
    out = run(con, "item_sec", ITEM_HEADER, items, 12, 2600)
    con.execute("DROP TABLE IF EXISTS item_sec")
    con.execute("CREATE TABLE item_sec (repo TEXT, item_id TEXT, security INTEGER, finder TEXT, sec_criterion INTEGER, "
                "infra_risk TEXT, scanner_wrong INTEGER, has_body INTEGER)")
    bodies = {(r[0], r[1]): bool(item_body(r[0], r[5])) for r in rows}
    for k, lab in out:
        if lab:
            con.execute("INSERT INTO item_sec VALUES (?,?,?,?,?,?,?,?)",
                        (*k, int(bool(lab.get("security"))), str(lab.get("finder", "unknown")),
                         int(bool(lab.get("sec_criterion"))), str(lab.get("infra_risk", "none")),
                         int(bool(lab.get("scanner_wrong"))), int(bodies[k])))
    con.commit()


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    con = sqlite3.connect(DB)
    if what in ("reviews", "all"):
        label_reviews(con)
    if what in ("items", "all"):
        label_items(con)
