#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Tests for install-approvals.sh.
#
# Not -e: the suite has to OBSERVE non-zero exits (2 to 5 are contract, not
# failure), so errexit would kill it on the first case it exists to check.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/install-approvals.sh"
SOURCE="$HERE/../assets/approvals/approvals.yaml"

PASS=0
FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $name"
    echo "  expected: $expected"
    echo "  actual:   $actual"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A git repo by default: outside one the installer cannot ask git about
# .gitignore and exits 5, which the "not a repo" case below pins.
fixture() {
  local d="$WORK/$1"
  rm -rf "$d"
  mkdir -p "$d"
  git -C "$d" init -q
  echo "$d"
}

yes_no() { "$@" && echo yes || echo no; }

# --- fresh install ----------------------------------------------------------
d=$(fixture fresh)
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "fresh: rc" "0" "$rc"
check "fresh: matches source" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml")"
check "fresh: merge-first note" "yes" "$(yes_no grep -q 'default branch' <<<"$out")"

out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "rerun: rc" "0" "$rc"
check "rerun: no .new" "yes" "$(yes_no test ! -e "$d/.claude/approvals.yaml.new")"

# --- a .gitignore that hides the policy is reported, not staged blind -------
d=$(fixture ignored)
printf '.claude/*\n!.claude/rules/\n' > "$d/.gitignore"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "ignored: rc" "4" "$rc"
check "ignored: names the negation" "yes" "$(yes_no grep -qF '!.claude/approvals.yaml' <<<"$out")"
check "ignored: file is installed" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml")"
check "ignored: merge-first note" "yes" "$(yes_no grep -q 'default branch' <<<"$out")"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "ignored, already current: rc" "4" "$rc"
printf '.claude/*\n!.claude/rules/\n!.claude/approvals.yaml\n' > "$d/.gitignore"
rm "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "negated: rc" "0" "$rc"

# A force-added policy is committed whatever .gitignore says.
d=$(fixture tracked)
printf '.claude/*\n' > "$d/.gitignore"
mkdir -p "$d/.claude" && cp "$SOURCE" "$d/.claude/approvals.yaml"
git -C "$d" add -f .claude/approvals.yaml
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "tracked though ignored: rc" "0" "$rc"

# --- git that cannot answer is unverified, never clear ----------------------
d=$(fixture notrepo)
rm -rf "$d/.git"
printf '.claude/*\n' > "$d/.gitignore"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "not a repo: rc" "5" "$rc"
check "not a repo: file is installed" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml")"

STUB="$WORK/stubgit"
mkdir -p "$STUB"
printf '#!/usr/bin/env bash\n[[ " $* " == *" check-ignore "* ]] && exit 128\nexec %q "$@"\n' "$(command -v git)" > "$STUB/git"
chmod +x "$STUB/git"
d=$(fixture gitfails)
out=$(PATH="$STUB:$PATH" "$INSTALLER" "$d" 2>&1); rc=$?
check "check-ignore error: rc" "5" "$rc"

# --- a different file is never overwritten ----------------------------------
d=$(fixture differs)
mkdir -p "$d/.claude"
echo "version: 1" > "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "differs: rc" "2" "$rc"
check "differs: original kept" "version: 1" "$(cat "$d/.claude/approvals.yaml")"
check "differs: .new written" "yes" "$(yes_no cmp -s "$SOURCE" "$d/.claude/approvals.yaml.new")"

# After the printed mv, `git add -A` would skip an ignored file without a word.
d=$(fixture differs_ignored)
printf '.claude/*\n' > "$d/.gitignore"
mkdir -p "$d/.claude"
echo "version: 1" > "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "differs + ignored: rc" "2" "$rc"
check "differs + ignored: names the negation" "yes" "$(yes_no grep -qF '!.claude/approvals.yaml' <<<"$out")"

# --- an existing .yml would shadow the vendored .yaml ------------------------
d=$(fixture yml)
mkdir -p "$d/.claude"
echo "version: 1" > "$d/.claude/approvals.yml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "yml: rc" "2" "$rc"
check "yml: no .yaml written beside it" "yes" "$(yes_no test ! -e "$d/.claude/approvals.yaml")"

# The re-vendor sweep's case: the vendored file is current and a .yml overrides it.
d=$(fixture yml_beside_current)
mkdir -p "$d/.claude"
cp "$SOURCE" "$d/.claude/approvals.yaml"
echo "version: 1" > "$d/.claude/approvals.yml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "yml beside current yaml: rc" "2" "$rc"

# --- symlinks are refused ---------------------------------------------------
OUTSIDE="$WORK/outside"
mkdir -p "$OUTSIDE"
echo "victim" > "$OUTSIDE/victim.yml"
d=$(fixture link_file)
mkdir -p "$d/.claude"
ln -s "$OUTSIDE/victim.yml" "$d/.claude/approvals.yaml"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link file: rc" "1" "$rc"
check "link file: target untouched" "victim" "$(cat "$OUTSIDE/victim.yml")"

d=$(fixture link_dir)
mkdir -p "$OUTSIDE/claude"
ln -s "$OUTSIDE/claude" "$d/.claude"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link dir: rc" "1" "$rc"
check "link dir: nothing written outside" "0" "$(find "$OUTSIDE/claude" -type f | wc -l | tr -d ' ')"

# A directory, not a file: mktemp resolves through the link and leaves its temp
# file there, while a link to a file is merely replaced by the mv and passes
# even with the guard deleted.
d=$(fixture link_new_dir)
mkdir -p "$d/.claude" "$OUTSIDE/newdir"
echo "version: 1" > "$d/.claude/approvals.yaml"
ln -s "$OUTSIDE/newdir" "$d/.claude/approvals.yaml.new"
out=$("$INSTALLER" "$d" 2>&1); rc=$?
check "link .new dir: rc" "1" "$rc"
check "link .new dir: nothing written outside" "0" "$(find "$OUTSIDE/newdir" -type f | wc -l | tr -d ' ')"

# --- missing source ---------------------------------------------------------
FAKE="$WORK/fakeplugin"
mkdir -p "$FAKE/scripts"
cp "$INSTALLER" "$FAKE/scripts/"
d=$(fixture nosource)
out=$("$FAKE/scripts/install-approvals.sh" "$d" 2>&1); rc=$?
check "missing source: rc" "3" "$rc"

# --- the asset itself -------------------------------------------------------
# Enforce mode lands fleet-wide in one re-vendor; it must be a deliberate edit
# to this assertion, not a side effect of refreshing the starter policy.
check "asset: observe mode" "yes" "$(yes_no grep -qx 'mode: observe' "$SOURCE")"
check "asset: parses as YAML with version 1" "1" \
  "$(uv run --quiet --no-project --with pyyaml python -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['version'])" "$SOURCE")"

echo "install-approvals: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
