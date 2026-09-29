#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# hero-lib.sh: shared helpers for wayfare.
#
# Sourced by skills, not executed. Every function here exists because the same
# logic was previously inlined in two or more SKILL.md files and had already
# drifted between copies. If you find yourself pasting the same awk/grep into a
# second skill, it belongs here instead.
#
# Usage from a skill:
#
#   WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
#   HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
#   # shellcheck source=/dev/null
#   . "$HERO_LIB" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
#
# Contract:
#   - Values go to stdout. Human-readable notes go to stderr. A function that
#     returns data never mixes the two, so a caller can parse stdout blindly.
#   - Absence/failure is a non-zero return, never an exit. The caller decides
#     what is fatal. No function exits the calling shell.
#   - Callers' shell state (cwd, variables) is never modified. Functions that
#     need to cd do it inside a subshell.
#   - A function that writes says so in its own comment (hero_exclude_add,
#     hero_work_store, hero_msg_deposit, the deploy-pending and pending-lock
#     helpers). Everything else is read-only.

# ---------- repo + config --------------------------------------------------

# Absolute path to the repo root, or the cwd when not in a git repo.
hero_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

# Read a single `- key: value` field from a hero-style markdown file. HERO.md
# and FLEET.md share the grammar, so they share the reader. With BLOCK (a full
# heading line, `## Fleet` or `### auth`), only that section is searched:
# FLEET.md keeps one `### NAME` block per repo, so an unscoped read of `path`
# would return whichever repo happens to come first. PARENT (an H2 line)
# further requires an H3 block to sit under that H2. The standard invites
# prose after `## Repos`, and a `### auth` under `## Known issues` must not
# answer for the repo row.
#
#   hero_md_field "$root/HERO.md" default-branch
#   hero_md_field "$fleet/FLEET.md" port "### auth" "## Repos"
#
# Prints the value (trimmed, comments stripped) on stdout.
#
# Returns: 0 found, 1 absent or present-but-empty, 2 rejected as unsafe (or a
# BLOCK that is not a heading line. A bare name would silently read as
# "absent").
#
# HERO.md is repo content, so in a cloned repo it is attacker-controlled. Its
# values flow into git and gh command lines across the skills. A value starting
# with `-` is read by those tools as an OPTION rather than an argument, and
# `git fetch origin --upload-pack=...` executes its value through a shell,
# arbitrary command execution from nothing but a checked-in config file.
# Rejecting here covers every call site at once, which is the whole point of
# having one reader.
hero_md_field() {
  local file key block parent value
  file="$1"
  key="$2"
  block="${3:-}"
  parent="${4:-}"
  [ -r "$file" ] || return 1
  block=${block%"${block##*[![:space:]]}"}
  parent=${parent%"${parent##*[![:space:]]}"}
  case "$block" in ''|'## '*|'### '*) ;; *)
    echo "hero_md_field: BLOCK must be a full '## X' or '### X' heading line, got: $block" >&2
    return 2 ;;
  esac
  # Skip fenced code blocks (both files document their own syntax in examples)
  # and keep scanning past a key whose value is empty, so a real setting later
  # in the file is not masked by a placeholder earlier in it.
  value=$(awk -v k="- $key" -v b="$block" -v p="$parent" '
    /^```/ { fence = !fence; next }
    fence  { next }
    /^##+ / {
      h = $0; sub(/[[:space:]]+$/, "", h)
      # An H2 starts a new section. An H3 only matters when the caller asked
      # for an H3, so a `### x` under `## Fleet` does not end the Fleet
      # section, and an H4 or deeper never opens or closes a block.
      if (h ~ /^## /)                        { sec = h; inblk = (h == b) }
      else if (h ~ /^### / && b ~ /^### /)   inblk = (h == b && (p == "" || sec == p))
      next
    }
    (b == "" || inblk) && index($0, k ":") == 1 {
      v = $0; sub(/^[^:]*: */, "", v); sub(/ *#.*/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      if (v != "") { print v; exit }
    }
  ' "$file")
  # Strip a stray surrounding quote pair (awk already trimmed whitespace).
  value=${value#[\"\']}; value=${value%[\"\']}
  [ -n "$value" ] || return 1
  case "$value" in
    -*)
      echo "hero_md_field: refusing '$key' in ${file##*/}; value starts with '-' and would be read as a command-line option: $value" >&2
      return 2 ;;
  esac
  # Control characters (newline, NUL-ish, escape) have no legitimate place in a
  # config scalar and break line-oriented consumers.
  case "$value" in
    *[[:cntrl:]]*)
      echo "hero_md_field: refusing '$key' in ${file##*/}; value contains control characters" >&2
      return 2 ;;
  esac
  printf '%s' "$value"
}

# Read a single `- key: value` field from HERO.md.
#   hero_field default-branch
#   hero_field bot-username
# First match wins, across sections and within one. `platform` repeats across
# sections (CI/CD and Deployment): read it with hero_md_field and a BLOCK, or
# the CI/CD value answers a Deployment question. `health-endpoint` repeats
# within a section and needs its own scan (see ship-pr).
hero_field() {
  local root
  root="${2:-$(hero_root)}"
  hero_md_field "$root/HERO.md" "$1"
}

# One field from a connection block in HERO.md (docs/CONNECTIONS.md):
#   hero_connection design at
#   hero_connection design-system namespace
# `hero_field` would answer from any section, and `namespace` or `type` exists
# in more than one, so a connection field is never read without its block.
# The shape rules for the two connection values that reach a COMMAND LINE
# rather than a comparison. Held here, not inline in one reader, because
# hero_connection_compat answers the same questions from the LEGACY key: a
# guard on only the new spelling is no guard at all until every repo has
# migrated, and the OWNER/NAME shape was enforced before connections existed.
#
# rc 0 allowed, 2 refused with the reason on stderr.
#
# TYPE matters for `at`: the locator's shape is the TYPE's business, not the
# kind's. `github` puts a repo there and reaches `gh --repo`; `linear` and
# `jira` put a workspace there, which `references/init.md` writes as the
# default template, and holding those to OWNER/NAME refuses the config this
# plugin itself generates.
hero_connection_guard() { # KIND KEY VALUE [TYPE]
  case "$2" in
    # `reach` names a tool, and docs/CONNECTIONS.md tells the agent to go check
    # that it is there: `command -v $REACH`, `$REACH --version`. A value
    # carrying `;`, `|`, `$(` or a space is a command that probe would run, and
    # refusing a leading `-` (all hero_md_field does) does not stop it.
    reach)
      printf '%s' "$3" | grep -qE '^[A-Za-z0-9._-]+$' && return 0
      echo "hero_connection: refusing $1.reach '$3'; a reach names one tool, [A-Za-z0-9._-] only" >&2
      return 2 ;;
    at)
      [ "$1" = issues ] || return 0
      # `none` is a declared answer, not a destination.
      [ "$(printf '%s' "$3" | tr '[:upper:]' '[:lower:]')" = none ] && return 0
      case "$(printf '%s' "${4:-}" | tr '[:upper:]' '[:lower:]')" in
        linear|jira)
          # A workspace, handed to an MCP tool as a parameter rather than to
          # argv. Still a closed shape: it has no use for a space or a shell
          # metacharacter.
          printf '%s' "$3" | grep -qE '^[A-Za-z0-9][A-Za-z0-9._/-]*$' && return 0
          echo "hero_connection: refusing issues.at '$3'; a workspace is [A-Za-z0-9._/-]" >&2
          return 2 ;;
        *)
          # github, self, or a block with no type: this is what reaches
          # `gh --repo`. The shape also excludes a host qualifier, since
          # `gh --repo ghe.attacker.example/owner/repo` files this repo's work
          # into someone else's GitHub Enterprise with this user's token, and
          # HERO.md is repo content in a clone.
          printf '%s' "$3" | grep -qE '^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$' && return 0
          echo "hero_connection: refusing issues.at '$3'; it reaches 'gh --repo' and must be OWNER/NAME" >&2
          return 2 ;;
      esac ;;
  esac
  return 0
}

hero_connection() { # KIND KEY [ROOT]
  local root value ctype
  root="${3:-$(hero_root)}" || return 1
  value=$(hero_md_field "$root/HERO.md" "$2" "### $1" "## Connections") || return $?
  # The block's own `type` decides what shape `at` may take. Read straight from
  # hero_md_field, never back through hero_connection, which would recurse.
  if [ "$2" = at ]; then
    ctype=$(hero_md_field "$root/HERO.md" type "### $1" "## Connections" 2>/dev/null)
  fi
  hero_connection_guard "$1" "$2" "$value" "${ctype:-}" || return 2
  printf '%s' "$value"
}

# A connection field, falling back to the flat HERO.md key it replaced.
#   hero_connection_compat design at design-project
#
# Connections moved out of `## Wayfare` and `## Project Management`
# (docs/CONNECTIONS.md), and a repo that has not migrated still carries the old
# key. Reading only the new shape would report a CONFIGURED attachment as
# absent, which is the one collapse that standard exists to prevent: the run
# then proceeds as though the repo had no design target at all. The legacy
# read is announced on stderr, once per call, so the fix is visible rather
# than indefinitely free.
#
# rc mirrors the reader that answered: 0 found, 1 neither set, 2 refused.
hero_connection_compat() { # KIND KEY LEGACY_KEY [ROOT]
  local root value rc
  root="${4:-$(hero_root)}" || return 1
  value=$(hero_connection "$1" "$2" "$root"); rc=$?
  if [ "$rc" = 1 ]; then
    value=$(hero_field "$3" "$root"); rc=$?
    # The legacy value goes through the same guard: applying it only to the new
    # spelling guards every repo except the ones still carrying the old one.
    if [ "$rc" = 0 ] && ! hero_connection_guard "$1" "$2" "$value"; then
      value=""; rc=2
    fi
    # Name the file: this runs against SIBLING repos too, and an unqualified
    # "HERO.md still carries..." sends the operator to fix the wrong one.
    [ "$rc" = 0 ] && echo "hero: $root/HERO.md still carries '$3'; it belongs under '## Connections' as '### $1' / '$2' (docs/CONNECTIONS.md)" >&2
  fi
  [ -n "$value" ] && printf '%s' "$value"
  return "$rc"
}

