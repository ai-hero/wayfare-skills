#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Check a repo's agent-instructions files against docs/AGENTS-MD.md.
#
# Usage: check-agents-md.sh [REPO_ROOT] [--warn-only]
#        check-agents-md.sh --commit-msg FILE      (no other options)
#        check-agents-md.sh -h | --help
#
# Checks R1-R6 of the standard (the mechanical ones). R7-R10 need judgment
# and are left to a rewrite pass. Thresholds: R2 200 lines (warn above 150),
# R3 60 lines, R4 warn above 1 / fail above 5, R5 5 lines.
#
# Exit codes:
#   0  no rule errors, or --warn-only (rule findings only)
#   1  at least one rule error
#   2  usage error, or the instructions file was not found
#   3  the checker could not run: a tool is missing or a file is unreadable
# 2 and 3 are never downgraded by --warn-only.

set -uo pipefail

MAX_LINES=200
WARN_LINES=150
RULE_MAX_UNSCOPED=60
SECTION_MAX=5
EMPHASIS_WARN=1
EMPHASIS_MAX=5

# The name must be the whole heading (a trailing ":", "(", or dash clause is
# allowed): "## Page layout rules" is a real rule section, not a tree dump.
# No {n,m} intervals anywhere in these: mawk before 20200717 (Ubuntu 22.04)
# treats them as literal characters and the check silently never matches.
DERIVABLE='^#+ +(layout|tech(nology)? stack|directory (structure|layout)|project structure|folder structure|data model|architecture overview|dependencies|file[- ]by[- ]file)( *([(:-]|—|–).*)?$'
# Fenced code is exempt from R4/R6 so a writing rule can list the phrases it
# bans without tripping the check.
BANNED="load-bearing|honest take|belt and suspenders|that'?s the unlock|you'?re absolutely right|delve"
EMPHASIS='\b(IMPORTANT|CRITICAL|NEVER|ALWAYS|MUST)\b'

ERRORS=0
WARNINGS=0
WARN_ONLY=0
ROOT=""

usage() { sed -n '5,20p' "$0" | sed 's/^# \{0,1\}//'; }
error() { echo "  ERROR: $1"; [[ -n "${2:-}" ]] && echo "         Fix:  $2"; ERRORS=$((ERRORS + 1)); }
warn()  { echo "  WARN:  $1"; [[ -n "${2:-}" ]] && echo "         Fix:  $2"; WARNINGS=$((WARNINGS + 1)); }
# finish [CODE]: the one exit for every path after argument parsing, so the
# summary line is always printed and --warn-only applies only to rule errors.
finish() {
  echo ""
  echo "check-agents-md: $ERRORS error(s), $WARNINGS warning(s)"
  if [[ -n "${1:-}" ]]; then exit "$1"; fi
  if (( ERRORS > 0 && WARN_ONLY == 0 )); then exit 1; fi
  exit 0
}
die() { error "$2"; finish "$1"; }

for tool in perl awk grep find; do
  command -v "$tool" >/dev/null 2>&1 || { echo "check-agents-md: '$tool' is required but not on PATH"; exit 3; }
done

# --- commit-msg mode --------------------------------------------------------
if [[ "${1:-}" == "--commit-msg" ]]; then
  [[ $# -eq 2 ]] || { usage; exit 2; }
  msg="$2"
  [[ -r "$msg" ]] || { echo "check-agents-md: cannot read commit message file '$msg'"; exit 3; }
  # `git commit -v` appends the staged diff below a scissors line; git strips
  # it after the hook runs, so the hook must stop there too or every commit
  # touching a file that mentions a banned phrase is rejected.
  hits=$(awk -v re="$BANNED" '/^# -+ >8 -+$/{exit} !/^#/ && tolower($0) ~ re {print NR": "$0}' "$msg") \
    || { echo "check-agents-md: awk failed scanning '$msg'"; exit 3; }
  if [[ -n "$hits" ]]; then
    echo "check-agents-md: commit message uses a banned phrase (R6):"
    echo "$hits" | sed 's/^/  /'
    echo "  Say the specific thing instead of the metaphor."
    exit 1
  fi
  exit 0
fi

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --warn-only) WARN_ONLY=1 ;;
    --commit-msg) echo "check-agents-md: --commit-msg must be the first and only option"; exit 2 ;;
    -*) echo "check-agents-md: unknown option '$arg'"; usage; exit 2 ;;
    *) [[ -z "$ROOT" ]] || { echo "check-agents-md: one REPO_ROOT only"; exit 2; }; ROOT="$arg" ;;
  esac
