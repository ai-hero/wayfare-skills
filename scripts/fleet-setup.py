#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Machine setup for a fleet, from the register's .fleet/setup.yaml.

    uv run scripts/fleet-setup.py [--file F] validate
    uv run scripts/fleet-setup.py [--file F] plan [--json] [--confirmed ID]...
    uv run scripts/fleet-setup.py [--file F] check [--json]
    uv run scripts/fleet-setup.py [--file F] apply --group G [--confirmed ID]...
    uv run scripts/fleet-setup.py [--file F] verify [--json]

F defaults to ./.fleet/setup.yaml. The schema is docs/SETUP-YAML.md.

plan, check and verify change nothing. apply runs one group's missing steps in
file order and stops at the first person step that is still open; run it again
with --confirmed ID once the person has done that step. Every step checks
before it acts, so a second apply runs nothing.

Exit: 0 done, 1 something missing or failed, 2 invalid file or usage,
10 apply stopped at a person step.
"""

import argparse
import json
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys

import yaml

PLATFORMS = ("macos-arm64",)
KINDS = ("brew", "cask", "pipx", "installer", "git", "shell", "path",
         "marketplace", "plugin", "mcp", "person")
PERSON_WHY = ("password", "browser", "secret", "gui", "choice")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PKG_RE = re.compile(r"^[A-Za-z0-9@._+/-]+$")
CMD_RE = re.compile(r"^[A-Za-z0-9._+-]+$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
GIT_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(\.[A-Za-z0-9-]+)+$")
PLUGIN_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")
HEADER_RE = re.compile(r"^[A-Za-z0-9-]+$")
# A launcher fetches the package at run time with the person's credentials in
# reach, so an unpinned one installs whatever was published a minute ago.
LAUNCHERS = {"npx", "bunx", "pnpx", "uvx"}
PINNED_RE = re.compile(r"^(@?[^@=\s]+)(@|==)\d[\w.+-]*$")


class Invalid(Exception):
    pass


class Errors:
    def __init__(self):
        self.items = []

    def add(self, where, msg):
        self.items.append(f"{where}: {msg}")


def _keys(errs, where, obj, required, optional=()):
    if not isinstance(obj, dict):
        errs.add(where, f"expected a mapping, got {type(obj).__name__}")
        return False
    allowed = set(required) | set(optional)
    for k in obj:
        if k not in allowed:
            errs.add(where, f"unknown key {k!r} (expected: {', '.join(sorted(allowed))})")
    for k in required:
        if k not in obj:
            errs.add(where, f"missing required key {k!r}")
    return True


def _str(errs, where, v, pattern=None, what="a string"):
    if not isinstance(v, str) or not v.strip():
        errs.add(where, f"expected {what}, got {type(v).__name__} {v!r}")
        return False
    if pattern and not pattern.match(v):
        errs.add(where, f"{v!r} is not a valid value")
        return False
    return True


def _str_list(errs, where, v, pattern=None):
    if not isinstance(v, list) or not v:
        errs.add(where, f"expected a non-empty list, got {type(v).__name__}")
        return
    for i, item in enumerate(v):
        _str(errs, f"{where}[{i}]", item, pattern)


def _home_file(errs, where, v):
    if not _str(errs, where, v):
        return
    if not v.startswith("~/") or ".." in pathlib.PurePosixPath(v).parts:
        errs.add(where, f"{v!r} must be a file under ~/ with no '..'")


def _check_mcp(errs, where, m):
    if not _keys(errs, where, m, ("name", "transport"),
                 ("scope", "command", "args", "url", "secrets")):
        return
    _str(errs, f"{where}.name", m.get("name"), NAME_RE)
    if m.get("scope", "user") != "user":
        errs.add(f"{where}.scope", "only 'user' is machine-level; a project server belongs in that repo")
    t = m.get("transport")
    if t == "stdio":
        for k in ("url",):
            if k in m:
                errs.add(where, f"{k!r} is for transport http")
        if _str(errs, f"{where}.command", m.get("command"), CMD_RE):
            args = m.get("args", [])
            if args:
                _str_list(errs, f"{where}.args", args)
            if m["command"] in LAUNCHERS and isinstance(args, list):
                pkgs = [a for a in args if isinstance(a, str) and not a.startswith("-")]
                if not pkgs or not PINNED_RE.match(pkgs[0]) or pkgs[0].endswith("@latest"):
                    errs.add(f"{where}.args", f"{m['command']} must run an exact version (pkg@1.2.3), got {pkgs[:1]}")
        secrets = m.get("secrets", [])
        if secrets:
            _str_list(errs, f"{where}.secrets", secrets, ENV_RE)
    elif t == "http":
        for k in ("command", "args"):
            if k in m:
                errs.add(where, f"{k!r} is for transport stdio")
        if _str(errs, f"{where}.url", m.get("url")) and not m["url"].startswith("https://"):
            errs.add(f"{where}.url", "must be https://")
        secrets = m.get("secrets", [])
        if secrets and not isinstance(secrets, list):
            errs.add(f"{where}.secrets", "expected a list")
        elif secrets:
            for i, s in enumerate(secrets):
                w = f"{where}.secrets[{i}]"
                if _keys(errs, w, s, ("header", "env"), ("prefix",)):
                    _str(errs, f"{w}.header", s.get("header"), HEADER_RE)
                    _str(errs, f"{w}.env", s.get("env"), ENV_RE)
                    if "prefix" in s and not isinstance(s["prefix"], str):
                        errs.add(f"{w}.prefix", "expected a string")
    else:
        errs.add(f"{where}.transport", f"expected stdio or http, got {t!r}")


def _check_step(errs, where, step, marketplaces):
    if not isinstance(step, dict) or len(step) != 1:
        got = list(step) if isinstance(step, dict) else type(step).__name__
        errs.add(where, f"a step is a mapping with exactly one of {', '.join(KINDS)}; got {got}")
        return
    (kind, body), = step.items()
    w = f"{where}.{kind}"
    if kind not in KINDS:
        errs.add(where, f"unknown step kind {kind!r} (expected: {', '.join(KINDS)})")
    elif kind in ("brew", "cask", "pipx"):
        _str_list(errs, w, body, PKG_RE)
    elif kind == "installer":
        if _keys(errs, w, body, ("name", "check", "run")):
            _str(errs, f"{w}.name", body.get("name"))
            _str(errs, f"{w}.check", body.get("check"), CMD_RE, "a command name")
            _str(errs, f"{w}.run", body.get("run"))
    elif kind == "git":
        if not isinstance(body, dict) or not body:
            errs.add(w, "expected a mapping of git config key to value")
        else:
            for k, v in body.items():
                if not isinstance(k, str) or not GIT_KEY_RE.match(k):
                    errs.add(w, f"{k!r} is not a git config key")
                if not isinstance(v, str):
                    errs.add(f"{w}.{k}", f"expected a string, got {type(v).__name__} {v!r}; quote it")
    elif kind in ("shell", "path"):
        field = "lines" if kind == "shell" else "entries"
        if _keys(errs, w, body, ("file", field)):
            _home_file(errs, f"{w}.file", body.get("file"))
            _str_list(errs, f"{w}.{field}", body.get(field))
    elif kind == "marketplace":
        if not isinstance(body, list) or not body:
            errs.add(w, "expected a non-empty list of {name, source}")
        else:
            for i, m in enumerate(body):
                if _keys(errs, f"{w}[{i}]", m, ("name", "source")):
                    if _str(errs, f"{w}[{i}].name", m.get("name"), PKG_RE):
                        marketplaces.add(m["name"])
                    _str(errs, f"{w}[{i}].source", m.get("source"), PKG_RE)
    elif kind == "plugin":
        _str_list(errs, w, body, PLUGIN_RE)
        if isinstance(body, list):
            for i, p in enumerate(body):
                if isinstance(p, str) and "@" in p and p.split("@", 1)[1] not in marketplaces:
                    errs.add(f"{w}[{i}]", f"marketplace {p.split('@', 1)[1]!r} is not declared by an earlier marketplace step")
    elif kind == "mcp":
        _check_mcp(errs, w, body)
    elif kind == "person":
        if _keys(errs, w, body, ("title", "why"), ("run", "check", "terminal")):
            _str(errs, f"{w}.title", body.get("title"))
            if body.get("why") not in PERSON_WHY:
                errs.add(f"{w}.why", f"expected one of {', '.join(PERSON_WHY)}, got {body.get('why')!r}")
            for k in ("run", "check"):
                if k in body:
                    _str(errs, f"{w}.{k}", body[k])
            term = body.get("terminal", "session")
            if term not in ("session", "separate"):
                errs.add(f"{w}.terminal", f"expected session or separate, got {term!r}")
            if body.get("why") == "secret" and term != "separate":
                errs.add(f"{w}.terminal", "a step that takes a secret runs in a separate terminal")


def validate(doc):
    errs = Errors()
    if not isinstance(doc, dict):
        raise Invalid(["file: expected a mapping at the top level"])
    _keys(errs, "file", doc, ("version", "platform", "workspace", "groups"), ("notes", "verify"))
    if "version" in doc and (type(doc["version"]) is not int or doc["version"] != 1):
        errs.add("version", f"expected 1, got {doc['version']!r}")
    if "platform" in doc and doc["platform"] not in PLATFORMS:
        errs.add("platform", f"expected one of {', '.join(PLATFORMS)}, got {doc['platform']!r}")
    if "workspace" in doc and _str(errs, "workspace", doc["workspace"]):
        if not doc["workspace"].startswith(("~/", "/")):
            errs.add("workspace", "must be absolute or start with ~/")
    if "notes" in doc:
        _str_list(errs, "notes", doc["notes"])
    marketplaces = set()
    groups = doc.get("groups")
    if "groups" in doc and (not isinstance(groups, list) or not groups):
        errs.add("groups", "expected a non-empty list")
    elif isinstance(groups, list):
        seen = set()
        for gi, g in enumerate(groups):
            gw = f"groups[{gi}]"
            if not _keys(errs, gw, g, ("name", "title", "steps"), ("optional", "ask", "notes")):
                continue
            if _str(errs, f"{gw}.name", g.get("name"), NAME_RE):
                if g["name"] in seen:
                    errs.add(f"{gw}.name", f"duplicate group {g['name']!r}")
                seen.add(g["name"])
                gw = f"groups[{gi}]({g['name']})"
            _str(errs, f"{gw}.title", g.get("title"))
            opt = g.get("optional", False)
            if not isinstance(opt, bool):
                errs.add(f"{gw}.optional", f"expected true or false, got {opt!r}")
            if opt is True and not isinstance(g.get("ask"), str):
                errs.add(f"{gw}.ask", "an optional group needs the question to ask")
            if opt is not True and "ask" in g:
                errs.add(f"{gw}.ask", "only an optional group is asked about")
            if "notes" in g:
                _str_list(errs, f"{gw}.notes", g["notes"])
            steps = g.get("steps")
            if not isinstance(steps, list) or not steps:
                errs.add(f"{gw}.steps", "expected a non-empty list")
                continue
            for si, s in enumerate(steps):
                _check_step(errs, f"{gw}.steps[{si}]", s, marketplaces)
    if "verify" in doc:
        v = doc["verify"]
        if not isinstance(v, list):
            errs.add("verify", "expected a list")
        else:
            for i, c in enumerate(v):
                if _keys(errs, f"verify[{i}]", c, ("name", "run", "passes")):
                    for k in ("name", "run", "passes"):
                        _str(errs, f"verify[{i}].{k}", c.get(k))
    if errs.items:
        raise Invalid(errs.items)
    return doc


def load(path):
    try:
        text = pathlib.Path(path).read_text()
    except OSError as e:
        raise Invalid([f"{path}: cannot read ({e.strerror})"])
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise Invalid([f"{path}: not YAML: {e}"])
    return validate(doc)


def home():
    return pathlib.Path(os.environ["HOME"])


def expand(p):
    p = p.replace("$HOME", str(home()))
    if p == "~" or p.startswith("~/"):
        p = str(home()) + p[1:]
    return p


def path_line(entry):
    return f'export PATH="{entry}:$PATH"'


def mcp_command(m):
    cmd = ["claude", "mcp", "add", "--scope", "user"]
    secrets = m.get("secrets") or []
    if m["transport"] == "http":
        cmd += ["--transport", "http", m["name"], m["url"]]
        parts = [shlex.join(cmd)]
        for s in secrets:
            parts.append(f'--header "{s["header"]}: {s.get("prefix", "")}${s["env"]}"')
        return " ".join(parts)
    # The name goes before -e: -e takes every value after it, so a name placed
    # later is read as another environment entry.
    parts = [shlex.join(cmd + [m["name"]])]
    for env in secrets:
        parts.append(f'-e {env}="${env}"')
    parts.append("-- " + shlex.join([m["command"], *m.get("args", [])]))
    return " ".join(parts)


def secret_script(m):
    """The block a person pastes into a separate terminal. It names each secret
    and never holds one: read -rs keeps the value off the screen and out of
    shell history, and unset drops it once claude has stored it."""
    names = [s if isinstance(s, str) else s["env"] for s in m["secrets"]]
    lines = [f"claude mcp get {m['name']} >/dev/null 2>&1 || {{"]
    for n in names:
        lines.append(f"  printf '%s: ' {n}; read -rs {n}; echo")
    lines.append("  " + mcp_command(m))
    lines.append(f"  unset {' '.join(names)}")
    lines.append("}")
    return "\n".join(lines)


class Machine:
    """Read-only probes of this machine, each run at most once."""

    def __init__(self, extra_path):
        self.env = dict(os.environ)
        self.env["PATH"] = os.pathsep.join([*extra_path, self.env.get("PATH", "")])
        self.cache = {}

    def which(self, cmd):
        return shutil.which(cmd, path=self.env["PATH"])

    def run(self, argv, quiet=True, timeout=120):
        exe = self.which(argv[0]) if not argv[0].startswith("/") else argv[0]
        if not exe:
            return None
        try:
            # Output is discarded, not captured: `claude mcp get` prints a
            # server's environment, secret values included.
            r = subprocess.run([exe, *argv[1:]], env=self.env, timeout=timeout,
                               stdout=subprocess.DEVNULL if quiet else subprocess.PIPE,
                               stderr=subprocess.DEVNULL if quiet else subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r

    def lines(self, key, argv):
        if key not in self.cache:
            r = self.run(argv, quiet=False)
            self.cache[key] = r.stdout.splitlines() if r and r.returncode == 0 else None
        return self.cache[key]

    def brew_has(self, cask, name):
        got = self.lines(("brew", cask), ["brew", "list", "--cask" if cask else "--formula", "-1"])
        return got is not None and name.rsplit("/", 1)[-1] in {x.strip() for x in got}

    def pipx_has(self, name):
        got = self.lines("pipx", ["pipx", "list", "--short"])
        return got is not None and name in {x.split()[0] for x in got if x.strip()}

    def claude_json(self, key, argv, field):
        got = self.lines(key, argv)
        if got is None:
            return set()
        try:
            return {x.get(field) for x in json.loads("\n".join(got))}
        except (ValueError, AttributeError):
            return set()

    def marketplace_has(self, name):
        return name in self.claude_json("mkt", ["claude", "plugin", "marketplace", "list", "--json"], "name")

    def plugin_has(self, pid):
        return pid in self.claude_json("plg", ["claude", "plugin", "list", "--json"], "id")

    def mcp_has(self, name):
        r = self.run(["claude", "mcp", "get", name], timeout=60)
        return bool(r and r.returncode == 0)

    def git_has(self, key, value):
        r = self.run(["git", "config", "--global", "--get", key], quiet=False)
        return bool(r and r.returncode == 0 and r.stdout.strip() == value)

    def shell_ok(self, cmd):
        r = self.run(["/bin/bash", "-c", cmd], timeout=120)
        return bool(r and r.returncode == 0)

    def forget(self):
        self.cache.clear()


def file_has_line(path, line):
    p = pathlib.Path(expand(path))
    return p.is_file() and line in p.read_text().splitlines()


def append_line(path, line):
    p = pathlib.Path(expand(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text() if p.exists() else ""
    with p.open("a") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")


def entries(doc):
    """The plan: one entry per thing to install or set, in file order."""
    for g in doc["groups"]:
        n = 0
        for step in g["steps"]:
            (kind, body), = step.items()
            items = []
            if kind in ("brew", "cask", "pipx", "plugin"):
                items = [(kind, x) for x in body]
            elif kind == "marketplace":
                items = [(kind, m) for m in body]
            elif kind == "git":
                items = [(kind, (k, v)) for k, v in body.items()]
            elif kind == "shell":
                items = [(kind, (body["file"], ln)) for ln in body["lines"]]
            elif kind == "path":
                items = [(kind, (body["file"], path_line(e))) for e in body["entries"]]
            else:
                items = [(kind, body)]
            for kind_, item in items:
                n += 1
                yield g, f"{g['name']}.{n}", kind_, item


def describe(kind, item):
    """(label, command, person-fields) for one entry. Commands never carry a
    secret value: the file has no field that can hold one."""
    if kind == "brew":
        return f"brew {item}", f"brew install {item}", None
    if kind == "cask":
        return f"cask {item}", f"brew install --cask {item}", None
    if kind == "pipx":
        return f"pipx {item}", f"pipx install {item}", None
    if kind == "installer":
        return f"installer {item['name']} (skipped when `{item['check']}` is on PATH)", item["run"], None
    if kind == "git":
        k, v = item
        return f"git {k}", f"git config --global {shlex.quote(k)} {shlex.quote(v)}", None
    if kind in ("shell", "path"):
        f, ln = item
        return f"{kind} {f}: {ln}", f"append to {f}: {ln}", None
    if kind == "marketplace":
        return f"marketplace {item['name']}", f"claude plugin marketplace add {item['source']}", None
    if kind == "plugin":
        return f"plugin {item}", f"claude plugin install {item}", None
    if kind == "mcp":
        if item.get("secrets"):
            return (f"mcp {item['name']} ({item['transport']}, needs {', '.join(s if isinstance(s, str) else s['env'] for s in item['secrets'])})",
                    secret_script(item),
                    {"why": "secret", "terminal": "separate",
                     "title": f"Add the {item['name']} MCP server; it needs a secret only you should type"})
        return f"mcp {item['name']} ({item['transport']})", mcp_command(item), None
    if kind == "person":
        return (f"person: {item['title']}", item.get("run", ""),
                {"why": item["why"], "terminal": item.get("terminal", "session"), "title": item["title"]})
    raise AssertionError(kind)


def status(m, kind, item, confirmed, eid):
    if kind in ("brew", "cask"):
        return m.brew_has(kind == "cask", item)
    if kind == "pipx":
        return m.pipx_has(item)
    if kind == "installer":
        return m.which(item["check"]) is not None
    if kind == "git":
        return m.git_has(*item)
    if kind in ("shell", "path"):
        return file_has_line(*item)
    if kind == "marketplace":
        return m.marketplace_has(item["name"])
    if kind == "plugin":
        return m.plugin_has(item)
    if kind == "mcp":
        return m.mcp_has(item["name"])
    if kind == "person":
        if eid in confirmed:
            return True
        return bool(item.get("check")) and m.shell_ok(item["check"])
    raise AssertionError(kind)


def machine_for(doc):
    extra = []
    for g in doc["groups"]:
        for step in g["steps"]:
            if "path" in step:
                extra += [expand(e) for e in step["path"]["entries"]]
    return Machine(extra)


def platform_now():
    # The override exists for the test suite, which also runs on Linux CI.
    forced = os.environ.get("FLEET_SETUP_PLATFORM")
    if forced:
        return forced
    sysname = {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    mach = {"aarch64": "arm64"}.get(platform.machine(), platform.machine())
    return f"{sysname}-{mach}"


def build_plan(doc, path, confirmed=()):
    m = machine_for(doc)
    ws = expand(doc["workspace"])
    plan = {
        "file": str(path), "version": doc["version"], "platform": doc["platform"],
        "platform_here": platform_now(), "workspace": doc["workspace"],
        "workspace_path": ws, "workspace_exists": os.path.isdir(ws),
        "notes": doc.get("notes", []), "groups": [], "verify": doc.get("verify", []),
    }
    plan["platform_ok"] = plan["platform_here"] == doc["platform"]
    by_name = {}
    for g, eid, kind, item in entries(doc):
        if g["name"] not in by_name:
            by_name[g["name"]] = {"name": g["name"], "title": g["title"],
                                  "optional": g.get("optional", False), "ask": g.get("ask"),
                                  "notes": g.get("notes", []), "steps": []}
            plan["groups"].append(by_name[g["name"]])
        label, command, person = describe(kind, item)
        done = status(m, kind, item, set(confirmed), eid)
        e = {"id": eid, "kind": kind, "label": label, "command": command,
             "status": "present" if done else ("person" if person else "missing")}
        if person:
            e["person"] = person
        by_name[g["name"]]["steps"].append(e)
    return plan


MARK = {"present": "[ok]    ", "missing": "[todo]  ", "person": "[person]"}


def print_plan(plan):
    print(f"fleet setup: {plan['file']} (version {plan['version']}, {plan['platform']})")
    print(f"platform: {'ok' if plan['platform_ok'] else 'MISMATCH, this machine is ' + plan['platform_here']}")
    print(f"workspace: {plan['workspace']} -> {plan['workspace_path']}"
          f" ({'exists' if plan['workspace_exists'] else 'missing'})")
    for n in plan["notes"]:
        print(f"note: {n}")
    for g in plan["groups"]:
        print()
        print(f"== {g['name']}{' (optional)' if g['optional'] else ''}: {g['title']}")
        if g["optional"]:
            print(f"   ask: {g['ask']}")
        for n in g["notes"]:
            print(f"   note: {n}")
        for s in g["steps"]:
            print(f"  {MARK[s['status']]} {s['id']:<14} {s['label']}")
            if s["status"] != "present" and s["command"]:
                for ln in s["command"].splitlines():
                    print(f"             {ln}")
            if "person" in s and s["status"] != "present":
                p = s["person"]
                print(f"             (needs {p['why']}; {'separate terminal' if p['terminal'] == 'separate' else 'this session'})")
    if plan["verify"]:
        print()
        print("verify:")
        for v in plan["verify"]:
            print(f"  - {v['name']}: {v['run']}  (passes: {v['passes']})")
    c = summary(plan)
    print()
    print(f"summary: {c['present']} present, {c['missing']} to run, {c['person']} person steps open;"
          f" optional groups: {', '.join(c['optional']) or 'none'}")


def summary(plan):
    c = {"present": 0, "missing": 0, "person": 0, "required_open": 0,
         "optional": [g["name"] for g in plan["groups"] if g["optional"]]}
    for g in plan["groups"]:
        for s in g["steps"]:
            c[s["status"]] += 1
            if s["status"] != "present" and not g["optional"]:
                c["required_open"] += 1
    return c


def run_verify(doc):
    m = machine_for(doc)
    out = []
    for v in doc.get("verify", []):
        # Pass or fail by exit status alone, output discarded: a check such as
        # `claude mcp list` prints stored keys.
        out.append({"name": v["name"], "run": v["run"], "passes": v["passes"],
                    "ok": m.shell_ok(v["run"])})
    return out


def apply_group(doc, path, group, confirmed):
    if platform_now() != doc["platform"]:
        print(f"apply: this file is for {doc['platform']}, and this machine is {platform_now()}", file=sys.stderr)
        return 2
    names = [g["name"] for g in doc["groups"]]
    if group not in names:
        print(f"apply: no group {group!r} (groups: {', '.join(names)})", file=sys.stderr)
        return 2
    m = machine_for(doc)
    confirmed = set(confirmed)
    for g, eid, kind, item in entries(doc):
        if g["name"] != group:
            continue
        label, command, person = describe(kind, item)
        if status(m, kind, item, confirmed, eid):
            print(f"[ok]     {eid:<14} {label}")
            continue
        if person:
            print(f"[person] {eid:<14} {label}")
            print(f"STOPPED at {eid}: {person['title']}")
            print(f"needs: {person['why']}; run in {'a separate terminal' if person['terminal'] == 'separate' else 'this session'}")
            if command:
                print("command:")
                for ln in command.splitlines():
                    print(f"  {ln}")
            print(f"then: apply --group {group} --confirmed {eid}")
            return 10
        print(f"[run]    {eid:<14} {command.splitlines()[0]}")
        if kind in ("shell", "path"):
            append_line(*item)
            continue
        if kind == "installer":
            argv = ["/bin/bash", "-c", item["run"]]
        else:
            argv = shlex.split(command)
        r = m.run(argv, quiet=False, timeout=1800)
        m.forget()
        if r is None or r.returncode != 0:
            print(f"FAILED {eid}: {label}" + ("" if r else f" ({argv[0]} not found)"))
            if r is not None:
                for ln in (r.stdout or "").splitlines()[-20:]:
                    print(f"  | {ln}")
            return 1
        if not status(m, kind, item, confirmed, eid):
            print(f"FAILED {eid}: the command succeeded but the check still fails ({label})")
            return 1
    print(f"group {group}: done")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", default=".fleet/setup.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    for name in ("plan", "check", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        if name == "plan":
            p.add_argument("--confirmed", action="append", default=[])
    p = sub.add_parser("apply")
    p.add_argument("--group", required=True)
    p.add_argument("--confirmed", action="append", default=[])
    a = ap.parse_args(argv)

    try:
        doc = load(a.file)
    except Invalid as e:
        for line in e.args[0]:
            print(f"invalid: {line}", file=sys.stderr)
        return 2

    if a.cmd == "validate":
        print(f"{a.file}: valid (version {doc['version']}, {len(doc['groups'])} groups)")
        return 0
    if a.cmd == "plan":
        plan = build_plan(doc, a.file, a.confirmed)
        print(json.dumps(plan, indent=2)) if a.json else print_plan(plan)
        return 0
    if a.cmd == "verify":
        res = run_verify(doc)
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            for v in res:
                print(f"{'ok  ' if v['ok'] else 'FAIL'} {v['name']}: {v['run']}  (passes: {v['passes']})")
        return 0 if all(v["ok"] for v in res) else 1
    if a.cmd == "check":
        plan = build_plan(doc, a.file)
        res = run_verify(doc)
        c = summary(plan)
        if a.json:
            print(json.dumps({"plan": plan, "verify": res, "summary": c}, indent=2))
        else:
            print_plan(plan)
            print()
            for v in res:
                print(f"{'ok  ' if v['ok'] else 'FAIL'} {v['name']}: {v['run']}")
        bad = c["required_open"] or not all(v["ok"] for v in res) or not plan["platform_ok"]
        return 1 if bad else 0
    return apply_group(doc, a.file, a.group, a.confirmed)


if __name__ == "__main__":
    sys.exit(main())
