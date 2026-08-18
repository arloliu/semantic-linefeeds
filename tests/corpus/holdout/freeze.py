"""Commit to the predicate a round will be scored against, before that round is drawn.

    python3 tests/corpus/holdout/freeze.py <round> "<why this predicate, now>" [--repair]

This is the record that carries the claim.
It names a digest of `scripts/check_linefeeds.py` and nothing that has been read yet,
because nothing of the round exists when it is written.

Run it, then commit the ledger line, then draw.
The draw and the seal both refuse while no record here names the predicate in front of them,
and `git log` is where the order becomes checkable by someone who was not present.

`--repair` binds four more things: the admission contract, the class taxonomy,
the draw configuration, and which sources the round draws from.
A repair round's meaning depends on all four,
and comparing a manifest against an in-code constant catches nothing
once both copies move together while the round is underway.
A labeling round binds none of them, because it never reads them.
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import Holdout, repair_round_bindings  # noqa: E402

CORPUS = TESTS / "corpus"


def main(number, intent, repair=False):
    if not intent.strip():
        sys.exit("a freeze with no stated intent records nothing; nothing was written")

    binds = (
        repair_round_bindings(
            json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        )
        if repair
        else None
    )
    holdout = Holdout(
        HERE.parent / f"round-{number}" / "bundle.json",
        CORPUS / "freeze.jsonl",
        TESTS.parent / "scripts" / "check_linefeeds.py",
        CORPUS / "manifest.json",
        round=number,
    )
    frozen = holdout.freeze_predicate(intent, binds)

    print(f"frozen for round {number}: {frozen['predicate_digest']}")
    print(f"  intent   {frozen['intent']}")
    print(f"  manifest {frozen['manifest_digest']}")
    print(f"  record   {frozen['id']}")
    for name, digest in sorted(frozen.get("binds", {}).items()):
        print(f"  binds    {name:<10} {digest}")
    print("commit this ledger line before drawing anything")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round", type=int)
    parser.add_argument("intent")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    main(args.round, args.intent, args.repair)
