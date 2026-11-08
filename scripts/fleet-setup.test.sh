#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for scripts/fleet-setup.py.
#
# Every case runs the script the way the skill does (`uv run`) against a fake
# HOME and a PATH of stubs, so nothing here installs software or touches the
# real git, shell or Claude config. The stubs record what they were asked to
# do, which is how "safe to run twice" is tested: the second apply must ask
# them for nothing.
#
# Usage: bash scripts/fleet-setup.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/fleet-setup.py"
EXAMPLE="$HERE/../assets/fleet/setup.example.yaml"

# No skip when uv is missing: a suite that skips prints the same as one that
# passed.
UV="$(command -v uv)" || { echo "fleet-setup.test.sh: uv missing (https://docs.astral.sh/uv/)"; exit 1; }
UV_CACHE="$("$UV" cache dir)"
UV_PY="$("$UV" python find '>=3.11')" || { echo "fleet-setup.test.sh: uv finds no python >= 3.11"; exit 1; }

PASS=0
FAIL=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL  %s\n      expected: [%s]\n      actual:   [%s]\n' "$1" "$2" "$3"
  fi
}
has() { # name needle haystack
  case "$3" in *"$2"*) PASS=$((PASS + 1)) ;; *) FAIL=$((FAIL + 1)); printf 'FAIL  %s\n      missing: [%s]\n      in: %s\n' "$1" "$2" "$3" ;; esac
}
lacks() { # name needle haystack
  case "$3" in *"$2"*) FAIL=$((FAIL + 1)); printf 'FAIL  %s\n      found: [%s]\n' "$1" "$2" ;; *) PASS=$((PASS + 1)) ;; esac
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
T="$(cd "$TMP" && pwd -P)"
H="$T/home"
BIN="$T/bin"
ST="$T/state"
LOG="$T/calls.log"
mkdir -p "$H" "$BIN" "$ST"
: > "$LOG"
CANARY="canary-value-do-not-print"

# Stubs. Each records its argv and keeps "installed" state in $ST.
cat > "$BIN/brew" <<EOF
#!/bin/bash
echo "brew \$*" >> "$LOG"
case "\$1 \$2" in
  "list --formula") cat "$ST/formula" 2>/dev/null; exit 0 ;;
  "list --cask") cat "$ST/cask" 2>/dev/null; exit 0 ;;
esac
if [ "\$1" = install ]; then
  shift
  f="$ST/formula"; [ "\$1" = --cask ] && { f="$ST/cask"; shift; }
  [ "\$1" = broken ] && { echo "Error: no formula broken"; exit 1; }
  echo "\${1##*/}" >> "\$f"; exit 0
fi
exit 1
EOF
cat > "$BIN/pipx" <<EOF
#!/bin/bash
echo "pipx \$*" >> "$LOG"
[ "\$1 \$2" = "list --short" ] && { cat "$ST/pipx" 2>/dev/null; exit 0; }
[ "\$1" = install ] && { echo "\$2 1.0.0" >> "$ST/pipx"; exit 0; }
exit 1
EOF
cat > "$BIN/claude" <<EOF
#!/bin/bash
echo "claude \$*" >> "$LOG"
case "\$*" in
  "plugin marketplace list --json") printf '[%s]' "\$(sed 's/.*/{"name":"&"}/' "$ST/mkt" 2>/dev/null | paste -sd, -)"; exit 0 ;;
  "plugin list --json") printf '[%s]' "\$(sed 's/.*/{"id":"&"}/' "$ST/plg" 2>/dev/null | paste -sd, -)"; exit 0 ;;
  "plugin marketplace add "*) echo "\${4##*/}" >> "$ST/mkt"; exit 0 ;;
  "plugin install "*) echo "\$3" >> "$ST/plg"; exit 0 ;;
  "mcp get "*)
    # The real command prints the server's environment, keys included.
    echo "CONTEXT7_API_KEY=\$CONTEXT7_API_KEY"
    grep -qxF "\$3" "$ST/mcp" 2>/dev/null; exit ;;
  "mcp add --scope user --transport "*) echo "\$*" >> "$ST/mcp-adds"; echo "\$7" >> "$ST/mcp"; exit 0 ;;
  "mcp add "*) echo "\$*" >> "$ST/mcp-adds"; n=\$5
    echo "\$n" >> "$ST/mcp"; exit 0 ;;
