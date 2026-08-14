#!/usr/bin/env python3
"""Install the semantic-linefeeds adapters into local AI coding agents.

Modes:
  --codex           merge the PostToolUse hook into $CODEX_HOME/hooks.json (default ~/.codex/hooks.json), append-never-overwrite, pointed at the neutral data root; also installs the native semantic-linefeeds skill under ~/.agents/skills and publishes the checker and README payloads under the neutral data root
  --opencode        copy the plugin and the checker side by side into $XDG_CONFIG_HOME/opencode/plugins (default ~/.config/...)
  --agentsmd PATH   manage a sentinel-marked snippet block in PATH (an explicit path is required)
  --cli             build the semlf zipapp and install it as ~/.local/bin/semlf
  --auto            detect installed agents by evidence (binary on PATH or config dir) and install a matching mode for each, plus the cli unconditionally
  (no mode)         report install status; no longer probes ./AGENTS.md — check a specific file with `semlf status agentsmd PATH`

Claude Code is installed through its own plugin marketplace and is never touched by this script.
Every selected flag combination preflights as one request: any leg's refusal aborts the whole request before the first write.
Options: --dry-run prints planned actions without writing.
--force allows overwriting opencode, codex-skill, or cli files whose content has diverged.
--uninstall removes an installed mode's artifacts instead of installing them.
It requires at least one mode flag and honors --dry-run and --force the same way.
--auto is mutually exclusive with every explicit mode flag and with --uninstall (64).
Exit codes: 0 success or no-op, 1 refusal or error, 64 usage error.
"""

import argparse
import hashlib
import io
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
CLI_PKG = REPO / "cli" / "semlf"
PYZ_INTERPRETER = "/usr/bin/env python3"
MAIN_STUB = "from semlf.cli import main\nraise SystemExit(main())\n"

sys.path.insert(0, str(REPO / "cli"))
from semlf import (
    lifecycle,  # noqa: E402 -- must follow the path insert above
    manifest,  # noqa: E402
    registry,  # noqa: E402
)
from semlf.lifecycle import (
    _forget_note,
)
from semlf.lifecycle import (  # noqa: E402
    exclusive_backup as _exclusive_backup,
)
from semlf.lifecycle import (
    publish_exclusive as _publish_new,
)
from semlf.manifest import (  # noqa: E402
    cli_bin_dest,
    codex_skill_dest,  # noqa: F401 -- re-exported for install_module.codex_skill_dest() in tests
)

PYZ_REQUIRED_MEMBERS = frozenset(
    {
        "__main__.py",
        "check_linefeeds.py",
        "semlf/__init__.py",
        "semlf/cli.py",
        "semlf/providers.py",
        "semlf/doctor.py",
        "semlf/manifest.py",
        "semlf/registry.py",
        "semlf/classify.py",
        "semlf/lifecycle.py",
    }
    | {row.member for row in registry.ROWS}
)


def core_version():
    """The repo core's version, read textually so nothing is imported."""
    match = re.search(
        r'^__version__ = "([^"]+)"$', CHECKER.read_text(encoding="utf-8"), re.MULTILINE
    )
    return match.group(1) if match else "unknown"


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
        registry.stage_payloads(stage, repo=REPO)
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
    # An artifact's identity check must never crash the installer:
    # a hostile or merely corrupt archive can raise far more than BadZipFile —
    # an encrypted member raises RuntimeError,
    # an unsupported compression method raises NotImplementedError,
    # a truncated or tampered deflate stream can surface as zlib.error,
    # and a tampered LZMA member's properties raise lzma.LZMAError,
    # which is not an OSError subclass and is not named here directly:
    # lzma is an optional stdlib module that zipfile itself only imports lazily,
    # so a bare "except Exception" is this function's actual totality contract —
    # every one of these means the same thing here: not a usable pyz.
    except Exception:
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


def _adopt_current_cli(dest, snapshot):
    """Record provenance for an install proven current by its snapshot.

    snapshot is guarded_pyz_state's (identity, bytes) pair — already verified equal to the fresh build by the caller — so adoption just records the digest of those same bytes.
    Nothing is re-read: the identity match is the whole proof, and re-recording an already-managed install is an idempotent replace of one state file.
    """
    manifest.record("cli", dest, core_version(), manifest.sha256_bytes(snapshot[1]))


