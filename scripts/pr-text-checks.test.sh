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
trap 'chmod -R u+rw "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT
# A commit hook runs this with GIT_INDEX_FILE (and friends) pointing at the
# outer repo; left set, every fixture `git add` writes into that real index.
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)

FOOT='_Generated using wayfare._'
body() { printf '%b\n' "$1" > "$TMP/body.md"; }
kinds() { sed -E 's/^pr_text_lint: ([a-z]+):.*/\1/' | sort -u | tr '\n' ' ' | sed 's/ $//'; }
# A crash or a usage error (exit 2) must not read as "no findings".
lint() {
  local out rc
  out=$(python3 "$LINT" "$@" --body-file "$TMP/body.md" 2>&1); rc=$?
  if [ "$rc" -gt 1 ]; then echo "exit $rc"; else printf '%s\n' "$out" | kinds; fi
}

body "## Summary\n\nAdds the thing.\n\n$FOOT"
check "clean pr" "" "$(lint --kind pr --title 'feat: add the thing')"
check "clean comment" "" "$(lint --kind comment)"
check "body on stdin" "" "$(python3 "$LINT" --kind comment --body-file - < "$TMP/body.md" | kinds)"
check "title over 70" "title" "$(lint --kind pr --title "feat: $(printf 'x%.0s' {1..70})")"
check "pr with no title" "title" "$(lint --kind pr)"

# The brand, not the words: `hero` is ordinary English and wayfare-push-pr is
# a skill name, so only the brand spellings fail.
for t in 'feat: wayfare adds the thing' 'Add wayfare support' 'feat: AI Hero onboarding' \
  'docs: credit A.I. Hero' 'feat: Hero dashboard'; do
  check "branded title: $t" "title" "$(lint --kind pr --title "$t")"
done
for t in 'fix(ui): hero section overflows' 'feat(wayfare-push-pr): lint the body' \
  'docs: document HERO.md' 'fix: read `wayfare` from config'; do
  check "unbranded title: $t" "" "$(lint --kind pr --title "$t")"
done
check "prose rules apply to the title" "prose" "$(lint --kind pr --title "$(printf 'fix: it works \xe2\x80\x94 mostly')")"

body "## Summary\n\nAdds the thing."
check "missing footer" "footer" "$(lint --kind comment)"
check "a commit needs no footer" "" "$(lint --kind commit)"
check "an inline comment needs no footer" "" "$(lint --kind inline)"

body "$FOOT\n\nmore\n\n$FOOT"
check "footer twice" "footer" "$(lint --kind review)"

body "Every post ends with \`$FOOT\`.\n\n$FOOT"
check "a footer quoted in code is not a second footer" "" "$(lint --kind comment)"

body "DRAFTED_FULL_BODY_HERE\n\n$FOOT"
check "placeholder left in" "placeholder" "$(lint --kind pr --title 'fix: x')"

body "gh pr review 1 {DECISION_FLAG}\n\n$FOOT"
check "brace placeholder left in" "placeholder" "$(lint --kind review)"

body "- [agent] {file:line}: {finding}\n\n$FOOT"
check "lowercase brace slot left in" "placeholder" "$(lint --kind comment)"

body "- {what's well-done}\n\n$FOOT"
check "brace slot with spaces left in" "placeholder" "$(lint --kind comment)"

body "The route is /users/{id} and it returns {ok: true}.\n\n$FOOT"
check "braces in ordinary prose" "" "$(lint --kind comment)"

body "## Self-Review\n<!-- ai-hero:self-review {N} FILE:LINE -->\n\nAll good.\n\n$FOOT"
check "placeholders inside an HTML comment" "" "$(lint --kind comment)"

body "Commits: SHA1, SHA2\n\n$FOOT"
check "Commits: SHA1 left in" "placeholder" "$(lint --kind comment)"

body "The SHA1 hash is no longer accepted.\n\n$FOOT"
check "SHA1 in prose" "" "$(lint --kind comment)"

