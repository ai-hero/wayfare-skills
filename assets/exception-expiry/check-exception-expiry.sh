#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

set -euo pipefail

# Usage: check-exception-expiry.sh [TRIVYIGNORE_YAML [VEX_DIR]]
#
# Docker Scout ignores OpenVEX `expired_at`: a statement dated in the past
# still suppresses its CVE. This script is the only thing that makes the date
# mean anything, so every workflow that applies the exceptions runs it first.
#
# An empty or omitted first argument means the repo keeps no
# .trivyignore.yaml. A NAMED file must exist, because a missing one is how a
# job without a checkout presents.
FILE="${1:-}"
# The VEX check must stay inert when the directory is absent: `.vex/` exists
# only while a Scout exception is in force. The argument lets a fixture point
# at a tree of its own.
VEX_DIR="${2:-.vex}"

if [ -n "$FILE" ]; then
  # Absent file gets its own branch: otherwise yq fails on the missing path
  # and the annotation reads "failed to parse as YAML", which names the wrong
  # cause.
  if [ ! -f "$FILE" ]; then
    echo "::error::$FILE not found — the workspace is not checked out, so neither scanner can read its exceptions"
    exit 1
  fi

  # The Python `yq` (kislyuk/yq, a jq wrapper) installs under the same name
  # and rejects mikefarah's expression syntax, so presence alone is not
  # enough. A missing or wrong parser must be red: "no output" from it would
  # otherwise read as "no exceptions in force".
  if ! yq --version 2>/dev/null | grep -qE 'mikefarah/yq.* v[4-9]\.'; then
    echo "::error::yq v4+ (mikefarah/yq) is required to parse $FILE — install it (brew install yq, or the mikefarah/yq release binary); ubuntu-latest ships it"
    exit 1
  fi
fi

# 90 days: long enough to plan a real fix around a normal release cycle,
# short enough that nobody can silence a CVE "permanently by arithmetic" by
# picking one big date once and forgetting it. Raising this
# number buys runway on one exception at the cost of raising how long every
# future exception can suppress a finding unwatched — it is a ceiling on that
# exposure, not a grace period to be generous with.
MAX_HORIZON_DAYS=90
TODAY=$(date -u +%Y-%m-%d)
# GNU date (`-d`, on the ubuntu-latest runner) and BSD date (`-v`, on a
# contributor's Mac running this script directly) compute a relative date with
# different flags; `-d` on BSD date silently means something else entirely
# rather than erroring, so this probes for GNU support instead of guessing
# from `uname`.
if date -u -d "+${MAX_HORIZON_DAYS} days" +%Y-%m-%d >/dev/null 2>&1; then
  CAP=$(date -u -d "+${MAX_HORIZON_DAYS} days" +%Y-%m-%d)
else
  CAP=$(date -u -v+"${MAX_HORIZON_DAYS}"d +%Y-%m-%d)
fi

# The Trivy half and the VEX half both suppress findings on a dated statement,
# so one comparison serves both: a second copy of either is how the halves
# drift apart (a VEX statement dated in the past or past the cap suppressing
# with exit 0).

exceeds_cap() {
  [ "$1" \> "$CAP" ]
}

# NOT `$TODAY > $review`. Trivy stops honouring an entry at midnight UTC on
# its expired_at, so a strictly-greater test first fires the day AFTER the
# suppression already lapsed — the scanners go red that morning with no
# annotation saying an exception expired, which is the bare "mystery CVE"
# this step exists to prevent.
review_is_due() {
  [ ! "$TODAY" \< "$1" ]
}

# Sort before head: the EARLIEST date is the one that expires first, and
# input order is not date order. Taking the first date seen instead lets a
# newly prepended (or newly written) entry with a later date hold the gate
# open while every older exception expires unnoticed. Shared so neither half
# can pick "first" instead of "earliest" by accident.
earliest_date() {
  sort | head -1
}

