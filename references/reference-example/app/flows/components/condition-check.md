component: condition-check@1

# ConditionCheck

used on: returns-desk

## Takes

- the returned tool: tool.tool_id, name, category
- its open loan: loan.loan_id, member, returned_on

## Affordances

- **Three questions** (shown one at a time, by category): does it power on or
  move freely, is anything cracked or missing, is it clean enough to lend.
- **Save check** (when all three are answered) calls
  `RecordCondition(loan_id, condition)`, which sets loan.condition_on_return and
  tool.last_checked_on, then sets tool.status to `available` for `good` or
  `worn`, or `in-repair` for `broken`; the volunteer returns to the waiting
  list.

## States

- **answering:** the current question and how many are left
- **saving:** the buttons are disabled
- **save failed:** the answers are kept and a Try again button shows
