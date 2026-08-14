"""semlf doctor — replay reality, report evidence (ADR-0014).

Every check either exercises the installed artifact end to end
or reports evidence a human (or ADR-0011's gate) needs verbatim.
Checks fail loudly; environment observations only warn.
Exit 0 when every check passes, 1 when any fails, 64 on usage.
"""
import json
import os
import platform
import shutil
import stat
import subprocess
import sys

import check_linefeeds as core
from semlf import lifecycle, manifest, registry

BAD_PAYLOAD = json.dumps({"tool_input": {
    "file_path": "/x/a.md",
    "new_string": "One sentence. Two sentence.\n"}})
GOOD_PAYLOAD = json.dumps({"tool_input": {
    "file_path": "/x/a.md",
    "new_string": "One sentence.\n"}})
CODEX_PAYLOAD = json.dumps({
    "hook_event_name": "PostToolUse",
    "tool_name": "apply_patch",
    "tool_input": {"command": (
        "*** Begin Patch\n*** Update File: pkg/doc.go\n@@\n"
        "+// Package cache provides caches. A cache\n"
        "+// holds entries.\n*** End Patch")},
    "tool_response": {"output": "Done"}})
CODEX_CLEAN_PAYLOAD = json.dumps({
    "hook_event_name": "PostToolUse",
    "tool_name": "apply_patch",
    "tool_input": {"command": (
        "*** Begin Patch\n*** Update File: pkg/doc.go\n@@\n"
        "+// Package cache provides caches.\n*** End Patch")},
    "tool_response": {"output": "Done"}})


def _diag(s):
    """An arbitrary string, made safe to interpolate into a printed line.

    A recorded provenance path or a hooks.json checker path is schema-valid but attacker-controlled text.
    Backslash-escaping every non-ASCII character keeps every diagnostic line printable no matter what the source string contains, even on a strict UTF-8 stdout.
    """
    return s.encode("ascii", "backslashreplace").decode("ascii")


def _artifact_command(artifact):
    """How to invoke the running artifact as a child process."""
    if artifact and os.path.isfile(artifact) and os.access(artifact, os.X_OK):
        return [artifact]
    return [sys.executable, artifact]