esac
exit 1
EOF
chmod +x "$BIN"/*

fs() { # args... ; runs the script as the skill does, against the fakes
  env -i HOME="$H" XDG_CONFIG_HOME="$H/.config" PATH="$BIN:/usr/bin:/bin" TMPDIR="$T" \
    UV_CACHE_DIR="$UV_CACHE" UV_PYTHON="$UV_PY" GIT_CONFIG_NOSYSTEM=1 \
    FLEET_SETUP_PLATFORM="${PLAT:-macos-arm64}" CONTEXT7_API_KEY="$CANARY" ${FS_ENV:-} \
    "$UV" run --quiet "$SCRIPT" "$@" 2>&1
}

GOOD="$T/good.yaml"
cat > "$GOOD" <<'EOF'
version: 1
platform: macos-arm64
workspace: ~/work
notes: [top note]
groups:
  - name: first
    title: First group
    notes: [a licence note]
    steps:
      - brew: [just, go]
      - cask: [orbstack]
      - pipx: [pre-commit]
      - installer: {name: Fake, check: fakecmd, run: "mkdir -p $HOME/.local/bin && printf '#!/bin/sh\\n' > $HOME/.local/bin/fakecmd && chmod +x $HOME/.local/bin/fakecmd && echo x >> $HOME/installer-ran"}
      - git: {pull.rebase: "false"}
      - shell: {file: ~/.zshrc, lines: ["alias k=kubectl", "alias gst='git status'"]}
      - path: {file: ~/.zshrc, entries: ["$HOME/.local/bin"]}
      - person: {title: Open the app once, why: gui, check: "test -f $HOME/opened"}
      - brew: [after-person]
  - name: claude
    title: Claude
    steps:
      - marketplace: [{name: claude-plugins-official, source: anthropics/claude-plugins-official}]
      - plugin: [tool@claude-plugins-official]
      - mcp: {name: playwright, transport: stdio, command: npx, args: [-y, "@playwright/mcp@0.0.83"]}
      - mcp: {name: vanta, transport: http, url: https://mcp.vanta.com/mcp}
      - mcp: {name: context7, transport: stdio, command: npx, args: [-y, "@upstash/context7-mcp@4.4.4"], secrets: [CONTEXT7_API_KEY]}
  - name: extras
    title: Extras
    optional: true
    ask: Install the extras?
    steps:
      - brew: [yq, hashicorp/tap/terraform]
verify:
  - {name: echoes the key, run: 'echo "$CONTEXT7_API_KEY"; true', passes: always}
  - {name: fails, run: "false", passes: never}
EOF

bad() { # name expected-exit needle yaml
  printf '%s\n' "$4" > "$T/bad.yaml"
  out=$(fs --file "$T/bad.yaml" validate); rc=$?
  check "$1: exit" "$2" "$rc"
  has "$1: message" "$3" "$out"
}

BASE='version: 1
platform: macos-arm64
workspace: ~/w'
step() { printf '%s\ngroups:\n  - name: g\n    title: G\n    steps:\n      - %s\n' "$BASE" "$1"; }

# ── schema ───────────────────────────────────────────────────────────
out=$(fs --file "$GOOD" validate); check "good file validates" 0 $?
check "example asset validates" 0 "$(fs --file "$EXAMPLE" validate >/dev/null; echo $?)"
bad "missing version" 2 "missing required key 'version'" "$(step 'brew: [a]' | sed 1d)"
bad "version 2" 2 "version: expected 1, got 2" "$(step 'brew: [a]' | sed 's/^version: 1/version: 2/')"
bad "version as string" 2 "version: expected 1, got '1'" "$(step 'brew: [a]' | sed "s/^version: 1/version: '1'/")"
bad "unknown top-level key" 2 "unknown key 'group'" "$(step 'brew: [a]' | sed 's/^groups:/group:/')"
bad "typo inside a step" 2 "installer: unknown key 'checks'" "$(step '{installer: {name: x, checks: x, run: x}}')"
bad "typo drops no step: the required key is also reported" 2 "missing required key 'check'" "$(step '{installer: {name: x, checks: x, run: x}}')"
bad "unknown step kind" 2 "unknown step kind 'brw'" "$(step 'brw: [a]')"
bad "two kinds in one step" 2 "exactly one of" "$(step '{brew: [a], cask: [b]}')"
bad "wrong type: list" 2 "expected a non-empty list, got str" "$(step 'brew: just')"
bad "wrong type: git value" 2 "expected a string, got bool False; quote it" "$(step '{git: {pull.rebase: false}}')"
bad "wrong type: optional" 2 "optional: expected true or false" "$(printf '%s\ngroups:\n  - {name: g, title: G, optional: "yes", ask: q, steps: [{brew: [a]}]}\n' "$BASE")"
bad "optional group needs ask" 2 "needs the question to ask" "$(printf '%s\ngroups:\n  - {name: g, title: G, optional: true, steps: [{brew: [a]}]}\n' "$BASE")"
bad "unpinned npx" 2 "must run exact versions" "$(step '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "@playwright/mcp"]}}')"
bad "npx at latest" 2 "must run exact versions" "$(step '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "@playwright/mcp@latest"]}}')"
bad "secret value is not a field" 2 "unknown key 'env'" "$(step '{mcp: {name: p, transport: stdio, command: node, env: {K: v}}}')"
bad "secret name shape" 2 "is not a valid value" "$(step '{mcp: {name: p, transport: stdio, command: node, secrets: ["sk-abc"]}}')"
bad "secret person step in session" 2 "runs in a separate terminal" "$(step '{person: {title: t, why: secret, check: "true"}}')"
bad "person step without a check" 2 "person: missing required key 'check'" "$(step '{person: {title: t, why: gui}}')"
# The YAML goes through a variable: bash brace-expands a `{a, b}` written
# inside a command substitution's argument, and the step would arrive split.
pin() { y="{mcp: {name: p, transport: stdio, command: $3, args: $4}}"; bad "pin: $1" "$2" "must run exact versions" "$(step "$y")"; }
pin "major only" 2 npx '[-y, "foo@1"]'
pin "x range" 2 npx '[-y, "foo@1.x"]'
pin "two parts" 2 npx '[-y, "foo@1.2"]'
pin "--package=latest" 2 npx '[-y, "--package=evil@latest", "evil"]'
pin "--package unpinned beside a pinned positional" 2 npx '[-y, "--package=evil@latest", "ok@1.2.3"]'
pin "-p unpinned" 2 npx '[-y, "-p", "evil", "evil"]'
pin "uvx --from unpinned" 2 uvx '["--from", "evil", "evil"]'
pin "uvx --with unpinned beside a pinned package" 2 uvx '["--with", "extra", "tool==1.2.3"]'
ok_step() { printf '%s\n' "$(step "$2")" > "$T/ok.yaml"; out=$(fs --file "$T/ok.yaml" validate); check "accepted: $1" 0 $?; }
ok_step "npx exact" '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "@scope/pkg@1.2.3"]}}'
ok_step "npx prerelease" '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "pkg@1.2.3-beta.1"]}}'
ok_step "npx -p pinned, command after" '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "-p", "pkg@1.2.3", "pkg-cli"]}}'
ok_step "uvx --from pinned" '{mcp: {name: p, transport: stdio, command: uvx, args: ["--from", "pkg==1.2.3", "cmd"]}}'
# The literal ~ is what the validator must refuse.
# shellcheck disable=SC2088
for e in '$HOME/bin"; touch /tmp/x; "' '$(id)' '`id`' '~/.local/bin' 'relative/bin' '/opt/a\\b' '$HOME/a b'; do
  y="{path: {file: ~/.zshrc, entries: ['$e']}}"
  bad "path entry rejected: $e" 2 "is not a valid value" "$(step "$y")"
done
ok_step "path entry absolute" '{path: {file: ~/.zprofile, entries: [/opt/homebrew/bin]}}'
# The literal ~ is what the validator must refuse.
# shellcheck disable=SC2088
for f in '~/.ssh/authorized_keys' '~/' '/etc/zshrc' '~/Library/LaunchAgents/x.plist'; do
  y="{shell: {file: '$f', lines: [x]}}"
  bad "rc file rejected: $f" 2 "is not a shell startup file" "$(step "$y")"
done
bad "two lines in one shell entry" 2 "one line per entry" "$(step '{shell: {file: ~/.zshrc, lines: ["a\nb"]}}')"
bad "header prefix with shell" 2 "prefix" "$(step '{mcp: {name: v, transport: http, url: "https://x", secrets: [{header: Authorization, env: T, prefix: "$(id) "}]}}')"
bad "plugin before its marketplace" 2 "marketplace 'm' is not declared" "$(step 'plugin: [p@m]')"
bad "plugin before a later marketplace" 2 "marketplace 'm' is not declared" "$(printf '%s\ngroups:\n  - {name: g, title: G, steps: [{plugin: [p@m]}, {marketplace: [{name: m, source: o/m}]}]}\n' "$BASE")"
bad "http server over plain http" 2 "must be https://" "$(step '{mcp: {name: v, transport: http, url: "http://x"}}')"
bad "platform" 2 "platform: expected one of" "$(step 'brew: [a]' | sed 's/macos-arm64/windows-x64/')"
bad "not yaml" 2 "not YAML" "version: [1"

# ── plan: order, statuses, presence with a fake PATH ────────────────
printf 'just\n' > "$ST/formula"
: > "$ST/cask"
out=$(fs --file "$GOOD" --unreviewed plan); rc=$?
check "plan exits 0" 0 "$rc"
order=$(printf '%s\n' "$out" | grep -oE '^== [a-z-]+' | tr '\n' ' ')
check "groups in file order" "== first == claude == extras " "$order"
ids=$(printf '%s\n' "$out" | grep -oE 'first\.[a-z]+:[^ ]+' | tr '\n' ' ')
check "steps listed in file order" "first.brew:just first.brew:go first.cask:orbstack first.pipx:pre-commit first.installer:fakecmd first.git:pull.rebase first.shell:fdf7b6a7 first.shell:5a00e7c4 first.path:a8e155da first.person:894bc4e0 first.brew:after-person " "$ids"
has "present formula is ok" "[ok]     first.brew:just " "$out"
has "absent formula is todo" "[todo]   first.brew:go " "$out"
has "installer absent is todo" "[todo]   first.installer:fakecmd" "$out"
has "person step open" "[person] first.person:894bc4e0" "$out"
has "optional group flagged" "== extras (optional): Extras" "$out"
has "optional group's question" "ask: Install the extras?" "$out"
has "group note shown" "note: a licence note" "$out"
has "summary" "optional groups: extras" "$out"
printf '#!/bin/sh\n' > "$BIN/fakecmd"; chmod +x "$BIN/fakecmd"
out=$(fs --file "$GOOD" --unreviewed plan)
has "installer present when its command is on PATH" "[ok]     first.installer:fakecmd" "$out"
rm "$BIN/fakecmd"
json=$(fs --file "$GOOD" --unreviewed plan --json)
check "json: statuses in order" "present missing missing missing missing missing missing missing missing person missing" \
  "$(printf '%s' "$json" | "$UV_PY" -c 'import json,sys; print(" ".join(s["status"] for s in json.load(sys.stdin)["groups"][0]["steps"]))')"
check "json: secret mcp is a person step in a separate terminal" "person separate secret" \
  "$(printf '%s' "$json" | "$UV_PY" -c 'import json,sys; s=json.load(sys.stdin)["groups"][1]["steps"][4]; print(s["status"], s["person"]["terminal"], s["person"]["why"])')"
check "plan changed nothing" "" "$(grep -E 'install|add|config --global [a-z.]+ ' "$LOG")"
check "plan wrote no rc file" "no" "$([ -e "$H/.zshrc" ] && echo yes || echo no)"

# ── secrets: the name is in the command, the value is nowhere ───────
has "secret command names the variable" "-e CONTEXT7_API_KEY=\"\$CONTEXT7_API_KEY\"" "$out"
has "server name before -e" "claude mcp add --scope user context7 -e" "$out"
has "secret read without echo" "read -rs CONTEXT7_API_KEY" "$out"
has "secret unset after" "unset CONTEXT7_API_KEY" "$out"
printf 'context7\n' > "$ST/mcp"
all="$(fs --file "$GOOD" --unreviewed plan)$(fs --file "$GOOD" --unreviewed plan --json)$(fs --file "$GOOD" --unreviewed check --json)$(fs --file "$GOOD" --unreviewed verify)$(fs --file "$GOOD" --unreviewed apply --group claude)"
lacks "secret value never printed (plan, check, verify, apply)" "$CANARY" "$all"
: > "$ST/mcp"; : > "$ST/mkt"; : > "$ST/plg"; : > "$LOG"

out=$(fs --file "$GOOD" --unreviewed check); check "check exits 1 while a required step is open" 1 $?
check "check changed nothing" "" "$(grep -E ' install|marketplace add|mcp add' "$LOG")"

# ── verify ───────────────────────────────────────────────────────────
out=$(fs --file "$GOOD" --unreviewed verify); rc=$?
check "verify exits 1 when a check fails" 1 "$rc"
has "verify reports pass" "ok   echoes the key" "$out"
has "verify reports fail" "FAIL fails" "$out"

# ── apply: order, person stop, idempotency ──────────────────────────
printf 'no newline at end' > "$H/.zshrc"
out=$(fs --file "$GOOD" --unreviewed apply --group first); rc=$?
check "apply stops at the open person step" 10 "$rc"
has "names the step to confirm" "then: apply --group first --confirmed first.person:894bc4e0" "$out"
check "steps after the person step did not run" "" "$(grep 'after-person' "$LOG")"
check "rc lines appended once, after a newline" "no newline at end
alias k=kubectl
alias gst='git status'
export PATH=\"\$HOME/.local/bin:\$PATH\"" "$(cat "$H/.zshrc")"
check "git set in the fake HOME" "false" "$(HOME="$H" GIT_CONFIG_NOSYSTEM=1 git config --global --get pull.rebase)"
check "installer ran once, and its command is found on the declared PATH entry" 1 "$(wc -l < "$H/installer-ran" | tr -d ' ')"
rm "$H/.local/bin/fakecmd"
out=$(fs --file "$GOOD" --unreviewed apply --group first); rc=$?
check "installer reruns while its command is absent" "10 2" "$rc $(wc -l < "$H/installer-ran" | tr -d ' ')"
: > "$LOG"
out=$(fs --file "$GOOD" --unreviewed apply --group first --confirmed first.person:894bc4e0); rc=$?
check "confirmed person step continues" 0 "$rc"
check "only the step after the person step installs" "brew install after-person" "$(grep -E ' install' "$LOG")"
: > "$LOG"
cp "$H/.zshrc" "$T/zshrc.before"
out=$(fs --file "$GOOD" --unreviewed apply --group first --confirmed first.person:894bc4e0); rc=$?
check "second apply exits 0" 0 "$rc"
check "second apply installs nothing" "" "$(grep -E ' install|marketplace add|mcp add' "$LOG")"
check "second apply leaves the rc file alone" "$(cat "$T/zshrc.before")" "$(cat "$H/.zshrc")"
touch "$H/opened"; rm -f "$H/.zshrc"
out=$(fs --file "$GOOD" --unreviewed apply --group first); rc=$?
check "a passing check closes a person step" 0 "$rc"
check "rc file created when absent" 3 "$(wc -l < "$H/.zshrc" | tr -d ' ')"

out=$(fs --file "$GOOD" --unreviewed apply --group claude); rc=$?
check "claude group stops at the secret step" 10 "$rc"
check "marketplace, plugin and plain mcp added in order" "plugin marketplace add anthropics/claude-plugins-official
plugin install tool@claude-plugins-official
mcp add --scope user playwright -- npx -y @playwright/mcp@0.0.83
mcp add --scope user --transport http vanta https://mcp.vanta.com/mcp" \
  "$(grep -E 'marketplace add|plugin install|mcp add' "$LOG" | sed 's/^claude //')"
check "the script never runs the secret step" "" "$(grep context7 "$ST/mcp-adds")"

: > "$LOG"
echo terraform >> "$ST/formula"
out=$(fs --file "$GOOD" --unreviewed apply --group extras); rc=$?
has "a tap formula is found by its short name" "[ok]     extras.brew:hashicorp/tap/terraform" "$out"
check "optional group applies only when named" "0 brew install yq" "$rc $(grep ' install' "$LOG")"
out=$(fs --file "$GOOD" --unreviewed apply --group nope); check "unknown group" 2 $?
out=$(PLAT=linux-x86_64 fs --file "$GOOD" --unreviewed apply --group extras); rc=$?
check "wrong platform refuses apply" 2 "$rc"
has "wrong platform says so" "this machine is linux-x86_64" "$out"

printf '%s\ngroups:\n  - {name: g, title: G, steps: [{brew: [broken]}, {brew: [later]}]}\n' "$BASE" > "$T/fail.yaml"
: > "$LOG"
out=$(fs --file "$T/fail.yaml" --unreviewed apply --group g); rc=$?
check "a failing step stops apply" 1 "$rc"
has "failure quotes the error" "| Error: no formula broken" "$out"
check "nothing after a failure runs" "" "$(grep later "$LOG")"

# ── secrets in a header prefix stay literal ─────────────────────────
printf '%s\ngroups:\n  - {name: g, title: G, steps: [{mcp: {name: v, transport: http, url: "https://x.example/mcp", secrets: [{header: Authorization, env: V_TOKEN, prefix: "Bearer "}]}}]}\n' "$BASE" > "$T/hdr.yaml"
out=$(fs --file "$T/hdr.yaml" --unreviewed plan)
has "header literal quoted, variable expanded" "--header 'Authorization: Bearer '\"\$V_TOKEN\"" "$out"

# ── a command that cannot start is reported as such ─────────────────
cp "$BIN/brew" "$T/brew.stub"
printf '\001\002not a program' > "$BIN/brew"; chmod +x "$BIN/brew"
out=$(fs --file "$T/fail.yaml" --unreviewed apply --group g); rc=$?
check "a command that cannot start fails apply" 1 "$rc"
has "names why it did not run" "brew could not start: Exec format error" "$out"
lacks "not reported as missing" "not found" "$out"
cp "$T/brew.stub" "$BIN/brew"

# ── --file: explicit, never a symlink, and apply needs --unreviewed ─
out=$(fs --file "$GOOD" apply --group extras); rc=$?
check "apply refuses --file without --unreviewed" 2 "$rc"
has "says why" "pass --unreviewed" "$out"
ln -s "$GOOD" "$T/link.yaml"
out=$(fs --file "$T/link.yaml" validate); rc=$?
check "a symlinked --file is refused" "3" "$rc"
has "names the symlink" "GATE SYMLINK" "$out"

# ── the review gate: origin/main of the pinned register, fetched ────
G="$T/gate"; F="$G/fleet"; R="$G/remote/register.git"
mkdir -p "$F" "$G/remote" "$H/.config/wayfare"
g() { HOME="$H" GIT_CONFIG_NOSYSTEM=1 git -c user.name=t -c user.email=t@example.com \
  -c commit.gpgsign=false -c tag.gpgsign=false -c init.defaultBranch=main "$@"; }
commit_setup() { # dir sed-expr message
  sed "$2" "$GOOD" > "$1/setup.yaml"
  g -C "$1" add -A && g -C "$1" commit -qm "$3"
}
g init -q --bare "$R"
g clone -q "$R" "$F/.fleet" 2>/dev/null
printf '# Fleet\n\n## Fleet\n\n- name: t\n' > "$F/.fleet/FLEET.md"
commit_setup "$F/.fleet" 's/^//' init
g -C "$F/.fleet" push -q origin HEAD:main
PINS="$H/.config/wayfare/registers"
printf '%s %s\n' "$F" "file$R" > "$PINS"
gate() { fs --fleet "$F" "$@"; }

out=$(gate validate); rc=$?
check "the pinned register's origin/main validates" 0 "$rc"
has "names where it was read" "setup.yaml @ origin/main" "$out"
out=$(gate apply --group extras); check "reviewed apply needs --at" 2 $?
SHA=$(gate plan | sed -n 's/^reviewed: \([0-9a-f]*\) .*/\1/p')
out=$(gate plan); has "plan prints the sha it read" "reviewed: $SHA" "$out"
out=$(gate apply --group extras --at "${SHA:0:12}"); check "reviewed apply at the planned sha runs without --unreviewed" 0 $?

