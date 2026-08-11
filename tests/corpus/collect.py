"""Resolve three labeling passes into one label per unit, and report what was measured.

    python3 tests/corpus/collect.py <corpus-dir> <labels-dir>

`<corpus-dir>` holds `sample.json`, and `adjudications.json` once decisions exist.
`<labels-dir>` holds `<labeler>-<index>.out`, one file per pass per batch.
The resolution is the one the manifest records:
unanimity stands, any refutation goes to a maintainer, and the rest is ambiguous.

Prevalence is what sets the sample size, through `ceil(M / p)`.
"""

import collections
import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent
sys.path.insert(0, str(TESTS))

from corpus_harness import REPORTING, defect, level_of, resolution  # noqa: E402


def reported_dimensions(sample):
    """The dimensions this sample is reported on, however it was drawn.

    A pilot draws on one stratum and the corpus draws on several,
    and a marginal is worth reading either way.
    """
    if "quotas" in sample:
        return [(name, spec["bands"])
                for name, spec in sorted(sample["quotas"].items())]
    return [(sample["stratum"], sample["bands"])]

ARRAY_RE = re.compile(r"\[\s*\{.*}\s*]", re.DOTALL)


def answers(path):
    """The JSON array a pass returned, however much prose it wrapped around it."""
    match = ARRAY_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return []
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return []


def main(corpus, labels):
    sample = json.loads((corpus / "sample.json").read_text(encoding="utf-8"))
    units = {unit["id"]: unit for unit in sample["units"] if not defect(unit)}
    dimensions = reported_dimensions(sample)

    passes = collections.defaultdict(dict)
    for path in sorted(labels.glob("*.out")):
        labeler = path.name.split("-")[0]
        for answer in answers(path):
            if answer.get("id") in units:
                passes[answer["id"]][labeler] = answer

    labelers = sorted({name for votes in passes.values() for name in votes})
    complete = [uid for uid, votes in passes.items() if len(votes) == len(labelers)]
    print(f"units {len(units)}  labelers {labelers}  fully labeled {len(complete)}")

    decisions = {}
    decided = corpus / "adjudications.json"
    if decided.exists():
        decisions = {(entry["id"], entry["kind"]): entry["label"]
                     for entry in json.loads(decided.read_text(encoding="utf-8"))
                     if entry["label"]}

    for kind in ("wrap", "fused"):
        settled = {uid: resolution(sorted(passes[uid][name][kind] for name in labelers))
                   for uid in complete}
        # A maintainer's decision replaces the referral.
        # A rate counts settled labels, not the fact that something was once unsettled.
        settled = {uid: decisions.get((uid, kind), label) if label == "adjudicated" else label
                   for uid, label in settled.items()}
        counts = collections.Counter(settled.values())
        rated = len(complete) - counts["ambiguous"]
        prevalence = counts["true"] / rated if rated else 0.0
        print(f"\n[{kind}]  " + "  ".join(f"{k}={counts[k]}" for k in
                                          ("true", "false", "ambiguous", "adjudicated")))
        print(f"  ambiguous fraction {counts['ambiguous'] / len(complete):.0%} "
              f"(a level over {REPORTING['max_ambiguous_fraction']:.0%} reports no rate)")
        if rated:
            need = math.ceil(REPORTING["min_true_violations"] / prevalence) if prevalence else None
            print(f"  prevalence among rated units {counts['true']}/{rated} = {prevalence:.0%}"
                  f"  ->  ceil(M/p) = {need} units per level" if need else
                  f"  prevalence 0/{rated}: no sample size follows from this pilot")
        for dimension, bands in dimensions:
            per_level = collections.defaultdict(collections.Counter)
            for uid, label in settled.items():
                per_level[level_of(units[uid], dimension, bands)][label] += 1
            print(f"  {dimension}")
            for level in sorted(per_level):
                row = per_level[level]
                print(f"    {level:<10} true={row['true']:<4} false={row['false']:<4} "
                      f"ambiguous={row['ambiguous']:<3} adjudicated={row['adjudicated']}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve())