# Resolve a repo-kind connection to an absolute checkout path.
#   hero_connection_repo design-system
#
# `at` holds a FLEET.md ROW NAME when there is a fleet, because the map is
# local and paths differ per machine, and a plain path otherwise
# (docs/CONNECTIONS.md). Resolving it in the caller is how the two spellings
# get answered differently in different places: a row name read as a path
# becomes "$ROOT/design-system", which does not exist, and the run reports "no
# design system" for what is actually a row it never looked up.
#
# `type` IS THE DISCRIMINATOR, and it is read before `at`. Deciding on `at`
# alone collapses three states the standard forbids collapsing: a refused value
# reads as none, `type: self` reads as none, and a `type: none` block with a
# stale `at` still resolves — the dead key overriding the declared absence.
#
# rc: 0 resolved, 1 none (or nothing to resolve), 2 refused or not a repo-kind
# connection, 3 set but unreachable. 3 is NOT 1 and 2 is NOT 1: "cannot reach
# it", "someone wrote something unsafe" and "there is none" are three answers,
# and every one of them needs a different fix.
hero_connection_repo() { # KIND [ROOT]
  local root ctype at fleet_root row_path rc
  root="${2:-$(hero_root)}" || return 1

  ctype=$(hero_connection "$1" type "$root"); rc=$?
  [ "$rc" = 2 ] && return 2
  ctype=$(printf '%s' "$ctype" | tr '[:upper:]' '[:lower:]')
  case "$ctype" in
    none) return 1 ;;
    # The attachment exists and lives in this repo, so the checkout to read is
    # this one. Returning 1 here would report it as absent, which is the pair
    # docs/CONNECTIONS.md spends a paragraph keeping apart.
    # `pwd -P`, like every other branch: a caller comparing this against a
    # path it resolved itself must not get a symlinked spelling back from one
    # branch and a physical one from the others.
    self) (cd "$root" && pwd -P) || return 3
          return 0 ;;
    # A design project id or a tracker workspace is not a checkout. Without
    # this, a UUID falls through to the path branch and comes back as rc 3,
    # reporting a perfectly reachable design as a missing directory.
    claude-design|figma|github|linear|jira)
      echo "hero_connection_repo: $1 is type '$ctype', which names no checkout" >&2
      return 2 ;;
  esac

  at=$(hero_connection "$1" at "$root"); rc=$?
  [ "$rc" = 2 ] && return 2
  # A type that names a repo, with no `at`, is a half-written block, not an
  # absence. Returning 1 here would report it as "there is none" with nothing
  # on stderr, which is the same collapse hero_connections prints `?` to avoid.
  if [ "$rc" != 0 ] || [ -z "$at" ]; then
    echo "hero_connection_repo: $1 is type '$ctype' but has no 'at' to resolve" >&2
    return 3
  fi
  [ "$(printf '%s' "$at" | tr '[:upper:]' '[:lower:]')" = none ] && return 1
  # An `at` with no `type` beside it is the other half-written block. Checked
  # AFTER the reads above, so a refused `at` still reports as refused and a
  # declared `none` still reports as none: half-written must not outrank
  # either, or it becomes a catch-all that hides both.
  if [ -z "$ctype" ]; then
    echo "hero_connection_repo: $1 has an 'at' but no 'type' to resolve it against" >&2
    return 3
  fi

  fleet_root=$(hero_fleet_root "$root" 2>/dev/null) || fleet_root=""
  if [ -n "$fleet_root" ]; then
    # hero_fleet_repos' skip lines reach stderr rather than /dev/null: a row it
    # REFUSED is not a row that does not exist, and silencing it makes the
    # message below ("neither a FLEET.md row nor a directory") a lie about a
    # row that is right there in the map.
    row_path=$(hero_fleet_repos "$fleet_root" | awk -F'\t' -v n="$at" '$1 == n { print $2; exit }')
    if [ -n "$row_path" ]; then
      [ -d "$row_path" ] || { echo "hero_connection_repo: $1 row '$at' has no checkout at $row_path" >&2; return 3; }
      printf '%s' "$row_path"; return 0
    fi
  fi

  # A path, resolved against ROOT rather than $PWD so a caller running from a
  # subdirectory does not get a different answer. Unlike hero_fleet_repos there
  # is NO containment check: a connection legitimately points outside its own
  # tree (`../design-system`), and the fleet's check exists because a row must
  # stay inside the fleet it is a row of. What keeps this safe is the caller,
  # which reads the resolved path and never writes it (docs/CONNECTIONS.md).
  case "$at" in /*) row_path=$at ;; *) row_path="$root/$at" ;; esac
  [ -d "$row_path" ] || {
    echo "hero_connection_repo: $1 at '$at' is neither a FLEET.md row nor a directory" >&2
    return 3
  }
  # `-d` passes for a directory with no search permission, and a dropped mount
  # is present-but-not-traversable. Letting the subshell's rc fall out of the
  # function turns that into rc 1, which is "there is none": the run then drops
  # the whole lane instead of reporting a checkout it cannot enter.
  (cd "$row_path" && pwd -P) || {
    echo "hero_connection_repo: $1 at '$at' resolves to $row_path, which cannot be entered" >&2
    return 3
  }
}

# Every declared connection, one per line: KIND<TAB>TYPE<TAB>AT<TAB>REACH.
# One awk pass, not a loop over hero_connection: that re-parses HERO.md three
# times per block.
#
# A block with `type: none` IS printed. A declared absence is an answer
# (docs/CONNECTIONS.md), and dropping it here makes it indistinguishable from
# a kind nobody has looked at, which is the one distinction this standard
# exists to keep. A block with no `type:` line prints `?`, not `none`: half
# written is not declared absent. AT and REACH are `-` when unset,
# never empty, so a caller's `IFS=$'\t' read` is safe.
#
# A block that cannot be trusted is SKIPPED, not defaulted: a value starting
# with `-` (it would be read as a command-line option), a control character, a
# kind that is not [A-Za-z0-9._-], or a duplicate kind. Each skip is one
# stderr line and the function returns 3 — same contract as hero_fleet_repos,
# because the caller reacts to it the same way.
hero_connections() { # [ROOT]
  local root
  root="${1:-$(hero_root)}" || return 1
  [ -r "$root/HERO.md" ] || return 1
  awk '
    # \034, not a tab, for the reason hero_fleet_repos gives (see its awk).
    # No apostrophe anywhere in this program: it is single-quoted, and one
    # would end it mid-parse. This comment lost its own quote to that once.
    #
    # awk EXTRACTS; the shell below applies the value rules. Re-implementing
    # the quote strip and the trust checks here would fork them from
    # hero_md_field, and the two readers of one line would disagree.
    function flush() { if (kind != "") printf "%s\034%s\034%s\034%s\n", kind, t, a, r; kind = "" }
    /^```/ { fence = !fence; next }
    fence  { next }
    /^## / { flush(); sec = $0; sub(/[[:space:]]+$/, "", sec); next }
    sec == "## Connections" && /^### / {
      flush(); kind = $0; sub(/^### +/, "", kind); sub(/[[:space:]]+$/, "", kind)
      t = ""; a = ""; r = ""; next
    }
    kind != "" && /^- (type|at|reach):/ {
      k = $0; sub(/^- /, "", k); sub(/:.*/, "", k)
      v = $0; sub(/^[^:]*: */, "", v); sub(/ *#.*/, "", v); gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      # First non-empty wins, the rule hero_md_field follows. Last-wins would
      # make a duplicated key answer differently here than it does through
      # hero_connection.
      if (v == "") next
      if      (k == "type"  && t == "") t = v
      else if (k == "at"    && a == "") a = v
      else if (k == "reach" && r == "") r = v
    }
    END { flush() }
  ' "$root/HERO.md" | {
    local kind t a r v reason seen nbad
    seen=" "; nbad=0
    while IFS=$'\034' read -r kind t a r; do
      reason=""
      case "$kind" in
        .|..|''|*[!A-Za-z0-9._-]*) reason="kind is [A-Za-z0-9._-] only, not '$kind'" ;;
      esac
      [ -n "$reason" ] || case "$seen" in *" $kind "*) reason="duplicate kind" ;; esac
      # Marked seen even when skipped, so a second block of the same kind is
      # reported as the duplicate it is. Appending only on success let a bad
      # first block be skipped and its clean twin printed as the answer, while
      # hero_connection — first-match-wins — still refused the bad one.
      seen="$seen$kind "
      t=${t#[\"\']}; t=${t%[\"\']}
      a=${a#[\"\']}; a=${a%[\"\']}
      r=${r#[\"\']}; r=${r%[\"\']}
      for v in "$t" "$a" "$r"; do
        [ -n "$reason" ] || case "$v" in -*|*[[:cntrl:]]*) reason="a value starts with '-' or holds a control character" ;; esac
      done
      # THE guard, not a copy of it. Restating the two regexes here is what let
      # the listing and the field reader disagree about `at: None` until a
      # review caught it; a caller that re-implements a rule eventually
      # implements a different one.
      [ -n "$reason" ] || [ -z "$r" ] \
        || reason=$(hero_connection_guard "$kind" reach "$r" 2>&1 >/dev/null)
      [ -n "$reason" ] || [ -z "$a" ] \
        || reason=$(hero_connection_guard "$kind" at "$a" "$t" 2>&1 >/dev/null)
      if [ -n "$reason" ]; then
        echo "hero_connections: skipping '$kind': $reason" >&2
        nbad=$((nbad + 1)); continue
      fi
      # A block with no `type:` line is NOT a declared `none`. It is half
      # written, and printing it as `none` is the unset-collapsed-into-absent
      # error one level down from the missing-block case.
      printf '%s\t%s\t%s\t%s\n' "$kind" "${t:-?}" "${a:--}" "${r:--}"
    done
    [ "$nbad" -eq 0 ] || return 3
  }
}

# Is this a shape git will accept as a branch name? Used to gate values that
# reach `git fetch`/`checkout`/`merge` and `gh pr create --base`.
hero_is_valid_branch() {
  [ -n "$1" ] || return 1
  case "$1" in -*|*' '*) return 1 ;; esac
  git check-ref-format --branch "$1" >/dev/null 2>&1
}

# Validate + normalize a git repo reference before it reaches `git ls-remote`,
# `git clone`, or `git -C` as a REMOTE URL. This is to a repo URL what
# hero_is_valid_branch is to a branch name.
#
# HERO.md is attacker-controlled in a cloned repo, and hero_field only blocks a
# leading `-` and control chars, but NOT git's `ext::sh -c "..."` transport helper,
# which git executes as a shell command. A `target-repo: ext::sh -c "curl …|sh"`
# therefore sails through hero_field and runs on the victim's machine the moment
# a skill feeds it to `git ls-remote`. This gate closes that at the one place
# every call site can share.
#
# Accepts and echoes a NORMALIZED value on stdout:
#   OWNER/NAME        -> https://github.com/OWNER/NAME  (GitHub shorthand git won't resolve itself)
#   https:// ssh://   -> unchanged
#   git@host:path     -> unchanged (scp-style ssh)
#   an existing local directory -> unchanged
#   none              -> unchanged (callers treat "disabled" uniformly)
# Everything else (`::` transport helpers, file://, other URL schemes, a
# non-existent bare path) is REJECTED: non-zero return, message on stderr.
hero_normalize_repo_ref() {
  local ref="$1"
  [ -n "$ref" ] || return 1
  [ "$ref" = none ] && { printf 'none'; return 0; }
  # `word::rest` is the transport-helper syntax (ext::, fd::, and so on), which is the RCE path.
  case "$ref" in
    *::*)
      echo "hero_normalize_repo_ref: refusing '$ref'; '::' transport-helper syntax runs a command" >&2
      return 2 ;;
  esac
  case "$ref" in
    https://*|ssh://*) printf '%s' "$ref"; return 0 ;;
    file://*)
      echo "hero_normalize_repo_ref: refusing '$ref'; file:// is not an allowed transport" >&2
      return 2 ;;
    *://*)
      echo "hero_normalize_repo_ref: refusing '$ref'; only https:// and ssh:// URL transports are allowed" >&2
      return 2 ;;
  esac
  # scp-style ssh (git@host:path): a colon, no scheme, no space.
  case "$ref" in
    *' '*) ;;                         # a space is never a valid ref → reject below
    *@*:*) printf '%s' "$ref"; return 0 ;;
  esac
  # An existing local directory is a safe, non-executing target.
  if [ -d "$ref" ]; then printf '%s' "$ref"; return 0; fi
  # GitHub OWNER/NAME shorthand: exactly one slash, safe chars, no colon/space.
  # In `case` globs `*` matches `/` too, so guard the slash count explicitly
  # (*/*/* = two+ slashes) rather than relying on char classes to exclude it.
  case "$ref" in
    *' '*|*:*|*/*/*) ;;                     # space, colon, or 2+ slashes → not shorthand
    */*)
      case "$ref" in
        *[!A-Za-z0-9_./-]*) ;;              # any char outside the safe set → reject
        *) printf 'https://github.com/%s' "$ref"; return 0 ;;
      esac ;;
  esac
  echo "hero_normalize_repo_ref: refusing '$ref': not OWNER/NAME, https://, ssh://, git@host:path, or an existing local directory" >&2
  return 2
}

# The repo's default branch per HERO.md, falling back to `main`.
#
# The fallback is silent by design at the call sites that only *read* (a diff
# base, a log range). Call sites that branch, merge, or open a PR against it
# should use hero_default_branch_verbose so a missing/mistyped HERO.md field
# can't silently target the wrong branch.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_default_branch() {
  local b
  if b=$(hero_field default-branch "$@") && hero_is_valid_branch "$b"; then
    printf '%s' "$b"
    return 0
  fi
  # A value that is not a valid branch name is as dangerous as one starting with
  # `-`: `main:refs/heads/evil`, `..`, `@{u}` and `main^` are all accepted by
  # `git fetch`/`checkout` as something other than the branch they resemble.
  # hero_field's character gate cannot catch those; check-ref-format can.
  [ -n "${b:-}" ] && echo "hero_default_branch: '$b' is not a valid branch name, using main" >&2
  printf 'main'
}

# Same, but reports where the value came from on stderr. Use before any
# destructive or outward-facing operation.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_default_branch_verbose() {
  local b rc
  b=$(hero_field default-branch "$@"); rc=$?
  if [ "$rc" = 0 ] && hero_is_valid_branch "$b"; then
    printf '%s' "$b"
    echo "default branch: $b (from HERO.md)" >&2
    return 0
  fi
  printf 'main'
  # Distinct messages: "not found" sends an operator hunting for a missing key
  # that is actually present and was rejected.
  case "$rc" in
    2) echo "default branch: main (fallback: HERO.md value REJECTED as unsafe)" >&2 ;;
    *) if [ -n "${b:-}" ]; then
         echo "default branch: main (fallback: '$b' is not a valid branch name)" >&2
       else
         echo "default branch: main (fallback: HERO.md default-branch not found)" >&2
       fi ;;
  esac
  return 3
}

# Advisory staleness hint: warn when HERO.md is older than the config files
# that shape it. Prints one note and always returns 0. It never blocks.
#
# This is the deliberate *fast subset* of scripts/check-hero-staleness.sh that
# the daily-flow skills (push-pr, wayfare-build-task) want at Step 0. The two are meant
# to stay roughly aligned but not identical: the standalone script can carry a
# longer pattern list without forcing this one to match. What it should NOT be
# is two hand-maintained copies of the same subset, which is what it was.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_check_staleness() {
  local root hero_time config_time
  root="${1:-$(hero_root)}"
  [ -r "$root/HERO.md" ] || return 0
  hero_time=$(git -C "$root" log -1 --format=%ct -- HERO.md 2>/dev/null | grep -E '^[0-9]+$' || echo 0)
  config_time=$(git -C "$root" log -1 --format=%ct -- \
    pyproject.toml ':(glob)**/pyproject.toml' \
    package.json ':(glob)**/package.json' \
    go.mod ':(glob)**/go.mod' \
    Cargo.toml ':(glob)**/Cargo.toml' \
    .github/workflows .pre-commit-config.yaml \
    CLAUDE.md Makefile justfile Taskfile.yml 2>/dev/null | grep -E '^[0-9]+$' || echo 0)
  if [ "${config_time:-0}" -gt "${hero_time:-0}" ]; then
    echo "note: HERO.md may be out of date; run wayfare:wayfare-init-repo recalibrate to refresh." >&2
  fi
  return 0
}

# ---------- fleet ----------------------------------------------------------
#
# A fleet is a folder of sibling checkouts with a FLEET.md at its top:
# operator's local map of the repos they work across. It is unversioned and
# never inside a repo; docs/FLEET-MD.md is the standard.
#
# Every function here defaults to $PWD, not hero_root: a fleet folder is by
# definition not a repo root, and under a dotfiles-managed $HOME hero_root is
# $HOME, which would hide every fleet beneath it.

