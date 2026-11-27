#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Which of a PR's changed files are on .github/auto-approve-human-review.txt:
# paths auto-approve never approves, so a person merges the PR. Read by
# wayfare-ship-pr Step 3c. It mirrors the `fleet-workflow` block in
# .github/workflows/auto-approve.yaml: same repo, same list ref, same file set,
# same matching. Drift between the two is what this exists to prevent: a path
# the skill misses gets `@auto-approve` and a REQUEST_CHANGES instead of the
# review it needed.
#
# Usage: human-review-paths.sh PR_NUMBER [OWNER/REPO]
#        human-review-paths.sh --match LIST_FILE PATHS_FILE
#
# Exit 0: nothing listed (or the repo keeps no list), prints nothing.
# Exit 1: prints each listed path as PATH<TAB>PATTERN.
# Exit 2: cannot tell (list or file list unreadable, list empty). Callers treat
#         this as listed: failing open here skips the review.
#
# Plain bash 3.2: macOS ships it, and an agent's shell may be zsh, where
# `shopt` does not exist and `$g` on the right of == is not a glob.
set -uo pipefail

# Only wayfare-skills' workflow reads the list (it keys on $REPO), so a list
# elsewhere decides nothing and must not stop a PR the workflow would approve.
LIST_REPO="ai-hero/wayfare-skills"

match() { # LIST_FILE PATHS_FILE
  local n=0 pat f hit=0
  local pats=()
  # `|| [ -n "$pat" ]`: read fails on a last line with no newline.
  while IFS= read -r pat || [ -n "$pat" ]; do
    pats[n]="$pat"
    n=$((n + 1))
  done < <(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; /^(#|$)/d' "$1" | tr -d '\r')
  [ "$n" -gt 0 ] || { echo "human-review-paths: list has no entries" >&2; return 2; }
  shopt -s nocasematch
  while IFS= read -r f || [ -n "$f" ]; do
    [ -n "$f" ] || continue
    local i=0
    while [ "$i" -lt "$n" ]; do
      # Unquoted on purpose: the right side of == is a glob, and `*` crosses /.
      # shellcheck disable=SC2053
      if [[ $f == ${pats[i]} ]]; then
        printf '%s\t%s\n' "$f" "${pats[i]}"
        hit=1
        break
      fi
      i=$((i + 1))
    done
  done < "$2"
  shopt -u nocasematch
  [ "$hit" -eq 0 ] || return 1
  return 0
}

case "${1:-}" in
  -h | --help) sed -n '5,20p' "$0"; exit 0 ;;
  --match) match "$2" "$3"; exit $? ;;
  '') echo "usage: human-review-paths.sh PR_NUMBER [OWNER/REPO]" >&2; exit 2 ;;
esac

PR="$1"
REPO="${2:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)}" || REPO=""
[ -n "$REPO" ] || { echo "human-review-paths: cannot tell which repo this is" >&2; exit 2; }
[ "$REPO" = "$LIST_REPO" ] || exit 0

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# refs/heads/main, never the PR's base: a base can be a branch the author
# controls, and a bare `main` resolves a same-named tag first.
gh api -H "Accept: application/vnd.github.raw" \
  "/repos/$REPO/contents/.github/auto-approve-human-review.txt?ref=refs/heads/main" \
  > "$TMP/list" || { echo "human-review-paths: cannot read the list at main" >&2; exit 2; }
# Paginated, and a rename's old path too: moving a listed file away counts.
gh api --paginate "/repos/$REPO/pulls/$PR/files?per_page=100" --jq '.[] | [.filename, .previous_filename // ""] | @json' \
  > "$TMP/files" || { echo "human-review-paths: cannot list the PR's files" >&2; exit 2; }
# The endpoint stops at 3000 files with no error; a short list is not a
# smaller PR.
want=$(gh api "/repos/$REPO/pulls/$PR" --jq .changed_files) || want=""
seen=$(grep -c . "$TMP/files")
[ -n "$want" ] && [ "$seen" = "$want" ] && [ "$seen" -gt 0 ] || {
  echo "human-review-paths: saw $seen of ${want:-?} changed files" >&2
  exit 2
}
jq -r '.[] | select(. != "")' "$TMP/files" > "$TMP/paths" || exit 2
match "$TMP/list" "$TMP/paths"
