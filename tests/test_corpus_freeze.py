"""The holdout ledger, and the four things it refuses to do.

The holdout is worth nothing unless opening it is hard to arrange by accident.
Every test here asserts a refusal.
A mechanism that works only when the operator cooperates is a note in a document, not a mechanism.
"""

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import Holdout, ScoringRefused  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent

PASSPHRASE = "the maintainer types this once"
PLAINTEXT = '{"units": [{"id": "h-0001", "label": "true"}]}\n'
RULES = {"interval": "wilson-95", "min_true": 10, "max_half_width": 0.15}

# A round nobody has created.
# The rules that keep a holdout out of history have to cover the next round as well as this one,
# and asking about an existing directory would not tell them apart.
UNDRAWN_ROUND = 97

# The round these tests act for.
# A pre-draw freeze names one, because a freeze that names no round authorizes every round.
TEST_ROUND = 90


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
        round=TEST_ROUND,
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

    A bundle that can be sealed before its predicate is frozen lets the freeze be written once the prose is already in the working tree,
    and a freeze written then predicts nothing.
    """
    with pytest.raises(ScoringRefused, match="freeze it before drawing"):
        unsealed.seal(PLAINTEXT, PASSPHRASE)
    assert not unsealed.bundle.exists(), "a refused seal must leave no bundle behind"


def test_a_predicate_tuned_after_its_freeze_cannot_be_sealed_against(unsealed):
    """Freezing something else does not count.

    The record names a digest,
    so editing the predicate afterwards leaves a ledger that is full and still does not name what is about to be sealed.
    """
    unsealed.freeze_predicate("a predicate that is about to change")
    unsealed.predicate.write_text(
        "def check(text, path):\n    return [(1, 'wrap')]\n", encoding="utf-8"
    )
    with pytest.raises(ScoringRefused, match="the predicate changed since the freeze"):
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
        "def check(text, path):\n    return [(1, 'fused')]\n", encoding="utf-8"
    )
    with pytest.raises(ScoringRefused, match="the predicate changed since the freeze"):
        holdout.open(PASSPHRASE)


def test_a_changed_calibration_manifest_no_longer_opens_the_bundle(holdout):
    """The denominator is part of what was frozen.

    A rate computed against a manifest edited after the freeze is not the rate that was promised,
    and the edit is invisible in the score.
    """
    holdout.freeze(RULES)
    holdout.manifest.write_text('{"units": [{"id": "c-0001"}]}\n', encoding="utf-8")
    with pytest.raises(
        ScoringRefused, match="the calibration manifest changed since the freeze"
    ):
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


@pytest.mark.parametrize(
    "name", ["sample.json", "adjudications.json", "labels/claude-0.out"]
)
def test_a_round_that_does_not_exist_yet_already_keeps_its_prose_out_of_history(name):
    """git keeps what a later commit deletes, so one careless `git add` ends a round.

    The seal deletes the plaintext, which protects the working tree and not the history.
    These paths are ignored for every round rather than for the rounds someone remembered,
    because the round that leaks is the one whose three lines nobody added.
    """
    path = f"tests/corpus/holdout/round-{UNDRAWN_ROUND}/{name}"
    ignored = subprocess.run(["git", "-C", str(REPO), "check-ignore", "--quiet", path])
    assert ignored.returncode == 0, f"{path} would be committable"


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


def test_a_freeze_written_for_one_round_authorizes_no_other(unsealed):
    """A round is not a label on a record; it is what the record authorizes.

    Without it one freeze covers every round that shares its predicate,
    so a spent round's commitment would stand in for a new round's.
    """
    unsealed.freeze_predicate("the round these tests act for")
    unsealed.round = TEST_ROUND + 1
    with pytest.raises(
        ScoringRefused, match=f"no freeze record names round {TEST_ROUND + 1}"
    ):
        unsealed.seal(PLAINTEXT, PASSPHRASE)


def test_a_round_cannot_be_frozen_twice(unsealed):
    """The second freeze is the one written after the prose was read."""
    unsealed.freeze_predicate("the first commitment")
    with pytest.raises(ScoringRefused, match="was already frozen"):
        unsealed.freeze_predicate("a second one, after reading the sample")


def test_a_freeze_that_names_no_round_authorizes_nothing(unsealed):
    """Rounds 1 to 3 wrote records without a round, and those records stand.

    They are not edited, and they are not honoured either:
    a record that names no round would authorize every round,
    which is the opposite of what a freeze is for.
    """
    unsealed.ledger.write_text(
        json.dumps(
            {
                "record": "predicate_freeze",
                "predicate_digest": unsealed._predicate_digest(),
                "manifest_digest": unsealed._manifest_digest(),
                "intent": "written the way rounds 1 to 3 wrote theirs",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ScoringRefused, match="predate the round rule"):
        unsealed.seal(PLAINTEXT, PASSPHRASE)


def test_a_predicate_tuned_after_the_draw_cannot_refreeze_and_seal(unsealed):
    """The sequence the ledger did not refuse before this rule existed.

    Freeze A, draw and label the prose, tune to B once it has been read,
    append a freeze for B, and seal against B.
    Every step was permitted, and the sealed bundle looked correct afterwards.
    What closes it is the sample carrying the id of the freeze it was drawn under:
    a seal that cannot name that record is refused,
    and the record it names still holds predicate A.
    """
    frozen = unsealed.freeze_predicate("predicate A, before any prose was drawn")
    drawn_under = frozen["id"]

    # The prose is drawn here, under A, and read.
    unsealed.predicate.write_text(
        "def check(text, path):\n    return [(1, 'wrap')]\n", encoding="utf-8"
    )
    # Round 90 is already frozen, so B cannot even be committed to.
    with pytest.raises(ScoringRefused, match="was already frozen"):
        unsealed.freeze_predicate("predicate B, tuned against prose it has now read")

    # And a seal naming the freeze the prose was actually drawn under refuses,
    # because that record names A while the tree holds B.
    with pytest.raises(ScoringRefused, match="the predicate changed since the freeze"):
        unsealed.seal(PLAINTEXT, PASSPHRASE, drawn_under=drawn_under)


def test_a_seal_naming_a_freeze_the_ledger_does_not_hold_is_refused(unsealed):
    """The sample's record id is checked against the ledger, not trusted from the sample."""
    unsealed.freeze_predicate("the freeze this round was drawn under")
    with pytest.raises(ScoringRefused, match="a freeze this ledger does not hold"):
        unsealed.seal(PLAINTEXT, PASSPHRASE, drawn_under="sha256:not-a-record")


