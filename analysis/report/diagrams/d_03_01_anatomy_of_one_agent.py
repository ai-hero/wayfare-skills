"""Diagram 3.1: one coding agent, drawn as the layers around the model, with a key to the trace per layer."""
import svg_lib as S

c = S.Canvas(1400, 1060)

# The person sits outside every layer: the authority boundary.
owner = c.node(40, 330, 250, 130, "person", "Owner", "prompts, approvals, logins; the harness stops and asks")

# Nested layers, outermost first.
account = c.group(340, 40, 1020, 700, "Account and limits · session, weekly, spend, credits")
checkout = c.group(370, 90, 960, 620, "Shared checkout or worktree · files, git, shell, CI")
harness = c.group(400, 140, 610, 540, "Harness · the program that runs the agent")

model = c.node(440, 200, 250, 110, "agent", "Model", "generates the next step from what the harness shows it")
tools = c.node(740, 200, 240, 110, "agent", "Tools", "Bash, Edit, Read, Agent, MCP; results return to the model")
guides = c.node(440, 370, 250, 130, "policy", "Guides", "instructions, skills, memory, permissions: steer before it acts")
sensors = c.node(740, 370, 240, 130, "check", "Sensors", "hooks, tests, CI: inspect what it did")
context = c.node(440, 550, 540, 100, "record", "Context window", "compacted at the one-million-token limit: 18 times in 328 interactive sessions")

c.arrow(model, tools, "flow", "calls")
c.arrow((565, 370), (565, 310), "dependency", "before it acts", label_at=0.5, label_dy=0)
c.arrow((860, 370), (640, 310), "feedback", "after a change", via=((860, 342), (640, 342)), label_at=0.55, label_dy=12)

# Subagents: invoked by the harness, fresh context, in the same checkout.
subs = []
for i, (label, sub) in enumerate([
    ("Subagent", "fresh context: sees the brief, not the parent's transcript"),
    ("Subagent", "own tools; 9 launched per interactive session"),
    ("Subagent", "3,197 runs; 72% of tool calls in the final week"),
]):
    subs.append(c.node(1060, 200 + i * 160, 250, 120, "agent", label, sub))
c.arrow((1010, 260), subs[0], "flow", "delegates", ports=(None, "left"))
c.arrow(subs[2], (1012, 470), "feedback", ports=("left", None), via=((1035, 580), (1035, 470)))
c.text(1026, 508, "returns a report", size=S.SMALL, color=S.BODY, anchor="end")

c.arrow(owner, harness, "authority", "authority boundary", ports=("right", "left"), via=((320, 395),), label_at=0.3, label_dy=-14)

# Measurement key: which trace observes each layer.
key = c.group(40, 780, 1320, 240, "Measurement key · .analysis/data/harness.sqlite, one table per layer")
rows = [
    ("sessions", "645 · the checkout and the session: repo, branch, model, cost"),
    ("turns", "112,082 · the model: tokens per turn, model, compaction"),
    ("tool_calls", "53,457 · tools and permissions: errors, rejections, skill"),
    ("subagent_runs", "3,197 · subagents: type, model, tokens, tool calls"),
    ("limit_events", "150 · account limits: session, weekly, spend, credits"),
]
for i, (label, sub) in enumerate(rows):
    c.node(70 + i * 256, 830, 236, 160, "evidence", label, sub)

S.finish(
    c, id="3.1", name="diagram-03-01-anatomy-of-one-agent",
    caption="The model is the innermost layer; the harness around it decides what it sees and which guides and sensors act on it, subagents start fresh rather than inheriting the parent's context, and the owner sits outside every layer.",
    alt="Nested boxes: account and limits contain the shared checkout, which contains the harness, which holds the model, its tools, guides, sensors and the context window. Three subagents sit inside the checkout beside the harness, which delegates to them and receives reports. The owner stands outside with an authority arrow into the harness. A key beneath names the five harness.sqlite tables that observe each layer.",
    source="Replaces D01 ONE CODING AGENT, PART BY PART and D10 ONE CODING AGENT. Counts from .analysis/data/harness.sqlite: sessions 645, turns 112,082, tool_calls 53,457, subagent_runs 3,197, limit_events 150 (kinds session, weekly, spend, credits). Chapter 3, The harness: subagents made 72% of tool calls in the final week and an interactive session launched nine; Memory across sessions: compaction 18 times in 328 interactive sessions at the one-million-token limit. Guides and sensors after Böckeler as the chapter cites them.",
)
