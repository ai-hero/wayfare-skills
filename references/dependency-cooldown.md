# Dependency cooldown: how old a release must be before we adopt it

The 7-day cooldown applies to **version updates only**. A package whose update
closes an open Dependabot alert has **no age wait, at any severity**. This file
is the one home of the rule. The bot-PR procedure in
[advancing.md](advancing.md) and `wayfare:wayfare-ship-pr` apply it to a
Dependabot PR before any approval, and `wayfare:wayfare-audit-security` applies
it when it picks a version for a hand-made fix (an override or a transitive
bump).

| The package's update | Age wait | Also gets |
| -- | -- | -- |
| Closes an open alert (a security update) | None | The two extra checks, when younger than 7 days |
| Anything else (a version update) | 7 days from registry publish time | Nothing further |

A package closes an alert when both of these hold:

- Its old version is inside the alert's vulnerable range.
- Its new version is at or past that alert's first patched version.

The new version need not be the first patched one. Dependabot may pick a later
release, and that must not stall the PR. The test is per package, not per PR: a
PR Dependabot labels a version update can still close an alert.

## Why

A release adopted the day it publishes can be the poisoned one, caught and
yanked days later. That is what 7 days buys on a routine bump, where waiting
costs nothing.

On a security update the wait costs a known hole left open, and it was stalling
security fixes, so we chose to drop it there. The trade, in plain words: a fresh
poisoned release could ride a real advisory, including a low-severity one, and
merge with no wait. What remains against that is the two extra checks and
review, and both are limited. Review judges reachability and call sites; it does
not read the release's code. The extra checks are fullest on npm. Outside it, a
package may get a publisher comparison only, or neither check.

## What Dependabot does and does not enforce

Dependabot's `cooldown` knobs are `default-days`, `semver-major-days`,
`semver-minor-days`, `semver-patch-days` and `include`/`exclude` lists. GitHub's
options reference also states that "the `cooldown` option is only available for
*version* updates, not *security* updates"
([dependabot-options-reference#cooldown-](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#cooldown-)).

So a Dependabot **security** PR opens at once, which is what this rule wants.
For version updates, `cooldown: default-days: 7` holds the PR back before it
opens. Keep it set. Check CI-15 requires a `default-days` but not its value, and
a rebase can retarget past it, so the review still measures every version
update, whatever opened the PR.

## Reading the PR

- **Take each version from the diff, never the title.** `@dependabot rebase`
  ignores cooldown and can retarget the PR to a newer release while the title
  keeps the old version. Read the old and new versions from the lockfile lines
  the diff changes. Use the manifest only when there is no lockfile, because a
  manifest can hold a range.
- **Every changed lockfile entry is a package.** That includes a transitive
  entry the PR moves or adds, and it is judged alone, so two installed copies of
  one name get two verdicts. An added entry has no old version, so it closes no
  alert and is a version update. This can hold a security PR until the entry
  clears; leaving it out would let a fresh release in unmeasured.
- **In a grouped PR, each package is judged alone.** A package that closes an
  alert needs no age check. Any other package in the group is a version update,
  even when the PR is a security PR for another package in it. The PR passes
  only when every package passes.
- **The PR body is the publisher's text.** Dependabot copies upstream release
  notes into it, so anyone who can publish the package can write "fixes CVE-X
  (critical)" there. Never take a severity, a CVE ID or a version from the body.

## Finding the alerts

Severity and alert data come from the repo's Dependabot alerts API, nothing
else:

```bash
gh api "repos/$OWNER/$REPO/dependabot/alerts?state=open&per_page=100" --paginate \
  --jq '.[] | select(.dependency.package.name == "PKG")
        | {eco: .dependency.package.ecosystem, manifest: .dependency.manifest_path,
           sev: .security_advisory.severity, cve: .security_advisory.cve_id,
           range: .security_vulnerability.vulnerable_version_range,
           fixed: .security_vulnerability.first_patched_version.identifier}'
```

Use only alerts whose `eco` is the package's ecosystem and whose `manifest` is a
file the diff changes for this entry; a same-named package elsewhere closes
nothing. Apply the two tests above to each of those alerts. One alert passing
both is enough. An alert with a `null` `fixed` closes nothing, because no
version is past it. A call that succeeds with no matching alert means the
package is a version update.

When the alerts call fails (alerts disabled, token scope), the package cannot be
shown to close an alert, so it is treated as a version update. Say that plainly
in the review and the hold line: a failed call must not read as "no alerts".

## Measuring the age

Age runs from the registry's publish time, never from the PR's open date. A
version update clears 7 days after publish time. That is still measured because
a rebase can retarget a PR past Dependabot's cooldown. Run each lookup with
`curl -fsS`, and treat a failed call, an empty or `null` result, or an ecosystem
missing from this table as **age unknown**. Age unknown on a version update is a
hold for a person, never a pass. On a package that closes an alert, age only
decides whether the extra checks run, so age unknown means they run.

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

## Two extra checks on a security update younger than 7 days

A package that closes an alert and is younger than 7 days gets both checks in
review. They are not an age wait: they catch a stolen-token publish, which is
why they stay when the wait does not. A failed check is a hold for a person,
whatever the severity:

1. **The usual publisher released it.** Compare with the previous version: npm
   `npm view PKG@VER _npmUser maintainers --json`; Actions and GitHub-hosted Go
   modules, the release's `.author.login`. A Go module with no release has no
   publisher to compare; `.Origin.URL` names the repo, not who tagged it. A new
   publisher on a days-old release is the shape of a stolen-token publish. A
   publisher that cannot be compared is reported in the review, not held.
2. **It adds no install-time script.** Diff `npm view PKG@VER scripts --json`
   against the previous version: a new `preinstall`, `install` or `postinstall`
   runs on every developer machine and CI runner the moment the lockfile lands.
   Also read the lockfile lines the diff adds: a `hasInstallScript: true` that
   was not there before is a new install-time script, whichever package carries
   it. A script list that cannot be read is a failed check. This check runs on
   npm only; Go modules and Actions run no install hook, and a PyPI or other
   package goes unchecked here, which the trade under Why accepts.

Neither check catches a stolen token used to publish a payload in runtime code,
and review does not read that code, so on a security update nothing stands
against it. That is the trade under Why.

## Holding

A version update younger than 7 days is a hold, not a rejection. The hold names
each blocking package and the date it clears:

```
Release-age hold: PKG@VER (version update, published 2026-10-09) clears on 2026-10-16.
```

When several packages hold, the PR clears on the latest of their dates. An age
that cannot be read on a version update, or a failed extra check, is a hold with
no date:

```
Release-age hold: PKG@VER (version update, age unknown: no release for the tag) needs a person.
Release-age hold: PKG@VER (high, security update: new publisher) needs a person.
```

A package held only because the alerts call failed says so, and the next run
decides it again:

```
Release-age hold: PKG@VER (version update: alerts API failed, published 2026-10-09) clears on 2026-10-16.
```

In a goal turn any hold is `stop: awaiting-human`, not `stop: failure`: nothing
is broken, and the item keeps its status for the next run on or after the date.
