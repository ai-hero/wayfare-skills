# Pipelines

Hero skills that orchestrate multi-step work render a linear-DAG progress line
on the console at each step transition. This doc is the single source of truth
for the canonical pipelines and the rendering format.

## Render Format

At the **start of each step** (just after announcing what is about to run),
print:

```
[N/M] (✓) step1 → (✓) step2 → (▶) step3 → ( ) step4 → ... → ( ) stepM

Now running: step3
```

Rules:

- `N` is the 1-indexed current step. `M` is the total number of steps.
- `(✓)` for steps already completed in this session.
- `(▶)` for the step currently starting.
- `( )` for steps not yet run.
- Use Unicode `→` (U+2192) between steps for the arrow chain.
- Keep the entire chain on one line, even if it wraps in narrow terminals.
- The "Now running:" line names the step that just opened, no other prose.

When a step is **skipped** (because it doesn't apply, e.g., `test` step on a
docs-only commit), mark it `(–)` and continue to the next step. Do not collapse
or renumber.

When a step is **deferred** (it applies, but answering it now would mean waiting
on something outside the pipeline, and nothing downstream depends on the
answer), mark it `(⏸)` and name what will pick it up. `(–)` would claim the step
did not apply, and `(✓)` would claim an answer nobody has. A deferred step is
owed by whatever runs next in that repo. A bounded wait is fine where the answer
is worth it and paid once; an unbounded one is not. wayfare-ship-pr's
`verify-deploy` is the worked example: it waits ten minutes for the merge
commit's runs, then defers the rest.

When the pipeline **stops early** (user declined, hard gate, error), print a
final DAG with `(✗)` on the failed/declined step and `( )` on remaining ones,
followed by `Stopped: REASON`.

## Canonical Pipelines

### Pipeline 1: init-project, scaffold a new project end-to-end

```
scaffold → wayfare-setup-dev → config → first-commit
```

Owner: `wayfare:wayfare-init-repo`. The skill scaffolds the project, then chains
forward to `wayfare:wayfare-setup-dev`, its own config stage, and a final
commit. Each stage announces itself with the DAG line.

**Naming note for `first-commit`:** When scaffolding a *standalone* repo,
`wayfare-init-repo`'s scaffold step already produces the literal first commit
(the scaffold). The DAG node `first-commit` refers specifically to **the commit
that lands `HERO.md` and `AGENTS.md`**, for standalone repos this is the second
commit; for "added to existing repo" it is just the next commit. The node is
named for the canonical case where everything begins with HERO.md present from
commit one onward.

### Pipeline 2: wayfare-build-task, ticket to merged PR in a single invocation

```
plan → implement → simplify → push → self-review → mark-ready → await-review → respond → ship
```

Owner: `wayfare:wayfare-build-task`. Invoked with an issue ID or description it
starts at `plan`; invoked with no arguments it resumes the current goal
(in-progress branch/diff/PR on the current branch, plus the in-flight item's
`## Subtasks` checklist, the plan file is the state file, so a run that died
mid-implement resumes at its first unchecked line) from the detected step and
drives it, through the usual user gates, to merged + a reset checkout. Nine
steps, each maps to a single skill (or `inline` when wayfare-build-task drives
it directly without delegating):

| # | Step | Skill to run standalone | Notes |
| -- | -- | -- | -- |
| 1 | `plan` | `wayfare:wayfare-grill-idea` | resolve `$ARGUMENTS` against `.plans/` and the tracker first; grill only if nothing matches. Re-verifies the item is still outstanding before building |
| 2 | `implement` | `inline` | executes the resolved work-item against its `success` criteria |
| 3 | `simplify` | `/simplify` (external) | review the dirty diff for reuse/quality/efficiency and fix; `(–)` if `/simplify` unavailable |
| 4 | `push` | `wayfare:wayfare-push-pr` | tests first (lint/typecheck/unit + UI smoke via Playwright MCP), then commits outstanding work with a conventional commit and pushes a draft PR |
| 5 | `self-review` | `wayfare:wayfare-review-pr --no-mark-ready` (Steps 1 to 8) | run the pr-review-toolkit agents plus a security pass on the draft, apply fixes |
| 6 | `mark-ready` | `wayfare:wayfare-review-pr`'s own Step 9, or `gh pr ready` | hard user gate that converts draft → ready |
| 7 | `await-review` | `inline` (poll) | poll for the configured Code Review Agent's first comment; `(–)` if `agent: none` |
| 8 | `respond` | `wayfare:wayfare-respond-pr` | address the bot's inline comments and resolve threads |
| 9 | `ship` | `wayfare:wayfare-ship-pr` | `@auto-approve`, await verdict, ask the user to merge, merge, reset to default branch |

