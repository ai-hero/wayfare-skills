#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/fleet-scan.sh.
#
# Each case is a drift that would otherwise go unreported: a port read from
# the wrong spelling of the compose file, a collision hidden behind a
# `HOST_PORT` grep, a row that points at a folder that is no longer a repo.
#
# Usage: bash scripts/fleet-scan.test.sh

set -uo pipefail

SCAN="$(cd "$(dirname "$0")" && pwd)/fleet-scan.sh"

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
F="$(cd "$TMP" && pwd -P)/fleet"

mkrepo() { # name [compose-file [content]]
  mkdir -p "$F/$1/.git" "$F/$1/.plans/inbox"
  [ -n "${2:-}" ] && printf '%s\n' "$3" > "$F/$1/$2"
  return 0
}

mkrepo auth  docker-compose.dev.yaml 'ports:
      - ${HOST_PORT:-33000}:3000'
touch "$F/auth/HERO.md"; printf '# A\n\n## Fleet\n\ntext\n' > "$F/auth/AGENTS.md"
mkrepo web   docker-compose.dev.yml  'ports:
      - "3000:3000"'
touch "$F/web/HERO.md"; printf '# W\n' > "$F/web/CLAUDE.md"
mkrepo clash docker-compose.dev.yaml 'ports:
      - ${HOST_PORT:-33000}:3000'
touch "$F/clash/AGENTS.md"
mkrepo extra
mkrepo notes
mkdir -p "$F/plain-folder"
mkrepo lone
mkrepo odd   docker-compose.dev.yaml 'ports:
      - "${HOST_PORT}:3000"'
# lone/odd twins carrying a real group: the port claim is only audited for a
# fleet member, so these are what keep PORT_UNIMPLEMENTED and PORT_UNPARSED
# covered while lone/odd prove a `none` row is left alone.
mkrepo lonefleet
touch "$F/lonefleet/HERO.md"; printf '# L\n\n## Fleet\n' > "$F/lonefleet/AGENTS.md"
mkrepo oddfleet docker-compose.dev.yaml 'ports:
      - "${HOST_PORT}:3000"'
touch "$F/oddfleet/HERO.md"; printf '# O\n\n## Fleet\n' > "$F/oddfleet/AGENTS.md"
mkdir -p "$F/sites"; mkrepo sites/web docker-compose.dev.yml 'ports:
      - "3000:3000"'
touch "$F/sites/web/HERO.md"; printf '# W\n\n## Fleet\n' > "$F/sites/web/AGENTS.md"
mkrepo multi docker-compose.dev.yaml 'services:
  db:
    ports:
      - "5432:5432"
  app:
    ports:
      # - "${HOST_PORT:-6666}:3000"
      - "127.0.0.1:33020:3000"'
touch "$F/multi/HERO.md"; printf '## Fleet\n' > "$F/multi/AGENTS.md"

# ---------- --list ---------------------------------------------------------

LIST=$("$SCAN" "$F" --list)
check "list: exit 0 without FLEET.md" "0" "$?"
check "list: HOST_PORT default read from .yaml" \
  "auth	$F/auth	33000" "$(printf '%s\n' "$LIST" | grep '^auth')"
check "list: literal mapping read from .yml" \
  "web	$F/web	3000" "$(printf '%s\n' "$LIST" | grep '^web')"
check "list: no compose file reports -" \
  "extra	$F/extra	-" "$(printf '%s\n' "$LIST" | grep '^extra')"
# awk with a real field separator, not grep '^odd\t': GNU grep does not read
# \t as a tab in a basic regex, so that matched nothing on Linux while passing
# on macOS. An exact field compare also keeps `oddfleet` out of this row.
check "list: compose file without a readable host port reports ?" \
  "odd	$F/odd	?" "$(printf '%s\n' "$LIST" | awk -F'\t' '$1=="odd"')"
check "list: without a port-range the first literal wins, comments skipped, bind prefix stripped" \
  "multi	$F/multi	5432" "$(printf '%s\n' "$LIST" | grep '^multi')"
check "list: a plain folder is not a checkout" \
  "" "$(printf '%s\n' "$LIST" | grep 'plain-folder')"

# ---------- --review -------------------------------------------------------

"$SCAN" "$F" --review >/dev/null 2>&1
check "review: no FLEET.md exits 2" "2" "$?"

cat > "$F/FLEET.md" <<'EOM'
# Fleet

## Fleet

