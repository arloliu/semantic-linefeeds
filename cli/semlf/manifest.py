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

KNOWN = ("cli", "codex-skill", "opencode-plugin", "opencode-checker")

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
        flags = (os.O_RDONLY
                 | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
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
    return (isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and entry["path"] != ""
            and "\x00" not in entry["path"]
            and isinstance(entry.get("sha256"), str)
            and _HEX64_RE.match(entry["sha256"]) is not None
            and isinstance(entry.get("version"), str))


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
    text = json.dumps({"path": str(path), "sha256": sha256,
                       "version": version}, indent=2) + "\n"
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
    if (len(argv) == 4
            and argv[0] == "python3"
            and os.path.basename(argv[1]) == "check_linefeeds.py"
            and argv[2:] == ["--hook", "codex"]):
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
    if os.environ.get("XDG_CONFIG_HOME"):
        base = Path(os.environ["XDG_CONFIG_HOME"])
    else:
        home = os.path.expanduser("~")
        if home == "~":
            return None
        base = Path(home) / ".config"
    return base / "opencode" / "plugins"


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


def cli_bin_dest():
    """~/.local/bin/semlf, or None when no home resolves.

    Same guard as codex_skill_dest.
    """
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "bin" / "semlf"
