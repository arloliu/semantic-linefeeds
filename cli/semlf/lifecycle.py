"""Shared lifecycle operations behind both doors (the redesign ADR).

`semlf install` and `scripts/install.py` are thin parsers over the operations here,
so the two doors produce byte-identical artifacts everywhere.
The engine is request-wide preflight then ordered apply:
every artifact of the whole request is classified read-only first,
any refusal aborts the run before the first write,
apply follows the registry's order,
provenance is recorded immediately after each artifact's publication,
and the published-but-not-recorded half-state is reported by name.
Rollback is deliberately not offered; a rerun converges.
Concurrent lifecycle commands stay out of scope (ADR-0014's boundary).
"""
import os
import re
import shutil
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

from semlf import classify, manifest, registry

Planned = namedtuple("Planned",
                     ["label", "name", "dest", "verdict", "do", "done"])
Planned.__new__.__defaults__ = (None,)
# label is the DISCLOSURE line (plans, prompts, dry runs);
# done, when set, is the COMPLETION line apply_plan prints instead —
# a leg whose pinned outputs differ between "would install" and
# "installed" carries both, and a leg with one voice sets only label.

_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def artifact_version():
    """The version of this artifact's own embedded checker payload.

    Read textually so nothing is imported;
    on the checkout door this is the canonical core file,
    so both doors agree by construction.
    """
    text = registry.payload_bytes("checker").decode("utf-8")
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "unknown"


def payload_destinations():
    """Each recorded single-file artifact's destination, or None entries.

    Derived from the registry rows — never a hand-maintained mapping.
    """
    return {row.id: row.dest() for row in registry.ROWS if row.recorded}


def rendered_bytes(name):
    """The exact bytes name's transform produces on this machine.

    Callers refuse a None destination before rendering,
    and every row whose rendering needs the data root has a destination
    that resolves exactly when the data root does,
    so the ValueError the codex-skill renderer raises on a None data root marks a caller bug, not a user-facing path.
    """
    return registry.BY_ID[name].render(manifest.semlf_data_dir())


# --- publication primitives -------------------------------------------------
# publish_exclusive and exclusive_backup move here verbatim from scripts/install.py (_publish_new, _exclusive_backup), docstrings included;
# install.py imports them back so the cli verb keeps its exact behavior.


