# Dependency cooldown: how old a release must be before we adopt it

A release we adopt must be old enough for its tier. The tier is set by the most
severe advisory the release fixes. This file is the one home of the rule. The
bot-PR procedure in [advancing.md](advancing.md) and `wayfare:wayfare-ship-pr`
apply it to a Dependabot PR before any approval, and
`wayfare:wayfare-audit-security` applies it when it picks a version for a
hand-made fix (an override or a transitive bump).

| Most severe advisory the release fixes | Minimum age at adoption |
| -- | -- |
| Critical, or its CVE is in CISA KEV (exploited in the wild) | 0 days: adopt the same day, even hours old |
| High | 2 days |
| Medium or low | 7 days |
| None (a routine version update) | 7 days |

## Why tiers, and why these numbers

A flat 0 days for every advisory lets a fresh, possibly poisoned release in
through any low-severity advisory: the attacker only needs a CVE to ride. A flat
7 days held back a critical fix for a full week. Two days for high catches most
malicious or broken releases, which are usually yanked within hours, and stays
well inside Vanta's remediation SLA for high.

## What Dependabot does and does not enforce

Dependabot's `cooldown` cannot be tiered by severity. Its only knobs are
`default-days`, `semver-major-days`, `semver-minor-days`, `semver-patch-days`
and `include`/`exclude` lists. GitHub's options reference also states that "the
`cooldown` option is only available for *version* updates, not *security*
updates"
([dependabot-options-reference#cooldown-](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#cooldown-)).

So a Dependabot **security** PR opens at once for every severity, and the tier
decides when we **merge** it. A medium-severity security PR for a release that
is 3 days old waits until day 7. For version updates,
`cooldown: default-days: 7` holds the PR back before it opens; check CI-15
requires a `default-days` but not its value, so the review still measures every
release, whatever opened the PR.

## Reading the PR

- **Take each version from the diff, never the title.** `@dependabot rebase`
  ignores cooldown and can retarget the PR to a newer release while the title
  keeps the old version. Read the new version from the manifest or lockfile
  lines the diff changes.
- **A grouped PR passes only when every package passes its own tier.** A package
  in the group that fixes no advisory is on the 7-day row, even when the PR is a
  security PR for another package in it.
- **The PR body is the publisher's text.** Dependabot copies upstream release
  notes into it, so anyone who can publish the package can write "fixes CVE-X
  (critical)" there. Never take a severity, a CVE ID or a version from the body.

## Finding the tier

Severity and CVE IDs come from the repo's Dependabot alerts, nothing else:

```bash
gh api "repos/$OWNER/$REPO/dependabot/alerts?state=open&per_page=100" --paginate \
  --jq '.[] | select(.dependency.package.name == "PKG")
        | {sev: .security_advisory.severity, cve: .security_advisory.cve_id,
           range: .security_vulnerability.vulnerable_version_range,
           fixed: .security_vulnerability.first_patched_version.identifier}'
```

An alert sets the tier of exactly one release: its `fixed` version, when the old
version is inside its `range`. A later release, even one published an hour after
the fix, is on the row of the advisories it fixes itself, usually the 7-day row.
That stops a poisoned release from riding a real fix onto the 0-day row. When
several alerts give the same release a tier, the most severe sets it.

Look up each CVE ID in CISA KEV; a listed CVE puts its fixed release on the
0-day row whatever its severity. Check the ID against `^CVE-[0-9]{4}-[0-9]+$`
before it reaches a shell command, and download the feed to a temporary file:

```bash
KEV=$(mktemp) \
  && curl -fsS -o "$KEV" https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json \
  && jq --arg c "$CVE" 'any(.vulnerabilities[]; .cveID == $c)' "$KEV"
```

This prints `true` or `false`. Any other result, or a failed download, means KEV
status is unknown. `curl | jq` would drop curl's exit status and turn a failed
download into "not listed", which is why the download is its own command.

When the alerts call fails (alerts disabled, token scope), the tier is unknown.
Unknown is the 7-day row, never a faster one.

## Measuring the age

Age runs from the registry's publish time, never from the PR's open date. A
release clears its tier on publish time plus the tier's days. Run each lookup
with `curl -fsS`, and treat a failed call, an empty or `null` result, or an
ecosystem missing from this table as **age unknown**, which is a hold for a
person, never a pass.

| Ecosystem | Publish time |
| -- | -- |
| npm | `registry.npmjs.org/PKG`, `.time["VER"]` |
| PyPI | `pypi.org/pypi/PKG/VER/json`, the latest `.urls[].upload_time_iso_8601` |
| Go | `proxy.golang.org/MOD/@v/VER.info`, `.Time` (see below) |
| Terraform provider | `registry.terraform.io/v1/providers/NS/NAME/VER`, `.published_at` |
| Terraform module | `registry.terraform.io/v1/modules/NS/NAME/PROVIDER/VER`, `.published_at` |
| Actions | `gh api repos/OWNER/ACTION/releases/tags/TAG`, `.published_at` |
| Docker Hub image | `hub.docker.com/v2/repositories/NS/REPO/tags/TAG`, `.tag_last_pushed` |

The traps in that table:

- **PyPI takes the latest upload, not the first.** A version accepts new files
  after its first upload, so a wheel added today would inherit the version's old
  date.
- **Go's `.Time` is the commit time, which the author sets**, and
  `index.golang.org` has no per-module lookup. Encode each uppercase letter in
  `MOD` as `!` plus its lowercase. For a GitHub-hosted module, also read that
  repo's release `published_at` for the tag, which GitHub sets, and take the
  later of the two. With no release, the age is author-reported: say so in the
  review.
- **An Actions pin with no GitHub release for its tag is age unknown.**
- **A Docker digest bump is measured only when the PR's digest is the tag's
  current `.digest`.** Otherwise, and for any registry other than Docker Hub,
  the age is unknown.

## Two extra checks inside the 7-day window

A release adopted before it is 7 days old (the 0-day and 2-day rows) gets both
checks in review. Either failing is a hold for a person, whatever the severity:

1. **The usual publisher released it.** Compare with the previous version: npm
   `npm view PKG@VER _npmUser maintainers --json`; Actions and GitHub-hosted Go
   modules, the release's `.author.login`. A Go module with no release has no
   publisher to compare; `.Origin.URL` names the repo, not who tagged it. A new
   publisher on a days-old release is the shape of a stolen-token publish.
2. **It adds no install-time script.** Diff `npm view PKG@VER scripts --json`
   against the previous version: a new `preinstall`, `install` or `postinstall`
   runs on every developer machine and CI runner the moment the lockfile lands.
   This check is npm's; Go modules and Actions run no install hook.

Neither check catches a stolen token used to publish a payload in runtime code.
That is what the days are for.

## Holding

A release too young for its tier is a hold, not a rejection. The hold names each
blocking package, its tier and the date it clears:

```
Release-age hold: PKG@VER (medium, published 2026-10-09) clears on 2026-10-16.
```

When several packages hold, the PR clears on the latest of their dates. An age
that cannot be read, or a failed extra check, is a hold with no date:

```
Release-age hold: PKG@VER (high, age unknown: no release for the tag) needs a person.
```

In a goal turn either hold is `stop: awaiting-human`, not `stop: failure`:
nothing is broken, and the item keeps its status for the next run on or after
the date.
