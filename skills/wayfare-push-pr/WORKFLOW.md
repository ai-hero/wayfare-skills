# Push: test, commit, push, open a draft PR, or merge

Test the outstanding work (verification plus smoke tests), commit it with a
smart conventional commit, branch off the default branch first if you're still
on it, push to the remote repository, and open a **draft PR by default**. Drafts
are the default because the author should run `wayfare:wayfare-review-pr` (which
calls all pr-review-toolkit agents plus a security pass, applies fixes, and asks
for confirmation) before promoting the PR to ready-for-review. After a
successful push, this skill also prints a brief CI status summary.

The test phase (Step 2) absorbed the former `test-changes` skill. Run
`wayfare:wayfare-push-pr test` for a test-only run that stops before any commit.

## Arguments

- `$ARGUMENTS` - Optional mode keyword or target branch. Only the **first**
  whitespace-separated token is matched against the keywords below, and it must
  match exactly rather than by prefix. A branch literally named `test`, `commit`
  or `ready` cannot be targeted this way, and needs a rename or a manual
  `git merge` instead:
  - `recalibrate` - Tune the `HERO.md` fields this skill reads, then stop (see
    below). Matched before every other form.
  - (none, default) - Test, commit if dirty, push, and create a **draft** PR
  - `test [MODIFIER...]` - Run only Step 2 (verification plus smoke tests) and
    stop. No commit, no push. Optional trailing tokens narrow the run: `verify`
    (static checks + unit tests only), `smoke` (skip verification), `backend`,
    `frontend [routes...]` (routes must start with `/`), `cli`, `mcp`,
    `branch BASE` (the whole branch against `origin/BASE` rather than the last
    commit: see 2b; a wayfare goal runs this once after its last task), or free
    text (a test description to focus on)
  - `commit` - Test only what the uncommitted change touches, commit it as one
    changeset (Step 3, smart commit), and stop. No push, no PR, no full suite,
    no smoke, no simplify. This is what a wayfare goal turn calls per task: the
    goal lands one commit per task on its own branch, then runs the full test
    phase and simplify once over the whole branch and opens a single PR at the
    end.
  - `ready` - Test, commit if dirty, push, and create a non-draft PR (ready for
    review immediately). Only use this when you have already self-reviewed, or
    for trivial changes
  - Any other first token - Treated as a target branch name (e.g., `main`,
    `develop`): test, commit if dirty, push, then merge into that branch (no
    PR). A branch literally named `recalibrate`, `test`, `commit`, or `ready`
    cannot be targeted this way and needs a rename or a manual `git merge`

## `recalibrate`

`wayfare:wayfare-push-pr recalibrate` tunes the config that drives this skill,
and stops. It does not go on to run the skill. You want to see which field was
wrong, not spend a whole run finding out.

Dispatch on it before parsing any other argument, in whichever step does that
parsing. When the first token of `$ARGUMENTS` is exactly `recalibrate`, print
`wayfare-push-pr: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md) (report, ask, write, commit)
using the table below as the report, and stop.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-push-pr
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

## Instructions

### Step 0: Load Hero Configuration

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }

ROOT=$(hero_root)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
hero_at_fleet_root && echo "FLEET_ROOT"
hero_check_staleness
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

> Each bash block below runs in a fresh shell, so re-source `hero-lib.sh` at the
> top of any block that calls a `hero_*` function.

Read `HERO.md` if it exists. This skill uses:

- **Repository** → default branch (for branching and PR base), branch
  convention, commit convention, task runner (test phase: prefer its targets
  over per-project raw commands when set)
- **Code Quality** → linters, formatters, type checkers (test phase + pre-commit
  steps)
- **Projects** → language, framework, install/test/dev commands, ports (test
  phase; skips auto-detection)
- **CI/CD** → platform name for PR description context and CI status reporting
- **The `issues` connection** → issue prefix for branch names,
  `Fixes:`/`Relates to:` trailers, and linking PRs to issues

If `HERO.md` is missing, suggest `wayfare:wayfare-init-repo` but proceed with
defaults (the test phase falls back to auto-detection). If the stale-HERO hint
fired, mention it once to the user but do not block.

### Step 1: Branch if on Default Branch

```bash
FIRST_ARG=$(printf '%s' "$ARGUMENTS" | awk '{print $1}')
```

Parse only the first whitespace-separated token. A target branch that happens to
start with `test` (e.g. `testing`, `test-staging`) must not be misread as the
`test` keyword.

**If `$FIRST_ARG` is exactly `recalibrate`, none of this step runs.** Go to the
`recalibrate` section above and stop there. The catch-all below treats any
unrecognized first token as a branch to merge into, so missing this dispatch
merges the work into a branch named `recalibrate`.

**If `$FIRST_ARG` is exactly `test`, skip this step.** A test-only run commits
nothing, so it may run on any branch, including the default.

**If `$FIRST_ARG` is exactly `commit`, skip this step too, but for the opposite
reason:** the caller has already put this checkout on the branch it wants the
commit on. A goal turn owns its branch, and branching here would move the commit
off it.

Never commit or push directly to the default branch.

```bash
# shellcheck source=/dev/null
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
BRANCH=$(git branch --show-current)
# _verbose: this value is branched off and pulled, so a silent fallback to the
# wrong branch would rebase the work onto an unrelated base.
DEFAULT_BRANCH=$(hero_default_branch_verbose)
echo "Current branch: $BRANCH (default: $DEFAULT_BRANCH)"
```

**If `$BRANCH` is not `$DEFAULT_BRANCH`, skip this step entirely** and proceed
to Step 2 on the current branch.

**If `$BRANCH` equals `$DEFAULT_BRANCH`:** pull it fresh before branching off
it. A stale local default branch means the new feature branch (and later, the
PR's base diff) silently misses recent commits.

```bash
if ! git pull --ff-only origin "$DEFAULT_BRANCH"; then
  echo "STOP: 'git pull --ff-only origin $DEFAULT_BRANCH' failed — local $DEFAULT_BRANCH may be divergent or dirty."
  echo "Resolve manually (check 'git status'; a diverged local $DEFAULT_BRANCH needs 'git fetch' + reconciling)."
  echo "Then re-run wayfare:wayfare-push-pr. Do not branch off a base that failed to update."
