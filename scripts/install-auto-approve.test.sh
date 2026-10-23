#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for install-auto-approve.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (2 and 3 are contract, not
# failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/install-auto-approve.sh"
SOURCE="$HERE/../assets/auto-approve/caller.yaml"

PASS=0
FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $name"
    echo "  expected: $expected"
    echo "  actual:   $actual"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fixture() {
  local d="$WORK/$1"
  rm -rf "$d"
  mkdir -p "$d/.github/workflows"
  echo "$d"
}

# --- fresh install ----------------------------------------------------------
d=$(fixture fresh)
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "fresh: rc" "0" "$rc"
check "fresh: file created" "yes" "$([[ -f "$d/.github/workflows/auto-approve.yaml" ]] && echo yes || echo no)"
check "fresh: matches source" "same" "$(cmp -s "$SOURCE" "$d/.github/workflows/auto-approve.yaml" && echo same || echo differs)"

# The regression that matters: SOURCE reverting to the shared logic. Assert on
# content, not the path, a caller job resolves a `uses:` and cannot carry
# `runs-on:`, so that pair distinguishes caller from logic no matter how the
# file is spelled.
check "fresh: is the caller" "yes" \
  "$(grep -q 'uses: ai-hero/wayfare-skills/.github/workflows/auto-approve.yaml@' "$d/.github/workflows/auto-approve.yaml" && echo yes || echo no)"
check "fresh: is NOT the logic" "yes" \
  "$(grep -q 'runs-on:' "$d/.github/workflows/auto-approve.yaml" && echo no || echo yes)"

# Guidance that only prints on this path reaches nobody who is migrating.
check "fresh: names ANTHROPIC_API_KEY" "yes" "$(grep -q ANTHROPIC_API_KEY <<<"$out" && echo yes || echo no)"
check "fresh: names the private-repo gate" "yes" "$(grep -qi 'PRIVATE' <<<"$out" && echo yes || echo no)"

# --- idempotent re-run ------------------------------------------------------
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "rerun: rc" "0" "$rc"
check "rerun: no .new written" "yes" \
  "$([[ ! -f "$d/.github/workflows/auto-approve.yml.new" ]] && echo yes || echo no)"

# --- existing .yaml is adopted, not shadowed --------------------------------
d=$(fixture yaml_exists)
printf 'name: Auto Approve\njobs:\n  claude-approve:\n    runs-on: ubuntu-latest\n' \
  > "$d/.github/workflows/auto-approve.yaml"
before=$(shasum -a 256 < "$d/.github/workflows/auto-approve.yaml")
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "yaml: rc" "2" "$rc"
check "yaml: .yaml.new written" "yes" "$([[ -f "$d/.github/workflows/auto-approve.yaml.new" ]] && echo yes || echo no)"
# The trap the adoption logic exists for: a second live issue_comment workflow.
check "yaml: no .yml created beside it" "yes" \
  "$([[ ! -f "$d/.github/workflows/auto-approve.yml" ]] && echo yes || echo no)"
check "yaml: original untouched" "$before" "$(shasum -a 256 < "$d/.github/workflows/auto-approve.yaml")"
check "yaml: says replace not merge" "yes" "$(grep -qi 'do not merge' <<<"$out" && echo yes || echo no)"
# Migrating repos take this path exclusively, so the notes must print here too.
check "yaml: still prints the notes" "yes" "$(grep -q ANTHROPIC_API_KEY <<<"$out" && echo yes || echo no)"

# --- existing .yml ----------------------------------------------------------
d=$(fixture yml_exists)
echo "old: true" > "$d/.github/workflows/auto-approve.yml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "yml: rc" "2" "$rc"
check "yml: .yml.new written" "yes" "$([[ -f "$d/.github/workflows/auto-approve.yml.new" ]] && echo yes || echo no)"

# --- both spellings present -------------------------------------------------
d=$(fixture both)
echo "old: true" > "$d/.github/workflows/auto-approve.yaml"
echo "old: true" > "$d/.github/workflows/auto-approve.yml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "both: rc" "2" "$rc"
check "both: adopts .yaml" "yes" "$([[ -f "$d/.github/workflows/auto-approve.yaml.new" ]] && echo yes || echo no)"
check "both: warns about the duplicate" "yes" "$(grep -qi 'also exists' <<<"$out" && echo yes || echo no)"

# --- symlinks are refused, and their targets left alone ---------------------
# A clone keeps a committed symlink; writing through one lands the caller (or
# its .new) wherever the target repo pointed it.
OUTSIDE="$WORK/outside"
mkdir -p "$OUTSIDE"
echo "victim" > "$OUTSIDE/victim.yaml"
d=$(fixture link_file)
ln -s "$OUTSIDE/victim.yaml" "$d/.github/workflows/auto-approve.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link file: rc" "1" "$rc"
check "link file: target untouched" "victim" "$(cat "$OUTSIDE/victim.yaml")"
check "link file: names the link" "yes" "$(grep -q 'is a symlink' <<<"$out" && echo yes || echo no)"

d=$(fixture link_new)
echo "old: true" > "$d/.github/workflows/auto-approve.yaml"
ln -s "$OUTSIDE/victim.yaml" "$d/.github/workflows/auto-approve.yaml.new"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link .new: rc" "1" "$rc"
check "link .new: target untouched" "victim" "$(cat "$OUTSIDE/victim.yaml")"

