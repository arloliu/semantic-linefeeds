#!/usr/bin/env python3
"""Install the semantic-linefeeds adapters into local AI coding agents.

Modes:
  --codex           merge the PostToolUse hook into $CODEX_HOME/hooks.json (default ~/.codex/hooks.json), append-never-overwrite; also installs the native semantic-linefeeds skill under ~/.agents/skills
  --opencode        copy the plugin and the checker side by side into $XDG_CONFIG_HOME/opencode/plugins (default ~/.config/...)
  --agentsmd PATH   manage a sentinel-marked snippet block in PATH (an explicit path is required)
  --cli             build the semlf zipapp and install it as ~/.local/bin/semlf
  (no mode)         report install status and Claude Code guidance

Claude Code is installed through its own plugin marketplace and is never touched by this script.
Options: --dry-run prints planned actions without writing.
--force allows overwriting opencode, codex-skill, or cli files whose content has diverged.
--uninstall removes an installed mode's artifacts instead of installing them.
It requires at least one mode flag and honors --dry-run and --force the same way.
Exit codes: 0 success or no-op, 1 refusal or error, 64 usage error.
"""
import argparse
import hashlib
import io
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
PYZ_REQUIRED_MEMBERS = {"__main__.py", "check_linefeeds.py",
                        "semlf/__init__.py", "semlf/cli.py",
                        "semlf/providers.py"}

SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"

TRUST_NOTE = ("note: Codex hashes unmanaged hooks; on your next interactive "
              "codex run it will ask you to trust this hook — accept it once.")

sys.path.insert(0, str(REPO / "cli"))
from semlf import manifest  # noqa: E402 -- must follow the path insert above
from semlf.manifest import (  # noqa: E402
    codex_home, opencode_plugins_dir, codex_skill_dest, cli_bin_dest,
)


