---
name: wayfare-check-preflight
# prettier-ignore
description: Run pre-flight checks for the wayfare pipeline. Catches missing tooling, stale HERO.md, .env mismatches and busy ports before any step does destructive work. Use before wayfare-push-pr, wayfare-ship-pr or wayfare-build-task, or when a pipeline step fails on setup.
argument-hint: "[--bucket tooling|repo|runtime|pipeline|all] [--projects p1,p2] | recalibrate"
disable-model-invocation: true
---

# Preflight: fail fast before the pipeline does damage

Runs the union of every downstream skill's blocking check so a
`wayfare-build-task` (or any individual hero skill) fails fast: before code is
edited, before a branch is created, before a PR is pushed.

The actual checks live in `scripts/preflight.sh`. This skill is a thin wrapper:
it invokes the script, renders the result for the user, and tells them what to
fix next.

## Arguments

- `recalibrate` - Tune the `HERO.md` fields this skill reads, then stop (see
  below). Matched before every other form.
- `$ARGUMENTS` - Optional flags passed straight to `scripts/preflight.sh`:
  - `--bucket BUCKET` - Run only one bucket. Values: `tooling`, `repo`,
    `runtime`, `pipeline`, or `all` (default).
  - `--projects p1,p2` - Restrict the `runtime` bucket to specific project paths
    or names from HERO.md. Useful when the diff only touches part of a monorepo.
  - `--quiet` - Suppress `[OK]` lines; only `[WARN]`, `[BLOCKER]`, `[SKIP]` are
    printed.

## Buckets

| Bucket | Checks |
| -- | -- |
| `tooling` | `gh` + auth + `repo` scope, `jq`, Node ≥18, Playwright MCP registered, pr-review-toolkit plugin installed, `pre-commit` present when `.pre-commit-config.yaml` exists |
| `repo` | HERO.md present + non-stale, `.github/workflows/auto-approve.yml` on default branch, no in-progress merge/rebase/cherry-pick |
| `runtime` | Per-project `.env` covers every key in `.env.example`, declared `port:` is free, declared `dependency-file:` exists |
| `pipeline` | `origin/DEFAULT_BRANCH` reachable, issue tracker auth (Linear / Jira / GitHub Issues) |

## Severity

- `[OK]` - check passed
- `[WARN]` - non-blocking issue. Surface it and continue.
- `[BLOCKER]` - the pipeline will fail. Halt.
- `[SKIP]` - check does not apply (e.g., no `.env.example`, no projects in
  HERO.md)

Exit code is `1` if any `BLOCKER` fired, `0` otherwise. Warnings never block.

## `recalibrate`

`wayfare:wayfare-check-preflight recalibrate` tunes the config that drives this
skill, and stops. It does not go on to run the skill. You want to see which
field was wrong, not spend a whole run finding out.

Dispatch on it before parsing any other argument, in whichever step does that
parsing. When the first token of `$ARGUMENTS` is exactly `recalibrate`, print
`preflight: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md) (report, ask, write, commit)
using the table below as the report, and stop.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-check-preflight
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

## Instructions

### Step 0: Load Hero Configuration

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

If `HERO.md` is missing, mention it but still run `scripts/preflight.sh`. The
script reports the missing-HERO blocker with a useful next step
(`wayfare:wayfare-init-repo`).

### Step 1: Run the Script

Resolve the plugin root through `WAYFARE_ROOT` (`references/loading.md`'s rule):
the harness-provided `CLAUDE_PLUGIN_ROOT` when set, else an exported
`WAYFARE_ROOT`, else the default install path. An agent with neither must
already have `WAYFARE_ROOT` exported per that rule.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
PREFLIGHT="$WAYFARE_ROOT/scripts/preflight.sh"
[ -x "$PREFLIGHT" ] || { echo "wayfare: cannot find preflight.sh at $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 2; }
"$PREFLIGHT" $ARGUMENTS
```

Stream the output to the user verbatim. Do NOT filter or summarize lines. The
structured prefixes (`[OK]`, `[WARN]`, `[BLOCKER]`, `[SKIP]`) are how the user
scans the result quickly.

### Step 2: Interpret the Exit Code

Capture the script's exit code. Then:

- **Exit 0, 0 warnings** → "All preflight checks passed. Safe to run
  wayfare:wayfare-build-task or any individual hero skill."
- **Exit 0, N warnings** → "Preflight passed with N warning(s). Safe to proceed;
  warnings are advisory and may bite later."
- **Exit 1** → "Preflight found one or more blockers. The wayfare pipeline will
  fail if you continue. Fix the blockers above, then re-run
  wayfare:wayfare-check-preflight."
- **Any other exit code** → preflight did not run to completion (e.g. it could
  not be found or resolve `WAYFARE_ROOT`). Report the exit code and the message
  printed above it; do not report it as pass or fail.

For each `[BLOCKER]` line, the script already prints the recommended fix inline.
Do not re-explain it. Point the user at the line.

### Step 3: Summary

Print a short summary block matching the style of other hero skills:

```
Preflight Summary
=================
Bucket(s):  tooling | repo | runtime | pipeline | all
Projects:   (all) or (the scoped list)

Blockers:   N
Warnings:   M
Skipped:    K

Result:     PASSED | BLOCKED

Next step: wayfare:wayfare-build-task $ARGUMENTS, which runs Steps 1-10 in one go.
Print this line only. Launch it on the user's word, never on your own.
```

If `Result: BLOCKED`, do not print the `wayfare-build-task` next step at all.
List the recommended fix commands from the script output instead, then suggest
re-running a single bucket after fixing
(`wayfare:wayfare-check-preflight --bucket repo`, or `tooling|runtime|pipeline`
as applicable) as that block's next step.

## When This Skill Runs Automatically

`wayfare:wayfare-build-task` calls `scripts/preflight.sh --bucket all` (with
`--projects` scoped to the projects the diff touches) at **Step 0.3**, before
auto-branching and resume detection. If any blocker fires, wayfare-build-task
halts before any branch is created.

You can also call it standalone any time: after adding a new project to HERO.md,
after editing a project's `.env`, or when something in the pipeline looks wrong
and you want a single command to see the whole environmental state.

## Notes

- The script is read-only. It never edits files, creates branches, modifies
  remote state, or runs interactive prompts. Safe to run on every invocation.
- For ports: the check uses `lsof -nP -iTCP:PORT -sTCP:LISTEN`. If `lsof` is
  unavailable (rare on macOS / linux dev boxes, common in minimal containers),
  the port check skips with `[SKIP]` rather than reporting a false-OK.
- For Playwright MCP: the canonical check is `claude mcp list`. If the `claude`
  CLI isn't on PATH (unusual but possible), the script falls back to grepping
  `~/.claude.json` for a `playwright` entry.
- For pr-review-toolkit: the script looks in
  `~/.claude/plugins/pr-review-toolkit/` and
  `$ROOT/.claude/plugins/pr-review-toolkit/`. If the plugin lives elsewhere on
  the user's setup, the check may report a false `[WARN]`. That is safe, because
  the worst case is `wayfare:wayfare-review-pr` falling back to a thinner
  review.
