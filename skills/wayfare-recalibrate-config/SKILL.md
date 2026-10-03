---
name: wayfare-recalibrate-config
# prettier-ignore
description: "Report and tune HERO.md config for wayfare, including Connections, Wayfare, and the architecture and security stages. Ask only about unset or incorrect fields. Use after a config failure or a change to the repo's structure."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin, git, and an existing HERO.md."
---

# Tune the config the route reads

Tune the config and **stop**. Do not run another skill after tuning.

Follow the four phases in [docs/RECALIBRATE.md](../../docs/RECALIBRATE.md)
(report, ask, write, commit) using the table below as the report.

## Instructions

### Step 0: fleet check

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If the command prints `FLEET_ROOT`, stop this repo procedure. Follow **At the
fleet root** in [docs/FLEET-MD.md](../../docs/FLEET-MD.md) for the repos the
user selects. Start a separate run inside each selected repo. Do not plan
against the fleet folder itself.

### Report

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" --all
```

### Ask

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. **A row that already holds the right value is not a question.**

`Connections::KIND` rows have two additional sentinel meanings. `(no-section)`
means the whole block is missing. Ask about it. `(n/a: type=...)` means the
block answered `none` or `self`, or its `type` was refused. **Do not ask about
that value.** See `references/configuration.md`.

The table covers more than wayfare's own connections: because
`wayfare:wayfare-sync-plan` runs `wayfare:wayfare-review-architecture`,
`wayfare:wayfare-sync-architecture` and `wayfare:wayfare-audit-security`, the
fields those read are in scope here too. A person who never calls those skills
directly still has one place to fix their config.

### Write, then commit

`../../references/configuration.md` has every field and what a bad value does.
Read it before writing a value you are unsure of. The reference identifies
fields that can fail open without reporting an error.

## Next steps

- Config is right, converge the roadmap → `wayfare:wayfare-sync-plan`
- No `HERO.md` at all → `wayfare:wayfare-init-repo`
