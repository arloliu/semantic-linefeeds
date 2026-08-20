"""Lay out one pass's repair batches from a drawn sample.

    python3 tests/corpus/repairs/batch.py <pass name> --sample <round>/sample.json [--out <dir>]

Everything a pass reads comes from the sample and from two files in this repository.
Nothing is recomputed from the checkout the units were drawn from,
which is what lets a batch be reproduced after that checkout is gone.

What a pass never sees:
the checker's own suggested repair,
another pass's answers,
the name of any class that withheld one,
and which candidate leaves the window unchanged.
The last of those is deliberate.
Changing nothing is one candidate among the others,
and a flag on it is a flag the undecided reach for.
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

from corpus_harness import file_digest, repair_batches  # noqa: E402

SKILL = REPO / "skills" / "semantic-linefeeds" / "SKILL.md"
REPAIRING = HERE.parent / "REPAIRING.md"
RENDERER = REPO / "scripts" / "check_linefeeds.py"

DIGESTED = {"skill": SKILL, "repairing": REPAIRING, "renderer": RENDERER}


def stale(sample):
    """Every pinned digest that no longer matches the file it names."""
    pinned = sample.get("stimulus_digests", {})
    return [
        f"{name}: the sample pins {pinned.get(name)}, and {path.name} is now {file_digest(path)}"
        for name, path in sorted(DIGESTED.items())
        if pinned.get(name) != file_digest(path)
    ]


def render(unit, number):
    """One unit, as a pass reads it."""
    lines = [
        f"## Unit {number}: `{unit['id']}`",
        "",
        "The checker reported this:",
        "",
        "```text",
        unit["stimulus"]["body"],
        "```",
        "",
        "The window it is about, exactly as the file holds it:",
        "",
        "```text",
    ]
    lines += unit["window"]["raw"]
    lines += ["```", "", "Candidate repairs:", ""]
    for candidate in unit["candidates"]:
        lines.append(f"{candidate['id']}:")
        lines.append("")
        lines.append("```text")
        lines += candidate["lines"]
        lines.append("```")
        lines.append("")
    lines.append(
        "Accept or reject every candidate above, name the one you would make, "
        "and say so if the repair you would make is not among them."
    )
    return "\n".join(lines)


ANSWER = """Answer every unit above in one JSON array, and nothing else that could be
mistaken for one. One object per unit:

```json
[{"id": "<unit id>", "choose": "<candidate>", "accept": ["<candidate>"],
  "reject": ["<candidate>"], "missing": []}]
```

Two rules an answer is checked against, and a unit that breaks either is thrown away:

1. `accept` and `reject` together name every candidate that unit offered, once each.
   Not a subset. Every one, including the candidate you would make.
2. `choose` is one of the names in your own `accept` list.
   If you would make a candidate, you accept it.

Leave `missing` empty unless the repair you would make is not on the list; when it is
not, put the lines you would write there instead, and leave `choose` out of that unit."""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    sample = json.loads(pathlib.Path(args.sample).read_text(encoding="utf-8"))
    problems = stale(sample)
    if problems:
        # A round whose stimulus changed halfway through measures two stimuli.
        sys.exit(
            "refused: the sample was drawn under a different rule\n  "
            + "\n  ".join(problems)
            + "\nnothing was laid out"
        )

    # A window the generator refused offers nothing to judge,
    # so it never reaches a pass.
    # It stays in the sample carrying its position count,
    # and `collect.py` reports it as the instrument defect it is.
    drawn = sample["units"]
    judgeable = [unit for unit in drawn if not unit.get("defect")]
    units = {unit["id"]: unit for unit in judgeable}
    batches = repair_batches(judgeable, args.name)
    out = pathlib.Path(args.out) if args.out else HERE.parent / "batches" / args.name
    out.mkdir(parents=True, exist_ok=True)

    rule = SKILL.read_text(encoding="utf-8")
    procedure = REPAIRING.read_text(encoding="utf-8")
    for index, batch in enumerate(batches, start=1):
        parts = [
            f"# Repair batch {index} of {len(batches)} for `{args.name}`\n\n"
            "Read the rule, then the procedure, then answer every unit below.",
            rule.strip("\n"),
            procedure.strip("\n"),
        ]
        parts += [
            render(units[unit["id"]], number)
            for number, unit in enumerate(batch, start=1)
        ]
        parts.append(ANSWER)
        path = out / f"batch-{index:02d}.md"
        path.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8")

    refused = len(drawn) - len(judgeable)
    print(f"{len(batches)} batch(es) for {args.name} -> {out}")
    print(f"{len(judgeable)} units laid out; {refused} left the sample as defects")


if __name__ == "__main__":
    main()
