"""tests/test_manifest.py — provenance identity and its failure directions."""
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
from semlf import manifest


def test_state_path_honors_xdg_state_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert manifest.artifact_state_path("cli") == (
        tmp_path / "state" / "semlf" / "artifacts" / "cli.json")


def record_current(name, artifact, version="0.6.0"):
    manifest.record(name, artifact, version,
                    manifest.sha256_bytes(artifact.read_bytes()))


def test_record_then_classify_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"published bytes")
    record_current("cli", artifact)
    assert manifest.classify("cli", artifact) == "managed"
    entry = manifest.load()["cli"]
    assert entry["version"] == "0.6.0"
    assert entry["path"] == str(artifact)


def test_edited_bytes_classify_as_edited(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"published bytes")
    record_current("cli", artifact)
    artifact.write_bytes(b"published bytes, then edited")
    assert manifest.classify("cli", artifact) == "edited"


def test_a_record_never_authorizes_a_different_path(tmp_path, monkeypatch):
    # The stale-entry case:
    # a digest match without path identity is unrecorded, so a moved HOME can never bless action elsewhere.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"published bytes")
    record_current("cli", artifact)
    twin = tmp_path / "elsewhere"
    twin.write_bytes(b"published bytes")
    assert manifest.classify("cli", twin) == "unrecorded"


def test_a_symlink_destination_is_never_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    real = tmp_path / "real"
    real.write_bytes(b"published bytes")
    link = tmp_path / "semlf"
    link.symlink_to(real)
    manifest.record("cli", link, "0.6.0",
                    manifest.sha256_bytes(b"published bytes"))
    assert manifest.classify("cli", link) == "unrecorded"


def test_invalid_entries_are_dropped_at_load(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    bad = {
        "cli": {"path": "/x", "sha256": "SHOUTING-NOT-HEX", "version": "1"},
        "codex-skill": ["not", "a", "dict"],
        "opencode-plugin": {"path": "/x"},
    }
    for name, entry in bad.items():
        state = manifest.artifact_state_path(name)
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(entry), encoding="utf-8")
    assert manifest.load() == {}


def test_valid_entry_rejects_an_unencodable_surrogate_path():
    # An unpaired UTF-16 surrogate can reach a Python string from JSON's \uXXXX escape,
    # and no OS filesystem call can ever open, stat, or otherwise identify a destination by that string.
    # Schema validity must reject it here, at load, rather than let it survive into a classification or diagnostic call downstream (fix-report P0-2b).
    entry = {"path": "/tmp/evil\ud800dir/semlf",
             "sha256": "a" * 64, "version": "0.6.0"}
    assert manifest._valid_entry(entry) is False


def test_unknown_artifact_names_are_never_read(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"x")
    rogue = manifest.artifact_state_path("cli").parent / "rogue.json"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_text(json.dumps({
        "path": str(artifact),
        "sha256": manifest.sha256_bytes(b"x"),
        "version": "0.6.0"}), encoding="utf-8")
    assert "rogue" not in manifest.load()


def test_state_reader_never_follows_or_oversizes(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert manifest.read_state_json(link) is None
    big = tmp_path / "big.json"
    big.write_bytes(b"[" + b"1," * 40000 + b"1]")
    assert manifest.read_state_json(big) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no mkfifo")
def test_state_reader_rejects_a_fifo_without_blocking(tmp_path):
    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    assert manifest.read_state_json(fifo) is None  # lstat rejects, no open


def test_read_regular_bytes_is_total_over_a_nul_carrying_path():
    # os.lstat/os.open raise ValueError ("embedded null byte") for a NUL-carrying path, not OSError;
    # "None for any trouble" must cover that too, since Task 3 and Task 5 consume this primitive directly over less-gated paths.
    assert manifest.read_regular_bytes("/tmp/\x00bad", 100) is None
    assert manifest.read_state_json("/tmp/\x00bad") is None


def test_state_reader_is_total_over_hostile_json(tmp_path):
    deep = tmp_path / "deep.json"
    deep.write_bytes(b"[" * 30000 + b"]" * 30000)
    assert manifest.read_state_json(deep) is None  # RecursionError is trouble


def test_rogue_artifact_names_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    for rogue in ("rogue", "../rogue", "cli/../../rogue", ""):
        with pytest.raises(ValueError):
            manifest.artifact_state_path(rogue)
    assert not (tmp_path / "state").exists()


def test_a_nul_path_entry_is_unrecorded_not_a_crash(tmp_path):
    entry = {"path": "/x/\x00/y", "sha256": "0" * 64, "version": "1"}
    probe = tmp_path / "probe"
    probe.write_bytes(b"x")
    assert manifest.classify_entry(entry, probe) == "unrecorded"


def test_missing_entry_and_missing_file_are_unrecorded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"x")
    assert manifest.classify("cli", artifact) == "unrecorded"
    record_current("cli", artifact)
    assert manifest.classify("cli", tmp_path / "gone") == "unrecorded"


def test_malformed_state_degrades_to_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    state = manifest.artifact_state_path("cli")
    state.parent.mkdir(parents=True)
    state.write_text("{not json", encoding="utf-8")
    assert manifest.load() == {}
    artifact = tmp_path / "semlf"
    artifact.write_bytes(b"x")
    assert manifest.classify("cli", artifact) == "unrecorded"


def test_codex_ownership_is_structural_not_substring():
    ours = {"type": "command",
            "command": 'python3 "/some/repo/scripts/check_linefeeds.py" --hook codex'}
    assert manifest.parse_managed_codex_hook("apply_patch", ours) is not None
    def cmd(text):
        return {"type": "command", "command": text}
    foreign_hooks = [
        cmd("echo check_linefeeds.py"),
        cmd('bash "/tmp/notcheck_linefeeds.py" --hook codex'),
        cmd('python3 "/elsewhere/notcheck_linefeeds.py" --hook codex'),
        cmd('python3 "/elsewhere/check_linefeeds.py" --hook claude'),
        cmd('python3 "/elsewhere/check_linefeeds.py" --hook codex extra'),
        cmd("unclosed 'quote check_linefeeds.py --hook codex"),
        {"type": "script", "command": ours["command"]},
        {"type": "command", "command": 7},
        "not-a-dict",
    ]
    for hook in foreign_hooks:
        assert manifest.parse_managed_codex_hook("apply_patch", hook) is None
    assert manifest.parse_managed_codex_hook("shell", ours) is None


def test_forget_removes_one_entry_and_keeps_the_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    record_current("cli", a)
    record_current("codex-skill", b)
    manifest.forget("cli")
    kept = manifest.load()
    assert "cli" not in kept
    assert "codex-skill" in kept


def test_writers_cannot_interfere_across_artifacts(tmp_path, monkeypatch):
    # The per-artifact layout is the concurrency ruling:
    # recording one name must not even read another name's state file, so a stale writer can neither drop nor resurrect a sibling entry.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    record_current("cli", a)
    record_current("codex-skill", b)
    manifest.forget("cli")
    record_current("opencode-plugin", b)  # a later, unrelated record
    assert "cli" not in manifest.load()   # the forgotten name stays gone
