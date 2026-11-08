# Fleet mode: set up a whole machine from the fleet root

Read this in full when `wayfare-setup-dev` runs at a fleet root, the folder
holding the register checkout `.fleet/` ([FLEET-MD.md](../../docs/FLEET-MD.md)).
It sets up the machine from `.fleet/setup.yaml`
([SETUP-YAML.md](../../docs/SETUP-YAML.md)), clones the repos the person picks,
restores their local-only files from an old machine, and then runs the per-repo
procedure in [SKILL.md](SKILL.md) in each one.

## Rules

- **The script decides what is present.** Never re-derive a step's status by
  hand, and never run a step's command yourself when `apply` can run it: `apply`
  checks first, so a rerun is safe, and your own copy of the command is not.
- **Stop at every person step.** Show the exact command and wait. In a step
  whose terminal is `session`, the person can run it here by typing `! COMMAND`.
  A step whose terminal is `separate` takes a secret, and runs in another
  terminal window, never in this session.
- **Never ask for, print, log or commit a secret.** That covers `.env` values,
  tokens, keys, and anything in `~/.claude.json`, `~/.zsh_history`, `~/.aws` or
  `~/.ssh`. Never open a `.env` file or run `claude mcp get`, which prints a
  server's keys. If the person pastes a secret into the chat, tell them to
  rotate it.
- **Ask once per optional group**, with the group's `ask`, and once before
  running each required group's commands, because they come from the register
  and run as the person.
- **Report failures as failures.** Quote the error, do not mark the step done,
  and do not switch to another package or installer without saying so.

## Instructions

### Step 1: Find the setup file

```bash
FLEET_ROOT=$(pwd -P)
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
command -v uv >/dev/null || echo "NO_UV"
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" --fleet "$FLEET_ROOT" validate
```

The script reads `setup.yaml` only from the register as it stands on
`refs/remotes/origin/main`, fetched this run, and only when the register's
`origin` is the one this machine pins. It never reads the working tree, so a
branch checked out to review a register PR, an unpushed edit, or a cloned fork
cannot choose what gets installed. Never pass `--file` or `--unreviewed` from
this skill. Read what it printed, in this order:

- `NO_UV`: the script runs through `uv`. Tell the person to run
  `brew install uv`, then start again.

- `GATE NO_SETUP_YAML` (exit 4): the register has no machine setup yet. Say so,
  point at `docs/SETUP-YAML.md` and `assets/fleet/setup.example.yaml` in the
  plugin, and go straight to Step 4: the repos and the restore do not need it.
  Writing the file is a register PR, never this skill's.

- Any other `GATE` line (exit 3): stop and quote it. `NO_PIN` means this machine
  has not pinned the register: show the pin step from
  `wayfare:wayfare-sync-fleet` (its `UNPINNED` case) and run nothing.
  `PIN_MISMATCH`, `NO_ORIGIN`, `NO_FETCH`, `SYMLINK` and `NOT_A_FILE` are
  findings for the person; never work around one.

- A validation error (exit 2): quote every `invalid:` line and stop. A typo in
  the register must not silently drop a step, so never run a partial plan.

### Step 2: Show the plan

```bash
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" --fleet "$FLEET_ROOT" plan
```

Show the person the plan as printed: the notes, each group with its `[ok]`,
`[todo]` and `[person]` entries, and the summary line. If the platform line says
`MISMATCH`, stop: the file is for another kind of machine.

**With `--check`, change nothing.** Run `check` instead of `plan`, then Step 4's
`--review` listing, Step 7's archive and exclude checks, and the per-repo
`--check` in each cloned repo the person picks. Report and stop.

```bash
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" --fleet "$FLEET_ROOT" check
```

### Step 3: Walk the groups

Take the groups in plan order. For each one:

1. Show its notes, such as a licence warning, before anything runs.

2. If it is optional, ask its `ask` question once. On no, skip the group and
   record it as declined.

