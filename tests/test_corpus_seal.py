"""What gets sealed into a holdout bundle, and what stops it.

The bundle is written once and read once.
Anything wrong inside it is discovered after the round has been spent,
so the checks that matter are the ones that refuse before the ciphertext exists.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

TESTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

from corpus_harness import KINDS, defect  # noqa: E402


def load_seal():
    """The seal script, imported as a module rather than run as a command."""
    path = TESTS / "corpus" / "holdout" / "seal.py"
    spec = importlib.util.spec_from_file_location("holdout_seal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seal = load_seal()


def unit(uid):
    """One drawn boundary, carrying everything the payload copies out of it."""
    return {
        "id": uid,
        "source": "grpc-go",
        "path": "internal/transport/http2_client.go",
        "lines": [40, 41],
        "raw_window": ["// one", "// two"],
        "upper_index": 0,
        "covariates": {"raw_end_column": 71},
    }


def round_dir(tmp_path, units, answered):
    """A labeled round on disk, with `answered` naming who judged which unit."""
    (tmp_path / "labels").mkdir()
    (tmp_path / "sample.json").write_text(
        json.dumps(
            {
                "seed": "holdout-9",
                "base": 2,
                "per_level": 1,
                "quotas": {},
                "population": 99,
                "units": units,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "adjudications.json").write_text("[]", encoding="utf-8")
    for family, ids in answered.items():
        (tmp_path / "labels" / f"{family}-0.out").write_text(
            json.dumps([{"id": uid, "wrap": "true", "fused": "false"} for uid in ids]),
            encoding="utf-8",
        )
    return tmp_path


def test_a_unit_one_pass_never_answered_stops_the_seal(tmp_path):
    """Two blind passes are not the instrument this corpus reports.

    Resolving from the two that answered reads as unanimity wherever they agree,
    and the bundle would carry that under the same name as a unanimous three.
    """
    everyone = ["h-0001", "h-0002"]
    where = round_dir(
        tmp_path,
        [unit(uid) for uid in everyone],
        {
            "claude": everyone,
            "codex": everyone,
            "agy": ["h-0001"],
        },
    )
    with pytest.raises(SystemExit) as refusal:
        seal.payload(where)
    assert "h-0002" in str(refusal.value)


def test_a_unit_recorded_as_a_defect_leaves_the_sample_instead(tmp_path):
    """The escape hatch costs a boundary and records why, which is the point.

    A defect that silently dropped the unit would let a labeler's failure shrink the denominator without anyone signing for it.
    """
    units = [unit("h-0001"), unit("h-0002")]
    units[1]["labeling_defect"] = "one pass would not answer this unit on four runs"
    where = round_dir(
        tmp_path,
        units,
        {
            "claude": ["h-0001"],
            "codex": ["h-0001"],
            "agy": ["h-0001"],
        },
    )
    body = seal.payload(where)
    assert [record["boundary"] for record in body["units"]] == ["h-0001"] * len(KINDS)


def test_a_sound_round_seals_every_unit_it_drew(tmp_path):
    """The refusals are worth nothing if the ordinary path does not work."""
    everyone = ["h-0001", "h-0002"]
    where = round_dir(
        tmp_path,
        [unit(uid) for uid in everyone],
        {
            "claude": everyone,
            "codex": everyone,
            "agy": everyone,
        },
    )
    body = seal.payload(where)
    assert len(body["units"]) == len(everyone) * len(KINDS)
    assert all(
        record["label"] == "true"
        for record in body["units"]
        if record["question"] == "wrap"
    )


def test_both_kinds_of_defect_take_a_unit_out_of_the_sample():
    """One frame offered a unit it should not have; one pass would not answer another.

    They are different facts and both end the same way,
    so the pipeline asks one question rather than repeating two conditions in four places.
    """
    assert defect({"id": "h-1", "sampling_defect": "a licence header"})
    assert defect({"id": "h-2", "labeling_defect": "a pass would not answer it"})
    assert not defect({"id": "h-3"})
