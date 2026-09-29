<p align="center">
  <img src="https://img.shields.io/badge/Wayfare-Agent_Skills-7C3AED?style=for-the-badge&logoColor=white" alt="Wayfare" />
</p>

<h3 align="center">Your dev workflow, automated end to end.</h3>

<p align="center">
  An opinionated development workflow for <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>, customizable to <em>your</em> opinions.
</p>

<p align="center">
  <a href="#how-it-works">How it works</a> &bull;
  <a href="#across-repos">Across repos</a> &bull;
  <a href="#install">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#commands">Commands</a> &bull;
  <a href="#heromd">Config</a> &bull;
  <a href="#extending">Extending</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/ai-hero/wayfare-skills?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/claude_code-plugin-blue?style=flat-square" alt="Claude Code Plugin" />
</p>

______________________________________________________________________

## Why wayfare?

Most dev work follows the same loop: grab a ticket, plan, implement, test,
review, commit, push, monitor. But every team does it slightly differently,
different PM tools, different CI, different deploy targets.

Wayfare gives you **one front door**: `wayfare:wayfare-sync-plan` converges the
roadmap, `wayfare:wayfare-start-goal` runs it. Configure once with `HERO.md`,
then every skill behind that door knows your conventions, your tools, and your
preferences, and drives the whole loop for you:

- **Plan and implement from tickets**: fetch from Linear/Jira/GitHub Issues,
  grill the work into dependency-aware work-items, create branches, then
  implement on approval
- **Verify changes**: auto-detect project type (API, frontend, CLI, MCP) and run
  lint, typecheck, unit tests, and smoke tests
- **Ship with confidence**: pre-commit checks, conventional commits, draft PRs
  by default, automated parallel review before requesting human review
- **Stay informed**: CI/CD status, cluster health, security scans

