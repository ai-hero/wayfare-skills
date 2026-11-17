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

# Exit 1, never 2, on an empty payload: without it stop_hook_active cannot be
# read, and a block the loop guard cannot see re-blocks every continuation for
# as long as the check keeps failing.
if [ -z "$PAYLOAD" ]; then
  echo "stop-checks: empty hook payload; not checking" >&2
  exit 1
fi

# Claude Code sets stop_hook_active once a Stop hook has already sent the agent
# back to work this turn. Blocking again is the infinite loop the field exists
# to break, so the second attempt to stop always succeeds; a check that is
# still red is told to the person instead, or nobody hears of it.
ACTIVE=0
if printf '%s' "$PAYLOAD" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  ACTIVE=1
fi

# The payload's cwd before CLAUDE_PROJECT_DIR: a session working in a worktree
# has the worktree as cwd and the main checkout as the project dir, and checking
# the project dir passes over the very tree the agent changed.
CWD="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
if ! { [ -n "$CWD" ] && cd "$CWD" 2>/dev/null; }; then
  cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
fi
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

# A status that fails prints nothing, which would read as a clean tree.
STATUS="$(git status --porcelain 2>/dev/null)" || STATUS="status failed"
# --not --remotes rather than @{u}..HEAD: a branch that was never pushed has no
# upstream, and @{u} then errors, which would read as "nothing unpushed".
if [ -z "$STATUS" ] &&
  [ -z "$(git rev-list --max-count=1 HEAD --not --remotes 2>/dev/null)" ]; then
  exit 0
fi

# Every message passed here is a fixed literal: it is printed into JSON
# unescaped, so a quote or backslash in one breaks the payload.
system_message() { # MESSAGE
  printf '{"systemMessage": "%s"}\n' "$1"
}

warn_once() { # MESSAGE
  local sid key
  sid="$(printf '%s' "$PAYLOAD" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9_-]*\)".*/\1/p')"
  # No session id means no marker: a shared one would silence the warning in
  # every later session on this machine.
  if [ -n "$sid" ]; then
    key="${TMPDIR:-/tmp}/stop-checks-warned-$sid"
    [ -e "$key" ] && return 0
    : >"$key" 2>/dev/null
  fi
  # stdout JSON with exit 0: systemMessage reaches the person without blocking.
  system_message "$1"
}

fail() { # RC ELAPSED OUTPUT
  local clean total
  if [ "$ACTIVE" -eq 1 ]; then
    system_message "stop-checks: just check-fast is still failing; run it to see why"
    exit 0
  fi
  clean="$(printf '%s\n' "$3" | sed $'s/\x1b\\[[0-9;]*[A-Za-z]//g')"
  total="$(printf '%s\n' "$clean" | wc -l | tr -d ' ')"
  {
    echo "just check-fast failed (exit $1) after ${2}s. Fix it before ending the turn."
    if [ "$total" -gt "$TAIL_LINES" ]; then
      echo "Last $TAIL_LINES of $total lines; run \`just check-fast\` for the rest:"
    fi
    printf '%s\n' "$clean" | tail -n "$TAIL_LINES"
  } >&2
  exit 2
}

if ! command -v just >/dev/null 2>&1; then
  warn_once "stop-checks: just is not installed, so check-fast did not run"
  exit 0
fi
# A Justfile that no longer parses fails --summary too; reading that as "no
# recipe" lets an agent that broke the Justfile end its turn.
SUMMARY="$(NO_COLOR=1 just --summary 2>&1)"
RC=$?
if [ "$RC" -ne 0 ]; then
  if printf '%s' "$SUMMARY" | grep -q 'No justfile found'; then
    warn_once "stop-checks: this repo has no Justfile, so nothing ran"
    exit 0
  fi
  fail "$RC" 0 "$SUMMARY"
fi
if ! printf '%s' "$SUMMARY" | tr ' ' '\n' | grep -qx 'check-fast'; then
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
fail "$RC" "$ELAPSED" "$OUTPUT"
