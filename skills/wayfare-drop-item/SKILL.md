---
name: wayfare-drop-item
# prettier-ignore
description: "Drop an open item with a recorded reason. For an unmerged branch, stash and switch only with a named, confirmed stash. Change no git state for an item without a branch. Use when abandoning work."
argument-hint: "ID [REASON]"
compatibility: "Requires the complete Wayfare plugin, git, and the repository's .plans store."
---

# Abandon work, and say so on the roadmap

Source is the current product. Target is the intended product, recorded in a
claude.ai/design project configured in HERO.md. Without a design project, the
route compares Source with its own `DESIGN.md`, gaps, and hardening needs. The
README command table describes each skill. **Use `docs/PLAN.md` as the
specification for the store and item format.**

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

### Abandon work, and say so on the roadmap

**Read `../../references/drop.md`.** Resolve the id before selecting the
procedure. For a task with a branch, create a named stash only after
confirmation. Then switch away from the branch. For an item without a branch,
change no git state. In both cases, write `status: dropped` and a dated reason.

Record the dropped status so an abandoned item does not remain `active`.
`dropped` does not satisfy a dependency. The listing must continue to report
dependent items as blocked.

## Next steps

- Pick up something else → `wayfare:wayfare-advance-item ID`
- Re-plan the ground it covered → `wayfare:wayfare-sync-plan`
