# Proving a Definition of Done

How a task's `## Definition of Done` lines get proven. Read by
`wayfare-grill-idea` when it writes the DoD, and by `wayfare-build-task` Step 2
before it builds toward one.

**The plan says what must be true; the build decides how to prove it.** A plan
never lists test cases. Tests written at planning time are written before the
code exists, against names and seams that were guessed, so the build either
follows them against code that turned out different or quietly rewrites them.
The first outcome tests the list instead of the claim, and a build subagent on a
cheaper model will do exactly that. The second leaves a plan that says one thing
while the branch does another. What the plan carries instead is a claim that can
be tested, and the question below is asked twice: once to check the claim, and
once to prove it.

> **How would you test this?**

## At planning: the question checks the line

For every DoD line, `wayfare-grill-idea` asks how it would be tested. A good
answer names something you can observe: a command and what it outputs, a route
and what it renders, a measurement at a viewport. If the only answer is "look at
it and see if it seems right", the line is too vague. Rewrite it until it has a
real answer ("works well" becomes "the list renders 500 trips in under 200ms").

Write the line, not the answer. The answer is just evidence that the line can be
tested. If you write it into the plan, it becomes the test list this page exists
to keep out.

## At build: the question becomes the method

Before the subtask that should make a DoD line true, answer these four for that
line, then write the test alongside the code:

1. **Which claim.** Quote the DoD line. A test that proves no line is either
   ordinary regression coverage for code you touched or a sign of scope creep
   (Step 2a).
2. **At what level.** Pick the cheapest level that still fails when the claim is
   false; `shape` sets the floor (below). A unit test cannot prove a `story`,
   and an end-to-end run is wasted on a pure function.
3. **What failure looks like.** The test must fail against the code as it was
   before this change. Run it and watch it fail. Only then does it count as
   proof, because a test that passes before the change proves nothing about the
   change. For a `defect`, the failing repro test comes first, before the fix.
4. **What already covers it.** Search for an existing test that asserts the
   claim or sits next to it. Extend that test rather than duplicating it, and
   follow the repo's own test layout, runner and fixtures.

Record the answer in `## Log` when the line is ticked, so the tick carries its
evidence:
`- 2026-09-26 (wayfare-build-task) note: DoD "session survives a refresh" proven by e2e/auth.spec.ts "keeps session on reload", failed before subtask 3`.

## By shape

| `shape` | How the claim is proven |
| -- | -- |
| `story` | A test through the real layers for the path the story names, plus rendering the surface. Mock only what the repo does not own (a third-party API, the clock). A story test that mocks the repo's own layers is testing one layer. |
| `structural` | Where the repo already has a check for this kind of property (an import-direction lint, an architecture test), add the property to it so every build enforces it. Otherwise it is proven by reading the code, and the Log line names the files you read. |
| `visual` | Measured at the named viewports. Where the repo has visual or computed-style tests, the measurement becomes one of them. |
| `defect` | A regression test that reproduces the repro and fails before the fix. |
| `dependency` | No new test: the existing suite, the closed alert, the healthy deploy. |
| `docs` | No test: the prose is read against the code it describes. |

## Traps

- **Asserting on the implementation.** A test that checks which internal
  function was called breaks on a harmless refactor and passes on a real bug.
  Assert on what a caller or a user can observe.
- **"Existing tests green" as proof of a new claim.** It shows nothing was
  broken, not that the new thing works. A DoD line of that form is regression
  cover, and it sits alongside a line for the new behaviour, never instead of
  one.
- **Loosening an assertion to go green.** That rewords the DoD line so it
  passes, which Step 2 forbids. If the claim turned out to be wrong, record a
  `mistake` line in `## Log` and raise it; do not quietly relax the test.
