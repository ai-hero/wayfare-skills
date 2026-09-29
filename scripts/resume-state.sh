#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# resume-state.sh: gather the git/PR state wayfare-build-task needs to pick a resume point.
#
# Prints shell-eval-able KEY=VALUE lines describing where the current branch
# sits in the pipeline. wayfare-build-task's Step 0.5 maps these onto a resume step; this
# script makes no routing decision itself, so the decision table stays in
# SKILL.md where a reader can see it.
#
# Usage:
#   eval "$(scripts/resume-state.sh)"
#
# Emits:
#   DEFAULT_BRANCH, CURRENT_BRANCH   branch context
#   UNCOMMITTED                      count of dirty files
#   AHEAD                            commits past origin/DEFAULT_BRANCH
#   UNPUSHED                         commits past the branch's own upstream
#   PR_EXISTS PR_NUMBER PR_STATE PR_IS_DRAFT PR_REVIEW
#   SELF_REVIEW_DONE BOT_REPLIED
#   ITEM_INFLIGHT ITEM_FILE          active .plans items (goals and bot PRs excluded);
#                                    the file bound to this branch, or the single
#                                    unbranched one. `unknown` when the store failed
#   SUBTASKS_OPEN SUBTASKS_TOTAL     unchecked / all lines in that item's ## Subtasks
#   DOD_OPEN DOD_TOTAL               same for its ## Definition of Done. EMPTY, not 0,
#                                    when ITEM_FILE is empty, 0 would claim a
#                                    checklist that was never read
#   STATE_OK STATE_ERRORS            aggregate health + which sources failed
#
# THE UNKNOWN/ZERO RULE
#
# A failed call produces values indistinguishable from a legitimate clean state:
# AHEAD=0 reads as "nothing to push" whether or not `git fetch` succeeded, and
# SELF_REVIEW_DONE=0 reads as "never reviewed" whether or not the comments call
# worked. Routing on either is how a pipeline skips a step it needed to run, or
# repeats one it didn't.
#
# So a value whose source failed is emitted as the literal string `unknown`,
# never as a number. This puts the uncertainty IN the value: a consumer doing
# `[ "$AHEAD" -eq 0 ]` fails loudly, and a decision table row written as
# `SELF_REVIEW_DONE == 0` cannot match. The guard is structural rather than a
# rule the reader has to remember.
#
# STATE_OK is false if ANY source failed, with STATE_ERRORS naming which. One
# row guarding STATE_OK covers every case, so adding a source later cannot
# silently bypass a guard that enumerated the old ones.
#
# Read-only apart from `git fetch`, which writes local remote-tracking refs.
# Never edits files, branches, or remote state. Always exits 0, the caller
# inspects STATE_OK.

set -uo pipefail

STATE_ERRORS=""
fail_source() { STATE_ERRORS="${STATE_ERRORS:+$STATE_ERRORS,}$1"; }

emit() { printf '%s=%s\n' "$1" "$(printf '%q' "$2")"; }

HERO_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
if ! . "$HERO_LIB" 2>/dev/null; then
  # Emit a well-formed unhealthy state rather than nothing. Emitting nothing
  # left every variable unset in the caller, including STATE_OK, so the guard
  # row could not match and the run proceeded on garbage.
  echo "STATE_OK=false"
  echo "STATE_ERRORS=lib"
  echo "echo 'resume-state: cannot source hero-lib.sh; reinstall the plugin.' >&2"
  exit 0
fi

# ---------- branch context -------------------------------------------------

# Capture hero_field's rc directly: hero_default_branch collapses "absent" and
# "rejected as unsafe" into the same silent `main`, so a HERO.md the security
# gate refused would otherwise leave every AHEAD/REF measurement pointed at the
# wrong branch while STATE_OK still read healthy.
DEFAULT_BRANCH=$(hero_field default-branch); HF_RC=$?
case "$HF_RC" in
  0) hero_is_valid_branch "$DEFAULT_BRANCH" || { DEFAULT_BRANCH=main; fail_source "default-branch-invalid"; } ;;
  2) DEFAULT_BRANCH=main; fail_source "default-branch-rejected" ;;
  *) DEFAULT_BRANCH=main
     [ -r "$(hero_root)/HERO.md" ] || fail_source "no-hero-md" ;;
