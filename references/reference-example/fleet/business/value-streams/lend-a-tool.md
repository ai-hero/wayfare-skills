value-stream: lend-a-tool@1

# Lend a tool

Status: **hypothesis**, written from the volunteers' description of a typical
Saturday. Not yet checked against a timed month.

- **Trigger:** a member of segment:households@1 or segment:makers@1 needs a tool
  for a job.
- **Outcome:** the right tool, working, in hand for the job, without buying one
  that sits in a garage for the rest of the year.
- **Owner role:** role:coordinator@1
- **serves:** goal:more-loans@1, goal:tools-that-work@1

## Stages

| # | Stage | Entrance criteria | Exit criteria | Value item | Participating roles | Enabling capabilities |
| -- | -- | -- | -- | -- | -- | -- |
| 1 | Find a tool | a member has a job in mind | the member has chosen an available tool | a chosen tool | none, the member alone | capability:tool-discovery@1 |
| 2 | Reserve | a tool is chosen | the tool is held for the member for a pickup day | a held tool | none, the member alone | capability:tool-discovery@1, capability:reservation@1 |
| 3 | Hand over | the member arrives on the pickup day | the loan is recorded with a due date and the tool leaves the shelf | a tool on loan | role:desk-volunteer@1 | capability:reservation@1 |
| 4 | Use | the tool is on loan | the member brings the tool back | a finished job | none, the member alone | none |
| 5 | Return and inspect | the tool is back at the desk | its condition is recorded and it is available or in repair | a tool known to work | role:desk-volunteer@1 | capability:returns@1, capability:condition-tracking@1 |
| 6 | Repair or retire | the tool failed inspection | the tool is fixed and available, or retired | a working catalog | role:repair-volunteer@1 | capability:condition-tracking@1 |

## Measures

| # | Volume | Lead time | Process time | % complete and accurate | Source |
| -- | -- | -- | -- | -- | -- |
| 1 | about 60 searches a week | unknown | unknown | unknown | volunteers' estimate |
| 2 | about 35 reservations a week | 1 day | 2 minutes | 90% | the paper hold book |
| 3 | about 30 hand-overs a week | 5 minutes | 3 minutes | 80% (due dates missed) | volunteers' estimate |
| 4 | about 30 loans a week | 6 days | outside the library | not measured | none |
| 5 | about 30 returns a week | 4 days | 5 minutes | 70% (condition not written down) | volunteers' estimate |
| 6 | about 4 repairs a week | 9 days | 40 minutes | unknown | the repair shelf |

## Constraint

**Stage 5, hypothesis.** Returns are checked only when a volunteer has time, so
a returned tool waits four days on the shelf for five minutes of inspection.
Every tool waiting there is a tool no member can reserve, which caps how many
loans the library makes in a week. Q1 would confirm it. If it holds, work at
stage 5 raises throughput; work elsewhere only saves effort.

## Where AI changes the work

| # | Issues (waste, impact) | AI opportunity | Readiness | Priority |
| -- | -- | -- | -- | -- |
| 1 | members ask the desk what is in stock (motion) | `automate`: a searchable catalog | the tool list exists on paper | 3 |
| 2 | holds lost from the paper book (defects) | `automate`: reservations online | no system of record yet | 2 |
| 3 | loans recorded without a due date (defects) | `none`: a required field fixes it | none needed | 4 |
| 4 | none observed | `none` | none needed | none |
| 5 | returned tools wait for inspection (waiting, inventory); condition not written down (defects) | `augment`: a guided condition check at the desk | volunteers agree to a checklist; low risk | 1 |
| 6 | broken tools reported by word of mouth (defects) | `agent`: draft the repair note from the condition check | depends on stage 5's record | 5 |

## Questions

- **Q1:** Is stage 5 really the constraint? Time ten returns from the desk to
  the shelf for one month.
- **Q2:** Does a required due date cut late returns? Compare late returns for
  the month before due dates were required with the month after.