fi
```

**If the pull failed, stop here. Do not proceed to branch creation below.** Only
continue once it succeeds.

Then derive a feature-branch name from the diff and check out a new branch.
Uncommitted changes follow the checkout automatically, so do **not** stash.

Generate `BRANCH_NAME` by applying `hero_branch_policy`, the shared naming
rules, which wayfare-build-task's auto-branch step also uses so the two cannot
drift:

```bash
# shellcheck source=/dev/null
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
hero_branch_policy   # apply these rules to the diff to derive BRANCH_NAME
```

Deriving the name is a model task, not a shell one: read the diff, then apply
the policy. Unlike wayfare-build-task (which derives and proceeds),
wayfare-push-pr proposes and waits for confirmation.

Present the proposed name and let the user confirm or modify:

```
You are on '$BRANCH', which is the default branch. wayfare-push-pr never commits or pushes directly to the default branch.

Proposed branch: BRANCH_NAME

Options:
1. Use the proposed name
2. Provide your own branch name
3. Cancel
```

**Wait for confirmation**, then:

```bash
git checkout -b "$BRANCH_NAME"
git branch --show-current
git status --porcelain
```

### Step 2: Test the Changes (Verification + Smoke)

Verify the implementation works end to end before anything is committed: static
checks (lint, typecheck) and unit tests against changed files, then auto-detect
project type and run smoke tests against running services. Works for standalone
projects, monorepo subprojects, or full-stack apps with multiple layers.

Mode selection from `$ARGUMENTS` (after the leading `test`, when present):
`verify` runs only Step 2b; `smoke`, `backend`, `frontend [routes...]`, `cli`,
and `mcp` skip Step 2b and run only the matching part of Step 2c; anything else
(including no modifier) runs both. Free text that is not a mode keyword is a
test description to focus on.

**Failure semantics:** if a check fails with a quick, mechanical fix (lint,
typo, import order), apply the fix and re-run. If it fails in a way that needs
design judgment (a test asserting wrong behavior, integration breakage, flaky
CI), or the UI smoke flags a regression on a changed route, **STOP**, report the
failure, and hand back to the user. Never carry a known regression into a
commit.

#### 2a: Detect Project Structure

Use HERO.md's **Projects** section when present. Otherwise scan the current
directory (and immediate subdirectories) for indicators:

| Indicator | Type | Default Port |
| -- | -- | -- |
| `pyproject.toml` + `fastmcp`/`mcp` dep | MCP Server | 8000 |
| `pyproject.toml` + FastAPI/Flask import in `app/` | Backend API | 8000 |
| `pyproject.toml` + `[project.scripts]` or `__main__.py` | CLI/Library | - |
| `package.json` + `next.config.*` | Frontend (Next.js) | 3000 |
| `package.json` + `vite.config.*` | Frontend (Vite) | 5173 |
| `backend/` + `frontend/` subdirs | Full-stack | both |

```bash
ls pyproject.toml package.json next.config.* vite.config.* 2>/dev/null
ls backend/pyproject.toml frontend/package.json 2>/dev/null
```

Check the project's `CLAUDE.md` for specific run instructions. Report what was
detected; if nothing, ask the user. Install dependencies first when needed
(`uv sync`, `npm install`, one per project for full-stack).

#### 2b: Verify Implementation (Lint, Typecheck, Unit Tests)

Capture the list of changed files first (uncommitted, then last commit, fallback
to empty). Read the dedupe back into the array with `mapfile` so filenames
containing spaces, tabs, or globs survive intact. `($(...))` would word-split
and corrupt them:

```bash
mapfile -t CHANGED_FILES < <(git diff --name-only; git diff --name-only HEAD~1 HEAD 2>/dev/null)
# Newline-safe dedupe (preserves spaces in filenames).
mapfile -t CHANGED_FILES < <(printf "%s\n" "${CHANGED_FILES[@]}" | sort -u)
```

If `CHANGED_FILES` is empty, run the checks on the whole project (replace
`"${CHANGED_FILES[@]}"` with `.` or the project root).

**With the `branch BASE` modifier the set is the whole branch, and so are the
checks.** Build it from `git diff --name-only origin/BASE...HEAD`, never
`HEAD~1`: a goal branch carries one commit per task, and the last commit alone
leaves every earlier task unchecked. Run the task runner's full `test` target
(not only the mapped tests), `pre-commit run --all-files` in place of the scoped
dry-run below, and `pre-commit run --hook-stage pre-push --all-files`, which is
where security scans such as semgrep run and which a clean-tree push would
otherwise skip. 2c derives its smoke routes from this same set. This is the only
full run a goal makes before its push, so it must be the whole branch.

**In `commit` mode the set is the uncommitted change only, and the checks stay
on it.** Build it from `git diff --name-only HEAD` plus
`git ls-files --others --exclude-standard`, never from `HEAD~1`: on a goal
branch the last commit is the previous task's, and folding it in re-tests work
that was already checked. Run lint and typecheck on that set, and only the tests
that cover it (the test files that map to those sources, or the narrowest runner
target that exercises them), not the task runner's full `test` target. An empty
set is a STOP: there is nothing to commit. The full suite runs once over the
goal's branch after its last task (wayfare's *One turn*, step 5), which is where
two tasks that each passed alone are checked together.

If `HERO.md`'s **Repository** section sets `task-runner` (e.g. `just`, `make`),
prefer that tool's targets (`just lint`, `just test`, and so on) over the
per-project commands below when both exist. The task runner is what CI itself
calls, so it is the copy that cannot drift from CI's actual gate.

Use commands from `HERO.md` **Code Quality** and **Projects** sections when
available. Otherwise auto-detect:

- **Lint:** `uv run ruff check "${CHANGED_FILES[@]}"` (Python),
  `npx eslint "${CHANGED_FILES[@]}"` (TS/JS), `go vet ./...` (Go)
- **Typecheck:** `uv run mypy "${CHANGED_FILES[@]}"` (Python),
  `npx tsc --noEmit` (TS)
- **Unit tests:** the `test-command` from HERO.md per project; else
  `uv run pytest` / `npm test`. If a test file maps directly to a changed source
  file, prefer running just those tests for speed.

Then run a scoped pre-commit dry-run. This is the only place a
`wayfare-push-pr test` run (which stops before Step 3) ever exercises
pre-commit, so skipping it here would mean commit-hook regressions surface only
in a real commit:

```bash
if command -v pre-commit > /dev/null 2>&1; then
  pre-commit run --files "${CHANGED_FILES[@]}"
