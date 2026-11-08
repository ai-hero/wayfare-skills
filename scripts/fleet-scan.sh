#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Enumerate the repos checked out in a fleet folder, and diff them against
# the fleet map, .fleet/FLEET.md. The engine behind wayfare:wayfare-review-fleet, which prints this
# output, and `sync` uses it to propose rows.
#
# Usage: fleet-scan.sh [FLEET_ROOT] [--list | --review]
#        fleet-scan.sh -h | --help
#
# --list (default): one line per child directory that is a git checkout:
#   NAME<TAB>PATH<TAB>PORT   (PORT: published host port, `-` no compose file,
#                            `?` compose file but no readable host port)
#
# --review: compare the listing with FLEET.md rows and print one finding per
#   line as CODE<TAB>NAME<TAB>DETAIL (DETAIL is free text), sorted:
#   NOT_CLONED         a row whose path under the fleet folder does not exist
#                      (detail: path). Informational: the map is shared through
#                      the register, so it names repos this machine never
#                      cloned. It alone never makes --review exit 1
#   MOVED              a NOT_CLONED row whose repo is checked out elsewhere in
#                      the folder: an unmapped checkout whose origin's repo
#                      name is the row name (detail: where it is)
#   DANGLING_LINK      a row whose path is a symlink to nothing
#   NO_PARENT          a relative row whose parent folder does not exist in
#                      the fleet folder, usually a mistyped `path:`
#   ABSENT_OUTSIDE     an absolute row (outside the fleet folder) whose path
#                      does not exist; sync never clones there
#   BAD_ROW            a row hero_fleet_repos refused   (detail: the reason)
#   NOT_GIT            a row whose path is not a git repo
#   PORT_MISMATCH      row port differs from compose    (detail: row -> compose)
#   PORT_UNIMPLEMENTED row claims a port, no compose file
#   PORT_UNPARSED      row claims a port, compose file has no readable one
#                      (these three are fleet-only: a `none` row claims a port
#                      as a reservation, and the fleet does not audit how a
#                      repo it does not govern binds it)
#   PORT_COLLISION     two repos on one port, claimed or published, fleet or
#                      not: a `none` repo's compose binds the host just the same
#   NO_HERO            a fleet repo (group != none) without HERO.md
#   NO_AGENTS          a fleet repo without AGENTS.md or CLAUDE.md
#   NOT_FLEET_AWARE    a fleet repo whose instructions file has no `## Fleet`
#                      section (assets/fleet/agents-md-fleet-section.md)
#   NO_INBOX           a fleet repo without .plans/inbox/, so a message or
#                      reply sent to it cannot be delivered
#   PLANS_NOT_EXCLUDED a repo, fleet or not, whose .plans/ git does not
#                      ignore, so the store can be committed
#
#   A checkout with no row is NOT reported. FLEET.md defines the fleet; a
#   folder cloned into the fleet folder does not join by being there. Use
#   --list to see what is on disk.
#
# Exit codes:
#   0  --list ran; or --review found nothing beyond NOT_CLONED
#   1  --review found at least one other finding
#   2  usage error; or, for --review, no .fleet/FLEET.md at the root (or one
#      that is not a readable file, or only a top-level FLEET.md), a HERO.md
#      in the root, a root inside a git work tree, or a root this machine pins
#      no register for (the error names the line to add; a pin is not checked
#      against the register's origin here, the audit does that)

set -uo pipefail

HERO_LIB="$(cd "$(dirname "$0")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "fleet-scan: cannot source $HERO_LIB" >&2; exit 2; }

# The end line tracks the header block above. Add a line up there and this
# range silently truncates `--help` mid-sentence — no error, and the Exit
# codes section is what falls off first.
usage() { sed -n '5,60p' "$0" | sed 's/^# \{0,1\}//'; }

MODE=list
ROOT=""
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --list) MODE=list ;;
    --review) MODE=review ;;
    -*) echo "fleet-scan: unknown option $arg" >&2; usage >&2; exit 2 ;;
    *) ROOT="$arg" ;;
  esac
done
ROOT="${ROOT:-$PWD}"
ROOT=$(cd "$ROOT" 2>/dev/null && pwd -P) || { echo "fleet-scan: no such directory: $ROOT" >&2; exit 2; }
RANGE=$(hero_fleet_field port-range "$ROOT" 2>/dev/null || true)

