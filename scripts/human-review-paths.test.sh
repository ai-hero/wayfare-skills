#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for scripts/human-review-paths.sh. A fake `gh` on PATH stands in for
# GitHub, so every way the lookup can fail is exercised: each must exit 2
# (cannot tell), never 0, because 0 lets wayfare-ship-pr skip the review.
#
# Not -e: the suite observes non-zero exits.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SUT="$HERE/human-review-paths.sh"
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

# --match: the pure part.
m() { # LIST PATHS -> "rc|stdout"
  printf '%b' "$1" > "$WORK/l"
  printf '%b' "$2" > "$WORK/p"
  local out rc=0
  out=$(bash "$SUT" --match "$WORK/l" "$WORK/p" 2>/dev/null) || rc=$?
  echo "$rc|$out"
}
check "a listed path" "1|scripts/audit.py	scripts/audit.py" "$(m 'scripts/audit.py\n' 'README.md\nscripts/audit.py\n')"
check "* crosses /" "1|hooks/a/b.sh	hooks/*" "$(m 'hooks/*\n' 'hooks/a/b.sh\n')"
check "case does not dodge the list" "1|.MCP.json	.mcp.json" "$(m '.mcp.json\n' '.MCP.json\n')"
check "comments, indent, CRLF, no final newline" "1|Justfile	Justfile" "$(m '# c\n  Justfile  \r\n\nx/*' 'Justfile\n')"
check "nothing listed" "0|" "$(m 'hooks/*\n' 'README.md\n')"
check "a list with no entries fails closed" "2|" "$(m '# only a comment\n\n' 'README.md\n')"
check "a path's glob characters are literal" "0|" "$(m 'scripts/audit.py\n' 'scripts/*\n')"

# Parity with the workflow: every path auto-approve-logic.test.sh holds the
# workflow's fleet-workflow block to, through this script and the real list.
LIST="$HERE/../.github/auto-approve-human-review.txt"
table() { # true|false -> the PATH column of that fw_cases table
  awk -v want="fw_cases $1 <<'EOF'" '$0 == want { on = 1; next } on && $0 == "EOF" { exit } on' \
    "$HERE/auto-approve-logic.test.sh" | cut -d'|' -f1
}
for want in true false; do
  rows=$(table "$want")
  check "parity: the $want table is non-empty" "yes" "$([ -n "$rows" ] && echo yes || echo no)"
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    printf '%s\n' "$p" > "$WORK/one"
    rc=0
    bash "$SUT" --match "$LIST" "$WORK/one" > /dev/null 2>&1 || rc=$?
    [ "$want" = true ] && exp=1 || exp=0
    check "parity: $p" "$exp" "$rc"
  done <<<"$rows"
done

# Full mode, against a fake gh driven by env.
mkdir -p "$WORK/bin"
cat > "$WORK/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"contents/.github/auto-approve-human-review.txt?ref=refs/heads/main"*)
    [ "${FAKE_LIST_FAIL:-}" = 1 ] && { echo "HTTP 403" >&2; exit 1; }
    printf 'scripts/audit.py\n.github/workflows/*\n' ;;
  *"/files?per_page=100"*)
    [ "${FAKE_FILES_FAIL:-}" = 1 ] && { echo "HTTP 502" >&2; exit 1; }
    printf '%s\n' "${FAKE_FILES:-}" ;;
  *"/pulls/"*" --jq .changed_files"*) echo "${FAKE_COUNT:-1}" ;;
  "repo view"*) echo "ai-hero/wayfare-skills" ;;
  *) echo "unexpected gh $*" >&2; exit 9 ;;
esac
EOF
chmod +x "$WORK/bin/gh"
run() { # REPO [env...] -> "rc|stdout"
  local repo="$1"; shift
  local out rc=0
  out=$(env PATH="$WORK/bin:$PATH" "$@" bash "$SUT" 7 "$repo" 2>/dev/null) || rc=$?
  echo "$rc|$out"
}
W=ai-hero/wayfare-skills
check "another repo keeps no list that counts" "0|" "$(run ai-hero/auth FAKE_FILES='["scripts/audit.py",""]')"
check "listed in wayfare-skills" "1|scripts/audit.py	scripts/audit.py" "$(run $W FAKE_FILES='["scripts/audit.py",""]')"
check "a rename away from a listed path" "1|scripts/audit.py	scripts/audit.py" "$(run $W FAKE_FILES='["scripts/old.py","scripts/audit.py"]')"
check "nothing listed" "0|" "$(run $W FAKE_FILES='["README.md",""]')"
check "an unreadable list fails closed" "2|" "$(run $W FAKE_LIST_FAIL=1 FAKE_FILES='["README.md",""]')"
check "an unreadable file list fails closed" "2|" "$(run $W FAKE_FILES_FAIL=1)"
check "a truncated file list fails closed" "2|" "$(run $W FAKE_COUNT=3001 FAKE_FILES='["README.md",""]')"
rc=0
out=$(env PATH="$WORK/bin:$PATH" FAKE_FILES='["scripts/audit.py",""]' bash "$SUT" 7 2>/dev/null) || rc=$?
check "the repo defaults to the checkout's" "1|scripts/audit.py	scripts/audit.py" "$rc|$out"

echo "human-review-paths: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
