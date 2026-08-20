"""Materialize the sources the corpus draws from, at the commits it pins.

    python3 tests/corpus/repairs/checkout.py [--root <dir>] [--verify] [--side <side>]

`manifest.json` names every source by url and commit,
so the tree a round is drawn from is reconstructible rather than vendored.
Nothing here decides what to fetch:
a source is what the manifest says it is, at the commit the manifest pins,
and a checkout sitting at any other commit is reported rather than corrected,
because a tree that quietly moved is how a round stops being comparable.

`--verify` reports without fetching, which is what a round should run before it draws.
"""

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
MANIFEST = HERE.parent.parent / "manifest.json"
DEFAULT_ROOT = HERE.parent.parent / "checkouts"


def head(where):
    """The commit a checkout sits at, or None when it is not a repository."""
    done = subprocess.run(
        ["git", "-C", str(where), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else None


def materialize(source, root, verify):
    """One source at its pinned commit, reported as (state, detail)."""
    where = root / source["id"]
    pinned = source["commit"]
    at = head(where) if where.exists() else None
    if at == pinned:
        return "present", pinned[:12]
    if at is not None:
        return "MOVED", f"sits at {at[:12]}, manifest pins {pinned[:12]}"
    if verify:
        return "MISSING", f"no checkout at {where}"
    root.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        ["git", "clone", "--quiet", source["url"], str(where)],
        capture_output=True,
        text=True,
    )
    if clone.returncode != 0:
        return "FAILED", clone.stderr.strip().splitlines()[-1:] or ["clone failed"]
    out = subprocess.run(
        ["git", "-C", str(where), "checkout", "--quiet", pinned],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return "FAILED", f"cloned, but {pinned[:12]} is not in it"
    return "fetched", pinned[:12]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--side", default=None, help="only sources on this side")
    parser.add_argument(
        "--verify", action="store_true", help="report without fetching anything"
    )
    args = parser.parse_args(argv)

    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    root = pathlib.Path(args.root).resolve()
    sources = [
        source
        for source in manifest["sources"]
        if args.side is None or source["side"] == args.side
    ]
    wrong = 0
    for source in sources:
        state, detail = materialize(source, root, args.verify)
        if state not in ("present", "fetched"):
            wrong += 1
        print(f"{source['id']:<16} {state:<8} {detail}")
    print(f"\n{len(sources) - wrong} of {len(sources)} at the pinned commit -> {root}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
