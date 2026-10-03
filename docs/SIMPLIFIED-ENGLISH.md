# Simplified English for skill instructions

Use STE-inspired English for agent procedures in `skills/`, `WORKFLOW.md`, and
`references/`. Use it when creating or revising instructions. This guide adapts
[danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) to
Wayfare. It does not certify compliance with the ASD-STE100 dictionary.

## Write the instruction

- Name the actor. Use an imperative for an action the executing agent must take.
  Name the script, user, or calling skill when that actor differs.
- Put the condition before the action. Keep the condition and its action
  together when splitting a sentence.
- Give one instruction per sentence. Use a numbered list for an ordered sequence
  of three or more actions.
- Aim for at most 20 words in an instruction and 25 words in an explanation.
  Preserve a longer sentence if splitting it would change scope or lose
  precision.
- Use active voice and simple verb forms when they preserve meaning. Keep a
  compound tense when it carries necessary timing or uncertainty.
- Use one topic per paragraph. Aim for at most six sentences per paragraph.
- Replace idioms and metaphors with the action or state they describe. Split
  independent clauses instead of joining them with a semicolon.
- Use stable names for domain concepts. Avoid dense noun groups. Define a
  necessary term before using it without explanation.

## Preserve the contract

A clearer sentence must preserve the original behavior. Check the original and
rewrite for the same actor, action, object, condition, exception, order, and
outcome.

Keep these elements unchanged unless the task explicitly changes behavior:

- Requirement strength: `must`, `may`, `only`, `never`, and `should` have
  different meanings.
- Failure states, sentinel values, readiness rules, authorization gates, and
  distinctions between an absent resource and an unavailable resource.
- Commands, code, paths, identifiers, schemas, templates, and machine-readable
  output strings.
- Counts, limits, timeouts, and the evidence required for a verdict.

Use distinct words for distinct operations. In Wayfare, a script can **check**
state, a person can **confirm** a proposal, and a test can **verify** a required
outcome. Do not replace these terms merely because a linter groups them as
synonyms. `hero`, `fleet`, and `wayfare` retain the meanings in AGENTS.md.

For example:

> If the command prints `FLEET_ROOT`, stop this repo procedure. Follow **At the
> fleet root** for the repos the user selects.

The stop condition remains attached to the command result. The instruction does
not authorize a run against every sibling repo.

## Review the rewrite

Read the original before editing. Compare each changed instruction with the
original after editing. Check code blocks and machine-readable literals
separately. Run the repository's documentation and plugin checks.

The upstream `scripts/ste-lint.py` can identify possible style problems. Its
sentence check works per physical line. Join wrapped prose before measuring
sentence length. Exclude frontmatter and code from prose measurements. Its
synonym and passive-voice findings require judgment. Passing that linter does
not prove equivalent behavior or dictionary compliance.

Use this guide for executable instructions. Continue to use `docs/HUMANIZING.md`
for prose intended for people. Do not force a person's quoted text or a fixed
output template into this style.

## Evidence and limits

The strongest direct evidence concerns human readers. Chervak, Drury, and
Ouellette tested 16 versions of four aircraft workcards with 175 maintenance
technicians. Simplified English improved comprehension, especially for difficult
workcards and non-native readers. The authors'
[aviation-maintenance proceedings report](https://libraryonline.erau.edu/online-full-text/human-factors-in-aviation-maintenance/proceedings/Meeting10.pdf)
reports comprehension error rates of 18% without SE and 14% with SE. That is a 4
percentage point reduction, or about 22% relative. These are comprehension-test
errors, not measured aircraft-maintenance accidents or agent failures. The
subgroup contained only 18 non-native speakers. Easy workcards had 17% errors
without SE and 19% with SE, so the aggregate benefit was not uniform.

LLM studies establish that wording can affect results, but do not establish that
ASD STE improves coding-agent execution.
[Zhan et al., EMNLP 2024](https://aclanthology.org/2024.emnlp-main.295/) found
sensitivity to small lexical changes.
[Hua et al., EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1006/)
evaluated seven models, six benchmarks, and twelve templates. They found that
evaluation methods account for much of the apparent prompt sensitivity. Neither
study tests this Wayfare rewrite.

Our reason to use this style is easier inspection of actors, conditions, and
stop rules. Better agent success remains a hypothesis. Shorter sentences alone
do not establish fewer tokens, faster execution, or fewer failures.

## Measure agent behavior

Before claiming an execution benefit, compare original and revised instructions
on the same fixed repo fixtures. Use the same model, tools, settings, and
starting state. Repeat both versions and alternate their order. Keep approval
and publication operations mocked.

Include a normal task and failure cases: `FLEET_ROOT`, an unavailable
dependency, an anti-feature, a declined readiness gate, a stale PR head, and a
zero-job approval run. Score observable actions and final state against an
independent expected result. Do not score wording similarity or linter findings
as task success.

Report task success, incorrect mutations, missed gates, tool calls, tokens, and
elapsed time. Include trial counts and uncertainty. This rewrite has no agent
A/B result yet.
