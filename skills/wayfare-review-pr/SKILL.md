---
name: wayfare-review-pr
# prettier-ignore
description: Review a PR with the pr-review-toolkit agents plus a security pass. No argument reviews your own draft PR and applies fixes. A PR number reviews the author's code via inline comments, no edits. Use before marking your PR ready, or to review someone else's.
argument-hint: "[#PR] [--no-mark-ready] | recalibrate"
---

# Review: review a pull request

Context-aware PR review. Auto-detects whether you're reviewing your own draft or
someone else's PR and runs the right mode. Every review includes a
security-focused pass (a checklist similar to `/security-review`, run as an
in-process agent rather than invoking that skill) alongside the
pr-review-toolkit agents.

## Arguments

- `$ARGUMENTS` - Optional PR number or URL, plus optional flags
  - `recalibrate` - Tune the `HERO.md` fields this skill reads, then stop (see
    below). Matched before every other form.
  - (none) - Auto-detect from the current branch, to your draft PR, to
    self-review mode
  - `#123` or URL - Your PR: self-review mode. Someone else's PR: review mode
    (no edits).
  - `--no-mark-ready` - Self-review mode only: run Steps 1 to 8 (post review,
    apply fixes, push, post improvements summary, update PR description) but
    skip Step 9 (the mark-ready prompt and `gh pr ready`). Used by
    `wayfare:wayfare-build-task` so its DAG can render `self-review` (Step 5)
    and `mark-ready` (Step 6) as distinct nodes without double-prompting.
    Combine with a PR number/URL as needed (`#42 --no-mark-ready`).

Parse `$ARGUMENTS` for the flag once at the top of Step 0:

```bash
NO_MARK_READY=false
ARGS_FILTERED=""
for tok in $ARGUMENTS; do
  case "$tok" in
    --no-mark-ready) NO_MARK_READY=true ;;
    *) ARGS_FILTERED="$ARGS_FILTERED $tok" ;;
  esac
done
ARGS_FILTERED=$(printf '%s' "$ARGS_FILTERED" | sed 's/^ //')
# Use $ARGS_FILTERED wherever the existing skill body references $ARGUMENTS
# for the PR identifier (Step 0's `PR_ARG=...awk '{print $1}'` lookup, etc.).
```

## Prerequisites

- `gh` CLI installed and authenticated
- The `pr-review-toolkit` plugin available

## `recalibrate`

`wayfare:wayfare-review-pr recalibrate` tunes the config that drives this skill,
and stops. It does not go on to run the skill. You want to see which field was
wrong, not spend a whole run finding out.

Dispatch on it before parsing any other argument, in whichever step does that
parsing. When the first token of `$ARGUMENTS` is exactly `recalibrate`, print
`wayfare-review-pr: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md) (report, ask, write, commit)
using the table below as the report, and stop.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-review-pr
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

## Instructions

### Step 0: Load Configuration and Detect Mode

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

Read `HERO.md` for:

- **Code Quality** → pre-commit (re-run after fixes in self-review mode)
- **Code Review Agent** → bot username (to avoid duplicating its comments)

If `HERO.md` is missing, suggest `wayfare:wayfare-init-repo` but proceed with
defaults.

Detect the PR and mode:

```bash
BRANCH=$(git branch --show-current)
ME=$(gh api user --jq '.login' 2>/dev/null)

if [ -n "$ARGUMENTS" ]; then
  PR_ARG=$(printf '%s' "$ARGUMENTS" | awk '{print $1}')
  PR_JSON=$(gh pr view "$PR_ARG" --json number,url,headRefName,baseRefName,state,isDraft,author)
else
  PR_JSON=$(gh pr list --head "$BRANCH" --json number,url,headRefName,baseRefName,state,isDraft,author --jq '.[0]')
fi

# When no PR is found, gh pr list --jq '.[0]' returns the literal string "null".
# A subsequent `jq -r '.number'` on that yields "null" too, which would slip past
# the "No PR found" mode-selection check below. Stop explicitly here instead.
if [ -z "$PR_JSON" ] || [ "$PR_JSON" = "null" ]; then
  echo "No PR found for branch '$BRANCH'. Run wayfare:wayfare-push-pr first."
  exit 1
fi

