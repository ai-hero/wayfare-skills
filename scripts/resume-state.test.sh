#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/resume-state.sh.
#
# Scoped to the two things that broke and could break again silently:
#   1. Emitted values that must never be a plausible number when their source
#      failed (the unknown sentinel), and must always set STATE_OK=false.
#   2. Agreement with wayfare-build-task's decision table, two fields were emitted in a
#      shape no table row could ever match, which made six of twelve rows dead
#      with no error anywhere.
#
# `gh` and `git` are stubbed, so this runs offline and deterministically.
#
# Usage: bash scripts/resume-state.test.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/resume-state.sh"
PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A real repo with a remote, so git calls behave; gh is stubbed per-case.
REPO="$TMP/repo"
git init -q "$REPO"
# Repo-local identity so the fixture does not depend on ambient git config.
# A CI runner with no global user.name makes the commit below fail and print a
# `fatal: empty ident name` into the log. Measured: none of the 33 cases
# currently depend on that commit existing, so the failure is cosmetic today,
# the guard is here so it stays that way. If a future case does start depending
# on a real HEAD, the `|| exit 1` below makes the setup failure loud instead of
# letting that case quietly assert against an unborn HEAD.
git -C "$REPO" config user.email "tests@wayfare.invalid"
git -C "$REPO" config user.name "wayfare tests"
git -C "$REPO" commit -q --allow-empty -m init || {
  echo "FATAL: fixture setup failed — could not create the initial commit." >&2
  exit 1
}
printf '# H\n\n- default-branch: main\n- bot-username: reviewbot\n' > "$REPO/HERO.md"

make_gh() { # PR_LIST_JSON COMMENTS_JSON
  mkdir -p "$TMP/bin"
  cat > "$TMP/bin/gh" <<EOF
#!/bin/sh
case "\$*" in
  *"pr list"*) cat <<'PRJSON'
$1
PRJSON
  ;;
  *"api user"*) echo me ;;
  *"api"*) cat <<'CJSON'
$2
CJSON
  ;;
  *) exit 1 ;;
esac
EOF
  chmod +x "$TMP/bin/gh"
}

run() { # -> emits KEY=VALUE lines
  ( cd "$REPO" && CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
      PATH="$TMP/bin:$PATH" bash "$SCRIPT" 2>/dev/null )
}

val() { # KEY  (from $OUT)
  printf '%s\n' "$OUT" | sed -n "s/^$1=//p" | tr -d "'\\\\"
}

# ---------- consumer agreement ---------------------------------------------

# `.isDraft // empty` returns empty for BOTH null and false, so PR_IS_DRAFT
# could never be the string "false", and all three table rows that test for it
# (await-review, respond, ship) were unreachable.
make_gh '[{"number":42,"url":"u","isDraft":false,"reviewDecision":"APPROVED","state":"OPEN"}]' \
        '[{"body":"x","user":{"login":"reviewbot"}}]'
OUT="$(run)"
check "non-draft PR emits the string false" "false" "$(val PR_IS_DRAFT)"
check "non-draft PR: review decision passes through" "APPROVED" "$(val PR_REVIEW)"

make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' '[]'
OUT="$(run)"
check "draft PR emits the string true" "true" "$(val PR_IS_DRAFT)"

# The marker is a plain string anyone can post. Only the authenticated
# account's comment counts, and a plain comment counts for nobody, an empty
# marker would make jq's test("") match every comment and route straight to
# mark-ready.
make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' \
        '[{"body":"lgtm","user":{"login":"reviewbot"}},{"body":"<!-- ai-hero:self-review -->","user":{"login":"stranger"}}]'
OUT="$(run)"
check "self-review: a stranger's marker comment counts 0" "0" "$(val SELF_REVIEW_DONE)"
# A review that posted findings and stopped is NOT done. Both comments carry
# the marker, so counting it routed past Step 5 on a half-finished review and
# ship-pr's prior-review gate then refused the PR for the missing half.
make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' \
        '[{"body":"lgtm","user":{"login":"me"}},{"body":"## Self-Review\n<!-- ai-hero:self-review -->","user":{"login":"me"}}]'
