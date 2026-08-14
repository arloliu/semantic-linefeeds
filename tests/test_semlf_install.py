"""tests/test_semlf_install.py — the package door's command surface."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

BOOTSTRAP = ("import sys; sys.path[:0] = [%r, %r]; "
             "from semlf.cli import main; sys.exit(main(sys.argv[1:]))"
             % (str(REPO / "cli"), str(REPO / "scripts")))


def isolated_env(tmp_path, path=""):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home),
            "CODEX_HOME": str(tmp_path / "codex"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PATH": path}


def run_semlf(args, env_overrides, stdin_text=""):
    env = os.environ.copy()
    env["PATH"] = ""
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", BOOTSTRAP] + args,
                          input=stdin_text, capture_output=True,
                          text=True, env=env, timeout=60)


def data_root(tmp_path):
    return tmp_path / "data" / "semlf"


def test_named_target_is_consent_and_applies(tmp_path):
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert (data_root(tmp_path) / "README.md").exists()
    hooks = json.loads((tmp_path / "codex" / "hooks.json").read_text())
    command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(data_root(tmp_path) / "check_linefeeds.py") in command
    skill = tmp_path / "home" / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert str(data_root(tmp_path) / "check_linefeeds.py") in body
    assert str(data_root(tmp_path) / "README.md") in body


def test_apply_order_puts_neutral_payloads_first(tmp_path):
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    out = r.stdout
    assert out.index("checker") < out.index("codex hook")


def test_non_tty_detection_without_yes_prints_plan_and_exits_one(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "codex").mkdir()  # codex detected by directory evidence
    r = run_semlf(["install"], env)
    assert r.returncode == 1
    assert "--yes" in r.stdout + r.stderr
    assert not data_root(tmp_path).exists()


def test_yes_applies_in_detection_mode(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "codex").mkdir()
    r = run_semlf(["install", "--yes"], env)
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").exists()


def test_zero_detection_is_an_explicit_noop(tmp_path):
    r = run_semlf(["install"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "no supported agents detected" in r.stdout.lower()


def test_dry_run_dominates_and_writes_nothing(tmp_path):
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert not data_root(tmp_path).exists()
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (tmp_path / "state").exists()


def test_dry_run_reports_a_would_be_refusal_at_exit_zero(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert (root / "check_linefeeds.py").read_text(
        encoding="utf-8") == "hand-patched"


def test_a_refusal_without_dry_run_aborts_the_whole_request(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (root / "README.md").exists()


def test_force_replaces_with_an_exclusive_backup(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert (root / "check_linefeeds.py.bak").read_text(
        encoding="utf-8") == "hand-patched"


def test_agentsmd_requires_an_explicit_path(tmp_path):
    r = run_semlf(["install", "agentsmd"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_agentsmd_with_a_path_is_first_class(tmp_path):
    target = tmp_path / "AGENTS.md"
    r = run_semlf(["install", "agentsmd", str(target)],
                  isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "semantic-linefeeds" in target.read_text(encoding="utf-8")


def test_unknown_target_is_a_usage_error(tmp_path):
    r = run_semlf(["install", "codey"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_shim_mismatch_is_warned_about(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "semlf"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    env = isolated_env(tmp_path, path=str(bindir))
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    assert "resolves to" in r.stdout + r.stderr


def test_claude_trailer_appears_last_when_claude_is_present(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    tail = r.stdout.strip().splitlines()[-3:]
    assert any("marketplace" in line for line in tail)


def test_trailer_ends_dry_run_and_refusal_outputs_too(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0 and "marketplace" in r.stdout
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("x", encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1 and "marketplace" in r.stdout


def test_a_refusing_request_still_names_every_verdict(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("x", encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    # The admissible legs are disclosed alongside the refusal.
    assert "readme" in r.stdout and "codex hook" in r.stdout


def test_dry_run_output_carries_the_dry_run_marker(tmp_path):
    r = run_semlf(["install", "codex", "--dry-run"],
                  isolated_env(tmp_path))
    assert "[dry-run] " in r.stdout


def test_subcommand_help_prints_usage_and_exits_zero(tmp_path):
    for cmd in ("install", "status", "uninstall"):
        r = run_semlf([cmd, "--help"], isolated_env(tmp_path))
        assert r.returncode == 0, cmd
        assert "usage: semlf" in r.stdout
