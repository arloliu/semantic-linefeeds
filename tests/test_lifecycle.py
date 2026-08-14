"""tests/test_lifecycle.py — preflight admits everything or nothing;
apply converges under any interruption."""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import classify, lifecycle, manifest, registry


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    (tmp_path / "home").mkdir()
    return tmp_path


def plan_names(targets, force=False):
    planned, refusals = [], []
    snapshot = manifest.load()
    destinations = lifecycle.payload_destinations()
    for name in targets:
        lifecycle.plan_file(name, force, snapshot, destinations,
                            planned, refusals)
    return planned, refusals


def test_artifact_version_matches_the_core(home):
    import check_linefeeds
    assert lifecycle.artifact_version() == check_linefeeds.__version__


def test_fresh_apply_publishes_and_records(home, capsys):
    planned, refusals = plan_names(["checker", "readme"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    data_dir = manifest.semlf_data_dir()
    assert ((data_dir / "check_linefeeds.py").read_bytes()
            == registry.payload_bytes("checker"))
    assert (data_dir / "README.md").read_bytes() == registry.payload_bytes("readme")
    assert manifest.classify("checker", data_dir / "check_linefeeds.py") == "managed"
    assert manifest.classify("readme", data_dir / "README.md") == "managed"


def test_rerun_is_idempotent_and_adopts_a_missing_record(home, capsys):
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    manifest.forget("checker")
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    before = dest.read_bytes()
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == before
    assert manifest.classify("checker", dest) == "managed"


def test_one_refusing_artifact_aborts_before_any_write(home, capsys):
    data_dir = manifest.semlf_data_dir()
    data_dir.mkdir(parents=True)
    (data_dir / "README.md").mkdir()  # object-state refusal on readme
    planned, refusals = plan_names(["checker", "readme"])
    assert refusals
    # The engine's caller must not apply when refusals exist;
    # assert nothing was written during planning itself.
    assert not (data_dir / "check_linefeeds.py").exists()


def test_record_side_preflight_refuses_before_any_write(home, capsys):
    state_dir = Path(os.environ["XDG_STATE_HOME"])
    state_dir.mkdir(parents=True)
    (state_dir / "semlf").write_text("a file squatting on the state root")
    planned, refusals = plan_names(["checker"])
    assert refusals and "not a directory" in refusals[0]


def test_half_state_is_reported_by_name_and_a_rerun_converges(
        home, capsys, monkeypatch):
    planned, _ = plan_names(["checker"])
    real_record = manifest.record

    def boom(*args, **kwargs):
        raise OSError("record write failed")

    monkeypatch.setattr(manifest, "record", boom)
    rc = lifecycle.apply_plan(planned)
    err = capsys.readouterr().err
    assert rc == 1
    assert "published" in err and "not record" in err.replace("recorded", "record")
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    assert dest.read_bytes() == registry.payload_bytes("checker")
    monkeypatch.setattr(manifest, "record", real_record)
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert manifest.classify("checker", dest) == "managed"


def test_crossed_interleavings_fail_closed(home):
    """Destination and record written by different runs classify as edited —
    degraded classification, never a silent overwrite."""
    dest = manifest.semlf_data_dir()
    dest.mkdir(parents=True)
    checker = dest / "check_linefeeds.py"
    # (a) destination replaced, record stale.
    checker.write_bytes(b"new bytes the record does not describe\n")
    manifest.record("checker", checker, "0.6.0",
                    manifest.sha256_bytes(b"what an old run staged\n"))
    v = classify.classify_artifact(manifest.load()["checker"], checker,
                                   b"rendered\n", "0.7.0", False)
    assert (v.state, v.action) == ("edited", "refuse")
    # (b) record refreshed, destination old.
    manifest.record("checker", checker, "0.7.0",
                    manifest.sha256_bytes(b"rendered\n"))
    v = classify.classify_artifact(manifest.load()["checker"], checker,
                                   b"rendered but dest still old\n", "0.7.0", False)
    assert (v.state, v.action) == ("edited", "refuse")


def test_forced_replace_of_an_edited_file_takes_an_exclusive_backup(
        home, capsys):
    dest_dir = manifest.semlf_data_dir()
    dest_dir.mkdir(parents=True)
    checker = dest_dir / "check_linefeeds.py"
    checker.write_bytes(b"hand-patched\n")
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert checker.read_bytes() == registry.payload_bytes("checker")
    assert (dest_dir / "check_linefeeds.py.bak").read_bytes() == b"hand-patched\n"


def test_a_failed_publication_after_backup_keeps_the_rerun_convergent(
        home, capsys, monkeypatch):
    """A forced backup-replace whose publication fails must not leave an occupied backup slot behind:
    the rerun would refuse forever."""
    dest_dir = manifest.semlf_data_dir()
    dest_dir.mkdir(parents=True)
    checker = dest_dir / "check_linefeeds.py"
    checker.write_bytes(b"hand-patched\n")
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    real_publish = lifecycle.publish_bytes

    def boom(dest, data):
        raise OSError("publication failed")

    monkeypatch.setattr(lifecycle, "publish_bytes", boom)
    assert lifecycle.apply_plan(planned) == 1
    assert checker.read_bytes() == b"hand-patched\n"
    assert not (dest_dir / "check_linefeeds.py.bak").exists()
    monkeypatch.setattr(lifecycle, "publish_bytes", real_publish)
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert checker.read_bytes() == registry.payload_bytes("checker")
    assert (dest_dir / "check_linefeeds.py.bak").read_bytes() == \
        b"hand-patched\n"


def test_adoption_record_failure_reports_the_half_state(
        home, capsys, monkeypatch):
    """Exact rendering with a failing record write is the published-but-not-recorded half-state, not a generic error."""
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    manifest.forget("checker")
    planned, refusals = plan_names(["checker"])
    assert refusals == []

    def boom(*args, **kwargs):
        raise OSError("record failed")

    monkeypatch.setattr(manifest, "record", boom)
    rc = lifecycle.apply_plan(planned)
    err = capsys.readouterr().err
    assert rc == 1
    assert "already correct" in err


def test_managed_replace_skips_the_backup(home, capsys):
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    # Simulate an older managed release at the destination.
    dest.write_bytes(b"an older managed rendering\n")
    manifest.record("checker", dest, "0.0.1",
                    manifest.sha256_bytes(b"an older managed rendering\n"))
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == registry.payload_bytes("checker")
    assert not (manifest.semlf_data_dir() / "check_linefeeds.py.bak").exists()


def test_adopt_rerecords_the_running_version_on_identical_bytes(
        home, capsys):
    """Adoption deliberately overwrites even a newer recorded version.

    Exact-byte content is checked before the managed-version guard,
    so a record claiming a newer release than this artifact is still adopted —
    and re-recorded at the running version —
    when the bytes on disk are already exactly what this run would publish.
    There is nothing left for a newer-guard to protect:
    the content is not being replaced, only its provenance is refreshed.
    """
    planned, _ = plan_names(["readme"])
    assert lifecycle.apply_plan(planned) == 0
    dest = manifest.semlf_data_dir() / "README.md"
    on_disk = dest.read_bytes()
    manifest.record("readme", dest, "99.0.0",
                    manifest.sha256_bytes(on_disk))
    planned, refusals = plan_names(["readme"])
    assert refusals == []
    assert planned[0].verdict.state == "exact"
    assert planned[0].verdict.action == "adopt"
    assert lifecycle.apply_plan(planned) == 0
    assert manifest.load()["readme"]["version"] == lifecycle.artifact_version()


def hook_path():
    return Path(os.environ["CODEX_HOME"]) / "hooks.json"


def plan_hook():
    planned, refusals = [], []
    lifecycle.plan_codex_hook(planned, refusals)
    return planned, refusals


def test_hook_plan_creates_a_fresh_hooks_json(home, capsys):
    planned, refusals = plan_hook()
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    import json
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    owned = manifest.owned_codex_hooks(data)
    assert len(owned) == 1
    checker = str(manifest.semlf_data_dir() / "check_linefeeds.py")
    assert owned[0][1] == checker


def test_hook_plan_updates_a_stale_path_and_preserves_foreign_entries(
        home, capsys):
    import json
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "shell",
         "hooks": [{"type": "command", "command": "echo hi"}]},
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": 'python3 "/old/clone/scripts/check_linefeeds.py"'
                        ' --hook codex'}]},
    ]}}), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    lifecycle.apply_plan(planned)
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    commands = [h["hooks"][0]["command"]
                for h in data["hooks"]["PostToolUse"]]
    assert commands[0] == "echo hi"
    assert "/old/clone/" not in commands[1]
    assert str(manifest.semlf_data_dir()) in commands[1]