PR_NUMBER=$(echo "$PR_JSON" | jq -r '.number')
PR_AUTHOR=$(echo "$PR_JSON" | jq -r '.author.login')
IS_DRAFT=$(echo "$PR_JSON" | jq -r '.isDraft')
PR_BRANCH=$(echo "$PR_JSON" | jq -r '.headRefName')
PR_URL=$(echo "$PR_JSON" | jq -r '.url')
PR_STATE=$(echo "$PR_JSON" | jq -r '.state')
BASE_BRANCH=$(echo "$PR_JSON" | jq -r '.baseRefName')
```

**Mode selection:**

| Condition | Mode |
| -- | -- |
| No PR found | STOP: "No PR for '$BRANCH'. Run `wayfare:wayfare-push-pr` first." |
| Closed or merged | STOP and report status. |
| PR author is you AND draft | Self-review mode |
| PR author is you AND not draft | Warn "PR is already ready-for-review. Continue self-review? [y/N]" |
| PR author is someone else | Review mode (no edits) |

______________________________________________________________________

## Self-Review Mode

### Step 1: Ensure on Correct Branch

```bash
CURRENT=$(git branch --show-current)
```

If `CURRENT != PR_BRANCH`, check for uncommitted changes:

```bash
git status --porcelain
```

If uncommitted changes exist, STOP. Show what is uncommitted and tell the user
to commit or cancel. Never silently stash.

When working tree is clean, switch:

```bash
git fetch origin "$PR_BRANCH"
git checkout "$PR_BRANCH"
git pull origin "$PR_BRANCH"
```

**Rebase onto the base before judging anything.** Work is concurrent: other
branches merge while this PR waits, so the head on the branch is routinely
behind the base, and a review of a stale head reviews code that is not what will
merge.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
HERO_LIB="$WAYFARE_ROOT/scripts/hero-lib.sh"
# shellcheck source=/dev/null
. "$HERO_LIB" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT — export WAYFARE_ROOT as the plugin root"; exit 1; }
BASE_BRANCH=${BASE_BRANCH:-$(hero_default_branch)}
hero_rebase_on_base "$BASE_BRANCH"; echo "REBASE_RC=$?"
```

`REBASE_RC=0` continues (up to date, or rebased and pushed; say which). `1` is a
conflict: the rebase was aborted and the branch is unchanged; STOP, list the
conflicting files it printed, and hand back to the user. Never resolve a
conflict on someone's behalf. `2` cannot proceed (dirty tree, detached HEAD,
fetch or lease failure): STOP with its message.

### Step 2: Scale the Review to the Diff, Then Run Agents in Parallel

**Measure the diff first, and pick a tier.** The full fan-out is six agents; a
16-line config change does not need six agents, and spending them there is how a
review that should take a minute takes ten and buries one real finding in five
"no findings" reports.

```bash
CHANGED_FILES=$(git diff --name-only "origin/$BASE_BRANCH...HEAD" | wc -l | tr -d ' ')
# insertions + deletions; `|| echo 0` so an empty diff yields 0, not an empty
# string that every numeric compare below would choke on.
CHANGED_LINES=$(git diff --numstat "origin/$BASE_BRANCH...HEAD" \
  | awk '{ n += $1 + $2 } END { print n + 0 }' || echo 0)
echo "wayfare-review-pr: $CHANGED_FILES files, $CHANGED_LINES lines changed"
```

Pick the tier from `CHANGED_LINES` and `CHANGED_FILES`. They are the input, not
a printout to read by eye:

| Diff | Agents | Which |
| -- | -- | -- |
| **under ~50 lines** | review inline, **no agents** | Read it yourself. Say you did, and why the fan-out was skipped. |
| **~50 to 300 lines** | 2 | `code-reviewer` + security |
| **~300 to 1500 lines** | all 6 | the five pr-review-toolkit agents plus security |
| **over ~1500 lines or 50 files** | all 6 | the same six. Review the whole diff; do not ask the author to shrink it |

**The tiers size the review effort, never the PR.** A PR is as big as the work
it does. A goal that genuinely takes 2000 lines gets a 2000-line review, not a
request to carve it into pieces that each review cleanly and none of which is
the change. What matters is that the commits are logical changesets a reviewer
can walk one at a time; line count is a hint about effort, not a limit anyone
has to stay under.

Two rules keep the tiers honest:

- **Security is never dropped.** It is in every tier that runs an agent at all,
  and in the inline tier it is a pass you run yourself. A small diff is exactly
  where a credential or an injection sneaks in unescorted.
- **Content overrides size.** Anything touching auth, crypto, permissions, a
  shared workflow, a migration, or a payment path takes the **full six**
  regardless of line count. A 12-line change to `.github/workflows/` in this
  repo reaches ~25 consumer repos on merge; a 12-line change to a README does
  not. Judge by blast radius, not by `wc -l`.

