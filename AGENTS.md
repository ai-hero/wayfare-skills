# AGENTS.md

This repo is **wayfare**, the A.I. Hero plugin: the skills agents invoke, the
assets they install into other repos, and the one workflow the whole fleet
executes. It ships no product and has no build. The checkout is
`~/.claude/plugins/wayfare-skills`, which is the default path in every skill's
`WAYFARE_ROOT` line.

**Renamed from `hero-skills` on 2026-09-21, and a `uses:` does NOT follow a
rename redirect.** The content API and the web UI do redirect, which is what
made this look safe; Actions does not, so every consumer's auto-approve failed
at startup (zero jobs, no failing step) from the rename until its caller was
re-vendored. Measured, not guessed: four consumers went green the minute their
`uses:` was updated. A consumer still on the old path is **broken now**, not
running on borrowed time, and `wayfare-init-repo` reports it as
`AUTO_APPROVE_STALE`. Once nothing references the old path, claim
`ai-hero/hero-skills` as an empty archived repo so the name cannot be taken:
`members_can_create_repositories` is `true` here, and any member claiming it
would be handed `ANTHROPIC_API_KEY` and an approve-capable token by any consumer
still pointed there.

Instructions for coding agents working here. Follow these strictly; ask before
deviating.

## The one thing to understand first

`.github/workflows/auto-approve.yaml` is a **reusable workflow that ~25 repos
call at `@main`**. Merging a change to it publishes that change to every one of
them, immediately, with no per-repo PR and no staging step.

That file has a blast radius no other file here has:

- **`main`'s branch protection is the only gate.** Approval required, stale
  approvals dismissed on push, last-push approval required. Without that last
  pair, an approval collected on a benign diff survives a force-push and ships
  fleet-wide seconds later.
- **Roll back by reverting on `main`.** That is the whole procedure.
- **Never rename or move it without sequencing.** Consumers reference it by
  exact path, so a rename breaks auto-approve, the very mechanism that approves
  the PRs fixing it. Bank the consumer approvals first, then flip.

`assets/auto-approve/caller.yaml` is what gets installed into consumers. It is
not the logic and must stay small.

## Layout

`ls` shows it. The two non-obvious facts: `assets/` is installed **into** other
repos (the auto-approve caller, the design-system rule and hook, the `## Fleet`
section for AGENTS.md), with the exception of `assets/compliance/`, the register
baseline the engine reads in place. And `pr-check.yaml` is this repo's own gate
while `auto-approve.yaml` is the fleet's.

## Conventions

- **Read before edit.** Match the surrounding style; don't introduce new
  patterns.

- **This file follows [docs/AGENTS-MD.md](./docs/AGENTS-MD.md)**, and
  `scripts/check-agents-md.sh` gates it on commit.

- **Don't wrap Markdown by hand.** The `mdformat` hook re-wraps every paragraph
  at 80 on commit, so write the sentence and let it place the breaks. Mechanical
  doc rules (dashes, banned phrases, step numbers, counts beside a chain) are
  `scripts/check_docs.py`'s, and its error names the fix.

- **Comments: see [.claude/rules/comments.md](./.claude/rules/comments.md).**
  Claude Code loads it automatically; other agents must read it first. The
  one-line test, so it survives a skimmed read:

  > **Would someone later undo this for a reason this comment prevents?**

  If no, leave it out.

- **`.yaml`, never `.yml`** (PLACE-06). Nothing in this fleet mandates `.yml`.
  The installer defaults fresh installs to `.yaml` but still adopts an existing
  `.yml`. Writing the second spelling beside the first would leave two live
  `issue_comment` workflows, and every trigger would run twice.

- **A folder of sibling checkouts is a fleet, not a project.** `FLEET.md` at its
  top maps it ([docs/FLEET-MD.md](./docs/FLEET-MD.md)); every repo skill tests
  for it in Step 0 and fans out instead of running against the folder. New
  skills get the check from `scripts/new-skill.sh`.

