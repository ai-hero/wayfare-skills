#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for stop-checks.sh.
#
# A skip exits 0, and so does a check that passed, so "exit 0" alone proves
# nothing. Each fixture's check-fast recipe touches a marker file, and
# the rows assert on whether it ran as well as on the exit code.

set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/stop-checks.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Run from a pre-commit hook, git exports GIT_DIR and GIT_INDEX_FILE, and the
# fixtures' `git init --bare` then re-inits the REAL repo with core.bare=true
# and `git add -A` overwrites its index. Clear every repo-local variable first.
while read -r v; do unset "$v"; done < <(git rev-parse --local-env-vars)
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export TMPDIR="$TMP"
unset CLAUDE_PROJECT_DIR

PASS=0
FAIL=0

# fixture NAME RECIPE_BODY: a repo pushed to a bare remote, clean and in sync.
fixture() {
  local d="$TMP/$1"
  git init -q --bare "$d.remote.git"
  git init -q -b main "$d"
  printf 'check-fast:\n    @touch ran\n    %s\n' "$2" >"$d/Justfile"
  printf 'ran\n' >"$d/.gitignore"
  git -C "$d" add -A
  git -C "$d" commit -qm init
  git -C "$d" remote add origin "$d.remote.git"
  git -C "$d" push -q -u origin main 2>/dev/null
  echo "$d"
}

payload() { # [STOP_HOOK_ACTIVE] [SESSION]
  printf '{"session_id":"%s","hook_event_name":"Stop","stop_hook_active":%s}' \
    "${2:-s1}" "${1:-false}"
}

# run DIR PAYLOAD -> sets RC, OUT, ERR, RAN
run() {
  rm -f "$1/ran"
  OUT="$(printf '%s' "$2" | CLAUDE_PROJECT_DIR="$1" bash "$HOOK" 2>"$TMP/err")"
  RC=$?
  ERR="$(cat "$TMP/err")"
  if [ -e "$1/ran" ]; then RAN=yes; else RAN=no; fi
}

check() { # NAME EXPECTED ACTUAL
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $1 — expected [$2], got [$3]"
    echo "      stdout: ${OUT:-(none)}"
    echo "      stderr: ${ERR:-(none)}"
  fi
}

has() { if printf '%s' "$1" | grep -qF -- "$2"; then echo yes; else echo no; fi; }

# --- nothing to check --------------------------------------------------------
d=$(fixture clean 'exit 1')
run "$d" "$(payload)"
check "clean tree: rc" 0 "$RC"
check "clean tree: check not run" no "$RAN"

# --- a change runs the check -------------------------------------------------
d=$(fixture pass 'true')
echo x >"$d/new.txt"
run "$d" "$(payload)"
check "untracked file, passing: rc" 0 "$RC"
check "untracked file, passing: ran" yes "$RAN"
check "passing: one line" yes "$(has "$OUT" "check-fast passed")"

d=$(fixture failing 'echo "lib/x.go:3: undefined: foo" >&2; exit 1')
echo x >>"$d/Justfile.extra"
run "$d" "$(payload)"
check "failing: rc 2" 2 "$RC"
check "failing: output on stderr" yes "$(has "$ERR" "undefined: foo")"
check "failing: names the recipe" yes "$(has "$ERR" "just check-fast failed")"

# A commit made and never pushed leaves the tree clean, and the branch has no
# upstream at all.
d=$(fixture unpushed 'exit 1')
git -C "$d" checkout -qb feature
echo y >"$d/f.txt"
git -C "$d" add f.txt
git -C "$d" commit -qm feature
run "$d" "$(payload)"
check "unpushed commit, no upstream: rc" 2 "$RC"
check "unpushed commit, no upstream: ran" yes "$RAN"

# --- the loop guard ----------------------------------------------------------
d=$(fixture active 'exit 1')
echo x >"$d/new.txt"
run "$d" "$(payload true)"
check "stop_hook_active, still red: rc 0, never 2" 0 "$RC"
check "stop_hook_active, still red: ran" yes "$RAN"
check "stop_hook_active, still red: tells the person" yes "$(has "$OUT" "still failing")"
run "$d" '{"session_id":"s1", "stop_hook_active" : true}'
check "stop_hook_active spaced: rc 0" 0 "$RC"
check "stop_hook_active spaced: tells the person" yes "$(has "$OUT" "still failing")"
run "$d" '{"cwd":"/a/\"stop_hook_active\": true","stop_hook_active":false}'
check "stop_hook_active inside a string: still blocks" 2 "$RC"

d=$(fixture active_green 'true')
echo x >"$d/new.txt"
run "$d" "$(payload true)"
check "stop_hook_active, now green: rc" 0 "$RC"
check "stop_hook_active, now green: no message" no "$(has "$OUT" "systemMessage")"

run "$d" ''
check "empty payload: rc 1, not 2" 1 "$RC"
check "empty payload: not run" no "$RAN"

# --- in-progress git operations ---------------------------------------------
for marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
  d=$(fixture "op_$marker" 'exit 1')
  echo x >"$d/new.txt"
  case "$marker" in
    rebase-*) mkdir "$d/.git/$marker" ;;
    *) git -C "$d" rev-parse HEAD >"$d/.git/$marker" ;;
  esac
  run "$d" "$(payload)"
  check "$marker: rc" 0 "$RC"
  check "$marker: not run" no "$RAN"
done

