#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/migrate-plan.sh.
#
# Scoped to what migrates SILENTLY WRONG. A migrator that dies is a migrator
# someone re-runs; one that writes `status: new` over `status: done` loses a
# roadmap and nobody notices until a shipped feature is handed out as READY.
# So: every kind and status mapping, the covers->parent inversion, the second
# pass it must refuse, and the fields it must not eat.
#
# Usage: bash scripts/migrate-plan.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MIG="$HERE/migrate-plan.sh"
# shellcheck source=/dev/null
. "$HERE/hero-lib.sh" || { echo "cannot source hero-lib.sh"; exit 1; }

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

# A real git repo: the store refuses to exist anywhere it cannot be ignored.
newrepo() { # NAME
  local r="$TMP/$1"
  mkdir -p "$r" && git -C "$r" init -q 2>/dev/null
  git -C "$r" config user.email t@example.com
  git -C "$r" config user.name t
  : > "$r/README.md"
  git -C "$r" add -A && git -C "$r" commit -qm init
  mkdir -p "$r/.plans"
  printf '%s' "$r"
}

item() { # STORE FILE BODY
  printf '%s\n' "$3" > "$1/.plans/$2"
}

# ---------- kind -> type/shape/channel -------------------------------------

R=$(newrepo kinds)
S="$R/.plans"
i=0
for spec in \
  "feature|task|story" \
  "architecture|task|structural" \
  "polish|task|visual" \
  "bug|task|defect" \
  "design-feedback|signal||design" \
  "design-system-feedback|signal||design-system" \
  "architecture-feedback|signal||architecture" \
  ; do
  i=$((i + 1))
  k=${spec%%|*}
  item "$R" "00$i-x.md" "---
id: $i
kind: $k
title: t
status: todo
---

## Context

x"
done
bash "$MIG" "$S" >/dev/null 2>&1

check "kind: feature -> task/story" "task story" \
  "$(hero_item_field "$S/items/001-x.md" type) $(hero_item_field "$S/items/001-x.md" shape)"
check "kind: architecture -> task/structural" "task structural" \
  "$(hero_item_field "$S/items/002-x.md" type) $(hero_item_field "$S/items/002-x.md" shape)"
check "kind: polish -> task/visual" "task visual" \
  "$(hero_item_field "$S/items/003-x.md" type) $(hero_item_field "$S/items/003-x.md" shape)"
check "kind: bug -> task/defect" "task defect" \
  "$(hero_item_field "$S/items/004-x.md" type) $(hero_item_field "$S/items/004-x.md" shape)"
check "kind: design-feedback -> signal/design" "signal design" \
  "$(hero_item_field "$S/items/005-x.md" type) $(hero_item_field "$S/items/005-x.md" channel)"
check "kind: design-system-feedback -> signal/design-system" "signal design-system" \
  "$(hero_item_field "$S/items/006-x.md" type) $(hero_item_field "$S/items/006-x.md" channel)"
check "kind: architecture-feedback -> signal/architecture" "signal architecture" \
  "$(hero_item_field "$S/items/007-x.md" type) $(hero_item_field "$S/items/007-x.md" channel)"
check "signal carries no shape" "" "$(hero_item_field "$S/items/005-x.md" shape)"
check "task carries no channel" "" "$(hero_item_field "$S/items/001-x.md" channel)"
check "items left the store root" "0" \
  "$(find "$S" -maxdepth 1 -name '0*.md' | wc -l | tr -d ' ')"

# security splits on `bot:`, which is the whole reason `shape` is not `kind`.
R=$(newrepo sec); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
kind: security
bot: dependabot
pr: https://example.test/pull/41
severity: high
status: todo
---

## Context

x"
item "$R" "002-b.md" "---
id: 2
kind: security
status: todo
---

## Context

x"
bash "$MIG" "$S" >/dev/null 2>&1
check "security with bot -> dependency" "task dependency" \
  "$(hero_item_field "$S/items/001-a.md" type) $(hero_item_field "$S/items/001-a.md" shape)"
