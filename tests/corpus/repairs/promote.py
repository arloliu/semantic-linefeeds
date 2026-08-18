"""Promote the settled repair units into the manifest.

    python3 tests/corpus/repairs/promote.py <repairs-dir> <answers-dir> <checkout-root>
        [--manifest <path>]

**This is the only place a repair algorithm is read.**
Drawing, batching, and resolution stay blind to it,
because a pass shown the machine's answer measures agreement with the machine.
Reading it here seals every acceptable set it is scored against.

What the shipped predicate produces is a historical fact, so it is pinned.
`baseline_suggestion` carries the digest of the predicate that produced it,
and promotion refuses when the tree holds a different one.
Otherwise a later session, running this against a widened predicate, rewrites history.
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
sys.path.insert(0, str(HERE.parent))

from collect import resolved, votes_for  # noqa: E402
from corpus_harness import (  # noqa: E402
    candidate_for_breaks,
    compose,
    file_digest,
    normalize_repair,
    repair_window,
    score_repair,
    set_acceptable,
)

PREDICATE = REPO / "scripts" / "check_linefeeds.py"


def baseline_for(unit, text, path):
    """What the shipped repair does to this window, composed and normalized.

    The shipped suggestion replaces the anchor and says nothing about the line below,
    so it is composed into a whole-window replacement before it is normalized.
    A class the predicate withholds produces nothing.
    That is recorded as nothing rather than as a failure.
    """
    import check_linefeeds

    records, _suppressions = check_linefeeds.judged_lines(text, path)
    window = repair_window(records, unit["index"])
    fused = [
        finding
        for finding in check_linefeeds.diagnose(text, path)
        if finding["kind"] == "fused" and finding["line"] == unit["line"]
    ]
    finding = fused[unit["match"]] if unit["match"] < len(fused) else None
    if finding is None or "suggestion" not in finding:
        return {
            "lines": None,
            "preserving": False,
            "carrier_valid": False,
            "intact": False,
            "breaks": None,
            "predicate": file_digest(PREDICATE),
        }
    lines = compose(window, finding["suggestion"]["lines"])
    got = normalize_repair(window, lines, text, path)
    return dict(got, lines=lines, predicate=file_digest(PREDICATE))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repairs")
    parser.add_argument("answers")
    parser.add_argument("root")
    parser.add_argument("--manifest", default=str(TESTS / "corpus" / "manifest.json"))
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)

    repairs = pathlib.Path(args.repairs).resolve()
    answers_dir = pathlib.Path(args.answers).resolve()
    root = pathlib.Path(args.root).resolve()
    manifest_path = pathlib.Path(args.manifest)

    # The lock is a digest of the manifest.
    # Writing one without repinning the other leaves the pair disagreeing.
    # Refused here rather than after the write:
    # the write is the expensive part of a round,
    # and a refusal that arrives afterwards arrives too late.
    lock_path = manifest_path.with_name("manifest.lock")
    if lock_path.exists() and not args.reason.strip():
        sys.exit(
            "promoting rewrites the manifest, and its lock has to say what changed.\n"
            "Pass --reason with a line a reviewer can read.\n"
            "Nothing was promoted."
        )

    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    units = {unit["id"]: unit for unit in sample["units"]}
    decided_path = repairs / "adjudications.json"
    decisions = (
        {
            entry["id"]: entry
            for entry in json.loads(decided_path.read_text(encoding="utf-8"))
            if entry.get("outcome")
        }
        if decided_path.exists()
        else {}
    )

    outcomes, names = resolved(sample, answers_dir, decisions)
    votes = votes_for(sample, answers_dir)
    if not outcomes:
        sys.exit("no unit was answered by every pass\nnothing was promoted")

    # Every referral must be decided before anything is written.
    # Promoting the settled units first reports a rate over the units that were easy.
    undecided = [
        uid
        for uid, got in sorted(outcomes.items())
        if got["outcome"] in ("adjudicated", "defect")
    ]
    if undecided:
        sys.exit(
            f"{len(undecided)} referral(s) still undecided, first {undecided[:3]}"
            "\nnothing was promoted"
        )

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = {record["id"]: record for record in document.get("repairs", [])}
    predicate = file_digest(PREDICATE)
    stale = [
        record["id"]
        for record in recorded.values()
        if record.get("baseline_suggestion", {}).get("predicate")
        not in (None, predicate)
    ]
    if stale:
        sys.exit(
            f"the manifest records {len(stale)} repair(s) under a different predicate, "
            f"first {stale[:3]}\nthe tree now holds {predicate}\nnothing was promoted"
        )

    texts, out = {}, []
    for uid, got in sorted(outcomes.items()):
        unit = units[uid]
        key = (unit["source"], unit["path"])
        if key not in texts:
            texts[key] = (root / unit["source"] / unit["path"]).read_text(
                encoding="utf-8"
            )
        text = texts[key]

        record = dict(unit)
        # The stratum a rate is reported over, with the weight that rate carries.
        # A record naming a set and not the population it came from cannot be weighted.
        record["stratum"] = dict(
            sample.get("strata", {}).get(unit["stratum"], {}), set=unit["stratum"]
        )
        record["passes"] = {
            name: {
                "choose": cast[name].get("choose"),
                "accept": cast[name].get("accept", []),
                "reject": cast[name].get("reject", []),
                "missing": cast[name].get("missing") or [],
            }
            for name in names
            for cast in [votes[uid]]
        }
        record["outcome"] = got["outcome"]
        if got.get("reason"):
            record["adjudication"] = got["reason"]
        acceptable = {tuple(cuts) for cuts in got.get("acceptable", ())}
        record["acceptable"] = [
            candidate["id"]
            for candidate in unit["candidates"]
            if tuple(candidate["cuts"]) in acceptable
        ]
        # Frozen before the machine speaks, and reading its answer below seals it.
        # The seal is a fact about this run rather than a field the manifest carries,
        # so it lives beside the record instead of in it.
        sealed = {}
        set_acceptable(sealed, acceptable)
        baseline = baseline_for(unit, text, unit["path"])
        landed = candidate_for_breaks(unit["candidates"], baseline["breaks"])
        baseline["candidate"] = landed["id"] if landed else None
        baseline["acceptable"] = bool(
            landed and score_repair(sealed, tuple(landed["cuts"]))
        )
        record["baseline_suggestion"] = baseline
        out.append(record)

    document["repairs"] = out
    manifest_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if lock_path.exists():
        lock_path.write_text(
            json.dumps(
                {"digest": file_digest(manifest_path), "reason": args.reason.strip()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    suggested = [r for r in out if r["baseline_suggestion"]["lines"] is not None]
    right = sum(1 for r in suggested if r["baseline_suggestion"]["acceptable"])
    print(f"{len(out)} repair record(s) -> {manifest_path}")
    if lock_path.exists():
        print(f"repinned {lock_path.name}")
    print(
        f"the shipped predicate repaired {len(suggested)} of them, "
        f"{right} landing in the acceptable set"
    )


if __name__ == "__main__":
    main()
