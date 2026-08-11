"""Prepare the units a maintainer has to decide, and check the decisions afterwards.

    python3 tests/corpus/adjudicate.py worksheet <corpus-dir> <labels-dir>
    python3 tests/corpus/adjudicate.py check     <corpus-dir> <labels-dir>

Decisions are written to `adjudications.json` beside the sample they belong to.

`worksheet` writes one entry per unit the passes could not settle,
carrying the prose, the three answers, and two empty fields.
`check` refuses the file until every entry has a label and a reason.

A decision without a reason is the failure this exists to prevent.
The manifest records why a maintainer overrode three blind passes,
and a blank reason turns that record into a rubber stamp.
"""

import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(HERE.parent))

from collect import answers  # noqa: E402
from corpus_harness import LABELS, defect, resolution  # noqa: E402


def pending(corpus, round_dir):
    """Every (unit, kind) the three passes sent to a maintainer, with what they said."""
    sample = json.loads((corpus / "sample.json").read_text(encoding="utf-8"))
    # A unit the sampler should never have drawn is reported, not decided.
    # Asking a maintainer to label a licence header would settle a defect by vote.
    units = {unit["id"]: unit for unit in sample["units"] if not defect(unit)}
    votes = collections.defaultdict(dict)
    for path in sorted(round_dir.glob("*.out")):
        for answer in answers(path):
            if answer.get("id") in units:
                votes[answer["id"]][path.name.split("-")[0]] = answer

    out = []
    for uid in sorted(votes):
        labelers = sorted(votes[uid])
        for kind in ("wrap", "fused"):
            cast = {name: votes[uid][name][kind] for name in labelers}
            if resolution(sorted(cast.values())) != "adjudicated":
                continue
            unit = units[uid]
            out.append({
                "id": uid,
                "kind": kind,
                "path": unit["path"],
                "lines": unit["lines"],
                "upper": unit["upper"],
                "lower": unit["lower"],
                "context": unit["context"],
                "passes": cast,
                "label": None,
                "reason": "",
            })
    return out


def worksheet(corpus, round_dir, out):
    entries = pending(corpus, round_dir)
    if out.exists():
        decided = {(e["id"], e["kind"]): e for e in json.loads(out.read_text(encoding="utf-8"))}
        for entry in entries:
            was = decided.get((entry["id"], entry["kind"]))
            if was:
                entry["label"], entry["reason"] = was["label"], was["reason"]
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    blank = sum(1 for e in entries if not e["reason"])
    print(f"{len(entries)} to decide, {blank} still blank -> {out}")


def check(corpus, round_dir, out):
    entries = {(e["id"], e["kind"]): e
               for e in json.loads(out.read_text(encoding="utf-8"))}
    problems = []
    for entry in pending(corpus, round_dir):
        key = entry["id"], entry["kind"]
        decided = entries.get(key)
        if decided is None:
            problems.append(f"{key[0]} [{key[1]}]: the passes could not settle this and nobody did")
            continue
        if decided["label"] not in LABELS:
            problems.append(f"{key[0]} [{key[1]}]: label {decided['label']!r} is not one of {LABELS}")
        if not decided["reason"].strip():
            problems.append(f"{key[0]} [{key[1]}]: decided with no reason recorded")
    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    mode, corpus, labels = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    out = corpus / "adjudications.json"
    sys.exit(worksheet(corpus, labels, out) or 0 if mode == "worksheet"
             else check(corpus, labels, out))
