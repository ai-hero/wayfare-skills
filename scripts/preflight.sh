#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Pre-flight checks for the wayfare pipeline.
#
# Runs the union of every downstream skill's blocking check so a `wayfare-build-task`
# (or any individual skill) can fail fast, before code is edited, before a
# branch is created, before a PR is pushed.
#
# Buckets:
#   tooling: gh + auth, node ≥18, Playwright MCP registered, pr-review-toolkit
#              installed, pre-commit if .pre-commit-config.yaml exists
#   repo:    HERO.md present + non-stale, auto-approve.yml on default branch,
#              no in-progress merge/rebase/cherry-pick
#   runtime: per-project .env keys vs .env.example, declared ports free,
#              dependency file present. Scoped to projects touched by the diff
#              when --projects is passed.
#   pipeline: issue tracker auth (Linear / Jira / GitHub Issues), default
#              branch fetch reachability
#
# Usage:
#   scripts/preflight.sh [--bucket tooling|repo|runtime|pipeline|all]
#                        [--projects path1,path2 | --auto-scope]
#                        [--quiet]
#
#   --auto-scope  derive --projects from the diff, and skip the runtime bucket
#                 entirely on a fresh start (default branch, clean tree). Use
#                 this instead of computing the scope in the caller.
#
# Output (one line per check):
#   [OK]      bucket: detail
#   [WARN]    bucket: detail (continues)
#   [BLOCKER] bucket: detail (sets exit code 1)
#   [SKIP]    bucket: detail (check not applicable)
#
# Exit code: 0 if no blockers, 1 if blockers found, 2 if preflight could not
# RUN at all (usage error, or a missing/corrupt hero-lib.sh). 2 means there are
# no [BLOCKER] lines to read. It is an installation problem, not a repo one.
# Warnings never block.
#
# This script is read-only. It never edits files, creates branches, or
# mutates remote state.

set -uo pipefail

