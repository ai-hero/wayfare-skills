---
name: wayfare-sync-fleet
# prettier-ignore
description: "Create or update FLEET.md, the fleet map of sibling checkouts, groups, and ports, kept in the register checkout at .fleet/. Propose rows and write only what the user confirms. Use from the folder containing the repos when adding a checkout or claiming a port. Use wayfare-review-fleet to report drift without writing."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin and a writable fleet folder containing sibling checkouts."
---

# Fleet: the map of the checkouts beside you

A fleet folder holds sibling repos. `FLEET.md` records fleet membership and the
host port assigned to each dev stack. The map lets a fleet run select the
correct repos and avoid port collisions. It lives in the register repo, cloned
at `.fleet/`, so the file this skill writes is `.fleet/FLEET.md`. Read
[docs/FLEET-MD.md](../../docs/FLEET-MD.md) before the first `sync`.

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

FLEET_ROOT=$(hero_fleet_root); rc=$?
if [ "$rc" = 2 ]; then
  echo "MAP_UNREADABLE"
elif [ "$rc" = 0 ]; then
  echo "FLEET_ROOT=$FLEET_ROOT"
  echo "MAP=$(hero_fleet_map "$FLEET_ROOT")"
  PIN=$(hero_register_pin "$FLEET_ROOT") && echo "PIN=$PIN" || echo "UNPINNED"
  hero_fleet_repos "$FLEET_ROOT"
else
  # No map above us. The candidate is this folder when not in git, else the
  # repo's parent (from inside .fleet/, the fleet folder) — never a repo root:
  # bootstrap would write a map into a product checkout, the standard's first
  # anti-pattern.
  CAND=$(git rev-parse --show-toplevel 2>/dev/null); CAND="${CAND:+$(dirname "$CAND")}"; CAND="${CAND:-$PWD}"
  echo "NO_FLEET candidate=$CAND"
  if [ -e "$CAND/.fleet/.git" ]; then echo "REGISTER=$CAND/.fleet"; else echo "NO_REGISTER"; fi
  "$SCAN" "$CAND" --list
fi
```

> Each bash block below runs in a fresh shell, so re-source `hero-lib.sh` at the
> top of any block that calls a `hero_*` function.

`MAP_UNREADABLE` → **stop.** `.fleet/FLEET.md` exists but is not a readable file
(the error above names it). Report it and stop: never fall back to a top-level
copy or bootstrap a new map over a broken register.

`NO_FLEET` with `NO_REGISTER` → **stop.** The map lives in the register repo, so
there is nowhere to write it yet. Tell the person to clone the fleet's register
into the candidate folder as `.fleet/` (`git clone <register> .fleet`), or, for
a new fleet, to create the private register repo and clone that, then run this
skill again. Never create `.fleet/` as a plain folder: a map outside a git
checkout has no history and no review, which is the state the register exists to
end.

`NO_FLEET` with `REGISTER=` → bootstrap (below), but **confirm the candidate
folder first**: show its path and the checkouts the scan found, and ask. A wrong
guess writes a registry into someone's home directory.

`UNPINNED` → offer to pin the register on this machine, after reading its
`origin` and confirming it is the fleet's register
(`git -C "$FLEET_ROOT/.fleet" remote get-url origin`). The pin lives outside the
register, so a fork carrying its own map cannot vouch for itself; the audit
warns while it is missing and will read the register UNREVIEWED once the legacy
top-level fallback is removed. On confirmation, run, with `OWNER/NAME` from that
`origin`:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/wayfare"
printf '%s %s\n' "$FLEET_ROOT" OWNER/NAME >> "${XDG_CONFIG_HOME:-$HOME/.config}/wayfare/registers"
```

`PIN=` that differs from the map's `register-repo` or from the register's
`origin` is a finding: report all three and stop. Never rewrite a pin to match
the map; the pin is what the map is checked against.

`MAP=` ending in a top-level `FLEET.md` (not `.fleet/FLEET.md`) is the legacy
layout. Offer the move from the standard's *Moving from a top-level FLEET.md*
before converging, and write the result to `.fleet/FLEET.md`.

## Converge FLEET.md with the folder