esac

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)

# Detached HEAD yields an empty branch name, and `gh pr list --head ""` does not
# error. It returns an ARBITRARY open PR. Binding the pipeline to an unrelated
# PR and then routing it toward ship is the worst failure this script can cause.
if [ -z "$CURRENT_BRANCH" ]; then
  fail_source "detached-head"
fi

# jq is a hard dependency for every PR field below. Without it `gh` still
# succeeds, so a GH-only flag reads healthy while every parse yields empty,
# PR_EXISTS=false on a repo with a live PR, which routes to push and opens a
# duplicate.
# Probe that jq WORKS, not merely that it exists on PATH, a jq that is present
# but broken (wrong arch, missing lib, shim on a stripped PATH) passes a
# `command -v` check and then fails every parse, which is the same silent-empty
# outcome as jq being absent.
JQ_OK=true
printf '{}' | jq -e . >/dev/null 2>&1 || { JQ_OK=false; fail_source "jq"; }

FETCH_OK=true
git fetch origin "$DEFAULT_BRANCH" >/dev/null 2>&1 || { FETCH_OK=false; fail_source "fetch"; }

# A successful fetch does NOT imply the ref resolves: in a --single-branch clone
# the refspec only covers the cloned branch, so `git fetch origin main` returns 0
# while origin/main does not exist. AHEAD would then be 0 on a branch carrying a
# full stack of commits.
REF_OK=true
git rev-parse --verify --quiet "origin/$DEFAULT_BRANCH" >/dev/null 2>&1 \
  || { REF_OK=false; fail_source "default-ref"; }

# `git status | wc -l` yields 0 when git FAILS, which is byte-identical to a
# clean tree. It was the only emitted count with no unknown branch.
if UNCOMMITTED_RAW=$(git status --porcelain 2>/dev/null); then
  UNCOMMITTED=$(printf '%s' "$UNCOMMITTED_RAW" | grep -c . | tr -d ' ')
else
  UNCOMMITTED=unknown
  fail_source "git-status"
fi

if [ "$FETCH_OK" = true ] && [ "$REF_OK" = true ]; then
  # `|| echo 0` here would fabricate a zero when rev-list itself fails, which
  # is indistinguishable from "nothing to push", the guarded refs only prove
  # the ref resolves, not that the count succeeded.
  AHEAD=$(git rev-list --count "origin/$DEFAULT_BRANCH..HEAD" 2>/dev/null | grep -E '^[0-9]+$') \
    || { AHEAD=unknown; fail_source "rev-list-ahead"; }
else
  AHEAD=unknown
fi

# UNPUSHED: commits past this branch's own upstream (the PR's head ref),
# distinct from AHEAD. Someone who pushed once then committed again locally has
# both non-zero, and those follow-ups must reach the PR before any review step.
#
# With no upstream configured (normal before the first push) `git rev-list
# @{u}..HEAD` fails silently and would yield 0, which routes the user past the
# push step and skips the initial push entirely. Fall back to AHEAD instead.
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  UNPUSHED=$(git rev-list --count '@{u}..HEAD' 2>/dev/null | grep -E '^[0-9]+$') \
    || { UNPUSHED=unknown; fail_source "rev-list-unpushed"; }
else
  UNPUSHED=$AHEAD
fi

# ---------- PR state -------------------------------------------------------

PR_EXISTS=unknown
PR_NUMBER=""
PR_STATE=""
PR_IS_DRAFT=""
PR_REVIEW=""
SELF_REVIEW_DONE=unknown
BOT_REPLIED=unknown

