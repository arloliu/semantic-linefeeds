"""Score a named predicate against a round's frozen acceptable sets.

    python3 tests/corpus/repairs/score.py <checkout-root> \
        --sample <sample.json> --answers <answers-dir> --predicate shipped|candidate

**Calibration admits nothing.**
Every number this prints is tuning feedback for the shape,
and the admission contract refuses every one of them as evidence:
no class is admissible on the calibration side
(`repair_admission.admissible_from`).

`--predicate` names one of the two committed constants,
`ADMITTED` or `CANDIDATE_ADMITTED`, and accepts nothing else.
A class set passed at a call site would let a scorer vary the candidate after the prose is read,
which is the one thing the frozen-constant design exists to prevent.

Both predicates flow through `composed` and `normalize_repair`,
so the two sides differ by the admitted set alone.
A machine repair the candidate universe cannot express is reported by unit id,
and it counts as a failure rather than leaving the denominator.
A predicate that withholds leaves the window as it is,
and the unchanged window is scored like any other answer,
because leaving the line alone is a candidate the passes were shown.
"""

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE.parent))

import check_linefeeds as clf  # noqa: E402
from collect import resolved  # noqa: E402
from corpus_harness import (  # noqa: E402
    candidate_for_breaks,
    composed,
    file_digest,
    normalize_repair,
    original_cuts,
    repair_window,
)

PREDICATES = {
    "shipped": lambda: clf.ADMITTED,
    "candidate": lambda: clf.CANDIDATE_ADMITTED,
}

# The outcomes whose units carry a rate.
# Ambiguous units leave the denominator and are kept as cases,
# the way the admission contract's own denominator clause reads.
UNRATED = ("ambiguous", "defect", "error", "adjudicated")


def machine_suggestion(unit, text, path, admitted):
    """What the named predicate does to this unit's window, and the window."""
    records, suppressions = clf.judged_lines(text, path)
    window = repair_window(records, unit["index"])
    anchor = records[unit["index"]]
    matches = list(clf.FUSED_RE.finditer(anchor["prose"]))
    if unit["match"] >= len(matches):
        return None, window
    match = matches[unit["match"]]
    successor = records[unit["index"] + 1] if unit["index"] + 1 < len(records) else None
    below = (
        successor
        if clf._wrap_paired(anchor, successor)
        and "wrap" not in suppressions.get(anchor["line"], frozenset())
        else None
    )
    return clf._fused_suggestion(anchor, match, below, admitted=admitted), window


def score_unit(unit, text, admitted):
    """One unit's verdict under the named predicate, structured for the report.

    The acceptable set speaks in cut positions over the window's joined prose,
    so a fired repair is mapped breaks -> candidate -> cuts,
    and a repair no candidate carries is inexpressible.
    A withheld repair leaves the window as it is,
    which is the original candidate's cuts.
    """
    suggestion, window = machine_suggestion(unit, text, unit["path"], admitted)
    original = original_cuts(window)
    if suggestion is None:
        return {
            "fired": False,
            "cuts": original,
            "original": original,
            "flags": None,
            "inexpressible": False,
        }
    lines = composed(window, suggestion)
    got = normalize_repair(window, lines, text, unit["path"])
    landed = candidate_for_breaks(unit["candidates"], got["breaks"])
    return {
        "fired": True,
        "cuts": tuple(landed["cuts"]) if landed else None,
        "original": original,
        "flags": {
            "preserving": got["preserving"],
            "carrier_valid": got["carrier_valid"],
            "intact": got["intact"],
        },
        "inexpressible": landed is None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="checkout root the sample's sources sit under")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--answers", required=True)
    parser.add_argument("--predicate", required=True, choices=sorted(PREDICATES))
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    sample = json.loads(pathlib.Path(args.sample).read_text(encoding="utf-8"))
    answers_dir = pathlib.Path(args.answers).resolve()
    admitted = PREDICATES[args.predicate]()

    outcomes, _names = resolved(sample, answers_dir)
    if not outcomes:
        sys.exit("no unit was answered by every pass\nnothing was scored")

    units = {unit["id"]: unit for unit in sample["units"]}
    strata = collections.defaultdict(
        lambda: {
            "scored": 0,
            "acceptable": 0,
            "fired": 0,
            "ambiguous": 0,
            "inexpressible": [],
            "zero_tolerance": {
                "prose_not_preserved": 0,
                "carrier_changed": 0,
                "fired_where_only_the_original_is_acceptable": 0,
            },
        }
    )
    texts = {}
    for uid, got in sorted(outcomes.items()):
        unit = units[uid]
        body = strata[unit["stratum"]]
        if got["outcome"] in UNRATED or "acceptable" not in got:
            body["ambiguous"] += 1
            continue
        key = (unit["source"], unit["path"])
        if key not in texts:
            texts[key] = (root / unit["source"] / unit["path"]).read_text(
                encoding="utf-8"
            )
        text = texts[key]

        acceptable = {tuple(cuts) for cuts in got["acceptable"]}
        verdict = score_unit(unit, text, admitted)

        body["scored"] += 1
        if verdict["fired"]:
            body["fired"] += 1
        if verdict["inexpressible"]:
            body["inexpressible"].append(uid)
        if not verdict["inexpressible"] and verdict["cuts"] in acceptable:
            body["acceptable"] += 1
        zero = body["zero_tolerance"]
        if verdict["fired"]:
            flags = verdict["flags"]
            if not (flags["preserving"] and flags["intact"]):
                zero["prose_not_preserved"] += 1
            if not flags["carrier_valid"]:
                zero["carrier_changed"] += 1
            if acceptable == {verdict["original"]}:
                zero["fired_where_only_the_original_is_acceptable"] += 1

    report = {
        "header": (
            "calibration admits nothing: these numbers are tuning feedback, "
            "and the admission contract refuses every one of them as evidence"
        ),
        "note": (
            "strata here were drawn under the taxonomy of their own round, "
            "so rates against a later taxonomy are indicative rather than admissible"
        ),
        "predicate": args.predicate,
        "predicate_digest": file_digest(REPO / "scripts" / "check_linefeeds.py"),
        "strata": {key: dict(body) for key, body in sorted(strata.items())},
    }
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(report["header"])
    print(report["note"])
    print(f"predicate: {args.predicate}")
    for key, body in sorted(strata.items()):
        shown = key or "(none: the shipped exact set)"
        line = (
            f"  {shown}: {body['acceptable']}/{body['scored']} acceptable, "
            f"{body['fired']} fired, {body['ambiguous']} ambiguous"
        )
        if body["inexpressible"]:
            line += f", {len(body['inexpressible'])} inexpressible"
        hits = {k: v for k, v in body["zero_tolerance"].items() if v}
        if hits:
            line += f", zero-tolerance {hits}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
