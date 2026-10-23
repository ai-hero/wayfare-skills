#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for install-design-system.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (2 is contract, not
# failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/install-design-system.sh"
SRC_RULE="$HERE/../assets/design-system/rules/design-system.md"

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

# --- fresh install ----------------------------------------------------------
d=$(fixture fresh)
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "fresh: rc" "0" "$rc"
check "fresh: rule matches source" "same" "$(cmp -s "$SRC_RULE" "$d/.claude/rules/design-system.md" && echo same || echo differs)"
check "fresh: hook executable" "yes" "$([[ -x "$d/.claude/hooks/check-design-tokens.sh" ]] && echo yes || echo no)"
check "fresh: local stub created" "yes" "$([[ -f "$d/.claude/rules/design-system.local.md" ]] && echo yes || echo no)"
check "fresh: no temp left behind" "0" "$(find "$d/.claude" -name '.*' -type f | wc -l | tr -d ' ')"

# --- symlinks are refused, and their targets left alone ---------------------
# A clone keeps a committed symlink, so `.claude/rules -> ~/.claude/rules`
# would put this repo's rule into every session on the machine.
OUTSIDE="$WORK/outside"
mkdir -p "$OUTSIDE/rules"
echo "victim" > "$OUTSIDE/victim.md"

d=$(fixture link_file)
mkdir -p "$d/.claude/rules"
ln -s "$OUTSIDE/victim.md" "$d/.claude/rules/design-system.md"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link file: rc" "1" "$rc"
check "link file: target untouched" "victim" "$(cat "$OUTSIDE/victim.md")"
check "link file: names the link" "yes" "$(grep -q 'is a symlink' <<<"$out" && echo yes || echo no)"

d=$(fixture link_new)
mkdir -p "$d/.claude/rules"
echo "drifted" > "$d/.claude/rules/design-system.md"
ln -s "$OUTSIDE/victim.md" "$d/.claude/rules/design-system.md.new"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "link .new: rc" "1" "$rc"
check "link .new: target untouched" "victim" "$(cat "$OUTSIDE/victim.md")"

d=$(fixture link_dir)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/rules" "$d/.claude/rules"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "link dir: rc" "1" "$rc"
check "link dir: nothing written outside" "0" "$(find "$OUTSIDE/rules" -type f | wc -l | tr -d ' ')"

# settings.json decides which hooks run. A live link would have its target
# read and copied into the repo; a dangling one would be created by `echo '{}' >`.
echo '{"mine": true}' > "$OUTSIDE/settings.json"
d=$(fixture link_settings)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/settings.json" "$d/.claude/settings.json"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "link settings: rc" "1" "$rc"
check "link settings: target untouched" '{"mine": true}' "$(cat "$OUTSIDE/settings.json")"
check "link settings: still a link" "yes" "$([[ -L "$d/.claude/settings.json" ]] && echo yes || echo no)"
# Refused before the first write, so nothing is half-installed.
check "link settings: nothing installed" "no" "$([[ -e "$d/.claude/rules/design-system.md" ]] && echo yes || echo no)"

d=$(fixture dangling_settings)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/absent-settings.json" "$d/.claude/settings.json"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "dangling settings: rc" "1" "$rc"
check "dangling settings: target not created" "no" "$([[ -e "$OUTSIDE/absent-settings.json" ]] && echo yes || echo no)"

echo ""
echo "install-design-system.test.sh: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
