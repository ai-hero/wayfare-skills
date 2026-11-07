#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for scripts/security_audit_upstream.py. Every case runs on a copy of the
# script and the vendored tree, and every network call goes to a fake `gh`, so
# the suite is offline.
#
# Not -e: cases assert on non-zero exit codes.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
PY="$(command -v python3)"

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
check_contains() { # name haystack needle
  if grep -qF -- "$3" <<< "$2"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL  %s\n      expected to contain: [%s]\n      in: [%s]\n' "$1" "$3" "$2"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK:?}"' EXIT

API="$WORK/api"
FAKEBIN="$WORK/bin"
EMPTYBIN="$WORK/empty"
mkdir -p "$API" "$FAKEBIN" "$EMPTYBIN"

# A fake `gh api PATH`: answers from a file named after PATH, logs every call.
cat > "$FAKEBIN/gh" <<GH
#!/bin/bash
echo "\$2" >> "$WORK/gh.log"
[ -e "$WORK/gh-down" ] && { echo "fake gh: down" >&2; exit 1; }
f="$API/\$(printf '%s' "\$2" | tr '/.' '__')"
[ -f "\$f" ] || { echo "fake gh: no answer for \$2" >&2; exit 1; }
cat "\$f"
GH
chmod +x "$FAKEBIN/gh"

R=cloudflare/security-audit-skill
PIN=$(sed -n 's/^sha: //p' "$REPO/assets/security-audit/UPSTREAM")
NEW=1111111111111111111111111111111111111111

api_file() { # API_PATH -> the file the fake gh serves it from
  printf '%s/%s' "$API" "$(printf '%s' "$1" | tr '/.' '__')"
}
answer() { # API_PATH, body on stdin
  cat > "$(api_file "$1")"
}
days_ago() { # N -> an ISO date N days ago
  "$PY" -c 'import datetime,sys; print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=float(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$1"
}
commit_json() { # SHA DATE
  printf '{"sha":"%s","commit":{"message":"subject line\\n\\nbody","author":{"date":"%s"},"committer":{"date":"%s"}}}' "$1" "$2" "$2"
}

fixture() { # -> path to a fresh copy of the script and vendored tree
  local d
  d=$(mktemp -d "$WORK/fx.XXXXXX")
  mkdir -p "$d/scripts" "$d/assets"
  cp "$REPO/scripts/security_audit_upstream.py" "$d/scripts/"
  cp -R "$REPO/assets/security-audit" "$d/assets/security-audit"
  echo "$d"
}
run() { # DIR ARGS... -> sets OUT and RC; the fake gh comes first on PATH
  local d="$1"; shift
  OUT=$(PATH="$FAKEBIN:/usr/bin:/bin" "$PY" "$d/scripts/security_audit_upstream.py" "$@" 2>&1)
  RC=$?
}
tree_hash() { # DIR -> one hash over the whole vendored directory
  (cd "$1/assets/security-audit" && find . -type f | LC_ALL=C sort | xargs cat | "$PY" -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
}
make_tarball() { # SHA MUTATOR -> writes the tarball answer; the mutator edits the staged tree
  local stage
  stage=$(mktemp -d "$WORK/stage.XXXXXX")
  mkdir -p "$stage/up-x/skills"
  cp -R "$REPO/assets/security-audit/skill" "$stage/up-x/skills/security-audit"
  cp "$REPO/assets/security-audit/LICENSE" "$stage/up-x/LICENSE"
  printf 'not vendored\n' > "$stage/up-x/README.md"
  "$2" "$stage/up-x"
  # COPYFILE_DISABLE: macOS tar otherwise adds a ._ member per file with xattrs.
  COPYFILE_DISABLE=1 tar -czf "$(api_file "repos/$R/tarball/$1")" -C "$stage" up-x
}

# ---------- verify: offline, and every kind of drift fails ------------------

d=$(fixture)
: > "$WORK/gh.log"
run "$d" verify
check "clean: rc" "0" "$RC"
check_contains "clean: tag" "$OUT" "VENDORED_OK"
check "verify makes no network call" "" "$(cat "$WORK/gh.log")"

d=$(fixture)
"$PY" - "$d/assets/security-audit/skill/ATTACK-CLASSES.md" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
b[100] ^= 1
open(p, "wb").write(bytes(b))
PY
run "$d" verify
check "one-byte edit: rc" "1" "$RC"
check_contains "one-byte edit: tag" "$OUT" "VENDORED_CHANGED skill/ATTACK-CLASSES.md"

d=$(fixture)
mv "$d/assets/security-audit/skill/HUNTING.md" "$d/gone"
run "$d" verify
check "missing file: rc" "1" "$RC"
check_contains "missing file: tag" "$OUT" "VENDORED_MISSING skill/HUNTING.md"

d=$(fixture)
printf 'x\n' > "$d/assets/security-audit/skill/NEW.md"
run "$d" verify
check "added file: rc" "1" "$RC"
check_contains "added file: tag" "$OUT" "VENDORED_ADDED skill/NEW.md"

d=$(fixture)
mkdir -p "$d/assets/security-audit/skill/sub/dir"
printf 'x\n' > "$d/assets/security-audit/skill/sub/dir/f.md"
run "$d" verify
check "added nested file: rc" "1" "$RC"
check_contains "added nested file: tag" "$OUT" "VENDORED_ADDED skill/sub/dir/f.md"

# What the formatters this tree is excluded from would do.
d=$(fixture)
printf '\n' >> "$d/assets/security-audit/skill/SKILL.md"
run "$d" verify
check "extra final newline: rc" "1" "$RC"

d=$(fixture)
"$PY" - "$d/assets/security-audit/skill/SKILL.md" <<'PY'
import sys
p = sys.argv[1]
b = open(p, "rb").read()
open(p, "wb").write(b.replace(b"\n", b"\r\n"))
PY
run "$d" verify
check "line endings rewritten: rc" "1" "$RC"

d=$(fixture)
chmod +x "$d/assets/security-audit/skill/SKILL.md"
run "$d" verify
check "mode change: rc" "1" "$RC"
check_contains "mode change: tag" "$OUT" "VENDORED_CHANGED skill/SKILL.md"

d=$(fixture)
mv "$d/assets/security-audit/skill/SKILL.md" "$d/gone"
ln -s /etc/hosts "$d/assets/security-audit/skill/SKILL.md"
run "$d" verify
check "symlink: rc" "1" "$RC"
check_contains "symlink: tag" "$OUT" "VENDORED_NOT_REGULAR skill/SKILL.md"

d=$(fixture)
printf 'x' >> "$d/assets/security-audit/LICENSE"
run "$d" verify
check "license edit: rc" "1" "$RC"

# Moving the pin by hand would claim a commit the tree was never compared with.
d=$(fixture)
sed "s/^sha: .*/sha: $NEW/" "$d/assets/security-audit/UPSTREAM" > "$d/u" && mv "$d/u" "$d/assets/security-audit/UPSTREAM"
run "$d" verify
check "pin edited alone: rc" "1" "$RC"
check_contains "pin edited alone: tag" "$OUT" "VENDORED_CHANGED UPSTREAM"

d=$(fixture)
mv "$d/assets/security-audit/MANIFEST.sha256" "$d/gone"
run "$d" verify
check "no manifest: rc" "1" "$RC"
check_contains "no manifest: tag" "$OUT" "MANIFEST_INVALID"

d=$(fixture)
sed '/skill\/SKILL.md/d' "$d/assets/security-audit/MANIFEST.sha256" > "$d/m" && mv "$d/m" "$d/assets/security-audit/MANIFEST.sha256"
run "$d" verify
check "manifest row removed: rc" "1" "$RC"
check_contains "manifest row removed: tag" "$OUT" "VENDORED_ADDED skill/SKILL.md"

# ---------- verify --upstream: the manifest against the pinned commit --------

keep() { :; }
make_tarball "$PIN" keep
d=$(fixture)
run "$d" verify --upstream
check "pin matches: rc" "0" "$RC"
check_contains "pin matches: tag" "$OUT" "PIN_OK"

tweak() { printf 'x' >> "$1/skills/security-audit/SKILL.md"; }
make_tarball "$PIN" tweak
run "$d" verify --upstream
check "pin mismatch: rc" "1" "$RC"
check_contains "pin mismatch: tag" "$OUT" "PIN_MISMATCH skill/SKILL.md"

# ---------- status ----------------------------------------------------------

printf '{"default_branch":"main"}' | answer "repos/$R"

d=$(fixture)
printf '{"status":"identical","ahead_by":0,"commits":[],"files":[]}' | answer "repos/$R/compare/$PIN...main"
run "$d" status
check "current: rc" "0" "$RC"
check_contains "current: tag" "$OUT" "UPSTREAM_CURRENT"

OLD_DATE=$(days_ago 30)
YOUNG_DATE=$(days_ago 1)
cat <<JSON | answer "repos/$R/compare/$PIN...main"
{"status":"ahead","ahead_by":2,
 "commits":[$(commit_json 2222222222222222222222222222222222222222 "$OLD_DATE"),$(commit_json "$NEW" "$YOUNG_DATE")],
 "files":[{"filename":"skills/security-audit/HUNTING.md","status":"modified"},{"filename":"README.md","status":"modified"}]}
JSON
run "$d" status
check "behind: rc" "0" "$RC"
check_contains "behind: tag" "$OUT" "UPSTREAM_BEHIND"
check_contains "behind: count" "$OUT" "2 commit(s) behind"
check_contains "behind: lists a commit" "$OUT" "22222222"
check_contains "behind: lists a vendored file" "$OUT" "* modified   skills/security-audit/HUNTING.md"
check_contains "behind: says the date is author-set" "$OUT" "set by the author's git client"
check_contains "behind: names the commit old enough" "$OUT" "refresh --to 2222222222222222222222222222222222222222"

run "$d" status --summary
check "summary: rc" "0" "$RC"
check "summary: one line" "1" "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')"

printf '{"status":"diverged","ahead_by":1,"commits":[],"files":[]}' | answer "repos/$R/compare/$PIN...main"
run "$d" status
check "diverged: rc" "1" "$RC"
check_contains "diverged: tag" "$OUT" "UPSTREAM_DIVERGED"

: > "$WORK/gh-down"
run "$d" status
check "API failure: rc" "2" "$RC"
check_contains "API failure: tag" "$OUT" "UPSTREAM_NOT_CHECKED"
mv "$WORK/gh-down" "$WORK/gh-up"

OUT=$(PATH="$EMPTYBIN" "$PY" "$d/scripts/security_audit_upstream.py" status 2>&1)
RC=$?
check "no gh: rc" "2" "$RC"
check_contains "no gh: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

printf 'not json' | answer "repos/$R"
run "$d" status
check "malformed API answer: rc" "2" "$RC"
printf '{"default_branch":"main"}' | answer "repos/$R"

# ---------- refresh ----------------------------------------------------------

setup_target() { # SHA DATE COMPARE_STATUS
  commit_json "$1" "$2" | answer "repos/$R/commits/$1"
  commit_json "$1" "$2" | answer "repos/$R/commits/main"
  printf '{"status":"%s"}' "$3" | answer "repos/$R/compare/$1...main"
  printf '{"status":"ahead"}' | answer "repos/$R/compare/$PIN...$1"
}
update() { # the upstream change a refresh should take
  printf 'an upstream change\n' >> "$1/skills/security-audit/HUNTING.md"
  printf 'new\n' > "$1/skills/security-audit/NEW-COMPANION.md"
  mv "$1/skills/security-audit/CLIENT-SIDE.md" "$1/moved-out.md"
}
make_tarball "$NEW" update

d=$(fixture)
BEFORE=$(tree_hash "$d")
setup_target "$NEW" "$(days_ago 6.9)" identical
run "$d" refresh
check "younger than 7 days: rc" "1" "$RC"
check_contains "younger than 7 days: tag" "$OUT" "REFRESH_REFUSED_TOO_NEW"
check_contains "younger than 7 days: says the date is author-set" "$OUT" "set by the author's git client"
check "younger than 7 days: tree untouched" "$BEFORE" "$(tree_hash "$d")"

setup_target "$NEW" "$(days_ago -3)" identical
run "$d" refresh
check "future date: rc" "1" "$RC"
check_contains "future date: tag" "$OUT" "REFRESH_REFUSED_TOO_NEW"

# One recent date of the two is enough to refuse: author and committer differ
# on a rebase, and either can be the honest one.
printf '{"sha":"%s","commit":{"message":"m","author":{"date":"%s"},"committer":{"date":"%s"}}}' "$NEW" "$(days_ago 30)" "$(days_ago 1)" | answer "repos/$R/commits/main"
run "$d" refresh
check "recent committer date: rc" "1" "$RC"
check_contains "recent committer date: tag" "$OUT" "REFRESH_REFUSED_TOO_NEW"

setup_target "$NEW" "$(days_ago 8)" diverged
run "$d" refresh --to "$NEW"
check "commit off the default branch: rc" "1" "$RC"
check_contains "commit off the default branch: tag" "$OUT" "REFRESH_REFUSED"
check "commit off the default branch: tree untouched" "$BEFORE" "$(tree_hash "$d")"

setup_target "$NEW" "$(days_ago 8)" identical
printf '{"status":"behind"}' | answer "repos/$R/compare/$PIN...$NEW"
run "$d" refresh --to "$NEW"
check "older than the pin: rc" "1" "$RC"
check_contains "older than the pin: tag" "$OUT" "older than the pin"
check "older than the pin: tree untouched" "$BEFORE" "$(tree_hash "$d")"

run "$d" refresh --to 'main;id'
check "--to that is not a SHA: rc" "1" "$RC"

add_link() { ln -s /etc/hosts "$1/skills/security-audit/link.md"; }
make_tarball "$NEW" add_link
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "symlink upstream: rc" "1" "$RC"
check_contains "symlink upstream: tag" "$OUT" "not a regular file"
check "symlink upstream: tree untouched" "$BEFORE" "$(tree_hash "$d")"

move_tree() { mv "$1/skills/security-audit" "$1/skills/other"; }
make_tarball "$NEW" move_tree
run "$d" refresh --to "$NEW"
check "tree moved upstream: rc" "1" "$RC"
check "tree moved upstream: tree untouched" "$BEFORE" "$(tree_hash "$d")"

make_tarball "$NEW" update
d=$(fixture)
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "refresh: rc" "0" "$RC"
check_contains "refresh: tag" "$OUT" "REFRESHED $NEW"
check_contains "refresh: says the date is author-set" "$OUT" "set by the author's git client"
check "refresh: pin moved" "$NEW" "$(sed -n 's/^sha: //p' "$d/assets/security-audit/UPSTREAM")"
check "refresh: change taken" "an upstream change" "$(tail -1 "$d/assets/security-audit/skill/HUNTING.md")"
check "refresh: added file taken" "new" "$(cat "$d/assets/security-audit/skill/NEW-COMPANION.md")"
check "refresh: removed file gone" "no" "$([ -e "$d/assets/security-audit/skill/CLIENT-SIDE.md" ] && echo yes || echo no)"
check "refresh: outside the tree not taken" "no" "$([ -e "$d/assets/security-audit/README.md" ] && echo yes || echo no)"
check "refresh: no temp left" "" "$(find "$d/assets" -name '.security-audit*')"
run "$d" verify
check "refresh: verify passes on the new tree" "0" "$RC"

# An update that renames something the wrapper skill names must not pass quietly.
rename_output() {
  "$PY" - "$1/skills/security-audit/SKILL.md" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(t.replace("FINDINGS-DETAIL.md", "DETAIL.md"))
PY
}
make_tarball "$NEW" rename_output
d=$(fixture)
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "wrapper contract broken: rc" "1" "$RC"
check_contains "wrapper contract broken: tag" "$OUT" "CONTRACT_MISSING skill/SKILL.md"
run "$d" verify
check "wrapper contract broken: verify keeps failing" "1" "$RC"

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