# Shared helpers. HERO.md parsing lives in exactly one place. This script
# previously carried two hand-rolled variants that disagreed with hero_field
# and with each other on a value carrying a trailing `# comment`.
# Resolve through symlinks: `dirname "$0"` gives the SYMLINK's directory, so
# `ln -s .../preflight.sh ~/bin/preflight` looked for hero-lib.sh in ~/bin.
SELF="${BASH_SOURCE[0]:-$0}"
while [ -L "$SELF" ]; do
  LINK=$(readlink "$SELF")
  case "$LINK" in
    /*) SELF="$LINK" ;;
    *)  SELF="$(cd "$(dirname "$SELF")" && pwd)/$LINK" ;;
  esac
done
HERO_LIB="$(cd "$(dirname "$SELF")" && pwd)/hero-lib.sh"

# Test the precondition and the RESULT, not `.`'s exit status. `.` returns the
# status of the last command in the sourced file, so one appended statement
# returning non-zero would read as "cannot source" on a healthy library.
[ -r "$HERO_LIB" ] || { echo "preflight: hero-lib.sh not readable at $HERO_LIB" >&2; exit 2; }
# shellcheck source=/dev/null
. "$HERO_LIB"
command -v hero_root >/dev/null 2>&1 \
  || { echo "preflight: sourced $HERO_LIB but hero_root is undefined; library is corrupt" >&2; exit 2; }

# ---------- arg parsing ----------------------------------------------------

BUCKET=all
PROJECT_SCOPE=""
QUIET=false
AUTO_SCOPE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --bucket)     BUCKET="${2:-all}"; shift 2 ;;
    --projects)   PROJECT_SCOPE="${2:-}"; shift 2 ;;
    --auto-scope) AUTO_SCOPE=true; shift ;;
    --quiet)      QUIET=true; shift ;;
    -h|--help)
      sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$BUCKET" in tooling|repo|runtime|pipeline|all) ;; *)
  echo "ERROR: --bucket must be one of: tooling, repo, runtime, pipeline, all" >&2
  exit 2 ;;
esac

# ---------- auto-scope -----------------------------------------------------
#
# Deciding which projects a run should runtime-check is this script's job, not
# its caller's. --auto-scope derives --projects from the diff (uncommitted plus
# committed-but-unpushed) and, on a truly fresh start with nothing changed yet,
# skips the runtime bucket entirely rather than checking every project in the
# repo for a diff that does not exist.

if [ "$AUTO_SCOPE" = "true" ]; then
  if [ -n "$PROJECT_SCOPE" ]; then
    echo "ERROR: --auto-scope and --projects are mutually exclusive" >&2
    exit 2
  fi
  AS_ROOT=$(hero_root)
  # _verbose: this value decides whether an entire bucket of blocking checks is
  # skipped. A silent fallback to `main` on a `master` repo would compare the
  # real branch against a fabricated one, with no signal that it happened.
  AS_DEFAULT=$(hero_default_branch_verbose "$AS_ROOT")

  # An unresolvable base ref makes `git diff origin/X...HEAD` fail into
  # 2>/dev/null and contribute NOTHING, indistinguishable from "no committed
  # changes". That reads as a fresh start and skips the runtime bucket entirely,
  # on a repo that may carry real blockers. There must be a third state:
  # "could not determine scope", which falls back to checking everything.
  if git -C "$AS_ROOT" rev-parse --verify --quiet "origin/$AS_DEFAULT" >/dev/null 2>&1; then
    AS_BASE_OK=true
  else
    AS_BASE_OK=false
    [ "$QUIET" = "true" ] || {
      echo "auto-scope: origin/$AS_DEFAULT does not resolve; cannot derive scope from the diff." >&2
      echo "auto-scope: checking ALL projects instead. Fix with: git fetch origin $AS_DEFAULT" >&2
    }
  fi

  if [ "$AS_BASE_OK" = "true" ]; then
    # Top-level directory of every changed path, deduped. Files at the repo root
    # (NF == 1) belong to no project and are intentionally excluded.
    # `ls-files --others` is required: neither diff form lists UNTRACKED paths,
    # so a newly scaffolded project directory, a first-class flow here, was
    # invisible to the scope and silently never runtime-checked.
    PROJECT_SCOPE=$( { git -C "$AS_ROOT" diff --name-only HEAD 2>/dev/null
                       git -C "$AS_ROOT" diff --name-only "origin/$AS_DEFAULT...HEAD" 2>/dev/null
                       git -C "$AS_ROOT" ls-files --others --exclude-standard 2>/dev/null
                     } | awk -F/ 'NF > 1 {print $1}' | sort -u | paste -sd, - )
  else
    PROJECT_SCOPE=""
  fi

  AS_BRANCH=$(git -C "$AS_ROOT" branch --show-current 2>/dev/null)
  AS_DIRTY=$(git -C "$AS_ROOT" status --porcelain 2>/dev/null)

  # A fresh start may only be DECLARED when it can be OBSERVED, hence the
  # AS_BASE_OK conjunct.
  if [ "$AS_BASE_OK" = "true" ] && [ -z "$PROJECT_SCOPE" ] \
     && [ "$AS_BRANCH" = "$AS_DEFAULT" ] && [ -z "$AS_DIRTY" ]; then
    if [ "$BUCKET" = "all" ]; then
      BUCKET=no-runtime
      [ "$QUIET" = "true" ] || echo "auto-scope: fresh start, skipping runtime bucket"
    else
      # Printing "skipping runtime bucket" here and then running it (because
      # --bucket was explicit) is a lie that gets believed later.
      [ "$QUIET" = "true" ] || echo "auto-scope: fresh start, but --bucket $BUCKET was requested explicitly, so running it anyway"
    fi
  elif [ -n "$PROJECT_SCOPE" ]; then
    [ "$QUIET" = "true" ] || echo "auto-scope: runtime checks scoped to '$PROJECT_SCOPE'"
  fi
fi

# ---------- result tracking ------------------------------------------------

BLOCKERS=0
WARNINGS=0

emit() {
  # $1 = severity (OK|WARN|BLOCKER|SKIP)
  # $2... = message
  local sev="$1"; shift
  case "$sev" in
    BLOCKER) BLOCKERS=$((BLOCKERS+1)) ;;
    WARN)    WARNINGS=$((WARNINGS+1)) ;;
  esac
  $QUIET && [ "$sev" = "OK" ] && return 0
  printf '[%-7s] %s\n' "$sev" "$*"
}

# ---------- shared context -------------------------------------------------

ROOT=$(hero_root)
HERO="$ROOT/HERO.md"
DEFAULT_BRANCH=$(hero_default_branch "$ROOT")

# Lazy gh-auth probe, set on first call, cached for the rest of the run.
# Used by check_repo / check_pipeline so they don't re-shell `gh auth status`
# when check_tooling ran (the common case) or when invoked standalone via
# `--bucket repo|pipeline`.
ensure_gh_auth_probed() {
  [ -n "${GH_AUTH_OK:-}" ] && return
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    GH_AUTH_OK=true
  else
    GH_AUTH_OK=false
  fi
}

# ---------- bucket: tooling ------------------------------------------------

check_tooling() {
  # 1. gh CLI + auth. Capture `gh auth status` once and reuse for both the
  #    pass/fail decision here and the scope check, so check_repo /
  #    check_pipeline can read GH_AUTH_OK instead of re-shelling.
  #    `gh auth status` prints the full scope list on one line like:
  #      `- Token scopes: 'gist', 'read:org', 'repo', 'workflow'`
  #    Strip the prefix and look for 'repo' anywhere in the remaining list.
  GH_AUTH_OK=false
  if command -v gh >/dev/null 2>&1; then
    local auth_out
    if auth_out=$(gh auth status 2>&1); then
      GH_AUTH_OK=true
      local scopes
      scopes=$(printf '%s' "$auth_out" | sed -n "s/^.*Token scopes: //p" | head -1)
      if printf '%s' "$scopes" | grep -q "'repo'"; then
        emit OK "tooling: gh authenticated (scopes: $scopes)"
      else
        emit WARN "tooling: gh authenticated but missing 'repo' scope (got: $scopes) — push-pr / ship-pr may fail"
      fi
    else
      emit BLOCKER "tooling: gh CLI not authenticated — run 'gh auth login'"
    fi
  else
    emit BLOCKER "tooling: 'gh' CLI not installed — https://cli.github.com/"
  fi

  # 2. jq (used by every gh-api call)
  if command -v jq >/dev/null 2>&1; then
    emit OK "tooling: jq present"
  else
    emit BLOCKER "tooling: 'jq' not installed — required by gh api calls"
  fi

  # 3. Node ≥18 (Playwright MCP needs it)
  if command -v node >/dev/null 2>&1; then
    local node_major
    node_major=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
    if [ "${node_major:-0}" -ge 18 ] 2>/dev/null; then
      emit OK "tooling: node $(node --version) (>=18)"
    else
      emit WARN "tooling: node $(node --version 2>/dev/null || echo missing); Playwright MCP needs >=18"
    fi
  else
    emit WARN "tooling: 'node' not installed — push-pr's test-phase UI smoke will be unavailable"
  fi

  # 4. Playwright MCP registered. `claude mcp list` is the canonical check;
  #    if claude CLI isn't available, fall back to the on-disk config.
  if command -v claude >/dev/null 2>&1; then
    if claude mcp list 2>/dev/null | grep -qi "playwright"; then
      emit OK "tooling: playwright MCP registered"
    else
      emit WARN "tooling: playwright MCP not registered — push-pr's test-phase UI smoke will skip. Install: claude mcp add playwright npx @playwright/mcp@latest"
    fi
  elif [ -f "$HOME/.claude.json" ] && grep -q '"playwright"' "$HOME/.claude.json" 2>/dev/null; then
    emit OK "tooling: playwright MCP present in ~/.claude.json"
  else
    emit WARN "tooling: cannot detect playwright MCP — push-pr's test-phase UI smoke may skip. Install: claude mcp add playwright npx @playwright/mcp@latest"
  fi

  # 5. pr-review-toolkit plugin. A marketplace install never lands at either
  #    legacy directory (it writes to plugins/cache/MARKETPLACE/PLUGIN/SHA),
  #    so check installed_plugins.json first, the marketplace's own record,
  #    then fall back to the two legacy directories for a hand-placed plugin.
  local plugin_found=false
  local installed_json="$HOME/.claude/plugins/installed_plugins.json"
  if [ -f "$installed_json" ] && command -v jq >/dev/null 2>&1; then
    local jq_rc
    jq -e '.plugins | has("pr-review-toolkit@claude-plugins-official")' \
      "$installed_json" >/dev/null 2>&1
    jq_rc=$?
    case "$jq_rc" in
      0) plugin_found=true ;;
      1) ;; # valid JSON, key absent — fall through to the directory probe
      *) emit WARN "tooling: installed_plugins.json is present but unreadable/malformed (jq exit $jq_rc) — falling back to directory probe" ;;
    esac
  fi
  if ! $plugin_found; then
    for d in "$HOME/.claude/plugins/pr-review-toolkit" \
             "$ROOT/.claude/plugins/pr-review-toolkit"; do
      [ -d "$d" ] && plugin_found=true && break
    done
  fi
  if $plugin_found; then
    emit OK "tooling: pr-review-toolkit plugin installed"
  else
    emit WARN "tooling: pr-review-toolkit plugin not found — Step 5 (self-review) runs a thinner review. Install: /plugin install pr-review-toolkit"
  fi

  # 6. pre-commit, only if the repo declares hooks. Verify *both* that the
  #    CLI is installed AND that the git hook is actually wired in
  #    (`.git/hooks/pre-commit` contains the pre-commit shim). A repo with
  #    .pre-commit-config.yaml but no installed hook silently skips every
  #    check at commit time, exactly the kind of fail-late that preflight
  #    is meant to catch upstream.
  if [ -f "$ROOT/.pre-commit-config.yaml" ]; then
    if ! command -v pre-commit >/dev/null 2>&1; then
      emit BLOCKER "tooling: 'pre-commit' not installed but .pre-commit-config.yaml exists — wayfare-build-task's Step 4 (push) will commit past every check. Install: pipx install pre-commit"
    else
      # Resolve the hook path via git so we honor core.hooksPath and work
      # correctly inside worktrees (where .git is a file, not a directory)
      # and bare repos. `git rev-parse --git-path` returns the path git
      # would actually use; it may be relative (anchored at $ROOT) or
      # absolute depending on the layout.
      local hook_path
      hook_path=$(git -C "$ROOT" rev-parse --git-path hooks/pre-commit 2>/dev/null)
      case "$hook_path" in
        /*) ;;
        *)  hook_path="$ROOT/$hook_path" ;;
      esac
      if [ -z "$hook_path" ] || [ ! -f "$hook_path" ]; then
        emit BLOCKER "tooling: pre-commit CLI present but git hook not installed at $hook_path — wayfare-build-task's Step 4 (push) will commit past every check. Run: pre-commit install"
      elif ! grep -q "generated by pre-commit" "$hook_path" 2>/dev/null; then
        emit WARN "tooling: $hook_path exists but is not pre-commit-managed — custom hook may be shadowing pre-commit checks. Verify with: pre-commit install --overwrite"
      else
        emit OK "tooling: pre-commit installed and git hook active ($hook_path)"
      fi
    fi
  else
    emit SKIP "tooling: no .pre-commit-config.yaml in repo"
  fi
}

# ---------- bucket: repo state ---------------------------------------------

check_repo() {
  ensure_gh_auth_probed

  # 1. HERO.md present
  if [ -f "$HERO" ]; then
    emit OK "repo: HERO.md present"
  else
    emit BLOCKER "repo: HERO.md missing — run wayfare:wayfare-init-repo"
    return 0  # downstream checks read HERO.md; bail this bucket
  fi

  # 2. HERO.md staleness. Fast subset of scripts/check-hero-staleness.sh,
  # intentionally diverged: that script carries a longer pattern list
  # (ruff, eslint, biome, Gemfile, requirements*.txt, agent configs, etc.).
  # Keep this list deliberately tight; the standalone script is the one
  # that grows. See check-hero-staleness.sh's header for the rationale.
  local hero_time config_time
  hero_time=$(git -C "$ROOT" log -1 --format=%ct -- HERO.md 2>/dev/null | grep -E '^[0-9]+$' || echo "")
  config_time=$(git -C "$ROOT" log -1 --format=%ct -- \
    pyproject.toml ':(glob)**/pyproject.toml' \
    package.json ':(glob)**/package.json' \
    go.mod ':(glob)**/go.mod' \
    Cargo.toml ':(glob)**/Cargo.toml' \
    .github/workflows .pre-commit-config.yaml \
    CLAUDE.md Makefile justfile Taskfile.yml 2>/dev/null \
    | grep -E '^[0-9]+$' || echo "")
  if [ -z "$hero_time" ] && [ -z "$config_time" ]; then
    emit SKIP "repo: cannot read git history (empty repo?) — staleness unknown"
  elif [ "${config_time:-0}" -gt "${hero_time:-0}" ]; then
    emit WARN "repo: HERO.md may be stale — run wayfare:wayfare-init-repo recalibrate"
  else
    emit OK "repo: HERO.md fresh"
  fi

  # 3. auto-approve workflow on default branch (wayfare-build-task's Step 9, ship, needs it). Reuse the
  # GH_AUTH_OK flag set by check_tooling instead of re-shelling gh auth.
  #
  # Both spellings, and this one is a BLOCKER: probing only .yml stopped
  # wayfare-build-task at Step 0.3, before any work started, against a repo whose
  # workflow was present and active under .yaml, with fix advice telling the
  # user to install a file they already had.
  if [ "${GH_AUTH_OK:-false}" = "true" ]; then
    AA_ON_DEFAULT=""
    for ext in yaml yml; do
      if gh api "/repos/{owner}/{repo}/contents/.github/workflows/auto-approve.$ext?ref=$DEFAULT_BRANCH" \
          --jq '.path' >/dev/null 2>&1; then
        AA_ON_DEFAULT="auto-approve.$ext"
        break
      fi
    done
    if [ -n "$AA_ON_DEFAULT" ]; then
      emit OK "repo: $AA_ON_DEFAULT present on $DEFAULT_BRANCH"
    else
      emit BLOCKER "repo: no .github/workflows/auto-approve.yaml (or .yml) on $DEFAULT_BRANCH — wayfare-build-task's Step 9 (ship) will be a no-op. Run wayfare:wayfare-init-repo recalibrate, then merge the workflow file to $DEFAULT_BRANCH."
    fi
  else
    emit SKIP "repo: gh unavailable — cannot check the auto-approve workflow remotely"
  fi

  # 4. No in-progress merge / rebase / cherry-pick. Resolve each path via
  # `git rev-parse --git-path` so the check works inside worktrees (where
  # .git is a file pointing at the real gitdir) and bare repos. Hard-coded
  # $ROOT/.git/* paths miss those layouts.
  local in_progress=false marker
  for marker in MERGE_HEAD CHERRY_PICK_HEAD rebase-merge rebase-apply; do
    local p
    p=$(git -C "$ROOT" rev-parse --git-path "$marker" 2>/dev/null)
    case "$p" in
      /*) ;;
      *)  p="$ROOT/$p" ;;
    esac
    if [ -e "$p" ]; then
      in_progress=true
      break
    fi
  done
  if $in_progress; then
    emit BLOCKER "repo: in-progress merge/rebase/cherry-pick — resolve before continuing"
  else
    emit OK "repo: working tree clean of in-progress operations"
  fi
}

# ---------- bucket: project runtime ----------------------------------------

# Parses HERO.md projects[] into the PROJECTS array. Each entry is a single
# line `name|path|port|dependency-file|dev-command`. Missing fields are empty.
parse_hero_projects() {
  awk '
    /^## Projects/        { in_projects = 1; next }
    in_projects && /^## / { in_projects = 0 }
    !in_projects          { next }
    /^### / {
      if (name != "") print name "|" path "|" port "|" depfile "|" devcmd
      name = $2; path = ""; port = ""; depfile = ""; devcmd = ""
      for (i = 3; i <= NF; i++) name = name " " $i
      next
    }
    /^- path:/             { sub(/^- path: */, ""); path = $0 }
    /^- port:/             { sub(/^- port: */, ""); port = $0 }
    /^- dependency-file:/  { sub(/^- dependency-file: */, ""); depfile = $0 }
    /^- dev-command:/      { sub(/^- dev-command: */, ""); devcmd = $0 }
    END {
      if (name != "") print name "|" path "|" port "|" depfile "|" devcmd
    }
  ' "$HERO" 2>/dev/null
}

