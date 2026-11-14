#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# The server backend of the store layer (hero-lib.sh, "the server backend"),
# without a server: a stub `wayfare` executable on WAYFARE_CLI records what it
# was asked and prints recorded JSON. Each case asserts both directions: what
# the function sent, and that its output matches what the local twin returns for
# the same data.
#
# Usage: bash scripts/hero-server.test.sh

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

URL="https://wf.test/ws-1"
STUB_DIR="$TMP/stub"; mkdir -p "$STUB_DIR"
export STUB_DIR
cat > "$TMP/wayfare" <<'STUB'
#!/usr/bin/env bash
sub=$1; shift
{ printf '%s url=%s ws=%s' "$sub" "${WAYFARE_URL:-}" "${WAYFARE_WORKSPACE:-}"; for a in "$@"; do printf ' [%s]' "$a"; done; echo; } >> "$STUB_DIR/calls.log"
while [ $# -gt 0 ]; do
  case $1 in --json) printf '%s' "$2" > "$STUB_DIR/payload.$sub"; shift ;; --number) num=$2; shift ;; esac
  shift
done
if [ -f "$STUB_DIR/$sub.fail" ]; then cat "$STUB_DIR/$sub.fail" >&2; exit 1; fi
f="$STUB_DIR/$sub${num:+.$num}.json"; [ -f "$f" ] || f="$STUB_DIR/$sub.json"
cat "$f"
STUB
chmod +x "$TMP/wayfare"
export WAYFARE_CLI="$TMP/wayfare"