OUT="$(run)"
check "self-review: findings without improvements counts 0" "0" "$(val SELF_REVIEW_DONE)"
make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' \
        '[{"body":"## Self-Review\n<!-- ai-hero:self-review -->","user":{"login":"me"}},{"body":"## Self-Review - Improvements\n<!-- ai-hero:self-review -->","user":{"login":"me"}}]'
OUT="$(run)"
check "self-review: both comments count 1"               "1" "$(val SELF_REVIEW_DONE)"

# `gh pr list` defaults to --state open, so a merged PR returned [] and read as
# "no PR at all", killing the rows that stop a merged branch being re-pushed.
make_gh '[{"number":37,"url":"u","isDraft":false,"reviewDecision":null,"state":"MERGED"}]' '[]'
OUT="$(run)"
check "merged PR is visible"        "true"   "$(val PR_EXISTS)"
check "merged PR reports its state" "MERGED" "$(val PR_STATE)"

# With --state all, a branch carrying an old closed PR and a current open one
# returns both; the open one is the PR this pipeline is working.
make_gh '[{"number":9,"url":"u","isDraft":false,"reviewDecision":null,"state":"CLOSED"},{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' '[]'
OUT="$(run)"
check "prefers the OPEN PR over a closed one" "42" "$(val PR_NUMBER)"

make_gh '[]' '[]'
OUT="$(run)"
check "no PR is false, not unknown" "false" "$(val PR_EXISTS)"
check "no PR: self-review count is a real zero" "0" "$(val SELF_REVIEW_DONE)"

# ---------- the unknown sentinel -------------------------------------------

# A broken jq leaves gh succeeding while every parse yields empty, which read
# as PR_EXISTS=false on a repo with a live PR, routing to push and opening a
# duplicate. Probing that jq WORKS (not that it exists) is what catches it.
make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' '[]'
printf '#!/bin/sh\nexit 127\n' > "$TMP/bin/jq"
chmod +x "$TMP/bin/jq"
OUT="$(run)"
check "broken jq: PR_EXISTS is unknown"  "unknown" "$(val PR_EXISTS)"
check "broken jq: STATE_OK is false"     "false"   "$(val STATE_OK)"
# The scratch repo has no remote, so fetch/default-ref legitimately fail too,
# assert jq is AMONG the named sources, not that it is the only one.
case "$(val STATE_ERRORS)" in
  *jq*) PASS=$((PASS + 1)) ;;
  *) FAIL=$((FAIL + 1)); echo "FAIL  broken jq is named in STATE_ERRORS (got: $(val STATE_ERRORS))" ;;
esac
rm -f "$TMP/bin/jq"

# A HERO.md value the security gate rejects must not degrade to a silent `main`
# with a healthy STATE_OK, every later ref measurement would target the wrong
# branch while reporting fine.
printf '# H\n\n- default-branch: --upload-pack=evil\n- bot-username: reviewbot\n' > "$REPO/HERO.md"
make_gh '[]' '[]'
OUT="$(run)"
check "rejected default-branch falls back to main" "main" "$(val DEFAULT_BRANCH)"
check "rejected default-branch sets STATE_OK=false" "false" "$(val STATE_OK)"
case "$(val STATE_ERRORS)" in
  *default-branch-rejected*) PASS=$((PASS + 1)) ;;
  *) FAIL=$((FAIL + 1)); echo "FAIL  rejected default-branch is named in STATE_ERRORS (got: $(val STATE_ERRORS))" ;;
esac

# A value that is a fine string but not a valid branch, git reads these as
# something other than the branch they resemble.
printf '# H\n\n- default-branch: main:refs/heads/evil\n- bot-username: reviewbot\n' > "$REPO/HERO.md"
OUT="$(run)"
check "invalid branch name falls back to main" "main" "$(val DEFAULT_BRANCH)"
check "invalid branch name sets STATE_OK=false" "false" "$(val STATE_OK)"

# `agent: none` is a supported setting with no bot-username. Treating the
# missing key as a failed source made STATE_OK=false on every resume, so
# wayfare-build-task stopped with a diagnostic on a valid configuration.
printf '# H\n\n- default-branch: main\n\n## Code Review Agent\n\n- agent: none\n' > "$REPO/HERO.md"
make_gh '[{"number":42,"url":"u","isDraft":true,"reviewDecision":null,"state":"OPEN"}]' '[]'
OUT="$(run)"
case "$(val STATE_ERRORS)" in
  *bot-username*) FAIL=$((FAIL + 1)); echo "FAIL  agent:none must not flag bot-username (got: $(val STATE_ERRORS))" ;;
  *) PASS=$((PASS + 1)) ;;
