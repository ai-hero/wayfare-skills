# Research questions

The questions the software-factory study asks, by topic. Each topic's `report/<topic>/data.py` computes
the answers against the local data under `.analysis/`; the answers themselves are not published here.
A question's id never changes: the book cites it (Q work-sources) whichever chapter shows it.

## Research setting and method (`report/method/`)

- **Q counting-units-compared** How different are the counts of the same history: commits on main, original commits, change sets?
- **Q commits-per-change-set** How many commits make a change set, and how many change sets make a work item?
- **Q change-sets-per-pr** How focused are PRs at each stage, in change sets per PR?
- **Q app-ranking-by-unit** How much does the ranking of apps change with the unit: lines, commits, PRs, change sets?
- **Q grouping-rater-agreement** How far does a second rater agree with Haiku's change-set grouping?
- **Q repo-stage-at-work** What did each repo have when its work happened: skills, work items, goals, messages?
- **Q active-repo-dates** When was each repo actively developed?
- **Q work-item-format** How has the work-item format changed, and which repos still run an old one?
- **Q change-set-work-item-links** How do change sets link to work items, and work items to goals?
- **Q inferred-link-accuracy** How accurate are the links we infer: PR → work item, goal log → commit, session → PR?
- **Q observable-work-share** How much of the work is observable: planned in a work item, logged in a session, or neither?
- **Q spend-attribution-chain** Can spend be tied to a change set or work item, and where does the chain break?
- **Q design-md-staleness** How stale does each app's DESIGN.md get, and does anything catch it?
- **Q weekly-change-sets-by-stage** How many change sets did the fleet ship per week, and at which stage?
- **Q change-set-size-over-time** Did change sets get smaller or larger as the factory evolved?
- **Q commit-authors** Who wrote the commits at each stage: human alone, agent, or bot?
- **Q commit-message-style** Did commit messages change as the factory evolved?
- **Q reviewer-by-stage** Who reviewed changes at each stage: nobody, a bot, or a human?
- **Q reviewer-disagreement** How often do reviewers disagree, and do any disagreements concern security?
- **Q where-rework-is-caught** How much rework is caught inside the PR, by a gate, or after merge?
- **Q crediting-factory-changes** Which factory changes can we credit with an effect, and on what evidence?
- **Q cost-saving-changes** Which process changes were made to save cost or time, and can we see their effect?

## The harness (`report/agent_harness/`)

- **Q model-share-over-time** Which model wrote the fleet's work each week, and how fast did each new model take over after its release?
- **Q fixes-by-model** Is work done with one model followed by more fixes than work done with another?
- **Q subagent-launches** How many subagents does a session launch, of which kinds, and how has that changed?
- **Q subagent-delegation** Does the main thread hand investigation to a subagent, as the instructions ask, and does its context stay small?
- **Q context-compaction** How often does a session hit context compaction, and does the owner correct the agent more often after it?
- **Q worktree-use** How often does work run in its own worktree rather than the shared checkout, and do sessions in a shared checkout collide?
- **Q agent-stops-per-hour** How often does the agent stop to ask the owner, as a question or a permission prompt, per hour of work?
- **Q feature-uptake-lag** How long after Claude Code ships a feature does the fleet use it, and which features did it later drop?

## Human in the loop (`report/owner/`)