scan() {
  local d
  for d in "$ROOT"/*/; do
    d="${d%/}"
    [ -e "$d/.git" ] || continue
    printf '%s\t%s\t%s\n' "${d##*/}" "$d" "$(hero_compose_port "$d" "$RANGE")"
  done
}

if [ "$MODE" = list ]; then
  scan
  exit 0
fi

# Called once with stderr open so the note about a leftover top-level FLEET.md
# reaches the reader; the later reads route stderr into $BAD or /dev/null.
hero_fleet_map "$ROOT" >/dev/null; rc=$?
[ "$rc" != 2 ] || exit 2
[ "$rc" = 0 ] || { echo "fleet-scan: no fleet map in $ROOT; clone the register into $ROOT/.fleet so .fleet/FLEET.md exists, or run wayfare:wayfare-sync-fleet to create it" >&2; exit 2; }
[ ! -f "$ROOT/HERO.md" ] || { echo "fleet-scan: $ROOT holds HERO.md beside its fleet map, which is a repo, not a fleet" >&2; exit 2; }
hero_at_fleet_root "$ROOT" 2>/dev/null || { echo "fleet-scan: $ROOT is inside a git work tree, so its map is a clone's content, not a fleet map" >&2; exit 2; }
hero_require_register_pin "$ROOT" >/dev/null || exit 2

BAD=$(mktemp) || exit 2
trap 'rm -f "$BAD"' EXIT
LISTING=$(scan)
ROWS=$(hero_fleet_repos "$ROOT" 2>"$BAD"); rc=$?
case "$rc" in 0|3) ;; *) echo "fleet-scan: cannot read the rows of $ROOT's fleet map" >&2; exit 2 ;; esac
TAB=$'\t'
NL=$'\n'