if [ "$JQ_OK" = true ] && [ -n "$CURRENT_BRANCH" ]; then
  # --state all is required: the default is `open`, so a merged or closed PR
  # returns [] and reads as "no PR", which made every MERGED/CLOSED row in
  # wayfare-build-task's decision table unreachable, including the one that stops a
  # merged branch from being pushed again as a duplicate.
  if PR_LIST=$(gh pr list --state all --head "$CURRENT_BRANCH" \
      --json number,url,isDraft,reviewDecision,state 2>/dev/null); then
    # With --state all, a branch that had a closed PR and then a new open one
    # returns both. Prefer the OPEN one, because that is the PR this pipeline
    # is working, and fall back to the first entry when none is open.
    PR_JSON=$(printf '%s' "$PR_LIST" \
      | jq -r '((map(select(.state == "OPEN")) | .[0]) // .[0]) // empty' 2>/dev/null)
    PR_NUMBER=$(printf '%s' "$PR_JSON" | jq -r '.number // empty' 2>/dev/null)
    PR_STATE=$(printf '%s' "$PR_JSON" | jq -r '.state // empty' 2>/dev/null)
    # `.isDraft // empty` returns empty for BOTH null and false, so PR_IS_DRAFT
    # could never be the string "false" and every table row testing for it was
    # dead. Convert explicitly instead of relying on //.
    PR_IS_DRAFT=$(printf '%s' "$PR_JSON" | jq -r 'if .isDraft == null then empty else (.isDraft|tostring) end' 2>/dev/null)
    PR_REVIEW=$(printf '%s' "$PR_JSON" | jq -r '.reviewDecision // empty' 2>/dev/null)
    if [ -n "$PR_NUMBER" ]; then PR_EXISTS=true; else PR_EXISTS=false; fi
  else
    fail_source "gh-pr-list"
  fi
fi

if [ "$PR_EXISTS" = "false" ]; then
  # No PR means these are genuinely zero, not unknown.
  SELF_REVIEW_DONE=0
  BOT_REPLIED=false
elif [ "$PR_EXISTS" = "true" ]; then
  # The self-review count is author-filtered (see hero_self_review_count);
  # an unknown login must not silently count zero self-reviews.
  #
  # A COMPLETE review, not a started one: the findings comment and the
  # improvements comment carry the same marker, so counting the marker made
  # a review that stopped after findings read as done. The table below routes
  # on `SELF_REVIEW_DONE == 0`, so that reading skipped Step 5 and handed the
  # PR to ship-pr, whose prior-review gate then refused it for the missing
  # half. Counting the improvements comment is counting the terminal
  # artifact; review-pr posts it even when it fixed nothing.
  ME=$(gh api user --jq .login 2>/dev/null) || { ME=""; fail_source "gh-user"; }
  if COMMENTS=$(gh api --paginate "/repos/{owner}/{repo}/issues/$PR_NUMBER/comments?per_page=100" 2>/dev/null); then
    SELF_REVIEW_DONE=$(printf '%s' "$COMMENTS" \
      | jq --arg fx "$HERO_SELF_REVIEW_FIXES_MARKER" --arg me "$ME" '[.[] | select(.user.login == $me) | select(.body | test($fx; "i"))] | length' 2>/dev/null) \
      || { SELF_REVIEW_DONE=unknown; fail_source "self-review-count"; }

    # BOT_REPLIED is only meaningful if we know who the bot is. Without
    # bot-username configured, a `false` here is indistinguishable from "no
    # reply yet" and await-review waits forever for a reply already posted.
    # `agent: none` is a first-class supported setting (`wayfare-init-repo` writes it when
    # no review bot is detected), and such a repo has no bot-username. Treating
    # that as a failed source made STATE_OK=false on every resume, so wayfare-build-task
    # stopped with a diagnostic on a perfectly valid configuration.
    REVIEW_AGENT=$(hero_field agent 2>/dev/null | tr '[:upper:]' '[:lower:]')
    if [ "$REVIEW_AGENT" = "none" ]; then
      BOT_REPLIED=none
    elif BOT_USER=$(hero_field bot-username 2>/dev/null); then
      # `|| echo 0` here produced BOT_REPLIED=false with STATE_OK=true, a
      # reply that exists, reported as absent, so await-review polls forever.
      if BOT_COUNT=$(printf '%s' "$COMMENTS" \
        | jq --arg u "$BOT_USER" '[.[] | select(.user.login == $u)] | length' 2>/dev/null); then
        if [ "${BOT_COUNT:-0}" -gt 0 ]; then BOT_REPLIED=true; else BOT_REPLIED=false; fi
      else
        BOT_REPLIED=unknown
        fail_source "bot-count"
      fi
    else
      BOT_REPLIED=unknown
      fail_source "bot-username"
    fi
  else
    fail_source "gh-comments"
  fi
