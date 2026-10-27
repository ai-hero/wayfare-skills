#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Migrate a `.plans/` store from the nine-kind schema to schema 1
# (docs/PLAN.md). Run once per repo; `wayfare-init-repo` runs it on sight of an
# unmigrated store.
#
# Usage: bash scripts/migrate-plan.sh [STORE] [--dry-run]

set -uo pipefail

LIB="$(cd "$(dirname "$0")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
. "$LIB" || { echo "migrate-plan: cannot source $LIB" >&2; exit 1; }

STORE=""
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    -*) echo "migrate-plan: unknown option '$a'" >&2; exit 2 ;;
    *) STORE="$a" ;;
  esac
done
# A dry run must not create the store: hero_work_store mkdirs and writes the
# exclude entry, which is a side effect on a repo that was only being asked.
if [ -z "$STORE" ]; then
  if [ "$DRY" = 1 ]; then STORE=$(hero_store_path) || exit 1
  else STORE=$(hero_work_store) || exit 1; fi
fi
[ -d "$STORE" ] || { echo "migrate-plan: no store at '$STORE'" >&2; exit 1; }

TODAY=$(date +%Y-%m-%d)
WARNED=0
# Called only from the main shell. A warn issued inside a $(...) increments a
# copy of WARNED that dies with the subshell, and the summary line that exists
# to make warnings impossible to miss then says there were none.
warn() { WARNED=$((WARNED + 1)); echo "migrate-plan: $*" >&2; }

ITEMS="$STORE/items"

# ---------- refusals -------------------------------------------------------

# The second-pass guard. A rerun finds no legacy files (they already sit in
# items/), so it would touch no item; what it WOULD do is rewrite PLAN.md
# from a scan of nothing: next_id back to 1, Scope back to the placeholder,
# the migration Log line gone. Hence a refusal, not a no-op.
if [ -f "$STORE/PLAN.md" ] && [ -n "$(hero_item_field "$STORE/PLAN.md" schema)" ]; then
  echo "migrate-plan: '$STORE' is already at schema $(hero_item_field "$STORE/PLAN.md" schema); nothing to do."
  exit 0
fi
# A PLAN.md without `schema:` was written by hand, and the writer below would
# replace it, Scope included.
if [ -f "$STORE/PLAN.md" ]; then
  echo "migrate-plan: '$STORE/PLAN.md' exists but carries no 'schema:'; move it aside (its Scope is worth keeping) and rerun" >&2
  exit 1
fi
# items/ populated with no PLAN.md is a run that failed midway. A rerun would
# build the covers map and the id scan from the root only, dropping every
# parent link already written and computing a next_id below ids in items/.
if [ -d "$ITEMS" ] && [ -n "$(find "$ITEMS" -maxdepth 1 -name '*.md' -print -quit 2>/dev/null)" ]; then
  echo "migrate-plan: '$ITEMS' already holds items but there is no PLAN.md: a previous run stopped midway. Move items/*.md back to '$STORE' and rerun" >&2
  exit 1
fi

# ---------- derivations ----------------------------------------------------

# kind [+ bot] -> NTYPE NSHAPE NCHANNEL; empty NSHAPE/NCHANNEL are `-`.
# Sets globals rather than printing, so warn() runs in this shell.
derive_type() { # KIND BOT FILE
  KINDNOTE=""
  case "$1" in
    ''|work-order|hardening|feature) NTYPE=task; NSHAPE=story; NCHANNEL=- ;;
    architecture)                    NTYPE=task; NSHAPE=structural; NCHANNEL=- ;;
    polish)                          NTYPE=task; NSHAPE=visual; NCHANNEL=- ;;
    bug)                             NTYPE=task; NSHAPE=defect; NCHANNEL=- ;;
    security)
      NTYPE=task; NCHANNEL=-
      if [ -n "$2" ]; then NSHAPE=dependency; else NSHAPE=defect; fi ;;
    goal)                            NTYPE=goal; NSHAPE=-; NCHANNEL=- ;;
    design-feedback)                 NTYPE=signal; NSHAPE=-; NCHANNEL=design ;;
    design-system-feedback)          NTYPE=signal; NSHAPE=-; NCHANNEL=design-system ;;
    architecture-feedback)           NTYPE=signal; NSHAPE=-; NCHANNEL=architecture ;;
    *)
      # Loud, and never guessed away: the item still migrates (a half-migrated
      # store is worse than a wrong shape), and the Log line makes the guess
      # visible in the item itself, not only on a stderr that scrolled past.
      warn "$3: unrecognized kind '$1'; migrated as task/story — check it"
      KINDNOTE="kind '$1' was not recognized; migrated as task/story — check the shape"
      NTYPE=task; NSHAPE=story; NCHANNEL=- ;;
  esac
}

