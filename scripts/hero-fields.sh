#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# The map of which skill is driven by which config fields, and what each
# field decides for that skill. The read-only first phase of every skill's
# `recalibrate` verb; see docs/RECALIBRATE.md.
#
# Usage:
#   scripts/hero-fields.sh SKILL [ROOT]   rows for one skill, with values read
#                                         from ROOT (default: the repo root)
#   scripts/hero-fields.sh --list         skill names that have a map entry
#   scripts/hero-fields.sh --all          every row, no values read
#
# Output is TSV with a header: SECTION KEY CURRENT DECIDES, the same four
# columns in every mode, so one record type describes the whole command.
# SECTION is `Heading`, or `Heading::sub` for one connection block. `--all`
# fills CURRENT with `-` because it reads no file.
#
# CURRENT is either a HERO.md value or one of seven parenthesised sentinels.
# The parentheses are what keep the two domains disjoint: no branch name,
# command or registry URL starts with `(`, so a file that literally says
# `- default-branch: unset` cannot be mistaken for a field that has none.
#
#   (present) (absent)      a `*` row's section heading, found or not
#   (n/a: KEY=...)          a connection whose `type` or `compliance-type`
#                           answered (none, self) or was refused; keys moot
#   (unset)                 the file does not carry this field, or carries it empty
#   (no-section)            the heading this field lives under is missing
#   (refused)               the reader rejected the value as unsafe
#   (no-file)               there is no readable HERO.md at all
#
# `(unset)` and `(refused)` are different findings and must stay that way:
# collapsing them would send `recalibrate` to ask about a field that is
# actually set to something dangerous. `(n/a: type=none)` is the same argument
# one level up: a connection whose `type` is `none` has answered for its whole
# block, and reporting its `at` as `(unset)` is what makes recalibrate ask a
# repo with no design system to name one, every single run.
#
# Exit: 0 rows printed, 1 cannot run (no lib, bad ROOT, reader failure),
# 2 unknown skill.

# Deliberately not `set -e`, unlike its six siblings in this directory. An
# unset field makes `hero_md_field` return non-zero, and that is this script's
# finding to report, not an error to die on. With `-e` the table stops at the
# first unset field and exits 1, silently, and every recalibrate that reads it
# then asks about nothing.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/hero-lib.sh" || { echo "hero-fields: cannot source hero-lib.sh" >&2; exit 1; }

