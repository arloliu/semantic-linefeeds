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

BOOTSTRAP = (
    "import sys; sys.path[:0] = [{!r}, {!r}]; "
    "from semlf.cli import main; sys.exit(main(sys.argv[1:]))".format(
        str(REPO / "cli"), str(REPO / "scripts")
    )
)


def isolated_env(tmp_path, path=""):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "HOME": str(home),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "PATH": path,
    }


def run_semlf(args, env_overrides, stdin_text=""):
    env = os.environ.copy()
    env["PATH"] = ""
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", BOOTSTRAP] + args,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def old_checkout_state(tmp_path):
    """A machine the pre-redesign checkout door installed:
    hook pointing into the checkout,
    skill rendered with checkout paths,
    records written the way the old installer wrote them."""
    env = isolated_env(tmp_path)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True)
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
                                    "command": f'python3 "{REPO}/scripts/check_linefeeds.py"'
                                    " --hook codex",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    skill_src = (REPO / "skills" / "semantic-linefeeds" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    old_body = skill_src.replace(
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>',
        f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>',
    )
    old_body = old_body.replace(
        "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
        "`../../scripts/check_linefeeds.py` relative to this "
        "SKILL.md.)\n\n",
        "",
    )
    old_body = old_body.replace("../../README.md", f"{REPO}/README.md")
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(old_body, encoding="utf-8")
    record = {
        "path": str(skill),
        "sha256": hashlib.sha256(old_body.encode("utf-8")).hexdigest(),
        "version": check_linefeeds.__version__,
    }
    state = tmp_path / "state" / "semlf" / "artifacts" / "codex-skill.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return env, hooks, skill


def test_install_migrates_a_checkout_rendered_machine(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    command = json.loads(hooks.read_text(encoding="utf-8"))["hooks"]["PostToolUse"][0][
        "hooks"
    ][0]["command"]
    assert str(data_dir / "check_linefeeds.py") in command
    assert str(REPO) not in command
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    assert str(REPO) not in body
    assert not skill.with_name("SKILL.md.bak").exists()


def test_a_machine_without_the_setup_skill_is_not_reported_broken(tmp_path):
    """Adding rows must not retroactively condemn every install that predates them.

    A machine set up before the setup skill existed has no record for those rows and no files at them.
    `status` should say so plainly, and `install` should offer them,
    but nothing about their absence is a fault:
    a release that reported every existing install as defective would teach people to ignore the report.
    """
    env, _, _ = old_checkout_state(tmp_path)
    out = run_semlf(["status"], env).stdout
    assert "setup skill: not installed" in out

    # Absent artifacts have no provenance record, so nothing claims they were edited or lost.
    for name in ("setup-skill", "opencode-setup-command"):
        assert not (
            tmp_path / "state" / "semlf" / "artifacts" / f"{name}.json"
        ).exists()
        assert f"{name}: missing" not in out

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert (
        tmp_path / "home" / ".agents" / "skills" / "setup-semlf" / "SKILL.md"
    ).exists()


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
    r = subprocess.run(
        [sys.executable, str(pyz), "doctor"],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(tmp_path),
        timeout=120,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "payload" in r.stdout and "FAIL" in r.stdout
    assert "Traceback" not in r.stderr


def test_forced_migration_replaces_an_unrecorded_old_skill(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    # Without its record the old rendering is unrecorded:
    # refuse without force, exclusive backup then replace with it.
    (tmp_path / "state" / "semlf" / "artifacts" / "codex-skill.json").unlink()
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert str(REPO) in skill.read_text(encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert str(tmp_path / "data" / "semlf") in skill.read_text(encoding="utf-8")
    assert skill.with_name("SKILL.md.bak").exists()


def test_uninstall_refuses_a_pre_rename_recorded_skill(tmp_path):
    """Install migrates a retired record; uninstall does not, so it needs --force once.

    The old machine's proof sits under the retired `codex-skill` name.
    `plan_remove_file` reads the live name only,
    so admission falls back to comparing bytes against the current rendering,
    which a body rendered by the pre-redesign checkout door cannot match.
    A refusal is the acceptable side of precision over recall,
    and one `install` run converges the record to `skill.json`,
    after which uninstall admits the file normally.
    """
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 1
    assert "content differs" in r.stderr
    assert skill.exists()

    r = run_semlf(["uninstall", "codex", "--force"], env)
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


def test_a_renamed_row_adopts_its_retired_record(tmp_path):
    """An upgrade must not stop at a wall because the row was renamed.

    The machine here is the one a release that changed SKILL.md leaves behind:
    the file still holds the bytes the old record proves,
    and this artifact's rendering differs from them.
    Without the retired record the new name reads unrecorded and the install refuses;
    with it the row is managed and replaces the file,
    exactly as a same-name upgrade always did.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    old_body = skill.read_text(encoding="utf-8") + "\n<!-- last release -->\n"
    skill.write_text(old_body, encoding="utf-8")
    entry["sha256"] = hashlib.sha256(old_body.encode("utf-8")).hexdigest()
    entry["version"] = "0.0.1"
    (records / "codex-skill.json").write_text(json.dumps(entry), encoding="utf-8")
    (records / "skill.json").unlink()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert "<!-- last release -->" not in skill.read_text(encoding="utf-8")
    assert not (records / "codex-skill.json").exists()
    assert json.loads((records / "skill.json").read_text())["path"] == str(skill)


def test_a_retired_record_does_not_excuse_an_edited_file(tmp_path):
    """Projection carries proof across the rename; it never manufactures proof.

    The record here proves bytes the file no longer holds,
    so the file is edited under the retired name exactly as it would be under the live one,
    and the strict path stands.
    The retired record survives the refusal too:
    nothing is cleared until the row that absorbed it is published.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "codex-skill.json").write_text(json.dumps(entry), encoding="utf-8")
    (records / "skill.json").unlink()
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\n<!-- drift -->\n", encoding="utf-8"
    )

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert "<!-- drift -->" in skill.read_text(encoding="utf-8")
    assert (records / "codex-skill.json").exists()


def test_two_retired_records_naming_one_file_converge(tmp_path):
    """A joined root can leave both codex-skill and opencode-skill on one file."""
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    for retired in ("codex-skill", "opencode-skill"):
        (records / f"{retired}.json").write_text(json.dumps(entry), encoding="utf-8")
    (records / "skill.json").unlink()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert (records / "skill.json").exists()
    assert not (records / "codex-skill.json").exists()
    assert not (records / "opencode-skill.json").exists()


def test_a_hostile_retired_record_is_ignored_not_obeyed(tmp_path):
    """Projection reads files an attacker may have touched, so it validates before trusting.

    A retired record that is not a valid entry proves nothing and must simply not exist
    as far as the projection is concerned —
    never a traceback, and never a projected entry the classifier would then read fields off.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    records = tmp_path / "state" / "semlf" / "artifacts"
    (records / "codex-skill.json").write_text("7", encoding="utf-8")
    (records / "opencode-skill.json").write_text(
        json.dumps({"path": "", "sha256": "nope", "version": 3}), encoding="utf-8"
    )

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr
    # The valid live record is untouched, and neither hostile file was adopted or cleared.
    assert json.loads((records / "skill.json").read_text())["sha256"]
    assert (records / "codex-skill.json").exists()


def test_disagreeing_retired_records_refuse_and_name_both(tmp_path):
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "codex-skill.json").write_text(json.dumps(entry), encoding="utf-8")
    other = dict(entry, sha256="0" * 64)
    (records / "opencode-skill.json").write_text(json.dumps(other), encoding="utf-8")
    (records / "skill.json").unlink()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert "codex-skill" in r.stderr
    assert "opencode-skill" in r.stderr


def _pip_and_setuptools_ok():
    try:
        import setuptools

        if int(setuptools.__version__.split(".")[0]) < 61:
            return False
    except Exception:
        return False
    r = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _pip_and_setuptools_ok(), reason="needs pip and setuptools>=61")
def test_a_wheel_installed_semlf_renders_the_codex_artifacts(tmp_path):
    """The design requires rendering proof from a wheel INSTALL,
    not only member inspection: build, install into a venv, run
    `semlf install codex` from the installed entry point."""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(REPO),
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    wheel = next(tmp_path.glob("semlf-*.whl"))
    venv_dir = tmp_path / "venv"
    r = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    r = subprocess.run(
        [str(venv_dir / "bin" / "pip"), "install", "--no-deps", str(wheel)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    env = isolated_env(tmp_path, path=str(venv_dir / "bin"))
    full_env = os.environ.copy()
    full_env.update(env)
    r = subprocess.run(
        [str(venv_dir / "bin" / "semlf"), "install", "codex"],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    assert (data_dir / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py"
    ).read_bytes()
    assert (data_dir / "README.md").read_bytes() == (REPO / "README.md").read_bytes()
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    hooks_text = (tmp_path / "codex" / "hooks.json").read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in hooks_text