# Nearest ancestor (inclusive) of START holding FLEET.md, or return 1. A
# directory holding HERO.md beside it is a repo that committed a FLEET.md:
# repo content, not the operator's map, so it is passed over (stderr note)
# and the walk continues upward.
# shellcheck disable=SC2120  # in-file callers take the default; the tests pass START
hero_fleet_root() { # [START]
  local d
  d=$(cd "${1:-$PWD}" && pwd -P) || return 1
  # Parameter expansion, not $(dirname): a subshell per level, and a dirname
  # that returns empty (stripped PATH) would leave `d` unchanged and spin.
  while [ -n "$d" ]; do
    if [ -f "$d/FLEET.md" ]; then
      if [ -f "$d/HERO.md" ]; then
        echo "hero_fleet_root: passing over $d; FLEET.md beside HERO.md is a repo, not a fleet" >&2
      else
        printf '%s' "$d"; return 0
      fi
    fi
    [ "$d" = "/" ] && return 1
    d=${d%/*}; d=${d:-/}
  done
  return 1
}

# True when DIR (default $PWD) is a fleet folder rather than a repo: it holds
# FLEET.md and no HERO.md. Skills test this in Step 0 and hand off to "At the
# fleet root" in docs/FLEET-MD.md instead of treating the folder as a project.
hero_at_fleet_root() { # [DIR]
  local d
  d="${1:-$PWD}"
  [ -f "$d/FLEET.md" ] && [ ! -f "$d/HERO.md" ]
}

# A fleet-level `- key: value` from the `## Fleet` section.
#   hero_fleet_field name
hero_fleet_field() { # KEY [FLEET_ROOT]
  local root
  root="${2:-$(hero_fleet_root)}" || return 1
  hero_md_field "$root/FLEET.md" "$1" "## Fleet"
}

# One `- key: value` from a repo's `### NAME` block under `## Repos`.
#   hero_fleet_repo_field auth port
hero_fleet_repo_field() { # NAME KEY [FLEET_ROOT]
  local root
  root="${3:-$(hero_fleet_root)}" || return 1
  hero_md_field "$root/FLEET.md" "$2" "### $1" "## Repos"
}

# Every repo listed under `## Repos`, one per line:
# NAME<TAB>PATH<TAB>GROUP<TAB>PORT. One awk pass, not a loop over
# hero_fleet_repo_field: that re-parses FLEET.md three times per row.
# PATH is absolute and physical when the directory exists (a relative `path:`
# resolves against the fleet root and defaults to ./NAME); GROUP is lowercased
# and defaults to `none`, which means "lives here, not fleet"; PORT is digits
# or empty when unclaimed. Columns 2 and 3 are never empty, so a caller's
# `IFS=$'\t' read` is safe. Do not add an optional column before PORT.
#
# A row that cannot be trusted is SKIPPED, not defaulted: a leading `-` or a
# control character in a value, a non-numeric port, a name that is not
# [A-Za-z0-9._-] or is `.`/`..`, a path resolving outside the fleet, or a
# duplicate name. Substituting a default path would point the caller's `cd` at
# a different directory than the one the row names. Each skip is one stderr
# line `hero_fleet_repos: skipping 'NAME' — REASON` (fleet-scan.sh reads
# them back as BAD_ROW), and the function returns 3 when any row was skipped.
#
# Locals are rpath/rgroup/rport, never `path`: sourced from zsh, `local path`
# empties the PATH-tied array and awk becomes "command not found", leaving an empty
# registry with rc 0.
hero_fleet_repos() { # [FLEET_ROOT]
  local root
  root="${1:-$(hero_fleet_root)}" || return 1
  [ -r "$root/FLEET.md" ] || { echo "hero_fleet_repos: cannot read $root/FLEET.md" >&2; return 1; }
  awk '
    # \034 (file separator), not a tab: `read` with a whitespace IFS collapses
    # consecutive tabs, so an empty path would shift group into its column.
    function flush() { if (name != "") printf "%s\034%s\034%s\034%s\n", name, rpath, rgroup, rport; name = "" }
    /^```/ { fence = !fence; next }
    fence  { next }
    /^## /  { flush(); sec = $0; sub(/[[:space:]]+$/, "", sec); next }
    sec == "## Repos" && /^### / {
      flush(); name = $0; sub(/^### +/, "", name); sub(/[[:space:]]+$/, "", name)
      rpath = ""; rgroup = ""; rport = ""; next
    }
    name != "" && /^- (path|group|port):/ {
      k = $0; sub(/^- /, "", k); sub(/:.*/, "", k)
      v = $0; sub(/^[^:]*: */, "", v); sub(/ *#.*/, "", v); gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      if (k == "path") rpath = v; else if (k == "group") rgroup = v; else rport = v
    }
    END { flush() }
  ' "$root/FLEET.md" | {
    local name rpath rgroup rport v reason seen nbad real
    seen=" "; nbad=0
    while IFS=$'\034' read -r name rpath rgroup rport; do
      reason=""
      case "$name" in
        .|..|''|*[!A-Za-z0-9._-]*) reason="a repo name is [A-Za-z0-9._-] only, not '$name'" ;;
      esac
      [ -n "$reason" ] || case "$seen" in *" $name "*) reason="duplicate row" ;; esac
      rpath=${rpath#[\"\']}; rpath=${rpath%[\"\']}
      rgroup=${rgroup#[\"\']}; rgroup=${rgroup%[\"\']}
      rport=${rport#[\"\']}; rport=${rport%[\"\']}
      for v in "$rpath" "$rgroup" "$rport"; do
        [ -n "$reason" ] || case "$v" in -*|*[[:cntrl:]]*) reason="a value starts with '-' or holds a control character" ;; esac
      done
      [ -n "$reason" ] || case "$rport" in *[!0-9]*) reason="port is not a number: $rport" ;; esac
      if [ -n "$reason" ]; then
        echo "hero_fleet_repos: skipping '$name': $reason" >&2
        nbad=$((nbad + 1)); continue
      fi
      seen="$seen$name "
      rgroup=$(printf '%s' "${rgroup:-none}" | tr '[:upper:]' '[:lower:]')
      [ -n "$rpath" ] || rpath="./$name"
      rpath=${rpath%/}
      case "$rpath" in /*) ;; *) rpath="$root/${rpath#./}" ;; esac
      if [ -d "$rpath" ]; then
        real=$(cd "$rpath" && pwd -P)
        case "$real" in "$root"/*) rpath=$real ;; *)
          echo "hero_fleet_repos: skipping '$name': path resolves outside the fleet: $real" >&2
          nbad=$((nbad + 1)); continue ;;
        esac
      fi
      printf '%s\t%s\t%s\t%s\n' "$name" "$rpath" "$rgroup" "$rport"
    done
    [ "$nbad" -eq 0 ] || return 3
  }
}

# Host port a checkout's dev compose file publishes: digits, `-` when there is
# no compose file, `?` when there is one but no host port could be read (the
# two are different findings: "not implemented" versus "unreadable"). Reads BOTH
# spellings, skips commented-out lines, and reads `HOST_PORT:-N`, a literal
# `[HOST:]PUBLISHED:CONTAINER` mapping, or long-syntax `published:`. An
# earlier fleet reconcile grepped only `HOST_PORT` in `.yaml` and silently
# reported two live repos as claiming no port at all. A multi-service file
# publishes several ports (the database's first, typically); with RANGE
# (`33000-33099`) the one inside it wins, else the first literal.
hero_compose_port() { # DIR [RANGE]
  local f ports lo hi p
  for f in docker-compose.dev.yaml docker-compose.dev.yml docker-compose.yaml docker-compose.yml compose.yaml compose.yml; do
    [ -r "$1/$f" ] || continue
    ports=$(sed -nE '/^[[:space:]]*#/d; s/.*HOST_PORT:-([0-9]+).*/\1/p' "$1/$f" | head -1)
    [ -n "$ports" ] || ports=$(sed -nE '/^[[:space:]]*#/d
      s/^[[:space:]]*-[[:space:]]*"?(([0-9.]+|\[[0-9a-fA-F:]+\]):)?([0-9]{2,5}):[0-9]{2,5}"?.*/\3/p
      s/^[[:space:]]*published:[[:space:]]*"?([0-9]{2,5})"?.*/\1/p' "$1/$f")
    [ -n "$ports" ] || { printf '?'; return 0; }
    if [ -n "${2:-}" ]; then
      lo=${2%-*}; hi=${2#*-}
      for p in $ports; do
        [ "$p" -ge "$lo" ] 2>/dev/null && [ "$p" -le "$hi" ] 2>/dev/null && { printf '%s' "$p"; return 0; }
      done
    fi
    printf '%s' "${ports%%
*}"
    return 0
  done
  printf -- '-'
}

# ---------- concurrent work --------------------------------------------------
#
# Several features build at once, with worktree subagents here and other people
# elsewhere, so a PR's head is routinely behind the default branch by the time
# it is reviewed, approved, or merged. A gate that judged a stale head judged
# code that is not what will merge. Every skill that reviews, approves, or
# merges rebases first, through this one function.

# Rebase the current branch onto a freshly fetched origin/BASE and push it
# with --force-with-lease. Prints one line on stderr saying what happened.
#
# Returns: 0 already up to date, or rebased and pushed;
#          1 the rebase conflicts. It is ABORTED, the branch is unchanged, and
#            the conflicting files are listed on stderr for the caller to STOP on;
#          2 cannot proceed: dirty tree, detached HEAD, on the base itself, a
#            fetch failure, or a push the lease refused (someone else pushed,
#            fetch and re-run; never retry without the lease).
#
# Branch protection dismisses approvals on push, so a caller that has already
# collected an approval must re-trigger it after a rebase, so rebase BEFORE the
# approval, and only re-check (not re-rebase) between approval and merge.
hero_rebase_on_base() { # BASE
  local base branch behind conflicts
  base="$1"
  hero_is_valid_branch "$base" || { echo "hero_rebase_on_base: not a branch name: '$base'" >&2; return 2; }
  branch=$(git branch --show-current)
  [ -n "$branch" ] || { echo "hero_rebase_on_base: detached HEAD; check out the PR branch first" >&2; return 2; }
  [ "$branch" != "$base" ] || { echo "hero_rebase_on_base: on $base itself, nothing to rebase" >&2; return 2; }
  if [ -n "$(git status --porcelain)" ]; then
    echo "hero_rebase_on_base: working tree is dirty; commit or discard first:" >&2
    git status --short >&2
    return 2
  fi
  git fetch -q origin "$base" || { echo "hero_rebase_on_base: git fetch origin $base failed" >&2; return 2; }
  behind=$(git rev-list --count "HEAD..origin/$base")
  if [ "$behind" -eq 0 ]; then
    echo "hero_rebase_on_base: $branch is up to date with origin/$base" >&2
    return 0
  fi
  if ! git rebase -q "origin/$base" >/dev/null 2>&1; then
    conflicts=$(git diff --name-only --diff-filter=U)
    git rebase --abort
    echo "hero_rebase_on_base: rebasing $branch onto origin/$base conflicts, aborted, branch unchanged. Conflicting files:" >&2
    printf '  %s\n' $conflicts >&2
    return 1
  fi
  git push -q --force-with-lease origin "$branch" 2>/dev/null || {
    echo "hero_rebase_on_base: push refused by the lease: origin/$branch moved; fetch, inspect, re-run" >&2
    return 2
  }
  echo "hero_rebase_on_base: rebased $branch onto origin/$base ($behind commits behind) and pushed" >&2
}

# True when DIR (default $PWD) is a linked git worktree: its `.git` is a file
# pointing into the primary checkout. ship-pr uses this to skip the
# default-branch reset. The default branch is checked out in the primary, so
# `git checkout main` here fails, and the worktree is the caller's to remove.
hero_in_worktree() { # [DIR]
  local d
  d="${1:-$PWD}"
  [ -f "$d/.git" ] && grep -q '/worktrees/' "$d/.git" 2>/dev/null
}

# ---------- repo-local ignore ----------------------------------------------

# Path to .git/info/exclude, resolved through git so worktrees, bare repos,
# and non-default gitdirs all work. We use info/exclude rather than .gitignore
# so adding an ignore never dirties a tracked file.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_exclude_path() {
  local root exclude
  root="${1:-$(hero_root)}"
  exclude=$(git -C "$root" rev-parse --git-path info/exclude 2>/dev/null) || return 1
  case "$exclude" in
    /*) ;;
    *)  exclude="$root/$exclude" ;;
  esac
  printf '%s' "$exclude"
}

# Idempotently add one or more entries to .git/info/exclude.
#   hero_exclude_add .plans/ .test-output/
#
# Fails PER ENTRY, not per call: returning only the last iteration's status
# meant a failed append for entry 1 was swallowed when entry 2 succeeded,
# the store stayed un-ignored with nothing programmatically detectable.
hero_exclude_add() {
  local exclude entry rc
  exclude=$(hero_exclude_path) || {
    echo "hero_exclude_add: not a git repo" >&2
    return 1
  }
  mkdir -p "$(dirname "$exclude")" || {
    echo "hero_exclude_add: cannot create $(dirname "$exclude")" >&2
    return 1
  }
  rc=0
  for entry in "$@"; do
    grep -qxF "$entry" "$exclude" 2>/dev/null && continue
    printf '\n%s\n' "$entry" >> "$exclude" 2>/dev/null || {
      echo "hero_exclude_add: cannot append '$entry' to $exclude" >&2
      rc=1
    }
  done
  return "$rc"
}

# ---------- PR review markers ----------------------------------------------

# The literal lives in three places that cannot share a variable: review-pr
# (which stamps it into the comment), auto-approve.yaml (the fleet's
# prior-review gate, two sites), and here (ship-pr, wayfare-build-task, resume-state).
# Change all three together or the gate stops recognizing every self-review.
HERO_SELF_REVIEW_MARKER='ai-hero:self-review'
# The improvements comment's own marker. A word match on "improvements" was
# satisfied by the findings comment's own suggestions, which made the two
# halves one comment; the heading is rewritten by the humanizer. Only a
# hidden marker is both exact and invisible to that pass.
# A heading, not the words.
# A review OF this gate quotes the strings the gate matches on, so an unanchored pattern read this PR's own findings comment as the fixes comment and collapsed findings to zero.
# Prose is unreliable exactly where it discusses the mechanism.
HERO_SELF_REVIEW_FIXES_MARKER='ai-hero:self-review-fixes|(^|\\n)#+[ \t]*self-review[^\\n]*improvements'

# Count of self-review comments on a PR, posted by the authenticated account.
# The author filter is the whole point: the marker is a plain string anyone
# can post, and without the filter a stranger's comment on a public repo lets
# an unattended goal turn resume past self-review. Prints nothing and returns
# non-zero when either API call fails, so callers must branch on the rc, since
# an empty count read as a number is zero, the value that means "no review".
hero_self_review_count() { # PR_NUMBER
  local me
  me=$(gh api user --jq .login) || return 1
  gh api --paginate "/repos/{owner}/{repo}/issues/$1/comments?per_page=100" \
    --jq "[.[] | select(.user.login == \"$me\") | select(.body | test(\"$HERO_SELF_REVIEW_MARKER\")) | select(.body | test(\"$HERO_SELF_REVIEW_FIXES_MARKER\"; \"i\") | not)] | length"
}

# The improvements half of the same review: the marker-carrying comment that
# records what was done about the findings. review-pr posts it even when it
# fixed nothing, so its absence means the review stopped half way rather than
# that there was nothing to fix. The shared auto-approve workflow's
# prior-review gate requires BOTH halves; a local check that asks only for
# the findings comment passes here and is then rejected there, which spends a
# workflow run to learn what this function can say for free. Matched on the
# word, not the heading, because the body is humanized before it is posted.
hero_self_review_fixes_count() { # PR_NUMBER
  local me
  me=$(gh api user --jq .login) || return 1
  gh api --paginate "/repos/{owner}/{repo}/issues/$1/comments?per_page=100" \
    --jq "[.[] | select(.user.login == \"$me\") | select(.body | test(\"$HERO_SELF_REVIEW_FIXES_MARKER\"; \"i\"))] | length"
}

# ---------- the .plans store ------------------------------------------------

# Path of the store without creating it: read-only callers must not mkdir or
# touch .git/info/exclude.
# A worktree shares the repo's items: resolve the store under the primary
# checkout, or a worktree gets an empty private store and a build launched
# there plans from nothing. Read the worktree's `.git` FILE rather than
# asking git: a caller with GIT_DIR exported (pre-commit hooks do) would get
# the answer for a different repo.
hero_store_path() { # [ROOT]
  local root gitdir
  root="${1:-$(hero_root)}"
  if [ -f "$root/.git" ]; then
    gitdir=$(sed -n 's/^gitdir: //p' "$root/.git")
    case "$gitdir" in */.git/worktrees/*) root=${gitdir%/.git/worktrees/*} ;; esac
  fi
  printf '%s' "$root/.plans"
}

# Absolute path to the work-item store, created and git-ignored on first use.
# A dot-directory: tool-private state, like `.beads/`. It keeps the repo root
# clean and is far less likely to collide with a real project directory.
#
# One-time migration: the store was formerly `my-work/`, and before that
# `plan-work/`. Move a legacy store rather than orphaning its items behind
# the new name.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_work_store() {
  local root store legacy
  store=$(hero_store_path "${1:-}")
  root=${store%/.plans}

  # Establish we can actually ignore the store BEFORE creating or migrating
  # anything. Doing it after meant a non-git directory got a store created and
  # left un-ignored, with the function still returning 0. Check, and later
  # write, against $root rather than the cwd: with an explicit root argument, the
  # cwd may be a DIFFERENT repo, and the guard passing on the wrong repo
  # created an un-ignored store in $root while polluting the cwd's excludes.
  hero_exclude_path "$root" >/dev/null || {
    echo "hero_work_store: '$root' is not a git repo; refusing to create an un-ignorable store" >&2
    return 1
  }

  # A store that is a symlink redirects every later work-item write outside
  # the checkout, into a directory the agent itself reads back. Refuse.
  if [ -L "$store" ]; then
    echo "hero_work_store: refusing to use '$store'; it is a symlink" >&2
    return 1
  fi
  for legacy in my-work plan-work; do
    # `[ -d ]` is true for a symlink to a directory, and `mv` renames the
    # LINK: a repo that commits `my-work -> ../../../.claude` (git preserves
    # symlinks on clone) would silently become `.plans -> ../../../.claude`.
    # Refuse rather than migrate, but only when a migration would actually
    # happen; a stale legacy symlink next to a healthy `.plans/` must not
    # brick the store forever.
    if [ -L "$root/$legacy" ]; then
      if [ ! -e "$store" ]; then
        echo "hero_work_store: refusing to migrate '$root/$legacy'; it is a symlink" >&2
        return 1
      fi
      echo "hero_work_store: ignoring legacy '$root/$legacy'; it is a symlink" >&2
      continue
    fi
    if [ -d "$root/$legacy" ] && [ ! -e "$store" ]; then
      mv "$root/$legacy" "$store" || {
        echo "hero_work_store: cannot migrate '$root/$legacy' to '$store'" >&2
        return 1
      }
      echo "Migrated legacy $legacy/ store to .plans/." >&2
    fi
    if [ -d "$root/$legacy" ] && [ -d "$store" ]; then
      echo "hero_work_store: both $legacy/ and .plans/ exist; items in $legacy/ are NOT migrated and will be invisible. Merge them by hand." >&2
    fi
    # Keep the legacy name excluded through the transition so a not-yet-migrated
    # legacy store is never accidentally committed either. The subshell cd
    # targets $root's excludes even when the caller's cwd is another repo.
    ( cd "$root" && hero_exclude_add "$legacy/" ) || return 1
  done
  mkdir -p "$store" || {
    echo "hero_work_store: cannot create '$store'" >&2
    return 1
  }
  ( cd "$root" && hero_exclude_add .plans/ ) || return 1
  printf '%s' "$store"
}

# Read a frontmatter scalar from a work-item.
#
# Bounded to the frontmatter block between the first two `---` fences: without
# that, a `status: done` line appearing in the BODY (acceptance criteria, a
# pasted log) was read as the item's status.
#
# Splits on the FIRST colon only and strips surrounding quotes. Splitting on
# every ': ' truncated any value containing a colon; not stripping quotes made
# `status: "done"` fail to equal `done`, which silently blocked every dependent
# forever. hero_field already strips quotes, so the two readers in this file must
# agree on the same syntax.
#
# A quoted value is taken whole, and an unquoted one loses a comment only at a
# `#` that opens the value or follows whitespace, as YAML reads it. Stripping
# from any `#` turned `blocked_on: "#42 upstream"` into an empty value, and an
# empty `blocked_on` lists the item READY.
hero_item_field() {
  awk -v k="$2" '
    /^---[[:space:]]*$/ { fence++; if (fence >= 2) exit; next }
    fence != 1 { next }
    index($0, k ":") == 1 {
      v = $0; sub(/^[^:]*: */, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      q = substr(v, 1, 1)
      e = (q == "\"" || q == "'"'"'") ? index(substr(v, 2), q) : 0
      if (e > 0) {
        v = substr(v, 2, e - 1)
      } else {
        if (substr(v, 1, 1) == "#") v = ""
        sub(/[[:space:]]+#.*/, "", v)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
        gsub(/^["'"'"']|["'"'"']$/, "", v)
      }
      print v
      exit
    }
  ' "$1"
}

# Print a frontmatter line's text after the colon, trimmed and otherwise
# unparsed, so a reader can tell a value the parser emptied from one never
# written. Callers warn only on `#` then a non-space (`#42`): `# note` is the
# comment the PLAN.md template itself writes after an empty field.
hero_item_field_raw() {
  awk -v k="$2" '
    /^---[[:space:]]*$/ { fence++; if (fence >= 2) exit; next }
    fence != 1 { next }
    index($0, k ":") == 1 {
      v = $0; sub(/^[^:]*:/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      print v
      exit
    }
  ' "$1"
}

# Print an item's depends_on ids, one per line.
hero_item_deps() { hero_item_list_field "$1" depends_on; }


# Print a frontmatter list field's entries, one per line.
#
# Handles BOTH YAML forms. Only the inline form was parsed before, so a block
# sequence like:
#
#   depends_on:
#     - 99
#
# yielded an empty value, the readiness loop never ran, and the item was
# reported READY despite depending on work that does not exist. Silently: there
# was no `d` for the readiness loop's existence check to flag as missing.
hero_item_list_field() {
  awk -v k="$2" '
    /^---[[:space:]]*$/ { fence++; if (fence >= 2) exit; next }
    fence != 1 { next }
    index($0, k ":") == 1 {
      v = $0; sub(/^[^:]*: */, "", v); sub(/ *#.*/, "", v)
      gsub(/[][,]/, " ", v)
      n = split(v, parts, /[[:space:]]+/)
      # Strip surrounding quotes per entry, mirroring the block branch below,
      # quoting is handled here, in the parser, not by the id normalizer.
      for (i = 1; i <= n; i++) {
        p = parts[i]
        gsub(/^["'"'"']|["'"'"']$/, "", p)
        if (p != "") print p
      }
      block = 1
      next
    }
    # A block sequence continues while lines are indented `- item` entries.
    block && /^[[:space:]]+-[[:space:]]*/ {
      v = $0; sub(/^[[:space:]]*-[[:space:]]*/, "", v); sub(/ *#.*/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      gsub(/^["'"'"']|["'"'"']$/, "", v)
      if (v != "") print v
      next
    }
    { block = 0 }
  ' "$1"
}

# Normalize a work-item status: lowercase, empty defaults to `new`.
# `Done` silently not matching `done` left every dependent blocked forever.
# The default is `new`, never a READY-eligible state: a status-less item must
# land as untriaged, not on the READY tier.
hero_item_status() {
  local s
  s=$(hero_item_field "$1" status | tr '[:upper:]' '[:lower:]')
  printf '%s' "${s:-new}"
}

# An item's TYPE (the enum is in docs/PLAN.md). Lowercased, because
# `Task` silently matching no arm of the listing table printed the item as
# invalid, which reads as a malformed file rather than a capital letter.
# Empty means the item was never migrated; the caller reports it, because
# guessing a type here is how a `goal` gets handed to wayfare-build-task as a task.
hero_item_type() {
  hero_item_field "$1" type | tr '[:upper:]' '[:lower:]'
}

# A task's SHAPE: story, structural, visual, defect, dependency or docs. Decides
# what the Definition of Done must assert, never whether the item is READY,
# so nothing in the listing reads it.
hero_item_shape() {
  hero_item_field "$1" shape | tr '[:upper:]' '[:lower:]'
}

# An item's PRIORITY: p0 to p3, lowercased like the other accessors so `P1`
# ranks as p1. Empty means unranked.
hero_item_priority() {
  hero_item_field "$1" priority | tr '[:upper:]' '[:lower:]'
}

# A signal's CHANNEL: design, design-system or architecture. Decides where
# the delivery procedure sends it, never whether it lists.
hero_item_channel() {
  hero_item_field "$1" channel | tr '[:upper:]' '[:lower:]'
}

# Read a field from the plan object's frontmatter (`.plans/PLAN.md`). A dotted
# KEY (`source.head`, `target.project`) reads one level into a block; a bare
# KEY that names a block prints nothing, so `hero_plan_field source` is NOT a
# way to read the head — it was, silently, the reason a drift scan saw no
# previous head on every run.
hero_plan_field() { # KEY [STORE]
  local store
  store="${2:-$(hero_store_path)}"
  [ -f "$store/PLAN.md" ] || return 1
  case "$1" in
    *.*)
      awk -v blk="${1%%.*}" -v key="${1#*.}" '
        /^---[[:space:]]*$/ { if (++fence == 2) exit; next }
        fence == 1 && index($0, blk ":") == 1 { inblk = 1; next }
        fence == 1 && inblk && $0 ~ /^[^[:space:]]/ { inblk = 0 }
        fence == 1 && inblk && index($0, "  " key ":") == 1 {
          v = $0; sub(/^[[:space:]]*[^:]+:[[:space:]]*/, "", v); sub(/[[:space:]]*#.*/, "", v)
          printf "%s", v; exit
        }' "$store/PLAN.md" ;;
    *) hero_item_field "$store/PLAN.md" "$1" ;;
  esac
}

# Absolute path to the item directory. Items live in `.plans/items/`, not
# beside PLAN.md: the listing globs `*.md`, so a plan file in that directory
# lists as a malformed item.
# shellcheck disable=SC2120  # optional arg; callers usually rely on the default
hero_items_dir() { # [ROOT]
  printf '%s' "$(hero_store_path "${1:-}")/items"
}

# How many ideas are parked, i.e. at `new` or `accepted`.
#
# The roadmap view prints this as one line ("7 ideas parked") instead of one
# row per idea: a parking lot is meant to grow, and forty rows of it between
# a reader and the READY set is how the actionable rows stop being read.
# The listing itself still emits an `idea` row per item, because a caller
# parsing rows must see every item; the collapsing is presentation.
hero_idea_count() { # [STORE]
  local items f n=0
  items="${1:-$(hero_store_path)}/items"
  [ -d "$items" ] || { printf 0; return 0; }
  ( cd "$items" 2>/dev/null || { printf 0; exit 0; }
    setopt localoptions nullglob 2>/dev/null || true
    for f in *.md; do
      [ -e "$f" ] || continue
      [ "$(hero_item_type "$f")" = idea ] || continue
      case "$(hero_item_status "$f")" in new|accepted) n=$((n + 1)) ;; esac
    done
    printf '%s' "$n" )
}

# Print the ids of a goal's members, ordered by `rank` then id, one per line.
# `depends_on` is not consulted: it gates each member's readiness in the
# listing, and a rank that contradicts it is a store defect `wayfare-sync-plan`
# reports. The second argument is the STORE, like every sibling here.
#
# Derived from each item's `parent`, never stored on the goal. The old schema
# kept the same edge twice (`covers` on the goal AND the members' own order),
# so the two could disagree and a sync had to reconcile them every round;
# worse, two goals could name one item and each pre-authorize merges on it.
# With one edge in one direction that is not representable.
#
# An empty GOAL_ID is refused: it would match every item with no `parent`,
# and a goal turn reading that as "my members" would start building orphans.
hero_goal_members() { # GOAL_ID [STORE]
  local items f id parent rank
  [ -n "$1" ] || { echo "hero_goal_members: empty GOAL_ID" >&2; return 2; }
  items="${2:-$(hero_store_path)}/items"
  [ -d "$items" ] || return 1
  ( cd "$items" 2>/dev/null || return 1
    setopt localoptions nullglob 2>/dev/null || true
    for f in *.md; do
      [ -e "$f" ] || continue
      parent=$(hero_norm_id "$(hero_item_field "$f" parent)")
      [ "$parent" = "$(hero_norm_id "$1")" ] || continue
      id=$(hero_norm_id "$(hero_item_field "$f" id)")
      [ -n "$id" ] || continue
      rank=$(hero_item_field "$f" rank)
      case "$rank" in ''|*[!0-9]*) rank=9999 ;; esac
      printf '%s %s\n' "$rank" "$id"
    done | sort -n -k1,1 -k2,2 | awk '{ print $2 }'
  )
}

# Messages in a store's mailbox (docs/MESSAGES.md) by state. With no second
# argument, UNREAD: inbox/*.md whose `status:` is `new`, absent (the default
# for a missing line, as for items), or any word outside the enum. An
# unrecognized status must count as unread, not as settled, or a sender's
# typo hides a message. `claimed` counts messages a session took and never
# released; the standard's takeover rule needs that number visible. A store
# with no inbox/ is 0; an `inbox` that is a file, not a directory, is a
# defect named on stderr, since a deposit into it would fail.
hero_inbox_count() { # STORE [claimed]
  local n=0 f st
  if [ -e "$1/inbox" ] && [ ! -d "$1/inbox" ]; then
    echo "hero_inbox_count: $1/inbox is not a directory; no message can land here" >&2
  fi
  [ -d "$1/inbox" ] || { printf 0; return 0; }
  # zsh aborts on an unmatched glob; an EMPTY inbox is the normal state after
  # every message is settled and must read as 0, not as an error.
  setopt localoptions nullglob 2>/dev/null || true
  for f in "$1"/inbox/*.md; do
    [ -f "$f" ] || continue
    st=$(hero_item_field "$f" status | tr '[:upper:]' '[:lower:]')
    if [ "${2:-}" = claimed ]; then
      [ "$st" = claimed ] && n=$((n + 1))
    else
      case "$st" in claimed|answered|declined) ;; *) n=$((n + 1)) ;; esac
    fi
  done
  printf '%s' "$n"
}

# A suspended item's `awaiting:` ids, one per line, in both YAML forms:
# the same two-form trap hero_item_deps documents: the block form
# (`awaiting:` then indented `- id` lines) is what a careful author writes,
# and a single-line reader prints it as empty, which renders a wait as one
# with nothing to wait for.
hero_item_awaiting() { # ITEM_FILE
  awk '
    /^---[[:space:]]*$/ { fence++; if (fence >= 2) exit; next }
    fence != 1 { next }
    /^awaiting:/ {
      v = $0; sub(/^[^:]*: */, "", v); sub(/ *#.*/, "", v)
      gsub(/[][,]/, " ", v)
      n = split(v, parts, /[[:space:]]+/)
      for (i = 1; i <= n; i++) { p = parts[i]; gsub(/^["'"'"']|["'"'"']$/, "", p); if (p != "") print p }
      block = 1; next
    }
    block && /^[[:space:]]+-[[:space:]]*/ {
      v = $0; sub(/^[[:space:]]*-[[:space:]]*/, "", v); sub(/ *#.*/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); gsub(/^["'"'"']|["'"'"']$/, "", v)
      if (v != "") print v; next
    }
    block { block = 0 }
  ' "$1"
}

# A message id with real entropy (docs/MESSAGES.md). Hash-named, never
# numbered: `.plans/` ids are a sequential integer namespace, and a sender
# allocating an id inside the RECIPIENT's namespace races that repo's own
# allocation, which surfaces as a duplicate id and a silent mis-resolution,
# not a failure.
hero_msg_id() {
  local h
  h=$(od -An -N3 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')
  # A SHORT read is the trap, not an empty one: `m-ab` is non-empty, passes a
  # `[ -n ]` test, and collapses the collision space from 2^24 to 2^8 while
  # still looking like an id everywhere downstream.
  case "$h" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *) echo "hero_msg_id: no usable entropy (got '${h:-}')" >&2; return 1 ;;
  esac
  printf 'm-%s' "$h"
}

# True when ID has the documented shape, m- plus exactly six lowercase hex.
# Every place an id becomes a PATH must go through this: `m-*` alone admits
# `m-../../AGENTS`, and the deposit builds `inbox/$ID.md` from it.
hero_is_msg_id() { # ID
  case "$1" in
    m-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) return 0 ;;
    *) return 1 ;;
  esac
}