- **Q owner-wait-points** Where does the factory wait on the owner, and which of those waits leave a timestamped record?
- **Q owner-gates-per-item** How many owner gates does a work item pass through, and how did the gate move as the factory matured?
- **Q ready-mark-batching** Does the owner mark work items ready in batches, and how long does an item wait for that mark?
- **Q owner-decision-share** What share of shipped work had an owner decision behind it, and what share reached main with none?
- **Q owner-typing** How much does the owner type into the factory each week, and how much per change set shipped?
- **Q owner-keyboard-hours** When is the owner at the keyboard, and does that time grow with the fleet?
- **Q owner-wait-share** How long does work sit waiting on the owner, and what share of session time is that wait?
- **Q agent-questions** How often does an agent stop to ask the owner something, what about, and at which phase?
- **Q recommendation-uptake** When the agent recommends an option, how often does the owner take it?
- **Q owner-corrections** How often does the owner correct or redirect an agent, and is that falling per change set?
- **Q owner-interrupts** How often does the owner stop a running agent mid-task?
- **Q tool-call-denials** How often does the owner deny a tool call, and did denials fall as permissions caught up with policy?
- **Q who-really-reviews** Who actually reviews and approves merged work, once agents acting under the owner's account are told apart from the owner?
- **Q one-way-door-changes** Do one-way-door changes stop for a human, or merge like everything else?
- **Q other-humans** Is the owner the only human in the loop?

## Skills and factory evolution (`report/skills/`)

- **Q skill-set-history** How has the set of skills grown, been renamed, merged and retired since the plugin started?
- **Q old-skill-names** After a skill is renamed, how long does the owner keep typing the old name?
- **Q skill-prose-vs-scripts** Did the skills' prose level off while scripts and tests grew?
- **Q scripted-step-share** What share of each skill's steps runs as a script rather than as prose the model interprets?
- **Q skill-run-frequency** How often is each skill invoked each week, and which few carry the factory?
- **Q who-starts-skills** Who starts each skill, the owner or an agent, and has that shifted?
- **Q skill-chain-completion** When one skill hands off to the next (push → review → ship), how often does the chain complete in one session?
- **Q clean-skill-runs** How often does a skill run end cleanly, without an error, an interruption or the owner correcting it?
- **Q route-to-merge** Which route does work take to a merge: a goal, a one-shot pipeline, pipeline skills by hand, or no skill at all?
- **Q factory-work-per-week** How much work went into the factory itself each week, and of what kind?
- **Q plugin-change-triggers** What sets off a change to the plugin: the owner's feedback, a fleet repo's report, a review or audit, or planned work?
- **Q plugin-follow-up-fixes** How often does a change to the plugin need a follow-up fix, and how quickly is it fixed?
- **Q verdict-skill-hygiene** Do the skills that give a verdict end with an explicit one, treat outside text as data, and cap their waits, and since when?
- **Q skill-use-by-repo** Which repos use the skills, since when, and how often is the roadmap refresh run in each?
- **Q plugin-uptake-and-rename** How does each repo take the plugin, and what did the 22 Sep repo rename cost?
- **Q hero-md-fields-set** Does each repo's HERO.md set every field the skills read?
- **Q repo-local-skills** Which repos wrote skills of their own, and did any move up into the plugin?

## Connectors (`report/connectors/`)

- **Q declared-connections** Which connections does each repo declare, in what form, and when did each first appear?
- **Q connections-read-by-skills** Which connection kinds does a skill actually read, and how long did declared kinds sit with nothing reading them?
- **Q connection-reach-in-use** How does the agent actually reach each connection, week by week, and does its use match what the repo declares?
- **Q wrong-declared-reach** How often was a declared reach wrong, and how long did it stay wrong?
- **Q copied-connector-values** How often is a connector's value copied into more than one place, and how long do the copies disagree?
- **Q unreachable-connections** When a connection could not be reached in a session, did the run say so or quietly carry on without it?
- **Q design-snapshot-lag** How far behind the design source does the design-system's snapshot sit, and does the gap shrink?
- **Q design-system-release-reach** How long does a design-system release take to reach each consuming repo?
- **Q registry-component-share** How much of each app's UI comes from the design-system registry rather than being written in the repo?
- **Q design-work-finders** Once a repo's agent could read its design, did design work shift from owner-reported to agent-found?
- **Q design-divergence** How much open divergence between the design and the code does each repo carry, and who notices it first?
- **Q divergence-outcomes** When the code diverges from the design, how does it end: a fix, a recorded decision to diverge, a question back to the design, or nothing?
- **Q design-feedback-loop** How often does the code send findings back to the design source, and do they get answered?
- **Q expired-logins** How often does work stop because a login or credential has expired, and how long does it wait for the owner?
- **Q human-only-verification** How many work items could only be verified by a person because the agent lacked access, and how long did they wait for that check?

