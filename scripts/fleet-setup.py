#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml==6.0.3"]
# ///
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Machine setup for a fleet, from the register's setup.yaml.

    uv run scripts/fleet-setup.py [--fleet DIR] validate
    uv run scripts/fleet-setup.py [--fleet DIR] plan [--json] [--confirmed ID]...
    uv run scripts/fleet-setup.py [--fleet DIR] check [--json]
    uv run scripts/fleet-setup.py [--fleet DIR] apply --group G --at SHA [--confirmed ID]...
    uv run scripts/fleet-setup.py [--fleet DIR] verify [--json]
    uv run scripts/fleet-setup.py --file F validate
    uv run scripts/fleet-setup.py --file F --unreviewed COMMAND ...
    uv run scripts/fleet-setup.py archive --kind local|memory ARCHIVE [--extract DEST]

DIR is the fleet root (default: the current folder). The file is read from the
register checkout DIR/.fleet as it stands on refs/remotes/origin/main, fetched
this run, and only when that checkout's origin is the register this machine
pins. --file reads a working-tree file instead, for a person or a test; every
command but validate refuses it without --unreviewed, because plan, check and
verify run the file's person-step checks and verify commands. The schema is
docs/SETUP-YAML.md.

plan, check and verify install nothing, but they do run those check commands.
plan prints the origin/main sha it read; apply --at SHA refuses (exit 3) when a
fetch finds origin/main has moved since, so nothing runs that the person has
not seen. apply runs one group's missing steps in file order and stops at the
first person step that is still open; run it again with --confirmed ID once the
person has done that step. Every step checks before it acts, so a second apply
runs nothing. archive checks that an archive from an old machine holds only the
files fleet setup restores, and with --extract unpacks exactly those.

