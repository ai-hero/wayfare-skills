"""4.3 From merged change to running application: the platform's path for the four launched apps, the evidence it
leaves, and the three things that can follow a failure."""
import svg_lib as S

c = S.Canvas(1400, 840)

# Row 1: from pull request to image.
pr = c.node(80, 80, 200, 110, "record", "Pull request", "reviewed; CI green")
approve = c.node(340, 80, 220, 110, "check", "Auto-approve", "refuses a red CI; branch protection requires no check")
merged = c.node(620, 80, 200, 110, "record", "Merged to main", "squash: one commit per PR")
build = c.node(880, 80, 220, 110, "check", "Build", "tests and lint, then push the image tagged by commit")
registry = c.node(1160, 80, 200, 110, "record", "Image registry", "Docker Hub")
c.arrow(pr, approve, "flow")
c.arrow(approve, merged, "flow")
c.arrow(merged, build, "flow", "on push")
c.arrow(build, registry, "flow")

# Row 2: the shared deploy and the host.
owner = c.node(80, 290, 240, 130, "person", "Owner", "sets the HCP, Docker Hub and Cloudflare tokens; started 7 of 358 deploys by hand")
deploy = c.node(760, 270, 340, 170, "policy", "deploy-swarm",
                "one shared workflow called by each app: reads HCP outputs, SSH through the Cloudflare Tunnel, "
                "docker stack deploy, waits for /readyz")
host = c.node(1160, 300, 200, 110, "delivery", "Droplet", "Docker Swarm; 4 launched apps")
c.arrow(build, deploy, "flow", "workflow_run", ports=("bottom", "top"), via=((990, 250), (930, 250)), label_at=0.3, label_dy=-14)
c.arrow(registry, host, "dependency", "pulls the image", ports=("bottom", "top"))
c.arrow(deploy, host, "flow")
c.arrow(owner, deploy, "authority", "tokens and keys as repo secrets, by hand")

# Row 3: what the host reports.
health = c.node(1160, 510, 200, 130, "check", "Health check", "every 6 h, /readyz asserts each dependency; 33 of 799 failed")
evidence = c.node(720, 520, 380, 110, "evidence", "Evidence", "the deploy run and image tag, the health result; "
                  "median 7 min from merge to production")
c.arrow(host, health, "flow", "GET /readyz")
c.arrow(health, evidence, "flow")
c.arrow(deploy, evidence, "flow", "36 of 394 failed", via=((930, 470), (910, 470)), ports=("bottom", "top"),
        label_dy=-14)

# Row 4: after a failure.
fixf = c.node(400, 700, 300, 100, "record", "Fix forward", "30 later app commits, 6 fixes to the shared workflow; median 29 h")
rollback = c.node(760, 700, 240, 100, "delivery", "Rollback", "redeploy a previous tag by hand; never used", target=True)
diagnose = c.node(1060, 700, 300, 100, "agent", "Diagnose", "read-only facts, posted as a work item; no direct patch",
                  target=True)
c.arrow(evidence, fixf, "flow", "a failed deploy or a failed check", via=((910, 665), (550, 665)), ports=("bottom", "top"),
        label_at=0.6)
c.arrow(evidence, rollback, "flow", target=True, via=((910, 665), (880, 665)), ports=("bottom", "top"))
c.arrow(evidence, diagnose, "flow", target=True, via=((910, 665), (1210, 665)), ports=("bottom", "top"))
c.arrow(fixf, pr, "feedback", "through the same path", via=((50, 750), (50, 135)), ports=("left", "left"), label_at=0.17)

c.legend(60, 810, arrows=("flow", "authority", "dependency", "feedback"), target=True, cols=5, cell=250)

S.finish(
    c, id="4.3", name="diagram-04-03-merge-to-running-application",
    caption="A merge builds an image and one shared workflow deploys it to the droplet in a median seven minutes, but "
            "a green deploy and a healthy service are two different results, and every failure so far was fixed "
            "forward: rollback exists and was never used.",
    alt="Flow diagram in four rows. A pull request passes auto-approve, merges, is built and pushed to Docker Hub. "
        "The build triggers the shared deploy-swarm workflow, which the owner supplies with tokens by hand; it "
        "deploys to a Docker Swarm droplet that pulls the image. A scheduled health check probes the droplet and, "
        "with the deploy run, forms the evidence. From the evidence three branches follow a failure: fix forward "
        "(solid, looping back to a new pull request), rollback and diagnose (both dashed).",
    source="Replaces D07 FROM A MERGED CHANGE TO A RUNNING APP. Mechanism: auth, design-system, elevate-commons and "
           "website .github/workflows (build, deploy thin caller) and infrastructure-environments "
           "deploy-swarm.yaml and health-check-app.yml, read 28 Sep 2026; github.sqlite ci_runs shows the deploy "
           "workflows run on push and workflow_run and the health check on schedule. 4 launched apps deploy on "
           "merge: Q deploy-on-merge. Median 7 min merge to production, 7 of 358 successful deploys started by "
           "hand: Q merge-to-production. 36 of 394 deploys failed, 30 cleared by a later app commit and 6 by a fix "
           "to the shared workflow, median 29 h, no revert: Q deploy-failures. 33 of 799 health runs failed: Q "
           "production-uptime. No required status check on the Terraform-managed repos; auto-approve's CI gate "
           "blocks a red check since 29 Aug: Q never-failed-checks. Rollback is the dispatch path in deploy.yaml "
           "with no instance in the record; diagnose is Chapter 4's proposal (one failed run of Diagnose "
           "Production in ci_runs).",
)
