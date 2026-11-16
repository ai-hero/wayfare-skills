#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression coverage for preflight.sh's pr-review-toolkit detection.
#
# Scoped to the one thing that broke: a marketplace install never lands at
# either legacy directory probe (it writes to
# plugins/cache/MARKETPLACE/PLUGIN/SHA, recorded in installed_plugins.json),
# so the WARN fired on every correctly-installed marketplace plugin. These
# cases pin the installed_plugins.json lookup and its fallback to the legacy
# directories, plus the WARN's step-number text.
#
# HOME is overridden per case so the real machine's plugin state (whatever it
# is) never leaks into the assertion.
#
# Usage: bash scripts/preflight.test.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/preflight.sh"

PASS=0
FAIL=0
check() { # name  expected_contains  actual
  case "$3" in
    *"$2"*) PASS=$((PASS + 1)) ;;
    *)
      FAIL=$((FAIL + 1))
      printf 'FAIL  %s\n      expected to contain: [%s]\n      actual:              [%s]\n' "$1" "$2" "$3"
      ;;
  esac
}
check_absent() { # name  unexpected_substring  actual
  case "$3" in
    *"$2"*)
      FAIL=$((FAIL + 1))
      printf 'FAIL  %s\n      expected NOT to contain: [%s]\n      actual:                  [%s]\n' "$1" "$2" "$3"
      ;;
    *) PASS=$((PASS + 1)) ;;
  esac
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run_tooling() { # FAKE_HOME -> pr-review-toolkit line from --bucket tooling
  HOME="$1" "$SCRIPT" --bucket tooling 2>&1 | grep -i 'pr-review-toolkit'
}

# Broader than run_tooling: the malformed-JSON WARN doesn't mention
# "pr-review-toolkit" (it's about installed_plugins.json itself), so this
# captures both that line and the plugin-detection line together.
run_tooling_full() { # FAKE_HOME -> full --bucket tooling output
  HOME="$1" "$SCRIPT" --bucket tooling 2>&1 | grep -iE 'pr-review-toolkit|installed_plugins\.json'
}

# Case 1: marketplace install recorded in installed_plugins.json, no legacy
# directory present -> OK. This is the regression case: before the fix, this
# state produced a WARN on every run.
FAKE_HOME_1="$TMP/marketplace-only"
mkdir -p "$FAKE_HOME_1/.claude/plugins"
printf '{"plugins": {"pr-review-toolkit@claude-plugins-official": [{"scope": "user", "installPath": "x"}]}}' \
  > "$FAKE_HOME_1/.claude/plugins/installed_plugins.json"
OUT1=$(run_tooling "$FAKE_HOME_1")
check "marketplace-only install -> OK" "OK" "$OUT1"

# Case 2: installed_plugins.json absent, legacy directory present -> OK
# (fallback path stays live for a hand-placed, non-marketplace install).
FAKE_HOME_2="$TMP/legacy-only"
mkdir -p "$FAKE_HOME_2/.claude/plugins/pr-review-toolkit"
OUT2=$(run_tooling "$FAKE_HOME_2")
check "legacy-directory-only install -> OK" "OK" "$OUT2"

# Case 3: installed_plugins.json present but lacking the key, no legacy
# directory -> WARN, with the corrected step number.
FAKE_HOME_3="$TMP/neither"
mkdir -p "$FAKE_HOME_3/.claude/plugins"
printf '{"plugins": {}}' > "$FAKE_HOME_3/.claude/plugins/installed_plugins.json"
OUT3=$(run_tooling "$FAKE_HOME_3")
check "no install anywhere -> WARN" "WARN" "$OUT3"
check "WARN cites the corrected step" "Step 5" "$OUT3"

# Case 4: installed_plugins.json is present but not valid JSON, no legacy
# directory -> a distinct WARN naming the malformed file, not silently read
# as "key absent". Pins the fix for a corrupted state file being conflated
# with "plugin not installed".
FAKE_HOME_4="$TMP/malformed"
mkdir -p "$FAKE_HOME_4/.claude/plugins"
printf '{not valid json' > "$FAKE_HOME_4/.claude/plugins/installed_plugins.json"
OUT4=$(run_tooling_full "$FAKE_HOME_4")
check "malformed JSON -> distinct WARN naming installed_plugins.json" "installed_plugins.json is present but unreadable/malformed" "$OUT4"

