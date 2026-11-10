#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# check-floors.sh: SessionStart hook. Warn when a tool the fleet's setup.yaml
# floors is installed below that floor, such as cloudflared before an
# advisory's fixed release.
#
# Runs `fleet-setup.py check --floors-only` from the nearest folder above the
# session's cwd that holds a .fleet/ register checkout. That mode reads the
# register's origin/main as last fetched and never fetches: a network call at
# every session start would cost seconds. A raised floor reaches this machine
# with its next fetch of the register.
#
# Input: the SessionStart hook JSON on stdin. Output: nothing, or one JSON
# object that shows the warnings to the person and to the agent. Every failure
# path exits 0 silently: a broken hook must never get in a session's way.

set -uo pipefail

command -v uv >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)

CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$CWD" ] || CWD=$PWD
FLEET=$(cd "$CWD" 2>/dev/null && pwd -P) || exit 0
while [ ! -d "$FLEET/.fleet/.git" ]; do
  [ "$FLEET" = / ] && exit 0
  FLEET=$(dirname "$FLEET")
done

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# --offline: a cold uv cache must not turn into a download at session start;
# it fails, and failing here is silence.
OUT=$(cd "$PLUGIN_ROOT" && env -u VIRTUAL_ENV -u CONDA_PREFIX -u UV_PYTHON -u UV_PROJECT_ENVIRONMENT \
  uv run --offline --no-config --quiet scripts/fleet-setup.py --fleet "$FLEET" check --floors-only 2>/dev/null) || exit 0
[ -n "$OUT" ] || exit 0

MSG="wayfare: below a fleet version floor (from $FLEET/.fleet setup.yaml):
$OUT"
jq -n --arg m "$MSG" '{systemMessage: $m, hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $m}}'
exit 0
