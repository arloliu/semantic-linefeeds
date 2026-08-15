"""Commit to the predicate a round will be scored against, before that round is drawn.

    python3 tests/corpus/holdout/freeze.py <round> "<why this predicate, now>"

This is the record that carries the claim.
It names a digest of `scripts/check_linefeeds.py` and nothing that has been read yet,
because nothing of the round exists when it is written.

Run it, then commit the ledger line, then draw.
The draw and the seal both refuse while no record here names the predicate in front of them,
and `git log` is where the order becomes checkable by someone who was not present.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))

from corpus_harness import Holdout  # noqa: E402

CORPUS = TESTS / "corpus"


def main(number, intent):
    if not intent.strip():
        sys.exit("a freeze with no stated intent records nothing; nothing was written")

    holdout = Holdout(
        HERE.parent / f"round-{number}" / "bundle.json",
        CORPUS / "freeze.jsonl",
        TESTS.parent / "scripts" / "check_linefeeds.py",
        CORPUS / "manifest.json",
    )
    holdout.freeze_predicate(intent)
    frozen = holdout.require_predicate_freeze()

    print(f"frozen for round {number}: {frozen['predicate_digest']}")
    print(f"  intent   {frozen['intent']}")
    print(f"  manifest {frozen['manifest_digest']}")
    print("commit this ledger line before drawing anything")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
