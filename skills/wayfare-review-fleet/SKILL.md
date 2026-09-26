---
name: wayfare-review-fleet
# prettier-ignore
description: Report drift between FLEET.md and the checkouts beside it, read-only. Names repos missing from the map, rows with no checkout, and port collisions between dev stacks. Writes nothing. Use from the folder that holds the repos, to check the map before trusting a fan-out.
argument-hint: ""
---

# Review the fleet: what the map claims against what is there

`FLEET.md` at the top of a fleet folder says which sibling checkouts are
family and which host port each dev stack claims. Every fan-out reads it, so
a stale map sends work to the wrong repos or lets two stacks fight over one
port. This skill reports the difference and changes nothing; `wayfare-sync-fleet`
is what writes. The standard is [docs/FLEET-MD.md](../../docs/FLEET-MD.md).

## Instructions

### Step 0: Load

```bash
# No `git rev-parse` fallback here: this is one of two skills built to run
# outside a repo, where that fallback resolves to /scripts/hero-lib.sh and a
# failed source would print a plausible NO_FLEET.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "wayfare-review-fleet: cannot load $HERO_LIB — STOP (reinstall the plugin)"; exit 1; }
SCAN="$(dirname "$HERO_LIB")/fleet-scan.sh"

if FLEET_ROOT=$(hero_fleet_root); then
  echo "FLEET_ROOT=$FLEET_ROOT"
  hero_fleet_repos "$FLEET_ROOT"
else
  echo "NO_FLEET"
fi
```

> Each bash block below runs in a fresh shell, so re-source `hero-lib.sh` at the top of any block that calls a `hero_*` function.

`NO_FLEET` → STOP. There is no map to review; say so and offer
`wayfare:wayfare-sync-fleet`, which bootstraps one. Do not guess a candidate
folder here: choosing one is a write decision and belongs to `sync`.

### Report the drift

```bash
"$SCAN" "$FLEET_ROOT" --review
```

Print each finding with its meaning from the standard and the repo it names.
Exit 1 means there is something to fix; say which of `wayfare:wayfare-sync-fleet`
or a repo-side skill fixes it. Write nothing: not `FLEET.md`, not a repo.

## Anti-patterns

- **Fixing what you found.** A drift report that also edits is a `sync` with
  no confirmation step. Report it and name the skill that fixes it.
- **Reporting "holds" on a missing map.** `NO_FLEET` is a finding, not a
  clean bill; an absent file must never produce the healthy verdict.

## Next steps

- Rows to add, remove, or a port to claim → `wayfare:wayfare-sync-fleet`