fi

# ---------- work-item state ------------------------------------------------

# The in-flight item's checklists are the only record of where wayfare-build-task's
# Step 2 stopped: `.plans/` is git-ignored, so the diff says what changed but
# not which subtask was mid-way. hero_store_path, not hero_work_store: this
# script is read-only.
#
# Which active item is THIS branch's: the one whose `branch:` matches (wayfare-build-task
# Step 2 writes it at the first edit). "The single active item" is not a rule
# that holds: a goal's features all sit in the shared store, so several can be
# active at once. What keeps this unambiguous is that a goal's features share
# ONE branch and each is closed out to `committed` by its own commit-only run before
# the next one starts, so at most one is ever active on a given branch. Two
# matches means that close-out did not happen; it is a real conflict, not a
# case to guess at. Items without `branch:` predate the field; for those, a
# single one is taken and two is a claim conflict.
ITEM_INFLIGHT=0
ITEM_FILE=""
SUBTASKS_OPEN=""; SUBTASKS_TOTAL=""; DOD_OPEN=""; DOD_TOTAL=""

STORE=$(hero_store_path 2>/dev/null)
# Items live in `.plans/items/` under schema 1 (docs/PLAN.md); the listing
# prints bare filenames, so every read below joins them to ITEMS, not STORE.
ITEMS="$STORE/items"
# The guard is on the store, never on `items/`: an unmigrated store has no
# such directory, and skipping the block for it read as "nothing in flight"
# on every consumer the day schema 1 shipped. hero_ready_items refuses such a
# store with rc=1, which is the `work-store` failure below.
if [ -n "$STORE" ] && [ -d "$STORE" ]; then
  # stderr stays visible: it carries hero_ready_items' reason for each invalid
  # row, and the caller's eval consumes stdout only.
  if ROWS=$(hero_ready_items "$STORE"); then
    # An invalid row may be the item being built (a mistyped `status: active`);
    # dropping it would read as "nothing in flight" and route past its
    # unchecked subtasks.
    case "$ROWS" in invalid*|*"
invalid"*) fail_source "store-invalid-item" ;; esac
    MATCHED=""; LEGACY=""; LEGACY_N=0
    while read -r state f _; do
      # A flag overrides the row word, so a build that wrote `blocked_on` or
      # `awaiting` and stopped lists as blocked or suspended while its status
      # is still `active`. Reading the row alone lost it on resume.
      case "$state" in
        active) ;;
        blocked|suspended) [ "$(hero_item_status "$ITEMS/$f")" = active ] || continue ;;
        *) continue ;;
      esac
      # hero_ready_items owns the status enum; `active` is wayfare-build-task's mark
      # before its first edit. Only a task can be the item on this branch: a
      # goal at active is a set of tasks, and a signal at active is being
      # delivered, not built. A `bot:` task is a dependency bot's PR that
      # wayfare's bot-PR procedure carries, never wayfare-build-task's.
      [ "$(hero_item_type "$ITEMS/$f")" = task ] || continue
      [ -n "$(hero_item_field "$ITEMS/$f" bot)" ] && continue
      ITEM_INFLIGHT=$((ITEM_INFLIGHT + 1))
      branch=$(hero_item_field "$ITEMS/$f" branch)
      if [ -n "$branch" ]; then
        [ "$branch" = "$CURRENT_BRANCH" ] && MATCHED="$MATCHED$f "
      else
        LEGACY="$f"; LEGACY_N=$((LEGACY_N + 1))
      fi
    done <<EOF