else
  echo "NO_PRECOMMIT"
fi
```

Report the verification result. `NO_PRECOMMIT` means pre-commit is not
installed, so report that case as `SKIPPED`:

```
Verification
============
Lint:      PASSED (0 issues)
Typecheck: PASSED (0 errors)
Unit tests: 42 passed, 0 failed
Pre-commit: PASSED (or SKIPPED if NO_PRECOMMIT)
```

If any check fails, apply the failure semantics above: mechanical fixes get
fixed and re-run, and judgment calls stop the skill before the smoke tests.

#### 2c: Run Smoke Tests by Type

Skip entirely in `verify` mode, and in `commit` mode: the goal smoke-tests once,
over the branch.

**CLI or library**: find entry points in `pyproject.toml` (`[project.scripts]`)
or `__main__.py` and run with `--help` or a basic invocation
(`uv run SCRIPT_NAME --help`); for libraries with no CLI,
`uv run python -c "import PACKAGE; print('OK')"`.

**Backend API**: start the server in the background (e.g.,
`uv run uvicorn app.main:app --reload --port 8000`), wait for ready, then smoke:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/openapi.json | head -50
```

**MCP server**: start the server, launch `npx @modelcontextprotocol/inspector`,
connect via Playwright at `http://localhost:6274` (Streamable HTTP → server URL
→ Connect), and exercise the available tools through the Inspector UI.

**Full-stack**: backend first (APIs must be ready), frontend second (it may
proxy to the backend), then smoke each layer.

**Frontend app**: the full recipe below. Detect whether this is a UI project,
confirm or start its dev server under `.test-output/`, derive up to 5 routes
from the diff (or use explicit `/`-routes passed after `frontend`), drive each
route with Playwright MCP, and apply the console-noise allowlist and failure
rules. If no UI project is detected, skip gracefully. That is expected on
backend-only diffs, not a failure.

##### Detect UI project

If Step 2a detected no frontend indicator at all (no `next.config.*`,
`vite.config.*`, and no HERO.md project with a UI-ish `framework`), skip this
section and print:

```
(–) frontend: no UI project detected — skipping frontend smoke.
This is expected on backend-only PRs.
```

Otherwise, confirm which project to drive using HERO.md's `## Projects` section
(already loaded in Step 0). UI detection there is **heuristic, not a closed
enum**. `wayfare-init-repo` does not constrain the `framework` value, so treat
the list below as a hint and fall back to asking the user when nothing matches.

**Known-UI frameworks (auto-detected as UI):**

```
next nextjs nuxt remix astro vite svelte sveltekit solid solid-start qwik
gatsby angular react cra create-react-app
```

**Known-non-UI frameworks (auto-detected as backend, skip silently):**

```
fastapi flask django starlette express nestjs hono fiber gin echo actix axum
rails sinatra laravel
```

**Decision:**

1. If any project's `framework` is in the known-UI set → that's the UI project.
   Continue.

2. If every project's `framework` is in the known-non-UI set OR there are no
   HERO.md projects with a `framework` field → fall back to Step 2a's file-based
   detection (`next.config.*`, `vite.config.*`). If that also found nothing,
   skip as above.

3. If a project's `framework` is in **neither** list (custom value, typo, or a
   UI framework not yet on the list), ask the user once:

   ```
   Project 'PROJECT_NAME' declares framework: FRAMEWORK_VALUE.
   Treat as a UI project for smoke testing?
     [y] Yes, drive the dev server with Playwright MCP
     [n] No, skip it (recommended for non-UI frameworks)
     [a] Add 'FRAMEWORK_VALUE' to the known-UI list in skills/wayfare-push-pr/SKILL.md and continue (asks once per session, not durable)
   ```

   Default to `n` if the user answers ambiguously. Silently smoking a backend
   project is worse than silently skipping a UI one.