- **Work is concurrent, so rebase before you judge.** Several features build at
  once (wayfare's goal turns run one worktree subagent per feature), and other
  people merge underneath every PR. Before a review, an approval, or a merge,
  rebase the PR onto the current default branch with `hero_rebase_on_base` and
  confirm it went through: no conflict, and checks green on the rebased head. A
  verdict on a stale head is a verdict on code that will not merge. Rebase
  *before* `@auto-approve`, never between the verdict and the merge: branch
  protection dismisses approvals on push.

- **Three nouns, and each owns one file.** `hero` is the single focus agent in
  one repo (`HERO.md`); `fleet` is the floor those repos sit on (`FLEET.md`,
  [docs/FLEET-MD.md](./docs/FLEET-MD.md)); `wayfare` is the route between the
  product as it is and as it should be (`.plans/`,
  [docs/PLAN.md](./docs/PLAN.md)). Conversation uses the three interchangeably;
  the code does not. Scope a verb to the wrong noun and it writes the wrong
  file, which is the mistake below.

- **What a repo attaches to is a connection; where it sits is the fleet.** Six
  kinds, closed list, one `### kind` block each under `## Connections` in
  HERO.md ([docs/CONNECTIONS.md](./docs/CONNECTIONS.md)). Three states, never
  two: no block means nobody looked, `type: none` means looked and there is
  none, and a set `type` whose `reach` is unavailable means broken. Read that
  last one as absent and the run silently drops the lane it should have
  reported.

- **`recalibrate` writes HERO.md; `sync` writes the skill's own file.** Ten
  skills carry the verb ([docs/RECALIBRATE.md](./docs/RECALIBRATE.md)), and
  `wayfare-recalibrate-config` is the verb itself; their field map is
  `scripts/hero-fields.sh`, and a field missing there is a field no recalibrate
  can ask about. `wayfare-sync-fleet` and `wayfare-sync-plan` are unrelated:
  they converge FLEET.md and the plan, not config. `wayfare-audit-compliance`
  writes no config at all (it is the compliance audit and the backport drafts),
  so the config verb is always `recalibrate`, however much `improve` sounds like
  one.

- **Three skills are stages, reached only by another skill.**
  `wayfare-review-architecture`, `wayfare-sync-architecture` and
  `wayfare-audit-security` are `user-invocable: false` and chained
  (`CHAINED_SKILLS` in `scripts/validate.sh`). None carries `recalibrate`;
  `wayfare-recalibrate-config` reads the whole field map with `--all`, so their
  fields are reachable without it. A verb added to one of them is a verb nobody
  reaches unless `wayfare-sync-plan` (or, for architecture,
  `wayfare-grill-idea`'s `arch` dispatch) calls it.

- **Assets are vendored downstream, not authored there.** Fix a bug here, then
  re-vendor. A consuming repo's copy is output.

- **Tests are `scripts/*.test.sh` and both runners glob.** Add a suite and it
  gates automatically, with no runner edit needed.

- **Agents are created once and versioned, not per run**; see
  `docs/PIPELINES.md`.

## Commands

```bash
pre-commit run --all-files     # every gate, including the shell suites
bash scripts/validate.sh       # plugin structure
```

## Fleet

This repo is one checkout in a fleet: sibling repos in the folder above it,
mapped by that folder's `FLEET.md` (`wayfare:wayfare-sync-fleet`). The map is
local and unversioned, so clone this repo beside the others and run
`wayfare:wayfare-review-fleet`. The host port this dev stack publishes is
claimed in that map, not chosen here: take the next free port there first, then
set it in every place this repo names it (compose defaults, health checks). Any
hero skill run from the fleet folder fans out to the repos you pick.

Work here is concurrent: other branches, including worktree subagents building
features in parallel, merge underneath every open PR. Before a review, an
approval, or a merge, rebase the PR onto the current default branch and confirm
it can be done (no conflict, checks green on the rebased head); never review,
approve, or merge a stale head. Rebase before the approval, not after it:
approvals are dismissed on push.

An agent working in one checkout that needs something from a sibling sends a
message rather than reaching into that repo directly; see
[docs/MESSAGES.md](./docs/MESSAGES.md).