def _plan_cli_install(planned, refusals, force):
    """install_cli's admission, read-only, as one plan leg.

    The decision table is install_cli's own, unchanged:
    a None destination or a symlink refuses;
    an unreadable object refuses;
    identity match with the fresh build plans an adopt no-op;
    a manifest-managed copy plans an upgrade without a backup;
    anything else refuses without --force,
    and with --force plans the exclusive backup unless the slot is occupied, which still refuses.
    The apply closure carries the remaining install_cli body:
    stage a fresh build in dest's directory, back up if planned,
    publish (exclusively for a fresh install), and record.
    planned may be empty on entry — a bare `--cli` run is exactly
    that — and this leg simply appends to whatever it is handed.
    """
    dest = cli_bin_dest()
    if dest is None:
        refusals.append(
            "refusing to install the cli: cannot determine a "
            "home directory to install it under."
        )
        return
    if dest.is_symlink():
        refusals.append(f"refusing to touch {dest}: it is a symlink.")
        return
    snapshot = None
    divergent = False
    managed = False
    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "semlf"
        build_pyz(fresh)
        fresh_state = pyz_state(fresh)
        if os.path.lexists(dest):
            snapshot = guarded_pyz_state(dest)
            if snapshot is None:
                refusals.append(
                    f"refusing to touch {dest}: it exists but "
                    "is not a readable regular file."
                )
                return
            if snapshot[0] == fresh_state:

                def _do(dest=dest, snapshot=snapshot):
                    _path_note(dest)
                    _adopt_current_cli(dest, snapshot)
                    return None

                planned.append(
                    lifecycle.Planned(
                        f"cli: already installed ({dest})", "cli", dest, None, _do
                    )
                )
                return
            managed = manifest.classify("cli", dest) == "managed"
            if not force and not managed:
                refusals.append(
                    f"refusing to overwrite {dest}: its "
                    "content differs from this build "
                    "(hand-patched or older version). "
                    "re-run with --force to replace it."
                )
                return
            divergent = True

    if not divergent:
        label = f"would install {dest}"
    elif managed:
        label = f"would upgrade {dest} (managed install)"
    else:
        bak = dest.with_name(dest.name + ".bak")
        if os.path.lexists(bak):
            refusals.append(
                f"refusing to overwrite {bak}: a backup "
                "already exists; move it aside and re-run."
            )
            return
        label = f"would back up and replace {dest}"

    def _do(dest=dest, divergent=divergent, managed=managed, snapshot=snapshot):
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
                    _exclusive_backup(dest, bak, snapshot[1])
                except FileExistsError:
                    os.unlink(staged)
                    return (
                        f"refusing to overwrite {bak}: a backup "
                        "already exists; move it aside and re-run."
                    )
                except OSError as exc:
                    os.unlink(staged)
                    return f"cannot back up {dest} to {bak}: {exc}"
                os.replace(staged, dest)
            elif divergent:
                os.replace(staged, dest)
            elif not _publish_new(staged, dest):
                return (
                    f"refusing to overwrite {dest}: it appeared "
                    "after classification; re-run so it can be "
                    "classified."
                )
        except BaseException:
            if staged.exists():
                os.unlink(staged)
            raise
        manifest.record("cli", dest, core_version(), digest)
        _path_note(dest)
        return None

    planned.append(
        lifecycle.Planned(
            label, "cli", dest, None, _do, done=f"cli: installed ({dest})"
        )
    )


def install_cli(dry, force):
    """Compatibility wrapper over the split pair.

    The direct-call tests and their monkeypatch seams stay green;
    the composed request path uses the planner directly.
    """
    planned, refusals = [], []
    _plan_cli_install(planned, refusals, force)
    if dry:
        lifecycle.describe_plan(planned, refusals, prefix="[dry-run] ")
        return 0
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    return lifecycle.apply_plan(planned)