## Knowledge and memory (`report/memory/`)

- **Q knowledge-stores** Which knowledge stores does each repo keep, and when did each one appear?
- **Q observable-repo-facts** What can the factory observe about each repo without asking an agent?
- **Q startup-instruction-size** How much instruction text does an agent load before it starts, and did moving detail on demand shrink it?
- **Q stale-prose-fixes** How often does work correct prose that had gone false, and is the fix its own work or a rider on something else?
- **Q work-item-log-contents** What do agents write into a work item's log, and has it become a record of mistakes and decisions?
- **Q work-item-cost-record** Can the cost of a work item be read back from the plan store?
- **Q memory-growth** How does agent memory grow, and what share of it says why and links to anything?
- **Q plan-store-authors** Who writes the plan store: skills, agents outside a skill, or the owner?

## Architecture records (`report/architecture/`)

- **Q design-record-adoption** When did each repo get a design record, and which repos still have none?
- **Q design-record-sections** Do all records carry the template's sections, and what do they hold?
- **Q design-record-growth** How did the design records grow, and are they still being edited?
- **Q decision-rate** How many decisions are recorded, and does the rate keep pace with the work?
- **Q decision-timing** Are decisions written when they are made, or backfilled later?
- **Q decision-in-same-change** Is each decision recorded in the same change that makes it?
- **Q design-record-writers** How much work touches the design record, and which path writes it?
- **Q append-only-decisions** Do records follow their own rule that decisions are append-only?
- **Q template-inheritance** How much of each app's record is inherited from the template, and how fast do template decisions reach the clones?
- **Q fleet-architecture-home** Where does fleet-level architecture live, and how much of it is restated per repo?
- **Q design-record-lag** How far behind the code is each record?
- **Q repeated-facts-agree** Do facts stated in several places agree, and are they checked?
- **Q design-guardrails-fired** Have the design record's own guardrails ever fired?
- **Q work-items-cite-design** Do architectural work items cite the design record?

## Work items and flow (`report/work_items/`)

- **Q backlog-trend** How many work items are opened and closed each week, and is the backlog growing or draining?
- **Q work-item-kinds** What kind of work do the items describe, and did the mix shift from features to structural work?
- **Q work-sources** Where does work come from: the roadmap, the owner, an audit, or something found while doing other work?
- **Q item-lead-time** How long does a work item take from filed to shipped, and did that get shorter as the factory evolved?
- **Q ready-mark-wait** How long does an item wait for the owner to mark it ready, and how long from ready to shipped?
- **Q pickup-wait** Once ready, how long do items wait to be picked up, and how long do blocked items wait after their dependency ships?
- **Q security-work-speed** Does security work ship faster than other work, and how much of the hardening audit has shipped?
- **Q work-item-endings** How does work end: shipped, delivered upstream, dropped, or still open?
- **Q prs-per-work-item** How many PRs does a work item take, and how many work items does one PR carry?
- **Q goal-duration-and-scope** How long does a goal take, how many items does it cover, and how often does its scope grow after it starts?
- **Q goal-budgets** Do goals stay within the commit budget they set themselves?
- **Q pr-open-time** How long is a PR open, and does that grow with the number of change sets it carries?
- **Q pr-time-breakdown** Where does a PR's open time go: agent working, CI, waiting for the owner, usage limits, or no session open?
- **Q sessions-per-pr** How many sessions does it take to carry a PR to merge, and how long are the pauses between them?
- **Q when-work-lands** When does work land, by day of the week and hour of the day?
- **Q change-set-size-vs-pr-time** Does a change set's size predict how long its PR stays open?

