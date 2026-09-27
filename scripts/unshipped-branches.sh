#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# unshipped-branches.sh: classify every branch by what merging it would land.
#
# The `unshipped` stage of wayfare-sync-plan (references/sync.md). Prints one
# tab-separated row per branch, after a health line:
#
#   UNSHIPPED_OK=true|false   UNSHIPPED_ERRORS=a,b
#   CLASS  BRANCH  AGE_DAYS  NET  WORKTREE  DIRTY  PR
#
# CLASS is one of:
#   open-pr    an open PR carries it; in review, not stranded
#   owned      a .plans item's `branch:` names it; in flight
#   merged     merging lands nothing, or its PR merged; a leftover to delete
#   conflicts  merging conflicts with the default branch; rebase or abandon
#   dirty      lands nothing, but its worktree holds uncommitted work
#   ship-now   lands a change cleanly, last commit within SHIP_NOW_DAYS (14)
#   stale      lands a change cleanly, older than that
#   unknown    merge-tree failed on it; never read this as merged
#
# Usage: scripts/unshipped-branches.sh [ROOT]
#
# Read-only apart from `git fetch`. `git merge-tree --write-tree` writes loose
# objects and no refs. Always exits 0; the caller reads UNSHIPPED_OK.

set -uo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SHIP_NOW_DAYS="${SHIP_NOW_DAYS:-14}"
NOW="${UNSHIPPED_NOW:-$(date +%s)}"

ERRORS=""
fail_source() { ERRORS="${ERRORS:+$ERRORS,}$1"; }

HERO_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
if ! . "$HERO_LIB" 2>/dev/null; then
  echo "UNSHIPPED_OK=false"
  echo "UNSHIPPED_ERRORS=lib"
  exit 0
fi

cd "$ROOT" || { echo "UNSHIPPED_OK=false"; echo "UNSHIPPED_ERRORS=root"; exit 0; }

DEFAULT=$(hero_default_branch "$ROOT" 2>/dev/null)
git fetch --prune -q origin 2>/dev/null || fail_source fetch
BASE="origin/$DEFAULT"
if ! BASE_TREE=$(git rev-parse -q --verify "$BASE^{tree}" 2>/dev/null); then
  echo "UNSHIPPED_OK=false"
  echo "UNSHIPPED_ERRORS=${ERRORS:+$ERRORS,}base"
  exit 0
fi

# `merge-tree --write-tree` arrived in git 2.38. Without it there is no way to
# tell a squash-merged branch from an unmerged one, so stop rather than guess.
if ! git merge-tree --write-tree "$BASE" "$BASE" >/dev/null 2>&1; then
  echo "UNSHIPPED_OK=false"
  echo "UNSHIPPED_ERRORS=${ERRORS:+$ERRORS,}merge-tree"
  exit 0
fi

# A failed listing is not "no PRs": every row then says pr=unknown, and no
# branch may be classed merged on the PR's word.
PRS=""
if PRS=$(gh pr list --state all --limit 1000 --json headRefName,state,number \
    --jq '.[] | "\(.headRefName)\t\(.state)\t\(.number)"' 2>/dev/null); then
  GH_OK=true
else
  GH_OK=false
  fail_source gh
fi

OWNED=""
STORE=$(hero_store_path "$ROOT")
for f in "$STORE"/items/*.md; do
  [ -f "$f" ] || continue
  b=$(hero_item_field "$f" branch)
  [ -n "$b" ] && OWNED="$OWNED$b"$'\n'
done

WORKTREES=$(git worktree list --porcelain 2>/dev/null | awk '
  /^worktree / { path = substr($0, 10) }
  /^branch refs\/heads\// { sub(/^branch refs\/heads\//, ""); print $0 "\t" path }')

# Local branches, then remote ones with no local twin: a branch an agent
# pushed from a worktree that has since been removed exists only on origin.
BRANCHES=$( {
  git for-each-ref --format='%(refname:short)' refs/heads
  git for-each-ref --format='%(refname:lstrip=3)' refs/remotes/origin |
    while read -r r; do
      [ "$r" = HEAD ] && continue
      git show-ref -q --verify "refs/heads/$r" || echo "origin/$r"
    done
} | grep -vxF -e "$DEFAULT" -e "origin/$DEFAULT" )

echo "UNSHIPPED_OK=$([ -z "$ERRORS" ] && echo true || echo false)"
echo "UNSHIPPED_ERRORS=$ERRORS"

printf '%s\n' "$BRANCHES" | while read -r ref; do
  [ -n "$ref" ] || continue
  name=${ref#origin/}

  pr="none"
  if [ "$GH_OK" = true ]; then
    # An open PR wins over a merged one: a branch reused after its first PR
    # merged is live again.
    pr=$(printf '%s\n' "$PRS" | awk -F'\t' -v b="$name" '
      $1 == b { if ($2 == "OPEN") { o = "OPEN#" $3 } else if (!s) { s = $2 "#" $3 } }
      END { print (o ? o : (s ? s : "none")) }')
  else
    pr="unknown"
  fi

  wt=$(printf '%s\n' "$WORKTREES" | awk -F'\t' -v b="$name" '$1 == b { print $2; exit }')
  dirty=0
  [ -n "$wt" ] && dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  last=$(git log -1 --format=%ct "$ref" 2>/dev/null || echo "$NOW")
  age=$(( (NOW - last) / 86400 ))

  # Never classify by ancestry or `git log BASE..ref`: the default merge is a
  # squash, so a shipped branch keeps commits the base will never contain and
  # would read as unshipped forever. What merging would land is the only test.
  net="-"
  tree=$(git merge-tree --write-tree "$BASE" "$ref" 2>/dev/null); rc=$?
  tree=${tree%%$'\n'*}
  case "$rc" in
    0) if [ "$tree" = "$BASE_TREE" ]; then
         class=merged
       else
         net=$(git diff --shortstat "$BASE_TREE" "$tree" | sed 's/^ *//')
         if [ "$age" -le "$SHIP_NOW_DAYS" ]; then class=ship-now; else class=stale; fi
       fi ;;
    1) class=conflicts ;;
    *) class=unknown ;;
  esac

  case "$pr" in MERGED#*) [ "$class" = unknown ] || class=merged ;; esac
  if printf '%s' "$OWNED" | grep -qxF "$name"; then class=owned; fi
  case "$pr" in OPEN#*) class=open-pr ;; esac
  # A dirty worktree holds work no ref records; merged would hide it.
  [ "$class" = merged ] && [ "$dirty" -gt 0 ] && class=dirty

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$class" "$ref" "$age" "${net:--}" "${wt:--}" "$dirty" "$pr"
done
