#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Install the wayfare design-system enforcement layer into a target repository.
#
# Usage: ./install-design-system.sh [TARGET_REPO_ROOT]
#   If TARGET_REPO_ROOT is omitted, uses the current git repo's toplevel.
#
# Writes:
#   .claude/rules/design-system.md      path-scoped UI constraints
#   .claude/hooks/check-design-tokens.sh  PostToolUse token check
# and wires the hook into .claude/settings.json.
#
# Idempotent. Never overwrites a customized file: on drift it writes .new and
# exits 2 so the caller can diff and decide, same contract as
# install-auto-approve.sh.
#
# Exit codes:
#   0  everything installed or already up to date
#   1  source files missing, a target path is a symlink (nothing written),
#      or settings.json could not be wired
#   2  an existing file differs; .new written, caller must reconcile

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_RULE="$PLUGIN_ROOT/assets/design-system/rules/design-system.md"
SRC_HOOK="$PLUGIN_ROOT/assets/design-system/hooks/check-design-tokens.sh"
SRC_TEST="$PLUGIN_ROOT/assets/design-system/hooks/check-design-tokens.test.sh"
SRC_LOCAL_STUB="$PLUGIN_ROOT/assets/design-system/rules/design-system.local.stub.md"

for f in "$SRC_RULE" "$SRC_HOOK" "$SRC_TEST" "$SRC_LOCAL_STUB"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: source file not found at $f" >&2
    exit 1
  fi
done

TARGET_ROOT="${1:-$(git rev-parse --show-toplevel)}"
DRIFT=0

# A clone keeps a committed symlink, and cp writes through one, so a target
# repo could aim .claude, rules/, hooks/ or a file itself anywhere on this
# machine, ~/.claude/rules included. Refuse a link at any component of the
# path we write.
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

# copy_or_flag SOURCE TARGET: install, no-op, or flag drift.
copy_or_flag() {
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

# create_once SOURCE TARGET: unlike copy_or_flag, this NEVER compares or
# overwrites an existing file, drifted or not. design-system.local.md is
# repo-owned the instant it exists; the installer's only job is to make sure
# it exists at all. Treating it like the other vendored files (refuse-on-drift,
# write .new) would silently defeat its purpose the first time a re-vendor ran
# after a repo customized it. A .new would sit next to it forever, unread,
# because nothing prompts a reconciliation for a file nobody expects to change.
create_once() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    echo "OK: $dst exists (repo-owned; never modified by this installer)"
    return 0
  fi
  write_file "$src" "$dst"
  echo "INSTALLED: $dst (repo-owned from here: edit freely, re-vendoring never touches it)"
}

SETTINGS="$TARGET_ROOT/.claude/settings.json"

# Every path is checked before the first write, so a refusal leaves nothing
# half-installed.
for f in rules/design-system.md hooks/check-design-tokens.sh \
         hooks/check-design-tokens.test.sh; do
  refuse_symlinked "$TARGET_ROOT/.claude/$f"
  refuse_symlinked "$TARGET_ROOT/.claude/$f.new"
done
refuse_symlinked "$TARGET_ROOT/.claude/rules/design-system.local.md"
refuse_symlinked "$SETTINGS"

copy_or_flag "$SRC_RULE" "$TARGET_ROOT/.claude/rules/design-system.md"
copy_or_flag "$SRC_HOOK" "$TARGET_ROOT/.claude/hooks/check-design-tokens.sh"
chmod +x "$TARGET_ROOT/.claude/hooks/check-design-tokens.sh" 2>/dev/null || true
copy_or_flag "$SRC_TEST" "$TARGET_ROOT/.claude/hooks/check-design-tokens.test.sh"
chmod +x "$TARGET_ROOT/.claude/hooks/check-design-tokens.test.sh" 2>/dev/null || true
create_once "$SRC_LOCAL_STUB" "$TARGET_ROOT/.claude/rules/design-system.local.md"

# --- Wire the PostToolUse hook into .claude/settings.json ---------------------
# The inner quotes are part of the command string: the value is run through a
# shell, so an unquoted $CLAUDE_PROJECT_DIR word-splits on a clone whose path
# contains a space and the hook silently never runs.
HOOK_CMD='"$CLAUDE_PROJECT_DIR/.claude/hooks/check-design-tokens.sh"'

