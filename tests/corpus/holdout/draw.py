"""Draw the holdout.

    python3 tests/corpus/holdout/draw.py <checkout-root>

Identical in shape to the calibration draw, and deliberately so.
A holdout drawn by a different procedure measures the procedure as well as the predicate.

The one difference is the seed, so that the two draws cannot coincide.

This has not been run.
Running it puts holdout prose in the working tree,
so the session that runs it must not be a session that tunes the predicate,
and the predicate must be frozen before anything here is labeled.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import draw_corpus, level_of, quota_shortfalls, records_for  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"

BASE = 200
SEED = "holdout-1"
PER_LEVEL = 38

QUOTAS = {
    "markdown_nesting": (None, PER_LEVEL),
    "trailing_inline_markup": (None, PER_LEVEL),
    "list_item_adjacency": (None, PER_LEVEL),
    "indentation_depth": ((0, 4, 8), PER_LEVEL),
    "raw_end_column": ((64, 71, 78, 85), PER_LEVEL),
}


def main(root):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    population = []
    for source in manifest["sources"]:
        if source["side"] == "holdout":
            population += records_for(source, root / source["id"])

    drawn = draw_corpus(population, BASE, QUOTAS, SEED)
    out = HERE.parent / "sample.json"
    out.write_text(json.dumps({
        "base": BASE,
        "seed": SEED,
        "per_level": PER_LEVEL,
        "quotas": {name: {"bands": bands, "per_level": count}
                   for name, (bands, count) in sorted(QUOTAS.items())},
        "population": len(population),
        "units": drawn,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"population {len(population)}, drew {len(drawn)} -> {out}")
    for name, (bands, count) in sorted(QUOTAS.items()):
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
    main(pathlib.Path(sys.argv[1]).resolve())
