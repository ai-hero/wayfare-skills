#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Advisory check for stale HERO.md.
#
# Compares the last-commit time of HERO.md against the last-commit time of
# files that affect the HERO.md schema (deps, CI, deploy, code quality, agent
# configs, task runners). If any of those is newer, prints a hint to stderr
# suggesting `wayfare:wayfare-init-repo recalibrate`.
#
# Always exits 0. This is purely informational.
#
# Usage: scripts/check-hero-staleness.sh
#
# Replaces the old hero-update-precommit.sh hook (which auto-ran Claude on
# every commit). Pre-commit was too slow; we let skills surface the hint
# on demand instead.
#
# Note: the daily-flow skills (wayfare-push-pr / wayfare-build-task) call hero_check_staleness
# in scripts/hero-lib.sh, a deliberately *fast subset* of this check. The two
# are meant to be roughly aligned but NOT byte-for-byte identical. This script
# can carry a longer pattern list (Cargo, ruff, biome, agent configs, etc.)
# without forcing the subset to match. New patterns added here do not
# automatically need to land there.

set -uo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# shellcheck source=/dev/null
. "$(dirname "${BASH_SOURCE[0]}")/hero-lib.sh" || exit 0
hero_config_exists "$ROOT" || exit 0

HERO_TIME=$(hero_config_commit_time "$ROOT" | grep -E '^[0-9]+$' || echo 0)
# Default-substitute any empty value (corrupt repo, env hijack, no commits) to
# 0. The `grep -E '^[0-9]+$'` already filters non-numeric output; this
# default + the grep together ensure the `(( arithmetic ))` compare below
# always sees a clean integer. Both are needed, because `set -u` would error
# on an empty value, and the arithmetic builtin would error on non-numerics.
HERO_TIME=${HERO_TIME:-0}

# Patterns that affect HERO.md fields. Mirrors the old hero-update-precommit
# gate so any commit that would have triggered an update is also caught here.
# `:(glob)**/foo` is git's magic pathspec for recursive matches. `*/foo`
# only matches one directory level deep, which silently misses nested
# subprojects in monorepos.
PATTERNS=(
  pyproject.toml ':(glob)**/pyproject.toml'
  package.json ':(glob)**/package.json'
  go.mod ':(glob)**/go.mod'
  Cargo.toml ':(glob)**/Cargo.toml'
  Gemfile ':(glob)**/Gemfile'
  'requirements*.txt' ':(glob)**/requirements*.txt'
  '.github/workflows'
  .gitlab-ci.yml
  Jenkinsfile
  .circleci
  Dockerfile ':(glob)**/Dockerfile'
  'docker-compose*.yml' ':(glob)**/docker-compose*.yml'
  k8s kubernetes deploy
  .pre-commit-config.yaml
  ruff.toml
  '.eslintrc*' 'eslint.config.*'
  tsconfig.json ':(glob)**/tsconfig.json'
  biome.json ':(glob)**/biome.json'
  '.prettierrc*'
  CLAUDE.md .claude
  .cursorrules .cursor
  .windsurfrules .windsurf
  .github/copilot-instructions.md
  Makefile justfile Taskfile.yml
)

# Find the most recent commit touching any of those paths.
NEWEST=$(git -C "$ROOT" log -1 --format=%ct -- "${PATTERNS[@]}" 2>/dev/null | grep -E '^[0-9]+$' || echo 0)
# Same default + numeric filter as HERO_TIME above.
NEWEST=${NEWEST:-0}

if (( NEWEST > HERO_TIME )); then
  cat >&2 <<'EOF'
note: HERO.md may be out of date — project config has changed since the last sync.
      Run `wayfare:wayfare-init-repo recalibrate` to refresh.
EOF
fi

exit 0
