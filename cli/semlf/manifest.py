"""Install identity: provenance, ownership, and destinations (ADR-0014).

One JSON file per artifact records what the installer last published:
$XDG_STATE_HOME/semlf/artifacts/<name>.json holding
{"path", "sha256", "version"}.
A record proves three things or nothing —
schema, path identity, and a digest of bytes the installer itself staged —
and every failure degrades to "unrecorded", which keeps the strict path:
provenance can make the installer more willing to replace bytes it can prove it wrote, never less careful with bytes it cannot.
One file per artifact is the concurrency ruling:
record replaces one file, forget unlinks one file,
so no writer can drop or resurrect another artifact's state,
and a same-name race resolves to one of the two racing intents.
"""

import hashlib
import json
import os
import re
import shlex
import stat
import tempfile
from pathlib import Path

KNOWN = (
    "cli",
    "checker",
    "readme",
    "codex-skill",
    "opencode-plugin",
    "opencode-checker",
    "codex-setup-skill",
    "opencode-setup-skill",
    "opencode-setup-command",
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _state_base():
    """$XDG_STATE_HOME/semlf, or ~/.local/state/semlf, or None.

    Same home guard as the destination helpers below.
    """
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / "semlf"
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "state" / "semlf"


def artifact_state_path(name):
    if name not in KNOWN:
        raise ValueError(f"unknown artifact name: {name!r}")
    base = _state_base()
    return None if base is None else base / "artifacts" / (name + ".json")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_regular_bytes(path, limit):
    """The bytes of a non-symlink regular file, or None for any trouble.

    The one no-follow snapshot primitive every lifecycle read and hash goes through:
    lstat first — only a non-symlink regular file within the size bound qualifies —
    then an open carrying O_NOFOLLOW (where the platform has it) plus O_NONBLOCK so a FIFO swapped in after the lstat can neither be followed into nor block the open, an fstat re-check of regular-file identity on the descriptor, and a bounded read from that descriptor —
    the path is never reopened.
    Where O_NOFOLLOW does not exist the lstat gate is the whole symlink guard;
    the residual window is same-user concurrency, out of scope by ADR-0014's stated boundary.
    """
    path = str(path)
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            chunks = []
            remaining = limit + 1
            while remaining > 0:
                chunk = os.read(fd, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        if len(data) > limit:
            return None
        return data
    except (OSError, ValueError):
        # A NUL-carrying path raises ValueError ("embedded null byte")
        # from lstat/open, not OSError; "any trouble" must catch it too.
        return None


def read_state_json(path, limit=65536):
    """Parsed JSON from a state file, or None for any trouble at all.

    Total over every bounded byte sequence:
    RecursionError from a deeply nested value is trouble like any other, never a traceback.
    """
    data = read_regular_bytes(path, limit)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        return None


def _valid_entry(entry):
    # An empty or NUL-carrying path would make the os.path functions raise instead of classify;
    # schema validity must imply totality.
    if not (
        isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and entry["path"] != ""
        and "\x00" not in entry["path"]
        and isinstance(entry.get("sha256"), str)
        and _HEX64_RE.match(entry["sha256"]) is not None
        and isinstance(entry.get("version"), str)
    ):
        return False
    # An unpaired surrogate, or any other text the filesystem encoding cannot represent, can never identify a real destination.
    # Dropping it here keeps every downstream os.path/os.lstat call, and every diagnostic print of entry["path"], free of a string this hostile.
    try:
        os.fsencode(entry["path"])
    except (UnicodeError, ValueError):
        return False
    return True


def load():
    """One snapshot: every KNOWN artifact whose state file holds a valid entry."""
    snapshot = {}
    for name in KNOWN:
        path = artifact_state_path(name)
        if path is None:
            continue
        entry = read_state_json(path)
        if _valid_entry(entry):
            snapshot[name] = entry
    return snapshot


def record(name, path, version, sha256):
    """Record a publication whose digest the caller computed pre-publish.

    The digest parameter is the contract:
    provenance is established from the bytes the installer staged or rendered, never by re-reading a mutable destination that a concurrent writer may have replaced.
    """
    state = artifact_state_path(name)
    if state is None:
        return
    state.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps({"path": str(path), "sha256": sha256, "version": version}, indent=2)
        + "\n"
    )
    fd, tmp = tempfile.mkstemp(dir=str(state.parent), prefix=state.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, state)
    except BaseException:
        os.unlink(tmp)
        raise


def forget(name):
    state = artifact_state_path(name)
    if state is None:
        return
    try:
        os.unlink(state)
    except FileNotFoundError:
        pass


CLASSIFY_LIMIT = 16 * 1024 * 1024  # a pyz or skill is far below this


def classify_entry(entry, path):
    """'managed', 'edited', or 'unrecorded' for the bytes at path.

    Managed needs the full proof, checked in this order:
    a valid entry, bytes taken through the no-follow snapshot primitive (so a symlink, FIFO, or over-limit file is never followed, hung on, or hashed — and is ruled out before any path resolution), the recorded path and the queried path resolving identically, and a digest match.
    Identity without a digest match is 'edited';
    anything else, including any read or resolution failure, is 'unrecorded'.
    """
    if not _valid_entry(entry):
        return "unrecorded"
    path = str(path)
    data = read_regular_bytes(path, CLASSIFY_LIMIT)
    if data is None:
        return "unrecorded"
    try:
        if os.path.realpath(path) != os.path.realpath(entry["path"]):
            return "unrecorded"
    except (OSError, ValueError):
        return "unrecorded"
    return "managed" if sha256_bytes(data) == entry["sha256"] else "edited"


def classify(name, path):
    return classify_entry(load().get(name), path)


def parse_managed_codex_hook(matcher, hook):
    """The parsed argv when (matcher, hook) is the entry this kit installs.

    Structural over the enclosing shape and the exact command the installer writes:
    matcher apply_patch, hook type command, and a command whose four POSIX-shlex tokens are python3, a path whose basename is exactly check_linefeeds.py, --hook, codex.
    Anything less — a foreign launcher, a lookalike basename, another matcher or hook type, extra arguments, unparsable quoting, a non-string — is None,
    and callers must preserve it untouched.
    """
    if matcher != "apply_patch" or not isinstance(hook, dict):
        return None
    if hook.get("type") != "command" or not isinstance(hook.get("command"), str):
        return None
    try:
        argv = shlex.split(hook["command"])
    except ValueError:
        return None
    if (
        len(argv) == 4
        and argv[0] == "python3"
        and os.path.basename(argv[1]) == "check_linefeeds.py"
        and argv[2:] == ["--hook", "codex"]
    ):
        return argv
    return None


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
    base = _opencode_config_dir()
    return None if base is None else base / "plugins"


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


def codex_setup_skill_dest():
    """Where the setup skill installs for Codex CLI, or None when no home resolves.

    Same root and same guard as `codex_skill_dest`, one directory over.
    """
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".agents" / "skills" / "setup-semlf" / "SKILL.md"


def _opencode_config_dir():
    """$XDG_CONFIG_HOME/opencode, or ~/.config/opencode, or None.

    The shared parent `opencode_plugins_dir` and the two setup destinations below all hang off,
    so the XDG guard is written once rather than three times.
    """
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "opencode"
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".config" / "opencode"


def opencode_setup_skill_dest():
    """opencode's own skills root, or None when no config dir resolves.

    opencode also scans `~/.agents/skills`, which is where Codex's copy lands,
    but installing there for opencode would make one target's uninstall remove another target's file.
    Each target owning its own copy keeps removal correct.
    """
    base = _opencode_config_dir()
    return None if base is None else base / "skills" / "setup-semlf" / "SKILL.md"


def opencode_setup_command_dest():
    """The user-typed `/setup-semlf` entry, or None when no config dir resolves.

    A skill in opencode reaches the model, not the user:
    its body loads only when the model elects to call the skill tool.
    A command file is the only thing a user can type, so it is what makes the skill reachable on purpose.
    """
    base = _opencode_config_dir()
    return None if base is None else base / "commands" / "setup-semlf.md"


def cli_bin_dest():
    """~/.local/bin/semlf, or None when no home resolves.

    Same guard as codex_skill_dest.
    """
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "bin" / "semlf"


def semlf_data_dir():
    """${XDG_DATA_HOME:-~/.local/share}/semlf, or None when no home resolves.

    The neutral payload root:
    installed hooks and skills point here, whatever channel semlf itself arrived by,
    so a hook survives a channel switch, a venv rebuild, or a CLI uninstall untouched.
    """
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / "semlf"
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "share" / "semlf"


def record_preflight(name):
    """None when name's record can be written here, else a refusal string.

    Preflight admits the provenance side before the first destination is touched:
    the state root must resolve, the record leaf must be absent or a regular file,
    and the nearest existing ancestor of its parent must be a directory —
    a file squatting on the semlf state directory would otherwise fail the record write after publication,
    leaving the half-state a preflight exists to prevent.
    """
    state = artifact_state_path(name)
    if state is None:
        return "no state root resolves (no home directory)"
    try:
        if os.path.lexists(state) and not stat.S_ISREG(os.lstat(state).st_mode):
            return f"record path {state} exists and is not a regular file"
        probe = state.parent
        while not os.path.lexists(probe):
            if probe.parent == probe:
                break
            probe = probe.parent
        if os.path.lexists(probe):
            if not probe.is_dir():
                return f"record parent {probe} exists and is not a directory"
            # record() creates missing directories, stages a temp file,
            # and os.replace()s it into the parent —
            # all of which need write+search permission on the nearest existing ancestor.
            if not os.access(str(probe), os.W_OK | os.X_OK):
                return f"record parent {probe} is not writable"
    except OSError as exc:
        return f"cannot inspect the record path {state}: {exc}"
    return None


def owned_codex_hooks(data):
    """Every managed hook argv in a parsed hooks.json; [] on any trouble.

    The one structural scan doctor, status, and the installer share,
    so "installed" can never mean different things to different verbs.
    """
    if not isinstance(data, dict):
        return []
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return []
    post = hooks.get("PostToolUse", [])
    if not isinstance(post, list):
        return []
    out = []
    for block in post:
        if isinstance(block, dict) and isinstance(block.get("hooks"), list):
            for h in block["hooks"]:
                argv = parse_managed_codex_hook(block.get("matcher"), h)
                if argv is not None:
                    out.append(argv)
    return out
