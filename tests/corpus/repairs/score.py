"""Score a predicate against frozen acceptable sets: calibration, or one sealed round.

    python3 tests/corpus/repairs/score.py <checkout-root> \
        --sample <sample.json> --answers <answers-dir> --predicate shipped|candidate
    python3 tests/corpus/repairs/score.py <checkout-root> --bundle <round-dir>

`--bundle` is the sealed-round mode, and it is atomic:
one open decrypts the bundle, records the spend before any plaintext escapes,
scores `candidate` and `shipped` in the same process through the same algorithm,
and appends one paired evaluation to the ledger —
or a failed-evaluation state, so a crash cannot make the bundle reusable.
A second open refuses (ADR-0008).
The mechanical admission verdict is computed clause by clause from the contract,
and it is recorded with the numbers;
what ships is still decided by the records Task 9 writes, never by this exit code.

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
import getpass
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE.parent))

import check_linefeeds as clf  # noqa: E402
from collect import resolved  # noqa: E402
from corpus_harness import (  # noqa: E402
    REPAIR_ADMISSION,
    Holdout,
    candidate_for_breaks,
    composed,
    file_digest,
    normalize_repair,
    original_cuts,
    repair_window,
    wilson,
)

CORPUS = TESTS / "corpus"


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


def scored_strata(sample, answers_dir, root, admitted, adjudications=None):
    """Per-stratum verdicts of one predicate over one round's resolved outcomes."""
    decisions = (
        {entry["id"]: entry for entry in adjudications if entry.get("outcome")}
        if adjudications
        else None
    )
    outcomes, _names = resolved(sample, answers_dir, decisions)
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
    return {key: dict(body) for key, body in sorted(strata.items())}


def admission_verdict(candidate_strata):
    """The preregistered contract, applied clause by clause to the candidate's strata.

    Mechanical and recorded, never deciding what ships:
    the flip is Task 9's, made against the records this verdict lands in.
    """
    floor = REPAIR_ADMISSION["floor"]
    rules = REPAIR_ADMISSION["reportable"]
    activated = {
        key: body
        for key, body in candidate_strata.items()
        if key and set(key.split(",")) <= set(clf.CANDIDATE_ADMITTED)
    }
    problems = []
    strata_out = {}
    if not activated:
        problems.append("no activated stratum was scored")
    for key, body in sorted(activated.items()):
        scored, ambiguous = body["scored"], body["ambiguous"]
        interval = wilson(body["acceptable"], scored) if scored else None
        entry = {
            "scored": scored,
            "acceptable": body["acceptable"],
            "ambiguous": ambiguous,
            "lower_bound": interval[0] if interval else None,
        }
        strata_out[key] = entry
        if scored < rules["min_scored"]:
            problems.append(f"{key}: {scored} scored is below {rules['min_scored']}")
            continue
        half = (interval[1] - interval[0]) / 2
        if half > rules["max_interval_half_width"]:
            problems.append(f"{key}: interval half-width {half:.3f} is unreportable")
        if ambiguous / (scored + ambiguous) > rules["max_ambiguous_fraction"]:
            problems.append(f"{key}: ambiguous fraction is unreportable")
        if interval[0] < floor:
            problems.append(
                f"{key}: lower bound {interval[0]:.3f} is below the floor {floor}"
            )
    zero = collections.Counter()
    for body in candidate_strata.values():
        zero.update(body["zero_tolerance"])
    for name, count in sorted(zero.items()):
        if count:
            problems.append(f"zero tolerance: {name} occurred {count} time(s)")
    return {
        "outcome": "refused" if problems else "admitted",
        "admitted": sorted(clf.CANDIDATE_ADMITTED),
        "problems": problems,
        "strata": strata_out,
        "zero_tolerance": dict(zero),
    }


def score_bundle(round_dir, root, manifest_path=None, passphrase=None):
    """One atomic open: decrypt, spend, score both sides, append the paired result."""
    round_dir = pathlib.Path(round_dir)
    number = int(round_dir.name.split("-")[-1])
    manifest_path = pathlib.Path(manifest_path or (CORPUS / "manifest.json"))
    holdout = Holdout(
        round_dir / "bundle.json",
        manifest_path.parent / "freeze.jsonl",
        REPO / "scripts" / "check_linefeeds.py",
        manifest_path,
        round=number,
    )
    if passphrase is None:
        passphrase = getpass.getpass("passphrase: ")
    text = holdout.open_spending(passphrase)
    try:
        body = json.loads(text)
        sample = body["sample"]
        with tempfile.TemporaryDirectory() as answers_dir:
            answers = pathlib.Path(answers_dir)
            for name, content in body["answers"].items():
                (answers / name).write_text(content, encoding="utf-8")
            sides = {
                name: scored_strata(
                    sample, answers, root, PREDICATES[name](), body.get("adjudications")
                )
                for name in ("candidate", "shipped")
            }
        verdict = admission_verdict(sides["candidate"])
        result = dict(
            verdict,
            candidate=sides["candidate"],
            shipped=sides["shipped"],
            predicate_digest=file_digest(REPO / "scripts" / "check_linefeeds.py"),
        )
    except BaseException as failure:
        holdout.complete_evaluation(
            {"state": "failed-evaluation", "error": repr(failure)}
        )
        raise
    holdout.complete_evaluation(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="checkout root the sample's sources sit under")
    parser.add_argument("--sample")
    parser.add_argument("--answers")
    parser.add_argument("--predicate", choices=sorted(PREDICATES))
    parser.add_argument("--bundle", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()

    if args.bundle is not None:
        if args.sample or args.answers or args.predicate:
            sys.exit("--bundle scores both sides by itself; drop the other flags")
        result = score_bundle(args.bundle, root, args.manifest)
        if args.json_out:
            pathlib.Path(args.json_out).write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(f"outcome: {result['outcome']} for {result['admitted']}")
        for problem in result["problems"]:
            print(f"  {problem}")
        for key, entry in sorted(result["strata"].items()):
            print(
                f"  {key}: {entry['acceptable']}/{entry['scored']} acceptable, "
                f"lower bound {entry['lower_bound']}"
            )
        print("the paired evaluation is in the ledger; the bundle is spent")
        return 0

    if not (args.sample and args.answers and args.predicate):
        sys.exit("calibration mode needs --sample, --answers, and --predicate")
    sample = json.loads(pathlib.Path(args.sample).read_text(encoding="utf-8"))
    if sample.get("drawn_under"):
        sys.exit(
            "this sample belongs to a ledger-bound round; "
            "a sealed round is scored only through --bundle, one open, both sides"
        )
    answers_dir = pathlib.Path(args.answers).resolve()
    admitted = PREDICATES[args.predicate]()
    strata = scored_strata(sample, answers_dir, root, admitted)

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
        "strata": strata,
    }
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(report["header"])
    print(report["note"])
    print(f"predicate: {args.predicate}")
    for key, body in sorted(strata.items()):  # noqa: B007 - already sorted dict
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