check "security without bot -> defect" "task defect" \
  "$(hero_item_field "$S/items/002-b.md" type) $(hero_item_field "$S/items/002-b.md" shape)"
check "bot: survives" "dependabot" "$(hero_item_field "$S/items/001-a.md" bot)"
check "pr: survives" "https://example.test/pull/41" "$(hero_item_field "$S/items/001-a.md" pr)"
check "severity: survives" "high" "$(hero_item_field "$S/items/001-a.md" severity)"

# ---------- status -> status/resolution ------------------------------------

R=$(newrepo stat); S="$R/.plans"
i=0
for st in new todo planning ready implementing committed reviewing 'done' queued delivered rejected review accepted; do
  i=$((i + 1))
  item "$R" "0$(printf %02d $i)-s.md" "---
id: $i
kind: feature
status: $st
---

## Context

x"
done
OUT=$(bash "$MIG" "$S" 2>&1)
sr() { printf '%s %s' "$(hero_item_field "$S/items/$1" status)" "$(hero_item_field "$S/items/$1" resolution)"; }
check "status: new"          "new "        "$(sr 001-s.md)"
check "status: todo -> accepted" "accepted " "$(sr 002-s.md)"
check "status: planning"     "planning "   "$(sr 003-s.md)"
check "status: ready"        "ready "      "$(sr 004-s.md)"
check "status: implementing -> active" "active " "$(sr 005-s.md)"
check "status: committed"    "committed "  "$(sr 006-s.md)"
check "status: reviewing -> review" "review " "$(sr 007-s.md)"
check "status: done -> done/shipped" "done shipped" "$(sr 008-s.md)"
check "status: queued -> ready" "ready "    "$(sr 009-s.md)"
check "status: delivered -> done/delivered" "done delivered" "$(sr 010-s.md)"
check "status: rejected -> done/rejected" "done rejected" "$(sr 011-s.md)"
# A store already partly on schema-1 statuses keeps them. Without their own
# arm they fell to the unrecognized one, which resets an open PR's item to new.
check "status: review"       "review "     "$(sr 012-s.md)"
check "status: accepted"     "accepted "   "$(sr 013-s.md)"
check "current statuses migrate without warning" "0" \
  "$(printf '%s' "$OUT" | grep -c 'unrecognized status' | tr -d ' ')"

# Suspension stops being a status: the item goes back to where it was and
# `awaiting` is what makes it suspended. A dropped suspended_from would have
# restored a `done` item to `new` and re-run shipped work.
R=$(newrepo susp); S="$R/.plans"
item "$R" "001-w.md" "---
id: 1
kind: feature
status: suspended
suspended_from: reviewing
suspended_at: 2026-09-01
awaiting: [m-ac7553]
expires: 2026-09-08
---

## Context

x"
bash "$MIG" "$S" >/dev/null 2>&1
check "suspended restores suspended_from" "review" "$(hero_item_field "$S/items/001-w.md" status)"
check "suspended_from is dropped" "" "$(hero_item_field "$S/items/001-w.md" suspended_from)"
check "awaiting survives" "m-ac7553" "$(hero_item_list_field "$S/items/001-w.md" awaiting)"
check "expires survives" "2026-09-08" "$(hero_item_field "$S/items/001-w.md" expires)"

# ---------- covers -> parent/rank ------------------------------------------

R=$(newrepo goal); S="$R/.plans"
item "$R" "007-g.md" "---
id: 7
kind: goal
title: g
status: done
covers: [12, 13, 77]
budget: 2
budget_max: 4
---

## Definition of Done

- [ ] x"
# Two goals name 13; the open one wins, whatever the glob order.
item "$R" "008-g2.md" "---
id: 8
kind: goal
title: g2
status: active
covers:
  - 13
---

## Definition of Done

- [ ] y"
item "$R" "012-a.md" "---
id: 12
kind: feature
status: done
---

## Context