If multiple UI projects exist, ask the user which one to smoke-test (or pass it
explicitly via the project's path). One per run keeps the dev-server lifecycle
simple.

Record `UI_PORT`, `UI_DEV_COMMAND`, `UI_PATH` from the matched project. Validate
that `UI_PATH` resolves under `$ROOT`:

```bash
if [ ! -d "$ROOT/$UI_PATH" ]; then
  echo "ERROR: UI project path '$ROOT/$UI_PATH' does not exist."
  echo "       Check the 'path:' field for this project in HERO.md, or run"
  echo "       wayfare:wayfare-init-repo recalibrate to re-detect."
  exit 1
fi
```

##### Confirm or start the dev server

Check whether the dev server is already up on `UI_PORT`:

```bash
DEV_URL="http://localhost:$UI_PORT"
if curl -sf -o /dev/null -m 3 "$DEV_URL"; then
  echo "Dev server already running at $DEV_URL — using it."
  STARTED_BY_US=false
else
  echo "Dev server is not responding at $DEV_URL."
  STARTED_BY_US=true
fi
```

If `STARTED_BY_US=true`, ask the user before starting it:

```
The dev server is not running. Start it now?
  [y] Start `UI_DEV_COMMAND` in the background — leaves it running after this skill finishes.
  [n] Cancel — start it yourself, then re-run this skill.
```

On `y`, start the dev server with output captured to a log under `.test-output/`
and PID tracked:

```bash
# Centralize all frontend-smoke artifacts under .test-output/ so they live
# next to the screenshots and are covered by the same exclude entry. The
# `mkdir -p` and exclude-append also happen below before the first
# screenshot — doing them here too is cheap and lets the dev-server log
# exist before the drive phase ever runs.
mkdir -p "$ROOT/.test-output"
# hero_exclude_add writes to .git/info/exclude (repo-local, untracked) rather
# than .gitignore (tracked) — modifying a tracked file would leave the working
# tree dirty and contradict the test phase's "never modifies tracked source
# files" contract. It resolves the path via git, so worktrees / bare repos /
# non-default gitdirs all work.
hero_exclude_add .test-output/
DEV_LOG="$ROOT/.test-output/dev-server.log"
# Truncate any stale log from a previous run so this run's diagnostics
# only reflect the current invocation.
: > "$DEV_LOG"

# Run UI_DEV_COMMAND without `eval`: bash field-splitting on the unquoted
# variable handles a command with plain arguments (e.g. `pnpm -C web dev
# --port 3001`). It does NOT interpret shell operators (`&&`, `|`, `;`) —
# those would be passed as literal argv. A project needing a compound command
# should wrap it in a script and point dev-command at that.
# shellcheck disable=SC2086  # intentional word-splitting on UI_DEV_COMMAND
( cd "$ROOT/$UI_PATH" && $UI_DEV_COMMAND > "$DEV_LOG" 2>&1 ) &
DEV_PID=$!
echo "Started dev server (pid $DEV_PID, log $DEV_LOG)."

# Wait up to 60s for the server to come up. Bail early if the spawned
# process has already died (typo'd UI_DEV_COMMAND, missing dep, port in use).
for i in $(seq 1 30); do
  if ! kill -0 "$DEV_PID" 2>/dev/null; then
    echo "Dev server process died before responding. Last 30 log lines:"
    tail -30 "$DEV_LOG"
    exit 1
  fi
  if curl -sf -o /dev/null -m 2 "$DEV_URL"; then
    echo "Dev server is up after ${i}x2s."
    break
  fi
  sleep 2
done

if ! curl -sf -o /dev/null -m 2 "$DEV_URL"; then
  # Server did not respond on $DEV_URL. Probe alternates: dev servers often
  # bind 0.0.0.0 (devcontainers / CI runners) or 127.0.0.1 only, and IPv6
  # localhost can resolve to an unreachable address. Surface that case
  # rather than reporting "did not come up" when it actually did.
  # 0.0.0.0 is a *bind* address, not a routable connect target — only
  # probe addresses that are actually reachable as clients.
  ALT_URL=""
  for HOST in 127.0.0.1 ::1; do
    # Wrap IPv6 literal in brackets for curl's URL syntax.
    case "$HOST" in
      ::*) PROBE_URL="http://[$HOST]:$UI_PORT" ;;
      *)   PROBE_URL="http://$HOST:$UI_PORT" ;;
    esac
    if curl -sf -o /dev/null -m 2 "$PROBE_URL"; then
      ALT_URL="$PROBE_URL"
      break
    fi
  done
  # Also grep the log for the framework's announced URL (Next, Vite, etc.
  # all print "Local:" / "ready on" / "Listening on" with a URL).
  LOG_URL=$(grep -Eom1 'https?://[a-zA-Z0-9.:-]+' "$DEV_LOG" 2>/dev/null || true)

  if [ -n "$ALT_URL" ] || [ -n "$LOG_URL" ]; then
    echo "Dev server is up but not on $DEV_URL."
    [ -n "$ALT_URL" ] && echo "  Reachable at: $ALT_URL"
    [ -n "$LOG_URL" ] && echo "  Server reports: $LOG_URL"
    echo "  Update HERO.md 'port:' (or 'host:' if your config supports it)"
    echo "  for project '$PROJECT_NAME' and re-run."
  else
    echo "Dev server did not come up within 60s. Last 30 log lines:"
    tail -30 "$DEV_LOG"
  fi

  echo ""
  echo "Cleaning up the process we started:"
  kill "$DEV_PID" 2>/dev/null || true
  # Verify the kill worked — frameworks like `next dev` spawn worker
  # processes; killing the parent can leave the port bound. Re-curl after
  # a beat; if it still answers, surface the orphan so the user can clean up.
  sleep 1
  if curl -sf -o /dev/null -m 2 "$DEV_URL"; then
    echo "WARN: stale process still bound to :$UI_PORT after kill."
    echo "      Investigate: lsof -i :$UI_PORT"
  fi
  exit 1
fi
```

Note the log path so the user can `tail -f` it in another terminal if a
smoke-test failure needs deeper diagnosis. Do NOT auto-tail it into this
conversation, because it floods the context.

##### Identify routes

If `/`-routes were passed after `frontend` (e.g.,
`wayfare:wayfare-push-pr test frontend /dashboard /settings/api`), use those
verbatim.

Otherwise, derive from the diff. For each changed file under the UI project, map
to its owning route(s):

- Next.js App Router: `app/foo/bar/page.tsx` → `/foo/bar`;
  `app/(group)/x/page.tsx` → `/x` (route groups are URL-invisible); route
  handlers (`route.ts`) excluded.
- Next.js dynamic / catch-all segments: `app/posts/[slug]/page.tsx`,
  `app/[...slug]/page.tsx`, `app/[[...slug]]/page.tsx`. There is no canonical
  URL for these. Ask the user once for a sample value (e.g., a real `slug` from
  the dev DB), or skip the route with `(–)` and a note. Do not invent values
  like `/posts/example`, which usually 404.
- Next.js parallel and intercepted routes: `app/@modal/...`, `app/(.)photo/...`,
  `app/(..)settings/...`: exclude these entirely. They have no free-standing
  URL; navigating to a literal `@modal` returns 404 and pollutes the smoke
  result.
- Next.js Pages Router: `pages/foo/bar.tsx` → `/foo/bar`; `pages/index.tsx` →
  `/`; `pages/[slug].tsx` → ask for a sample value or skip.
- Vite + React Router / SvelteKit / Remix / etc.: walk the routing config
  (`routes.tsx`, `+page.svelte`, `routes/`) and emit the canonical paths. Apply
  the same dynamic-segment rule (ask for a sample or skip).
- Shared components (`components/Button.tsx`, `lib/`, `hooks/`): no direct
  route. Pick the **landing page** (`/`) plus the **most-changed page** as a
  fallback so we exercise the rendering path at all.

If the diff touches no UI files at all (despite the project being a UI project,
for example when the change was server actions only), exercise just the landing
page `/` so we still detect a hard regression like a build break.

Cap the route list at **5 routes** for a smoke test. More than that and the user
should run a real E2E suite.

Print the route list before driving so the user can object:

```
Smoke routes (N):
  - /
  - /dashboard
  - /settings/api