sed -i.bak 's/yq, /dirty-evil, /' "$F/.fleet/setup.yaml"
out=$(gate plan); rc=$?
check "plan with a dirty working tree" 0 "$rc"
lacks "a dirty working tree is never read" "dirty-evil" "$out"
has "reads the reviewed copy" "brew yq" "$out"
has "says the working tree differs" "differs from origin/main" "$out"
g -C "$F/.fleet" checkout -q -- setup.yaml

g -C "$F/.fleet" checkout -q -b review
commit_setup "$F/.fleet" 's/yq, /branch-evil, /' branch
g -C "$F/.fleet" branch origin/main HEAD
out=$(gate plan)
lacks "a local branch named origin/main is not read" "branch-evil" "$out"
commit_setup "$F/.fleet" 's/yq, /tag-evil, /' tag
g -C "$F/.fleet" tag origin/main HEAD
out=$(gate plan)
lacks "a tag named origin/main is not read" "tag-evil" "$out"
has "the remote-tracking ref is" "brew yq" "$out"
g -C "$F/.fleet" update-ref refs/remotes/origin/main HEAD
out=$(gate plan)
lacks "a hand-moved origin/main is fetched over" "tag-evil" "$out"

printf '%s %s\n' "$F" "github.com/acme/register" > "$PINS"
out=$(gate plan); rc=$?
check "pin mismatch refuses" 3 "$rc"
has "pin mismatch says both" "GATE PIN_MISMATCH: origin is file" "$out"
printf '%s %s\n' "$F" "acme/register" > "$PINS"
out=$(gate validate); check "a two-part pin is github.com, so a local origin mismatches" 3 $?
: > "$PINS"
out=$(gate validate); rc=$?
check "no pin refuses" 3 "$rc"
has "says no pin" "GATE NO_PIN" "$out"
printf '%s %s\n' "$F" "file$G/missing" > "$PINS"
g -C "$F/.fleet" remote set-url origin "$G/missing.git"
out=$(gate validate); rc=$?
check "a failed fetch refuses" 3 "$rc"
has "says the fetch failed" "GATE NO_FETCH" "$out"
g -C "$F/.fleet" remote set-url origin "$R"
printf '%s %s\n' "$F" "file$R" > "$PINS"

