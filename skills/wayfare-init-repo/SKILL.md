---
name: wayfare-init-repo
# prettier-ignore
description: "Investigate a repo, write HERO.md, and create .plans/PLAN.md. Migrate an older store when found. Scaffold first in an empty directory. Use on a repo with no HERO.md or no .plans/PLAN.md."
argument-hint: "[recalibrate]"
compatibility: "Requires the complete Wayfare plugin, git, and optional network access for repository-host configuration."
---

# Configure the repo and create its plan

Source is the current product. Target is the intended product, recorded in a
claude.ai/design project configured in HERO.md. Without a design project,
compare Source with its own `DESIGN.md`, gaps, and hardening needs. The README
command table describes each skill. **Use `docs/PLAN.md` as the specification
for the store and item format.**

## Instructions

### Configure the repo and create its plan

**The fleet check is first and is a hard stop:**

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If the command prints `FLEET_ROOT`, stop this repo procedure. Follow **At the
fleet root** in [docs/FLEET-MD.md](../../docs/FLEET-MD.md) for the repos the
user selects. Start a separate run inside each selected repo. Do not plan
against the fleet folder itself.

**Read `../../references/init.md`.** Run it on a repo with no `HERO.md`, on one
with no `.plans/PLAN.md`, or with `recalibrate` to re-investigate the repo and
rewrite `HERO.md` whole. That is a different job from
`wayfare:wayfare-recalibrate-config`, which reports the field table and asks
about the ones that are unset. Use this one when the repo itself has changed
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