# Live messages in a store's inbox matching FROM and ABOUT, as paths, one per
# line. This is the dedupe probe every sender runs BEFORE depositing: the key
# is (from, about), never msg_id, which differs by construction, so a resumed
# sender that skips this re-sends and the recipient does the work twice.
#
# Returns 1 when nothing matches, so `if hero_msg_find ...` reads as "already
# sent"; 2 when the probe could not be run, which a caller must NOT read as
# "not sent yet".
#
# ABOUT is required and may not be empty. An absent `about:` reads as "" too,
# so an empty probe matches every about-less message from that sender, so two
# unrelated asks from one repo would dedupe against each other and the second
# would never be sent. A sender with no local item passes a subject token
# instead (docs/MESSAGES.md, Sending step 2).
hero_msg_find() { # STORE FROM ABOUT
  local f n=0 st exp today
  # rc 2, not 1: there is no mailbox to read, so this probe did not run. Read
  # as 1 ("not sent yet") the sender deposits into a store it has never been
  # able to check, which is the double-dispatch the probe exists to prevent.
  [ -d "$1/inbox" ] || { echo "hero_msg_find: no inbox at $1/inbox; probe did not run" >&2; return 2; }
  [ -n "${3:-}" ] || { echo "hero_msg_find: ABOUT is empty; an about-less probe matches every about-less message; pass a subject token" >&2; return 2; }
  today=$(date +%Y%m%d)
  setopt localoptions nullglob 2>/dev/null || true
  for f in "$1"/inbox/*.md; do
    [ -f "$f" ] || continue
    if [ ! -r "$f" ]; then
      # Skipping in silence would return "not sent yet" and send a duplicate,
      # the exact double-dispatch this probe exists to prevent.
      echo "hero_msg_find: cannot read $f; probe is incomplete" >&2
      continue
    fi
    [ "$(hero_item_field "$f" from)" = "$2" ] || continue
    [ "$(hero_item_field "$f" about)" = "$3" ] || continue
    st=$(hero_item_field "$f" status | tr '[:upper:]' '[:lower:]')
    # Liveness is the CLOSED enum, not "anything not settled". A typo'd or
    # missing status read as live would match forever and the sender could
    # never raise the subject again.
    case "$st" in
      new|claimed) ;;
      answered|declined) continue ;;
      *) echo "hero_msg_find: $f has status '${st:-<absent>}', outside the enum, not counted as live" >&2; continue ;;
    esac
    # An awaited message whose expiry has passed is settled by lapse: the
    # recipient never answered and the sender has already resumed, so holding
    # the subject closed on it hangs the conversation forever.
    # Compared as digits, not with `[ a \< b ]`: bash's test reads `<` as a
    # string comparison and zsh's reads it as a numeric one, so the string
    # form silently stops detecting expiry under the shell half this fleet
    # runs on.
    exp=$(hero_item_field "$f" expires | tr -d -)
    case "$exp" in
      '') ;;
      *[!0-9]*) echo "hero_msg_find: $f has an unparsable expires, treated as live" >&2 ;;
      *) if [ "$exp" -lt "$today" ]; then
           echo "hero_msg_find: $f expired, not counted as live" >&2
           continue
         fi ;;
    esac
    echo "$f"; n=$((n + 1))
  done
  [ "$n" -gt 0 ]
}

# Deposit a message file into a target store's inbox, atomically. BODY_FILE is
# the fully-written message; the deposited path goes to stdout.
#
# Atomicity is the whole reason this is a function: a recipient globbing
# inbox/*.md can read a file mid-write, so the content is written to a temp
# name IN THE SAME DIRECTORY and `mv`d into place. Rename is atomic on one
# filesystem, a direct write is not, and a torn read of a message is a request
# acted on in half.
#
# It refuses when `inbox/` is absent. A checkout with no mailbox has no agent
# workflow to read a message, and materializing one inside someone else's
# checkout is the second kind of write the standard bans.
#
# It is also the one chokepoint every sender passes through, so the checks the
# format documents but nothing else enforces live here: the id's shape, the
# body's `msg_id` agreeing with the filename every glob-based reader keys on,
# and `status` inside its enum.
hero_msg_deposit() { # TARGET_STORE MSG_ID BODY_FILE
  local dest tmp st body_id rc
  [ -r "$3" ] || { echo "hero_msg_deposit: cannot read $3" >&2; return 1; }
  hero_is_msg_id "$2" || { echo "hero_msg_deposit: '$2' is not a message id (m- plus six lowercase hex)" >&2; return 1; }
  body_id=$(hero_item_field "$3" msg_id)
  [ "$body_id" = "$2" ] || { echo "hero_msg_deposit: body msg_id '${body_id:-<absent>}' disagrees with '$2'; readers key on the filename, repliers on the body" >&2; return 1; }
  st=$(hero_item_field "$3" status | tr '[:upper:]' '[:lower:]')
  case "$st" in
    new|claimed|answered|declined) ;;
    *) echo "hero_msg_deposit: status '${st:-<absent>}' is outside the enum; the recipient's unread count cannot classify it" >&2; return 1 ;;
  esac
  [ -d "$1/inbox" ] || { echo "hero_msg_deposit: $1/inbox does not exist; the target has no mailbox; report it, do not create one" >&2; return 1; }
  dest="$1/inbox/$2.md"
  # `[ -e ] && { ...; }` would leave the happy path returning 1 under `set -e`.
  if [ -e "$dest" ]; then
    echo "hero_msg_deposit: $dest already exists; allocate a new id rather than overwrite a message" >&2
    return 1
  fi
  tmp="$1/inbox/.$2.$$.tmp"
  cat "$3" > "$tmp"; rc=$?
  if [ "$rc" -ne 0 ]; then
    rm -f "$tmp"
    echo "hero_msg_deposit: could not write $tmp (rc $rc); nothing was deposited" >&2
    return 1
  fi
  if ! mv "$tmp" "$dest"; then
    rm -f "$tmp"
    echo "hero_msg_deposit: could not move $tmp to $dest; nothing was deposited" >&2
    return 1
  fi
  printf '%s' "$dest"
}

# ---------- admission path scope -------------------------------------------

# True when PATH is inside one of the SCOPE paths (a goal turn's admission
# criterion 3, docs in references/goals.md *Admitting discovered work*).
#
# Mechanical on purpose. The other admission criteria are judgments an agent
# makes in the same context window as the content that suggested the work, and
# that content is untrusted, and a persuasive paragraph can produce an item that
# honestly seems to serve a DoD line. It cannot move the parent's declared
# paths, so this is the criterion that still holds when the judgment is the
# thing under attack. That only stays true if "within" is computed rather than
# argued, which is what this function is for.
#
# Containment is by path SEGMENT, never by string prefix: `src/app` must not
# contain `src/application`, which a bare `case "$p" in "$s"*)` would accept
# and which is a real directory-naming pattern, not a contrived one.
hero_path_within() { # PATH SCOPE [SCOPE...]
  local p="$1" s
  shift
  [ -n "$p" ] || return 1
  # `..` is refused outright rather than resolved: these are declared strings
  # from a git-excluded file, not paths on disk, so there is nothing to
  # canonicalize against and `a/../../etc` would otherwise "be within" `a`.
  case "$p" in *..*) return 1 ;; esac
  p="${p#./}"; p="${p%/}"
  for s in "$@"; do
    [ -n "$s" ] || continue
    case "$s" in *..*) continue ;; esac
    s="${s#./}"; s="${s%/}"
    [ "$p" = "$s" ] && return 0
    case "$p" in "$s"/*) return 0 ;; esac
  done
  return 1
}

# Paths no admission may touch, whatever DoD line is quoted: they widen what
# the NEXT goal may do without ever editing `## Permissions`. `.github/`
# carries the approval workflow this fleet calls at @main, `.claude/` is agent
# instructions, and HERO.md/FLEET.md name the gates themselves.
#
# Returns 0 when PATH is forbidden, so `if hero_path_forbidden "$p"` reads as
# "refuse it".
#
# A path this cannot judge is forbidden too: `..`, a bare `.`, an absolute
# path or a glob could each name one of these without spelling it. Matching is
# case-insensitive because macOS resolves `hero.md` and `.GitHub/` to the real
# files.
hero_path_forbidden() { # PATH
  local p
  p=$(printf '%s' "${1#./}" | tr '[:upper:]' '[:lower:]')
  case "$p" in
    ''|.|/*|*..*|*'*'*|*'?'*|*'['*) return 0 ;;
    .github|.github/*|.claude|.claude/*|hero.md|fleet.md) return 0 ;;
    */.github|*/.github/*|*/.claude|*/.claude/*|*/hero.md|*/fleet.md) return 0 ;;
  esac
  return 1
}