esac

# ---------- work-item checklist state --------------------------------------

# Guards: no store → 0 and empty counts; one active item → its file and both
# section counts; a goal or bot item never becomes ITEM_FILE; the branch field
# picks between active items; an invalid row or two unbranched claims flip
# STATE_OK; a failed count is `unknown`, never a number.
printf '# H\n\n- default-branch: main\n- bot-username: reviewbot\n' > "$REPO/HERO.md"
make_gh '[]' '[]'
OUT="$(run)"
check "no store: no in-flight item"     "0" "$(val ITEM_INFLIGHT)"
check "no store: counts are empty, not 0" "" "$(val SUBTASKS_OPEN)"

mkdir -p "$REPO/.plans/items"
printf -- '---\nschema: 1\ndefault_branch: main\nnext_id: 99\n---\n' > "$REPO/.plans/PLAN.md"
cat > "$REPO/.plans/items/003-foo.md" <<'ITEM'
---
id: 3
type: task
status: active
---
## Subtasks
- [x] 1. done
- [ ] 2. next
3. [ ] numbered form
## Definition of Done
- [ ] a
- [X] b
## Comments
- [ ] a tick outside the two sections is not a checklist line
ITEM
cat > "$REPO/.plans/items/004-bar.md" <<'ITEM'
---
id: 4
type: task
status: accepted
---
## Subtasks
- [ ] not in flight, must not be picked
ITEM
OUT="$(run)"
check "one in-flight item is found"      "1" "$(val ITEM_INFLIGHT)"
# basename: hero_root resolves symlinks (/private/var vs /var on macOS).
check "in-flight item path is emitted"   ".plans/items/003-foo.md" "$(val ITEM_FILE | sed 's|.*/\(\.plans/items/\)|\1|')"
check "subtasks: open count"             "2" "$(val SUBTASKS_OPEN)"
check "subtasks: total count"            "3" "$(val SUBTASKS_TOTAL)"
check "dod: open count"                  "1" "$(val DOD_OPEN)"
check "dod: total count"                 "2" "$(val DOD_TOTAL)"

# A section that is ABSENT is 0 0, which TOTAL tells apart from an all-ticked
# one (0 N). The close-out gate reads the difference.
cat > "$REPO/.plans/items/003-foo.md" <<'ITEM'
---
id: 3
type: task
status: active
---
## Subtasks
- [x] all done
ITEM
OUT="$(run)"
check "all-ticked item is still in flight" "1" "$(val ITEM_INFLIGHT)"
check "all-ticked subtasks: open is 0"   "0" "$(val SUBTASKS_OPEN)"
check "all-ticked subtasks: total kept"  "1" "$(val SUBTASKS_TOTAL)"
check "absent DoD section: total is 0"   "0" "$(val DOD_TOTAL)"

# `## Subtasks ` with a trailing space is still the section; an all-ticked DoD
# is `0 N`, the shape the close-out gate reads as "verified".
# printf, not a heredoc: the trailing space after `Subtasks` is the point of
# the case, and the whitespace hook strips it from a literal.
printf -- '---\nid: 3\ntype: task\nstatus: active\n---\n## Subtasks \n- [ ] a\n- [x] has a [ ] later in the text\n## Definition of Done\n- [x] a\n' > "$REPO/.plans/items/003-foo.md"
OUT="$(run)"
check "heading with trailing space still counts" "2" "$(val SUBTASKS_TOTAL)"
check "a [ ] later in a ticked line is not open"  "1" "$(val SUBTASKS_OPEN)"
check "all-ticked DoD: open 0"                    "0" "$(val DOD_OPEN)"
check "all-ticked DoD: total kept"                "1" "$(val DOD_TOTAL)"

