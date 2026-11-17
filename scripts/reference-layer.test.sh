#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for the reference-layer functions in scripts/hero-lib.sh,
# run against two fixture repos: one whose reference/ is a copy of
# references/reference-example/, and one with no reference/ at all.
#
# The second fixture is the contract every hook leans on: a repo without
# reference/ must get rc 1 and no output from every reader, and a PR body back
# byte for byte, or a skill gated on them changes behavior in repos that never
# opted in.
#
# Usage: bash scripts/reference-layer.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/hero-lib.sh" || { echo "cannot source hero-lib.sh"; exit 1; }
EXAMPLE="$HERE/../references/reference-example"
export WAYFARE_STORE=local

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

item() { # ROOT ID BRANCH STATUS CONTEXT_FIRST_LINE
  mkdir -p "$1/.plans/items"
  printf -- '---\nid: %s\ntype: task\ntitle: "t%s"\nstatus: %s\nbranch: %s\n---\n\n## Context\n\n%s\n\nMore context.\n' \
    "$2" "$2" "$4" "$3" "$5" >"$1/.plans/items/$(printf '%03d' "$2")-t.md"
}

WITH="$TMP/with"
WITHOUT="$TMP/without"
mkdir -p "$WITH" "$WITHOUT"
cp -R "$EXAMPLE" "$WITH/reference"
item "$WITH" 1 feat/desk ready 'Reference: screen:returns-desk@1, entity:loan@2'
item "$WITH" 2 feat/desk ready 'Reference: entity:loan@2, process:return-tool@2'
item "$WITH" 3 feat/old ready 'Reference: entity:loan@1, entity:gone@1'
item "$WITHOUT" 1 feat/desk ready 'No pin here.'
BODY=$'## Summary\nAdds the returns desk.\n\n## Changesets\n\n_Generated using wayfare._'

# ---------- a repo with reference/ ----------------------------------------

check "dir: found" "$WITH/reference" "$(hero_reference_dir "$WITH")"
check "index: one row per headed file in the example" "12" "$(hero_reference_index "$WITH" | wc -l | tr -d ' ')"
check "index: kind:id, version and path" "entity:loan	2	$WITH/reference/entities/loan.md" \
  "$(hero_reference_index "$WITH" | grep '^entity:loan	')"
check "index: README and CHANGELOG carry no header" "" \
  "$(hero_reference_index "$WITH" | grep -E '/(README|CHANGELOG)\.md$' | grep -v prototype)"

mkdir -p "$TMP/legacy/reference"
printf 'capabilities: shop@1\n\n# Map\n' >"$TMP/legacy/reference/capabilities.md"
check "index: hero-template's capabilities spelling reads as capability" "capability:shop	1" \
  "$(hero_reference_index "$TMP/legacy" | cut -f1,2)"

check "pins: in order, from the Reference line" $'screen:returns-desk@1\nentity:loan@2' \
  "$(hero_reference_pins "$WITH/.plans/items/001-t.md")"
check "pins: deduplicated across files" $'screen:returns-desk@1\nentity:loan@2\nprocess:return-tool@2' \
  "$(hero_reference_pins "$WITH/.plans/items/001-t.md" "$WITH/.plans/items/002-t.md")"
check "pins: stdin" "entity:tool@1" "$(printf 'x\nReference: `entity:tool@1`.\n' | hero_reference_pins -)"
check "pins: a mention mid-line is not a pin" "1" "$(printf 'see Reference: entity:tool@1\n' | hero_reference_pins - >/dev/null; echo $?)"

# What build-task reads before its first edit.
check "resolve: current pin" "screen:returns-desk@1	1	$WITH/reference/flows/screens/returns-desk.md" \
  "$(hero_reference_resolve "$WITH/.plans/items/001-t.md" "$WITH" | head -1)"
check "resolve: a pin behind its file shows the current version" "entity:loan@1	2" \
  "$(hero_reference_resolve "$WITH/.plans/items/003-t.md" "$WITH" | head -1 | cut -f1,2)"
check "resolve: a pin with no file is none" "entity:gone@1	none	" \
  "$(hero_reference_resolve "$WITH/.plans/items/003-t.md" "$WITH" | tail -1)"

check "line: one Reference line" "Reference: screen:returns-desk@1, entity:loan@2" \
  "$(hero_reference_line "$WITH/.plans/items/001-t.md")"
check "branch line: every item on the branch" "Reference: screen:returns-desk@1, entity:loan@2, process:return-tool@2" \
  "$(hero_reference_branch_line feat/desk "$WITH")"

# What push-pr posts.
check "pr body: the line follows the summary paragraph" \
  $'## Summary\nAdds the returns desk.\n\nReference: screen:returns-desk@1, entity:loan@2, process:return-tool@2\n\n## Changesets\n\n_Generated using wayfare._' \
  "$(cd "$WITH" && git init -q -b feat/desk . && hero_reference_pr_body "$BODY" "$WITH")"
check "pr body: a branch with no pins is unchanged" "$BODY" \
  "$(cd "$WITH" && git checkout -q -b feat/none && hero_reference_pr_body "$BODY" "$WITH")"

# ---------- a repo without reference/ -------------------------------------

for fn in hero_reference_dir hero_reference_index; do
  out=$("$fn" "$WITHOUT" 2>&1); rc=$?
  check "$fn: no reference/ is rc 1" "1" "$rc"
  check "$fn: no reference/ prints nothing" "" "$out"
done
cp "$WITH/.plans/items/001-t.md" "$WITHOUT/pinned.md"
out=$(hero_reference_resolve "$WITHOUT/pinned.md" "$WITHOUT" 2>&1); rc=$?
check "resolve: no reference/ is rc 1, even for a pinned file" "1" "$rc"
check "resolve: no reference/ prints nothing" "" "$out"
check "pr body: no reference/ leaves the body byte for byte" "$BODY" \
  "$(cd "$WITHOUT" && git init -q -b feat/desk . && hero_reference_pr_body "$BODY" "$WITHOUT")"

if [ "$FAIL" -gt 0 ]; then
  echo "reference-layer: $PASS passed, $FAIL FAILED"
  exit 1
fi
MIN_CASES=23
if [ "$PASS" -lt "$MIN_CASES" ]; then
  echo "reference-layer: only $PASS cases ran, expected >= $MIN_CASES" >&2
  exit 1
fi
echo "reference-layer: $PASS passed"