# --- Uninstall -------------------------------------------------------------
#
# One entry point, two phases, over the same shared planners the install side uses.
# Preflight is read-only:
# it classifies every selected target and appends a lifecycle.Planned to `planned` or a human-readable string to `refusals`.
# A `do=None` entry is a no-op note, printed as information, never treated as a mutation.
# `uninstall` refuses the whole request the moment any target is inadmissible, before apply_plan runs.


def _plan_cli_bak_note(dest, planned):
    bak = dest.with_name(dest.name + ".bak")
    if os.path.lexists(bak):
        planned.append(
            lifecycle.Planned(
                f"note: {bak} is your own backup; it is never touched by uninstall.",
                "cli",
                dest,
                None,
                None,
            )
        )


def _plan_cli(planned, refusals, force):
    """_plan_file's rules plus one admit: pyz identity against a fresh build.

    The live destination is never handed to pyz_state directly — only guarded_pyz_state's private temp copy, and a fresh temporary build, may use it.
    So a FIFO at dest cannot hang this check, and a symlink is never followed into.
    """
    dest = cli_bin_dest()
    if dest is None:
        refusals.append(
            "refusing to uninstall the cli: cannot determine a "
            "home directory to uninstall it from."
        )
        return
    dest = Path(dest)
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        planned.append(
            lifecycle.Planned(f"cli: not installed ({dest})", "cli", dest, None, None)
        )
        _plan_cli_bak_note(dest, planned)
        return
    except OSError as exc:
        refusals.append(f"refusing to uninstall the cli: cannot inspect {dest}: {exc}.")
        return
    if stat.S_ISDIR(st.st_mode):
        refusals.append(
            f"refusing to remove {dest}: it is a directory; "
            "removing a tree is not this verb's one-file unlink."
        )
        return
    admit = False
    reason = None
    if not stat.S_ISREG(st.st_mode):
        reason = (
            f"refusing to remove {dest}: it is not a regular file "
            "(symlink or special file)."
        )
    else:
        snapshot = guarded_pyz_state(dest)
        if snapshot is None:
            reason = (
                f"refusing to remove {dest}: it exists but is not a "
                "readable regular file."
            )
        else:
            with tempfile.TemporaryDirectory() as td:
                fresh = Path(td) / "semlf"
                build_pyz(fresh)
                identity_match = snapshot[0] == pyz_state(fresh)
            classification = manifest.classify("cli", dest)
            # A manifest that proves divergence ("edited") outranks the coarser pyz snapshot.
            # The snapshot only substitutes for a *missing* provenance record ("unrecorded"); it never overrides a provenance record that says otherwise.
            if classification == "managed" or (
                classification != "edited" and identity_match
            ):
                admit = True
            else:
                reason = (
                    f"refusing to remove {dest}: its content differs "
                    "from this build (hand-patched or older version)."
                )
    if admit or force:

        def _do(dest=dest):
            os.unlink(dest)
            return _forget_note(dest, "cli")

        planned.append(
            lifecycle.Planned(str(dest), "cli", dest, None, _do, done=f"removed {dest}")
        )
    else:
        refusals.append(reason + " re-run with --force to remove it anyway.")
    _plan_cli_bak_note(dest, planned)


def uninstall(args):
    """Preflight every selected target, then apply only if all admit."""
    planned, refusals = [], []
    destinations = lifecycle.payload_destinations()
    if args.codex:
        lifecycle.plan_remove_codex_hook(planned, refusals)
        lifecycle.plan_remove_file(
            "codex skill",
            destinations["codex-skill"],
            "codex-skill",
            args.force,
            planned,
            refusals,
            prune_parent=True,
        )
    if args.opencode:
        lifecycle.plan_remove_file(
            "opencode plugin",
            destinations["opencode-plugin"],
            "opencode-plugin",
            args.force,
            planned,
            refusals,
        )
        lifecycle.plan_remove_file(
            "opencode checker",
            destinations["opencode-checker"],
            "opencode-checker",
            args.force,
            planned,
            refusals,
        )
    if args.cli:
        _plan_cli(planned, refusals, args.force)
    if args.agentsmd is not None:
        lifecycle.plan_remove_agentsmd(Path(args.agentsmd), planned, refusals)
    if args.dry_run:
        # Dry-run dominates everything:
        # it reports the would-be refusals instead of taking them, and exits 0.
        # This is the same fixed precedence lifecycle.uninstall_command uses on the package door.
        for item in planned:
            print(
                item.label
                if item.do is None
                else f"[dry-run] would remove {item.label}"
            )
        for refusal in refusals:
            print(f"[dry-run] would refuse: {refusal}")
        return 0
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    return lifecycle.apply_plan(planned)


