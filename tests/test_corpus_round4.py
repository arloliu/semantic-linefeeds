"""The ledger-bound repair round: freeze, draw, seal, one spending open.

Every gate refuses on its own, and the happy path runs end to end,
all against a corpus in tmp so nothing here can touch the real ledger.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

TESTS = pathlib.Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(TESTS / "corpus" / "repairs"))

import score as score_module  # noqa: E402

# Both corpora carry a bare module named `collect`,
# and importing score binds the repairs copy into sys.modules,
# which would shadow the holdout copy for any later test in the same process.
# score holds its references already, so the cache entry can go.
sys.modules.pop("collect", None)

from corpus_harness import (  # noqa: E402
    Holdout,
    ScoringRefused,
    repair_admission_result_ledger_problems,
    repair_round_bindings,
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


draw = load("repair_draw", TESTS / "corpus" / "repairs" / "draw.py")
seal = load("repair_seal", TESTS / "corpus" / "repairs" / "seal.py")

PASSPHRASE = "spoken once, in a test"


def fixture_corpus(tmp_path, units_per_source=(30, 2, 2)):
    """A tmp corpus with three valid round-4 sources over git-indexed trees."""
    corpus = tmp_path / "corpus"
    (corpus / "repairs").mkdir(parents=True)
    (corpus / "freeze.jsonl").write_text("", encoding="utf-8")
    root = tmp_path / "src"
    compositions = ("self-authored", "third-party-code", "third-party-markdown")
    sources = []
    for index, composition in enumerate(compositions):
        ident = f"fresh-{index + 1}"
        tree = root / ident
        tree.mkdir(parents=True)
        for n in range(units_per_source[index]):
            (tree / f"note{n:03}.md").write_text(
                f"Take number {n} stands alone. Another sentence follows it.\n",
                encoding="utf-8",
            )
        subprocess.run(["git", "init", "-q", str(tree)], check=True)
        subprocess.run(["git", "-C", str(tree), "add", "-A"], check=True)
        sources.append(
            {
                "id": ident,
                "side": "holdout",
                "round": 4,
                "composition": composition,
                "url": f"https://example.invalid/{ident}",
                "commit": "0" * 40,
                "license": "MIT",
                "selection_command": "git ls-files '*.md'",
                "wrapping_column": 80,
                "qualification": "mode of raw line lengths is column 80, "
                "measured from line lengths, licence, and prior exposure only",
            }
        )
    manifest = corpus / "manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "sources": sources}, indent=2) + "\n",
        encoding="utf-8",
    )
    return corpus, manifest, root


def repair_holdout(corpus, manifest):
    return Holdout(
        corpus / "repairs" / "round-4" / "bundle.json",
        corpus / "freeze.jsonl",
        REPO / "scripts" / "check_linefeeds.py",
        manifest,
        round=4,
    )


def freeze_round_four(corpus, manifest):
    document = json.loads(manifest.read_text(encoding="utf-8"))
    return repair_holdout(corpus, manifest).freeze_predicate(
        "the widened window predicate, frozen before round 4 exists",
        binds=repair_round_bindings(document, 4),
    )


def drawn(tmp_path, corpus, manifest, root):
    done = draw.main([str(root), "--round", "4", "--manifest", str(manifest)])
    assert done is None
    sample_path = corpus / "repairs" / "round-4" / "sample.json"
    return json.loads(sample_path.read_text(encoding="utf-8")), sample_path


def answer_everything(corpus, sample):
    """Three passes accepting every candidate, choosing the original."""
    answers = corpus / "repairs" / "round-4" / "answers"
    answers.mkdir()
    for name in ("claude", "codex", "agy"):
        body = []
        for unit in sample["units"]:
            ids = [candidate["id"] for candidate in unit["candidates"]]
            (original,) = [
                candidate["id"]
                for candidate in unit["candidates"]
                if candidate["cuts"] == unit["original_cut"]
            ]
            body.append(
                {"id": unit["id"], "choose": original, "accept": ids, "reject": []}
            )
        (answers / f"{name}-01.out").write_text(json.dumps(body), encoding="utf-8")
    return answers


def sealed(corpus, manifest):
    holdout, body, drawn_under, binds, round_dir = seal.prepare(4, manifest)
    seal.seal_round(holdout, body, drawn_under, binds, round_dir, passphrase=PASSPHRASE)
    for path in seal.plaintext(round_dir):
        if path.is_dir():
            import shutil

            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    return round_dir


def test_a_draw_without_the_freeze_refuses_without_creating_a_directory(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    with pytest.raises(SystemExit, match="no freeze record names round 4"):
        draw.main([str(root), "--round", "4", "--manifest", str(manifest)])
    assert not (corpus / "repairs" / "round-4").exists()


def test_an_invalid_source_selection_refuses_before_the_ledger_moves(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["sources"] = document["sources"][:-1]
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="one source per composition"):
        draw.main([str(root), "--round", "4", "--manifest", str(manifest)])
    assert (corpus / "freeze.jsonl").read_text(encoding="utf-8") == ""
    assert not (corpus / "repairs" / "round-4").exists()


def test_the_drawn_sample_records_the_freeze_and_its_binds(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    frozen = freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    assert sample["drawn_under"] == frozen["id"]
    assert sample["binds"] == frozen["binds"]
    assert sample["round"] == 4
    assert len(sample["units"]) >= 26


def test_a_second_draw_refuses(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    drawn(tmp_path, corpus, manifest, root)
    with pytest.raises(SystemExit, match="draws once"):
        draw.main([str(root), "--round", "4", "--manifest", str(manifest)])


def test_a_mutated_sample_binding_alone_stops_the_seal(tmp_path):
    """ADR-0024: freeze, sample, and seal agree, even while ledger and tree still do."""
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, sample_path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    sample["binds"]["taxonomy"] = "sha256:" + "0" * 64
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    with pytest.raises(SystemExit, match="taxonomy"):
        seal.prepare(4, manifest)


def test_a_missing_drawn_under_stops_the_seal(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, sample_path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    del sample["drawn_under"]
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    with pytest.raises(SystemExit, match="names no freeze record"):
        seal.prepare(4, manifest)


def test_a_source_moved_after_the_freeze_stops_the_seal(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    for source in document["sources"]:
        if source.get("round") == 4:
            source["commit"] = "1" * 40
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="sources"):
        seal.prepare(4, manifest)


def test_sealing_removes_every_plaintext_artifact(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    round_dir = sealed(corpus, manifest)
    assert [entry.name for entry in round_dir.iterdir()] == ["bundle.json"]


def test_one_open_scores_both_sides_and_spends(tmp_path):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    round_dir = sealed(corpus, manifest)
    result = score_module.score_bundle(round_dir, root, manifest, passphrase=PASSPHRASE)
    assert set(result) >= {"outcome", "admitted", "candidate", "shipped", "strata"}
    assert result["admitted"] == ["terminator_period"]
    assert result["outcome"] == "admitted"
    assert result["strata"]["terminator_period"]["scored"] >= 26
    records = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    kinds = [record["record"] for record in records]
    assert kinds.count("evaluation") == 1
    assert kinds.count("evaluation_result") == 1
    with pytest.raises(ScoringRefused, match="already been evaluated"):
        score_module.score_bundle(round_dir, root, manifest, passphrase=PASSPHRASE)


def test_a_crash_after_the_spend_still_leaves_the_bundle_spent(tmp_path, monkeypatch):
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    round_dir = sealed(corpus, manifest)

    def explode(*args, **kwargs):
        raise RuntimeError("the scorer died mid-evaluation")

    monkeypatch.setattr(score_module, "scored_strata", explode)
    with pytest.raises(RuntimeError):
        score_module.score_bundle(round_dir, root, manifest, passphrase=PASSPHRASE)
    monkeypatch.undo()
    with pytest.raises(ScoringRefused, match="already been evaluated"):
        score_module.score_bundle(round_dir, root, manifest, passphrase=PASSPHRASE)
    records = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (failed,) = [
        record for record in records if record["record"] == "evaluation_result"
    ]
    assert failed["result"]["state"] == "failed-evaluation"


def admission_record_from(result, frozen, corpus):
    records = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (spend,) = [record for record in records if record["record"] == "evaluation"]
    return {
        "version": 1,
        "admitted": result["admitted"],
        "round": 4,
        "freeze_id": frozen["id"],
        "evaluation_digest": spend["ciphertext_digest"].split(":")[-1],
        "predicate_digest": frozen["predicate_digest"].split(":")[-1],
        "scoring": "score.py --bundle through composed and normalize_repair",
        "strata": {
            key: {
                "scored": body["scored"],
                "acceptable": body["acceptable"],
                "lower_bound": body["lower_bound"],
            }
            for key, body in result["strata"].items()
        },
        "zero_tolerance": result["zero_tolerance"],
        "outcome": result["outcome"],
        "adr": "0028",
    }, records


def test_the_ledger_cross_check_accepts_the_real_evaluation_and_nothing_else(
    tmp_path,
):
    corpus, manifest, root = fixture_corpus(tmp_path)
    frozen = freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    round_dir = sealed(corpus, manifest)
    result = score_module.score_bundle(round_dir, root, manifest, passphrase=PASSPHRASE)
    record, records = admission_record_from(result, frozen, corpus)
    # The digests the ledger stores are sha256:-prefixed; the record stores bare hex.
    document = {"repair_admission_result": record}
    problems = repair_admission_result_ledger_problems(document, records)
    assert problems == []
    tampered = dict(record, freeze_id="freeze-0000")
    assert repair_admission_result_ledger_problems(
        {"repair_admission_result": tampered}, records
    )
    unopened = dict(record, evaluation_digest="f" * 64)
    assert repair_admission_result_ledger_problems(
        {"repair_admission_result": unopened}, records
    )


def test_an_incomplete_evaluation_validates_no_admission(tmp_path, monkeypatch):
    corpus, manifest, root = fixture_corpus(tmp_path)
    frozen = freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    sealed(corpus, manifest)
    holdout = repair_holdout(corpus, manifest)
    holdout.open_spending(PASSPHRASE)  # spent, never completed
    records = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (spend,) = [record for record in records if record["record"] == "evaluation"]
    record = {
        "repair_admission_result": {
            "freeze_id": frozen["id"],
            "round": 4,
            "predicate_digest": frozen["predicate_digest"].split(":")[-1],
            "evaluation_digest": spend["ciphertext_digest"].split(":")[-1],
            "outcome": "admitted",
        }
    }
    problems = repair_admission_result_ledger_problems(record, records)
    assert any("never completed" in problem for problem in problems)


def test_a_wrong_passphrase_refuses_without_spending(tmp_path):
    """Authentication comes before the spend, so a typo cannot burn the round."""
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    sealed(corpus, manifest)
    holdout = repair_holdout(corpus, manifest)
    with pytest.raises(ScoringRefused, match="passphrase"):
        holdout.open_spending("not the passphrase")
    records = (corpus / "freeze.jsonl").read_text(encoding="utf-8")
    assert '"evaluation"' not in records
    assert holdout.open_spending(PASSPHRASE)


def test_a_crash_while_unmasking_still_leaves_the_bundle_spent(tmp_path, monkeypatch):
    """The spend lands between authentication and the plaintext, so no gap remains."""
    import corpus_harness

    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, _path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    sealed(corpus, manifest)
    holdout = repair_holdout(corpus, manifest)

    def explode(data, key):
        raise RuntimeError("died between the spend and the plaintext")

    monkeypatch.setattr(corpus_harness, "_mask", explode)
    with pytest.raises(RuntimeError):
        holdout.open_spending(PASSPHRASE)
    monkeypatch.undo()
    with pytest.raises(ScoringRefused, match="already been evaluated"):
        repair_holdout(corpus, manifest).open_spending(PASSPHRASE)


def test_a_sample_that_misstates_its_round_stops_the_seal(tmp_path):
    """A round's identity is not the directory it sits in."""
    corpus, manifest, root = fixture_corpus(tmp_path)
    freeze_round_four(corpus, manifest)
    sample, sample_path = drawn(tmp_path, corpus, manifest, root)
    answer_everything(corpus, sample)
    sample["round"] = 5
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    with pytest.raises(SystemExit, match="identity is not the directory"):
        seal.prepare(4, manifest)


