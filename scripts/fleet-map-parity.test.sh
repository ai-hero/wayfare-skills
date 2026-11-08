#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# The fleet map's path is resolved by three functions that must agree:
# hero_fleet_map (scripts/hero-lib.sh), fleet_map() in scripts/audit.py and
# fleet_map() in analysis/ingest/fleet.py. A case where one reads the legacy
# copy and another reports an error is a fleet that the skills, the audit and
# the analysis each see differently, with no message. Each case runs all three
# on one fixture and compares what they found and which note they printed.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
. "$REPO/scripts/hero-lib.sh" || { echo "cannot source hero-lib.sh"; exit 1; }
UV="$(command -v uv)" || { echo "fleet-map-parity: uv missing (https://docs.astral.sh/uv/)"; exit 1; }

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
trap 'chmod -R u+rwx "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
WORK="$(cd "$WORK" && pwd -P)"
GOOD="$WORK/good"; mkdir -p "$GOOD/.fleet"; printf '## Fleet\n' > "$GOOD/.fleet/FLEET.md"

# what DIR found: new | legacy | none | error, then the note: legacy | ignoring | -
classify() { # DIR RC OUT ERR
  local kind note=-
  case "$2" in
    0) case "$3" in "$1/.fleet/FLEET.md") kind=new ;; "$1/FLEET.md") kind=legacy ;; *) kind="?$3" ;; esac ;;
    1) kind=none ;;
    *) kind=error ;;
  esac
  case "$4" in *"reading legacy"*) note=legacy ;; *ignoring*) note=ignoring ;; esac
  printf '%s %s' "$kind" "$note"
}

shell_says() { # DIR
  local out err rc
  err=$( { out=$(hero_fleet_map "$1"); rc=$?; printf '%s\n' "$out" > "$WORK/out"; exit "$rc"; } 2>&1 ); rc=$?
  classify "$1" "$rc" "$(cat "$WORK/out")" "$err"
}

py_says() { # MODULE_PATH DIR
  local out err rc
  # The module's own inline metadata supplies its dependencies (pyyaml for
  # audit.py), so this cannot pass on a set the module does not declare.
  err=$(cd "$WORK" && WAYFARE_FLEET_ROOT="$GOOD" "$UV" run --quiet --no-project --with-requirements "$1" python -I -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("m", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules.setdefault("audit", m)
spec.loader.exec_module(m)
try:
    p = m.fleet_map(sys.argv[2])
except m.FleetMapError:
    sys.exit(2)
if p is None:
    sys.exit(1)
open(sys.argv[3], "w").write(str(p))
' "$1" "$2" "$WORK/out" 2>&1 >/dev/null); rc=$?
  [ "$rc" = 0 ] || : > "$WORK/out"
  # importing audit.py from a non-repo folder prints nothing; anything else on
  # stderr besides the notes is a crash, which must not read as a kind.
  case "$rc" in 0|1|2) ;; *) printf 'crash %s' "$rc"; return ;; esac
  classify "$2" "$rc" "$(cat "$WORK/out")" "$err"
}

agree() { # NAME DIR EXPECTED
  check "parity: $1: hero_fleet_map" "$3" "$(shell_says "$2")"
  check "parity: $1: audit.fleet_map" "$3" "$(py_says "$REPO/scripts/audit.py" "$2")"
  check "parity: $1: ingest fleet_map" "$3" "$(py_says "$REPO/analysis/ingest/fleet.py" "$2")"
}

D="$WORK/new"; mkdir -p "$D/.fleet"; printf '## Fleet\n' > "$D/.fleet/FLEET.md"
agree "new only" "$D" "new -"
D="$WORK/legacy"; mkdir -p "$D"; printf '## Fleet\n' > "$D/FLEET.md"
agree "legacy only" "$D" "legacy legacy"
D="$WORK/both"; mkdir -p "$D/.fleet"; printf '## Fleet\n' > "$D/.fleet/FLEET.md"; printf '## Fleet\n' > "$D/FLEET.md"
agree "both" "$D" "new ignoring"
D="$WORK/empty"; mkdir -p "$D/.fleet"
agree "an empty .fleet/" "$D" "none -"
D="$WORK/dir"; mkdir -p "$D/.fleet/FLEET.md"; printf '## Fleet\n' > "$D/FLEET.md"
agree "a .fleet/FLEET.md directory, legacy present" "$D" "error -"
D="$WORK/dangling"; mkdir -p "$D/.fleet"; ln -s "$D/.fleet/nowhere" "$D/.fleet/FLEET.md"; printf '## Fleet\n' > "$D/FLEET.md"
agree "a dangling .fleet/FLEET.md link, legacy present" "$D" "error -"
D="$WORK/reallink"; mkdir -p "$D/.fleet"; printf '## Fleet\n' > "$WORK/other.md"; ln -s "$WORK/other.md" "$D/.fleet/FLEET.md"
agree "a .fleet/FLEET.md symlink to a readable map" "$D" "error -"
D="$WORK/linkedreg"; mkdir -p "$D" "$WORK/realreg"; printf '## Fleet\n' > "$WORK/realreg/FLEET.md"; ln -s "$WORK/realreg" "$D/.fleet"
agree "a symlinked .fleet/" "$D" "error -"
D="$WORK/unreadable"; mkdir -p "$D/.fleet"; printf '## Fleet\n' > "$D/.fleet/FLEET.md"; chmod 000 "$D/.fleet/FLEET.md"
if [ ! -r "$D/.fleet/FLEET.md" ]; then
  agree "an unreadable .fleet/FLEET.md" "$D" "error -"
fi
D="$WORK/reg/.fleet"; mkdir -p "$D"; printf '## Fleet\n' > "$D/FLEET.md"
agree "a folder named .fleet holding FLEET.md" "$D" "none -"

if [ "$FAIL" -gt 0 ]; then
  echo "fleet-map-parity: $PASS passed, $FAIL FAILED"
  exit 1
fi
echo "fleet-map-parity: $PASS passed"
