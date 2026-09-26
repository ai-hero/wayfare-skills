---
description: Comment discipline, when a comment earns its place, and the slop that never does.
---

# Comments

Write a comment only to state a constraint the code cannot show. The test:

> **Would someone later undo this for a reason this comment prevents?**

If the answer is no, the comment is noise, and noise outlives its accuracy.
Comment rot is not untidiness: an outdated comment is worse than none, because
it gets believed.

**Don't** write what the next line does, where the code came from, that a change
is correct, or that a PR fixed something. That is talking to the reviewer, and
it is stale the moment the PR merges. Git already records the history. The usual
agent-generated forms all fail the test above: narrating the diff
(`// added validation`), restating the signature above a function, section
banners over three lines, `// TODO: consider...` filler. Leaving them out is not
an optimization; a change that adds them is wrong and gets reworked.

**Do** write the comment that stops a plausible "fix" from putting a bug back.
Every comment that has earned its place in this repo names a trap:

- `govet: {shadow: true}` is invalid and silently does nothing. The working
  spelling is `govet.enable: [shadow]` (`.golangci.yaml`). Without the note,
  someone "simplifies" it back and shadow checking stops running, with no error.
- `delete event.node.req.headers[...]` reports success and does nothing; h3
  forwards from a parse-time snapshot. That one line made `x-forwarded-for`
  spoofable end to end despite code that read correctly.
- `curl -fsS ... | jq` swallows curl's exit status, so a documented "non-zero on
  503" becomes a lie (`just health`).
- The container `HEALTHCHECK` probes `/livez`, never `/readyz`: container health
  drives restarts, so probing dependencies makes an orchestrator restart the
  container over someone else's outage.

Each reads as an odd choice until you know the failure. That is exactly when a
comment pays for itself.

Density: if two comments explain the same thing, delete one. If a file has none
and contains a trap, it has the wrong number.
