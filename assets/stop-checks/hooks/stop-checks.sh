#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Stop hook — run the repo's `just check-fast` before the agent ends its turn.
#
# Vendored by scripts/install-stop-checks.sh, which refuses to overwrite a
# drifted copy. Fix bugs here in the wayfare plugin and re-run the installer; a
# local patch in a consuming repo makes that repo permanently decline updates.
#
# Exit 2 with the failure on stderr is what makes the agent keep working;
# every other exit lets the turn end. What goes into check-fast is the repo's
# call, in its Justfile: this hook only knows the recipe name.

set -uo pipefail

TAIL_LINES=60

PAYLOAD="$(cat)"

# Exit 1, never 2, on an unreadable payload: without it stop_hook_active
# cannot be read, and a block the loop guard cannot see re-blocks every
# continuation for as long as the check keeps failing.
if [ -z "$PAYLOAD" ]; then
  echo "stop-checks: empty hook payload; not checking" >&2
  exit 1
fi

# Claude Code sets stop_hook_active once a Stop hook has already sent the agent
# back to work this turn. Blocking again is the infinite loop the field exists
# to break, so the second attempt to stop always succeeds.
if printf '%s' "$PAYLOAD" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ROOT" ]; then
  ROOT="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
fi
cd "${ROOT:-.}" 2>/dev/null || exit 0
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" || exit 0

# --git-path, not .git/<name>: in a worktree .git is a file, and the test
# `[ -f .git/MERGE_HEAD ]` is then false mid-merge.
for marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
  if [ -e "$(git rev-parse --git-path "$marker")" ]; then
    echo "stop-checks: skipped, a merge, rebase or cherry-pick is in progress"
    exit 0
  fi
done

# --not --remotes rather than @{u}..HEAD: a branch that was never pushed has no
# upstream, and @{u} then errors, which would read as "nothing unpushed".
if [ -z "$(git status --porcelain 2>/dev/null)" ] &&
  [ -z "$(git rev-list --max-count=1 HEAD --not --remotes 2>/dev/null)" ]; then
  exit 0
fi

warn_once() { # MESSAGE
  local sid key
  sid="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9_-]*\)".*/\1/p')"
  key="${TMPDIR:-/tmp}/stop-checks-warned-${sid:-nosession}"
  [ -e "$key" ] && return 0
  : >"$key" 2>/dev/null
  # stdout JSON with exit 0: systemMessage reaches the person without blocking.
  printf '{"systemMessage": "%s"}\n' "$1"
}

if ! command -v just >/dev/null 2>&1; then
  warn_once "stop-checks: just is not installed, so check-fast did not run"
  exit 0
fi
if ! just --summary 2>/dev/null | tr ' ' '\n' | grep -qx 'check-fast'; then
  warn_once "stop-checks: this repo's Justfile has no check-fast recipe, so nothing ran"
  exit 0
fi

START=$SECONDS
OUTPUT="$(NO_COLOR=1 just check-fast 2>&1)"
RC=$?
ELAPSED=$((SECONDS - START))

if [ "$RC" -eq 0 ]; then
  echo "stop-checks: just check-fast passed in ${ELAPSED}s"
  exit 0
fi

CLEAN="$(printf '%s\n' "$OUTPUT" | sed $'s/\x1b\\[[0-9;]*[A-Za-z]//g')"
TOTAL="$(printf '%s\n' "$CLEAN" | wc -l | tr -d ' ')"
{
  echo "just check-fast failed (exit $RC) after ${ELAPSED}s. Fix it before ending the turn."
  if [ "$TOTAL" -gt "$TAIL_LINES" ]; then
    echo "Last $TAIL_LINES of $TOTAL lines; run \`just check-fast\` for the rest:"
  fi
  printf '%s\n' "$CLEAN" | tail -n "$TAIL_LINES"
} >&2
exit 2