g clone -q "$R" "$G/work"
cp "$GOOD" "$G/work/other.yaml"; rm "$G/work/setup.yaml"; ln -s other.yaml "$G/work/setup.yaml"
g -C "$G/work" add -A && g -C "$G/work" commit -qm link && g -C "$G/work" push -q origin HEAD:main
out=$(gate validate); rc=$?
check "a committed symlink is refused" 3 "$rc"
has "names it" "GATE SYMLINK" "$out"
g -C "$G/work" rm -q setup.yaml && g -C "$G/work" commit -qm gone && g -C "$G/work" push -q origin HEAD:main
out=$(gate validate); rc=$?
check "no setup.yaml on origin/main" 4 "$rc"
has "says so" "GATE NO_SETUP_YAML" "$out"

# replace refs: a fetched refs/replace/* must not change what the gate reads
g -C "$G/work" checkout -q -- . 2>/dev/null
cp "$GOOD" "$G/work/setup.yaml"; rm -f "$G/work/other.yaml"
g -C "$G/work" add -A && g -C "$G/work" commit -qm back && g -C "$G/work" push -q origin HEAD:main
g -C "$F/.fleet" fetch -q origin "+refs/heads/main:refs/remotes/origin/main"
EVIL=$(sed 's/yq, /replace-evil, /' "$GOOD" | g -C "$F/.fleet" hash-object -w --stdin)
g -C "$F/.fleet" replace "$(g -C "$F/.fleet" rev-parse refs/remotes/origin/main:setup.yaml)" "$EVIL"
out=$(gate plan); rc=$?
check "plan with a replace ref" 0 "$rc"
lacks "a refs/replace object is not read" "replace-evil" "$out"
has "the reviewed blob is" "brew yq" "$out"