# Case 5: installed_plugins.json matches, but jq is not on PATH, no legacy
# directory -> falls back to the (correctly negative) directory probe, same
# as if the file were absent. `command -v jq` only reports the FIRST PATH hit,
# but a runner can have jq reachable from more than one directory (a distro
# package plus a language-toolchain shim, e.g.), shadowing only that one
# match left the real jq reachable from a later directory on Linux CI while
# passing on macOS. Instead, walk every PATH entry and shadow (as symlinks to
# every OTHER binary) any directory that itself contains a `jq` executable,
# so no directory in the rebuilt PATH can resolve jq.
SHADOW_ROOT="$TMP/shadow-no-jq"
NO_JQ_PATH=""
i=0
# `IFS=` scopes to the read, so the global stays untouched: a global IFS=':'
# changes how EVERY later unquoted expansion in this file splits, and the
# restore only runs if nothing between here and it exits first.
# The here-doc (not a pipe) keeps the loop in this shell, a `|` would run it
# in a subshell and NO_JQ_PATH would come back empty, silently rebuilding the
# PATH as "" and testing nothing.
while IFS= read -r dir; do
  i=$((i + 1))
  if [ -n "$dir" ] && [ -x "$dir/jq" ]; then
    shadow="$SHADOW_ROOT/$i"
    mkdir -p "$shadow"
    for f in "$dir"/*; do
      base="$(basename "$f")"
      [ "$base" = "jq" ] && continue
      ln -s "$f" "$shadow/$base" 2>/dev/null
    done
    dir="$shadow"
  fi
  NO_JQ_PATH="${NO_JQ_PATH:+$NO_JQ_PATH:}$dir"
done <<EOF
$(printf '%s' "$PATH" | tr ':' '\n')
EOF
FAKE_HOME_5="$TMP/no-jq"
mkdir -p "$FAKE_HOME_5/.claude/plugins"
printf '{"plugins": {"pr-review-toolkit@claude-plugins-official": [{"scope": "user", "installPath": "x"}]}}' \
  > "$FAKE_HOME_5/.claude/plugins/installed_plugins.json"
OUT5=$(HOME="$FAKE_HOME_5" PATH="$NO_JQ_PATH" "$SCRIPT" --bucket tooling 2>&1 | grep -i 'pr-review-toolkit')
check "jq unavailable, no legacy dir -> WARN (JSON lookup skipped)" "WARN" "$OUT5"

# Case 6: both the JSON record and a legacy directory are present -> OK,
# with no malformed-JSON warning riding along (confirms the short-circuit:
# the legacy loop is skipped once the JSON check already succeeded).
FAKE_HOME_6="$TMP/both"
mkdir -p "$FAKE_HOME_6/.claude/plugins/pr-review-toolkit"
printf '{"plugins": {"pr-review-toolkit@claude-plugins-official": [{"scope": "user", "installPath": "x"}]}}' \
  > "$FAKE_HOME_6/.claude/plugins/installed_plugins.json"
OUT6=$(run_tooling_full "$FAKE_HOME_6")
check "both present -> OK" "OK" "$OUT6"
check_absent "both present -> no malformed warning" "malformed" "$OUT6"

# ---------- the issues connection's tracker probe --------------------------
# Three emit-level behaviours, all new: the compat chain that keeps an
# unmigrated repo readable, the BLOCKER on a refused type, and the `self` arm.
# Each fails silently in the direction of "no tracker configured", which reads
# as a clean repo rather than an unchecked one.

run_pipeline() { # REPO -> the pipeline lines
  ( cd "$1" && "$SCRIPT" --bucket pipeline 2>&1 ) | grep -i 'tracker\|issues connection\|github-issues\|linear'
}
mkrepo_pf() { # DIR
  mkdir -p "$1"
  git -C "$1" init -q 2>/dev/null
  git -C "$1" config user.email t@example.com
  git -C "$1" config user.name t
}

PF="$TMP/pf"
mkrepo_pf "$PF/legacy"
printf '# Hero\n\n## Project Management\n\n- tool: linear\n' > "$PF/legacy/HERO.md"
OUT_PF1=$(run_pipeline "$PF/legacy")
check "unmigrated tracker is still checked" "linear" "$OUT_PF1"

mkrepo_pf "$PF/refused"
printf '# Hero\n\n## Connections\n\n### issues\n\n- type: -evil\n' > "$PF/refused/HERO.md"
OUT_PF2=$(run_pipeline "$PF/refused")
check "a refused tracker type is a BLOCKER, not 'none configured'" "REJECTED" "$OUT_PF2"
check_absent "and it does not report the repo as tracker-less" "no issue tracker configured" "$OUT_PF2"

mkrepo_pf "$PF/self"
printf '# Hero\n\n## Connections\n\n### issues\n\n- type: self\n' > "$PF/self/HERO.md"
OUT_PF3=$(run_pipeline "$PF/self")
check_absent "type self is a known tracker, not an unknown one" "unknown issue tracker" "$OUT_PF3"

# Claude Code older than v2.1.277 does not load AGENTS.md; a stub claude on
# PATH stands in for the installed version.
CCV="$TMP/ccver"; mkdir -p "$CCV/bin" "$CCV/home"
for v in 2.1.276 2.1.277 2.2.0 10.0.0; do
  printf '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "%s (Claude Code)"; fi\n' "$v" > "$CCV/bin/claude"
  chmod +x "$CCV/bin/claude"
  OUT_CC=$(HOME="$CCV/home" PATH="$CCV/bin:$PATH" "$SCRIPT" --bucket tooling 2>&1)
  case "$v" in
    2.1.276) check "claude $v: warns AGENTS.md will not load" "AGENTS.md will not load" "$OUT_CC" ;;
    *) check_absent "claude $v: no AGENTS.md warning" "AGENTS.md will not load" "$OUT_CC" ;;
  esac
done
printf '#!/bin/sh\necho "claude: command failed"\n' > "$CCV/bin/claude"
OUT_CC=$(HOME="$CCV/home" PATH="$CCV/bin:$PATH" "$SCRIPT" --bucket tooling 2>&1)
check "claude with no version: warns it could not read one" "could not read a version" "$OUT_CC"

echo ""
echo "preflight.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
