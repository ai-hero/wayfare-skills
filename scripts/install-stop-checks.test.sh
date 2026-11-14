#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for install-stop-checks.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (2 is contract, not
# failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/install-stop-checks.sh"
SRC_HOOK="$HERE/../assets/stop-checks/hooks/stop-checks.sh"

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

stop_entries() { jq '[.hooks.Stop[]?.hooks[]? | select(.command | test("stop-checks"))] | length' "$1"; }

# --- fresh install ----------------------------------------------------------
d=$(fixture fresh)
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "fresh: rc" "0" "$rc"
check "fresh: hook matches source" "same" "$(cmp -s "$SRC_HOOK" "$d/.claude/hooks/stop-checks.sh" && echo same || echo differs)"
check "fresh: hook executable" "yes" "$([[ -x "$d/.claude/hooks/stop-checks.sh" ]] && echo yes || echo no)"
check "fresh: wired once" "1" "$(stop_entries "$d/.claude/settings.json")"
check "fresh: no temp left behind" "0" "$(find "$d/.claude" -name '.*' -type f | wc -l | tr -d ' ')"

# --- re-run is a no-op ------------------------------------------------------
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "rerun: rc" "0" "$rc"
check "rerun: still wired once" "1" "$(stop_entries "$d/.claude/settings.json")"

# --- existing hooks are kept, a braced spelling counts as wired -------------
d=$(fixture existing)
mkdir -p "$d/.claude"
# shellcheck disable=SC2016
printf '%s\n' '{"hooks":{"PostToolUse":[{"matcher":"Write|Edit","hooks":[{"type":"command","command":"x.sh"}]}],"Stop":[{"hooks":[{"type":"command","command":"\"${CLAUDE_PROJECT_DIR}/.claude/hooks/stop-checks.sh\""}]}]},"permissions":{"deny":["Read(/a)"]}}' >"$d/.claude/settings.json"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "existing: rc" "0" "$rc"
check "existing: braced spelling not duplicated" "1" "$(stop_entries "$d/.claude/settings.json")"
check "existing: PostToolUse kept" "x.sh" "$(jq -r '.hooks.PostToolUse[0].hooks[0].command' "$d/.claude/settings.json")"
check "existing: permissions kept" "Read(/a)" "$(jq -r '.permissions.deny[0]' "$d/.claude/settings.json")"

# --- drift writes .new and exits 2 ------------------------------------------
d=$(fixture drift)
mkdir -p "$d/.claude/hooks"
echo "local patch" >"$d/.claude/hooks/stop-checks.sh"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "drift: rc" "2" "$rc"
check "drift: original untouched" "local patch" "$(cat "$d/.claude/hooks/stop-checks.sh")"
check "drift: .new is the source" "same" "$(cmp -s "$SRC_HOOK" "$d/.claude/hooks/stop-checks.sh.new" && echo same || echo differs)"

# --- invalid settings.json is refused ---------------------------------------
d=$(fixture badjson)
mkdir -p "$d/.claude"
echo '{not json' >"$d/.claude/settings.json"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "bad json: rc" "1" "$rc"
check "bad json: left as is" "{not json" "$(cat "$d/.claude/settings.json")"

# --- symlinks are refused, and their targets left alone ---------------------
OUTSIDE="$WORK/outside"
mkdir -p "$OUTSIDE/hooks"
echo '{"mine": true}' >"$OUTSIDE/settings.json"

d=$(fixture link_dir)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/hooks" "$d/.claude/hooks"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "link dir: rc" "1" "$rc"
check "link dir: nothing written outside" "0" "$(find "$OUTSIDE/hooks" -type f | wc -l | tr -d ' ')"

d=$(fixture link_settings)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/settings.json" "$d/.claude/settings.json"
"$INSTALLER" "$d" >/dev/null 2>&1; rc=$?
check "link settings: rc" "1" "$rc"
check "link settings: target untouched" '{"mine": true}' "$(cat "$OUTSIDE/settings.json")"
check "link settings: nothing installed" "no" "$([[ -e "$d/.claude/hooks/stop-checks.sh" ]] && echo yes || echo no)"

# --- a missing recipe is reported, not fatal --------------------------------
d=$(fixture norecipe)
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "no recipe: rc" "0" "$rc"
check "no recipe: noted" "yes" "$(grep -q 'no check-fast recipe' <<<"$out" && echo yes || echo no)"

d=$(fixture recipe)
printf 'check-fast: lint\n' >"$d/Justfile"
out=$("$INSTALLER" "$d" 2>&1)
check "recipe present: no note" "no" "$(grep -q 'no check-fast recipe' <<<"$out" && echo yes || echo no)"

echo ""
echo "install-stop-checks.test.sh: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