# ---------- deferred deploy checks ----------------------------------------

# A post-merge deploy check that could not be answered without waiting.
#
# ship-pr waits for the merge commit's runs, with a cap (Step 7e). What is
# still in flight when the cap expires is recorded here and probed by the
# next thing that runs in this repo, which pays no wait at all. Same shape
# as wayfare-build-task's await-review: cap the wait, then hand the enforcement to
# whatever runs next. The check is advisory and never un-merges anything,
# so the cap is a real bound, not a retry budget.
#
# One line per pending merge: SHA<TAB>PR<TAB>DATE.

# Serialize a read-modify-write on the list. `mkdir` is the portable atomic
# test-and-set; `flock` is absent on macOS. Separate runs share one list
# (hero_work_store resolves every worktree to the primary), and one can drain
# at Step 2a while another appends at Step 7e, so an unlocked rewrite silently
# drops whatever was appended between its read and its rename, which is a
# DEGRADED deploy nobody will ever see.
hero_pending_lock() { # FILE [TIMEOUT_S]
  local lock="$1.lock" waited=0 limit="${2:-10}" owner
  while ! mkdir "$lock" 2>/dev/null; do
    # A lock older than a minute outlived any legitimate holder. This guards
    # a grep and a rename, not a network call, and a crashed session must not
    # wedge every future drain.
    owner=$(find "$lock" -maxdepth 0 -mmin +1 2>/dev/null)
    [ -n "$owner" ] && { rm -rf "$lock"; continue; }
    [ "$waited" -ge "$limit" ] && { echo "hero_pending_lock: $lock held for ${limit}s, giving up" >&2; return 1; }
    sleep 1; waited=$((waited + 1))
  done
  return 0
}

