"""How three blind labeling passes become one label.

The resolution is deliberately asymmetric.
The gate that decides this release is zero false positives,
and a label of "not a violation" is the only material that can refute the predicate,
so a refutation buys a maintainer's attention rather than a majority vote.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import (  # noqa: E402
    COVARIATES, file_digest, manifest_problems, replay_kinds, resolution)

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO / "tests" / "corpus" / "manifest.json"
LOCK = REPO / "tests" / "corpus" / "manifest.lock"


def on_disk():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def unit(**overrides):
    """One labeled boundary, complete enough that the validator has no complaint."""
    record = {
        "id": "c-0001",
        "source": "styx",
        "frame": "main",
        "path": "internal/buffer.go",
        "lines": [12, 15],
        "text": "// A sentence that ends mid-clause because it was\n// wrapped at a column.\n",
        "covariates": {
            "prose_width": 78,
            "raw_end_column": 77,
            "indentation_depth": 0,
            "language": "go",
            "markdown_nesting": 0,
            "trailing_inline_markup": False,
            "list_item_adjacency": False,
            "paragraph_line_count": 2,
            "eligible_anchor_count": 2,
        },
        "passes": {"claude": "true", "codex": "true", "agy": "true"},
        "question": "wrap",
        "label": "true",
        "expected": "detected",
    }
    record.update(overrides)
    return record


def manifest(**overrides):
    """A manifest holding one unit, valid until a test breaks one thing in it."""
    document = {
        "schema_version": 1,
        "rubric": {"path": "skills/semantic-linefeeds/SKILL.md", "digest": "sha256:" + "0" * 64},
        "reporting": {
            "interval": "wilson-95",
            "min_true_violations": 10,
            "max_interval_half_width": 0.15,
            "max_ambiguous_fraction": 0.25,
        },
        "covariate_definitions": {name: f"how {name} is measured" for name in COVARIATES},
        "eligible_anchor": {
            "definition": "the count of positions in the upper line where a break "
                          "would leave text on both sides, stated geometrically "
                          "and computed by this harness rather than by the checker",
        },
        "protocol_notes": [
            "the session that labels the holdout must not be the session that later tunes a predicate",
        ],
        "frames": {"main": {}, "out_of_scope": {}},
        "sources": [{
            "id": "styx",
            "side": "calibration",
            "composition": "self-authored",
            "url": "https://github.com/arloliu/styx",
            "commit": "0" * 40,
            "license": "MIT",
            "selection_command": "git ls-files '*.go'",
        }],
        "units": [unit()],
    }
    document.update(overrides)
    return document


def test_three_agreeing_passes_fix_the_label():
    """Unanimity is the only case that needs no judgment."""
    assert resolution(["true", "true", "true"]) == "true"
    assert resolution(["false", "false", "false"]) == "false"
    assert resolution(["ambiguous", "ambiguous", "ambiguous"]) == "ambiguous"


def test_a_lone_refutation_goes_to_the_maintainer():
    """Two-against-one is where a majority vote would quietly discard the refutation."""
    assert resolution(["true", "true", "false"]) == "adjudicated"


def test_a_refutation_survives_being_outnumbered_by_ambiguity():
    """Ambiguity is not evidence against a refutation, so it cannot outvote one."""
    assert resolution(["ambiguous", "ambiguous", "false"]) == "adjudicated"


def test_a_split_between_violation_and_ambiguity_is_ambiguous():
    """Nobody refuted anything here, so there is nothing for a maintainer to weigh."""
    assert resolution(["true", "true", "ambiguous"]) == "ambiguous"
    assert resolution(["ambiguous", "ambiguous", "true"]) == "ambiguous"


def test_a_three_way_split_is_ambiguous_rather_than_adjudicated():
    """The one case where the settled table overlaps itself, resolved by measurement.

    Sending three-way splits to the maintainer made the ambiguous label unreachable:
    across two pilot rounds every ambiguous answer arrived beside a refutation,
    so all of them became adjudications and no unit ever carried the label.
    A refutation buried in a three-way split is the narrower thing to give up.
    """
    assert resolution(["true", "false", "ambiguous"]) == "ambiguous"


def test_a_refutation_against_agreeing_labelers_still_reaches_the_maintainer():
    """The asymmetry survives where it was aimed: at a denial that stands against agreement."""
    assert resolution(["true", "true", "false"]) == "adjudicated"
    assert resolution(["ambiguous", "ambiguous", "false"]) == "adjudicated"


def test_a_pass_that_answered_something_else_is_an_error_rather_than_a_label():
    """Silently coercing an unknown answer would put an invented label in the denominator."""
    with pytest.raises(ValueError, match="unknown"):
        resolution(["true", "true", "probably"])


def test_a_complete_unit_draws_no_complaint():
    """The validator has to accept something, or every later test passes for the wrong reason."""
    assert manifest_problems(manifest()) == []


def test_a_true_violation_must_carry_its_frozen_expected_status():
    """This is the per-unit gate, and it works at a sample of one.

    A unit that slips from detected to missed turns the suite red without any arithmetic,
    so small strata are guarded rather than excused.
    """
    problems = manifest_problems(manifest(units=[unit(expected=None)]))
    assert any("c-0001" in p and "expected" in p for p in problems), problems


def test_every_unit_must_say_which_question_it_answers():
    """One boundary is judged twice, and the two answers live in two records.

    Rates are per kind, so a record not naming its question leaves both denominators silently.
    """
    problems = manifest_problems(manifest(units=[unit(question=None)]))
    assert any("c-0001" in p and "question" in p for p in problems), problems


def test_a_unit_answering_a_question_nobody_asked_is_rejected():
    """The two questions are fixed by what the detector can report."""
    problems = manifest_problems(manifest(units=[unit(question="tone")]))
    assert any("c-0001" in p and "tone" in p for p in problems), problems


def test_an_ambiguous_unit_carries_no_expected_status():
    """Ambiguous units are excluded from rates.

    Giving one an expected status would smuggle it back into a denominator it was excluded from.
    """
    ambiguous = unit(passes={"claude": "true", "codex": "true", "agy": "ambiguous"},
                     label="ambiguous")
    problems = manifest_problems(manifest(units=[ambiguous]))
    assert any("c-0001" in p and "expected" in p for p in problems), problems


def test_a_label_that_contradicts_its_three_passes_is_rejected():
    """The recorded label is derived, not asserted.

    Letting the two disagree would make the resolution table decorative.
    """
    contradiction = unit(passes={"claude": "true", "codex": "true", "agy": "ambiguous"})
    problems = manifest_problems(manifest(units=[contradiction]))
    assert any("c-0001" in p and "label" in p for p in problems), problems


def test_an_adjudicated_unit_without_a_recorded_reason_is_rejected():
    """A maintainer overrode three blind passes, so the corpus records why."""
    adjudicated = unit(passes={"claude": "true", "codex": "true", "agy": "false"})
    problems = manifest_problems(manifest(units=[adjudicated]))
    assert any("c-0001" in p and "adjudication" in p for p in problems), problems


def test_an_adjudicated_unit_with_a_reason_is_accepted():
    """Adjudication is a legitimate outcome, not a defect."""
    adjudicated = unit(passes={"claude": "true", "codex": "true", "agy": "false"},
                       adjudication="the continuation is a demonstrative, not a wrapped clause")
    assert manifest_problems(manifest(units=[adjudicated])) == []


def test_a_unit_missing_one_covariate_is_rejected():
    """All nine are recorded for every unit, whether or not they drove a quota.

    A reader recomputes any cross they want from the manifest,
    which only works when the covariate vector is complete.
    """
    thin = unit()
    del thin["covariates"]["eligible_anchor_count"]
    problems = manifest_problems(manifest(units=[thin]))
    assert any("c-0001" in p and "eligible_anchor_count" in p for p in problems), problems


def test_a_unit_naming_an_undeclared_source_is_rejected():
    """Attribution and sampling auditability both run through the source record."""
    problems = manifest_problems(manifest(units=[unit(source="helix")]))
    assert any("c-0001" in p and "helix" in p for p in problems), problems


def test_a_manifest_missing_a_required_section_is_rejected():
    """A reviewer reproduces every reported rate from the manifest alone.

    A section that may go missing is a section the reviewer cannot rely on.
    """
    thin = manifest()
    del thin["reporting"]
    assert any("reporting" in p for p in manifest_problems(thin))


def test_reporting_rules_loosened_in_the_manifest_are_rejected():
    """The bar below which no rate is printed was settled before any rate existed.

    Recording it in the manifest documents it;
    checking it here is what stops a level from being made reportable after the fact.
    """
    loose = manifest()
    loose["reporting"]["min_true_violations"] = 3
    assert any("min_true_violations" in p for p in manifest_problems(loose))


def test_switching_the_interval_estimator_is_rejected():
    """A rate must not become reportable by changing how its interval is computed."""
    swapped = manifest()
    swapped["reporting"]["interval"] = "normal-approximation"
    assert any("interval" in p for p in manifest_problems(swapped))


def test_a_third_party_source_under_a_copyleft_license_is_rejected():
    """Unit text is vendored, so the licence decides what may be stored at all."""
    copyleft = manifest()
    copyleft["sources"][0].update(composition="third-party-code", license="GPL-3.0-only")
    assert any("GPL-3.0-only" in p for p in manifest_problems(copyleft))


def test_a_permissive_license_with_an_exception_that_only_relaxes_is_accepted():
    """The LLVM exception waives Apache conditions for object-code embedding and adds none.

    Vendored prose is governed by the plain Apache-2.0 terms,
    so text under the combined identifier is storable wherever Apache-2.0 text is.
    """
    excepted = manifest()
    excepted["sources"][0].update(
        composition="third-party-markdown", license="Apache-2.0 WITH LLVM-exception",
        wrapping_column=80,
        qualification="mode of raw Markdown paragraph line lengths over 32357 lines")
    assert manifest_problems(excepted) == []


def test_a_third_party_source_without_its_measured_column_is_rejected():
    """A third-party source qualifies on evidence that never touches detector output.

    Choosing sources by finding density repeats, at repository granularity,
    the error ADR-0003 forbids at candidate granularity,
    so the measurement that did qualify the source is recorded where a reviewer can check it.
    """
    unmeasured = manifest()
    unmeasured["sources"][0].update(composition="third-party-code", license="MIT")
    assert any("wrapping_column" in p for p in manifest_problems(unmeasured))


def test_a_measured_third_party_source_is_accepted():
    """The measurement is a requirement, not an obstacle."""
    measured = manifest()
    measured["sources"][0].update(
        composition="third-party-code", license="MIT",
        wrapping_column=72,
        qualification="mode of raw comment line lengths over 5996 lines")
    assert manifest_problems(measured) == []


def test_a_source_assigned_to_neither_side_is_rejected():
    """Calibration and holdout stay separate, which needs every source to say which it is."""
    stray = manifest()
    stray["sources"][0]["side"] = "both"
    assert any("both" in p for p in manifest_problems(stray))


def test_a_holdout_source_that_names_no_round_is_rejected():
    """A holdout source is spent by the round that opened it, and the round is what says so.

    Without it a later draw enumerates the spent sources alongside the new ones
    and scores a predicate against the prose its repairs were fitted to,
    which is the one failure the whole protocol exists to prevent.
    """
    unnumbered = manifest()
    unnumbered["sources"][0].update(side="holdout")
    assert any("declares no round" in p for p in manifest_problems(unnumbered))


def test_a_holdout_source_that_names_its_round_is_accepted():
    """The round is a requirement, not an obstacle."""
    numbered = manifest()
    numbered["sources"][0].update(side="holdout", round=2)
    assert manifest_problems(numbered) == []


def test_a_dimension_recorded_on_units_but_never_defined_is_rejected():
    """A reviewer reproduces every rate from the manifest alone.

    A covariate whose meaning lives only in the harness makes that impossible,
    and a marginal reported over an undefined dimension says nothing a reader can check.
    """
    undefined = manifest()
    del undefined["covariate_definitions"]["raw_end_column"]
    assert any("raw_end_column" in p for p in manifest_problems(undefined))


def test_a_unit_in_an_undeclared_frame_is_rejected():
    """The out-of-scope sample is reported on its own and never merged into the main rates.

    A unit naming a frame the manifest never declares lands in whichever bucket a reader assumes.
    """
    problems = manifest_problems(manifest(units=[unit(frame="whatever")]))
    assert any("c-0001" in p and "whatever" in p for p in problems), problems


def test_the_manifest_on_disk_satisfies_its_own_schema():
    """A schema no artifact obeys is a document, not a schema."""
    assert manifest_problems(on_disk()) == []


def test_the_pinned_rubric_still_matches_the_skill_it_names():
    """The corpus measures the standard the tool publishes, and nothing else.

    A separate rulebook would let the two drift with nobody noticing,
    so this fails the day the skill changes and forces a decision about relabeling.
    """
    rubric = on_disk()["rubric"]
    assert rubric["digest"] == file_digest(REPO / rubric["path"]), (
        "the published rule changed; decide whether the corpus needs relabeling, "
        "then repin the digest")


def test_every_frozen_status_still_holds():
    """The per-unit gate, and the reason a unit stores its raw lines at all.

    It needs no arithmetic and works at a sample of one,
    so a stratum too small to carry a rate is guarded rather than excused.
    A total could be held steady by a new mistake covering for a lost one; identity cannot.
    """
    slipped = []
    for record in on_disk()["units"]:
        frozen = record.get("expected")
        if frozen is None:
            continue
        now = "detected" if record["question"] in replay_kinds(record) else "accepted_miss"
        if now != frozen:
            slipped.append(f"{record['id']}: frozen as {frozen}, now {now}")
    assert not slipped, (
        "these labeled violations changed detection status; approve the change in the "
        "manifest or fix the regression:\n  " + "\n  ".join(slipped))


@pytest.mark.xfail(
    strict=True,
    reason="one of 450 labeled non-violations still draws a complaint: a line already "
           "carrying a fused sentence, whose wrap the labelers judged to be the same defect "
           "counted twice; the precision repairs cleared the other six",
)
def test_no_labeled_non_violation_draws_a_complaint():
    """Zero false positives, measured against prose somebody read rather than prose we wrote.

    The compliant corpus is adversarial and collects the known failure modes.
    This set is representative: it is whatever random sampling produced,
    so the two fail for different reasons and neither substitutes for the other.

    Marked strict, so it fails the moment it starts passing
    and the marker cannot outlive the defects it names.
    """
    complaints = [f"{record['id']}: {record['upper']}"
                  for record in on_disk()["units"]
                  if record["label"] == "false" and record["question"] in replay_kinds(record)]
    assert not complaints, (
        "the detector complained about prose three labelers judged correct:\n  "
        + "\n  ".join(complaints))


def test_the_manifest_has_not_changed_without_a_recorded_reason():
    """Every accepted miss and every relabel goes through a reviewer.

    The lock is what turns editing the manifest into an act somebody has to sign,
    which is the difference between bounding future losses and merely recording past ones.
    """
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["digest"] == file_digest(MANIFEST), (
        "the manifest changed; record what changed and why in manifest.lock, "
        "then repin the digest")
    assert lock["reason"].strip(), "a manifest change with no stated reason is an unexplained one"
