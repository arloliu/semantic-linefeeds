"""Seal a repair round: one ciphertext bundle, and no plaintext left behind.

    python3 tests/corpus/repairs/seal.py <round>

The bundle holds everything scoring needs — the sample, every pass's answers,
and the adjudications — so the round can be spent once, later, by one open.
Sealing recomputes every binding the round was frozen under
and refuses whichever moved (ADR-0022, ADR-0024):
the ledger's freeze, the sample's own copy, and the tree must all agree,
because a contract that moved everywhere at once, mid-round, was chosen after the reading.

The passphrase is read from a prompt rather than an argument or the environment,
for the reason the label seal gives:
anything else is a file, a history entry, or a transcript.
"""

import getpass
import json
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))

from corpus_harness import (  # noqa: E402
    Holdout,
    repair_admission_digest,
    repair_round_bindings,
)

CORPUS = TESTS / "corpus"


def plaintext(round_dir):
    """Everything that carries this round's prose in the clear."""
    return [
        round_dir / "sample.json",
        round_dir / "adjudications.json",
        round_dir / "answers",
        round_dir / "batches",
    ]


def payload(round_dir):
    """What one open must be able to score: sample, answers, adjudications."""
    sample = json.loads((round_dir / "sample.json").read_text(encoding="utf-8"))
    answers = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((round_dir / "answers").glob("*.out"))
    }
    if not answers:
        sys.exit("the round holds no answers; a bundle nothing can score seals nothing")
    decided = round_dir / "adjudications.json"
    adjudications = (
        json.loads(decided.read_text(encoding="utf-8")) if decided.exists() else None
    )
    return {"sample": sample, "answers": answers, "adjudications": adjudications}


def prepare(number, manifest_path=None):
    """Every refusal, run before a passphrase is even asked for."""
    manifest_path = pathlib.Path(manifest_path or (CORPUS / "manifest.json"))
    round_dir = manifest_path.parent / "repairs" / f"round-{number}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    body = payload(round_dir)
    sample = body["sample"]

    drawn_under = sample.get("drawn_under")
    if not drawn_under:
        sys.exit(
            f"round {number}'s sample names no freeze record.\n"
            "It was drawn before the draw recorded one, so nothing here can say "
            "which predicate its prose was drawn under.\n"
            "Nothing was written."
        )
    bound = sample.get("binds") or {}
    if not bound:
        sys.exit(
            f"round {number}'s sample carries no binds; "
            "a repair round records what it was frozen under, and this one did not.\n"
            "Nothing was written."
        )
    recomputed = repair_round_bindings(manifest, number)
    moved = sorted(
        name
        for name in set(bound) | set(recomputed)
        if bound.get(name) != recomputed.get(name)
    )
    if moved:
        sys.exit(
            f"round {number} was frozen against {sorted(bound)}, and {moved} has moved.\n"
            "Nothing was written."
        )

    holdout = Holdout(
        round_dir / "bundle.json",
        manifest_path.parent / "freeze.jsonl",
        REPO / "scripts" / "check_linefeeds.py",
        manifest_path,
        round=number,
    )
    return holdout, body, drawn_under, recomputed, round_dir


def main(number, manifest_path=None):
    holdout, body, drawn_under, binds, round_dir = prepare(number, manifest_path)

    if not sys.stdin.isatty():
        sys.exit(
            "run this from a terminal.\n"
            "Without one the passphrase would arrive on a pipe, "
            "which is a file, a history entry, or a transcript.\n"
            "Nothing was written."
        )
    seal_round(holdout, body, drawn_under, binds, round_dir)

    print(f"sealed round {number} -> {round_dir / 'bundle.json'}")
    print("one open will spend it; score it with score.py --bundle")


def seal_round(holdout, body, drawn_under, binds, round_dir, passphrase=None):
    """Write the ciphertext, bind it, and leave no plaintext beside it."""
    if passphrase is None:
        passphrase = getpass.getpass("passphrase (never stored, never recoverable): ")
        if passphrase != getpass.getpass("again: "):
            sys.exit("the two entries differ; nothing was written")
    if not passphrase.strip():
        sys.exit("an empty passphrase seals nothing; nothing was written")
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    holdout.seal(text, passphrase, drawn_under=drawn_under, binds=binds)
    holdout.freeze({"admission": repair_admission_digest()})

    for path in plaintext(round_dir):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    left = sorted(
        entry.name for entry in round_dir.iterdir() if entry.name != "bundle.json"
    )
    if left:
        sys.exit(
            f"sealed, but plaintext remains beside the bundle: {left}\n"
            "Remove it before committing; a sealed round leaves only its ciphertext."
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round", type=int)
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args()
    main(args.round, args.manifest)