Say which tier you picked and why, in one line, before launching. A review that
silently ran two agents reads identically to one that ran six and found nothing.

Then launch the tier's agents simultaneously in a single message, each with the
named type below and never `subagent_type: "fork"` (see *A fan-out subagent is
never a fork* in `docs/PIPELINES.md`). For the full six, the five
pr-review-toolkit agents plus the security agent:

```
Agent(subagent_type="pr-review-toolkit:code-reviewer", ...)
Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", ...)
Agent(subagent_type="pr-review-toolkit:pr-test-analyzer", ...)
Agent(subagent_type="pr-review-toolkit:comment-analyzer", ...)
Agent(subagent_type="pr-review-toolkit:type-design-analyzer", ...)
Agent(subagent_type="general-purpose", security review — prompt spec below)
```

**Security agent prompt spec.** Give the agent the PR diff scope (repo path,
branch/PR number) and this brief: review ONLY for security vulnerabilities that
are plausibly exploitable in the changed code: injection (SQL, command,
template), XSS, authentication/authorization flaws, secrets or credentials in
code or logs, SSRF, path traversal, unsafe deserialization/RCE, cryptographic
misuse, and sensitive-data exposure. High signal only: every finding needs a
concrete exploit scenario (who sends what, what happens). Explicitly EXCLUDE
noise categories: denial of service and rate limiting, memory safety in
memory-safe languages, theoretical issues with no plausible attack path, and
anything requiring an already-privileged attacker position. Return findings with
file:line, severity (Critical = exploitable, Important = realistic hardening
gap), and the exploit scenario; return "NO FINDINGS" when clean.

Wait for all agents to complete, then aggregate findings into: **Critical**
(bugs, security, data loss), **Important** (quality, correctness),
**Suggestions** (style, polish), **Strengths**. Security findings land in
Critical or Important per the spec above. Never bury an exploitable finding in
Suggestions.

### Step 3: Post Review Comment

Render the template with real findings, humanize it against
[docs/HUMANIZING.md](../../docs/HUMANIZING.md), keeping headings and counts,
then post:

```bash
BODY=$(cat <<'EOF'
## Self-Review
<!-- ai-hero:self-review -->

### Critical ({N})
- [agent] {file:line}: {finding}

### Important ({N})
- [agent] {file:line}: {finding}

### Suggestions ({N})
- [agent] {file:line}: {finding}

### Strengths
- {what's well-done}

---
_Generated using wayfare._
EOF
)
# The exact text that gets posted. A finding means fix the text and
# re-run, never post around it.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind comment --body-file - <<<"$BODY" || exit 1
gh pr comment $PR_NUMBER --body "$BODY"
```

Omit empty sections.

Two things about this comment matter, so do not "tidy" them:

- **The hidden `<!-- ai-hero:self-review -->` marker is what unblocks
  shipping.** The shared auto-approve workflow's prior-review gate accepts it as
  proof that auto-approve is not the only review on the PR. Drop the marker and
  `wayfare-ship-pr` gets REQUEST_CHANGES with no obvious cause.
- **The body must not START with `@auto-approve`.** That is the workflow's
  trigger, and this comment carries the very marker the prior-review gate
  accepts, so a comment that both fires the run and satisfies the gate would
  post a real APPROVE that nobody asked for. That happened once, before the
  trigger was anchored; the workflow now also ignores any comment carrying this
  marker, but keeping the heading first is the belt to that braces.

### Step 4: Ask Permission to Apply Fixes

Show the findings summary and ask:

```
Apply fixes? [Default: all]
1. All (critical + important + suggestions) ← default
2. Only critical + important
3. Only critical
4. Pick individually
5. Skip — leave the comment only
```

Wait for the user's choice. If "individually", walk through each finding yes/no.

### Step 5: Apply Fixes

For each accepted finding:

1. Read the file and surrounding context.
2. Apply the minimal fix. Do not refactor surrounding code.
3. Track changed files.
4. If a finding is ambiguous or conflicts with another, stop and ask.

After all fixes:

```bash
if command -v pre-commit > /dev/null 2>&1; then
  pre-commit run --files "${CHANGED_FILES[@]}"
else
  echo "NO_PRECOMMIT"
fi
```

Fix any pre-commit failures before continuing.

### Step 6: Commit and Push Fixes

End the message with the attribution trailer your harness specifies. If it
specifies none, end with `Co-Authored-By: Claude <noreply@anthropic.com>`, which
names no model and so cannot go stale.

