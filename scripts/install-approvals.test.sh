#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for install-approvals.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (2 and 3 are contract, not
# failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/install-approvals.sh"
SOURCE="$HERE/../assets/approvals/approvals.yaml"

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
  mkdir -p "$d"
  echo "$d"
}

yes_no() { "$@" && echo yes || echo no; }

# --- fresh install ----------------------------------------------------------
d=$(fixture fresh)
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "fresh: rc" "0" "$rc"
check "fresh: matches source" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml")"

out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "rerun: rc" "0" "$rc"
check "rerun: no .new" "yes" "$(yes_no test ! -e "$d/.claude/approvals.yaml.new")"

# --- a .gitignore that hides the policy is reported, not staged blind -------
d=$(fixture ignored)
git -C "$d" init -q
printf '.claude/*\n!.claude/rules/\n' > "$d/.gitignore"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "ignored: rc" "4" "$rc"
check "ignored: names the negation" "yes" "$(yes_no grep -qF '!.claude/approvals.yaml' <<<"$out")"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "ignored, already current: rc" "4" "$rc"
printf '.claude/*\n!.claude/rules/\n!.claude/approvals.yaml\n' > "$d/.gitignore"
rm "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "negated: rc" "0" "$rc"

# --- a different file is never overwritten ----------------------------------
d=$(fixture differs)
mkdir -p "$d/.claude"
echo "version: 1" > "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "differs: rc" "2" "$rc"
check "differs: original kept" "version: 1" "$(cat "$d/.claude/approvals.yaml")"
check "differs: .new written" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml.new")"

# --- an existing .yml would shadow the vendored .yaml ------------------------
d=$(fixture yml)
mkdir -p "$d/.claude"
echo "version: 1" > "$d/.claude/approvals.yml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "yml: rc" "2" "$rc"
check "yml: no .yaml written beside it" "yes" "$(yes_no test ! -e "$d/.claude/approvals.yaml")"

# --- symlinks are refused ---------------------------------------------------
OUTSIDE="$WORK/outside"
mkdir -p "$OUTSIDE"
echo "victim" > "$OUTSIDE/victim.yml"
d=$(fixture link_file)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/victim.yml" "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link file: rc" "1" "$rc"
check "link file: target untouched" "victim" "$(cat "$OUTSIDE/victim.yml")"

d=$(fixture link_dir)
mkdir -p "$OUTSIDE/claude"
ln -s "$OUTSIDE/claude" "$d/.claude"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link dir: rc" "1" "$rc"
check "link dir: nothing written outside" "0" "$(find "$OUTSIDE/claude" -type f | wc -l | tr -d ' ')"

# --- missing source ---------------------------------------------------------
FAKE="$WORK/fakeplugin"
mkdir -p "$FAKE/scripts"
cp "$INSTALLER" "$FAKE/scripts/"
d=$(fixture nosource)
out=$("$FAKE/scripts/install-approvals.sh" "$d" 2>&1); rc=$?
check "missing source: rc" "3" "$rc"

# --- the asset itself -------------------------------------------------------
# Enforce mode lands fleet-wide in one re-vendor; it must be a deliberate edit
# to this assertion, not a side effect of refreshing the starter policy.
check "asset: observe mode" "yes" "$(yes_no grep -qx 'mode: observe' "$SOURCE")"
check "asset: parses as YAML with version 1" "1" \
  "$(uv run --quiet --no-project --with pyyaml python -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['version'])" "$SOURCE")"

echo "install-approvals: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
