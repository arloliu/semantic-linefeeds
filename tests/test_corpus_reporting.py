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
    KINDS, REPORTED_STRATA, REPORTING, floor_problems, recall, wilson)

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
            record = {"id": f"{label}-{expected}-{i}", "question": kind, "label": label,
                      "covariates": dict(covariates)}
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
    level = recall(units("wrap", detected=9, missed=1, false_=90, ambiguous=5), "wrap")["all"]
    assert level["true"] == 10
    assert level["detected"] == 9


def test_a_level_below_the_minimum_true_violations_reports_no_rate():
    level = recall(units("fused", detected=8, missed=1), "fused")["all"]
    assert level["rate"] is None
    assert "fewer than 10 true violations" in level["withheld"]


def test_a_level_whose_interval_is_wider_than_the_bound_reports_no_rate():
    level = recall(units("fused", detected=7, missed=5), "fused")["all"]
    assert wilson(7, 12)[1] - wilson(7, 12)[0] > 2 * REPORTING["max_interval_half_width"]
    assert level["rate"] is None
    assert "interval wider than 15 points" in level["withheld"]


def test_a_level_a_quarter_of_which_is_ambiguous_reports_no_rate():
    level = recall(units("wrap", detected=30, missed=5, false_=25, ambiguous=21), "wrap")["all"]
    assert level["rate"] is None
    assert "more than a quarter of the labels are ambiguous" in level["withheld"]


def test_a_level_just_under_the_ambiguous_bound_still_reports():
    level = recall(units("wrap", detected=30, missed=5, false_=40, ambiguous=24), "wrap")["all"]
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
    population = (units("wrap", detected=12, missed=0, list_item_adjacency=True)
                  + units("wrap", detected=5, missed=7, list_item_adjacency=False))
    report = recall(population, "wrap", "list_item_adjacency")
    assert set(report) == {"True", "False"}
    assert report["True"]["detected"] == 12
    assert report["False"]["true"] == 12


def test_bands_group_a_numeric_dimension_into_the_levels_they_name():
    population = (units("wrap", detected=11, missed=0, raw_end_column=60)
                  + units("wrap", detected=2, missed=9, raw_end_column=79))
    report = recall(population, "wrap", "raw_end_column", (64, 71, 78, 85))
    assert set(report) == {"..64", "79..85"}


def test_the_other_kind_is_not_counted():
    population = units("wrap", detected=10, missed=0) + units("fused", detected=0, missed=10)
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
    population = (units("wrap", detected=40, missed=0, language="go")
                  + units("wrap", detected=60, missed=40, language="markdown"))
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
        assert floor_problems(document["units"], floors, dimension, bands) == [], dimension


def test_a_stratum_that_carries_a_rate_carries_a_floor():
    """Otherwise one stratum drifts down to nothing while the total still clears its floor."""
    document = on_disk()
    recorded = document["reporting"]["recall_floors"]
    missing = []
    for dimension in REPORTED_STRATA:
        for kind in KINDS:
            report = recall(document["units"], kind, dimension, recorded["strata_bands"].get(dimension))
            declared = recorded["calibration_strata"][dimension].get(kind, {})
            missing += [f"{dimension}/{kind}/{level}" for level, counts in report.items()
                        if counts["rate"] is not None and level not in declared]
    assert missing == []


def test_the_strata_a_rate_may_be_broken_down_by_are_fixed_in_code():
    """A stratum removable by editing the manifest is a floor removable by editing the manifest."""
    document = on_disk()
    assert set(document["reporting"]["recall_floors"]["calibration_strata"]) == set(REPORTED_STRATA)


def test_the_holdout_floors_are_declared_while_the_holdout_is_unlabeled():
    document = on_disk()
    floors = document["reporting"]["recall_floors"]["holdout"]
    assert set(floors) == {"wrap", "fused"}
    holdout = {source["id"] for source in document["sources"] if source["side"] == "holdout"}
    assert not [unit for unit in document["units"] if unit["source"] in holdout]


def test_every_reported_rate_names_the_frame_it_was_measured_in():
    document = on_disk()
    assert {unit["frame"] for unit in document["units"]} == {"main"}
