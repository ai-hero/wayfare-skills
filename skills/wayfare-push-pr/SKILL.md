---
name: wayfare-push-pr
description: "Test the work, commit it, push it, and open a draft PR with a CI report. Use when work is ready to check or share. Use test or commit mode to stop before publishing."
argument-hint: "[recalibrate | test [MODIFIER...] | commit | ready | target-branch]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access for publishing, and the repository configuration described by HERO.md."
---

# Push a pull request

Check the outstanding work before publication. Create a focused commit. Push the
feature branch. Open a draft PR by default. If the argument names a target
branch, merge the pushed branch into that target instead of opening a PR. This
mode bypasses the approval workflow. Use it only when the person names the
target themselves. Never use the default branch as that target. Never commit or
push directly to the default branch. Publish only after tests pass and you
understand the diff.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before running this skill. It defines
the argument modes, repository-state checks, verification and smoke-test
selection, commit construction, publication sequence, and failure behavior.

Use [the authorization model](../../references/authorization.md) for actions
that change local or remote state. Use
[the client capability map](../../references/client-capabilities.md) where the
workflow names a client-specific tool or chained skill.

## Invariants

- Preserve unrelated user changes. Never rewrite history without explicit
  authorization.
- A test failure stops publication and is reported with actionable evidence.
- A successful default run leaves a pushed branch and a discoverable draft PR.
  Continue into `wayfare-review-pr` and `wayfare-ship-pr` without asking. If
  another skill runs this skill as a step, return control to that skill instead.
- `test` and `commit` modes stop at the boundary their names promise.

Return the verification result, commit and branch state, PR URL when one was
created, CI state, and the next safe action.