# SKILL|SECTION|KEY|DECIDES
#
# One row per field a skill actually reads. A field listed here that no skill
# reads, or read by a skill and missing here, is what audit-plugin's HERO.md
# field-coverage pass reports: this map is the claim, the skills are the truth.
#
# Emitted by a function, not assigned through `MAP=$(cat <<'ROWS' ... )`: a
# here-doc nested in a command substitution makes bash scan the body for shell
# quotes, and the first apostrophe in a prose cell ("the bot's") becomes an
# unterminated string that fails the whole script at parse time.
# Rows for fields a skill reads but never tunes are legitimate: a skill does
# not have to offer `recalibrate` to appear here. wayfare-recalibrate-config
# is the one skill that reports and writes them all, and it does that with
# --all, so a field is reachable if and only if it has a row. A field with no
# row is a field no recalibrate can ask about.
rows() {
  cat <<'ROWS'
wayfare-init-repo|*|*|every section — init writes the whole file, the only whole-file pass
wayfare-push-pr|Repository|default-branch|the branch to cut from and the PR base
wayfare-push-pr|Repository|branch-convention|the shape of the branch name it creates
wayfare-push-pr|Repository|commit-convention|the shape of the commit message it writes
wayfare-push-pr|Repository|task-runner|the tool (just, make, …) whose targets the test phase prefers over per-project raw commands, when set
wayfare-push-pr|Connections::issues|issue-prefix|the ticket ID in the branch name and the PR trailers
wayfare-push-pr|Code Quality|pre-commit|whether the commit step expects hooks to run and re-stage
wayfare-push-pr|Code Quality|linters|the static checks the verify phase runs
wayfare-push-pr|CI/CD|platform|where the post-push CI status report is read from
wayfare-push-pr|Projects|*|per project: language, framework, install/test/dev commands, port — the test phase falls back to auto-detection without them
wayfare-ship-pr|Repository|default-branch|what the branch resets to after the merge
wayfare-ship-pr|Repository|merge-method|squash, rebase, or merge — the button this skill presses
wayfare-ship-pr|Repository|auto-delete-branches|whether ship deletes the head branch itself after merging
wayfare-ship-pr|CI/CD|auto-approve-installed|whether `@auto-approve` will do anything at all
wayfare-ship-pr|CI/CD|auto-approve-gates|the gates the approval verdict is expected to enforce
wayfare-ship-pr|Deployment|platform|whether there is a deploy to verify after the merge
wayfare-ship-pr|Deployment|registry|where the built image is expected to land
wayfare-ship-pr|Deployment|argocd|whether the deploy is GitOps-synced rather than pushed
wayfare-build-task|Repository|default-branch|the base for every step of the pipeline
wayfare-build-task|Repository|branch-convention|the branch the goal's work lands on
wayfare-build-task|Connections::issues|type|the tracker a ticket is fetched from and closed out in
wayfare-build-task|Connections::issues|at|the repo or workspace the ticket lives in
wayfare-build-task|Connections::issues|issue-prefix|how a plain-text argument is recognized as a ticket ID
wayfare-build-task|Code Review Agent|agent|which bot's review the await-review step waits for
wayfare-build-task|Code Review Agent|bot-username|whose comments count as the bot's, and whose do not
wayfare-build-task|CI/CD|auto-approve-installed|whether the ship step can complete
wayfare-build-task|Projects|*|per project: test and dev commands the build and verify steps use
wayfare-review-pr|Repository|default-branch|the base the diff under review is taken against
wayfare-review-pr|Code Quality|linters|the checks a finding must not simply restate
wayfare-review-pr|Coding Conventions|*|the conventions a review judges the code against, instead of inventing house style
wayfare-review-pr|Projects|*|per project: language and framework, which decide the review's focus
wayfare-respond-pr|Code Review Agent|agent|which reviewer's threads this skill answers
wayfare-respond-pr|Code Review Agent|bot-username|whose comments are the bot's, for the poll and the resolve
wayfare-respond-pr|Code Review Agent|trigger|how the bot's review is requested
wayfare-respond-pr|Code Review Agent|poll-method|how this skill knows the review has landed
wayfare-respond-pr|Repository|default-branch|the base for the diff a comment is read against
wayfare-respond-pr|Projects|*|per project: the test command run after a fix
wayfare-sync-plan|Wayfare|source-repo|the codebase reconciled against the design
wayfare-sync-plan|Connections::design|type|which design substrate this repo is built toward, or none
wayfare-sync-plan|Connections::design|at|the project or file the design is read from
wayfare-sync-plan|Connections::design|reach|how the design gets to the local snapshot, or manual
wayfare-sync-plan|Connections::design|ux-flow|the authoritative journey the codebase is reconciled against
wayfare-sync-plan|Connections::design|reconciliation|the target's own rolling reconciliation document, the starting point a sync reads
wayfare-sync-plan|Connections::design-system|type|whether there is an upstream design system at all
wayfare-sync-plan|Connections::design-system|at|the registry repo the UI work sources primitives from
wayfare-sync-plan|Connections::reference|type|whether there is a template this repo should still resemble
wayfare-sync-plan|Connections::reference|at|the template this repo is compared against for drift
wayfare-sync-plan|Connections::architecture|type|whether the architecture record is this repo's own DESIGN.md or lives elsewhere
wayfare-sync-plan|Connections::infrastructure|type|whether this system's IaC lives in a repo of its own
wayfare-sync-plan|Connections::infrastructure|at|the repo holding this system's IaC, when the harden stage must read it
wayfare-start-goal|Repository|default-branch|the base for every PR the goal turns open
wayfare-init-repo|Repository|type|single or monorepo, which decides whether one DESIGN.md covers the repo (the architecture stage) and where `init` scaffolds a new project
wayfare-sync-plan|Deployment|platform|the deploy shape DESIGN.md's invariants hold under, and whether the harden stage has images to scan
wayfare-sync-plan|Deployment|registry|where the image the harden stage scans is pulled from
wayfare-sync-plan|Code Quality|linters|the security checks already in the gate, which the harden stage must not re-propose
wayfare-sync-plan|Projects|*|per project: language and dependency file (the CVE scanners), in a monorepo which project DESIGN.md describes, and the names a new project must not collide with
wayfare-recomponentize-ui|Connections::design-system|role|producer refuses the run; consumer is what the pass is for
wayfare-recomponentize-ui|Connections::design-system|namespace|the registry prefix components are sourced under
wayfare-recomponentize-ui|Connections::design-system|registry-url|where the registry is fetched from
wayfare-recomponentize-ui|Connections::design-system|token-env-var|the env var holding the registry token
wayfare-recomponentize-ui|Projects|*|per project: the framework, which decides whether there is a UI at all
wayfare-drop-item|Repository|branch-convention|which branches this skill may discard
wayfare-start-goal|Repository|branch-convention|the shape of the branch a goal's work lands on
wayfare-check-preflight|Repository|default-branch|the branch every readiness check is made against
wayfare-check-preflight|CI/CD|auto-approve-installed|whether the ship step will be a no-op
wayfare-check-preflight|Code Quality|pre-commit|whether the gate is installed and current
wayfare-setup-dev|Developer Setup|*|required tools, recommended tools, and MCP servers — the checklist this skill walks
wayfare-setup-dev|Projects|*|per project: install and dev commands the setup verifies
wayfare-init-repo|Connections::design-system|namespace|the registry a scaffolded UI is wired to
wayfare-create-skill|Projects|*|per project: language and framework, which the new skill's examples follow
wayfare-write-handoff|Connections::issues|type|the tracker the distilled work-item is filed in
wayfare-write-handoff|Connections::issues|at|the repo or workspace it is filed against
wayfare-write-handoff|Connections::issues|issue-prefix|the ID shape the item is named with
wayfare-sync-plan|Connections::issues|type|whether confirmed security and compliance findings reach a tracker at all, and the compliance route's tracker when compliance-type is unset
wayfare-sync-plan|Connections::issues|reach|the tool the findings are filed through when compliance-reach is unset
wayfare-sync-plan|Connections::issues|at|the repo a github route files confirmed security and compliance findings into
wayfare-sync-plan|Connections::issues|compliance-type|the tracker confirmed security and compliance findings are filed in, when it is not the main one
wayfare-sync-plan|Connections::issues|compliance-reach|the tool that reaches the compliance tracker
wayfare-sync-plan|Connections::issues|compliance-team|the team confirmed security and compliance findings are filed under
wayfare-sync-plan|Connections::issues|compliance-project|the project confirmed security and compliance findings belong to
wayfare-sync-plan|Connections::issues|compliance-label|the label every finding ticket carries
wayfare-audit-security|Connections::issues|type|whether confirmed CVE findings reach a tracker at all, and the compliance route's tracker when compliance-type is unset
wayfare-audit-security|Connections::issues|reach|the tool the findings are filed through when compliance-reach is unset
wayfare-audit-security|Connections::issues|at|the repo a github route files confirmed CVE findings into
wayfare-audit-security|Connections::issues|compliance-type|the tracker confirmed CVE findings are filed in, when it is not the main one
wayfare-audit-security|Connections::issues|compliance-reach|the tool that reaches the compliance tracker
wayfare-audit-security|Connections::issues|compliance-team|the team confirmed CVE findings are filed under
wayfare-audit-security|Connections::issues|compliance-project|the project confirmed CVE findings belong to
wayfare-audit-security|Connections::issues|compliance-label|the label every finding ticket carries
wayfare-audit-compliance|Connections::issues|type|whether confirmed control findings reach a tracker at all, and the compliance route's tracker when compliance-type is unset
wayfare-audit-compliance|Connections::issues|reach|the tool the findings are filed through when compliance-reach is unset
wayfare-audit-compliance|Connections::issues|at|the repo a github route files confirmed control findings into
wayfare-audit-compliance|Connections::issues|compliance-type|the tracker confirmed control findings are filed in, when it is not the main one
wayfare-audit-compliance|Connections::issues|compliance-reach|the tool that reaches the compliance tracker
wayfare-audit-compliance|Connections::issues|compliance-team|the team confirmed control findings are filed under
wayfare-audit-compliance|Connections::issues|compliance-project|the project confirmed control findings belong to
wayfare-audit-compliance|Connections::issues|compliance-label|the label every finding ticket carries
wayfare-ship-pr|Connections::issues|type|the tracker a merged fix's finding ticket is moved to In Review in, when compliance-type is unset
wayfare-ship-pr|Connections::issues|reach|the tool that comments on that ticket, when compliance-reach is unset
wayfare-ship-pr|Connections::issues|compliance-type|the tracker the finding tickets live in
wayfare-ship-pr|Connections::issues|compliance-reach|the tool that comments on a finding ticket and moves it to In Review
wayfare-ship-pr|Connections::issues|at|the repo a github route's finding ticket must be in before Step 7f touches it
wayfare-ship-pr|Connections::issues|compliance-team|the team a linear route's finding ticket must be in before Step 7f touches it
wayfare-ship-pr|Connections::issues|compliance-label|the label a ticket must carry before Step 7f treats it as a finding ticket
ROWS
}

