#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for assets/exception-expiry/check-exception-expiry.sh.
#
# Not -e: the suite has to OBSERVE the script's non-zero exits.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../assets/exception-expiry/check-exception-expiry.sh"

PASS=0
FAIL=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Relative dates, never constants: the cap is 90 days from today, so a fixed
# "future" date drifts over the cap and every passing case turns red.
days_from_now() {
  if date -u -d "+$1 days" +%Y-%m-%d >/dev/null 2>&1; then
    date -u -d "$1 days" +%Y-%m-%d
  else
    date -u -v"$( [ "$1" -ge 0 ] && echo +)$1"d +%Y-%m-%d
  fi
}
FUTURE=$(days_from_now 30)
TODAY=$(date -u +%Y-%m-%d)
PAST=2000-01-01
OVER_CAP=$(days_from_now 120)

# vex <dir> <id:date|id:> ... — one statement per argument; an empty date
# omits expired_at from that statement.
vex() {
  local dir="$1"
  shift
  mkdir -p "$dir"
  local stmts="" sep="" id date
  for s in "$@"; do
    id="${s%%:*}"
    date="${s#*:}"
    if [ -n "$date" ]; then
      stmts="$stmts$sep{\"vulnerability\":{\"name\":\"$id\"},\"status\":\"not_affected\",\"expired_at\":\"$date\"}"
    else
      stmts="$stmts$sep{\"vulnerability\":{\"name\":\"$id\"},\"status\":\"not_affected\"}"
    fi
    sep=","
  done
  printf '{"@context":"https://openvex.dev/ns/v0.2.0","statements":[%s]}\n' "$stmts" >"$dir/fixture.openvex.json"
}

# expect <name> <exit> <stdout-regex> -- <args...>  (run from a fresh cwd)
expect() {
  local name="$1" want="$2" pattern="$3"
  shift 4
  local out code
  out=$(cd "$CASE" && "$SCRIPT" "$@" 2>&1)
  code=$?
  if [ "$code" = "$want" ] && [[ "$out" =~ $pattern ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $name"
    echo "  expected exit $want matching /$pattern/"
    echo "  got exit $code: $out"
  fi
}

new_case() {
  CASE="$WORK/$1"
  mkdir -p "$CASE"
}

# --- VEX only (no .trivyignore.yaml) ----------------------------------------

new_case no-exceptions
expect "no .vex and no trivy file passes" 0 '^$' --

new_case vex-future
vex "$CASE/.vex" "CVE-1:$FUTURE"
expect "an in-cap future date passes" 0 "VEX review date: $FUTURE" --

new_case vex-past
vex "$CASE/.vex" "CVE-1:$PAST"
expect "a past date fails — Scout would still honour it" 1 'reached their review date 2000-01-01' --

new_case vex-today
vex "$CASE/.vex" "CVE-1:$TODAY"
expect "the review date itself fails, not the day after" 1 'reached their review date' --

new_case vex-missing
vex "$CASE/.vex" "CVE-1:$FUTURE" "CVE-2:"
expect "a statement without expired_at fails and is named" 1 'without expired_at.*CVE-2' --

new_case vex-over-cap
vex "$CASE/.vex" "CVE-1:$OVER_CAP"
expect "a date beyond 90 days fails" 1 'beyond the 90-day cap' --

new_case vex-earliest
vex "$CASE/.vex" "CVE-1:$FUTURE" "CVE-2:$PAST"
expect "the earliest date gates, not the first in the file" 1 'reached their review date 2000-01-01' --

new_case vex-unpadded
vex "$CASE/.vex" "CVE-1:2026-1-5"
expect "an unpadded date fails rather than mis-sorting" 1 'malformed expired_at' --

new_case vex-not-json
mkdir -p "$CASE/.vex"
echo '{not json' >"$CASE/.vex/broken.json"
expect "unparsable VEX fails, never reads as no statements" 1 'failed to parse' --

new_case vex-statements-string
mkdir -p "$CASE/.vex"
echo '{"statements":"CVE-1"}' >"$CASE/.vex/odd.json"
expect "a non-array statements field fails" 1 'not an array' --

new_case vex-dir-arg
vex "$CASE/elsewhere" "CVE-1:$PAST"
expect "the VEX dir argument is honoured" 1 'reached their review date' -- "" elsewhere

# --- the Trivy half ---------------------------------------------------------

new_case trivy-named-missing
expect "a named trivy file that is absent fails (missing checkout)" 1 'not found' -- .trivyignore.yaml

if yq --version 2>/dev/null | grep -qE 'mikefarah/yq.* v[4-9]\.'; then
  new_case trivy-future
  printf 'vulnerabilities:\n  - id: CVE-9\n    expired_at: %s\n' "$FUTURE" >"$CASE/.trivyignore.yaml"
  expect "an in-cap trivy entry passes" 0 "exception review date: $FUTURE" -- .trivyignore.yaml

  new_case trivy-past
  printf 'vulnerabilities:\n  - id: CVE-9\n    expired_at: %s\n' "$PAST" >"$CASE/.trivyignore.yaml"
  expect "a lapsed trivy entry fails" 1 'reached their review date' -- .trivyignore.yaml

  new_case trivy-undated
  printf 'vulnerabilities:\n  - id: CVE-9\n' >"$CASE/.trivyignore.yaml"
  expect "an undated trivy entry fails" 1 'must carry exactly one expired_at' -- .trivyignore.yaml

  new_case both-halves
  printf 'vulnerabilities: []\n' >"$CASE/.trivyignore.yaml"
  vex "$CASE/.vex" "CVE-1:$PAST"
  expect "a lapsed VEX fails even beside an empty trivy file" 1 'reached their review date' -- .trivyignore.yaml
elif [ -n "${CI:-}" ]; then
  # Under CI a missing yq must not skip: the suite would pass having
  # exercised none of the Trivy half.
  echo "FAIL: mikefarah yq v4 is not on PATH under CI"
  FAIL=$((FAIL + 1))
else
  echo "skip: mikefarah yq v4 not on PATH — Trivy-half cases not run (brew install yq)"
fi

echo "check-exception-expiry: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