# A goal at `active` and a bot PR item are never this branch's item.
printf -- '---\nid: 9\ntype: goal\nstatus: active\n---\n## Subtasks\n- [ ] not a branch item\n' > "$REPO/.plans/items/009-goal.md"
printf -- '---\nid: 10\ntype: task\nshape: dependency\nbot: dependabot\nstatus: active\n---\n## Subtasks\n- [ ] bot\n' > "$REPO/.plans/items/010-bot.md"
OUT="$(run)"
check "active goal and bot item are not counted" "1" "$(val ITEM_INFLIGHT)"
check "active goal never becomes ITEM_FILE"      ".plans/items/003-foo.md" "$(val ITEM_FILE | sed 's|.*/\(\.plans/items/\)|\1|')"
rm -f "$REPO/.plans/items/009-goal.md" "$REPO/.plans/items/010-bot.md"

# Two unbranched in-flight items: the script must not pick one, and the
# conflict must reach STATE_OK so the table's guard row catches it.
sed 's/status: accepted/status: active/' "$REPO/.plans/items/004-bar.md" > "$REPO/.plans/items/004-bar.tmp" \
  && mv "$REPO/.plans/items/004-bar.tmp" "$REPO/.plans/items/004-bar.md"
OUT="$(run)"
check "two in-flight items: count is 2"  "2" "$(val ITEM_INFLIGHT)"
check "two in-flight items: no file"     ""  "$(val ITEM_FILE)"
check "two in-flight items: STATE_OK false" "false" "$(val STATE_OK)"
case "$(val STATE_ERRORS)" in
  *item-claim-conflict*) PASS=$((PASS + 1)) ;;
  *) FAIL=$((FAIL + 1)); echo "FAIL  claim conflict is named in STATE_ERRORS (got: $(val STATE_ERRORS))" ;;
esac

# `branch:` binds an item to its branch: under a goal, several features are
# implementing at once and the one for this branch is the resume point.
printf -- '---\nid: 4\ntype: task\nstatus: active\nbranch: other-branch\n---\n## Subtasks\n- [ ] b\n' > "$REPO/.plans/items/004-bar.md"
printf -- '---\nid: 3\ntype: task\nstatus: active\nbranch: %s\n---\n## Subtasks\n- [ ] a\n' "$(git -C "$REPO" branch --show-current)" > "$REPO/.plans/items/003-foo.md"
OUT="$(run)"
check "branch-bound: this branch's item is picked" ".plans/items/003-foo.md" "$(val ITEM_FILE | sed 's|.*/\(\.plans/items/\)|\1|')"
check "branch-bound: both still count as in flight" "2" "$(val ITEM_INFLIGHT)"
# The scratch repo has no remote, so STATE_OK is false for fetch reasons;
# assert the conflict source specifically.
case "$(val STATE_ERRORS)" in
  *item-claim-conflict*) FAIL=$((FAIL + 1)); echo "FAIL  branch-bound must not flag a claim conflict (got: $(val STATE_ERRORS))" ;;
  *) PASS=$((PASS + 1)) ;;
esac

# An invalid row may be the item being built; dropping it would read as
# "nothing in flight" and route past its unchecked subtasks.
printf -- '---\nid: 3\ntype: task\nstatus: in_progress\n---\n## Subtasks\n- [ ] a\n' > "$REPO/.plans/items/003-foo.md"
rm -f "$REPO/.plans/items/004-bar.md"
OUT="$(run)"
check "invalid row: STATE_OK false" "false" "$(val STATE_OK)"
case "$(val STATE_ERRORS)" in
  *store-invalid-item*) PASS=$((PASS + 1)) ;;
  *) FAIL=$((FAIL + 1)); echo "FAIL  invalid item is named in STATE_ERRORS (got: $(val STATE_ERRORS))" ;;
esac
rm -rf "$REPO/.plans"

# An unmigrated store has no items/ at all. Guarding on that directory skipped
# the whole block and read as "nothing in flight" on every consumer the day
# schema 1 shipped; the store must fail as a source instead.
mkdir -p "$REPO/.plans"
printf -- '---\nid: 3\nkind: feature\nstatus: implementing\n---\n## Subtasks\n- [ ] a\n' > "$REPO/.plans/003-foo.md"
OUT="$(run)"
check "unmigrated store: STATE_OK false" "false" "$(val STATE_OK)"
case "$(val STATE_ERRORS)" in
  *work-store*) PASS=$((PASS + 1)) ;;
  *) FAIL=$((FAIL + 1)); echo "FAIL  unmigrated store is named in STATE_ERRORS (got: $(val STATE_ERRORS))" ;;
esac
rm -rf "$REPO/.plans"