## Mistakes and rework (`report/mistakes/`)

- **Q mistake-records** Where does the factory record an agent's mistakes, and since when?
- **Q readable-gate-verdicts** Which gates leave a verdict a script can read, and which leave nothing?
- **Q in-pr-fix-share** How much of each PR's work is fixing that same PR before it merges?
- **Q fix-forwards** How often does a merged PR need a fix-forward, how soon, and is that falling?
- **Q reverts-and-reopens** How often did something go wrong badly enough to revert or reopen?
- **Q defect-lifetime** How long does a defect live between the PR that introduced it and the PR that fixed it?
- **Q defect-origin** Whose defect is it: this factory's earlier work, the template, or something older?
- **Q mistake-kinds** What kinds of mistakes do agents make, and which keep recurring?
- **Q who-catches-mistakes** Who catches the mistakes: the agent itself, review agents, CI, the judge, or the owner?
- **Q where-fixes-land** Where do the fixes land: product code, tests, CI, config or docs, and how many are security fixes?
- **Q done-not-done** How often is "done" not actually done, and what closes the gap?
- **Q reviewer-and-judge-changes** How have the reviewer and the judge changed, and how often does each send work back?
- **Q review-persona-value** Does each review persona earn its place?
- **Q hollow-checks** How often did a check pass without really checking, and who noticed?
- **Q found-problem-follow-up** What happens to the problems an agent finds but doesn't fix: filed, done, or left to sit?
- **Q replanning-after-ready** When a work item is marked ready, how often does it need replanning afterwards?
- **Q errors-vs-corrections** Are agents erring less, or just being corrected less?

## Security (`report/security/`)

- **Q scanner-coverage** When did each repo get secret, dependency and container scanning, and does each run in CI or only as a local hook?
- **Q supply-chain-pins** How far do supply-chain pins reach (action SHA pins, image digest pins, Dependabot coverage), and how did coverage grow?
- **Q security-work-share** How much of the fleet's work is security work, and how has that share moved as the factory grew?
- **Q security-finders** Where are security problems found: a scanner, Dependabot, a review bot, an audit, the owner, or production?
- **Q review-security-flags** How often does code review flag a security problem in a PR, how severe is it, and is the rate falling?
- **Q agent-security-defects** When an agent's own change introduced a security defect, how long did it sit on main, and did it reach production?
- **Q security-fix-time** How long does a security finding take from discovery to merged fix, and how many are still open?
- **Q dependency-fix-lag** When a dependency gets a security fix, how long does each repo take to apply it, and how often is the same advisory fixed separately in several repos?
- **Q sibling-hardening-lag** When a hardening fix lands in one repo, how long until the siblings with the same defect are fixed, and did each fix it the same way?
- **Q dependency-bump-upkeep** How much upkeep do dependency bumps cost each week, and does grouping make it smaller?
- **Q scanner-mistakes** How often has a scanner or its suppressions been wrong: an ignore that outlived its CVE, a scan aimed at the wrong target, a gate that could not fail?
- **Q judge-attack-tests** Can the auto-approve judge be tricked into approving, and how much of that has been tested rather than assumed?
- **Q plugin-security-fixes** Where do the plugin's own security fixes come from, and did each remove the risky mechanism or only narrow it?
- **Q unmet-security-criteria** How often is a work item marked done while one of its own security acceptance criteria is not met?
- **Q false-security-claims** Does a repo's documentation claim a security control the repo does not have, and where did each false claim come from?
- **Q infra-security-risks** What infrastructure security risks has the fleet recorded, and which have been checked live?
- **Q committed-secrets** Has a secret ever been committed to a repo, and how long did it stay before it was found and rotated?

## Fleet scope and apps (`report/fleet/`)

