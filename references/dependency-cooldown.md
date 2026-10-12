# Dependency cooldown: how old a release must be before we adopt it

A release we adopt must be old enough for its tier. The tier is set by the most
severe advisory the release fixes. This file is the one home of the rule.
`wayfare:wayfare-ship-pr` applies it before `@auto-approve` on a Dependabot PR,
and `wayfare:wayfare-audit-security` applies it when it picks a version for a
hand-made fix (an override or a transitive bump).

| Most severe advisory the release fixes | Minimum age at adoption |
| -- | -- |
| Critical, or its CVE is in CISA KEV (exploited in the wild) | 0 days: adopt the same day, even hours old |
| High | 2 days |
| Medium or low | 7 days |
| None (a routine version update) | 7 days, set by dependabot `cooldown` (check CI-15) |

## Why tiers, and why these numbers

A flat 0 days for every advisory lets a fresh, possibly poisoned release in
through any low-severity advisory: the attacker only needs a CVE to ride. A flat
7 days delayed COM-75's critical fixes by a week. Two days for high catches most
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
is 3 days old waits until day 7. The 7-day row for version updates is the only
one Dependabot enforces by itself; every other row is enforced at review.

## Reading the PR

- **Take each version from the diff, never the title.** `@dependabot rebase`
  ignores cooldown and can retarget the PR to a newer release while the title
  keeps the old version. Read the new version from the manifest or lockfile
  lines the diff changes.
- **A grouped PR passes only when every package passes its own tier.** A package
  in the group that fixes no advisory is on the 7-day row, even when the PR is a
  security PR for another package in it.

## Finding the severity

The severity is the advisory's `severity` field, from the PR body or from the
repo's open alerts. A release fixes an alert when the old version is in the
alert's vulnerable range and the new version is at or after its first patched
version:

```bash
gh api "repos/$OWNER/$REPO/dependabot/alerts?state=open&per_page=100" --paginate \
  --jq '.[] | select(.dependency.package.name == "PKG")
        | {sev: .security_advisory.severity, cve: .security_advisory.cve_id,
           range: .security_vulnerability.vulnerable_version_range,
           fixed: .security_vulnerability.first_patched_version.identifier}'
```

When several alerts match, the most severe sets the tier. Look up each CVE in
the CISA KEV catalogue; a listed CVE puts the release on the 0-day row whatever
its severity:

```bash
curl -fsS -o kev.json https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json \
  && jq -e --arg c "CVE_ID" 'any(.vulnerabilities[]; .cveID == $c)' kev.json
```

The download is a separate command because `curl | jq` drops curl's exit status,
and a failed download would then read as "not in KEV".

When neither the PR body nor the alerts call gives a severity (alerts disabled,
token scope), the severity is unknown. Unknown is the 7-day row, never the 0-day
row.

## Measuring the age

Age runs from the registry's publish time, never from the PR's open date. A
release clears its tier on publish time plus the tier's days.

| Ecosystem | Publish time |
| -- | -- |
| npm | `curl -s https://registry.npmjs.org/PKG \| jq -r '.time["VER"]'` |
| Go | `curl -s https://proxy.golang.org/MOD/@v/VER.info \| jq -r .Time` |
| Terraform | `curl -s https://registry.terraform.io/v1/providers/NS/NAME/VER \| jq -r .published_at` |
| PyPI | `curl -s https://pypi.org/pypi/PKG/VER/json \| jq -r '[.urls[].upload_time_iso_8601] \| min'` |
| Actions | `gh api repos/OWNER/ACTION/releases/tags/TAG --jq .published_at` |

Go's `.Time` is the commit time the module's origin reports, which the author
sets. A version that reads older than the proxy has known it for is backdated;
for a Go release near its tier boundary, check when `index.golang.org` first
listed it.

## Two extra checks inside the 7-day window

A release adopted before it is 7 days old (the 0-day and 2-day rows) gets both
checks in review. Either failing is a hold, whatever the severity:

1. **The usual publisher released it.** Compare with the previous version: npm
   `npm view PKG@VER _npmUser maintainers --json`; Go, the `.Origin.URL` in the
   `.info` above; Actions, the release's `.author.login`. A new publisher on a
   days-old release is the shape of a stolen-token publish.
2. **It adds no install-time script.** Diff `npm view PKG@VER scripts --json`
   against the previous version: a new `preinstall`, `install` or `postinstall`
   runs on every developer machine and CI runner the moment the lockfile lands.
   This check is npm's; Go modules and Actions run no install hook.

## Holding

A release too young for its tier is a hold, not a rejection. The hold names each
blocking package, its tier and the date it clears:

```
Release-age hold: PKG@VER (medium, published 2026-10-09) clears on 2026-10-16.
```

Re-run the gate on or after that date. When several packages hold, the PR clears
on the latest of their dates.
