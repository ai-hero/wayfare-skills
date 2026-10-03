---
name: wayfare-sync-plan
# prettier-ignore
description: "Refresh .plans against architecture, design, hardening, stale prose, compliance, dependency PRs, unmerged work, and goals. Propose items and goals. Write only what the user confirms. Use to refresh the roadmap."
argument-hint: "[CONTEXT | ideas]"
compatibility: "Requires the complete Wayfare plugin, git, and the optional issue, design, security, and fleet tools configured by HERO.md."
---

# Converge the roadmap with the world

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

### Converge the roadmap with the world

**Read `../../references/sync.md` in full before starting.** Read
`../../references/reconciliation.md` before any lane compares Source and Target.
Follow its authority direction and evidence rules. Resolve each target element
to a *source symbol*. Do not substitute a comparison of file paths or file text.
A path comparison detects file movement, not reconciliation.

**Read `../../references/shaping.md` before proposing any item**, and before
accepting one a person brings. A `shape: story` task is a vertical slice through
the whole system, never a layer of one.

Progress:

- [ ] 1. Step 0 above
- [ ] 2. Inbox: triage `.plans/inbox/`, resume what the replies unblock
- [ ] 3. Reconciliation lanes: design, architecture, design system, hardening,
  comments, compliance, deps, unshipped. The `uncovered` lane lists ground an
  anti-feature declines as `declined, see ID` and proposes nothing for it
- [ ] 4. Visual pass: the shipped screens, per `../../references/shaping.md`
- [ ] 5. Store defects: dangling deps, orphaned members, missing anchors, and
  the blocked lane, which asks per item whether its `blocked_on` has cleared.
  Then the roundup of every `new` item, plus any `accepted` task the person no
  longer wants, where each item is accepted or dropped with a reason
- [ ] 6. Confirm the proposal table with the user, row by row, including each
  task's proposed `priority`
- [ ] 7. Write the accepted items at `status: accepted` (`docs/PLAN.md` format)
- [ ] 8. Propose goals over what was planned. This skill writes goals but never
  authorizes them
- [ ] 9. Planning postflight (`../../references/planning.md`)
- [ ] 10. End with the roadmap view, the parked-idea count, and one `Next step:`
  line

`ideas` walks the parked ideas and promotes, parks or bins each one. Only when
asked: ideas are not re-triaged every round.

**The first task can ship before the whole roadmap is planned.** Plan each slice
so it can stand alone. Do not make full roadmap planning a gate on building.

## Next steps

- Authorize and run the next goal → `wayfare:wayfare-start-goal`
- Advance one item → `wayfare:wayfare-advance-item ID`