- **Q fleet-size-over-time** How many repos did the fleet hold each month, of which kinds, and when did each one join or leave?
- **Q fleet-map-accuracy** Since when has the fleet had a map, and how closely does it match the repos actually checked out?
- **Q dev-port-claims** Did every app with a dev stack claim its own port, and how long did new clones sit on the template's port?
- **Q repo-kind-requirements** Does the fleet say what each kind of repo must contain, and how much of it does each repo actually have?
- **Q template-shape** What shape is the template, and how did that shape change as it matured?
- **Q clone-template-share** Which template version did each clone start from, and how much of the template does each clone still share today?
- **Q stack-convergence** How many repos share the template's stack, and is the fleet converging on it or drifting apart?
- **Q shared-service-deps** Which apps depend on the shared services (identity, the design-system registry, the infrastructure repos), and do their design records say so?
- **Q design-system-scaffolding** Is the design system shipping components apps can use, or is its own scaffolding growing faster?
- **Q app-lifetime-work** How much work has each app received over its life, in change sets, and does it rise, plateau or fall with age?
- **Q features-vs-structure** How much of each app's work is features, and how much is structural work, and did the mix shift when larger Opus models took over?
- **Q feature-scope-progress** For each app, how many planned features have shipped and how many are still open, week by week?
- **Q code-origin-split** How does each app's code grow, split into code written for it, generated code and vendored code?
- **Q app-to-first-feature** How long does a new app take to go from creation to its first shipped feature and its first live deploy?
- **Q route-allowlist-pairs** When an app's API route and its UI proxy allowlist must change together, do both halves land in the same PR?
- **Q fleet-roster** Which repos make up the fleet, what is each one for, and when did each come alive?
- **Q repos-in-motion** How many repos did the owner keep moving at once?
- **Q fleet-throughput** How much work has the fleet shipped, counted in change sets, and how did the weekly rate grow?
- **Q work-by-repo** Where did the work go: which repos got the most, and did the mix shift?
- **Q apps-vs-factory-work** How much of the work built the apps, and how much built the factory itself?
- **Q codebase-size** How large has the codebase grown, repo by repo?
- **Q weekly-factory-cost** What does a week of the factory cost, in model spend and in the owner's hours?
- **Q work-kind-mix** What kind of work is it: features, fixes, or upkeep?
- **Q change-set-rollup** What does one change set look like, and how does it roll up into PRs, work items and goals?
- **Q planned-in-writing** How much of the work was planned in writing before it was built?
- **Q toolkit-growth** How did the factory's own toolkit grow: skills, checks and practices, and when did each arrive?
- **Q work-by-theme** Which of the study's themes does the fleet's work fall under, and how has that shifted?

## Cross-repo messaging (`report/messages/`)

- **Q message-channels** What channels have repos used to pass requests and context to each other, and when did each start carrying traffic?
- **Q message-direction** Which way do messages flow: from shared repos down to their consumers, or up from consumers to the shared repos?
- **Q message-delivery** Of the messages sent, how many reached the recipient's inbox, and how many were answered, declined or are still waiting?
- **Q message-response-time** Once a message is delivered, how many days until the receiving repo answers or acts on it, and does an awaited message get answered faster?
- **Q cross-repo-finds** When an agent finds that another repo needs to change, does it send a message, file it locally, fix the other repo itself, or drop it?
- **Q message-fidelity** When a repo acts on a message, how far does the work it ships differ from what the message asked for?
- **Q sibling-awareness** How much does an agent working in one repo know about its siblings, and where does it get that from?
- **Q cross-repo-edits** How often does a session in one repo open changes in another repo, and did that stop when the mailbox made it against the rules?
- **Q upstream-vs-local-changes** When the same change lands in several repos, how often was it made once upstream and carried out, and how often did each repo make it on its own?
- **Q upstream-change-reach** Once a change exists upstream, how many days until each consumer has it, and how many consumers still do not?
- **Q vendored-file-staleness** Do the rules, hooks and workflows vendored from wayfare stay current in each repo, or go stale until the next re-vendor?
- **Q fan-out-method** How does a change actually get carried across the fleet: one session fanning out, or a session in each repo?
- **Q fan-out-review** When a change lands in many repos, is each PR reviewed, and how many problems surface after merge instead?
- **Q shared-piece-references** How do repos consume shared pieces: by a moving reference, a vendored copy, or a pinned version, and how has that mix changed?
- **Q upstream-breaks** When an upstream change outside CI broke its consumers, how many repos broke, and how long until each was fixed?
- **Q upstream-impact-notes** When an upstream change affects its consumers, does the change say which repos it affects?
- **Q cross-repo-decision-agreement** Where a decision should hold in every repo, do the design records agree, and how long does a disagreement last?
- **Q ownership-handovers** When scope or a convention moves from one repo to another, do both repos' records say who owns it now?