x"
item "$R" "013-b.md" "---
id: 13
kind: feature
status: todo
---

## Context

x"
OUT=$(bash "$MIG" "$S" 2>&1)
check "covers -> parent on member 1" "7" "$(hero_item_field "$S/items/012-a.md" parent)"
check "covers: the open goal wins over the closed one" "8" "$(hero_item_field "$S/items/013-b.md" parent)"
check "covers: rank comes from the winning goal" "1 1" \
  "$(hero_item_field "$S/items/012-a.md" rank) $(hero_item_field "$S/items/013-b.md" rank)"
check "covers: the collision is warned" "1" \
  "$(printf '%s' "$OUT" | grep -c 'item 13 is covered by goals 7 (closed) and 8 (open); keeping 8' | tr -d ' ')"
check "covers: a dangling id is warned" "1" \
  "$(printf '%s' "$OUT" | grep -c 'covers item 77, which no item carries' | tr -d ' ')"
check "covers is gone from the goal" "" "$(hero_item_field "$S/items/007-g.md" covers)"
check "goal keeps its type" "goal" "$(hero_item_field "$S/items/007-g.md" type)"
check "goal at done stays done" "done" "$(hero_item_field "$S/items/007-g.md" status)"
check "goal at done carries no shipped resolution" "" \
  "$(hero_item_field "$S/items/007-g.md" resolution)"
check "budget survives" "2" "$(hero_item_field "$S/items/007-g.md" budget)"

# ---------- anchors, source list -------------------------------------------

R=$(newrepo anch); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
kind: feature
status: todo
source: services/auth/, cmd/api/main.go
target: auth/
source_ref: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
target_ref: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
---

## Context

x"
bash "$MIG" "$S" >/dev/null 2>&1
check "source_ref -> anchors.source" "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  "$(sed -n '/^anchors:/,/^[a-z]/p' "$S/items/001-a.md" | sed -n 's/^  source: //p')"
check "target_ref -> anchors.target" "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" \
  "$(sed -n '/^anchors:/,/^[a-z]/p' "$S/items/001-a.md" | sed -n 's/^  target: //p')"
check "source_ref is gone" "" "$(hero_item_field "$S/items/001-a.md" source_ref)"
check "comma source becomes a list" "services/auth/
cmd/api/main.go" "$(hero_item_list_field "$S/items/001-a.md" source)"

# ---------- body sections -> ## Log ----------------------------------------

R=$(newrepo body); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
kind: feature
status: todo
---

## Context

why

## Mistakes

- 2026-07-24 (feature 1 build): wired it the wrong way round

## Design Feedback

- DF-1-2026-07-25-1 [undelivered] the design orders consent first
- DF-1-2026-07-20-1 [item: 61] already promoted, must not be copied

## Comments

- 2026-07-23 (rahul): a note"
bash "$MIG" "$S" >/dev/null 2>&1
F="$S/items/001-a.md"
check "one ## Log section" "1" "$(grep -c '^## Log' "$F" | tr -d ' ')"
check "## Comments is gone" "0" "$(grep -c '^## Comments' "$F" | tr -d ' ')"
check "## Mistakes is gone" "0" "$(grep -c '^## Mistakes' "$F" | tr -d ' ')"
check "## Context survives" "1" "$(grep -c '^## Context' "$F" | tr -d ' ')"
check "comment line is tagged note" "1" \
  "$(grep -c '^- 2026-07-23 (rahul) note: a note$' "$F" | tr -d ' ')"
check "mistake line is tagged mistake" "1" \
  "$(grep -c '^- 2026-07-24 (feature 1 build) mistake: wired it' "$F" | tr -d ' ')"
# The DF id and the marker are the entry'"'"'s identity and state: a promoted
# signal item'"'"'s `entry:` points at the id, and the next sync counts
# `[undelivered]` markers. Strip either and every entry is re-proposed.
check "undelivered DF becomes a signal line, id and marker intact" "1" \
  "$(grep -c '^- 2026-07-25 (migrate) signal: DF-1-2026-07-25-1 \[undelivered\] the design orders consent first$' "$F" | tr -d ' ')"
