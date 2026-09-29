---
name: wayfare-push-pr
description: Test, commit, push, and open a draft PR with a CI report. Use when work is ready to verify or share; use its test or commit modes when the run must stop before publishing.
argument-hint: "[recalibrate | test [MODIFIER...] | commit | ready | target-branch]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access for publishing, and the repository configuration described by HERO.md."
---

# Push a pull request

Verify the outstanding work, create a focused commit, push the feature branch,
and open a draft PR by default. Never commit or push directly to the default
branch. Treat tests and a clean understanding of the diff as prerequisites to
publication.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before running this skill. It defines
the argument modes, repository-state checks, verification and smoke-test
selection, commit construction, publication sequence, and failure behavior.

Use [the authorization model](../../references/authorization.md) for actions
that change local or remote state. Use
[the client capability map](../../references/client-capabilities.md) where the
workflow names a client-specific tool or chained skill.

## Invariants

- Preserve unrelated user changes and never rewrite history without explicit
  authorization.
- A test failure stops publication and is reported with actionable evidence.
- A successful default run leaves a pushed branch and a discoverable draft PR.
- `test` and `commit` modes stop at the boundary their names promise.

Return the verification result, commit and branch state, PR URL when one was
created, CI state, and the next safe action.
