---
name: wayfare-review-fleet
# prettier-ignore
description: "Compare FLEET.md with sibling checkouts. Report unmapped repos, missing checkouts, and port collisions. Write nothing. Use from the folder containing the repos to check the map before a fleet run."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin and a fleet folder containing sibling checkouts and FLEET.md."
---

# Review the fleet: what the map claims against what is there

`FLEET.md` identifies fleet checkouts and the host port assigned to each dev
stack. Every fleet run reads this map. A stale map can direct work to the wrong
repo or allow a port collision. This skill reports differences and writes
nothing. Use `wayfare-sync-fleet` to update the map. Follow
[docs/FLEET-MD.md](../../docs/FLEET-MD.md).

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

> Each bash block below runs in a fresh shell, so re-source `hero-lib.sh` at the
> top of any block that calls a `hero_*` function.

`NO_FLEET` → STOP. There is no map to review. Report that fact and offer
`wayfare:wayfare-sync-fleet`, which bootstraps one. Do not guess a candidate
folder here: choosing one is a write decision and belongs to `sync`.

### Report the drift

```bash
"$SCAN" "$FLEET_ROOT" --review
```

Print each finding with its meaning from the standard and the repo it names.
Exit 1 means there is something to fix. Say which of
`wayfare:wayfare-sync-fleet` or a repo-side skill fixes it. Write nothing: not
`FLEET.md`, not a repo.

## Anti-patterns

- **Fixing what you found.** A drift report that also edits is a `sync` with no
  confirmation step. Report it and name the skill that fixes it.
- **Reporting "holds" on a missing map.** `NO_FLEET` is a finding, not a healthy
  verdict. An absent file must never produce the healthy verdict.

## Next steps

- Rows to add, remove, or a port to claim → `wayfare:wayfare-sync-fleet`
