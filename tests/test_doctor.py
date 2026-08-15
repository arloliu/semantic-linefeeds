"""tests/test_doctor.py — doctor replays reality instead of listing files."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "cli"))
INSTALL = REPO / "scripts" / "install.py"


def installed_pyz(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "CODEX_HOME": str(tmp_path / "codex"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )
    (tmp_path / "home").mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, str(INSTALL), "--cli"],
        capture_output=True,
        env=env,
        check=True,
    )
    return tmp_path / "home" / ".local" / "bin" / "semlf", env


def run_doctor(pyz, env, cwd):
    return subprocess.run(
        [sys.executable, str(pyz), "doctor"],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


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
        "[semlf]\nexclude =\n    vendor/\n    *.generated.md\n", encoding="utf-8"
    )
    r = run_doctor(pyz, env, project)
    assert "vendor/" in r.stdout
    assert "*.generated.md" in r.stdout


def test_doctor_reports_the_config_long_limit_with_its_source(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".semlf.ini").write_text("[semlf]\nlong-limit = 80\n", encoding="utf-8")
    env.pop("SEMLF_LONG_LINE", None)
    r = run_doctor(pyz, env, project)
    assert "long-limit: 80 (.semlf.ini)" in r.stdout


def test_doctor_labels_an_invalid_env_limit_as_fallthrough(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".semlf.ini").write_text("[semlf]\nlong-limit = 80\n", encoding="utf-8")
    env["SEMLF_LONG_LINE"] = "not-a-number"
    r = run_doctor(pyz, env, project)
    assert "long-limit: 80 (.semlf.ini)" in r.stdout


def test_doctor_survives_hostile_state(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    (artifacts / "cli.json").write_text(
        json.dumps(["not", "a", "dict"]), encoding="utf-8"
    )
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
    entry = {
        "path": str(rogue),
        "sha256": hashlib.sha256(b"whatever").hexdigest(),
        "version": "0.6.0",
    }
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    (artifacts / "cli.json").write_text(json.dumps(entry), encoding="utf-8")
    r = run_doctor(pyz, env, tmp_path)
    assert "managed" not in [
        word
        for line in r.stdout.splitlines()
        if line.startswith("provenance: cli")
        for word in line.split()
    ]
    assert "expected" in r.stdout


def test_doctor_fails_a_hook_that_blocks_everything(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    fake = tmp_path / "check_linefeeds.py"
    fake.write_text(
        "import sys; sys.stderr.write('fused'); sys.exit(2)\n", encoding="utf-8"
    )
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    # The literal python3 launcher is what the predicate requires;
    # the test environment resolves it from PATH like a real install would.
    command = f'python3 "{fake}" --hook codex'
    hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "apply_patch",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 1
    assert "clean patch expected exit 0" in r.stdout


def test_doctor_survives_a_nul_carrying_checker_path(tmp_path):
    # A hostile hooks.json can carry a NUL byte inside an otherwise owned-shaped command;
    # shlex handles it fine, but os.lstat raises ValueError ("embedded null byte"), not OSError.
    # doctor's checker gate must catch that too and fail the check, never traceback (fix-report P0-2a).
    # Built as JSON directly rather than via write_text on a Python string literal:
    # json.dumps renders the embedded NUL as a JSON escape sequence,
    # and json.loads decodes it right back to a real NUL byte,
    # so this is the same hostile bytes an attacker-controlled hooks.json would carry on disk.
    pyz, env = installed_pyz(tmp_path)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker_path = "/tmp/evil\x00dir/check_linefeeds.py"
    command = f'python3 "{checker_path}" --hook codex'
    payload = json.dumps(
        {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "apply_patch",
                        "hooks": [{"type": "command", "command": command}],
                    }
                ]
            }
        }
    )
    hooks.write_text(payload, encoding="utf-8")
    assert (
        "\x00" in json.loads(payload)["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    )
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "codex hook: FAIL" in r.stdout


def test_doctor_survives_a_surrogate_checker_path_in_hooks_json(tmp_path):
    # A hostile hooks.json can carry an unpaired UTF-16 surrogate inside an otherwise owned-shaped checker path;
    # JSON's \uXXXX escape admits any codepoint, including a lone surrogate that no UTF-8 stream can encode.
    # Built the same way as the NUL case above — a plain-ASCII JSON escape on disk that json.loads decodes right back to the real hostile character —
    # so this is the same bytes an attacker-controlled hooks.json would carry on disk.
    # os.lstat correctly raises (UnicodeEncodeError, a ValueError subclass) for that path,
    # but the FAIL message must not re-interpolate the same hostile string unguarded,
    # or printing the diagnosis crashes the diagnosis (fix-report P0-2a).
    # PYTHONIOENCODING pins the child's stdout to strict UTF-8 so the test cannot pass by accident on a locale that already tolerates surrogates.
    pyz, env = installed_pyz(tmp_path)
    env["PYTHONIOENCODING"] = "utf-8:strict"
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker_path = "/tmp/evil\ud800dir/check_linefeeds.py"
    command = f'python3 "{checker_path}" --hook codex'
    payload = json.dumps(
        {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "apply_patch",
                        "hooks": [{"type": "command", "command": command}],
                    }
                ]
            }
        }
    )
    hooks.write_text(payload, encoding="utf-8")
    assert "\\ud800" in payload
    assert (
        json.loads(payload)["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == command
    )
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "codex hook: FAIL" in r.stdout


def test_doctor_drops_a_surrogate_provenance_path_and_runs_clean(tmp_path):
    # A hostile cli.json state entry can carry the same unpaired surrogate in its recorded path, via a JSON \uXXXX escape.
    # manifest._valid_entry now probes os.fsencode and rejects any path the filesystem encoding cannot represent,
    # so this entry never survives load():
    # it is dropped at the schema gate, never reaches a provenance print, and doctor finishes clean rather than crashing on it (fix-report P0-2b).
    pyz, env = installed_pyz(tmp_path)
    entry = {"path": "/tmp/evil\ud800dir/semlf", "sha256": "a" * 64, "version": "0.6.0"}
    payload = json.dumps(entry)
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "cli.json").write_text(payload, encoding="utf-8")
    assert "\\ud800" in payload
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr
    assert "provenance: cli" not in r.stdout


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
    _install_via_semlf(tmp_path, env)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker = REPO / "scripts" / "check_linefeeds.py"
    command = f'python3 "{checker}" --hook codex'
    hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "apply_patch",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    r = run_doctor(pyz, env, tmp_path)
    assert r.returncode == 0
    assert "codex hook: ok" in r.stdout


def test_doctor_certifies_every_owned_hook_not_just_the_first(tmp_path):
    # One healthy owned entry must not vouch for a broken sibling:
    # the installer updates every owned entry, so doctor certifies them all.
    pyz, env = installed_pyz(tmp_path)
    good = REPO / "scripts" / "check_linefeeds.py"
    broken = tmp_path / "check_linefeeds.py"  # basename must match to be owned
    broken.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)

    def entry(path):
        return {
            "matcher": "apply_patch",
            "hooks": [{"type": "command", "command": f'python3 "{path}" --hook codex'}],
        }

    hooks.write_text(
        json.dumps({"hooks": {"PostToolUse": [entry(good), entry(broken)]}}),
        encoding="utf-8",
    )
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
    cli_lines = [
        line for line in r.stdout.splitlines() if line.startswith("provenance: cli")
    ]
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
    entry = {"path": str(link), "sha256": manifest.sha256_bytes(b"x"), "version": "1"}
    line = doctor._provenance_line("cli", entry, link)
    assert "managed" not in line


def test_doctor_rejects_arguments(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = subprocess.run(
        [sys.executable, str(pyz), "doctor", "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 64


def _install_via_semlf(tmp_path, env, target="codex"):
    bootstrap = (
        "import sys; sys.path[:0] = [{!r}, {!r}]; "
        "from semlf.cli import main; "
        "sys.exit(main(sys.argv[1:]))".format(str(REPO / "cli"), str(REPO / "scripts"))
    )
    r = subprocess.run(
        [sys.executable, "-c", bootstrap, "install", target],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return r


def test_doctor_passes_with_current_payloads(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_via_semlf(tmp_path, env)
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "payload" in r.stdout


def test_doctor_fails_on_an_expected_payload_mismatch(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_via_semlf(tmp_path, env)
    checker = Path(env["XDG_DATA_HOME"]) / "semlf" / "check_linefeeds.py"
    checker.write_text(
        checker.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8"
    )
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 1
    assert "payload" in r.stdout and "FAIL" in r.stdout


def test_doctor_fails_an_installed_hook_with_no_published_payload(tmp_path):
    """An owned hook makes the payloads expected;
    a machine that has the hook but never published them is the migration half-state doctor exists to flag."""
    pyz, env = installed_pyz(tmp_path)
    hooks = Path(env["CODEX_HOME"]) / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker = Path(env["XDG_DATA_HOME"]) / "semlf" / "check_linefeeds.py"
    hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "apply_patch",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f'python3 "{checker}" --hook codex',
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 1
    assert "payload" in r.stdout and "FAIL" in r.stdout


def test_doctor_warns_but_passes_on_no_consumer_leftovers(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_via_semlf(tmp_path, env)
    # Remove the consumer but keep the payloads
    # (the uninstall verb's deliberate leftover policy).
    hooks = Path(env["CODEX_HOME"]) / "hooks.json"
    hooks.write_text('{"hooks": {"PostToolUse": []}}', encoding="utf-8")
    skill = Path(env["HOME"]) / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    if skill.exists():
        skill.unlink()
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout
    assert "warn" in r.stdout.lower()
    assert str(Path(env["XDG_DATA_HOME"]) / "semlf") in r.stdout


def test_doctor_passes_on_a_machine_with_no_integrations(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr


def test_doctor_leftover_pointer_names_each_real_path(tmp_path):
    """The leftover pointer derives from each identity row's own destination:
    an opencode-checker leftover is named by its path in the opencode plugins directory,
    not by a hand-maintained path.

    checker and readme are shared rows now,
    so losing opencode's own consumer signal leaves them without a consumer too,
    and their own destination — the neutral data root — legitimately joins the leftover list alongside it.
    """
    pyz, env = installed_pyz(tmp_path)
    _install_via_semlf(tmp_path, env, "opencode")
    plugins = Path(env["XDG_CONFIG_HOME"]) / "opencode" / "plugins"
    (plugins / "semantic-linefeeds.ts").unlink()
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout
    assert "warn" in r.stdout.lower()
    assert str(plugins / "check_linefeeds.py") in r.stdout
