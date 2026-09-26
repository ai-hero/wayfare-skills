---
name: wayfare-sync-fleet
# prettier-ignore
description: Create and converge FLEET.md, the local unversioned map of sibling checkouts (group, port). Scans the folder, proposes rows, and writes only what the user confirms. Use from the folder that holds the repos, when adding a checkout or claiming a port. To report drift without writing, use wayfare-review-fleet.
argument-hint: ""
---

# Fleet: the map of the checkouts beside you

A fleet folder holds sibling repos. `FLEET.md` at its top says which of them
are family, which are just parked there, and which host port each dev stack
claims, so a skill run from the folder can fan out to the right repos, and
two stacks never fight over one port. The standard is
[docs/FLEET-MD.md](../../docs/FLEET-MD.md); read it once before the first
`sync`.

## Instructions

### Step 0: Load

```bash
# No `git rev-parse` fallback here: this is the one skill built to run outside
# a repo, where that fallback resolves to /scripts/hero-lib.sh and a failed
# source would print a plausible NO_FLEET.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "fleet: cannot load $HERO_LIB — STOP (reinstall the plugin)"; exit 1; }
SCAN="$(dirname "$HERO_LIB")/fleet-scan.sh"

if FLEET_ROOT=$(hero_fleet_root); then
  echo "FLEET_ROOT=$FLEET_ROOT"
  hero_fleet_repos "$FLEET_ROOT"
else
  # No FLEET.md above us. The candidate is this folder when not in git, else
  # the repo's parent — never a repo root: bootstrap would write FLEET.md
  # into the checkout, the standard's first anti-pattern.
  CAND=$(git rev-parse --show-toplevel 2>/dev/null); CAND="${CAND:+$(dirname "$CAND")}"; CAND="${CAND:-$PWD}"
  echo "NO_FLEET candidate=$CAND"
  "$SCAN" "$CAND" --list
fi
```

> Each bash block below runs in a fresh shell, so re-source `hero-lib.sh` at the top of any block that calls a `hero_*` function.

`NO_FLEET` → bootstrap (below), but **confirm the candidate folder first**:
show its path and the checkouts the scan found, and ask. A wrong guess writes
a registry into someone's home directory.

## Converge FLEET.md with the folder

Both modes share one shape: **scan, propose, write only what the user
confirms.** `sync` writes one file, `FLEET.md`, and sends the `## Fleet`
section to each fleet repo as a message (step *Make the repos fleet-aware*, both
modes). Any other repo change, such as a port or a missing `HERO.md`, goes to
the skill that owns it.

**Bootstrap: no FLEET.md yet.**

1. Scan: `"$SCAN" "$CAND" --list`. Every git checkout directly under the
   folder is a candidate row; plain folders are not.
2. Ask, in one pass, for the `## Fleet` block: name (default: the folder
   name), `org` (the GitHub owner: read it off the first checkout's
   `origin` with `git -C PATH remote get-url origin`, offer it), the template
   repo if there is one, and the port range. Skip what does not apply; only
   `name` is required.
3. Ask for the groups. Offer `template` / `apps` / `infra` / `none` with the
   meanings from the standard, and let the user rename or add. `none` stays.
4. Propose the rows as a table of name, group, port, and what, with every group
   defaulted to `none` and the port read from the compose file. Guess nothing
   about membership: a repo is fleet when the user says so. `what` comes from
   the repo's `README.md` first line or `HERO.md`'s framework field; leave it
   blank rather than invent it.
5. Show the whole file, confirm, write `FLEET_ROOT/FLEET.md`. Then run
   `"$SCAN" "$FLEET_ROOT" --review` and show it. A fresh registry that
   already reports collisions is telling the truth on day one.

**Converge: FLEET.md exists.**

