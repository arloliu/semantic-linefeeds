"""The three-axis artifact classifier (the redesign ADR).

Admission is decided on three independent axes for every single-file artifact:
object state, provenance state, and execution mode.
Force widens the provenance axis only — it never overrides an object-state refusal,
and an occupied backup slot refuses uniformly.
Adoption in the exact-rendering row is deliberate:
publication and record are separate files,
so a correct copy with a missing record must converge to managed on the next run.
The classifier fails closed:
a recorded version that does not parse as dot-separated integers is unorderable,
refused rather than guessed at.
"""
import os
import stat
from collections import namedtuple

from semlf import manifest

Verdict = namedtuple("Verdict", ["state", "action", "detail", "snapshot"])
Verdict.__new__.__defaults__ = (None, None)


def parse_version(text):
    """A dot-separated non-negative integer tuple, or None."""
    if not isinstance(text, str) or not text:
        return None
    parts = text.split(".")
    if not all(p.isascii() and p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def object_state(dest):
    """absent | regular | symlink | directory | special | unreadable."""
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unreadable"
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if stat.S_ISDIR(st.st_mode):
        return "directory"
    if not stat.S_ISREG(st.st_mode):
        return "special"
    return "regular"


def classify_artifact(entry, dest, rendered, version, force):
    """One artifact's verdict for this run, read-only.

    entry is the caller's one manifest snapshot's entry for this name (or None);
    rendered is the exact bytes this machine's transform produces;
    version is the running artifact's own version string.
    """
    state = object_state(dest)
    if state == "absent":
        return Verdict("absent", "write", None)
    if state != "regular":
        return Verdict(state, "refuse",
                       f"{dest} is a {state}; move it aside and re-run "
                       "(--force never overrides this)")
    current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
    if current is None:
        return Verdict("unreadable", "refuse",
                       f"{dest} exists but is not a readable regular "
                       "file (--force never overrides this)")
    if current == rendered:
        return Verdict("exact", "adopt", None, current)
    prov = manifest.classify_entry(entry, dest)
    if prov == "managed":
        recorded = parse_version(entry["version"])
        running = parse_version(version)
        if recorded is None or running is None:
            if force:
                return Verdict("managed-unorderable", "replace", None,
                               current)
            return Verdict("managed-unorderable", "refuse",
                           f"{dest}: cannot order the recorded version "
                           f"({entry['version']}) against this "
                           f"artifact's ({version}); rerun with --force "
                           "to replace it")
        if recorded > running:
            if force:
                return Verdict("managed-newer", "replace", None, current)
            return Verdict("managed-newer", "refuse",
                           f"{dest}: published is newer than this "
                           "artifact — rerun with `--force` to "
                           "downgrade")
        state = "managed-older" if recorded < running else "managed-equal"
        return Verdict(state, "replace", None, current)
    # prov is "edited" or "unrecorded"
    if not force:
        return Verdict(prov, "refuse",
                       f"{dest}: its content differs from what this kit "
                       f"installed ({prov}); rerun with --force to back "
                       "it up and replace it")
    bak = dest.with_name(dest.name + ".bak")
    if os.path.lexists(bak):
        return Verdict(prov, "refuse",
                       f"refusing to overwrite {bak}: a backup already "
                       "exists; move it aside and re-run")
    return Verdict(prov, "backup-replace", None, current)