# Only a task can be the item on this branch: a signal at active is being
# delivered, not built, and must not count as in flight or claim the branch.
mkdir -p "$REPO/.plans/items"
printf -- '---\nschema: 1\ndefault_branch: main\nnext_id: 99\n---\n' > "$REPO/.plans/PLAN.md"
printf -- '---\nid: 3\ntype: task\nstatus: active\nbranch: %s\n---\n## Subtasks\n- [ ] a\n' "$(git -C "$REPO" branch --show-current)" > "$REPO/.plans/items/003-foo.md"
printf -- '---\nid: 5\ntype: signal\nchannel: design\nstatus: active\n---\n' > "$REPO/.plans/items/005-sig.md"
OUT="$(run)"
check "signal at active is not in flight" "1" "$(val ITEM_INFLIGHT)"
check "signal at active never claims the branch" ".plans/items/003-foo.md" "$(val ITEM_FILE | sed 's|.*/\(\.plans/items/\)|\1|')"
rm -rf "$REPO/.plans"

# A build that wrote `blocked_on` and stopped lists as blocked while its status
# is still active, and resume must still find it.
mkdir -p "$REPO/.plans/items"
printf -- '---\nschema: 1\ndefault_branch: main\nnext_id: 99\n---\n' > "$REPO/.plans/PLAN.md"
printf -- '---\nid: 3\ntype: task\nstatus: active\nblocked_on: vendor key\nblocked_since: 2026-09-29\nbranch: %s\n---\n## Subtasks\n- [ ] a\n' "$(git -C "$REPO" branch --show-current)" > "$REPO/.plans/items/003-foo.md"
printf -- '---\nid: 6\ntype: task\nstatus: ready\nblocked_on: vendor key\nblocked_since: 2026-09-29\n---\n' > "$REPO/.plans/items/006-rdy.md"
OUT="$(run)"
check "blocked active task is in flight"     "1" "$(val ITEM_INFLIGHT)"
check "blocked active task is the branch item" ".plans/items/003-foo.md" "$(val ITEM_FILE | sed 's|.*/\(\.plans/items/\)|\1|')"
rm -rf "$REPO/.plans"

# ---------- the eval contract ----------------------------------------------

# Output is consumed via `eval`, so a hostile branch name or config value must
# not break out of the quoting.
printf '# H\n\n- default-branch: main\n- bot-username: reviewbot\n' > "$REPO/HERO.md"
git -C "$REPO" checkout -q -b 'weird/branch.name-1'
make_gh '[]' '[]'
OUT="$(run)"
rm -f "$TMP/eval_marker"
eval "$OUT"
check "output evals cleanly" "weird/branch.name-1" "${CURRENT_BRANCH:-}"
check "eval executed nothing" "no" "$([ -e "$TMP/eval_marker" ] && echo yes || echo no)"

# Every run must emit the full key set, so a consumer never reads an unset var.
for key in DEFAULT_BRANCH CURRENT_BRANCH UNCOMMITTED AHEAD UNPUSHED PR_EXISTS \
           PR_NUMBER PR_STATE PR_IS_DRAFT PR_REVIEW SELF_REVIEW_DONE \
           BOT_REPLIED ITEM_INFLIGHT ITEM_FILE SUBTASKS_OPEN SUBTASKS_TOTAL \
           DOD_OPEN DOD_TOTAL STATE_OK STATE_ERRORS; do
  if printf '%s\n' "$OUT" | grep -q "^$key="; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1)); echo "FAIL  missing key: $key"
  fi
done

if [ "$FAIL" -gt 0 ]; then
  echo "resume-state: $PASS passed, $FAIL FAILED"
  exit 1
fi
# Floor on the case count. Neither suite runs under `set -e`, so a setup line
# that starts failing does not fail the run. It just stops incrementing PASS,
# and a block whose glob went empty runs zero iterations. Without this, a
# refactor that silently stops executing 25 cases still reports 0 failures and
# exits 0. The whole reason these cases exist is that each one could be wrong
# SILENTLY; the suite must not be able to go quiet the same way.
MIN_CASES=68
if [ "$PASS" -lt "$MIN_CASES" ]; then
  echo "resume-state: only $PASS cases ran, expected >= $MIN_CASES — a block stopped executing" >&2
  exit 1
fi
echo "resume-state: $PASS passed"
