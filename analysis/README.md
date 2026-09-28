# analysis/: code that answers the software-factory question bank

Data lives in the gitignored `.analysis/data/` (sqlite files, large and
personal — never committed).

A question is a query over tables built once. We don't re-read a repo, a
transcript, or GitHub per question.

The ingest, cube, detector and question layers are generic across fleets;
the chapter code under `report/` is not — see "Running it on another fleet"
below.

## Running it on another fleet

`ingest/` and `detectors/` read the fleet from `FLEET.md` and config rather
than hardcoding its name, repos or dates. The chapter code under `report/`
carries this fleet's specifics (repo names, week ranges, known outages) and
needs adapting before it means anything elsewhere.

- `ingest/fleet.py` finds the plugin root the same way every wayfare skill
  does (`CLAUDE_PLUGIN_ROOT`, then `WAYFARE_ROOT`) and the fleet root the
  same way `scripts/hero-lib.sh`'s `hero_fleet_root` does (nearest ancestor
  of the current directory holding `FLEET.md` with no sibling `HERO.md`).
  **Run every script here from inside the fleet folder** (or a repo beneath
  it), or export `WAYFARE_FLEET_ROOT=/path/to/fleet` first — from outside
  both, `ingest/fleet.py` exits with a clear error rather than guessing.
- Repo roles come from `FLEET.md`'s own `group:` field (template/apps/infra)
  plus whichever repo's checkout matches the running plugin's own directory
  name (`PLUGIN_REPO_NAME`, not a hardcoded "wayfare-skills" string).
- Anything `FLEET.md`/`HERO.md` genuinely can't answer for a fresh fleet — a
  baseline before/after-the-factory cutoff date, which repos have no
  roadmap yet, which app IS the design system, finer role labels than a
  bare group — lives in `.analysis/config.json` (gitignored, per
  installation). Copy `config.example.json` to `<repo root>/.analysis/config.json`
  and fill in what applies; every key is optional, and code that reads one
  handles it being unset rather than assuming this fleet's values.

## Layout

```
analysis/
  bank/questions.csv     the question bank
  bank/coverage.py        how much of the bank has a questions/*.py implementation
  ingest/<source>.py      reads one source once -> .analysis/data/<source>.sqlite
  cube/db.py               connect(): ATTACHes the shared .analysis/data/*.sqlite, named label caches + cube/views.sql
  cube/views.sql            shared views over the attached sources
  detectors/d*.py          the ten shared detectors (D1-D10 from the plan); output -> detectors.sqlite
  questions/RQ_*.py        one file per answered question; questions/runner.py runs them
  report/book_pages.py     the book: one HTML page per chapter of chapters.json (--out DIR, --only N, --lessons TALK)
  report/deck_html.py      the page library: reads a topic deck (.pptx) back and fills the viewer
  report/html_views.py     extra HTML-only tabs a topic saves to .analysis/data/views/
```

`book_pages.py` injects each page, through `deck_html.py`, into a prebuilt viewer (`.analysis/viewer/dist/index.html`,
built with `npm run build` there). The viewer uses the private design system's components,
so it stays in the gitignored `.analysis/` with the data; this repo holds only the Python half.

## Running it

```bash
# ingest (each idempotent, drop-and-recreate)
python3 ingest/git.py          # local only, no fetch, no rate-limit risk
python3 ingest/plans.py        # local only
python3 ingest/knowledge.py    # local only
python3 ingest/github.py       # hits the GitHub API -- see "Rate limits" below
python3 ingest/harness.py      # reads ~/.claude/ transcripts, local only

# detectors
python3 detectors/d10_presence.py     # pure git plumbing, no model, no network
python3 detectors/d1_changesets.py    # batches commits to Haiku via `claude -p`, costs real $

# questions
python3 questions/runner.py                # run every implemented question
python3 questions/runner.py RQ-h1-016       # run one
python3 bank/coverage.py --missing          # what's left, coding-first order (sql, then detector, then haiku, then human)
```

## Rate limits (github ingest)

`ingest/github.py` was rate-limited once already running at the old
`WORKERS=10`. It's now `WORKERS=4`, checks `gh api rate_limit` before
starting and again before the heaviest fan-out (CI billable-minutes calls,
one call per run), and aborts rather than grinding quota to zero. `git.py`,
`plans.py`, `knowledge.py` never call `gh` or `git fetch` — they're local
reads of already-cloned repos, so re-running them carries no rate-limit risk
at all.

## Haiku usage

