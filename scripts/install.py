#!/usr/bin/env python3
"""Install the semantic-linefeeds adapters into local AI coding agents.

Modes:
  --codex           merge the PostToolUse hook into $CODEX_HOME/hooks.json (default ~/.codex/hooks.json), append-never-overwrite; also installs the native semantic-linefeeds skill under ~/.agents/skills
  --opencode        copy the plugin and the checker side by side into $XDG_CONFIG_HOME/opencode/plugins (default ~/.config/...)
  --agentsmd [PATH] manage a sentinel-marked snippet block in AGENTS.md (default ./AGENTS.md)
  --cli             build the semlf zipapp and install it as ~/.local/bin/semlf
  (no mode)         report install status and Claude Code guidance

Claude Code is installed through its own plugin marketplace and is never touched by this script.
Options: --dry-run prints planned actions without writing.
--force allows overwriting opencode, codex-skill, or cli files whose content has diverged.
Exit codes: 0 success or no-op, 1 refusal or error, 64 usage error.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_linefeeds.py"
OPENCODE_PLUGIN = REPO / "adapters" / "opencode" / "semantic-linefeeds.ts"
SNIPPET = REPO / "adapters" / "agentsmd" / "SNIPPET.md"
SKILL_SOURCE = REPO / "skills" / "semantic-linefeeds" / "SKILL.md"
CLI_PKG = REPO / "cli" / "semlf"
PYZ_INTERPRETER = "/usr/bin/env python3"
MAIN_STUB = "from semlf.cli import main\nraise SystemExit(main())\n"
PYZ_REQUIRED_MEMBERS = {"__main__.py", "check_linefeeds.py", "semlf/__init__.py", "semlf/cli.py"}

SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"

TRUST_NOTE = ("note: Codex hashes unmanaged hooks; on your next interactive "
              "codex run it will ask you to trust this hook — accept it once.")


def codex_home():
    """$CODEX_HOME, or ~/.codex, or None when neither resolves.

    Same guard as `codex_skill_dest`:
    `Path.home()` raises when a home directory cannot be determined,
    so the env var is checked first and `os.path.expanduser` stands in for the unguarded fallback.
    """
    if os.environ.get("CODEX_HOME"):
        return Path(os.environ["CODEX_HOME"])
    home = os.path.expanduser("~")
    return None if home == "~" else Path(home) / ".codex"


def opencode_plugins_dir():
    """$XDG_CONFIG_HOME/opencode/plugins, or ~/.config/..., or None.

    Same guard as `codex_home`.
    """
    if os.environ.get("XDG_CONFIG_HOME"):
        base = Path(os.environ["XDG_CONFIG_HOME"])
    else:
        home = os.path.expanduser("~")
        if home == "~":
            return None
        base = Path(home) / ".config"
    return base / "opencode" / "plugins"


def desired_codex_command():
    return f'python3 "{CHECKER}" --hook codex'


def atomic_write(path, text, dry):
    """Write text to path via a same-directory temp file and os.replace.

    An existing file is first copied to <name>.bak so one bad run is always recoverable.
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
    home = codex_home()
    if home is None:
        print("refusing to install the codex hook: cannot determine a "
              "home directory to install it under.", file=sys.stderr)
        return 1
    path = home / "hooks.json"
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


# The three exact literal edits ADR-0006 requires:
# the fenced command line points at this checkout's absolute path instead of a plugin-only env var,
# the CLAUDE_PLUGIN_ROOT fallback sentence — meaningless outside Claude Code — is removed,
# and the skill's relative suppression-section link is rewritten to this checkout's absolute README path,
# so it still resolves once installed under ~/.agents/skills.
CODEX_SKILL_COMMAND_OLD = (
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>'
)
CODEX_SKILL_FALLBACK_LINE = (
    "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
    "`../../scripts/check_linefeeds.py` relative to this SKILL.md.)\n\n"
)
CODEX_SKILL_README_LINK_OLD = "../../README.md"