done
[[ -n "$ROOT" ]] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[[ -d "$ROOT" ]] || { echo "check-agents-md: '$ROOT' is not a directory"; exit 2; }

# Everything below reads through stdin, never a filename argument: perl's <>
# treats a name starting with "|" as a command, and a committed file whose
# name contains a newline can put exactly that on the next line of a file list.
# normalize, what the loader sees: no BOM, no CR.
normalize()       { perl -0pe 's/\A\xEF\xBB\xBF//; s/\r\n/\n/g' < "$1"; }
# strip_comments, block HTML comments are removed before the file enters
# context, so they are free and must not count toward R2.
strip_comments()  { perl -0pe 's/<!--.*?-->//gs'; }
# blank_* keep line numbers intact so R6 can report the real line.
blank_comments()  { perl -0pe 's/(<!--.*?-->)/"\n" x ($1 =~ tr|\n||)/gse'; }
blank_fences()    { awk '/^```/{f=!f; print ""; next} f{print ""; next} {print}'; }
count_lines()     { grep -c ''; }
# grep_or_die PATTERN <<< TEXT: sets HITS; grep's exit 2 (bad pattern, I/O)
# is a checker failure, not "no match".
grep_or_die() { HITS=$(grep -n -E "$@"); local rc=$?; (( rc == 2 )) && die 3 "grep failed on pattern: $*"; return 0; }
# scoped FILE: true when the frontmatter block carries a paths: value. Only
# frontmatter scopes a rule; a paths: line in the body is prose, and an
# unclosed frontmatter is no frontmatter.
scoped() {
  normalize "$1" | awk '
    NR==1 && $0!="---" { exit }
    NR>1  && $0=="---" { closed=1; exit }
    /^paths:[[:space:]]*[^[:space:]]/ { found=1 }
    /^paths:[[:space:]]*$/ { want=1; next }
    want && /^[[:space:]]+-[[:space:]]*[^[:space:]]/ { found=1 }
    { want=0 }
    END { exit !(closed && found) }'
}
rules() {
  [[ -e "$ROOT/.claude/rules" ]] || return 0
  find "$ROOT/.claude/rules" -name '*.md' -type f -print0
}

# --- R1: one file, AGENTS.md ------------------------------------------------
# A CLAUDE.md symlink only warns: erroring would break every consumer's
# pre-commit the day this ships. Claude Code v2.1.277+ loads AGENTS.md itself.
echo "check-agents-md: $ROOT"
TARGET=""
if [[ -L "$ROOT/CLAUDE.md" ]]; then
  [[ -f "$ROOT/AGENTS.md" ]] || die 2 "R1: CLAUDE.md is a symlink, but AGENTS.md is missing"
  warn "R1: CLAUDE.md is a symlink — Claude Code loads AGENTS.md itself" "git rm CLAUDE.md"
  TARGET="$ROOT/AGENTS.md"
elif [[ -f "$ROOT/CLAUDE.md" && -f "$ROOT/AGENTS.md" ]]; then
  error "R1: AGENTS.md and CLAUDE.md are both regular files — edits will diverge" \
    "Merge CLAUDE.md into AGENTS.md, then git rm CLAUDE.md"
  TARGET="$ROOT/AGENTS.md"
elif [[ -f "$ROOT/AGENTS.md" ]]; then
  TARGET="$ROOT/AGENTS.md"
elif [[ -f "$ROOT/CLAUDE.md" ]]; then
  warn "R1: only CLAUDE.md — other agents read AGENTS.md" "git mv CLAUDE.md AGENTS.md"
  TARGET="$ROOT/CLAUDE.md"
else
  die 2 "no AGENTS.md or CLAUDE.md in $ROOT"