hero_pending_unlock() { # FILE
  rm -rf "$1.lock"
}

# Queue a merge whose deploy probe was deferred. Appending a SHA already
# present is a no-op. A re-run of the same merge must not queue it twice.
hero_deploy_pending_add() { # STORE SHA PR
  local f="$1/.deploy-pending"
  [ -d "${1:-}" ] || { echo "hero_deploy_pending_add: no store at '${1:-}'" >&2; return 1; }
  # 40-hex, matching what the rest of the store means by a SHA. An abbreviated
  # sha would be added but never cleared, because hero_deploy_pending_clear matches
  # the full field, so the entry would be re-probed and re-reported forever.
  case "$2" in
    ????????????????????????????????????????) ;;
    *) echo "hero_deploy_pending_add: '$2' is not a 40-character commit sha" >&2; return 1 ;;
  esac
  case "$2" in *[!0-9a-f]*) echo "hero_deploy_pending_add: '$2' is not lowercase hex" >&2; return 1 ;; esac
  # The PR is what the drain names in its verdict. Blank is representable and,
  # because dedupe is on the SHA alone, permanent: a later add carrying the
  # number is a no-op.
  case "${3:-}" in
    '') echo "hero_deploy_pending_add: PR is required; the drain reports the verdict against it" >&2; return 1 ;;
    *[!0-9]*) echo "hero_deploy_pending_add: PR '$3' is not a number" >&2; return 1 ;;
  esac
  hero_pending_lock "$f" || return 1
  if [ -f "$f" ] && awk -F'\t' -v s="$2" '$1 == s { found = 1 } END { exit !found }' "$f"; then
    hero_pending_unlock "$f"; return 0
  fi
  # A file whose last line lost its newline would fuse with this one: the
  # fused line matches no sha, so both entries become unclearable.
  if [ -s "$f" ] && [ -n "$(tail -c 1 "$f")" ]; then printf '\n' >> "$f"; fi
  printf '%s\t%s\t%s\n' "$2" "$3" "$(date +%Y-%m-%d)" >> "$f"
  rc=$?
  hero_pending_unlock "$f"
  [ "$rc" -eq 0 ] || { echo "hero_deploy_pending_add: could not append to $f" >&2; return 1; }
}

# The pending merges, oldest first, as SHA<TAB>PR<TAB>DATE. rc 1 means nothing
# is waiting; rc 2 means the question could not be asked. Collapsing the two
# is how a repo with an unreadable list reports a clean slate forever.
hero_deploy_pending() { # STORE
  local f="$1/.deploy-pending"
  [ -d "${1:-}" ] || { echo "hero_deploy_pending: no store at '${1:-}'" >&2; return 2; }
  [ -s "$f" ] || return 1
  [ -r "$f" ] || { echo "hero_deploy_pending: $f exists but cannot be read" >&2; return 2; }
  cat "$f"
}

# Drop one sha from the list, once it has been probed and reported. Only call
# this after printing a verdict for SHA: clearing an entry the probe never
# answered is how a DEGRADED deploy disappears with no record.
hero_deploy_pending_clear() { # STORE SHA
  local f="$1/.deploy-pending" tmp rc
  [ -f "$f" ] || return 0
  # The destructive half validates what the additive half validates. `$2` is
  # interpolated into a BRE, so an unvalidated `.*` matches every line and the
  # whole queue goes.
  case "$2" in
    ????????????????????????????????????????) ;;
    *) echo "hero_deploy_pending_clear: '$2' is not a 40-character commit sha" >&2; return 1 ;;
  esac
  case "$2" in *[!0-9a-f]*) echo "hero_deploy_pending_clear: '$2' is not lowercase hex" >&2; return 1 ;; esac
  hero_pending_lock "$f" || return 1
  tmp="$f.$$.tmp"
  grep -v "^$2	" "$f" > "$tmp"; rc=$?
  # grep's rc 1 is "every line matched, nothing remains", the normal empty
  # case. rc 2+ is an ERROR, and treating it as "nothing remains" (or reading
  # a short write as one) unlinks a list of never-probed checks.
  if [ "$rc" -gt 1 ]; then
    rm -f "$tmp"; hero_pending_unlock "$f"
    echo "hero_deploy_pending_clear: cannot rewrite $f (grep rc $rc); $2 left pending" >&2
    return 1
  fi
  if ! mv "$tmp" "$f"; then
    rm -f "$tmp"; hero_pending_unlock "$f"
    echo "hero_deploy_pending_clear: cannot replace $f; $2 left pending" >&2
    return 1
  fi
  [ -s "$f" ] || rm -f "$f"
  hero_pending_unlock "$f"
}

# Repo-local skills that plug into wayfare: every .claude/skills/*/SKILL.md
# whose frontmatter carries `wayfare: HOOK`, as `name<TAB>hook<TAB>path`, one
# per line; HOOK filters to one hook. The three hooks are sync (a stage of
# `wayfare-sync-plan`), verify (a Definition-of-Done verifier) and recipe (a way to
# build that planning may name). Discovery, not configuration: a list of these
# in HERO.md would be a copy of the directory and would go stale.
hero_local_skills() { # ROOT [HOOK]
  local f name hook real seen
  seen=" "
  # zsh aborts on an unmatched glob, and most repos have no .claude/skills/,
  # that must be an empty listing with rc 0, not an error on every Step 0.
  setopt localoptions nullglob 2>/dev/null || true
  for f in "$1"/.claude/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    # A symlinked skill directory would list its target twice, and the local
    # stage runs what the listing says.
    real=$(cd "$(dirname "$f")" && pwd -P)
    case "$seen" in *" $real "*) continue ;; esac
    seen="$seen$real "
    hook=$(hero_item_field "$f" wayfare | tr '[:upper:]' '[:lower:]')
    [ -n "$hook" ] || continue
    name=$(hero_item_field "$f" name)
    case "$hook" in
      sync|verify|recipe) ;;
      *) echo "hero_local_skills: $f declares wayfare: '$hook', which is not sync|verify|recipe; skipped" >&2; continue ;;
    esac
    [ -z "${2:-}" ] || [ "$2" = "$hook" ] || continue
    printf '%s\t%s\t%s\n' "${name:-$(basename "$(dirname "$f")")}" "$hook" "$f"
  done
}

# Normalize a work-item id for comparison: all-digit ids (the standard form)
# drop leading zeros so `007` equals `7`; anything else lowercases and
# compares verbatim rather than aborting. The old `$((10#$id))` arithmetic
# was a FATAL error on any non-digit and silently blanked the whole listing.
# Quote-stripping is the frontmatter readers' job, not this function's.
hero_norm_id() {
  case "$1" in
    ''|*[!0-9]*) printf '%s' "$1" | tr '[:upper:]' '[:lower:]' ;;
    *) printf '%s' "$((10#$1))" ;;
  esac
}

# Reorder listing rows (`WORD FILE — TITLE` on stdin) by priority, then by the
# order they arrive in, which is filename and so id. Reads each row's file from
# the current directory. The sort must stay stable (-s): without it the tie
# between two p1 rows falls to comparing the whole line and id order is lost.
# Absent and unrecognized both rank 4, after p3.
hero_sort_rows_by_priority() {
  local row f key p
  while IFS= read -r row; do
    read -r _ f _ <<EOF
$row
EOF
    p=
    if [ -r "$f" ]; then
      p=$(hero_item_priority "$f")
    else
      echo "hero_sort_rows_by_priority: could not read $f for its priority; sorted as unranked" >&2
    fi
    case "$p" in
      p0) key=0 ;; p1) key=1 ;; p2) key=2 ;; p3) key=3 ;; *) key=4 ;;
    esac
    printf '%s\t%s\n' "$key" "$row"
  done | sort -s -t "$(printf '\t')" -k1,1n | cut -f2-
}

