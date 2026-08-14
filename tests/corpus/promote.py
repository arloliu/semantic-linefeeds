"""Promote the settled pilot units into the manifest.

    python3 tests/corpus/promote.py <corpus-dir> <labels-dir> <checkout-root>

One sampled boundary becomes two records, one per question,
because a rate is reported per kind and a record that answers both would belong to neither.

The detector runs here and nowhere earlier.
Sampling and labeling stay blind to it;
the frozen detected-or-accepted-miss status is a record of what the detector does today,
and a unit that slips from detected to missed later turns the suite red on identity alone.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))
sys.path.insert(0, str(HERE.parent))

from collect import answers  # noqa: E402
from corpus_harness import KINDS, defect, resolution  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"


def detected_in(root, source, path):
    """Every (line, kind) the detector reports for one file, as it stands today."""
    import check_linefeeds

    text = (root / source / path).read_text(encoding="utf-8", errors="replace")
    return {(lineno, kind) for lineno, kind, _, _ in check_linefeeds.check(text, path)}


def main(corpus, labels, root):
    sample = json.loads((corpus / "sample.json").read_text(encoding="utf-8"))
    decided = {
        (entry["id"], entry["kind"]): entry
        for entry in json.loads(
            (corpus / "adjudications.json").read_text(encoding="utf-8")
        )
    }

    votes = {}
    for path in sorted(labels.glob("*.out")):
        for answer in answers(path):
            votes.setdefault(answer["id"], {})[path.name.split("-")[0]] = answer

    findings, units = {}, []
    for unit in sample["units"]:
        if defect(unit) or unit["id"] not in votes:
            continue
        cast = votes[unit["id"]]
        key = unit["source"], unit["path"]
        if key not in findings:
            findings[key] = detected_in(root, *key)

        for kind in KINDS:
            passes = {name: cast[name][kind] for name in sorted(cast)}
            settled = resolution(sorted(passes.values()))
            record = {
                "id": f"{unit['id']}#{kind}",
                "boundary": unit["id"],
                "source": unit["source"],
                "frame": unit["frame"],
                "path": unit["path"],
                "lines": unit["lines"],
                "upper": unit["upper"],
                "lower": unit["lower"],
                "context": unit["context"],
                "raw_window": unit["raw_window"],
                "upper_index": unit["upper_index"],
                "covariates": unit["covariates"],
                "passes": passes,
                "question": kind,
                "label": settled,
            }
            if settled == "adjudicated":
                entry = decided[(unit["id"], kind)]
                record["label"] = entry["label"]
                record["adjudication"] = entry["reason"]
            if record["label"] == "true":
                record["expected"] = (
                    "detected"
                    if (unit["lines"][0], kind) in findings[key]
                    else "accepted_miss"
                )
            units.append(record)

    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["units"] = units
    MANIFEST.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    missed = sum(1 for u in units if u.get("expected") == "accepted_miss")
    print(
        f"{len(units)} records from {len(units) // len(KINDS)} boundaries; "
        f"{missed} true violations the detector does not report"
    )


if __name__ == "__main__":
    main(
        pathlib.Path(sys.argv[1]).resolve(),
        pathlib.Path(sys.argv[2]).resolve(),
        pathlib.Path(sys.argv[3]).resolve(),
    )