$ROWS
EOF
    set -- $MATCHED
    if [ $# -eq 1 ]; then
      ITEM_FILE="$ITEMS/$1"
    elif [ $# -gt 1 ]; then
      fail_source "item-claim-conflict"
    elif [ "$LEGACY_N" -eq 1 ]; then
      ITEM_FILE="$ITEMS/$LEGACY"
    elif [ "$LEGACY_N" -gt 1 ]; then
      # Two unbranched claims on the store is not a choice this script makes.
      fail_source "item-claim-conflict"
    fi
  else
    ITEM_INFLIGHT=unknown
    fail_source "work-store"
  fi
fi

# Counts within one `## ` section: unchecked and all checklist lines, as
# `OPEN TOTAL`. A missing section is 0 0, distinguishable from an all-ticked
# one only by TOTAL, which is why both are emitted. The heading compare trims
# trailing whitespace like hero_md_field does; `## Subtasks ` from a hand edit
# must not read as "no section".
checklist_counts() { # FILE SECTION
  awk -v sec="## $2" '
    /^## / { h = $0; sub(/[ \t]+$/, "", h); in_s = (h == sec); next }
    in_s && /^[ \t]*([-*]|[0-9]+\.)[ \t]+\[[ xX]\]/ {
      total++
      if ($0 ~ /^[ \t]*([-*]|[0-9]+\.)[ \t]+\[ \]/) open++
    }
    END { printf "%d %d", open + 0, total + 0 }
  ' "$1"
}
# BSD awk prints nothing on an unopenable file; gawk still runs END and prints
# `0 0`. Neither is a count, so validate the shape rather than the rc alone.
if [ -n "$ITEM_FILE" ]; then
  for SECTION in "Subtasks" "Definition of Done"; do
    COUNTS=$(checklist_counts "$ITEM_FILE" "$SECTION" 2>/dev/null) && [ -r "$ITEM_FILE" ] \
      && printf '%s' "$COUNTS" | grep -Eq '^[0-9]+ [0-9]+$' \
      || { COUNTS="unknown unknown"; fail_source "item-checklist"; }
    case "$SECTION" in
      Subtasks) read -r SUBTASKS_OPEN SUBTASKS_TOTAL <<EOF
$COUNTS
EOF
      ;;
      *) read -r DOD_OPEN DOD_TOTAL <<EOF
$COUNTS
EOF
      ;;
    esac
  done
fi

STATE_OK=true
[ -n "$STATE_ERRORS" ] && STATE_OK=false

emit DEFAULT_BRANCH   "$DEFAULT_BRANCH"
emit CURRENT_BRANCH   "$CURRENT_BRANCH"
emit UNCOMMITTED      "$UNCOMMITTED"
emit AHEAD            "$AHEAD"
emit UNPUSHED         "$UNPUSHED"
emit PR_EXISTS        "$PR_EXISTS"
emit PR_NUMBER        "$PR_NUMBER"
emit PR_STATE         "$PR_STATE"
emit PR_IS_DRAFT      "$PR_IS_DRAFT"
emit PR_REVIEW        "$PR_REVIEW"
emit SELF_REVIEW_DONE "$SELF_REVIEW_DONE"
emit BOT_REPLIED      "$BOT_REPLIED"
emit ITEM_INFLIGHT    "$ITEM_INFLIGHT"
emit ITEM_FILE        "$ITEM_FILE"
emit SUBTASKS_OPEN    "$SUBTASKS_OPEN"
emit SUBTASKS_TOTAL   "$SUBTASKS_TOTAL"
emit DOD_OPEN         "$DOD_OPEN"
emit DOD_TOTAL        "$DOD_TOTAL"
emit STATE_OK         "$STATE_OK"
emit STATE_ERRORS     "$STATE_ERRORS"