- name: test
- port-range: 33000-33099

## Repos

### auth

- group: apps
- port: 33000

### web

- group: apps
- port: 33001

### clash

- group: apps
- port: 33000

### notes

- group: none

### gone

- group: apps
- port: 33002

### folder

- path: ./plain-folder
- group: apps

### lone

- group: none
- port: 33002

### odd

- group: none
- port: 33003

### lonefleet

- group: apps
- port: 33030

### oddfleet

- group: apps
- port: 33031

### web2

- path: ./sites/web/
- group: apps
- port: 33001

### multi

- group: apps
- port: 33020

### evil

- path: --upload-pack=x
- group: apps

### ../escape

- group: apps
EOM

OUT=$("$SCAN" "$F" --review); RC=$?
check "review: findings exit 1" "1" "$RC"
check "review: every finding, sorted" \
"$(printf 'BAD_ROW\t../escape\ta repo name is [A-Za-z0-9._-] only, not %s../escape%s\nBAD_ROW\tevil\ta value starts with %s-%s or holds a control character\nMISSING\tgone\t%s/gone\nNOT_GIT\tfolder\t%s/plain-folder\nNO_HERO\tclash\t%s/clash\nNOT_FLEET_AWARE\tclash\t%s/clash\nNOT_FLEET_AWARE\tweb\t%s/web\nPORT_COLLISION\tclash\t33000, also auth\nPORT_COLLISION\tweb2\t3000, also web\nPORT_COLLISION\tweb2\t33001, also web\nPORT_MISMATCH\tweb\t33001 -> 3000\nPORT_MISMATCH\tweb2\t33001 -> 3000\nPORT_UNIMPLEMENTED\tlonefleet\t33030 (no compose file)\nPORT_UNPARSED\toddfleet\t33031 (compose file, no readable host port)' "'" "'" "'" "'" "$F" "$F" "$F" "$F" "$F" | sort)" \
"$OUT"

# A `none` row is exempt from NO_HERO/NO_AGENTS: it lives here, it is not fleet.
check "review: group none is not asked for HERO.md" \
  "" "$(printf '%s\n' "$OUT" | grep 'notes')"
check "review: port-range picks the app port over the database's, and a trailing-slash non-child path is matched" \
  "" "$(printf '%s\n' "$OUT" | grep -E '^PORT_MISMATCH	multi')"

# FLEET.md defines the fleet. A checkout that no row names is not a member and
# is not a finding — `extra` is on disk throughout this fixture.
check "review: a checkout with no row is not reported" \
  "" "$(printf '%s\n' "$OUT" | grep -E 'extra')"

# A repo that committed its own FLEET.md is not a fleet.
touch "$F/HERO.md"
"$SCAN" "$F" --review >/dev/null 2>&1
check "review: HERO.md beside FLEET.md exits 2" "2" "$?"
rm "$F/HERO.md"

# A FLEET.md inside a git work tree is a clone's content, and the message must
# say that rather than blame a HERO.md that is not there.
WT="$TMP/wtfleet"; mkdir -p "$WT/.git"; printf '## Repos\n' > "$WT/FLEET.md"
WTERR=$("$SCAN" "$WT" --review 2>&1 >/dev/null); WTRC=$?
check "review: a FLEET.md inside a git work tree exits 2" "2" "$WTRC"
check "review: the work-tree refusal names the work tree, not HERO.md" \
  "1 0" "$(printf '%s\n' "$WTERR" | grep -c 'inside a git work tree') $(printf '%s\n' "$WTERR" | grep -c 'HERO.md')"
rm -rf "$WT"

# The first sync: a FLEET.md with no rows yet claims nothing, so review has
# nothing to say about the checkouts. `--list` is what shows them, and it still
# sees every one. Before, this reported the whole folder as findings, which
# made an empty map look like a fleet-wide problem instead of an empty map.
printf '# Fleet\n\n## Fleet\n\n- name: t\n' > "$F/FLEET.md"
OUT=$("$SCAN" "$F" --review)
check "review: zero rows reports no checkout as a finding" \
  "0" "$(printf '%s\n' "$OUT" | grep -c 'extra')"
check "review: --list still sees every checkout when no row exists" \
  "1" "$("$SCAN" "$F" --list | grep -c '^extra')"

