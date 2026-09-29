# Diagram brief: redrawing the book's conceptual diagrams

The owner's specification is `.analysis/book/_FIGURES_BRIEF.md` (Part Two, and the Chapter 1 entries of
Part One that are conceptual), parsed into `.analysis/book/figures.json`. You own a set of diagrams. For
each you write one module `analysis/report/diagrams/d_NN_MM_slug.py` that draws it with `svg_lib` and
finishes it, which writes the SVG, PDF, 2x PNG and a sidecar with caption, alt text and source to
`.analysis/diagrams/book/`. The placement script reads the sidecar; you do not edit the manuscript.

Read first: `report/diagrams/svg_lib.py` (the grammar, in its docstring), the chapter and section the
diagram sits in (`.analysis/book/0N-*.md`; the anchor paragraph is in the manifest), and the Origin
diagram's entry at the end of `.analysis/book/_FIGURES_APPENDIX.md` (`### TAG`, its `Shows:` line) plus its
drawn PNG in `.analysis/diagrams/` where the deck had one (`Deck X, with a drawn image`; the file names
there are `<deck>-<slug>.png`). The Origin diagram is what the owner drew before; the brief says what
changes.

## Per diagram

1. **Resolve concepts before drawing.** Use the book's current vocabulary: the five loops (direction,
   production, delivery, consistency, improvement), control plane and work cells, durable objects (work
   item, goal, plan, message, decision record, register), guides and sensors, applications and
   repositories. Read the chapter's own definitions and use its words; never keep an old label because a
   deck used it.
2. **Every factual label comes from the record.** Repository names, counts, dates, shares and totals
   come from `.analysis/data/*.sqlite` (CHAPTER_BRIEF.md lists the tables; query with `sqlite3`), from
   `deck_lib.MILESTONES` (introduction commits), from the fleet's `FLEET.md` at `~/workspaces/aihero`, or
   from the chapter text where it states a number the data holds. Put each such number in the sidecar's
   `source`. A label you cannot source is drawn as `unresolved` in muted text, never guessed.
3. **Observed versus proposed.** Anything that existed during the study is solid. Anything proposed,
   intended or not yet built (a trigger that would start work, an exception path the register has no
   instance of, an integration the chapter says is next) is `target=True`: dashed, muted. The factory
   must not look more autonomous than the evidence.
4. **The grammar is fixed.** Node kinds: person, agent, record, policy, check, delivery, evidence, plain.
   Arrow kinds: flow, authority, dependency, feedback. Groups for planes, cells and boundaries. Do not
   invent a colour, a shape or a line style; if the grammar cannot say something, say so in your report.
   Type sizes: `LABEL` for node labels, `SMALL` for arrow labels and second lines, `MONO_SIZE` for group
   labels; nothing smaller. Direct labels beside objects; a legend only when a kind's meaning is not
   obvious from its labels (`c.legend`).
5. **Layout.** A canvas 1400 wide (taller when the content needs it, never wider). Left to right or top
   to bottom follows the reading order the chapter gives. Leave 40 px margins, 60 px between nodes, and
   route arrows with `via` corners so no arrow crosses a node. Nothing outside the canvas.
6. **Caption and alt.** `caption`: one sentence saying what the reader should notice, in the owner's plain
   voice. `alt`: what the diagram shows, for a screen reader, in one or two sentences. `source`: the
   Origin tags it replaces (`D16 THE FLEET; D17 ...`) and the record the labels come from.
7. **Look at it.** Open the PNG and check: no overlapping text, no label outside its box, no arrow through
   a node, every label readable, the proposed parts visibly dashed. Fix and re-run until clean.

Sidecar ids: `S.finish(c, id="1.5", name="diagram-01-05-fleet-map", ...)` for a diagram; for the table
`kind="table"` with the rows in `.analysis/diagrams/book/<name>.md` as a Markdown table (no SVG; call
`finish` only for the sidecar after writing the `.md`; `render` is skipped when the canvas is empty, so
pass a 1x1 canvas). A Part One conceptual figure drawn by you (5.1, the fleet dependency map) takes
`kind="figure"` so its ref is `Figure 5.1`.

## Rules

- Write only your modules under `analysis/report/diagrams/`, your assets under `.analysis/diagrams/book/`,
  and your scratch directory. Do not edit `svg_lib.py`, `book_*.py`, any chapter `.md`, `figures.json` or
  another agent's module; report a library bug instead of fixing it.
- Read-only everywhere else: no ingests, no GitHub API, no writes to the fleet checkouts, no commits.
- No secrets in any label, sidecar or report.
- Comments in code only where they stop a plausible "fix" from putting a bug back
  (`.claude/rules/comments.md`).

## Report back

Per diagram: the asset name, the caption, every factual label with its source, what you marked as
proposed, and any concept you could not resolve from the chapter. Then library bugs or gaps found.