1. Run `"$SCAN" "$FLEET_ROOT" --review`. Exit 0 with no output: say so and
   stop. Otherwise, one proposal per finding:

   | Finding | Proposal |
   | --- | --- |
   | `BAD_ROW` | the row could not be trusted (the detail says why: a bad name, a dashed or non-numeric value, a duplicate, a path outside the fleet). Fix or drop it, and never guess a replacement |
   | `MISSING` | drop the row, or fix `path` if the folder moved. Ask first |
   | `NOT_GIT` | same as `MISSING`; a folder that stopped being a checkout is not a repo |
   | `PORT_MISMATCH` | the row is the assignment, the compose default is the implementation. Ask which is right. If the repo must change, hand it to `wayfare:wayfare-build-task` in that repo. The standard's last anti-pattern names every place the port appears. Never edit the repo from here |
   | `PORT_UNIMPLEMENTED` | the claim is made, the repo has no compose file yet. Nothing to fix here; it clears when the dev stack lands |
   | `PORT_UNPARSED` | a compose file the scanner cannot read a host port from. Look at it: either it publishes no port (drop the row's port) or it uses a syntax worth adding to `hero_compose_port` |
   | `PORT_COLLISION` | pick the next free port in `port-range` for the newer row, propose it; same routing as a mismatch for the repo side |
   | `NO_HERO` | offer `wayfare:wayfare-init-repo` in that repo (a subagent, per the standard's fan-out) |
   | `NO_AGENTS` | same, via `wayfare-init-repo`'s Step 1 |
   | `NOT_FLEET_AWARE` | *Make the repos fleet-aware*, below |

2. Checkouts with no row: `"$SCAN" "$FLEET_ROOT" --list`, minus the paths
   FLEET.md names. `--review` does not report these, deliberately: **FLEET.md
   defines the fleet, and a folder does not join it by being cloned there.**
   Print them as *on disk, not listed* and add no rows unless the user asks
   for one by name. Offering a row per parked clone is how a repo nobody
   claimed acquires one and starts reading as a member.
3. If `org` is set, list what exists there and is not on disk.
   `gh repo list ORG --limit 200 --json name,isArchived --jq '.[] | select(.isArchived|not) | .name'`
   minus the folder's checkouts. Print it as *not cloned*; add no rows.
4. Show the proposed rows, confirm, write. Re-run `--review` and show the
   remainder. The repo-side findings that were routed elsewhere stay until
   those PRs merge, and that is the correct state.

**Make the repos fleet-aware, after the rows are written, in both modes.**

A clone knows nothing about the folder it sits in, so every fleet repo's own
instructions carry the pointer. For each row whose group is not `none` and
whose `AGENTS.md` (or `CLAUDE.md`) has no `## Fleet` heading (the
`NOT_FLEET_AWARE` rows from `--review`), propose adding the section:

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
SECTION="$WAYFARE_ROOT/assets/fleet/agents-md-fleet-section.md"
cat "$SECTION"
```

**This is a message, not an edit.** `sync` does not write the section into
those repos: appending to a dozen siblings' `AGENTS.md` leaves a dozen dirty
working trees nobody reviewed, in repos whose own agents did not make the
change. Each repo lands its own section, in its own PR, under its own gates.

So for each repo in the list, deposit a `type: ask` into its `.plans/inbox/`
per the *Sending* procedure in `docs/MESSAGES.md`, with:

- `from: fleet`, the reserved sender for a fleet-root run, which has no repo
  of its own. Not the recipient's own row: `from == to` is how a repo marks a
  note from its own previous session, and borrowing it throws away the one
  provenance signal the recipient has.
- `to:` that repo's row name.
- `about: fleet-section`, a subject token, because a fleet-root run has no
  local item id. The dedupe probe keys on `(from, about)` and an empty
  `about` matches every about-less message from the same sender, so two
  unrelated fleet asks would collapse into one and the second would never be
  sent.
- an `## Ask` naming the section and where the asset lives, the section's
  full text in the body so the recipient never reaches back into this folder
  to read it, and the instruction that it appends to `AGENTS.md`, or to
  `CLAUDE.md` when that is the regular file and `AGENTS.md` is absent.

Show the drafts and the list once, confirm once, then deposit with
`hero_msg_deposit`. Report the repos that now have mail and the one line each
runs to act on it (`wayfare:wayfare-sync-plan`, whose `inbox` stage promotes
the ask).

A row whose `.plans/` does not exist cannot receive one: no mailbox, and no
agent workflow to read it. Name those separately and offer to `cd` in. Never
create a store inside someone else's checkout to make the deposit work. That
is the second kind of write, and it is the one that does not exist.

A repo whose section is present but differs from the asset gets the same
message, saying so; the asset is authored here, and a per-repo edit to it is
output to be overwritten.

## Anti-patterns

- **Guessing membership.** A checkout with a `HERO.md` is a repo the hero
  skills run in, not proof it shares the fleet's stack. Default `none`, ask.
- **Editing a repo to satisfy the registry.** `sync` touches no repo at all.
  The `## Fleet` section goes as a message, like everything else
  (`docs/MESSAGES.md`). Port changes and missing configs go through the skill
  that owns them, in that repo, on a PR.
- **Adding rows for repos that are not on disk.** The org listing is
  informational. See the standard.

## Next steps

- Findings routed to repos → run the named skill from the fleet root and pick
  those repos (the standard's fan-out), or `cd` in.
- Clean → nothing. Re-run `review` after cloning or moving a checkout.
