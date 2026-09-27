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

branch_with finished finished.txt "item closed, branch kept"

# PR 20 merged the branch's first head; the commit after it is unshipped.
branch_with post-merge post.txt "merged part"
POST_OID=$(g rev-parse post-merge)
g merge -q --squash post-merge >/dev/null && g commit -q -m "squash: post" && g push -q origin main
g checkout -q post-merge && printf 'after the merge\n' > "$R/later.txt" && g add -A && g commit -q -m later && g checkout -q main
# PR 21 merged exactly this tip, though the base does not hold it.
branch_with covered covered.txt "merged by its PR"
COVERED_OID=$(g rev-parse covered)
# PR 30 came from a fork whose branch has the common name and this very tip.
branch_with patch-1 patch.txt "ours, not the fork's"
PATCH_OID=$(g rev-parse patch-1)

# Pushed from another checkout: origin has a commit the local ref lacks.
branch_with behind behind.txt "first"
g checkout -q behind && printf 'second\n' > "$R/behind2.txt" && g add -A && g commit -q -m second
g push -q origin behind && g reset -q --hard HEAD~1 && g checkout -q main
g push -q origin fresh

g worktree add -q --detach "$TMP/det" main
printf 'lost\n' > "$TMP/det/lost.txt" && git -C "$TMP/det" add -A && git -C "$TMP/det" commit -q -m lost
DET_SHA=$(git -C "$TMP/det" rev-parse HEAD)
g worktree add -q --detach "$TMP/det-clean" main

mkdir -p "$R/.plans/items"
printf -- '---\nid: 1\ntype: task\nstatus: active\nbranch: claimed\n---\n' > "$R/.plans/items/001-claimed.md"
printf -- '---\nid: 2\ntype: task\nstatus: done\nbranch: finished\n---\n' > "$R/.plans/items/002-finished.md"

mkdir -p "$TMP/bin"
{
  printf 'reviewing\tOPEN\t7\t0\tfalse\n'
  printf 'post-merge\tMERGED\t20\t%s\tfalse\n' "$POST_OID"
  printf 'covered\tMERGED\t21\t%s\tfalse\n' "$COVERED_OID"
  printf 'patch-1\tMERGED\t30\t%s\ttrue\n' "$PATCH_OID"
} > "$TMP/prs.tsv"
cat > "$TMP/bin/gh" <<EOF
#!/bin/sh
[ -n "\${GH_FAIL:-}" ] && exit 1
cat "$TMP/prs.tsv"
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
check "a done item's branch is not owned" "ship-now" "$(class_of finished)"
check "commits after a merged PR stay unshipped" "ship-now" "$(class_of post-merge)"
check "a merged PR whose head holds the tip marks it merged" "merged" "$(class_of covered)"
check "a fork PR with the same name does not mark it merged" "ship-now" "$(class_of patch-1)"
check "origin ahead of local is scanned too" "ship-now" "$(class_of origin/behind)"
check "local behind origin keeps its own row" "ship-now" "$(class_of behind)"
check "origin equal to local is not a second row" "" "$(class_of origin/fresh)"
check "detached worktree with an unreachable commit" "detached" "$(class_of "$DET_SHA")"
check "detached row names its worktree" "$(cd "$TMP/det" && pwd -P)" \
  "$(printf '%s\n' "$OUT" | awk -F'\t' '$1 == "detached" { print $5 }' | xargs -I{} sh -c 'cd "{}" && pwd -P')"
check "clean detached worktree on a ref is not a row" "1" \
  "$(printf '%s\n' "$OUT" | awk -F'\t' '$1 == "detached"' | wc -l | tr -d ' ')"
check "net diff shown for ship-now" "1 file changed, 1 insertion(+)" \
  "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "fresh" { print $4 }')"

OUT=$(GH_FAIL=1 run)
check "gh failure is unhealthy" "UNSHIPPED_OK=false" "$(printf '%s\n' "$OUT" | head -1)"
check "gh failure marks pr unknown" "unknown" "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "fresh" { print $7 }')"
check "without gh, a PR branch falls back to its git class" "ship-now" "$(class_of reviewing)"

# gh absent, not failing: the shell's own "command not found" must not pass
# for an empty PR list.
mkdir -p "$TMP/nogh"
for t in bash sh git awk sed grep wc tr date dirname cat head sort mktemp; do
  p=$(command -v "$t") && ln -sf "$p" "$TMP/nogh/$t"
done
OUT=$(PATH="$TMP/nogh" UNSHIPPED_NOW=$(date +%s) "$TMP/nogh/bash" "$SCRIPT" "$R")
check "gh missing is unhealthy" "UNSHIPPED_ERRORS=gh" "$(printf '%s\n' "$OUT" | sed -n 2p)"
check "gh missing marks pr unknown" "unknown" "$(printf '%s\n' "$OUT" | awk -F'\t' '$2 == "fresh" { print $7 }')"
check "gh missing still classifies by git" "merged" "$(class_of squashed)"

# No default-branch in HERO.md: origin's HEAD names it, not a guessed `main`.
git init -q --bare -b master "$TMP/m-origin.git"
git clone -q "$TMP/m-origin.git" "$TMP/m-seed" 2>/dev/null
printf 'base\n' > "$TMP/m-seed/a.txt"
git -C "$TMP/m-seed" add -A && git -C "$TMP/m-seed" commit -q -m init && git -C "$TMP/m-seed" push -q origin master
git clone -q "$TMP/m-origin.git" "$TMP/m-repo" 2>/dev/null
git -C "$TMP/m-repo" checkout -q -b topic && printf 'x\n' > "$TMP/m-repo/b.txt" &&
  git -C "$TMP/m-repo" add -A && git -C "$TMP/m-repo" commit -q -m topic && git -C "$TMP/m-repo" checkout -q master
OUT=$(PATH="$TMP/bin:$PATH" UNSHIPPED_NOW=$(date +%s) bash "$SCRIPT" "$TMP/m-repo")
check "master default is healthy" "UNSHIPPED_OK=true" "$(printf '%s\n' "$OUT" | head -1)"
check "master default is not a row" "" "$(class_of master)"
check "branch diffed against master" "ship-now" "$(class_of topic)"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