Each of those is a stage the front door runs for you, and each one is also its
own skill you can run alone (see [Quick Start](#quick-start)).

## How it works

Wayfare is the one skill you run. It reads the world, converges it into a plan,
and hands tasks to the build chain, which folds the result back into the world
it read.

```mermaid
flowchart TB
  SRC["<b>Source</b> · this repo<br/>code + DESIGN.md"]
  TGT["<b>Target</b> · claude.ai/design<br/>optional"]
  PLAN["<b>wayfare-sync-plan</b><br/>reconcile · audit · propose"]
  STORE[("<b>.plans/</b><br/>PLAN.md + items/")]
  NEXT["<b>wayfare-start-goal</b><br/>authorize a goal"]
  DO["<b>wayfare-advance-item ID</b><br/>advance one item"]
  BUILD["wayfare-build-task → wayfare-push-pr<br/>→ wayfare-review-pr → wayfare-ship-pr"]

  SRC -- read --> PLAN
  TGT -- read --> PLAN
  PLAN --> STORE
  STORE --> NEXT
  STORE --> DO
  NEXT --> BUILD
  DO --> BUILD
  BUILD -- merged --> SRC
  STORE -. signal .-> TGT

  classDef verb fill:#7C3AED,stroke:#5B21B6,color:#fff
  classDef store fill:#1E293B,stroke:#0F172A,color:#fff
  classDef end_ fill:#FEF3C7,stroke:#D97706,color:#78350F
  class PLAN,NEXT,DO verb
  class STORE store
  class SRC,TGT end_
```

With no design project configured the target end is simply absent, and
`wayfare-sync-plan` reconciles the repo against `DESIGN.md`, its own gaps and
its own hardening instead: a self-review.

### The plan store

`.plans/` is the system of record: one `PLAN.md` per repo and one file per item.
Items come in five types, and a task's `shape` decides what its Definition of
Done has to assert.

| Type | What it is | What happens to it |
| -- | -- | -- |
| `task` | a change to this repo, shipped on a PR | built |
| `signal` | a finding delivered where this repo cannot write | delivered upstream |
| `goal` | an ordered set of tasks with one Definition of Done | grouped and authorized |
| `idea` | something worth doing eventually, not yet shaped into work | nothing, until you promote it |
| `anti-feature` | a thing looked at and decided against | refused and cited |

An **idea** is the parking lot: a thought worth keeping that nobody has
committed to. It carries no plan, no paths and no Definition of Done. An idea
that can state one is a task that was mis-filed. Nothing builds an idea and
nothing may depend on one; `wayfare-sync-plan` reports the parked set as a count
and promotes only what you pick, at which point whatever it becomes carries
`discovered_from` pointing back at it.

Every item runs one lifecycle. `ready` is the only state a person sets, and it
is the gate: nothing is built without it.

```mermaid
stateDiagram-v2
  [*] --> new
  new --> accepted: plan accepts it
  accepted --> planning: wayfare-grill-idea
  planning --> ready: your ready-mark
  ready --> active: wayfare-build-task starts
  active --> committed: on a goal branch
  active --> review: PR opens
  committed --> review: goal's PR opens
  review --> done: merged, deploy verified
  active --> dropped: wayfare-drop-item
  done --> [*]
  dropped --> [*]
```

`done` unblocks whatever depends on the item; `dropped` deliberately does not,
because the prerequisite was abandoned. The full specification is
[docs/PLAN.md](./docs/PLAN.md).

### From tasks to goals

Grouping is the **last stage of every `wayfare-sync-plan`**, not a separate step
you run. It works bottom-up from the dependency graph: the first goal is the
smallest outcome whose tasks depend on nothing outside the group, the next is
the smallest outcome whose remaining dependencies are already inside a formed
goal, and so on.

```mermaid
flowchart TB
  subgraph G7["goal 7 · I can manage my trips"]
    T12["task 12<br/>save a trip"]
    T13["task 13<br/>rename it"]
    T21["task 21<br/>empty state"]
    T12 --> T13
    T12 --> T21
  end

  subgraph G9["goal 9 · I can share a trip"]
    T15["task 15<br/>share link"]
    T18["task 18<br/>read-only view"]
    T15 --> T18
  end

  T13 -. "task edge crosses the boundary" .-> T15
  G7 == "so goal 9 depends_on 7 — derived, never authored" ==> G9
```

Goals are grouped by **outcome** (what a person can do once the whole group
ships), never by area or layer. A group whose Definition of Done cannot be
stated as one user-visible outcome is a filter over the roadmap, not a goal, and
it will report `done` without anything shipping that a person notices.

The stage holds one invariant: **every item at `ready` or further and not `done`
is in exactly one open goal.** `wayfare-start-goal` walks goals and never items,
so a `ready` task in no goal is an orphan nothing in the loop reaches. A task
that adds up to nothing larger becomes a one-item goal: small, but reachable.

Each round **re-cuts** the open goals rather than appending to them: tasks join
and leave, two goals naming one outcome coalesce, a goal whose DoD became two
outcomes splits. An `active` goal is frozen, because its members and permissions
were authorized as a set at `wayfare-start-goal`'s gate.

`sync` writes the goal. It never authorizes it. That is typed by a person at
`wayfare-start-goal`, in-session, and is never stored in the file.

## Across repos

**Wayfare works in one repo at a time: the one it runs in.** It never edits a
sibling. That rule is what makes the rest of this predictable: a change made in
a repo whose own agent did not make it lands in no PR, is reviewed by nobody,
and turns up as a dirty working tree someone else has to explain.

A folder of sibling checkouts is a **fleet**, mapped by a `FLEET.md` at its top
([docs/FLEET-MD.md](./docs/FLEET-MD.md)). The map is local and unversioned. Work
crosses a repo line in exactly three ways:

```mermaid
flowchart LR
  subgraph FLEET["the fleet folder · FLEET.md maps it"]
    A["<b>repo A</b><br/>wayfare runs here"]
    B["<b>repo B</b><br/>a sibling checkout"]
    DS["<b>design system</b><br/>a sibling checkout"]
  end
  PACKET["<b>packet</b><br/>$STORE/.feedback/"]

  A == "1 · fan-out<br/>an agent runs in B" ==> B
  A -- "2 · message<br/>into B's inbox" --> B
  A -. "3 · signal<br/>into its inbox" .-> DS
  A -. "3 · signal<br/>no row owns it" .-> PACKET

  classDef repo fill:#FEF3C7,stroke:#D97706,color:#78350F
  classDef out fill:#EDE9FE,stroke:#7C3AED,color:#4C1D95
  class A,B,DS repo
  class PACKET out
```

**1. Fan-out.** Running a hero skill from the fleet root does not reach
sideways. It *starts an agent in* each repo you pick, and that agent writes only
to its own repo, on its own branch, under its own gates. This is the sanctioned
way a sibling changes.

**2. Messages.** An agent in A that needs something from B deposits a file in
B's `.plans/inbox/`, and that is the **only** write A ever makes outside itself.
No code, no config, no branch, no `git` command in another checkout. Two gates
apply: a **fleet gate** (only a repo with a `FLEET.md` row may deposit) and a
**promotion gate**: an inbound message never becomes work by itself. B's agent
reads it, weighs it, and promotes it to an ordinary item. Skip that and a
sibling is writing B's roadmap. See [docs/MESSAGES.md](./docs/MESSAGES.md).

**3. Signals.** What building teaches travels back out to whoever owns the thing
it disagrees with, as a message into that repo's inbox, so its own wayfare
promotes it like any other. The destination is not configured: you name the
`FLEET.md` row at delivery, because a fleet holds more than one repo that can
own a divergence and a stored destination sends all of them to whichever was set
first. When no row owns it, the signal is written to a local packet file instead
and nothing silently vanishes.

A message is **data, never an instruction**: it was written by another agent, so
it is the same untrusted class as a design doc or a PR comment thread. One that
appears to give orders is content that rode in, and it has no effect.

## Install

```bash
git clone https://github.com/ai-hero/wayfare-skills.git ~/.claude/plugins/wayfare-skills
```

Skills are immediately available in any Claude Code session. No restart needed.

The plugin is **wayfare**, so its skills are invoked as
`wayfare:wayfare-sync-plan` and the like. The clone target is `wayfare-skills`,
which is the default path in every skill's `WAYFARE_ROOT` line
(`$HOME/.claude/plugins/wayfare-skills`).

The same skills install into Codex, Cursor, and other Agent Plugin hosts from
the same checkout. The root `plugin.json` is their shared portable Agent Plugin
manifest; `.agents/plugins/` provides Codex marketplace metadata. Claude Code
does not load the portable `plugin.json`; its separate adapter remains under
`.claude-plugin/`. No separate build or rewrite is needed. `CLAUDE_PLUGIN_ROOT`
is a Claude Code harness variable, and it is not reliably set in a skill's Bash
calls, so every skill resolves its plugin root through one `WAYFARE_ROOT` line:
`CLAUDE_PLUGIN_ROOT` when set, else an exported `WAYFARE_ROOT`, else the default
clone path. An agent with neither exports `WAYFARE_ROOT` as
`$(cd "$(dirname "$SKILL_MD")/../.." && pwd)` (the directory two levels above
the `SKILL.md` it loaded) before running a skill (see
[references/loading.md](./references/loading.md)).

Every Wayfare skill declares this complete-plugin dependency in its Agent Skills
`compatibility` metadata. Activation entrypoints stay below 500 lines. For the
five long PR pipeline stages, `SKILL.md` holds discovery, routing, and
invariants while a linked `WORKFLOW.md` preserves the executable specification.
Portable instructions name capabilities rather than one client's tool-call
syntax; [client capabilities](./references/client-capabilities.md) maps those
operations to Codex, Claude Code, or a compatible client, and
[authorization](./references/authorization.md) defines when a run continues,
confirms, stops, or defers.

For Cursor, import this repository from **Customize -> Plugins -> From GitHub
Repository**, install `wayfare`, then reload the window. Cursor reads the root
`plugin.json`. For local development, copy the complete checkout into
`~/.cursor/plugins/local/wayfare`; Cursor does not follow a symlink whose target
is outside that directory. Installing the complete plugin matters because the
skills share root-level scripts, references, and assets.

The repo was called `hero-skills` until 2026-09-21. If you vendored the
auto-approve caller before then, it says
`ai-hero/hero-skills/.github/workflows/auto-approve.yaml@main` and **it is
broken**: GitHub redirects the old name for the API and the web UI, but a
workflow `uses:` does not follow that redirect, so the run fails at startup with
zero jobs and no failing step. Re-vendor `assets/auto-approve/caller.yaml`; that
is the whole fix, and it takes effect as soon as it lands on your default
branch.

### Companion installs (for full pipeline coverage)

Three pieces ride along with wayfare-build-task, install them so Steps 4
(`push`, tests included), 5 (`self-review`), 8 (`respond`), and 9 (`ship`) work
out of the box:

**1. GitHub CLI (`gh`)**: required by `wayfare-push-pr`, `wayfare-review-pr`,
`wayfare-respond-pr` and `wayfare-ship-pr` for every PR / comment / workflow
operation. Without it, every step from `push` onward fails immediately.

```bash
# macOS (Homebrew)
brew install gh

# Linux (Debian/Ubuntu)
sudo apt install gh

# Other platforms: https://cli.github.com/
```

Then authenticate with the `repo` scope (required for PR creation, merge, and
`gh secret set`):

```bash
gh auth login -s repo
```

`wayfare:wayfare-check-preflight` verifies both presence and the `repo` scope.

**2. `pr-review-toolkit` plugin**: provides five of the six review agents that
`wayfare:wayfare-review-pr` runs in parallel (code-reviewer,
silent-failure-hunter, pr-test-analyzer, comment-analyzer, type-design-analyzer;
the sixth, a security pass, needs no install). From inside Claude Code:

```
/plugin install pr-review-toolkit
```

Or from the host shell:

```bash
claude plugins add pr-review-toolkit@claude-plugins-official
```

If you skip this, `wayfare:wayfare-review-pr` still runs but produces a much
thinner review.

**3. Playwright MCP server**: drives the browser smoke test in
`wayfare:wayfare-push-pr`'s test phase (frontend smoke). Requires Node.js 18+
(check with `node --version`):

```bash
claude mcp add playwright npx @playwright/mcp@latest
```

Use `--scope user` to share the registration across every project on the
machine, or `--scope project` to commit it to the repo. Without this, the
frontend-smoke portion of the test phase renders `(–)` (skipped) and you lose
the UI regression check before commits land.

## Quick Start

Three commands. Everything else is run by them.

```
# 1. Configure your project (run once per repo)
wayfare:wayfare-init-repo

# 2. Converge the world into a plan. One round, thirteen stages:
#    config → inbox → architecture → harden → comments → compliance → local → deps → unshipped → design → reconcile → plan → goals
#    Reads the mailbox from sibling repos (bug reports become bug items),
#    reviews DESIGN.md (offers to converge it), audits dependency/container/
#    code hardening, flags comments and docs the code now contradicts,
#    checks the repo against the compliance register (generic
#    baseline + your fleet's overlay), runs the repo's own `wayfare: sync`
#    skills, gathers the bots' open PRs, refreshes the design snapshot,
#    reconciles source against design, plans every feature with you, then
#    proposes goals bottom-up over what was planned, and re-cuts the ones
#    already there. Writes only what you confirm; your ready-mark is the gate.
wayfare:wayfare-sync-plan

# 3. Take the next goal. It reads the goal's permissions aloud (mark-ready,
#    respond, auto-approve, merge, deploy, absorb), you authorize them
#    in-session, and it runs the goal right there: features built one after
#    another on one branch, one commit each, tested locally, and a single PR
#    opened at the end. Work it finds along the way is absorbed into the same
#    goal rather than spawning a new one. A run that stops hands back to you,
#    with a /goal line to paste if you would rather have it loop unattended.
wayfare:wayfare-start-goal
```

`wayfare:wayfare-advance-item ID` advances one thing on its own: a feature
through the build pipeline, a Dependabot PR to merged and deployed, or one goal
turn. `wayfare:wayfare-audit-compliance` runs the compliance audit alone, in one
repo or across the whole fleet from its root, and drafts backports where this
repo is ahead of the template. `wayfare:wayfare-recalibrate-config` tunes the
config every stage reads, and `wayfare:wayfare-drop-item ID` abandons a branch
and says so on the roadmap.

### The stages, runnable alone when you need to

`wayfare:wayfare-start-goal` runs the build pipeline for you, but each stage is
its own skill, so you can run a single step by hand:

```
/simplify                                   # tidy the dirty diff
wayfare:wayfare-push-pr                         # test (lint/typecheck/unit + UI smoke), commit + push, DRAFT PR
wayfare:wayfare-review-pr                       # parallel review agents + security pass, fixes, then mark-ready gate
wayfare:wayfare-respond-pr             # address Copilot/CodeRabbit/Greptile inline comments
wayfare:wayfare-ship-pr                         # @auto-approve, merge, reset to default branch
```

Each command reads your `HERO.md` config and adapts to your stack automatically.

`wayfare:wayfare-build-task` chains those stages end to end for a single small,
low-risk PR, without going through `wayfare:wayfare-sync-plan` first:

```
wayfare:wayfare-build-task PROJ-123   # start a new ticket or a READY item id
wayfare:wayfare-build-task            # resume the current goal to merged + reset branch
```

For a small change you can only describe,
`wayfare:wayfare-one-shot "DESCRIPTION"` is the front door: it drafts one task,
shows it, and on your yes marks it ready and runs `wayfare-build-task` on it. A
description that is several items, an anti-feature or a one-way door goes to
`wayfare:wayfare-grill-idea` instead.

It chains
`plan → implement → simplify → push → self-review → mark-ready → await-review → respond → ship`
end to end, with explicit user gates at plan-approval, mark-ready, and merge.
`plan` resolves what you asked for against your `.plans/` store and this repo's
tracker before it plans anything new, delegating to `wayfare:wayfare-grill-idea`
only when nothing matches, and it re-checks a matched item against the codebase
first, so already-finished work is reported rather than rebuilt. `simplify` runs
the `/simplify` skill on the dirty diff so the commit lands clean. `push` tests
first (lint/typecheck/unit tests plus a UI smoke check via Playwright MCP for
routes affected by the diff, skipped automatically on backend-only PRs), then
commits and opens the draft PR. `self-review` runs the review agents plus a
security pass. `mark-ready` is the explicit draft → ready gate; `await-review`
polls for your configured Code Review Agent (Copilot, CodeRabbit, Greptile, …)
before `respond` addresses its feedback.

At each step transition, wayfare-build-task prints a progress line so you always
know where you are:

```
[5/9] (✓) plan → (✓) implement → (✓) simplify → (✓) push → (▶) self-review → ( ) mark-ready → ( ) await-review → ( ) respond → ( ) ship

Now running: self-review
```

Each step maps to a skill you can run on its own when you don't want the whole
pipeline:

| # | Step | Skill to run standalone |
| -- | -- | -- |
| 1 | `plan` | `wayfare:wayfare-grill-idea` (only when nothing resolves from `.plans/` or the tracker) |
| 2 | `implement` | inline (executes the resolved work-item) |
| 3 | `simplify` | `/simplify` (external skill) |
| 4 | `push` | `wayfare:wayfare-push-pr` (tests, verification + UI smoke, then commits + pushes a draft PR) |
| 5 | `self-review` | `wayfare:wayfare-review-pr --no-mark-ready` |
| 6 | `mark-ready` | `wayfare:wayfare-review-pr`'s own Step 9 gate, or `gh pr ready` |
| 7 | `await-review` | inline poll (no separate skill) |
| 8 | `respond` | `wayfare:wayfare-respond-pr` |
| 9 | `ship` | `wayfare:wayfare-ship-pr` |

Re-running `wayfare:wayfare-build-task` mid-flow is safe: it inspects git + the
open PR for that branch and resumes from the inferred step deterministically, no
confirmation prompt. With no arguments, that resume behavior is the whole point.
On the default branch with work to preserve, wayfare-build-task auto-branches
off (no prompt) before resuming. It exits cleanly with a hand-off hint only when
there's nothing left to do (e.g., after the PR has merged) or when state can't
be inferred safely (e.g., a failed `git fetch`).

See [`PIPELINES.md`](./docs/PIPELINES.md) for the full DAG and stop conditions.

## Commands

### The front door

Source is the product as it is; Target is the product as it should be. Every
task is one leg of the route between them, and each leg is its own skill, so its
description is what an agent matches your request against. This table is the
map; there is no skill whose job is to hold it.

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-init-repo` | Investigate the repo, write `HERO.md`, create the plan object `.plans/PLAN.md`, migrating an older store on sight. Scaffolds first in an empty directory |
| `wayfare:wayfare-sync-plan` | One round of convergence (`config → inbox → architecture → harden → comments → compliance → local → deps → unshipped → design → reconcile → plan → goals`), writing every `.plans/` item and proposing goals bottom-up over what was planned. Writes only what you confirm |
| `wayfare:wayfare-start-goal` | Pick the next runnable goal, read its `## Permissions` aloud (mark-ready, respond, auto-approve, merge, deploy, absorb) for your in-session authorization, and run its first turn |
| `wayfare:wayfare-advance-item` | Advance one item as far as its gates allow: a ready task, a Dependabot PR to merged, or one goal turn. Never plans |
| `wayfare:wayfare-drop-item` | Abandon work on an unmerged branch and write `status: dropped`, so the roadmap stops claiming it |
| `wayfare:wayfare-recalibrate-config` | Report and tune every field the stages read, then stop |
| `wayfare:wayfare-audit-compliance` | Audit this repo, or the whole fleet from its root, against the compliance register, and draft the backports |

Features are SLC vertical slices (user stories, never layers) carrying subtasks,
a definition of done, a log, design feedback back to the design team, and
staleness flags against both ends.

Three skills are stages of `sync` and hidden from the slash menu
(`user-invocable: false`). You never call them, but they still own their
procedures:

| Stage | Skill | What it does |
| -- | -- | -- |
| `architecture` | `wayfare:wayfare-review-architecture` | Report where a single root `DESIGN.md` and the code have drifted: tech stack, boundaries, dependency rules, invariants, users, flows, interaction standards, append-only decisions. Writes nothing |
| `architecture` | `wayfare:wayfare-sync-architecture` | Bootstrap `DESIGN.md`, and apply the drift rows the review found. Never restates what the code says |
| `wayfare-audit-security` | `wayfare:wayfare-audit-security` | Audit read-only for hardening, dependency CVEs (Dependabot), container CVEs (Docker Scout, Trivy), code robustness, and emit execution-ready plans as `.plans/` security items |

### Setup

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-init-repo` | Investigate your repo, auto-detect stack, create `HERO.md` config |
| `wayfare:wayfare-check-preflight` | Catch missing tooling, stale `HERO.md`, env mismatches, and busy ports before a pipeline step does destructive work |
| `wayfare:wayfare-setup-dev` | Set up a developer's local environment (tools, auth, dependencies) |
| `wayfare:wayfare-init-repo` | Scaffold a new project (Python, full-stack, Node.js) |
| `wayfare:wayfare-create-skill` | Create a new Claude Code skill, subagent, rule, or hook |

### Development Cycle

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-push-pr` | Test (lint, typecheck, unit tests + smoke incl. UI via Playwright MCP), commit + push + draft PR + CI status, or `test` for a test-only run, or a target branch to merge into |

### Code Review

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-review-pr` | Review a PR with the review agents plus a security pass: your draft → applies fixes, asks before marking ready. Others' PR → inline comments only. |
| `wayfare:wayfare-humanize-prose` | Strip AI-writing patterns from prose ([docs/HUMANIZING.md](./docs/HUMANIZING.md), from Wikipedia's "Signs of AI writing"). The pipeline steps that emit prose read the doc directly; this skill runs it on any text you hand it |
| `wayfare:wayfare-respond-pr` | Fix PR review comments, resolve threads, optionally loop with external review agent |
| `wayfare:wayfare-ship-pr` | Trigger gated `@auto-approve`, wait for the verdict, merge if it passes, reset to the default branch, and wait for the merge commit's runs to report post-merge CI and deployment health |

### Pipelines (orchestrators)

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-one-shot` | Takes one small, clear change from a one-line description to a merged PR: drafts one task, shows it, and on your yes marks it ready and runs `wayfare-build-task` on it. Stops and routes to `wayfare-grill-idea` when the description is several items, touches an anti-feature, or is a one-way door. |
| `wayfare:wayfare-build-task` | Drives a small task end-to-end: plan → implement → simplify → push → self-review → mark-ready → await-review → respond → ship, with the tests run inside push. Detects a resume point on re-invocation; with no arguments, drives the current goal to merged + reset branch. Explicit user gates at each destructive step. |
| `wayfare:wayfare-init-repo` | Scaffolds a new project, then chains into wayfare-setup-dev → config → first-commit. |

### Operations

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-grill-idea` | Brainstorm + grill an idea one question at a time into shared understanding and dependency-aware work-items |
| `wayfare:wayfare-sync-fleet` | Create + converge `FLEET.md`, the local, unversioned map of the repos checked out beside each other (group, port). Scans the folder and proposes rows, writing only what you confirm. Every repo skill run from the fleet root fans out to the repos you pick (see `docs/FLEET-MD.md`) |
| `wayfare:wayfare-review-fleet` | Report drift between `FLEET.md` and the checkouts beside it: repos missing from the map, rows with no checkout, port collisions. Writes nothing |
| `wayfare:wayfare-write-handoff` | Distill the current conversation into one self-contained work-item for a downstream agent (optionally filed to the tracker, or to **another repo** with `--repo OWNER/NAME`) |

### Utilities

| Command | What it does |
| -- | -- |
| `wayfare:wayfare-recomponentize-ui` | Refactor a project's UI into atomic components, sourcing primitives from a design-system registry and codemodding off-token styling |
| `wayfare:wayfare-humanize-prose` | Strip the signs of AI-generated writing out of text |
| `wayfare:wayfare-write-handoff` | Distil the session into one self-contained work-item for an agent with no context from it |
| `wayfare:wayfare-audit-plugin` | Audit the wayfare plugin itself for quality and consistency |

## Updating vendored assets in a downstream repo

`scripts/install-design-system.sh` and `scripts/install-auto-approve.sh` copy
files *into* consuming repos (`.claude/rules/`, `.claude/hooks/`). Those copies
are vendored, not authored: fix bugs here, then re-vendor.

To refresh a consuming repo after a fix lands upstream:

```bash
"$PLUGIN_ROOT/scripts/install-design-system.sh" /path/to/repo
```

The installer **never overwrites a file that differs**. On drift it writes
`<file>.new` beside the original and exits 2, leaving you to reconcile:

```bash
diff .claude/hooks/check-design-tokens.sh{,.new}
```

**Read that diff in both directions before taking `.new`.** Drift is not always
upstream-is-newer. A consuming repo can carry a genuine improvement that was
never back-ported, and blindly accepting `.new` silently reverts it, for a
*check*, that reads as "still installed" while no longer catching what it used
to. Back-port the downstream improvement here first, then re-vendor, so both
sides converge on one version instead of alternating.

Exit 2 means "you have a decision to make", not "it failed".

**Auto-approve is the exception: always take `.new`, never merge it.** The two
files are not two versions of one thing. The existing file is the old inline
copy of the review *logic*; `.new` is a ~40-line caller into the shared
workflow. Reconciling them the way you would a design-system hook, keeping the
local improvement, is exactly how the fleet ended up with a private copy per
repo, several of them missing security fixes made here. A job holding both
`uses:` and `steps:` is also an invalid workflow file, and because the trigger
is `issue_comment` nothing surfaces that until someone tries to ship.

## `main` is the distribution mechanism

Consumers call
`ai-hero/wayfare-skills/.github/workflows/auto-approve.yaml@main`, so **merging
a change to `auto-approve.yaml` publishes it to every consuming repo the moment
it lands.** There is no release step, no tag to move, and no per-repo PR to
open.

Three consequences worth internalising:

- That file has a blast radius no other file here has. Review it accordingly.
- **`main`'s branch protection is the only gate.** Not a formality: approval
  required, stale approvals dismissed on push, and last-push approval required.
  Without that last pair, an approval collected on a benign diff survives a
  force-push and ships fleet-wide seconds later.
- Roll back by reverting on `main`. That is the whole procedure.

This replaced a moving `v1` tag. The tag needed a release workflow to move it,
an App to be allowed to move it past a ruleset, and a carve-out in the fleet's
pin rule, and its one distinctive feature, a manual lever to point the tag at an
arbitrary commit, turned out to be a way around the very branch protection the
design depended on. A branch ref cannot be aimed anywhere; there is nothing to
aim.

`assets/auto-approve/caller.yaml` is what gets installed into consumers. It is
not the logic and should stay small; `scripts/install-auto-approve.test.sh`
asserts it stays a caller and that its secrets and permissions still line up
with what `auto-approve.yaml` declares.

## HERO.md

Every skill reads `HERO.md` from your repo root. It declares your stack so
skills don't have to guess. **HERO.md is committed to the repo**. It's
team-shared, so every developer and every skill works from the same config.

When project config drifts (new deps, CI changes, switched task runner), skills
detect the staleness and remind you to run
`wayfare:wayfare-init-repo recalibrate` to refresh. There is no auto-pre-commit
hook for this. It was too slow. Run the refresh on demand.

**`recalibrate` is on ten skills, and is a skill of its own.** When a skill does
the wrong thing because its config is wrong, you fix it where you noticed:
`wayfare:wayfare-ship-pr recalibrate` asks about the eight fields
`wayfare-ship-pr` reads across Repository, CI/CD and Deployment, writes what you
confirm, commits, and stops. It does not then ship.
`wayfare:wayfare-init-repo recalibrate` is the whole-file pass.
`scripts/hero-fields.sh SKILL` prints the fields of any skill that carries the
verb, with their current values. See [docs/RECALIBRATE.md](docs/RECALIBRATE.md).

Note that `recalibrate` is not `sync`: `wayfare-sync-fleet` converges
`FLEET.md`, and `wayfare-sync-plan` converges the plan (and, through its
architecture stage, `DESIGN.md`). Those keep their own verbs, and none of them
is configuration.

**Connections are what the repo attaches to.** Its design (a claude.ai/design
project, a Figma file), the component registry it installs primitives from, the
template it should still resemble, the repo holding its architecture record, the
one holding its Terraform, and the tracker its work is filed in: six kinds, one
`### kind` block each under `## Connections`. Each may be absent, and absence is
written down: no block means nobody has looked, `type: none` means looked and
there is none, and a connection that is set but cannot be reached is neither: it
is broken, and says so. See [docs/CONNECTIONS.md](docs/CONNECTIONS.md).

Here's what a minimal config looks like:

```markdown
# HERO Configuration

## Connections

### issues
- type: linear
- at: PROJ
- reach: linear

## CI/CD
- platform: github-actions

## Code Quality
- pre-commit: true
- linters: [ruff]
- formatters: ruff format

## Projects

### api
- language: python
- framework: fastapi
- test-command: pytest
- dev-command: uvicorn main:app --reload
```

No `HERO.md`? Skills fall back to auto-detection. Run
`wayfare:wayfare-init-repo` to generate one. It investigates your repo and asks
smart questions to fill in what it can't detect.

<details>
<summary><strong>Full config reference</strong></summary>

`HERO.md` supports these sections:

- **Connections**: one `### kind` block per outward attachment: `design`,
  `design-system`, `reference`, `architecture`, `infrastructure`, `issues` (this
  is where the tracker lives, and where the old **Project Management** and
  **Design System** sections went). See
  [docs/CONNECTIONS.md](docs/CONNECTIONS.md)
- **Repository**: default branch, branch and commit conventions, merge method,
  task runner
- **Code Review Agent**: Greptile, CodeRabbit, Copilot (trigger, poll method,
  bot username)
- **CI/CD**: GitHub Actions, GitLab CI, Jenkins, CircleCI
- **Deployment**: Kubernetes, Vercel, ECS, Fly.io, container registries
- **Code Quality**: pre-commit, linters, formatters, type checkers
- **Developer Setup**: the tools a contributor needs, required and recommended
- **Coding Conventions**: the house style a review judges against
- **Projects**: per-subproject language, framework, test/dev commands, ports
- **Wayfare**: `source-repo`, and nothing else; every other wayfare input is a
  connection
- **Coding Agent**: written by `wayfare:wayfare-init-repo`, read by no skill
  today

Keys are **lowercase and exact**. The readers match `- key:` literally, so
`- Platform:` is not read as `platform`, and a field spelled that way is
silently unset rather than wrong-looking.

</details>

## Extending

Use `wayfare:wayfare-create-skill` to create new skills that plug into the same
workflow and read the same `HERO.md` config.

Skills are markdown files in the `skills/` directory. Each is a structured
prompt with instructions Claude follows when you invoke it. No code to compile,
no APIs to wire up.

## License

MIT, built by [AI Hero](https://aihero.studio).

## Compliance register

`scripts/audit.py` computes (check × repo) results live, from a register in two
halves: the generic **baseline** in `assets/compliance/`, shipped here, and your
fleet's private **overlay** (incident history and checks of its own) in the
register checkout FLEET.md names (`register: .fleet/`). No check names a repo:
which repos pass is the audit's output, computed per run, never a field in the
rule. Inside a fleet the family is FLEET.md's rows whose group is not `none`;
anywhere else, the current repo alone against the baseline.
`scripts/consistency.py` writes the fleet's human table into that checkout.
`wayfare-sync-plan` runs the audit as its `compliance` stage;
`wayfare-audit-compliance` runs it alone. See `assets/compliance/README.md`.
