---
name: wayfare-init-repo
# prettier-ignore
description: "Configure a repo for wayfare: investigate it, write HERO.md, and create the plan object .plans/PLAN.md, migrating an older store on sight. Scaffolds first in an empty directory. Use on a repo that has no HERO.md or no .plans/PLAN.md."
argument-hint: "[recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, and optional network access for repository-host configuration."
---

# Configure the repo and create its plan

Source is the product as it is; Target is the product as it should be, a
claude.ai/design project configured in HERO.md. With no design project the route
reconciles Source against itself: `DESIGN.md`, its own gaps, its own hardening.
The README's command table says which skill does what; **`docs/PLAN.md` is the
store's specification, and nothing here restates it.**

## Instructions

### Configure the repo and create its plan

**The fleet check is first and is a hard stop:**

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo. Stop and follow
**At the fleet root** in [docs/FLEET-MD.md](../../docs/FLEET-MD.md), which fans
out into the repos you pick, starting a run inside each. A run against the
folder itself plans nothing.

**Read `../../references/init.md`.** Run it on a repo with no `HERO.md`, on one
with no `.plans/PLAN.md`, or with `recalibrate` to re-investigate the repo and
rewrite `HERO.md` whole. That is a different job from
`wayfare:wayfare-recalibrate-config`, which reports the field table and asks
about the ones that are unset; use this one when the repo itself has changed
shape and the config has gone stale. In an empty directory,
`../../references/scaffold.md` runs first and falls through into it.

Progress:

- [ ] 1. Fleet check: at a fleet root this is `wayfare:wayfare-sync-fleet`, not
  init
- [ ] 2. Scaffold, only when there is no repo yet
  (`../../references/scaffold.md`)
- [ ] 3. Investigate, then confirm the findings with evidence-based questions
- [ ] 4. Write `HERO.md` and refresh `AGENTS.md`'s managed sections
- [ ] 5. Write `.plans/PLAN.md`, or migrate an unmigrated store and say so
- [ ] 6. Fill `## Scope`: a round that plans against "TODO" plans against
  nothing

This is the only skill that creates the plan object. Every other one reads it,
and `hero_ready_items` refuses a store without one rather than printing an empty
roadmap that reads as "nothing to do".

## Next steps

- Converge the roadmap → `wayfare:wayfare-sync-plan`
