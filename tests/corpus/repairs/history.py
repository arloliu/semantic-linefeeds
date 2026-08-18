"""Count how often a finding in this repository's history was followed by a repair.

    python3 tests/corpus/repairs/history.py [--json <out>]

The plan for the repair corpus rests on this number:
if the wild population were large enough, the corpus would be captured rather than elicited.
It is not, so the instrument that says so is committed rather than described.

What it counts is an approximation, and the approximation is the point.
A repair event is a finding on the parent blob whose anchor line does not appear in the child.
That over-counts:
a deleted line, a rename with edits, and a rewrite for unrelated reasons all look the same.
So the result is a ceiling on the number of real repairs, not an estimate of it,
and the plan reads it as one.

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


def git(*args):
    return subprocess.run(
        ["git", "-C", str(REPO)] + list(args),
        capture_output=True,
        text=True,
    ).stdout


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
    walked = 0

    for commit in commits:
        parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) != 1:
            continue
        parent = parents[0]
        walked += 1
        # -M follows a rename.
        # A moved file is then compared with itself,
        # rather than counted as one deletion beside one addition.
        changed = git("diff", "--name-only", "-M", parent, commit).splitlines()
        for name in changed:
            if not name.endswith(SUFFIXES) or name.startswith(EXCLUDED_PREFIX):
                continue
            before, after = (
                git("show", f"{parent}:{name}"),
                git("show", f"{commit}:{name}"),
            )
            if not before or not after:
                continue
            present = set(after.splitlines())
            was = set(before.splitlines())
            for kind, anchor in anchors(before, name):
                if anchor in present:
                    survived[kind] += 1
                else:
                    repaired[kind] += 1
            for kind, anchor in anchors(after, name):
                if anchor not in was:
                    introduced[kind] += 1

    report = {
        "rev": git("rev-parse", args.rev).strip(),
        "commits_walked": walked,
        "suffixes": list(SUFFIXES),
        "excluded_prefix": EXCLUDED_PREFIX,
        "repaired": dict(repaired),
        "introduced": dict(introduced),
        "survived": dict(survived),
        "note": "repaired counts any anchor line that stopped existing, so it is a ceiling",
    }
    print(f"{walked} first-parent commits walked")
    for label, counter in (
        ("repaired (at most)", repaired),
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
