# The setup.yaml standard

What a fleet's machine setup file must be, why, and how a new machine gets from
nothing to running it. `scripts/fleet-setup.py` reads it, and
`wayfare:wayfare-setup-dev` walks it when run from the fleet root.

## The principle

Every developer in a fleet needs the same machine: the same CLIs, the same
Claude Code plugins and MCP servers at the same pinned versions, the same shell
lines. That setup used to be a hand-written runbook in one repo, which an agent
read and re-typed, step by step, a little differently each time.

It is now data: **`.fleet/setup.yaml`**, in the register repo beside
`.fleet/FLEET.md` ([FLEET-MD.md](./FLEET-MD.md)). It is versioned and reviewed
with the register, so a change reaches every machine the next time setup runs,
and a script, not an agent, decides what is present and what is missing.

It holds **machine-level setup only**. A step one repo needs (its `.env`, its
dev stack, the Node major in its `.nvmrc`, its dev certificate) stays in that
repo's `HERO.md`, under `## Developer Setup` and `## Projects`, which
`wayfare-setup-dev` already reads per repo. That is the rule `FLEET.md` follows
too: a fact a repo depends on lives in that repo. `setup.yaml` never names a
repo.

**Who can steer it.** `setup.yaml` names commands that run on every developer's
machine, as that developer. Whoever can merge to the register can therefore run
code on those machines, the same people who can already change `checkers.py`.
The register's review is the gate, and the script enforces it:

- It reads `setup.yaml` from `refs/remotes/origin/main` of the register checkout
  `.fleet/`, fetched that run, by the full ref name, because a local branch or
  tag called `origin/main` would win over the short name. **Never the working
  tree**: unlike the map, a local edit to `setup.yaml` does nothing until it is
  merged and fetched, so a branch checked out to review a register PR cannot
  choose what gets installed.

- It runs only when the checkout's `origin` is the register this machine pins
  (`${XDG_CONFIG_HOME:-~/.config}/wayfare/registers`,
  [FLEET-MD.md](./FLEET-MD.md)), compared with the same normaliser as the audit.
  A fork or a look-alike remote is refused, and so is an unpinned register.

- It refuses a `setup.yaml` that is a symlink, which git would review as the
  link while the commands came from wherever it points.

- It reads with `GIT_NO_REPLACE_OBJECTS=1` and no inherited `GIT_*`, so a
  fetched `refs/replace/*` cannot swap the blob behind the reviewed commit.

- `plan` prints the commit it read, and `apply` takes it back as `--at SHA`. If
  origin/main has moved by the time `apply` fetches, it refuses, so nothing runs
  that the person was not shown.

`--file` reads a working-tree file instead, for someone editing the file or a
test. Only `validate` runs nothing from the file. `plan`, `check` and `verify`
run its person-step checks and `verify` commands, and `apply` runs its installs,
so all four refuse `--file` unless `--unreviewed` is passed too. The skill never
passes either. On top of the gate, the skill shows each group's commands and
asks before running them.

## Bootstrap: before wayfare is on the machine

The skill cannot install itself, so a person does these first, in a terminal, on
a clean Mac:

1. Install the command-line tools and wait for the installer to finish:
   `xcode-select -p >/dev/null 2>&1 || xcode-select --install`.
