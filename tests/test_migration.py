"""tests/test_migration.py — the package door over a pre-redesign machine:
checkout-rendered artifacts, old records, leftover zipapp."""

import hashlib
import json
import os
import shutil
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


def test_uninstall_projects_a_pre_rename_recorded_skill(tmp_path):
    """The upgrade boundary must not need --force, and must not strand the record.

    The old machine's proof sits under the retired `codex-skill` name.
    Reading the live name only, removal fell back to comparing bytes against the current rendering,
    which refuses the moment a release changes the skill body.
    It also cleared a record that never existed and left the retired one naming a path it had just deleted,
    where nothing afterwards can read or name it.
    """
    env, hooks, skill = old_checkout_state(tmp_path)
    state = tmp_path / "state" / "semlf" / "artifacts"
    assert (state / "codex-skill.json").is_file()

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    assert not (state / "codex-skill.json").exists(), "the retired record was stranded"

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


def legacy_opencode_skill(tmp_path, name="semantic-linefeeds"):
    d = tmp_path / "xdg" / "opencode" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    return d / "SKILL.md"


def prove_legacy(tmp_path, path, retired, body):
    """Write a legacy file and the record that proves this kit wrote it."""
    path.write_text(body, encoding="utf-8")
    records = tmp_path / "state" / "semlf" / "artifacts"
    records.mkdir(parents=True, exist_ok=True)
    (records / f"{retired}.json").write_text(
        json.dumps(
            {
                "path": str(path),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "version": check_linefeeds.__version__,
            }
        ),
        encoding="utf-8",
    )
    return records / f"{retired}.json"


def pre_change_opencode_machine(tmp_path):
    """Both pre-change opencode skill copies, each proven, and nothing else installed."""
    env = isolated_env(tmp_path)
    copies = []
    for folder, retired in (
        ("semantic-linefeeds", "opencode-skill"),
        ("setup-semlf", "opencode-setup-skill"),
    ):
        legacy = legacy_opencode_skill(tmp_path, folder)
        prove_legacy(tmp_path, legacy, retired, f"---\nname: {folder}\n---\n\nold\n")
        copies.append(legacy)
    return env, copies


def test_a_request_naming_no_agent_target_never_clears_the_legacy_copies(tmp_path):
    """The install side of the guard `plan_remove_targets` already applies to removals.

    Legacy cleanup only ever unlinks under opencode's own skills root,
    so a request that does not name opencode has no business running it.
    agentsmd is the sharpest case: it is a paragraph of prose with no skill behind it,
    so it publishes nothing that could replace what the cleanup would take,
    and ungated it leaves the machine with no judgment skill at all.
    """
    env, copies = pre_change_opencode_machine(tmp_path)
    agents_md = tmp_path / "AGENTS.md"

    r = run_semlf(["install", "agentsmd", str(agents_md)], env)
    assert r.returncode == 0, r.stderr
    for legacy in copies:
        assert legacy.is_file(), f"a request naming no agent target removed {legacy}"
    assert "semantic-linefeeds" in agents_md.read_text(encoding="utf-8")


def test_an_unproven_opencode_file_does_not_refuse_a_codex_install(tmp_path):
    """The refusal belongs to opencode's request, not to every request.

    This project's own pre-change manual install instructions produced exactly such a file,
    so released users have one at that path.
    Ungated it aborted the whole request, and `semlf install codex` —
    which touches nothing under that root — could not run at all until the file was moved aside.
    """
    env = isolated_env(tmp_path)
    legacy = legacy_opencode_skill(tmp_path)
    legacy.write_text("hand written\n", encoding="utf-8")

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert legacy.read_text(encoding="utf-8") == "hand written\n"
    assert (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    ).is_file()

    # opencode's own request still refuses it, which is the behavior the guard protects.
    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1
    assert str(legacy) in r.stderr
    assert legacy.is_file()


def test_migration_refuses_an_edited_legacy_file(tmp_path):
    """A record that names the path is not proof; the bytes are.

    This is the state a user reaches by editing a skill this kit once wrote,
    and it is the reason removal asks the classifier rather than merely asking whether a record exists.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    legacy = legacy_opencode_skill(tmp_path)
    record = prove_legacy(
        tmp_path,
        legacy,
        "opencode-skill",
        "---\nname: semantic-linefeeds\n---\n\nold\n",
    )
    legacy.write_text(
        "---\nname: semantic-linefeeds\n---\n\nmy own notes\n", encoding="utf-8"
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1
    assert str(legacy) in r.stderr
    assert legacy.read_text(encoding="utf-8").endswith("my own notes\n")
    assert record.exists(), (
        "a refused removal must keep the record that proves the path"
    )


def test_migration_removes_a_proven_legacy_opencode_skill(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    legacy = legacy_opencode_skill(tmp_path)
    body = "---\nname: semantic-linefeeds\n---\n\nold\n"
    legacy.write_text(body, encoding="utf-8")
    records = tmp_path / "state" / "semlf" / "artifacts"
    (records / "opencode-skill.json").write_text(
        json.dumps(
            {
                "path": str(legacy),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "version": check_linefeeds.__version__,
            }
        ),
        encoding="utf-8",
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not legacy.exists()
    assert not legacy.parent.exists()
    assert not (records / "opencode-skill.json").exists()


def test_migration_never_removes_the_shared_file_through_a_joined_root(tmp_path):
    """The trap: on a joined root the legacy record's path IS the shared file."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )

    skills = tmp_path / "xdg" / "opencode" / "skills"
    skills.parent.mkdir(parents=True, exist_ok=True)
    skills.symlink_to(
        tmp_path / "home" / ".agents" / "skills", target_is_directory=True
    )

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(skills / "semantic-linefeeds" / "SKILL.md"))),
        encoding="utf-8",
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert shared.is_file(), "the shared skill was deleted through the joined root"