def codex_skill_dest():
    """Where the native skill installs, or None when no home resolves.

    Uses `os.path.expanduser("~")` rather than `Path.home()`.
    `expanduser` returns its input unchanged when it cannot resolve;
    `Path.home()` would raise instead.
    That mirrors `_judgment_layer_present` in `scripts/check_linefeeds.py`, the hook probe's own check.
    """
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"


def build_pyz(dest):
    """Build and publish the semlf zipapp at dest, atomically and executable.

    The core is copied from scripts/ at build time,
    same rule as the packaging proof: a committed second copy would be a fork.
    The archive is staged in dest's own directory and published by os.replace,
    with the execute bit set before publication,
    so no observer ever sees a partial or non-runnable file at dest.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "stage"
        (stage / "semlf").mkdir(parents=True)
        shutil.copy2(CHECKER, stage / CHECKER.name)
        for src in sorted(CLI_PKG.glob("*.py")):
            shutil.copy2(src, stage / "semlf" / src.name)
        (stage / "__main__.py").write_text(MAIN_STUB, encoding="utf-8")
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
        os.close(fd)
        try:
            zipapp.create_archive(stage, tmp, interpreter=PYZ_INTERPRETER)
            os.chmod(tmp, 0o755)
            os.replace(tmp, dest)
        except BaseException:
            os.unlink(tmp)
            raise


def pyz_state(path):
    """The installed-equality identity of a pyz, or None when unreadable.

    (member digest, owner-execute bit, interpreter line):
    member contents because that is what runs,
    the owner-execute bit and the shebang because without them nothing runs at all.
    The owner bit, not effective access,
    so state reflects what was published rather than who is asking.
    zipapp embeds member timestamps, so they are deliberately excluded.
    """
    path = Path(path)
    try:
        first_line = path.read_bytes().split(b"\n", 1)[0]
        owner_exec = bool(path.stat().st_mode & stat.S_IXUSR)
        digest = hashlib.sha256()
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                digest.update(name.encode("utf-8"))
                digest.update(archive.read(name))
    except (OSError, zipfile.BadZipFile):
        return None
    return (digest.hexdigest(), owner_exec, first_line)


def pyz_runnable(path):
    """Whether the archive at path can actually run as the semlf command.

    The one validity seam install equality's neighbor status() reuses,
    so "installed" and "current" can never drift apart:
    not a symlink (install_cli refuses to manage one, so status must not bless one),
    readable, executable, the expected interpreter, and every required member.
    """
    path = Path(path)
    if path.is_symlink():
        return False
    state = pyz_state(path)
    if state is None or not state[1]:
        return False
    if state[2] != b"#!" + PYZ_INTERPRETER.encode("utf-8"):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return PYZ_REQUIRED_MEMBERS <= names


def cli_bin_dest():
    """~/.local/bin/semlf, or None when no home resolves.

    Same guard as codex_skill_dest.
    """
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "bin" / "semlf"


def _path_note(dest):
    if str(dest.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"note: {dest.parent} is not on PATH; add it in your shell profile.")


def _publish_new(staged, dest):
    """Exclusively publish staged at dest; False when dest already appeared.

    os.link fails with FileExistsError when dest exists,
    so a file that appeared after classification is never replaced unclassified.
    The staged file is always consumed.
    """
    try:
        os.link(staged, dest)
    except FileExistsError:
        return False
    finally:
        os.unlink(staged)
    return True


def install_cli(dry, force):
    """Install the executable pyz as the semlf command.

    Symlinks and non-regular destinations are refused outright;
    a fresh install publishes exclusively
    (a dest appearing after classification is refused, not replaced);
    only a classified, backed-up divergence is replaced under --force.
    """
    dest = cli_bin_dest()
    if dest is None:
        print("refusing to install the cli: cannot determine a "
              "home directory to install it under.", file=sys.stderr)
        return 1
    if dest.is_symlink():
        print(f"refusing to touch {dest}: it is a symlink.", file=sys.stderr)
        return 1
    if dest.exists() and not dest.is_file():
        print(f"refusing to touch {dest}: it exists and is not a regular file.",
              file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "semlf"
        build_pyz(fresh)
        divergent = False
        if dest.is_file():
            if pyz_state(dest) == pyz_state(fresh):
                print(f"cli: already installed ({dest})")
                _path_note(dest)
                return 0
            if not force:
                print(f"refusing to overwrite {dest}: its content differs "
                      "from this build (hand-patched or older version). "
                      "re-run with --force to replace it.", file=sys.stderr)
                return 1
            divergent = True
    if dry:
        print(f"would back up and replace {dest}" if divergent
              else f"would install {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
    os.close(fd)
    staged = Path(staged_name)
    try:
        build_pyz(staged)
        if divergent:
            shutil.copy2(dest, dest.with_name(dest.name + ".bak"))
            os.replace(staged, dest)
        elif not _publish_new(staged, dest):
            print(f"refusing to overwrite {dest}: it appeared after "
                  "classification; re-run so it can be classified.", file=sys.stderr)
            return 1
    except BaseException:
        if staged.exists():
            os.unlink(staged)
        raise
    print(f"cli: installed {dest}")
    _path_note(dest)
    return 0


def codex_skill_body():
    text = SKILL_SOURCE.read_text(encoding="utf-8")
    text = text.replace(CODEX_SKILL_COMMAND_OLD,
                         f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>')
    text = text.replace(CODEX_SKILL_FALLBACK_LINE, "")
    return text.replace(CODEX_SKILL_README_LINK_OLD, f"{REPO}/README.md")


def install_codex_skill(dry, force):
    dest = codex_skill_dest()
    if dest is None:
        print("refusing to install the codex skill: cannot determine a "
              "home directory to install it under.", file=sys.stderr)
        return 1
    body = codex_skill_body()
    payload = body.encode("utf-8")
    if dest.exists():
        try:
            same = dest.read_bytes() == payload
        except OSError:
            same = False
        if same:
            print(f"codex skill: already installed ({dest})")
            return 0
        if not force:
            print(f"refusing to overwrite {dest}: its content differs "
                  "from this repo's copy (hand-patched or older version). "
                  "re-run with --force to replace it.", file=sys.stderr)
            return 1
    atomic_write(dest, body, dry)
    print(f"codex skill: installed {dest}")
    return 0


def install_opencode(dry, force):
    dest_dir = opencode_plugins_dir()
    if dest_dir is None:
        print("refusing to install opencode: cannot determine a "
              "home directory to install it under.", file=sys.stderr)
        return 1
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
        if has_open and (text.count(SENTINEL_OPEN) != 1
                          or text.count(SENTINEL_CLOSE) != 1
                          or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
            print(f"refusing to touch {target}: sentinel markers are out of "
                  "order or repeated; repair the block by hand.", file=sys.stderr)
            return 1
        if has_open:
            pre = text.split(SENTINEL_OPEN)[0]
            post_raw = text.split(SENTINEL_CLOSE, 1)[1]
            post = post_raw.lstrip('\n')
            if post:
                post = "\n" + post
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


def main():
    ap = argparse.ArgumentParser(prog="install", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codex", action="store_true",
                    help="install the Codex CLI hook and the native semantic-linefeeds skill")
    ap.add_argument("--opencode", action="store_true",
                    help="install the opencode plugin and checker")
    ap.add_argument("--agentsmd", nargs="?", const="AGENTS.md", default=None,
                    metavar="PATH",
                    help="write the snippet block into PATH (default ./AGENTS.md)")
    ap.add_argument("--cli", action="store_true",
                    help="build the semlf zipapp and install it as ~/.local/bin/semlf")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned actions without writing anything")
    ap.add_argument("--force", action="store_true",
                    help="overwrite opencode, codex-skill, or cli files whose content has diverged")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    codes = []
    if args.codex:
        codes.append(install_codex(args.dry_run))
        codes.append(install_codex_skill(args.dry_run, args.force))
    if args.opencode:
        codes.append(install_opencode(args.dry_run, args.force))
    if args.agentsmd is not None:
        codes.append(install_agentsmd(Path(args.agentsmd), args.dry_run))
    if args.cli:
        codes.append(install_cli(args.dry_run, args.force))
    if not codes:
        codes.append(status())
    sys.exit(max(codes))


def status():
    cli_dest = cli_bin_dest()
    if cli_dest is None:
        print("cli: no home to check")
    elif not cli_dest.exists() and not cli_dest.is_symlink():
        print(f"cli: not installed ({cli_dest})")
    elif not pyz_runnable(cli_dest):
        # Same validity seam as install equality: a foreign shebang,
        # a stripped execute bit, or a missing member is never "installed".
        print(f"cli: present but not runnable ({cli_dest})")
    else:
        try:
            with zipfile.ZipFile(cli_dest) as archive:
                text = archive.read("check_linefeeds.py").decode("utf-8")
            match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
            version = match.group(1) if match else "unknown"
        except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
            version = "unknown"
        print(f"cli: installed (v{version}) ({cli_dest})")

    home = codex_home()
    if home is None:
        print("codex: no home to check")
    else:
        hooks_path = home / "hooks.json"
        state = "not installed"
        if hooks_path.exists():
            try:
                data = json.loads(hooks_path.read_text(encoding="utf-8"))
                cmds = [h.get("command", "")
                        for block in data.get("hooks", {}).get("PostToolUse", [])
                        if isinstance(block, dict)
                        for h in block.get("hooks", [])
                        if isinstance(h, dict)]
            except (ValueError, AttributeError, OSError):
                cmds = []
                state = "unreadable"
            if any(c == desired_codex_command() for c in cmds):
                state = "installed"
            elif any("check_linefeeds.py" in c for c in cmds):
                state = "installed (stale checker path; re-run --codex)"
        print(f"codex: {state} ({hooks_path})")

    skill_dest = codex_skill_dest()
    if skill_dest is None:
        print("codex skill: no home to check")
    else:
        skill_state = "not installed"
        if skill_dest.exists():
            try:
                raw = skill_dest.read_bytes()
            except OSError:
                skill_state = "unreadable"
            else:
                try:
                    raw.decode("utf-8")
                except UnicodeDecodeError:
                    skill_state = "unreadable"
                else:
                    # Byte-level, like the install-time check above and the hook probe's own read.
                    # A text-mode comparison would launder a CRLF-converted copy back through universal-newline translation.
                    # It would call the copy installed.
                    skill_state = ("installed" if raw == codex_skill_body().encode("utf-8")
                                    else "diverged")
        print(f"codex skill: {skill_state} ({skill_dest})")

    d = opencode_plugins_dir()
    if d is None:
        print("opencode: no home to check")
    else:
        present = [s.name for s in (OPENCODE_PLUGIN, CHECKER)
                   if (d / s.name).exists() and (d / s.name).read_bytes() == s.read_bytes()]
        if len(present) == 2:
            print(f"opencode: installed ({d})")
        elif present:
            print(f"opencode: partial — only {present[0]} matches ({d})")
        else:
            print(f"opencode: not installed ({d})")

    agents = Path("AGENTS.md")
    mark = "absent"
    if agents.exists():
        try:
            if SENTINEL_OPEN in agents.read_text(encoding="utf-8"):
                mark = "present"
        except (ValueError, OSError):
            mark = "absent (unreadable)"
    print(f"agentsmd: block {mark} in ./{agents}")

    print("claude: managed by Claude Code itself — install with:")
    print("  claude plugin marketplace add /path/to/semantic-linefeeds  # or a private git remote")
    print("  claude plugin install semantic-linefeeds@semantic-linefeeds")
    return 0


if __name__ == "__main__":
    main()