```bash
git add "${CHANGED_FILES[@]}"
MSG=$(cat <<'EOF'
fix: address self-review findings

- {summary of fix 1}
- {summary of fix 2}
EOF
)
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind commit --body-file - <<<"$MSG" || exit 1
git commit -m "$MSG"
git push origin "$PR_BRANCH"
```

Commit logically distinct fixes separately if they touch unrelated areas.

### Step 7: Post Improvements Summary

**Always post this, even when no fixes were applied.** This is the durable
record that the review ran.

Render the template with real values. Never post literal placeholders. Omit
sections whose count is zero. Draft this and Step 8's description together,
humanize both in one `inline` call keeping the headings and the markers, then
post.

**Keep the `<!-- ai-hero:self-review-fixes -->` marker and the heading**, the
same way Step 3's comment keeps its own. The prior-review gate counts this
marker to tell this comment apart from the findings one; the heading it used to
be recognised by is rewritten by the humanizer (`docs/HUMANIZING.md` forbids em
dashes and rewrites heading case), so the marker is the only part of this
comment that survives the pass intact. Lose it and a finished review reads as
half-finished, fleet-wide.

```bash
BODY=$(cat <<'EOF'
## Self-Review: Improvements
<!-- ai-hero:self-review -->
<!-- ai-hero:self-review-fixes -->

**Critical (A / X fixed):**
- FILE:LINE: FINDING. Fixed: FIX_DESCRIPTION

**Important (B / Y fixed):**
- FILE:LINE: FINDING. Fixed: FIX_DESCRIPTION

**Suggestions (C / Z fixed):**
- FILE:LINE: FINDING. Fixed: FIX_DESCRIPTION

**Skipped:**
- FILE:LINE: FINDING. Skipped: REASON

Commits: SHA1, SHA2

---
_Generated using wayfare._
EOF
)
# The exact text that gets posted. A finding means fix the text and
# re-run, never post around it.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind comment --body-file - <<<"$BODY" || exit 1
gh pr comment $PR_NUMBER --body "$BODY"
```

If the post fails, surface the rendered body for manual paste. Do NOT swallow
the error.

### Step 8: Update PR Description if Scope Changed

Update when:

- New files added by fixes weren't in the original description
- Critical fixes changed observable behavior (security, data-loss, correctness)
- Features were removed or defaults changed

Leave unchanged for: style/typo/comment fixes only. Default to update when
uncertain.

```bash
gh pr view $PR_NUMBER --json title,body --jq '{title, body}'
```

