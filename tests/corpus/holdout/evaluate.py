"""Open the holdout once, score the frozen predicate against it, and spend it.

    python3 tests/corpus/holdout/evaluate.py

The bundle opens only if the ledger already names this predicate, this calibration manifest,
and this ciphertext, and only if it has not been scored before.
Both refusals are the point of the mechanism rather than an obstacle to it.

The detector runs here and nowhere earlier.
Sampling and labeling never saw its output,
and nothing in the sealed payload records what it would say.

The result is written to `result.json` beside the bundle, and appended to the ledger.
It carries unit identifiers, counts, and rates.
It carries no prose:
the sources are public and pinned by commit, so a reader looks a line up rather than reading it here.
"""

import getpass
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))

from corpus_harness import (  # noqa: E402
    KINDS, REPORTED_STRATA, Holdout, ScoringRefused,
    floor_problems, recall, replay_kinds)

CORPUS = TESTS / "corpus"
HOLDOUT = CORPUS / "holdout"


def scored(units):
    """Every unit, with the status the predicate gives it today.

    A true violation is detected or missed.
    A non-violation the predicate reports is a false positive,
    which is the other half of what a holdout is for.
    """
    for record in units:
        reported = record["question"] in replay_kinds(record)
        if record["label"] == "true":
            record["expected"] = "detected" if reported else "accepted_miss"
        elif record["label"] == "false" and reported:
            record["false_positive"] = True
    return units


def main():
    if not sys.stdin.isatty():
        sys.exit("run this from a terminal; nothing was opened")

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    floors = manifest["reporting"]["recall_floors"]
    bands = floors["strata_bands"]
    holdout = Holdout(HOLDOUT / "bundle.json", CORPUS / "freeze.jsonl",
                      TESTS.parent / "scripts" / "check_linefeeds.py", CORPUS / "manifest.json")

    passphrase = getpass.getpass("passphrase: ")
    try:
        body = json.loads(holdout.open(passphrase))
    except ScoringRefused as refusal:
        sys.exit(f"refused: {refusal}")

    units = scored(body["units"])
    overall = {kind: recall(units, kind)["all"] for kind in KINDS}
    strata = {
        dimension: {kind: recall(units, kind, dimension, bands.get(dimension))
                    for kind in KINDS}
        for dimension in REPORTED_STRATA
    }
    false_positives = sorted(record["id"] for record in units if record.get("false_positive"))
    non_violations = sum(1 for record in units if record["label"] == "false")

    result = {
        "drawn_by": body["drawn_by"],
        "records": len(units),
        "boundaries": len(units) // len(KINDS),
        "floors": floors["holdout"],
        "floors_met": not floor_problems(units, floors["holdout"]),
        "floor_problems": floor_problems(units, floors["holdout"]),
        "recall": {kind: {"detected": counts["detected"], "true": counts["true"],
                          "rate": counts["rate"], "interval": counts["interval"],
                          "withheld": list(counts["withheld"])}
                   for kind, counts in overall.items()},
        "strata": {dimension: {kind: {str(level): {
                        "detected": counts["detected"], "true": counts["true"],
                        "rate": counts["rate"], "withheld": list(counts["withheld"])}
                        for level, counts in sorted(report.items(), key=lambda p: str(p[0]))}
                    for kind, report in per_kind.items()}
                   for dimension, per_kind in strata.items()},
        "false_positives": {"count": len(false_positives),
                            "of_labeled_non_violations": non_violations,
                            "ids": false_positives},
        "ambiguous": sum(1 for record in units if record["label"] == "ambiguous"),
    }

    (HOLDOUT / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    holdout.record_evaluation(result)

    print(f"{result['records']} records, {result['boundaries']} boundaries")
    for kind, counts in sorted(overall.items()):
        rate = "withheld: " + "; ".join(counts["withheld"]) if counts["rate"] is None \
            else f"{counts['rate']:.1%}"
        print(f"  {kind:6} {counts['detected']:4}/{counts['true']:<4} {rate}"
              f"   floor {floors['holdout'][kind]:.2f}")
    print(f"  false positives  {len(false_positives)} of {non_violations}")
    print(f"  ambiguous        {result['ambiguous']}")
    print("floors met" if result["floors_met"] else "FLOORS NOT MET:")
    for problem in result["floor_problems"]:
        print(f"  {problem}")
    print("the bundle is now spent and will not open again")


if __name__ == "__main__":
    main()
