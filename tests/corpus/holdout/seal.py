"""Seal one labeled holdout round, bind the predicate to it, and delete the plaintext.

    python3 tests/corpus/holdout/seal.py <round>

The passphrase is read from a prompt rather than from an argument or the environment,
so it never reaches a process list, a shell history, or an agent's transcript.
Losing it destroys the holdout, and that is the accepted cost of not storing it.

Sealing is refused unless the ledger already froze this predicate.
That record is written before the draw, so it is a prediction rather than a description;
the freeze written here binds it to a ciphertext that could not exist until now.

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
from corpus_harness import KINDS, Holdout, defect, resolution  # noqa: E402

CORPUS = TESTS / "corpus"
HOLDOUT = CORPUS / "holdout"


def plaintext(round_dir):
    """Everything that carries this round's prose in the clear."""
    return [
        round_dir / "sample.json",
        round_dir / "adjudications.json",
        round_dir / "labels",
    ]


def payload(round_dir):
    """One record per question per boundary, carrying no detector output.

    The expected status is deliberately absent.
    Whether the predicate reports a unit is what the evaluation measures,
    so recording it here would seal the answer in with the question.
    """
    sample = json.loads((round_dir / "sample.json").read_text(encoding="utf-8"))
    decided = {
        (entry["id"], entry["kind"]): entry
        for entry in json.loads(
            (round_dir / "adjudications.json").read_text(encoding="utf-8")
        )
    }

    passes, families = {}, set()
    for out in sorted((round_dir / "labels").glob("*.out")):
        labeler = out.name.rsplit("-", 1)[0]
        families.add(labeler)
        for answer in answers(out):
            for kind in KINDS:
                passes.setdefault((answer["id"], kind), {})[labeler] = answer[kind]

    # A unit judged by two passes is not the same instrument as one judged by three.
    # Resolving it anyway would read as unanimity wherever the two happened to agree,
    # so a short unit stops the seal until somebody records why it is short.
    drawn = [unit for unit in sample["units"] if not defect(unit)]
    short = sorted(
        unit["id"]
        for unit in drawn
        if set(passes.get((unit["id"], KINDS[0]), {})) != families
    )
    if short:
        sys.exit(
            "these units were not judged by every labeling pass:\n  "
            + "\n  ".join(short)
            + "\nrerun the batch, or mark the unit in sample.json with a labeling_defect "
            "naming what failed; nothing was written"
        )

    records = []
    for unit in drawn:
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
        "drawn_by": {
            "seed": sample["seed"],
            "base": sample["base"],
            "per_level": sample["per_level"],
            "quotas": sample["quotas"],
            "population": sample["population"],
        },
        "units": records,
    }


def main(number):
    round_dir = HOLDOUT / f"round-{number}"
    body = payload(round_dir)
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    holdout = Holdout(
        round_dir / "bundle.json",
        CORPUS / "freeze.jsonl",
        TESTS.parent / "scripts" / "check_linefeeds.py",
        CORPUS / "manifest.json",
        round=number,
    )

    # The sample names the freeze its prose was drawn under, and the seal answers to that record.
    # Without this the ledger accepts any freeze naming the current predicate,
    # so a predicate could be frozen, drawn against, tuned once the prose had been read,
    # frozen again, and sealed against the second freeze.
    sample = json.loads((round_dir / "sample.json").read_text(encoding="utf-8"))
    drawn_under = sample.get("drawn_under")
    if not drawn_under:
        sys.exit(
            f"round {number}'s sample names no freeze record.\n"
            "It was drawn before the draw recorded one, so nothing here can say "
            "which predicate its prose was drawn under.\n"
            "Nothing was written."
        )

    if not sys.stdin.isatty():
        sys.exit(
            "run this from a terminal.\n"
            "Without one the passphrase would arrive on a pipe, "
            "which is a file, a history entry, or a transcript.\n"
            "Nothing was written."
        )

    # The floors are a prediction, so they are stated before the bundle they will judge exists.
    # Sealing without them would let the number be chosen once the labels were in hand.
    floors = manifest["reporting"]["recall_floors"]["holdout"].get(str(number))
    if not floors:
        sys.exit(
            f"the manifest states no floors for round {number}; "
            "state them before sealing, or they are chosen after the fact"
        )

    passphrase = getpass.getpass("passphrase (never stored, never recoverable): ")
    if passphrase != getpass.getpass("again: "):
        sys.exit("the two entries differ; nothing was written")
    if not passphrase.strip():
        sys.exit("an empty passphrase seals nothing; nothing was written")

    holdout.seal(text, passphrase, drawn_under=drawn_under)
    holdout.freeze(
        {
            **{
                name: manifest["reporting"][name]
                for name in (
                    "interval",
                    "min_true_violations",
                    "max_interval_half_width",
                    "max_ambiguous_fraction",
                )
            },
            "recall_floors": floors,
        }
    )

    if holdout.open(passphrase) != text:
        sys.exit(
            "the bundle did not reproduce what was sealed; the plaintext is untouched"
        )

    removed = plaintext(round_dir)
    for path in removed:
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    counts = {}
    for record in body["units"]:
        counts[(record["question"], record["label"])] = (
            counts.get((record["question"], record["label"]), 0) + 1
        )
    print(
        f"sealed {len(body['units'])} records from {len(body['units']) // len(KINDS)} boundaries"
    )
    for key in sorted(counts):
        print(f"  {key[0]:6} {key[1]:10} {counts[key]}")
    print("frozen against the predicate and the calibration manifest as they stand now")
    print("plaintext removed: " + ", ".join(p.name for p in removed))


if __name__ == "__main__":
    main(int(sys.argv[1]))
