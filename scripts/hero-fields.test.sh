#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/hero-fields.sh.
#
# The map is what every `recalibrate` verb reports before it asks anything, so
# the cases here are the ways that report could lie: a set field reported as
# unset, a refused value reported as merely absent (which would send the verb
# to ask about a value that is actually present and dangerous), a broken
# reader reported as either, and a section heading found inside a code fence.
#
# The loop assertions at the bottom carry counters. Without them each one
# compares an empty accumulator against an empty expectation and passes
# whenever the loop examines nothing at all, including when hero-fields.sh
# does not exist.

set -uo pipefail

FIELDS="$(cd "$(dirname "$0")" && pwd)/hero-fields.sh"
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
R="$(cd "$TMP" && pwd -P)/repo"
mkdir -p "$R"

# `platform` appears in the map twice: push-pr reads CI/CD's, ship-pr reads
# Deployment's, so both sections carry one here. hero-lib.sh calls this the
# trap its BLOCK argument exists for; without both sections in the fixture the
# scoping argument is never exercised and could be dropped with no test failing.
cat > "$R/HERO.md" <<'EOM'
# Hero Configuration

## Repository

- default-branch: release
- branch-convention:
- commit-convention: --exec=touch /tmp/pwned

## CI/CD

- platform: github-actions

## Deployment

- platform: fly

## Projects

### app

- language: go
EOM

cell() { # key column — output is TSV, so a field is addressed by its column
  awk -F'\t' -v k="$1" -v c="$2" '$2 == k { print $c }'
}

OUT=$("$FIELDS" wayfare-push-pr "$R"); RC=$?
check "a clean read exits 0" "0" "$RC"

check "set field reports its value" \
  "release" "$(printf '%s\n' "$OUT" | cell default-branch 3)"

# `- branch-convention:` with nothing after it is a field the file carries but
# does not answer. Reporting it as set would hide exactly the case
# recalibrate exists to fix.
check "present-but-empty field is unset" \
  "(unset)" "$(printf '%s\n' "$OUT" | cell branch-convention 3)"

# A leading `-` makes the value an option to every git and gh command it
# reaches. hero_md_field refuses it; the map must say so rather than report
# the field as simply missing.
check "refused value is not reported as unset" \
  "(refused)" "$(printf '%s\n' "$OUT" | cell commit-convention 3)"

check "section row with the heading present" \
  "(present)" "$(printf '%s\n' "$OUT" | awk -F'\t' '$1 == "Projects" { print $3 }')"

check "section row with the heading absent" \
  "(absent)" "$("$FIELDS" wayfare-setup-dev "$R" | awk -F'\t' '$1 == "Developer Setup" { print $3 }')"

# A field under a heading that does not exist needs a different question than
# a blank under a heading that does, because phase 3 has to create the section.
check "field under a missing section is no-section" \
  "(no-section)" "$(printf '%s\n' "$OUT" | cell linters 3)"

# The same key under two headings. Read unscoped it returns the first match in
# the file, so both rows would say github-actions.
check "CI/CD platform is read from CI/CD" \
  "github-actions" "$(printf '%s\n' "$OUT" | awk -F'\t' '$1 == "CI/CD" && $2 == "platform" { print $3 }')"
check "Deployment platform is read from Deployment" \
  "fly" "$("$FIELDS" wayfare-ship-pr "$R" | awk -F'\t' '$1 == "Deployment" && $2 == "platform" { print $3 }')"

# hero_md_field skips fenced blocks; the heading probe must agree with it, or
# a HERO.md quoting its own template reports sections it does not have.
mkdir -p "$TMP/fenced"
cat > "$TMP/fenced/HERO.md" <<'EOM'
# Hero Configuration

Example of what this file can hold:

```markdown
## Developer Setup

- tool: git
```
EOM
check "a heading inside a code fence is not present" \
  "(absent)" "$("$FIELDS" wayfare-setup-dev "$TMP/fenced" | awk -F'\t' '$1 == "Developer Setup" { print $3 }')"

# No HERO.md at all: every row says so, and the command still succeeds, so
# recalibrate reads the rows and sends the user to `wayfare-init-repo`.
mkdir -p "$TMP/bare"
BARE=$("$FIELDS" wayfare-push-pr "$TMP/bare"); check "missing HERO.md exits 0" "0" "$?"
check "every row is no-file when there is no HERO.md" \
  "9" "$(printf '%s\n' "$BARE" | tail -n +2 | grep -c '(no-file)' | tr -d ' ')"