fi
NAME="${TARGET##*/}"
[[ -r "$TARGET" ]] || die 3 "$NAME is not readable"
TEXT=$(normalize "$TARGET") || die 3 "could not read $NAME"
STRIPPED=$(strip_comments <<<"$TEXT")
PROSE=$(blank_comments <<<"$TEXT" | blank_fences)

# --- R2: size ----------------------------------------------------------------
lines=$(count_lines <<<"$STRIPPED")
if (( lines > MAX_LINES )); then
  error "R2: $NAME is $lines lines (max $MAX_LINES)" \
    "Move derivable sections to HERO.md/DESIGN.md, procedures to skills, area rules to .claude/rules with paths:"
elif (( lines > WARN_LINES )); then
  warn "R2: $NAME is $lines lines (warn above $WARN_LINES, max $MAX_LINES)"
fi

# --- R3 + R6 over the rules --------------------------------------------------
# Checked here, not inside rules(): that runs in a process substitution, where
# a die would end the subshell and the loop would read "no rules".
if [[ -e "$ROOT/.claude/rules" && ! ( -r "$ROOT/.claude/rules" && -x "$ROOT/.claude/rules" ) ]]; then
  die 3 ".claude/rules exists but is not readable"
fi
while IFS= read -r -d '' rule; do
  [[ -f "$rule" ]] || continue
  rel="${rule#"$ROOT"/}"
  [[ -r "$rule" ]] || die 3 "$rel is not readable"
  rtext=$(normalize "$rule") || die 3 "could not read $rel"
  rl=$(strip_comments <<<"$rtext" | count_lines)
  if (( rl > RULE_MAX_UNSCOPED )) && ! scoped "$rule"; then
    error "R3: $rel is $rl lines with no paths: frontmatter — it loads in every session" \
      "Add frontmatter: paths: [\"src/**\"] (or split it)"
  fi
  grep_or_die -i "$BANNED" < <(blank_comments <<<"$rtext" | blank_fences)
  if [[ -n "$HITS" ]]; then
    error "R6: $rel uses a banned phrase:" "Name the specific thing instead"
    echo "$HITS" | sed 's/^/         /'
  fi
done < <(rules)

# --- R4: emphasis ------------------------------------------------------------
grep_or_die "$EMPHASIS" <<<"$PROSE"
emph=$( [[ -n "$HITS" ]] && count_lines <<<"$HITS" || echo 0 )
if (( emph > EMPHASIS_MAX )); then
  error "R4: $emph lines shout (IMPORTANT/NEVER/ALWAYS/MUST/CRITICAL); when many lines are emphasized, none is" \
    "Keep at most one; state the others plainly with the trap they prevent"
elif (( emph > EMPHASIS_WARN )); then
  warn "R4: $emph lines carry emphasis words — one is the budget"
fi

# --- R5: derivable sections -------------------------------------------------
# A section ends at the next heading of the same or a higher level; counting
# past that blames the sibling section's lines on the derivable one.
while IFS='|' read -r title body; do
  [[ -n "$title" ]] || continue
  error "R5: \"$title\" has $body lines of content the agent can derive from the tree or manifests" \
    "Keep a <=$SECTION_MAX-line pointer (HERO.md, DESIGN.md, docs/) and delete the rest"
done < <(awk -v max="$SECTION_MAX" -v re="$DERIVABLE" '
  function flush() { if (in_sec && body > max) printf "%s|%d\n", title, body; in_sec = 0 }
  /^#+ / {
    match($0, /^#+/); lvl = RLENGTH
    if (in_sec && lvl <= sec_lvl) flush()
    if (tolower($0) ~ re) { in_sec = 1; sec_lvl = lvl; title = $0; body = 0 }
    next
  }
  in_sec && NF > 0 { body++ }
  END { flush() }
' <<<"$PROSE")

# --- R6: banned phrases in the main file ------------------------------------
grep_or_die -i "$BANNED" <<<"$PROSE"
if [[ -n "$HITS" ]]; then
  error "R6: $NAME uses a banned phrase:" "Name the specific thing instead"
  echo "$HITS" | sed 's/^/         /'
fi

finish
