#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# analysis/ingest/fleet.py resolves ROOT at import, by the same rule as
# hero_fleet_root and audit.py's fleet_root: a folder holding a map
# (.fleet/FLEET.md, or the legacy top-level FLEET.md) inside a git work tree is
# a clone's content and is passed over.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FLEET_PY="$REPO/analysis/ingest/fleet.py"

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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
WORK="$(cd "$WORK" && pwd -P)"

root_from() { # DIR -> the ROOT fleet.py resolves when imported from DIR
  (cd "$1" && python3 -I -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("fleet", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.ROOT)
' "$FLEET_PY" 2>/dev/null)
}

FLEET="$WORK/fleet"
CLONE="$FLEET/clone"
mkdir -p "$CLONE/.fleet" "$FLEET/.fleet/sub"
printf '# Fleet\n\n## Fleet\n\n## Repos\n' > "$FLEET/.fleet/FLEET.md"
git -C "$FLEET/.fleet" init -q
printf '# Cloned FLEET.md\n\n## Fleet\n\n## Repos\n' > "$CLONE/.fleet/FLEET.md"
git -C "$CLONE" init -q
git -C "$CLONE" add .fleet/FLEET.md
git -C "$CLONE" -c user.name=t -c user.email=t@example.com commit -q -m init

unset WAYFARE_FLEET_ROOT
check "clone committing .fleet/FLEET.md is passed over, walk reaches the fleet" "$FLEET" "$(root_from "$CLONE")"
check "fleet folder outside any work tree resolves" "$FLEET" "$(root_from "$FLEET")"
check "a walk from inside the register lands on the fleet folder" "$FLEET" "$(root_from "$FLEET/.fleet/sub")"
check "WAYFARE_FLEET_ROOT overrides" "$CLONE" "$(WAYFARE_FLEET_ROOT="$CLONE" root_from "$CLONE")"

# The legacy top-level FLEET.md, read until .fleet/FLEET.md exists; delete with
# the fallback in fleet_map().
mv "$FLEET/.fleet/FLEET.md" "$FLEET/FLEET.md"
check "a legacy top-level FLEET.md still resolves" "$FLEET" "$(root_from "$CLONE")"
git -C "$CLONE" mv .fleet/FLEET.md FLEET.md
check "a clone committing a legacy FLEET.md is passed over too" "$FLEET" "$(root_from "$CLONE")"

rm "$FLEET/FLEET.md"
check "clone alone resolves no fleet" "" "$(root_from "$CLONE")"

if [ "$FAIL" -gt 0 ]; then
  echo "ingest-fleet: $PASS passed, $FAIL FAILED"
  exit 1
fi
echo "ingest-fleet: $PASS passed"
