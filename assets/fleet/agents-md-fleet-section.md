## Fleet

This repo is one checkout in a fleet: sibling repos in the folder above it,
mapped by that folder's `FLEET.md` (`wayfare:wayfare-sync-fleet`). The map is local and
unversioned, so clone this repo beside the others and run
`wayfare:wayfare-review-fleet`. The host port this dev stack publishes is claimed
in that map, not chosen here: take the next free port there first, then set
it in every place this repo names it (compose defaults, health checks).
Any wayfare skill run from the fleet folder fans out to the repos you pick.

Work here is concurrent: other branches, including worktree subagents
building features in parallel, merge underneath every open PR. Before a
review, an approval, or a merge, rebase the PR onto the current default
branch and confirm it can be done (no conflict, checks green on the rebased
head); never review, approve, or merge a stale head. Rebase before the
approval, not after it: approvals are dismissed on push.
