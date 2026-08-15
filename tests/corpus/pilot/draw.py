"""Draw the pilot sample from the calibration sources.

Run it again with the same seed and the same commits and it produces the same units.
That is the point: a reviewer redraws the sample rather than trusting the run that made it.

    python3 tests/corpus/pilot/draw.py <checkout-root>

`<checkout-root>` holds one directory per source id, at the commit the manifest pins.
Nothing here consults detector output.
Sampling from findings would exclude every violation the detector already misses,
which is the one thing that makes recall unfalsifiable.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import draw, records_for  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"

# Fixed before the draw, and recorded in the manifest beside the seed.
STRATUM = "raw_end_column"
BANDS = (64, 71, 78, 85)
PER_LEVEL = 12
SEED = "pilot-raw-end-column-1"


def main(root):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    population = []
    for source in manifest["sources"]:
        if source["side"] != "calibration":
            continue
        population += records_for(source, root / source["id"])

    flat = [
        dict(record, **{STRATUM: record["covariates"][STRATUM]})
        for record in population
    ]
    sample = draw(flat, STRATUM, BANDS, PER_LEVEL, SEED)
    for record in sample:
        record.pop(STRATUM)

    out = HERE.parent / "sample.json"
    out.write_text(
        json.dumps(
            {
                "stratum": STRATUM,
                "bands": list(BANDS),
                "per_level": PER_LEVEL,
                "seed": SEED,
                "population": len(population),
                "units": sample,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"population {len(population)}, sampled {len(sample)} -> {out}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve())