Exit: 0 done, 1 something missing or failed (or an archive refused), 2 invalid
file or usage, 3 the review gate refused the file, 4 the register has no
setup.yaml, 10 apply stopped at a person step.
"""

import argparse
import contextlib
import importlib.util
import io
import gzip
import hashlib
import json
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

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
PREFIX_RE = re.compile(r"^[A-Za-z0-9 ._-]*$")
# Written inside double quotes in an rc file, so anything the shell expands
# there ($(, `, ", \) would run at every login. A leading ~ is not expanded
# inside quotes, so the entry would name a folder literally called ~.
PATH_ENTRY_RE = re.compile(r"^(\$HOME|/[A-Za-z0-9._@+-]+)(/[A-Za-z0-9._@+-]+)*$")
RC_FILES = ("~/.zshrc", "~/.zprofile", "~/.zshenv", "~/.bashrc", "~/.bash_profile", "~/.profile")
# A launcher fetches the package at run time with the person's credentials in
# reach, so an unpinned one installs whatever was published a minute ago. npm
# reads `pkg@1` and `pkg@1.x` as ranges, so only a full MAJOR.MINOR.PATCH pins.
LAUNCHERS = {"npx", "bunx", "pnpx", "uvx"}
PKG_FLAGS = ("--package", "-p", "--from", "--with", "-w")
PINNED_RE = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9._/-]*(@|==)\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")
REVIEWED_REF = "refs/remotes/origin/main"
HERE = pathlib.Path(__file__).resolve().parent


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


def _rc_file(errs, where, v):
    if _str(errs, where, v) and v not in RC_FILES:
        errs.add(where, f"{v!r} is not a shell startup file (expected one of: {', '.join(RC_FILES)})")


def launcher_packages(args):
    """The package-bearing arguments of an npx/uvx-style launcher: every value
    of --package, -p, --from, --with and -w (attached, as in -wPKG, or not),
    and the first positional argument when none of those is given (with one,
    that argument is a command)."""
    pkgs, named, positional, i = [], False, [], 0
    while i < len(args):
        a = args[i]
        flag, eq, val = a.partition("=")
        if not eq and a[:2] in ("-p", "-w") and len(a) > 2:
            flag, eq, val = a[:2], "=", a[2:]
        if flag in PKG_FLAGS:
            named = True
            if eq:
                pkgs.append(val)
            else:
                pkgs.append(args[i + 1] if i + 1 < len(args) else "")
                i += 1
        elif not a.startswith("-"):
            positional.append(a)
        i += 1
    return pkgs if named else positional[:1]


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
            if m["command"] in LAUNCHERS and isinstance(args, list) and all(isinstance(a, str) for a in args):
                pkgs = launcher_packages(args)
                bad = [p for p in pkgs if not PINNED_RE.match(p)] or ([] if pkgs else ["(none)"])
                if bad:
                    errs.add(f"{where}.args", f"{m['command']} must run exact versions (pkg@1.2.3), got {bad}")
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
                    if "prefix" in s and (not isinstance(s["prefix"], str) or not PREFIX_RE.match(s["prefix"])):
                        errs.add(f"{w}.prefix", f"{s['prefix']!r} must match {PREFIX_RE.pattern}")
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
            _rc_file(errs, f"{w}.file", body.get("file"))
            _str_list(errs, f"{w}.{field}", body.get(field), PATH_ENTRY_RE if kind == "path" else None)
            if kind == "shell" and isinstance(body.get("lines"), list):
                for i, ln in enumerate(body["lines"]):
                    if isinstance(ln, str) and "\n" in ln:
                        errs.add(f"{w}.lines[{i}]", "one line per entry")
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
        # check is required: without one the step can never read as done, so
        # every later apply stops at it again.
        if _keys(errs, w, body, ("title", "why", "check"), ("run", "terminal")):
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


def parse(text, where):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise Invalid([f"{where}: not YAML: {e}"])
    validate(doc)
    seen, dup = set(), []
    for _, eid, _, _ in entries(doc):
        if eid in seen:
            dup.append(f"{eid}: the same step twice in one group")
        seen.add(eid)
    if dup:
        raise Invalid(dup)
    return doc


class Gate(Exception):
    """The review gate refused the file: CODE and why."""

    def __init__(self, code, detail, rc=3):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.rc = code, detail, rc


def load_file(path):
    """A working-tree file named by --file. A symlink is refused: what was
    reviewed would be the link, and what runs is whatever it points at."""
    p = pathlib.Path(path)
    if p.is_symlink():
        raise Gate("SYMLINK", f"{path} is a symlink")
    try:
        return p.read_text(), str(path), None
    except (OSError, UnicodeDecodeError) as e:
        raise Invalid([f"{path}: cannot read ({getattr(e, 'strerror', None) or e})"])


def audit_module():
    """scripts/audit.py, for remote_identity() and pinned_register(): one
    normaliser, so this gate and the audit cannot disagree on which register a
    pin names. Importing it binds the module from the cwd and prints notes, so
    the import runs from an empty folder with its stderr dropped."""
    spec = importlib.util.spec_from_file_location("wayfare_audit", HERE / "audit.py")
    mod = importlib.util.module_from_spec(spec)
    with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), \
            contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(mod)
    return mod


def git_env():
    # Inherited GIT_* can point git at another repository (a hook, a linked
    # worktree) or at other objects. A refs/replace/* ref swaps the blob the
    # gate reads while rev-parse still names the reviewed commit, so
    # replacements are off.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes",
               GIT_NO_REPLACE_OBJECTS="1")
    return env


def git(repo, *args, timeout=120):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                           env=git_env(), timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except OSError as e:
        return 127, "", str(e)
    return r.returncode, r.stdout, r.stderr.strip()


def load_reviewed(fleet):
    """setup.yaml as it stands on the pinned register's origin/main, fetched
    now. The full ref name, because a local branch or tag called origin/main
    wins over the remote-tracking ref when the short name is resolved. The
    working tree is never read: a branch checked out to review a register PR,
    or an unpushed edit, would otherwise choose what this machine installs."""
    root = pathlib.Path(fleet).resolve()
    reg = root / ".fleet"
    if not (reg / ".git").exists():
        raise Gate("NO_REGISTER", f"{reg} is not a git checkout")
    audit = audit_module()
    pin = audit.pinned_register(root)
    if pin is None:
        raise Gate("NO_PIN", f"this machine pins no register for {root} ({audit.pin_file()})")
    rc, url, err = git(reg, "remote", "get-url", "origin")
    if rc:
        raise Gate("NO_ORIGIN", f"{reg} has no origin remote")
    seen = audit.remote_identity(url)
    if seen != pin:
        raise Gate("PIN_MISMATCH", f"origin is {seen}, but this machine pins {pin}")
    rc, _, err = git(reg, "fetch", "-q", "origin", f"+refs/heads/main:{REVIEWED_REF}")
    if rc:
        raise Gate("NO_FETCH", f"fetching origin main failed: {err}")
    rc, tree, err = git(reg, "ls-tree", REVIEWED_REF, "--", "setup.yaml")
    if rc:
        raise Gate("NO_FETCH", f"{REVIEWED_REF} does not resolve: {err}")
    if not tree.strip():
        raise Gate("NO_SETUP_YAML", f"origin/main of {seen} has no setup.yaml", rc=4)
    mode = tree.split()[0]
    if mode == "120000":
        raise Gate("SYMLINK", "setup.yaml on origin/main is a symlink")
    if mode not in ("100644", "100755"):
        raise Gate("NOT_A_FILE", f"setup.yaml on origin/main has mode {mode}")
    rc, text, err = git(reg, "show", f"{REVIEWED_REF}:setup.yaml")
    if rc:
        raise Gate("NO_FETCH", f"cannot read setup.yaml from {REVIEWED_REF}: {err}")
    _, sha, _ = git(reg, "rev-parse", "--verify", f"{REVIEWED_REF}^{{commit}}")
    sha = sha.strip()
    local = reg / "setup.yaml"
    try:
        if local.is_symlink() or local.read_text() != text:
            print(f"note: {local} differs from origin/main; the reviewed copy is used", file=sys.stderr)
    except OSError:
        pass
    return text, f"{seen} setup.yaml @ origin/main {sha[:12]}", sha


def home():
    return pathlib.Path(os.environ["HOME"])


def expand(p):
    """An rc file (~/...) or a PATH entry ($HOME/... or absolute) as a real
    path. Validation has already limited both to those two prefixes."""
    if p.startswith("~/"):
        return str(home()) + p[1:]
    if p == "$HOME" or p.startswith("$HOME/"):
        return str(home()) + p[len("$HOME"):]
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
            # The quoted literal and the variable are adjacent words, so the
            # shell joins them; only the variable is expanded.
            parts.append(f'--header {shlex.quote(s["header"] + ": " + s.get("prefix", ""))}"${s["env"]}"')
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
    lines = [f"claude mcp get {shlex.quote(m['name'])} >/dev/null 2>&1 || {{"]
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
        """(result, why): result is None when the command did not run, and why
        then says whether it was missing, timed out, or failed to start."""
        exe = self.which(argv[0]) if not argv[0].startswith("/") else argv[0]
        if not exe:
            return None, f"{argv[0]} not found"
        try:
            # Output is discarded, not captured: `claude mcp get` prints a
            # server's environment, secret values included.
            r = subprocess.run([exe, *argv[1:]], env=self.env, timeout=timeout,
                               stdout=subprocess.DEVNULL if quiet else subprocess.PIPE,
                               stderr=subprocess.DEVNULL if quiet else subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True)
        except subprocess.TimeoutExpired:
            return None, f"{argv[0]} timed out after {timeout}s"
        except OSError as e:
            return None, f"{argv[0]} could not start: {e.strerror or e}"
        return r, ""

    def ok(self, argv, **kw):
        r, _ = self.run(argv, **kw)
        return bool(r and r.returncode == 0)

    def lines(self, key, argv):
        if key not in self.cache:
            r, _ = self.run(argv, quiet=False)
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
        return self.ok(["claude", "mcp", "get", name], timeout=60)

    def git_has(self, key, value):
        r, _ = self.run(["git", "config", "--global", "--get", key], quiet=False)
        return bool(r and r.returncode == 0 and r.stdout.strip() == value)

    def shell_ok(self, cmd):
        return self.ok(["/bin/bash", "-c", cmd], timeout=120)

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


def _short(*parts):
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:8]


def entry_key(kind, item):
    """What an entry is, not where it sits: an edit that inserts a step above
    one must not move its id, or a --confirmed given for one person step
    would close another."""
    if kind in ("brew", "cask", "pipx", "plugin"):
        return item
    if kind in ("marketplace", "mcp", "installer"):
        return item["name"] if kind != "installer" else item["check"]
    if kind == "git":
        return item[0]
    if kind in ("shell", "path"):
        return _short(*item)
    if kind == "person":
        return _short(item["title"], item["check"])
    raise AssertionError(kind)


def entries(doc):
    """The plan: one entry per thing to install or set, in file order, each
    with the id GROUP.KIND:KEY."""
    for g in doc["groups"]:
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
                yield g, f"{g['name']}.{kind_}:{entry_key(kind_, item)}", kind_, item


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
        return eid in confirmed or m.shell_ok(item["check"])
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
    if plan.get("sha"):
        print(f"reviewed: {plan['sha']} (pass apply --at {plan['sha'][:12]})")
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
            print(f"  {MARK[s['status']]} {s['id']:<32} {s['label']}")
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


def apply_group(doc, group, confirmed):
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
            print(f"[ok]     {eid:<32} {label}")
            continue
        if person:
            print(f"[person] {eid:<32} {label}")
            print(f"STOPPED at {eid}: {person['title']}")
            print(f"needs: {person['why']}; run in {'a separate terminal' if person['terminal'] == 'separate' else 'this session'}")
            if command:
                print("command:")
                for ln in command.splitlines():
                    print(f"  {ln}")
            print(f"then: apply --group {group} --confirmed {eid}")
            return 10
        print(f"[run]    {eid:<32} {command.splitlines()[0]}")
        if kind in ("shell", "path"):
            append_line(*item)
            continue
        if kind == "installer":
            argv = ["/bin/bash", "-c", item["run"]]
        else:
            argv = shlex.split(command)
        r, why = m.run(argv, quiet=False, timeout=1800)
        m.forget()
        if r is None or r.returncode != 0:
            print(f"FAILED {eid}: {label}" + (f" ({why})" if why else f" (exit {r.returncode})"))
            if r is not None:
                for ln in (r.stdout or "").splitlines()[-20:]:
                    print(f"  | {ln}")
            return 1
        if not status(m, kind, item, confirmed, eid):
            print(f"FAILED {eid}: the command succeeded but the check still fails ({label})")
            return 1
    print(f"group {group}: done")
    return 0


# What an old machine's archives may hold. Anything else (a LaunchAgent, a
# Claude hook, a link out of the folder) would land in ~ or a checkout, and
# run there, if the archive were unpacked whole.
ARCHIVE_KINDS = {
    "local": (re.compile(r"^(FLEET\.md|[A-Za-z0-9_][A-Za-z0-9._-]*/\.env|[A-Za-z0-9_][A-Za-z0-9._-]*/\.plans(/.+)?)$"),
              re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")),
    "memory": (re.compile(r"^\.claude/projects/[^/]+/memory(/.+)?$"),
               re.compile(r"^\.claude(/projects(/[^/]+)?)?$")),
}


def read_archive(path):
    """(TarFile, problems). Read once, into memory, by this parser only: the
    check and the extraction must see the same members. Python's reader stops
    quietly at a damaged header, where bsdtar skips it and reads on, so bytes
    after the last member it parsed that are not zero padding mean members
    one reader sees and the other does not, and the archive is refused."""
    try:
        raw = pathlib.Path(path).read_bytes()
    except OSError as e:
        return None, [f"{path}: cannot read ({e.strerror})"]
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as e:
            return None, [f"{path}: damaged gzip stream ({e})"]
    try:
        t = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
        t.getmembers()
    except tarfile.TarError as e:
        return None, [f"{path}: not a tar archive ({e})"]
    if raw[t.offset:].strip(b"\0"):
        return None, [f"{path}: unreadable data after byte {t.offset}, where the last member ends; "
                      "another tar reader could find members there"]
    return t, []


def check_archive(t, kind):
    """The members fleet setup would not restore, each with why. Only regular
    files and folders, with relative names and no `..`."""
    member, parent = ARCHIVE_KINDS[kind]
    bad = []
    for m in t.getmembers():
        name = m.name[2:] if m.name.startswith("./") else m.name
        name = name.rstrip("/")
        parts = pathlib.PurePosixPath(name).parts
        if not name or name.startswith("/") or ".." in parts or "\\" in name:
            bad.append(f"{m.name}: not a plain relative path")
        elif not (m.isfile() or m.isdir()):
            bad.append(f"{m.name}: not a regular file or folder")
        elif m.mode & 0o6000:
            bad.append(f"{m.name}: setuid or setgid")
        elif m.isdir() and parent.match(name):
            continue
        elif not member.match(name):
            bad.append(f"{m.name}: not something fleet setup restores")
    return bad


def extract_archive(t, dest):
    """Unpack every member of a checked archive under `dest`, keeping any file
    already there. (extracted, kept, refused); `data` refuses a member whose
    path would resolve outside `dest`, such as through a symlink already
    there."""
    dest = pathlib.Path(dest)
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    done, kept, refused = 0, 0, []
    for m in t.getmembers():
        target = dest / m.name
        if (m.isdir() and target.is_dir()) or (not m.isdir() and os.path.lexists(target)):
            kept += not m.isdir()
            continue
        try:
            t.extract(m, dest, filter="data")
        except (tarfile.FilterError, OSError) as e:
            refused.append(f"{m.name}: {e}")
            continue
        done += not m.isdir()
    return done, kept, refused


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--fleet", default=".", help="the fleet root (default: here)")
    src.add_argument("--file", help="a working-tree setup.yaml, read without the review gate")
    ap.add_argument("--unreviewed", action="store_true",
                    help="let apply run a --file that has not been through the register's review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    p = sub.add_parser("archive")
    p.add_argument("--kind", choices=sorted(ARCHIVE_KINDS), required=True)
    p.add_argument("--extract", metavar="DEST", help="unpack the checked members under DEST")
    p.add_argument("path")
    for name in ("plan", "check", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        if name == "plan":
            p.add_argument("--confirmed", action="append", default=[])
    p = sub.add_parser("apply")
    p.add_argument("--group", required=True)
    p.add_argument("--at", metavar="SHA", help="the origin/main commit plan showed; required without --file")
    p.add_argument("--confirmed", action="append", default=[])
    a = ap.parse_args(argv)

    if a.cmd == "archive":
        t, bad = read_archive(a.path)
        bad = bad or check_archive(t, a.kind)
        for b in bad:
            print(f"REFUSED {b}")
        if bad:
            print(f"{a.path}: refused ({a.kind}); nothing unpacked")
            return 1
        if a.extract:
            done, kept, refused = extract_archive(t, a.extract)
            for r in refused:
                print(f"REFUSED {r}")
            print(f"{a.path}: unpacked {done} files into {a.extract}, kept {kept} already there"
                  f"{f', refused {len(refused)}' if refused else ''} ({a.kind})")
            return 1 if refused else 0
        else:
            print(f"{a.path}: ok ({a.kind})")
        return 0
    if a.file and a.cmd != "validate" and not a.unreviewed:
        print(f"{a.cmd}: --file runs commands from a file nobody reviewed (person-step checks, verify, "
              "installs); pass --unreviewed as well to mean it", file=sys.stderr)
        return 2
    if a.cmd == "apply" and not a.file and not a.at:
        print("apply: pass --at SHA, the origin/main commit plan printed", file=sys.stderr)
        return 2
    try:
        text, source, sha = load_file(a.file) if a.file else load_reviewed(a.fleet)
        if a.cmd == "apply" and sha and not (len(a.at) >= 7 and sha.startswith(a.at.lower())):
            raise Gate("MOVED", f"origin/main is now {sha[:12]}, not the {a.at} that plan showed; "
                                "run plan again and show it")
        doc = parse(text, source)
    except Gate as e:
        print(f"GATE {e.code}: {e.detail}", file=sys.stderr)
        return e.rc
    except Invalid as e:
        for line in e.args[0]:
            print(f"invalid: {line}", file=sys.stderr)
        return 2

    if a.cmd == "validate":
        print(f"{source}: valid (version {doc['version']}, {len(doc['groups'])} groups)")
        return 0
    if a.cmd == "plan":
        plan = build_plan(doc, source, a.confirmed)
        plan["sha"] = sha
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
        plan = build_plan(doc, source)
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
    return apply_group(doc, a.group, a.confirmed)


if __name__ == "__main__":
    sys.exit(main())
