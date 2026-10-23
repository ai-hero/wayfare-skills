#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Install the auto-approve CALLER into a target repository.
#
# Usage: ./install-auto-approve.sh [TARGET_REPO_ROOT]
#   If TARGET_REPO_ROOT is omitted, uses the current git repo's toplevel.
#
# SOURCE is the CALLER, not this repo's own .github/workflows/auto-approve.yaml.
# Point it at the logic and every target repo gets a private copy of the shared
# workflow, which then drifts, including past security fixes made here.
#
# Idempotent: if the target file already matches the source, no-op.
# An existing file is never overwritten: the new version lands beside it as
# .new and the operator decides.
#
# Exit codes are a contract, wayfare-init-repo (references/init.md) branches on them:
#   0  installed, or already up to date (safe to stage)
#   2  a different file exists; .new written beside it (do NOT stage)
#   3  the plugin's own source is missing (the plugin is broken)
#   1  anything else, e.g. the target filesystem rejected the write

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$PLUGIN_ROOT/assets/auto-approve/caller.yaml"

if [[ ! -f "$SOURCE" ]]; then
  echo "ERROR: source file not found at $SOURCE" >&2
  # Distinct from 1: "the plugin is incompletely installed" and "the write
  # failed" need different fixes, and 1 is what set -e gives us for the latter.
  exit 3
fi

# Printed on BOTH the fresh-install and the already-exists paths. Every repo
# migrating off an inline copy takes the exit-2 path, so guidance that prints
# only after a fresh cp reaches nobody who is actually migrating.
post_install_notes() {
  echo ""
  echo "Reminder: GitHub only triggers issue_comment workflows that already"
  echo "exist on the default branch. Commit and merge this file before"
  echo "@auto-approve will work on PRs."
  echo ""
  echo "The target repo needs an ANTHROPIC_API_KEY secret (org-level is fine),"
  echo "and must be PRIVATE. The caller is gated on it, and on a public repo"
  echo "@auto-approve produces a skipped run with no error anywhere."
}

TARGET_ROOT="${1:-$(git rev-parse --show-toplevel)}"
TARGET_DIR="$TARGET_ROOT/.github/workflows"

# Adopt an existing workflow under EITHER spelling as the target. GitHub runs
# both, so writing auto-approve.yaml beside an existing auto-approve.yml does
# not "install" anything. It leaves two live issue_comment workflows, which
# means two Claude verifications and two review submissions per @auto-approve
# comment, and ship-pr polling whichever of the two same-named workflows the
# API happens to return first. Every guard below is keyed to TARGET, so a
# TARGET that cannot see the existing file has no guard at all.
# .yaml is the fleet standard (PLACE-06). This is only the default for
# a repo that has neither spelling yet, the loop below still adopts an
# existing .yml rather than writing a second live workflow beside it.
TARGET="$TARGET_DIR/auto-approve.yaml"
for ext in yaml yml; do
  if [[ -f "$TARGET_DIR/auto-approve.$ext" ]]; then
    TARGET="$TARGET_DIR/auto-approve.$ext"
    break
  fi
done

# A clone keeps a committed symlink, and cp writes through one, so a target
# repo could aim .github, the workflows folder or the file itself anywhere on
# this machine. Refuse a link at any component of the path we write.
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

# Through a temp file in the same folder, so the final path is only ever
# replaced by rename, never opened for writing.
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

if [[ -f "$TARGET" ]] && cmp -s "$SOURCE" "$TARGET"; then
  echo "OK: $TARGET already up to date"
  exit 0
fi

if [[ -f "$TARGET" ]]; then
  write_file "$SOURCE" "$TARGET.new"
  echo "EXISTS: $TARGET"
  echo "  Wrote new version to $TARGET.new"
  echo "  Diff:    diff -u $TARGET $TARGET.new"
  echo "  REPLACE: mv $TARGET.new $TARGET"
  echo ""
  # Not "diff and merge". The existing file is almost always the old inline
  # logic; the new one is a caller. Merging them yields a job with both `uses:`
  # and `steps:`, which GitHub rejects as an invalid workflow file, and since
  # the trigger is issue_comment, nothing surfaces that until someone runs
  # ship-pr and gets a failure with no failing step.
  echo "  Replace it, do not merge it: the existing file is the old inline"
  echo "  logic and the new one is a caller. A job holding both 'uses:' and"
  echo "  'steps:' is an invalid workflow, and it fails silently until used."

  # Both spellings live -> the operator is one mv away from two live
  # issue_comment workflows, which is the state the adoption logic above
  # exists to avoid. It can detect that; say so rather than let them find out.
  OTHER=""
  [[ "$TARGET" == *.yaml ]] && OTHER="$TARGET_DIR/auto-approve.yml"
  [[ "$TARGET" == *.yml ]] && OTHER="$TARGET_DIR/auto-approve.yaml"
  if [[ -n "$OTHER" && -f "$OTHER" ]]; then
    echo ""
    echo "  WARNING: $OTHER also exists. GitHub runs both, so two verifications"
    echo "  and two review submissions per @auto-approve. Delete one."
  fi

  post_install_notes
  exit 2
fi

write_file "$SOURCE" "$TARGET"
echo "INSTALLED: $TARGET"
post_install_notes
