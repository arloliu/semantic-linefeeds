"""Count how often a finding in this repository's history was followed by a repair.

    python3 tests/corpus/repairs/history.py [--json <out>]

The plan for the repair corpus rests on this number:
if the wild population were large enough, the corpus would be captured rather than elicited.
It is not, so the instrument that says so is committed rather than described.

What it counts is an approximation, and the approximation is the point.
A repair event is a finding on the parent blob whose anchor line occurs fewer times in the child.
That over-counts:
a deleted line and a rewrite for unrelated reasons both look like a repair.
So the result is an over-count of repairs rather than an estimate of them.

Two things it does not do, so the number is read as an over-count rather than a proven ceiling.
It compares whole blobs rather than diff hunks,
so a line repaired in one place and reintroduced in another nets to nothing.
And it sees only this repository, which is one project's history.

Only first-parent commits are walked.
A merge's diff against its first parent attributes the whole side branch to one commit,
which would count the same repair twice.
"""

import argparse
import collections
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parent.parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402

SUFFIXES = (".md", ".py", ".go", ".ts")
EXCLUDED_PREFIX = "tests/"


def git(*args, allow_failure=False):
    """Run one git command, refusing to treat a failure as an empty answer.

    The first version returned stdout without checking the status,
    so a command that failed contributed nothing and looked like a file with no findings.
    A miscount that silently lowers the headline number is the one this instrument must not make.
    """
    done = subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        if allow_failure:
            return None
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def changed_paths(parent, commit):
    """Every changed path as (status, old path, new path), with renames carrying both."""
    out = []
    raw = git("diff", "--name-status", "-M", parent, commit)
    for line in raw.splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            out.append((status, parts[1], parts[2]))
        elif len(parts) == 2:
            out.append((status, parts[1], parts[1]))
    return out


def anchors(text, path):
    """Every blocking finding's anchor line, by kind."""
    try:
        diagnostics = clf.diagnose(text, path)
    except Exception:
        return []
    return [
        (d["kind"], text[d["anchor"]["start"] : d["anchor"]["end"]])
        for d in diagnostics
        if d["kind"] != "long"
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="out")
    parser.add_argument("--rev", default="HEAD")
    args = parser.parse_args(argv)

    commits = git("rev-list", "--first-parent", "--reverse", args.rev).split()
    repaired = collections.Counter()
    introduced = collections.Counter()
    survived = collections.Counter()
    skipped = []
    walked = 0

    for commit in commits:
        parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) != 1:
            continue
        parent = parents[0]
        walked += 1
        # -M detects a rename, and --name-status is what reports both of its paths.
        # --name-only returns one name.
        # Reading that name from both blobs does not follow a rename:
        # it looks for the new path inside the old commit.
        for status, old_name, new_name in changed_paths(parent, commit):
            # A deletion has no child blob and an addition has no parent one,
            # so neither can carry a repair.
            # Skipping them is not an error.
            if status.startswith(("D", "A")):
                continue
            if not new_name.endswith(SUFFIXES) or new_name.startswith(EXCLUDED_PREFIX):
                continue
            before = git("show", f"{parent}:{old_name}", allow_failure=True)
            after = git("show", f"{commit}:{new_name}", allow_failure=True)
            if before is None or after is None:
                skipped.append(f"{commit[:8]} {old_name} -> {new_name}")
                continue
            if not before or not after:
                continue
            # Counted by occurrence, not by membership.
            # A file can hold one line twice.
            # Repairing one of them leaves the other in the set,
            # which a membership test reads as survival.
            present = collections.Counter(after.splitlines())
            was = collections.Counter(before.splitlines())
            seen = collections.Counter()
            for kind, anchor in anchors(before, old_name):
                seen[anchor] += 1
                if seen[anchor] <= present[anchor]:
                    survived[kind] += 1
                else:
                    repaired[kind] += 1
            fresh = collections.Counter()
            for kind, anchor in anchors(after, new_name):
                fresh[anchor] += 1
                if fresh[anchor] > was[anchor]:
                    introduced[kind] += 1

    report = {
        "rev": git("rev-parse", args.rev).strip(),
        "commits_walked": walked,
        "suffixes": list(SUFFIXES),
        "excluded_prefix": EXCLUDED_PREFIX,
        "skipped": skipped,
        "repaired": dict(repaired),
        "introduced": dict(introduced),
        "survived": dict(survived),
        "note": (
            "repaired counts any anchor line whose occurrences fell, "
            "so a deletion and an unrelated rewrite are counted alongside a real repair; "
            "it is an over-count of repairs rather than a proven ceiling on them"
        ),
    }
    print(f"{walked} first-parent commits walked")
    if skipped:
        print(f"  {len(skipped)} path(s) skipped: {skipped[:3]}")
    for label, counter in (
        ("repaired (over-counted)", repaired),
        ("introduced", introduced),
        ("survived unchanged", survived),
    ):
        print(f"  {label:<20} {dict(counter)}")
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
