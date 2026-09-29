"""1.8 The evidence chain behind the book: three source families, the identifiers that join them, the tables
the analysis derives, and where the record is missing or the join is inferred."""
import os
import sqlite3
from datetime import date

import svg_lib as S

DATA = os.path.join(S.ROOT, ".analysis", "data")
# No Claude Code session is logged between 9 and 25 Aug 2026 (CHAPTER_BRIEF.md, "Data not available, 10–24 Aug").
GAP = ("2026-08-10", "2026-08-24")


def q(db, sql):
    con = sqlite3.connect(os.path.join(DATA, db))
    row = con.execute(sql).fetchone()
    con.close()
    return row


def count(db, table, col=None, where=""):
    """(count, first day, last day) of a table, the days from `col`."""
    if col is None:
        return q(db, f"SELECT COUNT(*) FROM {table} {where}")[0], None, None
    return q(db, f"SELECT COUNT(*), MIN(SUBSTR({col},1,10)), MAX(SUBSTR({col},1,10)) FROM {table} {where}")


def d(iso):
    return date.fromisoformat(iso).strftime("%-d %b %Y")


def n(v):
    return f"{v:,}"


def span(first, last):
    return f"{d(first)} to {d(last)}"


commits = count("git.sqlite", "commits", "day")
pr_commits = count("pr_commits.sqlite", "pr_commits", "ts")
prs = count("github.sqlite", "prs", "day")
reviews = count("github.sqlite", "pr_reviews", "submitted_ts")
ci = count("github.sqlite", "ci_runs", "day")
items = count("plans.sqlite", "plan_items", "created_ts", "WHERE type != 'goal'")
goals = count("plans.sqlite", "plan_items", "created_ts", "WHERE type = 'goal'")
messages = count("plans.sqlite", "messages", "created_ts")
docs = count("knowledge.sqlite", "doc_versions", "day")
register = count("knowledge.sqlite", "register_history", "ts")
sessions = count("harness.sqlite", "sessions", "day")
turns = count("harness.sqlite", "turns", "ts")
tools = count("harness.sqlite", "tool_calls", "ts")
prompts = count("harness.sqlite", "prompts", "day")
gap_sessions = q("harness.sqlite", f"SELECT COUNT(*) FROM sessions WHERE day BETWEEN '{GAP[0]}' AND '{GAP[1]}'")[0]
assert gap_sessions == 0, gap_sessions
sessions_with_pr = q("harness.sqlite", "SELECT COUNT(*) FROM sessions WHERE pr_links NOT IN ('', '[]') AND pr_links IS NOT NULL")[0]
items_with_pr = q("plans.sqlite", "SELECT COUNT(*) FROM plan_items WHERE type != 'goal' AND raw_frontmatter_json LIKE '%\"pr\"%'")[0]
items_with_branch = q("plans.sqlite", "SELECT COUNT(*) FROM plan_items WHERE type != 'goal' AND raw_frontmatter_json LIKE '%\"branch\"%'")[0]
sets_haiku = q("detectors.sqlite", "SELECT COUNT(*) FROM cs_sets s JOIN cs_units u ON u.repo = s.repo AND "
                                   "u.unit_kind = s.unit_kind AND u.unit_id = s.unit_id WHERE u.method = 'haiku'")[0]
# The book's headline count: change sets in 2026 with Dependabot's left out (report/record.py changeset_facts,
# as the intro deck's "Proof of work" slide computes it).
CHANGE_SETS_2026 = 2492
DEPLOYED = 4

c = S.Canvas(1400, 1590)

# Column 1: three source families.
git = c.group(40, 40, 400, 510, "Git, GitHub and CI")
c.node(60, 76, 360, 84, "evidence", f"Commits on main · {n(commits[0])}", span(commits[1], commits[2]))
c.node(60, 172, 360, 84, "evidence", f"Original PR commits · {n(pr_commits[0])}", span(pr_commits[1], pr_commits[2]))
c.node(60, 268, 360, 84, "evidence", f"Pull requests · {n(prs[0])}", f"reviews {n(reviews[0])} · {span(prs[1], prs[2])}")
c.node(60, 364, 360, 84, "evidence", f"CI runs · {n(ci[0])}", f"deploy and health runs among them · from {d(ci[1])}")
c.text(60, 470, "Covers the whole study period.", size=S.SMALL, color=S.BODY, width=360)

factory = c.group(40, 590, 400, 520, "Factory records")
c.node(60, 626, 360, 84, "evidence", f"Work items · {n(items[0])}", f".plans, from {d(items[1])}")
c.node(60, 722, 360, 84, "evidence", f"Goals · {goals[0]} · Messages · {messages[0]}",
       f"from {d(goals[1])} and {d(messages[1])}")
c.node(60, 818, 360, 84, "evidence", f"Guide versions · {n(docs[0])}", f"HERO.md, AGENTS.md, DESIGN.md · from {d(docs[1])}")
c.node(60, 914, 360, 84, "evidence", f"Register versions · {register[0]}", f"from {d(register[1])}")
c.text(60, 1020, "Begin when each capability was built: earlier practice has no record here.", size=S.SMALL,
       color=S.BODY, width=360)