def publish_bytes(dest, data):
    """Atomic complete-file publication: same-directory temp, os.replace."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
    except BaseException:
        os.unlink(tmp)
        raise


def publish_exclusive(staged, dest):
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


def exclusive_backup(src, bak, data):
    """Write data — the already-guarded classification snapshot — to bak.

    data, never a fresh read of src, is the point:
    the caller took src's bytes through the no-follow snapshot primitive once, to classify it,
    and the backup must preserve exactly what was classified, not whatever src holds by the time this runs.
    O_EXCL is the other half: the backup slot is claimed atomically,
    so a concurrent double --force cannot overwrite the only copy of a hand-patched artifact,
    and a pre-existing symlink at bak is refused, never followed.
    copystat still reads src's own metadata (permissions, timestamps) — that is a stat call, not a content read,
    and src is already proven a regular file by the caller before this runs.
    The cleanup covers every step including copystat:
    a failure at any point releases the slot,
    so a retry never finds it occupied by a half-made backup.
    """
    fd = os.open(str(bak), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        shutil.copystat(src, bak)
    except BaseException:
        os.unlink(bak)
        raise


def _describe(name, dest, verdict):
    if verdict.action == "write":
        return f"{name}: install {dest}"
    if verdict.action == "adopt":
        return f"{name}: up to date ({dest})"
    if verdict.action == "backup-replace":
        return f"{name}: back up and replace {dest} ({verdict.state})"
    return f"{name}: replace {dest} ({verdict.state})"


def plan_file(name, force, snapshot, destinations, planned, refusals):
    """Classify one registry single-file artifact into the plan."""
    dest = destinations[name]
    if dest is None:
        refusals.append(f"refusing to install {name}: cannot determine "
                        "a home directory to install it under.")
        return
    rendered = rendered_bytes(name)
    verdict = classify.classify_artifact(snapshot.get(name), dest,
                                         rendered, artifact_version(),
                                         force)
    if verdict.action == "refuse":
        refusals.append(verdict.detail)
        return
    record_trouble = manifest.record_preflight(name)
    if record_trouble is not None:
        refusals.append(f"refusing to install {name}: {record_trouble}")
        return

    def _do(name=name, dest=dest, rendered=rendered, verdict=verdict):
        return apply_file(name, dest, rendered, verdict)

    planned.append(Planned(_describe(name, dest, verdict), name, dest,
                           verdict, _do))


def apply_file(name, dest, rendered, verdict):
    """Publish one classified artifact and record it.

    Returns None on success, or the published-but-not-recorded half-state note when the record write failed after publication —
    the destination is correct, and a rerun adopts the missing record.
    """
    if verdict.action == "adopt":
        try:
            manifest.record(name, dest, artifact_version(),
                            manifest.sha256_bytes(rendered))
        except OSError as exc:
            return (f"{name}: {dest} is already correct, but its "
                    f"provenance could not be recorded: {exc}; "
                    "a re-run records it")
        return None
    if verdict.action == "backup-replace":
        bak = dest.with_name(dest.name + ".bak")
        exclusive_backup(dest, bak, verdict.snapshot)
        try:
            publish_bytes(dest, rendered)
        except BaseException:
            # This attempt's backup must not poison the slot:
            # the destination is unchanged (publication failed before its os.replace),
            # so removing the backup keeps the rerun convergent instead of refusing on an occupied slot.
            os.unlink(bak)
            raise
    elif verdict.action == "write":
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, staged_name = tempfile.mkstemp(dir=str(dest.parent),
                                           prefix=dest.name)
        with os.fdopen(fd, "wb") as fh:
            fh.write(rendered)
        if not publish_exclusive(Path(staged_name), dest):
            raise OSError(f"{dest} appeared after classification; "
                          "re-run so it can be classified")
    else:
        publish_bytes(dest, rendered)
    try:
        manifest.record(name, dest, artifact_version(),
                        manifest.sha256_bytes(rendered))
    except OSError as exc:
        return (f"{name}: published {dest} but could not record its "
                f"provenance: {exc}; a re-run records it")
    return None


def apply_plan(planned):
    """Ordered apply with per-artifact reporting; 0 clean, 1 otherwise."""
    had_error = False
    completed = []
    for i, item in enumerate(planned):
        if item.do is None:
            print(item.label)
            continue
        try:
            note = item.do()
        except OSError as exc:
            remaining = [p.label for p in planned[i + 1:]
                         if p.do is not None]
            print(f"error while applying {item.label}: {exc}",
                  file=sys.stderr)
            print("applied: "
                  + (", ".join(completed) if completed else "(nothing)"),
                  file=sys.stderr)
            print("not applied: " + ", ".join([item.label] + remaining),
                  file=sys.stderr)
            print("a re-run converges: completed artifacts no-op, "
                  "incomplete ones are attempted again.", file=sys.stderr)
            return 1
        if note:
            print(note, file=sys.stderr)
            had_error = True
        else:
            print(item.done or item.label)
        completed.append(item.label)
    return 1 if had_error else 0


def describe_plan(planned, refusals, prefix=""):
    """The read-only report every disclosure path shares.

    The dry run passes prefix="[dry-run] "
    so scripts keep a stable marker to grep for;
    the consent prompt and the refusal report print the same lines bare.
    A refusing request reports every artifact's verdict, not only the refusals —
    the admissible legs are part of the disclosure.
    """
    for item in planned:
        print(prefix + item.label)
    for refusal in refusals:
        print(f"{prefix}would refuse: {refusal}")
