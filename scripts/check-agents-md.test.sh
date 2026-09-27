#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for check-agents-md.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (1, 2 and 3 are contract,
# not failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/check-agents-md.sh"
DOC="$HERE/../docs/AGENTS-MD.md"

PASS=0
FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $name"
    echo "  expected: $expected"
    echo "  actual:   $actual"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# fixture NAME: a repo root with a compliant 30-line AGENTS.md and the symlink.
# The R2 boundary cases below add to that 30.
fixture() {
  local d="$WORK/$1"
  mkdir -p "$d/.claude/rules"
  {
    echo "# AGENTS.md"
    echo
    echo "## Conventions"
    for i in $(seq 1 27); do echo "- Rule $i names a trap and the fix for it."; done
  } > "$d/AGENTS.md"
  ln -s AGENTS.md "$d/CLAUDE.md"
  echo "$d"
}

lines() { for i in $(seq 1 "$1"); do echo "- filler line $i"; done; }
run() { out=$("$CHECK" "$@" 2>&1); rc=$?; }
has() { grep -qF -- "$1" <<<"$out" && echo yes || echo no; }

# --- compliant repo ----------------------------------------------------------
d=$(fixture good)
run "$d"
check "good: rc" "0" "$rc"
check "good: summary" "yes" "$(has ' 0 error(s), 0 warning(s)')"

# --- argument contract ---------------------------------------------------------
run "$d" --bogus
check "unknown flag: rc" "2" "$rc"
run "$d" "$d"
check "two positionals: rc" "2" "$rc"
run "$d/AGENTS.md"
check "file as ROOT: rc" "2" "$rc"
run --help
check "--help: rc" "0" "$rc"
check "--help: prints usage" "yes" "$(has 'Usage:')"
run --warn-only "$d"
check "flag before root: rc" "0" "$rc"

# --- R1 ------------------------------------------------------------------------
d=$(fixture both)
rm "$d/CLAUDE.md"; cp "$d/AGENTS.md" "$d/CLAUDE.md"
run "$d"
check "R1 both regular files: rc" "1" "$rc"
check "R1 both regular files: named" "yes" "$(has 'R1: AGENTS.md and CLAUDE.md are both regular')"

d=$(fixture claude_only)
rm "$d/CLAUDE.md"; mv "$d/AGENTS.md" "$d/CLAUDE.md"
run "$d"
check "R1 CLAUDE.md only: rc (warn, not error)" "0" "$rc"
check "R1 CLAUDE.md only: warned" "yes" "$(has 'WARN:  R1')"

d=$(fixture agents_only); rm "$d/CLAUDE.md"
run "$d"
check "R1 AGENTS.md only: rc (warn)" "0" "$rc"
check "R1 AGENTS.md only: warned" "yes" "$(has 'CLAUDE.md is missing')"

# A wrong symlink is an R1 error, but the checks still run against AGENTS.md,
# not through the link.
d=$(fixture wrong_link)
rm "$d/CLAUDE.md"; lines 300 > "$d/README.md"; ln -s README.md "$d/CLAUDE.md"
run "$d"
check "R1 wrong symlink target: rc" "1" "$rc"
check "R1 wrong symlink target: checks AGENTS.md not the link" "no" "$(has 'R2:')"

d=$(fixture dot_link); rm "$d/CLAUDE.md"; ln -s ./AGENTS.md "$d/CLAUDE.md"
run "$d"
check "R1 ./AGENTS.md link form: rc" "0" "$rc"

d=$(fixture dangling); rm "$d/AGENTS.md"
run "$d"
check "R1 dangling symlink: rc" "2" "$rc"
check "R1 dangling symlink: summary still printed" "yes" "$(has 'error(s)')"
run "$d" --warn-only
check "R1 dangling symlink with --warn-only: still 2" "2" "$rc"

d=$(fixture neither); rm "$d/CLAUDE.md" "$d/AGENTS.md"
run "$d"
check "R1 neither: rc" "2" "$rc"
run "$d" --warn-only
check "R1 neither with --warn-only: still 2" "2" "$rc"

# --- R2 ------------------------------------------------------------------------
d=$(fixture too_long); lines 171 >> "$d/AGENTS.md"
run "$d"
check "R2 201 lines: rc" "1" "$rc"
check "R2 201 lines: named" "yes" "$(has 'R2: AGENTS.md is 201 lines')"