def _run_request(targets, agentsmd_path, cli, dry, force):
    """One preflight-then-apply request across every selected leg.

    A checkout flag is an explicit action, so it is consent:
    no prompt, exactly like naming a target on the package door.
    """
    planned, refusals = lifecycle.plan_install(targets, agentsmd_path, force)
    if cli:
        _plan_cli_install(planned, refusals, force)
    if dry:
        lifecycle.describe_plan(planned, refusals, prefix="[dry-run] ")
        return 0
    if refusals:
        lifecycle.describe_plan(planned, [])
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    return lifecycle.apply_plan(planned)


def main():
    ap = argparse.ArgumentParser(
        prog="install",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--codex",
        action="store_true",
        help="install the Codex CLI hook and the native "
        "semantic-linefeeds skill; also publishes the "
        "checker and README under the neutral data root",
    )
    ap.add_argument(
        "--opencode",
        action="store_true",
        help="install the opencode plugin and checker",
    )
    ap.add_argument(
        "--agentsmd",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="write the snippet block into PATH (an explicit path is required)",
    )
    ap.add_argument(
        "--cli",
        action="store_true",
        help="build the semlf zipapp and install it as ~/.local/bin/semlf",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned actions without writing anything",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite opencode, codex-skill, or cli files whose content has diverged",
    )
    ap.add_argument(
        "--uninstall",
        action="store_true",
        help="remove a previously installed artifact (requires a mode flag)",
    )
    ap.add_argument(
        "--auto",
        action="store_true",
        help="detect installed agents and install for each "
        "one found, plus the cli unconditionally",
    )
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    if args.agentsmd is not None and not args.agentsmd:
        print(
            "install: --agentsmd requires an explicit path; "
            "refusing to default to ./AGENTS.md.",
            file=sys.stderr,
        )
        sys.exit(64)
    if args.auto and (
        args.codex
        or args.opencode
        or args.cli
        or args.agentsmd is not None
        or args.uninstall
    ):
        print(
            "install: --auto cannot be combined with a mode flag or --uninstall.",
            file=sys.stderr,
        )
        sys.exit(64)
    if args.uninstall:
        if not (args.codex or args.opencode or args.cli or args.agentsmd is not None):
            print(
                "install: --uninstall requires a mode flag (--codex, "
                "--opencode, --cli, --agentsmd PATH).",
                file=sys.stderr,
            )
            sys.exit(64)
        sys.exit(uninstall(args))
    codes = []
    if args.auto:
        detected = dict(lifecycle.detect_agents())
        for agent in ("codex", "opencode"):
            if agent in detected:
                print(f"{agent}: detected ({detected[agent]})")
            else:
                print(f"{agent}: not detected; skipped")
        targets = [a for a in ("codex", "opencode") if a in detected]
        codes.append(
            _run_request(targets, None, cli=True, dry=args.dry_run, force=args.force)
        )
        lifecycle.claude_code_trailer()
    else:
        targets = [
            a for a, on in (("codex", args.codex), ("opencode", args.opencode)) if on
        ]
        agentsmd = Path(args.agentsmd) if args.agentsmd is not None else None
        if targets or agentsmd is not None or args.cli:
            codes.append(
                _run_request(
                    targets, agentsmd, cli=args.cli, dry=args.dry_run, force=args.force
                )
            )
    if not codes:
        codes.append(status())
    sys.exit(max(codes))


def _print_cli_status():
    """The checkout door's own cli/zipapp status section."""
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


def status():
    """The checkout door's no-flag report.

    The cli/zipapp section is checkout-owned and prints first;
    everything else is the shared status body, which already ends with the shim warning and the Claude Code trailer.
    """
    _print_cli_status()
    return lifecycle.status_command([], shim_expected=cli_bin_dest())


if __name__ == "__main__":
    main()
