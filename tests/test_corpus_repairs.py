"""The pinned repair measurements, checked against the detector that produced them.

Neither instrument can run here.
`measure.py` needs the three calibration sources cloned at their pinned commits,
and `history.py` needs this repository's whole history walked, which takes minutes.
So the outputs are pinned and this checks what the outputs claim,
which is the part that goes stale when the code moves underneath them.
"""

import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402

REPAIRS = REPO / "tests" / "corpus" / "repairs"
MEASURED = json.loads((REPAIRS / "measured.json").read_text(encoding="utf-8"))
MANIFEST = json.loads(
    (REPO / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8")
)


def sources():
    return {source["id"]: source for source in MANIFEST["sources"]}


@pytest.mark.parametrize("source_id", sorted(MEASURED))
def test_each_measured_source_is_pinned_to_the_commit_the_manifest_declares(source_id):
    """A measurement of a moving checkout is a measurement of nothing."""
    assert MEASURED[source_id]["commit"] == sources()[source_id]["commit"]
    assert sources()[source_id]["side"] == "calibration"


@pytest.mark.parametrize("source_id", sorted(MEASURED))
def test_every_measured_class_is_one_the_detector_declares(source_id):
    """The instrument reads `withheld_by` now, so a renamed class must break this."""
    body = MEASURED[source_id]
    assert set(body["per_class"]) == set(clf.WITHHOLDING_CLASSES)
    for key in body["exact_sets"]:
        named = set(key.split(",")) - {""}
        assert named <= set(clf.WITHHOLDING_CLASSES), key


@pytest.mark.parametrize("source_id", sorted(MEASURED))
def test_the_exact_sets_add_up_to_the_class_marginals(source_id):
    """The strata partition the population, and the marginals are sums over them.

    This is what says the two tables in the file are the same measurement.
    An exact set is a stratum; a class marginal is every stratum that contains it.
    """
    body = MEASURED[source_id]
    per_class = dict.fromkeys(clf.WITHHOLDING_CLASSES, 0)
    total = 0
    for key, count in body["exact_sets"].items():
        total += count
        for name in set(key.split(",")) - {""}:
            per_class[name] += count
    assert total == body["totals"]["boundaries"]
    assert per_class == body["per_class"]
    assert body["exact_sets"].get("", 0) == body["totals"].get("suggested", 0)


def test_the_wild_repair_population_is_too_thin_to_score_a_widening():
    """The measured fact the plan's elicit-rather-than-capture choice rests on.

    The count over-counts repairs rather than bounding them:
    a deleted line and an unrelated rewrite both look like one.
    Ten of them, over-counted, is still no population.
    """
    history = json.loads((REPAIRS / "history.json").read_text(encoding="utf-8"))
    assert history["repaired"].get("fused", 0) <= 10
    assert history["commits_walked"] > 200


# --- what a repair is, as an object two repairs can be compared as ---------
#
# Four facts, and the window they are measured over.
# Every shape the measured population holds has to be representable here,
# because a shape the normalizer cannot describe is a unit the round cannot score.

sys.path.insert(0, str(REPO / "tests"))

from corpus_harness import (  # noqa: E402
    carrier_valid,
    collapsed,
    compose,
    normalize_repair,
    repair_window,
    splice,
)


def window_at(text, path, index=0):
    records, _suppressions = clf.judged_lines(text, path)
    return repair_window(records, index)


def facts(text, path, replacement, index=0):
    window = window_at(text, path, index)
    return normalize_repair(window, replacement, text, path)


# One row per shape the plan names.
# Leaving one out is then a failing test rather than a gap nobody counts.
# Each row is (text, path, index, replacement, expected facts).
PAIR = "It ends mid-clause and\nthen it keeps running on.\n"

SHAPES = {
    "unchanged": (
        PAIR,
        "doc.md",
        0,
        ["It ends mid-clause and", "then it keeps running on."],
        (True, (22,), True, True),
    ),
    "rejoined": (
        PAIR,
        "doc.md",
        0,
        ["It ends mid-clause and then it keeps running on."],
        (True, (), True, True),
    ),
    "reworded": (
        PAIR,
        "doc.md",
        0,
        ["It ends and", "then it runs on."],
        (False, None, True, True),
    ),
    # A dropped line takes its leader and tail with it, which the rule counts as invalid.
    "clause dropped": (
        PAIR,
        "doc.md",
        0,
        ["It ends mid-clause and"],
        (False, None, False, True),
    ),
    "only the lower line touched": (
        "Stop now! Go later.\nit keeps running on.\n",
        "doc.md",
        0,
        ["Stop now! Go later.", "it keeps", "running on."],
        (True, (19, 28), True, True),
    ),
    "three lines out of two": (
        PAIR,
        "doc.md",
        0,
        ["It ends", "mid-clause and", "then it keeps running on."],
        (True, (7, 22), True, True),
    ),
    "last line of a paragraph": (
        "A first line stands here.\n\nStop now! Go later.\n",
        "doc.md",
        1,
        ["Stop now!", "Go later."],
        (True, (9,), True, True),
    ),
    "bulleted item with a continuation": (
        "- It ends mid-clause and\n  then it keeps running on.\n",
        "doc.md",
        0,
        ["- It ends mid-clause and then it keeps running on."],
        (True, (), True, True),
    ),
    "multi-digit ordered item": (
        "10. It ends mid-clause and\n   then it keeps running on.\n",
        "doc.md",
        0,
        ["10. It ends mid-clause and then it keeps running on."],
        (True, (), True, True),
    ),
    "nested blockquote": (
        "> > It ends mid-clause and\n> > then it keeps running on.\n",
        "doc.md",
        0,
        ["> > It ends mid-clause and then it keeps running on."],
        (True, (), True, True),
    ),
    # A docstring split cannot repeat `\"\"\"`, so it is representable and not valid,
    # which is the same answer the detector gives when it withholds as `prefix_other`.
    "docstring": (
        'def f():\n    """Stop now! Go later.\n\n    It continues here.\n    """\n',
        "x.py",
        0,
        ['    """Stop now!', "    Go later."],
        (True, (9,), False, True),
    ),
    "undecorated block comment": (
        "/* Stop now! Go later.\nIt continues here. */\n",
        "x.c",
        0,
        ["/* Stop now! Go later. It continues here. */"],
        (True, (), True, True),
    ),
    "different leaders above and below": (
        "// Stop now! Go later.\n//   it keeps running on.\n",
        "x.go",
        0,
        ["// Stop now!", "// Go later.", "//   it keeps running on."],
        (True, (9, 19), True, True),
    ),
    "a split repeating the anchor's leader": (
        "// Stop now! Go later.\n",
        "x.go",
        0,
        ["// Stop now!", "// Go later."],
        (True, (9,), True, True),
    ),
    "a split forgetting the anchor's leader": (
        "// Stop now! Go later.\n",
        "x.go",
        0,
        ["// Stop now!", "Go later."],
        (False, None, False, False),
    ),
    "a rejoin dropping the absorbed leader": (
        "> It ends mid-clause and\n> then it keeps running on.\n",
        "doc.md",
        0,
        ["> It ends mid-clause and then it keeps running on."],
        (True, (), True, True),
    ),
    "a rejoin keeping the absorbed leader": (
        "// It ends mid-clause and\n// then it keeps running on.\n",
        "x.go",
        0,
        ["// It ends mid-clause and // then it keeps running on."],
        (False, None, False, True),
    ),
    "a carrier kept where it was": (
        "Stop now! Go later. <!-- semlf-ignore wrap -->\nIt continues here.\n",
        "doc.md",
        0,
        ["Stop now!", "Go later. <!-- semlf-ignore wrap -->", "It continues here."],
        (True, (9, 19), True, True),
    ),
    "a carrier deleted by the repair": (
        "Stop now! Go later. <!-- semlf-ignore wrap -->\nIt continues here.\n",
        "doc.md",
        0,
        ["Stop now! Go later.", "It continues here."],
        (True, (19,), False, True),
    ),
    "a carrier moved to another line": (
        "Stop now! Go later. <!-- semlf-ignore wrap -->\nIt continues here.\n",
        "doc.md",
        0,
        ["Stop now! <!-- semlf-ignore wrap -->", "Go later.", "It continues here."],
        (True, (9, 19), False, True),
    ),
    "a rejoin absorbing a line that carries a carrier": (
        "It ends mid-clause and <!-- semlf-ignore wrap -->\nthen it keeps running on.\n",
        "doc.md",
        0,
        ["It ends mid-clause and then it keeps running on."],
        (True, (), False, True),
    ),
    # Long enough that the last line starts past every original line's prose,
    # so it belongs to no line the window holds and there is no leader it could carry.
    "a repair longer than the window it replaces": (
        PAIR,
        "doc.md",
        0,
        [
            "It ends and",
            "then it runs on.",
            "and more words follow",
            "here at the very end.",
        ],
        (False, None, False, True),
    ),
    "a carrier the repair invented": (
        PAIR,
        "doc.md",
        0,
        ["It ends mid-clause and then it keeps running on. <!-- semlf-ignore wrap -->"],
        (True, (), False, True),
    ),
    "an unrecognized trailing tail kept": (
        "/* Stop now! Go later. */\n",
        "x.c",
        0,
        ["/* Stop now! Go later. */"],
        (True, (), True, True),
    ),
    "an unrecognized trailing tail dropped": (
        "/* Stop now! Go later. */\n",
        "x.c",
        0,
        ["/* Stop now! Go later."],
        (True, (), False, True),
    ),
    "split across a blank line": (
        PAIR,
        "doc.md",
        0,
        ["It ends mid-clause and", "", "then it keeps running on."],
        (False, None, False, False),
    ),
    "turned into a fence": (
        PAIR + "\nA later paragraph stands here.\n",
        "doc.md",
        0,
        ["```", "It ends mid-clause and then it keeps running on."],
        (False, None, False, False),
    ),
    "turned into a heading": (
        PAIR,
        "doc.md",
        0,
        ["# It ends mid-clause and then it keeps running on."],
        (False, None, False, False),
    ),
    "turned into a table row": (
        PAIR,
        "doc.md",
        0,
        ["| It ends mid-clause and then it keeps running on. |"],
        (False, None, False, False),
    ),
}

NAMED_SHAPES = (
    "unchanged",
    "rejoined",
    "reworded",
    "clause dropped",
    "only the lower line touched",
    "three lines out of two",
    "last line of a paragraph",
    "bulleted item with a continuation",
    "multi-digit ordered item",
    "nested blockquote",
    "docstring",
    "undecorated block comment",
    "different leaders above and below",
    "a split repeating the anchor's leader",
    "a split forgetting the anchor's leader",
    "a rejoin dropping the absorbed leader",
    "a rejoin keeping the absorbed leader",
    "a carrier kept where it was",
    "a carrier deleted by the repair",
    "a carrier moved to another line",
    "a rejoin absorbing a line that carries a carrier",
    "a repair longer than the window it replaces",
    "a carrier the repair invented",
    "an unrecognized trailing tail kept",
    "an unrecognized trailing tail dropped",
    "split across a blank line",
    "turned into a fence",
    "turned into a heading",
    "turned into a table row",
)


def test_every_named_shape_has_a_row():
    """The list is long enough that partial coverage would read as completion."""
    assert set(SHAPES) == set(NAMED_SHAPES)


@pytest.mark.parametrize("name", NAMED_SHAPES)
def test_each_shape_normalizes_to_the_facts_it_should(name):
    text, path, index, replacement, expected = SHAPES[name]
    got = facts(text, path, replacement, index)
    preserving, breaks, carrier, intact = expected
    assert (got["preserving"], got["breaks"], got["carrier_valid"], got["intact"]) == (
        preserving,
        breaks,
        carrier,
        intact,
    ), got


def test_a_decorated_block_comment_has_no_carrier_valid_split():
    """The rule is byte for byte, and a `*` continuation is not a `/*` leader.

    This is not a gap in the rule.
    A split that repeated `/*` would not be a C comment,
    and the detector already withholds its own suggestion here as `prefix_other`.
    The shape is representable, and the answer for it is no.
    """
    got = facts(
        "/* Stop now! Go later.\n * It continues here. */\n",
        "x.c",
        ["/* Stop now!", " * Go later.", " * It continues here. */"],
    )
    assert got["preserving"] and got["intact"]
    assert not got["carrier_valid"]


def test_doing_nothing_is_a_point_in_this_space():
    """A finding whose right answer is to change nothing is an outcome, not a hole."""
    window = window_at(PAIR, "doc.md")
    assert window.breaks == (22,)
    unchanged = facts(PAIR, "doc.md", [record["raw"] for record in window.records])
    assert unchanged["breaks"] == window.breaks

    one_line = window_at("Stop now! Go later.\n", "doc.md")
    assert one_line.form == "one-line"
    assert one_line.breaks == ()


def test_collapsing_a_gap_moves_no_break():
    """A repair whose only change is the gap lands on the same point as the original.

    That is the intended answer.
    It is worth a test because three of the four facts cannot tell it from doing nothing.
    Where a break goes is what this corpus measures;
    how much whitespace sits at one is not.
    """
    text = "Stop now!  Go later.\n"
    window = window_at(text, "doc.md")
    assert facts(text, "doc.md", ["Stop now! Go later."])["breaks"] == window.breaks


def test_a_window_stops_at_a_paragraph_boundary():
    """A lower line from the next paragraph is not a line this repair may touch."""
    text = "Stop now! Go later.\n\nA later paragraph stands here.\n"
    assert window_at(text, "doc.md", 0).form == "one-line"
    directive = "Stop now! Go later.\n<!-- semlf-ignore-next long -->\nA later line.\n"
    assert window_at(directive, "doc.md", 0).form == "one-line"


def test_a_crlf_file_stays_a_crlf_file_through_a_splice():
    text = "Stop now! Go later.\r\nIt continues here.\r\n"
    window = window_at(text, "doc.md")
    spliced = splice(window, ["Stop now!", "Go later.", "It continues here."], text)
    assert "\n" not in spliced.replace("\r\n", "")
    assert facts(text, "doc.md", ["Stop now!", "Go later.", "It continues here."])[
        "carrier_valid"
    ]


def test_a_repair_writing_its_own_terminator_is_not_carrier_valid():
    assert not facts(
        PAIR, "doc.md", ["It ends mid-clause and\nthen it keeps running on."]
    )["carrier_valid"]


def test_composing_an_anchor_only_repair_keeps_the_lower_line_byte_for_byte():
    """The shipped suggestion replaces the anchor and says nothing about the line below.

    From `original_raw` rather than `raw`:
    the judged view has had the suppression carrier taken off it,
    and splicing that view back would delete the carrier from the file.
    """
    text = "Stop now! Go later.\nIt continues here. <!-- semlf-ignore wrap -->\n"
    window = window_at(text, "doc.md")
    (finding,) = [
        d
        for d in clf.diagnose(text, "doc.md")
        if d["kind"] == "fused" and d["line"] == 1
    ]
    composed = compose(window, finding["suggestion"]["lines"])
    assert composed[-1] == window.records[1]["original_raw"]
    assert "<!-- semlf-ignore wrap -->" in composed[-1]
    got = normalize_repair(window, composed, text, "doc.md")
    assert got == {
        "preserving": True,
        "breaks": (9, 19),
        "carrier_valid": True,
        "intact": True,
    }


def test_composing_into_a_one_line_window_adds_nothing():
    window = window_at("Stop now! Go later.\n", "doc.md")
    assert compose(window, ["Stop now!", "Go later."]) == ["Stop now!", "Go later."]


def test_the_collapse_is_what_makes_two_rewrites_comparable():
    assert collapsed("a   b\tc ") == "a b c"


def test_a_window_measured_against_a_file_that_moved_is_not_scored():
    """A window records what stood outside it, and a stale window is refused.

    The four facts are only about the window,
    so nothing else in them would notice that the rest of the file had changed underneath.
    Refusing is the answer, because a repair scored against the wrong file is not scored.
    """
    window = window_at(PAIR, "doc.md")
    moved = "An earlier paragraph stands here.\n\n" + PAIR
    got = normalize_repair(
        window, ["It ends mid-clause and then it keeps running on."], moved, "doc.md"
    )
    assert got["intact"] is False
    assert got["preserving"] is False


def test_a_replacement_that_splits_a_paragraph_is_not_intact():
    """Two paragraphs where there was one is a structural change, not a line break."""
    got = facts(
        PAIR, "doc.md", ["It ends mid-clause and", "", "then it keeps running on."]
    )
    assert got["intact"] is False


def test_a_window_never_reaches_past_its_own_paragraph():
    """The lower line has to be one the anchor's repair may touch."""
    text = "Stop now! Go later.\n\nA later paragraph stands here.\n"
    records, _suppressions = clf.judged_lines(text, "doc.md")
    assert len(records) == 2
    assert records[0]["paragraph"] != records[1]["paragraph"]
    window = repair_window(records, 0)
    assert window.form == "one-line"
    assert window.below == ("A later paragraph stands here.",)


def test_a_stale_window_is_caught_by_what_stood_above_it():
    """Equal-length prose above, so nothing but the recorded prefix notices."""
    original = "A first line.\n\n" + PAIR
    window = window_at(original, "doc.md", 1)
    assert window.above == ("A first line.",)
    moved = "A worse line.\n\n" + PAIR
    got = normalize_repair(
        window, ["It ends mid-clause and then it keeps running on."], moved, "doc.md"
    )
    assert got["intact"] is False


def test_a_stale_window_is_caught_by_what_stood_below_it():
    """The same, on the other side, where the counts and the paragraphs both still fit."""
    original = PAIR + "\nA later line.\n"
    window = window_at(original, "doc.md", 0)
    assert window.below == ("A later line.",)
    moved = PAIR + "\nA WRONG line.\n"
    got = normalize_repair(
        window, ["It ends mid-clause and then it keeps running on."], moved, "doc.md"
    )
    assert got["intact"] is False


def judged(raw, prose):
    """One judged line built directly, for a shape no extractor path produces today."""
    return clf._judged_record("", [0, 0], 1, raw, prose, raw, None, 0)


def test_a_repair_does_not_write_its_own_line_terminators():
    """Checked on the replacement itself, before anything is spliced.

    A newline inside a line would also reach the file as two lines and be refused for
    that, but the two refusals are not the same one:
    the repair was handed lines and wrote something that is not a line.
    """
    window = window_at("Stop now! Go later.\n", "doc.md")
    produced = [judged("It ends and then it runs on.", "It ends and then it runs on.")]
    assert not carrier_valid(window, ["It ends and\nthen it runs on."], produced)
    assert not carrier_valid(window, ["It ends and\rthen it runs on."], produced)


def test_a_line_in_the_middle_of_a_split_carries_no_tail_of_its_own():
    """A tail belongs to the line it was on, and a split does not give it a second home.

    Constructed, because a block comment is the only shape with a tail worth moving,
    and splitting one of those crosses a paragraph before it gets here.
    """
    window = window_at("/* Stop now! Go later. */\n", "x.c")
    assert window.records[0]["tail"] == " */"
    closing = [
        judged("/* Stop now! */", "Stop now!"),
        judged("/* Go later. */", "Go later."),
    ]
    assert not carrier_valid(window, ["/* Stop now! */", "/* Go later. */"], closing)
    plain = [
        judged("/* Stop now!", "Stop now!"),
        judged("/* Go later. */", "Go later."),
    ]
    assert carrier_valid(window, ["/* Stop now!", "/* Go later. */"], plain)