d=$(fixture at_max); lines 170 >> "$d/AGENTS.md"
run "$d"
check "R2 exactly 200 lines: rc (warn)" "0" "$rc"
check "R2 exactly 200 lines: warned" "yes" "$(has 'WARN:  R2')"

d=$(fixture at_warn); lines 120 >> "$d/AGENTS.md"
run "$d"
check "R2 exactly 150 lines: no warning" "no" "$(has 'WARN:  R2')"

d=$(fixture comments)
{ echo "<!--"; lines 180; echo "-->"; } >> "$d/AGENTS.md"
run "$d"
check "R2 comment lines are free: rc" "0" "$rc"

d=$(fixture crlf_main)
{ echo; echo "## Layout"; lines 8; } | sed 's/$/\r/' >> "$d/AGENTS.md"
run "$d"
check "CRLF main file: R5 still fires" "yes" "$(has 'R5: "## Layout"')"

# --- R3 ------------------------------------------------------------------------
d=$(fixture rule_unscoped); lines 61 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 unscoped 61-line rule: rc" "1" "$rc"
check "R3 unscoped 61-line rule: named" "yes" "$(has 'R3: .claude/rules/big.md')"

d=$(fixture rule_at_max); lines 60 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 unscoped 60-line rule: rc" "0" "$rc"

d=$(fixture rule_scoped)
printf -- '---\ndescription: x\npaths:\n  - "src/**"\n---\n' > "$d/.claude/rules/big.md"; lines 61 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 scoped (list form): rc" "0" "$rc"

d=$(fixture rule_scoped_inline)
printf -- '---\npaths: ["src/**"]\n---\n' > "$d/.claude/rules/big.md"; lines 61 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 scoped (inline form): rc" "0" "$rc"

d=$(fixture rule_paths_empty)
printf -- '---\npaths:\n---\n' > "$d/.claude/rules/big.md"; lines 61 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 paths: with no value: rc" "1" "$rc"

d=$(fixture rule_unclosed)
printf -- '---\ndescription: x\n' > "$d/.claude/rules/big.md"; lines 61 >> "$d/.claude/rules/big.md"; echo "paths: are described above" >> "$d/.claude/rules/big.md"
run "$d"
check "R3 unclosed frontmatter, paths: in body: rc" "1" "$rc"

d=$(fixture rule_crlf)
printf -- '---\r\npaths: ["src/**"]\r\n---\r\n' > "$d/.claude/rules/big.md"; lines 61 | sed 's/$/\r/' >> "$d/.claude/rules/big.md"
run "$d"
check "R3 scoped CRLF rule: rc" "0" "$rc"

d=$(fixture rule_bom)
printf -- '\xEF\xBB\xBF---\npaths: ["src/**"]\n---\n' > "$d/.claude/rules/big.md"; lines 61 >> "$d/.claude/rules/big.md"
run "$d"
check "R3 scoped BOM rule: rc" "0" "$rc"

d=$(fixture rule_nested); mkdir -p "$d/.claude/rules/web"; lines 61 >> "$d/.claude/rules/web/deep.md"
run "$d"
check "R3 nested rules dir: rc" "1" "$rc"
check "R3 nested rules dir: relative path" "yes" "$(has 'R3: .claude/rules/web/deep.md')"

# --- R4 ------------------------------------------------------------------------
d=$(fixture shouty); for i in $(seq 1 6); do echo "- IMPORTANT: rule $i" >> "$d/AGENTS.md"; done
run "$d"
check "R4 six emphasized lines: rc" "1" "$rc"

d=$(fixture five_emph); for i in $(seq 1 5); do echo "- NEVER do $i" >> "$d/AGENTS.md"; done
run "$d"
check "R4 exactly five: rc (warn)" "0" "$rc"
check "R4 exactly five: warned" "yes" "$(has 'WARN:  R4')"

d=$(fixture one_emph); echo "- IMPORTANT: one" >> "$d/AGENTS.md"
run "$d"
check "R4 exactly one: silent" "no" "$(has 'R4')"

