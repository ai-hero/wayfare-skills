---
name: wayfare-review-pr
description: Review a PR with independent quality and security passes, applying fixes only in self-review mode. Use before marking your PR ready or when asked to review another author's PR without editing it.
argument-hint: "[#PR] [--no-mark-ready] | recalibrate"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, and optional review-agent capabilities in the active client."
---

# Review a pull request

Review the rebased PR head that can actually merge. In self-review mode, fix
confirmed findings and verify the result. When reviewing another author, leave
the tree unchanged and report or publish findings through the configured review
channel.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before executing the review. It defines
mode detection, review scopes, security coverage, severity, fix handling,
publication, and the mark-ready gate.

Use [the authorization model](../../references/authorization.md) before remote
mutations. Use
[the client capability map](../../references/client-capabilities.md) to run
independent review passes with the active client's delegation mechanism; when
delegation is unavailable, perform the passes sequentially and disclose that
limitation.

## Invariants

- Rebase before the verdict, never between the verdict and approval or merge.
- Findings cite concrete evidence and distinguish defects from preferences.
- Review mode never edits another author's branch.
- Marking a PR ready remains a consequential remote action and requires the
  workflow's authorization gate.

Return the reviewed head, findings by severity, fixes and verification, review
publication state, and the remaining gate.
