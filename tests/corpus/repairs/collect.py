"""Resolve three repairing passes into one acceptable set per unit, and report.

    python3 tests/corpus/repairs/collect.py <repairs-dir> <answers-dir>

`<repairs-dir>` holds `sample.json`, and `adjudications.json` once decisions exist.
`<answers-dir>` holds `<pass>-<index>.out`, one file per pass per batch.

The resolution is the one the plan records.
A candidate is acceptable when it is valid and every pass accepted it.
A candidate the passes split on is referred, and so is the whole unit.

Three counts are reported as headlines rather than footnotes:
candidates that lose prose, candidates that mangle a leader or a carrier,
and candidates that stop being prose.
They are the rate at which a competent agent damages a line while repairing it,
and they bound what any automatic class may be trusted with.
"""

import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))

from corpus_harness import (  # noqa: E402
    candidate_is_valid,
    pass_answers,
    repair_pass_verdicts,
    repair_resolution,
)


def votes_for(sample, answers_dir):
    """Every pass's answer per unit, keyed by the pass's name."""
    units = {unit["id"]: unit for unit in sample["units"]}
    votes = collections.defaultdict(dict)
    for path in sorted(answers_dir.glob("*.out")):
        name = path.name.split("-")[0]
        for answer in pass_answers(path):
            if answer.get("id") in units:
                votes[answer["id"]][name] = answer
    return votes


def resolved(sample, answers_dir, decisions=None):
    """One outcome per unit that every pass answered, adjudications applied."""
    decisions = decisions or {}
    units = {unit["id"]: unit for unit in sample["units"]}
    votes = votes_for(sample, answers_dir)
    names = sorted({name for cast in votes.values() for name in cast})

    out = {}
    for uid, cast in sorted(votes.items()):
        if sorted(cast) != names:
            continue
        unit = units[uid]
        if unit.get("defect"):
            # A window the generator refused is reported, not decided.
            out[uid] = {"outcome": "defect", "reason": unit["defect"]}
            continue
        candidates = {
            tuple(candidate["cuts"]): candidate for candidate in unit["candidates"]
        }
        try:
            verdicts = [
                repair_pass_verdicts(cast[name], unit["candidates"]) for name in names
            ]
        except ValueError as problem:
            out[uid] = {"outcome": "error", "reason": str(problem)}
            continue
        got = repair_resolution(verdicts, candidates)
        decided = decisions.get(uid)
        if got["outcome"] == "adjudicated" and decided:
            # The worksheet asks for candidate ids, because a maintainer reads ids.
            # The cuts they stand for are what everything downstream compares.
            named = {
                candidate["id"]: tuple(candidate["cuts"])
                for candidate in unit["candidates"]
            }
            unknown = sorted(set(decided["acceptable"]) - set(named))
            if unknown:
                out[uid] = {
                    "outcome": "error",
                    "reason": f"a decision named candidates the unit never had: {unknown}",
                }
                continue
            got = dict(
                got,
                outcome=decided["outcome"],
                acceptable=frozenset(named[one] for one in decided["acceptable"]),
                reason=decided["reason"],
            )
        out[uid] = got
    return out, names


def main(repairs, answers_dir):
    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    units = {unit["id"]: unit for unit in sample["units"]}
    decided = repairs / "adjudications.json"
    decisions = (
        {
            entry["id"]: entry
            for entry in json.loads(decided.read_text(encoding="utf-8"))
            if entry.get("outcome")
        }
        if decided.exists()
        else {}
    )

    outcomes, names = resolved(sample, answers_dir, decisions)
    print(f"units {len(units)}  passes {names}  answered by all {len(outcomes)}")

    damage = collections.Counter()
    offered = 0
    for unit in units.values():
        for candidate in unit.get("candidates", []):
            offered += 1
            damage["not preserving"] += not candidate["preserving"]
            damage["carrier invalid"] += not candidate["carrier_valid"]
            damage["not intact"] += not candidate["intact"]
            damage["valid"] += candidate_is_valid(candidate)
    print(f"\ncandidates offered {offered}")
    for name in ("valid", "not preserving", "carrier invalid", "not intact"):
        print(f"  {name:<16} {damage[name]}")

    per_stratum = collections.defaultdict(collections.Counter)
    for uid, got in outcomes.items():
        per_stratum[units[uid]["stratum"]][got["outcome"]] += 1
    print("\nper stratum")
    shown = ("settled", "adjudicated", "ambiguous", "defect", "error")
    print(f"  {'':<44}" + "".join(f"{name:>13}" for name in shown))
    for key in sorted(per_stratum):
        row = per_stratum[key]
        label = (key or "(none: suggested today)")[:42]
        print(f"  {label:<44}" + "".join(f"{row[name]:>13}" for name in shown))

    # Descriptive, and it decides nothing.
    # The admission contract gates each activated stratum on its own bound.
    settled = sum(row["settled"] for row in per_stratum.values())
    print(f"\n{settled} of {len(outcomes)} units settled without a maintainer")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve())
