#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for hooks/check-deferrals.sh, the plugin's Stop hook.
#
# The two failures that matter: blocking forever (stop_hook_active ignored),
# and blocking a turn that already filed its deferral.
#
# Usage: bash scripts/check-deferrals.test.sh

set -uo pipefail

HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/check-deferrals.sh"

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

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not installed"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# A commit hook runs this with GIT_INDEX_FILE (and friends) pointing at the
# outer repo; left set, every fixture `git add` writes into that real index.
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)

git init -q "$TMP/repo" && mkdir -p "$TMP/repo/.plans/items"
git init -q "$TMP/plain"

user()      { jq -cn --arg t "$1" '{type:"user",message:{role:"user",content:$t}}'; }
tool_res()  { jq -cn '{type:"user",message:{role:"user",content:[{type:"tool_result",tool_use_id:"x",content:"ok"}]}}'; }
said()      { jq -cn --arg t "$1" '{type:"assistant",message:{role:"assistant",content:[{type:"text",text:$t}]}}'; }
wrote()     { jq -cn --arg p "$1" '{type:"assistant",message:{role:"assistant",content:[{type:"tool_use",name:"Write",input:{file_path:$p,content:"x"}}]}}'; }

run() { # CWD TRANSCRIPT [STOP_ACTIVE] [LAST_MESSAGE]
  jq -cn --arg c "$1" --arg t "$2" --argjson a "${3:-false}" --arg m "${4:-}" \
    '{session_id:"s",cwd:$c,transcript_path:$t,hook_event_name:"Stop",stop_hook_active:$a}
     + (if $m == "" then {} else {last_assistant_message:$m} end)' \
    | bash "$HOOK" | jq -r '.decision // empty' 2>/dev/null
}

T="$TMP/defer.jsonl"
{ user "fix the login bug"; said "Fixed it. The retry logic is out of scope, left as a follow-up."; } > "$T"
check "deferral with no .plans write blocks" "block" "$(run "$TMP/repo" "$T")"
check "stop_hook_active never blocks" "" "$(run "$TMP/repo" "$T" true)"
check "repo without .plans is a no-op" "" "$(run "$TMP/plain" "$T")"
check "outside git is a no-op" "" "$(run "$TMP" "$T")"

T="$TMP/filed.jsonl"
{ user "fix the login bug"; wrote "$TMP/repo/.plans/items/007-retry.md"; tool_res; said "Done; the retry is out of scope, filed as item 7."; } > "$T"
check "turn that wrote .plans/ passes" "" "$(run "$TMP/repo" "$T")"

T="$TMP/earlier.jsonl"
{ user "first"; wrote "$TMP/repo/.plans/items/001-a.md"; tool_res; said "ok"; user "second"; said "Deferred the cache work."; } > "$T"
check "a .plans write from an earlier turn does not count" "block" "$(run "$TMP/repo" "$T")"

T="$TMP/clean.jsonl"
{ user "fix it"; said "Fixed. Next step: wayfare:wayfare-ship-pr"; } > "$T"
check "a Next step line is not a deferral" "" "$(run "$TMP/repo" "$T")"

T="$TMP/tools.jsonl"
{ user "fix it"; said "Looking."; tool_res; said "Fixed; one known gap remains."; } > "$T"
check "tool results do not end the turn" "block" "$(run "$TMP/repo" "$T")"

check "last_assistant_message is preferred when present" "" \
  "$(run "$TMP/repo" "$TMP/tools.jsonl" false "All fixed.")"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
