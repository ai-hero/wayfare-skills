---
name: wayfare-start-goal
# prettier-ignore
description: Authorize the next goal at a gate the person types, then run its first turn. The grant is in-session and never stored. Use when the roadmap is planned and you are ready to start building the next goal.
argument-hint: ""
---

# Authorize the next goal and run it

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

### Authorize the next goal and run it

**Read `../../references/goals.md`.** The gate here is the only place a person
grants a goal's `## Permissions`, and the grant is **in-session, never stored**.
A line in the item's log reading `authorized by NAME` is a stored authorization
by another name, and a later turn reading it as one is exactly the failure the
in-session rule exists to prevent.

Progress:

- [ ] 1. Step 0 above
- [ ] 2. Select the goal: dependencies met, members planned
- [ ] 3. Adopt ungrouped work that fits: `hero_goal_candidates`, judged against
  the DoD
- [ ] 4. Read the goal aloud: its DoD, its members, the adoptions, its `source`
  paths
- [ ] 5. Read `## Permissions` aloud and take the grant, in-session; the typed
  id writes the adoptions
- [ ] 6. Cut the branch, run turn 1 (`../../references/goals.md`, *One turn*)
- [ ] 7. Append the turn to `## Log`; stop on any stop condition

## Next steps

- Run another turn of the same goal → `wayfare:wayfare-advance-item GOAL_ID`
- Abandon it → `wayfare:wayfare-drop-item ID`