UI smoke runs inside `push`'s test phase (absorbed from the former
`test-changes` skill; `wayfare:wayfare-push-pr test` runs it standalone);
backend-only PRs skip it.

`simplify` sits between `implement` and `push` so the dirty diff is tidied
before it lands in git history. `wayfare-push-pr` also invokes `/simplify`
internally for standalone use; running wayfare-build-task just makes that step
visible in the DAG and pays a no-op cost on the second invocation.

**A fan-out subagent is never a fork.** Every parallel launch in this plugin
(simplify's review angles, wayfare-review-pr's toolkit agents, harden's audit
angles, wayfare's builders) uses the default agent type or a named one, and
hands the agent only what its one task needs, such as the diff and an angle for
a review; `subagent_type: "fork"` is never passed. A fork inherits the whole
calling conversation, including every pipeline step still to run, and it runs
them: twice, simplify's four forks each ran the tests, the commit, and `.plans/`
edits concurrently with the parent. The agent does its task and returns; the
pipeline's remaining steps stay with the parent. `/simplify` ships outside this
plugin and leaves the agent type to its caller, so the callers here say it.

**A fan-out waits for every agent, then one writer commits once.** The fork rule
is not enough on its own: fan-out agents that are not forks still race if each
one applies its own fix as soon as it has one. Three parts, and every parallel
launch here keeps all three. The agents report findings and never edit, stage or
commit. The parent applies nothing until every agent it launched has reported,
or has gone silent and been stopped by the parent. A parent waits only on the
agents it launched itself, and each of those waits on its own agents before it
reports, so the wait passes down level by level and no one has to stop an agent
they did not launch. Then the parent applies the combined fixes in one pass and
commits once. Goal 19's simplify pass broke all three at once: one review agent
committed while two sibling agents were still running, one re-staged the same
edits, and one ran `git reset --soft HEAD~1` under the others.
`wayfare-review-pr`'s Step 2 already works this way. The same holds one level
up: a parent never reads, records or tests a branch while an agent it delegated
to is still out, because until that agent reports, the tree is not final.

**The work-item store closes this pipeline's loop.** `wayfare-grill-idea`,
`wayfare-write-handoff`, `wayfare-audit-security`, and `wayfare` write items
into the git-ignored `.plans/` store, and all read it back so they build on the
plate rather than beside it. What wayfare-build-task alone does is *execute* an
item and close it out: Step 1 resolves against the store before grilling
anything new, and Step 9a marks the merged item `done`, no other skill does that
automatically. Because nothing else observes the codebase on the store's behalf,
Step 1 also re-checks a resolved item's `success` criteria against reality,
because `status: ready` only means nobody edited the file, not that the work is
still outstanding.

**Architecture and harden chain.** `wayfare-sync-plan`'s architecture stage runs
`wayfare:wayfare-review-architecture`, and offers its `sync`, before judging the
roadmap, its `wayfare-audit-security` stage runs
`wayfare:wayfare-audit-security all`, and `wayfare-grill-idea` delegates a
leading `arch` argument to the architecture skill. Every edge requires the child
to stay model-invocable (guarded by validate.sh's `CHAINED_SKILLS`); both
children are `user-invocable: false`, so wayfare is the only way a person
reaches them.

**The design return channel.** Every other edge flows target → source. One flows
back: wayfare-build-task logs a divergence it found while building as a `signal`
line in the task's `## Log`, and `wayfare-sync-plan` delivers it. Two
destinations, no third: a sibling checkout the user names from the `FLEET.md`
rows gets a **message** in its `.plans/inbox/` (entries verbatim plus a
manifest, its own agent promotes it), and everything else (no fleet, no row that
owns the divergence, no `.plans/inbox/` to deposit into) gets a packet under
`$STORE/.feedback/` that the user delivers by hand. There is no configured
destination: a fleet holds more than one repo that can own a divergence, and a
stored one sends every lane to whichever was set first. `.plans/` is git-ignored
and wayfare never writes the target, so there is no other way out. Delivery
deliberately does *not* route through `wayfare:wayfare-write-handoff`: that
skill distills the *current* conversation, which would both narrate the wrong
session and carry this repo's branches and PR numbers into a third party's
tracker. See `references/feedback-channels.md`.

**wayfare-build-task authors only Step 2a items.** Step 2a pushes discovered or
mis-scoped work out of the running item into its own `.plans/` item, a
`shape: story` task when it satisfies target-design paths, a `structural` or
`defect` one otherwise (`origin: wayfare-build-task`, `status: accepted` either
way), which is how the one-item-one-PR scope guard survives contact with
implementation. Everything else in the store is authored by the producers above.

`mark-ready` is split from `self-review` so the conversion from draft → ready is
a visible, separately-gated step. `await-review` is split from `respond` so the
poll-for-bot phase is visible even when there is nothing to respond to.

The user must explicitly approve at each gate that involves a destructive or
shared-state change: marking the PR ready, posting `@auto-approve`, and merging.
The skill does not skip those confirmations.

### Pipeline 3: hero init/recalibrate, generate or refresh HERO.md

```
investigate → confirm → write → commit
```

Owner: `wayfare:wayfare-init-repo`. Four steps:

1. `investigate`, deeply scan the repo for evidence of stack, conventions, CI,
   deploy
2. `confirm`, present findings as a numbered list and ask the user to
   confirm/correct
3. `write`, write HERO.md, update AGENTS.md summary sections (CLAUDE.md is a
   symlink to it), and (if the user opted in during `confirm`) install
   `.github/workflows/auto-approve.yaml` via Step 6a and the design-system
   enforcement layer via Step 6b
4. `commit`, stage and commit HERO.md + AGENTS.md + the CLAUDE.md symlink (and
   the auto-approve workflow / design-system rule + hook if installed this run)

Run by itself (`wayfare:wayfare-init-repo` or
`wayfare:wayfare-init-repo recalibrate`) or as the third step of Pipeline 1.

The other skills carry a scoped slice of this pipeline as their own
`recalibrate` verb. RECALIBRATE.md names its phases
`report → ask → write → commit`, where `report` is this pipeline's `investigate`
narrowed to the fields that skill reads, and the verb ends at `commit` without
going on to do the skill's work. The field map is `scripts/hero-fields.sh`; the
contract is [RECALIBRATE.md](./RECALIBRATE.md).

### Pipeline 4: wayfare-sync-plan, one round of convergence

```
config → inbox → architecture → harden → comments → compliance → local → deps → design → reconcile → plan → goals
```

Owner: `wayfare:wayfare-sync-plan`. Twelve stages: the config gate; the mailbox
(`docs/MESSAGES.md`, every unread message through the fleet gate and the
promotion gate, a `type: bug` message becoming a proposed `shape: defect` task);
`wayfare:wayfare-review-architecture` (offering its `sync`);
`wayfare:wayfare-audit-security all`; the `comments` stage (prose gone false
about the code, references/sync.md *The `comments` stage*); the compliance audit
(`scripts/audit.py --repo THIS`, baseline plus the fleet's register overlay)
with each failing check proposed as an item; the repo's own `wayfare: sync`
skills (discovered in `.claude/skills/`, run with the harden contract); the
dependency bots' open PRs written as `shape: dependency` tasks; the design
snapshot refresh; the reconciliation lanes; the planning postflight
(`wayfare:wayfare-grill-idea` in Roadmap mode); and goals proposed bottom-up
until every planned build item is in exactly one open goal, with existing
`accepted` goals re-cut, coalesced when two name one outcome, split when one
names two. Stages that do not apply render `(–)` with the reason; the goals
stage never does. It ends with the roadmap view and, when a goal is runnable,
`Next step: wayfare:wayfare-start-goal`.

`wayfare:wayfare-audit-compliance` is the compliance stage on its own, plus the
backport half sync never does: where this repo is the reference for a check the
template fails, it drafts the message to the template's inbox. At a fleet root
it runs the whole family, regenerates the register's CONSISTENCY.md (fleet-root
form only; consistency.py refuses to run outside a fleet), and offers the
per-repo fan-out.

### Pipeline 5: wayfare-advance-item, a bot's PR to merged and deployed

```
current → test → review → ship → close-out
```

Owner: `wayfare:wayfare-advance-item ITEM_ID` on a `shape: dependency` task with
`bot:` (written and ready-marked by Pipeline 4), see *Carrying a bot's PR* in
the skill. The bot already implemented the bump, so there is no `implement` and
no PR of ours; `test` and `ship` delegate to `wayfare:wayfare-push-pr test` and
`wayfare:wayfare-ship-pr`, and the item is `done` only once the deployment
verifies. A goal turn runs the same steps for each bot item among its members,
on the bot's branch. A bot item never joins the goal's own branch: its PR is the
bot's and has to stay bot-authored.

### Goals: `wayfare-start-goal` runs the turn; `/goal` only re-runs it

`wayfare:wayfare-start-goal` picks the next goal in bottom-up order, reads its
`## Permissions` aloud (`mark-ready`, `respond`, `auto-approve`, `merge`,
`deploy`, `absorb`), takes the user's in-session authorization, and runs one
turn of the goal in that session; `wayfare:wayfare-advance-item GOAL_ID` is that
same turn on its own. A turn that ends on a stop line prints the `/goal` line
that would re-run it unattended, for the person to paste; wayfare cannot set
`/goal` itself.

**A goal is one branch, one PR, and one commit per task.** The turn builds its
member tasks one after another on the goal's branch, in member order. Each build
is handed to one subagent on a cheaper model, scoped to that task's `source`
paths, one at a time because they share the checkout, and it implements, runs
the tests covering its own change, and commits one changeset. The expensive
checks run once, after the last task: one simplify pass and one full test run
over the whole branch. A failure there is bisected across the task commits to
find the task that caused it, and gets its own scoped fix agent and its own
commit rather than being repaired in the parent. Nothing is pushed until every
task is in and the whole branch has passed locally; only then does
wayfare-build-task run once over the branch to push, review, and ship it. That
is one review pass, one auto-approve and one merge for the goal, instead of one
of each per task, and the commits still separate the work for whoever reads the
PR.

Only an invocation that can reach a gate carries the granted permissions, as one
literal line: step 7's hand-off and a bot PR's carry. Build, fix and simplify
agents never get it. A gate the goal was not granted rests the goal at its PR
and ends the loop with `stop: awaiting-human`. Work a turn finds inside a member
task does not become a new goal: if it serves a line of this goal's Definition
of Done it is **admitted** into the goal (its `parent` is set), planned and
built in the same run under `absorb`. `budget` is what the goal is expected to
take in commits, not a gate: going over is ordinary and the report says so, and
`budget_max` is a checkpoint: the turn raises it with a `## Log` line and builds
on in the same PR, up to a ceiling of twice what the gate authorized, and stops
when the rest would need another PR or the raise would pass the ceiling. A goal
ships a second PR only when what is left is a different changeset from what is
already on the branch, never to get a diff under some line count: a PR is as big
as its work, and the commits are what make it reviewable.