check_runtime() {
  [ -f "$HERO" ] || { emit SKIP "runtime: HERO.md missing — cannot scope checks"; return 0; }

  local projects=()
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    projects+=("$line")
  done < <(parse_hero_projects)

  if [ "${#projects[@]}" -eq 0 ]; then
    emit SKIP "runtime: no projects[] section in HERO.md"
    return 0
  fi

  # Build the scope set if --projects was passed. Use a newline-separated
  # list with `grep -F` (fixed-string match) so paths containing regex
  # metacharacters (`.`, `+`, `*`) match literally, feeding raw user
  # input through `tr ',' '|'` into `grep -E` would over-match (e.g.
  # `.test-output` as ERE matches any string containing `test-output`).
  local scope_list=""
  if [ -n "$PROJECT_SCOPE" ]; then
    scope_list=$(printf '%s' "$PROJECT_SCOPE" | tr ',' '\n')
  fi

  local matched=0
  for entry in "${projects[@]}"; do
    IFS='|' read -r name proj_path port depfile devcmd <<< "$entry"
    [ -z "$proj_path" ] && proj_path="./"
    [ -z "$name" ] && name="(unnamed)"

    # Scope filter: skip projects whose name/proj_path doesn't substring-match
    # any entry in --projects. Substring match is fine because monorepo
    # paths are already unique top-level dirs.
    if [ -n "$scope_list" ]; then
      local in_scope=false needle
      while IFS= read -r needle; do
        [ -z "$needle" ] && continue
        case "$name $proj_path" in
          *"$needle"*) in_scope=true; break ;;
        esac
      done <<< "$scope_list"
      $in_scope || continue
    fi
    matched=$((matched+1))

    local proj_root="$ROOT/${proj_path#./}"
    proj_root="${proj_root%/}"

    if [ ! -d "$proj_root" ]; then
      emit WARN "runtime: project '$name' proj_path '$proj_path' does not exist"
      continue
    fi

    # 1. .env vs .env.example key parity
    if [ -f "$proj_root/.env.example" ]; then
      local example_keys env_keys missing
      example_keys=$(grep -E '^[A-Z_][A-Z0-9_]*=' "$proj_root/.env.example" 2>/dev/null | cut -d= -f1 | sort -u || true)
      if [ -f "$proj_root/.env" ] || [ -f "$proj_root/.env.local" ]; then
        env_keys=$(cat "$proj_root/.env" "$proj_root/.env.local" 2>/dev/null \
          | grep -E '^[A-Z_][A-Z0-9_]*=' | cut -d= -f1 | sort -u || true)
        missing=$(comm -23 <(printf '%s\n' "$example_keys") <(printf '%s\n' "$env_keys") | grep -v '^$' || true)
        if [ -n "$missing" ]; then
          emit BLOCKER "runtime: $name: .env missing keys from .env.example: $(printf '%s' "$missing" | tr '\n' ',' | sed 's/,$//')"
        else
          emit OK "runtime: $name: .env covers all .env.example keys"
        fi
      else
        emit BLOCKER "runtime: $name: .env.example present but no .env / .env.local — copy and fill it in"
      fi
    else
      emit SKIP "runtime: $name: no .env.example"
    fi

    # 2. Declared port is free (only meaningful if a dev-command exists)
    if [ -n "$port" ] && [ -n "$devcmd" ] && [ "$devcmd" != "none" ]; then
      if command -v lsof >/dev/null 2>&1; then
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
          local owner
          owner=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -F c 2>/dev/null | awk '/^c/ {print substr($0,2); exit}')
          emit WARN "runtime: $name: port $port already in use by '${owner:-unknown}' — dev server / smoke test may collide"
        else
          emit OK "runtime: $name: port $port free"
        fi
      else
        emit SKIP "runtime: $name: lsof unavailable — cannot check port $port"
      fi
    fi

    # 3. Dependency file present
    if [ -n "$depfile" ] && [ "$depfile" != "none" ]; then
      if [ -f "$proj_root/$depfile" ]; then
        emit OK "runtime: $name: dependency file $depfile present"
      else
        emit BLOCKER "runtime: $name: dependency file $depfile missing"
      fi
    fi
  done

  # If --projects was passed but nothing matched, surface that explicitly
  # so the bucket isn't silently empty (otherwise the user sees only the
  # "no projects[] section" SKIP and misreads it as "all clear").
  if [ -n "$scope_list" ] && [ "$matched" -eq 0 ]; then
    emit SKIP "runtime: no HERO.md project matches --projects '$PROJECT_SCOPE'"
  fi
}

