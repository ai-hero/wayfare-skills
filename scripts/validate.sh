#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Validate wayfare plugin structure against Claude Code official requirements.
# Usage: ./scripts/validate.sh [--verbose]

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0
WARNINGS=0
VERBOSE="${1:-}"

red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
dim()    { printf "\033[2m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

error() {
  red "  ERROR: $1"
  if [[ -n "${2:-}" ]]; then
    dim "         File: $2"
  fi
  if [[ -n "${3:-}" ]]; then
    dim "         Line: $3"
  fi
  if [[ -n "${4:-}" ]]; then
    printf "\033[36m         Fix:  %s\033[0m\n" "$4"
  fi
  ERRORS=$((ERRORS + 1))
}

warn() {
  yellow "  WARN:  $1"
  if [[ -n "${2:-}" ]]; then
    dim "         File: $2"
  fi
  if [[ -n "${3:-}" ]]; then
    printf "\033[36m         Fix:  %s\033[0m\n" "$3"
  fi
  WARNINGS=$((WARNINGS + 1))
}

pass() {
  if [[ "$VERBOSE" == "--verbose" ]]; then
    green "  OK:    $*"
  fi
}

strip_fences_and_comments() { # FILE -> prints it with fenced ``` blocks and lines mentioning <!-- removed
  awk '
    /^```/           { fence = !fence; next }
    fence            { next }
    /<!--/           { next }
    { print }
  ' "$1"
}

echo ""
bold "Hero Skills Plugin Validator"
echo "────────────────────────────"
echo ""

# ─── Plugin Manifest ──────────────────────────────────────────────

bold "1. Plugin Manifest"

MANIFEST="$PLUGIN_ROOT/.claude-plugin/plugin.json"
MANIFEST_REL=".claude-plugin/plugin.json"
# Defaulted so section 2b can read them under `set -u`. Empty here means one
# of three things: the manifest is missing, its JSON is invalid, or it parsed
# fine but has no "version" key — section 1 above already reported which.
NAME=""
VERSION=""

if [[ ! -f "$MANIFEST" ]]; then
  error "Missing plugin manifest" \
    "$MANIFEST_REL" \
    "" \
    "Create .claude-plugin/plugin.json with at minimum: { \"name\": \"your-plugin-name\" }"
else
  if ! jq empty "$MANIFEST" 2>/dev/null; then
    error "Invalid JSON syntax" \
      "$MANIFEST_REL" \
      "" \
      "Run: jq . $MANIFEST_REL to see the parse error, then fix the JSON"
  else
    pass "plugin.json is valid JSON"

    NAME=$(jq -r '.name // empty' "$MANIFEST")
    if [[ -z "$NAME" ]]; then
      error "Missing required 'name' field" \
        "$MANIFEST_REL" \
        "" \
        "Add a \"name\" field: { \"name\": \"my-plugin\" } — must be kebab-case"
    elif [[ ! "$NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
      error "Plugin name '$NAME' is not kebab-case" \
        "$MANIFEST_REL" \
        "$(grep -n '"name"' "$MANIFEST" | head -1 | cut -d: -f1)" \
        "Use lowercase letters and hyphens only, e.g. \"my-plugin-name\""
    else
      pass "name: $NAME"
    fi

    VERSION=$(jq -r '.version // empty' "$MANIFEST")
    if [[ -n "$VERSION" && ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      warn "Version '$VERSION' is not valid semver" \
        "$MANIFEST_REL" \
        "Use format X.Y.Z, e.g. \"1.0.0\""
    else
      pass "version: ${VERSION:-not set}"
    fi

    DESC=$(jq -r '.description // empty' "$MANIFEST")
    if [[ -z "$DESC" ]]; then
      warn "No description in plugin manifest" \
        "$MANIFEST_REL" \
        "Add a \"description\" field to help users understand what this plugin does"
    else
      pass "description present"
    fi
  fi
fi

echo ""

# ─── Marketplace Manifest ─────────────────────────────────────────

bold "2. Marketplace Manifest"

MARKETPLACE="$PLUGIN_ROOT/.claude-plugin/marketplace.json"
MARKETPLACE_REL=".claude-plugin/marketplace.json"

if [[ ! -f "$MARKETPLACE" ]]; then
  pass "marketplace.json not found (optional — only needed for publishing)"
else
  if ! jq empty "$MARKETPLACE" 2>/dev/null; then
    error "Invalid JSON syntax" \
      "$MARKETPLACE_REL" \
      "" \
      "Run: jq . $MARKETPLACE_REL to see the parse error"
  else
    pass "marketplace.json is valid JSON"
  fi
fi

echo ""

# ─── Cross-Agent Manifests ────────────────────────────────────────

bold "2b. Cross-Agent Manifests"

AGENTS_MANIFEST="$PLUGIN_ROOT/.agents/plugins/marketplace.json"
AGENTS_MANIFEST_REL=".agents/plugins/marketplace.json"
PORTABLE_MANIFEST="$PLUGIN_ROOT/plugin.json"
PORTABLE_MANIFEST_REL="plugin.json"

if [[ ! -f "$PORTABLE_MANIFEST" ]]; then
  error "Missing cross-agent plugin manifest" "$PORTABLE_MANIFEST_REL" "" \
    "Create $PORTABLE_MANIFEST_REL so Agent Plugin hosts and Cursor can load this package"
elif ! jq empty "$PORTABLE_MANIFEST" 2>/dev/null; then
  error "Invalid JSON syntax" "$PORTABLE_MANIFEST_REL" "" \
    "Run: jq . $PORTABLE_MANIFEST_REL to see the parse error, then fix the JSON"
else
  pass "$PORTABLE_MANIFEST_REL is valid JSON"
fi

if [[ -f "$PORTABLE_MANIFEST" ]] && jq empty "$PORTABLE_MANIFEST" 2>/dev/null; then
  PORTABLE_SCHEMA=$(jq -r '.["$schema"] // empty' "$PORTABLE_MANIFEST")
  [[ "$PORTABLE_SCHEMA" == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json" ]] || \
    error "Portable manifest has the wrong or missing Agent Plugins schema" \
      "$PORTABLE_MANIFEST_REL" "" \
      "Set \"\$schema\" to https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
fi

if [[ -f "$PORTABLE_MANIFEST" ]] && jq empty "$PORTABLE_MANIFEST" 2>/dev/null; then
  other_name=$(jq -r '.name // empty' "$PORTABLE_MANIFEST")
  other_version=$(jq -r '.version // empty' "$PORTABLE_MANIFEST")
  [[ "$other_name" == "$NAME" ]] || error "$PORTABLE_MANIFEST_REL name '$other_name' disagrees with '$NAME'" \
    "$PORTABLE_MANIFEST_REL" "" "Set \"name\": \"$NAME\""
  [[ "$other_version" == "$VERSION" ]] || error "$PORTABLE_MANIFEST_REL version '$other_version' disagrees with '$VERSION'" \
    "$PORTABLE_MANIFEST_REL" "" "Set \"version\": \"$VERSION\""
fi

CLAUDE_SKILLS=$(jq -r '.skills // empty' "$MANIFEST" 2>/dev/null)
if [[ -n "$CLAUDE_SKILLS" && "$CLAUDE_SKILLS" != "./skills/" ]]; then
  error "Plugin manifest's \"skills\" is '$CLAUDE_SKILLS', not './skills/'" \
    "$MANIFEST_REL" "" "Set \"skills\": \"./skills/\" in $MANIFEST_REL"
fi

# `(.plugins // [])[]?` so a manifest whose .plugins is missing, null, or not
# an array reports zero matching entries instead of aborting the whole
# script under `set -e` on the first manifest that doesn't have one.
check_plugins_entry() {  # $1=required(true/false) $2=label $3=file $4=rel_path
  local required="$1" label="$2" file="$3" rel="$4"
  if [[ ! -f "$file" ]]; then
    [[ "$required" == true ]] && error "Missing $label" "$rel" "" \
      "Create $rel with a .plugins[] entry named \"$NAME\""
    return
  fi
  if ! jq empty "$file" 2>/dev/null; then
    error "Invalid JSON syntax" "$rel" "" "Run: jq . $rel to see the parse error, then fix the JSON"
    return
  fi
  local count
  count=$(jq -r --arg name "$NAME" '[(.plugins // [])[]? | select(.name == $name)] | length' "$file")
  case "$count" in
    0) error "no .plugins entry named '$NAME' in $label" "$rel" "" \
         "Add a .plugins[] entry with \"name\": \"$NAME\"" ;;
    1) pass "$rel: .plugins entry named $NAME" ;;
    *) error "more than one .plugins entry named '$NAME' in $label" "$rel" "" \
         "Keep exactly one .plugins[] entry named \"$NAME\"" ;;
  esac
}
check_plugins_entry false "the marketplace manifest" "$MARKETPLACE" "$MARKETPLACE_REL"
check_plugins_entry true "the .agents manifest" "$AGENTS_MANIFEST" "$AGENTS_MANIFEST_REL"

