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
tool()      { jq -cn --arg n "$1" --argjson i "$2" '{type:"assistant",message:{role:"assistant",content:[{type:"tool_use",name:$n,input:$i}]}}'; }
meta()      { jq -cn --arg t "$1" '{type:"user",isMeta:true,message:{role:"user",content:$t}}'; }

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
{ user "first"; wrote "$TMP/repo/.plans/items/001-a.md"; tool_res; said "ok"; user "second"; said "Left the cache work for a follow-up."; } > "$T"
check "a .plans write from an earlier turn does not count" "block" "$(run "$TMP/repo" "$T")"

T="$TMP/clean.jsonl"
{ user "fix it"; said "Fixed. Next step: wayfare:wayfare-ship-pr"; } > "$T"
check "a Next step line is not a deferral" "" "$(run "$TMP/repo" "$T")"

T="$TMP/tools.jsonl"
{ user "fix it"; said "Looking."; tool_res; said "Fixed; one known gap remains."; } > "$T"
check "tool results do not end the turn" "block" "$(run "$TMP/repo" "$T")"

check "last_assistant_message is preferred when present" "" \
  "$(run "$TMP/repo" "$TMP/tools.jsonl" false "All fixed.")"

# Wayfare's own report lines carry these words without deferring anything.
for m in \
  "22 (from 13) → not admitted, follow-up ground: unrelated log-format refactor" \
  "An item that is not admitted is named in the report as follow-up ground." \
  "PR state: Draft (mark-ready deferred to caller)" \
  "Pushed two follow-ups to the review thread."; do
  T="$TMP/own.jsonl"
  { user "go"; said "$m"; } > "$T"
  check "wayfare's own line does not block: $m" "" "$(run "$TMP/repo" "$T")"
done

for m in \
  "Fixed. The cache is left for a follow-up." \
  "Fixed. I'll open a follow-up PR for the cache." \
  "Fixed. I'd leave the cache work for later." \
  "Fixed. We can handle the cache as a follow-up."; do
  T="$TMP/defers.jsonl"
  { user "go"; said "$m"; } > "$T"
  check "a real deferral blocks: $m" "block" "$(run "$TMP/repo" "$T")"
done

for m in \
  "The cache work is out of scope; item 12 covers it." \
  "The cache work is out of scope; see #12." \
  "The cache work is out of scope, already in .plans/items/012-cache.md."; do
  T="$TMP/cited.jsonl"
  { user "go"; said "$m"; } > "$T"
  check "a message citing an item does not block: $m" "" "$(run "$TMP/repo" "$T")"
done

T="$TMP/read.jsonl"
{ user "fix it"
  tool Read "{\"file_path\":\"$TMP/repo/.plans/items/001-a.md\"}"; tool_res
  tool Grep '{"pattern":"cache","path":".plans/"}'; tool_res
  tool Bash '{"command":"cat .plans/items/*.md | grep cache > /dev/null"}'; tool_res
  said "Fixed; the cache is out of scope."; } > "$T"
check "reading .plans/ is not filing" "block" "$(run "$TMP/repo" "$T")"

for c in \
  'cat > .plans/items/012-cache.md <<EOF' \
  'printf x >> "$(hero_store_path)/items/012-cache.md"' \
  'echo note | tee -a .plans/items/003-x.md' \
  'hero_msg_deposit "$S" "$ID" body.md'; do
  T="$TMP/bashwrite.jsonl"
  { user "fix it"; tool Bash "$(jq -cn --arg c "$c" '{command:$c}')"; tool_res
    said "Fixed; the cache is out of scope."; } > "$T"
  check "a Bash write into the store counts: $c" "" "$(run "$TMP/repo" "$T")"
done

T="$TMP/edit.jsonl"
{ user "fix it"; tool Edit "{\"file_path\":\"$TMP/repo/.plans/items/001-a.md\",\"old_string\":\"a\",\"new_string\":\"b\"}"; tool_res
  said "Fixed; the cache is out of scope."; } > "$T"
check "an Edit under .plans/ counts" "" "$(run "$TMP/repo" "$T")"

T="$TMP/meta.jsonl"
{ user "fix it"; wrote "$TMP/repo/.plans/items/007-retry.md"; tool_res
  meta "<system-reminder>context</system-reminder>"
  user "<task-notification>agent finished</task-notification>"
  said "Done; the retry is out of scope."; } > "$T"
check "isMeta and task notifications do not start a turn" "" "$(run "$TMP/repo" "$T")"

# Malformed input must never trap a session: exit 0, nothing on stdout.
raw() { printf '%s' "$1" | bash "$HOOK"; echo "rc=$?"; }
check "malformed stdin" "rc=0" "$(raw 'not json {')"
check "empty stdin" "rc=0" "$(raw '')"
T="$TMP/garbage.jsonl"
{ user "go"; echo '{"type":"assistant","message":'; said "Out of scope, left for later."; } > "$T"
check "malformed transcript line" "rc=0" \
  "$(raw "$(jq -cn --arg c "$TMP/repo" --arg t "$T" '{cwd:$c,transcript_path:$t,stop_hook_active:false}')")"
check "missing transcript" "rc=0" \
  "$(raw "$(jq -cn --arg c "$TMP/repo" '{cwd:$c,transcript_path:"/nonexistent/x.jsonl"}')")"

# The command runs through a shell, so an unquoted path splits at a space in
# the plugin root and the hook never runs.
PR_ROOT="$TMP/plugin root"
mkdir -p "$PR_ROOT/hooks" "$PR_ROOT/scripts"
cp "$HOOK" "$PR_ROOT/hooks/" && cp "$(dirname "$HOOK")/../scripts/hero-lib.sh" "$PR_ROOT/scripts/"
chmod +x "$PR_ROOT/hooks/check-deferrals.sh"
CMD=$(jq -r '.hooks.Stop[0].hooks[0].command' "$(dirname "$HOOK")/hooks.json")
check "hooks.json command survives a plugin root with a space" "block" \
  "$(jq -cn --arg c "$TMP/repo" --arg t "$TMP/defer.jsonl" '{cwd:$c,transcript_path:$t,stop_hook_active:false}' \
     | CLAUDE_PLUGIN_ROOT="$PR_ROOT" sh -c "$CMD" | jq -r '.decision // empty' 2>/dev/null)"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