# inherited GIT_* config cannot repoint the register's origin past the pin
out=$(FS_ENV="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=url.$G/elsewhere.git.insteadOf GIT_CONFIG_VALUE_0=$R" gate validate); rc=$?
check "inherited GIT_CONFIG_* is dropped" 0 "$rc"

# apply --at: a merge after plan is refused
SHA=$(gate plan | sed -n 's/^reviewed: \([0-9a-f]*\) .*/\1/p')
sed -i.bak 's/yq, /merged-later, /' "$G/work/setup.yaml"
g -C "$G/work" commit -qam later && g -C "$G/work" push -q origin HEAD:main
out=$(gate apply --group extras --at "${SHA:0:12}"); rc=$?
check "apply refuses when origin/main moved since plan" 3 "$rc"
has "says it moved" "GATE MOVED" "$out"
check "and installed nothing" "" "$(grep merged-later "$LOG")"

# ── archives from an old machine ────────────────────────────────────
mkarch() { # out spec... ; spec is NAME:TYPE, TYPE f file, d folder, l symlink,
  # h hardlink to the first member, s setuid file; the spec JUNK is 512 bytes of
  # garbage where a header should be
  "$UV" run --quiet --no-project --python "$UV_PY" python - "$@" <<'PY'
import gzip, sys, tarfile
out, first, buf = sys.argv[1], None, b""
for spec in sys.argv[2:]:
    if spec == "JUNK":
        buf += b"\xff" * 512
        continue
    name, kind = spec.rsplit(":", 1)
    i = tarfile.TarInfo(name)
    data = b""
    if kind == "d":
        i.type, i.mode = tarfile.DIRTYPE, 0o755
    elif kind == "l":
        i.type, i.linkname = tarfile.SYMTYPE, "/etc/passwd"
    elif kind == "h":
        i.type, i.linkname = tarfile.LNKTYPE, first
    else:
        i.mode = 0o4755 if kind == "s" else 0o600
        data = b'{"hooks": "x"}\n'
        i.size = len(data)
    first = first or name
    buf += i.tobuf(tarfile.GNU_FORMAT) + data + b"\0" * (-len(data) % 512)
open(out, "wb").write(gzip.compress(buf + b"\0" * 1024))
PY
}
arch() { # name kind expected-rc needle spec...
  local n=$1 k=$2 want=$3 needle=$4; shift 4
  mkarch "$T/a.tgz" "$@"
  out=$(fs archive --kind "$k" "$T/a.tgz"); rc=$?
  check "archive $n" "$want" "$rc"
  has "archive $n: message" "$needle" "$out"
}
arch "local, expected members" local 0 "ok (local)" "web/:d" "web/.plans/:d" "web/.plans/a.md:f" "web/.env:f" "FLEET.md:f"
arch "local with a LaunchAgent" local 1 "REFUSED Library/LaunchAgents/x.plist" "web/.env:f" "Library/LaunchAgents/x.plist:f"
arch "local with a link" local 1 "not a regular file" "web/.plans/x:l"
arch "local escaping the folder" local 1 "not a plain relative path" "../web/.env:f"
arch "local with an absolute name" local 1 "not a plain relative path" "/web/.env:f"
arch "local with another dotfile" local 1 "not something fleet setup restores" "web/.envrc:f"
arch "setuid" local 1 "setuid" "web/.plans/run:s"
arch "memory, expected members" memory 0 "ok (memory)" ".claude/:d" ".claude/projects/:d" ".claude/projects/-u-x/:d" ".claude/projects/-u-x/memory/:d" ".claude/projects/-u-x/memory/MEMORY.md:f"
arch "memory with a settings hook" memory 1 "REFUSED .claude/settings.json" ".claude/projects/-u-x/memory/MEMORY.md:f" ".claude/settings.json:f"
arch "memory escaping memory/" memory 1 "not a plain relative path" ".claude/projects/-u-x/memory/../../../settings.json:f"
arch "memory with a project file" memory 1 "not something fleet setup restores" ".claude/projects/-u-x/session.jsonl:f"

