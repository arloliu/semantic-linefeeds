"""tests/test_migration.py — the package door over a pre-redesign machine:
checkout-rendered artifacts, old records, leftover zipapp."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds

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


def old_checkout_state(tmp_path):
    """A machine the pre-redesign checkout door installed:
    hook pointing into the checkout,
    skill rendered with checkout paths,
    records written the way the old installer wrote them."""
    env = isolated_env(tmp_path)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": f'python3 "{REPO}/scripts/check_linefeeds.py"'
                        ' --hook codex'}]}]}}, indent=2) + "\n",
        encoding="utf-8")
    skill_src = (REPO / "skills" / "semantic-linefeeds" /
                 "SKILL.md").read_text(encoding="utf-8")
    old_body = skill_src.replace(
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" '
        '--file <files>',
        f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>')
    old_body = old_body.replace(
        "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
        "`../../scripts/check_linefeeds.py` relative to this "
        "SKILL.md.)\n\n", "")
    old_body = old_body.replace("../../README.md", f"{REPO}/README.md")
    skill = (tmp_path / "home" / ".agents" / "skills" /
             "semantic-linefeeds" / "SKILL.md")
    skill.parent.mkdir(parents=True)
    skill.write_text(old_body, encoding="utf-8")
    record = {"path": str(skill),
              "sha256": hashlib.sha256(
                  old_body.encode("utf-8")).hexdigest(),
              "version": check_linefeeds.__version__}
    state = tmp_path / "state" / "semlf" / "artifacts" / \
        "codex-skill.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(record, indent=2) + "\n",
                     encoding="utf-8")
    return env, hooks, skill


def test_install_migrates_a_checkout_rendered_machine(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    command = json.loads(hooks.read_text(encoding="utf-8"))[
        "hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(data_dir / "check_linefeeds.py") in command
    assert str(REPO) not in command
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    assert str(REPO) not in body
    assert not skill.with_name("SKILL.md.bak").exists()


def test_dry_run_over_the_old_machine_writes_nothing(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    before_hooks = hooks.read_bytes()
    before_skill = skill.read_bytes()
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert hooks.read_bytes() == before_hooks
    assert skill.read_bytes() == before_skill


def _built_pyz(tmp_path):
    import importlib
    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    return pyz


def test_status_survives_the_old_machine(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_doctor_flags_the_old_machine_through_a_real_artifact(tmp_path):
    """Doctor replays through a BUILT zipapp —
    its replay child derives from sys.argv[0],
    so the checkout bootstrap would prove nothing.
    The old machine has an owned hook but no published payloads:
    doctor must flag exactly that, deterministically."""
    env, hooks, skill = old_checkout_state(tmp_path)
    pyz = _built_pyz(tmp_path)
    full_env = os.environ.copy()
    full_env["PATH"] = ""
    full_env.update(env)
    r = subprocess.run([sys.executable, str(pyz), "doctor"],
                       capture_output=True, text=True, env=full_env,
                       cwd=str(tmp_path), timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "payload" in r.stdout and "FAIL" in r.stdout
    assert "Traceback" not in r.stderr


def test_forced_migration_replaces_an_unrecorded_old_skill(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    # Without its record the old rendering is unrecorded:
    # refuse without force, exclusive backup then replace with it.
    (tmp_path / "state" / "semlf" / "artifacts" /
     "codex-skill.json").unlink()
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert str(REPO) in skill.read_text(encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert str(tmp_path / "data" / "semlf") in skill.read_text(
        encoding="utf-8")
    assert skill.with_name("SKILL.md.bak").exists()


def test_uninstall_admits_the_old_recorded_skill(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    data = json.loads(hooks.read_text(encoding="utf-8"))
    from semlf import manifest
    assert manifest.owned_codex_hooks(data) == []


def test_leftover_zipapp_on_path_is_warned_about(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # The design names a REAL pre-redesign zipapp as the collision;
    # a shell stub would only prove generic path-mismatch wording.
    shim = bindir / "semlf"
    import importlib
    importlib.import_module("install").build_pyz(shim)
    env["PATH"] = str(bindir)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    assert "resolves to" in r.stdout + r.stderr
    r = run_semlf(["status"], env)
    out = r.stdout + r.stderr
    assert "resolves to" in out
    # The migration report carries the checkout-door removal pointer.
    assert "install.py --uninstall --cli" in out


def _pip_and_setuptools_ok():
    try:
        import setuptools
        if int(setuptools.__version__.split(".")[0]) < 61:
            return False
    except Exception:
        return False
    r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                       capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _pip_and_setuptools_ok(),
                    reason="needs pip and setuptools>=61")
def test_a_wheel_installed_semlf_renders_the_codex_artifacts(tmp_path):
    """The design requires rendering proof from a wheel INSTALL,
    not only member inspection: build, install into a venv, run
    `semlf install codex` from the installed entry point."""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps",
         "--no-build-isolation", "-w", str(tmp_path)],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    wheel = next(tmp_path.glob("semlf-*.whl"))
    venv_dir = tmp_path / "venv"
    r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    r = subprocess.run([str(venv_dir / "bin" / "pip"), "install",
                        "--no-deps", str(wheel)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    env = isolated_env(tmp_path, path=str(venv_dir / "bin"))
    full_env = os.environ.copy()
    full_env.update(env)
    r = subprocess.run([str(venv_dir / "bin" / "semlf"),
                        "install", "codex"],
                       capture_output=True, text=True, env=full_env,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    assert (data_dir / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert (data_dir / "README.md").read_bytes() == (
        REPO / "README.md").read_bytes()
    skill = (tmp_path / "home" / ".agents" / "skills" /
             "semantic-linefeeds" / "SKILL.md")
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    hooks_text = (tmp_path / "codex" / "hooks.json").read_text(
        encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in hooks_text
