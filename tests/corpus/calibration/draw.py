"""Draw the calibration corpus.

    python3 tests/corpus/calibration/draw.py <checkout-root>

A random base spreads the dimensions nothing quotas.
Quotas then top up the levels that are structurally rare,
because a level a random draw leaves nearly empty can never carry a rate.

`raw_end_column` carries a quota, though the plan expects that dimension to spread on its own.
Measurement refused that expectation: its widest band is 2.7% of the population,
so a base large enough to fill it by chance would be roughly four times this whole corpus.
The top-up costs the difference instead.

Nothing here consults detector output.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import draw_corpus, level_of, records_for  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"

BASE = 200
SEED = "calibration-2"

# The pilot's rule gives 75 per level, driven entirely by how rare a fused line is.
# Half of that is taken knowingly.
# It buys every per-level wrap rate and gives up every per-level fused rate,
# because a fused rate needs the corpus entire and a wrap rate does not.
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
        if source["side"] == "calibration":
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
        thin = {k: v for k, v in sorted(levels.items()) if v < count}
        print(f"  {name:<24} {dict(sorted(levels.items()))}"
              + (f"   short: {thin}" if thin else ""))


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve())
