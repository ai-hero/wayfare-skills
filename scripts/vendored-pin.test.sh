#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for the `touched` step in .github/workflows/vendored-pin.yaml, which
# decides whether a PR gets the upstream compare. The block sits between
# `# test: begin touched` / `# test: end touched` and runs here against real
# merge commits, the shape a pull_request checkout has.
#
# Not -e: the suite observes non-zero exits.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WF="$HERE/../.github/workflows/vendored-pin.yaml"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

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

awk '
  $0 ~ "# test: begin touched$" { on = 1; next }
  $0 ~ "# test: end touched$"   { on = 0 }
  on { sub(/^          /, ""); print }
' "$WF" > "$WORK/touched.sh"
check "extraction is non-empty" "yes" "$([ -s "$WORK/touched.sh" ] && echo yes || echo no)"
check "extraction parses" "0" "$(bash -n "$WORK/touched.sh" 2>/dev/null; echo $?)"

g() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

# A repo whose HEAD is a merge of a PR branch that adds FILES onto main.
merge_repo() { # DIR FILE...
  local d="$1"; shift
  g init -q "$d"
  (
    cd "$d" || exit 1
    echo base > README.md && g add . && g commit -qm base
    g checkout -qb pr
    for f in "$@"; do mkdir -p "$(dirname "$f")" && echo x > "$f"; done
    g add . && g commit -qm pr
    g checkout -q main
    echo other > OTHER.md && g add . && g commit -qm other
    g merge -q --no-ff -m merge pr
  )
}

run() { # DIR -> "rc|output-file-contents"
  local out="$WORK/out.$$"
  : > "$out"
  local rc=0
  (cd "$1" && GITHUB_OUTPUT="$out" bash "$WORK/touched.sh" > /dev/null 2>&1) || rc=$?
  echo "$rc|$(cat "$out")"
}

merge_repo "$WORK/touch" assets/security-audit/SKILL.md
check "touching the tree asks for the compare" "0|yes=true" "$(run "$WORK/touch")"

merge_repo "$WORK/other" scripts/foo.sh
check "a PR elsewhere skips the compare" "0|" "$(run "$WORK/other")"

merge_repo "$WORK/sibling" assets/security-audit-notes/x.md
check "a sibling folder is not the tree" "0|" "$(run "$WORK/sibling")"

# More than a pipe buffer of paths, the tree sorting first: `diff | grep -q`
# read this as "no change" under pipefail.
many=(assets/security-audit/a.md)
for i in $(seq 1 2500); do many+=("z/long-directory-name-to-fill-the-pipe-buffer/file-$i.txt"); done
merge_repo "$WORK/big" "${many[@]}"
check "a diff larger than a pipe buffer still asks" "0|yes=true" "$(run "$WORK/big")"

g init -q "$WORK/flat"
(cd "$WORK/flat" && echo a > a && g add . && g commit -qm a && mkdir -p assets/security-audit && echo b > assets/security-audit/b && g add . && g commit -qm b)
check "a checkout that is not a merge commit fails" "1|" "$(run "$WORK/flat")"

echo "vendored-pin: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