# exceeds_cap/review_is_due compare dates as plain strings, so an unpadded
# value like "2026-1-5" sorts by byte ('-' < every digit) rather than by
# calendar date — "2026-1-5" reads as EARLIER than "2026-09-18" even though
# January is later in the year than September, silently defeating both the
# cap check and the review-due check. Every date pulled from either half
# goes through this before comparison instead of straight into exceeds_cap
# or review_is_due.
validate_date() {
  local label="$1" date="$2"
  if ! [[ "$date" =~ ^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$ ]]; then
    echo "::error::$label has a malformed expired_at ($date) — must be zero-padded YYYY-MM-DD, or the cap/review comparisons below silently mis-order it"
    exit 1
  fi
}

# Checked before the Trivy half, which exits 0 on an empty .trivyignore.yaml:
# a VEX statement can suppress a finding with no Trivy entry present at all.
if [ -d "$VEX_DIR" ]; then
  MISSING_VEX_EXPIRY=""
  VEX_OVER_CAP=""
  VEX_DATES=""
  while IFS= read -r -d '' vexfile; do
    # `.statements[]?` swallows "cannot iterate" when `.statements` is present
    # but not an array (e.g. a bare string) — valid JSON, so it passes the
    # parse check below, then both queries below emit nothing, reading exactly
    # like a legitimately empty statement list instead of the malformed file
    # it is.
    if ! shape=$(jq -r '(.statements // []) | if type == "array" then "ok" else "bad" end' "$vexfile" 2>&1); then
      echo "::error::failed to parse $vexfile as VEX JSON — cannot verify its exceptions are unexpired: $shape"
      exit 1
    fi
    if [ "$shape" != "ok" ]; then
      echo "::error::$vexfile's statements field is not an array — cannot verify its exceptions are unexpired"
      exit 1
    fi

    # `2>&1` on failure, not `2>/dev/null || true`: a malformed or unreadable
    # VEX file must not be indistinguishable from "this file has no
    # statements" — that is the exact fail-open the missing-file branch above
    # exists to prevent for .trivyignore.yaml, and jq erroring here is the same
    # class of gap for the VEX half.
    if ! ids=$(jq -r '.statements[]? | select(has("expired_at") | not) | (.vulnerability.name? // .vulnerability // "unknown")' "$vexfile" 2>&1); then
      echo "::error::failed to parse $vexfile as VEX JSON — cannot verify its exceptions are unexpired: $ids"
      exit 1
    fi
    if [ -n "$ids" ]; then
      MISSING_VEX_EXPIRY="$MISSING_VEX_EXPIRY $(basename "$vexfile"):$(echo "$ids" | tr '\n' ',')"
    fi

    if ! vex_stmts=$(jq -r '.statements[]? | select(has("expired_at")) | "\(.vulnerability.name? // .vulnerability // "unknown")\t\(.expired_at)"' "$vexfile" 2>&1); then
      echo "::error::failed to parse $vexfile as VEX JSON — cannot verify its exceptions are unexpired: $vex_stmts"
      exit 1
    fi
    while IFS=$'\t' read -r vid vdate; do
      [ -z "$vid" ] && continue
      validate_date "$vid" "$vdate"
      VEX_DATES="$VEX_DATES
$vdate"
      if exceeds_cap "$vdate"; then
        VEX_OVER_CAP="$VEX_OVER_CAP $vid($vdate)"
      fi
    done <<<"$vex_stmts"
  done < <(find "$VEX_DIR" -type f -name '*.json' -print0)

  if [ -n "$MISSING_VEX_EXPIRY" ]; then
    echo "::error::VEX statement(s) in $VEX_DIR without expired_at — a VEX half must carry the same expiry its Trivy entry does:$MISSING_VEX_EXPIRY"
    exit 1
  fi

  if [ -n "$VEX_OVER_CAP" ]; then
    echo "::error::VEX statement(s) in $VEX_DIR dated beyond the ${MAX_HORIZON_DAYS}-day cap ($CAP) — re-date within the cap or delete: $VEX_OVER_CAP"
    exit 1
  fi

  VEX_REVIEW=$(printf '%s\n' "$VEX_DATES" | grep -v '^$' | earliest_date || true)
  if [ -n "$VEX_REVIEW" ] && review_is_due "$VEX_REVIEW"; then
    echo "::error::VEX statement(s) in $VEX_DIR reached their review date $VEX_REVIEW. Re-read the advisories: if the base image has been rebuilt on a fixed package, rebuild and DELETE the statements rather than extending the date."
    exit 1
  fi
  if [ -n "$VEX_REVIEW" ]; then
    echo "VEX review date: $VEX_REVIEW (today $TODAY)"
  fi
