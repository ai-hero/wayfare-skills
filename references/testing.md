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
and what it renders, a measurement at a viewport. If the answer names nothing
specific to observe ("check that it works"), the line is too vague. Rewrite it
until it has one ("works well" becomes "the list renders 500 trips in under
200ms"). The planner asks itself first, and asks the user only when it cannot
answer.

Write the line, not the answer. The answer is just evidence that the line can be
tested. If you write it into the plan, it becomes the test list this page exists
to keep out.

## At build: the question becomes the method

Before the subtask that should make a DoD line true, answer these four for that
line:

1. **Which claim.** Quote the DoD line. A test that proves no line is either
   ordinary regression coverage for code you touched or a sign of scope creep
   (Step 2a).
2. **What evidence.** Choose it from what the line claims, not from the task's
   shape alone. The line that asserts the task's own claim takes the evidence
   the table below names for its `shape`; "docs updated" is proven by reading,
   and "tests green" by the run. Where the evidence is a test, pick the cheapest
   level that still fails when the claim is false: a unit test cannot prove a
   `story`, and an end-to-end run is wasted on a pure function.
3. **What failure looks like.** For a line a test proves, write the test first,
   run it, and see it fail on its assertion, not on a missing import or an
   undefined name. Then write the code and see it pass. A test that has never
   failed proves nothing about the change. Writing it first is also what keeps
   you from stashing or checking out to recreate the old code: never do either.
   For a `defect`, the failing test is the repro.
4. **What already covers it.** Search for an existing test that asserts the
   claim or sits next to it. Extend that test rather than duplicating it, and
   follow the repo's own test layout, runner and fixtures.

Record the evidence in `## Log` when the line is ticked (the test and that it
failed first, or what was read or measured), so the tick carries it. One line
may carry both the subtask tick and the DoD evidence:
`- 2026-09-26 (wayfare-build-task) note: DoD "session survives a refresh" proven by e2e/auth.spec.ts "keeps session on reload", failed before subtask 3`.

## By shape

The evidence for the line that asserts the shape's own claim:

| `shape` | How the claim is proven |
| -- | -- |
| `story` | A test through the real layers for the path the story names, plus rendering the surface. Mock only what the repo does not own (a third-party API, the clock). A story test that mocks the repo's own layers is testing one layer. Where the repo has no harness that reaches the path, the evidence is the rendered surface and a named observation, and the missing harness is its own item (Step 2a), not built inside this task. |
| `structural` | Where the repo already has a check for this kind of property (an import-direction lint, an architecture test), add the property to it so every build enforces it. Otherwise it is proven by reading the code, and the Log line names the files you read. |
| `visual` | Measured at the named viewports. Where the repo has visual or computed-style tests, the measurement becomes one of them. |
| `defect` | A regression test that runs the repro and fails before the fix. |
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
- **Loosening an assertion to go green.** It has the same effect as rewording
  the DoD line so it passes, which Step 2 forbids. If the claim turned out to be
  wrong, write a `mistake` line in `## Log` and stop, per Step 2's *Stop and ask
  on ambiguity*; under a goal turn, report it as the task's `stop: failure`.