## Compliance and drift (`report/compliance/`)

- **Q register-growth** How has the control register grown since it was created, and what share of its checks can a machine run?
- **Q control-origins** What prompted each control: a bug seen in a fleet repo, an outside incident, or a design choice made before anything broke?
- **Q rule-change-review** Who changes the rules, and does a rule change pass the same review gate as code?
- **Q audit-frequency** How often is the fleet actually checked against the register, and how stale is the picture between checks?
- **Q audit-pass-rate** At each audit, what share of check × repo results passed, and which repos pulled the rate down?
- **Q new-check-violations** When a new check is written, how many repos already break it, and how long could they have been breaking it?
- **Q violation-fix-time** Once a check catches a repo, how long until that repo passes, and what share never does?
- **Q open-violations** Which failures are still open, and were they worked in severity order before any control had a deadline?
- **Q clone-compliance-drift** Does a new clone start as compliant as the template, and does it stay there?
- **Q register-copy-drift** Do copies of the register drift from the canonical one, and what catches them?
- **Q compliance-work-share** How much of the fleet's work and spend goes to compliance and security rather than product?
- **Q changes-name-controls** How often does a change name the control or check it serves?
- **Q gate-loosening** Do changes to the gates only tighten them, and what comes before a loosening?
- **Q fix-or-silence** When a gate fails, does the agent fix the code or silence the gate?
- **Q rule-files-self-check** Do the instruction files that state the factory's rules pass those rules themselves?

## Deployment (`report/deployment/`)

- **Q platform-history** How did the platform a merged change lands on evolve over the year?
- **Q app-to-infra-time** How long does a new app take to go from its first commit to provisioned infrastructure?
- **Q deploy-on-merge** Which provisioned apps actually deploy on merge, and since when?
- **Q merge-to-production** How long does a merged change take to reach production, and has that shortened?
- **Q deploy-failures** How often does a deploy fail, and what brought it back?
- **Q production-uptime** Is production up, and do outages line up with deploys?
- **Q ci-red-rate** How often does a PR's CI go red, and has that fallen as checks moved before the push?
- **Q ci-red-to-green** When a PR's CI goes red, what turns it green, and how long does it take?
- **Q flaky-checks** Which checks fail and then pass with no code change, and is that getting rarer?
- **Q never-failed-checks** Which checks have never failed in the observed history, and could they?
- **Q shared-workflow-breaks** When a shared workflow changes, how many repos break, and for how long?
- **Q action-pin-spread** How fast does a pinned action version reach every repo, and how many refs are unpinned?
- **Q infra-built-like-apps** Is the infrastructure built by the factory the same way the apps are?

## Spend and cost (`report/spend/`)