def test_a_sealed_sample_that_misstates_its_round_fails_the_scoring_open(tmp_path):
    """Sealed around the check on purpose: the one open still refuses, and spends."""
    corpus, manifest, root = fixture_corpus(tmp_path)
    frozen = freeze_round_four(corpus, manifest)
    sample, sample_path = drawn(tmp_path, corpus, manifest, root)
    answers = answer_everything(corpus, sample)
    tampered = dict(sample, round=5)
    body = {
        "sample": tampered,
        "answers": {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(answers.glob("*.out"))
        },
        "adjudications": None,
    }
    holdout = repair_holdout(corpus, manifest)
    holdout.seal(
        json.dumps(body, sort_keys=True),
        PASSPHRASE,
        drawn_under=frozen["id"],
        binds=frozen["binds"],
    )
    holdout.freeze({"admission": "tampered-fixture"})
    with pytest.raises(ScoringRefused, match="identity is not its directory"):
        score_module.score_bundle(
            corpus / "repairs" / "round-4", root, manifest, passphrase=PASSPHRASE
        )
    records = [
        json.loads(line)
        for line in (corpus / "freeze.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (failed,) = [
        record for record in records if record["record"] == "evaluation_result"
    ]
    assert failed["result"]["state"] == "failed-evaluation"