# Print one line per work-item:  STATE  file — title
# A blocked row whose dependency does not exist anywhere in the store gets a
# trailing ` [missing dep: ID…]` annotation, because that reference can NEVER be
# satisfied, which is different from ordinary waiting.
#
# STATE is one of:
#   READY    a task at `ready` whose every depends_on target is done
#   blocked  not done, but a dependency is unmet or unresolvable, or
#            `blocked_on:` names something outside the store (annotated
#            `[on: TEXT, since DATE]`). Never READY, never a satisfied dependency
#   backlog  a task at `accepted`: on the roadmap, not yet planned; annotated
#            `[deps unmet]` when a dependency isn't done. Never READY: handing
#            an unplanned task to wayfare-build-task would skip planning entirely
#   plan     status is planning: still being shaped; a HUMAN marks it ready
#   active   status is active: someone is already on it
#   review   a task at review: PR open, awaiting merge
#   committed a task committed on a goal's branch that has not merged. Never
#            READY and never a satisfied dependency, because the default
#            branch lacks the code; a dependent's row names it as
#            `[committed dep: ID…]` so a goal turn can tell "already on my
#            branch" from a real block
#   suspended `awaiting:` is non-empty: waiting on a sibling repo's reply
#            (docs/MESSAGES.md). Never READY and never a satisfied dependency
#   feedback a signal at accepted or ready: a divergence written but not yet
#            landed upstream. Never READY, because a signal is DELIVERED and
#            never built, so handing one to wayfare-build-task is wrong
#   goal     a goal at accepted: approved, waiting to run. Never READY: a goal
#            is a container for tasks, and wayfare-build-task builds tasks.
#            `wayfare-start-goal` selects goals by type instead
#   idea     an idea at new or accepted: parked, never work until promoted
#   anti     an anti-feature at new or accepted: a decision not to build, checked
#            against and never work
#   new      status is new (or absent): created, not yet triaged. Never READY,
#            because nobody has decided this should be worked on
#   done     finished; the only state that satisfies a dependency
#   dropped  abandoned; terminal, and does NOT satisfy a dependency
#   invalid  no usable id, no type, or an unrecognized status. Either way the
#            item cannot participate in dependency order and is never READY
#
# One enum for every type (docs/PLAN.md): new | accepted | planning | ready |
# active | committed | review | done | dropped. Which states a type visits is
# the type's business; the listing only refuses combinations that make no
# sense (a goal at ready, a signal at committed) as invalid.
#
# `done` rows are PRINTED, not hidden. Callers need to see them: wayfare-build-task's
# Step 1c resolves an argument against this listing to answer "has this already
# landed?", and handoff reads it to update an existing item rather than
# duplicating it. Filtering them out silently defeated both.
#
# `active` is separated from READY so two sessions cannot both pick up the same
# in-flight item: wayfare-build-task marks an item active before its first edit
# specifically to prevent that, and folding it into READY undid it.
#
# `planning` is never READY regardless of dependencies: the item is still being
# shaped and awaits a human ready-mark. Without this state, freshly emitted
# items were handed straight to wayfare-build-task. Wayfare writes tasks as `accepted`,
# which is backlog, and still never READY.
#
# NOTE: readiness is a claim about DEPENDENCIES, not about the codebase. An item
# stays READY after its work lands until someone marks it done, so consumers must
# verify against the repo before acting.
#
# Runs in a subshell: it cds, and leaking that into a sourced caller's shell
# silently reroutes every later relative path.
hero_ready_items() (
  local store items f d raw deps ready title id state itype row all_ids done_ids
  local open_goals parent committed_ids committed missing awaiting blocked_on since enum
  local idea_ids anti_ids shape channel resolution
  store="${1:-$(hero_work_store)}" || return 1

  # An unmigrated store lists NOTHING rather than listing wrong. Every item in
  # it still carries `kind`, which schema 1 does not read, so a permissive pass
  # would print an empty roadmap for a repo that has a full one — and an empty
  # roadmap reads as "nothing to do", not as "this did not work".
  if [ ! -f "$store/PLAN.md" ] || [ -z "$(hero_item_field "$store/PLAN.md" schema)" ]; then
    echo "hero_ready_items: '$store' has no PLAN.md at schema 1; run 'bash scripts/migrate-plan.sh $store', or wayfare:wayfare-init-repo on a repo with no plan yet" >&2
    return 1
  fi

  items="$store/items"
  cd "$items" 2>/dev/null || { echo "hero_ready_items: no item directory at ${items}" >&2; return 1; }
  # zsh errors out on an unmatched glob (bash leaves it literal for the
  # `[ -e ]` guard to skip), so an EMPTY store aborted with a raw "no matches
  # found" and rc=1, indistinguishable from a missing store. nullglob makes
  # it an empty listing in both shells.
  setopt localoptions nullglob 2>/dev/null || true

  # Collect every id, the done subset, and the open goals. Ids are integers by
  # convention, but comparison is string-tolerant (hero_norm_id), so the ids
  # rejected here are EMPTY ones and ids containing whitespace, because
  # whitespace would inject extra tokens into the space-delimited sets below,
  # letting a dep on a NONEXISTENT id resolve (and even count as done) with no
  # warning at all. A malformed hand-written item must not erase or corrupt
  # the whole listing.
  all_ids=" "
  done_ids=" "
  committed_ids=" "
  open_goals=" "
  idea_ids=" "
  anti_ids=" "
  for f in *.md; do
    [ -e "$f" ] || continue
    id=$(hero_norm_id "$(hero_item_field "$f" id)")
    case "$id" in
      '')
        echo "hero_ready_items: $f has no id; dependents on it cannot resolve" >&2
        continue ;;
      *[[:space:]]*)
        echo "hero_ready_items: $f has a whitespace-containing id ('$id'); dependents on it cannot resolve" >&2
        continue ;;
    esac
    case "$all_ids" in
      *" $id "*)
        echo "hero_ready_items: duplicate id $id; dependents may resolve against the wrong item" >&2 ;;
    esac
    all_ids="$all_ids$id "
    # The same alphabet gate the listing loop applies, applied BEFORE anything
    # is admitted to done_ids. Without it an item the listing prints as
    # `invalid` (`type: foo bar`, `status: done`) still unblocked its
    # dependents, invisible on the listing but live in the dependency order.
    state=$(hero_item_status "$f")
    itype=$(hero_item_type "$f")
    # A missing type is checked on its own: `done` with no type concatenates
    # to a clean word, passed the alphabet gate, and unblocked its dependents
    # while the listing printed the item `invalid`.
    [ -n "$itype" ] || continue
    case "$state$itype" in *[!a-z-]*) continue ;; esac
    # ONE rule, for every type. That is what `resolution` bought: a signal
    # ends `done` with `resolution: rejected`, so "we asked and they said no"
    # unblocks its dependents without the listing knowing what a signal is.
    # `dropped` is terminal and deliberately does NOT satisfy: the
    # prerequisite was abandoned, so anything waiting on it really is blocked.
    case "$state" in
      done)      done_ids="$done_ids$id " ;;
      # NOT done: the commit sits on a goal branch the default branch lacks,
      # so a dependent built against it merges onto a tree missing it.
      committed) committed_ids="$committed_ids$id " ;;
    esac
    # Only an OPEN goal counts as cover. `new` is untriaged and an
    # unrecognized status lists as invalid; crediting either would let a
    # defective goal silence the orphan warning for every item under it.
    case "$itype:$state" in
      goal:accepted|goal:active) open_goals="$open_goals$id " ;;
    esac
    # Ideas are collected whatever their status: a dependency on one is a
    # defect even after it is promoted, because the dependent was written
    # against a parking-lot entry rather than against the work it became.
    case "$itype" in idea) idea_ids="$idea_ids$id " ;; anti-feature) anti_ids="$anti_ids$id " ;; esac
  done

  for f in *.md; do
    [ -e "$f" ] || continue
    state=$(hero_item_status "$f")
    title=$(hero_item_field "$f" title)
    itype=$(hero_item_type "$f")
    # An item with no `type` in a store that IS migrated was written by hand or
    # by something that has not caught up. Never guessed: guessing `task` is
    # how a goal gets handed to wayfare-build-task to build.
    if [ -z "$itype" ]; then
      echo "hero_ready_items: $f has no type; schema 1 requires task, signal, goal, idea or anti-feature (docs/PLAN.md)" >&2
      echo "invalid $f — $title"
      continue
    fi
    # Gate the ALPHABET before the table: both values come from hand-editable
    # frontmatter, and the type-keyed patterns below anchor on a `:` join, so a
    # smuggled colon (`status: x:ready`) would otherwise match the `*:ready`
    # arm and walk an unrecognized status straight into READY, the exact silent
    # fall-through the invalid arm exists to stop. Every legal keyword is
    # lowercase letters and hyphens only.
    case "$state$itype" in
      *[!a-z-]*)
        echo "hero_ready_items: $f has a malformed status/type ('$state' / '$itype'); keywords are lowercase letters and hyphens only, not eligible for READY" >&2
        echo "invalid $f — $title"
        continue ;;
    esac
    # An item with no usable id is broken whatever its status: nothing can
    # depend on it and nothing can mark it done. Checked before the status
    # table so there is one rule instead of one per status.
    id=$(hero_norm_id "$(hero_item_field "$f" id)")
    case "$id" in
      ''|*[[:space:]]*) echo "invalid $f — $title"; continue ;;
    esac

    # `shape` decides what a task's Definition of Done must assert and nothing
    # about readiness, so a typo cannot misroute the item — it can only make
    # the DoD be written against the wrong test, silently, which is the whole
    # value of the field gone. Warned, never invalidated: the row is correct.
    case "$itype" in
      task)
        shape=$(hero_item_shape "$f")
        case "$shape" in
          story|structural|visual|defect|dependency|docs) ;;
          '') echo "hero_ready_items: $f is a task with no shape; a DoD written without one is written against no test (docs/PLAN.md)" >&2 ;;
          *)  echo "hero_ready_items: $f has unrecognized shape '$shape'; expected story, structural, visual, defect, dependency or docs" >&2 ;;
        esac ;;
      *)
        shape=$(hero_item_shape "$f")
        [ -z "$shape" ] || echo "hero_ready_items: $f is a $itype and carries shape '$shape'; shape belongs to tasks only" >&2 ;;
    esac
    # `channel` is the same kind of field for a signal: never readiness, only
    # where delivery goes, so a typo routes the signal nowhere without a word.
    channel=$(hero_item_channel "$f")
    case "$itype:$channel" in
      signal:design|signal:design-system|signal:architecture) ;;
      signal:)  echo "hero_ready_items: $f is a signal with no channel; expected design, design-system or architecture" >&2 ;;
      signal:*) echo "hero_ready_items: $f has unrecognized channel '$channel'; expected design, design-system or architecture" >&2 ;;
      *:)       ;;
      *)        echo "hero_ready_items: $f is a $itype and carries channel '$channel'; channel belongs to signals only" >&2 ;;
    esac
    # `resolution` is the ending, so one on an item that has not ended is a
    # status that was rolled back by hand without clearing it, or a `done`
    # someone meant and did not write. Either way the two fields disagree.
    resolution=$(hero_item_field "$f" resolution | tr '[:upper:]' '[:lower:]')
    if [ -n "$resolution" ] && [ "$state" != "done" ]; then
      echo "hero_ready_items: $f carries resolution '$resolution' at status '$state'; resolution is set only at done" >&2
    elif [ "$state" = "done" ]; then
      case "$itype:$resolution" in
        task:shipped|signal:delivered|signal:rejected|idea:promoted|anti-feature:promoted|*:obsolete) ;;
        idea:|anti-feature:) echo "hero_ready_items: $f is a done $itype with no resolution; expected promoted or obsolete" >&2 ;;
        *:) ;;
        *) echo "hero_ready_items: $f is a $itype with resolution '$resolution', which is not an ending a $itype has (docs/PLAN.md)" >&2 ;;
      esac
    fi

    # `priority` orders the listing and nothing else. An unrecognized value
    # sorts as unranked (hero_sort_rows_by_priority), so a typo can only lose
    # its rank, never claim p0; the warning keeps that from being silent.
    case "$(hero_item_priority "$f")" in
      ''|p0|p1|p2|p3) ;;
      *) echo "hero_ready_items: $f has unrecognized priority '$(hero_item_field "$f" priority)'; expected p0, p1, p2 or p3. Sorting it as unranked" >&2 ;;
    esac

    # Suspension is a FLAG, not a status (docs/PLAN.md): the item keeps the
    # status it held and `awaiting` is what makes it suspended. Read before the
    # status table, because it overrides every non-terminal row. A terminal
    # item is not waiting on anything, whatever stale ids it still carries.
    awaiting=""
    case "$state" in
      done|dropped) ;;
      *) awaiting=$(hero_item_awaiting "$f" | tr '\n' ' ' | sed 's/ $//') ;;
    esac
    if [ -n "$awaiting" ]; then
      # A wait with no age is indistinguishable from a healthy one.
      since=$(hero_item_field "$f" suspended_at)
      echo "suspended $f — $title [awaiting $(printf '%s\n' "$awaiting" | wc -w | tr -d ' '): $awaiting${since:+ — since $since}]"
      continue
    fi

    # `blocked_on` is the same kind of flag for a wait that is not a sibling's
    # reply (docs/PLAN.md). It sits after `awaiting` so a mailbox wait keeps its
    # own row. Nothing clears it here: a stale one on a terminal item is
    # warned about and ignored, never allowed to hold anything up. Only work
    # can be blocked: on an idea or anti-feature it would hide the row that
    # says what the item is.
    blocked_on=$(hero_item_field "$f" blocked_on)
    since=$(hero_item_field "$f" blocked_since)
    if [ -z "$blocked_on" ]; then
      case "$(hero_item_field_raw "$f" blocked_on)" in
        '#'[![:space:]]*) echo "hero_ready_items: $f has a blocked_on line the parser read as empty (a leading '#' is a YAML comment); quote the value. Treated as not blocked" >&2 ;;
      esac
      [ -z "$since" ] || echo "hero_ready_items: $f carries blocked_since with no blocked_on; a date with no reason is a half-cleared block" >&2
    elif [ "$itype" != task ] && [ "$itype" != signal ] && [ "$itype" != goal ]; then
      echo "hero_ready_items: $f is an $itype and carries blocked_on; a parked thought or a decision waits on nothing. Ignored" >&2
    else
      case "$state" in
        done|dropped)
          echo "hero_ready_items: $f is $state and still carries blocked_on '$blocked_on'; ignored. Delete the field" >&2 ;;
        *)
          [ -n "$since" ] || echo "hero_ready_items: $f carries blocked_on with no blocked_since; the sync lane cannot say how long" >&2
          case "$blocked_on" in
            '|'|'>') echo "hero_ready_items: $f has blocked_on written as a block scalar, which the reader does not parse; put the reason on one line" >&2 ;;
          esac
          if printf '%s' "$blocked_on" | grep -Eq '^#?[0-9]+$'; then
            echo "hero_ready_items: $f has blocked_on '$blocked_on', which looks like an item id; an item wait belongs in depends_on" >&2
          fi
          echo "blocked $f — $title [on: $blocked_on${since:+, since $since}]"
          continue ;;
      esac
    fi

    # A planned task outside every open goal is invisible to `wayfare-start-goal`,
    # which walks goals and never items, so it sits READY forever unless
    # someone runs `wayfare-advance-item N` by hand. A committed one is worse: it is the residue
    # of an abandoned goal branch, claiming work the repo does not have. Warn
    # on stderr only; the row itself is still correct. Sits ABOVE the status
    # table because the mid-flight arms `continue`.
    case "$itype:$state" in
      task:ready|task:active|task:review|task:committed)
        parent=$(hero_norm_id "$(hero_item_field "$f" parent)")
        case "$open_goals" in
          *" ${parent:-__none__} "*) ;;
          *) if [ "$state" = ready ]; then
               echo "hero_ready_items: $f is $state and no open goal has it as a member; a goal gate may adopt it (hero_goal_candidates), else wayfare-sync-plan groups it" >&2
             else
               echo "hero_ready_items: $f is $state and no open goal has it as a member; wayfare-sync-plan groups it into a goal" >&2
             fi ;;
        esac ;;
    esac

    # One table over `type:status`. Nine kinds across two enums collapsed to
    # this: the shared states are written once, with a `*:` wildcard, because
    # they now genuinely mean the same thing for every type.
    row=READY
    case "$itype:$state" in
      # Above `*:new`, which would otherwise swallow `idea:new` and print a
      # parked thought as an untriaged item. An idea is not work yet:
      # nothing builds it, nothing delivers it, and `sync` must not read it
      # as coverage. Its own row word at BOTH open statuses, so the roadmap
      # view can collapse the parking lot to one count instead of printing
      # forty rows between a reader and the READY set.
      idea:new|idea:accepted|anti-feature:new|anti-feature:accepted)
        [ -z "$(hero_item_deps "$f")" ] || echo "hero_ready_items: $f is an $itype; an $itype depends on nothing. depends_on ignored" >&2
        # Same reason for an anti-feature, and its own word: it is a
        # decision, so `*:new` printing it as an untriaged item would invite
        # a triage that promotes "we chose not to" into work.
        case "$itype" in
          idea) echo "idea    $f — $title" ;;
          *)    echo "anti    $f — $title" ;;
        esac
        continue ;;
      *:new)       echo "new     $f — $title"; continue ;;
      # Terminal and frozen. A rejected signal is kept on purpose: "we raised
      # this and they said no" is the history that stops it being raised again
      # next quarter, and `resolution` is where the answer lives.
      *:done)      echo "done    $f — $title"; continue ;;
      # Abandoned. Its own row word, never `done`, so nothing reads it as
      # satisfied work and re-plans around code that was never written.
      *:dropped)   echo "dropped $f — $title"; continue ;;
      # Type-keyed, not `*:`: an idea at `active` or a goal at `planning` is
      # not a shared state, it is a mis-filed item, and the wildcard walked it
      # into a row resume-state then picked up as the item in flight.
      task:planning) echo "plan    $f — $title"; continue ;;
      task:active|signal:active|goal:active) echo "active  $f — $title"; continue ;;
      # Its own row word rather than `done`, so no caller has to read the log
      # to learn whether the default branch has the code (it does not).
      task:committed) echo "committed $f — $title"; continue ;;
      task:review) echo "review  $f — $title"; continue ;;
      # A goal is a container, never a unit of work: READY means "hand this to
      # wayfare-build-task", and wayfare-build-task builds tasks. `wayfare-start-goal` selects goals by
      # type and `wayfare-advance-item GOAL_ID` takes one by id, never off the
      # READY tier.
      goal:accepted) echo "goal    $f — $title"; continue ;;
      # A signal is delivered, not built, so it never reaches READY either.
      # Its own row word so the open-feedback count is a scan rather than a
      # judgment about prose: a miscount of zero is indistinguishable from
      # "no feedback exists".
      signal:accepted|signal:ready) echo "feedback $f — $title"; continue ;;
      # Never READY, but falls through to the dep check: dangling refs must
      # still warn, and unmet deps must annotate the row (a goal turn reads them).
      task:accepted) row=backlog ;;
      task:ready) ;; # the one READY-eligible arm — dep check below
      *)
        # An UNRECOGNIZED status must never fall through to the READY path. The
        # display label is `plan` while the keyword is `planning`, so `status:
        # plan`, or any misspelling of a keyword, is an easy hand or model error that
        # would otherwise be handed straight to wayfare-build-task with no human
        # ready-mark, silently defeating the gate the ready state exists to
        # enforce. Treat it like a rejected id: name it loudly, never READY.
        case "$itype" in
          task)   enum="new/accepted/planning/ready/active/committed/review/done/dropped" ;;
          signal) enum="new/accepted/ready/active/done/dropped" ;;
          goal)   enum="new/accepted/active/done/dropped" ;;
          idea|anti-feature) enum="new/accepted/done/dropped" ;;
          *)      enum="a status of an unrecognized type '$itype'; expected task, signal, goal, idea or anti-feature" ;;
        esac
        echo "hero_ready_items: $f has unrecognized status '$state', which is not one of $enum; not eligible for READY" >&2
        echo "invalid $f — $title"
        continue ;;
    esac

    deps=$(hero_item_deps "$f")
    ready=1
    missing=""
    committed=""
    # Heredoc keeps the loop in this shell (so `ready` persists) and works under
    # both bash and zsh, which does not word-split unquoted vars.
    while IFS= read -r raw; do
      [ -z "$raw" ] && continue
      d=$(hero_norm_id "$raw")
      # An item that depends on itself is blocked forever and looks like
      # ordinary waiting: the id exists and is not done.
      if [ "$d" = "$id" ]; then
        echo "hero_ready_items: $f depends_on itself ('$raw'); blocked until the reference is removed" >&2
        missing="$missing $raw"
        ready=0
        continue
      fi
      case "$all_ids" in
        *" $d "*) ;;
        *)
          # A dangling reference blocks FOREVER, silently, unless it is named:
          # nothing will ever mark a nonexistent id done. Say so on both the
          # listing (so the model sees it) and stderr (so a human does), and
          # say it with the RAW value as written in the file, so grepping the
          # store for the printed token actually finds it.
          echo "hero_ready_items: $f depends_on '$raw', which no item carries; blocked until the reference is fixed" >&2
          missing="$missing $raw"
          ready=0
          continue ;;
      esac
      # An idea is not committed work. Depending on one blocks a real item
      # behind something nobody has decided to do, and no route exists to
      # mark an idea `done` by building it, so the block is permanent and
      # looks like ordinary waiting. Name it like a dangling ref.
      case "$idea_ids" in
        *" $d "*)
          echo "hero_ready_items: $f depends_on '$raw', which is an idea; an idea is not work and nothing can build it. Promote it, then depend on what it became" >&2
          missing="$missing $raw"
          ready=0
          continue ;;
      esac
      # A decision not to build is never satisfied by building, so a dependent
      # would wait forever. Same defect as an idea, named the same way.
      case "$anti_ids" in
        *" $d "*)
          echo "hero_ready_items: $f depends_on '$raw', which is an anti-feature; nothing builds a declined thing. Reverse the decision first, then depend on what it became" >&2
          missing="$missing $raw"
          ready=0
          continue ;;
      esac
      case "$done_ids" in *" $d "*) continue ;; esac
      ready=0
      case "$committed_ids" in *" $d "*) committed="$committed $d" ;; esac
    done <<EOF
