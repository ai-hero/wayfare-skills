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
#   merged     merging lands nothing, or a same-repo PR merged a head that
#              contains its tip; a leftover to delete
#   conflicts  merging conflicts with the default branch; rebase or abandon
#   dirty      lands nothing, but its worktree holds uncommitted work
#   ship-now   lands a change cleanly, last commit within SHIP_NOW_DAYS (14)
#   stale      lands a change cleanly, older than that
#   unknown    merge-tree failed on it; never read this as merged
#   detached   a detached worktree with uncommitted files or a HEAD no ref
#              reaches; BRANCH is the HEAD sha. Nothing else would find it
#
# PR can name a merged PR on a row that is not `merged`: that PR merged an
# older head, and the commits since are still unshipped.
#
# A local branch and its origin twin get two rows when origin/X holds commits
# X lacks: a push from another checkout is invisible from the local ref.
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

# hero_default_branch falls back to `main`, which on a `master` repo makes the
# default branch itself a row and every branch a diff against a missing base.
if ! { DEFAULT=$(hero_field default-branch "$ROOT" 2>/dev/null) && hero_is_valid_branch "$DEFAULT"; }; then
  DEFAULT=$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)
  DEFAULT=${DEFAULT#origin/}
  [ -n "$DEFAULT" ] || DEFAULT=main
fi
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
if PRS=$(gh pr list --state all --limit 1000 \
    --json headRefName,state,number,headRefOid,isCrossRepository \
    --jq '.[] | "\(.headRefName)\t\(.state)\t\(.number)\t\(.headRefOid)\t\(.isCrossRepository)"' 2>/dev/null); then
  GH_OK=true
else
  GH_OK=false
  fail_source gh
fi

OWNED=""
STORE=$(hero_store_path "$ROOT")
for f in "$STORE"/items/*.md; do
  [ -f "$f" ] || continue
  # A finished item keeps its `branch:`; counting it would hide that branch
  # from every other class for good.
  case "$(hero_item_status "$f")" in done|dropped) continue ;; esac
  b=$(hero_item_field "$f" branch)
  [ -n "$b" ] && OWNED="$OWNED$b"$'\n'
done

WORKTREES=$(git worktree list --porcelain 2>/dev/null | awk '
  /^worktree / { path = substr($0, 10) }
  /^branch refs\/heads\// { sub(/^branch refs\/heads\//, ""); print $0 "\t" path }')

DETACHED=$(git worktree list --porcelain 2>/dev/null | awk '
  /^worktree / { path = substr($0, 10) }
  /^HEAD / { head = $2 }
  /^detached$/ { print head "\t" path }')

# Local branches, then remote ones: a branch pushed from a worktree since
# removed exists only on origin, and one pushed from another checkout can be
# ahead of its local twin.
BRANCHES=$( {
  git for-each-ref --format='%(refname:short)' refs/heads
  git for-each-ref --format='%(refname:lstrip=3)' refs/remotes/origin |
    while read -r r; do
      [ "$r" = HEAD ] && continue
      if git show-ref -q --verify "refs/heads/$r"; then
        git merge-base --is-ancestor "refs/remotes/origin/$r" "refs/heads/$r" 2>/dev/null ||
          echo "origin/$r"
      else
        echo "origin/$r"
      fi
    done
} | grep -vxF -e "$DEFAULT" -e "origin/$DEFAULT" )

# Prints CLASS<TAB>NET for REF from what merging it would land.
# Never classify by ancestry or `git log BASE..ref`: the default merge is a
# squash, so a shipped branch keeps commits the base will never contain and
# would read as unshipped forever.
git_class() { # REF AGE
  local tree rc
  tree=$(git merge-tree --write-tree "$BASE" "$1" 2>/dev/null); rc=$?
  tree=${tree%%$'\n'*}
  case "$rc" in
    0) if [ "$tree" = "$BASE_TREE" ]; then
         printf 'merged\t-'
       elif [ "$2" -le "$SHIP_NOW_DAYS" ]; then
         printf 'ship-now\t%s' "$(git diff --shortstat "$BASE_TREE" "$tree" | sed 's/^ *//')"
       else
         printf 'stale\t%s' "$(git diff --shortstat "$BASE_TREE" "$tree" | sed 's/^ *//')"
       fi ;;
    1) printf 'conflicts\t-' ;;
    *) printf 'unknown\t-' ;;
  esac
}

echo "UNSHIPPED_OK=$([ -z "$ERRORS" ] && echo true || echo false)"
echo "UNSHIPPED_ERRORS=$ERRORS"

printf '%s\n' "$BRANCHES" | while read -r ref; do
  [ -n "$ref" ] || continue
  name=${ref#origin/}

  # A fork's PR shares only a name (patch-1) with this branch; it says nothing
  # about it, so cross-repo rows never count.
  pr="none"; covered=false
  if [ "$GH_OK" = true ]; then
    mine=$(printf '%s\n' "$PRS" | awk -F'\t' -v b="$name" '$1 == b && $5 != "true"')
    # An open PR wins over a merged one: a branch reused after its first PR
    # merged is live again.
    live=$(printf '%s\n' "$mine" | awk -F'\t' '$2 == "OPEN" { print "OPEN#" $3; exit }')
    if [ -n "$live" ]; then
      pr=$live
    else
      first=$(printf '%s\n' "$mine" | awk -F'\t' 'NF { print $2 "#" $3; exit }')
      [ -n "$first" ] && pr=$first
      # A merged PR covers the branch only if the head it merged contains the
      # tip. Commits pushed after the merge are unshipped work, and calling
      # the row merged puts that work beside a delete command.
      while IFS=$'\t' read -r _ st num oid _; do
        [ "$st" = MERGED ] && [ -n "$oid" ] || continue
        if git merge-base --is-ancestor "$ref" "$oid" 2>/dev/null; then
          pr="MERGED#$num"; covered=true; break
        fi
      done <<< "$mine"
    fi
  else
    pr="unknown"
  fi

  wt=$(printf '%s\n' "$WORKTREES" | awk -F'\t' -v b="$name" '$1 == b { print $2; exit }')
  dirty=0
  [ -n "$wt" ] && dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  last=$(git log -1 --format=%ct "$ref" 2>/dev/null || echo "$NOW")
  age=$(( (NOW - last) / 86400 ))

  IFS=$'\t' read -r class net <<< "$(git_class "$ref" "$age")"

  [ "$covered" = true ] && [ "$class" != unknown ] && class=merged
  if printf '%s' "$OWNED" | grep -qxF "$name"; then class=owned; fi
  case "$pr" in OPEN#*) class=open-pr ;; esac
  # A dirty worktree holds work no ref records; merged would hide it.
  [ "$class" = merged ] && [ "$dirty" -gt 0 ] && class=dirty

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$class" "$ref" "$age" "${net:--}" "${wt:--}" "$dirty" "$pr"
done

printf '%s\n' "$DETACHED" | while IFS=$'\t' read -r sha wt; do
  [ -n "$sha" ] || continue
  dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$dirty" -gt 0 ] || [ -z "$(git for-each-ref --contains "$sha" --count=1 2>/dev/null)" ] || continue
  last=$(git log -1 --format=%ct "$sha" 2>/dev/null || echo "$NOW")
  age=$(( (NOW - last) / 86400 ))
  IFS=$'\t' read -r _ net <<< "$(git_class "$sha" "$age")"
  printf 'detached\t%s\t%s\t%s\t%s\t%s\tnone\n' "$sha" "$age" "${net:--}" "$wt" "$dirty"
done
