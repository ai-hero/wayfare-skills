# Planning a task

`sync`'s postflight, not a verb of its own: how a task moves from `accepted`
through `planning` to the user's ready-mark.

Planning is `wayfare:wayfare-grill-idea FEATURE_ID`, whose **Feature mode**
plans the task in place, invoked by `sync`'s *Plan the set* over the whole
roadmap, and wayfare owns only the contract it fills:

- The flip `accepted → planning` happens as the run starts (an
  already-`planning` task resumes; `ready` and later are refused, replanning
  those goes through `sync`).
- Grilling runs against the task's `source` paths, the source architecture
  (`DESIGN.md`, when present; see sync's *Map the source*), the target design,
  the UX flow (`ux-flow`) for the steps this task's story covers, the source
  repo's configured component registry (when one exists; see sync's
  Investigate), the repo's `wayfare: recipe` skills (a recipe that fits is named
  in `## Approach`, and wayfare-build-task invokes it instead of hand-rolling
  the procedure), and the task's own `## Log`.
- **The slice is grilled first.** Before planning how, confirm the task still
  passes the SLC test: name what a person can do when it ships, and whether it
  works every time for that path. A task that turns out to be a layer, or that
  cannot be made Complete without swallowing three more stories, is a shaping
  problem. Say so and route it to `sync`'s **horizontal slices** finding rather
  than planning around it.
- **Plan it the way a principal architect would.** wayfare-grill-idea's
  *Principal Checklist* is the bar, and *Right fix, honestly sized* is the line
  that decides the approach: the fix goes at the layer the problem lives at, and
  `## Approach` names the quicker version that was not taken and what it would
  have cost. A build subagent executes this plan on a cheaper model without
  re-litigating it (*One turn* step 4), so judgment that is not written here is
  judgment nobody applies.
- **Bounded by effort, not ambition.** Right-sized is a handful of subtasks one
  build run lands as one changeset. When the correct fix is bigger than that,
  plan the smallest correct step this slice needs and route the rest to `sync`
  as its own task, `story` or `structural`.
- **`source` names where the change begins, not its boundary.** A plan that
  stops at the file list and leaves a caller, a migration or a test un-updated
  is incomplete, and the build has to go further than the plan did anyway (*One
  turn* step 4): the change reaches further, never the field, which no turn
  edits. Name the ripple in `## Subtasks` so the build works from a list rather
  than discovering it.
- Conclusions land IN the task file per the format below: `## Approach` and the
  one-line `success:`; the ordered `## Subtasks` checklist (**how** it gets
  built), sequenced along the source architecture's dependency direction (e.g.
  schema updates → structs → routes → frontend against the design system). This
  is where layer order belongs, cutting *down* through the slice; and the
  `## Definition of Done` checklist (**what must be observably true** when it
  ships: behavior in place, tests green, target design satisfied for the task's
  `target` paths, docs updated, verifiable statements, never restatements of
  subtasks). At least one DoD line must assert the **user-visible story working
  end to end**: a DoD whose every line is about one layer describes a layer, not
  a slice. `anchors.target` is refreshed to the head planned against. In
  self-review mode there is no target head to refresh it to, so it stays absent.
- The task is the unit of work, with no separate work-items. Subtasks are
  checklist lines, and wayfare-build-task works through them in order (PR
  granularity is wayfare-build-task's call, per its Step 2).
- The ready-mark is the user's (wayfare-grill-idea's Step 5): a confirmed task
  flips to `ready`, which is what `wayfare-advance-item ID` builds next. One
  exception, granted by a person at `wayfare-start-goal`'s gate and nowhere
  else: a goal with `absorb: yes` marks an **admitted** item ready inside its
  own run (*Admitting discovered work*).
