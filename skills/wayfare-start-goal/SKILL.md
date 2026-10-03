---
name: wayfare-start-goal
# prettier-ignore
description: "Ask the user to authorize the next goal, then run its first turn. Keep the grant in the session. Never store it. Use when the roadmap is planned and the user is ready to build the next goal."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin, git, an interactive authorization gate, and a planned .plans store."
---

# Authorize the next goal and run it

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

### Authorize the next goal and run it

**Read `../../references/goals.md`.** Only this gate accepts a person's grant of
a goal's `## Permissions`. Keep the grant **in the session, never in storage**.
Do not write `authorized by NAME` in the item's log. A later turn could
incorrectly treat that stored line as permission.

Progress:

- [ ] 1. Step 0 above
- [ ] 2. Select the goal: dependencies met, members planned
- [ ] 3. Adopt ungrouped work that fits: `hero_goal_candidates`, judged against
  the DoD
- [ ] 4. Read the goal aloud: its DoD, its members, the adoptions, its `source`
  paths
- [ ] 5. Read `## Permissions` aloud and take the grant, in-session. The typed
  id writes the adoptions
- [ ] 6. Cut the branch, run turn 1 (`../../references/goals.md`, *One turn*)
- [ ] 7. Append the turn to `## Log`. Stop on any stop condition

## Next steps

- Run another turn of the same goal → `wayfare:wayfare-advance-item GOAL_ID`
- Abandon it → `wayfare:wayfare-drop-item ID`