# old status -> NSTATUS NRESOLUTION for the derived NTYPE; empty NRESOLUTION
# is `-`. Type-aware, because the old enums let a goal sit at `ready` and a
# feedback item at `reviewing`, and the schema-1 listing refuses both as
# invalid: a store that migrates clean and then lists its approved goal as
# invalid is a migration that failed without saying so.
derive_status() { # STATUS SUSPENDED_FROM FILE
  local s
  s=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  NRESOLUTION=-
  case "$s" in
    new)                       NSTATUS=new ;;
    todo)                      NSTATUS=accepted ;;
    accepted|planning|ready|review) NSTATUS=$s ;;
    queued)                    NSTATUS=ready ;;
    implementing|in-progress|active) NSTATUS=active ;;
    committed)                 NSTATUS=committed ;;
    reviewing)                 NSTATUS=review ;;
    done)                      NSTATUS="done" ;;
    delivered)                 NSTATUS="done"; NRESOLUTION=delivered ;;
    rejected)                  NSTATUS="done"; NRESOLUTION=rejected ;;
    suspended)
      # Suspension stops being a status and becomes `awaiting` being non-empty,
      # so the status it left is simply restored. `suspended_from` was a saved
      # copy of a value that never had to change.
      case "$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')" in
        '')        warn "$3: suspended with no suspended_from; restored to accepted"; NSTATUS=accepted ;;
        suspended) warn "$3: suspended_from is itself 'suspended'; restored to accepted"; NSTATUS=accepted ;;
        *)         derive_status "$2" "" "$3"; return ;;
      esac ;;
    *)
      warn "$3: unrecognized status '$1'; migrated as new"
      NSTATUS=new ;;
  esac
  case "$NTYPE:$NSTATUS" in
    task:done)   [ "$NRESOLUTION" = - ] && NRESOLUTION=shipped ;;
    # A goal ends by being met; `shipped` is a task's word for it.
    goal:done)   NRESOLUTION=- ;;
    goal:ready|goal:planning|goal:review)
      warn "$3: goal at '$1' has no schema-1 equivalent; migrated as accepted"
      NSTATUS=accepted ;;
    goal:committed)
      warn "$3: goal at 'committed' has no schema-1 equivalent; migrated as active"
      NSTATUS=active ;;
    signal:planning)
      warn "$3: signal at 'planning' has no schema-1 equivalent; migrated as accepted"
      NSTATUS=accepted ;;
    signal:review|signal:committed)
      warn "$3: signal at '$1' has no schema-1 equivalent; migrated as active"
      NSTATUS=active ;;
    signal:done)
      [ "$NRESOLUTION" = - ] && warn "$3: signal at 'done' with no delivered/rejected; set its resolution by hand" ;;
  esac
}

# ---------- pass 1: find items, read the covers map ------------------------