# A function, not an inline $( … ): bash 3.2 cannot parse an unparenthesised
# `pat)` inside a command substitution.
review() {
  local name repo_path group rport actual line ports uncloned origin_name moved
  ports=""      # "PORT NAME" lines: every claim and every published port
  uncloned=""   # "NAME<TAB>PATH" lines, held back until MOVED is ruled out
  while IFS="$TAB" read -r name repo_path group rport; do
    [ -n "$name" ] || continue
    if [ ! -e "$repo_path" ]; then
      # A claim is a claim whether or not this machine cloned the repo, and
      # another row on the same port still collides with it.
      [ -z "$rport" ] || ports="$ports$rport $name$NL"
      if [ -L "$repo_path" ]; then
        printf 'DANGLING_LINK\t%s\t%s\n' "$name" "$repo_path"
      else
        case "$repo_path" in
          "$ROOT"/*)
            if [ -d "${repo_path%/*}" ]; then uncloned="$uncloned$name$TAB$repo_path$NL"
            else printf 'NO_PARENT\t%s\t%s\n' "$name" "$repo_path"; fi ;;
          *) printf 'ABSENT_OUTSIDE\t%s\t%s\n' "$name" "$repo_path" ;;
        esac
      fi
      continue
    fi
    [ -e "$repo_path/.git" ] || { printf 'NOT_GIT\t%s\t%s\n' "$name" "$repo_path"; continue; }
    case "$LISTING" in
      *"$TAB$repo_path$TAB"*) actual=${LISTING#*"$TAB$repo_path$TAB"}; actual=${actual%%"$NL"*} ;;
      *) actual=$(hero_compose_port "$repo_path" "$RANGE") ;;   # a row whose repo_path is not a direct child
    esac
    if [ -n "$rport" ]; then
      # These three judge whether a repo implements the port its row claims,
      # and that is only the fleet's business for a member. For a `none` row
      # the claim is a RESERVATION, not a promise: the row exists so nothing
      # else takes the number, and a repo the fleet does not govern is free to
      # bind whatever it likes. Reporting it produced a finding whose only
      # honest fix was to edit a non-member's compose file from the fleet root.
      # The reservation below is still recorded, and the port it actually
      # publishes is still collected, so PORT_COLLISION is unaffected.
      if [ "$group" != none ]; then
        case "$actual" in
          -)   printf 'PORT_UNIMPLEMENTED\t%s\t%s (no compose file)\n' "$name" "$rport" ;;
          '?') printf 'PORT_UNPARSED\t%s\t%s (compose file, no readable host port)\n' "$name" "$rport" ;;
          "$rport") ;;
          *)   printf 'PORT_MISMATCH\t%s\t%s -> %s\n' "$name" "$rport" "$actual" ;;
        esac
      fi
      ports="$ports$rport $name$NL"
    fi
    case "$actual" in -|'?'|"$rport") ;; *) ports="$ports$actual $name$NL" ;; esac
    # Only rc 1 means "not ignored". 128 is a .git that git cannot read, and
    # reporting it would send someone to fix an exclude file that is fine.
    if [ -d "$repo_path/.plans" ]; then
      git -C "$repo_path" check-ignore -q .plans/ 2>/dev/null
      [ $? -ne 1 ] || printf 'PLANS_NOT_EXCLUDED\t%s\t%s\n' "$name" "$repo_path/.plans"
    fi
    [ "$group" != none ] || continue
    [ -d "$repo_path/.plans/inbox" ] || printf 'NO_INBOX\t%s\t%s\n' "$name" "$repo_path/.plans/inbox"
    [ -f "$repo_path/HERO.md" ] || printf 'NO_HERO\t%s\t%s\n' "$name" "$repo_path"
    if [ -f "$repo_path/AGENTS.md" ] || [ -f "$repo_path/CLAUDE.md" ]; then
      # CLAUDE.md is normally a symlink to AGENTS.md; read whichever resolves.
      grep -qs '^## Fleet' "$repo_path/AGENTS.md" "$repo_path/CLAUDE.md" || printf 'NOT_FLEET_AWARE\t%s\t%s\n' "$name" "$repo_path"
    else
      printf 'NO_AGENTS\t%s\t%s\n' "$name" "$repo_path"
    fi
  done <<< "$ROWS"

  # A checkout with no row is NOT a finding. FLEET.md defines the fleet; the
  # folder is just where things happen to be cloned, and a repo that belongs to
  # nobody here needs no row to say so. Reporting it made every parked clone a
  # standing item that `sync` then offered to "fix" by adding a row, which is
  # how a non-member acquires a row and starts reading as one.
  # Its port is still collected: a non-fleet repo's compose binds the host port
  # just the same, so it can still collide with a claimed one. `--list` remains
  # the way to discover what is on disk.
  moved=""
  while IFS="$TAB" read -r name repo_path actual; do
    [ -n "$name" ] || continue
    case "$ROWS" in *"$TAB$repo_path$TAB"*) continue ;; esac
    case "$actual" in -|'?') ;; *) ports="$ports$actual $name$NL" ;; esac
    [ -n "$uncloned" ] || continue
    origin_name=$(git -C "$repo_path" remote get-url origin 2>/dev/null) || continue
    origin_name=${origin_name%/}; origin_name=${origin_name%.git}; origin_name=${origin_name##*[/:]}
    case "$NL$uncloned" in *"$NL$origin_name$TAB"*)
      printf 'MOVED\t%s\tchecked out at %s\n' "$origin_name" "$repo_path"
      moved="$moved$origin_name$NL" ;;
    esac
  done <<< "$LISTING"
  while IFS="$TAB" read -r name repo_path; do
    [ -n "$name" ] || continue
    case "$NL$moved" in *"$NL$name$NL"*) continue ;; esac
    printf 'NOT_CLONED\t%s\t%s\n' "$name" "$repo_path"
  done <<< "$uncloned"

  printf '%s' "$ports" | sort -u | awk '
    NF == 2 { if ($1 in first) printf "PORT_COLLISION\t%s\t%s, also %s\n", $2, $1, first[$1]; else first[$1] = $2 }'

  while IFS= read -r line; do
    case "$line" in
      *"skipping '"*"': "*) name=${line#*skipping \'}; name=${name%%\'*}; printf 'BAD_ROW\t%s\t%s\n' "$name" "${line#*\': }" ;;
    esac
  done < "$BAD"
}

FINDINGS=$(review) || { echo "fleet-scan: review failed" >&2; exit 2; }
[ -n "$FINDINGS" ] || exit 0
sort <<< "$FINDINGS"
grep -qv "^NOT_CLONED$TAB" <<< "$FINDINGS" || exit 0
exit 1
