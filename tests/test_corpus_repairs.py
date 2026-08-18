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
