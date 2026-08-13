"""Content providers for the semlf git modes.

The provider contract every mode shares:
a provider returns [(path, text), ...] pairs for one git snapshot,
where path is relative to the invoking directory
(so reports read naturally from wherever semlf ran)
and text is the full decoded content to check.
Selection, filtering, and reading all happen here;
analysis stays in the core (ADR-0004),
and the core never learns git exists.
Failures raise SourceError with a message ready for stderr:
a snapshot that cannot be enumerated or read is a loud stop,
never a silently shorter file list.
"""
import os
import subprocess

import check_linefeeds as core


class SourceError(Exception):
    """A git snapshot could not be enumerated or read."""


def _git(root, *args, input_bytes=None):
    try:
        proc = subprocess.run(["git", "-C", root, *args],
                              capture_output=True, input=input_bytes)
    except OSError as exc:
        raise SourceError(f"semlf: cannot run git: {exc}")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SourceError(f"semlf: {detail or 'git exited %d' % proc.returncode}")
    return proc.stdout


def _git_query(root, *args):
    """(returncode, stdout, stderr) — for probes where a failure code is the answer.

    Only launching git at all is a hard failure here;
    the caller owns the meaning of every exit status.
    """
    try:
        proc = subprocess.run(["git", "-C", root, *args], capture_output=True)
    except OSError as exc:
        raise SourceError(f"semlf: cannot run git: {exc}")
    return proc.returncode, proc.stdout, proc.stderr


def repo_root():
    """The enclosing repository's top-level directory, or a loud SourceError."""
    out = _git(os.getcwd(), "rev-parse", "--show-toplevel")
    return os.fsdecode(out).strip()


def _parse_raw(out):
    """[(path, post-image mode, post-image oid)] from git diff --raw -z bytes.

    A pure function so hostile and truncated byte streams are unit-testable.
    Record shape: ":<old mode> <new mode> <old oid> <new oid> <status>" NUL <path> NUL,
    with one terminal NUL closing the stream.
    --no-renames is pinned by the caller, so two-path R/C records cannot occur
    and no status carries a score;
    U (unmerged) and X (git's unknown status) are loud by ruling,
    both modes must be six octal digits,
    both ids full hexadecimal in the repository's one width (40 or 64),
    the status exactly one accepted letter,
    and any malformed, truncated, or trailing-garbage stream is a
    SourceError, never an IndexError and never a silently shorter list.
    """
    tokens = out.split(b"\0")
    records = []
    i = 0
    while i < len(tokens) and tokens[i]:
        meta = os.fsdecode(tokens[i])
        fields = meta[1:].split(" ")
        if not meta.startswith(":") or len(fields) != 5:
            raise SourceError("semlf: unparsable git diff record")
        if i + 1 >= len(tokens) or not tokens[i + 1]:
            raise SourceError("semlf: truncated git diff record")
        path = os.fsdecode(tokens[i + 1])
        i += 2
        old_mode, new_mode, old_oid, new_oid, status = fields
        for mode in (old_mode, new_mode):
            if len(mode) != 6 or any(c not in "01234567" for c in mode):
                raise SourceError("semlf: unparsable git diff record")
        for oid in (old_oid, new_oid):
            if (len(oid) not in (40, 64)
                    or any(c not in "0123456789abcdef" for c in oid)):
                raise SourceError("semlf: unparsable git diff record")
        if len(old_oid) != len(new_oid):
            raise SourceError("semlf: unparsable git diff record")
        if status == "U":
            raise SourceError(
                f"semlf: unmerged path {path}; resolve the merge first")
        if status == "X":
            raise SourceError(
                f"semlf: git reported an unknown change for {path}")
        if status not in ("A", "M", "T"):
            raise SourceError(
                f"semlf: unsupported diff status {status} for {path}")
        records.append((path, new_mode, new_oid))
    if tokens[i:] != [b""]:
        raise SourceError("semlf: trailing garbage in git diff records")
    return records


def _raw_records(root, *selector):
    """One raw enumeration per snapshot: status, mode, and oid travel together.

    --no-renames keeps the record shape independent of host
    diff.renames/diff.copies configuration —
    a rename arrives as an addition of the new path,
    which is the checkable post-image either way.
    """
    out = _git(root, "diff", "--raw", "-z", "--no-abbrev", "--no-renames",
               "--diff-filter=AMTUX", *selector)
    return _parse_raw(out)


def _head_or_empty_tree(root):
    """HEAD when it resolves; the empty tree only for a proven-unborn branch.

    Unborn means: HEAD is symbolic and its target ref is absent.
    Absence is probed with rev-parse --verify --quiet on the target,
    whose contract is exit 1 with empty stderr for a missing ref —
    a broken ref emits a diagnostic instead, and stays loud,
    because silently diffing against the empty tree would report
    every file changed.
    """
    try:
        _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
        return "HEAD"
    except SourceError:
        try:
            target = os.fsdecode(
                _git(root, "symbolic-ref", "--quiet", "HEAD")).strip()
        except SourceError:
            raise SourceError("semlf: cannot resolve HEAD in this repository")
        code, _, err = _git_query(root, "rev-parse", "--verify", "--quiet",
                                  target)
        if code != 1 or err.strip():
            raise SourceError("semlf: cannot resolve HEAD in this repository")
        return os.fsdecode(
            _git(root, "hash-object", "-t", "tree", "--stdin", input_bytes=b"")
        ).strip()


def _checkable(rel):
    return core.is_markdown(rel) or core.lang_for_path(rel) is not None


def _display(root, rel):
    """Path as reported: relative to the invoking directory when possible."""
    absolute = os.path.join(root, rel)
    try:
        return os.path.relpath(absolute)
    except ValueError:
        return absolute


CHECKABLE_MODES = {"100644", "100755"}


def _selected(root, records):
    """The checkable, non-excluded, regular-file subset of a raw listing.

    The mode gate is git's recorded post-image type —
    under core.symlinks=false a symlink materializes as a plain file
    holding link text, and only the recorded type can tell —
    so symlinks (120000) and gitlinks (160000) never reach a reader.
    """
    kept = []
    for rel, mode, oid in records:
        if mode not in CHECKABLE_MODES:
            continue
        if not _checkable(rel):
            continue
        if core.excluded(os.path.join(root, rel)):
            continue
        kept.append((rel, oid, _display(root, rel)))
    return kept


def _worktree_sources(root, records):
    sources = []
    for rel, _, display in _selected(root, records):
        full = os.path.join(root, rel)
        if os.path.islink(full) or os.path.isdir(full):
            # Physical no-follow belt over the mode gate:
            # open must never follow a link into unselected content.
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                sources.append((display, fh.read()))
        except OSError as exc:
            raise SourceError(f"semlf: cannot read {display}: {exc}")
    return sources


def staged_sources(root):
    """Index versus HEAD; text is the staged blob, read by the record's own oid.

    One index view end to end:
    the raw record that named the path also carries the object id read,
    so no second index query can see a different index,
    and a filename like 0:doc.md can never be parsed as stage syntax.
    """
    sources = []
    for _, oid, display in _selected(root, _raw_records(root, "--cached")):
        blob = _git(root, "cat-file", "blob", oid)
        sources.append((display, blob.decode("utf-8", "replace")))
    return sources


def diff_sources(root):
    """Worktree versus index: unstaged changes, read from the worktree."""
    return _worktree_sources(root, _raw_records(root))


def changed_sources(root):
    """Worktree versus HEAD: staged and unstaged together, read from the worktree."""
    return _worktree_sources(root, _raw_records(root, _head_or_empty_tree(root)))
