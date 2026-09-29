"""1.7 The five loops of the software factory, in the words of Chapter 1's opening: direction, production,
delivery, consistency and improvement, around the working change."""
import svg_lib as S

c = S.Canvas(1400, 960)

signals = c.node(340, 40, 250, 60, "plain", "Needs, designs and signals")
running = c.node(1090, 40, 250, 60, "plain", "Running software in production")

factory = c.group(260, 120, 1100, 500, "The factory")

direction = c.group(280, 170, 250, 260, "Direction loop")
people = c.node(300, 210, 210, 74, "person", "People", "guide what gets built")
work = c.node(300, 320, 210, 90, "record", "Authorized work", "work item, goal, plan")

production = c.group(685, 170, 250, 260, "Production loop")
agents = c.node(705, 210, 210, 74, "agent", "Agents", "plan, build, test, record")
change = c.node(705, 320, 210, 90, "record", "The working change", "a change set")

delivery = c.group(1090, 170, 250, 260, "Delivery loop")
review = c.node(1110, 210, 210, 74, "check", "Review and approval check", None)
deployed = c.node(1110, 320, 210, 90, "delivery", "In production", "merged, deployed, observed")

consistency = c.group(280, 480, 655, 110, "Consistency loop · across the fleet")
shared = c.node(300, 516, 615, 56, "policy", "Shared fixes, components and policies", None)

improvement = c.group(260, 690, 1100, 130, "Improvement loop")
changes = c.node(280, 730, 480, 60, "policy", "Changes the factory itself", "guides, checks, skills, template")
measures = c.node(820, 730, 520, 60, "evidence", "Measures waiting, cost, defects and drift", None)

c.arrow((465, 100), (465, 170), "flow", "intent", label_dy=8)
c.arrow(direction, production, "authority", "authorized work")
c.arrow(production, delivery, "flow", "pull request")
c.arrow(delivery, running, "flow")
c.arrow((730, 430), (730, 480), "flow", "a fix made once", label_dy=2)
c.arrow((890, 480), (890, 430), "flow", "to every repository", label_dy=2)
c.arrow((1215, 430), (1215, 730), "feedback", "production evidence", label_at=0.75)
c.arrow(measures, changes, "flow")
c.arrow(changes, factory, "feedback", "changes the factory", via=((150, 760), (150, 370)))

c.legend(280, 850, kinds=("person", "agent", "record", "check", "delivery", "policy", "evidence"),
         arrows=("flow", "authority", "feedback"), cols=5, cell=216)

S.finish(
    c, id="1.7", name="diagram-01-07-five-factory-loops",
    caption="Direction turns signals into authorized work, production and delivery carry the working change into "
            "production, consistency runs across the fleet rather than after delivery, and improvement feeds "
            "production evidence back into the factory itself.",
    alt="Five loops drawn as boxes. Along the top, direction (people and authorized work), production (agents and "
        "the working change) and delivery (review and approval check, then merged, deployed and observed) pass "
        "intent, authorized work and a pull request left to right, with running software leaving at the right. "
        "Below them a consistency loop exchanges shared fixes, components and policies with production. At the "
        "bottom, the improvement loop measures waiting, cost, defects and drift from production evidence and "
        "changes the factory's guides, checks, skills and template.",
    source="D24 THE PIECES OF A FACTORY. Loop names and what each does: Chapter 1, opening ('The factory in this "
           "book can be understood as five linked loops'); object names: the book's vocabulary (work item, goal, "
           "plan, change set, approval check, guides and checks). No counts.",
)
