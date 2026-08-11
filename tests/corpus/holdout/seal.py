"""Seal the labeled holdout, freeze the predicate against it, and delete the plaintext.

    python3 tests/corpus/holdout/seal.py

The passphrase is read from a prompt rather than from an argument or the environment,
so it never reaches a process list, a shell history, or an agent's transcript.
Losing it destroys the holdout, and that is the accepted cost of not storing it.

Everything that carries holdout prose in the clear is removed once the bundle verifies:
the sample, the three labeling passes, and the adjudications.
The sample can be redrawn from its seed.
The labels cannot, which is why they live only inside the bundle.
"""

import getpass
import json
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "scripts"))
sys.path.insert(0, str(HERE.parent.parent))

from collect import answers  # noqa: E402
from corpus_harness import KINDS, Holdout, resolution  # noqa: E402

CORPUS = TESTS / "corpus"
HOLDOUT = CORPUS / "holdout"
PLAINTEXT = [HOLDOUT / "sample.json", HOLDOUT / "adjudications.json", HOLDOUT / "labels"]


def payload():
    """One record per question per boundary, carrying no detector output.

    The expected status is deliberately absent.
    Whether the predicate reports a unit is what the evaluation measures,
    so recording it here would seal the answer in with the question.
    """
    sample = json.loads((HOLDOUT / "sample.json").read_text(encoding="utf-8"))
    decided = {(entry["id"], entry["kind"]): entry
               for entry in json.loads((HOLDOUT / "adjudications.json").read_text(encoding="utf-8"))}

    passes = {}
    for out in sorted((HOLDOUT / "labels").glob("*.out")):
        labeler = out.name.rsplit("-", 1)[0]
        for answer in answers(out):
            for kind in KINDS:
                passes.setdefault((answer["id"], kind), {})[labeler] = answer[kind]

    records = []
    for unit in sample["units"]:
        for kind in KINDS:
            key = (unit["id"], kind)
            three = passes[key]
            label = resolution(tuple(three[name] for name in sorted(three)))
            reason = None
            if label == "adjudicated":
                decision = decided[key]
                label, reason = decision["label"], decision["reason"]
            record = {
                "id": f"{unit['id']}#{kind}",
                "boundary": unit["id"],
                "question": kind,
                "label": label,
                "passes": three,
                "source": unit["source"],
                "path": unit["path"],
                "lines": unit["lines"],
                "raw_window": unit["raw_window"],
                "upper_index": unit["upper_index"],
                "covariates": unit["covariates"],
            }
            if reason:
                record["reason"] = reason
            records.append(record)
    return {
        "drawn_by": {"seed": sample["seed"], "base": sample["base"],
                     "per_level": sample["per_level"], "quotas": sample["quotas"],
                     "population": sample["population"]},
        "units": records,
    }


def main():
    body = payload()
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    holdout = Holdout(HOLDOUT / "bundle.json", CORPUS / "freeze.jsonl",
                      TESTS.parent / "scripts" / "check_linefeeds.py", CORPUS / "manifest.json")

    if not sys.stdin.isatty():
        sys.exit("run this from a terminal.\n"
                 "Without one the passphrase would arrive on a pipe, "
                 "which is a file, a history entry, or a transcript.\n"
                 "Nothing was written.")

    passphrase = getpass.getpass("passphrase (never stored, never recoverable): ")
    if passphrase != getpass.getpass("again: "):
        sys.exit("the two entries differ; nothing was written")
    if not passphrase.strip():
        sys.exit("an empty passphrase seals nothing; nothing was written")

    holdout.seal(text, passphrase)
    holdout.freeze({
        **{name: manifest["reporting"][name]
           for name in ("interval", "min_true_violations",
                        "max_interval_half_width", "max_ambiguous_fraction")},
        "recall_floors": manifest["reporting"]["recall_floors"]["holdout"],
    })

    if holdout.open(passphrase) != text:
        sys.exit("the bundle did not reproduce what was sealed; the plaintext is untouched")

    for path in PLAINTEXT:
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    counts = {}
    for record in body["units"]:
        counts[(record["question"], record["label"])] = \
            counts.get((record["question"], record["label"]), 0) + 1
    print(f"sealed {len(body['units'])} records from {len(body['units']) // len(KINDS)} boundaries")
    for key in sorted(counts):
        print(f"  {key[0]:6} {key[1]:10} {counts[key]}")
    print("frozen against the predicate and the calibration manifest as they stand now")
    print("plaintext removed: " + ", ".join(p.name for p in PLAINTEXT))


if __name__ == "__main__":
    main()