# ── archives: one parser checks and extracts ────────────────────────
MEM=".claude/projects/-u-x/memory/MEMORY.md"
arch "a damaged header hiding a hardlink" memory 1 "unreadable data after byte" "$MEM:f" JUNK ".claude/settings.json:h"
arch "a hardlink member" memory 1 "not a regular file or folder" "$MEM:f" ".claude/projects/-u-x/memory/b.md:h"
arch "a symlink member" memory 1 "not a regular file or folder" ".claude/projects/-u-x/memory/b.md:l"
arch "a .plans symlink" local 1 "web/.plans: not a regular file or folder" "web/.plans:l"
mkarch "$T/poc.tgz" "$MEM:f" JUNK ".claude/settings.json:h"
out=$(fs archive --kind memory --extract "$T/poc-home" "$T/poc.tgz"); rc=$?
check "a refused archive extracts nothing" "1 no no" "$rc $([ -e "$T/poc-home/.claude/settings.json" ] && echo yes || echo no) $([ -e "$T/poc-home/$MEM" ] && echo yes || echo no)"
mkarch "$T/la.tgz" "web/.env:f" "Library/LaunchAgents/x.plist:f"
out=$(fs archive --kind local --extract "$T/la" "$T/la.tgz"); rc=$?
check "a refused member stops the whole extract" "1 0" "$rc $(find "$T/la" -type f 2>/dev/null | wc -l | tr -d ' ')"
mkarch "$T/mem.tgz" ".claude/:d" ".claude/projects/:d" ".claude/projects/-u-x/:d" ".claude/projects/-u-x/memory/:d" "$MEM:f" ".claude/projects/-u-x/memory/b.md:f"
mkdir -p "$T/xh/.claude/projects/-u-x/memory"; printf 'newer\n' > "$T/xh/.claude/projects/-u-x/memory/b.md"
out=$(fs archive --kind memory --extract "$T/xh" "$T/mem.tgz"); rc=$?
check "extract exits 0" 0 "$rc"
has "extract says what it did" "unpacked 1 files into $T/xh, kept 1 already there" "$out"
check "extract wrote the checked member" '{"hooks": "x"}' "$(cat "$T/xh/$MEM")"
check "extract never overwrites" "newer" "$(cat "$T/xh/.claude/projects/-u-x/memory/b.md")"
out=$(fs archive --kind memory --extract "$T/xh" "$T/mem.tgz")
has "a second extract keeps both" "unpacked 0 files into $T/xh, kept 2 already there" "$out"
mkdir -p "$T/xl" "$T/outside"; ln -s "$T/outside" "$T/xl/.claude"
out=$(fs archive --kind memory --extract "$T/xl" "$T/mem.tgz"); rc=$?
check "a symlink already in DEST cannot carry a member out" "1 0" "$rc $(find "$T/outside" -type f | wc -l | tr -d ' ')"