echo ""

# ─── Skills ───────────────────────────────────────────────────────

bold "3. Skills"

SKILLS_DIR="$PLUGIN_ROOT/skills"

if [[ ! -d "$SKILLS_DIR" ]]; then
  error "Missing skills/ directory" \
    "" \
    "" \
    "Create a skills/ directory and add skill subdirectories, each with a SKILL.md"
else
  SKILL_COUNT=0
  SKILL_PASS=0

  for skill_dir in "$SKILLS_DIR"/*/; do
    [[ -d "$skill_dir" ]] || continue
    SKILL_NAME=$(basename "$skill_dir")
    SKILL_COUNT=$((SKILL_COUNT + 1))
    SKILL_ERRORS_BEFORE=$ERRORS

    SKILL_FILE="$skill_dir/SKILL.md"
    SKILL_REL="skills/$SKILL_NAME/SKILL.md"

    # 1. SKILL.md exists
    if [[ ! -f "$SKILL_FILE" ]]; then
      error "Missing SKILL.md" \
        "skills/$SKILL_NAME/" \
        "" \
        "Create $SKILL_REL with YAML frontmatter (--- delimited) containing 'name' and 'description'"
      continue
    fi

    # 2. Extract frontmatter
    FRONTMATTER=$(awk '/^---$/{n++; next} n==1{print} n>=2{exit}' "$SKILL_FILE")

    if [[ -z "$FRONTMATTER" ]]; then
      error "No YAML frontmatter found" \
        "$SKILL_REL" \
        "1" \
        "Add frontmatter at the top: ---\\nname: $SKILL_NAME\\ndescription: What this skill does\\n---"
      continue
    fi

    # 3. Name field
    FM_NAME=$(echo "$FRONTMATTER" | grep -E '^name:' | sed 's/^name:[[:space:]]*//' | head -1 || true)
    NAME_LINE=$(grep -n '^name:' "$SKILL_FILE" | head -1 | cut -d: -f1 || true)

    if [[ -z "$FM_NAME" ]]; then
      error "Frontmatter missing 'name' field" \
        "$SKILL_REL" \
        "2" \
        "Add 'name: $SKILL_NAME' to the frontmatter block"
    elif [[ ${#FM_NAME} -gt 64 || ! "$FM_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
      error "Name '$FM_NAME' breaks the Agent Skills name rules (1-64 chars, lowercase letters, digits and single hyphens, none leading or trailing)" \
        "$SKILL_REL" \
        "$NAME_LINE" \
        "Change to: name: $(echo "$FM_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')"
    elif [[ "$FM_NAME" != "$SKILL_NAME" ]]; then
      warn "Frontmatter name '$FM_NAME' doesn't match directory name '$SKILL_NAME'" \
        "$SKILL_REL" \
        "$NAME_LINE" \
        "Either rename the directory to '$FM_NAME/' or change frontmatter to 'name: $SKILL_NAME'"
    else
      pass "$SKILL_NAME: name OK"
    fi

    # 4. Description field
    FM_DESC=$(echo "$FRONTMATTER" | grep -E '^description:' | sed 's/^description:[[:space:]]*//' | head -1 || true)
    DESC_LINE=$(grep -n '^description:' "$SKILL_FILE" | head -1 | cut -d: -f1 || true)

    if [[ -z "$FM_DESC" ]]; then
      error "Frontmatter missing 'description' field" \
        "$SKILL_REL" \
        "${DESC_LINE:-3}" \
        "Add 'description: What this skill does. Use when user asks to \"trigger phrase\".' — be specific about when to trigger"
    elif [[ ${#FM_DESC} -lt 20 ]]; then
      warn "Description is only ${#FM_DESC} chars — too short to be useful" \
        "$SKILL_REL" \
        "$DESC_LINE" \
        "Expand to include what the skill does AND trigger phrases (e.g. 'Use when...'). Aim for 50+ chars."
    else
      pass "$SKILL_NAME: description (${#FM_DESC} chars)"
    fi

    # 5. Body content
    BODY=$(awk '/^---$/{n++; next} n>=2{found=1; print}' "$SKILL_FILE")
    BODY_START_LINE=$(awk '/^---$/{n++; if(n==2){print NR+1; exit}}' "$SKILL_FILE")

    if [[ -z "$BODY" ]]; then
      error "No body content after frontmatter" \
        "$SKILL_REL" \
        "$BODY_START_LINE" \
        "Add skill instructions after the closing --- delimiter"
    else
      pass "$SKILL_NAME: body content present"
    fi

    # 6/7. Size budget, per activation entrypoint. Agent Skills loads all of
    # SKILL.md on activation, so no pipeline gets a larger exception. Detailed
    # executable specifications belong in skill-local resources and are loaded
    # only when the entrypoint routes execution to them.
    LIMIT_LINES=500; LIMIT_WORDS=5000

    LINE_COUNT=$(wc -l < "$SKILL_FILE" | tr -d ' ')
    if [[ $LINE_COUNT -gt $LIMIT_LINES ]]; then
      warn "SKILL.md is $LINE_COUNT lines (recommended: under $LIMIT_LINES)" \
        "$SKILL_REL" \
        "" \
        "Move detailed content to references/ and link it from the body with the condition under which to read it"
    else
      pass "$SKILL_NAME: $LINE_COUNT lines"
    fi

    WORD_COUNT=$(wc -w < "$SKILL_FILE" | tr -d ' ')
    if [[ $WORD_COUNT -gt $LIMIT_WORDS ]]; then
      warn "SKILL.md is $WORD_COUNT words (recommended: under $LIMIT_WORDS)" \
        "$SKILL_REL" \
        "" \
        "Large skills consume context window. Split into references/ loaded on demand, each linked from the body with a load condition"
    else
      pass "$SKILL_NAME: $WORD_COUNT words"
    fi

    # 7a. Wayfare skills depend on plugin-global scripts and references. Make
    # that package boundary explicit with the standard compatibility field so
    # a client does not mistake one directory for a standalone skill bundle.
    FM_COMPAT=$(echo "$FRONTMATTER" | grep -E '^compatibility:' | sed 's/^compatibility:[[:space:]]*//' | head -1 || true)
    if [[ -z "$FM_COMPAT" ]]; then
      error "Frontmatter missing the Agent Skills compatibility field" \
        "$SKILL_REL" "" \
        "Describe the complete Wayfare plugin and any runtime tools this skill requires"
    elif [[ ${#FM_COMPAT} -gt 502 ]]; then
      # The shell reads the YAML representation, including a possible pair of
      # quotes. Two extra characters preserve the specification's 500-character
      # value limit without needing a second YAML parser here.
      error "Compatibility value exceeds the Agent Skills 500-character limit" \
        "$SKILL_REL" "" \
        "Keep compatibility to the package and runtime requirements"
    else
      pass "$SKILL_NAME: compatibility declared"
    fi

    # A detailed executable specification is useful only when the activation
    # entrypoint routes to it. An unlinked WORKFLOW.md silently preserves old
    # prose while the active skill forgets the actual procedure.
    if [[ -f "$skill_dir/WORKFLOW.md" ]]; then
      if grep -qF '[WORKFLOW.md](WORKFLOW.md)' "$SKILL_FILE"; then
        pass "$SKILL_NAME: executable specification is discoverable"
      else
        error "WORKFLOW.md exists but SKILL.md does not route to it" \
          "$SKILL_REL" "" \
          "Link [WORKFLOW.md](WORKFLOW.md) and state when it must be read"
      fi
    fi

    # Activation entrypoints use capability language. Product names remain
    # valid when they identify real infrastructure or client metadata, but
    # portable operations must not assume another client's tool call syntax.
    CLIENT_TOOL_HITS=$(grep -nE 'via (the )?Skill tool|Use (the )?(Read|Bash) tool|Agent\(subagent_type=' "$SKILL_FILE" || true)
    if [[ -n "$CLIENT_TOOL_HITS" ]]; then
      error "SKILL.md hard-codes client tool syntax" \
        "$SKILL_REL" \
        "$(printf '%s' "$CLIENT_TOOL_HITS" | head -1 | cut -d: -f1)" \
        "Describe the capability and route through references/client-capabilities.md"
    else
      pass "$SKILL_NAME: activation language is client-neutral"
    fi

    # 8. `../../references/NAME` paths the body names must exist. This
    # matches the ../../ form deliberately: the earlier version keyed on a
    # per-skill `references/` directory, and when the tree moved to the
    # plugin root no skill had one any more, so the guard's `-d` test was
    # false for every skill and it checked nothing. It went unnoticed
    # because a dead guard and a passing guard print the same thing.
    # create-skill names bare `references/` paths as examples and ships
    # none; the ../../ prefix is what separates a real path from a sample.
    REF_PATHS=$(grep -oE '\.\./\.\./references/[A-Za-z0-9._-]+\.md' "$SKILL_FILE" | sort -u || true)
    while IFS= read -r ref; do
      [[ -n "$ref" ]] || continue
      if [[ ! -f "$PLUGIN_ROOT/${ref#../../}" ]]; then
        REF_LINE=$(grep -nF "$ref" "$SKILL_FILE" | head -1 | cut -d: -f1 || true)
        error "'$ref' is named in the body but does not exist" \
          "$SKILL_REL" \
          "$REF_LINE" \
          "Create ${ref#../../} at the plugin root or fix the path in the body"
      else
        pass "$SKILL_NAME: $ref exists"
      fi
    done <<< "$REF_PATHS"

    # 9. Empty subdirectories
    for subdir in references scripts examples assets; do
      if [[ -d "$skill_dir/$subdir" ]]; then
        file_count=$(find "$skill_dir/$subdir" -type f | wc -l | tr -d ' ')
        if [[ $file_count -eq 0 ]]; then
          warn "skills/$SKILL_NAME/$subdir/ exists but is empty" \
            "skills/$SKILL_NAME/$subdir/" \
            "Add files or remove the empty directory"
        else
          pass "$SKILL_NAME: $subdir/ ($file_count files)"
        fi
      fi
    done

    # Track per-skill pass/fail
    if [[ $ERRORS -eq $SKILL_ERRORS_BEFORE ]]; then
      SKILL_PASS=$((SKILL_PASS + 1))
    fi

  done

  echo ""
  echo "  Skills: $SKILL_PASS/$SKILL_COUNT passed"
fi

# ── WAYFARE_ROOT: script resolution has exactly one sanctioned line ────────
# CLAUDE_PLUGIN_ROOT does not exist outside Claude Code.
# Every site that resolves the plugin root must use the identical
# WAYFARE_ROOT line, so an agent that exports WAYFARE_ROOT itself
# (references/loading.md's rule) reaches every script, not just the ones a
# past edit remembered to route through it. A stray CLAUDE_PLUGIN_ROOT
# default is invisible to that export.
SANCTIONED_WAYFARE_ROOT_LINE='WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"'
WAYFARE_ROOT_ERRORS=0
WAYFARE_ROOT_FILES_SCANNED=0
while IFS= read -r f; do
  WAYFARE_ROOT_FILES_SCANNED=$((WAYFARE_ROOT_FILES_SCANNED + 1))
  # Scoped to fenced code, not prose: loading.md and check-preflight's own
  # Step 1 text NAME CLAUDE_PLUGIN_ROOT to explain WAYFARE_ROOT, and that
  # explanation is the point, not a stray resolver to flag. The fence toggle
  # allows leading whitespace and either ``` or ~~~, so an indented or ~~~
  # fence still hides its prose from the scan.
  hits=$(awk '
    /^[[:space:]]*(```|~~~)/ { infence = !infence; next }
    infence && (/CLAUDE_PLUGIN_ROOT/ || /plugins\/wayfare-skills\/scripts/ || /\.claude\/plugins\/wayfare-skills/) { print NR":"$0 }
  ' "$f" || true)
  [ -z "$hits" ] && continue
  while IFS= read -r hit; do
    hit_line="${hit%%:*}"
    hit_text="${hit#*:}"
    trimmed=$(printf '%s' "$hit_text" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    if [[ "$trimmed" != "$SANCTIONED_WAYFARE_ROOT_LINE" ]]; then
      WAYFARE_ROOT_ERRORS=1
      error "CLAUDE_PLUGIN_ROOT or a hardcoded plugin path outside the one sanctioned WAYFARE_ROOT line" \
        "${f#"$PLUGIN_ROOT/"}" \
        "$hit_line" \
        "Resolve the plugin root with exactly: $SANCTIONED_WAYFARE_ROOT_LINE"
    fi
  done <<< "$hits"
done < <(find "$SKILLS_DIR" "$PLUGIN_ROOT/references" -type f -name '*.md' 2>/dev/null)
if [[ $WAYFARE_ROOT_FILES_SCANNED -eq 0 ]]; then
  error "the WAYFARE_ROOT scan of skills/ and references/ found zero files" \
    "" "" "Something broke the find above (paths moved?) — fix it before trusting this guard's PASS"
elif [[ $WAYFARE_ROOT_ERRORS -eq 0 ]]; then
  pass "every CLAUDE_PLUGIN_ROOT site in skills/ and references/ uses the sanctioned WAYFARE_ROOT line"
fi

# ── '../../' escapes only reach references/ or docs/ ───────────────────────
# The spec's model is a self-contained skill; references/ and docs/ are the
# one sanctioned exception, shared roots every manifest installs alongside
# skills/. A '../../' escape anywhere else reaches
# outside the skill into a path with no install-layout guarantee.
DOTDOT_ERRORS=0
DOTDOT_FILES_SCANNED=0
while IFS= read -r f; do
  DOTDOT_FILES_SCANNED=$((DOTDOT_FILES_SCANNED + 1))
  hits=$(grep -noE '\.\./\.\./[A-Za-z0-9._/-]*' "$f" 2>/dev/null || true)
  [ -z "$hits" ] && continue
  while IFS= read -r hit; do
    hit_line="${hit%%:*}"
    hit_path="${hit#*:}"
    case "$hit_path" in
      ../../references/*|../../docs/*)
        # A prefix match is not enough: a further '..' segment after it
        # (../../references/../scripts/x) walks right back out of the
        # sanctioned exception, so it gets the same rejection as never
        # having the prefix at all.
        rest="${hit_path#../../}"
        rest="${rest#*/}"
        case "$rest" in
          ../*|*/../*|..) ;;
          *) continue ;;
        esac
        ;;
    esac
    DOTDOT_ERRORS=1
    error "'../../' escape does not point cleanly into references/ or docs/" \
      "${f#"$PLUGIN_ROOT/"}" \
      "$hit_line" \
      "Point it at ../../references/NAME or ../../docs/NAME with no further '..' segment, or bring the content inside the skill"
  done <<< "$hits"
done < <(find "$SKILLS_DIR" -type f -name '*.md' 2>/dev/null)
if [[ $DOTDOT_FILES_SCANNED -eq 0 ]]; then
  error "the '../../' scan of skills/ found zero files" \
    "" "" "Something broke the find above (paths moved?) — fix it before trusting this guard's PASS"
elif [[ $DOTDOT_ERRORS -eq 0 ]]; then
  pass "every '../../' escape in skills/ points into references/ or docs/"
fi

# ── chained-skill invocability guard ───────────────────────────────
# wayfare-build-task (skills/wayfare-build-task/SKILL.md) delegates its steps to child skills via
# the Skill tool, and a wayfare goal turn chains into wayfare-grill-idea and
# wayfare-build-task the same way. A chained skill carrying
# `disable-model-invocation: true` cannot be invoked by the model, so the
# calling pipeline breaks at that step (there is no per-caller allowlist).
# Keep this list in sync with wayfare-build-task's step→skill mapping AND
# a goal turn's tiers. `wayfare-build-task` is here because re-adding its flag
# would silently break every goal turn. `architecture` is chained three
# ways: wayfare-sync-plan runs its review/sync in both modes, and
# wayfare-grill-idea's `arch` dispatch
# delegates to it. `wayfare-write-handoff` is deliberately NOT here: wayfare's
# design-feedback delivery deposits a message directly into the sibling's
# `.plans/inbox/` rather than routing through handoff, because handoff
# distills the *current conversation* and would carry this session's state
# into the sibling's inbox.
# `wayfare-audit-security` is here because re-adding `disable-model-invocation: true` would
# break every sync at its harden stage.
# `wayfare-one-shot` is here because build-task's Step 1d chains it, and
# new-skill.sh scaffolds `disable-model-invocation: true` by default.
# `wayfare-check-preflight` is intentionally absent, wayfare-build-task runs
# it via scripts/preflight.sh, not the Skill tool, so it may stay user-only.
CHAINED_SKILLS="wayfare-grill-idea wayfare-push-pr wayfare-review-pr wayfare-respond-pr wayfare-ship-pr wayfare-build-task wayfare-review-architecture wayfare-sync-architecture wayfare-audit-security wayfare-one-shot"
for chained in $CHAINED_SKILLS; do
  chained_file="$SKILLS_DIR/$chained/SKILL.md"
  # A missing chained skill silently breaks the calling pipeline at that step, so error
  # rather than skip, the list above must always resolve to real skills.
  if [[ ! -f "$chained_file" ]]; then
    error "the pipelines chain '$chained' but skills/$chained/SKILL.md is missing" \
      "skills/$chained/SKILL.md" \
      "" \
      "Restore the skill, or update the calling skill's step→skill mapping and this guard's CHAINED_SKILLS list to match"
    continue
  fi
  # Scope the check to the YAML frontmatter (first --- ... --- block) so a
  # `disable-model-invocation: true` line inside a body code block (e.g. a
  # scaffolding example) can't produce a false positive. Allow leading
  # whitespace on the key.
  CHAINED_FM=$(awk '/^---$/{n++; next} n==1{print} n>=2{exit}' "$chained_file")
  # Here-string, not `printf | grep -q`. Under `set -o pipefail`, grep -q exits
  # the moment it matches, which SIGPIPEs the still-writing printf; the pipeline
  # then reports 141 and the `if` takes the FAILURE branch even though the match
  # succeeded. The bigger the input, the likelier it fires, so the guard would
  # start lying precisely as a skill grew.
  if grep -qE '^[[:space:]]*disable-model-invocation:[[:space:]]*true' <<< "$CHAINED_FM"; then
    DMI_LINE=$(grep -nE '^[[:space:]]*disable-model-invocation:[[:space:]]*true' "$chained_file" | head -1 | cut -d: -f1)
    error "'$chained' is chained by a hero pipeline but is user-only (disable-model-invocation: true)" \
      "skills/$chained/SKILL.md" \
      "$DMI_LINE" \
      "Remove the 'disable-model-invocation: true' line — a hero pipeline invokes this skill via the Skill tool and cannot call a user-only skill"
  else
    pass "$chained: model-invocable (chainable by the hero pipelines)"
  fi
done

echo ""
echo "────────────────────────────"

# ── absorbed-skill dangling-reference guard ────────────────────────
# scan-vulns, test-changes, and document-arch were deleted and folded into
# harden, push-pr, and wayfare-grill-idea respectively. A live reference to one
# of these names is fine ONLY as a lineage note ("absorbed the former X",
# "absorbed from X"), anything else is a leftover pointer to a skill that no
# longer exists. Scoped to tracked, non-historical docs; a plans/ retrospective
# describing what the repo looked like at the time it was written is exempt.
ABSORBED_SKILLS="scan-vulns test-changes document-arch"
for absorbed in $ABSORBED_SKILLS; do
  if [[ -d "$SKILLS_DIR/$absorbed" ]]; then
    error "'$absorbed' was supposed to be absorbed elsewhere but skills/$absorbed/ still exists" \
      "skills/$absorbed/SKILL.md" \
      "" \
      "Either this skill was reinstated (update ABSORBED_SKILLS in scripts/validate.sh to drop it) or the merge is incomplete"
    continue
  fi
  # The lineage word may sit on the line before the name: the formatter
  # wraps paragraphs, and "absorbed the former" often ends the previous line.
  HITS=$(grep -rn "$absorbed" --include='*.md' --include='*.sh' \
    "$SKILLS_DIR" "$PLUGIN_ROOT/README.md" "$PLUGIN_ROOT/docs/PIPELINES.md" "$PLUGIN_ROOT/scripts" 2>/dev/null \
    | grep -v "$(basename "$0")" \
    | while IFS= read -r hit; do
        f="${hit%%:*}"; rest="${hit#*:}"; n="${rest%%:*}"
        sed -n "$(( n > 1 ? n - 1 : 1 )),${n}p" "$f" | grep -qiE 'absorb' || printf '%s\n' "$hit"
      done || true)
  if [[ -n "$HITS" ]]; then
    while IFS= read -r hit; do
      hit_file="${hit%%:*}"
      error "reference to deleted skill '$absorbed' without lineage context (expected 'absorbed...')" \
        "${hit_file#"$PLUGIN_ROOT"/}" \
        "" \
        "Either add lineage framing ('absorbed the former $absorbed...') or this is a stale pointer to a skill that no longer exists"
    done <<< "$HITS"
  else
    pass "no dangling references to deleted skill '$absorbed'"
  fi
done

echo ""
echo "────────────────────────────"

# ── skill-reference resolution guard ───────────────────────────────
# `wayfare:NAME` references fan out across skills, README, and
# PIPELINES.md; a renamed or deleted skill rots every one of them silently.
# ABSORBED_SKILLS above is the hand-curated tail of that class. This is the
# generic half: every referenced name must resolve to skills/NAME/SKILL.md.
# Lineage notes ("absorbed the former X") are exempt, same rule
# as the absorbed guard.
# docs/ is globbed, not enumerated: enumerating leaves each new doc's
# references unguarded.
# The prefix is the plugin's own name, read rather than spelled: hardcoding
# it means the next rename leaves REF_NAMES empty, the loop below never runs,
# and the guard prints success over a repo full of dangling references.
# That is not hypothetical — this very rename changed the prefix, and during
# it the guard could not see a surviving reference to the old one.
PLUGIN_NS=$(jq -r '.name // empty' "$MANIFEST" 2>/dev/null)
# assets/ is in the set because it is vendored INTO ~25 consumer repos
# (AGENTS.md, *Layout*), so a name that rots here rots in every one of them,
# where nothing runs this check. assets/compliance/ is the register the
# engine reads in place, not a skill reference, so it stays out.
REF_NAMES=$(grep -rhoE "$PLUGIN_NS:[a-z][a-z0-9-]*" --include='*.md' \
  "$SKILLS_DIR" "$PLUGIN_ROOT/README.md" "$PLUGIN_ROOT/AGENTS.md" \
  "$PLUGIN_ROOT"/docs/*.md "$PLUGIN_ROOT"/references/*.md \
  "$PLUGIN_ROOT"/assets/auto-approve "$PLUGIN_ROOT"/assets/design-system \
  "$PLUGIN_ROOT"/assets/fleet 2>/dev/null \
  | sort -u | cut -d: -f2)
if [[ -z "$PLUGIN_NS" ]]; then
  error "cannot read the plugin name, so the skill-reference guard cannot run" \
    "$MANIFEST_REL" "" "Restore the \"name\" field; without it this guard silently checks nothing"
elif [[ -z "$REF_NAMES" ]]; then
  error "no '$PLUGIN_NS:NAME' reference found anywhere" \
    "$MANIFEST_REL" "" "Either the prefix is wrong or every reference rotted; the guard cannot pass vacuously"
fi
DANGLING_REFS=0
for ref in $REF_NAMES; do
  [[ -f "$SKILLS_DIR/$ref/SKILL.md" ]] && continue
  # Trailing-boundary match so `wayfare-build-task` never swallows a hit on `one-shots`.
  # The SAME file set the names were extracted from. Narrowing it here (this
  # line read docs/PIPELINES.md alone) makes the guard silently pass: a ref
  # that lives only in another docs file is extracted, fails to resolve, then
  # is searched somewhere it cannot appear, so HITS comes back empty and the
  # `continue` below files it as a harmless lineage note.
  HITS=$(grep -rnE "$PLUGIN_NS:$ref([^a-z0-9-]|\$)" --include='*.md' \
    "$SKILLS_DIR" "$PLUGIN_ROOT/README.md" "$PLUGIN_ROOT/AGENTS.md" \
    "$PLUGIN_ROOT"/docs/*.md "$PLUGIN_ROOT"/references/*.md \
    "$PLUGIN_ROOT"/assets/auto-approve "$PLUGIN_ROOT"/assets/design-system \
    "$PLUGIN_ROOT"/assets/fleet 2>/dev/null \
    | grep -viE 'absorb' || true)
  [[ -z "$HITS" ]] && continue # lineage-only references are fine
  DANGLING_REFS=1
  while IFS= read -r hit; do
    hit_file="${hit%%:*}"
    hit_line=$(printf '%s' "$hit" | cut -d: -f2)
    error "'$PLUGIN_NS:$ref' does not resolve to skills/$ref/SKILL.md" \
      "${hit_file#"$PLUGIN_ROOT"/}" \
      "$hit_line" \
      "Point the reference at the skill's current name, or add lineage framing ('absorbed the former $ref ...') if it is a history note"
  done <<< "$HITS"
done
if [[ "$DANGLING_REFS" = 0 ]]; then
  pass "all $PLUGIN_NS:NAME references resolve to existing skills"
fi

echo ""
echo "────────────────────────────"

# ── re-inlined shared helpers ──────────────────────────────────────
# HERO.md parsing, .git/info/exclude writes, and work-item status parsing live
# in scripts/hero-lib.sh. A file that re-implements one forks the behavior
# silently, and the fork only surfaces when two skills disagree at runtime.
#
# This checks SEMANTICS, not literal byte strings. An earlier version matched
# the exact awk one-liners that existed at the time; those strings stopped
# appearing the moment hero-lib.sh was rewritten, so the guard matched nothing
# anywhere in the repo, including the canonical implementation, and reported
# clean over every possible violation. Any reworded copy (awk -F":", sed -n,
# grep|cut) escaped it too.
#
# The inverted rule: if a file TOUCHES shared state, it must also reference the
# library. That has no phrasing to evade. You cannot parse default-branch
# without naming default-branch.
#
# Format: "marker-regex|hero-lib replacement|human description"
# Match the PARSING IDIOM, not the field name. Matching field names both
# over-fired (prose mentioning "default-branch", init GENERATING the
# HERO.md template, a test writing fixtures) and under-fired (it never named
# merge-method / platform / health-endpoint, so four hand-rolled parsers in
# ship-pr went unseen). Reading HERO.md through a text tool is the actual
# duplication; writing it is not.
# Match the PARSING IDIOM, not the field name. Field names both over-fired
# (prose, init GENERATING the HERO.md template, tests writing fixtures)
# and under-fired (never naming merge-method / platform, so four hand-rolled
# parsers in ship-pr went unseen). Reading HERO.md through a text tool is the
# duplication; writing it is not.
#
# Fields are :: separated because the patterns contain `|` alternations.
# `.*` not `[^\n]*`: grep -E reads the latter as "not backslash or n", which
# cannot span an ordinary word like `print`. grep is line-based regardless.
# \b word boundaries are required too: without them `sed` matches inside
# "pas_sed_" and "ba_sed_", flagging ordinary prose.
SHARED_STATE=(
  "\\b(awk|sed|cut)\\b.*HERO\\.md::hero_field::hand-rolled HERO.md parsing"
  "rev-parse.*info/exclude::hero_exclude_add::.git/info/exclude resolution"
)
ALLOW_MARKER="hero-lint: allow-inline"

while IFS= read -r f; do
  case "$f" in
    */hero-lib.sh|*/validate.sh) continue ;;
  esac
  for entry in "${SHARED_STATE[@]}"; do
    marker="${entry%%::*}"
    rest="${entry#*::}"
    replacement="${rest%%::*}"
    description="${rest##*::}"
    # Report only lines that BOTH match the idiom and lack the opt-out marker.
    # Checked per line, not per file: a file may legitimately use the library
    # in one place and document the anti-pattern in another.
    hits=$(grep -nE "$marker" "$f" 2>/dev/null | grep -vF "$ALLOW_MARKER" || true)
    [ -z "$hits" ] && continue
    error "$description — use $replacement" \
      "${f#"$PLUGIN_ROOT/"}" \
      "$(printf '%s' "$hits" | head -1 | cut -d: -f1)" \
      "Source scripts/hero-lib.sh and call $replacement, or append a '$ALLOW_MARKER' comment on that line if it is deliberate"
  done
done < <(find "$SKILLS_DIR" "$PLUGIN_ROOT/scripts" -type f 2>/dev/null)

if [[ $ERRORS -eq 0 ]]; then
  pass "no file touches shared state without hero-lib.sh"
fi

# ── fleet root: a skill that reads HERO.md must detect the fleet folder ──
# At a fleet root there is no HERO.md, so a repo skill would treat the folder
# as a project. AGENTS.md promises every repo skill tests for it; this holds
# that for any skill that reads HERO.md by any spelling. The check must be
# the executable test, not the word FLEET_ROOT in prose.
# audit-plugin reads HERO.md to audit this plugin's own field coverage, not
# as a project's config, and never runs in another repo. A `user-invocable:
# false` skill is reached only by a Skill-tool chain from a skill that already
# ran the fleet test (wayfare Step 0, wayfare-grill-idea Step 0), a second test
# there would be dead code that reads as a promise, and dropping the exemption
# would re-add fleet handling to skills that have no user path to a fleet
# folder. A hand-typed run at a fleet root is unguarded and fails loudly on
# NO_HERO_CONFIG instead; that is accepted.
FLEET_GATE_ERRORS=0
for f in "$SKILLS_DIR"/*/SKILL.md; do
  case "$f" in */wayfare-audit-plugin/SKILL.md) continue ;; esac
  FLEET_FM=$(awk '/^---[[:space:]]*$/{n++; next} n==1{print} n>=2{exit}' "$f")
  grep -qE '^[[:space:]]*user-invocable:[[:space:]]*false' <<< "$FLEET_FM" && continue
  SKILL_DIR=$(dirname "$f")
  SKILL_CONTENT=$(find "$SKILL_DIR" -maxdepth 1 -type f \( -name 'SKILL.md' -o -name 'WORKFLOW.md' \) -exec cat {} +)
  grep -qE 'HERO\.md|hero_field|hero_md_field' <<< "$SKILL_CONTENT" || continue
  grep -qE 'hero_at_fleet_root|hero_fleet_root|-f "\$(PWD|ROOT)/FLEET\.md" \]' <<< "$SKILL_CONTENT" && continue
  FLEET_GATE_ERRORS=$((FLEET_GATE_ERRORS + 1))
  error "reads HERO.md but never tests for the fleet root" \
    "${f#"$PLUGIN_ROOT/"}" "" \
    "Add the FLEET_ROOT line from scripts/new-skill.sh's Step 0 and the pointer to docs/FLEET-MD.md"
done
[[ $FLEET_GATE_ERRORS -eq 0 ]] && pass "every skill that reads HERO.md tests for the fleet root"

# ── work-item store: producers must have a consumer ────────────────
# wayfare-grill-idea, handoff, and harden all WRITE work-items into .plans/
# (and read the plate back to build on it). wayfare-build-task is the only skill that
# CONSUMES an item, resolving it to execute and marking it done. (It also
# authors Step 2a carve-outs, but it never plans one from scratch.) If that delegation
# is ever edited away, the store silently becomes write-only: items pile up,
# nothing marks them done, and wayfare-build-task goes back to planning from scratch
# while ignoring the plate. Nothing else in this repo would catch that.
ONE_SHOT="$SKILLS_DIR/wayfare-build-task/WORKFLOW.md"
if [[ ! -f "$ONE_SHOT" ]]; then
  error "skills/wayfare-build-task/WORKFLOW.md is missing" "skills/wayfare-build-task/WORKFLOW.md" "" \
    "wayfare-build-task owns Pipeline 2; restore its executable specification or update this guard"
else
  # Strip HTML comments and fenced blocks before matching, and require the
  # reference in an ACTIVE position (an Invoke instruction or a table row).
  # A bare substring check was satisfied by leaving the name in a comment,
  # "this pipeline used to call wayfare:wayfare-grill-idea" passed while
  # every real delegation had been deleted, which is exactly the drift this
  # guard exists to catch.
  ONE_SHOT_ACTIVE=$(strip_fences_and_comments "$ONE_SHOT")
  # Here-string rather than `printf | grep -q`, see the pipefail/SIGPIPE note
  # on the chained-skill guard above. This site is the one that actually bit:
  # the match sits near the top of wayfare-build-task's Step->skill table, so grep -q
  # exited early and killed printf mid-write, and the guard reported drift that
  # had not happened.
  if grep -qE '(Invoke|Skill tool|^\|).*wayfare:wayfare-grill-idea' <<< "$ONE_SHOT_ACTIVE"; then
    pass "wayfare-build-task's plan step delegates to wayfare-grill-idea"
  else
    error "wayfare-build-task no longer references wayfare-grill-idea — the plan step has drifted back to planning from scratch" \
      "skills/wayfare-build-task/WORKFLOW.md" \
      "" \
      "wayfare-grill-idea is the planning skill; wayfare-build-task's Step 1 must resolve against .plans/ and delegate to it. See PIPELINES.md Pipeline 2"
  fi
  # Require several real references, not one incidental mention. "plans" is
  # a word that appears in ordinary prose, so match the literal `.plans` token.
  STORE_HITS=$(printf '%s\n' "$ONE_SHOT_ACTIVE" | grep -cF '.plans' || true)
  if [[ "${STORE_HITS:-0}" -ge 3 ]]; then
    pass "wayfare-build-task reads the .plans/ store ($STORE_HITS references)"
  else
    error "wayfare-build-task does not read .plans/ — the work-item store has no consumer" \
      "skills/wayfare-build-task/WORKFLOW.md" \
      "" \
      "wayfare-grill-idea, handoff, and harden all emit into .plans/; wayfare-build-task Step 1 must resolve against it and Step 9 must mark the merged item done"
  fi
fi

# ── goal turn: the per-task build launch never carries the grant ──
# references/goals.md step 4 hands each task's build a `commit only: goal G
# branch GOAL_BRANCH` line and nothing else; commit-only mode never reaches
# a gate, so a stray `gates pre-authorized in-session` line on that same
# launch would sit unused today but re-arm the moment build-task's Step 0.5
# routing changes. A plain whole-file substring check can't tell that launch
# paragraph apart from the prose elsewhere in this file that legitimately
# names both literals (the permissions-travel rules a few sections up), so
# this narrows to the paragraph(s) that contain the commit-only literal.
#
# Deliberately NOT run through strip_fences_and_comments: the real step-4
# invocation is itself inside an indented ``` fence (it's the literal prompt
# text a build agent copies), so stripping fences here would strip away the
# one paragraph this guard exists to check. A fenced counter-example placed
# elsewhere in the file would still be read as live and could raise a false
# error — safe, since it fails loud and points at the file, unlike a stripped
# real paragraph, which would fail silently.
GOALS_MD="$PLUGIN_ROOT/references/goals.md"
if [[ ! -f "$GOALS_MD" ]]; then
  error "references/goals.md is missing" "references/goals.md" "" \
    "goals.md documents a goal turn's build-launch invocation; restore it or update this guard"
else
  # Paragraph mode: a record is one blank-line-delimited block, which is
  # exactly the "same paragraph" the DoD asks about. Count every matching
  # paragraph rather than taking the first (`exit`): a clean paragraph
  # mentioning the commit-only literal earlier in the file — a glossary
  # entry, a cross-reference — would otherwise satisfy the check and leave a
  # real regression in a later paragraph unread.
  LAUNCH_COUNT=$(awk -v RS='' '/commit only: goal G branch GOAL_BRANCH/ { c++ } END { print c+0 }' "$GOALS_MD")
  BAD_COUNT=$(awk -v RS='' '/commit only: goal G branch GOAL_BRANCH/ && /gates pre-authorized in-session/ { c++ } END { print c+0 }' "$GOALS_MD")
  if [[ "$LAUNCH_COUNT" -eq 0 ]]; then
    error "references/goals.md no longer carries the commit-only build-launch literal — this guard has nothing to check" \
      "references/goals.md" "" \
      "Keep the exact line \`commit only: goal G branch GOAL_BRANCH\` in step 4's per-task build invocation, or update this guard alongside its removal"
  elif [[ "$BAD_COUNT" -gt 0 ]]; then
    error "references/goals.md's per-task build-launch paragraph carries both the commit-only line and the permissions grant ($BAD_COUNT of $LAUNCH_COUNT matching paragraph(s))" \
      "references/goals.md" "" \
      "Commit-only mode never reaches a gate; keep \`gates pre-authorized in-session\` out of step 4's per-task build invocation — it belongs only at step 7's hand-off"
  else
    pass "references/goals.md's commit-only build-launch paragraph carries no permissions grant ($LAUNCH_COUNT matching paragraph(s) checked)"
  fi
fi

echo ""
echo "────────────────────────────"

if [[ $ERRORS -gt 0 ]]; then
  echo ""
  red "FAILED: $ERRORS error(s), $WARNINGS warning(s)"
  echo ""
  dim "Fix the errors above and re-run: ./scripts/validate.sh"
  dim "Use --verbose to also see passing checks."
  exit 1
elif [[ $WARNINGS -gt 0 ]]; then
  echo ""
  yellow "PASSED with $WARNINGS warning(s)"
  dim "Warnings won't block commits but should be addressed."
  exit 0
else
  echo ""
  green "ALL CHECKS PASSED"
  exit 0
fi