if ! command -v jq >/dev/null 2>&1; then
  echo ""
  echo "NOTE: jq not found, so could not wire the hook automatically."
  echo "Add this to $SETTINGS by hand:"
  echo '  "hooks": { "PostToolUse": [ { "matcher": "Write|Edit",'
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

# Match on the hook's PATH appearing in an existing command, not on exact
# string equality with $HOOK_CMD. A prior install (or a hand-edit) commonly
# writes ${CLAUDE_PROJECT_DIR} (braced) where this script's own HOOK_CMD is
# unbraced. Both expand identically in the shell that runs it, but an exact
# match sees them as different strings and adds a SECOND PostToolUse entry
# for the same hook, which then runs check-design-tokens.sh twice per edit.
# `// empty` drops a null/absent command (a hooks[] entry with no "command"
# key) before test() ever sees it, because test() throws on a non-string
# input, and
# an uncaught jq error here reads as "not wired", adding a duplicate entry
# next to a sibling hook that merely lacks a command field of its own.
if jq -e \
  '[.hooks.PostToolUse[]?.hooks[]?.command // empty] | any(test("check-design-tokens\\.sh"))' \
  "$SETTINGS" >/dev/null 2>&1; then
  echo "OK: PostToolUse hook already wired in $SETTINGS"
else
  TMP="$(mktemp)"
  jq --arg cmd "$HOOK_CMD" '
    .hooks //= {} |
    .hooks.PostToolUse //= [] |
    .hooks.PostToolUse += [{
      matcher: "Write|Edit",
      hooks: [{ type: "command", command: $cmd }]
    }]
  ' "$SETTINGS" > "$TMP"

  # Only replace the real file once jq produced valid JSON, a failed jq run
  # must not truncate the user's settings.
  if jq -e . "$TMP" >/dev/null 2>&1; then
    mv "$TMP" "$SETTINGS"
    echo "WIRED: PostToolUse hook added to $SETTINGS"
  else
    rm -f "$TMP"
    echo "ERROR: failed to update $SETTINGS; left unchanged." >&2
    exit 1
  fi
fi

# --- Warn if what we just wrote is gitignored -------------------------------
# A blanket `.claude/*` rule is common, and it makes these files local-only:
# the installer reports success, the rule works on this machine, and every
# teammate and CI agent silently gets nothing. Surface it loudly, a
# half-installed enforcement layer is worse than none, because it looks done.
IGNORED=()
if git -C "$TARGET_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  for f in .claude/rules/design-system.md .claude/rules/design-system.local.md \
           .claude/hooks/check-design-tokens.sh \
           .claude/hooks/check-design-tokens.test.sh .claude/settings.json; do
    if git -C "$TARGET_ROOT" check-ignore -q "$f" 2>/dev/null; then
      IGNORED+=("$f")
    fi
  done
fi

echo ""
echo "Design-system enforcement installed."
echo "  Rule:  .claude/rules/design-system.md  (loads on **/*.{tsx,jsx,css})"
echo "  Local: .claude/rules/design-system.local.md  (repo-owned; never overwritten,"
echo "         put facts specific to this repo here, not in design-system.md)"
echo "  Hook:  .claude/hooks/check-design-tokens.sh  (advisory: PostToolUse cannot"
echo "         block a call that already ran; mirror it in pre-commit for a gate)"
echo "  Test:  .claude/hooks/check-design-tokens.test.sh  (run it after editing the hook)"

if [[ ${#IGNORED[@]} -gt 0 ]]; then
  echo ""
  echo "WARNING: these files are gitignored, so they are LOCAL-ONLY:"
  printf '  - %s\n' "${IGNORED[@]}"
  echo ""
  echo "Enforcement will work on this machine and nowhere else. If the repo"
  echo "uses a blanket '.claude/*' rule, add negations so clones inherit them:"
  echo "  !.claude/rules/"
  echo "  !.claude/hooks/"
  echo "  !.claude/settings.json"
  echo "(Keep .claude/settings.local.json ignored; that one is personal.)"
fi

[[ $DRIFT -eq 1 ]] && exit 2
exit 0
