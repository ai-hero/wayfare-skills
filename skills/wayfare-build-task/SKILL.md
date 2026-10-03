---
name: wayfare-build-task
description: "Build one small task through planning, implementation, review, and shipping, or resume the current goal. Use for a low-risk change that fits one PR. Route larger or irreversible work through wayfare-sync-plan."
argument-hint: "[ISSUE_ID [additional-context] | DESCRIPTION | recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, and the repository configuration described by HERO.md."
---

# Build one task

Run one small, low-risk work item through this pipeline:

```text
plan -> implement -> simplify -> push -> self-review -> mark-ready -> await-review -> respond -> ship
```

Keep the run to one item and one PR. A goal turn may produce one commit per item
on the goal branch. If the work contains multiple items, route it to
`wayfare:wayfare-sync-plan` or `wayfare:wayfare-grill-idea`. Use the same route
for a one-way door or an unclear product decision.

## Load the workflow

Read [WORKFLOW.md](WORKFLOW.md) in full before executing or resuming the
pipeline. Follow its state detection, confirmation gates, headless stops, and
contracts between skills.

Use [the authorization model](../../references/authorization.md) when deciding
whether to continue, confirm, stop, or defer. Use
[the client capability map](../../references/client-capabilities.md) to
translate generic operations such as invoking another skill or delegating a
review into facilities available in the active client.

## Outcome

Report the item and PR state, completed stages, verification evidence, any
remaining gate, and the next safe action. Claim that a stage completed only if
you can observe its required final state.