fi

if [ -z "$FILE" ]; then
  exit 0
fi

# Parsed, never matched line by line: Trivy applies any list entry in these
# sections whatever its key order or style, so a `- id:` line match misses
# `- statement: …` followed by `id:`, and `- {id: …}`, and silences a CVE
# with no expiry in every scan. mikefarah/yq keeps a duplicated key instead
# of rejecting it, so "exactly one expired_at" is a key count, not a lookup.
ENTRIES=""
for section in vulnerabilities misconfigurations secrets licenses; do
  if ! kind=$(SECTION=$section yq '.[strenv(SECTION)] | tag' "$FILE" 2>&1); then
    echo "::error::failed to parse $FILE as YAML — cannot verify its exceptions are unexpired: $kind"
    exit 1
  fi
  case "$kind" in
    '!!null') continue ;;
    '!!seq') ;;
    *)
      echo "::error::$FILE's $section is not a list ($kind) — cannot verify its exceptions are unexpired"
      exit 1
      ;;
  esac
  # `|`, not a tab: tab is IFS whitespace, so `read` collapses an empty
  # leading field and an undated entry's id would land in the date slot.
  # select + `//`, not if/then/else: ubuntu-latest's yq (4.53) has no
  # conditional and fails the parse, which reads as a broken exceptions file.
  if ! rows=$(SECTION=$section yq '
      .[strenv(SECTION)][]
      | (
          select(tag == "!!map")
          | ([keys[] | select(. == "expired_at")] | length | tostring)
            + "|" + (.expired_at // "" | tostring)
            + "|" + (.id // "" | tostring)
        ) // "0||"
    ' "$FILE" 2>&1); then
    echo "::error::failed to parse $FILE as YAML — cannot verify its exceptions are unexpired: $rows"
    exit 1
  fi
  ENTRIES="$ENTRIES
$rows"
done

if [ -z "$(printf '%s' "$ENTRIES" | tr -d '\n')" ]; then
  echo "no CVE exceptions in force"
  exit 0
fi

NO_ID=0
UNDATED=""
ID_DATES=""
while IFS='|' read -r n date id; do
  [ -z "$n" ] && continue
  if [ -z "$id" ]; then
    NO_ID=$((NO_ID + 1))
  elif [ "$n" != 1 ] || [ -z "$date" ]; then
    UNDATED="$UNDATED$id "
  else
    ID_DATES="$ID_DATES
$id $date"
  fi
done <<<"$ENTRIES"
if [ "$NO_ID" -gt 0 ]; then
  echo "::error::$NO_ID exception(s) in $FILE without an id — every entry must name the finding it suppresses"
  exit 1
fi
if [ -n "$UNDATED" ]; then
  echo "::error::every exception in $FILE must carry exactly one expired_at — these do not: $UNDATED"
  exit 1
fi

OVER_CAP=""
while IFS=' ' read -r id date; do
  [ -z "$id" ] && continue
  validate_date "$id" "$date"
  if exceeds_cap "$date"; then
    OVER_CAP="$OVER_CAP $id($date) "
  fi
done <<<"$ID_DATES"
if [ -n "$OVER_CAP" ]; then
  echo "::error::exception(s) dated beyond the ${MAX_HORIZON_DAYS}-day cap ($CAP) — re-date within the cap or delete: $OVER_CAP"
  exit 1
fi

REVIEW=$(printf '%s\n' "$ID_DATES" | awk 'NF { print $2 }' | earliest_date)
echo "exception review date: $REVIEW (today $TODAY)"
if review_is_due "$REVIEW"; then
  echo "::error::CVE exceptions reached their review date $REVIEW. Re-read the advisories: if the base image has been rebuilt on a fixed package, rebuild and DELETE the entries rather than extending the date."
  exit 1
fi
