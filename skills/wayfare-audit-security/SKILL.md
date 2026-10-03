---
name: wayfare-audit-security
# prettier-ignore
description: "Run by wayfare-sync-plan. Audit dependency CVEs, container CVEs with Scout and Trivy, and code hardening. Write executable security plans under .plans. Never edit source."
argument-hint: "[deps|docker|code|all]"
compatibility: "Requires the complete Wayfare plugin; some audit modes require GitHub CLI, Docker, Scout, Trivy, and network access."
user-invocable: false
---

# Harden: audit read-only, emit execution-ready hardening plans

Audit the codebase for security and hardening needs. Write plans that a
downstream executor can apply and test with **no context from this session**.
The executor can be a cheaper model, a fresh session, or
`wayfare:wayfare-build-task`.

**Run this stage only through `wayfare:wayfare-sync-plan`.** Wayfare invokes it
with `launched by wayfare` after updating the architecture map and before
judging the roadmap. Wayfare's planning postflight marks the resulting items
ready and groups them into a security goal. This stage accepts only the audit
scope. Use wayfare's `recalibrate` for the fields this stage reads. The calling
skill already selected one repo and checked for a fleet root. Thus, Step 0 does
not repeat that check.

Use the approach from [shadcn/improve](https://github.com/shadcn/improve): the
stronger model investigates, judges, and specifies the fix. Cheaper models
execute the plan. **The plan is the product.** This skill absorbed the former
`scan-vulns` skill. Parts A and B retain its Dependabot and Docker CVE scans.
Put apply and commit commands in the plan's execution recipe. Do not execute
them in this session's working tree.

## The Hard Rule

**This skill never edits source code, dependency files, Dockerfiles, or
workflows. Read-only, always.** Its only writes are plan items under the
git-ignored `.plans/` store. If you catch yourself about to run `npm install`,
edit a Dockerfile, or `git commit`, stop. That command belongs *inside* a plan
item's execution recipe.

## Arguments

- `$ARGUMENTS` - What to audit (default: `all`)
  - `deps` - Dependency CVEs only (Dependabot alerts + open Dependabot PRs)
  - `docker` - Container image CVEs only (Docker Scout + Trivy)
  - `code` - Code-level hardening audit only
  - `all` - Everything (what wayfare passes)

## Prerequisites

- `gh` CLI installed and authenticated (for Dependabot alerts)
- `docker` CLI installed for Docker Scout. If unavailable, report the `docker`
  part as skipped.
- `trivy` CLI installed as the second container scanner (Part B). If
  unavailable, use Scout only and report the missing scanner.

## Instructions

### Step 0: Load Hero Configuration and the .plans Store

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }

ROOT=$(hero_root)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"

# Same store wayfare-grill-idea and handoff emit into — one plate per repo,
# git-ignored via .git/info/exclude so no tracked file is ever dirtied.
hero_ready_items "$(hero_work_store)"
```

Read `HERO.md` for **Deployment** (registry for Docker Scout), **Projects**
(languages/frameworks → which dependency files and which code-audit angles
apply), and **Code Quality** (existing tooling so plans don't re-propose what a
linter already enforces). Read existing .plans items so new plans reference or
supersede rather than duplicate.

### Step 1: Detect Repository Context

```bash
gh repo view --json nameWithOwner,url
cat .github/dependabot.yml 2>/dev/null || echo "NO_DEPENDABOT_CONFIG"
find . -name "Dockerfile*" -type f 2>/dev/null | head -10
```

______________________________________________________________________

## Part A: Dependency CVE Audit (`deps` / `all`)

### A1: Get Dependabot Alerts

```bash
gh api repos/{owner}/{repo}/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {
    number, package: .dependency.package.name,
    severity: .security_advisory.severity,
    summary: .security_advisory.summary
  }' || echo "DEPENDABOT_ALERTS_UNAVAILABLE — check that alerts are enabled for this repo and the token has the security_events/repo scope"
