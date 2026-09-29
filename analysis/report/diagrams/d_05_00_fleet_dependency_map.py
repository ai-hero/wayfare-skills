"""Figure 5.1: the fleet as a directed network, grouped by repository type, one edge per dependency kind."""
import svg_lib as S

c = S.Canvas(1400, 1120)

# The plugin sits above the fleet: its process dependency is the boundary every other repository is inside.
plugin = c.node(40, 40, 420, 96, "agent", "wayfare-skills",
                "process plugin, since Mar · skills, auto-approve workflow, register baseline")
c.text(500, 46, "Process dependency", size=S.LABEL, weight=500, color=S.INK)
c.text(500, 78, "Every repository below runs the plugin's skills (HERO.md in all 15) and calls its approval "
                "workflow at @main (14 of 15). The register audits 13; hiro and saga are outside it.",
       size=S.SMALL, color=S.BODY, width=850)

fleet = c.group(40, 200, 1320, 880,
                "The fleet · FLEET.md maps 12 of 15 study repos correctly; hiro and saga have no row; the plugin's row is under its old name")
c.arrow(plugin, (250, 200), "authority", "process", ports=("bottom", None))

# Row 1: template, shared services, infrastructure.
tg = c.group(60, 250, 360, 150, "Template")
template = c.node(80, 292, 320, 84, "record", "hero-template", "cloned to start a project · since Jul")

sg = c.group(460, 250, 480, 150, "Shared services")
auth = c.node(480, 292, 170, 84, "agent", "auth", "identity · since Apr")
ds = c.node(730, 292, 190, 84, "agent", "design-system", "registry · since Jul")
c.arrow((650, 318), (730, 318), "dependency", "registry", label_dy=-12)
c.arrow((730, 352), (650, 352), "dependency", "sign-in", label_dy=14)

ig = c.group(980, 250, 360, 360, "Infrastructure")
root = c.node(1000, 292, 320, 84, "record", "infrastructure-root", "since May 2025")
envs = c.node(1000, 476, 320, 100, "record", "infrastructure-environments", "app_<name>.tf · since Jul")
c.arrow(root, envs, "dependency", "provisions its workspaces", ports=("bottom", "top"))

# Row 2: applications, clones on the left under the template, older products on the right.
ag = c.group(60, 680, 1280, 380, "Applications")
cg = c.group(80, 720, 800, 320, "Cloned from hero-template · 6")
clones = [("elevate-commons", "Jul"), ("aihero-wayfare", "Jul"), ("aihero-steadfast", "Sep"),
          ("ah-cozy", "Aug · no features yet"), ("aihero-dokyu", "Aug · no features yet"),
          ("aihero-mehr", "Aug · no features yet")]
for i, (name, sub) in enumerate(clones):
    x, y = 100 + (i % 3) * 260, 760 + (i // 3) * 130
    c.node(x, y, 240, 96, "agent", name, f"clone · since {sub}")

pg = c.group(920, 720, 400, 320, "Products before the template · 3")
c.node(940, 760, 360, 76, "agent", "website", "product · since May")
c.node(940, 850, 360, 76, "agent", "hiro", "product, winding down · since Apr · no FLEET.md row")
c.node(940, 940, 360, 76, "agent", "saga", "stopped Aug · sign-in only: no registry, no infra · no FLEET.md row")

# Edges from the shared layers to the applications. Group-level, with the consumer count on each.
c.arrow(template, (240, 720), "flow", "template · copied once · 6 clones", ports=("bottom", None), via=((240, 376),),
        label_at=0.55)
c.arrow(auth, (565, 680), "dependency", "runtime · sign-in · 10 apps + template", ports=("bottom", None),
        label_at=0.35)
c.arrow(ds, (825, 680), "dependency", "design · registry · 9 apps + template", ports=("bottom", None),
        label_at=0.65)
c.arrow(envs, (1160, 680), "dependency", "delivery · defines 10 apps, not saga", ports=("bottom", None), label_at=0.5)
c.arrow(envs, sg, "dependency", "delivery", ports=("left", "right"), via=((960, 526), (960, 325)), label_at=0.5)

c.legend(60, 1088, arrows=("flow", "authority", "dependency"), cols=4, cell=300)

S.finish(
    c, id="5.1", name="figure-05-01-fleet-dependency-map", kind="figure",
    caption="Every application hangs off the same four shared layers, so a failure in any one of them reaches "
            "most of the fleet at once; the template's dependency is the only one that stops at the copy.",
    alt="A network of the fleet's fifteen repositories grouped into plugin, template, shared services, "
        "infrastructure and applications, with arrows for process, template, runtime, design and delivery "
        "dependencies; the plugin's process dependency encloses every other repository.",
    source="Replaces D16 THE FLEET. Roster, roles and first commits: .analysis/data/git.sqlite repos. Groups: "
           "~/workspaces/aihero/FLEET.md and ingest/fleet.py categories. Sign-in (10), registry (9) and infrastructure "
           "(10) consumers: Q shared-service-deps grid (report/fleet/data.py), September 2026; hero-template's sign-in "
           "and registry links: git grep of its mirror. Auto-approve callers at @main (14 of 15) and HERO.md presence "
           "(15 of 15): .analysis/data/mirrors. Register scope (13 repos): knowledge.check_results as of 21 Sep. Map "
           "accuracy (12 of 15, hiro and saga missing, plugin under its old name): Q fleet-map-accuracy. "
           "infrastructure-root provisions infrastructure-environments' workspaces: its README.",
)