@pytest.mark.parametrize("number", [1, 2, 3])
def test_the_sealed_rounds_still_answer_to_their_own_freeze(number):
    """A protocol repair that invalidates the evidence already gathered is not a repair.

    Rounds 1 to 3 were sealed before a pre-draw record named a round,
    and round 1 wrote no pre-draw record at all.
    Binding new rounds to one must leave the old bundles reachable,
    which they are: opening and scoring answer to the bundle's own freeze,
    and that record binds a ciphertext rather than a round.
    """
    corpus = REPO / "tests" / "corpus"
    bundle = corpus / "holdout" / f"round-{number}" / "bundle.json"
    ciphertext = json.loads(bundle.read_text(encoding="utf-8"))["ciphertext"]
    ledger = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    holdout = Holdout(
        bundle=bundle,
        ledger=corpus / "freeze.jsonl",
        predicate=REPO / "scripts" / "check_linefeeds.py",
        manifest=corpus / "manifest.json",
        round=number,
    )
    digest = holdout._ciphertext_digest()
    assert any(
        record.get("record") == "freeze" and record["ciphertext_digest"] == digest
        for record in ledger
    ), f"round {number}'s bundle has no freeze record naming it"
    assert ciphertext, "a sealed bundle carries a ciphertext"


@pytest.mark.parametrize("number", [1, 2, 3])
def test_a_spent_round_cannot_be_drawn_again(number):
    """ADR-0008 retires a round's sources once the round has been opened.

    The pre-draw path is where a redraw would start,
    and the three spent rounds have no record it will honour.
    """
    corpus = REPO / "tests" / "corpus"
    holdout = Holdout(
        bundle=corpus / "holdout" / f"round-{number}" / "bundle.json",
        ledger=corpus / "freeze.jsonl",
        predicate=REPO / "scripts" / "check_linefeeds.py",
        manifest=corpus / "manifest.json",
        round=number,
    )
    with pytest.raises(ScoringRefused, match="predate the round rule"):
        holdout.require_predicate_freeze()