```

A failed call (alerts disabled, insufficient token scope) prints nothing to
stdout, which is indistinguishable from "zero open alerts" unless the failure is
caught explicitly. If `DEPENDABOT_ALERTS_UNAVAILABLE` fires, the summary's
Dependabot line is exactly `Dependabot alerts: skipped (unavailable) — REASON`
rather than "0 alerts, clean." Wayfare reads that spelling back as an
`unverified` row.

Prioritize by severity: **critical > high > medium > low**.

### A2: List Open Dependabot PRs

```bash
gh pr list --author "app/dependabot" --state open --json number,title,headRefName,url
```

For each PR, view the diff and extract: package name, version change, file
affected. An open Dependabot PR is *evidence for the plan*. Note whether the
plan item should say "merge Dependabot PR #N" or "apply the update manually",
for example when the PR is stale or conflicts.

A bot PR that can merge as it stands is not harden's to re-implement: wayfare's
`deps` stage writes it as a `shape: dependency` task with `bot:`, and
`wayfare-advance-item ID` takes that one PR through review, tests,
`@auto-approve`, merge and the deployment check, without a copy of its diff.
Harden's batch (A4) exists for the alerts no PR covers, and for bumps that must
be tested together. If a batch supersedes a bot's PR, name that PR. Wayfare
leaves its item `accepted` instead of carrying both fixes.

### A3: Judge Each Alert

For each open alert, read enough of the codebase to judge (this is the
expensive-model work):

- Is the vulnerable code path actually reachable from this repo's usage?
- Is the fix a patch/minor bump (low risk) or a major bump (breaking-change
  risk, so flag it)?
- What is the correct update command for this ecosystem
  (`npm install PACKAGE@VERSION`, `uv lock && uv sync` after a `pyproject.toml`
  edit, a version pin bump in `.github/workflows/*.yml`)?
- What test/verification proves the update didn't break anything?

### A4: Specify the Batching Strategy in the Plan

The plan's execution recipe (Step 3) must have the executor batch **every**
dependency bump onto one fresh branch, tested together in one e2e run. Two
updates can pass separately and fail together. Specify a combined test in the
recipe. Do not emit one plan item per package:

1. Branch fresh off the default branch (never a long-lived security-fix branch
   reused across runs, because a fresh branch off today's default never has a
   stale base to reconcile against).
2. Edit every version bump directly into the manifest first (`package.json`,
   `pyproject.toml`, workflow pins) rather than one `npm install PKG@VER` per
   package, which regenerates the lockfile N times over.
3. Regenerate the lockfile **once**, covering all bumps together.
4. Run the test suite once against the combined change. A bump that breaks tests
   gets reverted individually and noted as skipped. It does not block the rest
   of the batch.
5. Make one commit for the whole batch. Use `wayfare:wayfare-push-pr` to open
   the PR.
6. Once `wayfare:wayfare-ship-pr` merges it, close every Dependabot PR listed in
   A2 directly with
   `gh pr close N --comment "Superseded by #MERGED_PR_NUMBER, merged in MERGED_SHA."`
   **Do not wait for GitHub to auto-close them.** This is not a timing issue,
   and it is not "nightly" or slow. GitHub only recognizes a fix as resolving a
   Dependabot PR when *that PR itself* is the one merged. A batched fix lands
   via a different commit by design (step 2), and Dependabot does not reliably
   detect that as equivalent. Two runs of this workflow left the original PRs
   open indefinitely after merge. GitHub community reports describe the same
   behavior (dependabot-core#3880). Proactively closing with a reference is the
   only reliable path.

______________________________________________________________________

## Part B: Container CVE Audit (`docker` / `all`)

### B1: Identify and Scan Images

If `docker` is unavailable, do not let Part B silently drop out of the audit.
Report `Docker/Scout: skipped (unavailable) — container CVE audit not performed`
in the Step 4 summary and stop here for this part, the same way an unavailable
`trivy` is reported below rather than left unmentioned:

```bash
command -v docker > /dev/null 2>&1 || echo "DOCKER_UNAVAILABLE"
```

Scan the base of the **final/runtime stage**. Builder stages never ship.

```bash
find . -name "Dockerfile*" -type f
docker scout cves IMAGE_NAME:TAG --only-fixed
```

**Scan with a second scanner too.** Scout and Trivy have different advisory
databases and each misses what the other catches. Report the union, not
whichever ran first:

```bash
trivy image --severity HIGH,CRITICAL --scanners vuln IMAGE_NAME:TAG
```

Example of the gap this closes: on one distroless Node image, Trivy reported
only the Debian `libssl3` CVEs and had no advisory for the Node runtime CVEs,
while Scout caught the Node CVEs plus `glibc`. Trivy alone would have concluded
OpenSSL was the whole story. The two scanners' advisory databases genuinely do
not overlap, and this is not a one-off fluke. If `trivy` is unavailable, report
`Trivy: skipped (unavailable)` and proceed on Scout alone rather than failing
the whole audit.

### B2: Get recommendations, and do not trust a clean one blindly

```bash
docker scout recommendations IMAGE_NAME:TAG
```

Read-only: record the recommended base-image bumps and system-package updates.

**`scout recommendations` is unreliable for non-Docker-Hub bases.** For
`gcr.io/distroless/*` (and other registries outside Hub's tag graph) it
auto-detects the base as `:latest` and reports a false all-clear:

```text
Base image is :latest
Refresh base image  -> This image version is up to date.
Change base image   -> There are no tag recommendations at this time.
```

It printed exactly that for an image carrying 14 HIGH (1 CRITICAL). **Never
treat "no tag recommendations" as "no fix exists"** for these bases. The tool is
blind, not reassuring. Enumerate the upgrade axes by hand (B2a) before the plan
concludes a CVE has no fix.

### B2a: Enumerate Every Upgrade Axis Before the Plan Says "No Fix Available"

Before a plan item claims "upstream has not published a fix" or "clears on the
next base bump", check **all** of these, because a fix on any one axis resolves
it today:

1. **Tag refresh**: repull, then compare against upstream `IMAGE:TAG` directly.
2. **Runtime major**: for example `nodejs22` to `nodejs24`.
3. **OS generation**: for example `-debian12` to `-debian13`. **Most often
   missed.** A newer OS generation frequently ships both a newer runtime and
   patched system libs, and Scout never suggests it for distroless.
4. **Variant**: `:nonroot`, `:debug`, or `-static`.

Verify by scanning the candidate directly rather than reasoning about it:

```bash
# Substitute the actual base; compare candidates side by side.
for base in nodejs24-debian12 nodejs24-debian13; do
  echo "== $base"
  docker scout cves --only-severity critical,high \
    "gcr.io/distroless/$base:nonroot" 2>&1 \
    | grep -E "vulnerabilities found|No vulnerable"
done
```

**Example of the miss this guards against:** a run bumped `nodejs22-debian12` ->
`nodejs24-debian12` and deferred 2 HIGH, reasoning that the newer Node runtime
was "not yet published to distroless" on a newer OS generation. It *was*
published, on `nodejs24-debian13`, which also cleared the `libssl3` and `glibc`
CVEs. Only axis 3 was skipped, and the finding was written off as unfixable. The
lesson generalizes: whichever axis gets skipped is the one that silently
produces a false "no fix available."

Record which axes were checked and what each returned directly in the plan item,
so the executor (or the next harden run) can refute a deferred CVE instead of
silently inheriting it.

### B2b: Note What the Plan's Verification Must Cover

A base bump can scan clean and still not boot. Flag this so the plan's
Verification section (Step 3) requires more than a rescan:

- Rescan with **both** scanners after the bump.
- Every binary `COPY`'d in from another stage: a base-OS bump changes the
  runtime linker/libc, and a static-binary assumption may not hold, so the
  recipe should run
  `docker run --rm --entrypoint BINARY_PATH IMAGE_NAME:TAG --version` for each.
- Bring up the project's smoke stack, wait for the healthcheck, and hit a route
  that exercises each process. A base-OS generation bump is otherwise low-risk
  when the payload does not link the base libs (a `CGO_ENABLED=0` Go binary, a
  static tini), but that assumption still needs proving per image.

A base-image plan item is not done when it merely "scans clean". Say so in the
plan's success criteria.

______________________________________________________________________

## Part C: Code-Level Hardening Audit (`code` / `all`)

Sweep the codebase for robustness gaps that scanning tools can't see. Audit
angles, applying the ones the stack makes relevant:

- **Boundary validation**: unvalidated input at API routes, CLI args, or file
  and env parsing
- **Silent failures**: swallowed exceptions, a bare `except` or empty `catch`,
  error paths that return defaults
- **Secrets hygiene**: credentials in code, config or logs, tokens in URLs,
  missing redaction
- **Authentication and authorization seams**: endpoints missing checks that
  sibling endpoints have
- **Unsafe defaults**: debug modes, permissive CORS, `verify=False`,
  world-readable artifacts
- **Missing timeouts and retries**: outbound calls that can hang forever, retry
  loops without backoff or caps
- **Injection surfaces**: string-built SQL, shell or HTML where a parameterized
  or escaped form exists

High signal only: every finding needs a concrete failure or exploit scenario and
a specific fix. Skip theoretical issues, DoS/rate-limiting noise, and anything
the repo's linters already enforce. For a large codebase, fan the angles out as
parallel read-only agents, never forks (see *A fan-out subagent is never a fork*
in `docs/PIPELINES.md`), and aggregate only once every angle has reported (*A
fan-out waits for every agent, then one writer commits once*).

______________________________________________________________________

## Step 2: Prioritize

Rank findings by `severity × blast radius ÷ effort`. Group dependency updates
into one batch per ecosystem. Group code findings into one hardening item per
subsystem or mechanism. Do not create one item per line. Emit at most the top
**10** items per run. Report findings excluded by that limit.

## Step 3: Emit Plan Items

Write each unit as a work item in `.plans/` using wayfare-grill-idea's format.
Continue id numbering from the highest existing id. Use filename `NNN-slug.md`.
Use `depends_on` when another plan must land first. Use `discovered_from` only
for provenance. Add the two sections below for the executor. Emit every plan
with `status: planning`.

```markdown
---
id: 12
type: task # every item is a wayfare item (docs/PLAN.md)
shape: defect # a CVE fix, a bump batch, an image bump; `structural` when the fix is a boundary or a trust decision rather than a patch
origin: harden
title: Update lodash + minimist for critical CVEs
status: planning # the user marks audit plans ready — audit output never goes straight to build
depends_on: []
one_way_door: false
success: "gh api dependabot/alerts shows 0 open critical/high; test suite green"
---

## Context

Which alerts/CVEs/findings this addresses and why they matter here (reachability, blast radius).

## Approach

The chosen fix and why (e.g., merge Dependabot PR #41 rather than manual bump — it is current and CI-green).

## Execution recipe

Exact commands and edits, in order, assuming zero context:
1. `npm install lodash@4.17.21`
2. ...
N. After `wayfare:wayfare-ship-pr` merges this batch: `gh pr close 41 --comment "Superseded by #MERGED_PR_NUMBER, merged in MERGED_SHA."` for each Dependabot PR from A2 (#41 here). Do not rely on GitHub auto-closing them — it doesn't reliably fire for a batched fix (see A4 step 6).

## Subtasks

- [ ] 1. The execution recipe above, one line per step, for wayfare-build-task to tick.

## Definition of Done

- [ ] The verification below, as observable statements.

## Verification

How the executor proves it worked (tests to run, rescan commands with both scanners, binary/health checks per B2b, endpoints to probe).

## Failure modes

What can break, and the rollback (e.g., major-bump risk: pin back and mark blocked).
```

A plan an executor cannot follow without asking questions is not done. Rewrite
it rather than handing it off vague.

### Self-Check: Confirm Nothing Tracked Was Touched

Before printing the Step 4 summary, verify the Hard Rule actually held. Do not
just assert it:

```bash
git diff --stat --exit-code || echo "VIOLATION: tracked files were modified — this run broke the read-only contract"
git status --porcelain | grep -v '^?? \.plans/' && echo "VIOLATION: unexpected changes outside .plans/"
```

If either check reports a violation, do not print "Source files modified: NONE".
Say what changed instead and treat it as a bug in this run, not a footnote.

## Step 4: Summary

```
Harden Audit Summary
====================
Dependabot:   5 alerts (2 critical, 2 high, 1 medium) → 2 plan items
  Original PRs to close after merge (do NOT wait on GitHub auto-close): #123, #124
Docker:       3 images scanned (Scout + Trivy), 10 fixable CVEs → 1 plan item
  # or, if docker is unavailable: "Docker/Scout: skipped (unavailable) — container CVE audit not performed"
  # or, if only trivy is missing: "Trivy: skipped (unavailable), Scout ran" — partial, and wayfare reads it as unverified
  # and when alerts could not be read: "Dependabot alerts: skipped (unavailable) — REASON"
  Deferred: CVE-XXXX-XXXXX — axes checked: tag refresh (same), runtime major
            (same), OS generation debian13 (same), variant (n/a) → no fix upstream
Code audit:   4 findings (2 important) → 2 plan items

Automated scanning: NONE (no dependabot config, no CI scan)
  -> this audit is a snapshot; pinned tags rot unwatched. Note in the plan
     whether to add a scheduled CI gate.

Plans emitted: .plans/items/012-*.md … 016-*.md (5 items, 0 cut)
Source files modified: NONE (read-only by contract)

```

Then return to wayfare. The summary above is what its `wayfare-audit-security`
stage reads back: every `skipped (unavailable)` and every `Deferred:` line
becomes an `unverified` row in the sync report, and the emitted items are
ready-marked in its planning postflight. Print no terminal next step of your
own, because the stage after this one is wayfare's to announce. (Run standalone,
the next step is `wayfare:wayfare-sync-plan`, which is also what ready-marks the
items.)

## Safety Notes

- Never edit source, dependency files, Dockerfiles, or workflows. The plan is
  the product.
- Flag major version updates as breaking-change risks in the plan. Default the
  recipe to the non-breaking path.
- Never assume Dependabot auto-closes its own PRs once a batched fix lands. It
  does not reliably fire for a fix that lands via a different commit than its
  own PR (see A4 step 6). The execution recipe must close each superseded
  Dependabot PR explicitly after merge, with a comment referencing the merged
  PR.
- Always specify rescanning with **both** Scout and Trivy in a Docker plan
  item's verification. Neither scanner alone is sufficient (see B1).
- `.plans/` is private and git-ignored. Never commit or push it.

### Before a plan says "no fix available"

That phrase is a claim about upstream, and it has been wrong. Earn it:

- Walk **every** axis in B2a (tag, runtime major, **OS generation**, variant)
  and scan the candidate. Do not infer availability from a version number.
- "`scout recommendations` had nothing" is **not** evidence, especially for
  `gcr.io/distroless/*`, where it is blind and reports a false all-clear.
- If a CVE is genuinely deferred, record **which axes were checked** and what
  each returned in the plan item, so the next audit can refute it instead of
  inheriting it.

### This audit is a snapshot, and pinned base tags rot between runs

This runs once per `wayfare-sync-plan`, and it is typically wired into neither
CI nor pre-commit. A pinned base tag accrues new CVEs with nothing watching: one
image went from "0 CRITICAL, 2 HIGH" at audit time to "1 CRITICAL, 14 HIGH"
shortly after, with no code change. A clean audit means clean **as of now**,
never clean going forward. When a repo has no automated scanning, say so in the
summary and note in the emitted plan(s) whether to add a scheduled CI gate
(`trivy image --exit-code 1 --severity HIGH,CRITICAL` on a `schedule:` trigger).
A push-only gate cannot catch rot, because rot happens without pushes.