def test_hook_plan_noops_when_current(home, capsys):
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    before = hook_path().read_text(encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    assert all(item.do is None for item in planned)
    lifecycle.apply_plan(planned)
    assert hook_path().read_text(encoding="utf-8") == before


def test_hook_plan_refuses_unparseable_json(home):
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text("{not json", encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals and "hand" in refusals[0]


def test_hook_plan_is_total_over_hostile_parseable_shapes(home, capsys):
    """{"hooks": 7} and a non-dict block must be planned around and preserved exactly,
    never raise TypeError mid-preflight."""
    import json
    hook_path().parent.mkdir(parents=True)
    hostile = {"hooks": {"PostToolUse": [
        None, {"hooks": 7}, {"matcher": "apply_patch"}]}}
    hook_path().write_text(json.dumps(hostile), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    lifecycle.apply_plan(planned)
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    post = data["hooks"]["PostToolUse"]
    assert post[:3] == hostile["hooks"]["PostToolUse"]
    assert len(manifest.owned_codex_hooks(data)) == 1


def test_an_up_to_date_hook_ignores_a_hostile_backup_slot(home, capsys):
    """A no-op writes nothing,
    so a symlink squatting on hooks.json.bak must not break clean idempotence."""
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    bak = hook_path().with_name("hooks.json.bak")
    if bak.exists():
        bak.unlink()
    bak.symlink_to(hook_path().parent / "elsewhere")
    planned, refusals = plan_hook()
    assert refusals == []
    assert all(item.do is None for item in planned)
    # A stale hook with the same hostile slot still refuses.
    import json
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] = (
        'python3 "/old/check_linefeeds.py" --hook codex')
    hook_path().write_text(json.dumps(data), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals and ".bak" in refusals[0]


def test_hook_merge_backs_up_the_shared_file(home, capsys):
    """Shared merged files keep their .bak —
    the skip-backups rule is for provenance-managed single files only."""
    import json
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "shell",
         "hooks": [{"type": "command", "command": "echo hi"}]}]}}),
        encoding="utf-8")
    before = hook_path().read_bytes()
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    bak = hook_path().with_name("hooks.json.bak")
    assert bak.read_bytes() == before


