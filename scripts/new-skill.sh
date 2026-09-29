#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Scaffold a new hero skill.
# Usage: ./scripts/new-skill.sh <skill-name> [description]
# Example: ./scripts/new-skill.sh deploy "Deploy to production environments"

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$PLUGIN_ROOT/skills"

# ─── Parse args ───────────────────────────────────────────────────

SKILL_NAME="${1:-}"
DESCRIPTION="${*:2}"

if [[ -z "$SKILL_NAME" ]]; then
  echo "Usage: $0 <skill-name> [description]"
  echo ""
  echo "Examples:"
  echo "  $0 deploy \"Deploy to production environments\""
  echo "  $0 lint \"Run linters across all projects\""
  exit 1
fi

# Validate kebab-case
if [[ ${#SKILL_NAME} -gt 64 || ! "$SKILL_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "Error: skill name must be 1-64 chars of lowercase letters, digits and single hyphens, none leading or trailing. Got: $SKILL_NAME"
  exit 1
fi

# Check if exists
if [[ -d "$SKILLS_DIR/$SKILL_NAME" ]]; then
  echo "Error: skill '$SKILL_NAME' already exists at $SKILLS_DIR/$SKILL_NAME"
  exit 1
fi

# Default description
if [[ -z "$DESCRIPTION" ]]; then
  DESCRIPTION="TODO: Describe what this skill does and when to use it. Include trigger phrases."
fi

# Title-case the skill name for the H1 heading. Use a portable approach
# (tr + cut) instead of Bash 4's ${var^} since macOS ships Bash 3.2.
SKILL_TITLE="$(echo "${SKILL_NAME:0:1}" | tr '[:lower:]' '[:upper:]')${SKILL_NAME:1}"

# ─── Create skill ─────────────────────────────────────────────────

# Quoted, because a description routinely contains ": ", which ends an
# unquoted YAML scalar and makes the whole frontmatter fail to parse.
DESCRIPTION_YAML=${DESCRIPTION//\\/\\\\}
DESCRIPTION_YAML=${DESCRIPTION_YAML//\"/\\\"}

mkdir -p "$SKILLS_DIR/$SKILL_NAME"

cat > "$SKILLS_DIR/$SKILL_NAME/SKILL.md" << EOF
---
name: $SKILL_NAME
# prettier-ignore
description: "$DESCRIPTION_YAML"
argument-hint: [args]
compatibility: "Requires the complete Wayfare plugin. Replace this sentence with the actual runtime tools and network requirements."
# Omit the next line for skills meant to be model-invocable / chained by an
# orchestrator like wayfare-build-task (a user-only skill cannot be called
# through the active client's skill mechanism).
disable-model-invocation: true
---

# ${SKILL_TITLE} (TODO: Title)

TODO: Brief description of what this skill does.

## Arguments

- \`\$ARGUMENTS\` - TODO: describe arguments

## Instructions

### Step 0: Load Hero Configuration

\`\`\`bash
ROOT=\$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "\$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "\$PWD/FLEET.md" ] && [ ! -f "\$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
\`\`\`

If \`FLEET_ROOT\` printed, this folder is a fleet, not a repo: stop and follow **At the fleet root** in \`docs/FLEET-MD.md\`.

Read \`HERO.md\` if it exists. This skill uses:
- TODO: list which HERO.md sections this skill reads

Use capability language rather than naming one client's file, shell, skill, or
subagent tools. For client translation and authorization gates, read
\`../../references/client-capabilities.md\` and
\`../../references/authorization.md\` only when this workflow needs them.

If \`HERO.md\` is missing, suggest \`wayfare:wayfare-init-repo\` but proceed with auto-detection.

### Step 1: TODO

TODO: First step of the skill.

### Step 2: TODO

TODO: Second step.

## Gotchas

- TODO: facts about this environment the agent would get wrong without
  being told. Delete the section if there are none.

## Examples

\`\`\`
/$SKILL_NAME                # TODO: example usage
\`\`\`
EOF

echo "Created: $SKILLS_DIR/$SKILL_NAME/SKILL.md"
echo ""
echo "Next steps:"
echo "  1. Edit $SKILLS_DIR/$SKILL_NAME/SKILL.md (keep it under 500 lines; longer material goes in references/)"
echo "  2. Run ./scripts/validate.sh to check"
echo "  3. Commit and push"
