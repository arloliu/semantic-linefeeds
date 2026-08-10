# Adapter Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `scripts/install.py`,
a one-command installer for the Codex, opencode, and AGENTS.md adapters,
so a stranger who clones the repo succeeds on first run without hand-editing configs.

**Architecture:** One stdlib-only Python file beside the detector.
It reads adapter payloads from the cloned repo at install time (no embedded copies to drift),
mutates agent configs defensively (append-never-overwrite, `.bak` backups, atomic writes, refuse on unparseable input),
and leaves Claude Code entirely to its own marketplace.
Design rationale and prior art (superpowers' harness-owned model, rtk's `init` machinery) are recorded in
`docs/research/2026-08-09-install-story.md`.

**Tech Stack:** Python 3.9+ stdlib only (`argparse json os shutil subprocess sys tempfile pathlib`);
pytest for tests (env-isolated tmp dirs, no live agents).

## Global Constraints

- `scripts/install.py` is stdlib-only Python 3.9+ and never imports from `check_linefeeds.py`.
- `scripts/check_linefeeds.py` is NOT modified by any task in this plan.
- The installer never reads or writes Claude Code configuration;
  the Claude path stays marketplace-only guidance text.
- Mutating writes are defensive, always:
  parse-then-append for JSON (never rewrite unrelated keys),
  `.bak` backup of any existing file before changing it,
  write-to-temp-then-`os.replace` in the destination directory,
  refuse (exit 1) on unparseable or structurally alien input.
- `--dry-run` performs zero filesystem writes, everywhere.
- Config paths resolve through env overrides first:
  `$CODEX_HOME` else `~/.codex`;
  `$XDG_CONFIG_HOME` else `~/.config` for opencode.
