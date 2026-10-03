---
name: wayfare-ship-pr
description: "Trigger the configured approval workflow and read its verdict. Merge an approved PR and check state after the merge. Use after review when a pull request is ready to ship."
argument-hint: "[pr-number | recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, repository approval configuration, and permission to merge."
---

# Ship a pull request

Ship only the reviewed, current PR head. The reusable approval workflow affects
the whole fleet. Preserve all invariants for branch protection, stale approvals,
last-push approval, and rebasing.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before running this skill, before
triggering approval or changing remote state. It defines preflight, rebase
ordering, approval triggering, verdict interpretation, merge authorization,
cleanup, and post-merge verification.

Use [the authorization model](../../references/authorization.md). Merging
changes external state and retains an explicit authorization gate. Use
[the client capability map](../../references/client-capabilities.md) to
translate any client-specific invocation language without changing behavior.

## Invariants

- Rebase onto the current base before requesting approval, never after it.
- Never merge a stale head, bypass branch protection, or use an admin override.
- Treat a zero-job approval run as a failed startup, not a passing verdict.
- A deployment check is advisory after merge and never rewrites history.
- Cleanup occurs only after the merged head is identified exactly.

Return the approved head and verdict, merge result, cleanup result, post-merge
CI and deployment evidence, and any deferred verification.