body "- a.ts:3: QUESTION. Answer: because\n- b.ts:4: FINDING. Skipped: REASON\n\n$FOOT"
check "uppercase template words in template position" "placeholder" "$(lint --kind comment)"

body "The QUESTION is whether the REASON holds.\n\n$FOOT"
check "uppercase words in prose" "" "$(lint --kind comment)"

body "## Summary\n[1-3 sentence overview]\n\n- [ ] [Test step 1]\n\n$FOOT"
check "unfilled bracket slot lines" "placeholder" "$(lint --kind comment)"

body "See [the docs](https://x.invalid) and\n[a link](y.md)\n- [x] done\n- [ ]\n[ref]\n\n[ref]: https://x.invalid\n\n$FOOT"
check "links, boxes and shortcut references are not slots" "" "$(lint --kind comment)"

body "It works \xe2\x80\x94 mostly.\n\n$FOOT"
check "em dash" "prose" "$(lint --kind comment)"
check "an inline comment gets the prose rules" "prose" "$(lint --kind inline)"
check "pr-edit leaves an inherited body's prose alone" "" "$(lint --kind pr-edit --title 'fix: x')"

body "Nice docs \xf0\x9f\x91\x8d\n\nDRAFTED_FULL_BODY_HERE"
check "pr-edit still wants the footer and no placeholders" "footer placeholder" "$(lint --kind pr-edit --title 'fix: x')"

body "A load-bearing change.\n\n$FOOT"
check "banned phrase" "prose" "$(lint --kind comment)"

body "Run \`a \xe2\x80\x94 b\`:\n\n\`\`\`\nx \xe2\x80\x94 y\n\`\`\`\n\n$FOOT"
check "dashes in code are fine" "" "$(lint --kind comment)"

body "fix(api): handle the null case\n\nThe guard returns early.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
check "a commit with a Co-Authored-By trailer" "" "$(lint --kind commit)"

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

# Every template the three skills post, filled with sample values, must pass,
# and left unfilled must fail. A template the lint can never pass would stop
# every post; one it passes unfilled would post its placeholders.
cat > "$TMP/templates.py" <<'PY'
import pathlib, re, subprocess, sys
root, lint = pathlib.Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(root / "scripts"))
from pr_text_lint import SLOT_LINE
FILL = {
    "DRAFTED_FULL_BODY_HERE": "## Summary\n\nHandles the null case.\n\n_Generated using wayfare._",
    "{file:line}": "src/app.ts:12", "FILE:LINE": "src/app.ts:12",
    "{finding}": "the null case is unhandled", "FINDING": "The null case is unhandled",
    "FIX_DESCRIPTION": "added a guard", "REVIEWER_FEEDBACK": "Handle null",
    "ANSWER_OR_RATIONALE": "The helper predates this code.",
    "REASON_FOR_DECLINING": "out of scope", "Skipped: REASON": "Skipped: out of scope",
    "QUESTION": "Why not the helper?", "LIST_OR_NONE": "none",
    "SHA1": "abc1234", "SHA2": "def5678", "{what's well-done}": "Clear tests",
    "{type}": "fix", "{scope}": "api", "{description}": "handle the null case",
    "{body if needed}": "The guard returns early.",
    "{1-3 sentence summary}": "Solid change.", "{most important issue}": "Null case",
    "{second most important}": "Naming", "{positive observations}": "Good tests",
}
BLOCK = re.compile(r"(\w+)=\$\(cat <<'EOF'\n(.*?)\nEOF\n\)\n(.*?)pr_text_lint\.py\" --kind (\S+)"
                   r"(?: --title \"([^\"]*)\")?", re.S)

def fill(text):
    for k, v in FILL.items():
        text = text.replace(k, v)
    text = re.sub(r"\{summary of fix \d+\}", "Handle the null case", text)
    text = re.sub(r"\{[NWXYZ]\}", "1", text)
    return "\n".join(re.sub(r"\[[^\]]+\]\s*$", "Sample text", ln) if SLOT_LINE.match(ln) else ln
                     for ln in text.split("\n"))

