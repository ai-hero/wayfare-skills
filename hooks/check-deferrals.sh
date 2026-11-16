#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# check-deferrals.sh: Stop hook. Catch work the agent deferred and never filed.
#
# When the turn's last assistant message defers work ("out of scope",
# "as a follow-up", "didn't get to") and the turn wrote nothing under .plans/, the
# stop is blocked once, asking the agent to file an item or say why not.
# Only repos with a .plans/ store are checked; everywhere else this is a no-op.
#
# Input: the Stop hook JSON on stdin. Output: a block decision on stdout, or
# nothing. Every failure path exits 0 silently: a broken hook must never trap
# a session.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)

# The block below makes the agent continue, and its next stop arrives with
# stop_hook_active=true. Without this check the hook would block forever.
[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)" = true ] && exit 0

CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$CWD" ] || CWD=$PWD
ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0

HERO_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" 2>/dev/null || exit 0
STORE_PATH=$(hero_store_path "$ROOT")
[ -d "$STORE_PATH" ] || exit 0
STORE_NAME=$(hero_store_name)

TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -f "$TRANSCRIPT" ] || exit 0

# The current turn: every entry after the last user message a person typed.
# Tool results arrive as `user` entries too, and so do harness injections
# (`isMeta`, a background task's notification); none of those starts a turn,
# and treating one as the start drops a filing made earlier in the turn.
TURN_START='def turn_start:
  .type == "user"
  and (.isMeta | not)
  and ((.message.content | type) == "string"
       and (.message.content | startswith("<task-notification>") | not)
       or any(.message.content[]?; .type == "text"));'

# This runs on every Stop, and `jq -s` over a long session's whole transcript
# takes seconds and gigabytes, past the hook's timeout. So read from the end
# and hand jq only the lines from the turn's start. A grep finds candidates
# cheaply, but tool results are `user` entries too, so a candidate is taken
# only once the exact rule above accepts it; one it rejects is walked past,
# never used. A line the grep wrongly skips only widens the slice, because jq
# still picks the last real start inside it.
MAX_MB=${WAYFARE_DEFERRALS_MAX_MB:-512}
case $MAX_MB in '' | *[!0-9]*) MAX_MB=512 ;; esac
SIZE=$(wc -c <"$TRANSCRIPT" 2>/dev/null | tr -d ' ')
[ -n "$SIZE" ] && [ "$SIZE" -le $((MAX_MB * 1048576)) ] || exit 0

# GNU tail's -r is an error and BSD has no tac, so test for tac first.
if command -v tac >/dev/null 2>&1; then
  rev() { tac "$@"; }
elif tail -r </dev/null >/dev/null 2>&1; then
  rev() { tail -r "$@"; }
else
  exit 0
fi

BACK=0
TRIES=0
while IFS= read -r CAND; do
  TRIES=$((TRIES + 1))
  [ "$TRIES" -le 500 ] || exit 0
  if printf '%s' "${CAND#*:}" | jq -e "$TURN_START"' turn_start' >/dev/null 2>&1; then
    BACK=${CAND%%:*}
    break
  fi
done < <(rev "$TRANSCRIPT" 2>/dev/null | grep -n '"type":"user"' | grep -v -e '"type":"tool_result"' -e '"isMeta":true')

if [ "$BACK" -gt 0 ]; then
  SLICE=$(tail -n "$BACK" "$TRANSCRIPT" 2>/dev/null) || exit 0
  [ -n "$SLICE" ] || exit 0
else
  SLICE=$(cat "$TRANSCRIPT" 2>/dev/null) || exit 0
fi
TURN=$(printf '%s\n' "$SLICE" | jq -c -s "$TURN_START"'
  (to_entries | map(select(.value | turn_start)) | last | .key) as $start
  | .[(($start // -1) + 1):]' 2>/dev/null) || exit 0

# A turn that wrote to the store already filed something; trust it. Only a
# write counts: a Read or grep of .plans/ is how an agent checks for an item,
# and counting it waved through the very turn that looked and filed nothing.
printf '%s' "$TURN" | jq -e --arg dir "$STORE_NAME" '
  ($dir | gsub("\\."; "\\.")) as $d
  | def store_path: test("(^|/)" + $d + "/");
  def store_write:
    test("(>>?|\\btee\\b(\\s+-a)?)\\s*[\"'"'"']?[^\\s|;&]*(" + $d + "/|STORE|hero_store_path|hero_work_store|hero_items_dir)")
    or test("\\bhero_(msg_deposit|deploy_pending_add|deploy_pending_clear)\\b|migrate-plan\\.sh");
  any(.[]; .type == "assistant"
      and any(.message.content[]?; .type == "tool_use"
              and (((.name | IN("Write", "Edit", "MultiEdit", "NotebookEdit"))
                    and ((.input.file_path // .input.notebook_path // "") | store_path))
                   or (.name == "Bash" and ((.input.command // "") | store_write)))))' \
  >/dev/null 2>&1 && exit 0

MESSAGE=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
if [ -z "$MESSAGE" ]; then
  MESSAGE=$(printf '%s' "$TURN" | jq -r '
    [.[] | select(.type == "assistant")
         | [.message.content[]? | select(.type == "text") | .text] | join("\n")
         | select(length > 0)] | last // empty' 2>/dev/null)
fi
[ -n "$MESSAGE" ] || exit 0

# A message that names an item already points at where the work is filed.
printf '%s' "$MESSAGE" | grep -qiE '\bitems? #?[0-9]+|(^|[^[:alnum:]&/])#[0-9]+\b|'"${STORE_NAME//./\\.}"'/items/' && exit 0

# Bare "follow-up" and "deferred" stay off this list: wayfare's own reports say
# "follow-up ground" (references/goals.md) and "mark-ready deferred to caller"
# (review-pr), and matching them blocked turns that deferred nothing. Every
# wayfare report also ends in a `Next step:` line, so "next step" stays off too.
PHRASE=$(printf '%s' "$MESSAGE" | grep -oiE \
  "out of scope|as an? follow-?up|(left|leave|leaving|saved?|saving) ([[:alnum:]-]+ ){0,4}for (a |an )?(later|follow-?up)|follow-?up (pr|pull request|change|task|ticket|issue)s?|for a later (pass|pr|round)|didn't get to|did not get to|known gaps?|separate pr|future pr|not in this (pr|pass|change)|deferred (to|until) (a |an )?(later|follow-?up|future|next)" \
  | head -1)
[ -n "$PHRASE" ] || exit 0

jq -n --arg p "$PHRASE" '{
  decision: "block",
  reason: ("Your last message defers work (\"" + $p + "\") but this turn wrote nothing to .plans/. If that is real work, write it as an item (docs/PLAN.md format, status: new) or name the existing item that covers it. If it is not work, say so in one line. Then stop.")
}'
