"""The GitHub Action's workflow contract: input names, defaults, and the output.

A workflow that sets `fail-on` or reads `sarif-file` breaks on a rename,
so the names and defaults are pinned here as text —
the stdlib has no YAML parser, and a pin needs no more than presence.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACTION = (REPO / "action.yml").read_text(encoding="utf-8")


def section(name):
    got = re.search(rf"^{name}:\n(.*?)(?=^\S)", ACTION, re.M | re.S)
    assert got, f"action.yml lost its {name} block"
    return got.group(1)


def input_block(name):
    # One input's own block: from its key to the next sibling key,
    # so an assertion can never satisfy itself from a later input.
    inputs = section("inputs")
    got = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", inputs, re.M | re.S)
    assert got, f"action.yml lost the {name} input"
    return got.group(1)


def test_the_input_names_and_defaults_are_pinned():
    assert re.search(r"^    default: fused$", input_block("fail-on"), re.M)
    assert re.search(r"^    default: base$", input_block("mode"), re.M)
    assert re.search(
        r"^    default: \$\{\{ github\.event\.pull_request\.base\.sha \}\}$",
        input_block("base"),
        re.M,
    )
    assert re.search(r'^    default: ""$', input_block("sarif-file"), re.M)


def test_the_sarif_file_output_is_pinned():
    outputs = section("outputs")
    assert re.search(r"^  sarif-file:$", outputs, re.M)
    assert "steps.check.outputs.sarif-file" in outputs


def test_the_gate_grammar_is_documented_on_the_input():
    # The frozen fail-on grammar: trimmed segments, empty segments ignored,
    # duplicates tolerated, at least one of fused/wrap required.
    fail_on = input_block("fail-on")
    for phrase in (
        "comma-separated",
        "whitespace-trimmed",
        "empty",
        "duplicates",
        "at least one",
    ):
        assert phrase in fail_on, f"fail-on description no longer names {phrase}"