Runtime labeling only — never used to delegate
writing this code itself. `detectors/d1_changesets.py` calls `claude -p
--model haiku --effort low` from `/tmp` (so it doesn't pick up this repo's
own CLAUDE.md/AGENTS.md as billed context), batched ~40 commits per call so
the ~$0.015-0.06 fixed cost per CLI invocation amortizes across many commits
instead of one call each. Results are cached by `sha256(subject+body)` in
`detectors.sqlite`'s `changesets` table — editing the prompt does not
auto-invalidate the cache; delete rows to force relabeling.

## Fixed bugs worth knowing about

- `detectors/d10_presence.py`'s `.plans` check used to always read 0/absent
  everywhere: `.plans/` is untracked (excluded via `.git/info/exclude`), so
  `git cat-file`/`ls-tree` can never see it no matter what's really on disk.
  Fixed to stat the live filesystem for that one artifact, "head" snapshot
  only (there's no way to know a historical snapshot's untracked state).
- `detectors/d1_changesets.py` used to crash the whole run on one hung
  `claude -p` call (`TimeoutExpired`, no retry) — already-committed batches
  survived, but every later batch was lost. Now retries with a growing
  timeout before giving up on a batch.
- `ingest/plans.py`'s `_scalar()` never stripped an unquoted frontmatter
  value's trailing `# comment` — corrupted `ready_marked` into an
  unparsable date string wherever a plan item's frontmatter had one (e.g.
  `ready_marked: 2026-08-27 # user's go-ahead...`), and turned
  `one_way_door: true # why` into neither `True` nor a clean string. Fixed;
  re-running `ingest/plans.py` cleared every instance in the current data.
- `ingest/knowledge.py`'s `_field()` anchored its regex at column 0
  (`^(?:-\s*)?name:`), which only ever matched the `id:` field itself (the
  one on the `- id: ...` line) — every OTHER field on a check or control
  (`control:`, `title:`, `severity:`, `layer:`/`scope:`) is indented two
  spaces under that line and silently came back empty for every check and
  control, though the parse raised no error. This blocked the
  whole controls/checks/compliance family of questions (title-less, kind-
  less, unlinked to any control). Fixed to allow leading whitespace.
- `report/record.py`'s `commit_facts` had three faults, and every chapter
  that counts work in commits inherited them. It listed a commit once per PR
  that carried it (stacked PRs), so those commits counted twice. It only read
  a PR's own commits for `pr` change-set units, so `pr-squash` PRs (Dependabot
  among them) were counted by their squash commit, and a squash is never work.
  And it gave no PR to the commits a merge-commit PR brought onto main, since
  on main only the merge commit carries the PR number; `changeset_facts` read
  those PRs' change sets as direct pushes the same way. Now each commit counts
  once, a PR with no recovered commits is left out rather than counted by its
  squash, and `merged_via` gives those commits and change sets their PR back.

## Known caveats baked into the code

- `ingest/fleet.NO_ROADMAP_YET` (config `no_roadmap_yet`) — apps with no
  stated feature roadmap yet, so a 0% feature share there isn't
  "upkeep-only," it's early.
- `ingest/fleet.BASELINE_CUTOFF = "2026-06-01"` — the working before/after-
  the-factory boundary, taken from the deck's own auth groundings. Q2.19 in
  the bank asks whether a July 2026 boundary (hero-template/clones starting)
  separates the eras better; that's still open.
- `plans.item_logs` has no actor/author column, so "what share of log
  entries are human vs agent-written" (RQ-h6-056, RQ-h7-010) can't be
  answered yet — would need `ingest/plans.py` extended to parse a per-line
  attribution suffix, if the raw markdown carries one.
- `knowledge.controls.raw_json` is actually raw YAML text, not JSON, despite
  the column name, and carries no `priority`/`deadline` fields — only
  `id`, `title`, `severity`, `reference`, `intent`, `why`. NEW-C08-01
  ("share of controls with both a priority and a deadline") has no data for
  those two fields as things stand.
- A checkout on disk but missing from `FLEET.md`'s group mapping is invisible
  to `ingest.fleet.ALL_REPOS`; add it with config `extra_repos`.

## Status

`bank/coverage.py` reports implementation status (`--missing` lists what's left,
coding-first order); `python3 questions/runner.py` runs every implemented question.

What's left is concentrated in three buckets: `baseline`-status questions
needing deeper multi-detector cross-referencing than a single query
comfortably supports, ~30 more `haiku`-method questions that would need
their own classifier (not yet built), and a handful mixing `sql + human`
where only the sql half is code-answerable. A meaningful number of
questions across all these buckets are stubbed as `answerable_by_code:
False` with a specific reason (missing column, no ground truth, etc.)
rather than skipped — search `questions/` for that string to find them, or
extend `bank/generate_human_stubs.py`'s pattern.
