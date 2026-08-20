"""How far the round has got, and whether what has come back is answerable.

    python3 tests/corpus/repairs/status.py [<round-dir>]

Counts per family rather than in total.
A family that has stopped answering looks like a slow one until the counts sit together.
"""

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))

from corpus_harness import pass_answers  # noqa: E402


def main(round_dir, sample_path=None):
    sample_path = sample_path or HERE.parent / "sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    judgeable = {unit["id"]: unit for unit in sample["units"] if not unit.get("defect")}
    shown = {
        uid: {candidate["id"] for candidate in unit["candidates"]}
        for uid, unit in judgeable.items()
    }

    per_family = collections.defaultdict(
        lambda: {"batches": 0, "answers": 0, "covered": 0, "missing": 0, "unknown": 0}
    )
    answered = collections.defaultdict(set)
    for path in sorted(round_dir.glob("*.out")):
        family = path.name.split("-")[0]
        row = per_family[family]
        row["batches"] += 1
        for answer in pass_answers(path):
            uid = answer.get("id")
            if uid not in judgeable:
                row["unknown"] += 1
                continue
            row["answers"] += 1
            answered[family].add(uid)
            if answer.get("missing"):
                row["missing"] += 1
                continue
            covered = set(answer.get("accept") or []) | set(answer.get("reject") or [])
            if covered == shown[uid] and answer.get("choose") in set(
                answer.get("accept") or []
            ):
                row["covered"] += 1

    print(f"{len(judgeable)} judgeable units")
    print(
        f"{'family':<10}{'batches':>9}{'answers':>9}{'well-formed':>13}"
        f"{'missing':>9}{'unknown':>9}"
    )
    for family in sorted(per_family):
        row = per_family[family]
        print(
            f"{family:<10}{row['batches']:>9}{row['answers']:>9}"
            f"{row['covered']:>13}{row['missing']:>9}{row['unknown']:>9}"
        )
    # Over every family the round has a file for, not every family that parsed one.
    # A family whose first batch is still running has answered nothing,
    # and dropping it reports the round as further along than it is,
    # exactly while that is most misleading.
    families = sorted(per_family)
    if families:
        complete = set.intersection(*(answered[name] for name in families))
        print(
            f"\nanswered by all of {', '.join(families)}: "
            f"{len(complete)} of {len(judgeable)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round_dir", nargs="?", default=str(HERE.parent / "round-1"))
    parser.add_argument(
        "--sample",
        default=None,
        help="the sample the round was drawn from, when it does not sit beside this script",
    )
    args = parser.parse_args()
    main(
        pathlib.Path(args.round_dir).resolve(),
        pathlib.Path(args.sample).resolve() if args.sample else None,
    )
