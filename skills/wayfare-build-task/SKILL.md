---
name: wayfare-build-task
description: "Drive one small task through planning, implementation, review, and shipping, or resume the current goal. Use for a low-risk change that should become one PR; route larger or irreversible work through wayfare-sync-plan."
argument-hint: "[ISSUE_ID [additional-context] | DESCRIPTION | recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, and the repository configuration described by HERO.md."
---

# Build one task

Orchestrate one small, low-risk work item through:

```text
plan -> implement -> simplify -> push -> self-review -> mark-ready -> await-review -> respond -> ship
```

Keep the run to one item and one PR. A goal turn may instead produce one commit
per item on the goal branch. Route multiple items, a one-way door, or an unclear
product decision to `wayfare:wayfare-sync-plan` or `wayfare:wayfare-grill-idea`.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before executing or resuming the
pipeline. It is the executable specification: its state detection, confirmation
gates, headless stops, and cross-skill contracts are required behavior.

Use [the authorization model](../../references/authorization.md) when deciding
whether to continue, confirm, stop, or defer. Use
[the client capability map](../../references/client-capabilities.md) to
translate generic operations such as invoking another skill or delegating a
review into facilities available in the active client.

## Outcome

Report the item and PR state, completed stages, verification evidence, any
remaining gate, and the next safe action. Do not claim a stage completed unless
its observable postcondition holds.