def run(kind, title, text):
    args = ["python3", lint, "--kind", kind, "--body-file", "-"]
    if title is not None:
        args += ["--title", title]
    return subprocess.run(args, input=text + "\n", capture_output=True, text=True)

seen = 0
for skill in ("wayfare-push-pr", "wayfare-review-pr", "wayfare-respond-pr"):
    md = (root / "skills" / skill / "SKILL.md").read_text()
    for m in BLOCK.finditer(md):
        var, text, _, kind, title = m.groups()
        if "\n```" in m.group(3):
            continue
        seen += 1
        t = None if title is None else "fix: handle the null case"
        p = run(kind, t, fill(text))
        if p.returncode:
            print(f"{skill} {var} ({kind}) filled: {p.stdout.strip()}")
        if run(kind, t, text).returncode == 0:
            print(f"{skill} {var} ({kind}) passes with its placeholders still in")
if seen < 10:
    print(f"found only {seen} templates; the extraction regex has drifted")
PY
check "every skill template passes once filled" "" "$(python3 "$TMP/templates.py" "$HERE/.." "$LINT")"

# respond-pr posts only the quoted part of HERO.md's trigger field, which
# init writes as `"@greptile review" comment` or with backticks. Run the
# skill's own extraction line, so the test cannot drift from the skill.
EXTRACT=$(grep -m1 "TEXT=\$(printf '%s' \"\$TRIGGER\"" "$HERE/../skills/wayfare-respond-pr/SKILL.md" | sed 's/^ *//')
check "trigger extraction line found in respond-pr" "yes" "$([ -n "$EXTRACT" ] && echo yes || echo no)"
for form in '"@greptile review" comment' '`@greptile review` comment'; do
  got=$(TRIGGER="$form" bash -c "$EXTRACT"'; printf "%s" "$TEXT"')
  check "trigger text from: $form" "@greptile review" "$got"
done
check "an unquoted trigger yields no text" "" "$(TRIGGER='auto on push' bash -c "$EXTRACT"'; printf "%s" "$TEXT"')"

# diff_leftovers over a real repo. Fixture lines carry `leftovers: ok` in a
# shell comment outside the quotes, so this file passes its own scan while the
# fixture files it writes do not carry the marker.
R="$TMP/repo"
git init -q -b main "$R"
git -C "$R" config user.email tests@wayfare.invalid
git -C "$R" config user.name "wayfare tests"
printf 'old\n// TODO: pre-existing debt\n' > "$R/a.js" # leftovers: ok
git -C "$R" add -A && git -C "$R" commit -q -m init
left() {
  local out rc
  out=$(cd "$R" && python3 "$LEFT" "$@" 2>&1); rc=$?
  if [ "$rc" -gt 1 ]; then echo "exit $rc"; return; fi
  printf '%s\n' "$out" | sed -E 's/^.+:[0-9]+: ([a-z]+).*/\1/' | sort -u | tr '\n' ' ' | sed 's/^ //; s/ $//'
}

check "untouched debt is not flagged" "" "$(left)"
printf 'console.log(x)\n' >> "$R/a.js" # leftovers: ok
check "console.log added" "debug" "$(left)"
git -C "$R" checkout -q -- a.js
printf 'x = 1  # TODO: tidy\n' > "$R/b.py" # leftovers: ok
git -C "$R" add b.py
check "a staged todo added" "todo" "$(left)"
printf 'x = 1  # TODO(#42): tidy\ny = 2  # FIXME ABC-7\n' > "$R/b.py"; git -C "$R" add b.py
check "a todo with an issue reference" "" "$(left)"
printf 'print("usage: x")\n' > "$R/b.py"; git -C "$R" add b.py
check "print is not debug code" "" "$(left)"
printf 'Add a TODO list and console.log docs.\n' > "$R/notes.md"; git -C "$R" add notes.md # leftovers: ok
check "prose files are skipped" "" "$(left)"
printf 'debugger;\n' > "$R/new.js" # leftovers: ok
check "an untracked new file is read" "debug" "$(left)"
printf 'console.log(x) // leftovers: ok, the fixture\n' > "$R/new.js" # leftovers: ok
check "the allow marker accepts a line" "" "$(left)"
rm "$R/new.js"
git -C "$R" commit -q -m wip

