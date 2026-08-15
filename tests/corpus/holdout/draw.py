"""Draw one holdout round.

    python3 tests/corpus/holdout/draw.py <checkout-root> <round>

Identical in shape to the calibration draw, and deliberately so.
A holdout drawn by a different procedure measures the procedure as well as the predicate.

The one difference is the seed, so that no two draws can coincide.

Running this puts holdout prose in the working tree,
so the session that runs it must not be a session that tunes the predicate.
The predicate must already be frozen when it runs,
and the draw refuses rather than trusting whoever runs it to remember.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import (  # noqa: E402
    Holdout,
    ScoringRefused,
    draw_corpus,
    level_of,
    quota_shortfalls,
    records_for,
)

CORPUS = TESTS / "corpus"
MANIFEST = CORPUS / "manifest.json"

BASE = 200
PER_LEVEL = 38

QUOTAS = {
    "markdown_nesting": (None, PER_LEVEL),
    "trailing_inline_markup": (None, PER_LEVEL),
    "list_item_adjacency": (None, PER_LEVEL),
    "indentation_depth": ((0, 4, 8), PER_LEVEL),
    "raw_end_column": ((64, 71, 78, 85), PER_LEVEL),
}


def main(root, number):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out_dir = HERE.parent / f"round-{number}"

    # The bundle this round will produce does not exist yet,
    # so what is checked here is the predicate alone.
    # Nothing else can be checked before the prose is on disk,
    # which is exactly why this check has to happen here rather than at sealing time.
    holdout = Holdout(
        out_dir / "bundle.json",
        CORPUS / "freeze.jsonl",
        TESTS.parent / "scripts" / "check_linefeeds.py",
        MANIFEST,
    )
    try:
        frozen = holdout.require_predicate_freeze()
    except ScoringRefused as refusal:
        sys.exit(f"refused: {refusal}\nnothing was drawn")
    print(f"drawing against a predicate frozen for: {frozen['intent']}")

    population = []
    for source in manifest["sources"]:
        if source["side"] == "holdout" and source["round"] == number:
            population += records_for(source, root / source["id"])
    if not population:
        sys.exit(f"no source declares round {number}; pin one in the manifest first")

    seed = f"holdout-{number}"
    drawn = draw_corpus(population, BASE, QUOTAS, seed)
    # Created only once the round is known to be a real one,
    # so a mistyped number refuses above rather than leaving an empty directory behind.
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "sample.json"
    out.write_text(
        json.dumps(
            {
                "base": BASE,
                "seed": seed,
                "per_level": PER_LEVEL,
                "quotas": {
                    name: {"bands": bands, "per_level": count}
                    for name, (bands, count) in sorted(QUOTAS.items())
                },
                "population": len(population),
                "units": drawn,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"population {len(population)}, drew {len(drawn)} -> {out}")
    for name, (bands, _count) in sorted(QUOTAS.items()):
        levels = {}
        for unit in drawn:
            level = level_of(unit, name, bands)
            levels[level] = levels.get(level, 0) + 1
        print(f"  {name:<24} {dict(sorted(levels.items(), key=lambda p: str(p[0])))}")

    # A level filled with nothing has no units to appear in the report above,
    # so what the quotas could not buy is said separately.
    shortfalls = quota_shortfalls(population, drawn, QUOTAS)
    print("could not buy:" if shortfalls else "every quota bought what it asked for")
    for problem in shortfalls:
        print(f"  {problem}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve(), int(sys.argv[2]))
