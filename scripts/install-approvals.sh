#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Install the Claude Approvals policy into a target repository.
#
# Usage: ./install-approvals.sh [TARGET_REPO_ROOT]
#   If TARGET_REPO_ROOT is omitted, uses the current git repo's toplevel.
#
# Exit codes extend install-auto-approve.sh's with 4, and callers branch on them:
#   0  installed, or already up to date (safe to stage)
#   2  a different file exists; .new written beside it (do NOT stage)
#   3  the plugin's own source is missing (the plugin is broken)
#   1  anything else, e.g. the target filesystem rejected the write
#   4  installed, but the repo's .gitignore hides it (do NOT stage until fixed)

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

# Approvals reads approvals.yml ahead of approvals.yaml, so the vendored .yaml
# (PLACE-06) beside an existing .yml would never be read.
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

# The fleet's .gitignore ignores `.claude/*` and re-includes chosen children,
# so without its own `!` line the policy is written, never committed, and
# Approvals never sees it while the working tree looks correct.
exit_if_ignored() {
  if git -C "$TARGET_ROOT" rev-parse --git-dir >/dev/null 2>&1 \
    && git -C "$TARGET_ROOT" check-ignore -q --no-index .claude/approvals.yaml; then
    echo ""
    echo "IGNORED: .gitignore hides .claude/approvals.yaml."
    echo "  Add this line after the other !.claude/ lines, then stage:"
    echo "    !.claude/approvals.yaml"
    exit 4
  fi
}

if [[ -f "$TARGET" ]] && cmp -s "$SOURCE" "$TARGET"; then
  echo "OK: $TARGET already up to date"
  exit_if_ignored
  exit 0
fi

if [[ -f "$TARGET" ]]; then
  write_file "$SOURCE" "$TARGET.new"
  echo "EXISTS: $TARGET"
  echo "  Wrote new version to $TARGET.new"
  echo "  Diff:    diff -u $TARGET $TARGET.new"
  echo "  REPLACE: mv $TARGET.new $TARGET"
  exit 2
fi

write_file "$SOURCE" "$TARGET"
echo "INSTALLED: $TARGET"
exit_if_ignored
echo ""
echo "Claude Approvals reads the policy from the default branch, and only once"
echo "the Claude GitHub App is installed on the repo. Merge this file first."
