---
name: wayfare-one-shot
# prettier-ignore
description: "Take one small, clear change from a one-line description to a merged PR: draft one task, show it, and on the person's yes mark it ready and build it. Routes to wayfare-grill-idea when the description is several items, an anti-feature, or a one-way door. Use for a fix you already understand."
argument-hint: "DESCRIPTION"
compatibility: "Requires the complete Wayfare plugin, git, GitHub CLI, network access, and an interactive readiness gate."
---

# One thing, described once, shipped

A feature needs a grill; "rename this flag and update the docs" does not.
`wayfare-grill-idea` asks one question at a time and stops for the ready-mark,
which is right for the first and slow for the second. This skill is the front
door for the second: it drafts the one task itself, asks one question, and hands
the item to `wayfare:wayfare-build-task`. **`docs/PLAN.md` is the store's
specification; nothing here restates the item format.**

## Arguments

- `$ARGUMENTS`: the description of the change, in the person's words. Empty
  means there is nothing to draft: say so and stop, and never guess from the
  branch.

## Instructions

### Step 0: load

**Read `../../references/loading.md` and work its checklist**; nothing below
runs until it passes.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT, export WAYFARE_ROOT as the plugin root"; exit 1; }
hero_at_fleet_root && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `../../docs/FLEET-MD.md`. A description run against the
folder itself drafts nothing.

### Step 1: read what the description names

Read every file, path and symbol the description names, and search for the ones
it implies. The draft is written from the code as it is, never from the
description alone: a rename that misses three call sites is a red build in the
next step.

Before drafting, read `hero_ready_items`. A description that names an existing
item (id, slug or title) is not a new task: stop and suggest
`wayfare:wayfare-build-task ID`, which resolves it. A `hero_ready_items` failure
stops the run here, since the guard below reads the same listing.

### Step 2: the guard

Three stops. Each names its reason, writes nothing, and routes to
`wayfare:wayfare-grill-idea` with the description, because the work needs shared
understanding before it is an item.

- **More than one item.** The description drafts into two or more tasks, or one
  task whose Subtasks are separate stories a person could ship on their own.
  Name the split you found. `wayfare-build-task` drives one item to one PR, and
  a stack is exactly what its scope check refuses.
- **An anti-feature.** Match the description against every item whose file
  carries `type: anti-feature`, whatever row word it lists under, by title and
  by the paths in the file's `source` (the row does not carry them). Any
  `hero_ready_items` stderr line naming an anti-feature is a hit too. A hit is a
  decision not to build this: print the anti-feature's id, title and
  `## Context` as the citation and stop. Reversing it is a person's, through
  `wayfare-grill-idea`, and `wayfare-build-task` refuses the same row when
  handed its id. Never draft past it.
- **A one-way door.** The change is expensive to reverse: schema, public API,
  data model, money. Say which, and stop. `one_way_door: true` items do not
  belong in a run that asks one question.

The drafts that pass are small, single-approach and single-area: the same size
test the standard uses for its no-planning-run path.

### Step 3: draft the one task

Write `.plans/items/NNN-slug.md` at `status: planning`. The id is the highest
existing `id` in `.plans/` plus one, **re-checked immediately before writing**,
because a collision surfaces only as a `duplicate id` line on stderr.

- `type: task`, and a `shape` inferred from the standard's table in
  `../../docs/PLAN.md`: a rename with docs is `structural` or `docs`, a
  reproduced bug is `defect`. A shape that reads as a user story with no surface
  behind it means the description was a feature: back to the guard.
- `origin: wayfare-one-shot`, `source` the paths you read, `anchors.source` the
  full source head, `one_way_door: false`, and a `success` sentence that states
  an observable behavior.
- `## Context` quotes the description and says what the reading found.
  `## Approach` is three lines at most. `## Subtasks` is the ordered checklist.
  `## Definition of Done` has one line per observable outcome, asserting what
  the shape requires.
- A `## Log` line:
  `note: drafted by wayfare-one-shot from a one-line description`.

Print the item whole, then ask the one question:

```
Build this? [y/N]
```

### Step 4: the ready-mark, then the build

The standard reserves `ready` for the person, explicitly. The yes to Step 3's
question is that act. Nothing else counts: not the description, not a
permissions line, not a file.

- **Yes:** set `status: ready` and `ready_marked:` to today, append a `## Log`
  line saying the person confirmed it, then run `hero_ready_items` and confirm
  the item is listed READY. Not listed means the write is wrong: fix it and say
  so, rather than building around it.
- **No, or anything else:** leave the item at `planning`, print its path, and
  stop. Never flip it on a maybe.

Invoke `wayfare:wayfare-build-task ID` through the active client's skill
mechanism. Its Step 1b resolves the READY item, and everything from Step 2 to
the merge and reset runs as it always does, with its own gates: mark-ready for
the PR and the merge are still the person's. This skill adds no schema and
waives no gate.

Print what came back: the merged SHA, or the step it stopped at and why. A
stopped run leaves the item where `wayfare-build-task` left it.

## Gotchas

- The guard runs before anything is written. A No at Step 4 leaves the drafted
  `planning` item on purpose, for the person to edit, mark ready or drop. A run
  that ends any other way between Step 3's write and Step 4's answer leaves an
  item nobody chose to keep: print its path and offer `wayfare-drop-item` on it.
- `origin: wayfare-one-shot` is the only marker. There is no new type or shape,
  so an item this skill wrote is an ordinary task to everything downstream.

## Next steps

- Too big for one line → `wayfare:wayfare-grill-idea DESCRIPTION`
- Pick up an existing item → `wayfare:wayfare-build-task ID`