- **Q weekly-spend** How much does the factory spend a week, and in which repos?
- **Q traceable-spend** How much of the spend can be traced to the change set it produced?
- **Q change-set-cost-trend** What does one change set cost, and has that fallen as the factory matured?
- **Q cost-rollup** How does cost roll up from change set to PR, work item and goal?
- **Q paid-vs-reported-cost** What does the factory actually pay compared with the cost the harness reports?
- **Q spend-by-model** Which models carry the spend, and what does a change set cost on each?
- **Q subagent-spend** How much of the spend goes to subagents, and to which kind?
- **Q review-cost** What does review cost per change set, and does it grow with the size or risk of the change?
- **Q spend-by-work-kind** What share of spend goes to features, fixes, security and upkeep, and how has the mix moved?
- **Q ci-minutes** How many CI minutes does the fleet use a week, and on which workflows?
- **Q wasted-ci-minutes** How many CI minutes go to runs that could not change an outcome?
- **Q dependency-update-cost** How much spend and CI goes to dependency updates rather than the owner's own work?
- **Q ci-change-effect** Did the fleet's CI changes lower CI minutes per change set?
- **Q multi-repo-change-cost** What does a change cost when it is made in several repos instead of once upstream?

## Floor efficiency (`report/efficiency/`)

- **Q change-set-traceability** Can each shipped change set be traced to its cost, its wall time and any later fix?
- **Q session-clock** Where does the factory's session clock go: working, waiting on the owner, stopped by a limit, or idle?
- **Q usage-limit-stops** How often did usage limits stop the factory, how long did each stop last, and what changed them?
- **Q owner-wait-length** When the factory waits on the owner, how long does it wait, in a session and at a PR?
- **Q concurrent-sessions** How many sessions run at once, and how close does the factory come to the owner's ceiling of about six?
- **Q work-in-progress** How much work does the factory carry in progress: open PRs and unfinished work items?
- **Q pr-vs-item-lead-time** How long does work take from start to merge, at the PR and at the work item, and do the two agree?
- **Q work-while-away** How much of the factory's work happens while the owner is away from the keyboard?
- **Q unshipped-work-share** What share of opened work and of session spend never ships?
- **Q right-first-time** What share of merged change sets ship right the first time, with no fix within a week?
- **Q wasted-session-effort** How much session effort is thrown away: tool calls that fail or are refused, and sessions a limit cut short?
- **Q output-vs-agent-hours** Does output rise with the hours agents work, or stay flat as more sessions run?
- **Q oee-score** Summed into one OEE-style score (availability × performance × quality), how efficient is the factory, and which factor holds it down?

## Manager's thinking (`report/manager/`)

- **Q written-reasons** Where does the factory write down why a rule, gate or skill exists, and how much of that record carries a reason?
- **Q owner-attention-split** How did the owner split attention between building the products and building the factory?
- **Q correction-kinds-over-time** Did the owner's corrections move from direction and taste to catching the agent's errors?
- **Q corrections-to-memory** When the owner corrects an agent, does the correction become a memory, a rule or a check, and how soon?
- **Q auto-approve-changes** What prompted each change to the auto-approve gate?
- **Q controls-after-incidents** Were the register's controls written after an incident, as the owner says?
- **Q register-origin** When and why did the fleet get a shared control register?
- **Q restated-rules** Which rules did the owner have to restate most?
- **Q plugin-restructures** What triggered each restructuring of the plugin's names and layout, and what broke after each?
- **Q limit-driven-changes** What did the owner change because of spend and usage limits?
- **Q owner-as-go-between** How often did the owner act as the go-between for concurrent agent sessions, and did the mailbox take that over?
- **Q care-vs-speed** When did the owner trade care for speed, and what did it cost in follow-up fixes?
- **Q incident-bursts** Which incidents were followed by the biggest bursts of factory change?
- **Q practice-flow-direction** Did practices flow up from the products into the template and plugin, or down from them?

## Toward an architecture (`report/components/`)

