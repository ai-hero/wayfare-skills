#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# The parity suite: the same scenarios run on the local backend and on the
# Wayfare server, and the outcomes are diffed. A scenario passes when both
# backends print the same lines for it.
#
# Two parts:
#   1. Always: the comparison itself, against a stateful stub `wayfare` CLI.
#      A server outcome changed on purpose must fail the suite (the mutations
#      below), or a diff that can never fail would pass for proof.
#   2. Opt-in: the same runner against a live fleet, when WAYFARE_PARITY names
#      the backend URL (`<origin>/<workspace id>`). Without it `just check`
#      stays offline and says so in one line.
#
# Live run, in order:
#   - the fixture repo `check` is written under WAYFARE_PARITY_FIXTURE (default
#     a temp dir) and handed to WAYFARE_PARITY_IMPORT, a shell command that
#     receives the fixture directory as $1 and imports it into the fleet. Unset,
#     the import is skipped and the fleet is assumed to hold the fixture
#     already. The repo is named `check` because a repo maps to the project
#     whose slug is its directory name.
#   - each scenario runs on a copy of the fixture under WAYFARE_STORE=local,
#     then under WAYFARE_STORE=<url>, and the two outputs are diffed.
#
# Re-runnable: scenarios that write put back what they changed, except what
# the server keeps forever. Priority and rank are restored; a message thread
# is closed; an audit result is a merge by check id. A log line stays (the log
# is append-only), so the assertion is the last line carrying this run's nonce,
# never a count of lines, and re-importing the fixture does not remove it
# either (the importer keeps log lines the files never had).
#
# Not compared, because the server has no value for them (docs/PLAN.md, the
# server backend): priority p0 (read back as p1), awaiting, replaced_by,
# channel, the plan's next_id and target.project, the fleet's name,
# template-port and register fields, the fleet row's path (FLEET_ROOT/NAME on
# the server), commit times, and the deploy-pending list (local by design).
# The fleet map is not imported: `wayfare-import fleet` writes the workspace's
# settings, which this suite must not touch, so the local FLEET.md is rendered
# from what the server holds for `check`. That compares the readers over one
# set of data, not the import.
#
# STORE_PARITY_SHOW=1 prints each scenario's local outcome.
#
# Usage: bash scripts/store-parity.test.sh

set -uo pipefail

LIB="$(cd "$(dirname "$0")" && pwd)/hero-lib.sh"
# shellcheck source=/dev/null
. "$LIB" || { echo "cannot source $LIB"; exit 1; }

PASS=0
FAIL=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); else
    FAIL=$((FAIL + 1))
    printf 'FAIL  %s\n      expected: [%s]\n      actual:   [%s]\n' "$1" "$2" "$3"
  fi
}

TMP="$(cd "$(mktemp -d)" && pwd -P)"
trap 'chmod -R u+w "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT
export TMPDIR="$TMP/tmp"; mkdir -p "$TMPDIR"
export XDG_CONFIG_HOME="$TMP/xdg"
unset WAYFARE_STORE
LIVE_CLI="${WAYFARE_CLI:-wayfare}"

# ---------- the fixture repo ---------------------------------------------------