d=$(fixture wt_main 'exit 1')
git -C "$d" worktree add -q -b wt "$TMP/wt" 2>/dev/null
echo x >"$TMP/wt/new.txt"
git -C "$TMP/wt" rev-parse HEAD >"$(git -C "$TMP/wt" rev-parse --git-path MERGE_HEAD)"
run "$TMP/wt" "$(payload)"
check "worktree merge: rc" 0 "$RC"
check "worktree merge: not run" no "$RAN"

# --- missing tooling warns once and never blocks ----------------------------
d=$(fixture norecipe 'true')
printf 'other:\n    true\n' >"$d/Justfile"
run "$d" "$(payload false nr)"
check "no recipe: rc" 0 "$RC"
check "no recipe: warns" yes "$(has "$OUT" "systemMessage")"
run "$d" "$(payload false nr)"
check "no recipe: warns once per session" "" "$OUT"
run "$d" '{"stop_hook_active":false}'
check "no session id: warns anyway" yes "$(has "$OUT" "systemMessage")"
run "$d" '{"stop_hook_active":false}'
check "no session id: no shared marker" yes "$(has "$OUT" "systemMessage")"

# A Justfile that no longer parses is the agent's mistake, not a missing recipe.
d=$(fixture brokenjf 'true')
printf 'check-fast:\n    @touch ran\nbroken recipe ((\n' >"$d/Justfile"
run "$d" "$(payload false bj)"
check "unparsable Justfile: rc 2" 2 "$RC"
check "unparsable Justfile: shows the parse error" yes "$(has "$ERR" "error")"

d=$(fixture nojustfile 'true')
rm "$d/Justfile"
run "$d" "$(payload false njf)"
check "no Justfile: rc" 0 "$RC"
check "no Justfile: warns" yes "$(has "$OUT" "no Justfile")"

# just finds justfile and .justfile in any case; each must reach check-fast,
# not the "no Justfile" skip. Fixtures are numbered, not named after the file:
# on a case-insensitive filesystem jfnamejustfile and jfnameJUSTFILE collide.
i=0
for name in justfile .justfile JUSTFILE; do
  i=$((i + 1))
  d=$(fixture "jfname$i" 'exit 1')
  git -C "$d" mv Justfile "$name.tmp" && git -C "$d" mv "$name.tmp" "$name"
  run "$d" "$(payload false "jf$name")"
  check "$name: rc 2" 2 "$RC"
  check "$name: ran" yes "$RAN"
done

# A Justfile above the repo root is still the one just runs.
mkdir -p "$TMP/parentjf"
printf 'check-fast:\n    @touch ran\n    exit 1\n' >"$TMP/parentjf/Justfile"
d=$(fixture parentjf/child 'true')
rm "$d/Justfile"
run "$d" "$(payload false pjf)"
check "parent Justfile: rc 2" 2 "$RC"

d=$(fixture nojust 'exit 1')
echo x >"$d/new.txt"
NOJUST="$TMP/nojust-bin"
mkdir -p "$NOJUST"
for t in git sed grep tr wc tail cat; do ln -s "$(command -v "$t")" "$NOJUST/$t"; done
rm -f "$d/ran"
OUT="$(payload false nj | CLAUDE_PROJECT_DIR="$d" PATH="$NOJUST" "$(command -v bash)" "$HOOK" 2>/dev/null)"
RC=$?
check "no just: rc" 0 "$RC"
check "no just: warns" yes "$(has "$OUT" "just is not installed")"

# --- output trimming ---------------------------------------------------------
d=$(fixture long 'seq 1 500; printf "\033[31mred-error\033[0m\n"; exit 1')
echo x >"$d/new.txt"
run "$d" "$(payload)"
check "long: rc" 2 "$RC"
check "long: says it trimmed" yes "$(has "$ERR" "Last 60 of")"
check "long: keeps the end" yes "$(has "$ERR" "red-error")"
check "long: drops the start" no "$(printf '%s\n' "$ERR" | grep -qx 1 && echo yes || echo no)"
check "long: ANSI stripped" no "$(has "$ERR" $'\033[')"

d=$(fixture exact 'seq 1 58; exit 1')
echo x >"$d/new.txt"
run "$d" "$(payload)"
check "exactly 60 lines: no trim header" no "$(has "$ERR" "Last 60 of")"

# --- which tree is checked ---------------------------------------------------
d=$(fixture cwd 'exit 1')
echo x >"$d/new.txt"
rm -f "$d/ran"
printf '{"cwd":"%s","stop_hook_active":false}' "$d" | (cd / && bash "$HOOK") >/dev/null 2>&1
RC=$?
check "payload cwd, no project dir: rc" 2 "$RC"
check "payload cwd, no project dir: ran" yes "$([ -e "$d/ran" ] && echo yes || echo no)"

# A worktree session has the worktree as cwd and the main checkout as
# CLAUDE_PROJECT_DIR; the change is in the worktree.
main=$(fixture cwd_main 'exit 1')
git -C "$main" worktree add -q -b cwdwt "$TMP/cwdwt" 2>/dev/null
echo x >"$TMP/cwdwt/new.txt"
rm -f "$TMP/cwdwt/ran" "$main/ran"
printf '{"cwd":"%s","stop_hook_active":false}' "$TMP/cwdwt" |
  CLAUDE_PROJECT_DIR="$main" bash "$HOOK" >/dev/null 2>&1
RC=$?
check "worktree cwd over project dir: rc" 2 "$RC"
check "worktree cwd over project dir: ran in the worktree" yes "$([ -e "$TMP/cwdwt/ran" ] && echo yes || echo no)"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "stop-checks: $PASS passed"
  exit 0
fi
echo "stop-checks: $PASS passed, $FAIL FAILED"
exit 1
