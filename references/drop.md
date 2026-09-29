# `drop ID`: abandon work and record that it was abandoned

Stop work on an item that will not be finished. If it has a branch that never
merged, stash anything uncommitted, switch back to the default branch and pull;
either way, mark the item so the roadmap tells the truth about it.

This was `wayfare:wayfare-drop-item`. Two things changed in the move. It takes
an **item id**, and it writes `status: dropped` on that item, the state
`docs/PLAN.md` defines and that nothing previously set, so an abandoned branch
used to leave its item sitting at `active` forever, claiming work that had
stopped. And `dropped` deliberately does **not** satisfy a dependency: the
prerequisite was abandoned, so anything waiting on it really is blocked, and the
listing says so instead of quietly unblocking.

`wayfare:wayfare-ship-pr` already cleans up a **merged** branch. This verb is
for the opposite case, and it checks: a branch whose PR turns out to have merged
is not a drop, and the run says so rather than deleting it.

## Marking the item

Resolve the id first, before touching the working tree, and branch on what it
names:

- **A task with a `branch:` field** runs Steps 1 to 5 below, then the item
  write.
- **Any other open item** (a `new`, `accepted` or `planning` task, an `idea`, an
  `anti-feature`, a `signal`, a goal) has no branch and nothing in git to undo.
  Skip Steps 1 to 5: touch no stash, no checkout and no pull, run the item write
  and report. It does not need `HERO.md` for a default branch either, so skip
  Step 0's read of it.

Both paths need a reason. If the invocation carried none, ask for one before
writing anything; a drop with no reason is a file the next round cannot tell
from an oversight.

The item write, after the branch work succeeds (or straight away on the
branchless path):

- Set `status: dropped` on the item. Leave `resolution` unset: `dropped` is its
  own terminal, not a flavour of `done`.
- Append one `## Log` line saying what was abandoned and why, dated:
  `- DATE (wayfare-drop-item) decision: dropped: REASON`. This is the only
  record: `.plans/` is git-ignored, so there is no diff and no blame to recover
  the reason from later.
- **Keep the file.** A dropped item is the history that stops the same work
  being re-proposed next round, the same reason a `rejected` signal is kept.
- Say which dependents this blocks. `hero_ready_items` will report them as
  blocked from here on, and the user should hear it now rather than discover it
  at the next sync.

An id that names a `done` item is refused: finished work is not abandoned. An id
with no item is refused rather than guessed at. An id that is already `dropped`
is reported and left alone.

**A goal with open members asks first.** Dropping a goal leaves its tasks
pointing at a parent that will never run, so list the members that are not
`done` (`hero_goal_members`) and ask whether to drop the set. On yes, each open
member gets the same item write with the same reason, and the goal is written
last; a member with a `branch:` still needs its own branch steps, so run them
per member. On no, drop nothing.

## Step 0: Load Hero Configuration

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

This step and every step after it are the branch path; the branchless path skips
them. Read `HERO.md` if it exists. This skill uses:

- **Repository** → default-branch (to know which branch to switch back to)

If `HERO.md` is missing, default to `main`.

## Step 1: Check for Uncommitted Work

```bash
git status --porcelain
CURRENT=$(git branch --show-current)
git stash list
```

**If uncommitted changes exist, STOP and show:**

```
You have uncommitted changes on '$CURRENT':

  (list changed files from git status)

Options:
1. Stash changes (saved as "wayfare-drop-item: WIP on $CURRENT") — you can restore later with `git stash pop`
2. Cancel — go back and commit or handle changes first
```

**STOP and wait for user to choose.** Do NOT proceed without explicit
confirmation. Do NOT offer a "discard" option. A user who truly wants to discard
can do that themselves before running this skill.

**If user chooses option 1 (stash):**

```bash
git stash push -m "wayfare-drop-item: WIP on $CURRENT"
```

Report the stash ref:

```
Stashed as: stash@{0} — "wayfare-drop-item: WIP on $CURRENT"
You can restore later with: git stash pop
```

Note: this does NOT auto-pop the stash since the purpose is to switch away from
the current branch. The user must manually restore if needed.

## Step 2: Confirm the Branch Is Actually Unmerged, Then Switch Away