```

##### Drive the browser

Mark `BROWSER_OPENED=true` after the first successful `browser_navigate` so the
cleanup step knows whether to call `browser_close`.

For each route in order, run the same recipe via Playwright MCP:

1. `mcp__playwright__browser_navigate` to `$DEV_URL$ROUTE`. Set `expectedStatus`
   to 200-399 if the tool supports it; otherwise check status from a follow-up
   `browser_network_requests` call.

2. `mcp__playwright__browser_wait_for` until the page is interactive (look for a
   stable selector: `body`, the route's `<h1>`, or a known landmark from the
   snapshot).

3. `mcp__playwright__browser_snapshot`: capture the accessibility tree as the
   canonical "did it render" check.

4. `mcp__playwright__browser_console_messages`: read messages emitted since the
   last navigate.

5. `mcp__playwright__browser_take_screenshot`: save a PNG named
   `smoke-ROUTE_SLUG.png` under `$ROOT/.test-output/playwright-mcp/`. **Before
   the first screenshot of this run**, do the three-step setup once:

   ```bash
   # shellcheck source=/dev/null
   WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
   . "$WAYFARE_ROOT/scripts/hero-lib.sh"
   mkdir -p "$ROOT/.test-output/playwright-mcp"
   # Idempotent, and safe whether or not the dev-server block above already ran.
   hero_exclude_add .test-output/
   # Clear stale artifacts from previous runs so this report only reflects
   # the current diff. Scope the delete to this skill's artifacts so
   # co-located Playwright traces / videos from unrelated sessions are not
   # touched.
   rm -f "$ROOT/.test-output/playwright-mcp"/smoke-*.png
   ```

   `$ROOT/.test-output/` is the canonical local-only test-artifacts directory
   for wayfare. All disposable outputs from any wayfare skill (Playwright
   screenshots, traces, videos, network logs, dev-server logs, coverage reports)
   land somewhere under it so the repo root stays clean and a single exclude
   entry covers them all.

For routes that involve a form change (detected by reading the diff: `<form>` /
`useForm` / `onSubmit` added or modified), additionally:

1. `mcp__playwright__browser_fill_form` with placeholder-but-plausible values
   for the visible inputs (keep it under 5 inputs, and refuse if the form is
   huge; that's a real E2E test, not a smoke test).
2. Click the submit control, `browser_wait_for` the success state,
   `browser_console_messages` again.

###### Console noise allowlist

Dev-mode frameworks emit benign warnings on every page load. The allowlist below
is **the only set of console messages this skill ignores**; everything else
(including any console message of `type=error`) is treated as a failure. Do not
invent additional patterns at runtime.

```
Next.js / React (development mode):
  - "[Fast Refresh]"
  - "[HMR]"
  - "Download the React DevTools"
  - "Warning: ReactDOM.render is no longer supported"
  - any message whose body starts with "Warning:" AND contains "in development"

Vite:
  - "[vite] connecting…"
  - "[vite] connected."
  - "[vite] hot updated:"

SvelteKit / Svelte:
  - "[vite] connecting…"  (same as Vite — Kit uses Vite under the hood)

