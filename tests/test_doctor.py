"""tests/test_doctor.py — doctor replays reality instead of listing files."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "cli"))
INSTALL = REPO / "scripts" / "install.py"


def installed_pyz(tmp_path):
    env = os.environ.copy()
    env.update({
        "HOME": str(tmp_path / "home"),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    })
    (tmp_path / "home").mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(INSTALL), "--cli"],
                   capture_output=True, env=env, check=True)
    return tmp_path / "home" / ".local" / "bin" / "semlf", env


def run_doctor(pyz, env, cwd):
    return subprocess.run([sys.executable, str(pyz), "doctor"],
                          capture_output=True, text=True, env=env, cwd=cwd)


def test_doctor_passes_on_a_healthy_install(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 0
    assert "platform:" in r.stdout
    assert "replay: ok" in r.stdout
    assert "doctor: ok" in r.stdout


def test_doctor_reports_provenance(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = run_doctor(pyz, env, tmp_path)
    assert "provenance: cli managed" in r.stdout
    pyz.write_bytes(pyz.read_bytes() + b"#patched\n")
    r = run_doctor(pyz, env, tmp_path)
    assert "edited" in r.stdout


def test_doctor_lists_the_excludes_in_force(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".semlf.ini").write_text(
        "[semlf]\nexclude =\n    vendor/\n    *.generated.md\n",
        encoding="utf-8")
    r = run_doctor(pyz, env, project)
    assert "vendor/" in r.stdout
    assert "*.generated.md" in r.stdout


def test_doctor_reports_the_config_long_limit_with_its_source(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".semlf.ini").write_text("[semlf]\nlong-limit = 80\n",
                                        encoding="utf-8")
    env.pop("SEMLF_LONG_LINE", None)
    r = run_doctor(pyz, env, project)
    assert "long-limit: 80 (.semlf.ini)" in r.stdout


def test_doctor_labels_an_invalid_env_limit_as_fallthrough(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".semlf.ini").write_text("[semlf]\nlong-limit = 80\n",
                                        encoding="utf-8")
    env["SEMLF_LONG_LINE"] = "not-a-number"
    r = run_doctor(pyz, env, project)
    assert "long-limit: 80 (.semlf.ini)" in r.stdout


def test_doctor_survives_hostile_state(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    (artifacts / "cli.json").write_text(json.dumps(["not", "a", "dict"]),
                                        encoding="utf-8")
    (artifacts / "codex-skill.json").write_text("7", encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_doctor_warns_on_a_record_for_the_wrong_path(tmp_path):
    # A hostile-but-valid record must never vouch for an arbitrary file:
    # doctor classifies against the expected destination,
    # so a digest match at a foreign path only ever yields a mismatch warning.
    pyz, env = installed_pyz(tmp_path)
    import hashlib
    rogue = tmp_path / "rogue-file"
    rogue.write_bytes(b"whatever")
    entry = {"path": str(rogue),
             "sha256": hashlib.sha256(b"whatever").hexdigest(),
             "version": "0.6.0"}
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    (artifacts / "cli.json").write_text(json.dumps(entry), encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert "managed" not in [
        word for line in r.stdout.splitlines()
        if line.startswith("provenance: cli") for word in line.split()]
    assert "expected" in r.stdout


def test_doctor_fails_a_hook_that_blocks_everything(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    fake = tmp_path / "check_linefeeds.py"
    fake.write_text("import sys; sys.stderr.write('fused'); sys.exit(2)\n",
                    encoding="utf-8")
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    # The literal python3 launcher is what the predicate requires;
    # the test environment resolves it from PATH like a real install would.
    command = f'python3 "{fake}" --hook codex'
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "apply_patch",
         "hooks": [{"type": "command", "command": command}]}
    ]}}), encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 1
    assert "clean patch expected exit 0" in r.stdout


def test_doctor_fails_when_the_replay_misbehaves(tmp_path, monkeypatch):
    # Full isolation for a direct in-process call:
    # without it, doctor's codex check would resolve the developer's real CODEX_HOME and execute a live installed hook from inside a unit test.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)
    from semlf import doctor
    fake = tmp_path / "fake-semlf"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    rc = doctor.run([], artifact=str(fake))
    assert rc == 1


def test_doctor_replays_an_installed_codex_hook(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker = REPO / "scripts" / "check_linefeeds.py"
    command = f'python3 "{checker}" --hook codex'
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "apply_patch",
         "hooks": [{"type": "command", "command": command}]}
    ]}}), encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 0
    assert "codex hook: ok" in r.stdout


def test_doctor_certifies_every_owned_hook_not_just_the_first(tmp_path):
    # One healthy owned entry must not vouch for a broken sibling:
    # the installer updates every owned entry, so doctor certifies them all.
    pyz, env = installed_pyz(tmp_path)
    good = REPO / "scripts" / "check_linefeeds.py"
    broken = tmp_path / "check_linefeeds.py"   # basename must match to be owned
    broken.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    entry = lambda path: {"matcher": "apply_patch", "hooks": [
        {"type": "command", "command": f'python3 "{path}" --hook codex'}]}
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        entry(good), entry(broken)]}}), encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 1
    assert "codex hook: FAIL" in r.stdout


def test_doctor_never_classifies_a_symlinked_destination(tmp_path):
    # Integration:
    # a symlink planted at the expected destination is never followed and never managed.
    pyz, env = installed_pyz(tmp_path)
    real = tmp_path / "moved-semlf"
    real.write_bytes(pyz.read_bytes())
    pyz.unlink()
    pyz.symlink_to(real)
    r = run_doctor(real, env, tmp_path)
    cli_lines = [l for l in r.stdout.splitlines()
                 if l.startswith("provenance: cli")]
    assert cli_lines and "managed" not in cli_lines[0]


def test_provenance_classifies_before_any_resolution(tmp_path, monkeypatch):
    # Causal:
    # realpath is booby-trapped to fail unless the guarded classifier has already run for this destination,
    # so moving the diagnostic comparison above classify_entry turns this test red —
    # the label alone could not detect that regression.
    from semlf import doctor, manifest
    calls = []
    real_classify = manifest.classify_entry
    def tracking(entry, dest):
        calls.append("classify")
        return real_classify(entry, dest)
    monkeypatch.setattr(manifest, "classify_entry", tracking)
    real_realpath = doctor.os.path.realpath
    def guarded_realpath(p):
        assert "classify" in calls, "realpath ran before classification"
        return real_realpath(p)
    monkeypatch.setattr(doctor.os.path, "realpath", guarded_realpath)
    real = tmp_path / "real"
    real.write_bytes(b"x")
    link = tmp_path / "dest"
    link.symlink_to(real)
    entry = {"path": str(link),
             "sha256": manifest.sha256_bytes(b"x"),
             "version": "1"}
    line = doctor._provenance_line("cli", entry, link)
    assert "managed" not in line


def test_doctor_rejects_arguments(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = subprocess.run([sys.executable, str(pyz), "doctor", "--json"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 64