# The header block above IS the help text, so this range tracks it: line 6 is
# the first line after the copyright, line 42 the last of the exit contract.
# Reflowing that block without moving these numbers prints the copyright as
# usage and truncates the range mid-sentence.
usage() { sed -n '6,42p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in
  ''|-h|--help) usage; exit 0 ;;
  --list) rows | cut -d'|' -f1 | sort -u; exit 0 ;;
  --all)
    printf 'SKILL\tSECTION\tKEY\tCURRENT\tDECIDES\n'
    rows | awk -F'|' -v OFS='\t' '{ print $1, $2, $3, "-", $4 }'
    exit 0 ;;
esac

SKILL="$1"
ROOT="${2:-$(hero_root)}"

# A ROOT that is not a directory is a caller bug (a typo, a stale variable),
# not a repo without config. Without this it would render a full table of
# `(no-file)` and exit 0, and recalibrate would offer to write a fresh HERO.md
# into a tree that does not exist.
[ -d "$ROOT" ] || { echo "hero-fields: ROOT is not a directory: $ROOT" >&2; exit 1; }

# Compare the field, don't interpolate into a regex: `grep "^$SKILL|"` made
# `hero-fields.sh push.pr` print push-pr's table and exit 0, so a mangled
# argument reported another skill's fields and recalibrate wrote them.
SKILL_ROWS=$(rows | awk -F'|' -v s="$SKILL" '$1 == s')
if [ -z "$SKILL_ROWS" ]; then
  echo "hero-fields: no map entry for '$SKILL'; run --list for the skills that have one" >&2
  exit 2
