#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/unshipped-branches.sh.
#
# The case that matters most is the squash merge: its commits never reach the
# default branch, so any ancestry-based check reports shipped work as
# unshipped. `gh` is stubbed; git runs for real against a local bare origin.
#
# Usage: bash scripts/unshipped-branches.test.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/unshipped-branches.sh"

PASS=0
FAIL=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL  %s\n      expected: [%s]\n      actual:   [%s]\n' "$1" "$2" "$3"
  fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export GIT_AUTHOR_NAME="wayfare tests" GIT_AUTHOR_EMAIL="tests@wayfare.invalid"
export GIT_COMMITTER_NAME="wayfare tests" GIT_COMMITTER_EMAIL="tests@wayfare.invalid"
# A commit hook runs this with GIT_INDEX_FILE (and friends) pointing at the
# outer repo; left set, every fixture `git add` writes into that real index.
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)

git init -q --bare -b main "$TMP/origin.git"
git clone -q "$TMP/origin.git" "$TMP/repo" 2>/dev/null
R="$TMP/repo"
g() { git -C "$R" "$@"; }

printf '# H\n\n- default-branch: main\n' > "$R/HERO.md"
printf 'line one\n' > "$R/shared.txt"
g add -A && g commit -q -m init && g push -q origin main || { echo "FATAL: fixture setup failed" >&2; exit 1; }

branch_with() { # NAME FILE CONTENT [COMMITTER_DATE]
  g checkout -q -b "$1" main
  printf '%s\n' "$3" > "$R/$2"
  g add -A
  if [ -n "${4:-}" ]; then
    GIT_COMMITTER_DATE="$4" GIT_AUTHOR_DATE="$4" g commit -q -m "$1"
  else
    g commit -q -m "$1"
  fi
  g checkout -q main
}

branch_with squashed feature.txt "shipped"
g merge -q --squash squashed >/dev/null && g commit -q -m "squash: shipped" && g push -q origin main
branch_with fresh fresh.txt "new work"
branch_with old old.txt "old work" "2026-01-01T00:00:00Z"
branch_with clash shared.txt "their line"
printf 'our line\n' > "$R/shared.txt" && g commit -q -am "main moves" && g push -q origin main
branch_with claimed claimed.txt "in flight"
branch_with reviewing reviewing.txt "under review"
branch_with pushed-only pushed.txt "remote only"
g push -q origin pushed-only && g branch -q -D pushed-only
branch_with leftover-wt wt.txt "shipped too"
g merge -q --squash leftover-wt >/dev/null && g commit -q -m "squash: wt" && g push -q origin main
g worktree add -q "$TMP/wt" leftover-wt
printf 'unsaved\n' > "$TMP/wt/scratch.txt"

mkdir -p "$R/.plans/items"
printf -- '---\nid: 1\ntype: task\nstatus: active\nbranch: claimed\n---\n' > "$R/.plans/items/001-claimed.md"

mkdir -p "$TMP/bin"
cat > "$TMP/bin/gh" <<'EOF'
#!/bin/sh
[ -n "${GH_FAIL:-}" ] && exit 1
printf 'reviewing\tOPEN\t7\n'
EOF
chmod +x "$TMP/bin/gh"

run() { PATH="$TMP/bin:$PATH" UNSHIPPED_NOW=$(date +%s) bash "$SCRIPT" "$R"; }
OUT=$(run)
class_of() { printf '%s\n' "$OUT" | awk -F'\t' -v b="$1" '$2 == b { print $1 }'; }

check "healthy run" "UNSHIPPED_OK=true" "$(printf '%s\n' "$OUT" | head -1)"
check "squash-merged branch is merged, not unshipped" "merged" "$(class_of squashed)"
check "recent clean change is ship-now" "ship-now" "$(class_of fresh)"
check "old clean change is stale" "stale" "$(class_of old)"
check "conflicting branch" "conflicts" "$(class_of clash)"
check "branch an item names is owned" "owned" "$(class_of claimed)"
check "branch with an open PR" "open-pr" "$(class_of reviewing)"
check "remote-only branch is scanned" "ship-now" "$(class_of origin/pushed-only)"
check "merged branch with a dirty worktree is not a leftover" "dirty" "$(class_of leftover-wt)"
check "dirty count reported" "1" "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "leftover-wt" { print $6 }')"
check "default branch skipped" "" "$(class_of main)"
check "net diff shown for ship-now" "1 file changed, 1 insertion(+)" \
  "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "fresh" { print $4 }')"

OUT=$(GH_FAIL=1 run)
check "gh failure is unhealthy" "UNSHIPPED_OK=false" "$(printf '%s\n' "$OUT" | head -1)"
check "gh failure marks pr unknown" "unknown" "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "fresh" { print $7 }')"
check "without gh, a PR branch falls back to its git class" "ship-now" "$(class_of reviewing)"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
