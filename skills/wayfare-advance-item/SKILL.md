---
name: wayfare-advance-item
# prettier-ignore
description: "Advance one item as far as its gates allow: a ready task through the build pipeline, a Dependabot PR to merged, or one turn of a goal. Never plans. Use to move a specific item forward by id."
argument-hint: "ID"
---

# Advance one item

Source is the product as it is; Target is the product as it should be, a
claude.ai/design project configured in HERO.md. With no design project the
route reconciles Source against itself: `DESIGN.md`, its own gaps, its own
hardening. The README's command table says which skill does what;
**`docs/PLAN.md` is the store's specification, and nothing here restates
it.**

## Instructions

### Step 0: load

**Read `../../references/loading.md` and work its checklist**; nothing below
runs until it passes.

The fleet check is first and is a hard stop:

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `../../docs/FLEET-MD.md`, which fans out into the
repos you pick. A run against the folder itself plans nothing.

Progress:

- [ ] 1. Fleet check: the command above
- [ ] 2. Config gate: the `## Connections` blocks and `## Wayfare` (`../../references/configuration.md`)
- [ ] 3. Store read: `hero_ready_items`, the inbox, the plan object
- [ ] 4. Snapshot: pull the design snapshot, resolve both heads
- [ ] 5. Local stages: this repo's own `wayfare: sync` skills, at the trust gate

An unset sentinel (`SOURCE_HEAD`, `UX_FLOW`, `DS_REPO`, `RECON`) **stops the
run**. A store that is not at schema 1 stops it too: `hero_ready_items`
refuses one and names the migrator.

### Advance one item

**Read `../../references/advancing.md`.** It dispatches on the item's type:
a task runs *Advancing one item*; a `shape: dependency` task with `bot:` runs
*Carrying a bot's PR*; a goal id runs one turn.

**This skill never plans.** An item that is not `ready` or further is
refused with `Next step: wayfare:wayfare-sync-plan`; an item with unmet
dependencies is refused naming them.

## Next steps

- Nothing ready → `wayfare:wayfare-sync-plan`
- Abandon the work instead → `wayfare:wayfare-drop-item ID`