d=$(fixture link_dir)
rm -rf "$d/.github"
mkdir -p "$OUTSIDE/gh"
ln -s "$OUTSIDE/gh" "$d/.github"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link dir: rc" "1" "$rc"
check "link dir: nothing written outside" "0" "$(find "$OUTSIDE/gh" -type f | wc -l | tr -d ' ')"

# --- missing source is distinguishable from a failed write ------------------
FAKE="$WORK/fakeplugin"
mkdir -p "$FAKE/scripts"
cp "$INSTALLER" "$FAKE/scripts/"
d=$(fixture nosource)
out=$("$FAKE/scripts/install-auto-approve.sh" "$d" 2>&1); rc=$?
check "missing source: rc" "3" "$rc"

# --- caller <-> callee contract ---------------------------------------------
# These four break in the ~25 CONSUMING repos, not here, so nothing in this
# repo's normal feedback loop would ever show them.
CALLEE="$HERE/../.github/workflows/auto-approve.yaml"

# A caller may name a secret only if the callee declares it under
# on.workflow_call.secrets. Naming an undeclared one makes GitHub reject the
# CALLER's workflow file outright, in the other repo.
caller_secrets=$(python3 -c "
import yaml,sys
d=yaml.safe_load(open('$SOURCE'))
j=list(d['jobs'].values())[0]
print(','.join(sorted((j.get('secrets') or {}).keys())))
")
callee_secrets=$(python3 -c "
import yaml,sys
d=yaml.safe_load(open('$CALLEE'))
wc=(d[True] if True in d else d['on'])['workflow_call']
print(','.join(sorted(((wc or {}).get('secrets') or {}).keys())))
")
check "contract: caller secrets declared by callee" "$caller_secrets" \
  "$(comm -12 <(tr ',' '\n' <<<"$caller_secrets" | sort) <(tr ',' '\n' <<<"$callee_secrets" | sort) | paste -sd, -)"

# The caller's job permissions are the ceiling on the callee's token. A scope
# the callee declares but the caller lacks is a startup validation error in
# every consumer ("The workflow is requesting 'checks: read', but is only
# allowed 'checks: none'"). No step runs, no verdict posts, and nothing
# changes on their side. Passing here is necessary, not sufficient: consumers must
# also have VENDORED the new caller before the callee change merges.
missing_perms=$(python3 -c "
import yaml
c=yaml.safe_load(open('$SOURCE')); e=yaml.safe_load(open('$CALLEE'))
cp=list(c['jobs'].values())[0].get('permissions') or {}
ep=e.get('permissions') or {}
print(','.join(sorted(k for k in ep if k not in cp)) or 'none')
")
check "contract: caller grants every scope the callee declares" "none" "$missing_perms"

# Code lines only. The caller carries a comment WARNING against
# `secrets: inherit`, and a plain grep matches that and reports the file as
# using it, the same prose-matching trap as init's install probe.
check "contract: caller never uses secrets: inherit" "yes" \
  "$(grep -vE '^\s*#' "$SOURCE" | grep -q 'secrets: *inherit' && echo no || echo yes)"

# The caller must track this repo's DEFAULT branch. A tag or SHA here means a
# fix to the shared workflow is not live until a PR lands in each of ~25
# consumers; a non-default branch means the fleet runs code that main's branch
# protection never gated. Both fail silently: consumers keep running the old
# workflow with nothing red anywhere. So assert the ref explicitly.
caller_ref=$(grep -oE 'auto-approve\.ya?ml@[A-Za-z0-9._/-]+' "$SOURCE" | head -1 | cut -d@ -f2)
check "contract: caller tracks main" "main" "$caller_ref"

# --- trigger anchoring -------------------------------------------------------
# Reads as a style preference; it is not. With `contains`, merely MENTIONING
# the command in any comment posted a real APPROVE, and review-pr's
# self-review comment does exactly that while also carrying the marker the
# prior-review gate accepts, one comment both fired the run and satisfied the
# gate meant to stop auto-approve being the only review.
trigger_if=$(python3 -c "
import yaml
print(yaml.safe_load(open('$CALLEE'))['jobs']['claude-approve']['if'])
")
check "trigger: anchored with startsWith" "yes" \
  "$(grep -qF 'startsWith(github.event.comment.body' <<<"$trigger_if" && echo yes || echo no)"
# The exact dangerous form, not just "contains(", the condition legitimately
# uses !contains(...) to exclude self-review comments.
UNANCHORED="contains(github.event.comment.body, '@auto-approve')"
check "trigger: unanchored contains is gone" "yes" \
  "$(grep -oF "$UNANCHORED" <<<"$trigger_if" | grep -qv '^!' && echo no || echo yes)"
check "trigger: self-review comments excluded" "yes" \
  "$(grep -q 'ai-hero:self-review' <<<"$trigger_if" && echo yes || echo no)"
check "trigger: author_association gate intact" "yes" \
  "$(grep -q 'author_association' <<<"$trigger_if" && echo yes || echo no)"

echo ""
echo "install-auto-approve.test.sh: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