# ---------- bucket: pipeline-specific --------------------------------------

check_pipeline() {
  ensure_gh_auth_probed

  # 1. Default branch reachable on origin. Use `git ls-remote --exit-code`
  # instead of `git fetch`, same network round-trip for reachability but
  # ~10× faster (single ref query, no objects pulled, no local refs updated).
  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git -C "$ROOT" ls-remote --exit-code --heads origin "$DEFAULT_BRANCH" >/dev/null 2>&1; then
      emit OK "pipeline: origin/$DEFAULT_BRANCH reachable"
    else
      emit BLOCKER "pipeline: cannot reach origin/$DEFAULT_BRANCH — check network/auth"
    fi
  else
    emit BLOCKER "pipeline: not inside a git work tree"
  fi

  # 2. Issue tracker auth (only if HERO.md declares one)
  local tracker rc nudge
  # Two things must not be swallowed here. The stderr is hero_connection_compat's
  # migration nudge, which is the whole point of the fallback existing, and rc 2
  # is a value someone WROTE and the reader refused — reported as an empty
  # tracker it lands in the `none` arm and this check says "no issue tracker
  # configured" for a repo that has one it cannot trust.
  nudge=$(mktemp) || { emit WARN "pipeline: cannot create a temp file for the tracker probe"; return 0; }
  tracker=$(hero_connection_compat issues type tool "$ROOT" 2>"$nudge"); rc=$?
  if [ "$rc" = 1 ]; then
    tracker=$(hero_connection_compat issues type issue-tracker "$ROOT" 2>"$nudge"); rc=$?
  fi
  # Every line: a refusal and a migration nudge can both be waiting, and
  # `head -1` reports whichever came first and drops the other.
  [ -s "$nudge" ] && while IFS= read -r line; do emit WARN "pipeline: $line"; done < "$nudge"
  rm -f "$nudge"
  if [ "$rc" = 2 ]; then
    emit BLOCKER "pipeline: the issues connection's type was REJECTED as unsafe — fix HERO.md"
    return 0
  fi
  case "${tracker:-none}" in
    linear)
      # Linear MCP is the usual integration. We can't probe Anthropic's
      # MCP auth state from bash, so check whether a `linear` CLI or
      # LINEAR_API_KEY env var is present.
      if [ -n "${LINEAR_API_KEY:-}" ] || command -v linear >/dev/null 2>&1; then
        emit OK "pipeline: linear credentials detected"
      else
        emit WARN "pipeline: HERO.md says the issues connection is linear but no LINEAR_API_KEY / linear CLI found — Step 1 (plan) may prompt to re-auth"
      fi
      ;;
    jira)
      if [ -n "${JIRA_API_TOKEN:-}" ] && [ -n "${JIRA_EMAIL:-}" ]; then
        emit OK "pipeline: jira credentials detected"
      else
        emit WARN "pipeline: HERO.md says the issues connection is jira but JIRA_API_TOKEN / JIRA_EMAIL not set — Step 1 (plan) may fail to fetch tickets"
      fi
      ;;
    # `self` is legal on every connection (docs/CONNECTIONS.md) and for a
    # tracker it means "this repo's own GitHub issues". Without this arm it
    # falls to `*)` and SKIPs, so a repo whose tracker is its own issues passes
    # preflight with gh logged out.
    github-issues|github|self)
      # Reuse GH_AUTH_OK from check_tooling rather than re-shell gh auth.
      if [ "${GH_AUTH_OK:-false}" = "true" ]; then
        emit OK "pipeline: github-issues uses the gh auth checked above"
      else
        emit BLOCKER "pipeline: HERO.md says the issues connection is github but gh is not authenticated"
      fi
      ;;
    none|"")
      emit SKIP "pipeline: no issue tracker configured (plain-description plans only)"
      ;;
    *)
      emit SKIP "pipeline: unknown issue tracker '$tracker' — auth check skipped"
      ;;
  esac
}

# ---------- dispatch -------------------------------------------------------

case "$BUCKET" in
  tooling)  check_tooling ;;
  repo)     check_repo ;;
  runtime)  check_runtime ;;
  pipeline) check_pipeline ;;
  all)
    check_tooling
    check_repo
    check_runtime
    check_pipeline
    ;;
  # Internal, set only by --auto-scope on a fresh start: everything except the
  # runtime bucket, which needs a diff to be meaningful. Not accepted from the
  # command line (the --bucket validator above rejects it).
  no-runtime)
    check_tooling
    check_repo
    check_pipeline
    ;;
esac

# ---------- summary --------------------------------------------------------

echo ""
if [ "$BLOCKERS" -gt 0 ]; then
  echo "preflight: $BLOCKERS blocker(s), $WARNINGS warning(s); pipeline will fail. Fix blockers above before running wayfare:wayfare-build-task."
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "preflight: 0 blockers, $WARNINGS warning(s): safe to proceed, warnings are advisory."
  exit 0
else
  echo "preflight: all checks passed."
  exit 0
fi