printf 'x\n' > "$R/a b.js"; git -C "$R" add "a b.js"; git -C "$R" commit -q -m space
printf 'console.log(1)\n' >> "$R/a b.js" # leftovers: ok
check "a path with a space keeps its name" "a b.js:2" "$(cd "$R" && python3 "$LEFT" | cut -d: -f1,2)"
git -C "$R" checkout -q -- "a b.js"

printf 'x\n' > "$R/na$(printf '\xc3\xa9').js"; git -C "$R" add -A; git -C "$R" commit -q -m accent
printf 'console.log(1)\n' >> "$R/na$(printf '\xc3\xa9').js" # leftovers: ok
check "a non-ASCII path is not quoted" "na$(printf '\xc3\xa9').js:2" "$(cd "$R" && python3 "$LEFT" | cut -d: -f1,2)"
git -C "$R" checkout -q -- .

printf '++ looks like a header\nconsole.log(2)\n' >> "$R/a.js" # leftovers: ok
check "an added line starting ++ is content" "debug" "$(left)"
check "diff.noprefix does not break parsing" "debug" "$(cd "$R" && git config diff.noprefix true; python3 "$LEFT" | sed -E 's/^.+:[0-9]+: ([a-z]+).*/\1/'; git config --unset diff.noprefix)"
check "diff.mnemonicPrefix does not break parsing" "debug" "$(cd "$R" && git config diff.mnemonicPrefix true; python3 "$LEFT" | sed -E 's/^.+:[0-9]+: ([a-z]+).*/\1/'; git config --unset diff.mnemonicPrefix)"
git -C "$R" checkout -q -- a.js

printf 'ok\n\xff\xfe bad bytes\ndebugger\n' >> "$R/a.js" # leftovers: ok
check "invalid UTF-8 in a diff" "debug" "$(left)"
git -C "$R" checkout -q -- a.js
printf 'debugger\n\0binary\n' > "$R/blob.bin" # leftovers: ok
check "an untracked binary file is skipped" "" "$(left)"
rm "$R/blob.bin"

mkdir -p "$R/sub"; printf 'debugger\n' > "$R/top.js" # leftovers: ok
check "untracked files outside cwd are seen" "debug" "$( (cd "$R/sub" && python3 "$LEFT") | sed -E 's/^.+:[0-9]+: ([a-z]+).*/\1/' | sort -u)"
rm "$R/top.js"

printf 'debugger\n' > "$R/locked.js"; chmod 000 "$R/locked.js" # leftovers: ok
check "an unreadable untracked file does not crash" "0" "$( (cd "$R" && python3 "$LEFT" >/dev/null 2>&1); echo $?)"
chmod 600 "$R/locked.js"; rm "$R/locked.js"

git -C "$R" checkout -q -b feat
printf 'breakpoint()\n' > "$R/c.py"; git -C "$R" add c.py; git -C "$R" commit -q -m c # leftovers: ok
check "--base reads the whole branch" "debug" "$(left --base main)"
git -C "$R" rm -q c.py; git -C "$R" commit -q -m rm
printf 'console.log(3)\n' >> "$R/a.js" # leftovers: ok
check "--base reads an uncommitted edit" "debug" "$(left --base main)"
git -C "$R" checkout -q -- a.js
printf 'debugger\n' > "$R/u.js" # leftovers: ok
check "--base reads untracked files" "debug" "$(left --base main)"
rm "$R/u.js"
check "an unknown base exits 2" "2" "$( (cd "$R" && python3 "$LEFT" --base nope >/dev/null 2>&1); echo $?)"

E="$TMP/empty"
git init -q -b main "$E"
printf 'debugger\n' > "$E/x.js"; printf 'console.log(1)\n' > "$E/y.js"; git -C "$E" add y.js # leftovers: ok
check "a repo with no commits" "y.js x.js" "$(cd "$E" && python3 "$LEFT" | cut -d: -f1 | tr '\n' ' ' | sed 's/ $//')"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