# Every compared field is written explicitly, so a server default cannot read
# as a mismatch.
make_fixture() { # DIR
  local d=$1/check i
  rm -rf "$d" "$1/.fleet"
  mkdir -p "$d/.plans/items" "$d/.plans/inbox" "$1/.fleet"
  i="$d/.plans/items"
  cat > "$d/HERO.md" <<'EOF'
# Hero Configuration

## Repository

- default-branch: main

## CI/CD

- platform: github-actions

## Deployment

- platform: fly
EOF
  printf -- '---\nschema: 1\nrepo: acme/check\nnext_id: 20\nsource:\n  root: .\n  head: aaaa1111\ntarget:\n  project: D\n  head: bbbb2222\n---\n' > "$d/.plans/PLAN.md"
  printf -- '---\nid: 1\ntype: task\ntitle: Parity bootstrap\nstatus: done\nresolution: shipped\nshape: structural\npriority: p2\nparent: 9\nrank: 1\nsource: [src/one.go]\n---\n' > "$i/001-parity-bootstrap.md"
  printf -- '---\nid: 2\ntype: task\ntitle: Parity ready one\nstatus: ready\nshape: story\npriority: p2\nparent: 9\nrank: 2\ndepends_on: [1]\nsource: [src/two.go]\n---\n' > "$i/002-parity-ready-one.md"
  printf -- '---\nid: 3\ntype: task\ntitle: Parity ready two\nstatus: ready\nshape: story\npriority: p2\nparent: 9\nrank: 3\ndepends_on: [2]\nsource: [src/three.go]\n---\n\n## Subtasks\n\n- [ ] parity box\n' > "$i/003-parity-ready-two.md"
  printf -- '---\nid: 4\ntype: idea\ntitle: Parity parked idea\nstatus: accepted\n---\n' > "$i/004-parity-parked-idea.md"
  printf -- '---\nid: 5\ntype: task\ntitle: Parity wait on vendor\nstatus: ready\nshape: story\npriority: p2\nparent: 9\nrank: 5\nblocked_on: vendor review\nblocked_since: 2026-11-10\nsource: [src/five.go]\n---\n' > "$i/005-parity-wait-on-vendor.md"
  printf -- '---\nid: 9\ntype: goal\ntitle: Parity goal\nstatus: accepted\n---\n' > "$i/009-parity-goal.md"
  printf '# Fleet\n\n## Repos\n\n### check\n' > "$1/.fleet/FLEET.md"
}

