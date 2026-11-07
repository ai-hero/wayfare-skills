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

resync_row() { # DIR REL -> rewrites REL's manifest row to match the file, as a careful edit would
  "$PY" - "$1/assets/security-audit" "$2" <<'PY'
import hashlib, os, sys
root, rel = sys.argv[1], sys.argv[2]
digest = hashlib.sha256(open(os.path.join(root, rel), "rb").read()).hexdigest()
m = os.path.join(root, "MANIFEST.sha256")
rows = [f"{digest}  100644  {rel}" if l.endswith("  " + rel) else l for l in open(m).read().splitlines()]
open(m, "w").write("\n".join(rows) + "\n")
PY
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

d=$(fixture)
mv "$d/assets/security-audit/skill/SKILL.md" "$d/gone"
mkdir "$d/elsewhere"
ln -s "$d/elsewhere" "$d/assets/security-audit/skill/linked"
run "$d" verify
check "symlink to a directory: rc" "1" "$RC"
check_contains "symlink to a directory: tag" "$OUT" "VENDORED_NOT_REGULAR skill/linked"

d=$(fixture)
m="$d/assets/security-audit/MANIFEST.sha256"
{ printf '%064d  100644  LICENSE\n' 0; cat "$m"; } > "$d/m" && mv "$d/m" "$m"
run "$d" verify
check "duplicate manifest row: rc" "1" "$RC"
check_contains "duplicate manifest row: tag" "$OUT" "MANIFEST_INVALID"

d=$(fixture)
printf '\377\376' > "$d/assets/security-audit/MANIFEST.sha256"
run "$d" verify
check "non-UTF-8 manifest: rc" "1" "$RC"
check_contains "non-UTF-8 manifest: tag" "$OUT" "MANIFEST_INVALID"

# A pin moved with its manifest row still has to name this repo and a full SHA.
for bad in "s/^sha: .*/sha: abc1234/" "s#^repo: .*#repo: https://github.com/someone/fork#" "s#^path: .*#path: elsewhere#" "/^commit-date: /d"; do
  d=$(fixture)
  u="$d/assets/security-audit/UPSTREAM"
  sed "$bad" "$u" > "$d/u" && mv "$d/u" "$u"
  resync_row "$d" UPSTREAM
  run "$d" verify
  check "bad pin [$bad]: rc" "1" "$RC"
  check_contains "bad pin [$bad]: tag" "$OUT" "UPSTREAM_INVALID"
done

# A name cannot forge a clean line for whoever reads these lines back.
d=$(fixture)
printf 'x' > "$d/assets/security-audit/skill/$(printf 'x\nVENDORED_OK 22 files')"
run "$d" verify
check "newline in a file name: rc" "1" "$RC"
check "newline in a file name: no forged line" "no" "$(grep -q '^VENDORED_OK' <<< "$OUT" && echo yes || echo no)"

d=$(fixture)
chmod 000 "$d/assets/security-audit/LICENSE"
if [ -r "$d/assets/security-audit/LICENSE" ]; then
  PASS=$((PASS + 2))
else
  run "$d" verify
  check "unreadable file: rc" "2" "$RC"
  check_contains "unreadable file: tag" "$OUT" "CHECK_FAILED"
fi
chmod 644 "$d/assets/security-audit/LICENSE"

# ---------- verify --upstream: the manifest against the pinned commit --------

PIN_DATE=$(sed -n 's/^commit-date: //p' "$REPO/assets/security-audit/UPSTREAM")
printf '{"default_branch":"main"}' | answer "repos/$R"
printf '{"status":"identical"}' | answer "repos/$R/compare/$PIN...main"
commit_json "$PIN" "$PIN_DATE" | answer "repos/$R/commits/$PIN"
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

# The hole the offline check cannot see: a file and its row edited together.
make_tarball "$PIN" keep
d=$(fixture)
printf 'x' >> "$d/assets/security-audit/skill/HUNTING.md"
resync_row "$d" skill/HUNTING.md
run "$d" verify
check "file and row edited together: offline passes" "0" "$RC"
run "$d" verify --upstream
check "file and row edited together: upstream catches it" "1" "$RC"
check_contains "file and row edited together: tag" "$OUT" "PIN_MISMATCH skill/HUNTING.md"

d=$(fixture)
extra() { printf 'x\n' > "$1/skills/security-audit/EXTRA.md"; }
make_tarball "$PIN" extra
run "$d" verify --upstream
check "file upstream with no row: rc" "1" "$RC"
check_contains "file upstream with no row: tag" "$OUT" "PIN_MISMATCH skill/EXTRA.md"

lose() { mv "$1/skills/security-audit/HUNTING.md" "$1/moved-out.md"; }
make_tarball "$PIN" lose
run "$d" verify --upstream
check "row upstream lacks: rc" "1" "$RC"
check_contains "row upstream lacks: tag" "$OUT" "PIN_MISMATCH skill/HUNTING.md"

make_tarball "$PIN" keep
printf '{"status":"diverged"}' | answer "repos/$R/compare/$PIN...main"
run "$d" verify --upstream
check "pin off the default branch: rc" "1" "$RC"
check_contains "pin off the default branch: tag" "$OUT" "PIN_OFF_BRANCH"
printf '{"status":"behind"}' | answer "repos/$R/compare/$PIN...main"
run "$d" verify --upstream
check "pin past the default branch: rc" "1" "$RC"
printf '{"status":"identical"}' | answer "repos/$R/compare/$PIN...main"

commit_json "$PIN" "2020-01-01T00:00:00Z" | answer "repos/$R/commits/$PIN"
run "$d" verify --upstream
check "false commit-date: rc" "1" "$RC"
check_contains "false commit-date: tag" "$OUT" "PIN_MISMATCH UPSTREAM commit-date"
commit_json "$PIN" "$PIN_DATE" | answer "repos/$R/commits/$PIN"

# Files that vanish without an error are the false clean this guards.
tarball_file=$(api_file "repos/$R/tarball/$PIN")
head -c 20000 "$tarball_file" > "$WORK/cut" && mv "$WORK/cut" "$tarball_file"
run "$d" verify --upstream
check "truncated tarball: rc" "2" "$RC"
check_contains "truncated tarball: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

make_tarball "$PIN" keep
"$PY" - "$tarball_file" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
for i in range(len(b) // 2, len(b) // 2 + 64):
    b[i] ^= 0xff
open(p, "wb").write(bytes(b))
PY
run "$d" verify --upstream
check "damaged tarball: rc" "2" "$RC"
check_contains "damaged tarball: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

printf 'not a tarball' > "$tarball_file"
run "$d" verify --upstream
check "not a tarball: rc" "2" "$RC"

make_tarball "$PIN" keep
: > "$WORK/gh-down"
run "$d" verify --upstream
check "upstream unreachable: rc" "2" "$RC"
check_contains "upstream unreachable: tag" "$OUT" "UPSTREAM_NOT_CHECKED"
check "upstream unreachable: no clean line" "no" "$(grep -q VENDORED_OK <<< "$OUT" && echo yes || echo no)"
mv "$WORK/gh-down" "$WORK/gh-up"

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
check_contains "behind: count" "$OUT" "UPSTREAM_BEHIND 2 "
check_contains "behind: lists a commit" "$OUT" "22222222"
check "behind: a vendored file is starred" "1" "$(grep -cE '^ +\* .*skills/security-audit/HUNTING.md' <<< "$OUT")"
check "behind: another file is not" "0" "$(grep -cE '^ +\* .*README.md' <<< "$OUT")"
check_contains "behind: says the date is author-set" "$OUT" "DATE_IS_AUTHOR_SET"
check_contains "behind: names the commit old enough" "$OUT" "NEWEST_OLD_ENOUGH refresh --to 2222222222222222222222222222222222222222"

run "$d" status --summary
check "summary: rc" "0" "$RC"
check "summary: one line" "1" "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')"

# Upstream text reaches a terminal: no escape byte and no forged line gets through.
ESC=$(printf '\033')
cat <<JSON | answer "repos/$R/compare/$PIN...main"
{"status":"ahead","ahead_by":3,
 "commits":[{"sha":"3333333333333333333333333333333333333333","commit":{"message":"evil \\u001b[2J subject","author":{"date":"$OLD_DATE"},"committer":{"date":"$OLD_DATE"}}},
            $(commit_json 4444444444444444444444444444444444444444 "$OLD_DATE")],
 "files":[{"filename":"evil\\u001b[2J\\nUPSTREAM_CURRENT.md","status":"added"},
          {"filename":"moved.md","previous_filename":"skills/security-audit/OLD.md","status":"renamed"}]}
JSON
run "$d" status
check "escape bytes are not printed" "no" "$(grep -q "$ESC" <<< "$OUT" && echo yes || echo no)"
check "a file name cannot forge a tag" "no" "$(grep -q '^UPSTREAM_CURRENT' <<< "$OUT" && echo yes || echo no)"
check_contains "the newest of two old commits is named" "$OUT" "NEWEST_OLD_ENOUGH refresh --to 4444444444444444444444444444444444444444"
check_contains "a list GitHub cut short says so" "$OUT" "1 more"
check "a file renamed out of the tree is starred" "1" "$(grep -cE '^ +\* .*moved.md' <<< "$OUT")"

printf '{"status":"ahead","ahead_by":1,"commits":[%s],"files":[]}' "$(commit_json "$NEW" "$YOUNG_DATE")" | answer "repos/$R/compare/$PIN...main"
run "$d" status
check_contains "nothing old enough: tag" "$OUT" "NONE_OLD_ENOUGH"

printf '{}' | answer "repos/$R/compare/$PIN...main"
run "$d" status
check "compare with no status: rc" "2" "$RC"
check_contains "compare with no status: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

printf '{"status":"ahead","ahead_by":1,"commits":[{"sha":"x"}],"files":[]}' | answer "repos/$R/compare/$PIN...main"
run "$d" status
check "wrong-shape answer: rc" "2" "$RC"
check_contains "wrong-shape answer: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

d2=$(fixture)
printf 'junk\n' > "$d2/assets/security-audit/UPSTREAM"
run "$d2" status
check "unparsable pin: rc" "2" "$RC"
check_contains "unparsable pin: tag" "$OUT" "UPSTREAM_NOT_CHECKED"

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
check_contains "younger than 7 days: says the date is author-set" "$OUT" "DATE_IS_AUTHOR_SET"
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

printf '{"sha":"%s","commit":{"message":"m","author":{"date":"%s"},"committer":{"date":"%s"}}}' "$NEW" "$(days_ago 1)" "$(days_ago 30)" | answer "repos/$R/commits/main"
run "$d" refresh
check "recent author date: rc" "1" "$RC"
check_contains "recent author date: tag" "$OUT" "REFRESH_REFUSED_TOO_NEW"

# `behind` is what a fork commit stacked on the tip of main should return.
for state in diverged behind; do
  setup_target "$NEW" "$(days_ago 8)" "$state"
  run "$d" refresh --to "$NEW"
  check "commit off the default branch [$state]: rc" "1" "$RC"
  check_contains "commit off the default branch [$state]: tag" "$OUT" "REFRESH_REFUSED_OFF_BRANCH"
  check "commit off the default branch [$state]: tree untouched" "$BEFORE" "$(tree_hash "$d")"
done

setup_target "$NEW" "$(days_ago 8)" identical
printf '{"status":"behind"}' | answer "repos/$R/compare/$PIN...$NEW"
run "$d" refresh --to "$NEW"
check "older than the pin: rc" "1" "$RC"
check_contains "older than the pin: tag" "$OUT" "REFRESH_REFUSED_OLDER_THAN_PIN"
check "older than the pin: tree untouched" "$BEFORE" "$(tree_hash "$d")"

for bad_to in 'main;id' 'abc1234;id' ''; do
  run "$d" refresh --to "$bad_to"
  check "--to [$bad_to]: rc" "1" "$RC"
  check_contains "--to [$bad_to]: tag" "$OUT" "REFRESH_REFUSED_BAD_SHA"
done
check "bad --to: tree untouched" "$BEFORE" "$(tree_hash "$d")"

d2=$(fixture)
printf 'junk\n' > "$d2/assets/security-audit/UPSTREAM"
run "$d2" refresh --to "$NEW"
check "unparsable pin cannot skip the rollback check: rc" "1" "$RC"
check_contains "unparsable pin cannot skip the rollback check: tag" "$OUT" "REFRESH_REFUSED_BAD_PIN"

add_link() { ln -s /etc/hosts "$1/skills/security-audit/link.md"; }
make_tarball "$NEW" add_link
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "symlink upstream: rc" "1" "$RC"
check_contains "symlink upstream: tag" "$OUT" "TARBALL_REFUSED_NOT_REGULAR"
check "symlink upstream: tree untouched" "$BEFORE" "$(tree_hash "$d")"

move_tree() { mv "$1/skills/security-audit" "$1/skills/other"; }
make_tarball "$NEW" move_tree
run "$d" refresh --to "$NEW"
check "tree moved upstream: rc" "1" "$RC"
check_contains "tree moved upstream: tag" "$OUT" "TARBALL_REFUSED_NO_TREE"
check "tree moved upstream: tree untouched" "$BEFORE" "$(tree_hash "$d")"

no_license() { mv "$1/LICENSE" "$1/moved-out.txt"; }
make_tarball "$NEW" no_license
run "$d" refresh --to "$NEW"
check "no license upstream: rc" "1" "$RC"
check_contains "no license upstream: tag" "$OUT" "TARBALL_REFUSED_NO_LICENSE"
check "no license upstream: tree untouched" "$BEFORE" "$(tree_hash "$d")"

# tar cannot write these names, so the fixture is built member by member.
hostile_tarball() { # MEMBER_NAME
  "$PY" - "$(api_file "repos/$R/tarball/$NEW")" "$1" "$REPO/assets/security-audit" <<'PY'
import io, os, sys, tarfile
out, name, src = sys.argv[1:4]
with tarfile.open(out, "w:gz") as tar:
    for rel, arc in (("LICENSE", "up-x/LICENSE"), ("skill/SKILL.md", "up-x/skills/security-audit/SKILL.md"),
                     ("skill/report-schema.json", "up-x/skills/security-audit/report-schema.json")):
        tar.add(os.path.join(src, rel), arcname=arc)
    info = tarfile.TarInfo(name)
    info.size = 1
    tar.addfile(info, io.BytesIO(b"x"))
PY
}
for member in "up-x/skills/security-audit/../../../../../../escaped.txt" "/abs/escaped.txt"; do
  hostile_tarball "$member"
  run "$d" refresh --to "$NEW"
  check "hostile member [$member]: rc" "1" "$RC"
  check_contains "hostile member [$member]: tag" "$OUT" "TARBALL_REFUSED_UNSAFE_MEMBER"
  check "hostile member [$member]: tree untouched" "$BEFORE" "$(tree_hash "$d")"
done
check "hostile member: nothing escaped" "" "$(find "$WORK" -name escaped.txt)"

make_tarball "$NEW" update
: > "$WORK/cut"
head -c 20000 "$(api_file "repos/$R/tarball/$NEW")" > "$WORK/cut" && mv "$WORK/cut" "$(api_file "repos/$R/tarball/$NEW")"
run "$d" refresh --to "$NEW"
check "truncated tarball on refresh: rc" "2" "$RC"
check "truncated tarball on refresh: tree untouched" "$BEFORE" "$(tree_hash "$d")"

# The documented flow: a commit older than the tip, with the tip still too young.
make_tarball "$NEW" update
d=$(fixture)
setup_target "$NEW" "$(days_ago 8)" ahead
run "$d" refresh --to "$NEW"
check "a commit behind the tip: rc" "0" "$RC"

make_tarball "$NEW" update
d=$(fixture)
mkdir -p "$d/assets/.security-audit.new/stale" "$d/assets/.security-audit.old/stale"
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "refresh: rc" "0" "$RC"
check "refresh: stale leftovers not carried in" "" "$(find "$d/assets/security-audit" -name stale)"
check_contains "refresh: tag" "$OUT" "REFRESHED $NEW"
check_contains "refresh: says the date is author-set" "$OUT" "DATE_IS_AUTHOR_SET"
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
BEFORE=$(tree_hash "$d")
setup_target "$NEW" "$(days_ago 8)" identical
run "$d" refresh --to "$NEW"
check "wrapper contract broken: rc" "1" "$RC"
check_contains "wrapper contract broken: tag" "$OUT" "CONTRACT_MISSING skill/SKILL.md"
check "wrapper contract broken: tree untouched" "$BEFORE" "$(tree_hash "$d")"

rename_verdict() {
  "$PY" - "$1/skills/security-audit/report-schema.json" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(t.replace("needs_validation", "blocked"))
PY
}
make_tarball "$NEW" rename_verdict
run "$d" refresh --to "$NEW"
check "verdict renamed upstream: rc" "1" "$RC"
check_contains "verdict renamed upstream: tag" "$OUT" "CONTRACT_MISSING skill/report-schema.json"

# The vendored tree can also lose a contract name by hand, with its row resynced.
d=$(fixture)
"$PY" - "$d/assets/security-audit/skill/SKILL.md" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(t.replace("FINDINGS-DETAIL.md", "DETAIL.md"))
PY
resync_row "$d" skill/SKILL.md
run "$d" verify
check "contract name lost in the tree: rc" "1" "$RC"
check_contains "contract name lost in the tree: tag" "$OUT" "CONTRACT_MISSING"

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