- Exit codes: 0 success or no-op;
  1 refusal or error;
  64 usage error (mirroring the detector's convention);
  `--help` exits 0.
- All Markdown written or modified must pass
  `python3 scripts/check_linefeeds.py --file <file>` with zero fused/wrap findings.
- Commits follow `.agents/rules/600-git-conventions.md`:
  Conventional Commits, header ≤ 50 chars, body ≤ 72, no attribution trailers.
- Run the full test suite (`python3 -m pytest tests/ -q`) before every commit.
- Version bumps to 0.3.0 only in the final task.

## File Structure (end state)

```
scripts/install.py            # the installer: path resolution, codex merge, opencode copy, agentsmd block, status
tests/test_installer.py       # env-isolated subprocess tests
adapters/codex/INSTALL.md     # gains the one-command path, keeps manual steps
adapters/opencode/INSTALL.md  # gains the one-command path, keeps manual steps
adapters/agentsmd/SNIPPET.md  # unchanged content; still the block source
README.md                     # install matrix gains installer commands
CHANGELOG.md                  # [0.3.0] Added entry
.claude-plugin/plugin.json    # version 0.3.0
```

---

### Task 1: Installer scaffold and the Codex merge

**Files:**
- Create: `scripts/install.py`
- Create: `tests/test_installer.py`

**Interfaces:**
- Consumes: `adapters/codex/` layout (template stays as documentation only);
  the detector's path `scripts/check_linefeeds.py` (referenced, not imported).
- Produces (later tasks add to the same file):
  `REPO`, `CHECKER`, `atomic_write(path, text, dry)`,
  `codex_home() -> Path`, `desired_codex_command() -> str`, `install_codex(dry) -> int`,
  argparse `main()` with `--codex`, `--dry-run`, exit-code aggregation;
  `run_install(args, env, cwd)` test helper in `tests/test_installer.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_installer.py`:

```python
import json
import os
import subprocess
import sys

from conftest import REPO

INSTALL = REPO / "scripts" / "install.py"


def run_install(args, env_overrides, cwd=None):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(INSTALL)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def isolated_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "HOME": str(home),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }


def codex_hooks_path(tmp_path):
    return tmp_path / "codex" / "hooks.json"


def read_hooks(tmp_path):
    return json.loads(codex_hooks_path(tmp_path).read_text(encoding="utf-8"))


def test_codex_fresh_install_creates_hooks_json(tmp_path):
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    entries = data["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "apply_patch"
    command = entries[0]["hooks"][0]["command"]
    assert "check_linefeeds.py" in command
    assert "--hook codex" in command
    assert "trust" in r.stdout.lower()


def test_codex_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    before = codex_hooks_path(tmp_path).read_text(encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert "already" in r.stdout.lower()
    assert codex_hooks_path(tmp_path).read_text(encoding="utf-8") == before


def test_codex_merge_preserves_existing_entries(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    existing = {"hooks": {"PostToolUse": [
        {"matcher": "shell", "hooks": [{"type": "command", "command": "echo hi"}]}
    ]}, "unrelated": {"keep": True}}
    path.write_text(json.dumps(existing), encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    assert data["unrelated"] == {"keep": True}
    commands = [h["hooks"][0]["command"] for h in data["hooks"]["PostToolUse"]]
    assert commands[0] == "echo hi"
    assert any("check_linefeeds.py" in c for c in commands)
    assert path.with_name("hooks.json.bak").exists()


def test_codex_stale_path_is_updated_in_place(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    stale = {"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": "python3 \"/old/clone/scripts/check_linefeeds.py\" --hook codex"}
        ]}
    ]}}
    path.write_text(json.dumps(stale), encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "updat" in r.stdout.lower()
    entries = read_hooks(tmp_path)["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert "/old/clone/" not in entries[0]["hooks"][0]["command"]
    assert str(REPO) in entries[0]["hooks"][0]["command"]


def test_codex_unparseable_json_is_refused(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 1
    assert path.read_text(encoding="utf-8") == "not json"
    assert not path.with_name("hooks.json.bak").exists()


def test_codex_dry_run_writes_nothing(tmp_path):
    r = run_install(["--codex", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not codex_hooks_path(tmp_path).exists()
    assert "dry-run" in r.stdout.lower()


def test_usage_error_exits_64(tmp_path):
    assert run_install(["--bogus"], isolated_env(tmp_path)).returncode == 64


def test_help_exits_zero(tmp_path):
    assert run_install(["--help"], isolated_env(tmp_path)).returncode == 0
```

- [ ] **Step 2: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_installer.py -q`
Expected: every test fails because `scripts/install.py` does not exist.

- [ ] **Step 3: Write scripts/install.py**

```python
#!/usr/bin/env python3
"""Install the semantic-linefeeds adapters into local AI coding agents.

Modes:
  --codex           merge the PostToolUse hook into $CODEX_HOME/hooks.json
                    (default ~/.codex/hooks.json), append-never-overwrite
  --opencode        copy the plugin and the checker side by side into
                    $XDG_CONFIG_HOME/opencode/plugins (default ~/.config/...)
  --agentsmd [PATH] manage a sentinel-marked snippet block in AGENTS.md
                    (default ./AGENTS.md)
  (no mode)         report install status and Claude Code guidance

Claude Code is installed through its own plugin marketplace and is never
touched by this script.

Options: --dry-run prints planned actions without writing; --force allows
overwriting an opencode file whose content has diverged. Exit codes:
0 success or no-op, 1 refusal or error, 64 usage error.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_linefeeds.py"
OPENCODE_PLUGIN = REPO / "adapters" / "opencode" / "semantic-linefeeds.ts"
SNIPPET = REPO / "adapters" / "agentsmd" / "SNIPPET.md"

TRUST_NOTE = ("note: Codex hashes unmanaged hooks; on your next interactive "
              "codex run it will ask you to trust this hook — accept it once.")


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def opencode_plugins_dir():
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "opencode" / "plugins"


def desired_codex_command():
    return f'python3 "{CHECKER}" --hook codex'


def atomic_write(path, text, dry):
    """Write text to path via a same-directory temp file and os.replace.

    An existing file is first copied to <name>.bak so one bad run is
    always recoverable.
    """
    if dry:
        print(f"[dry-run] would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def install_codex(dry):
    path = codex_home() / "hooks.json"
    command = desired_codex_command()
    entry = {"matcher": "apply_patch",
             "hooks": [{"type": "command", "command": command}]}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            hooks = data["hooks"] if "hooks" in data else data.setdefault("hooks", {})
            post = hooks.setdefault("PostToolUse", [])
            if not isinstance(data, dict) or not isinstance(post, list):
                raise ValueError("unexpected structure")
        except (json.JSONDecodeError, TypeError, AttributeError, ValueError) as e:
            print(f"refusing to touch {path}: cannot parse it ({e}).",
                  file=sys.stderr)
            print("merge the PostToolUse entry from adapters/codex/hooks.json "
                  "by hand (see adapters/codex/INSTALL.md).", file=sys.stderr)
            return 1
        ours = [h for block in post if isinstance(block, dict)
                for h in block.get("hooks", [])
                if isinstance(h, dict) and "check_linefeeds.py" in h.get("command", "")]
        if ours:
            if all(h["command"] == command for h in ours):
                print(f"codex: already installed ({path})")
                return 0
            for h in ours:
                h["command"] = command
            atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
            print(f"codex: updated the checker path in {path}")
            print(TRUST_NOTE)
            return 0
        post.append(entry)
        atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
        print(f"codex: appended the PostToolUse hook to {path}")
    else:
        data = {"hooks": {"PostToolUse": [entry]}}
        atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
        print(f"codex: created {path}")
    print(TRUST_NOTE)
    return 0


def main():
    ap = argparse.ArgumentParser(prog="install", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codex", action="store_true",
                    help="install the Codex CLI hook")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned actions without writing anything")
    ap.add_argument("--force", action="store_true",
                    help="overwrite opencode files whose content has diverged")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    codes = []
    if args.codex:
        codes.append(install_codex(args.dry_run))
    if not codes:
        codes.append(status())
    sys.exit(max(codes))


def status():
    print("no install mode given; see --help for --codex/--opencode/--agentsmd")
    return 0


if __name__ == "__main__":
    main()
```

Note: `status()` is a stub here;
Task 4 replaces it with the real report.
The `--force` flag is declared now so the CLI surface is stable,
and Task 2 consumes it.

- [ ] **Step 4: Run the tests, expect PASS**

Run: `python3 -m pytest tests/test_installer.py -q`
Expected: all pass.
Then run the full suite: `python3 -m pytest tests/ -q` — no regressions.

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_installer.py
git commit -m "feat: installer scaffold with the codex merge"
```

---

### Task 2: opencode install path

**Files:**
- Modify: `scripts/install.py` (add `install_opencode`, wire `--opencode`)
- Modify: `tests/test_installer.py` (append tests)

**Interfaces:**
- Consumes: `atomic_write`, `opencode_plugins_dir`, `run_install`, `isolated_env` from Task 1;
  `OPENCODE_PLUGIN` and `CHECKER` constants.
- Produces: `install_opencode(dry, force) -> int`;
  `--opencode` flag.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_installer.py`)

```python
def opencode_dir(tmp_path):
    return tmp_path / "xdg" / "opencode" / "plugins"


def test_opencode_fresh_install_copies_both_files(tmp_path):
    r = run_install(["--opencode"], isolated_env(tmp_path))
    assert r.returncode == 0
    d = opencode_dir(tmp_path)
    assert (d / "semantic-linefeeds.ts").exists()
    assert (d / "check_linefeeds.py").exists()
    src = (REPO / "adapters" / "opencode" / "semantic-linefeeds.ts").read_bytes()
    assert (d / "semantic-linefeeds.ts").read_bytes() == src


def test_opencode_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    r = run_install(["--opencode"], env)
    assert r.returncode == 0
    assert "already" in r.stdout.lower()


def test_opencode_changed_file_requires_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    target = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    target.write_text("// user hand-patch\n", encoding="utf-8")
    r = run_install(["--opencode"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr
    assert target.read_text(encoding="utf-8") == "// user hand-patch\n"


def test_opencode_force_overwrites_and_backs_up(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    target = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    target.write_text("// user hand-patch\n", encoding="utf-8")
    r = run_install(["--opencode", "--force"], env)
    assert r.returncode == 0
    src = (REPO / "adapters" / "opencode" / "semantic-linefeeds.ts").read_bytes()
    assert target.read_bytes() == src
    backup = target.with_name(target.name + ".bak")
    assert backup.read_text(encoding="utf-8") == "// user hand-patch\n"


def test_opencode_dry_run_writes_nothing(tmp_path):
    r = run_install(["--opencode", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not opencode_dir(tmp_path).exists()
```

- [ ] **Step 2: Run the tests, expect the new ones to FAIL**

Run: `python3 -m pytest tests/test_installer.py -q -k opencode`
Expected: FAIL — `--opencode` is not a valid flag yet (exit 64).

- [ ] **Step 3: Implement**

Add to `scripts/install.py`:

```python
def install_opencode(dry, force):
    dest_dir = opencode_plugins_dir()
    rc = 0
    copied = skipped = 0
    for src in (OPENCODE_PLUGIN, CHECKER):
        dest = dest_dir / src.name
        payload = src.read_bytes()
        if dest.exists():
            if dest.read_bytes() == payload:
                skipped += 1
                continue
            if not force:
                print(f"refusing to overwrite {dest}: its content differs "
                      "from this repo's copy (hand-patched or older version). "
                      "re-run with --force to replace it.", file=sys.stderr)
                rc = 1
                continue
        atomic_write(dest, payload.decode("utf-8"), dry)
        copied += 1
    if rc == 0 and copied == 0:
        print(f"opencode: already installed ({dest_dir})")
    elif copied:
        print(f"opencode: installed {copied} file(s) into {dest_dir}")
    print("note: the skill needs no copy when the Claude plugin is installed; "
          "see adapters/opencode/INSTALL.md otherwise.")
    return rc
```

Wire the flag into `main()`:

```python
    ap.add_argument("--opencode", action="store_true",
                    help="install the opencode plugin and checker")
```

and, beside the codex dispatch:

```python
    if args.opencode:
        codes.append(install_opencode(args.dry_run, args.force))
```

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_installer.py
git commit -m "feat: install the opencode plugin files"
```

---

### Task 3: Sentinel-managed AGENTS.md block

**Files:**
- Modify: `scripts/install.py` (add `agents_block`, `install_agentsmd`, wire `--agentsmd`)
- Modify: `tests/test_installer.py` (append tests)

**Interfaces:**
- Consumes: `atomic_write`, `SNIPPET`, `REPO` from Task 1; the test helpers.
- Produces: `SENTINEL_OPEN`/`SENTINEL_CLOSE` constants,
  `agents_block() -> str`, `install_agentsmd(target, dry) -> int`;
  `--agentsmd [PATH]` flag (optional value, default `./AGENTS.md` in the caller's cwd).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_installer.py`)

```python
SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"


def test_agentsmd_creates_file_with_block(tmp_path):
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert SENTINEL_OPEN in text and SENTINEL_CLOSE in text
    assert "Semantic linefeeds" in text
    assert str(REPO) in text  # the <repo> placeholder is substituted


def test_agentsmd_rerun_is_idempotent(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--agentsmd"], env, cwd=tmp_path)
    before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    r = run_install(["--agentsmd"], env, cwd=tmp_path)
    assert r.returncode == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == before


def test_agentsmd_replaces_block_and_keeps_user_text(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# My rules\n\nkeep me\n\n"
        f"{SENTINEL_OPEN}\nstale old block\n{SENTINEL_CLOSE}\n\ntail kept too\n",
        encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "keep me" in text and "tail kept too" in text
    assert "stale old block" not in text
    assert "Semantic linefeeds" in text


def test_agentsmd_appends_to_existing_file_without_block(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# My rules\n", encoding="utf-8")
    run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# My rules\n")
    assert SENTINEL_OPEN in text


def test_agentsmd_unbalanced_sentinels_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(f"{SENTINEL_OPEN}\nno close marker\n", encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == f"{SENTINEL_OPEN}\nno close marker\n"


def test_agentsmd_explicit_path(tmp_path):
    other = tmp_path / "docs-agents.md"
    r = run_install(["--agentsmd", str(other)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    assert SENTINEL_OPEN in other.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests, expect the new ones to FAIL**

Run: `python3 -m pytest tests/test_installer.py -q -k agentsmd`

- [ ] **Step 3: Implement**

Add to `scripts/install.py`:

```python
SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"


def agents_block():
    body = SNIPPET.read_text(encoding="utf-8").replace("<repo>", str(REPO))
    return f"{SENTINEL_OPEN}\n{body.rstrip()}\n{SENTINEL_CLOSE}\n"


def install_agentsmd(target, dry):
    block = agents_block()
    if target.exists():
        text = target.read_text(encoding="utf-8")
        has_open = SENTINEL_OPEN in text
        has_close = SENTINEL_CLOSE in text
        if has_open != has_close:
            print(f"refusing to touch {target}: found one sentinel marker "
                  "without its pair; repair the block by hand.", file=sys.stderr)
            return 1
        if has_open:
            pre = text.split(SENTINEL_OPEN)[0]
            post = text.split(SENTINEL_CLOSE, 1)[1]
            new = pre + block + post
        else:
            new = text.rstrip("\n") + "\n\n" + block
        if new == text:
            print(f"agentsmd: already up to date ({target})")
            return 0
    else:
        new = block
    atomic_write(target, new, dry)
    print(f"agentsmd: wrote the snippet block to {target}")
    return 0
```

Wire the flag into `main()`
(`nargs="?"` with a `const` mirrors the detector's `--hook` pattern):

```python
    ap.add_argument("--agentsmd", nargs="?", const="AGENTS.md", default=None,
                    metavar="PATH",
                    help="write the snippet block into PATH (default ./AGENTS.md)")
```

and beside the other dispatches:

```python
    if args.agentsmd is not None:
        codes.append(install_agentsmd(Path(args.agentsmd), args.dry_run))
```

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_installer.py
git commit -m "feat: sentinel-managed AGENTS.md install"
```

---

### Task 4: Status report, docs, v0.3.0

**Files:**
- Modify: `scripts/install.py` (replace the `status()` stub)
- Modify: `tests/test_installer.py` (append status tests)
- Modify: `README.md`, `adapters/codex/INSTALL.md`, `adapters/opencode/INSTALL.md`
- Modify: `CHANGELOG.md`, `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: the released 0.3.0 surface.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_installer.py`)

```python
def test_status_reports_all_targets_and_claude_guidance(tmp_path):
    r = run_install([], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    out = r.stdout
    assert "codex: not installed" in out
    assert "opencode: not installed" in out
    assert "agentsmd" in out and "absent" in out
    assert "claude plugin" in out


def test_status_sees_installed_targets(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex", "--opencode", "--agentsmd"], env, cwd=tmp_path)
    out = run_install([], env, cwd=tmp_path).stdout
    assert "codex: installed" in out
    assert "opencode: installed" in out
    assert "present" in out
```

- [ ] **Step 2: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_installer.py -q -k status`
Expected: FAIL — the stub prints none of these lines.

- [ ] **Step 3: Replace the `status()` stub**

```python
def status():
    hooks_path = codex_home() / "hooks.json"
    state = "not installed"
    if hooks_path.exists():
        try:
            data = json.loads(hooks_path.read_text(encoding="utf-8"))
            cmds = [h.get("command", "")
                    for block in data.get("hooks", {}).get("PostToolUse", [])
                    if isinstance(block, dict)
                    for h in block.get("hooks", [])
                    if isinstance(h, dict)]
        except (json.JSONDecodeError, AttributeError):
            cmds = []
            state = "unreadable"
        if any(c == desired_codex_command() for c in cmds):
            state = "installed"
        elif any("check_linefeeds.py" in c for c in cmds):
            state = "installed (stale checker path; re-run --codex)"
    print(f"codex: {state} ({hooks_path})")

    d = opencode_plugins_dir()
    present = [s.name for s in (OPENCODE_PLUGIN, CHECKER)
               if (d / s.name).exists() and (d / s.name).read_bytes() == s.read_bytes()]
    if len(present) == 2:
        print(f"opencode: installed ({d})")
    elif present:
        print(f"opencode: partial — only {present[0]} matches ({d})")
    else:
        print(f"opencode: not installed ({d})")

    agents = Path("AGENTS.md")
    mark = "present" if agents.exists() and SENTINEL_OPEN in agents.read_text(encoding="utf-8") else "absent"
    print(f"agentsmd: block {mark} in ./{agents}")

    print("claude: managed by Claude Code itself — install with:")
    print("  claude plugin marketplace add arloliu/semantic-linefeeds")
    print("  claude plugin install semantic-linefeeds@semantic-linefeeds")
    return 0
```

Before committing, mirror the exact marketplace commands against README.md's install section;
if the README's wording differs, the README is the source of truth — copy its commands.

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Update the docs**

`README.md` — in the per-agent install matrix,
change the Codex row's instruction to
`python3 scripts/install.py --codex` (manual steps: `adapters/codex/INSTALL.md`),
the opencode row's to
`python3 scripts/install.py --opencode` (manual steps: `adapters/opencode/INSTALL.md`),
and the "anything else" row's to
`python3 scripts/install.py --agentsmd` (snippet source: `adapters/agentsmd/SNIPPET.md`).
Keep the Claude Code row's marketplace commands unchanged.

`adapters/codex/INSTALL.md` — insert, after the intro line:

```markdown
The quick path is the installer,
which merges the hook into an existing `hooks.json` instead of overwriting it:

    python3 scripts/install.py --codex

The manual steps below remain for review or for unusual setups.
```

`adapters/opencode/INSTALL.md` — insert, after the intro line:

```markdown
The quick path is the installer:

    python3 scripts/install.py --opencode

The manual steps below remain for review or for unusual setups.
```

`CHANGELOG.md` — add above the `[0.2.1]` entry:

```markdown
## [0.3.0] - <today's date>

### Added

- `scripts/install.py`:
  a stdlib-only installer for the Codex (`--codex`), opencode (`--opencode`),
  and AGENTS.md (`--agentsmd`) adapters,
  with append-never-overwrite JSON merging, `.bak` backups, atomic writes,
  `--dry-run`, `--force`, and a no-argument status report.
  Claude Code stays marketplace-installed and is never touched.
```

`.claude-plugin/plugin.json` — set `"version": "0.3.0"`.

- [ ] **Step 6: Self-check every touched Markdown file**

Run:

```bash
python3 scripts/check_linefeeds.py --file README.md CHANGELOG.md \
  adapters/codex/INSTALL.md adapters/opencode/INSTALL.md \
  docs/plans/done/2026-08-09-installer.md
```

Expected: exit 0 (long advisories are judged, not obeyed).

- [ ] **Step 7: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "docs: prepare the v0.3.0 release"
```

---

## Verification checklist (run after the final task)

- `python3 -m pytest tests/ -q` — all green, installer tests included.
- `python3 scripts/install.py` (no args) — status report prints all four targets.
- `python3 scripts/install.py --codex --opencode --agentsmd --dry-run` — prints plans, writes nothing
  (verify with `git status` on a scratch `$CODEX_HOME`/`$XDG_CONFIG_HOME`).
- `python3 scripts/check_linefeeds.py --file $(git ls-files '*.md' ':!tests/')` — exit 0.
- `grep -E "^import|^from" scripts/install.py` — stdlib modules only.
- Live smoke on this machine (real configs, so read the dry-run first):
  `--codex` reports already-installed against the existing `~/.codex/hooks.json`;
  `--opencode` reports already-installed against `~/.config/opencode/plugins/`.
