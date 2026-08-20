"""What the corpus is allowed to say, and what it must refuse to say.

A rate is a claim about material the corpus has not seen.
The reporting rules were fixed before any rate existed,
so a level that cannot support a claim prints its counts and stops.

The floors are the other half.
A rate nobody records is a number, not a gate:
it drifts down one detection at a time and no run ever fails.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import (  # noqa: E402
    KINDS,
    REPAIR_ADMISSION,
    REPORTED_STRATA,
    REPORTING,
    floor_problems,
    recall,
    repair_admission_problems,
    wilson,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO / "tests" / "corpus" / "manifest.json"


def on_disk():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def units(kind, detected, missed, false_=0, ambiguous=0, **covariates):
    """A synthetic level, described by its counts rather than by its prose."""
    made = []
    for label, expected, count in (
        ("true", "detected", detected),
        ("true", "accepted_miss", missed),
        ("false", None, false_),
        ("ambiguous", None, ambiguous),
    ):
        for i in range(count):
            record = {
                "id": f"{label}-{expected}-{i}",
                "question": kind,
                "label": label,
                "covariates": dict(covariates),
            }
            if expected:
                record["expected"] = expected
            made.append(record)
    return made


# --- the interval ---------------------------------------------------------


def test_the_interval_is_wilson_and_not_the_naive_proportion():
    low, high = wilson(165, 220)
    assert (round(low, 3), round(high, 3)) == (0.689, 0.803)
    assert abs((low + high) / 2 - 0.75) > 1e-6  # wilson is not centred on p


def test_a_perfect_count_still_carries_uncertainty():
    low, high = wilson(20, 20)
    assert low < 1.0
    assert high == 1.0


def test_an_empty_denominator_has_no_interval():
    assert wilson(0, 0) is None


# --- what a level may claim ----------------------------------------------


def test_a_level_reports_the_rate_its_counts_support():
    level = recall(units("wrap", detected=165, missed=55), "wrap")["all"]
    assert level["true"] == 220
    assert level["detected"] == 165
    assert level["rate"] == pytest.approx(0.75)
    assert level["withheld"] == ()


def test_the_denominator_counts_true_violations_only():
    level = recall(units("wrap", detected=9, missed=1, false_=90, ambiguous=5), "wrap")[
        "all"
    ]
    assert level["true"] == 10
    assert level["detected"] == 9


def test_a_level_below_the_minimum_true_violations_reports_no_rate():
    level = recall(units("fused", detected=8, missed=1), "fused")["all"]
    assert level["rate"] is None
    assert "fewer than 10 true violations" in level["withheld"]


def test_a_level_whose_interval_is_wider_than_the_bound_reports_no_rate():
    level = recall(units("fused", detected=7, missed=5), "fused")["all"]
    assert (
        wilson(7, 12)[1] - wilson(7, 12)[0] > 2 * REPORTING["max_interval_half_width"]
    )
    assert level["rate"] is None
    assert "interval wider than 15 points" in level["withheld"]


def test_a_level_a_quarter_of_which_is_ambiguous_reports_no_rate():
    level = recall(
        units("wrap", detected=30, missed=5, false_=25, ambiguous=21), "wrap"
    )["all"]
    assert level["rate"] is None
    assert "more than a quarter of the labels are ambiguous" in level["withheld"]


def test_a_level_just_under_the_ambiguous_bound_still_reports():
    level = recall(
        units("wrap", detected=30, missed=5, false_=40, ambiguous=24), "wrap"
    )["all"]
    assert level["rate"] is not None


def test_a_withheld_level_still_reports_its_counts():
    level = recall(units("fused", detected=3, missed=1), "fused")["all"]
    assert (level["detected"], level["true"]) == (3, 4)
    assert level["rate"] is None


def test_a_level_with_no_true_violations_is_withheld_rather_than_divided_by_zero():
    level = recall(units("fused", detected=0, missed=0, false_=40), "fused")["all"]
    assert level["true"] == 0
    assert level["rate"] is None


# --- levels ---------------------------------------------------------------


def test_a_dimension_splits_the_report_into_its_levels():
    population = units("wrap", detected=12, missed=0, list_item_adjacency=True) + units(
        "wrap", detected=5, missed=7, list_item_adjacency=False
    )
    report = recall(population, "wrap", "list_item_adjacency")
    assert set(report) == {"True", "False"}
    assert report["True"]["detected"] == 12
    assert report["False"]["true"] == 12


def test_bands_group_a_numeric_dimension_into_the_levels_they_name():
    population = units("wrap", detected=11, missed=0, raw_end_column=60) + units(
        "wrap", detected=2, missed=9, raw_end_column=79
    )
    report = recall(population, "wrap", "raw_end_column", (64, 71, 78, 85))
    assert set(report) == {"..64", "79..85"}


def test_the_other_kind_is_not_counted():
    population = units("wrap", detected=10, missed=0) + units(
        "fused", detected=0, missed=10
    )
    assert recall(population, "wrap")["all"]["detected"] == 10
    assert recall(population, "fused")["all"]["detected"] == 0


# --- the floors -----------------------------------------------------------


def test_a_rate_that_meets_its_floor_draws_no_complaint():
    assert floor_problems(units("wrap", detected=165, missed=55), {"wrap": 0.75}) == []


def test_a_rate_one_detection_below_its_floor_is_refused():
    problems = floor_problems(units("wrap", detected=164, missed=56), {"wrap": 0.75})
    assert len(problems) == 1
    assert "wrap" in problems[0]


def test_a_floor_on_a_kind_the_corpus_cannot_rate_is_refused():
    problems = floor_problems(units("fused", detected=4, missed=1), {"fused": 0.75})
    assert len(problems) == 1
    assert "no rate" in problems[0]


def test_a_floor_for_a_kind_the_corpus_never_asked_about_is_refused():
    problems = floor_problems(units("wrap", detected=20, missed=0), {"typo": 0.5})
    assert len(problems) == 1


def test_a_stratum_floor_is_checked_at_every_level_it_names():
    population = units("wrap", detected=40, missed=0, language="go") + units(
        "wrap", detected=60, missed=40, language="markdown"
    )
    floors = {"wrap": {"go": 1.0, "markdown": 0.6}}
    assert floor_problems(population, floors, "language") == []
    problems = floor_problems(population, {"wrap": {"markdown": 0.7}}, "language")
    assert len(problems) == 1
    assert "markdown" in problems[0]


def test_a_stratum_floor_naming_a_level_the_corpus_withholds_is_refused():
    population = units("wrap", detected=3, missed=1, language="go")
    problems = floor_problems(population, {"wrap": {"go": 0.5}}, "language")
    assert len(problems) == 1
    assert "no rate" in problems[0]


# --- the corpus on disk ---------------------------------------------------


def test_the_calibration_corpus_meets_the_floors_recorded_for_it():
    document = on_disk()
    floors = document["reporting"]["recall_floors"]["calibration"]
    assert floor_problems(document["units"], floors) == []


def test_every_stratum_the_corpus_can_rate_meets_the_floor_recorded_for_it():
    document = on_disk()
    recorded = document["reporting"]["recall_floors"]
    for dimension in REPORTED_STRATA:
        bands = recorded["strata_bands"].get(dimension)
        floors = recorded["calibration_strata"][dimension]
        assert floor_problems(document["units"], floors, dimension, bands) == [], (
            dimension
        )


def test_a_stratum_that_carries_a_rate_carries_a_floor():
    """Otherwise one stratum drifts down to nothing while the total still clears its floor."""
    document = on_disk()
    recorded = document["reporting"]["recall_floors"]
    missing = []
    for dimension in REPORTED_STRATA:
        for kind in KINDS:
            report = recall(
                document["units"],
                kind,
                dimension,
                recorded["strata_bands"].get(dimension),
            )
            declared = recorded["calibration_strata"][dimension].get(kind, {})
            missing += [
                f"{dimension}/{kind}/{level}"
                for level, counts in report.items()
                if counts["rate"] is not None and level not in declared
            ]
    assert missing == []


def test_the_strata_a_rate_may_be_broken_down_by_are_fixed_in_code():
    """A stratum removable by editing the manifest is a floor removable by editing the manifest."""
    document = on_disk()
    assert set(document["reporting"]["recall_floors"]["calibration_strata"]) == set(
        REPORTED_STRATA
    )


def test_every_holdout_round_declares_its_floors_while_it_is_unlabeled():
    """A floor is a prediction, so it is stated while the answer is still unknown.

    Each round states its own.
    The calibration rates a floor derives from move between rounds,
    and one floor covering both would be restated after a round had already answered it.
    """
    document = on_disk()
    per_round = document["reporting"]["recall_floors"]["holdout"]
    rounds = {
        str(source["round"])
        for source in document["sources"]
        if source["side"] == "holdout"
    }
    assert set(per_round) == rounds
    assert all(set(floors) == {"wrap", "fused"} for floors in per_round.values())
    holdout = {
        source["id"] for source in document["sources"] if source["side"] == "holdout"
    }
    assert not [unit for unit in document["units"] if unit["source"] in holdout]


def test_every_reported_rate_names_the_frame_it_was_measured_in():
    document = on_disk()
    assert {unit["frame"] for unit in document["units"]} == {"main"}


# --- a scored round on disk -----------------------------------------------


def scored_rounds():
    """Every round that has been opened, by number, with what it measured."""
    return sorted(
        (
            (
                int(path.parent.name.split("-")[1]),
                json.loads(path.read_text(encoding="utf-8")),
            )
            for path in (REPO / "tests" / "corpus" / "holdout").glob(
                "round-*/result.json"
            )
        ),
        key=lambda scored: scored[0],
    )


def test_a_round_that_opened_was_scored_against_the_floors_it_declared():
    document = on_disk()
    declared = document["reporting"]["recall_floors"]["holdout"]
    for number, result in scored_rounds():
        assert result["floors"] == declared[str(number)], number


def acknowledged_misses():
    """Every floor a round missed and somebody accounted for, by round number."""
    recorded = on_disk()["reporting"]["recall_floors"]["holdout_misses"]
    return {key: entries for key, entries in recorded.items() if key.isdigit()}


def test_a_floor_a_round_missed_says_what_it_is_attributed_to_and_what_it_blocks():
    """A missed prediction nobody wrote down is read by the next reader as a pass.

    The floors are stated before a round is drawn and the round answers them once.
    Nothing else in this repository fails when one of those answers is no,
    so a miss survives only as a field in a result file that no gate consults.
    Acknowledging it here is what makes ignoring one an edit somebody has to make.
    """
    acknowledged = acknowledged_misses()
    for number, result in scored_rounds():
        entries = acknowledged.get(str(number), [])
        assert [entry["problem"] for entry in entries] == result["floor_problems"], (
            number
        )
        for entry in entries:
            for field in ("attributed_to", "blocks", "diagnosable"):
                assert entry.get(field, "").strip(), f"{entry['problem']}: {field}"


def test_a_floor_nothing_missed_carries_no_acknowledgement():
    """An acknowledgement for a round that has not answered is a floor excused in advance."""
    scored = {str(number) for number, _ in scored_rounds()}
    assert set(acknowledged_misses()) <= scored


# --- what a widened automatic repair must clear ---------------------------


def candidate(strata, **overrides):
    """A candidate class described by its counts, clearing everything not under test."""
    record = {
        "class": "terminator_period",
        "algorithm": "absorb-the-line-below",
        "baseline_algorithm": "absorb-the-line-below",
        "zero_tolerance": dict.fromkeys(REPAIR_ADMISSION["zero_tolerance"], 0),
        "strata": {
            name: {"scored": scored, "acceptable": acceptable, "ambiguous": 0}
            for name, (acceptable, scored) in strata.items()
        },
    }
    record.update(overrides)
    return record


def test_a_candidate_that_clears_every_clause_is_admitted():
    """Thirty-seven of forty is the smallest count at forty units whose bound clears."""
    assert repair_admission_problems(candidate({"{period}": (37, 40)})) == []


def test_a_point_rate_well_above_the_floor_does_not_clear_it():
    """Nine in ten repairs correct, and the interval still reaches below the floor.

    The bar is on the lower bound rather than on the rate,
    because a rate on forty units is compatible with a population rate ten points worse.
    Reading 0.900 against 0.80 and calling it cleared is the arithmetic this refuses.
    """
    problems = repair_admission_problems(candidate({"{period}": (36, 40)}))
    assert len(problems) == 1
    assert "0.769" in problems[0] and "0.80" in problems[0]


def test_a_class_scored_through_another_algorithm_than_the_shipped_one_is_refused():
    """Two algorithms in one round cannot say which of the two moved the result.

    The candidate absorbs the line below and the shipped repair replaces the anchor,
    so a comparison across them changes the repair shape and the eligibility class at once.
    """
    problems = repair_admission_problems(
        candidate({"{period}": (40, 40)}, baseline_algorithm="replace-the-anchor")
    )
    assert any("one algorithm" in problem for problem in problems)


def test_a_candidate_naming_no_algorithm_on_one_side_is_refused():
    """An unnamed algorithm cannot be shown to be the same one."""
    problems = repair_admission_problems(
        candidate({"{period}": (40, 40)}, baseline_algorithm=None)
    )
    assert any("algorithm" in problem for problem in problems)


def test_one_condition_hit_once_refuses_a_class_that_scores_perfectly():
    """The three conditions are conditions and not rates.

    Repairing a line that should have been left alone is the worst outcome this tool has,
    and a class does not buy its way past one by being right everywhere else.
    """
    perfect = candidate({"{period}": (40, 40)})
    perfect["zero_tolerance"]["fired_where_only_the_original_is_acceptable"] = 1
    problems = repair_admission_problems(perfect)
    assert any("however well it scores" in problem for problem in problems)


def test_a_condition_that_was_not_measured_refuses_the_class():
    """An unmeasured condition is not a satisfied one.

    Absent counts read as zero everywhere else in this harness.
    Here that reading would let a round admit a class by not looking.
    """
    unmeasured = candidate({"{period}": (40, 40)})
    del unmeasured["zero_tolerance"]["carrier_changed"]
    problems = repair_admission_problems(unmeasured)
    assert any("not measured" in problem for problem in problems)


def test_a_candidate_activating_nothing_has_not_been_scored():
    """No stratum is not a clean sheet."""
    assert repair_admission_problems(candidate({})) != []


def test_an_activated_stratum_with_nothing_scored_refuses_rather_than_clears():
    """There is no interval on an empty denominator, and no interval is not a pass."""
    problems = repair_admission_problems(candidate({"{period}": (0, 0)}))
    assert any("cannot rate" in problem for problem in problems)


def test_an_unreportable_activated_stratum_refuses_the_whole_candidate():
    """A candidate that reaches prose the round cannot score has not been scored.

    Dropping the stratum admits the class exactly where the least is known about it.
    """
    problems = repair_admission_problems(
        candidate({"{period}": (40, 40), "{period,colon}": (20, 20)})
    )
    assert any("{period,colon}" in problem for problem in problems)
    assert all("{period}:" not in problem for problem in problems)


def test_a_large_stratum_clearing_the_floor_does_not_carry_a_small_one_that_fails():
    """Each activated stratum is gated on its own bound rather than on their combination.

    Pooled, these are 156 of 170 at a lower bound of 0.866, which would clear.
    Taken apart, the smaller stratum is ten points worse and does not.
    """
    problems = repair_admission_problems(
        candidate({"{period}": (120, 130), "{period,dash}": (36, 40)})
    )
    assert len(problems) == 1
    assert "{period,dash}" in problems[0]


def test_a_stratum_large_enough_to_draw_but_too_wide_to_rate_is_refused():
    """The minimum size is a floor on the draw, and the half-width is the rule on the answer.

    Twenty-six units clears the first and says nothing about the second.
    Half of them repaired correctly spans eighteen points,
    and the frozen rules print no rate at that width.
    """
    problems = repair_admission_problems(candidate({"{period}": (13, 26)}))
    assert len(problems) == 1
    assert "interval wider" in problems[0]
    assert "below the floor" not in problems[0]


def test_a_stratum_a_quarter_of_which_is_ambiguous_cannot_be_rated():
    """The same rule the recall rates answer to, on the repair rates."""
    heavy = candidate({"{period}": (30, 30)})
    heavy["strata"]["{period}"].update(ambiguous=11, labeled=41)
    problems = repair_admission_problems(heavy)
    assert any("ambiguous" in problem for problem in problems)


def test_the_minimum_stratum_size_is_recorded_as_policy_and_not_as_a_derivation():
    """Twenty-six is a floor taken on a stated ground, which is not the same as proven.

    What the frozen rules make reportable depends on the realized count,
    the half-width and the ambiguous fraction, none of them known before labeling,
    so nothing can prove a smaller stratum intrinsically unreportable.
    The stated ground is the arithmetic below.
    A rate of 0.80 fits inside the frozen half-width at twenty-six units, not at twenty-five.
    """
    rules = REPAIR_ADMISSION["reportable"]
    assert rules["min_scored"] == 26
    assert "policy minimum rather than a derivation" in rules["min_scored_note"]
    bound = REPORTING["max_interval_half_width"]
    fits, misses = wilson(21, 26), wilson(20, 25)
    assert (fits[1] - fits[0]) / 2 <= bound < (misses[1] - misses[0]) / 2


def test_a_stratum_at_the_minimum_is_rated_and_then_refused_on_its_bound():
    """Being large enough to print a rate is not the same as clearing one.

    Twenty-six units at just over 0.80 is reportable and its bound is 0.62,
    so the message names the floor rather than naming a reason it could not be rated.
    """
    problems = repair_admission_problems(candidate({"{period}": (21, 26)}))
    assert len(problems) == 1
    assert "below the floor" in problems[0]
    assert "cannot rate" not in problems[0]


def test_more_acceptable_repairs_than_scored_units_is_refused_rather_than_computed():
    """A proportion above one is a defect in the count, not a very good class."""
    problems = repair_admission_problems(candidate({"{period}": (41, 40)}))
    assert any("not a proportion" in problem for problem in problems)