# Clean fleet: only the true rows, every fleet repo carries the section, and
# no `none` repo publishes a port a row claims (the host does not care about
# groups).
printf '# W\n\n## Fleet\n' > "$F/web/CLAUDE.md"
rm "$F/clash/docker-compose.dev.yaml"
cat > "$F/FLEET.md" <<'EOM'
## Repos

### auth

- group: apps
- port: 33000

### web

- group: apps
- port: 3000

### clash

- group: none

### extra

- group: none

### notes

- group: none

### lone

- group: none

### odd

- group: none

### multi

- group: none
EOM
OUT=$("$SCAN" "$F" --review); RC=$?
check "review: clean fleet exits 0 with no output" "0|" "$RC|$OUT"

# ---------- --review: inbox and exclude ------------------------------------

# Real checkouts: `git check-ignore` needs one. A `.plans/` in the user's
# global excludes would hide PLANS_NOT_EXCLUDED here, so read no user config.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null XDG_CONFIG_HOME="$TMP/xdg"
G="$(cd "$TMP" && pwd -P)/inboxfleet"
mkgit() { # name group-is-fleet(0|1) [plans: inbox|bare|none] [excluded: 0|1]
  git init -q "$G/$1" 2>/dev/null
  [ "$2" = 1 ] && { touch "$G/$1/HERO.md"; printf '## Fleet\n' > "$G/$1/AGENTS.md"; }
  case "$3" in
    inbox) mkdir -p "$G/$1/.plans/inbox" ;;
    bare) mkdir -p "$G/$1/.plans" ;;
  esac
  [ "$4" = 1 ] && printf '.plans/\n' >> "$G/$1/.git/info/exclude"
  return 0
}
mkgit ready      1 inbox 1
mkgit noinbox    1 bare  1
mkgit noplans    1 none  1
mkgit leaky      1 inbox 0
mkgit parked     0 bare  1
mkgit parkedleak 0 bare  0
mkdir -p "$G/fakegit/.git" "$G/fakegit/.plans"
touch "$G/fakegit/HERO.md"; printf '## Fleet\n' > "$G/fakegit/AGENTS.md"
cat > "$G/FLEET.md" <<'EOM'
## Repos

### ready

- group: apps

### noinbox

- group: apps

### noplans

- group: apps

### leaky

- group: apps

### parked

- group: none

### parkedleak

- group: none

### fakegit

- group: apps

### gone

- group: apps
EOM
OUT=$("$SCAN" "$G" --review); RC=$?
check "review: inbox findings exit 1" "1" "$RC"
check "review: NO_INBOX and PLANS_NOT_EXCLUDED, sorted" \
"$(printf 'MISSING\tgone\t%s/gone\nNO_INBOX\tfakegit\t%s/fakegit/.plans/inbox\nNO_INBOX\tnoinbox\t%s/noinbox/.plans/inbox\nNO_INBOX\tnoplans\t%s/noplans/.plans/inbox\nPLANS_NOT_EXCLUDED\tleaky\t%s/leaky/.plans\nPLANS_NOT_EXCLUDED\tparkedleak\t%s/parkedleak/.plans' "$G" "$G" "$G" "$G" "$G" "$G" | sort)" \
"$OUT"
# Sending to a `none` repo is meant to fail, so its missing inbox is correct.
check "review: group none is exempt from NO_INBOX" \
  "0" "$(printf '%s\n' "$OUT" | grep -c '^NO_INBOX	parked')"
check "review: a missing checkout is MISSING only, never NO_INBOX" \
  "1" "$(printf '%s\n' "$OUT" | grep -c 'gone')"
check "review: a .git that git cannot read is not PLANS_NOT_EXCLUDED" \
  "0" "$(printf '%s\n' "$OUT" | grep -c '^PLANS_NOT_EXCLUDED	fakegit')"

mkdir -p "$G/noinbox/.plans/inbox" "$G/noplans/.plans/inbox" "$G/fakegit/.plans/inbox"
printf '.plans/\n' >> "$G/leaky/.git/info/exclude"
printf '.plans/\n' >> "$G/parkedleak/.git/info/exclude"
sed -i.bak '/^### gone$/,$d' "$G/FLEET.md" && rm "$G/FLEET.md.bak"
OUT=$("$SCAN" "$G" --review); RC=$?
check "review: every inbox present and .plans/ excluded exits 0" "0|" "$RC|$OUT"

echo "fleet-scan: $PASS passed${FAIL:+, $FAIL FAILED}" | sed 's/, 0 FAILED//'
[ "$FAIL" -eq 0 ]