fi

TARGET="$ROOT/HERO.md"
if [ -e "$TARGET" ] && [ ! -r "$TARGET" ]; then
  # Distinct from absent on purpose: a HERO.md nobody can read is a
  # permissions problem to surface, and reporting it as "no config" invites
  # recalibrate to propose writing over a file that is already there.
  echo "hero-fields: $TARGET exists but is not readable" >&2
  exit 1
fi

# `hero_md_field` skips fenced code blocks because HERO.md documents its own
# syntax in examples. This heading probe must skip them too, or a `## Section`
# quoted inside a fence reports as present and recalibrate never asks for it.
# The separator is `::`, never `/`: `## CI/CD` is a real heading with a slash in
# it, and splitting on that one reports every CI/CD field as (no-section).
# The sub-heading is only looked for INSIDE its parent: `### design` also
# exists under `## Projects`, and a bare search would report the connection
# as present because a project shares its name.
has_section() { # SECTION FILE
  local want sub_want
  want="## ${1%%::*}"
  sub_want=""
  # Not `case "$1" in *::*)` inside the awk -v: a case statement in a command
  # substitution is a bash-3.2 parse error, and macOS still ships 3.2.
  if [ "$1" != "${1#*::}" ]; then sub_want="### ${1#*::}"; fi
  # The "an H3 counts only inside its parent H2" rule is also implemented in
  # hero_md_field's awk (hero-lib.sh). Change one and the probe and the read
  # disagree about whether a block exists.
  awk -v want="$want" -v sub_want="$sub_want" '
    /^```/ { fence = !fence; next }
    fence  { next }
    { line = $0; sub(/[[:space:]]+$/, "", line) }
    line ~ /^## / { insec = (line == want); if (insec && sub_want == "") { found = 1; exit } ; next }
    insec && sub_want != "" && line == sub_want { found = 1; exit }
    END { exit !found }
  ' "$2"
}

# Not `rows | while`: a pipeline puts the loop in a subshell, where a reader
# failure could set no flag the script could exit on. Every row read below
# reported success no matter how badly hero_md_field broke.
ERRF=$(mktemp); trap 'rm -f "$ERRF"' EXIT
FAILED=0

printf 'SECTION\tKEY\tCURRENT\tDECIDES\n'
while IFS='|' read -r _skill section key decides; do
  [ -n "$section" ] || continue

  if [ ! -r "$TARGET" ]; then
    current="(no-file)"
  elif [ "$key" = '*' ]; then
    if [ "$section" = '*' ] || has_section "$section" "$TARGET"; then
      current="(present)"
    else
      current="(absent)"
    fi
  elif ! has_section "$section" "$TARGET"; then
    # The field cannot be unset when the heading it lives under is missing.
    # Those need different questions, and phase 3 needs to know it is creating
    # a section rather than filling a blank in one.
    current="(no-section)"
  else
    if [ "$section" = "${section#*::}" ]; then
      current=$(hero_md_field "$TARGET" "$key" "## $section" 2>"$ERRF"); rc=$?
    else
      # The issues block's compliance route has its own discriminator, and it
      # defaults to the main `type`. Judging `compliance-team` against `type`
      # alone reports a Linear route under `type: none` as moot, and judging
      # a set `compliance-type` at all reports the route's own answer as n/a.
      disc="type"
      case "$key" in
        compliance-type)
          hero_md_field "$TARGET" compliance-type "### ${section#*::}" "## ${section%%::*}" >/dev/null 2>&1
          [ "$?" = 1 ] || disc="" ;;
        compliance-*)
          hero_md_field "$TARGET" compliance-type "### ${section#*::}" "## ${section%%::*}" >/dev/null 2>&1
          [ "$?" = 1 ] || disc=compliance-type ;;
      esac
      conn_type=""; type_rc=1
      if [ -n "$disc" ]; then
        # Not piped into `tr`: a pipeline reports the LAST command's rc, so
        # hero_md_field's refusal would arrive as 0 and a rejected
        # discriminator would read as an unmigrated block.
        if [ "$disc" = compliance-type ]; then
          # Through the guard: `jira`, or `github` under a non-github main
          # type, is a route nothing can file into, and its keys are blocked.
          conn_type=$(hero_connection "${section#*::}" compliance-type "$ROOT" 2>/dev/null); type_rc=$?
        else
          conn_type=$(hero_md_field "$TARGET" "$disc" "### ${section#*::}" "## ${section%%::*}" 2>/dev/null); type_rc=$?
        fi
      fi
      conn_type=$(printf '%s' "$conn_type" | tr '[:upper:]' '[:lower:]')
      if [ "$key" != type ] && [ "$type_rc" = 2 ]; then
        # The discriminator holds something the reader refuses. Asking about
        # this block's other keys invites recalibrate to interview the user
        # about a connection nothing can act on until the `type` is fixed.
        current="(n/a: $disc=refused)"; rc=0
      elif [ "$key" != type ] && { [ "$conn_type" = none ] || [ "$conn_type" = self ]; }; then
        # The block answered. `none` has nothing to locate and `self` is
        # located by being here, so `(unset)` on their other keys would read as
        # a question the repo already settled.
        current="(n/a: $disc=$conn_type)"; rc=0
      else
        # Through hero_connection for a connection's own keys: it carries the
        # shape rules for `reach` and `issues.at`, and a table that reports a
        # value every runtime reader refuses is a table recalibrate never asks
        # about.
        current=$(hero_connection "${section#*::}" "$key" "$ROOT" 2>"$ERRF"); rc=$?
        # A github route has no team or project: unset there is the answer.
        # Set, the guard refuses it, which is the defect to report.
        if [ "$rc" = 1 ] && [ "$conn_type" = github ]; then
          case "$key" in
            compliance-team|compliance-project) current="(n/a: $disc=github)"; rc=0 ;;
          esac
        fi
      fi
    fi
    case "$rc" in
      0) ;;
      1) current="(unset)" ;;
      2) current="(refused)" ;;
      # hero_md_field returns only 0, 1 or 2. Anything else means the reader
      # itself broke, renamed by a refactor, or a stale vendored hero-lib.sh
      # where the function is simply gone (127). Reporting that as `(unset)`
      # is how a field holding `--exec=...` gets read as merely absent.
      *) echo "hero-fields: reader failed rc=$rc on $section/$key: $(cat "$ERRF")" >&2
         current="(reader-failed)"; FAILED=1 ;;
    esac
  fi

  printf '%s\t%s\t%s\t%s\n' "$section" "$key" "$current" "$decides"
done <<EOF
$SKILL_ROWS
EOF

exit "$FAILED"
