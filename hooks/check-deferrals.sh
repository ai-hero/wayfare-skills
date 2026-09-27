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
[ -d "$(hero_store_path "$ROOT")" ] || exit 0

TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -f "$TRANSCRIPT" ] || exit 0

# The current turn: every entry after the last user message a person typed.
# Tool results arrive as `user` entries too, and so do harness injections
# (`isMeta`, a background task's notification); none of those starts a turn,
# and treating one as the start drops a filing made earlier in the turn.
TURN=$(jq -c -s '
  (to_entries
   | map(select(.value.type == "user"
                and (.value.isMeta | not)
                and ((.value.message.content | type) == "string"
                     and (.value.message.content | startswith("<task-notification>") | not)
                     or any(.value.message.content[]?; .type == "text"))))
   | last | .key) as $start
  | .[(($start // -1) + 1):]' "$TRANSCRIPT" 2>/dev/null) || exit 0

# A turn that wrote to the store already filed something; trust it. Only a
# write counts: a Read or grep of .plans/ is how an agent checks for an item,
# and counting it waved through the very turn that looked and filed nothing.
printf '%s' "$TURN" | jq -e '
  def store_path: test("(^|/)\\.plans/");
  def store_write:
    test("(>>?|\\btee\\b(\\s+-a)?)\\s*[\"'"'"']?[^\\s|;&]*(\\.plans/|STORE|hero_store_path|hero_work_store|hero_items_dir)")
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
printf '%s' "$MESSAGE" | grep -qiE '\bitems? #?[0-9]+|(^|[^[:alnum:]&/])#[0-9]+\b|\.plans/items/' && exit 0

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
