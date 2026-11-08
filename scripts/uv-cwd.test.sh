#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Every skill runs its Python through uv, and uv picks the interpreter from the
# directory it starts in: a committed .venv/bin/python, or a .python-version
# naming any path, runs before the script does. Skills start in a consumer
# repo, possibly one under review, so each call must cd to the plugin first.
# uv takes VIRTUAL_ENV, CONDA_PREFIX and UV_PYTHON ahead of any directory, and
# a session that activated the repo's venv exports them, so each call strips
# them too. This plants all of it in a fake consumer repo, runs every uv call
# the skills and references contain from there with those variables pointing
# at the plant, and fails if the planted interpreter ran.
#
# A fresh cache per case, because a script environment uv already built is
# reused without looking for an interpreter: on a shared cache only the first
# call is cold, and every later one would pass without being tested.
# Offline, so no case downloads anything: the interpreter is chosen before
# dependencies resolve, and that choice is what is under test.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
UV="$(command -v uv)" || { echo "uv-cwd.test.sh: uv missing (https://docs.astral.sh/uv/)"; exit 1; }
REAL_PY="$("$UV" python find '>=3.12')" || { echo "uv-cwd.test.sh: uv finds no python >= 3.12"; exit 1; }

PASS=0
FAIL=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL  %s\n      expected: [%s]\n      actual:   [%s]\n' "$1" "$2" "$3"
  fi
}

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
T="$(cd "$T" && pwd -P)"
# shellcheck disable=SC2046
unset $(git rev-parse --local-env-vars)
export UV_OFFLINE=1

R="$T/consumer"
MARK="$T/planted-interpreter-ran"
mkdir -p "$R/.venv/bin" "$R/bin"
for p in "$R/.venv/bin/python" "$R/bin/python3"; do
  # A fresh regular file in this run's own temp dir, never through a link:
  # writing through one would overwrite a real interpreter.
  [ ! -e "$p" ] && [ ! -L "$p" ] || { echo "uv-cwd.test.sh: $p already exists"; exit 1; }
  printf '#!/bin/sh\necho "$0 $*" >> "%s"\nexec "%s" "$@"\n' "$MARK" "$REAL_PY" > "$p"
  chmod +x "$p"
done
printf 'home = %s\nversion = 3.12.0\n' "$(dirname "$REAL_PY")" > "$R/.venv/pyvenv.cfg"
printf '%s\n' "$R/bin/python3" > "$R/.python-version"
git init -q "$R"

export WAYFARE_ROOT="$ROOT" CALLER_DIR="$R" SCRATCH="$T/scratch" FLEET_ROOT="$T/fleet"
export BODY=$'ok\n\n_Generated using wayfare._' MSG="fix: x" REPLY="ok" COMMENT_BODY="ok" TEXT="ok"
export PR_TITLE="fix: x" DEFAULT_BRANCH=main FINGERPRINT=fp
mkdir -p "$SCRATCH" "$FLEET_ROOT"
# What an activated venv or conda env in the consumer repo leaves exported.
export VIRTUAL_ENV="$R/.venv" CONDA_PREFIX="$R/.venv" UV_PYTHON="$R/.venv/bin/python" UV_PROJECT_ENVIRONMENT="$R/.venv"

ran_planted() { # COMMAND -> yes | no, running COMMAND in the consumer repo
  local cache
  rm -f "$MARK"
  cache="$(mktemp -d "$T/cache.XXXXXX")"
  (cd "$R" && UV_CACHE_DIR="$cache" bash -c "$1" </dev/null >/dev/null 2>&1)
  [ -e "$MARK" ] && echo yes || echo no
}

# The fixture must catch the hole, or every case below passes vacuously.
check "fixture: uv started in the consumer repo runs its interpreter" "yes" \
  "$(ran_planted 'uv run --quiet "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind comment --body-file - <<<"$BODY"')"

# Every uv command in the skills and references, as written. A command split
# with a trailing backslash is joined first; one quoted inline in prose is
# taken from its backticks.
CMDS="$T/cmds"
env -u VIRTUAL_ENV -u CONDA_PREFIX -u UV_PYTHON -u UV_PROJECT_ENVIRONMENT \
  "$UV" run --quiet --no-project --python "$REAL_PY" python -I - "$ROOT" > "$CMDS" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
for md in sorted([*root.glob("skills/**/*.md"), *root.glob("references/*.md")]):
    text = md.read_text().replace("\\\n", " ")
    for line in text.split("\n"):
        if "uv run" not in line or "WAYFARE_ROOT" not in line:
            continue
        spans = [s for s in re.findall(r"`([^`]*)`", line) if "uv run" in s]
        for cmd in spans or [line.strip()]:
            print(f"{md.relative_to(root)}\t{cmd}")
PY

FORM='(cd "$WAYFARE_ROOT" && env -u VIRTUAL_ENV -u CONDA_PREFIX -u UV_PYTHON -u UV_PROJECT_ENVIRONMENT uv run --no-config --quiet '
n=0
while IFS=$'\t' read -r file cmd; do
  n=$((n + 1))
  check "$file: the plugin-checkout form, environment stripped: $cmd" "yes" \
    "$(grep -qF "$FORM" <<<"$cmd" && echo yes || echo no)"
  check "$file: planted interpreter never runs: $cmd" "no" "$(ran_planted "$cmd")"
done < "$CMDS"
# A drifted extraction would find nothing and pass.
check "found the skills' uv calls" "yes" "$([ "$n" -ge 25 ] && echo yes || echo "only $n")"

if [ "$FAIL" -gt 0 ]; then
  echo "uv-cwd: $PASS passed, $FAIL FAILED"
  exit 1
fi
echo "uv-cwd: $PASS passed"