srv() { ( export WAYFARE_STORE="$URL"; "$@" ); }
calls() { cat "$STUB_DIR/calls.log" 2>/dev/null; }
reset() { rm -f "$STUB_DIR/calls.log" "$STUB_DIR"/payload.* "$STUB_DIR"/*.fail; }

# ---------- fixtures: one fleet, two repos, the same data both ways -------------

FLEET="$TMP/fleet"
mkdir -p "$FLEET/.fleet/.git" "$FLEET/app/.plans/items" "$FLEET/app/.plans/inbox" "$FLEET/lib/.plans/items" "$FLEET/lib/.plans/inbox"
cat > "$FLEET/.fleet/FLEET.md" <<'EOF'
# Fleet

## Fleet

- name: test

## Repos

### app

- group: Core
- port: 33008

### lib

- group: Core
EOF
APP="$FLEET/app"; LIB_REPO="$FLEET/lib"
cat > "$APP/HERO.md" <<'EOF'
# Hero Configuration

## Repository

- default-branch: main # the trunk

## CI/CD

- platform: github-actions

## Deployment

- platform: fly
EOF
printf -- '---\nschema: 1\n---\n' > "$APP/.plans/PLAN.md"
I="$APP/.plans/items"
printf -- '---\nid: 1\ntype: task\ntitle: Bootstrap\nstatus: done\nshape: structural\n---\n' > "$I/001-bootstrap.md"
printf -- '---\nid: 2\ntype: task\ntitle: Add login\nstatus: ready\npriority: p1\nshape: story\nparent: 9\nrank: 2\ndepends_on: [1]\n---\n' > "$I/002-add-login.md"
printf -- '---\nid: 3\ntype: task\ntitle: Add logout\nstatus: ready\nshape: story\nparent: 9\nrank: 3\ndepends_on: [2]\n---\n' > "$I/003-add-logout.md"
printf -- '---\nid: 4\ntype: idea\ntitle: Parked thing\nstatus: accepted\n---\n' > "$I/004-parked-thing.md"
printf -- '---\nid: 9\ntype: goal\ntitle: The goal\nstatus: accepted\n---\n' > "$I/009-the-goal.md"

cat > "$STUB_DIR/projects.json" <<'EOF'
{"framing":"x","projects":[{"id":"p-app","slug":"app","name":"App"},{"id":"p-lib","slug":"lib","name":"Lib"}]}
EOF
cat > "$STUB_DIR/items.json" <<'EOF'
{"framing":"x","items":[
{"number":1,"type":"task","title":"Bootstrap","status":"done","shape":"structural"},
{"number":2,"type":"task","title":"Add login","status":"ready","priority":"high","shape":"story","goal_number":9,"rank":2,"depends_on":[1]},
{"number":3,"type":"task","title":"Add logout","status":"ready","shape":"story","goal_number":9,"rank":3,"depends_on":[2]},
{"number":4,"type":"idea","title":"Parked thing","status":"accepted"},
{"number":9,"type":"goal","title":"The goal","status":"accepted"}]}
EOF
cat > "$STUB_DIR/item.2.json" <<'EOF'
{"framing":"x","item":{"number":2,"type":"task","title":"Add login","status":"ready","priority":"high","shape":"story","goal_number":9,"rank":2,"depends_on":[1],"description":"## Context\n\nWhy.","log":[{"at":"2026-11-11T10:00:00Z","by":"rahul","tag":"note","body":"first"}]}}
EOF
# The local twin of item 2 with its body, kept apart so the writes below do not
# disturb the listing fixtures.
printf -- '---\nid: 2\ntype: task\ntitle: Add login\nstatus: ready\npriority: p1\nshape: story\nparent: 9\nrank: 2\ndepends_on: [1]\n---\n\n## Context\n\nWhy.\n\n## Log\n\n- 2026-11-11 (rahul) note: first\n' > "$TMP/item2-with-body.md"

# ---------- list ready ------------------------------------------------------

L=$(hero_ready_items "$APP/.plans" 2>&1)
reset; S=$(srv hero_ready_items "$APP/.plans" 2>&1)
check "ready: the server listing equals the local twin's on the same data" "$L" "$S"
check "ready: the local listing is the one we think (READY row, blocked row)" "READY   002-add-login.md — Add login" "$(printf '%s\n' "$L" | grep ^READY)"
check "ready: asked the projects and that project's items, under the URL's workspace" \
  "projects url=https://wf.test ws=ws-1
items url=https://wf.test ws=ws-1 [--project-id] [p-app]" "$(calls)"
check "ready: ideas parked agree" "$(hero_idea_count "$APP/.plans")" "$(srv hero_idea_count "$APP/.plans")"
check "ready: goal members agree" "$(hero_goal_members 9 "$APP/.plans" | tr '\n' ' ')" "$(srv hero_goal_members 9 "$APP/.plans" | tr '\n' ' ')"
check "ready: an explicit non-.plans store is read as given under the server" "$(hero_ready_items "$APP/.plans")" "$(srv hero_ready_items "$APP/.plans")"
cp -R "$APP/.plans" "$TMP/copied-store"
check "ready: a store path outside .plans is the caller's own and reads as given" "$L" "$(srv hero_ready_items "$TMP/copied-store" 2>&1)"

# ---------- read an item ------------------------------------------------------

reset
F=$(srv hero_item_file 2 "$APP")
check "item: the server's item file is byte for byte the local file" "$(cat "$TMP/item2-with-body.md")" "$(cat "$F")"
check "item: asked item 2 of project p-app" "item url=https://wf.test ws=ws-1 [--project-id] [p-app] [--number] [2]" "$(calls | tail -1)"
check "item: the file is read-only" "no" "$([ -w "$F" ] && echo yes || echo no)"
check "item: a field reads the same through the same reader" "p1" "$(hero_item_field "$F" priority)"
check "item: the local file path is what hero_item_file returns without a server" "$I/002-add-login.md" "$(hero_item_file 2 "$APP")"

# ---------- write an item, append a log line -----------------------------------

reset
cat > "$STUB_DIR/update-item.json" <<'EOF'
{"item":{"number":2,"title":"Add login","priority":"high"}}
EOF
W="$TMP/w"; cp -R "$FLEET" "$W"
check "set: local writes the field and prints it" "priority: p2" "$(hero_item_set 2 priority p2 "$W/app")"
check "set: local file holds it" "p2" "$(hero_item_field "$W/app/.plans/items/002-add-login.md" priority)"
reset; echo '{"item":{"number":2,"priority":"medium"}}' > "$STUB_DIR/update-item.json"
check "set: server prints the same line for the same write" "priority: p2" "$(srv hero_item_set 2 priority p2 "$APP")"
check "set: server was sent medium for p2, on project p-app item 2" '{"project_id":"p-app","number":2,"priority":"medium"}' "$(jq -c . "$STUB_DIR/payload.update-item")"
echo '{"item":{"number":2,"depends_on":[1,5]}}' > "$STUB_DIR/update-item.json"
srv hero_item_set 2 depends_on "[1, 5]" "$APP" >/dev/null
check "set: a list goes as JSON numbers" '{"project_id":"p-app","number":2,"depends_on":[1,5]}' "$(jq -c . "$STUB_DIR/payload.update-item")"
echo '{"item":{"number":2,"goal_number":9}}' > "$STUB_DIR/update-item.json"
check "set: parent is the server's goal_number" "parent: 9" "$(srv hero_item_set 2 parent 9 "$APP")"
check "set: a title that looks like a number stays a string" "string" "$(echo '{"item":{"number":2,"title":"2026"}}' > "$STUB_DIR/update-item.json"; srv hero_item_set 2 title 2026 "$APP" >/dev/null; jq -r '.title | type' "$STUB_DIR/payload.update-item")"
hero_item_set 2 status "done" "$W/app" >/dev/null 2>&1; check "set: a status is not a field write (rc 2)" "2" "$?"
check "set: the file is untouched by the refusal" "ready" "$(hero_item_field "$W/app/.plans/items/002-add-login.md" status)"

reset; echo '{"item":{"number":2,"log":[{"at":"2026-11-14T09:00:00Z","by":"agent","tag":"note","body":"hello world"}]}}' > "$STUB_DIR/log.json"
check "log: local prints TAG: TEXT" "note: hello world" "$(hero_item_log 2 note "hello world" "$W/app")"
check "log: local appended a dated line to the end of ## Log" "- $(date +%Y-%m-%d) (agent) note: hello world" "$(tail -1 "$W/app/.plans/items/002-add-login.md")"
check "log: server prints the same line" "note: hello world" "$(srv hero_item_log 2 note "hello world" "$APP")"
check "log: server was sent tag and text for p-app item 2" '{"project_id":"p-app","number":2,"tag":"note","text":"hello world"}' "$(jq -c . "$STUB_DIR/payload.log")"

# ---------- messages -----------------------------------------------------------

reset
ID=$(hero_msg_send lib request "Need X" "Please do X" "$W/app")
case "$ID" in m-??????) check "send: local prints a message id" ok ok ;; *) check "send: local prints a message id" "m-xxxxxx" "$ID" ;; esac
check "send: local deposited it in the recipient's inbox" "yes" "$([ -f "$W/lib/.plans/inbox/$ID.md" ] && echo yes || echo no)"
check "send: the recipient counts it unread" "1" "$(hero_inbox_count "$W/lib/.plans")"
echo '{"thread":{"id":"thr-1","status":"OPEN"}}' > "$STUB_DIR/send.json"
check "send: server prints the thread id" "thr-1" "$(srv hero_msg_send lib request "Need X" "Please do X" "$APP")"
check "send: server was sent both projects, kind, subject, body" '{"from_project_id":"p-app","to_project_id":"p-lib","kind":"request","subject":"Need X","body":"Please do X"}' "$(jq -c . "$STUB_DIR/payload.send")"
echo '{"threads":[{"id":"thr-1","to_project_id":"p-lib","status":"OPEN"},{"id":"thr-2","to_project_id":"p-lib","status":"CLAIMED"},{"id":"thr-3","to_project_id":"p-app","status":"OPEN"}]}' > "$STUB_DIR/messages.json"
check "inbox: server counts the open threads addressed to this repo" "1" "$(srv hero_inbox_count "$LIB_REPO/.plans")"
check "inbox: and the claimed ones" "1" "$(srv hero_inbox_count "$LIB_REPO/.plans" claimed)"

check "reply: local prints the id" "$ID" "$(hero_msg_reply "$ID" "on it" "$W/lib")"
check "reply: local wrote a comment" "- $(date +%Y-%m-%d) (lib): on it" "$(tail -1 "$W/lib/.plans/inbox/$ID.md")"
echo '{"thread":{"id":"thr-1","status":"OPEN"}}' > "$STUB_DIR/reply.json"
check "reply: server prints the thread id" "thr-1" "$(srv hero_msg_reply thr-1 "on it" "$LIB_REPO")"
check "reply: server was sent the thread and body as lib" '{"project_id":"p-lib","thread_id":"thr-1","body":"on it"}' "$(jq -c . "$STUB_DIR/payload.reply")"
L=$(hero_msg_close "$ID" answered "done" "$W/lib")
check "close: local prints ID OUTCOME" "$ID answered" "$L"
check "close: the recipient no longer counts it unread" "0" "$(hero_inbox_count "$W/lib/.plans")"
echo '{"thread":{"id":"thr-1","status":"ANSWERED"}}' > "$STUB_DIR/close.json"
check "close: server prints the same shape" "thr-1 answered" "$(srv hero_msg_close thr-1 answered "done" "$LIB_REPO")"
check "close: server was sent outcome and reason" '{"project_id":"p-lib","thread_id":"thr-1","outcome":"answered","reason":"done"}' "$(jq -c . "$STUB_DIR/payload.close")"

# ---------- HERO.md fields -------------------------------------------------------

reset
jq -n --rawfile m "$APP/HERO.md" '{framing: "x", data: {exists: true, markdown: $m}}' > "$STUB_DIR/config.json"
check "config: hero_field agrees" "$(hero_field default-branch "$APP")" "$(srv hero_field default-branch "$APP")"
check "config: a repeated key in a named block agrees" "$(hero_field_in "$APP" platform "## Deployment")" "$(srv hero_field_in "$APP" platform "## Deployment")"
check "config: sections agree" "$(hero_config_sections "$APP" "CI/CD")" "$(srv hero_config_sections "$APP" "CI/CD")"
check "config: the whole file agrees" "$(hero_config_show "$APP")" "$(srv hero_config_show "$APP")"
check "config: asked the config of p-app" "config url=https://wf.test ws=ws-1 [--project-id] [p-app]" "$(calls | grep '^config' | head -1)"
echo '{"framing":"x","data":{}}' > "$STUB_DIR/config.json"
srv hero_config_exists "$APP"; check "config: a project with no config there reads as no config" "1" "$?"
srv hero_field default-branch "$APP" >/dev/null 2>&1; check "config: and a field of it is absent (rc 1)" "1" "$?"

# ---------- fleet rows ----------------------------------------------------------

reset
cat > "$STUB_DIR/fleet.json" <<'EOF'
{"framing":"x","data":{"groups":[{"id":"g1","name":"Core"}],"rows":[{"project":{"slug":"app","groupId":"g1","port":33008}},{"project":{"slug":"lib","groupId":"g1"}}]}}
EOF
check "fleet: rows agree with the map's" "$(hero_fleet_repos "$FLEET")" "$(srv hero_fleet_repos "$FLEET")"
check "fleet: a repo's port agrees" "$(hero_fleet_repo_field app port "$FLEET")" "$(srv hero_fleet_repo_field app port "$FLEET")"
check "fleet: a repo's group agrees" "$(hero_fleet_repo_field app group "$FLEET")" "$(srv hero_fleet_repo_field app group "$FLEET")"
srv hero_fleet_repo_field app register "$FLEET" >/dev/null 2>&1; check "fleet: a key the server row lacks fails, never empty-success" "1" "$?"

# ---------- audit results ---------------------------------------------------------

reset
RES='[{"check_id":"A-1","state":"pass"},{"check_id":"A-2","state":"fail"}]'
echo '{"recorded":2,"failing":1}' > "$STUB_DIR/report-results.json"
check "audit: local counts the same" '{"recorded":2,"failing":1}' "$(hero_audit_record app "$RES" "$APP" 2>/dev/null)"
check "audit: server answers the same" '{"recorded":2,"failing":1}' "$(srv hero_audit_record app "$RES" "$APP")"
check "audit: server was sent the repo and the results" "{\"repo\":\"app\",\"results\":$RES}" "$(jq -c . "$STUB_DIR/payload.report-results")"

# ---------- a failing CLI is an error naming the server, never an empty result -----

fails() { # NAME CMD... : rc != 0, stdout empty, stderr names the server URL
  local name=$1 out err rc; shift
  err=$(srv "$@" 2>&1 >"$TMP/out"); rc=$?
  out=$(cat "$TMP/out")
  check "fail: $name returns non-zero" "1" "$([ "$rc" -ne 0 ] && echo 1 || echo "rc=$rc")"
  check "fail: $name prints nothing on stdout" "" "$out"
  case "$err" in *"$URL"*) check "fail: $name names the server and the CLI's reason" ok ok ;; *) check "fail: $name names the server" "mentions $URL" "$err" ;; esac
  case "$err" in *"boom: token rejected"*) ;; *) check "fail: $name carries the CLI's stderr" "contains boom" "$err" ;; esac
}
reset
for s in projects items item config fleet messages send reply close update-item log report-results; do echo "boom: token rejected" > "$STUB_DIR/$s.fail"; done
fails ready hero_ready_items "$APP/.plans"
fails item_file hero_item_file 2 "$APP"
fails item_set hero_item_set 2 priority p1 "$APP"
fails item_log hero_item_log 2 note x "$APP"
fails idea_count hero_idea_count "$APP/.plans"
fails msg_send hero_msg_send lib request s b "$APP"
fails inbox_count hero_inbox_count "$APP/.plans"
fails config_file hero_config_file "$APP"
fails field hero_field default-branch "$APP"
fails fleet_repos hero_fleet_repos "$FLEET"
fails audit hero_audit_record app "$RES" "$APP"
rm -f "$STUB_DIR"/*.fail

# a missing CLI, a missing workspace, a repo with no project
( export WAYFARE_STORE="$URL" WAYFARE_CLI="$TMP/nope"; hero_ready_items "$APP/.plans" ) >/dev/null 2>"$TMP/err"; check "fail: a missing CLI is an error (rc 1)" "1" "$?"
case "$(cat "$TMP/err")" in *"$URL"*"not on PATH"*) check "fail: a missing CLI names the server" ok ok ;; *) check "fail: a missing CLI names the server" "names $URL" "$(cat "$TMP/err")" ;; esac
( export WAYFARE_STORE="https://wf.test"; hero_ready_items "$APP/.plans" ) >/dev/null 2>"$TMP/err"; check "fail: a URL with no workspace is an error" "1" "$?"
case "$(cat "$TMP/err")" in *"workspace id"*"WAYFARE_STORE"*) check "fail: and it names the switch" ok ok ;; *) check "fail: and it names the switch" "names WAYFARE_STORE" "$(cat "$TMP/err")" ;; esac
mkdir -p "$FLEET/ghost/.plans/items"
srv hero_ready_items "$FLEET/ghost/.plans" >/dev/null 2>"$TMP/err"; check "fail: a repo with no project is an error" "1" "$?"
case "$(cat "$TMP/err")" in *"ghost"*"$URL"*|*"$URL"*"ghost"*) check "fail: and it names the repo and the server" ok ok ;; *) check "fail: and it names the repo and the server" "names ghost" "$(cat "$TMP/err")" ;; esac

# ---------- functions with no server variant fail loudly, never read the files ----

for fn in "hero_plan_field schema $APP/.plans" "hero_goal_candidates 9 $APP/.plans" "hero_items_dir $APP" "hero_inbox_exists $APP" \
          "hero_msg_find $APP/.plans lib x" "hero_config_commit_time $APP" \
          "hero_check_staleness $APP" "hero_fleet_field name $FLEET"; do
  name=${fn%% *}
  # shellcheck disable=SC2086
  srv $fn >"$TMP/out" 2>"$TMP/err"; rc=$?
  check "loud: $name fails under the server" "1" "$([ "$rc" -ne 0 ] && echo 1 || echo "rc=$rc")"
  check "loud: $name prints nothing on stdout" "" "$(cat "$TMP/out")"
  case "$(cat "$TMP/err")" in *"$name"*"Wayfare server at $URL"*) check "loud: $name names itself and the server" ok ok ;; *) check "loud: $name names itself and the server" "names both" "$(cat "$TMP/err")" ;; esac
done

# ---------- local stays the default ------------------------------------------------

check "default: with no switch a field reads the file" "main" "$(hero_field default-branch "$APP")"
check "default: with no switch the item file is the local one" "$I/002-add-login.md" "$(hero_item_file 2 "$APP")"
check "default: WAYFARE_STORE=local is local" "$I/002-add-login.md" "$(WAYFARE_STORE=local hero_item_file 2 "$APP")"

echo "hero-server.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
