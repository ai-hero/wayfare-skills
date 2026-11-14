#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Install the wayfare Stop hook into a target repository.
#
# Usage: ./install-stop-checks.sh [TARGET_REPO_ROOT]
#   If TARGET_REPO_ROOT is omitted, uses the current git repo's toplevel.
#
# Writes:
#   .claude/hooks/stop-checks.sh       Stop hook: runs `just check-fast`
#   .claude/hooks/stop-checks.test.sh  its regression table
# and wires the hook into .claude/settings.json. The target repo supplies the
# check-fast recipe; without one the hook warns once per session and passes.
#
# Idempotent. Never overwrites a customized file: on drift it writes .new and
# exits 2 so the caller can diff and decide, same contract as
# install-design-system.sh.
#
# Exit codes:
#   0  everything installed or already up to date
#   1  source files missing, a target path is a symlink (nothing written),
#      or settings.json could not be wired
#   2  an existing file differs; .new written, caller must reconcile

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_HOOK="$PLUGIN_ROOT/assets/stop-checks/hooks/stop-checks.sh"
SRC_TEST="$PLUGIN_ROOT/assets/stop-checks/hooks/stop-checks.test.sh"

for f in "$SRC_HOOK" "$SRC_TEST"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: source file not found at $f" >&2
    exit 1
  fi
done

TARGET_ROOT="${1:-$(git rev-parse --show-toplevel)}"
DRIFT=0

# A clone keeps a committed symlink, and cp writes through one, so a target
# repo could aim .claude, hooks/ or a file itself anywhere on this machine.
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
  if cp "$1" "$tmp" && chmod 755 "$tmp" && mv "$tmp" "$2"; then
    return 0
  fi
  rm -f "$tmp"
  return 1
}

copy_or_flag() { # SOURCE TARGET
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"

  if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
    echo "OK: $dst already up to date"
    return 0
  fi

  if [[ -f "$dst" ]]; then
    write_file "$src" "$dst.new"
    echo "EXISTS: $dst"
    echo "  Wrote new version to $dst.new"
    echo "  Diff:  diff -u $dst $dst.new"
    echo "  Apply: mv $dst.new $dst"
    DRIFT=1
    return 0
  fi

  write_file "$src" "$dst"
  echo "INSTALLED: $dst"
}

SETTINGS="$TARGET_ROOT/.claude/settings.json"

for f in hooks/stop-checks.sh hooks/stop-checks.test.sh; do
  refuse_symlinked "$TARGET_ROOT/.claude/$f"
  refuse_symlinked "$TARGET_ROOT/.claude/$f.new"
done
refuse_symlinked "$SETTINGS"

copy_or_flag "$SRC_HOOK" "$TARGET_ROOT/.claude/hooks/stop-checks.sh"
copy_or_flag "$SRC_TEST" "$TARGET_ROOT/.claude/hooks/stop-checks.test.sh"

# The inner quotes are part of the command string: the value is run through a
# shell, so an unquoted $CLAUDE_PROJECT_DIR word-splits on a clone whose path
# contains a space and the hook silently never runs.
HOOK_CMD='"$CLAUDE_PROJECT_DIR/.claude/hooks/stop-checks.sh"'

if ! command -v jq >/dev/null 2>&1; then
  echo ""
  echo "NOTE: jq not found, so could not wire the hook automatically."
  echo "Add this to $SETTINGS by hand:"
  echo '  "hooks": { "Stop": [ {'
  echo "    \"hooks\": [ { \"type\": \"command\", \"command\": \"$HOOK_CMD\" } ] } ] }"
  [[ $DRIFT -eq 1 ]] && exit 2
  exit 0
fi

mkdir -p "$(dirname "$SETTINGS")"
[[ -f "$SETTINGS" ]] || echo '{}' > "$SETTINGS"

if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
  echo "ERROR: $SETTINGS is not valid JSON; refusing to modify it." >&2
  echo "Fix the file, then re-run this installer." >&2
  exit 1
fi

# Matched on the path inside any command, not on equality with HOOK_CMD: a
# braced ${CLAUDE_PROJECT_DIR} spelling is the same hook, and an exact match
# would add a second entry that runs check-fast twice per stop.
if jq -e \
  '[.hooks.Stop[]?.hooks[]?.command // empty] | any(test("stop-checks\\.sh"))' \
  "$SETTINGS" >/dev/null 2>&1; then
  echo "OK: Stop hook already wired in $SETTINGS"
else
  TMP="$(mktemp)"
  jq --arg cmd "$HOOK_CMD" '
    .hooks //= {} |
    .hooks.Stop //= [] |
    .hooks.Stop += [{
      hooks: [{ type: "command", command: $cmd }]
    }]
  ' "$SETTINGS" > "$TMP"

  if jq -e . "$TMP" >/dev/null 2>&1; then
    mv "$TMP" "$SETTINGS"
    echo "WIRED: Stop hook added to $SETTINGS"
  else
    rm -f "$TMP"
    echo "ERROR: failed to update $SETTINGS; left unchanged." >&2
    exit 1
  fi
fi

if ! grep -Eq '^check-fast[[:space:]]*:' "$TARGET_ROOT/Justfile" 2>/dev/null; then
  echo ""
  echo "NOTE: no check-fast recipe in $TARGET_ROOT/Justfile, so the hook will"
  echo "warn once per session and check nothing. Add one with the checks that"
  echo "finish in seconds (formatter, vet, typecheck, lint); it runs on every stop."
fi

echo ""
echo "Stop checks installed."
echo "  Hook:  .claude/hooks/stop-checks.sh  (runs just check-fast; exit 2 keeps the agent working)"
echo "  Test:  .claude/hooks/stop-checks.test.sh  (run it after editing the hook)"

[[ $DRIFT -eq 1 ]] && exit 2
exit 0