# ── --file runs nothing without --unreviewed ────────────────────────
printf '%s\ngroups:\n  - {name: g, title: G, steps: [{person: {title: t, why: gui, check: "touch $HOME/check-ran"}}]}\nverify:\n  - {name: v, run: "touch $HOME/verify-ran", passes: p}\n' "$BASE" > "$T/runs.yaml"
for c in plan check verify; do
  out=$(fs --file "$T/runs.yaml" "$c"); rc=$?
  check "$c refuses --file without --unreviewed" 2 "$rc"
done
check "and ran none of its commands" "no no" "$([ -e "$H/check-ran" ] && echo yes || echo no) $([ -e "$H/verify-ran" ] && echo yes || echo no)"
out=$(fs --file "$T/runs.yaml" validate); check "validate --file runs nothing and needs no flag" "0 no" "$? $([ -e "$H/check-ran" ] && echo yes || echo no)"

# ── step ids survive edits ──────────────────────────────────────────
awk '/- brew: \[just, go\]/ { print "      - brew: [inserted]" } 1' "$GOOD" > "$T/edited.yaml"
out=$(fs --file "$T/edited.yaml" --unreviewed plan)
has "an inserted step does not move a person step's id" " first.person:894bc4e0 " "$out"
has "the inserted step is listed" " first.brew:inserted " "$out"
printf '%s\ngroups:\n  - {name: g, title: G, steps: [{brew: [a]}, {brew: [a]}]}\n' "$BASE" > "$T/dup.yaml"
out=$(fs --file "$T/dup.yaml" validate); rc=$?
check "the same step twice in a group is invalid" 2 "$rc"
has "names the duplicate" "g.brew:a: the same step twice" "$out"

# ── uvx -w ──────────────────────────────────────────────────────────
pin "uvx -w unpinned" 2 uvx '["-w", "extra", "tool==1.2.3"]'
pin "uvx -wVALUE unpinned" 2 uvx '["-wextra", "tool==1.2.3"]'
ok_step "uvx -wVALUE pinned" '{mcp: {name: p, transport: stdio, command: uvx, args: ["-wextra==1.2.3", "tool==1.2.3"]}}'

echo "fleet-setup.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