Draft the full new body preserving structure (Summary, Changesets, Test Plan)
and ending with `_Generated using wayfare._` as the final line (humanized with
Step 7's summary), then apply:

```bash
BODY=$(cat <<'EOF'
DRAFTED_FULL_BODY_HERE
EOF
)
# The exact text that gets posted. A finding means fix the text and
# re-run, never post around it.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind pr-edit --title "NEW_TITLE_UNDER_70_CHARS" --body-file - <<<"$BODY" || exit 1
gh pr edit $PR_NUMBER --title "NEW_TITLE_UNDER_70_CHARS" --body "$BODY"
```

Substitute `DRAFTED_FULL_BODY_HERE` with actual Markdown before running. The
drafted body must end with `_Generated using wayfare._`. `--kind pr-edit` skips
the prose rules on the body, because the body it edits was often written by a
person or before those rules existed; the title, footer and placeholders are
still checked, and the lines you add still follow HUMANIZING.md.

### Step 9: Ask to Mark Ready

**Skip this step entirely when `$NO_MARK_READY` is `true`** (caller passed
`--no-mark-ready`, typically `wayfare:wayfare-build-task` whose own Step 6 owns
the mark-ready gate). In that case, jump straight to Step 10. The summary will
show `PR state: Draft (mark-ready deferred to caller)`.

Otherwise, ask the user:

```
Self-review complete.

Critical fixed: A/X | Important fixed: B/Y | Suggestions fixed: C/Z

Convert draft PR #{number} to ready-for-review? [y/N]
```

Wait for the user's confirmation. Never mark ready without it.

```bash
gh pr ready $PR_NUMBER
```

### Step 10: Summary

```
Self-Review Summary
===================
PR: #{number} - {title}
Branch: {branch}

Findings:
  Critical: X (Y fixed, Z skipped)
  Important: A (B fixed, C skipped)
  Suggestions: D (E fixed, F skipped)

Commits: N pushed
PR description: {updated | left as-is} ({reason})
PR state: {Draft / Ready for review}
URL: {pr-url}

Next step: (pick exactly one, based on what actually happened above)
```

- **`$NO_MARK_READY` is `true`** (deferred to caller, e.g.
  `wayfare-build-task`): no next-step line. The caller owns what happens next
  (wayfare-build-task's own Step 7 mark-ready gate).
- **Marked ready, agent configured**: print
  `Waiting on {agent}'s first review, then run wayfare:wayfare-respond-pr.` (no
  prompt, nothing to invoke yet).
- **Marked ready, `agent: none`**:
  `Next step: wayfare:wayfare-ship-pr, which posts @auto-approve, merges, and resets`
  (offer to auto-run: ask "Run it now? [y/N]", invoke via Skill tool on yes).
- **Declined mark-ready**:
  `Next step: address the findings above, then re-run wayfare:wayfare-review-pr.`
  (print only, because re-invoking the same skill right after it finishes is not
  auto-chained).

______________________________________________________________________

## Review Mode (Someone Else's PR)

### Step 1: Get PR Context

`OWNER`, `REPO`, `PR_NUMBER`, `HEAD_SHA` from Step 0 detection.

```bash
gh pr diff $PR_NUMBER
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" \
  --jq '.[] | {path: .path, line: .line, body: .body, user: .user.login}'
gh pr view $PR_NUMBER --json commits --jq '.commits[].messageHeadline'
```

Read the PR description carefully. It explains design decisions.

Apply the same tiering as self-review Step 2: measure the diff, pick the tier,
say which one and why. A large diff means more review effort, not a request for
the author to split it; walk the commits in order, since that is the structure
they carry.

### Step 2: Run All Review Agents in Parallel

Same as self-review Step 2: pick the tier from the diff size (with the
security-always and content-overrides-size rules), launch that tier's agents
simultaneously, and aggregate findings.

### Step 3: Post Inline Comments

Start each comment with its severity as a word, never an emoji
([docs/HUMANIZING.md](../../docs/HUMANIZING.md) bans them in posted text):

| Category | Prefix |
| -- | -- |
| Critical | `Critical:` |
| Important | `Important:` |
| Suggestion | `nit:` |
| Question | `Question:` |
| Strength | `Nice:` |

Comment guidelines: be specific, constructive, respectful. Skip findings already
raised by others. Skip nits the linter catches. An inline comment carries no
footer; the lint still checks it for placeholders and the prose rules.

```bash
OWNER=$(echo "$PR_URL" | awk -F/ '{print $4}')
REPO=$(echo "$PR_URL" | awk -F/ '{print $5}')
HEAD_SHA=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits[-1].oid')

COMMENT_BODY=$(cat <<'EOF'
Important: {finding}
EOF
)
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind inline --body-file - <<<"$COMMENT_BODY" || exit 1
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" \
  -f body="$COMMENT_BODY" \
  -f commit_id="$HEAD_SHA" \
  -f path="$FILE_PATH" \
  -F line=$LINE_NUMBER \
  -f side="RIGHT"
```

For multi-line: also pass `-F start_line=$START_LINE -f start_side="RIGHT"`.

### Step 4: Submit Overall Review

| Has criticals? | Has importants? | Decision |
| -- | -- | -- |
| Yes | any | `--request-changes` |
| No | Yes | `--comment` |
| No | No | `--approve` (unless questions remain) |

```bash
BODY=$(cat <<'EOF'
## Review Summary

**Findings:** {X} critical, {Y} important, {Z} suggestions

### Overall Assessment
{1-3 sentence summary}

### Key Findings
- {most important issue}
- {second most important}

### What's Good
- {positive observations}

---
_Generated using wayfare._
EOF
)
# The exact text that gets posted. A finding means fix the text and
# re-run, never post around it.
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
python3 "$WAYFARE_ROOT/scripts/pr_text_lint.py" --kind review --body-file - <<<"$BODY" || exit 1
gh pr review $PR_NUMBER {DECISION_FLAG} --body "$BODY"
```

### Step 5: Report

```
Review Summary
==============
PR: #{number} - {title}
Author: @{username}
Files: {N} changed (+A -D)

Findings:
  🔴 Critical: {X}
  🟡 Important: {Y}
  🔵 Suggestions: {Z}
  ❓ Questions: {W}

Inline comments posted: {N}
Decision: {Comment / Approve / Request Changes}
URL: {pr-url}
```

## Notes

- Never edit code in review mode. Only post comments.
- Never mark a PR ready without explicit user confirmation.
- Do not auto-resolve other reviewers' comments.
