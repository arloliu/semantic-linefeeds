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
    # A list marker may not be repeated: two lines opening `4. ` are two items.
    # What replaces it is the continuation the window itself shows.
    "an ordered item split onto its continuation indent": (
        "4. It ends mid-clause and.\n   then it keeps running on.\n",
        "doc.md",
        0,
        ["4. It ends mid-clause and.", "   then it keeps running on."],
        (True, (23,), True, True),
    ),
    "a bulleted item split onto its continuation indent": (
        "- It ends mid-clause and.\n  then it keeps running on.\n",
        "doc.md",
        0,
        ["- It ends mid-clause and.", "  then it keeps running on."],
        (True, (23,), True, True),
    ),
    "a bulleted item split with a second marker": (
        "- It ends mid-clause and.\n  then it keeps running on.\n",
        "doc.md",
        0,
        ["- It ends mid-clause and.", "- then it keeps running on."],
        (False, None, False, False),
    ),
    "a lazily continued item keeps the file's own lazy continuation": (
        "* It ends mid-clause and.\nthen it keeps running on.\n",
        "doc.md",
        0,
        ["* It ends mid-clause and.", "then it keeps running on."],
        (True, (23,), True, True),
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
    "an ordered item split onto its continuation indent",
    "a bulleted item split onto its continuation indent",
    "a bulleted item split with a second marker",
    "a lazily continued item keeps the file's own lazy continuation",
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


# --- the acceptable set ----------------------------------------------------
#
# A label has three values and a repair does not.
# A long fused line can be split at either of two real clause boundaries,
# and both results are correct prose,
# so the settled outcome is a set and the question is whether the machine's answer is in it.

from corpus_harness import (  # noqa: E402
    MAX_POSITIONS,
    ScoringRefused,
    candidate_is_valid,
    continuation_leader,
    cut_positions,
    original_cuts,
    repair_candidates,
    repair_pass_verdicts,
    repair_resolution,
    score_repair,
    set_acceptable,
)


def universe(text, path, index=0):
    window = window_at(text, path, index)
    return window, repair_candidates(window, text, path)


def test_the_original_is_always_in_the_universe():
    """Leaving the line alone has to be an answer the corpus can give.

    For a window whose anchor ends mid-clause,
    the existing break sits where no lexical rule offers one.
    Most units in the stratum a period widening activates are exactly that.
    A universe built from the lexical rule alone would not hold the original for them.
    """
    for text, path in (
        (PAIR, "doc.md"),
        ("Stop now! Go later.\n", "doc.md"),
        ("- It ends mid-clause and\n  then it keeps running on.\n", "doc.md"),
    ):
        window, found = universe(text, path)
        cuts = original_cuts(window)
        assert cuts in found["candidates"], (text, found["candidates"].keys())
        assert candidate_is_valid(found["candidates"][cuts])
        assert found["candidates"][cuts]["lines"] == [
            record["original_raw"] for record in window.records
        ]


def test_a_wrap_carrying_window_offers_its_own_break():
    """The non-lexical source, named on its own because it is the majority case."""
    window = window_at(PAIR, "doc.md")
    assert cut_positions(window) == (22,)
    assert PAIR.splitlines()[0].endswith("and")


def test_the_universe_is_the_size_the_bound_says():
    """`1 + n + n(n-1)/2`, at most two cuts, which is three lines out of two."""
    text = "One thing, and another; a third: a fourth.\nthen it keeps on.\n"
    window, found = universe(text, "doc.md")
    positions = cut_positions(window)
    assert found["defect"] is None
    assert (
        len(found["candidates"])
        == 1 + len(positions) + len(positions) * (len(positions) - 1) // 2
    )
    assert max(len(cuts) for cuts in found["candidates"]) == 2


def test_a_window_offering_too_many_positions_leaves_the_sample():
    """Recorded with its position count rather than silently absent."""
    text = (
        "One thing, another thing, a third thing, a fourth thing, "
        "a fifth thing, a sixth thing, a seventh thing.\nthen it keeps on.\n"
    )
    window, found = universe(text, "doc.md")
    assert len(cut_positions(window)) > MAX_POSITIONS
    assert found["candidates"] == {}
    assert str(found["positions"]) in found["defect"]


def test_the_generator_offers_a_comma_without_judging_it():
    """A comma joining a compound object is offered, and the passes reject it.

    Asking the generator to decide would put the clause judgment back in the instrument,
    which is the thing this project leaves to a reader.
    """
    text = "It holds apples, pears and plums in one basket here.\nthen it keeps on.\n"
    window, _found = universe(text, "doc.md")
    assert 16 in cut_positions(window)
    assert text[:16].endswith("apples,")


def test_the_generator_never_reaches_the_shipped_repair(monkeypatch):
    """Nothing in the drawing path may read a suggestion.

    Patched to raise rather than to return a secret:
    the generator has no call site that could reach it,
    and a secret nobody could have produced proves nothing by being absent.
    """

    def refuse(*args, **kwargs):
        raise AssertionError("the generator read the shipped repair")

    monkeypatch.setattr(clf, "_fused_suggestion", refuse)
    _window, found = universe("Stop now! Go later.\nthen it keeps on.\n", "doc.md")
    assert found["defect"] is None
    assert found["candidates"]


def test_a_window_with_no_valid_split_offers_only_the_original():
    """A docstring opener cannot be repeated, and neither can a decorated block comment.

    This is the intended answer rather than a gap in the generator.
    The detector withholds its own suggestion on these as `prefix_other`.
    The third zero-tolerance condition exists to protect exactly this unit:
    one whose only acceptable repair is the original.
    """
    text = 'def f():\n    """Stop now! Go later.\n\n    More here.\n    """\n'
    window, found = universe(text, "x.py")
    valid = [cuts for cuts, c in found["candidates"].items() if candidate_is_valid(c)]
    assert valid == [original_cuts(window)]


# --- three verdicts per candidate become one set --------------------------


def a_pass(chosen, accept, universe_keys):
    accept = [tuple(key) for key in accept]
    return {
        "chosen": tuple(chosen),
        "accept": accept,
        "reject": [key for key in universe_keys if key not in accept],
    }


def synthetic(valid=True):
    """Two candidates, described by their validity rather than by any prose."""
    return {
        (): {"preserving": True, "carrier_valid": True, "intact": True},
        (9,): {"preserving": valid, "carrier_valid": True, "intact": True},
    }


def test_a_candidate_every_pass_accepted_is_acceptable():
    candidates = synthetic()
    keys = list(candidates)
    passes = [a_pass((), [(), (9,)], keys) for _ in range(3)]
    got = repair_resolution(passes, candidates)
    assert got["outcome"] == "settled"
    assert got["acceptable"] == frozenset({(), (9,)})


def test_a_candidate_every_pass_rejected_is_rejected():
    candidates = synthetic()
    keys = list(candidates)
    passes = [a_pass((), [()], keys) for _ in range(3)]
    got = repair_resolution(passes, candidates)
    assert got["outcome"] == "settled"
    assert got["acceptable"] == frozenset({()})
    assert got["rejected"] == frozenset({(9,)})


def test_a_candidate_the_passes_split_on_refers_the_whole_unit():
    """Two passes accepting {A, B} against one accepting {A} is a referral, not a vote.

    A disagreement about where a line may be cut is the same question a widening asks.
    """
    candidates = synthetic()
    keys = list(candidates)
    passes = [
        a_pass((), [(), (9,)], keys),
        a_pass((), [(), (9,)], keys),
        a_pass((), [()], keys),
    ]
    got = repair_resolution(passes, candidates)
    assert got["outcome"] == "adjudicated"
    assert got["referred"] == frozenset({(9,)})
    assert got["acceptable"] == frozenset({()})


def test_an_invalid_candidate_never_enters_the_set_however_many_accepted_it():
    candidates = synthetic(valid=False)
    keys = list(candidates)
    passes = [a_pass((), [(), (9,)], keys) for _ in range(3)]
    got = repair_resolution(passes, candidates)
    assert got["acceptable"] == frozenset({()})


def test_a_unit_whose_only_unanimous_candidate_is_invalid_is_adjudicated():
    candidates = {
        (): {"preserving": False, "carrier_valid": True, "intact": True},
        (9,): {"preserving": True, "carrier_valid": True, "intact": True},
    }
    keys = list(candidates)
    passes = [a_pass((), [()], keys) for _ in range(3)]
    got = repair_resolution(passes, candidates)
    assert got["outcome"] == "adjudicated"
    assert got["acceptable"] == frozenset()


def test_a_repair_the_generator_never_offered_refuses_the_unit():
    """The generator was wrong about the universe, and the set cannot be patched.

    Three-pass coverage of a universe is the only thing that makes a set complete,
    so a candidate added after the coverage failed has no coverage.
    """
    candidates = synthetic()
    keys = list(candidates)
    passes = [a_pass((), [(), (9,)], keys) for _ in range(2)]
    passes.append({"chosen": (4,), "accept": [(4,), ()], "reject": [(9,)]})
    got = repair_resolution(passes, candidates)
    assert got["outcome"] == "defect"
    assert got["invented"] == frozenset({(4,)})
    assert got["acceptable"] == frozenset()


def test_a_pass_that_did_not_answer_every_candidate_is_an_error():
    """Malformed is not an outcome.
    It is a record nobody can read.
    """
    candidates = synthetic()
    with pytest.raises(ValueError):
        repair_resolution([{"chosen": (), "accept": [()], "reject": []}], candidates)


def test_a_pass_reporting_a_missing_repair_still_answers_every_candidate():
    """Reporting one repair as absent does not excuse skipping the rest.

    `REPAIRING.md` asks for a verdict on every candidate, the unchanged one included,
    and a `missing` report is an addition to that rather than a replacement for it.
    Resolution short-circuited on `missing` before it checked,
    so a partial answer travelled all the way to the manifest schema.
    """
    candidates = synthetic()
    partial = {
        "chosen": None,
        "accept": [],
        "reject": [()],
        "missing": [["a line", "another line"]],
    }
    with pytest.raises(ValueError):
        repair_resolution([partial], candidates)


def test_a_pass_reporting_a_missing_repair_that_answered_them_all_is_a_defect():
    """The refusal still stands once the verdicts are complete."""
    candidates = synthetic()
    keys = list(candidates)
    complete = {
        "chosen": None,
        "accept": [],
        "reject": [tuple(key) for key in keys],
        "missing": [["a line", "another line"]],
    }
    got = repair_resolution([complete], candidates)
    assert got["outcome"] == "defect"


def test_a_pass_that_rejected_the_repair_it_would_make_is_an_error():
    candidates = synthetic()
    keys = list(candidates)
    broken = a_pass((), [(9,)], keys)
    broken["chosen"] = ()
    with pytest.raises(ValueError):
        repair_resolution([broken], candidates)


def test_a_pass_reporting_a_missing_repair_names_no_choice():
    """A pass with nothing acceptable to name has no choice to give.

    `REPAIRING.md` requires the chosen repair to be one the pass accepted,
    so a pass that accepted none of them names none,
    and the resolution reads `missing` before it ever reads a choice.
    """
    candidates = [{"id": "c00", "cuts": []}, {"id": "c01", "cuts": [9]}]
    supplied = [["one line,", "and its continuation."]]
    got = repair_pass_verdicts(
        {"accept": [], "reject": ["c00", "c01"], "missing": supplied}, candidates
    )
    assert got["chosen"] is None
    assert got["missing"] == supplied


def test_a_pass_naming_neither_a_choice_nor_a_missing_repair_is_an_error():
    """Malformed is not an outcome, and saying nothing about either is malformed."""
    candidates = [{"id": "c00", "cuts": []}]
    with pytest.raises(ValueError):
        repair_pass_verdicts(
            {"accept": ["c00"], "reject": [], "missing": []}, candidates
        )


def test_every_pass_omitting_a_valid_candidate_still_puts_it_to_them():
    """Agreement by omission is the failure the generated universe exists to prevent."""
    text = "One thing, and another thing entirely.\nthen it keeps on.\n"
    window, found = universe(text, "doc.md")
    keys = list(found["candidates"])
    omitted = (10,)
    assert omitted in keys
    assert candidate_is_valid(found["candidates"][omitted])
    passes = [
        a_pass(original_cuts(window), [original_cuts(window)], keys) for _ in range(3)
    ]
    got = repair_resolution(passes, found["candidates"])
    assert omitted in got["rejected"]
    assert omitted not in got["acceptable"]


# --- the ordering, enforced rather than asked for -------------------------


def test_nothing_may_enlarge_an_acceptable_set_after_a_machine_repair_is_read():
    """Promotion is the only place a repair algorithm is read, and it runs last."""
    unit = {}
    set_acceptable(unit, [(), (9,)])
    assert score_repair(unit, (9,)) is True
    assert score_repair(unit, (4,)) is False
    with pytest.raises(ScoringRefused):
        set_acceptable(unit, [(), (9,), (4,)])


def test_a_unit_with_no_acceptable_set_cannot_be_scored():
    with pytest.raises(ScoringRefused):
        score_repair({}, ())


def test_an_acceptable_set_may_be_written_until_it_is_read():
    unit = {}
    set_acceptable(unit, [()])
    set_acceptable(unit, [(), (9,)])
    assert unit["acceptable"] == frozenset({(), (9,)})


# --- the population, and the draw over it ---------------------------------
#
# The strata are exact class sets because they partition the population.
# Class membership overlaps.
# A top-up on one class raises another class's members' chance of selection,
# and a raw marginal over such a draw is biased.

from corpus_harness import (  # noqa: E402
    REPAIR_ADMISSION,
    draw_strata,
    exact_set_key,
    repair_admission_problems,
    repair_population,
    stratum_shortfalls,
    weighted_rate,
)

QUOTAS = {"per_set": 40, "floor": 26}


def synthetic_population(spec):
    """A population described by (stratum classes, count) pairs and nothing else."""
    made = []
    for classes, count in spec:
        key = exact_set_key(classes)
        for number in range(count):
            made.append(
                {
                    "id": f"{key or 'none'}-{number:04d}",
                    "stratum": key,
                    "withheld_by": list(classes),
                }
            )
    return made


def test_the_stratum_key_is_the_one_the_measurement_was_pinned_with():
    """`measured.json` carries these keys, and a table nobody can cross-check is not one."""
    for source_id, body in MEASURED.items():
        for key in body["exact_sets"]:
            assert exact_set_key(key.split(",") if key else []) == key, source_id


def test_a_line_carrying_two_boundaries_yields_two_units_at_one_window():
    """One walk position, two units, and two identities.

    A consumer looking a record up by line number alone lands on the wrong one.
    A line with two boundaries is the `many_boundaries` stratum by definition.
    """
    root = REPO / "tests" / "diagnostics" / "fixtures"
    units = repair_population(
        {"id": "styx", "selection_command": "git ls-files 'many_boundaries.md'"}, root
    )
    assert [unit["match"] for unit in units] == [0, 1]
    assert len({unit["index"] for unit in units}) == 1
    assert len({unit["id"] for unit in units}) == 2
    assert all(unit["stratum"] == "many_boundaries" for unit in units)


def test_a_unit_carries_the_raw_lines_its_window_can_be_rebuilt_from():
    root = REPO / "tests" / "diagnostics" / "fixtures"
    (unit,) = repair_population(
        {"id": "styx", "selection_command": "git ls-files 'period_boundary.md'"}, root
    )
    assert unit["window"]["raw"] == ["One sentence here. Another sentence follows."]
    assert unit["window"]["form"] == "one-line"
    assert unit["stratum"] == "terminator_period"
    assert unit["covariates"]["language"] == "markdown"


def test_the_drawing_path_never_reaches_the_shipped_repair(monkeypatch):
    """Nothing in the drawing path may read a suggestion.

    `repair_population` does call `diagnose`,
    so a secret planted in the suggestion would reach the sample if anything copied one.
    Asserted over the whole serialized sample, not over the fields expected to be clean.
    """
    secret = "sxJQ7pLeakCanary"
    monkeypatch.setattr(
        clf, "_fused_suggestion", lambda record, match: {"lines": [secret, secret]}
    )
    root = REPO / "tests" / "diagnostics" / "fixtures"
    population = repair_population(
        {"id": "styx", "selection_command": "git ls-files '*.md'"}, root
    )
    assert population
    drawn, strata = draw_strata(population, {"per_set": 40, "floor": 1}, "leak")
    assert drawn
    assert secret not in json.dumps({"units": drawn, "strata": strata})


def test_a_stratum_below_the_floor_is_drawn_at_zero_and_declared():
    """Not silently absent, and not drawn thin and quietly counted."""
    population = synthetic_population(
        [(["terminator_period"], 25), (["protected_span"], 40)]
    )
    drawn, strata = draw_strata(population, QUOTAS, "seed")
    assert strata["terminator_period"]["drawn"] == 0
    assert strata["terminator_period"]["reportable"] is False
    assert strata["terminator_period"]["population"] == 25
    assert {unit["stratum"] for unit in drawn} == {"protected_span"}


def test_a_class_with_a_large_marginal_can_still_be_unreportable():
    """The shape the measured population actually has.

    `terminator_period` carries thousands of units.
    Almost none of them are in the set it activates alone.
    A candidate is scored on the exact sets it activates, not on every unit carrying it,
    so a marginal that clears the floor says nothing about whether the draw can rate it.
    """
    population = synthetic_population(
        [
            (["terminator_period"], 20),
            (["terminator_period", "protected_span"], 60),
            (["terminator_period", "many_boundaries"], 60),
        ]
    )
    marginal = sum(
        1 for unit in population if "terminator_period" in unit["withheld_by"]
    )
    assert marginal == 140
    _drawn, strata = draw_strata(population, QUOTAS, "seed")
    assert strata["terminator_period"]["reportable"] is False
    problems = stratum_shortfalls(population, strata, QUOTAS)
    assert any(
        problem.startswith("terminator_period: holds 20") for problem in problems
    )


def test_the_draw_is_unchanged_when_the_class_declarations_are_reordered():
    """A stratum is a set, and a set has no order for a seed to depend on."""
    spec = [
        (["terminator_period", "protected_span"], 50),
        (["many_boundaries", "terminator_period"], 50),
    ]
    first, _strata = draw_strata(synthetic_population(spec), QUOTAS, "repairs-1")
    shuffled = synthetic_population(
        [(list(reversed(classes)), count) for classes, count in spec]
    )
    second, _again = draw_strata(shuffled, QUOTAS, "repairs-1")
    assert [unit["id"] for unit in first] == [unit["id"] for unit in second]


def test_the_draw_is_reproducible_from_its_seed_and_moves_with_it():
    population = synthetic_population([(["terminator_period"], 100)])
    once, _a = draw_strata(population, QUOTAS, "repairs-1")
    twice, _b = draw_strata(population, QUOTAS, "repairs-1")
    other, _c = draw_strata(population, QUOTAS, "repairs-2")
    assert [unit["id"] for unit in once] == [unit["id"] for unit in twice]
    assert [unit["id"] for unit in once] != [unit["id"] for unit in other]


def test_every_stratum_records_the_probability_a_unit_entered_by():
    population = synthetic_population([(["terminator_period"], 100)])
    _drawn, strata = draw_strata(population, QUOTAS, "seed")
    body = strata["terminator_period"]
    assert body["inclusion_probability"] == body["drawn"] / body["population"] == 0.4


def test_a_weighted_rate_differs_from_the_unweighted_one_it_replaces():
    """The reason the strata carry their population sizes at all.

    Two strata drawn to the same size out of very different populations.
    Pooling the drawn units counts the small stratum as heavily as the large one,
    and the population-weighted answer is the one that describes the population.
    """
    population = synthetic_population(
        [(["terminator_period"], 1000), (["protected_span"], 40)]
    )
    drawn, strata = draw_strata(population, QUOTAS, "seed")
    scored = [
        dict(unit, acceptable=unit["stratum"] == "terminator_period") for unit in drawn
    ]
    pooled = sum(unit["acceptable"] for unit in scored) / len(scored)
    weighted = weighted_rate(scored, strata, {"terminator_period", "protected_span"})
    assert pooled == 0.5
    assert round(weighted, 4) == round(1000 / 1040, 4)
    assert weighted != pooled


def test_the_weighted_rate_decides_nothing():
    """It is descriptive, and the admission gate never sees it.

    The gate is per stratum on its own Wilson bound.
    One interval over this mean would need a variance estimator nobody defined.
    """
    population = synthetic_population([(["terminator_period"], 100)])
    drawn, strata = draw_strata(population, QUOTAS, "seed")
    scored = [dict(unit, acceptable=True) for unit in drawn]
    assert weighted_rate(scored, strata, {"terminator_period"}) == 1.0
    refused = repair_admission_problems(
        {
            "class": "terminator_period",
            "algorithm": "a",
            "baseline_algorithm": "a",
            "zero_tolerance": dict.fromkeys(REPAIR_ADMISSION["zero_tolerance"], 0),
            "strata": {"terminator_period": {"scored": 40, "acceptable": 36}},
        }
    )
    assert refused, "a perfect weighted rate must not rescue a stratum below the floor"


def test_an_ambiguous_unit_leaves_the_weighted_rate():
    population = synthetic_population([(["terminator_period"], 100)])
    drawn, strata = draw_strata(population, QUOTAS, "seed")
    scored = [dict(unit, acceptable=False, ambiguous=True) for unit in drawn[:20]]
    scored += [dict(unit, acceptable=True) for unit in drawn[20:]]
    assert weighted_rate(scored, strata, {"terminator_period"}) == 1.0


def test_a_class_the_population_never_produced_is_a_line_rather_than_an_absence():
    """An empty class and a class nobody asked about look identical once omitted."""
    population = synthetic_population([(["terminator_period"], 40)])
    _drawn, strata = draw_strata(population, QUOTAS, "seed")
    problems = stratum_shortfalls(population, strata, QUOTAS)
    for name in clf.WITHHOLDING_CLASSES:
        if name != "terminator_period":
            assert any(problem.startswith(f"{name}: no unit") for problem in problems)


# --- the stimulus, and the batch a pass reads -----------------------------
#
# A pass must see what a repairing agent sees, minus the answer.
# Being precise about the "minus" is the point.
# What it is shown is `format_findings` output, not `deliver` output:
# `deliver` appends a suggested-replacement block for any finding carrying one.
# The elicited rates therefore describe agents given a blinded body,
# not agents given complete hook feedback.

import importlib.util  # noqa: E402
import subprocess  # noqa: E402

from corpus_harness import (  # noqa: E402
    REPAIR_BATCH,
    attach_candidates,
    file_digest,
    pass_answers,
    repair_batches,
    repair_stimulus,
)

FIXTURES = REPO / "tests" / "diagnostics" / "fixtures"
BATCH = REPO / "tests" / "corpus" / "repairs" / "batch.py"
DRAW = REPO / "tests" / "corpus" / "repairs" / "draw.py"


def fixture_units(pattern):
    """Units from the golden fixture tree, laid out so a checkout root sits above them."""
    return repair_population(
        {"id": "fixtures", "selection_command": f"git ls-files '{pattern}'"}, FIXTURES
    )


def test_the_stimulus_is_the_report_body_and_not_the_delivered_one():
    """`deliver` appends the suggestion, and this is the redaction that removes it."""
    text = "Stop now! Go later.\n"
    stimulus = repair_stimulus(text, "doc.md", 1)
    assert "[fused] line 1" in stimulus["body"]
    assert "Fix these in the block you just wrote" in stimulus["body"]
    assert "Go later." in stimulus["body"]
    # The line does carry a suggestion, and none of it reaches the body.
    (finding,) = clf.diagnose(text, "doc.md")
    assert "suggestion" in finding
    assert "suggested" not in stimulus["body"].lower()


def test_the_stimulus_says_line_n_rather_than_line_n_of_your_edit():
    """`snippet=False`, because a drawn unit is a file's line and not an edit's."""
    body = repair_stimulus("Stop now! Go later.\n", "doc.md", 1)["body"]
    assert "line 1:" in body
    assert "of your edit" not in body


def test_every_finding_on_the_anchor_line_reaches_the_stored_body():
    """A `wrap` travels with a blocking finding.
    The rejoin it invites is the repair this corpus measures.
    """
    long_line = "and it also runs on well past the advisory limit " * 3
    text = f"Stop now! Go later, {long_line}and\nthen it keeps running on.\n"
    stimulus = repair_stimulus(text, "doc.md", 1)
    assert stimulus["kinds"] == ["fused", "long", "wrap"]
    for kind in ("[fused]", "[wrap]", "[long]"):
        assert kind in stimulus["body"]


def test_the_stimulus_records_the_limit_it_was_rendered_under():
    """`format_findings` prints the number, so a changed limit changes the text."""
    stimulus = repair_stimulus("Stop now! Go later.\n", "doc.md", 1)
    assert str(stimulus["long_limit"]) in stimulus["body"]


def test_two_boundaries_on_one_line_share_one_body():
    """A host sends the line's findings, not one of them."""
    units = fixture_units("many_boundaries.md")
    assert len(units) == 2
    assert units[0]["stimulus"] == units[1]["stimulus"]
    assert units[0]["stimulus"]["body"].count("[fused]") == 2


def test_a_batch_is_reproducible_after_the_checkout_is_gone(tmp_path):
    """Everything a pass reads comes from the sample and from two files in this repo."""
    sample = tmp_path / "sample.json"
    units = attach_candidates(fixture_units("*.md"), FIXTURES.parent)
    sample.write_text(
        json.dumps(
            {
                "units": units,
                "stimulus_digests": {
                    "skill": file_digest(
                        REPO / "skills" / "semantic-linefeeds" / "SKILL.md"
                    ),
                    "repairing": file_digest(
                        REPO / "tests" / "corpus" / "repairs" / "REPAIRING.md"
                    ),
                    "renderer": file_digest(REPO / "scripts" / "check_linefeeds.py"),
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    first, second = tmp_path / "a", tmp_path / "b"
    for out in (first, second):
        done = subprocess.run(
            [
                sys.executable,
                str(BATCH),
                "claude",
                "--sample",
                str(sample),
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert done.returncode == 0, done.stderr
    names = sorted(path.name for path in first.iterdir())
    assert names
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_a_batch_refuses_when_the_rule_it_was_drawn_under_has_moved(tmp_path):
    """A round whose stimulus changed halfway through measures two stimuli."""
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "units": [],
                "stimulus_digests": {
                    "skill": "sha256:" + "0" * 64,
                    "repairing": "sha256:" + "0" * 64,
                    "renderer": "sha256:" + "0" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    done = subprocess.run(
        [
            sys.executable,
            str(BATCH),
            "claude",
            "--sample",
            str(sample),
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode != 0
    for name in ("skill", "repairing", "renderer"):
        assert name in done.stderr
    assert "nothing was laid out" in done.stderr


def test_a_batch_shows_no_suggestion_no_class_name_and_no_original_marker(tmp_path):
    """Three redactions, and the third is the one that is easy to forget.

    Changing nothing is one candidate among the others.
    A flag on it is a flag the undecided reach for.
    """
    units = attach_candidates(fixture_units("*.md"), FIXTURES.parent)
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "units": units,
                "stimulus_digests": {
                    "skill": file_digest(
                        REPO / "skills" / "semantic-linefeeds" / "SKILL.md"
                    ),
                    "repairing": file_digest(
                        REPO / "tests" / "corpus" / "repairs" / "REPAIRING.md"
                    ),
                    "renderer": file_digest(REPO / "scripts" / "check_linefeeds.py"),
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    done = subprocess.run(
        [
            sys.executable,
            str(BATCH),
            "claude",
            "--sample",
            str(sample),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(out.iterdir())
    )
    assert rendered
    # A unit's path is data the batch echoes rather than a label it chose,
    # and these fixtures are named after the classes they exercise,
    # so the paths come out before the class names are looked for.
    composed = rendered
    for unit in units:
        composed = composed.replace(unit["path"], "<path>")
    assert "<path>" in composed
    for name in clf.WITHHOLDING_CLASSES:
        assert name not in composed
    for field in ("original_cut", "preserving", "carrier_valid", "withheld_by"):
        assert field not in rendered


def test_a_pass_reads_its_units_in_an_order_of_its_own():
    """The same reason `labeling_batches` randomizes: drift must not line up."""
    sample = [{"id": f"u-{number:03d}"} for number in range(40)]
    one = [unit["id"] for batch in repair_batches(sample, "claude") for unit in batch]
    two = [unit["id"] for batch in repair_batches(sample, "codex") for unit in batch]
    again = [unit["id"] for batch in repair_batches(sample, "claude") for unit in batch]
    assert sorted(one) == sorted(two) == [unit["id"] for unit in sample]
    assert one != two
    assert one == again


def test_a_batch_holds_no_more_units_than_a_sitting():
    sample = [{"id": f"u-{number:03d}"} for number in range(40)]
    batches = repair_batches(sample, "claude")
    assert max(len(batch) for batch in batches) <= REPAIR_BATCH
    assert sum(len(batch) for batch in batches) == 40


# --- collect, adjudicate, promote -----------------------------------------
#
# Promotion is the only place a repair algorithm is read, and it runs last.

COLLECT = REPO / "tests" / "corpus" / "repairs" / "collect.py"
ADJUDICATE = REPO / "tests" / "corpus" / "repairs" / "adjudicate.py"
PROMOTE = REPO / "tests" / "corpus" / "repairs" / "promote.py"

PASSES = ("claude", "codex", "agy")


def round_dir(tmp_path, pattern="suggestion_*.md"):
    """A whole round on disk: a sample, and a place for the answers to land."""
    repairs = tmp_path / "repairs"
    repairs.mkdir()
    units = attach_candidates(fixture_units(pattern), FIXTURES.parent)
    assert units
    (repairs / "sample.json").write_text(
        json.dumps({"units": units}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    answers = tmp_path / "answers"
    answers.mkdir()
    return repairs, answers, units


def answer_all(
    answers, units, choose, accept=None, missing=None, names=PASSES, unanswered=None
):
    """Write one `.out` per pass, each answering every unit the same way.

    The shapes here are the ones a real pass produces, not tidier ones.
    A pass reporting a repair the list never offered names no choice:
    `REPAIRING.md` requires the chosen repair to be one the pass accepted,
    and a pass that accepted none of them has none to name.
    A fixture that always wrote a `choose` could not reach that shape,
    and a shape no fixture reaches is a shape no test guards.

    `unanswered` names candidates to leave out of both verdict lists,
    for the partial answer that is malformed rather than merely refusing.
    """
    for name in names:
        payload = []
        for unit in units:
            shown = [candidate["id"] for candidate in unit["candidates"]]
            absent = set(unanswered(unit) if unanswered else ())
            ruled = [one for one in shown if one not in absent]
            refused = missing(unit) if missing else []
            taken = [] if refused else (accept(unit) if accept else [choose(unit)])
            answer = {
                "id": unit["id"],
                "accept": [one for one in ruled if one in taken],
                "reject": [one for one in ruled if one not in taken],
                "missing": refused,
            }
            if not refused:
                answer["choose"] = choose(unit)
            payload.append(answer)
        (answers / f"{name}-01.out").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )


def original_id(unit):
    """The candidate that leaves the window as it is, which a pass is never told."""
    (found,) = [
        candidate["id"]
        for candidate in unit["candidates"]
        if candidate["cuts"] == unit["original_cut"]
    ]
    return found


def run(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
    )


def test_a_unanimous_round_settles_and_reports_per_stratum(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    answer_all(answers, units, original_id)
    done = run(COLLECT, repairs, answers)
    assert done.returncode == 0, done.stderr
    assert "per stratum" in done.stdout
    assert "candidates offered" in done.stdout
    assert f"{len(units)} of {len(units)} units settled" in done.stdout


def test_the_damage_counts_are_headlines_rather_than_footnotes(tmp_path):
    """The rate at which a competent agent breaks a line while repairing it."""
    repairs, answers, units = round_dir(tmp_path, "docstring_prefix.py")
    answer_all(answers, units, original_id)
    done = run(COLLECT, repairs, answers)
    assert done.returncode == 0, done.stderr
    assert "carrier invalid" in done.stdout
    invalid = sum(
        1
        for unit in units
        for candidate in unit["candidates"]
        if not candidate["carrier_valid"]
    )
    assert invalid
    assert f"carrier invalid  {invalid}" in done.stdout.replace("   ", "  ")


def test_a_split_referral_reaches_the_worksheet_grouped_by_its_shape(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    everything = [candidate["id"] for candidate in units[0]["candidates"]]
    answer_all(
        answers,
        units,
        original_id,
        accept=lambda u: everything,
        names=("claude", "codex"),
    )
    answer_all(answers, units, original_id, names=("agy",))
    assert run(ADJUDICATE, "worksheet", repairs, answers).returncode == 0
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    assert entries
    assert {entry["shape"] for entry in entries} == {"split"}
    assert all(entry["referred"] for entry in entries)
    assert all(entry["outcome"] is None for entry in entries)


def test_a_decision_names_candidates_the_way_the_worksheet_asks_for_them(tmp_path):
    """The worksheet asks for candidate ids, so resolution has to read candidate ids.

    A decision that survives the form but not its reader is a decision silently lost,
    and the loss surfaces as a unit that scores wrong rather than as an error.
    """
    # `tests/corpus/collect.py` shadows this one by name, so load it by path.
    spec = importlib.util.spec_from_file_location("repairs_collect", COLLECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolved = module.resolved

    repairs, answers, units = round_dir(tmp_path)
    everything = [candidate["id"] for candidate in units[0]["candidates"]]
    answer_all(
        answers, units, original_id, accept=lambda u: everything, names=("claude",)
    )
    answer_all(answers, units, original_id, names=("codex", "agy"))
    run(ADJUDICATE, "worksheet", repairs, answers)
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    assert entries
    for entry in entries:
        entry["outcome"] = "settled"
        entry["acceptable"] = [entry["candidates"][0]["id"]]
        entry["reason"] = "the original is the only correct answer here"
    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    by_id = {unit["id"]: unit for unit in sample["units"]}
    decisions = {entry["id"]: entry for entry in entries}
    outcomes, _names = resolved(sample, answers, decisions)

    entry = entries[0]
    named = entry["acceptable"][0]
    cuts = next(
        candidate["cuts"]
        for candidate in by_id[entry["id"]]["candidates"]
        if candidate["id"] == named
    )
    assert outcomes[entry["id"]]["outcome"] == "settled"
    assert outcomes[entry["id"]]["acceptable"] == frozenset({tuple(cuts)})


def test_a_unit_no_candidate_could_repair_leaves_the_rate_once_decided(tmp_path):
    """A refused unit still has to stop being pending, or nothing can ever promote.

    Its acceptable set cannot be completed —
    three-pass coverage of a universe is what makes a set complete,
    and a candidate supplied after that coverage failed has none.
    So the maintainer's decision moves it out of the rate rather than into one,
    and `ambiguous` is the outcome that says so.
    """
    spec = importlib.util.spec_from_file_location("repairs_collect", COLLECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    repairs, answers, units = round_dir(tmp_path)
    answer_all(
        answers, units, original_id, missing=lambda u: [["a line", "another line"]]
    )
    run(ADJUDICATE, "worksheet", repairs, answers)
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    assert {entry["shape"] for entry in entries} == {"missing"}
    for entry in entries:
        entry["outcome"] = "ambiguous"
        entry["supplied"] = [["a line", "another line"]]
        entry["reason"] = "no candidate in the universe is a correct repair"
    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    decisions = {entry["id"]: entry for entry in entries}
    outcomes, _names = module.resolved(sample, answers, decisions)

    got = outcomes[entries[0]["id"]]
    assert got["outcome"] == "ambiguous"
    assert got["acceptable"] == frozenset()
    # Nothing may stay pending, or `promote.py` refuses the round forever.
    assert not [
        uid
        for uid, one in outcomes.items()
        if one["outcome"] in ("adjudicated", "defect")
    ]


def test_a_unit_no_candidate_could_repair_cannot_be_settled(tmp_path):
    """Settled means somebody named the correct answers, and here nobody can."""
    spec = importlib.util.spec_from_file_location("repairs_collect", COLLECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    repairs, answers, units = round_dir(tmp_path)
    answer_all(
        answers, units, original_id, missing=lambda u: [["a line", "another line"]]
    )
    run(ADJUDICATE, "worksheet", repairs, answers)
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    for entry in entries:
        entry["outcome"] = "settled"
        entry["supplied"] = [["a line", "another line"]]
        entry["reason"] = "supplied by hand"
    sample = json.loads((repairs / "sample.json").read_text(encoding="utf-8"))
    decisions = {entry["id"]: entry for entry in entries}
    outcomes, _names = module.resolved(sample, answers, decisions)
    assert outcomes[entries[0]["id"]]["outcome"] == "error"


def test_a_repair_the_generator_missed_is_its_own_shape(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    answer_all(
        answers, units, original_id, missing=lambda u: [["a line", "another line"]]
    )
    assert run(ADJUDICATE, "worksheet", repairs, answers).returncode == 0
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    assert {entry["shape"] for entry in entries} == {"missing"}


def test_a_decision_without_a_reason_is_refused(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    answer_all(
        answers,
        units,
        original_id,
        accept=lambda u: [candidate["id"] for candidate in u["candidates"]],
        names=("claude",),
    )
    answer_all(answers, units, original_id, names=("codex", "agy"))
    run(ADJUDICATE, "worksheet", repairs, answers)
    assert run(ADJUDICATE, "check", repairs, answers).returncode == 1
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    for entry in entries:
        entry["outcome"] = "settled"
        entry["acceptable"] = [entry["candidates"][0]["id"]]
    (repairs / "adjudications.json").write_text(json.dumps(entries), encoding="utf-8")
    done = run(ADJUDICATE, "check", repairs, answers)
    assert done.returncode == 1
    assert "no reason recorded" in done.stdout
    for entry in entries:
        entry["reason"] = "the second break severs a clause"
    (repairs / "adjudications.json").write_text(json.dumps(entries), encoding="utf-8")
    assert run(ADJUDICATE, "check", repairs, answers).returncode == 0


def test_a_round_carrying_every_referral_shape_reaches_the_manifest(tmp_path):
    """The whole chain, on the shapes a real round actually produces.

    Each stage of this pipeline had a test and the composition had none,
    so four readers ignored the form their own writer fills in,
    and every one of them was reachable only through a shape the fixtures could not build:
    a pass refusing a unit without naming a choice,
    a decision naming candidates by the id the worksheet asks for,
    and a decision on a unit no candidate could repair.
    A round that cannot be promoted is the only symptom they share,
    so promotion is what this asserts.
    """
    repairs, answers, units = round_dir(tmp_path, "suggestion_*.md")
    refused = units[0]["id"]
    everything = [candidate["id"] for candidate in units[0]["candidates"]]

    # One pass splits from the others, and every pass refuses the first unit.
    def taken(unit):
        return everything if unit["id"] != refused else []

    def absent(unit):
        return (
            [["a line the generator never offered", "and its continuation"]]
            if (unit["id"] == refused)
            else []
        )

    answer_all(answers, units, original_id, missing=absent, names=("claude",))
    answer_all(
        answers,
        units,
        original_id,
        accept=taken,
        missing=absent,
        names=("codex", "agy"),
    )
    assert run(COLLECT, repairs, answers).returncode == 0

    assert run(ADJUDICATE, "worksheet", repairs, answers).returncode == 0
    entries = json.loads((repairs / "adjudications.json").read_text(encoding="utf-8"))
    shapes = {entry["id"]: entry["shape"] for entry in entries}
    assert shapes[refused] == "missing"
    assert set(shapes.values()) >= {"missing", "split"}

    for entry in entries:
        entry["reason"] = "decided by the test"
        if entry["shape"] == "missing":
            # Its acceptable set cannot be completed, so it leaves the rate.
            entry["outcome"] = "ambiguous"
            entry["supplied"] = [["a line the generator never offered", "and more"]]
        else:
            # Named by id, which is what the worksheet asks a maintainer for.
            entry["outcome"] = "settled"
            entry["acceptable"] = [entry["candidates"][0]["id"]]
    (repairs / "adjudications.json").write_text(json.dumps(entries), encoding="utf-8")
    assert run(ADJUDICATE, "check", repairs, answers).returncode == 0

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    done = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert done.returncode == 0, done.stdout + done.stderr

    records = json.loads(manifest.read_text(encoding="utf-8"))["repairs"]
    assert len(records) == len(units)
    outcomes = {record["id"]: record["outcome"] for record in records}
    assert outcomes[refused] == "ambiguous"
    assert set(outcomes.values()) == {"ambiguous", "settled"}
    # A decision named by id has to arrive as the cuts it stands for,
    # or the acceptable set is empty and nothing it protects is scored.
    settled = [r for r in records if r["outcome"] == "settled"]
    assert settled and all(r["acceptable"] for r in settled)
    for record in records:
        assert record["baseline_suggestion"]["predicate"] == file_digest(
            REPO / "scripts" / "check_linefeeds.py"
        )
        assert record["passes"], record["id"]
    # A refused unit records what the repair should have been,
    # and carries no acceptable set, because it has none to carry.
    refusal = next(r for r in records if r["id"] == refused)
    assert refusal["acceptable"] == []


def promoted(tmp_path, pattern="suggestion_*.md"):
    repairs, answers, units = round_dir(tmp_path, pattern)
    answer_all(answers, units, original_id)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    done = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    return done, manifest, repairs, answers, units


def test_promotion_records_what_the_shipped_predicate_did(tmp_path):
    done, manifest, _repairs, _answers, units = promoted(tmp_path)
    assert done.returncode == 0, done.stderr
    records = json.loads(manifest.read_text(encoding="utf-8"))["repairs"]
    assert len(records) == len(units)
    for record in records:
        baseline = record["baseline_suggestion"]
        assert baseline["predicate"] == file_digest(
            REPO / "scripts" / "check_linefeeds.py"
        )
        assert baseline["lines"], record["id"]
        assert baseline["preserving"] and baseline["carrier_valid"]
        # The passes accepted only the unchanged window, and the shipped repair splits.
        assert baseline["acceptable"] is False


def test_promotion_refuses_a_referral_nobody_decided(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    answer_all(
        answers,
        units,
        original_id,
        accept=lambda u: [candidate["id"] for candidate in u["candidates"]],
        names=("claude",),
    )
    answer_all(answers, units, original_id, names=("codex", "agy"))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    done = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert done.returncode != 0
    assert "undecided" in done.stderr
    assert "nothing was promoted" in done.stderr
    assert "repairs" not in json.loads(manifest.read_text(encoding="utf-8"))


def test_promotion_refuses_when_no_unit_was_answered_by_every_pass(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    done = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert done.returncode != 0
    assert "nothing was promoted" in done.stderr


def test_promotion_refuses_to_rewrite_a_round_under_another_predicate(tmp_path):
    """A later predicate cannot rewrite what this round recorded.

    The record is a historical fact about the predicate that produced it,
    and a replay under a different one would break the identity it was written for.
    """
    done, manifest, repairs, answers, _units = promoted(tmp_path)
    assert done.returncode == 0, done.stderr
    document = json.loads(manifest.read_text(encoding="utf-8"))
    for record in document["repairs"]:
        record["baseline_suggestion"]["predicate"] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps(document), encoding="utf-8")
    again = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert again.returncode != 0
    assert "a different predicate" in again.stderr
    assert "nothing was promoted" in again.stderr
    # And it did not rewrite what it refused.
    assert json.loads(manifest.read_text(encoding="utf-8")) == document


def test_replaying_promotion_reproduces_the_same_manifest(tmp_path):
    done, manifest, repairs, answers, _units = promoted(tmp_path)
    assert done.returncode == 0, done.stderr
    first = manifest.read_text(encoding="utf-8")
    again = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert again.returncode == 0, again.stderr
    assert manifest.read_text(encoding="utf-8") == first


def test_a_pass_naming_a_candidate_it_was_never_shown_is_an_error(tmp_path):
    repairs, answers, units = round_dir(tmp_path)
    answer_all(answers, units, lambda unit: "c99")
    done = run(COLLECT, repairs, answers)
    assert done.returncode == 0, done.stderr
    assert "error" in done.stdout


# --- the manifest section, and the validator over it ----------------------
#
# The repair records live in the same manifest as the label records.
# One manifest, one lock, one digest to repin:
# splitting them would let one move without the other noticing.

from corpus_harness import (  # noqa: E402
    REPAIR_FIELDS,
    manifest_problems,
    repair_floor_problems,
    repair_problems,
)


def repair_record(**overrides):
    """One promoted repair, complete enough that the validator has no complaint."""
    record = {
        "id": "styx:internal/buffer.go:12:0#repair",
        "source": "styx",
        "frame": "main",
        "path": "internal/buffer.go",
        "line": 12,
        "match": 0,
        "index": 3,
        "lines": [12, 13],
        "window": {
            "form": "two-line",
            "raw": ["// One sentence here. Another follows.", "// and it goes on."],
            "prose": "One sentence here. Another follows. and it goes on.",
            "leaders": ["// ", "// "],
            "tails": ["", ""],
            "breaks": [35],
        },
        "withheld_by": ["terminator_period"],
        "stratum": {
            "set": "terminator_period",
            "population": 3851,
            "drawn": 40,
            "inclusion_probability": 0.0104,
            "reportable": True,
        },
        "covariates": {"co_wrap": True, "language": "go"},
        "stimulus": {"body": "semantic-linefeeds: 1 issue(s)", "kinds": ["fused"]},
        "candidates": [
            {
                "id": "c00",
                "cuts": [],
                "breaks": [],
                "lines": ["// One sentence here. Another follows. and it goes on."],
                "preserving": True,
                "carrier_valid": True,
                "intact": True,
            },
            {
                "id": "c01",
                "cuts": [18],
                "breaks": [18],
                "lines": [
                    "// One sentence here.",
                    "// Another follows. and it goes on.",
                ],
                "preserving": True,
                "carrier_valid": True,
                "intact": True,
            },
        ],
        "passes": {
            name: {"choose": "c01", "accept": ["c01"], "reject": ["c00"], "missing": []}
            for name in ("agy", "claude", "codex")
        },
        "outcome": "settled",
        "acceptable": ["c01"],
        "baseline_suggestion": {
            "lines": ["// One sentence here.", "// Another follows. and it goes on."],
            "breaks": [18],
            "candidate": "c01",
            "acceptable": True,
            "preserving": True,
            "carrier_valid": True,
            "intact": True,
            "predicate": "sha256:" + "1" * 64,
        },
    }
    record.update(overrides)
    return record


def test_a_complete_repair_record_draws_no_complaint():
    assert repair_problems(repair_record()) == []


@pytest.mark.parametrize("field", REPAIR_FIELDS)
def test_a_repair_record_missing_a_field_is_rejected(field):
    """A field that may go missing is a field no reader can rely on."""
    thin = repair_record()
    del thin[field]
    assert any(field in problem for problem in repair_problems(thin))


def test_a_settled_unit_with_an_empty_acceptable_set_is_rejected():
    """Settled means somebody said what the right answers are."""
    problems = repair_problems(repair_record(acceptable=[]))
    assert any("empty acceptable set" in problem for problem in problems)


def test_an_ambiguous_unit_carries_no_acceptable_repair():
    """An ambiguous unit leaves the rate rather than carrying one."""
    problems = repair_problems(repair_record(outcome="ambiguous"))
    assert any("leaves the rate" in problem for problem in problems)


def test_an_acceptable_candidate_that_is_not_valid_is_rejected():
    """A repair that loses a word is not a variant of the right answer."""
    broken = repair_record()
    broken["candidates"][1]["preserving"] = False
    problems = repair_problems(broken)
    assert any("not valid on all three flags" in problem for problem in problems)


def test_an_acceptable_name_that_is_not_a_candidate_is_rejected():
    problems = repair_problems(repair_record(acceptable=["c99"]))
    assert any("not a candidate" in problem for problem in problems)


def test_a_pass_that_did_not_answer_every_candidate_is_rejected():
    """The universe is what makes a set complete, so a partial answer covers nothing."""
    partial = repair_record()
    partial["passes"]["agy"] = {
        "choose": "c01",
        "accept": ["c01"],
        "reject": [],
        "missing": [],
    }
    problems = repair_problems(partial)
    assert any("answered 1 of 2 candidates" in problem for problem in problems)


def test_a_pass_that_both_accepted_and_rejected_a_candidate_is_rejected():
    doubled = repair_record()
    doubled["passes"]["agy"]["reject"] = ["c00", "c01"]
    problems = repair_problems(doubled)
    assert any("both accepted and rejected" in problem for problem in problems)


def test_a_class_the_detector_does_not_declare_is_rejected():
    """A stratum named after a class nobody declares cannot be drawn again."""
    problems = repair_problems(repair_record(withheld_by=["terminator_semicolon"]))
    assert any("does not declare" in problem for problem in problems)


def test_a_stratum_that_is_not_the_exact_set_of_its_classes_is_rejected():
    """The strata partition the population, and a mislabelled one breaks the partition."""
    crossed = repair_record()
    crossed["stratum"]["set"] = "protected_span"
    problems = repair_problems(crossed)
    assert any("not the exact set" in problem for problem in problems)


def test_a_stratum_with_no_inclusion_probability_is_rejected():
    """Nothing it contributes to can be weighted without one."""
    unweighted = repair_record()
    del unweighted["stratum"]["inclusion_probability"]
    problems = repair_problems(unweighted)
    assert any("inclusion probability" in problem for problem in problems)


def test_a_baseline_produced_by_another_predicate_is_rejected():
    """What the shipped repair did is a historical fact about the predicate that did it."""
    problems = repair_problems(repair_record(), predicate="sha256:" + "2" * 64)
    assert any("predicate in the tree" in problem for problem in problems)
    assert repair_problems(repair_record(), predicate="sha256:" + "1" * 64) == []


def test_a_repair_floor_for_a_round_nobody_declared_is_rejected():
    """A floor for a round nobody drew is a prediction nothing will ever answer."""
    document = {
        "sources": [{"id": "styx", "side": "holdout", "round": 4}],
        "reporting": {"repair_floors": {"4": {}, "9": {}}},
    }
    problems = repair_floor_problems(document)
    assert len(problems) == 1
    assert "round 9" in problems[0]


def test_the_repairs_section_is_required_whether_or_not_it_holds_a_round():
    """A reader must be able to tell an empty corpus from a section nobody wrote.

    The section held nothing until a round was promoted into it,
    so what is asserted is that it is present and readable,
    not how many records a given round happened to leave there.
    """
    document = json.loads(
        (REPO / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    assert isinstance(document["repairs"], list)
    assert manifest_problems(document) == []
    del document["repairs"]
    assert any("repairs" in problem for problem in manifest_problems(document))
    assert manifest_problems(dict(document, repairs=[])) == []


def test_a_broken_repair_record_reaches_the_manifest_gate():
    """The validator joins `manifest_problems` rather than standing beside it."""
    document = json.loads(
        (REPO / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    document["repairs"] = [repair_record(acceptable=[])]
    assert any(
        "empty acceptable set" in problem for problem in manifest_problems(document)
    )


def test_the_manifest_states_what_round_four_must_be_before_it_is_drawn():
    """Stating it now is what stops any of it being chosen once the round is in hand.

    A requirement written after a round exists is one the round satisfies by existing.
    """
    document = json.loads(
        (REPO / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    (note,) = [
        line for line in document["protocol_notes"] if line.startswith("the round that")
    ]
    declared = {source["id"] for source in document["sources"]}
    assert len(declared) == 12
    for phrase in (
        "round 4",
        "none of the twelve",
        "did not tune that predicate",
        "qualify.py",
    ):
        assert phrase in note
    assert "no class is admissible" in note.lower()


def test_promotion_refuses_to_leave_the_lock_disagreeing_with_the_manifest(tmp_path):
    """The lock is a digest of the manifest, and promoting rewrites the manifest.

    Refused before the write rather than after it.
    The write is the expensive part of a round.
    A refusal arriving afterwards arrives at the end of hours of elicitation.
    """
    repairs, answers, units = round_dir(tmp_path)
    answer_all(answers, units, original_id)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    lock = tmp_path / "manifest.lock"
    lock.write_text(json.dumps({"digest": "sha256:" + "0" * 64, "reason": "before"}))

    done = run(PROMOTE, repairs, answers, FIXTURES.parent, "--manifest", manifest)
    assert done.returncode != 0
    assert "--reason" in done.stderr
    assert "Nothing was promoted" in done.stderr
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"schema_version": 1}

    done = run(
        PROMOTE,
        repairs,
        answers,
        FIXTURES.parent,
        "--manifest",
        manifest,
        "--reason",
        "the repair round was promoted, and no label changes",
    )
    assert done.returncode == 0, done.stderr
    repinned = json.loads(lock.read_text(encoding="utf-8"))
    assert repinned["digest"] == file_digest(manifest)
    assert "repair round" in repinned["reason"]


def test_a_pass_that_restates_its_template_is_still_read(tmp_path):
    """The longest array of objects carrying an id is the answer.

    A pass often echoes the shape it was given before writing its own,
    and one regex spanning from the first `[` to the last `]` parses as neither.
    """
    out = tmp_path / "claude-01.out"
    out.write_text(
        'Sure.\n```json\n[{"id": "<unit id>", "choose": "<candidate>"}]\n```\n'
        'Here they are:\n[{"id": "a", "choose": "c00"}, {"id": "b", "choose": "c01"}]\n',
        encoding="utf-8",
    )
    assert [answer["id"] for answer in pass_answers(out)] == ["a", "b"]


def test_an_answer_that_is_not_a_list_of_units_is_read_as_nothing(tmp_path):
    out = tmp_path / "claude-01.out"
    out.write_text('["a", "b"]\nI could not answer.', encoding="utf-8")
    assert pass_answers(out) == []


def test_a_window_the_generator_refused_never_reaches_a_pass():
    """It leaves the sample carrying its position count, and is not put to anyone.

    Sixty of the round's 368 units are refused this way,
    every one of them for offering more cut positions than a pass can judge.
    """
    sample = json.loads(
        (REPO / "tests" / "corpus" / "repairs" / "sample.json").read_text(
            encoding="utf-8"
        )
    )
    refused = [unit for unit in sample["units"] if unit.get("defect")]
    assert refused
    for unit in refused:
        assert unit["candidates"] == []
        assert unit["positions"] > MAX_POSITIONS
        assert str(unit["positions"]) in unit["defect"]


def test_a_list_item_split_carries_a_continuation_rather_than_a_second_marker():
    """Two lines both opening `4. ` are two list items, not one item on two lines.

    Found by putting the round in front of real agents:
    on the first batch each of them saw,
    two of the three model families reported the correct repair as one nobody offered.
    """
    text = "4. One thing here. Another thing here.\n   and it continues on.\n"
    window, found = universe(text, "doc.md")
    # A candidate that splits the anchor, not merely one that differs from the original:
    # the full rejoin also differs, and it needs no continuation at all.
    anchor_cut = original_cuts(window)[0]
    split = [
        candidate["lines"]
        for cuts, candidate in found["candidates"].items()
        if candidate_is_valid(candidate) and any(cut < anchor_cut for cut in cuts)
    ]
    assert split, "a list item with a continuation has a split it can express"
    for lines in split:
        assert lines[0].startswith("4. ")
        for line in lines[1:]:
            assert not line.startswith("4. "), lines
        assert lines[1].startswith("   "), lines


def test_the_continuation_is_the_one_the_window_shows():
    """Markdown allows an indent or nothing at all, and the file has already chosen.

    Copying the file's own answer keeps that choice out of the generator.
    """
    indented = window_at("- One thing here. Another.\n  and it goes on.\n", "doc.md")
    assert continuation_leader(indented, 0) == "  "
    lazy = window_at("* One thing here. Another.\nand it goes on lazily.\n", "doc.md")
    assert continuation_leader(lazy, 0) == ""


def test_a_list_window_with_nothing_below_falls_back_to_the_marker_width():
    alone = window_at("- One thing here. Another thing here.\n", "doc.md")
    assert alone.form == "one-line"
    assert continuation_leader(alone, 0) == "  "
    numbered = window_at("10. One thing here. Another thing here.\n", "doc.md")
    assert continuation_leader(numbered, 0) == "    "


def test_two_list_items_are_two_paragraphs_so_a_window_never_spans_them():
    """The extractor already separates siblings, so no window holds two items."""
    text = "- One thing here. Another thing here.\n- a second item entirely.\n"
    records, _suppressions = clf.judged_lines(text, "doc.md")
    assert [record["leader"] for record in records] == ["- ", "- "]
    assert records[0]["paragraph"] != records[1]["paragraph"]
    assert repair_window(records, 0).form == "one-line"


def test_a_sibling_item_below_is_not_copied_from():
    """Constructed, because the extractor never puts two items in one window.

    The rule still has to say what it would do.
    A leader copied from a sibling would open a third item rather than continue the first.
    """
    window = window_at("- One thing here. Another thing here.\n", "doc.md")
    sibling = window._replace(
        records=(
            window.records[0],
            clf._judged_record(
                "", [0, 0, 0], 2, "- a second item.", "a second item.", "", None, 0
            ),
        )
    )
    assert sibling.records[1]["leader"] == "- "
    assert continuation_leader(sibling, 0) == "  "


def test_every_other_leader_still_repeats_byte_for_byte():
    """The rule changed for list markers and for nothing else."""
    for text, path in (
        ("> One thing here. Another thing here.\n> and it goes on.\n", "doc.md"),
        ("// One thing here. Another thing here.\n// and it goes on.\n", "x.go"),
        ("    One thing here. Another thing here.\n    and it goes on.\n", "doc.md"),
    ):
        records, _suppressions = clf.judged_lines(text, path)
        if not records:
            continue
        window = repair_window(records, 0)
        assert continuation_leader(window, 0) == window.records[0]["leader"], text