check "promoted DF entry is kept with its [item: N] marker" "1" \
  "$(grep -c '^- 2026-07-20 (migrate) signal: DF-1-2026-07-20-1 \[item: 61\] already promoted' "$F" | tr -d ' ')"

# ---------- PLAN.md and the second-pass refusal ----------------------------

check "PLAN.md written" "1" "$(hero_item_field "$S/PLAN.md" schema)"
check "next_id is max+1" "2" "$(hero_item_field "$S/PLAN.md" next_id)"
check "default_branch recorded" "1" \
  "$([ -n "$(hero_item_field "$S/PLAN.md" default_branch)" ] && echo 1 || echo 0)"
check "no target key without a design project" "0" \
  "$(grep -c '^target:' "$S/PLAN.md" | tr -d ' ')"

OUT=$(bash "$MIG" "$S" 2>&1); RC=$?
check "second pass exits 0" "0" "$RC"
check "second pass refuses" "1" \
  "$(printf '%s' "$OUT" | grep -c 'already at schema' | tr -d ' ')"
check "second pass did not re-derive a shape" "story" "$(hero_item_field "$F" shape)"
check "second pass did not duplicate ## Log" "1" "$(grep -c '^## Log' "$F" | tr -d ' ')"

# An unrecognized kind must be loud and must still migrate: a half-migrated
# store is worse than one wrong shape.
R=$(newrepo odd); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
kind: features
status: todo
---

## Context

x"
OUT=$(bash "$MIG" "$S" 2>&1)
check "unrecognized kind warns" "1" \
  "$(printf '%s' "$OUT" | grep -c "unrecognized kind 'features'" | tr -d ' ')"
check "unrecognized kind still migrates" "task" "$(hero_item_field "$S/items/001-a.md" type)"
# The summary is the one line a long run's reader sees; a warn raised inside a
# subshell used to leave it saying nothing.
check "unrecognized kind is counted in the summary" "1" \
  "$(printf '%s' "$OUT" | grep -c '1 warning(s) above need a look' | tr -d ' ')"
check "unrecognized kind leaves a Log line in the item" "1" \
  "$(grep -c "note: kind 'features' was not recognized" "$S/items/001-a.md" | tr -d ' ')"

# ---------- type-aware status clamps, case, existing Log -------------------

R=$(newrepo clamp); S="$R/.plans"
item "$R" "001-g.md" "---
id: 1
kind: goal
status: ready
---

## Context

x"
item "$R" "002-s.md" "---
id: 2
kind: design-feedback
status: reviewing
---

## Context

x"
item "$R" "003-w.md" "---
id: 3
kind: feature
status: suspended
suspended_from: Done
awaiting: [m-1]
---

## Context

x

## Log

- 2026-08-01 (rahul) note: already tagged

## Comments

- 2026-08-02 (rahul): a later comment
- 2026-08-03: no actor"
item "$R" "004-sd.md" "---
id: 4
kind: design-feedback
status: done
---

## Context

x"
OUT=$(bash "$MIG" "$S" 2>&1)
check "goal at ready clamps to accepted" "accepted" "$(hero_item_field "$S/items/001-g.md" status)"
check "signal at reviewing clamps to active" "active" "$(hero_item_field "$S/items/002-s.md" status)"
check "clamps are warned" "2" \
  "$(printf '%s' "$OUT" | grep -c 'has no schema-1 equivalent' | tr -d ' ')"
check "suspended_from is case-insensitive" "done" "$(hero_item_field "$S/items/003-w.md" status)"
check "restored done gets shipped" "shipped" "$(hero_item_field "$S/items/003-w.md" resolution)"
check "an existing ## Log is not duplicated" "1" "$(grep -c '^## Log' "$S/items/003-w.md" | tr -d ' ')"
check "existing Log lines survive untouched" "1" \
  "$(grep -c '^- 2026-08-01 (rahul) note: already tagged$' "$S/items/003-w.md" | tr -d ' ')"
