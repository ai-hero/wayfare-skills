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
  env -i HOME="$H" PATH="$BIN:/usr/bin:/bin" TMPDIR="$T" \
    UV_CACHE_DIR="$UV_CACHE" UV_PYTHON="$UV_PY" GIT_CONFIG_NOSYSTEM=1 \
    FLEET_SETUP_PLATFORM="${PLAT:-macos-arm64}" CONTEXT7_API_KEY="$CANARY" \
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
bad "unpinned npx" 2 "must run an exact version" "$(step '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "@playwright/mcp"]}}')"
bad "npx at latest" 2 "must run an exact version" "$(step '{mcp: {name: p, transport: stdio, command: npx, args: [-y, "@playwright/mcp@latest"]}}')"
bad "secret value is not a field" 2 "unknown key 'env'" "$(step '{mcp: {name: p, transport: stdio, command: node, env: {K: v}}}')"
bad "secret name shape" 2 "is not a valid value" "$(step '{mcp: {name: p, transport: stdio, command: node, secrets: ["sk-abc"]}}')"
bad "secret person step in session" 2 "runs in a separate terminal" "$(step '{person: {title: t, why: secret}}')"
bad "plugin before its marketplace" 2 "marketplace 'm' is not declared" "$(step 'plugin: [p@m]')"
bad "plugin before a later marketplace" 2 "marketplace 'm' is not declared" "$(printf '%s\ngroups:\n  - {name: g, title: G, steps: [{plugin: [p@m]}, {marketplace: [{name: m, source: o/m}]}]}\n' "$BASE")"
bad "rc file outside home" 2 "must be a file under ~/" "$(step '{shell: {file: /etc/zshrc, lines: [x]}}')"
bad "http server over plain http" 2 "must be https://" "$(step '{mcp: {name: v, transport: http, url: "http://x"}}')"
bad "platform" 2 "platform: expected one of" "$(step 'brew: [a]' | sed 's/macos-arm64/windows-x64/')"
bad "not yaml" 2 "not YAML" "version: [1"

# ── plan: order, statuses, presence with a fake PATH ────────────────
printf 'just\n' > "$ST/formula"
: > "$ST/cask"
out=$(fs --file "$GOOD" plan); rc=$?
check "plan exits 0" 0 "$rc"
order=$(printf '%s\n' "$out" | grep -oE '^== [a-z-]+' | tr '\n' ' ')
check "groups in file order" "== first == claude == extras " "$order"
ids=$(printf '%s\n' "$out" | grep -oE 'first\.[0-9]+' | tr '\n' ' ')
check "steps numbered in file order" "first.1 first.2 first.3 first.4 first.5 first.6 first.7 first.8 first.9 first.10 first.11 " "$ids"
has "present formula is ok" "[ok]     first.1        brew just" "$out"
has "absent formula is todo" "[todo]   first.2        brew go" "$out"
has "installer absent is todo" "[todo]   first.5" "$out"
has "person step open" "[person] first.10" "$out"
has "optional group flagged" "== extras (optional): Extras" "$out"
has "optional group's question" "ask: Install the extras?" "$out"
has "group note shown" "note: a licence note" "$out"
has "summary" "optional groups: extras" "$out"
printf '#!/bin/sh\n' > "$BIN/fakecmd"; chmod +x "$BIN/fakecmd"
out=$(fs --file "$GOOD" plan)
has "installer present when its command is on PATH" "[ok]     first.5" "$out"
rm "$BIN/fakecmd"
json=$(fs --file "$GOOD" plan --json)
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
all="$(fs --file "$GOOD" plan)$(fs --file "$GOOD" plan --json)$(fs --file "$GOOD" check --json)$(fs --file "$GOOD" verify)$(fs --file "$GOOD" apply --group claude)"
lacks "secret value never printed (plan, check, verify, apply)" "$CANARY" "$all"
: > "$ST/mcp"; : > "$ST/mkt"; : > "$ST/plg"; : > "$LOG"

out=$(fs --file "$GOOD" check); check "check exits 1 while a required step is open" 1 $?
check "check changed nothing" "" "$(grep -E ' install|marketplace add|mcp add' "$LOG")"