def test_agentsmd_plan_writes_and_reruns_clean(home, tmp_path, capsys):
    target = tmp_path / "AGENTS.md"
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals == []
    lifecycle.apply_plan(planned)
    text = target.read_text(encoding="utf-8")
    assert lifecycle.SENTINEL_OPEN in text and lifecycle.SENTINEL_CLOSE in text
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals == []
    assert all(item.do is None for item in planned)


def test_agentsmd_plan_refuses_a_broken_sentinel_pair(home, tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(lifecycle.SENTINEL_OPEN + "\nno close",
                      encoding="utf-8")
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals and "sentinel" in refusals[0]


def test_agentsmd_up_to_date_note_prints_at_plan_time(
        home, tmp_path, capsys, monkeypatch):
    """The up-to-date leg has no `do` closure for apply_plan to print through,
    so plan_agentsmd prints its advisory note immediately —
    a deliberate plan-time disclosure,
    not a stray apply-time side effect, and never an action to undo on a later refusal."""
    target = tmp_path / "AGENTS.md"
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    lifecycle.apply_plan(planned)
    capsys.readouterr()  # discard the first write's own output

    monkeypatch.setattr(lifecycle.shutil, "which", lambda name: None)
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    out = capsys.readouterr().out
    assert "not on PATH" in out
    assert refusals == []
    assert len(planned) == 1 and planned[0].do is None

    monkeypatch.setattr(lifecycle.shutil, "which",
                        lambda name: "/usr/bin/semlf")
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    out = capsys.readouterr().out
    assert "not on PATH" not in out
    assert len(planned) == 1 and planned[0].do is None


@pytest.mark.parametrize("name", ["checker", "readme", "codex-skill",
                                  "opencode-plugin",
                                  "opencode-checker"])
def test_every_registry_row_reaches_the_classifier(home, name, capsys):
    """Each recorded row classifies through its own registry destination and rendering —
    edited refuses, managed-older replaces, exact adopts —
    so no row can bypass the matrix."""
    targets = ["codex", "opencode"]
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert refusals == []
    lifecycle.apply_plan(planned)
    dest = lifecycle.payload_destinations()[name]
    dest.write_bytes(b"hand-patched\n")
    manifest.forget(name)
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert any(str(dest) in r for r in refusals)
    manifest.record(name, dest, "0.0.1",
                    manifest.sha256_bytes(b"hand-patched\n"))
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == lifecycle.rendered_bytes(name)
    assert manifest.classify(name, dest) == "managed"


def test_tty_prompt_answered_n_declines(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    rc = lifecycle.install_command([])
    assert rc == 1
    assert not (manifest.semlf_data_dir() / "check_linefeeds.py").exists()


def test_tty_prompt_eof_declines(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert lifecycle.install_command([]) == 1


def test_tty_prompt_y_applies(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert lifecycle.install_command([]) == 0
    assert (manifest.semlf_data_dir() / "check_linefeeds.py").exists()


def test_a_transform_error_during_rendering_becomes_a_refusal(
        home, monkeypatch):
    """A canonical-source edit that breaks a rewrite must refuse the plan cleanly,
    never escape planning as a raw traceback."""
    def boom(data_dir):
        raise registry.TransformError("boom")

    monkeypatch.setattr(registry, "render_codex_skill", boom)
    planned, refusals = lifecycle.plan_install(["codex"], None, False)
    assert any("codex-skill" in r and "boom" in r for r in refusals)
    assert not any(item.name == "codex-skill" for item in planned)


def test_dry_run_reports_a_transform_error_as_a_would_be_refusal(
        home, monkeypatch, capsys):
    def boom(data_dir):
        raise registry.TransformError("boom")

    monkeypatch.setattr(registry, "render_codex_skill", boom)
    rc = lifecycle.install_command(["codex", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would refuse" in out