2. Install Homebrew from [brew.sh](https://brew.sh), then add
   `eval "$(/opt/homebrew/bin/brew shellenv)"` to `~/.zprofile` and run it.
3. `brew install gh uv`, then `gh auth login` and `gh auth setup-git`. The setup
   script runs through `uv`.
4. Put `~/.local/bin` on `PATH` in `~/.zshrc`
   (`export PATH="$HOME/.local/bin:$PATH"`), then install Claude Code:
   `curl -fsSL https://claude.ai/install.sh | bash`.
5. `claude plugin marketplace add ai-hero/wayfare-skills`, then
   `claude plugin install wayfare@wayfare`.
6. Make the workspace and clone the register into it as `.fleet/`:
   `mkdir -p ~/workspaces/acme && gh repo clone acme-inc/fleet-register ~/workspaces/acme/.fleet`.
7. Pin the register on this machine, as in [FLEET-MD.md](./FLEET-MD.md)'s new
   machine steps. Fleet mode runs commands from `setup.yaml`, so it refuses a
   register that is not pinned.
8. Start `claude` in the workspace and run `wayfare:wayfare-setup-dev`.

The first group of a fleet's `setup.yaml` usually repeats these steps, so a
machine that skipped one is told, and the rest show as present.

## The file format

`assets/fleet/setup.example.yaml` is a commented example that validates. The top
level:

| Key | Required | Meaning |
| -- | -- | -- |
| `version` | yes | `1`, as an integer. A file of any other version is refused |
| `platform` | yes | `macos-arm64` (Apple Silicon macOS), the only platform so far. `apply` refuses to run on another |
| `workspace` | yes | where the fleet root lives on a new machine, absolute or `~/…` |
| `notes` | no | lines shown once, before the plan |
| `groups` | yes | the setup, in the order it runs |
| `verify` | no | checks run at the end |

A **group** is `name` (lowercase, digits, `-`; unique), `title`, `steps`, and
optionally `notes` (shown when the group is reached, for a licence warning or a
caveat), `optional: true` and `ask`. An optional group carries the question the
skill asks once, and runs only on a yes; a required group never has `ask`.

A **step** is a mapping with exactly one key, its kind:

| Kind | Value | Present when | Runs |
| -- | -- | -- | -- |
| `brew` | list of formulae, each a name or a [floor](#version-floors) | `brew list --formula` has it (a tap formula by its short name) | `brew install NAME` |
| `cask` | list of casks, each a name or a floor | `brew list --cask` has it | `brew install --cask NAME` |
| `pipx` | list of packages, each a name or a floor | `pipx list --short` has it | `pipx install NAME` |
| `installer` | `name`, `check`, `run` | the command `check` is on `PATH` | `run`, by bash, then `check` again |
| `git` | map of key to string value | `git config --global --get KEY` equals it | `git config --global KEY VALUE` |
| `shell` | `file`, `lines` | the file has the line, exactly | appends the line |
| `path` | `file`, `entries` | the file has `export PATH="ENTRY:$PATH"` | appends that line |
| `marketplace` | list of `name`, `source` | `claude plugin marketplace list` has `name` | `claude plugin marketplace add SOURCE` |
| `plugin` | list of `NAME@MARKETPLACE` | `claude plugin list` has it | `claude plugin install ID` |
| `mcp` | one server (below) | `claude mcp get NAME` exits 0 | `claude mcp add --scope user …` |
| `person` | `title`, `why`, `check`, optional `run`, `terminal` | `check` exits 0, or the person confirmed it | never; the skill stops and shows it |

Rules the validator enforces, each because getting it wrong would install
something other than what the file says:

1. **An unknown key is an error, at every level.** `checks:` for `check:` would
   otherwise drop the presence check without a word, and an unknown step kind
   would drop the whole step.
2. **Values are typed.** A git value is a string, so `pull.rebase: "false"` is
   quoted; YAML reads a bare `false` as a boolean.
3. **`shell` and `path` write only shell startup files**: `~/.zshrc`,
   `~/.zprofile`, `~/.zshenv`, `~/.bashrc`, `~/.bash_profile` or `~/.profile`.
   Anything else under `~/`, such as `~/.ssh/authorized_keys`, is refused.
4. **A `path` entry is `$HOME/…` or an absolute path**, of letters, digits and
   `._@+-` only. It is written inside double quotes, where `"`, `` ` ``, `$(` or
   `\` would run as shell at every login, and where a leading `~` is not
   expanded, so it would name a folder literally called `~`.
5. **A `plugin` names a marketplace an earlier `marketplace` step declared.**
6. **A stdio `mcp` server run through `npx`, `bunx`, `pnpx` or `uvx` names exact
   versions**: a full `MAJOR.MINOR.PATCH`, with an optional prerelease or build
   suffix (`@playwright/mcp@0.0.83`, `pkg==1.2.3`), never bare, `@latest`, `@1`
   or `@1.x`, which npm reads as ranges. Every value of `--package`, `-p`,
   `--from` and `--with` is checked, and the first positional argument when none
   of those is given. Those launchers fetch the package each run with the
   person's credentials in reach, and an unpinned one skips the cooldown on new
   releases.
7. **A `person` step has a `check`**, so it can read as done; without one every
   later `apply` would stop at it again. One whose `why` is `secret` runs in a
   separate terminal (`terminal: separate`).
8. **An http header's `prefix`** is letters, digits, spaces and `._-` only.
9. **A version floor's `min` is quoted digits and dots** (`"2026.10.2"`), and
   comes with a `why`. Unquoted, YAML reads `2026.10` as a number.

### Version floors

A `brew`, `cask` or `pipx` item is a name, or a mapping that also sets the
lowest version the fleet accepts:

```yaml
- brew:
    - just
    - name: cloudflared
      min: "2026.10.2"
      why: earlier releases trust the compromised eMudhra intermediates
      command: cloudflared   # optional; the default is the short name
```

Presence is checked as before. A present item with a floor runs
`COMMAND --version` and reads the first dotted number, so what is measured is
the binary on `PATH`, the one that runs. A copy outside the package manager,
earlier on `PATH`, is what an advisory's upgrade most often misses. When the
command is not on `PATH` (a cask app, say), the version comes from
`brew list --versions` or `pipx list --short`. Versions compare as numbers, so
`2026.10.10` is above `2026.10.2`. A version that cannot be read counts as below
the floor.

Below the floor, the entry's status is `outdated` (`[update]` in the plan). The
plan shows the installed version, where it was read, the floor and the `why`.
`check` exits 1 for it, even in an optional group, because a floor is a security
fix for a tool already in use. `apply` runs `brew upgrade NAME`,
`brew upgrade --cask NAME` or `pipx upgrade NAME`, then reads the version again.
If the copy on `PATH` is still old, it fails and names that copy.

`why` is one of `password`, `browser`, `secret`, `gui` or `choice` (a value only
the person can give, such as their commit email). `path` entries are also put on
the script's own `PATH` for its checks, so a tool installed into `~/.local/bin`
is found in the same run.

### MCP servers

```yaml
- mcp:
    name: context7
    transport: stdio            # or http
    command: npx                # stdio only
    args: [-y, "@upstash/context7-mcp@4.4.4"]
    secrets: [CONTEXT7_API_KEY] # names only
- mcp:
    name: vanta
    transport: http
    url: https://mcp.vanta.com/mcp   # https only
    secrets:                         # http: a header filled from a variable
      - {header: Authorization, env: VANTA_TOKEN, prefix: "Bearer "}
```

Servers are added at user scope; a project's own server belongs in that repo.

**Secrets are declared by name and never stored.** The file has no field that
can hold a value. A server with `secrets` becomes a person step that runs in a
separate terminal: the script prints a block that reads each value with
`read -rs`, passes it to `claude mcp add` through the variable, and unsets it.
The server name comes before `-e`, because `-e` takes every value after it. The
value goes from the person's keyboard to Claude Code's config and never through
the agent, the script's output, or shell history.

### Verify

```yaml
verify:
  - name: github sign-in
    run: gh auth status
    passes: gh holds a valid github.com token
```

Each check passes or fails by exit status. Its output is discarded, never shown,
because a check such as `claude mcp list` prints stored keys. `passes` says what
a pass means, for the report.

## The script

```bash
uv run scripts/fleet-setup.py --fleet FLEET_ROOT validate
uv run scripts/fleet-setup.py --fleet FLEET_ROOT plan [--json]
uv run scripts/fleet-setup.py --fleet FLEET_ROOT check [--json]
uv run scripts/fleet-setup.py --fleet FLEET_ROOT apply --group NAME --at SHA [--confirmed ID]...
uv run scripts/fleet-setup.py --fleet FLEET_ROOT verify [--json]
uv run scripts/fleet-setup.py --file setup.yaml validate          # an edit, before its PR
uv run scripts/fleet-setup.py --file setup.yaml --unreviewed plan # runs its checks
uv run scripts/fleet-setup.py archive --kind local|memory ARCHIVE [--extract DEST]
```

`--fleet` defaults to the current folder. Every command but `archive` goes
through the gate above first; a refusal prints `GATE CODE: why` and exits 3, and
a register with no `setup.yaml` on `origin/main` exits 4 (`NO_SETUP_YAML`).

`plan` prints the reviewed commit and lists every entry in file order with an
id, its status (`present`, `missing`, `outdated`, `person`) and the command it
would run. The id is `GROUP.KIND:KEY`, where the key is what the entry is (a
formula, a server name, a git key, or a short hash of a shell line or a person
step's title and check), so an edit that adds a step does not move another's id,
and the same step twice in one group is invalid. `check` is the plan plus
`verify`, and exits 1 while a required step is open or a check fails. Neither
installs anything; both run the file's check commands.

`apply` needs `--at SHA` from `plan` (exit 3, `GATE MOVED`, when origin/main has
moved since). It runs one group's missing entries in file order and stops at the
first person step still open (exit 10), printing the step and the command. Once
the person has done it, run `apply` again with `--confirmed ID`; everything
already present is skipped, so a rerun is safe. A failing command stops the
group with exit 1 and quotes the last lines of its output, and says when a
command timed out or could not start. Invalid files, wrong platforms and usage
errors exit 2.

`archive` checks an archive from an old machine before anything is unpacked: a
`local` one may hold only `NAME/.plans/…`, `NAME/.env` and a top-level
`FLEET.md`; a `memory` one only `.claude/projects/PROJECT/memory/…`. Both hold
only plain files and folders, with relative names and no `..`. Any other member
is printed as `REFUSED` and the command exits 1, and so is an archive with
unreadable data after its last member: another tar reader could find members
there that this one never checked. With `--extract DEST`, an archive that passes
is unpacked from that same parse, with Python's `data` filter, and a file
already at its path is kept, never overwritten. Never unpack one with `tar`.
