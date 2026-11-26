#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Install the Claude Approvals policy into a target repository.
#
# Usage: ./install-approvals.sh [TARGET_REPO_ROOT]
#   If TARGET_REPO_ROOT is omitted, uses the current git repo's toplevel.
#
# Exit codes extend install-auto-approve.sh's with 4 and 5; callers branch on them:
#   0  installed, or already up to date, and git will commit it (safe to stage)
#   2  do NOT stage: a different approvals.yaml exists (a .new is written beside
#      it), or an approvals.yml shadows it (nothing is written)
#   4  installed, but the repo's .gitignore hides it (fix it, re-run, stage on 0)
#   5  installed, but git could not say whether it is ignored (not a repo, git
#      missing or refusing the repo); verify by hand before staging
#   3  the plugin's own source is missing (the plugin is broken)
#   1  anything else, e.g. the target filesystem rejected the write

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$PLUGIN_ROOT/assets/approvals/approvals.yaml"

if [[ ! -f "$SOURCE" ]]; then
  echo "ERROR: source file not found at $SOURCE" >&2
  exit 3
fi

TARGET_ROOT="${1:-$(git rev-parse --show-toplevel)}"
TARGET_DIR="$TARGET_ROOT/.claude"
TARGET="$TARGET_DIR/approvals.yaml"

if [[ -f "$TARGET_DIR/approvals.yml" ]]; then
  echo "EXISTS: $TARGET_DIR/approvals.yml"
  echo "  Claude Approvals reads it ahead of approvals.yaml, so the vendored"
  echo "  policy would never apply. Compare it with $SOURCE and remove it."
  exit 2
fi

refuse_symlinked() { # PATH under TARGET_ROOT
  local p="$TARGET_ROOT" part parts
  IFS=/ read -ra parts <<<"${1#"$TARGET_ROOT"/}"
  for part in "${parts[@]}"; do
    p="$p/$part"
    if [[ -L "$p" ]]; then
      echo "ERROR: $p is a symlink; refusing to write through it" >&2
      exit 1
    fi
  done
}

write_file() { # SRC DST
  local tmp
  tmp=$(mktemp "$(dirname "$2")/.$(basename "$2").XXXXXX")
  if cp "$1" "$tmp" && chmod 644 "$tmp" && mv "$tmp" "$2"; then
    return 0
  fi
  rm -f "$tmp"
  return 1
}

refuse_symlinked "$TARGET"
refuse_symlinked "$TARGET.new"

mkdir -p "$TARGET_DIR"

post_install_notes() {
  echo ""
  echo "Claude Approvals reads the policy from the default branch, and only once"
  echo "the Claude GitHub App is installed on the repo. Merge this file first."
}

# The fleet's .gitignore ignores `.claude/*` and re-includes chosen children,
# so without its own `!` line the policy is written, never committed, and
# Approvals never sees it while the working tree looks correct. Anything git
# cannot answer is "unknown", never "clear": reading an error as "not ignored"
# reported safe-to-stage for a file git would skip.
ignore_state() {
  git -C "$TARGET_ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo unknown; return; }
  # Tracked beats ignored: check-ignore --no-index still matches a file that
  # was force-added, which would read as exit 4 on every run.
  if git -C "$TARGET_ROOT" ls-files --error-unmatch .claude/approvals.yaml >/dev/null 2>&1; then
    echo clear
    return
  fi
  local rc=0
  git -C "$TARGET_ROOT" check-ignore -q --no-index .claude/approvals.yaml || rc=$?
  case "$rc" in
    0) echo ignored ;;
    1) echo clear ;;
    *) echo unknown ;;
  esac
}

ignored_hint() {
  echo ""
  echo "IGNORED: .gitignore hides .claude/approvals.yaml. Add this line after the"
  echo "  other !.claude/ lines:"
  echo "    !.claude/approvals.yaml"
  echo "  A bare '.claude/' line excludes the folder itself and no '!' line can"
  echo "  reach inside it; change it to '.claude/*' first."
}

exit_by_ignore_state() {
  case "$(ignore_state)" in
    clear) post_install_notes; exit 0 ;;
    ignored) ignored_hint; post_install_notes; exit 4 ;;
    *)
      echo ""
      echo "UNVERIFIED: git could not say whether .claude/approvals.yaml is ignored."
      echo "  Run 'git check-ignore -v --no-index .claude/approvals.yaml' in the repo."
      post_install_notes
      exit 5
      ;;
  esac
}

if [[ -f "$TARGET" ]] && cmp -s "$SOURCE" "$TARGET"; then
  echo "OK: $TARGET already up to date"
  exit_by_ignore_state
fi

if [[ -f "$TARGET" ]]; then
  write_file "$SOURCE" "$TARGET.new"
  echo "EXISTS: $TARGET"
  echo "  Wrote new version to $TARGET.new"
  echo "  Diff:    diff -u $TARGET $TARGET.new"
  echo "  REPLACE: mv $TARGET.new $TARGET"
  [[ "$(ignore_state)" == ignored ]] && ignored_hint
  exit 2
fi

write_file "$SOURCE" "$TARGET"
echo "INSTALLED: $TARGET"
exit_by_ignore_state