3. If it is required and has `[todo]` entries, list their commands and ask once
   to run them. On no, record the group as skipped and go on.

4. Run the group:

   ```bash
   uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" --fleet "$FLEET_ROOT" apply --group GROUP CONFIRMED_FLAGS
   ```

   `CONFIRMED_FLAGS` is one `--confirmed ID` per person step the person has done
   in this run, empty at first. Allow a long timeout: a cask or an installer can
   take minutes.

5. Read the exit status:

   | Exit | Meaning | Do |
   | -- | -- | -- |
   | 0 | the group is done | next group |
   | 10 | stopped at a person step | show its title, what it needs and its command; wait for the person to say it is done; add `--confirmed ID` and run step 4 again |
   | 1 | a command failed | quote the `FAILED` line and the output under it; ask whether to retry, skip the group, or stop |
   | 2 | wrong platform or unknown group | report it and stop |

For a person step whose `why` is `choice` (a value such as the commit name and
email), ask the person for the value, show the command with it filled in, and
run it on their yes. For one whose terminal is `separate`, tell the person to
open another terminal, paste the block there, and come back; the block reads the
secret itself and never shows it.

A `path` step changes new shells only. If a later step in this session needs the
new entry, the script already has it; anything you run yourself does not.

### Step 4: Offer the repos

Clones follow `wayfare:wayfare-sync-fleet`'s rules: its *Step 0: Load* (the pin,
`UNPINNED`, `ORG_MISMATCH`) and the findings table under *Converge FLEET.md with
the folder* (`NOT_CLONED`, `ABSENT_OUTSIDE`). Read them there and apply them
unchanged. Run its Step 0 block from the fleet root, then:

```bash
"$WAYFARE_ROOT/scripts/fleet-scan.sh" "$FLEET_ROOT" --review
```

In short, and only as that skill says:

- Offer only `NOT_CLONED` rows whose path is `FLEET_ROOT/NAME`. Ask which to
  clone: names, a group name, or `all`, which means every such row whose group
  is not `none`. Never assume `all`.
- Build each URL from this machine's pin (`PIN=HOST/OWNER/NAME` gives
  `git@HOST:OWNER/NAME.git` for the register's owner), never from the map's
  `org:`, and show every URL in full before cloning.
- With `UNPINNED`, a `file…` pin, or `ORG_MISMATCH`, offer no clone.
- Report `ABSENT_OUTSIDE` rows and never clone them or write there.

```bash
git clone git@HOST:OWNER/NAME.git "$FLEET_ROOT/NAME"
```

### Step 5: Restore local-only files

Git does not carry each repo's `.plans/` and `.env`, or Claude Code's memory.
Ask whether there is an old machine to copy them from. If not, skip this step:
`.env` values are then set by hand, per each repo's `HERO.md`, and `.plans/` and
the memory start empty.

If there is, the person runs this on the old machine, from its fleet root:

```bash
(umask 077; setopt nullglob 2>/dev/null; tar czf ~/fleet-local.tgz */.plans */.env)
(umask 077; cd ~ && tar czf ~/claude-memory.tgz .claude/projects/*/memory)
```

Tell them: **`fleet-local.tgz` holds live secrets, unencrypted.** Send both
files directly between the machines, such as by AirDrop, never through a synced
folder, a chat or a repo.

Ask the person where each archive is. If one is in `~/Downloads`, show its full
path and ask before using it; never pick an archive up without asking. Then
check each one before anything is unpacked:

```bash
chmod 600 LOCAL_ARCHIVE MEMORY_ARCHIVE
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" archive --kind local LOCAL_ARCHIVE
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" archive --kind memory MEMORY_ARCHIVE
```

