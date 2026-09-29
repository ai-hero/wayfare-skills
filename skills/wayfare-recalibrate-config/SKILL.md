---
name: wayfare-recalibrate-config
# prettier-ignore
description: "Report and tune the config every wayfare skill reads: the `## Connections` blocks and `## Wayfare` in HERO.md plus the fields the architecture and security stages read. Asks only about fields that are unset or wrong, then writes. Use when a run complained about config, or after the repo changed shape."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin, git, and an existing HERO.md."
---

# Tune the config the route reads

This skill tunes the config and **stops**. It does not go on to run anything
else: you want to see which field was wrong, not spend a whole run finding out.

Follow the four phases in [docs/RECALIBRATE.md](../../docs/RECALIBRATE.md)
(report, ask, write, commit) using the table below as the report.

## Instructions

### Step 0: fleet check

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo. Stop and follow
**At the fleet root** in [docs/FLEET-MD.md](../../docs/FLEET-MD.md), which fans
out into the repos you pick, starting a run inside each. A run against the
folder itself plans nothing.

### Report

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" --all
```

### Ask

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. **A row that already holds the right value is not a question.**

`Connections::KIND` rows carry two sentinels of their own. `(no-section)` is the
whole block missing, which IS a question. `(n/a: type=...)` is the block having
answered (`none`, `self`) or being blocked on a refused `type`, and it is the
one parenthesised value that is **not** a question. See
`references/configuration.md`.

The table covers more than wayfare's own connections: because
`wayfare:wayfare-sync-plan` runs `wayfare:wayfare-review-architecture`,
`wayfare:wayfare-sync-architecture` and `wayfare:wayfare-audit-security`, the
fields those read are in scope here too. A person who never calls those skills
directly still has one place to fix their config.

### Write, then commit

`../../references/configuration.md` has every field and what a bad value does.
Read it before writing any value you are unsure of; several fields fail open
rather than loudly, and the reference is where that is recorded.

## Next steps

- Config is right, converge the roadmap → `wayfare:wayfare-sync-plan`
- No `HERO.md` at all → `wayfare:wayfare-init-repo`
