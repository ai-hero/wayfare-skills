---
name: wayfare-respond-pr
description: "Address actionable PR review comments. Check the fixes and resolve the corresponding conversations. Use when a reviewer or review bot leaves feedback on your pull request."
argument-hint: "[pr-number | recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, and write access to the pull request branch."
---

# Respond to pull-request feedback

Read unresolved review feedback. Classify it before making changes. Make only
justified fixes. Check the result. Resolve a conversation only when you
addressed its concern.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before running this skill, before
changing code or remote review state. It defines PR discovery, branch checks,
feedback retrieval, classification, fix and verification behavior, thread
replies, summaries, and the review loop.

Use [the authorization model](../../references/authorization.md) to avoid
redundant prompts for ordinary fixes already requested while retaining gates for
ambiguous product choices and consequential remote actions. Use
[the client capability map](../../references/client-capabilities.md) when the
workflow names a client-specific file, shell, or skill facility.

## Invariants

- Do not implement ambiguous feedback as though it were a requirement.
- Do not resolve a thread until its concern is addressed or explicitly declined
  with rationale.
- Preserve unrelated changes. Never force-push without explicit authority.
- Verification evidence accompanies every code-changing response cycle.

Return addressed, declined, unresolved, and newly discovered findings plus the
commit, push, and thread-resolution state.
