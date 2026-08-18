"""Draw the repair round from the calibration sources.

    python3 tests/corpus/repairs/draw.py <checkout-root> [--out <sample.json>]

The population is every `fused` boundary the detector raises on the calibration sources,
enumerated through each source's own selection command.
Not every prose boundary, which is what the label corpus draws from:
a repair exists only where a finding was delivered,
and that conditional is what this corpus measures.

The strata are exact class sets, because they partition the population.
A unit refused by three classes belongs to three of them,
so a top-up on one class raises another class's members' chance of selection,
and a raw marginal over such a draw is biased for the population marginal.
Exact sets are disjoint, so this draw has known inclusion probabilities.

Nothing here reads a suggestion.
The passes judge prose, and a pass shown the machine's answer measures agreement with it.
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402
from corpus_harness import (  # noqa: E402
    REPAIR_ADMISSION,
    REPAIR_DRAW,
    attach_candidates,
    contract_digest,
    draw_strata,
    file_digest,
    repair_admission_digest,
    repair_population,
    stratum_shortfalls,
)

CORPUS = TESTS / "corpus"
MANIFEST = CORPUS / "manifest.json"
SKILL = REPO / "skills" / "semantic-linefeeds" / "SKILL.md"
REPAIRING = HERE.parent / "REPAIRING.md"

# One copy of these numbers, in the harness, because the freeze that binds them
# and this draw that obeys them have to be looking at the same ones.
#
# Every unit comes from a stratum quota, so there is no random base.
# The label corpus uses one because its dimensions overlap,
# and a base is what spreads whatever nothing quotas.
# Here the strata are disjoint and enumerable,
# so a base would only add units nothing could weight.
BASE = REPAIR_DRAW["base"]
SEED = REPAIR_DRAW["seed"]
PER_SET = REPAIR_DRAW["per_set"]
FLOOR = REPAIR_DRAW["floor"]

QUOTAS = {"per_set": PER_SET, "floor": FLOOR}

# The floor is the admission contract's, not a second number that happens to agree.
assert FLOOR == REPAIR_ADMISSION["reportable"]["min_scored"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--out", default=str(HERE.parent / "sample.json"))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    population = []
    for source in manifest["sources"]:
        if source["side"] == "calibration":
            population += repair_population(source, root / source["id"])
    if not population:
        sys.exit("no calibration source produced a unit; check the checkout root")

    drawn, strata = draw_strata(population, QUOTAS, SEED)
    attach_candidates(drawn, root)
    shortfalls = stratum_shortfalls(population, strata, QUOTAS)

    out = pathlib.Path(args.out)
    out.write_text(
        json.dumps(
            {
                "base": BASE,
                "seed": SEED,
                "quotas": QUOTAS,
                "population": len(population),
                "strata": strata,
                "shortfalls": shortfalls,
                # What the round was drawn under.
                # A digest of the contract's content rather than of the manifest file,
                # whose digest moves with every unit the corpus grows.
                "admission_digest": repair_admission_digest(),
                "taxonomy_digest": contract_digest(list(clf.WITHHOLDING_CLASSES)),
                "draw_digest": contract_digest(
                    {"base": BASE, "seed": SEED, "quotas": QUOTAS}
                ),
                # What the stimulus was rendered under.
                # A batch checks these before it lays anything out,
                # so a changed rule refuses.
                # It does not silently change the stimulus halfway through a round.
                "stimulus_digests": {
                    "skill": file_digest(SKILL),
                    "repairing": file_digest(REPAIRING),
                    "renderer": file_digest(REPO / "scripts" / "check_linefeeds.py"),
                },
                "sources": {
                    source["id"]: source["commit"]
                    for source in manifest["sources"]
                    if source["side"] == "calibration"
                },
                "units": drawn,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    reportable = sum(1 for body in strata.values() if body["reportable"])
    print(f"population {len(population)} over {len(strata)} exact sets")
    print(f"drew {len(drawn)} from {reportable} strata at or above the floor -> {out}")
    print(f"{'n':>8}{'drawn':>7}{'p':>9}  set")
    for key in sorted(strata, key=lambda name: -strata[name]["population"]):
        body = strata[key]
        shown = "{" + key.replace(",", ", ") + "}" if key else "{} (suggested today)"
        print(
            f"{body['population']:>8}{body['drawn']:>7}"
            f"{body['inclusion_probability']:>9.4f}  {shown}"
        )

    # A stratum drawn at zero has no unit in the report above,
    # so what the draw could not buy is said separately.
    print("could not buy:" if shortfalls else "every stratum bought what it asked for")
    for problem in shortfalls:
        print(f"  {problem}")


if __name__ == "__main__":
    main()
