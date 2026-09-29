---
name: wayfare-sync-plan
# prettier-ignore
description: "Converge the roadmap with the world: the architecture record, the design snapshot, the hardening audit, prose gone false about the code, the compliance register, the dependency bots' PRs, branches built and never merged, and goals, into .plans. Proposes items and goals; writes only what the user confirms. Use to refresh what is worth doing."
argument-hint: "[CONTEXT | ideas]"
---

# Converge the roadmap with the world

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

### Converge the roadmap with the world

The longest procedure in wayfare and the one with the most ways to be quietly
wrong. **Read `../../references/sync.md` in full before starting**, and
`../../references/reconciliation.md` before any lane that compares the two ends:
it carries the direction of authority, the evidence rules, and the rule that a
target element resolves to a *source symbol*, never to a path whose text can be
diffed. A round that compares paths answers "did these files move".

**Read `../../references/shaping.md` before proposing any item**, and before
accepting one a person brings. A `shape: story` task is a vertical slice through
the whole system, never a layer of one.

Progress:

- [ ] 1. Step 0 above
- [ ] 2. Inbox: triage `.plans/inbox/`, resume what the replies unblock
- [ ] 3. Reconciliation lanes: design, architecture, design system, hardening,
  comments, compliance, deps, unshipped
- [ ] 4. Visual pass: the shipped screens, per `../../references/shaping.md`
- [ ] 5. Store defects: dangling deps, orphaned members, missing anchors, and
  the blocked lane, which asks per item whether its `blocked_on` has cleared
- [ ] 6. Confirm the proposal table with the user, row by row, including each
  task's proposed `priority`
- [ ] 7. Write the accepted items at `status: accepted` (`docs/PLAN.md` format)
- [ ] 8. Propose goals over what was planned; this skill writes them, never
  authorizes
- [ ] 9. Planning postflight (`../../references/planning.md`)
- [ ] 10. End with the roadmap view, the parked-idea count, and one `Next step:`
  line

`ideas` walks the parked ideas and promotes, parks or bins each one. Only when
asked: ideas are not re-triaged every round.

**This is not a gate on building.** The roadmap does not have to be fully
planned before the first task ships; that would be waterfall, and it contradicts
slicing the work so each piece stands alone.

## Next steps

- Authorize and run the next goal → `wayfare:wayfare-start-goal`
- Advance one item → `wayfare:wayfare-advance-item ID`