```bash
# shellcheck source=/dev/null
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
# _verbose, not the silent variant: this value gates a force-delete. On a repo
# whose real default is `master`, a silent fallback to `main` makes
# `gh pr list --base main` return 0, the branch reads as never-merged, and
# Delete is offered on work that was merged.
DEFAULT_BRANCH=$(hero_default_branch_verbose)
if ! git fetch origin "$DEFAULT_BRANCH"; then
  echo "WARN: 'git fetch origin $DEFAULT_BRANCH' failed — the merged-check below may be unreliable. Resolve network/auth before trusting its result."
fi
```

If already on the default branch, skip to Step 3.

Otherwise, check whether the current branch has secretly already been merged
(this catches squash-and-merge). If it has, this is not a drop at all: point the
user at `wayfare-ship-pr`'s cleanup rather than duplicating it here. Check
remotely first, but fall back to a local check when the API call fails. A
network hiccup must not read as "unmerged" when a real merge-status query would
have said otherwise, and that matters more now that it gates the destructive
Delete option below:

```bash
MERGED_COUNT=$(gh pr list --head "$CURRENT" --base "$DEFAULT_BRANCH" --state merged --json number --jq 'length' 2>/dev/null)
if [ -z "$MERGED_COUNT" ]; then
  echo "WARN: could not query merged-PR status via gh — falling back to a local check."
  if git branch --merged "origin/$DEFAULT_BRANCH" 2>/dev/null | grep -Eq "^[[:space:]]*\*?[[:space:]]*${CURRENT}$"; then
    MERGED_COUNT=1
  else
    MERGED_COUNT=0
  fi
fi
```

**If `$MERGED_COUNT >= 1` (already merged):** stop and say
`'$CURRENT' already has a merged PR, so this is not a drop. Run wayfare:wayfare-ship-pr's cleanup flow (or delete '$CURRENT' manually) instead.`
If Step 1 stashed anything, say so explicitly here too, because the user is
being redirected away and would otherwise get no reminder:
`Note: your uncommitted changes are stashed (stash@{0}). Restore them with 'git stash pop' after switching branches.`
Do not proceed with this verb.

**Otherwise (genuinely unmerged):**

```
Warning: Branch '$CURRENT' has NOT been merged into '$DEFAULT_BRANCH'.

Options:
1. Pause — switch away, keep '$CURRENT' locally to come back to later
2. Delete — abandon for good: force-delete '$CURRENT' locally (and its remote
   branch / open PR, if any) after switching away
3. Cancel — stay on '$CURRENT' and handle it first
```

**STOP and wait for user to choose.** Never delete without this explicit
confirmation. An unmerged branch is unrecoverable work once its local ref and
reflog expire.

**If the user chose option 3 (Cancel): stop here.** Do not run the checkout
below.

For options 1 (Pause) and 2 (Delete), switch to the default branch first:

```bash
if [ "$CURRENT" != "$DEFAULT_BRANCH" ]; then
  git checkout $DEFAULT_BRANCH
fi
```

**If the user chose option 2 (Delete):** force-delete the local branch, then
check for a remote branch and/or open PR and offer to remove those too. Do not
delete them silently:

```bash
git branch -D "$CURRENT"

PR_INFO=$(gh pr list --head "$CURRENT" --state open --json number,url --jq '.[0]' 2>/dev/null)
REMOTE_EXISTS=$(git ls-remote --heads origin "$CURRENT" 2>/dev/null)
```

If `$PR_INFO` is non-empty, ask:
`Open PR #{number} ({url}) still points at '$CURRENT'. Close it too? [y/N]` On
yes, run `gh pr close {number} --delete-branch`, which closes the PR and deletes
the remote branch in one call. On no, leave the PR and remote branch alone and
say so explicitly.

If there's no open PR but `$REMOTE_EXISTS` is non-empty, ask:
`Remote branch 'origin/$CURRENT' still exists. Delete it too? [y/N]` On yes, run
`git push origin --delete "$CURRENT"`.

## Step 3: Pull Latest

```bash
git pull origin $DEFAULT_BRANCH
```

**If pull fails due to conflicts:** Report and let user resolve.

## Step 4: Clear Context

Run `/clear` to reset the conversation context.

## Step 5: Report

```
Abandon Summary
==================
Branch: {default-branch}
Status: Up to date with origin

Previous branch: {previous-branch} [paused, kept locally / deleted (local + remote/PR, if confirmed) / was already on default]
Pulled: N new commits
Stashed: [yes — "wayfare-drop-item: WIP on {branch}" (restore with `git stash pop`) / no]
Context: Cleared

Next step: wayfare:wayfare-build-task — start the next task (print only — launch it on the user's word, never spontaneously)
```
