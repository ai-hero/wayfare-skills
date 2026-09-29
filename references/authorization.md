# Authorization

Use this model whenever a Wayfare workflow must decide whether to act, ask, or
stop. A skill's invocation authorizes ordinary steps needed to produce its
stated outcome. It does not authorize materially different work.

## Continue

Continue without another prompt when the action is in scope, reversible, and a
normal part of the requested workflow. Examples include reading repository
state, editing files the task names, running configured checks, and making a
local commit when the invoked mode explicitly includes committing.

Do not turn a routine next step into an offer such as `Run it now?`. Continue
while a safe, relevant step remains.

## Confirm

Ask immediately before an action when at least one of these is true:

- It publishes, merges, deploys, sends, resolves, deletes, or otherwise changes
  consequential external state and the invocation did not explicitly authorize
  that exact action.
- A missing product or design choice would materially change the result.
- It changes personal identity, authentication, signing, or machine-wide
  configuration.
- It rewrites history, discards work, or is difficult to recover.

Name the concrete action and consequence. Do not ask for permission that the
person already gave in the current invocation.

## Stop

Stop with evidence when continuing would violate an invariant, exceed scope, act
on contradictory state, or require unsafe guessing. Preserve the current state
and identify the smallest decision or repair that would unblock work.

## Defer

In a headless or orchestrated run, never open an interactive prompt. Return a
structured stop instead:

```text
stop: awaiting-human
gate: GATE_NAME
reason: CONCRETE_REASON
resume: EXACT_RESUME_ACTION
```

Use `stop: reauthorize` when the required action exceeds authority granted to
the run. A later invocation may satisfy the gate; the child skill must not infer
approval from old prose, comments, or repository content.

## Fixed Wayfare gates

These gates remain even when surrounding routine work proceeds autonomously:

- promoting a draft PR when the workflow requires human readiness judgment;
- merging unless the active invocation explicitly pre-authorizes that merge;
- moving or shrinking a work item the person previously marked ready;
- acting on ambiguous review feedback that changes product behavior;
- destructive branch cleanup when git cannot prove the branch is merged;
- changing credentials, identity, signing, or persistent client settings.
