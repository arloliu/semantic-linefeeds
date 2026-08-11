"""What a quota could not buy, said out loud.

A draw reports the levels it filled.
A level it filled with nothing has no units to report,
so the one case worth hearing about is the one that stays silent.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import band_levels, draw_corpus, quota_shortfalls  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


def population(**levels):
    """One record per unit, carrying only the covariates a quota reads."""
    made = []
    for dimension, counts in levels.items():
        for value, how_many in counts.items():
            for i in range(how_many):
                made.append({"id": f"{dimension}-{value}-{i}",
                             "covariates": {dimension: value}})
    return made


def test_the_named_levels_of_a_band_include_the_edges_and_both_tails():
    assert band_levels((64, 71)) == ("..64", "65..71", "72..")


def test_a_satisfied_quota_says_nothing():
    people = population(language={"go": 40, "markdown": 40})
    drawn = draw_corpus(people, 20, {"language": (None, 20)}, "seed")
    assert quota_shortfalls(people, drawn, {"language": (None, 20)}) == []


def test_a_level_thinner_than_its_quota_is_reported():
    people = population(language={"go": 40, "markdown": 5})
    drawn = draw_corpus(people, 10, {"language": (None, 20)}, "seed")
    problems = quota_shortfalls(people, drawn, {"language": (None, 20)})
    assert len(problems) == 1
    assert "markdown" in problems[0] and "5 of 20" in problems[0]


def test_a_named_band_the_population_never_reaches_is_reported():
    """The silent case.

    A band with no units contributes no row to a report built from the units drawn,
    so it reads as a level nobody asked about rather than as a level nobody could fill.
    """
    people = population(raw_end_column={60: 40, 70: 40})
    quotas = {"raw_end_column": ((64, 71), 20)}
    drawn = draw_corpus(people, 20, quotas, "seed")
    problems = quota_shortfalls(people, drawn, quotas)
    assert [p for p in problems if p.startswith("raw_end_column at 72..")] == [
        "raw_end_column at 72..: 0 of 20"]


def test_a_dimension_the_population_holds_at_one_level_separates_nothing():
    """A constant is not a stratum.

    This is what a repair to the extractor can do to a dimension without anyone noticing:
    the level stops existing in the sampling frame,
    and a quota asking for it reports success because there is nothing left to be short of.
    """
    people = population(list_item_adjacency={False: 80})
    quotas = {"list_item_adjacency": (None, 20)}
    drawn = draw_corpus(people, 40, quotas, "seed")
    problems = quota_shortfalls(people, drawn, quotas)
    assert len(problems) == 1
    assert "separates nothing" in problems[0]


def test_an_empty_population_is_reported_rather_than_divided_by_zero():
    assert quota_shortfalls([], [], {"language": (None, 20)}) == [
        "language: the population holds nothing, so the quota separates nothing"]


def test_the_holdout_draw_reports_what_it_could_not_buy():
    """The draw on disk, checked against the same rule.

    Two of its quotas were unbuyable, and both for the same reason:
    the precision repairs changed which boundaries the extractor yields at all.
    """
    sample_path = REPO / "tests" / "corpus" / "holdout" / "sample.json"
    if not sample_path.exists():
        return
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    quotas = {name: (spec["bands"], spec["per_level"])
              for name, spec in sample["quotas"].items()}
    problems = quota_shortfalls(sample["units"], sample["units"], quotas)
    assert any("list_item_adjacency" in p and "separates nothing" in p for p in problems)