# ── verify ───────────────────────────────────────────────────────────
out=$(fs --file "$GOOD" verify); rc=$?
check "verify exits 1 when a check fails" 1 "$rc"
has "verify reports pass" "ok   echoes the key" "$out"
has "verify reports fail" "FAIL fails" "$out"

# ── apply: order, person stop, idempotency ──────────────────────────
printf 'no newline at end' > "$H/.zshrc"
out=$(fs --file "$GOOD" apply --group first); rc=$?
check "apply stops at the open person step" 10 "$rc"
has "names the step to confirm" "then: apply --group first --confirmed first.10" "$out"
check "steps after the person step did not run" "" "$(grep 'after-person' "$LOG")"
check "rc lines appended once, after a newline" "no newline at end
alias k=kubectl
alias gst='git status'
export PATH=\"\$HOME/.local/bin:\$PATH\"" "$(cat "$H/.zshrc")"
check "git set in the fake HOME" "false" "$(HOME="$H" GIT_CONFIG_NOSYSTEM=1 git config --global --get pull.rebase)"
check "installer ran once, and its command is found on the declared PATH entry" 1 "$(wc -l < "$H/installer-ran" | tr -d ' ')"
rm "$H/.local/bin/fakecmd"
out=$(fs --file "$GOOD" apply --group first); rc=$?
check "installer reruns while its command is absent" "10 2" "$rc $(wc -l < "$H/installer-ran" | tr -d ' ')"
: > "$LOG"
out=$(fs --file "$GOOD" apply --group first --confirmed first.10); rc=$?
check "confirmed person step continues" 0 "$rc"
check "only the step after the person step installs" "brew install after-person" "$(grep -E ' install' "$LOG")"
: > "$LOG"
cp "$H/.zshrc" "$T/zshrc.before"
out=$(fs --file "$GOOD" apply --group first --confirmed first.10); rc=$?
check "second apply exits 0" 0 "$rc"
check "second apply installs nothing" "" "$(grep -E ' install|marketplace add|mcp add' "$LOG")"
check "second apply leaves the rc file alone" "$(cat "$T/zshrc.before")" "$(cat "$H/.zshrc")"
touch "$H/opened"; rm -f "$H/.zshrc"
out=$(fs --file "$GOOD" apply --group first); rc=$?
check "a passing check closes a person step" 0 "$rc"
check "rc file created when absent" 3 "$(wc -l < "$H/.zshrc" | tr -d ' ')"

out=$(fs --file "$GOOD" apply --group claude); rc=$?
check "claude group stops at the secret step" 10 "$rc"
check "marketplace, plugin and plain mcp added in order" "plugin marketplace add anthropics/claude-plugins-official
plugin install tool@claude-plugins-official
mcp add --scope user playwright -- npx -y @playwright/mcp@0.0.83
mcp add --scope user --transport http vanta https://mcp.vanta.com/mcp" \
  "$(grep -E 'marketplace add|plugin install|mcp add' "$LOG" | sed 's/^claude //')"
check "the script never runs the secret step" "" "$(grep context7 "$ST/mcp-adds")"

: > "$LOG"
echo terraform >> "$ST/formula"
out=$(fs --file "$GOOD" apply --group extras); rc=$?
has "a tap formula is found by its short name" "[ok]     extras.2" "$out"
check "optional group applies only when named" "0 brew install yq" "$rc $(grep ' install' "$LOG")"
out=$(fs --file "$GOOD" apply --group nope); check "unknown group" 2 $?
out=$(PLAT=linux-x86_64 fs --file "$GOOD" apply --group extras); rc=$?
check "wrong platform refuses apply" 2 "$rc"
has "wrong platform says so" "this machine is linux-x86_64" "$out"

printf '%s\ngroups:\n  - {name: g, title: G, steps: [{brew: [broken]}, {brew: [later]}]}\n' "$BASE" > "$T/fail.yaml"
: > "$LOG"
out=$(fs --file "$T/fail.yaml" apply --group g); rc=$?
check "a failing step stops apply" 1 "$rc"
has "failure quotes the error" "| Error: no formula broken" "$out"
check "nothing after a failure runs" "" "$(grep later "$LOG")"

echo "fleet-setup.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