An archive with any `REFUSED` line is not unpacked at all: quote the lines and
stop this step. The check allows only `NAME/.plans/…`, `NAME/.env` and a
top-level `FLEET.md` in the local archive, and only
`.claude/projects/PROJECT/memory/…` in the memory one, as plain files and
folders. Anything else, such as a Claude hook or a LaunchAgent, would run once
unpacked into `~`.

Unpack the memory archive into `~`, naming the one folder it may write:

```bash
tar xzkf MEMORY_ARCHIVE -C ~ .claude/projects
```

`tar -k` keeps any file already there, so a rerun cannot overwrite newer work.
Memory folders are named after the project's full path, so they match only when
the username and the fleet root path are the same on both machines; say so.

Restore each cloned repo. A clone does not carry `.git/info/exclude`, which is
the only thing ignoring `.plans/` in most repos, so the loop writes the excludes
first; without them, `git add -A` commits the plans. A `.env` git would not
ignore is left behind rather than restored.

```bash
(umask 077; mkdir -p ~/fleet-restore && tar xzf LOCAL_ARCHIVE -C ~/fleet-restore)
cd "$FLEET_ROOT"
for repo in */; do
  repo=${repo%/}
  [ -d "$repo/.git" ] || continue
  mkdir -p "$repo/.git/info"
  for p in .plans/ .test-output/ .worktrees/; do
    grep -qxF "$p" "$repo/.git/info/exclude" 2>/dev/null || echo "$p" >> "$repo/.git/info/exclude"
  done
  [ -d ~/fleet-restore/"$repo"/.plans ] && cp -Rn ~/fleet-restore/"$repo"/.plans "$repo/"
  if [ -f ~/fleet-restore/"$repo"/.env ]; then
    if git -C "$repo" check-ignore -q .env; then
      cp -n ~/fleet-restore/"$repo"/.env "$repo/.env"
    else
      echo "NOT RESTORED: $repo/.env is not ignored by git"
    fi
  fi
done
```

Report every `NOT RESTORED` line: that repo needs a `.gitignore` entry before
its `.env` comes across. Never print, open or list the values of a restored
file. The archive's `FLEET.md`, if any, is not restored: the map comes from the
register.

Once every repo the person wants is cloned, ask them to delete the archives and
`~/fleet-restore` on this machine, naming the paths they gave, and the archives
on the old machine.

### Step 6: Set up each repo

For each repo cloned or chosen in Step 4, in this session, one at a time: `cd`
into it and follow [SKILL.md](SKILL.md) from Step 1. Its gates ask the person,
so it does not fan out to subagents. Collect each repo's summary for the report.

### Step 7: Verify and report

```bash
uv run "$WAYFARE_ROOT/scripts/fleet-setup.py" --fleet "$FLEET_ROOT" verify
for f in ~/fleet-local.tgz ~/claude-memory.tgz ~/fleet-restore ~/Downloads/fleet-local.tgz ~/Downloads/claude-memory.tgz; do
  [ -e "$f" ] && echo "SECRETS ARCHIVE STILL PRESENT: $f"
done
cd "$FLEET_ROOT"
for repo in */; do
  repo=${repo%/}
  [ -d "$repo/.git" ] || continue
  git -C "$repo" check-ignore -q .plans/ || echo "PLANS NOT IGNORED: $repo"
done
```

Run it and report what it prints; never infer a pass from the steps above. Then
report, in this order:

```text
FLEET SETUP
═══════════
Groups:      ✓ base, dev-tools, claude   ✗ infra (FAILED infra.12: ...)
Declined:    marketing, rare-tools
Person steps still open: claude.11 restart Claude Code and sign in with /mcp
Repos:       cloned auth, web; restored .plans in 2, .env in 1
             NOT RESTORED: web/.env is not ignored by git
Verify:      3/4 pass; FAIL docker compose
Archive:     gone from this machine; old machine not confirmed
Per repo:    one SETUP SUMMARY block each, from Step 6
```

If `setup.yaml` was wrong for this machine, propose the correction as a register
PR for the person to open; this skill never writes it.