def test_migration_removes_a_hard_linked_legacy_skill(tmp_path):
    """A hard link reads as the same file but must go.

    Sparing it leaves it in place until the shared file is next published:
    publish_bytes stages a temp file and replaces it,
    the shared path gets a new inode,
    and the spared link is stranded serving last release's bytes.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    legacy = legacy_opencode_skill(tmp_path)
    os.link(shared, legacy)

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(legacy))), encoding="utf-8"
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not legacy.exists()
    assert shared.is_file()


def test_a_codex_install_keeps_a_hard_linked_legacy_record(tmp_path):
    """A request that cannot remove the file must not clear the record proving it.

    A hard link shares an inode with the shared destination,
    so project_retired collects opencode-skill as an alias even on a codex-only request,
    while the legacy cleanup, whose outcome is gated on the request naming opencode, cannot take the file.
    Forgetting the record there stranded the link permanently:
    the following `install opencode` found a file this kit could no longer prove it wrote,
    and refused for good.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    legacy = legacy_opencode_skill(tmp_path)
    os.link(shared, legacy)

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(legacy))), encoding="utf-8"
    )

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert legacy.is_file()
    assert (records / "opencode-skill.json").exists(), (
        "install codex forgot the only record proving a file it cannot remove"
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not legacy.exists()
    assert not (records / "opencode-skill.json").exists()
    assert shared.is_file()


def test_a_failed_hard_link_unlink_leaves_its_record_intact(tmp_path, monkeypatch):
    """A failed unlink must not lose the only proof a re-run can use.

    project_retired also proves opencode-skill through the hard link,
    since a hard link shares an inode with the shared file same_file compares against.
    Before the fix that alias-forget ran during the row loop,
    ahead of plan_legacy_cleanup's own removal step,
    so a failed unlink left the record cleared and the file stranded —
    unprovable on the very next run.
    The fix skips that early forget for a retired name the cleanup step owns,
    so only the cleanup's own step ever clears it,
    and only after its unlink actually succeeds.

    This drives plan_install and apply_plan in-process,
    rather than through the subprocess-based run_semlf,
    so os.unlink can be monkeypatched to fail on exactly this one path without touching any other artifact's real unlink.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    legacy = legacy_opencode_skill(tmp_path)
    os.link(shared, legacy)

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(legacy))), encoding="utf-8"
    )

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from semlf import lifecycle

    real_unlink = os.unlink

    def failing_unlink(path, *a, **kw):
        if str(path) == str(legacy):
            raise OSError("simulated failure")
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(os, "unlink", failing_unlink)

    planned, refusals = lifecycle.plan_install(["opencode"], None, False)
    assert refusals == []
    rc = lifecycle.apply_plan(planned)
    assert rc == 1

    assert legacy.exists(), "the failed unlink should have left the file in place"
    assert (records / "opencode-skill.json").exists(), (
        "the record must survive an unlink it cannot prove happened"
    )


def test_migration_refuses_an_unproven_legacy_file(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    legacy = legacy_opencode_skill(tmp_path)
    legacy.write_text("hand written\n", encoding="utf-8")

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1
    assert str(legacy) in r.stderr
    assert legacy.exists()


def test_uninstall_clears_legacy_copies_without_a_new_install(tmp_path):
    """Upgrading the package and uninstalling immediately is a reachable path.

    Without this the old skill survives an uninstall that reported success, and
    because opencode scans its own root it stays advertised.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    legacy = tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds"
    legacy.mkdir(parents=True, exist_ok=True)
    body = "---\nname: semantic-linefeeds\n---\n\nold\n"
    (legacy / "SKILL.md").write_text(body, encoding="utf-8")
    records = tmp_path / "state" / "semlf" / "artifacts"
    (records / "opencode-skill.json").write_text(
        json.dumps(
            {
                "path": str(legacy / "SKILL.md"),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "version": check_linefeeds.__version__,
            }
        ),
        encoding="utf-8",
    )

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not (legacy / "SKILL.md").exists()
    assert not (records / "opencode-skill.json").exists()


def test_uninstall_keeps_a_legacy_record_it_could_not_remove(tmp_path):
    """A refused removal must not forget its record.

    On a joined root with another consumer still installed the shared file survives correctly,
    but its only proof is that retired record.
    Forgetting it would leave a file no record proves,
    and the next install would refuse without --force.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    skills = tmp_path / "xdg" / "opencode" / "skills"
    if skills.exists():
        shutil.rmtree(skills)
    skills.symlink_to(
        tmp_path / "home" / ".agents" / "skills", target_is_directory=True
    )
    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(skills / "semantic-linefeeds" / "SKILL.md"))),
        encoding="utf-8",
    )

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert shared.is_file()
    assert (records / "opencode-skill.json").exists()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr


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
