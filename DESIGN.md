# Design

> Last updated: 2026-08-07 · Source ref:
> ffe17a28a74d0a0f23730ad438e01486d297f880

Why wayfare is shaped the way it is. Facts the code cannot state about itself,
and decisions someone would otherwise undo.

## Overview

A Claude Code plugin: skills, the scripts they call, and assets they install
into other repos. No product, no build, no runtime. Its output is *other repos'
configuration*.

That inversion drives everything below: a change here is a change to ~25 repos,
so the interesting risks are distribution risks, not correctness risks.

## Tech stack

Shell (bash) and Markdown. No compiled language, no package manifest, no build
step. `pre-commit` and `scripts/validate.sh` are the entire toolchain. GitHub
Actions runs the same two gates CI runs locally.

## Codemap

| Path | What lives there |
| -- | -- |
| `skills/<name>/SKILL.md` | One skill each: instructions an agent follows, not code it runs. |
| `scripts/` | Shell helpers and their `*.test.sh` suites; `validate.sh` checks plugin structure. |
| `assets/` | Files copied **into** other repos by the installers. |
| `.github/workflows/auto-approve.yaml` | The shared reusable workflow ~25 repos execute at `@main`. |
| `.github/workflows/pr-check.yaml` | This repo's own gate. |
| `docs/` | Non-entry documentation, e.g. `PIPELINES.md`. |

## Boundaries

| Boundary | Rule |
| -- | -- |
| `skills/` → the world | Skills are instructions, not code. They are read by an agent and executed with the agent's own tools. |
| `assets/` → consumers | Copied verbatim into other repos by `scripts/install-*.sh`. Treat as vendored downstream: fix here, re-vendor. |
| `.github/workflows/auto-approve.yaml` → consumers | Executed *in place* by ~25 repos via `uses: …@main`. Not copied; resolved at trigger time. |

The last row is the one that surprises people. `assets/auto-approve/caller.yaml`
is **copied**; `auto-approve.yaml` is **called**. A change to the first reaches
a repo when someone re-runs the installer. A change to the second reaches every
repo on merge.

## Decisions

### Distribution: `@main`, deliberately

Consumers track `main` rather than a tag or a SHA.

This replaced a moving `v1` tag. The tag needed a release workflow to move it, a
GitHub App installed as a ruleset bypass actor to be *allowed* to move it, and a
carve-out in the fleet's pin rule. All of that was built and verified, and then
its one distinctive capability turned out to be the problem: the release
workflow's manual repoint accepted any commit, so write access here was enough
to aim 25 repos' approval pipeline at unreviewed code, around the branch
protection the design depended on.

A branch ref has nothing to aim. `main`'s protection is the whole gate.

The tradeoff accepted: no way to hold the fleet at a known-good commit while
`main` moves ahead. Rollback is a revert. That is a worthwhile trade for a
shared CI workflow and would not be for a library.

### Why the shared workflow is called, not copied

The fleet previously carried 25 private copies in six distinct versions, two
still running a verdict parser that failed **open**, approving PRs when the API
errored. That is the failure mode copying produces: a fix made once reaches
nobody, and nothing reports the drift.

Calling it means this class of bug is fixed once. The cost is the blast radius
above, which is why `main`'s protection settings are a gate, not hygiene.

### Gates live in code, not in the prompt

`auto-approve.yaml` checks *prior review present* and *all threads resolved* as
deterministic bash steps before the model is consulted. Other repos in the fleet
historically asked the model to judge those in the prompt.

Deterministic beats judged for anything with a crisp answer: the model's job is
narrowed to what only a model can do: reading a diff against a description. A
gate that a prompt can be talked out of is not a gate.

The trigger is anchored for the same reason: it fires only when a comment
*starts with* the command. Matching anywhere meant that merely writing about
`@auto-approve` (as a self-review comment does) posted a real approval.

## Invariants

### Testing

`scripts/*.test.sh`, globbed by both `pre-commit` and CI so a new suite gates
without a runner edit. They assert exit codes and filesystem state, never stdout
wording: output text changes for documentation reasons and would make the suite
brittle for no bug-catching value.

`install-auto-approve.test.sh` additionally asserts the **caller↔callee
contract**: secret declarations line up, the caller's permissions cover what the
callee declares, `secrets: inherit` is absent, and the caller tracks `main`.
Those violations fail in the *consuming* repos, not here, so nothing in this
repo's normal feedback loop would surface them.

### Compliance

Controls are defined in the fleet's register checkout (`CONTROLS.yaml` /
`CHECKS.yaml`), not here. This repo is audited as a family member. A check names
no repo (not an exemplar and not an exemption), so an open gap shows up as a
failing cell every run rather than as a carve-out nobody re-reads.