Both modes use this sequence: **scan, propose, write only what the user
confirms.** `sync` writes only `.fleet/FLEET.md` (and, when asked, this
machine's register pin), and **never commits the map**: the edit lands as an
uncommitted change in the register checkout, for the person to commit and open a
PR there. Say so when you write it. Fan-out and `review` read the map from the
working tree, so a row is usable on this machine at once; the compliance audit
reads the register UNREVIEWED until the change is merged and pulled, and
everyone else sees it only then. Send the `## Fleet` section as a message to
each fleet repo after confirmation, as specified below. Route other repo
changes, including ports and missing `HERO.md`, to the skill that owns them.

**Bootstrap: no FLEET.md yet.**

1. Scan: `"$SCAN" "$CAND" --list`. Each git checkout directly under the folder
   is a candidate row. Exclude plain folders.
2. Ask, in one pass, for the `## Fleet` block: name (default: the folder name),
   `org` (the GitHub owner: read it off the first checkout's `origin` with
   `git -C PATH remote get-url origin`, offer it), the template repo if there is
   one, and the port range. Skip fields that do not apply. Only `name` is
   required.
3. Ask for the groups. Offer `template` / `apps` / `infra` / `none` with the
   meanings from the standard, and let the user rename or add. `none` stays.
4. Propose the rows as a table of name, group, port, and what, with every group
   defaulted to `none` and the port read from the compose file. Guess nothing
   about membership: a repo is fleet when the user says so. `what` comes from
   the repo's `README.md` first line or `HERO.md`'s framework field. Leave it
   blank rather than invent it.
5. Show the whole file, confirm, write `CAND/.fleet/FLEET.md`. Then offer the
   register pin (the `UNPINNED` step above, with `CAND` as the root), run
   `"$SCAN" "$CAND" --review` and show it. A fresh registry that already reports
   collisions is telling the truth on day one.

**Converge: FLEET.md exists.**

1. Run `"$SCAN" "$FLEET_ROOT" --review`. Exit 0 with no output: say so and stop.
   Otherwise, one proposal per finding:

   | Finding | Proposal |
   | -- | -- |
   | `BAD_ROW` | the row could not be trusted (the detail says why: a bad name, a dashed or non-numeric value, a duplicate, a relative path outside the fleet). Fix or drop it, and never guess a replacement |
   | `NOT_CLONED` | normal for a shared map: this machine has no checkout. Offer to clone it **only to `FLEET_ROOT/NAME`** (`git clone git@github.com:ORG/NAME.git "$FLEET_ROOT/NAME"`), and only when the row's path resolves there. A row with any other `path:` is reported, never offered: fix the row first. **Never propose dropping the row** on this finding alone: drop it only when the person says the repo is retired |
   | `ABSENT_OUTSIDE` | an absolute or `~/` row whose folder does not exist. Report it and **never offer a clone or any write there**: the map is shared content, and an absolute path is a place someone else named, such as a skills or shell-config folder. The person installs it themselves, or fixes the row |
   | `MOVED` | the repo is checked out under another folder name. Propose fixing the row's `path` to where it is (or renaming the folder), never a second clone |
   | `DANGLING_LINK` | the row's path is a symlink to nothing. Ask where the checkout went; fix the link or the row. Never clone through the link |
   | `NO_PARENT` | a relative `path:` whose parent folder is missing, usually a typo. Propose the corrected path; never create the parent folders |
   | `NOT_GIT` | the folder exists but is not a checkout. Ask whether it moved (fix `path`), whether to re-clone it, or whether the repo is retired (drop the row) |
   | `PORT_MISMATCH` | the row is the assignment, the compose default is the implementation. Ask which is right. If the repo must change, hand it to `wayfare:wayfare-build-task` in that repo. The standard's last anti-pattern names every place the port appears. Never edit the repo from here |
   | `PORT_UNIMPLEMENTED` | the claim is made, the repo has no compose file yet. Nothing to fix here. It clears when the dev stack lands |
   | `PORT_UNPARSED` | a compose file the scanner cannot read a host port from. Look at it: either it publishes no port (drop the row's port) or it uses a syntax worth adding to `hero_compose_port` |
   | `PORT_COLLISION` | pick the next free port in `port-range` for the newer row, propose it. Route the repo change as for a mismatch |
   | `NO_HERO` | offer `wayfare:wayfare-init-repo` in that repo (a subagent, per the standard's fan-out) |
   | `NO_AGENTS` | same, via `wayfare-init-repo`'s Step 1 |
   | `NOT_FLEET_AWARE` | *Make the repos fleet-aware*, below |
   | `NO_INBOX` | a reply sent to that repo cannot be delivered. Offer a wayfare skill that opens the store, such as `wayfare-sync-plan`, in that repo (a subagent); its Step 0 creates the inbox after the exclude entry. Never create the inbox from here: the sender-side refusal in [MESSAGES.md](../../docs/MESSAGES.md) exists because a store written from outside can be committed |
   | `PLANS_NOT_EXCLUDED` | the repo's `.plans/` can be committed. Same route as `NO_INBOX`, whose Step 0 writes `.plans/` to `.git/info/exclude`. In a `none` repo the store is stray: ask whether to remove it, in that repo. Never edit its exclude file from here |

2. Checkouts with no row: `"$SCAN" "$FLEET_ROOT" --list`, minus the paths
   FLEET.md names. `--review` does not report these, deliberately: **FLEET.md
   defines the fleet, and a folder does not join it by being cloned there.**
   Print them as *on disk, not listed* and add no rows unless the user asks for
   one by name. Offering a row per parked clone is how a repo nobody claimed
   acquires one and starts reading as a member.

3. If `org` is set, list what exists there, is not on disk, and has no row.
   `gh repo list ORG --limit 200 --json name,isArchived --jq '.[] | select(.isArchived|not) | .name'`
   minus the folder's checkouts and the rows. Print it as *in the org, not in
   the fleet*. Add no rows.

4. Show the proposed rows, confirm, write `FLEET_ROOT/.fleet/FLEET.md`, and say
   it is an uncommitted change in the register for the person to commit and PR.
   Re-run `--review` and show the remainder. The repo-side findings that were
   routed elsewhere stay until those PRs merge, and that is the correct state.

**Make the repos fleet-aware, after the rows are written, in both modes.**

A clone knows nothing about the folder it sits in, so every fleet repo's own
instructions carry the pointer. For each row whose group is not `none` and whose
`AGENTS.md` (or `CLAUDE.md`) has no `## Fleet` heading (the `NOT_FLEET_AWARE`
rows from `--review`), propose adding the section:

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
SECTION="$WAYFARE_ROOT/assets/fleet/agents-md-fleet-section.md"
cat "$SECTION"
```

**This is a message, not an edit.** `sync` does not write the section into those
repos: appending to a dozen siblings' `AGENTS.md` leaves a dozen dirty working
trees nobody reviewed, in repos whose own agents did not make the change. Each
repo lands its own section, in its own PR, under its own gates.

So for each repo in the list, deposit a `type: ask` into its `.plans/inbox/` per
the *Sending* procedure in `docs/MESSAGES.md`, with:

- `from: fleet`, the reserved sender for a fleet-root run, which has no repo of
  its own. Not the recipient's own row: `from == to` is how a repo marks a note
  from its own previous session, and borrowing it throws away the one provenance
  signal the recipient has.
- `to:` that repo's row name.
- `about: fleet-section`, a subject token, because a fleet-root run has no local
  item id. The dedupe probe keys on `(from, about)` and an empty `about` matches
  every about-less message from the same sender, so two unrelated fleet asks
  would collapse into one and the second would never be sent.
- an `## Ask` naming the section and where the asset lives, the section's full
  text in the body so the recipient never reaches back into this folder to read
  it, and the instruction that it appends to `AGENTS.md`, or to `CLAUDE.md` when
  that is the regular file and `AGENTS.md` is absent.

Show the drafts and the list once, confirm once, then deposit with
`hero_msg_deposit`. Report the repos that now have mail and the one line each
runs to act on it (`wayfare:wayfare-sync-plan`, whose `inbox` stage promotes the
ask).

A row whose `.plans/` does not exist cannot receive one: no mailbox, and no
agent workflow to read it. Name those separately and offer to `cd` in. Never
create a store inside someone else's checkout to make the deposit work. That is
the second kind of write, and it is the one that does not exist.

If a repo's existing section differs from the asset, send the same message and
report the difference. Wayfare maintains the source asset. Treat each repo's
copy as output that re-vendoring can overwrite.

## Anti-patterns

- **Guessing membership.** A checkout with a `HERO.md` is a repo the hero skills
  run in, not proof it shares the fleet's stack. Default `none`, ask.
- **Editing a repo to satisfy the registry.** `sync` touches no repo at all. The
  `## Fleet` section goes as a message, like everything else
  (`docs/MESSAGES.md`). Port changes and missing configs go through the skill
  that owns them, in that repo, on a PR.
- **Adding rows for repos that are not on disk.** The org listing is
  informational. See the standard.
- **Dropping a row because it is not cloned here.** The map is shared; another
  machine has that checkout. Offer the clone; drop only a retired repo.
- **Committing the map.** `sync` leaves the change in the register's working
  tree. The person commits it and opens the PR, under the register's own review.

## Next steps

- Findings routed to repos → run the named skill from the fleet root and pick
  those repos (the standard's fan-out), or `cd` in.
- Clean → nothing. Re-run `review` after cloning or moving a checkout.
