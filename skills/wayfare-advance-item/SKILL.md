---
name: wayfare-advance-item
# prettier-ignore
description: "Advance one item through its permitted gates. Handle a ready task, a Dependabot PR, or one goal turn. Do not plan. Use to advance a specific item by id."
argument-hint: "ID"
compatibility: "Requires the complete Wayfare plugin, git, and the repository configuration described by HERO.md."
---

# Advance one item

Source is the current product. Target is the intended product, recorded in a
claude.ai/design project configured in HERO.md. Without a design project,
compare Source with its own `DESIGN.md`, gaps, and hardening needs. The README
command table describes each skill. **Use `docs/PLAN.md` as the specification
for the store and item format.**

## Instructions

### Step 0: load

**Read `../../references/loading.md`.** Complete its checklist. Run the steps
below only after the checklist passes.

The fleet check is first and is a hard stop:

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If the command prints `FLEET_ROOT`, stop this repo procedure. Follow **At the
fleet root** in `../../docs/FLEET-MD.md` for the repos the user selects. Do not
plan against the fleet folder itself.

Progress:

- [ ] 1. Fleet check: the command above
- [ ] 2. Config gate: the `## Connections` blocks and `## Wayfare`
  (`../../references/configuration.md`)
- [ ] 3. Store read: `hero_ready_items`, the inbox, the plan object
- [ ] 4. Snapshot: pull the design snapshot, resolve both heads
- [ ] 5. Local stages: this repo's own `wayfare: sync` skills, at the trust gate

**Stop if any sentinel is unset:** `SOURCE_HEAD`, `UX_FLOW`, `DS_REPO`, or
`RECON`. Stop if the store does not use schema 1. `hero_ready_items` rejects
that store and names the migrator.

### Advance one item

**Read `../../references/advancing.md`.** Select the procedure by item type. For
a task, run *Advancing one item*. For a `shape: dependency` task with `bot:`,
run *Carrying a bot's PR*. For a goal id, run one turn.

**This skill never plans.** Reject an item whose status precedes `ready`. Print
`Next step: wayfare:wayfare-sync-plan` for that item. Reject an item with unmet
dependencies and name those dependencies.

## Next steps

- Nothing ready → `wayfare:wayfare-sync-plan`
- Abandon the work instead → `wayfare:wayfare-drop-item ID`
