# Planning a task

`sync`'s postflight, not a verb of its own: how a task moves from `accepted`
through `planning` to the user's ready-mark.

Planning is `wayfare:wayfare-grill-idea`, whose **Feature mode** plans one task
in place and whose **Roadmap mode** plans a set in one pass, the mode `sync`'s
*Plan the set* invokes over the whole roadmap. Roadmap mode also forms the goal
a set belongs to and writes the goal's `## Plan` in that pass. Wayfare owns only
the contract it fills:

- The flip `accepted → planning` happens as the run starts (an
  already-`planning` task resumes; `ready` and later are refused, replanning
  those goes through `sync`).
- Grilling runs against the task's `source` paths, the source architecture
  (`DESIGN.md`, when present; see sync's *Map the source*), the target design,
  the UX flow (`ux-flow`) for the steps this task's story covers, the source
  repo's configured component registry (when one exists; see sync's
  Investigate), the repo's `wayfare: recipe` skills (a recipe that fits is named
  in `## Approach`, or in a goal member's slice, and wayfare-build-task invokes
  it instead of hand-rolling the procedure), and the task's own `## Log`.
- **The slice is grilled first.** Before planning how, confirm the task still
  passes the SLC test: name what a person can do when it ships, and whether it
  works every time for that path. A task that turns out to be a layer, or that
  cannot be made Complete without swallowing three more stories, is a shaping
  problem. Say so and route it to `sync`'s **horizontal slices** finding rather
  than planning around it.
- **Plan it the way a principal architect would.** wayfare-grill-idea's
  *Principal Checklist* is the bar, and *Right fix, honestly sized* is the line
  that decides the approach: the fix goes at the layer the problem lives at, and
  `## Approach` (a goal member's slice) names the quicker version that was not
  taken and what it would have cost. A build subagent executes this plan on a
  cheaper model without re-litigating it (*One turn* step 4), so judgment that
  is not written here is judgment nobody applies.
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
  subtasks, and never test cases: each line must answer "how would you test
  this?", but the answer is the build's to write, per `testing.md`). At least
  one DoD line must assert the **user-visible story working end to end**: a DoD
  whose every line is about one layer describes a layer, not a slice.
  `anchors.target` is refreshed to the head planned against. In self-review mode
  there is no target head to refresh it to, so it stays absent.
- **A member of a goal that carries `## Plan` has no `## Approach`.** Its "how"
  is the goal's `### Task N` slice for its id, and its `## Subtasks` is
  generated from that slice; its `## Definition of Done` stays on the member
  (`docs/PLAN.md`, *Goal-only sections*). The set's cross-cutting decisions go
  in the goal's `### Design`, not in the members' `## Context`. A goal with no
  `## Plan` keeps its members' `## Approach` as above.
- The task is the unit of work, with no separate work-items. Subtasks are
  checklist lines, and wayfare-build-task works through them in order (PR
  granularity is wayfare-build-task's call, per its Step 2).
- The ready-mark is the user's (wayfare-grill-idea's Step 5): a confirmed task
  flips to `ready`, which is what `wayfare-advance-item ID` builds next. A goal
  that carries `## Plan` takes one ready-mark, on its plan, covering the plan
  and every member's DoD; it flips every `planning` member that passes
  `hero_member_planned` to `ready`. One exception, granted by a person at
  `wayfare-start-goal`'s gate and nowhere else: a goal with `absorb: yes` marks
  an **admitted** item ready inside its own run (*Admitting discovered work*).

## A goal's plan: what Roadmap mode writes

When the set Roadmap mode plans is, or becomes, a goal's members, the plan goes
on the goal, in the same pass. A set is a goal's members when its tasks already
share one `parent` goal. It becomes one when the goals stage's grouping rules
(`sync.md`, *Plan the set*, step 4: bottom-up, by outcome, one `parent` per
task) put it in a goal. Roadmap mode proposes that goal before its Step 3 gate:
the members in `rank` order and the one outcome the goal's DoD states. The user
confirms it like any other row. A set that splits into several goals gets one
proposal, one `## Plan` and one ready-mark each.

A confirmed goal is written in the full goal format with the values the goals
stage sets (`status: accepted`, `parent` and `rank` on each member, derived
`depends_on`, `budget`, `budget_max`, the `cut` line, the default
`## Permissions` and `## Stop conditions`, a DoD that spans the group), and its
plan as `## Plan` (`docs/PLAN.md`, *Goal-only sections*):

- **`### Requirements`**: what the merged change must do end to end, including
  that existing services keep working. The goal's DoD is its checkable form.
- **`### Design`**: the cross-cutting decisions the pass settled, with
  `#### Contracts` (each interface one member produces and another consumes:
  name, signature, schema or format, producer id, consumer ids),
  `#### Ordering and compatibility` (why this order, and for a breaking change
  the expand/contract sequence that leaves existing callers working at every
  intermediate commit), and `#### Checkpoints` (the members after which the full
  suite runs: every contract boundary, and at least every 4 members).
- **One `### Task N` slice per member**, the heading exactly `### Task N` keyed
  by its store id, in `rank` order: that member's approach and nothing else.
  Depth scales with the member: a one-file member may be two lines, a multi-file
  member gets a full approach. Slices are written goal-aware, with no "branch
  fresh off main" and no push, PR or merge step, because the goal owns the
  branch and the PR.

The goal and its `## Plan` are written first, then each member with `parent`
set, its `## Subtasks` generated from its slice, its own `## Definition of Done`
and `success:`, and no `## Approach`. Written the other way round, a run that
dies between the two leaves tasks pointing at a goal that does not exist.
Cross-cutting decisions go in `### Design`, never in the members' `## Context`;
an architectural one also goes in `DESIGN.md`. A member that already carries
`## Approach` is lifted into its slice (`sync.md`, *Plan the set*, step 2), its
ticked `## Subtasks` lines kept ticked and verbatim. An `active` goal is frozen,
and Roadmap mode never writes its `## Plan`. A task the pass leaves outside any
goal (the user declined the proposal) gets its own `## Approach`, `## Subtasks`
and `## Definition of Done`, with the shared decisions in its `## Context`.

A task planned alone whose `parent` goal already carries `## Plan` (an admission
under `absorb: yes`, or a task joining an `accepted` goal) is planned onto the
goal the same way: a new `### Task ID` slice placed by its `rank`, and any
contract it introduces under `#### Contracts`. It may add a slice and a
contract, nothing more. A change to an existing contract, to
`#### Ordering and compatibility`, or to another member's DoD, `source` or
`target` is what the goal's ready-mark approved: the run writes none of it and
stops naming the change it needs.