def _pipe(cmd, payload):
    """(exit code, stderr text), or None when the process cannot start."""
    try:
        proc = subprocess.run(cmd, input=payload.encode("utf-8"),
                              capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.returncode, proc.stderr.decode("utf-8", "replace")


def _expected_destinations():
    """Each known artifact's current expected location, or None entries."""
    destinations = lifecycle.payload_destinations()
    destinations["cli"] = manifest.cli_bin_dest()
    return destinations


def _long_limit_line():
    """The limit in force for the invoking directory, with its source.

    active_long_limit consults project config only when it is handed a path (it starts discovery from that path's directory),
    so doctor passes a synthetic child of the cwd — the same resolution any file checked here would get.
    The source label re-walks the precedence legs with the core's own validity rule:
    an invalid environment value falls through exactly as the core treats it.
    """
    probe = os.path.join(os.getcwd(), "doctor-probe.md")
    value = core.active_long_limit(probe)
    env_raw = os.environ.get("SEMLF_LONG_LINE")
    env_valid = False
    if env_raw is not None:
        try:
            env_valid = int(env_raw) >= 0
        except ValueError:
            env_valid = False
    if env_valid:
        source = "$SEMLF_LONG_LINE"
    elif "long_limit" in core.load_config(os.getcwd()):
        source = ".semlf.ini"
    else:
        source = "default"
    return f"long-limit: {value} ({source})"


def run(argv, artifact=None):
    if argv:
        print("semlf doctor takes no arguments", file=sys.stderr)
        return 64
    artifact = artifact if artifact is not None else sys.argv[0]
    failures = 0

    print(f"platform: {platform.platform()} "
          f"{platform.python_implementation()} {platform.python_version()}")
    print(f"artifact: {os.path.abspath(artifact)} (core {core.__version__})")

    resolved = shutil.which("semlf")
    if resolved is None:
        print("path: warn — semlf is not on PATH")
    elif os.path.realpath(resolved) != os.path.realpath(artifact):
        print(f"path: warn — `semlf` resolves to {resolved}, not the "
              "artifact running doctor; a pre-redesign zipapp may be "
              "shadowing it (remove with install.py --uninstall --cli)")
    else:
        print(f"path: semlf resolves to {resolved}")

    print(_long_limit_line())
    for pattern in core.load_config(os.getcwd()).get("exclude", []):
        print(f"exclude: {pattern}")

    cmd = _artifact_command(artifact) + ["--hook", "claude"]
    bad = _pipe(cmd, BAD_PAYLOAD)
    good = _pipe(cmd, GOOD_PAYLOAD)
    if bad is None or good is None:
        print("replay: FAIL — could not run the artifact")
        failures += 1
    elif bad[0] != 2 or "fused" not in bad[1]:
        print(f"replay: FAIL — fused edit expected exit 2 with a fused "
              f"report, got exit {bad[0]}")
        failures += 1
    elif good[0] != 0:
        print(f"replay: FAIL — clean edit expected exit 0, got {good[0]}")
        failures += 1
    else:
        print("replay: ok — fused edit blocked (exit 2), clean edit passed (exit 0)")

    # One manifest snapshot for the whole run:
    # display and classification must agree, load() has already dropped invalid and unknown entries,
    # and every record is judged against the artifact's CURRENT expected destination —
    # classifying a record against its own recorded path would let a hostile record vouch for an arbitrary file.
    destinations = _expected_destinations()
    for name, entry in sorted(manifest.load().items()):
        print(_provenance_line(name, entry, destinations.get(name)))

    failures += _codex_hook_check()
    failures += _payload_identity_check()

    if failures:
        print(f"doctor: {failures} check(s) failed")
        return 1
    print("doctor: ok")
    return 0


def _provenance_line(name, entry, dest):
    """One artifact's provenance report, guarded classification first.

    classify_entry snapshots through the no-follow primitive before any path resolution,
    so no realpath touches the destination until it is ruled a regular file or the entry is already unrecorded;
    the diagnostic realpath comparison below runs only afterwards, and only to label WHY an entry is unrecorded.
    Extracted from the run loop so a causal test can pin exactly this ordering.
    """
    if dest is None:
        return f"provenance: {name} warn — no destination resolves here"
    state = manifest.classify_entry(entry, dest)
    if state != "unrecorded":
        return f"provenance: {name} {state} ({entry['version']})"
    if not os.path.lexists(str(dest)):
        return (f"provenance: {name} warn — recorded at {_diag(entry['path'])} "
                "but missing")
    try:
        mismatch = (os.path.realpath(str(dest))
                    != os.path.realpath(entry["path"]))
    except (OSError, ValueError):
        mismatch = False
    if mismatch:
        return (f"provenance: {name} warn — recorded for {_diag(entry['path'])}, "
                f"expected {dest}")
    return f"provenance: {name} unrecorded ({entry['version']})"


def _payload_identity_check():
    """Expected-payload mismatches fail; no-consumer leftovers warn.

    Expectedness is conditioned on consumers:
    an installed integration makes its payloads expected,
    a payload with no remaining consumer is a warning with the manual-removal pointer,
    a machine with no integrations passes,
    and a codex-only machine is never failed over the absent opencode copy.
    """
    failures = 0
    consumers = lifecycle.installed_consumers()
    destinations = lifecycle.payload_destinations()
    leftover_paths = []
    # The identity set, its consumer expectedness,
    # and the leftover pointer all come from the registry rows —
    # no hand-maintained name tuple here.
    for row in registry.ROWS:
        if not row.identity:
            continue
        expected = row.owner in consumers
        state, line = lifecycle.payload_identity(row.id)
        if state == "missing" and not expected:
            continue
        if expected and state != "ok":
            print(f"payload: FAIL — {line}")
            failures += 1
        elif not expected:
            print(f"payload: warn — {line} (no remaining consumer)")
            if destinations[row.id] is not None:
                leftover_paths.append(destinations[row.id])
        else:
            print(f"payload: {line}")
    if leftover_paths:
        listed = ", ".join(str(p) for p in leftover_paths)
        print(f"payload: warn — remove {listed} by hand if unwanted")
    return failures


def _codex_hook_check():
    """Replay a fused and a clean Codex patch through the installed hook.

    Both directions are required for an ok:
    a checker that exits 2 for everything would block clean edits and must not be certified.
    An installed hook doctor cannot certify is a FAIL, never a silent pass —
    only a genuinely absent hook contributes nothing.
    """
    home = manifest.codex_home()
    if home is None:
        print("codex hook: no home to check")
        return 0
    hooks_path = home / "hooks.json"
    if not os.path.lexists(str(hooks_path)):
        print("codex hook: not installed")
        return 0
    data = manifest.read_state_json(hooks_path)
    if data is None:
        print("codex hook: FAIL — hooks.json is unreadable, oversized, "
              "not a regular file, or not valid JSON")
        return 1
    owned = manifest.owned_codex_hooks(data)
    if not owned:
        print("codex hook: not installed")
        return 0
    if os.name == "nt":
        # The installed command string carries POSIX quoting;
        # executing it through a different tokenizer would certify a guess.
        # An installed hook we cannot replay is a failed check, not a pass.
        print("codex hook: FAIL — installed, but replay is not yet "
              "defined on this platform")
        return 1
    # The installer treats every owned entry as managed and updates all of them,
    # so certification must cover all of them too:
    # one healthy entry must not vouch for a stale or broken sibling.
    for argv in owned:
        try:
            if not stat.S_ISREG(os.lstat(argv[1]).st_mode):
                print(f"codex hook: FAIL — configured checker is not a "
                      f"regular file ({_diag(argv[1])})")
                return 1
        # A NUL-carrying or otherwise unencodable path makes os.lstat raise ValueError, not OSError —
        # a hostile hooks.json must fail this check, never crash the doctor.
        except (OSError, ValueError):
            print(f"codex hook: FAIL — configured checker missing ({_diag(argv[1])})")
            return 1
        fused = _pipe(argv, CODEX_PAYLOAD)
        clean = _pipe(argv, CODEX_CLEAN_PAYLOAD)
        if fused is None or clean is None:
            print("codex hook: FAIL — could not run the configured command")
            return 1
        if fused[0] != 2 or "fused" not in fused[1]:
            print(f"codex hook: FAIL — fused patch expected exit 2 with a "
                  f"fused report, got exit {fused[0]}")
            return 1
        if clean[0] != 0:
            print(f"codex hook: FAIL — clean patch expected exit 0, "
                  f"got {clean[0]}")
            return 1
    print(f"codex hook: ok — {len(owned)} owned entr"
          f"{'y' if len(owned) == 1 else 'ies'} certified in both directions")
    return 0
