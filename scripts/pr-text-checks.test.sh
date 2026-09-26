#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/pr_text_lint.py and scripts/diff_leftovers.py,
# the two checks the skills run in a consumer repo before they post or push.
#
# Usage: bash scripts/pr-text-checks.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LINT="$HERE/pr_text_lint.py"
LEFT="$HERE/diff_leftovers.py"

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
# A commit hook runs this with GIT_INDEX_FILE (and friends) pointing at the
# outer repo; left set, every fixture `git add` writes into that real index.
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)

FOOT='_Generated using wayfare._'
body() { printf '%b\n' "$1" > "$TMP/body.md"; }
lint() { python3 "$LINT" "$@" --body-file "$TMP/body.md" | sed -E 's/^pr_text_lint: ([a-z]+):.*/\1/' | sort -u | tr '\n' ' ' | sed 's/ $//'; }

body "## Summary\n\nAdds the thing.\n\n$FOOT"
check "clean pr" "" "$(lint --kind pr --title 'feat: add the thing')"
check "clean comment" "" "$(lint --kind comment)"
check "title over 70" "title" "$(lint --kind pr --title "feat: $(printf 'x%.0s' {1..70})")"
check "branded title" "title" "$(lint --kind pr --title 'feat: wayfare adds the thing')"
check "pr with no title" "title" "$(lint --kind pr)"

body "## Summary\n\nAdds the thing."
check "missing footer" "footer" "$(lint --kind comment)"
check "a commit needs no footer" "" "$(lint --kind commit)"

body "$FOOT\n\nmore\n\n$FOOT"
check "footer twice" "footer" "$(lint --kind review)"

body "DRAFTED_FULL_BODY_HERE\n\n$FOOT"
check "placeholder left in" "placeholder" "$(lint --kind pr --title 'fix: x')"

body "gh pr review 1 {DECISION_FLAG}\n\n$FOOT"
check "brace placeholder left in" "placeholder" "$(lint --kind review)"

body "- [agent] {file:line}: {finding}\n\n$FOOT"
check "lowercase brace slot left in" "placeholder" "$(lint --kind comment)"

body "- {what's well-done}\n\n$FOOT"
check "brace slot with spaces left in" "placeholder" "$(lint --kind comment)"

body "## Summary\n[1-3 sentence overview]\n\n- [ ] [Test step 1]\n\n$FOOT"
check "unfilled bracket slot lines" "placeholder" "$(lint --kind comment)"

body "See [the docs](https://x.invalid) and\n[a link](y.md)\n- [x] done\n\n$FOOT"
check "links and checked boxes are not slots" "" "$(lint --kind comment)"

body "It works \xe2\x80\x94 mostly.\n\n$FOOT"
check "em dash" "prose" "$(lint --kind comment)"

body "A load-bearing change.\n\n$FOOT"
check "banned phrase" "prose" "$(lint --kind comment)"

body "Run \`a \xe2\x80\x94 b\`:\n\n\`\`\`\nx \xe2\x80\x94 y\n\`\`\`\n\n$FOOT"
check "dashes in code are fine" "" "$(lint --kind comment)"

# The lint runs in consumer repos, which may lack pyyaml; check_docs.py
# (whose prose rules it imports) must not need yaml at import time.
body "ok\n\n$FOOT"
check "runs without pyyaml" "0" "$(python3 -c "
import runpy, sys
sys.modules['yaml'] = None
sys.argv = ['pr_text_lint.py', '--kind', 'comment', '--body-file', '$TMP/body.md']
try:
    runpy.run_path('$LINT', run_name='__main__')
except SystemExit as e:
    print(e.code or 0)
" 2>&1)"

# diff_leftovers over a real repo.
R="$TMP/repo"
git init -q -b main "$R"
git -C "$R" config user.email tests@wayfare.invalid
git -C "$R" config user.name "wayfare tests"
printf 'old\n// TODO: pre-existing debt\n' > "$R/a.js"
git -C "$R" add -A && git -C "$R" commit -q -m init
left() { (cd "$R" && python3 "$LEFT" "$@") | sed -E 's/^[^:]+:[0-9]+: ([a-z]+).*/\1/' | sort -u | tr '\n' ' ' | sed 's/ $//'; }

check "untouched debt is not flagged" "" "$(left)"
printf 'console.log(x)\n' >> "$R/a.js"
check "console.log added" "debug" "$(left)"
git -C "$R" checkout -q -- a.js
printf 'x = 1  # TODO: tidy\n' > "$R/b.py"; git -C "$R" add b.py
check "untracked TODO added" "todo" "$(left)"
printf 'x = 1  # TODO(#42): tidy\ny = 2  # FIXME ABC-7\n' > "$R/b.py"; git -C "$R" add b.py
check "TODO with an issue reference" "" "$(left)"
printf 'print("usage: x")\n' > "$R/b.py"; git -C "$R" add b.py
check "print is not debug code" "" "$(left)"
printf 'Add a TODO list and console.log docs.\n' > "$R/notes.md"; git -C "$R" add notes.md
check "prose files are skipped" "" "$(left)"
printf 'debugger;\n' > "$R/new.js"
check "an untracked new file is read" "debug" "$(left)"
rm "$R/new.js"
git -C "$R" commit -q -m wip
git -C "$R" checkout -q -b feat
printf 'breakpoint()\n' > "$R/c.py"; git -C "$R" add c.py; git -C "$R" commit -q -m c
check "--base reads the whole branch" "debug" "$(left --base main)"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
