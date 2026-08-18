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
    cut_positions,
    original_cuts,
    repair_candidates,
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


def test_a_pass_that_rejected_the_repair_it_would_make_is_an_error():
    candidates = synthetic()
    keys = list(candidates)
    broken = a_pass((), [(9,)], keys)
    broken["chosen"] = ()
    with pytest.raises(ValueError):
        repair_resolution([broken], candidates)


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