LEGACY=""
for f in "$STORE"/*.md; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  # A file with no frontmatter fence is not an item: moved into items/ it
  # would list as `invalid` on every call forever.
  if [ "$(head -n1 "$f")" != "---" ]; then
    warn "$base: no frontmatter; not an item, left in place"
    continue
  fi
  LEGACY="$LEGACY$f
"
done

if [ -z "$LEGACY" ] && [ ! -d "$ITEMS" ]; then
  echo "migrate-plan: '$STORE' holds no items; writing PLAN.md only."
fi

# id:parent:rank triples, space-delimited, looked up by string match. bash 3.2
# ships on macOS and has no associative arrays.
PARENT_MAP=" "
OPEN_GOALS=" "
COVERED=" "
while IFS= read -r f; do
  [ -n "$f" ] || continue
  [ "$(hero_item_field "$f" kind)" = goal ] || continue
  gid=$(hero_norm_id "$(hero_item_field "$f" id)")
  [ -n "$gid" ] || { warn "$(basename "$f"): goal with no id; its covers are dropped"; continue; }
  gopen=0
  case "$(hero_item_status "$f")" in new|todo|active|planning|ready) gopen=1; OPEN_GOALS="$OPEN_GOALS$gid " ;; esac
  rank=0
  while IFS= read -r cid; do
    [ -n "$cid" ] || continue
    cid=$(hero_norm_id "$cid")
    rank=$((rank + 1))
    COVERED="$COVERED$cid "
    case "$PARENT_MAP" in
      *" $cid:"*)
        # Two goals name one item. An open goal wins over a closed one: a
        # member handed to a done goal is a member no turn will ever build.
        prev=${PARENT_MAP#* $cid:}; prev=${prev%% *}; prevgid=${prev%:*}
        case "$gopen:$OPEN_GOALS" in
          1:*" $prevgid "*|0:*)
            warn "item $cid is covered by goals $prevgid and $gid; keeping $prevgid"; continue ;;
        esac
        warn "item $cid is covered by goals $prevgid (closed) and $gid (open); keeping $gid"
        PARENT_MAP=$(printf '%s' "$PARENT_MAP" | sed "s/ $cid:$prev / /") ;;
    esac
    PARENT_MAP="$PARENT_MAP$cid:$gid:$rank "
  done <<EOF
$(hero_item_list_field "$f" covers)
EOF
done <<EOF
$LEGACY
EOF

# ---------- pass 2: rewrite each item --------------------------------------

MAXID=0
COUNT=0
SEEN_IDS=" "
while IFS= read -r f; do
  [ -n "$f" ] || continue
  base=$(basename "$f")
  id=$(hero_norm_id "$(hero_item_field "$f" id)")
  case "$id" in
    ''|*[!0-9]*) warn "$base: id '$id' is not a number; the file is moved but its links cannot resolve" ;;
    *) [ "$id" -gt "$MAXID" ] && MAXID=$id ;;
  esac
  SEEN_IDS="$SEEN_IDS$id "

  derive_type "$(hero_item_field "$f" kind)" "$(hero_item_field "$f" bot)" "$base"
  derive_status "$(hero_item_status "$f")" "$(hero_item_field "$f" suspended_from)" "$base"

  parent="-" ; rank="-"
  case "$PARENT_MAP" in
    *" $id:"*)
      triple=${PARENT_MAP#* $id:}
      triple=${triple%% *}
      parent=${triple%:*}
      rank=${triple#*:} ;;
  esac

  out="$ITEMS/$base"
  if [ "$DRY" = 1 ]; then
    desc=$NTYPE
    [ "$NSHAPE" != "-" ] && desc="$desc/$NSHAPE"
    [ "$NCHANNEL" != "-" ] && desc="$desc/$NCHANNEL"
    echo "would migrate $base -> items/  ($desc, $NSTATUS)"
    COUNT=$((COUNT + 1)); continue
  fi
  mkdir -p "$ITEMS" || { echo "migrate-plan: cannot create $ITEMS" >&2; exit 1; }

  awk -v ntype="$NTYPE" -v nshape="$NSHAPE" -v nchannel="$NCHANNEL" \
      -v nstatus="$NSTATUS" -v nresolution="$NRESOLUTION" \
      -v parent="$parent" -v rank="$rank" -v today="$TODAY" -v base="$base" \
      -v kindnote="$KINDNOTE" '
    function emitopt(k, v) { if (v != "-" && v != "") printf "%s: %s\n", k, v }
    # `source: a, b` was a comma string on some items and a YAML list on
    # others. Schema 1 says list, and the two readers must agree.
    function aslist(v,   n, parts, i, out) {
      if (v ~ /^\[/) return v
      n = split(v, parts, /,[[:space:]]*/)
      out = ""
      for (i = 1; i <= n; i++) {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", parts[i])
        if (parts[i] == "") continue
        out = out (out == "" ? "" : ", ") parts[i]
      }
      return "[" out "]"
    }
    function logline(tag, body) {
      # `- DATE (ACTOR): text` -> `- DATE (ACTOR) TAG: text`; with no actor,
      # the tag goes straight after the date, and a colon already there is
      # reused rather than doubled.
      if (body ~ /^- [0-9-]+ \([^)]*\):/) { sub(/\):/, ") " tag ":", body); return body }
      if (body ~ /^- [0-9-]+ \([^)]*\)/)  { sub(/\)/, ") " tag ":", body); return body }
      if (body ~ /^- [0-9-]+:/)           { sub(/:/, " " tag ":", body); return body }
      if (body ~ /^- [0-9-]+/)            { sub(/^(- [0-9-]+)/, "& " tag ":", body); return body }
      return body
    }

    BEGIN { fence = 0; sect = ""; nlog = 0; sawkind = 0; sawanchors = 0 }

    /^---[[:space:]]*$/ {
      fence++
      if (fence == 1) { print; next }
      if (fence == 2) {
        # A legacy item may have no `kind:` line to rewrite in place, and an
        # item with no `type:` lists as invalid under schema 1 — so the
        # derivation is written here, not skipped.
        if (!sawkind) { print "type: " ntype; emitopt("shape", nshape); emitopt("channel", nchannel) }
        emitopt("parent", parent)
        emitopt("rank", rank)
        if ((srcref != "" || tgtref != "") && !sawanchors) {
          print "anchors:"
          if (srcref != "") print "  source: " srcref
          if (tgtref != "") print "  target: " tgtref
        }
        print
        next
      }
      print; next
    }

    fence == 1 {
      # Known fields are rewritten; everything else passes through verbatim,
      # so bot/pr/severity/branch/success/msg_id/budget survive untouched.
      if ($0 ~ /^kind:/)  { sawkind = 1; print "type: " ntype; emitopt("shape", nshape); emitopt("channel", nchannel); next }
      if ($0 ~ /^status:/) { print "status: " nstatus; emitopt("resolution", nresolution); next }
      if ($0 ~ /^source_ref:/) { srcref = $0; sub(/^source_ref:[[:space:]]*/, "", srcref); sub(/[[:space:]]*#.*/, "", srcref); next }
      if ($0 ~ /^target_ref:/) { tgtref = $0; sub(/^target_ref:[[:space:]]*/, "", tgtref); sub(/[[:space:]]*#.*/, "", tgtref); next }
      if ($0 ~ /^anchors:/) { sawanchors = 1 }
      if ($0 ~ /^suspended_from:/) next
      if ($0 ~ /^covers:/) { incovers = 1; next }
      if (incovers && $0 ~ /^[[:space:]]+-/) next
      incovers = 0
      if ($0 ~ /^source:/) { v = $0; sub(/^source:[[:space:]]*/, "", v); sub(/[[:space:]]*#.*/, "", v); if (v != "") { print "source: " aslist(v); next } }
      if ($0 ~ /^target:/) { v = $0; sub(/^target:[[:space:]]*/, "", v); sub(/[[:space:]]*#.*/, "", v); if (v != "") { print "target: " aslist(v); next } }
      print; next
    }

    # ---- body ----
    /^## Comments[[:space:]]*$/        { sect = "note"; next }
    /^## Mistakes[[:space:]]*$/        { sect = "mistake"; next }
    /^## Turn log[[:space:]]*$/        { sect = "turn"; next }
    /^## Design Feedback[[:space:]]*$/ { sect = "signal"; next }
    # An item that already has a Log keeps its lines as they are; a second
    # heading would strand half the history under the first.
    /^## Log[[:space:]]*$/             { sect = "log"; next }
    /^## /                             { sect = ""; print; next }

    sect != "" {
      if ($0 ~ /^[[:space:]]*$/) next
      if (sect == "log") { nlog++; lg[nlog] = $0; next }
      if (sect == "signal") {
        # The DF id and the state marker survive verbatim: a promoted signal
        # item points back at the id through `entry:`, and the marker is the
        # state of the entry itself (`[undelivered]` is what the open-feedback
        # count reads; `[item: N]`, `[queued: ...]` and `[obsolete ...]` are
        # closed). Stripping either re-proposes every entry as undelivered on
        # the next sync.
        d = $0
        if (d ~ /^-[[:space:]]*DF-[0-9]+-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9]+/) {
          sub(/^-[[:space:]]*DF-[0-9]+-/, "", d)
          dt = substr(d, 1, 10)
          nlog++; lg[nlog] = "- " dt " (migrate) signal: " substr($0, index($0, "DF-"))
        } else { nlog++; lg[nlog] = logline("signal", $0) }
        next
      }
      if ($0 ~ /^-[[:space:]]/) { nlog++; lg[nlog] = logline(sect, $0) }
      else                      { nlog++; lg[nlog] = $0 }
      next
    }

    { print }

    END {
      print ""
      print "## Log"
      print ""
      for (i = 1; i <= nlog; i++) print lg[i]
      if (kindnote != "") print "- " today " (migrate) note: " kindnote
      print "- " today " (migrate) note: migrated to schema 1 from " base
    }
  ' "$f" > "$out.tmp" && mv "$out.tmp" "$out" || { rm -f "$out.tmp"; echo "migrate-plan: failed on $base" >&2; exit 1; }
  [ "$out" = "$f" ] || rm -f "$f" || { echo "migrate-plan: migrated $base but cannot remove the legacy copy at $f" >&2; exit 1; }
  COUNT=$((COUNT + 1))
done <<EOF
$LEGACY
EOF

# A covers id no item carries would be a member nobody can find. Like a
# dangling depends_on, it is named rather than dropped.
for cid in $COVERED; do
  case "$SEEN_IDS" in *" $cid "*) ;; *) warn "a goal covers item $cid, which no item carries; the link is dropped" ;; esac
done

# ---------- PLAN.md --------------------------------------------------------

ROOT=${STORE%/.plans}
REPO=$(git -C "$ROOT" remote get-url origin 2>/dev/null \
  | sed -e 's#^git@[^:]*:##' -e 's#^https\{0,1\}://[^/]*/##' -e 's#\.git$##')
BRANCH=$(cd "$ROOT" && hero_default_branch 2>/dev/null) || BRANCH=main
HEAD=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)
# rc 2 is a value someone WROTE and the reader refused. Writing it into
# PLAN.md as `none` persists that collapse: the plan then claims the repo has
# no design target, and nothing ever said otherwise.
DESIGN=$(hero_connection_compat design at design-project "$ROOT"); rc=$?
if [ "$rc" = 2 ]; then
  echo "migrate-plan: design connection REJECTED as unsafe; writing design: none — fix HERO.md and re-run" >&2
  DESIGN=none
elif [ "$rc" != 0 ]; then
  DESIGN=none
fi

if [ "$DRY" = 1 ]; then
  echo "would write $STORE/PLAN.md (repo ${REPO:-unknown}, next_id $((MAXID + 1)))"
  echo "migrate-plan: dry run — $COUNT item(s), $WARNED warning(s)."
  exit 0
fi

{
  echo "---"
  echo "schema: 1"
  [ -n "$REPO" ] && echo "repo: $REPO"
  echo "default_branch: $BRANCH"
  echo "initialized: $TODAY"
  echo "next_id: $((MAXID + 1))"
  echo "source:"
  echo "  root: ."
  [ -n "$HEAD" ] && echo "  head: $HEAD"
  case "$DESIGN" in
    ''|none|ask) : ;;
    *) echo "target:"; echo "  project: $DESIGN" ;;
  esac
  echo "---"
  echo ""
  echo "## Scope"
  echo ""
  echo "TODO — one paragraph: what this repo is and what the plan over it is"
  echo "for. \`wayfare-init-repo\` fills this in; the migrator cannot know it."
  echo ""
  echo "## Log"
  echo ""
  echo "- $TODAY (migrate) note: migrated $COUNT item(s) from the nine-kind schema"
} > "$STORE/PLAN.md.tmp" && mv "$STORE/PLAN.md.tmp" "$STORE/PLAN.md" \
  || { rm -f "$STORE/PLAN.md.tmp"; echo "migrate-plan: items migrated but PLAN.md could not be written; fix permissions on $STORE and rerun (the run refuses until items/ is moved back)" >&2; exit 1; }

echo "migrate-plan: migrated $COUNT item(s) into $STORE/items/, wrote PLAN.md."
[ "$WARNED" -gt 0 ] && echo "migrate-plan: $WARNED warning(s) above need a look."
exit 0