d=$(fixture lower_emph); for i in $(seq 1 6); do echo "- you must never do $i" >> "$d/AGENTS.md"; done
run "$d"
check "R4 lowercase is not emphasis" "no" "$(has 'R4')"

d=$(fixture fence_emph); { echo '```bash'; for i in $(seq 1 6); do echo "MUST_SET_$i=1"; done; echo '```'; } >> "$d/AGENTS.md"
run "$d"
check "R4 emphasis in fence: rc" "0" "$rc"

# --- R5 ------------------------------------------------------------------------
d=$(fixture layout_table)
{ echo; echo "## Layout"; echo; echo "| Path | Purpose |"; echo "| --- | --- |"
  for i in $(seq 1 6); do echo "| \`dir$i/\` | thing $i |"; done; echo; echo "## After"; echo "- x"; } >> "$d/AGENTS.md"
run "$d"
check "R5 8-line Layout table: rc" "1" "$rc"
check "R5 8-line Layout table: named" "yes" "$(has 'R5: "## Layout" has 8 lines')"

d=$(fixture layout_pointer)
{ echo; echo "## Tech Stack"; echo "See HERO.md."; echo; echo "## Layout"; echo "\`ls\` shows it; assets/ is vendored downstream."; } >> "$d/AGENTS.md"
run "$d"
check "R5 pointer sections: rc" "0" "$rc"

d=$(fixture layout_at_max); { echo; echo "## Layout"; lines 5; } >> "$d/AGENTS.md"
run "$d"
check "R5 exactly five body lines: rc" "0" "$rc"

d=$(fixture layout_then_long)
{ echo; echo "## Layout"; echo "See HERO.md."; echo; echo "## Conventions"; lines 10; } >> "$d/AGENTS.md"
run "$d"
check "R5 sibling section not counted: rc" "0" "$rc"

d=$(fixture layout_child)
{ echo; echo "## Layout"; echo "See HERO.md."; echo "### Detail"; lines 6; } >> "$d/AGENTS.md"
run "$d"
check "R5 child heading counted toward parent: rc" "1" "$rc"

d=$(fixture layout_rules)
{ echo; echo "## Page layout rules"; lines 8; } >> "$d/AGENTS.md"
run "$d"
check "R5 heading containing 'layout': rc" "0" "$rc"

d=$(fixture layout_suffixed)
{ echo; echo "## Data model — Phase 1 (singleton)"; lines 8; } >> "$d/AGENTS.md"
run "$d"
check "R5 name with trailing dash clause: rc" "1" "$rc"

d=$(fixture layout_in_fence)
{ echo; echo '```markdown'; echo "## Layout"; lines 8; echo '```'; } >> "$d/AGENTS.md"
run "$d"
check "R5 heading inside a code fence: rc" "0" "$rc"

# docs/AGENTS-MD.md is the spec: every name it lists under R5 must trip the
# checker. The extraction is asserted non-empty first, because a renumbered doc
# would otherwise run zero cases and pass.
# The whole numbered item, not its first line: mdformat wraps the doc, so a
# list of names routinely continues onto the next lines.
doc_item() { awk -v head="$1. **R$1" 'index($0, head) == 1 {on=1; print; next} on && (/^[0-9]+\. / || /^$/) {exit} on' "$DOC"; }
r5_names=$(doc_item 5 | grep -oE '`[^`]+`' | tr -d '`')
check "R5 doc list extracted" "yes" "$([[ -n "$r5_names" ]] && echo yes || echo no)"
while IFS= read -r name; do
  d=$(fixture "doc_r5_$(tr -c 'a-z' _ <<<"$name")")
  { echo; echo "## $name"; lines 8; } >> "$d/AGENTS.md"
  run "$d"
  check "R5 doc-listed heading '$name': rc" "1" "$rc"
done <<<"$r5_names"

# --- R6 ------------------------------------------------------------------------
r6_phrases=$(doc_item 6 | grep -oE '`[^`]+`' | tr -d '`')
check "R6 doc list extracted" "yes" "$([[ -n "$r6_phrases" ]] && echo yes || echo no)"
while IFS= read -r phrase; do
  d=$(fixture "doc_r6_$(tr -c 'a-z' _ <<<"$phrase")")
  echo "- Careful, this is $phrase here." >> "$d/AGENTS.md"
  run "$d"
  check "R6 doc-listed phrase '$phrase': rc" "1" "$rc"
