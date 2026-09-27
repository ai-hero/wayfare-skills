---
name: wayfare-setup-dev
# prettier-ignore
description: Set up a developer's local environment. Reads HERO.md, checks required tools, guides through git config, CLI auth, and missing dependencies. Per-developer, and never modifies shared files. Use on a fresh machine or clone, or when a tool or login is missing.
argument-hint: "[--check | recalibrate]"
disable-model-invocation: true
---

# Setup: get a developer's machine ready

Guide an individual developer through setting up their local environment based
on the team's `HERO.md` configuration. This skill handles everything that is
per-developer and should NOT be committed to the repo.

## Arguments

- `recalibrate` - Tune the `HERO.md` fields this skill reads, then stop (see
  below). Matched before every other form.
- `$ARGUMENTS`:
  - (none) - Full guided setup
  - `--check` - Only verify the current setup and report what is missing

## Prerequisites

`HERO.md` must exist. If it doesn't, tell the user:

```
No HERO.md found. Run wayfare:wayfare-init-repo first to configure the project.
```

## `recalibrate`

`wayfare:wayfare-setup-dev recalibrate` tunes the config that drives this skill,
and stops. It does not go on to run the skill. You want to see which field was
wrong, not spend a whole run finding out.

Dispatch on it before parsing any other argument, in whichever step does that
parsing. When the first token of `$ARGUMENTS` is exactly `recalibrate`, print
`wayfare-setup-dev: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md) (report, ask, write, commit)
using the table below as the report, and stop.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-setup-dev
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

## Instructions

### Step 1: Read HERO.md

**If the first token of `$ARGUMENTS` is exactly `recalibrate`, run the
`recalibrate` section above and stop.** Do this before the missing-HERO.md check
below, which would otherwise send the user to `wayfare-init-repo` for the very
file the verb exists to fill in.

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

Parse the `## Developer Setup` section for required tools, recommended tools,
and MCP servers. Also read other sections for implicit requirements (e.g., CI
platform → `gh`, deployment platform → `kubectl`).

### Step 2: Check Git Configuration

```bash
# Local git config
git config --local user.name
git config --local user.email

# Global fallback
git config --global user.name
git config --global user.email

# Signing
git config --local commit.gpgsign
git config --global commit.gpgsign
git config --local gpg.format

# Remote
git remote -v
```

**Present findings:**

```
GIT CONFIGURATION
─────────────────
[OK] user.name: "Jane Doe" (global)
[OK] user.email: "jane@company.com" (global)
[--] No local git config — using global values
     → Set local config for this repo? (useful if you use a different
       email for work vs personal projects)
[--] Commit signing: not configured
     → Set up GPG/SSH signing? (recommended for verified commits)
```

**If local config is missing**, offer to set it:

```bash
git config --local user.name "USER_NAME"
git config --local user.email "USER_EMAIL"
```

Ask the user. Never auto-set identity config without confirmation.

### Step 3: Check Required CLI Tools

For each tool in HERO.md `## Developer Setup → Required Tools`:

```bash
which TOOL_NAME 2>/dev/null && TOOL_NAME --version 2>/dev/null
```

**Present findings:**

```
REQUIRED TOOLS
──────────────
[OK] node: v20.11.0 (required: >=20) ✓
[OK] pnpm: 9.1.0 ✓
[OK] docker: 24.0.7 ✓
[!!] gh: not installed
     → Required for PR workflows. Install: brew install gh
[!!] tofu: not installed
     → Required for infrastructure. Install: brew install opentofu
     ⚠ Do NOT install terraform — this project uses OpenTofu
```

For missing tools, provide **platform-appropriate install commands**:

- macOS: `brew install TOOL_NAME`
- Linux: distro-appropriate (apt, dnf, pacman) or official install script
- Suggest the user's package manager if detectable

### Step 4: Check Authentication & Access

For each installed CLI tool that requires auth:

```bash
# GitHub
gh auth status 2>&1

# AWS
aws sts get-caller-identity 2>&1

# GCP
gcloud auth list 2>&1

# kubectl
kubectl cluster-info 2>&1

# Docker registry
docker info 2>&1 | grep -i registry

# Linear
linear whoami 2>&1 || linear auth status 2>&1
```

**Present findings:**

```
AUTHENTICATION
──────────────
[OK] gh: authenticated as jane-doe (github.com)
[!!] aws: not authenticated
     → Run: aws configure (or aws sso login)
[OK] kubectl: connected to staging-cluster
[--] linear: CLI not installed (recommended, not required)
```

Only check auth for tools that are actually installed AND relevant to HERO.md.

### Step 5: Check Recommended Tools

Same as Step 3 but for `## Developer Setup → Recommended Tools`. Use `[--]`
instead of `[!!]` for missing recommended tools. They are nice to have, not
blockers.

```
RECOMMENDED TOOLS
─────────────────
[OK] pre-commit: 3.6.0 ✓
[--] linear: not installed
     → Optional CLI for issue management. Install: npm i -g @linear/cli
```

### Step 6: Check MCP Servers

If HERO.md lists MCP servers:

```
MCP SERVERS
───────────
[??] linear (mcp__linear): listed in HERO.md
     → Is the Linear MCP server configured in your Claude settings?
     → This is needed for wayfare:wayfare-build-task to fetch issues
[??] slack (mcp__slack): listed in HERO.md
     → Is the Slack MCP server configured in your Claude settings?
```

MCP server setup happens in the client's settings, not on the command line. Tell
the user what is expected and why.

### Step 7: Summary & Next Steps

**If `--check` was passed**, just show the summary and exit.

**For full setup**, after each section offer to fix what's missing. Then show
final summary:

```
SETUP SUMMARY
═════════════
Git config:     ✓ local user.name and user.email set
Required tools: ✓ all 5 installed
Authentication: ⚠ 1 issue — aws not authenticated
Recommended:    ✓ 2/2 installed
MCP servers:    ? 1 to verify — linear

Remaining action items:
  1. Run: aws sso login
  2. Verify Linear MCP server is configured in Claude settings

Your environment is ready for development! 🎉
Run wayfare:wayfare-init-repo recalibrate if the project setup has changed.

Next step: wayfare:wayfare-check-preflight — sanity-check tooling, .env, ports before starting (print only — model-invocation-restricted, cannot auto-run)
```

Don't also print `wayfare:wayfare-build-task`; `wayfare-check-preflight`'s own
next-steps lead there once it passes.

## Key Principles

- **Never modify shared files.** This skill only touches local git config and
  suggests installs. It never writes to HERO.md, CLAUDE.md, or any committed
  file.
- **Always ask before changing config.** Git identity, signing keys, and auth
  are personal. Confirm before setting any of them.
- **Platform-aware.** Detect macOS vs Linux and suggest the right install
  commands.
- **Idempotent.** Running `wayfare:wayfare-setup-dev` twice should be safe. Skip
  whatever is already done.
- **Reference HERO.md.** Every check should tie back to why it's needed:
  "Required by HERO.md for wayfare:wayfare-push-pr" or "Used by CI (GitHub
  Actions)".

## Examples

```
wayfare:wayfare-setup-dev          # Full guided setup
wayfare:wayfare-setup-dev --check  # Just verify, don't change anything
```