# A reader that breaks must not look like a file that is merely empty. This is
# the case that turns a `--exec=` payload into a benign-looking blank.
mkdir -p "$TMP/shim"
sed 's/^hero_md_field() {/hero_md_field() { return 127;/' "$PLUGIN_ROOT/scripts/hero-lib.sh" > "$TMP/shim/hero-lib.sh"
cp "$FIELDS" "$TMP/shim/hero-fields.sh"
SHIM_OUT=$(bash "$TMP/shim/hero-fields.sh" wayfare-push-pr "$R" 2>/dev/null); SHIM_RC=$?
check "a broken reader is not reported as unset" \
  "0" "$(printf '%s\n' "$SHIM_OUT" | grep -c '(unset)' | tr -d ' ')"
check "a broken reader fails the command" "1" "$SHIM_RC"

# A ROOT that does not exist is a caller bug, not a repo without config.
check "nonexistent ROOT exits 1" \
  "1" "$("$FIELDS" wayfare-push-pr "$TMP/nope" >/dev/null 2>&1; echo $?)"

# `grep "^$SKILL|"` used to interpolate the argument as a regex, so `push.pr`
# printed push-pr's table and exited 0.
check "a regex metachar does not match a skill" \
  "2" "$("$FIELDS" 'push.pr' "$R" >/dev/null 2>&1; echo $?)"

check "unknown skill exits 2" \
  "2" "$("$FIELDS" nope "$R" >/dev/null 2>&1; echo $?)"

# --help is a slice of the header comment by line number, so it rots silently
# when that block is reflowed. Pin both ends of the range.
HELP=$("$FIELDS" --help)
check "--help does not start with the copyright" \
  "0" "$(printf '%s\n' "$HELP" | grep -c 'All Rights Reserved' | tr -d ' ')"
check "--help reaches the exit contract" \
  "1" "$(printf '%s\n' "$HELP" | grep -c '2 unknown skill' | tr -d ' ')"

# Both modes emit the same five columns, so one record type describes the
# whole command and a column index means the same thing in each.
check "--all rows all have 5 columns" \
  "" "$("$FIELDS" --all | awk -F'\t' 'NF != 5 { print NR }' | tr '\n' ' ' | sed 's/ $//')"

# The map is 80-odd hand-edited lines and will grow. A short row yields an
# empty DECIDES cell, so recalibrate reports a field without saying what it
# decides; a duplicate asks the same question twice in one run.
check "no duplicate SKILL/SECTION/KEY row" \
  "" "$("$FIELDS" --all | tail -n +2 | cut -f1-3 | sort | uniq -d | tr '\n' ' ' | sed 's/ $//')"
check "no DECIDES cell is empty" \
  "" "$("$FIELDS" --all | tail -n +2 | awk -F'\t' '$5 == "" { print $1 }' | sort -u | tr '\n' ' ' | sed 's/ $//')"
check "no DECIDES cell contains a pipe" \
  "0" "$("$FIELDS" --all | tail -n +2 | cut -f5 | grep -c '|' | tr -d ' ')"

check "--list is non-empty" \
  "yes" "$([ "$("$FIELDS" --list | wc -l | tr -d ' ')" -gt 0 ] && echo yes || echo no)"

# Every listed name is a real skill directory. This catches a typo'd skill
# name in a new map row, which would otherwise surface only when someone runs
# the verb.
BAD_NAME=""
for name in $("$FIELDS" --list); do
  [ -d "$PLUGIN_ROOT/skills/$name" ] || BAD_NAME="$BAD_NAME $name"
done
check "every mapped name is a skill directory" "" "$BAD_NAME"

# The map is the claim and the skills are the truth. Match the frontmatter
# anchored to the first block: create-skill/SKILL.md carries a second
# `argument-hint:` at column 0 inside a fenced template, so an unanchored grep
# counts a skill whose *example* mentions the verb.
declares_verb() { # skill-dir
  awk 'NR == 1 { if ($0 != "---") exit 1; next }
       $0 == "---" { exit !found }
       /^argument-hint:.*recalibrate/ { found = 1 }
       END { exit !found }' "$1/SKILL.md" 2>/dev/null
}