done <<<"$r6_phrases"

# The reported line number is the file's, not the stripped buffer's.
d=$(fixture banned_lineno)
{ echo "<!--"; echo "note"; echo "note"; echo "-->"; echo "- This config is Load-Bearing."; } >> "$d/AGENTS.md"
run "$d"
check "R6 banned phrase: rc" "1" "$rc"
check "R6 banned phrase: real line number (35), case-insensitive" "yes" "$(has '35:- This config is Load-Bearing.')"

d=$(fixture banned_in_rule); echo "Give an honest take." > "$d/.claude/rules/writing.md"
run "$d"
check "R6 banned phrase in a rule: rc" "1" "$rc"

d=$(fixture banned_fenced)
printf -- 'Do not write these:\n\n```text\nload-bearing\nhonest take\n```\n' > "$d/.claude/rules/writing.md"
{ echo '```'; echo "load-bearing"; echo '```'; } >> "$d/AGENTS.md"
run "$d"
check "R6 banned list in fences (rule and main): rc" "0" "$rc"

d=$(fixture banned_in_comment); printf -- '<!-- load-bearing -->\n' >> "$d/AGENTS.md"
run "$d"
check "R6 banned phrase in an HTML comment: rc" "0" "$rc"

# --- error accumulation and --warn-only ---------------------------------------------
d=$(fixture two_errors); lines 171 >> "$d/AGENTS.md"; echo "- delve" >> "$d/AGENTS.md"
run "$d"
check "two errors: counted" "yes" "$(has ' 2 error(s)')"
run "$d" --warn-only
check "--warn-only on failing repo: rc" "0" "$rc"
check "--warn-only still reports" "yes" "$(has 'ERROR: R2')"

# --- checker cannot run: exit 3, never 0 -------------------------------------------
d=$(fixture no_perl); mkdir -p "$WORK/bin"; printf '#!/bin/sh\nexit 127\n' > "$WORK/bin/perl"; chmod +x "$WORK/bin/perl"
out=$(PATH="$WORK/bin:$PATH" "$CHECK" "$d" 2>&1); rc=$?
check "perl failing: rc" "3" "$rc"

if [[ "$(id -u)" != "0" ]]; then
  d=$(fixture unreadable); chmod 000 "$d/AGENTS.md"
  run "$d"
  check "unreadable AGENTS.md: rc" "3" "$rc"
  chmod 644 "$d/AGENTS.md"

  d=$(fixture unreadable_rule); lines 80 >> "$d/.claude/rules/x.md"; chmod 000 "$d/.claude/rules/x.md"
  run "$d"
  check "unreadable rule: rc" "3" "$rc"
  chmod 644 "$d/.claude/rules/x.md"

  d=$(fixture unreadable_rules_dir); lines 80 >> "$d/.claude/rules/x.md"; chmod 000 "$d/.claude/rules"
  run "$d"
  check "unreadable rules dir: rc" "3" "$rc"
  chmod 755 "$d/.claude/rules"
fi

# --- --commit-msg ----------------------------------------------------------------
m="$WORK/msg"; echo "feat: the Load-Bearing fix" > "$m"
run --commit-msg "$m"
check "commit-msg banned (case-insensitive): rc" "1" "$rc"
echo "feat: strip inbound headers in filterHeaders" > "$m"
run --commit-msg "$m"
check "commit-msg clean: rc" "0" "$rc"
printf 'feat: x\n# load-bearing is mentioned in this git comment\n' > "$m"
run --commit-msg "$m"
check "commit-msg banned only in # comment: rc" "0" "$rc"
printf 'feat: x\n# ------------------------ >8 ------------------------\n+settings are load-bearing here\n' > "$m"
run --commit-msg "$m"
check "commit-msg banned only below scissors: rc" "0" "$rc"
run --commit-msg "$WORK/does-not-exist"
check "commit-msg missing file: rc" "3" "$rc"
run --commit-msg "$m" --warn-only
check "commit-msg with extra option: rc" "2" "$rc"
run "$d" --commit-msg "$m"
check "commit-msg not first: rc" "2" "$rc"

echo ""
echo "check-agents-md.test.sh: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