check "a dated line with no actor gets one colon" "1" \
  "$(grep -c '^- 2026-08-03 note: no actor$' "$S/items/003-w.md" | tr -d ' ')"
check "signal at done gets no task resolution" "" "$(hero_item_field "$S/items/004-sd.md" resolution)"
check "signal at done without an answer is warned" "1" \
  "$(printf '%s' "$OUT" | grep -c 'signal at .done. with no delivered/rejected' | tr -d ' ')"
check "warning count matches" "1" \
  "$(printf '%s' "$OUT" | grep -c '3 warning(s) above need a look' | tr -d ' ')"

# ---------- refusals and non-items -----------------------------------------

R=$(newrepo hand); S="$R/.plans"
printf '## Scope\n\nhand-written\n' > "$S/PLAN.md"
item "$R" "001-a.md" "---
id: 1
kind: feature
status: todo
---

## Context

x"
bash "$MIG" "$S" >/dev/null 2>&1; RC=$?
check "hand-written PLAN.md is refused" "1" "$RC"
check "hand-written PLAN.md is untouched" "1" "$(grep -c hand-written "$S/PLAN.md" | tr -d ' ')"
rm "$S/PLAN.md"
printf '# notes\n\nnot an item\n' > "$S/README.md"
OUT=$(bash "$MIG" "$S" 2>&1)
check "a file with no frontmatter is left in place" "1" "$([ -f "$S/README.md" ] && echo 1 || echo 0)"
check "a file with no frontmatter is not moved" "0" "$([ -f "$S/items/README.md" ] && echo 1 || echo 0)"
check "a non-item is warned" "1" \
  "$(printf '%s' "$OUT" | grep -c 'README.md: no frontmatter; not an item' | tr -d ' ')"
# A run that stopped midway leaves items/ populated and no PLAN.md; a rerun
# would rebuild parent links and next_id from an empty root.
rm "$S/PLAN.md"
bash "$MIG" "$S" >/dev/null 2>&1; RC=$?
check "items/ without PLAN.md is refused" "1" "$RC"

# ---------- legacy items: no kind, old status aliases ----------------------

R=$(newrepo legacy); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
title: no kind at all
status: in-progress
---

## Context

x"
item "$R" "002-b.md" "---
id: 2
title: no status either
---

## Context

x"
bash "$MIG" "$S" >/dev/null 2>&1
# Without a `kind:` line there is nothing to rewrite in place, and an item
# with no `type:` lists as invalid: the whole store would come out unusable.
check "no-kind item gets type: task" "task" "$(hero_item_field "$S/items/001-a.md" type)"
check "no-kind item gets shape: story" "story" "$(hero_item_field "$S/items/001-a.md" shape)"
check "in-progress maps to active" "active" "$(hero_item_field "$S/items/001-a.md" status)"
check "no-status item gets type too" "task" "$(hero_item_field "$S/items/002-b.md" type)"
check "no-kind store lists with no invalid rows" "0" \
  "$(hero_ready_items "$S" 2>/dev/null | grep -c '^invalid' | tr -d ' ')"

# ---------- dry run changes nothing ----------------------------------------

R=$(newrepo dry); S="$R/.plans"
item "$R" "001-a.md" "---
id: 1
kind: feature
status: todo
---

## Context

x"
bash "$MIG" "$S" --dry-run >/dev/null 2>&1
check "dry run leaves the item in place" "1" \
  "$(find "$S" -maxdepth 1 -name '001-a.md' | wc -l | tr -d ' ')"
check "dry run writes no PLAN.md" "0" \
  "$([ -f "$S/PLAN.md" ] && echo 1 || echo 0)"
check "dry run writes no items dir" "0" \
  "$([ -d "$S/items" ] && echo 1 || echo 0)"

printf '\nmigrate-plan: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