MISSING=""
DECLARED=0
for d in "$PLUGIN_ROOT"/skills/*/; do
  name=$(basename "$d")
  declares_verb "$d" || continue
  DECLARED=$((DECLARED + 1))
  "$FIELDS" --list | grep -qx "$name" || MISSING="$MISSING $name"
done
check "every skill offering recalibrate has map rows" "" "$MISSING"

# Exempt by name, not by circumstance. An earlier version skipped any skill
# that happened not to invoke the script, which is the absence of the thing
# being checked: deleting a skill's `hero-fields.sh" NAME` block then made
# the check pass instead of fail, and a 26-directory rename sweep is exactly
# what deletes one. wayfare-init-repo is the only real exemption: its
# `recalibrate` re-investigates the repo and rewrites HERO.md whole rather
# than reporting a field table, so it reads no map. Anything else appearing
# here is a skill that lost its call.
NO_INVOCATION="wayfare-init-repo"

# A mapped skill no longer has to offer `recalibrate` itself. The wayfare
# verbs were split out of one skill, and tuning went with them into
# `wayfare-recalibrate-config`, so `wayfare-sync-plan` reads Wayfare fields
# and offers no verb of its own. What still has to hold is that every field
# is reachable by SOME recalibrate, which the `*|*` row below is.
MAPPED=0
WRONG_CALL=""
for name in $("$FIELDS" --list); do
  MAPPED=$((MAPPED + 1))
  # The binding a 16-file copy-paste actually breaks: a block still reading
  # `hero-fields.sh" push-pr` inside another skill prints the wrong table and
  # asks about fields that skill never reads. Checked only where a skill
  # invokes the script at all; a mapped skill that never invokes it is fine.
  # Keyed on declaring the verb, not on being mapped. A mapped skill that
  # offers no `recalibrate` has nothing to invoke the script FOR: since the
  # split, wayfare-recalibrate-config tunes those fields. A skill that DOES
  # offer the verb and reads no map asks the user about nothing.
  if declares_verb "$PLUGIN_ROOT/skills/$name"; then
    case " $NO_INVOCATION " in
      *" $name "*) ;;
      *) grep -qE "hero-fields.sh\" ($name|--all)\$" "$PLUGIN_ROOT/skills/$name/"{SKILL,WORKFLOW}.md 2>/dev/null ||
           WRONG_CALL="$WRONG_CALL $name" ;;
    esac
  fi
done
check "a skill offering recalibrate reads its own rows" "" "$WRONG_CALL"

# Every field must be reachable by some recalibrate, or it is a field nobody
# can fix. A `*|*` row does NOT deliver that: hero-fields.sh prints it as one
# literal row rather than expanding it, so the earlier version of this check
# asserted a coverage the script never had, by grepping source text instead of
# running it. Run it: --all must reach every SECTION|KEY the map declares.
ALL_PAIRS=$(awk -F'|' '/^wayfare-[a-z-]+\|/ && $2 != "*" { print $2 "|" $3 }' "$FIELDS" | sort -u)
SEEN_PAIRS=$("$FIELDS" --all "$R" | awk -F'\t' 'NR > 1 { print $2 "|" $3 }' | sort -u)
check "--all reaches every mapped field" "" "$(comm -23 <(echo "$ALL_PAIRS") <(echo "$SEEN_PAIRS") | tr '\n' ' ' | sed 's/ $//')"
check "the recalibrate-config skill reads the whole map" "yes" \
  "$(grep -q 'hero-fields.sh" --all$' \
      "$PLUGIN_ROOT/skills/wayfare-recalibrate-config/SKILL.md" && echo yes || echo no)"

# The loop accumulates into a variable that starts empty, so it passes when it
# examines nothing. This is what makes it mean something.
check "the mapped-skills loop examined something" "yes" "$([ "$MAPPED" -gt 0 ] && echo yes || echo no)"
# The OTHER loop needs its own counterweight. declares_verb parses the first
# frontmatter block; reflow it, or rename the key, and every skill `continue`s,
# MISSING stays empty, and "every skill offering recalibrate has map rows"
# reports PASS having checked nothing.
check "the declared-skills loop examined something" "yes" "$([ "$DECLARED" -gt 0 ] && echo yes || echo no)"

# Connection blocks: a `### kind` under `## Connections` is reached by its
# `Heading::kind` section, and `## CI/CD` proves the separator cannot be `/`.
# The (n/a: type=none) sentinel is the one that keeps recalibrate from asking a
# repo with no design system to name one on every single run.
CR="$(cd "$TMP" && pwd -P)/connrepo"
mkdir -p "$CR"
cat > "$CR/HERO.md" <<'EOM'
# Hero Configuration

## CI/CD

- platform: github-actions

## Connections

### design

- type: none

### issues

- type: github
- at: acme/web
- issue-prefix: PROJ

## Projects

### design

- language: go

### reference

- language: go
EOM

OUT_C=$("$FIELDS" wayfare-sync-plan "$CR")
check "connection field reads from its own block" \
  "none" "$(printf '%s' "$OUT_C" | awk -F'\t' '$1 == "Connections::design" && $2 == "type" { print $3 }')"
check "type=none marks the block's other rows n/a, not a question" \
  "(n/a: type=none)" "$(printf '%s' "$OUT_C" | awk -F'\t' '$1 == "Connections::design" && $2 == "at" { print $3 }')"
check "a missing connection block is (no-section)" \
  "(no-section)" "$(printf '%s' "$OUT_C" | awk -F'\t' '$1 == "Connections::architecture" { print $3 }')"
# `### reference` exists under ## Projects and nowhere else. A probe that does
# not scope the H3 to its parent H2 reports the CONNECTION as present, and
# recalibrate then never asks for a connection an unrelated project shadowed.
check "a block under another section does not count as the connection" \
  "(no-section)" "$(printf '%s' "$OUT_C" | awk -F'\t' '$1 == "Connections::reference" && $2 == "type" { print $3 }')"
# The two guarded keys are refused by every runtime reader; a table that
# reports one as configured is a table recalibrate never asks about.
CR2="$(cd "$TMP" && pwd -P)/connrepo2"
mkdir -p "$CR2"
printf '# Hero\n\n## Connections\n\n### issues\n\n- type: github\n- at: ghe.attacker.example/owner/repo\n' > "$CR2/HERO.md"
check "a guarded value the readers refuse reports (refused)" \
  "(refused)" "$("$FIELDS" wayfare-build-task "$CR2" | awk -F'\t' '$1 == "Connections::issues" && $2 == "at" { print $3 }')"
printf '# Hero\n\n## Connections\n\n### design\n\n- type: -none\n- at: x\n' > "$CR2/HERO.md"
check "a refused discriminator blocks its block's other rows" \
  "(n/a: type=refused)" "$("$FIELDS" wayfare-sync-plan "$CR2" | awk -F'\t' '$1 == "Connections::design" && $2 == "at" { print $3 }')"
printf '# Hero\n\n## Connections\n\n### design-system\n\n- type: self\n' > "$CR2/HERO.md"
check "type self answers for its block too" \
  "(n/a: type=self)" "$("$FIELDS" wayfare-sync-plan "$CR2" | awk -F'\t' '$1 == "Connections::design-system" && $2 == "at" { print $3 }')"
OUT_I=$("$FIELDS" wayfare-push-pr "$CR")
check "a set connection field reports its value" \
  "PROJ" "$(printf '%s' "$OUT_I" | awk -F'\t' '$1 == "Connections::issues" && $2 == "issue-prefix" { print $3 }')"
# `## CI/CD` has a slash in the heading. Split the section name on `/` and the
# heading probe looks for `## CI`, which is absent, so every CI/CD field
# reports (no-section) — a field that is merely unset then reads as a whole
# section nobody has written.
OUT_P=$("$FIELDS" wayfare-check-preflight "$CR")
check "a heading containing a slash still resolves to its section" \
  "(unset)" "$(printf '%s' "$OUT_P" | awk -F'\t' '$1 == "CI/CD" && $2 == "auto-approve-installed" { print $3 }')"

if [ "$FAIL" -gt 0 ]; then
  echo "hero-fields: $PASS passed, $FAIL FAILED"
  exit 1
fi
# Floor on the case count, for the reason hero-lib.test.sh carries one: the
# suite runs without `set -e`, so a block that stops executing reports zero
# failures and exits 0.
MIN_CASES=40
if [ "$PASS" -lt "$MIN_CASES" ]; then
  echo "hero-fields: only $PASS cases ran, expected >= $MIN_CASES — a block stopped executing" >&2
  exit 1
fi
echo "hero-fields: $PASS passed"