def core_version():
    """The repo core's version, read textually so nothing is imported."""
    match = re.search(r'^__version__ = "([^"]+)"$',
                      CHECKER.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else "unknown"


def desired_codex_command():
    return f'python3 "{CHECKER}" --hook codex'


class _BackupSlotRefused(Exception):
    """atomic_write's backup slot is occupied by something not a regular file."""

    def __init__(self, bak):
        super().__init__(str(bak))
        self.bak = bak


def atomic_write(path, text, dry):
    """Write text to path via a same-directory temp file and os.replace.

    An existing file is first copied to <name>.bak so one bad run is always recoverable.
    The backup slot itself is guarded:
    anything already at <name>.bak that is not absent or a regular file — above all a symlink, which shutil.copy2 would follow and overwrite through — raises instead of being backed up over.
    A regular .bak keeps its existing last-run-wins behavior:
    unlike the cli's exclusive backup, atomic_write's callers back up a merged shared file the next run re-merges, never the only copy of anything.
    """
    if dry:
        print(f"[dry-run] would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        try:
            bak_mode = os.lstat(bak).st_mode
        except FileNotFoundError:
            bak_mode = None
        if bak_mode is not None and not stat.S_ISREG(bak_mode):
            raise _BackupSlotRefused(bak)
        shutil.copy2(path, bak)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _guarded_atomic_write(path, text, dry):
    """atomic_write, turning a refused backup slot into a normal exit-1 diagnostic."""
    try:
        atomic_write(path, text, dry)
    except _BackupSlotRefused as exc:
        print(f"refusing to overwrite {exc.bak}: it exists and is not "
              "a regular file; move it aside and re-run.", file=sys.stderr)
        return 1
    return None


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
        data = manifest.read_state_json(path)
        if data is None:
            print(f"refusing to touch {path}: cannot read or parse it.",
                  file=sys.stderr)
            print("merge the PostToolUse entry from adapters/codex/hooks.json "
                  "by hand (see adapters/codex/INSTALL.md).", file=sys.stderr)
            return 1
        try:
            hooks = data["hooks"] if "hooks" in data else data.setdefault("hooks", {})
            post = hooks.setdefault("PostToolUse", [])
            if not isinstance(data, dict) or not isinstance(post, list):
                raise ValueError("unexpected structure")
        except (TypeError, AttributeError, ValueError) as e:
            print(f"refusing to touch {path}: cannot parse it ({e}).",
                  file=sys.stderr)
            print("merge the PostToolUse entry from adapters/codex/hooks.json "
                  "by hand (see adapters/codex/INSTALL.md).", file=sys.stderr)
            return 1
        ours = [h for block in post if isinstance(block, dict)
                for h in block.get("hooks", [])
                if isinstance(h, dict)
                and manifest.parse_managed_codex_hook(
                    block.get("matcher"), h) is not None]
        if ours:
            if all(h["command"] == command for h in ours):
                print(f"codex: already installed ({path})")
                return 0
            for h in ours:
                h["command"] = command
            rc = _guarded_atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
            if rc is not None:
                return rc
            print(f"codex: updated the checker path in {path}")
            print(TRUST_NOTE)
            return 0
        post.append(entry)
        rc = _guarded_atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
        if rc is not None:
            return rc
        print(f"codex: appended the PostToolUse hook to {path}")
    else:
        data = {"hooks": {"PostToolUse": [entry]}}
        rc = _guarded_atomic_write(path, json.dumps(data, indent=2) + "\n", dry)
        if rc is not None:
            return rc
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


def _snapshot_runnable(state, data):
    """Whether a guarded_pyz_state snapshot describes a runnable archive.

    The one validity seam install equality's neighbor status() reuses, so "installed" and "current" can never drift apart:
    executable, the expected interpreter, and every required member — checked entirely against the snapshot's own bytes (`io.BytesIO(data)`), never by reopening a destination pathname.
    """
    if state is None or not state[1]:
        return False
    if state[2] != b"#!" + PYZ_INTERPRETER.encode("utf-8"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return PYZ_REQUIRED_MEMBERS <= names


def guarded_pyz_state(dest):
    """(pyz identity, bytes) from one guarded snapshot of dest, or None.

    The lstat that decides the mode also supplies the owner-exec bit, the bytes come from the no-follow primitive, and the identity is computed on a private temp copy —
    the destination pathname is never handed to open, stat, or ZipFile directly,
    so a FIFO cannot hang us and a symlink is never followed.
    """
    try:
        st = os.lstat(dest)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    data = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
    if data is None:
        return None
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "copy"
        copy.write_bytes(data)
        if st.st_mode & stat.S_IXUSR:
            os.chmod(copy, 0o755)
        return pyz_state(copy), data


def pyz_runnable(path):
    """Whether the archive at path can actually run as the semlf command.

    Delegates to guarded_pyz_state so path is read exactly once, through the guard:
    not a symlink (install_cli refuses to manage one, so status must not bless one), readable, executable, the expected interpreter, and every required member.
    """
    snapshot = guarded_pyz_state(path)
    if snapshot is None:
        return False
    return _snapshot_runnable(*snapshot)


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


def _exclusive_backup(src, bak):
    """Copy src's bytes to bak, claiming the slot exclusively.

    O_EXCL is the point: the backup slot is claimed atomically,
    so a concurrent double --force cannot overwrite the only copy of a hand-patched artifact,
    and a pre-existing symlink at bak is refused, never followed.
    The cleanup covers every step including copystat:
    a failure at any point releases the slot,
    so a retry never finds it occupied by a half-made backup.
    """
    fd = os.open(str(bak), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(Path(src).read_bytes())
        shutil.copystat(src, bak)
    except BaseException:
        os.unlink(bak)
        raise


def _adopt_current_cli(dest, snapshot):
    """Record provenance for an install proven current by its snapshot.

    snapshot is guarded_pyz_state's (identity, bytes) pair — already verified equal to the fresh build by the caller — so adoption just records the digest of those same bytes.
    Nothing is re-read: the identity match is the whole proof, and re-recording an already-managed install is an idempotent replace of one state file.
    """
    manifest.record("cli", dest, core_version(),
                    manifest.sha256_bytes(snapshot[1]))


def install_cli(dry, force):
    """Install the executable pyz as the semlf command.

    Symlinks are refused outright.
    Provenance from the manifest decides everything past that:
    an exact-current copy is adopted or reported already installed, a copy this installer itself recorded upgrades without --force and without a backup (a recorded release is not the only copy of anything), and anything else needs --force and gets an exclusive backup before replacement.
    """
    dest = cli_bin_dest()
    if dest is None:
        print("refusing to install the cli: cannot determine a "
              "home directory to install it under.", file=sys.stderr)
        return 1
    if dest.is_symlink():
        print(f"refusing to touch {dest}: it is a symlink.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "semlf"
        build_pyz(fresh)
        divergent = False
        managed = False
        if os.path.lexists(dest):
            snapshot = guarded_pyz_state(dest)
            if snapshot is None:
                print(f"refusing to touch {dest}: it exists but is not "
                      "a readable regular file.", file=sys.stderr)
                return 1
            if snapshot[0] == pyz_state(fresh):
                print(f"cli: already installed ({dest})")
                _path_note(dest)
                if not dry:
                    _adopt_current_cli(dest, snapshot)
                return 0
            managed = manifest.classify("cli", dest) == "managed"
            if not force and not managed:
                print(f"refusing to overwrite {dest}: its content differs "
                      "from this build (hand-patched or older version). "
                      "re-run with --force to replace it.", file=sys.stderr)
                return 1
            divergent = True
    if dry:
        if not divergent:
            print(f"would install {dest}")
        elif managed:
            print(f"would upgrade {dest} (managed install)")
        else:
            bak = dest.with_name(dest.name + ".bak")
            if os.path.lexists(bak):
                print(f"refusing to overwrite {bak}: a backup already "
                      "exists; move it aside and re-run.", file=sys.stderr)
                return 1
            print(f"would back up and replace {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
    os.close(fd)
    staged = Path(staged_name)
    try:
        build_pyz(staged)
        digest = manifest.sha256_bytes(staged.read_bytes())
        if divergent and not managed:
            bak = dest.with_name(dest.name + ".bak")
            try:
                _exclusive_backup(dest, bak)
            except FileExistsError:
                os.unlink(staged)
                print(f"refusing to overwrite {bak}: a backup already "
                      "exists; move it aside and re-run.", file=sys.stderr)
                return 1
            except OSError as exc:
                os.unlink(staged)
                print(f"cannot back up {dest} to {bak}: {exc}",
                      file=sys.stderr)
                return 1
            os.replace(staged, dest)
        elif divergent:
            os.replace(staged, dest)
        elif not _publish_new(staged, dest):
            print(f"refusing to overwrite {dest}: it appeared after "
                  "classification; re-run so it can be classified.",
                  file=sys.stderr)
            return 1
    except BaseException:
        if staged.exists():
            os.unlink(staged)
        raise
    manifest.record("cli", dest, core_version(), digest)
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
    if os.path.lexists(dest):
        current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
        if current is None:
            print(f"refusing to touch {dest}: it exists but is not a "
                  "readable regular file.", file=sys.stderr)
            return 1
        if current == payload:
            print(f"codex skill: already installed ({dest})")
            return 0
        if not force:
            print(f"refusing to overwrite {dest}: its content differs "
                  "from this repo's copy (hand-patched or older version). "
                  "re-run with --force to replace it.", file=sys.stderr)
            return 1
    rc = _guarded_atomic_write(dest, body, dry)
    if rc is not None:
        return rc
    if not dry:
        manifest.record("codex-skill", dest, core_version(),
                        manifest.sha256_bytes(payload))
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
    for src, name in ((OPENCODE_PLUGIN, "opencode-plugin"),
                       (CHECKER, "opencode-checker")):
        dest = dest_dir / src.name
        payload = src.read_bytes()
        if os.path.lexists(dest):
            current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
            if current is None:
                print(f"refusing to touch {dest}: it exists but is not a "
                      "readable regular file.", file=sys.stderr)
                rc = 1
                continue
            if current == payload:
                skipped += 1
                continue
            if not force:
                print(f"refusing to overwrite {dest}: its content differs "
                      "from this repo's copy (hand-patched or older version). "
                      "re-run with --force to replace it.", file=sys.stderr)
                rc = 1
                continue
        write_rc = _guarded_atomic_write(dest, payload.decode("utf-8"), dry)
        if write_rc is not None:
            rc = write_rc
            continue
        if not dry:
            manifest.record(name, dest, core_version(),
                            manifest.sha256_bytes(payload))
        copied += 1
    if rc == 0 and copied == 0:
        print(f"opencode: already installed ({dest_dir})")
    elif copied:
        print(f"opencode: installed {copied} file(s) into {dest_dir}")
    print("note: the skill needs no copy when the Claude plugin is installed; "
          "see adapters/opencode/INSTALL.md otherwise.")
    return rc


def agents_block():
    body = SNIPPET.read_text(encoding="utf-8")
    return f"{SENTINEL_OPEN}\n{body.rstrip()}\n{SENTINEL_CLOSE}\n"


def _semlf_note():
    if shutil.which("semlf") is None:
        print("note: semlf is not on PATH; the snippet's check command "
              "needs it. run install.py --cli first.")


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
            _semlf_note()
            return 0
    else:
        new = block
    rc = _guarded_atomic_write(target, new, dry)
    if rc is not None:
        return rc
    print(f"agentsmd: wrote the snippet block to {target}")
    _semlf_note()
    return 0


# --- Uninstall -------------------------------------------------------------
#
# One entry point, two phases.
# Preflight (the _plan_* helpers) is read-only: it classifies every selected target and appends either a (label, apply_callable) pair to `actions` or a human-readable string to `refusals`.
# A `None` apply_callable marks a no-op note — printed as information, never treated as a mutation.
# `uninstall` refuses the whole request the moment any target is inadmissible, before `_apply` runs.


def _write_shared(path, text):
    """atomic_write for a shared-file uninstall edit (hooks.json, AGENTS.md).

    Folds a refused backup slot into a plain OSError so _apply's one except clause handles every planned action's failure the same way.
    """
    try:
        atomic_write(path, text, False)
    except _BackupSlotRefused as exc:
        raise OSError(f"backup slot {exc.bak} exists and is not a regular "
                      "file; move it aside and re-run") from exc


def _bak_sibling_ok(path):
    """Whether path's .bak sibling is absent or a plain regular file.

    The rewrite's own backup copy would otherwise write through a symlink
    or other special file left in that slot, so preflight must see it too.
    """
    bak = path.with_name(path.name + ".bak")
    try:
        return not os.path.lexists(bak) or stat.S_ISREG(os.lstat(bak).st_mode)
    except OSError:
        return False


def _plan_codex_hook(actions, refusals):
    home = codex_home()
    if home is None:
        refusals.append("refusing to uninstall the codex hook: cannot "
                        "determine a home directory to uninstall it from.")
        return
    path = home / "hooks.json"
    if not os.path.lexists(path):
        actions.append((f"codex: not installed ({path})", None))
        return
    data = manifest.read_state_json(path)
    # Same parity as install_codex's own guard: a shape too strange to locate PostToolUse in — a non-dict top level, a "hooks" value that isn't a dict, or a "PostToolUse" value that isn't a list — is a refusal, not silently nothing-to-do.
    # A "hooks" or "PostToolUse" key that is simply *absent* from an otherwise-sane dict is not strange; it is empty, and empty is a legitimate no-op.
    hooks = data.get("hooks", {}) if isinstance(data, dict) else None
    post = hooks.get("PostToolUse", []) if isinstance(hooks, dict) else None
    if not isinstance(data, dict) or not isinstance(hooks, dict) or not isinstance(post, list):
        refusals.append(f"refusing to touch {path}: cannot read or parse "
                        "it; repair or remove it by hand.")
        return
    if not _bak_sibling_ok(path):
        bak = path.with_name(path.name + ".bak")
        refusals.append(f"refusing to touch {path}: its backup slot {bak} "
                        "exists and is not a regular file; move it aside "
                        "and re-run.")
        return
    changed = False
    new_post = []
    for block in post:
        if isinstance(block, dict) and isinstance(block.get("hooks"), list):
            original = block["hooks"]
            kept = [h for h in original
                    if not (isinstance(h, dict)
                            and manifest.parse_managed_codex_hook(
                                block.get("matcher"), h) is not None)]
            if len(kept) == len(original):
                # Nothing of ours was in this block: preserve it exactly, including a foreign block that was already empty before we ever looked at it.
                new_post.append(block)
                continue
            changed = True
            if kept:
                block = dict(block)
                block["hooks"] = kept
                new_post.append(block)
            # else: our own filtering emptied this block; drop it.
        else:
            new_post.append(block)
    hooks["PostToolUse"] = new_post
    if not changed:
        actions.append((f"codex: no managed hook entry found in {path}", None))
        return
    text = json.dumps(data, indent=2) + "\n"
    def _do(path=path, text=text):
        _write_shared(path, text)
    actions.append((f"the managed hook entry from {path}", _do))


def _prune_empty_parent(dest):
    parent = dest.parent
    try:
        if not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def _forget_note(dest, name):
    """Unlink already succeeded.

    Forget provenance without letting its own failure masquerade as dest never having been removed.
    Returns None on a clean forget.
    On a raised OSError it returns an accurate stderr line instead — the caller still counts dest as removed either way.
    """
    try:
        manifest.forget(name)
    except OSError as exc:
        return (f"removed {dest}, but could not clear its provenance "
               f"record: {exc}")
    return None


def _plan_file(label, dest, reference_bytes, name, force, actions, refusals,
               prune_parent=False):
    """Plan removal of one installer-owned file, or a refusal.

    Shared by the codex skill and both opencode files.
    `_plan_cli` layers one extra admission rule (pyz identity) on top of the same shape.
    """
    if dest is None:
        refusals.append(f"refusing to uninstall the {label}: cannot "
                        "determine a home directory to uninstall it from.")
        return
    dest = Path(dest)
    try:
        st = os.lstat(dest)
    except OSError:
        actions.append((f"{label}: not installed ({dest})", None))
        return
    if stat.S_ISDIR(st.st_mode):
        refusals.append(f"refusing to remove {dest}: it is a directory; "
                        "removing a tree is not this verb's one-file unlink.")
        return
    admit = False
    reason = None
    if not stat.S_ISREG(st.st_mode):
        reason = (f"refusing to remove {dest}: it is not a regular file "
                  "(symlink or special file).")
    else:
        current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
        if current is None:
            reason = (f"refusing to remove {dest}: it exists but is not a "
                      "readable regular file.")
        elif current == reference_bytes or manifest.classify(name, dest) == "managed":
            admit = True
        else:
            reason = (f"refusing to remove {dest}: its content differs from "
                      "what this kit installed (hand-patched or older "
                      "version).")
    if not (admit or force):
        refusals.append(reason + " re-run with --force to remove it anyway.")
        return
    def _do(dest=dest, name=name, prune_parent=prune_parent):
        os.unlink(dest)
        note = _forget_note(dest, name)
        if prune_parent:
            _prune_empty_parent(dest)
        return note
    actions.append((str(dest), _do))


def _plan_opencode(actions, refusals, force):
    dest_dir = opencode_plugins_dir()
    if dest_dir is None:
        refusals.append("refusing to uninstall opencode: cannot determine "
                        "a home directory to uninstall it from.")
        return
    _plan_file("opencode plugin", dest_dir / OPENCODE_PLUGIN.name,
              OPENCODE_PLUGIN.read_bytes(), "opencode-plugin", force,
              actions, refusals)
    _plan_file("opencode checker", dest_dir / CHECKER.name,
              CHECKER.read_bytes(), "opencode-checker", force,
              actions, refusals)


def _plan_cli(actions, refusals, force):
    """_plan_file's rules plus one admit: pyz identity against a fresh build.

    The live destination is never handed to pyz_state directly — only guarded_pyz_state's private temp copy, and a fresh temporary build, may use it.
    So a FIFO at dest cannot hang this check, and a symlink is never followed into.
    """
    dest = cli_bin_dest()
    if dest is None:
        refusals.append("refusing to uninstall the cli: cannot determine a "
                        "home directory to uninstall it from.")
        return
    dest = Path(dest)
    try:
        st = os.lstat(dest)
    except OSError:
        actions.append((f"cli: not installed ({dest})", None))
        _plan_cli_bak_note(dest, actions)
        return
    if stat.S_ISDIR(st.st_mode):
        refusals.append(f"refusing to remove {dest}: it is a directory; "
                        "removing a tree is not this verb's one-file unlink.")
        return
    admit = False
    reason = None
    if not stat.S_ISREG(st.st_mode):
        reason = (f"refusing to remove {dest}: it is not a regular file "
                  "(symlink or special file).")
    else:
        snapshot = guarded_pyz_state(dest)
        if snapshot is None:
            reason = (f"refusing to remove {dest}: it exists but is not a "
                      "readable regular file.")
        else:
            with tempfile.TemporaryDirectory() as td:
                fresh = Path(td) / "semlf"
                build_pyz(fresh)
                identity_match = snapshot[0] == pyz_state(fresh)
            classification = manifest.classify("cli", dest)
            # A manifest that proves divergence ("edited") outranks the coarser pyz snapshot.
            # The snapshot only substitutes for a *missing* provenance record ("unrecorded"); it never overrides a provenance record that says otherwise.
            if classification == "managed" or (
                    classification != "edited" and identity_match):
                admit = True
            else:
                reason = (f"refusing to remove {dest}: its content differs "
                          "from this build (hand-patched or older version).")
    if admit or force:
        def _do(dest=dest):
            os.unlink(dest)
            return _forget_note(dest, "cli")
        actions.append((str(dest), _do))
    else:
        refusals.append(reason + " re-run with --force to remove it anyway.")
    _plan_cli_bak_note(dest, actions)


def _plan_cli_bak_note(dest, actions):
    bak = dest.with_name(dest.name + ".bak")
    if os.path.lexists(bak):
        actions.append((f"note: {bak} is your own backup; it is never "
                        "touched by uninstall.", None))


def _plan_agentsmd(target, actions, refusals):
    """Plan splicing the sentinel block out of target, or a refusal.

    target is user-owned, so --force never overrides a refusal here —
    unlike the installer-owned single-file artifacts above.
    """
    try:
        st = os.lstat(target)
    except OSError:
        actions.append((f"agentsmd: not installed ({target})", None))
        return
    if not stat.S_ISREG(st.st_mode):
        refusals.append(f"refusing to touch {target}: it is not a regular "
                        "file; repair it by hand.")
        return
    if not _bak_sibling_ok(target):
        bak = target.with_name(target.name + ".bak")
        refusals.append(f"refusing to touch {target}: its backup slot {bak} "
                        "exists and is not a regular file; move it aside "
                        "and re-run.")
        return
    data = manifest.read_regular_bytes(target, manifest.CLASSIFY_LIMIT)
    if data is None:
        refusals.append(f"refusing to touch {target}: cannot read it; "
                        "repair or remove it by hand.")
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        refusals.append(f"refusing to touch {target}: cannot decode it as "
                        "UTF-8; repair it by hand.")
        return
    has_open = SENTINEL_OPEN in text
    has_close = SENTINEL_CLOSE in text
    if has_open != has_close:
        refusals.append(f"refusing to touch {target}: found one sentinel "
                        "marker without its pair; repair the block by hand.")
        return
    if has_open and (text.count(SENTINEL_OPEN) != 1
                      or text.count(SENTINEL_CLOSE) != 1
                      or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
        refusals.append(f"refusing to touch {target}: sentinel markers are "
                        "out of order or repeated; repair the block by hand.")
        return
    if not has_open:
        actions.append((f"agentsmd: no block found in {target}", None))
        return
    def _do(target=target, text=text):
        pre = text.split(SENTINEL_OPEN)[0]
        post = text.split(SENTINEL_CLOSE, 1)[1].lstrip("\n")
        new = pre.rstrip("\n")
        if new and post:
            new = new + "\n\n" + post
        elif post:
            new = post
        elif new:
            new = new + "\n"
        _write_shared(target, new)
    actions.append((f"the semantic-linefeeds block from {target}", _do))


def _apply(actions, dry_run):
    """Execute every planned action, or report the dry-run plan.

    Runs what preflight admitted without revalidating it — a target mutated between the two phases is same-user concurrency, out of scope by ADR-0014's stated boundary.
    Stops at the first unexpected OSError and reports what was and was not removed.
    """
    if dry_run:
        for label, fn in actions:
            if fn is None:
                print(label)
            else:
                print(f"[dry-run] would remove {label}")
        return 0
    removed = []
    had_error = False
    for i, (label, fn) in enumerate(actions):
        if fn is None:
            print(label)
            continue
        try:
            note = fn()
        except OSError as exc:
            remaining = [l for l, f in actions[i + 1:] if f is not None]
            print(f"error while removing {label}: {exc}", file=sys.stderr)
            print("removed so far: "
                  + (", ".join(removed) if removed else "(nothing)"),
                  file=sys.stderr)
            print("not removed: " + ", ".join([label] + remaining),
                  file=sys.stderr)
            return 1
        # A non-None return is a partial-failure note (e.g. the unlink succeeded but manifest.forget could not run): the removal still counts as done, but the request as a whole still failed.
        if note:
            print(note, file=sys.stderr)
            had_error = True
        else:
            print(f"removed {label}")
        removed.append(label)
    return 1 if had_error else 0


def uninstall(args):
    """Preflight every selected target, then apply only if all admit."""
    actions, refusals = [], []
    if args.codex:
        _plan_codex_hook(actions, refusals)
        _plan_file("codex skill", codex_skill_dest(), codex_skill_body().encode("utf-8"),
                  "codex-skill", args.force, actions, refusals, prune_parent=True)
    if args.opencode:
        _plan_opencode(actions, refusals, args.force)
    if args.cli:
        _plan_cli(actions, refusals, args.force)
    if args.agentsmd is not None:
        _plan_agentsmd(Path(args.agentsmd), actions, refusals)
    for refusal in refusals:
        print(refusal, file=sys.stderr)
    if refusals:
        return 1
    return _apply(actions, args.dry_run)


def main():
    ap = argparse.ArgumentParser(prog="install", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codex", action="store_true",
                    help="install the Codex CLI hook and the native semantic-linefeeds skill")
    ap.add_argument("--opencode", action="store_true",
                    help="install the opencode plugin and checker")
    ap.add_argument("--agentsmd", nargs="?", const="", default=None,
                    metavar="PATH",
                    help="write the snippet block into PATH "
                         "(an explicit path is required)")
    ap.add_argument("--cli", action="store_true",
                    help="build the semlf zipapp and install it as ~/.local/bin/semlf")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned actions without writing anything")
    ap.add_argument("--force", action="store_true",
                    help="overwrite opencode, codex-skill, or cli files whose content has diverged")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove a previously installed artifact "
                         "(requires a mode flag)")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    if args.agentsmd is not None and not args.agentsmd:
        print("install: --agentsmd requires an explicit path; "
              "refusing to default to ./AGENTS.md.", file=sys.stderr)
        sys.exit(64)
    if args.uninstall:
        if not (args.codex or args.opencode or args.cli or args.agentsmd is not None):
            print("install: --uninstall requires a mode flag (--codex, "
                  "--opencode, --cli, --agentsmd PATH).", file=sys.stderr)
            sys.exit(64)
        sys.exit(uninstall(args))
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
    elif not os.path.lexists(cli_dest):
        print(f"cli: not installed ({cli_dest})")
    else:
        snapshot = guarded_pyz_state(cli_dest)
        if snapshot is None or not _snapshot_runnable(*snapshot):
            # Same validity seam as install equality:
            # a foreign shebang, a stripped execute bit, a missing member, or an unreadable/non-regular object is never "installed" —
            # and a FIFO here must never hang this check.
            print(f"cli: present but not runnable ({cli_dest})")
        else:
            state, data = snapshot
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    text = archive.read("check_linefeeds.py").decode("utf-8")
                match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
                version = match.group(1) if match else "unknown"
            except (KeyError, zipfile.BadZipFile, UnicodeDecodeError):
                version = "unknown"
            print(f"cli: installed (v{version}) ({cli_dest})")

    home = codex_home()
    if home is None:
        print("codex: no home to check")
    else:
        hooks_path = home / "hooks.json"
        state = "not installed"
        if hooks_path.exists():
            data = manifest.read_state_json(hooks_path)
            if data is None:
                state = "unreadable"
            else:
                try:
                    managed = [h.get("command", "")
                               for block in data.get("hooks", {}).get("PostToolUse", [])
                               if isinstance(block, dict)
                               for h in block.get("hooks", [])
                               if isinstance(h, dict)
                               and manifest.parse_managed_codex_hook(
                                   block.get("matcher"), h) is not None]
                except AttributeError:
                    managed = []
                    state = "unreadable"
                else:
                    if any(c == desired_codex_command() for c in managed):
                        state = "installed"
                    elif managed:
                        state = "installed (stale checker path; re-run --codex)"
        print(f"codex: {state} ({hooks_path})")

    skill_dest = codex_skill_dest()
    if skill_dest is None:
        print("codex skill: no home to check")
    else:
        skill_state = "not installed"
        if os.path.lexists(skill_dest):
            raw = manifest.read_regular_bytes(skill_dest, manifest.CLASSIFY_LIMIT)
            if raw is None:
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
        matched = []
        unreadable = []
        for s in (OPENCODE_PLUGIN, CHECKER):
            dest = d / s.name
            if not os.path.lexists(dest):
                continue
            raw = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
            if raw is None:
                unreadable.append(s.name)
            elif raw == s.read_bytes():
                matched.append(s.name)
        if unreadable:
            print(f"opencode: unreadable — {', '.join(unreadable)} ({d})")
        elif len(matched) == 2:
            print(f"opencode: installed ({d})")
        elif matched:
            print(f"opencode: partial — only {matched[0]} matches ({d})")
        else:
            print(f"opencode: not installed ({d})")

    agents = Path("AGENTS.md").resolve()
    mark = "absent"
    if agents.exists():
        try:
            if SENTINEL_OPEN in agents.read_text(encoding="utf-8"):
                mark = "present"
        except (ValueError, OSError):
            mark = "absent (unreadable)"
    print(f"agentsmd: block {mark} in {agents}")

    print("claude: managed by Claude Code itself — install with:")
    print("  claude plugin marketplace add /path/to/semantic-linefeeds  # or a private git remote")
    print("  claude plugin install semantic-linefeeds@semantic-linefeeds")
    return 0


if __name__ == "__main__":
    main()
