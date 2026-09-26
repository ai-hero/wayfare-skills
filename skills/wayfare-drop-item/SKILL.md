---
name: wayfare-drop-item
# prettier-ignore
description: Abandon work on an unmerged branch and write status dropped on the item, so the roadmap stops claiming it. Stashes only with a named, confirmed stash. Use when work on a branch is being given up rather than finished.
argument-hint: "ID"
---

# Abandon work, and say so on the roadmap

Source is the product as it is; Target is the product as it should be, a
claude.ai/design project configured in HERO.md. With no design project the route
reconciles Source against itself: `DESIGN.md`, its own gaps, its own hardening.
The README's command table says which skill does what; **`docs/PLAN.md` is the
store's specification, and nothing here restates it.**

## Instructions

### Step 0: load

**Read `../../references/loading.md` and work its checklist**; nothing below
runs until it passes.

The fleet check is first and is a hard stop:

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `../../docs/FLEET-MD.md`, which fans out into the repos
you pick. A run against the folder itself plans nothing.

Progress:

- [ ] 1. Fleet check: the command above
- [ ] 2. Config gate: the `## Connections` blocks and `## Wayfare`
  (`../../references/configuration.md`)
- [ ] 3. Store read: `hero_ready_items`, the inbox, the plan object
- [ ] 4. Snapshot: pull the design snapshot, resolve both heads
- [ ] 5. Local stages: this repo's own `wayfare: sync` skills, at the trust gate

An unset sentinel (`SOURCE_HEAD`, `UX_FLOW`, `DS_REPO`, `RECON`) **stops the
run**. A store that is not at schema 1 stops it too: `hero_ready_items` refuses
one and names the migrator.

### Abandon work, and say so on the roadmap

**Read `../../references/drop.md`.** It stashes (never silently, always named,
always confirmed), switches away, and writes `status: dropped`.

The item write is the part that did not exist before: an abandoned branch used
to leave its item at `active` forever, claiming work that had stopped. `dropped`
does not satisfy a dependency, so the listing reports the dependents as blocked
instead of quietly unblocking them.

## Next steps

- Pick up something else → `wayfare:wayfare-advance-item ID`
- Re-plan the ground it covered → `wayfare:wayfare-sync-plan`