harness = c.group(40, 1150, 400, 400, "Harness logs · Claude Code")
c.node(60, 1186, 360, 84, "evidence", f"Sessions · {sessions[0]}", f"from {d(sessions[1])}; 15 repos · cost, subagents, asks")
c.node(60, 1282, 360, 84, "evidence", f"Turns · {n(turns[0])}", f"tool calls {n(tools[0])}")
c.node(60, 1378, 360, 84, "evidence", f"Typed prompts · {n(prompts[0])}",
       f"from {d(prompts[1])}; continue through the gap below")
c.text(60, 1484, f"Not available: {d(GAP[0])} to {d(GAP[1])}, no session logged.",
       size=S.SMALL, color=S.MUTED, width=360)

# Column 2: the identifiers that join them.
ids = c.group(540, 300, 300, 600, "Shared identifiers")
id_nodes = [
    ("Repository", "every table"),
    ("Commit sha", "commits, PR commits, CI runs"),
    ("Pull request number", "commits, PRs, reviews, items, sessions"),
    ("Branch", "items, sessions"),
    ("Item and goal id", "items, goals, logs, messages"),
    ("Session id", "sessions, turns, tool calls"),
]
for i, (label, sub) in enumerate(id_nodes):
    c.node(560, 336 + i * 92, 260, 80, "record", label, sub)

# Column 3: what the analysis derives.
derived = c.group(940, 300, 420, 600, "Derived tables")
sets = c.node(960, 336, 380, 108, "evidence", f"Change sets · {n(CHANGE_SETS_2026)}",
              f"2026, Dependabot left out; a model groups each PR's original commits ({n(sets_haiku)} sets)")
stage = c.node(960, 464, 380, 84, "evidence", "Repository stage on each day",
               "skills, work items, goals, messages: first HERO.md, item, goal, message")
link = c.node(960, 568, 380, 110, "evidence", "Session and item to pull request",
              f"{sessions_with_pr} of {sessions[0]} sessions name a PR; {items_with_pr} of {n(items[0])} items name "
              f"a PR, {items_with_branch} a branch")
deploy = c.node(960, 698, 380, 84, "evidence", "Deploy and health runs",
                f"{DEPLOYED} apps deploy on merge; the rest are not deployed by choice")
c.text(960, 806, "Grey open-headed joins are inferred by a model or from a name; ink joins are keyed.",
       size=S.SMALL, color=S.BODY, width=380)

# Sources into identifiers.
c.arrow((440, 300), (540, 400), "flow", via=((490, 300), (490, 400)))
c.arrow((440, 700), (540, 744), "flow", via=((490, 700), (490, 744)))
c.arrow((440, 1330), (540, 836), "flow", via=((470, 1330), (470, 836)))

# Identifiers into derived tables.
c.arrow((840, sets.cy), (960, sets.cy), "dependency", "inferred")
c.arrow((840, stage.cy), (960, stage.cy), "flow")
c.arrow((840, link.cy), (960, link.cy), "dependency", "inferred")
c.arrow((840, deploy.cy), (960, deploy.cy), "flow")

# Derived tables into the book.
book = c.node(940, 1000, 420, 90, "record", "The book's questions",
              "each figure cites its tables; the data ends with September 2026")
c.arrow((1150, 900), (1150, 1000), "flow")

S.finish(
    c, id="1.8", name="diagram-01-08-evidence-chain",
    caption="Git and GitHub cover the whole study, the factory's own records begin only when each capability "
            "was built, the session logs start on 9 August with a fortnight missing, and two of the four "
            "derived tables rest on inferred joins rather than keys.",
    alt="A provenance diagram in three columns. Left, three source families with record counts and coverage "
        "windows: Git, GitHub and CI; factory records such as work items, goals, messages, guide and register "
        "versions; and Claude Code harness logs, with 10 to 24 August 2026 marked as not available. Middle, the "
        "shared identifiers that join them: repository, commit sha, pull request number, branch, item and goal "
        "id, session id. Right, the derived tables: change sets, repository stage per day, session and item to "
        "pull request, deploy and health runs, with the model-grouped and name-matched joins drawn as inferred; "
        "all flow into the book's questions.",
    source="D20 PROOF OF WORK · THE RECORD; D25 WHERE THE EVIDENCE COMES FROM. Counts and windows queried at "
           "build time from .analysis/data: git.sqlite commits; pr_commits.sqlite pr_commits; github.sqlite prs, "
           "pr_reviews, ci_runs; plans.sqlite plan_items (type = goal or not), messages; knowledge.sqlite "
           "doc_versions, register_history; harness.sqlite sessions, turns, tool_calls, prompts (pr_links for "
           "sessions naming a PR); detectors.sqlite cs_sets and cs_units (method = haiku); plan_items "
           "raw_frontmatter_json for the pr and branch fields. Change sets 2,492: report/record.py "
           "changeset_facts, 2026, Dependabot left out (Chapter 1, 'Evidence from a factory in motion'). "
           "Deployed apps: report/deployment/data.py DEPLOYED_APPS. Missing 10–24 Aug sessions: CHAPTER_BRIEF.md.",
)
