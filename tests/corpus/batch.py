"""Emit one labeling batch, identical in content for every labeler.

    python3 tests/corpus/batch.py <sample.json> <labeler> <index>

Only the order differs between labelers, and the order is derived from the labeler's name,
so the same name always produces the same sequence.
No detector output goes into a batch.
A labeler shown the verdict would measure agreement with the detector instead of judging prose.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))

from corpus_harness import labeling_batches  # noqa: E402

SIZE = 15

HEADER = """You are labeling prose for a corpus that measures a line-break checker.
Judge the prose against the rule below. Do not guess what any tool would say.

=== THE RULE (normative) ===
{rule}

=== THE PROCEDURE ===
{procedure}

=== UNITS ===
Each unit shows a paragraph. The line marked UPPER and the line marked LOWER are the
boundary under judgment; the other lines are context only.

{units}

=== ANSWER ===
Reply with JSON only, no prose around it, exactly this shape:

[{{"id": "<unit id>", "wrap": "true|false|ambiguous", "fused": "true|false|ambiguous"}}]

"wrap"  answers: is the boundary between UPPER and LOWER a violation?
"fused" answers: does UPPER alone hold more than one sentence?
Answer every unit in the batch, in any order.
"""


def render(unit):
    lines = [f"unit {unit['id']}"]
    upper, lower = unit["upper"], unit["lower"]
    seen_upper = False
    for line in unit["context"]:
        if not seen_upper and line == upper:
            lines.append(f"  UPPER  | {line}")
            seen_upper = True
        elif (
            seen_upper
            and line == lower
            and not any(m.startswith("  LOWER") for m in lines)
        ):
            lines.append(f"  LOWER  | {line}")
        else:
            lines.append(f"         | {line}")
    return "\n".join(lines)


def main(sample_path, labeler, index):
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    batches = labeling_batches(sample["units"], labeler, SIZE)
    units = batches[index]
    print(
        HEADER.format(
            rule=(REPO / "skills" / "semantic-linefeeds" / "SKILL.md").read_text(
                encoding="utf-8"
            ),
            procedure=(TESTS / "corpus" / "LABELING.md").read_text(encoding="utf-8"),
            units="\n\n".join(render(unit) for unit in units),
        )
    )


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
