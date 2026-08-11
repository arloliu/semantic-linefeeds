"""The holdout ledger, and the four things it refuses to do.

The holdout is worth nothing unless opening it is hard to arrange by accident.
Every test here asserts a refusal.
A mechanism that works only when the operator cooperates is a note in a document, not a mechanism.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import Holdout, ScoringRefused  # noqa: E402

PASSPHRASE = "the maintainer types this once"
PLAINTEXT = '{"units": [{"id": "h-0001", "label": "true"}]}\n'
RULES = {"interval": "wilson-95", "min_true": 10, "max_half_width": 0.15}


@pytest.fixture
def unsealed(tmp_path):
    """A predicate and a manifest that exist, an empty ledger, and no bundle yet."""
    predicate = tmp_path / "check_linefeeds.py"
    predicate.write_text("def check(text, path):\n    return []\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"units": []}\n', encoding="utf-8")
    return Holdout(
        bundle=tmp_path / "holdout.bundle.json",
        ledger=tmp_path / "freeze.jsonl",
        predicate=predicate,
        manifest=manifest,
    )


@pytest.fixture
def holdout(unsealed):
    """A sealed bundle, reached the way the protocol reaches one.

    The predicate is frozen first because sealing refuses otherwise,
    which is the ordering every test below inherits rather than arranges.
    """
    unsealed.freeze_predicate("a bundle these tests are about to seal")
    unsealed.seal(PLAINTEXT, PASSPHRASE)
    return unsealed


def test_sealing_against_an_unfrozen_predicate_is_refused(unsealed):
    """The ordering the first round kept by hand.

    A bundle that can be sealed before its predicate is frozen
    lets the freeze be written once the prose is already in the working tree,
    and a freeze written then predicts nothing.
    """
    with pytest.raises(ScoringRefused, match="freeze it before drawing"):
        unsealed.seal(PLAINTEXT, PASSPHRASE)
    assert not unsealed.bundle.exists(), "a refused seal must leave no bundle behind"


def test_a_predicate_tuned_after_its_freeze_cannot_be_sealed_against(unsealed):
    """Freezing something else does not count.

    The record names a digest, so editing the predicate afterwards
    leaves a ledger that is full and still does not name what is about to be sealed.
    """
    unsealed.freeze_predicate("a predicate that is about to change")
    unsealed.predicate.write_text(
        "def check(text, path):\n    return [(1, 'wrap')]\n", encoding="utf-8")
    with pytest.raises(ScoringRefused, match="no freeze record names this predicate"):
        unsealed.seal(PLAINTEXT, PASSPHRASE)


def test_an_unfrozen_bundle_will_not_open(holdout):
    """Freezing is the whole protocol; skipping it must not be possible."""
    with pytest.raises(ScoringRefused, match="no freeze record"):
        holdout.open(PASSPHRASE)


def test_a_frozen_bundle_opens_to_the_text_that_was_sealed(holdout):
    """The refusals are worth nothing if the legitimate path does not work.

    Sealing and opening are separated by a serialization,
    so this also pins that the bundle survives a round trip through the repository.
    """
    holdout.freeze(RULES)
    assert holdout.open(PASSPHRASE) == PLAINTEXT


def test_a_tuned_predicate_no_longer_opens_the_bundle(holdout):
    """The one refusal the whole protocol is built around.

    Tuning against calibration and then scoring on the holdout is model selection,
    so a predicate that moved after the freeze has to be told no.
    """
    holdout.freeze(RULES)
    holdout.predicate.write_text(
        "def check(text, path):\n    return [(1, 'fused')]\n", encoding="utf-8")
    with pytest.raises(ScoringRefused, match="the predicate changed since the freeze"):
        holdout.open(PASSPHRASE)


def test_a_changed_calibration_manifest_no_longer_opens_the_bundle(holdout):
    """The denominator is part of what was frozen.

    A rate computed against a manifest edited after the freeze is not the rate that was promised,
    and the edit is invisible in the score.
    """
    holdout.freeze(RULES)
    holdout.manifest.write_text('{"units": [{"id": "c-0001"}]}\n', encoding="utf-8")
    with pytest.raises(ScoringRefused, match="the calibration manifest changed since the freeze"):
        holdout.open(PASSPHRASE)


def test_a_bundle_that_was_already_scored_will_not_open_again(holdout):
    """One bundle, one evaluation.

    Without this the loser of a holdout run reopens the same bundle after a tweak,
    which is the leakage the one-shot rule exists to prevent.
    """
    holdout.freeze(RULES)
    holdout.open(PASSPHRASE)
    holdout.record_evaluation({"wrap": {"detected": 7, "true": 10}})
    with pytest.raises(ScoringRefused, match="already been evaluated"):
        holdout.open(PASSPHRASE)


def test_the_wrong_passphrase_is_refused_rather_than_answered_with_garbage(holdout):
    """A keystream cipher decrypts anything, correctly or not.

    Silence about a wrong passphrase would let a mistyped one produce nonsense units
    that get scored as if they were the holdout.
    """
    holdout.freeze(RULES)
    with pytest.raises(ScoringRefused, match="passphrase"):
        holdout.open("not the passphrase")


def test_recording_a_result_leaves_the_freeze_record_byte_identical(holdout):
    """The ledger is evidence, so it may grow but never change.

    A harness that rewrote an earlier line could restate what was frozen after reading the holdout.
    """
    holdout.freeze(RULES)
    before = holdout.ledger.read_text(encoding="utf-8")
    holdout.open(PASSPHRASE)
    holdout.record_evaluation({"wrap": {"detected": 7, "true": 10}})
    after = holdout.ledger.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert len(after.splitlines()) == len(before.splitlines()) + 1


def test_the_sealed_bundle_carries_nothing_but_cipher_parameters(holdout):
    """The bundle is committed, so whatever is readable in it is readable by the tuner.

    A substring check alone passes against a plaintext copy stored under JSON escaping,
    so the field set is asserted whole rather than sampled.
    """
    text = holdout.bundle.read_text(encoding="utf-8")
    assert set(json.loads(text)) == {"kdf", "iterations", "salt", "ciphertext", "tag"}
    assert "h-0001" not in text


def test_resealing_the_same_text_does_not_restore_a_spent_bundle(holdout):
    """Sealing again is the honest escape hatch, and it costs what it should.

    A fresh seal is a new ciphertext with no freeze record,
    so the way back to scoring runs through a freeze committed in the open.
    """
    holdout.freeze(RULES)
    holdout.open(PASSPHRASE)
    holdout.record_evaluation({"wrap": {"detected": 7, "true": 10}})
    holdout.seal(PLAINTEXT, PASSPHRASE)
    with pytest.raises(ScoringRefused, match="no freeze record names this bundle"):
        holdout.open(PASSPHRASE)
