#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# analysis/ingest/fleet.py resolves ROOT at import, by the same rule as
# hero_fleet_root and audit.py's fleet_root: a folder holding .fleet/FLEET.md
# inside a git work tree is a clone's content and is passed over, and a
# top-level FLEET.md is never a map.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FLEET_PY="$REPO/analysis/ingest/fleet.py"
UV="$(command -v uv)" || { echo "ingest-fleet: uv missing (https://docs.astral.sh/uv/)"; exit 1; }

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
  (cd "$1" && "$UV" run --quiet --no-project --with-requirements "$FLEET_PY" python -I -c '
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

cp "$FLEET/.fleet/FLEET.md" "$FLEET/FLEET.md"
check "a leftover top-level copy beside .fleet/FLEET.md changes nothing" "$FLEET" "$(root_from "$CLONE")"
rm "$FLEET/.fleet/FLEET.md"
check "a top-level FLEET.md alone is no fleet" "" "$(root_from "$FLEET")"

rm "$FLEET/FLEET.md"
check "clone alone resolves no fleet" "" "$(root_from "$CLONE")"

# A register that is not a git checkout: a folder named .fleet is never the
# root, so the walk from inside it lands on its parent.
PLAIN="$WORK/plainfleet"
mkdir -p "$PLAIN/.fleet/sub"
printf '# Fleet\n\n## Fleet\n' > "$PLAIN/.fleet/FLEET.md"
check "from a plain .fleet/ lands on its parent" "$PLAIN" "$(root_from "$PLAIN/.fleet")"
check "from a plain .fleet/sub lands on the fleet folder" "$PLAIN" "$(root_from "$PLAIN/.fleet/sub")"

# Present but unreadable stops the import with the file named, even with a
# top-level copy beside it.
rm "$PLAIN/.fleet/FLEET.md"; mkdir "$PLAIN/.fleet/FLEET.md"; printf '## Fleet\n' > "$PLAIN/FLEET.md"
check "an unreadable .fleet/FLEET.md resolves no root" "" "$(root_from "$PLAIN")"
ERR=$(cd "$PLAIN" && "$UV" run --quiet --no-project --with-requirements "$FLEET_PY" python -I -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("fleet", sys.argv[1])
spec.loader.exec_module(importlib.util.module_from_spec(spec))
' "$FLEET_PY" 2>&1 >/dev/null)
check "an unreadable .fleet/FLEET.md is named" "1" "$(printf '%s\n' "$ERR" | grep -c 'not a readable file')"

if [ "$FAIL" -gt 0 ]; then
  echo "ingest-fleet: $PASS passed, $FAIL FAILED"
  exit 1
fi
echo "ingest-fleet: $PASS passed"