General:
  - any message whose URL is a `chrome-extension://` source (browser extensions
    emitting in the page context — not the app's fault).
```

If a future framework has its own benign-warnings set, the user must update this
list explicitly via a follow-up edit to this skill. The frontend smoke does not
silently expand its filter set.

###### Failure rules

A route fails the smoke if any of:

- The HTTP status of the document request is 4xx or 5xx.

- An entry in `browser_console_messages` has `type=error` AND its body does NOT
  match an allowlist entry from the section above. Match the allowlist
  conservatively: if you are not sure whether a message is benign, treat it as a
  failure and let the user decide.

- An uncaught exception appears in the dev server log (covers a broad set of
  common failures and ignores nothing). This check only applies when **this**
  skill started the dev server. `$DEV_LOG` is only set on that path. When the
  server was already running there is no log to grep, so gate on `$DEV_LOG`
  being set and the file existing:

  ```bash
  if [ -n "$DEV_LOG" ] && [ -f "$DEV_LOG" ]; then
    grep -Ei '\b(Error|Warning|Exception|Traceback|Unhandled[A-Z][a-zA-Z]*Rejection):' "$DEV_LOG"
    grep -E '\bat [A-Za-z_$][A-Za-z0-9_$.]* \(.*:[0-9]+:[0-9]+\)' "$DEV_LOG"   # JS stack frames
    grep -E '\bModule(Not)?Found|SyntaxError|RangeError|TypeError|ReferenceError' "$DEV_LOG"
  fi
  ```

- `browser_wait_for` times out, so the page never became interactive.

- A form submission's `wait_for` fails, so the success state never rendered.

On any failure: stop driving further routes, surface the failing route + the
console message + the screenshot path, and treat the run as failed. Do **not**
auto-retry; the model is a poor judge of "transient vs real" for UI bugs.

#### 2d: Test Cleanup and Report

```bash
# Close the browser session — only if the frontend drive step actually
# opened one. Skipping this when no UI project was found (or the server
# failed to come up) avoids noisy "no session to close" errors from the
# MCP server.
if [ "${BROWSER_OPENED:-false}" = "true" ]; then
  mcp__playwright__browser_close
fi

# If we started the frontend dev server ourselves, leave it running by
# default — most users want it for follow-up work. Offer to stop only if
# the user explicitly asked for cleanup.
if [ "${STARTED_BY_US:-false}" = "true" ]; then
  echo ""
  echo "Dev server is still running (pid $DEV_PID, log $DEV_LOG)."
  echo "Stop it now? [y/N]"
fi
```

If the user says yes, `kill "$DEV_PID"` and remove the log. Otherwise leave both
in place. Stop any other background servers (backend, MCP inspector) started for
this run via `TaskStop`, then report:

```
Test Results
=================
Project: {name}
Mode: all (verification + smoke)

Verification:
  Lint:      PASSED (0 issues)
  Typecheck: PASSED (0 errors)
  Unit tests: 42 passed, 0 failed

Smoke Tests:
  Backend (FastAPI on :8000):
    GET /health -> 200 OK
  Frontend (Next.js on :3000):
    Routes:      N tested (/, /dashboard, /settings/api)
    Console:     X errors, Y warnings (filtered framework noise)
    Screenshots: $ROOT/.test-output/playwright-mcp/*.png
    Result:      OK | FAILED at ROUTE — REASON
```

**If `$FIRST_ARG` (from Step 1) is exactly `test`, STOP here.** The test-only
run is complete. Suggest `/simplify` and a plain `wayfare:wayfare-push-pr` as
next steps. Otherwise continue to Step 3.

### Step 3: Commit Dirty Changes (Smart Commit)

```bash
git status --porcelain
```

**If the tree is clean (no output):** the work is already committed, so skip
straight to Step 4.

**If the tree is dirty**, run the following before pushing.

#### 3a: Run Pre-commit (if available)

In `commit` mode, skip this step: 2b's scoped dry-run already covered the
changed files, and the hooks run on them again at `git commit`.

```bash
if command -v pre-commit > /dev/null 2>&1; then
  pre-commit run --all-files
else
  echo "NO_PRECOMMIT"
fi
```

If pre-commit is installed and checks fail: report errors, offer to auto-fix, do
not proceed until passing. If not installed, skip and continue.

#### 3b: Analyze Changes

```bash
git status --porcelain
git diff
git diff --cached
git diff --stat
```

For each changed file: read the diff, understand its purpose, assess quality.

#### 3c: Simplify Code

In `commit` mode, skip `simplify` and go to the humanizer pass below: the goal
simplifies once, over the whole branch diff.

Invoke the `simplify` skill through the active client's skill mechanism.
`simplify` is **not** part of this plugin. It ships separately (see the
user-invocable skills list in the current session). It reviews the current diff
for reuse, quality, and efficiency and fixes any issues found before the commit
lands. Step 3g below handles the post-fix pre-push dry-run.

Launch its review agents as fresh subagents scoped to the diff and their angle,
never forks: see *A fan-out subagent is never a fork* in `docs/PIPELINES.md`.
They report findings only. Apply nothing until every one of them has reported,
then apply the fixes in one pass and make one commit: see *A fan-out waits for
every agent, then one writer commits once*.

If the `simplify` skill is unavailable in this environment, report
`NO_SIMPLIFY_SKILL: falling back to inline checklist` and apply this check
before continuing:

- [ ] No premature abstractions
- [ ] No over-engineering
- [ ] Could this be simpler?

Then the **humanizer pass**: [docs/HUMANIZING.md](../../docs/HUMANIZING.md) over
the prose this diff adds or rewrites: code comments, docstrings,
README/docs/CHANGELOG text, error and log messages a person reads. The same pass
covers every prose this skill emits: the commit body (3f) and the PR body (A3),
drafted first, humanized once.

#### 3d: Ruthless Code Review

Additional checks beyond simplify:

**Naming Consistency**

- Same concepts use same names throughout
- Imports match exports

**Code Quality**

Debug code and TODOs without an issue are a script's job, not a read. In
`commit` mode it reads the uncommitted change against `HEAD`; otherwise, the
whole branch against its merge base with the default branch. Both read the
working tree and untracked files, since this runs before the commit:

```bash
# shellcheck source=/dev/null
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
FIRST_ARG=$(printf '%s' "$ARGUMENTS" | awk '{print $1}')
if [ "$FIRST_ARG" = "commit" ]; then
  python3 "$WAYFARE_ROOT/scripts/diff_leftovers.py"
else
  DEFAULT_BRANCH=$(hero_default_branch)
  python3 "$WAYFARE_ROOT/scripts/diff_leftovers.py" --base "origin/$DEFAULT_BRANCH"
fi
```

Each hit is fixed before the commit, or marked `leftovers: ok` on the same line
with a reason when the line means it (a test fixture, a pattern list). Fixing
means removing the debug line or giving the TODO an issue reference (`#123`,
`ABC-123`, or a URL). Exit 2 is git failing to answer (an unknown base, say):
fetch the base and re-run, never read it as clean. Then read for what a script
cannot judge:

- [ ] No commented-out code
- [ ] No obvious security issues

**Completeness**

- [ ] All renames updated everywhere
- [ ] Imports correct
- [ ] Tests updated if behavior changed

**Report:**

```
Code Review Summary
===================
Files Changed: N
Lines Added: A, Removed: D

Issues Found:
- CRITICAL: FILE:LINE — description
- WARNING: FILE:LINE — description

Suggestions:
- IMPROVEMENT
```

Fix any CRITICAL or WARNING issues found. Re-run pre-commit after fixes (if
available).

#### 3e: Group into Changesets

Group logically related changes:

- Same feature/component together
- Same type of change together
- Dependency updates separate
- Documentation separate

#### 3f: Commit Each Changeset

End the message with the attribution trailer the active client or repository
specifies. If neither specifies one, add no generated co-author trailer. Never
invent an agent or model identity.

```bash
git add file1 file2 ...
git diff --cached --stat
MSG=$(cat <<'EOF'
{type}({scope}): {description}

{body if needed}
EOF
)
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind commit --body-file - <<<"$MSG" || exit 1
git commit -m "$MSG"
```

**Types:** feat, fix, refactor, docs, style, test, chore, perf

A commit body, when written, is humanized (3c) before the commit.

**If issue ID in branch name:** Add `Fixes: PROJ-123` or `Relates to: PROJ-123`.

#### 3g: Post-Commit Pre-Push Dry-Run

In `commit` mode, skip this step: nothing is pushed, and the goal runs the
pre-push stage once over the whole branch (`test branch BASE`, 2b). Do not count
on the push to run it: a goal pushes a clean tree, which skips Step 3 entirely.

Dry-run any pre-push hooks now so failures surface before the actual push
(Workflow A1 / B1):

```bash
if command -v pre-commit > /dev/null 2>&1; then
  pre-commit run --hook-stage pre-push --all-files
else
  echo "NO_PRECOMMIT"
fi
```

#### 3h: Commit Summary

```
Commit Summary
======================
Branch: {branch-name}
Commits Created: N

1. {type}({scope}): {description}
   Files: file1, file2 (+X -Y)

Pre-commit: PASSED (or SKIPPED)
```

**If `$FIRST_ARG` is exactly `commit`, STOP here.** Print the commit SHA as the
deliverable and do not continue. The caller (a wayfare goal turn, through
wayfare-build-task's commit-only mode) pushes and opens the PR once, after every
feature is in and the branch has passed locally.

Proceed to Step 4.

### Step 4: Determine Workflow

| Argument | Workflow |
| -- | -- |
| (none, default) | Push + **Draft** PR |
| `test` | Already stopped after Step 2 (test-only) |
| `commit` | Stop after Step 3: the commit is the deliverable. Report the SHA and stop; do not reach Workflow A or B. |
| `ready` | Push + non-draft PR |
| `main`/`master` | Push + Merge to main |
| Other branch | Push + Merge to target |

______________________________________________________________________

## Workflow A: Push and Create PR (No Target)

### A1: Push to Remote

```bash
git push -u origin $(git branch --show-current)
```

**Handle push failures:**

| Error | Action |
| -- | -- |
| `rejected` (non-fast-forward) | Suggest `git pull --rebase` |
| `permission denied` | Suggest `gh auth login` |
| `remote not found` | Check remote configuration |

### A2: Check for Existing PR

```bash
gh pr list --head $(git branch --show-current) --json number,url,title,state
```

**If PR exists:** Report it and skip to A5 (CI status).

### A3: Create Pull Request

```bash
# shellcheck source=/dev/null
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
ROOT=$(hero_root)
# The _verbose variant reports whether the value came from HERO.md or the
# fallback, so a missing/mistyped default-branch key can't silently open the PR
# against the wrong base (e.g. `main` on a repo whose real default is `master`).
DEFAULT_BRANCH=$(hero_default_branch_verbose)
# Refresh the remote-tracking ref before diffing against it — Step 1 only
# fetches when this branch came from the default branch; a branch that
# existed before this run may never have fetched at all this session.
FETCH_FOR_DIFF_OK=true
git fetch origin "$DEFAULT_BRANCH" || FETCH_FOR_DIFF_OK=false
git log origin/$DEFAULT_BRANCH..HEAD --pretty=format:"%s%n%b" --reverse
git diff origin/$DEFAULT_BRANCH..HEAD --stat
git diff origin/$DEFAULT_BRANCH..HEAD --name-only
```

If `$FETCH_FOR_DIFF_OK` is `false`: this does not block the PR (GitHub computes
the actual base and diff server-side regardless of local staleness), but the
title and changeset list generated below are built from this possibly-stale
local log. Prepend a note to the generated PR body:
`Note: generated against a possibly-stale local view of $DEFAULT_BRANCH (fetch failed); verify the changeset list against GitHub's own diff.`

Determine the draft flag (drafts are the default). Parse the first
whitespace-separated token of `$ARGUMENTS` so trailing whitespace or extra
arguments don't silently fall through:

```bash
# Draft is the default; pass `ready` to opt into a non-draft PR
FIRST_ARG=$(printf '%s' "$ARGUMENTS" | awk '{print $1}')
DRAFT_FLAG="--draft"
if [ "$FIRST_ARG" = "ready" ]; then
  DRAFT_FLAG=""
fi
```

**Generate the PR title from commit history** (use the most descriptive commit,
or summarize if multiple):

```bash
# Default to first commit subject; override with a better summary if needed
PR_TITLE="$(git log origin/$DEFAULT_BRANCH..HEAD --pretty=%s | head -1)"
```

**Generate PR content by listing each commit as a changeset with its files and
description.** Keep the title unbranded (no "Hero"/"wayfare"). Humanize the
drafted body (3c) before creating. End the body with exactly one attribution
line, `_Generated using wayfare._`:

```bash
BODY=$(cat <<'EOF'
## Summary
[1-3 sentence overview of what this PR accomplishes]

## Changesets

### 1. `commit-type(scope): commit-message`
**Files:** `file1.ts`, `file2.ts` (+A -D)
Brief description of what this commit does and why

### 2. `commit-type(scope): commit-message`
**Files:** `file3.py` (+A -D)
Brief description of what this commit does and why

[...repeat for each commit on the branch]

## Test Plan
- [ ] [Test step 1]
- [ ] [Test step 2]

## Related Issues
[Link issues if mentioned in commits]

_Generated using wayfare._
EOF
)
# The exact text that gets posted. A finding means fix the text and
# re-run, never post around it.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind pr --title "$PR_TITLE" --body-file - <<<"$BODY" || exit 1
gh pr create $DRAFT_FLAG --base "$DEFAULT_BRANCH" --title "$PR_TITLE" --body "$BODY"
```

### A4: Report Success

```
Push Summary
=================
Branch: {branch-name}
Action: Push + Create Draft PR

Commits pushed: N
Draft PR created: #{number}
URL: {pr-url}

Next step: `wayfare:wayfare-review-pr` performs self-review, independent quality
and security passes, fixes, and the mark-ready gate.
```

If the PR was created with `ready` (non-draft), report `PR created` instead of
`Draft PR created`, skip the self-review hint, and pick exactly one next step
instead:

- **This PR touched dependency files** (`package.json`, `pyproject.toml`,
  lockfiles, `.github/workflows/*.yml` version pins, or `Dockerfile*`, since
  harden covers Docker image hardening too):
  `Next step: wayfare:wayfare-sync-plan, whose harden stage audits the new dependency surface and writes any fix as a security item`
  (print only).
- **Otherwise**:
  `Next step: wayfare:wayfare-ship-pr, which once green posts @auto-approve, merges, verifies the deploy, and resets`
  (offer to auto-run).

### A5: Report CI Status

Give a brief, non-blocking CI summary after the push. Skip this step entirely if
`gh` is unavailable.

```bash
BRANCH=$(git branch --show-current)
# Distinguish three outcomes explicitly so an errored gh call is never mistaken
# for "no runs yet" (which would otherwise read as a clean/absent CI state):
if ! gh repo view --json nameWithOwner -q .nameWithOwner >/dev/null 2>&1; then
  echo "CI status unavailable (gh not authenticated or no remote) — skipping CI block."
else
  RUNS_JSON=$(gh run list --branch "$BRANCH" --limit 5 \
    --json databaseId,name,status,conclusion,headBranch,createdAt,url 2>&1)
  if [ $? -ne 0 ]; then
    echo "CI status unavailable (gh run list failed) — skipping CI block: $RUNS_JSON"
  elif [ "$(printf '%s' "$RUNS_JSON" | tr -d '[:space:]')" = "[]" ]; then
    echo "Overall: NO RUNS YET"
  else
    printf '%s\n' "$RUNS_JSON"   # classify PASSING / FAILING / IN PROGRESS from these
  fi
fi
```

For each run, report: workflow name, status (queued/in_progress/completed),
conclusion (success/failure/cancelled/skipped).

If any run failed, surface the failing job/step:

```bash
gh run view RUN_ID --json jobs \
  --jq '.jobs[] | select(.conclusion=="failure") | {name, steps: [.steps[] | select(.conclusion=="failure") | .name]}'
```

**Do not poll or block on long-running CI.** If runs are still
`queued`/`in_progress`, say so once and note that re-running this command later
will show updated status.

Print a compact summary:

```
CI Status
=========
Branch: {branch-name}

Workflow Runs (latest 5):
  1. Build & Test   SUCCESS   2m 15s
  2. Lint           SUCCESS   45s
  3. Docker Build   FAILURE   1m 48s

Overall: PASSING | FAILING | IN PROGRESS | NO RUNS YET
```

If `gh` is unavailable, or `gh run list` errors (no workflows, no auth, etc.),
skip this step silently and omit the CI Status block from the report.

______________________________________________________________________

## Workflow B: Merge to Target Branch

### B1: Push Feature Branch

```bash
git push -u origin $(git branch --show-current)
```

### B2: Switch to Target and Pull

Before switching, verify the working tree is clean (Step 3 should have committed
everything, but double-check):

```bash
FEATURE_BRANCH=$(git branch --show-current)
git status --porcelain
```

**If uncommitted changes exist at this point, STOP.** Do not switch branches. Go
back and commit them (re-run Step 3) before continuing.

```bash
git checkout $TARGET_BRANCH
git pull origin $TARGET_BRANCH
```

### B3: Merge Feature Branch

```bash
git merge $FEATURE_BRANCH --no-ff -m "Merge branch '$FEATURE_BRANCH' into $TARGET_BRANCH"
```

**If merge conflicts:** Stop and let user resolve.

### B4: Push Target

```bash
git push origin $TARGET_BRANCH
```

### B5: Report and Suggest Cleanup

```
Push Summary
=================
Source: {feature-branch}
Target: {target-branch}

Merged successfully!

Suggestion: Delete the feature branch?
  git branch -d {feature-branch}
  git push origin --delete {feature-branch}
```

______________________________________________________________________

## Safety Checks

- [ ] Test phase (Step 2) passed, so no known regression is committed
- [ ] Pre-push hooks pass before any push
- [ ] Working tree clean before push (Step 3 committed any dirty changes)
- [ ] Not force pushing
- [ ] Merge commits (not fast-forward) for traceability

### Pre-push Hook Awareness

If `.pre-commit-config.yaml` exists, check for `pre-push` stage hooks:

```bash
if [ -f .pre-commit-config.yaml ]; then
  grep -B2 "pre-push" .pre-commit-config.yaml
fi
```

Pre-push hooks often run tests, builds, and security scans which can take
minutes. If heavy hooks are detected, warn the user before pushing:

```
Note: Pre-push hooks will run before push completes.
Detected: [pytest, eslint, build, semgrep, trivy, etc.]
This may take a few minutes.
```

### Never Do

- Force push to main/master without explicit confirmation
- Auto-resolve merge conflicts
- Skip hooks with `--no-verify`
- Push secrets or sensitive files
- Stash changes to work around a dirty tree. Commit them instead (Step 3)

## Large PR Warning

Report the size of a large diff (over 1000 lines or 50 files) so the author
knows what the reviewer is about to get. Do **not** suggest splitting the PR. A
PR is as big as the work it does, and one of this skill's callers is a wayfare
goal, whose whole shape is one branch and one PR carrying every feature in
`covers`. Advising a split there is advising the author to undo the grouping on
purpose. Commits are where the work is separated, and the goal already puts one
per feature.

## Examples

```
wayfare:wayfare-push-pr                                       # Test, commit, push, draft PR
wayfare:wayfare-push-pr ready                                 # Test, commit, push, non-draft PR
wayfare:wayfare-push-pr test                                  # Test only (verification + smoke), no commit
wayfare:wayfare-push-pr commit                                # Test and commit, stop before pushing
wayfare:wayfare-push-pr test verify                           # Only lint, typecheck, unit tests
wayfare:wayfare-push-pr test frontend /dashboard /settings    # Smoke-test specific routes (verbatim)
wayfare:wayfare-push-pr test cli run the export command       # Smoke-test a specific CLI command
wayfare:wayfare-push-pr develop                               # Test, commit, push, merge into develop
```

## Notes

- Uses GitHub CLI (`gh`) for PR, branch, and CI operations
- Respects repository PR templates if they exist
- Always creates merge commits for traceability
- Never commits or pushes directly to the default branch. Step 1 branches off
  first
- Always check the project's CLAUDE.md first for custom run instructions
- The frontend smoke is a **smoke** test, not a full E2E: cap routes at 5, skip
  large forms, do not chase flaky tests. If a real E2E suite already exists in
  the repo (Playwright config, Cypress, etc.), prefer running it directly
  instead.
- The test phase never modifies tracked source files. It only reads, drives, and
  reports, but writes disposable local artifacts under `$ROOT/.test-output/`
  (screenshots in `.test-output/playwright-mcp/`, the dev-server log at
  `.test-output/dev-server.log`). The ignore rule lives in `.git/info/exclude`,
  which is repo-local and untracked, *not* `.gitignore`, so the working tree
  never gets dirtied.
- Use `browser_snapshot` (not screenshots) for reliable element interaction;
  screenshots are captured separately as evidence for the report
- When testing completes, stop the background servers the test phase started,
  except the frontend dev server, which is left running by default and only
  stopped when the user opts in
