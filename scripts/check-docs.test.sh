#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/check_docs.py.
#
# Each case builds a minimal checkout, breaks one rule, and asserts the check
# names it; the clean fixture asserts nothing fires, so a check that starts
# matching everything fails here too.
#
# Usage: bash scripts/check-docs.test.sh

set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/check_docs.py"

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

python3 -c 'import yaml' 2>/dev/null || { echo "SKIP: pyyaml not installed"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# A commit hook runs this with GIT_INDEX_FILE (and friends) pointing at the
# outer repo; left set, every fixture `git add` writes into that real index.
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)

fixture() {
  R="$TMP/r$RANDOM$RANDOM"
  mkdir -p "$R/docs" "$R/scripts" "$R/skills/wayfare-demo"
  git init -q "$R"
  printf '# P\n\n```\na → b → c\n```\n\nThree steps: a, b, c.\n' > "$R/docs/PIPELINES.md"
  printf '# C\n\n## The kinds\n\n| Kind | x |\n| --- | --- |\n| `one` | x |\n| `two` | x |\n\n## Next\n' > "$R/docs/CONNECTIONS.md"
  printf 'wayfare-ship-pr|R|a|b\n' > "$R/scripts/hero-fields.sh"
  cat > "$R/skills/wayfare-demo/SKILL.md" <<'EOF'
---
name: wayfare-demo
description: "Does one thing: demo. Use when testing."
---

# Demo

## Instructions

### Step 1: First

#### 1a: Sub

#### 1b: Sub

### Step 2: Second

Run `a → b → c` and see [the plan](../../docs/PIPELINES.md).

## Other mode

### Step 1: Again
EOF
  printf '# Readme\n\nTwo kinds, one block each.\n' > "$R/README.md"
}
run() { git -C "$R" add -A >/dev/null; python3 "$SCRIPT" --root "$R" 2>/dev/null; }
checks_of() { run | sed -nE 's/.*\[([a-z]+)\].*/\1/p' | sort -u | tr '\n' ' ' | sed 's/ $//'; }
SK() { printf '%s\n' "$R/skills/wayfare-demo/SKILL.md"; }

fixture
check "clean fixture passes" "" "$(run)"

fixture; sed -i.bak 's/^description: .*/description: Does one thing: demo./' "$(SK)"; rm -f "$(SK).bak"
check "unquoted colon in frontmatter" "frontmatter" "$(checks_of)"

fixture; printf -- '---\ndescription: "x. Use when y."\nname: wayfare-demo\n---\n' > "$(SK)"
check "keys out of order" "frontmatter" "$(checks_of)"

fixture; sed -i.bak 's/### Step 2: Second/### Step 3: Second/' "$(SK)"; rm -f "$(SK).bak"
check "gap in step numbers" "steps" "$(checks_of)"

fixture; sed -i.bak 's/#### 1b: Sub/#### 1c: Sub/' "$(SK)"; rm -f "$(SK).bak"
check "gap in sub-step letters" "steps" "$(checks_of)"

fixture; printf '\nPass <branch-name> here.\n' >> "$(SK)"
check "lowercase placeholder" "placeholder" "$(checks_of)"

fixture; printf '\nSee <https://example.com> and <br> and `<code-name>`.\n' >> "$(SK)"
check "autolinks, html and inline code are not placeholders" "" "$(run)"

fixture; printf '\nTODO: finish this.\n' >> "$(SK)"
check "leftover TODO note" "todo" "$(checks_of)"

fixture; printf '\nLook for TODO/FIXME markers in the code.\n' >> "$(SK)"
check "prose naming TODO markers is fine" "" "$(run)"

fixture; printf '\nThis \xe2\x80\x94 that.\n' >> "$R/README.md"
check "em dash" "prose" "$(checks_of)"

fixture; printf '\nHe said \xe2\x80\x9cso\xe2\x80\x9d.\n' >> "$R/README.md"
check "curly quotes" "prose" "$(checks_of)"

fixture; printf '\nA load-bearing wall.\n' >> "$R/README.md"
check "banned phrase" "prose" "$(checks_of)"

fixture; printf '\n```\nThis \xe2\x80\x94 that.\n```\n\nInline `a \xe2\x80\x94 b` too.\n\n<!-- check-docs: off -->\nBefore: x \xe2\x80\x94 y.\n<!-- check-docs: on -->\n' >> "$R/README.md"
check "code and exempt regions are skipped" "" "$(run)"

fixture; printf '\nA span `wrapped\nacross \xe2\x80\x94 lines` is code.\n' >> "$R/README.md"
check "a code span wrapped over two lines is still code" "" "$(run)"

fixture; printf '\n| a | b |\n| -- | -- |\n| x | y |\n\nThe changes -- long overdue -- land.\n' >> "$R/README.md"
check "a double hyphen is flagged, a table delimiter is not" "1" "$(run | grep -c '\[prose\]')"

fixture; printf -- '---\ndescription: Rules: for x.\n---\n\n# R\n' > "$R/rule.md"
check "any frontmatter must parse, not only a skill's" "frontmatter" "$(checks_of)"

fixture; printf '\nThe order is a → b → d.\n' >> "$R/README.md"
check "chain that differs from PIPELINES.md" "chain" "$(checks_of)"

fixture; printf '\nFour steps:\na → b → c\n' >> "$R/README.md"
check "stage count beside a chain" "chain" "$(checks_of)"

fixture; printf '\nThree kinds, one block each.\n' >> "$R/README.md"
check "number word that miscounts" "count" "$(checks_of)"

fixture; printf 'x: 1\n' > "$R/ci.yml"
check "tracked .yml" "yml" "$(checks_of)"

fixture; printf '\nSee [gone](docs/MISSING.md).\n' >> "$R/README.md"
check "broken relative link" "link" "$(checks_of)"

fixture; ln -s README.md "$R/CLAUDE.md"; printf '\nThis \xe2\x80\x94 that.\n' >> "$R/README.md"
check "a symlink is not checked twice" "1" "$(run | grep -c '\[prose\]')"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
