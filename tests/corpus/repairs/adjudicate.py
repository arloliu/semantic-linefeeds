"""Prepare the repair units a maintainer has to decide, and check the decisions.

    python3 tests/corpus/repairs/adjudicate.py worksheet <repairs-dir> <answers-dir>
    python3 tests/corpus/repairs/adjudicate.py check     <repairs-dir> <answers-dir>

Decisions are written to `adjudications.json` beside the sample they belong to.

Referrals are grouped by the shape of the disagreement rather than listed.
A prose list of sixty disagreements is not a decision procedure,
and the three shapes below are decided in three different ways:

- `split`: one pass rejected a candidate the others accepted.
- `missing`: a pass reported a repair the generator never offered.
- `none accepted`: no candidate was unanimously accepted.

Each entry is a choice among the candidates the unit was drawn with,
plus a candidate the maintainer supplies,
plus `ambiguous`, which means the rule does not settle what this line should become.

A decision without a reason is the failure this exists to prevent.
"""

import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(HERE.parent))

from collect import resolved, votes_for  # noqa: E402

OUTCOMES = ("settled", "ambiguous")


def shape_of(got, unit):
    """Which of the three disagreements this is, so like is decided beside like."""
    if got["outcome"] == "defect":
        return "missing"
    if got["referred"]:
        return "split"
    return "none accepted"


def pending(repairs, answers_dir):
    """Every unit the passes sent to a maintainer, with what they said."""
    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    units = {unit["id"]: unit for unit in sample["units"]}
    outcomes, names = resolved(sample, answers_dir)
    cast = votes_for(sample, answers_dir)

    out = []
    for uid, got in sorted(outcomes.items()):
        if got["outcome"] not in ("adjudicated", "defect"):
            continue
        unit = units[uid]
        out.append(
            {
                "id": uid,
                "shape": shape_of(got, unit),
                "path": unit["path"],
                "lines": unit["lines"],
                "window": unit["window"]["raw"],
                "candidates": [
                    {"id": candidate["id"], "lines": candidate["lines"]}
                    for candidate in unit["candidates"]
                ],
                "referred": sorted(
                    candidate["id"]
                    for candidate in unit["candidates"]
                    if tuple(candidate["cuts"]) in got.get("referred", ())
                ),
                "passes": {name: cast[uid][name] for name in sorted(cast[uid])},
                # What the maintainer fills in.
                # `acceptable` names candidates by id.
                # `supplied` holds whole line lists, for a repair no candidate offered.
                "outcome": None,
                "acceptable": [],
                "supplied": [],
                "reason": "",
            }
        )
    return out


def worksheet(repairs, answers_dir, out):
    entries = pending(repairs, answers_dir)
    if out.exists():
        decided = {
            entry["id"]: entry for entry in json.loads(out.read_text(encoding="utf-8"))
        }
        for entry in entries:
            was = decided.get(entry["id"])
            if was:
                for field in ("outcome", "acceptable", "supplied", "reason"):
                    entry[field] = was.get(field, entry[field])
    out.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    by_shape = collections.Counter(entry["shape"] for entry in entries)
    blank = sum(1 for entry in entries if not entry["reason"].strip())
    print(f"{len(entries)} to decide, {blank} still blank -> {out}")
    for shape, count in sorted(by_shape.items()):
        print(f"  {shape:<14} {count}")
    return 0


def check(repairs, answers_dir, out):
    entries = (
        {entry["id"]: entry for entry in json.loads(out.read_text(encoding="utf-8"))}
        if out.exists()
        else {}
    )
    problems = []
    for entry in pending(repairs, answers_dir):
        decided = entries.get(entry["id"])
        if decided is None:
            problems.append(
                f"{entry['id']}: the passes could not settle this and nobody did"
            )
            continue
        if decided.get("outcome") not in OUTCOMES:
            problems.append(
                f"{entry['id']}: outcome {decided.get('outcome')!r} is not one of {OUTCOMES}"
            )
        elif decided["outcome"] == "settled" and not (
            decided.get("acceptable") or decided.get("supplied")
        ):
            problems.append(
                f"{entry['id']}: settled with an empty acceptable set; "
                "a unit whose only correct answer is the original names that candidate"
            )
        if not decided.get("reason", "").strip():
            problems.append(f"{entry['id']}: decided with no reason recorded")
    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    mode = sys.argv[1]
    repairs = pathlib.Path(sys.argv[2]).resolve()
    answers_dir = pathlib.Path(sys.argv[3]).resolve()
    decided = repairs / "adjudications.json"
    sys.exit(
        worksheet(repairs, answers_dir, decided)
        if mode == "worksheet"
        else check(repairs, answers_dir, decided)
    )
