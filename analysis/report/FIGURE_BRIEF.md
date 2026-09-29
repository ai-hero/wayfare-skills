# Figure brief: regenerating the book's evidence figures

The owner's specification is `.analysis/book/_FIGURES_BRIEF.md` (Part One), parsed into
`.analysis/book/figures.json` by `report/book_spec.py`. You own a set of figures and the decks their
cards live in. For each figure you answer the **updated question** from the source records, revise the
card so its answer view is that figure, leave a machine-readable summary, and write a results sidecar the
placement script reads. You do not edit the manuscript.

Read first: `analysis/report/CHAPTER_BRIEF.md` (the data, the rules, QA), `report/deck_lib.py`'s docstring,
`report/figure_lib.py`, and the current card in `.analysis/book/_FIGURES_APPENDIX.md` (search `### Q slug`).
The dataviz rules that apply: one axis, never dual; categorical colours in fixed order (`figure_lib.CAT`);
thin marks; direct labels on the few points that matter; sample sizes visible; a legend for two or more
series; never a number on every point.

## Per figure

1. **The updated question is the specification.** Its population, unit, denominator, window and
   comparisons replace the card's `Asks`. Where the manifest lists several cards, build the figure on the
   first card (the primary) on one common population, and cite the others as inputs in the notes; their
   cards stay as they are.
2. **Recompute from `.analysis/data/*.sqlite`** through the deck's `data.py` (add a function or revise the
   existing one). Never copy a number from the appendix, a slide or the prose. Sanity-check every headline
   number with a second query.
3. **Expose what the brief asks for**: unknown or inferred categories as their own bars, censored
   observations marked, sample sizes on the axis label, an interval where a small sample could overstate a
   difference (`figure_lib.wilson`, `bootstrap_median`). Descriptive wording: "coincided with", never
   "caused".
4. **Validation.** Where the brief asks for a manual audit of a classification, draw a random sample of
   20 to 30 rows, judge them by hand from the record (commit message, prompt, item text), and report the
   agreement rate in the slide notes and the summary. If the figure needs a label you cannot audit, say so.
5. **Chart form.** The brief's *Expected figure form* decides. A bar, stacked bar, 100% bar or line is a
   native chart through `deck_lib` (`timeline`, `bars`, `chart`, `month_lines`), which the book viewer
   renders interactively. A dot-and-whisker, dumbbell, heatmap, survival or cumulative curve, scatter,
   lane timeline, Pareto or small multiple is drawn with `figure_lib` (matplotlib, brand style) and placed
   with `F.picture` in the chart box. Two panels: `deck_lib.split_box` for two native charts, or one drawn
   figure with two axes.
6. **Revise the card**, in the deck's `deck.py`: the question slide's text becomes the updated question
   (keep `originally=` as the Origin question); the **answer slide** becomes the new figure with a title
   that states the finding with its numbers; keep or add breakdown slides for the diagnostic cuts the
   brief names (by repository, by model, sensitivity to a threshold). Every number in the caption you
   will write must appear on a slide (title, points or source), or the page builder flags it.
7. **Summary table**: `F.summary(id, question=..., params={...}, columns=[...], table=[...rows...],
   notes=..., sources=[...])`, called from the deck build so the rows are the ones the chart drew. It
   lands in `.analysis/data/figures/<id>.json`.
8. **Results sidecar** `.analysis/book/results/<id>.json`:

   ```json
   {"id": "3.1", "ref": "Q fixes-by-model",
    "caption": "One sentence saying what the reader should notice, with the key numbers.",
    "alt": "Plain description of the chart for a screen reader.",
    "source": "one line: tables and detectors used",
    "summary": ".analysis/data/figures/3.1.json",
    "validation": "what was audited and the agreement rate, or 'none needed'",
    "changed": [{"old": "exact sentence in the manuscript that is now wrong", "new": "the corrected sentence"}],
    "notes": "anything the lead must know: a population that could not be shared, a form you departed from and why"}
   ```

   `ref` is the card whose first view is the figure: `Q slug`, or `Q slug · Label` to draw a named view.
   `changed` lists every manuscript sentence (search all nine `.analysis/book/0*.md` files for the old
   numbers) that the regenerated values contradict, verbatim old and new; empty list if nothing moved.
9. **Rebuild and look**: build your decks to `.analysis/decks/<topic>.pptx` (the build command is in each
   deck's docstring; use `/tmp/pptxenv/bin/python3`, which has matplotlib), validate, convert to PDF and
   render the slides you changed to images, and look at them (CHAPTER_BRIEF's QA section; the skill
   paths there may have moved: `soffice --headless --convert-to pdf` and `pdftoppm` work directly).
   Fix overflow, empty axes, a title the chart does not support.

## Rules

- Write only in your decks' folders under `analysis/report/<topic>/`, your results sidecars, your
  summaries, your deck files in `.analysis/decks/`, your figure PNGs under `.analysis/diagrams/book/`,
  and your scratch directory. Do not edit `deck_lib.py`, `figure_lib.py`, `record.py`, `book_*.py`,
  other topics' folders, `chapters.json`, or any chapter `.md`; report a bug in shared code instead of
  fixing it.
- Do not run ingests, call the GitHub API, delete `.analysis/data/*.sqlite`, write into the fleet
  checkouts, commit or push. Reading `~/workspaces/aihero` and the mirrors is fine.
- Run every script from `analysis/` with `WAYFARE_FLEET_ROOT=~/workspaces/aihero`.
- No secrets on slides, in notes or in summaries.
- Comments in code only where they stop a plausible "fix" from putting a bug back
  (`.claude/rules/comments.md`).

## Report back

Per figure: the ref, the caption, the headline numbers before and after, the population and window used,
what was audited and the agreement, what could not be done and why. Then: shared-code bugs found,
and the deck paths you rebuilt.