$deps
EOF
    # backlog rows report dep state without ever becoming READY: the
    # annotation is what wayfare's "none of the above" report prints (blocked
    # rows and their unmet deps), and the missing-dep warning keeps a
    # bootstrap-time typo'd id loud instead of a task that silently never
    # becomes selectable.
    if [ "$row" = backlog ]; then
      if [ "$ready" = 1 ]; then
        echo "backlog $f — $title"
      else
        echo "backlog $f — $title [deps unmet${missing:+; missing dep:$missing}${committed:+; committed dep:$committed}]"
      fi
    elif [ "$ready" = 1 ]; then
      echo "READY   $f — $title"
    else
      echo "blocked $f — $title${missing:+ [missing dep:$missing]}${committed:+ [committed dep:$committed]}"
    fi
  # No `return` inside the loop above: it is the left side of this pipe, so a
  # return would exit only that subshell, never this function.
  done | hero_sort_rows_by_priority
)

# Tasks no open goal holds that `wayfare-start-goal`'s gate may adopt into
# GOAL_ID (references/goals.md, *Adopting ungrouped work*). Stdout is
# `ID STATUS` per candidate, in id order; each ungrouped task at `accepted` or
# `ready` that is left out goes to stderr as `ID skipped: REASON`. Fit to the
# goal's DoD is the gate's judgment; the rest is checked here.
#
# A task with no `source` paths is skipped, not offered: the forbidden-path
# guard cannot run on it, and reading that as "touches nothing" lets exactly
# the undeclared tasks through. An `accepted` task must also sit inside the
# members' paths, as an admission must: nobody has read its plan, because the
# goal writes it after the gate. Deps are settled to a fixed point, so a
# candidate whose dep was dropped is dropped too, and a cycle is dropped whole.
hero_goal_candidates() ( # GOAL_ID [STORE]
  local goal store f id itype state parent pinfo index gstate members mpaths blocked_on
  local paths p bad deps dep dstate cands next changed out
  [ -n "$1" ] || { echo "hero_goal_candidates: empty GOAL_ID" >&2; return 2; }
  goal=$(hero_norm_id "$1")
  store="${2:-$(hero_work_store)}" || return 1
  cd "$store/items" 2>/dev/null || { echo "hero_goal_candidates: no item directory at $store/items" >&2; return 1; }
  setopt localoptions nullglob 2>/dev/null || true

  # `id type status` per item. An item with no id cannot be depended on or
  # adopted; left in, its empty first field shifts every later read.
  index=
  for f in *.md; do
    id=$(hero_norm_id "$(hero_item_field "$f" id)")
    itype=$(hero_item_type "$f")
    state=$(hero_item_status "$f")
    if [ -z "$id" ]; then
      case "$state" in accepted|ready) echo "hero_goal_candidates: $f skipped: no id, a store defect" >&2 ;; esac
      continue
    fi
    index="$index$id ${itype:-none} $state
"
  done

  gstate=$(printf '%s' "$index" | awk -v i="$goal" '$1 == i { print $2, $3; exit }')
  case "$gstate" in
    "goal accepted"|"goal active") ;;
    *) echo "hero_goal_candidates: $goal is not an open goal (${gstate:-no such item})" >&2; return 2 ;;
  esac
  members=$(hero_goal_members "$goal" "$store") || { echo "hero_goal_candidates: cannot read the members of goal $goal" >&2; return 1; }
  mpaths=
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    for f in *.md; do
      [ "$(hero_norm_id "$(hero_item_field "$f" id)")" = "$id" ] || continue
      mpaths="$mpaths$(hero_item_list_field "$f" source)
"
      break
    done
  done <<MEMBERS
$members
MEMBERS
  members=" $(printf '%s' "$members" | tr '\n' ' ') "

  # `ID STATUS DEP,DEP` per task that passes every check but the deps.
  cands=
  for f in *.md; do
    id=$(hero_norm_id "$(hero_item_field "$f" id)")
    [ -n "$id" ] || continue
    itype=$(hero_item_type "$f")
    state=$(hero_item_status "$f")
    case "$state" in accepted|ready) ;; *) continue ;; esac
    if [ -z "$itype" ]; then
      echo "hero_goal_candidates: $id skipped: no type, a store defect" >&2; continue
    fi
    [ "$itype" = task ] || continue
    parent=$(hero_norm_id "$(hero_item_field "$f" parent)")
    if [ -n "$parent" ]; then
      pinfo=$(printf '%s' "$index" | awk -v i="$parent" '$1 == i { print $2, $3; exit }')
      case "$pinfo" in
        "goal accepted"|"goal active") continue ;;
        "goal done"|"goal dropped") ;;
        *) echo "hero_goal_candidates: $id skipped: parent $parent is not a goal (${pinfo:-no such item}), a store defect" >&2; continue ;;
      esac
    fi
    if [ -n "$(hero_item_list_field "$f" awaiting)" ]; then
      echo "hero_goal_candidates: $id skipped: suspended, awaiting a message" >&2; continue
    fi
    blocked_on=$(hero_item_field "$f" blocked_on)
    if [ -z "$blocked_on" ]; then
      case "$(hero_item_field_raw "$f" blocked_on)" in
        '#'[![:space:]]*) echo "hero_goal_candidates: $f has a blocked_on line the parser read as empty (a leading '#' is a YAML comment); quote the value. Treated as not blocked" >&2 ;;
      esac
      [ -z "$(hero_item_field "$f" blocked_since)" ] || echo "hero_goal_candidates: $f carries blocked_since with no blocked_on; a date with no reason is a half-cleared block" >&2
    else
      [ -n "$(hero_item_field "$f" blocked_since)" ] || echo "hero_goal_candidates: $f carries blocked_on with no blocked_since; the sync lane cannot say how long" >&2
      echo "hero_goal_candidates: $id skipped: blocked_on $blocked_on" >&2; continue
    fi
    if [ -n "$(hero_item_field "$f" bot)" ]; then
      echo "hero_goal_candidates: $id skipped: a bot's PR, carried on its own" >&2; continue
    fi
    paths=$(hero_item_list_field "$f" source)
    if [ -z "$paths" ]; then
      echo "hero_goal_candidates: $id skipped: no source paths to check" >&2; continue
    fi
    bad=
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      # One scope per member path, so the split is wanted; noglob keeps a
      # declared `src/*` from expanding against the items directory.
      # shellcheck disable=SC2046
      if hero_path_forbidden "$p"; then
        bad="$bad $p"
      elif [ "$state" = accepted ] && ! (set -f; hero_path_within "$p" $(printf '%s' "$mpaths")); then
        echo "hero_goal_candidates: $id skipped: unplanned, and $p is outside the goal's paths" >&2; bad=-; break
      fi
    done <<PATHS
$paths
PATHS
    [ "$bad" = - ] && continue
    if [ -n "$bad" ]; then
      echo "hero_goal_candidates: $id skipped: touches$bad, which needs its own goal" >&2; continue
    fi
    deps=$(hero_item_deps "$f" </dev/null | while IFS= read -r dep; do hero_norm_id "$dep"; done | tr '\n' ',')
    cands="$cands$id $state ${deps:-,}
"
  done

  # Drop, until nothing changes, every candidate with a dep that is not done,
  # not a member, and not a surviving candidate.
  changed=1
  while [ "$changed" = 1 ]; do
    changed=0; next=
    while read -r id state deps; do
      [ -n "$id" ] || continue
      bad=
      for dep in $(printf '%s' "$deps" | tr ',' ' '); do
        case "$members" in *" $dep "*) continue ;; esac
        printf '%s' "$cands" | awk -v i="$dep" '$1 == i { f = 1 } END { exit !f }' && continue
        dstate=$(printf '%s' "$index" | awk -v i="$dep" '$1 == i { print $3; exit }')
        case "$dstate" in
          done) ;;
          "") bad="$bad $dep (which no item has)" ;;
          *) bad="$bad $dep (not done, not in this goal)" ;;
        esac
      done
      if [ -n "$bad" ]; then
        echo "hero_goal_candidates: $id skipped: depends on$bad" >&2; changed=1
      else
        next="$next$id $state $deps
"
      fi
    done <<CANDS
$cands
CANDS
    cands=$next
  done

  # Only a cycle among the candidates can block what remains. Place each one
  # whose in-pool deps are placed; what never places is the cycle.
  out=; changed=1
  while [ "$changed" = 1 ]; do
    changed=0; next=
    while read -r id state deps; do
      [ -n "$id" ] || continue
      bad=
      for dep in $(printf '%s' "$deps" | tr ',' ' '); do
        printf '%s' "$cands" | awk -v i="$dep" '$1 == i { f = 1 } END { exit !f }' || continue
        printf '%s' "$out" | awk -v i="$dep" '$1 == i { f = 1 } END { exit !f }' || bad=1
      done
      if [ -n "$bad" ]; then
        next="$next$id $state $deps
"
      else
        out="$out$id $state
"; changed=1
      fi
    done <<CANDS
$cands
CANDS
    cands=$next
  done
  while read -r id state deps; do
    [ -n "$id" ] && echo "hero_goal_candidates: $id skipped: in a dependency cycle, a store defect" >&2
  done <<CANDS
$cands
CANDS
  printf '%s' "$out" | sort -n -k1,1
)

# ---------- branch naming ---------------------------------------------------
#
# Deriving the name itself is a *model* task, not a shell one. It reads a diff
# or a description and summarizes. What lives here is the policy the model
# applies, in one place, because it was previously stated in both push-pr and
# wayfare-build-task and the two had already drifted (one listed a `test/` prefix, the
# other did not; one asked for a 3-5 word slug, the other 2-3).
#
# Skills reference hero_branch_policy in their instructions instead of
# restating the rules. It prints the policy for the model to apply.

hero_branch_policy() {
  cat <<'POLICY'
Branch name = TYPE/SLUG, or ISSUE-ID-SLUG when an issue ID is known.

TYPE — pick from the change's dominant intent:
  feat      new functionality
  fix       bug fix
  refactor  restructuring with no behavior change
  perf      performance improvement with no behavior change
  docs      documentation only
  test      tests only
  chore     tooling, CI, dependency bumps

SLUG — 3-5 words, lowercase, hyphen-separated, <=50 chars.
  Strip filler words (the, a, an, for, to, in).
  Derive from the task description when one was given, else from the diff:
  the most-changed top-level directory plus what changed.

ISSUE ID — when the task starts with an issue ID matching
  ^[A-Z][A-Z0-9]{1,9}-[0-9]+(\s|$), or HERO.md sets an issue-prefix and an ID
  appears in the diff or draft commit message, prefer ISSUE-ID-SLUG.
  The match must be anchored at position 0, so "Fix CVE-2024-1234 in auth"
  is NOT an issue ID and falls through to TYPE/SLUG.
POLICY
}