# The local FLEET.md for `check`, rendered from `wayfare fleet`'s JSON.
fleet_md() { # FLEET_JSON_FILE
  jq -r '
    .data as $d | ($d.groups // []) as $g
    | ([$d.rows[]? | .project | select(.slug == "check")][0] // {}) as $p
    | "# Fleet\n\n## Fleet\n\n- name: parity\n"
      + (if ($d.settings.org // "") != "" then "- org: \($d.settings.org)\n" else "" end)
      + (if ($d.settings.template // "") != "" then "- template: \($d.settings.template)\n" else "" end)
      + (if (($d.settings.port_min // 0) + ($d.settings.port_max // 0)) > 0 then "- port-range: \($d.settings.port_min // 0)-\($d.settings.port_max // 0)\n" else "" end)
      + "\n## Repos\n\n### check\n\n"
      + (([$g[] | select(.id == ($p.group_id // ""))][0].name // "") as $gn | if $gn != "" then "- group: \($gn)\n" else "" end)
      + (if ($p.port // 0) != 0 then "- port: \($p.port)\n" else "" end)
      + (if ($p.what // "") != "" then "- what: \($p.what)\n" else "" end)' "$1"
}

# ---------- the scenarios --------------------------------------------------------

# Each scenario prints its outcome on stdout. ROOT is the repo, FLEET its
# parent. Output that legitimately differs (message ids, who wrote a log line)
# is normalised here, so the diff means a real difference.

FIELDS_TASK="type title status shape priority rank parent"

sc_ready() {
  hero_ready_items "$ROOT/.plans" 2>/dev/null | grep -E '[[:space:]]00[0-9]-' | sed 's/[[:space:]]*$//'
  echo "rc=${PIPESTATUS[0]}"
  echo "ideas: $(hero_idea_count "$ROOT/.plans" 2>/dev/null)"
  echo "goal 9 members: $(hero_goal_members 9 "$ROOT/.plans" 2>/dev/null | tr '\n' ' ')"
}

sc_item_fields() {
  local n f k
  for n in 1 2 3 4 5 9; do
    f=$(hero_item_file "$n" "$ROOT" 2>/dev/null) || { echo "item $n: no file"; continue; }
    if [ "$n" = 4 ] || [ "$n" = 9 ]; then
      for k in type title status; do echo "item $n $k: $(hero_item_field "$f" "$k")"; done
      continue
    fi
    for k in $FIELDS_TASK; do echo "item $n $k: $(hero_item_field "$f" "$k")"; done
    echo "item $n depends_on: $(hero_item_deps "$f" | tr '\n' ' ')"
    echo "item $n source: $(hero_item_list_field "$f" source | tr '\n' ' ')"
  done
  f=$(hero_item_file 1 "$ROOT") && echo "item 1 resolution: $(hero_item_field "$f" resolution)"
  f=$(hero_item_file 5 "$ROOT") && echo "item 5 blocked_on: $(hero_item_field "$f" blocked_on)"
}

sc_write_item() {
  local f
  echo "set priority p3: $(hero_item_set 2 priority p3 "$ROOT" 2>&1)"
  f=$(hero_item_file 2 "$ROOT"); echo "read: $(hero_item_field "$f" priority)"
  echo "set rank 7: $(hero_item_set 2 rank 7 "$ROOT" 2>&1)"
  f=$(hero_item_file 2 "$ROOT"); echo "read: $(hero_item_field "$f" rank)"
  hero_item_set 2 priority p2 "$ROOT" >/dev/null 2>&1
  hero_item_set 2 rank 2 "$ROOT" >/dev/null 2>&1
  f=$(hero_item_file 2 "$ROOT"); echo "restored: $(hero_item_field "$f" priority) $(hero_item_field "$f" rank)"
  echo "status is not a field write: rc=$(hero_item_set 2 status "done" "$ROOT" >/dev/null 2>&1; echo $?)"
}

sc_log() {
  local f
  echo "log: $(hero_item_log 2 note "parity $NONCE" "$ROOT" 2>&1)"
  f=$(hero_item_file 2 "$ROOT")
  echo "last line: $(grep -E '^- ' "$f" | grep -F "parity $NONCE" | tail -1 \
    | sed -E 's/^- [0-9]{4}-[0-9]{2}-[0-9]{2}[0-9T:Z ]*//; s/^\([^)]*\) //')"
  echo "lines with the nonce: $(grep -c -F "parity $NONCE" "$f")"
}

# A thread to oneself is `within` on the server and a deposit in the repo's
# own inbox locally. The server lets an agent send only from a project where it holds a live
# claim or a task it planned; create_item writes as the agent's owner and does
# not count. Item 2 is claimed (its dependency is done) and released after the
# thread closes. Each CLI run is a new instance, so the release passes the
# handle the claim ran under, or the claim stays until its lease lapses and
# the next import skips the item.
ensure_anchor() {
  local t origin ws
  case "$(hero_store_backend "$ROOT")" in local) return 0 ;; esac
  ANCHOR_PID=$(hero_srv_project "$ROOT") || return 1
  ANCHOR_TASK=$(hero_srv_cli "$ROOT" item --project-id "$ANCHOR_PID" --number 2 | jq -r '.item.id // empty')
  [ -n "$ANCHOR_TASK" ] || return 1
  t=$(hero_srv_target "$ROOT") || return 1
  origin=${t% *}; ws=${t#* }
  ANCHOR_INSTANCE=$(WAYFARE_URL="$origin" WAYFARE_WORKSPACE="$ws" "${WAYFARE_CLI:-wayfare}" claim --project-id "$ANCHOR_PID" --task-id "$ANCHOR_TASK" 2>&1 >/dev/null \
    | sed -n 's/^Wayfare-Instance: //p')
  [ -n "$ANCHOR_INSTANCE" ]
}

release_anchor() {
  [ -n "${ANCHOR_INSTANCE:-}" ] || return 0
  hero_srv_cli "$ROOT" release --project-id "$ANCHOR_PID" --task-id "$ANCHOR_TASK" --instance "$ANCHOR_INSTANCE" >/dev/null
  ANCHOR_INSTANCE=""
}

sc_messages() {
  local before id rid out
  before=$(hero_inbox_count "$ROOT/.plans" 2>/dev/null)
  id=$(hero_msg_send check request "parity $NONCE" "body $NONCE" "$ROOT" 2>/dev/null) || {
    ensure_anchor && id=$(hero_msg_send check request "parity $NONCE" "body $NONCE" "$ROOT" 2>/dev/null)
  }
  echo "send: $([ -n "$id" ] && echo id)"
  echo "unread after send: +$(($(hero_inbox_count "$ROOT/.plans" 2>/dev/null) - before))"
  rid=$(hero_msg_reply "$id" "on it $NONCE" "$ROOT" 2>/dev/null)
  echo "reply: $([ "$rid" = "$id" ] && echo same-thread || echo "$rid")"
  echo "unread after reply: +$(($(hero_inbox_count "$ROOT/.plans" 2>/dev/null) - before))"
  out=$(hero_msg_close "$id" answered "done $NONCE" "$ROOT" 2>/dev/null)
  echo "close: ${out//$id/ID}"
  echo "unread after close: +$(($(hero_inbox_count "$ROOT/.plans" 2>/dev/null) - before))"
  release_anchor 2>/dev/null || echo "release: the claim on item 2 was not released"
}

sc_hero_fields() {
  echo "default-branch: $(hero_field default-branch "$ROOT")"
  echo "deployment platform: $(hero_field_in "$ROOT" platform "## Deployment")"
  echo "ci platform: $(hero_field_in "$ROOT" platform "## CI/CD")"
  echo "sections: $(hero_config_sections "$ROOT" "CI/CD")"
  echo "exists: rc=$(hero_config_exists "$ROOT"; echo $?)"
}

sc_fleet() {
  local k
  hero_fleet_repos "$FLEET" 2>/dev/null | awk -F'\t' '$1 == "check" { print $1 " group=" $3 " port=" $4 }'
  for k in group port what; do echo "check $k: $(hero_fleet_repo_field check "$k" "$FLEET" 2>/dev/null)"; done
  for k in org template port-range; do echo "fleet $k: $(hero_fleet_field "$k" "$FLEET" 2>/dev/null)"; done
}

# Only `pass` is recorded: a failing result opens a reconcile change on every
# project that reads the repo. The local backend counts and records nothing;
# the server's `recorded` is every row held for the repo, so only "at least
# the one just sent" is comparable. Its `failing` is cumulative too, so a repo
# with an earlier failure shows here as a difference.
sc_audit() {
  hero_audit_record check "[{\"check_id\":\"$AUDIT_CHECK\",\"state\":\"pass\"}]" "$ROOT" 2>/dev/null \
    | jq -c '{recorded_at_least_one: (.recorded >= 1), failing}'
  echo "rc=${PIPESTATUS[0]}"
}

# build-task's item writes: a status, a box and a branch, read back through
# the rendered item. The server logs `review` instead of moving the task (a
# claim and link_pr move it), so only whether the status was taken compares.
sc_build() {
  local f out
  out=$(hero_item_set_status 3 review "" "$ROOT" 2>&1)
  echo "status review: rc=$? $(printf '%s\n' "$out" | grep -c review)"
  echo "tick: $(hero_item_tick 3 "parity box" "$ROOT" 2>&1)"
  echo "set branch: $(hero_item_set 3 branch "feat/parity-$NONCE" "$ROOT" 2>&1)"
  f=$(hero_item_file 3 "$ROOT") || { echo "read: failed"; return; }
  echo "read branch: $(hero_item_field "$f" branch)"
  echo "box: $(grep -E '^[-*] \[[ xX]\] parity box' "$f")"
}

SCENARIOS="ready item_fields write_item log messages hero_fields fleet audit build"

# run_backend LABEL BACKEND : the scenarios on one backend, into $TMP/out/LABEL
run_backend() {
  local label=$1 backend=$2 s src
  mkdir -p "$TMP/out/$label"
  src=$FIXTURE; [ "$label" = local ] && src=${LOCAL_FIXTURE:-$FIXTURE}
  cp -R "$src" "$TMP/$label-fleet"
  [ -n "${FLEET_MD:-}" ] && printf '%s\n' "$FLEET_MD" > "$TMP/$label-fleet/.fleet/FLEET.md"
  for s in $SCENARIOS; do
    (
      export WAYFARE_STORE="$backend"
      ROOT="$TMP/$label-fleet/check"; FLEET="$TMP/$label-fleet"
      export ROOT FLEET
      "sc_$s" > "$TMP/out/$label/$s.out" 2> "$TMP/out/$label/$s.err"
    )
  done
}

# compare NAME : one check per scenario, local against server
compare() { # PREFIX
  local s
  for s in $SCENARIOS; do
    [ -n "${STORE_PARITY_SHOW:-}" ] && { echo "--- $1$s (local)"; cat "$TMP/out/local/$s.out"; }
    if diff -u "$TMP/out/local/$s.out" "$TMP/out/server/$s.out" > "$TMP/out/$s.diff"; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      printf 'FAIL  %s%s: the backends differ (- local, + server)\n' "$1" "$s"
      sed 's/^/      /' "$TMP/out/$s.diff"
      [ -s "$TMP/out/server/$s.err" ] && sed 's/^/      server stderr: /' "$TMP/out/server/$s.err" | head -5
    fi
    # An empty outcome on both sides would "agree" on nothing.
    if [ ! -s "$TMP/out/local/$s.out" ]; then
      FAIL=$((FAIL + 1)); printf 'FAIL  %s%s: the local backend printed nothing\n' "$1" "$s"
    else
      PASS=$((PASS + 1))
    fi
  done
}

# parity PREFIX BACKEND_URL : both backends, diffed
parity() {
  rm -rf "$TMP/out" "$TMP/local-fleet" "$TMP/server-fleet"
  run_backend local local
  run_backend server "$2"
  compare "$1"
}

# ---------- part 1: the comparison against a stub CLI ------------------------------

STUB="$TMP/stub"; mkdir -p "$STUB"
cat > "$TMP/wayfare" <<'STUB'
#!/usr/bin/env bash
# A stateful stand-in for the wayfare CLI over the fixture's data.
# STUB_MUTATE=NAME changes one outcome, to prove the comparison can fail.
sub=$1; shift
payload=""
num=""
while [ $# -gt 0 ]; do
  case $1 in --json) payload=$2; shift ;; --number) num=$2; shift ;; esac
  shift
done
S="$STUB_DIR"
save() { cat > "$S/$1.tmp" && mv "$S/$1.tmp" "$S/$1"; }
case $sub in
  projects) echo '{"projects":[{"id":"p-check","slug":"check","name":"Check"}]}' ;;
  items) jq -c '{items: [.[] | del(.description, .log)]}' "$S/items.json" ;;
  item) jq -c --argjson n "$num" '{item: (.[] | select(.number == $n))}' "$S/items.json" ;;
  update-item)
    n=$(printf '%s' "$payload" | jq '.number')
    [ "$STUB_MUTATE" = write_item ] && payload=$(printf '%s' "$payload" | jq -c 'del(.priority)')
    jq -c --argjson n "$n" --argjson p "$payload" 'map(if .number == $n then . + ($p | del(.project_id, .number)) else . end)' "$S/items.json" | save items.json
    jq -c --argjson n "$n" '{item: (.[] | select(.number == $n))}' "$S/items.json" ;;
  log)
    n=$(printf '%s' "$payload" | jq '.number')
    [ "$STUB_MUTATE" = log ] && payload=$(printf '%s' "$payload" | jq -c 'if .tag == "note" then .text |= ascii_upcase else . end')
    [ "$STUB_MUTATE" = build ] && payload=$(printf '%s' "$payload" | jq -c 'if .tag == "tick" then .tag = "note" else . end')
    jq -c --argjson n "$n" --argjson p "$payload" 'map(if .number == $n then .log += [{at: "2026-11-14T10:00:00Z", by: "agent", tag: $p.tag, body: $p.text}] else . end)' "$S/items.json" | save items.json
    jq -c --argjson n "$n" '{item: (.[] | select(.number == $n))}' "$S/items.json" ;;
  messages) jq -c '{threads: .}' "$S/threads.json" ;;
  claim) : > "$S/claimed"; echo '{"task":{"status":"active"}}'; echo "Wayfare-Instance: inst-1" >&2 ;;
  release)
    [ -f "$S/claimed" ] || { echo "this agent does not hold a live claim on the task" >&2; exit 1; }
    rm -f "$S/claimed"; echo '{"task":{"status":"ready"}}' ;;
  send)
    [ -f "$S/claimed" ] || { echo "an agent speaks for a project only where it has planned a task or holds an unexpired claim there" >&2; exit 1; }
    id="thr-$(($(jq length "$S/threads.json") + 1))"
    if [ "$STUB_MUTATE" != messages ]; then
      jq -c --arg id "$id" --argjson p "$payload" '. + [{id: $id, from_project_id: $p.from_project_id, to_project_id: $p.to_project_id, status: "OPEN", subject: $p.subject}]' "$S/threads.json" | save threads.json
    fi
    echo "{\"thread\":{\"id\":\"$id\",\"status\":\"OPEN\"}}" ;;
  reply) printf '{"thread":{"id":%s,"status":"OPEN"}}' "$(printf '%s' "$payload" | jq '.thread_id')" ;;
  close)
    id=$(printf '%s' "$payload" | jq -r '.thread_id')
    jq -c --arg id "$id" 'map(if .id == $id then .status = "ANSWERED" else . end)' "$S/threads.json" | save threads.json
    echo "{\"thread\":{\"id\":\"$id\",\"status\":\"ANSWERED\"}}" ;;
  config) jq -n --rawfile m "$S/HERO.md" '{framing: "x", data: {exists: true, markdown: $m}}' ;;
  fleet) cat "$S/fleet.json" ;;
  register) echo '{"data":{"controls":[{"id":"C-1","checks":[{"id":"CHK-1"}]}],"unassigned":[]}}' ;;
  report-results)
    if [ "$STUB_MUTATE" = audit ]; then echo '{"recorded":0,"failing":0}'; else
      printf '%s' "$payload" | jq -c '{recorded: (.results | length), failing: ([.results[] | select(.state == "fail")] | length)}'; fi ;;
  *) echo "stub: unhandled $sub" >&2; exit 1 ;;
esac
STUB
chmod +x "$TMP/wayfare"
export STUB_DIR="$STUB"

# The stub's data is the fixture's, written out as the server would return it.
FIXTURE="$TMP/fixture"; make_fixture "$FIXTURE"
cp "$FIXTURE/check/HERO.md" "$STUB/HERO.md"
cat > "$STUB/items.json" <<'EOF'
[
{"number":1,"type":"task","title":"Parity bootstrap","status":"done","resolution":"shipped","shape":"structural","priority":"medium","goal_number":9,"rank":1,"sources":["src/one.go"],"depends_on":[],"description":"","log":[]},
{"id":"t-2","number":2,"type":"task","title":"Parity ready one","status":"ready","shape":"slice","priority":"medium","goal_number":9,"rank":2,"sources":["src/two.go"],"depends_on":[1],"description":"","log":[]},
{"number":3,"type":"task","title":"Parity ready two","status":"ready","shape":"slice","priority":"medium","goal_number":9,"rank":3,"sources":["src/three.go"],"depends_on":[2],"description":"## Subtasks\n\n- [ ] parity box","log":[]},
{"number":4,"type":"idea","title":"Parity parked idea","status":"accepted","description":"","log":[]},
{"number":5,"type":"task","title":"Parity wait on vendor","status":"ready","shape":"slice","priority":"medium","goal_number":9,"rank":5,"sources":["src/five.go"],"depends_on":[],"blocked_on":"vendor review","blocked_since":"2026-11-10T00:00:00Z","blocked":true,"description":"","log":[]},
{"number":9,"type":"goal","title":"Parity goal","status":"accepted","description":"","log":[]}
]
EOF
echo '[]' > "$STUB/threads.json"
cat > "$STUB/fleet.json" <<'EOF'
{"data":{"settings":{"org":"acme","template":"tpl","port_min":33000,"port_max":33099},"groups":[{"id":"g1","name":"Core"}],"rows":[{"project":{"slug":"check","group_id":"g1","port":33008,"what":"The check repo"}}]}}
EOF
export WAYFARE_CLI="$TMP/wayfare"
AUDIT_CHECK=CHK-1
NONCE="selftest$$"
FLEET_MD=$(fleet_md <(cat "$STUB/fleet.json"))
STUB_URL="https://wf.test/ws-1"

cp -R "$STUB" "$TMP/stub-pristine"
reset_stub() { rm -rf "$STUB"; cp -R "$TMP/stub-pristine" "$STUB"; }

STUB_MUTATE=""; export STUB_MUTATE
before_fail=$FAIL
parity "stub: " "$STUB_URL"
check "stub: every scenario passes against an unmutated stub, none of them vacuous" "$before_fail" "$FAIL"
check "stub: the scenarios compared (two checks each)" "$((2 * $(wc -w <<< "$SCENARIOS")))" "$((PASS - 1))"

# The mutations: each changes one server outcome and must fail exactly its own
# scenario. FAIL is rolled back after, because the failure is the expected result.
for m in write_item log messages audit build; do
  reset_stub; STUB_MUTATE=$m; export STUB_MUTATE
  p0=$PASS; f0=$FAIL
  out=$(parity "mutated($m): " "$STUB_URL")
  failed=$(grep -c '^FAIL  mutated' <<< "$out" || true)
  named=$(grep -c "^FAIL  mutated($m): $m:" <<< "$out" || true)
  PASS=$p0; FAIL=$f0
  check "mutation: changing the server's $m outcome fails the suite, naming that scenario" "1 1" "$failed $named"
done
STUB_MUTATE=""; export STUB_MUTATE

# An outcome changed on the local side fails the same way.
reset_stub
LOCAL_FIXTURE="$TMP/fixture-tampered"; rm -rf "$LOCAL_FIXTURE"; cp -R "$FIXTURE" "$LOCAL_FIXTURE"
sed -i.bak 's/^title: Parity ready one/title: Parity ready 1/' "$LOCAL_FIXTURE/check/.plans/items/002-parity-ready-one.md"
p0=$PASS; f0=$FAIL
out=$(parity "local-mutated: " "$STUB_URL")
PASS=$p0; FAIL=$f0
unset LOCAL_FIXTURE
check "mutation: a local outcome changed fails the suite, naming the scenarios that read it" "1 1" "$(grep -c '^FAIL  local-mutated: item_fields:' <<< "$out") $(grep -c '^FAIL  local-mutated: ready:' <<< "$out")"

# ---------- part 2: the live fleet, when asked -------------------------------------

if [ -z "${WAYFARE_PARITY:-}" ]; then
  echo "store-parity: live comparison skipped; set WAYFARE_PARITY=<origin>/<workspace id> to run both backends against a fleet"
else
  unset STUB_MUTATE
  export WAYFARE_CLI="$LIVE_CLI"
  FIXTURE="${WAYFARE_PARITY_FIXTURE:-$TMP/live-fixture}"
  mkdir -p "$FIXTURE"; make_fixture "$FIXTURE"
  live_ok=1
  if [ -n "${WAYFARE_PARITY_IMPORT:-}" ]; then
    echo "store-parity: importing the fixture"
    bash -c "$WAYFARE_PARITY_IMPORT" parity-import "$FIXTURE" || { FAIL=$((FAIL + 1)); live_ok=0; echo "FAIL  live: the fixture import failed"; }
  else
    echo "store-parity: no WAYFARE_PARITY_IMPORT; assuming the fleet already holds the fixture"
  fi
  if [ "$live_ok" = 1 ]; then
    probe="$FIXTURE/check"
    fleet_json=$(WAYFARE_STORE="$WAYFARE_PARITY" hero_srv_cli "$probe" fleet) || live_ok=0
    register_json=$(WAYFARE_STORE="$WAYFARE_PARITY" hero_srv_cli "$probe" register) || live_ok=0
    if [ "$live_ok" = 0 ]; then FAIL=$((FAIL + 1)); echo "FAIL  live: cannot read the fleet and register from $WAYFARE_PARITY"; fi
  fi
  if [ "$live_ok" = 1 ]; then
    FLEET_MD=$(printf '%s' "$fleet_json" | fleet_md /dev/stdin)
    AUDIT_CHECK=$(printf '%s' "$register_json" | jq -r '[(.data.controls[]?.checks[]?.id), (.data.unassigned[]?.id)] | map(select(. != null)) | first // empty')
    if [ -z "$AUDIT_CHECK" ]; then FAIL=$((FAIL + 1)); echo "FAIL  live: the register holds no check to record a result against"; else
      NONCE="$(date +%s)$$"
      parity "live: " "$WAYFARE_PARITY"
    fi
  fi
fi

echo "store-parity.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