- **Q component-inventory** What are the factory's components, when did each first ship, and which are still in use today?
- **Q adoption-order** In what order did each repo take the components up, and do repos skip or reorder steps?
- **Q adoption-lag** How long after a component shipped did each repo start using it?
- **Q retired-components** Which components were built and then removed or replaced, and how long did each live?
- **Q component-traffic** What share of the fleet's change sets passed through each component, week by week?
- **Q output-after-adoption** How did an app's weekly output change in the weeks after it took each component up?
- **Q fixes-after-adoption** Did follow-up fixes after a merge become more or less common after an app took each component up?
- **Q owner-share-after-adoption** Did the owner's hands-on share of the work fall after an app took each component up?
- **Q cost-by-architecture-depth** Does work that goes through more of the architecture cost more or less per change set?
- **Q component-dependencies** How do the components depend on each other, and has that web grown more tangled or simpler?
- **Q skipped-components** Did any repo use a later component without an earlier one, and how did those weeks go?
- **Q template-vs-plugin-components** Which components reach a repo through the template at creation, and which arrive later through the plugin?
- **Q milestones-vs-releases** How much of the change around each milestone coincides with a new model or Claude Code release instead?
- **Q recommended-adoption-order** What order of adoption does the fleet's evidence support for a new factory?

## The field (`report/field/`)

- **Q portable-questions** Could another factory ask this study's questions of itself, or are they written in this fleet's names?
- **Q git-only-measurability** How much of this study could another factory measure from git and GitHub alone, and how much needs transcripts or wayfare's own records?
- **Q unified-timeline** Can the fleet's separate logs merge into one timeline that replays what happened, and at what time resolution?
- **Q comparable-units** Is each number we compare with the field defined in a unit another factory could reproduce?
- **Q no-human-merges** What share of merged changes reached main with no human action, and how has it moved as the factory evolved?
- **Q review-load-vs-volume** Did human review work per merged change grow as the fleet's volume grew, the way large deployments report?
- **Q throughput-by-stage** How did measured throughput change as each app moved through the stages, and does it match the speed-up the owner believes in?
- **Q human-reading-points** At which stages does a human read the agent's intermediate output, and how has that placement moved?
- **Q onboarding-speed** Did each new repo get onto the factory faster than the one before it?
- **Q minimal-register** What is the smallest part of the control register another factory could reuse, and do its honesty signals hold up?
- **Q practices-after-failures** Which verification practices did the factory adopt after a specific failure, and did that failure stop recurring?
- **Q coordination-limits** How close did one operator's coordination conventions come to their limit as repos and parallel work grew?

## Conclusion (`report/conclusion/`)

- **Q total-output** What did the factory ship in total, and in which repos and weeks?
- **Q stage-comparison** At each stage, how did throughput, rework, spend and owner time per change set compare?
- **Q quality-vs-throughput** Did quality hold as throughput rose?
- **Q change-sets-per-owner-hour** How many change sets does an hour of the owner's attention buy, and is that rising?
- **Q unattended-run-length** How long does the factory run without the owner, and is that stretch growing?
- **Q repos-vs-attention** Does adding repos add output, or split a fixed amount of owner attention?
- **Q binding-constraint** Which constraint binds the factory now: owner attention, rate limits, spend or CI?
- **Q one-shot-gap** Is the one-shot gap closing, and in which repos is it still open?
- **Q evidence-coverage** Which evidence covers which weeks, and which practices predate their own data?
- **Q sessions-without-merge** What share of agent sessions and spend leads to no merged change?
- **Q unanswered-questions** Which of the study's questions could not be answered, and why?
- **Q hypotheses-checked** Which of the owner's hypotheses held, and which findings were surprises?
- **Q backlog-age** Is the backlog shrinking or growing, and how old is the open work?
- **Q new-work-sources** Where does new work come from now: the owner, the audits, messages, or one-shot tasks?
- **Q unfixed-recurring-problems** Which recurring problems has the factory not yet fixed at the source?
- **Q ranked-next-steps** Which next steps does the evidence most support, ranked by what each would save?
