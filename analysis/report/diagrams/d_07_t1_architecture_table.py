"""Table 7.T1: one row per component drawn in Diagram 7.1, in the order the diagram reads.

The rows are written as a Markdown table to `.analysis/diagrams/book/<name>.md`; `finish` gets an empty
1x1 canvas so it writes only the sidecar.
"""
import os

import svg_lib as S

NAME = "table-07-01-architecture-part-by-part"
COLS = ["Component", "Purpose", "Current implementation", "System of record", "Evidence or sensor", "Owner",
        "Open gap"]

ROWS = [
    ["**Control plane**", "", "", "", "", "", ""],
    ["Work intake and goals",
     "Turn signals into work items, group them into goals, keep a revisable plan",
     "Grill, sync-plan and audit skills propose items; the owner authorizes goals and approves plans",
     "`.plans/` in each repository (work items, goals, logs)",
     "Q component-traffic; Q new-work-sources; Q cost-by-architecture-depth",
     "The owner",
     "Nothing starts or resumes work without a person; 35% of change sets had a work item and 27% a goal"],
    ["Shared skills",
     "Make the supported path the default path for every cell",
     "The wayfare plugin, installed once per machine; HERO.md configures it per repository",
     "The plugin repository, at `main`",
     "Q component-traffic; Q plugin-restructures; Q skill-run-frequency",
     "The plugin (control plane)",
     "No versioning, staged rollout or rollback; the 21 September rename broke 13 repositories"],
    ["Policy register",
     "State each fleet expectation with the sensor that checks it",
     "CONTROLS.yaml and CHECKS.yaml in the plugin plus a local fleet overlay; the audit writes CONSISTENCY.md",
     "The plugin and the `.fleet` overlay",
     "Q rule-change-review; Q audit-frequency",
     "The plugin (control plane)",
     "Runs only when the owner starts a sync; rule changes go in unreviewed; no exceptions or deadlines recorded"],
    ["Merge policy",
     "Approve, reject or escalate a change set on the evidence attached to it",
     "The auto-approve reusable workflow every repository calls",
     "The workflow file in the plugin; approvals on the pull request",
     "Q component-traffic; Q no-human-merges; Q who-catches-mistakes",
     "The plugin (control plane)",
     "Reads the review report, not the code; no canary before a shared change; authority does not contract when evidence fails"],
    ["Message routing",
     "Carry a request to the cell that owns the change and track the response",
     "The mailbox: an inbox directory in a repository, written by an agent in another",
     "Inbox files in the receiving repository",
     "Q message-delivery; Q coordination-limits",
     "The plugin (control plane)",
     "Few repositories have an inbox; replies to a repository without one are lost; nothing wakes the receiver"],
    ["Credentials",
     "Grant each role the capability its action needs",
     "Repository secrets for the gate; the agent runs on the owner's account",
     "GitHub repository secrets; the owner's account",
     "Q expired-logins",
     "The owner",
     "Authority is an identity, not a capability; no revocation path"],
    ["Fleet inventory",
     "Know which cells exist, who owns them and what they depend on",
     "FLEET.md: groups, ports, roles",
     "FLEET.md, local and unversioned",
     "Q onboarding-speed; Q coordination-limits",
     "The owner",
     "Local to one machine; no dependency graph, so a failed shared release cannot name the affected cells"],
    ["Evidence index",
     "Link checks, review, deployment and outcome to the change that caused them",
     "Session logs, git, pull requests, CI and plans, joined by the scripts written for this study",
     "The study's databases on the owner's machine",
     "Q git-only-measurability; Q unified-timeline; Q change-set-work-item-links",
     "The study (the owner)",
     "294 days before session logs began; plans untracked for 72 days; no work identifier on sessions or branches"],
    ["Operational view (proposed)",
     "Show what every cell is doing and why work is waiting",
     "None",
     "None",
     "Q binding-constraint (the waiting it would show)",
     "None yet",
     "The first priority of Chapter 9: a control plane independent of one workstation with a collaborative surface"],
    ["**Work cell**", "", "", "", "", "", ""],
    ["Harness",
     "Run the agent: model, subagents, hooks, memory, permissions",
     "Claude Code on the owner's account and laptop, in auto mode",
     "The session log the harness keeps",
     "Q session-clock; Q worktree-use; Q feature-uptake-lag",
     "The vendor; chosen, not built",
     "Parallel agents share one checkout; runs on one workstation under one account's usage limits"],
    ["Local context",
     "Give a fresh session what it needs without loading everything",
     "Code, AGENTS.md, HERO.md, DESIGN.md, tests and design references in the repository",
     "The repository",
     "Q design-record-lag; Q design-guardrails-fired; Q observable-work-share",
     "The cell",
     "DESIGN.md is checked for format, not truth; work asked for directly in a session leaves no plan"],
    ["Connectors",
     "Declare what the cell reaches outside its code",
     "`## Connections` in HERO.md, one block per kind; Claude Design read through a tool",
     "HERO.md in the repository",
     "Q declared-connections; Q unreachable-connections; Q expired-logins",
     "The cell",
     "A declared but unreachable connection reads as absent; two kinds nothing reads; logins only the owner can do"],
    ["Local sensors",
     "Catch a mistake before the merge policy sees the change set",
     "Pre-commit hooks, CI, tests and review agents on the pull request",
     "CI runs and review comments on the pull request",
     "Q hollow-checks; Q who-catches-mistakes; Q scanner-coverage",
     "The cell",
     "Checks that can never fail; secret scanning is a local hook in most repositories"],
    ["Delivery path",
     "Move a merged change to production and observe it there",
     "Merge, CI build, image, server pull; the owner does the logins agents cannot",
     "CI runs and the deployed image",
     "Q deploy-on-merge; Q production-uptime",
     "The cell",
     "Health evidence does not yet close the goal or open follow-up work; rollback is manual"],
]


def main():
    lines = ["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
    for r in ROWS:
        lines.append("| " + " | ".join(r) + " |")
    os.makedirs(S.OUT, exist_ok=True)
    with open(os.path.join(S.OUT, f"{NAME}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    S.finish(
        S.Canvas(1, 1), id="7.T1", kind="table", name=NAME,
        caption="The components of Diagram 7.1, one row each: what it is for, what stands in for it today, where "
                "its record lives, which question measures it, who owns it and what is still missing.",
        alt="A table with one row per component of Diagram 7.1, grouped into control plane and work cell, and "
            "columns for purpose, current implementation, system of record, evidence or sensor, owner and open gap.",
        source="Replaces D04 THE ARCHITECTURE SO FAR · PART BY PART. Purposes from Chapter 7; implementations "
               "and gaps from the components deck's part-by-part table and prose "
               "(analysis/report/components/deck.py, PARTS_TABLE and PART_PROSE), Chapter 7 'Shared services and "
               "blast radius' (13 repositories, 21 September rename) and Chapter 9 'What I would change next' "
               "(294 days, 72 days); shares from Q component-traffic (35%, 27%). Sensors are question cards in "
               "the figures appendix.",
    )


if __name__ == "__main__":
    main()
