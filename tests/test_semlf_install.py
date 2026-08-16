"""tests/test_semlf_install.py — the package door's command surface."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

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


def data_root(tmp_path):
    return tmp_path / "data" / "semlf"


def test_named_target_is_consent_and_applies(tmp_path):
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py"
    ).read_bytes()
    assert (data_root(tmp_path) / "README.md").exists()
    hooks = json.loads((tmp_path / "codex" / "hooks.json").read_text())
    command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(data_root(tmp_path) / "check_linefeeds.py") in command
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert str(data_root(tmp_path) / "check_linefeeds.py") in body
    assert str(data_root(tmp_path) / "README.md") in body


def test_installing_opencode_alone_publishes_the_shared_payloads(tmp_path):
    """The shared skill cites the neutral root, so any target must publish it.

    This inverts the old assertion that an opencode-only install creates no data root:
    under per-target skills that root was Codex's alone,
    and citing it from opencode's copy would have referenced a file the install never wrote.
    One shared skill body can only cite one checker, so the payloads it cites belong to every target.
    """
    r = run_semlf(["install", "opencode"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").is_file()
    assert (data_root(tmp_path) / "README.md").is_file()


def test_agentsmd_alone_publishes_no_shared_payload(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# Agents\n", encoding="utf-8")
    r = run_semlf(["install", "agentsmd", str(target)], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert not data_root(tmp_path).exists()


def test_symlinked_skill_roots_install_cleanly(tmp_path):
    """The refusal this arrangement used to earn, retired with the second copy.

    Pointing opencode's skills root at `~/.agents/skills` is a reasonable thing to do,
    and opencode does not even need it, since it already reads that directory natively.
    Under per-target rows it joined two skill destinations onto one file
    and the whole request had to be refused.
    One row publishes each skill now,
    and a single row cannot collide with itself,
    so the arrangement needs no rule and the install simply succeeds.
    """
    env = isolated_env(tmp_path)
    agents = tmp_path / "home" / ".agents" / "skills"
    agents.mkdir(parents=True)
    (tmp_path / "xdg" / "opencode").mkdir(parents=True)
    (tmp_path / "xdg" / "opencode" / "skills").symlink_to(agents)

    r = run_semlf(["install", "codex", "opencode"], env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "both resolve to" not in r.stdout + r.stderr

    # One skill, written once, reachable through both names for the one directory.
    skill = agents / "semantic-linefeeds" / "SKILL.md"
    assert skill.is_file()
    via_opencode = tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds"
    assert (via_opencode / "SKILL.md").read_bytes() == skill.read_bytes()
    assert sorted(p.name for p in agents.iterdir()) == [
        "semantic-linefeeds",
        "setup-semlf",
    ]


def test_a_collision_assembled_across_two_requests_is_refused(tmp_path):
    """Two requests, one file, two owners — the state the old check could not see.

    Install codex, point opencode's plugins directory at the payload root,
    then install opencode.
    Naming opencode selects both the shared `checker` row and opencode's own `opencode-checker` row in that same request,
    and the symlink makes their destinations name one file,
    so the selected-against-selected comparison catches it.
    The old owner-keyed check missed this:
    `checker`'s owner is "shared", not "opencode",
    so it was never compared against `opencode-checker` at all.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    plugins.parent.mkdir(parents=True, exist_ok=True)
    plugins.symlink_to(data_root(tmp_path), target_is_directory=True)

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1, r.stdout
    assert "resolve to" in r.stderr
    assert "opencode-checker" in r.stderr


def test_a_collision_between_two_destinations_that_do_not_exist_yet_is_refused(
    tmp_path,
):
    """Nothing installed, both roots joined, both leaves absent.

    realpath reports two different paths here,
    so a fallback keyed on it finds no collision,
    both rows are planned,
    the first write creates the file and the second fails as "appeared after classification" — a half-applied request,
    which preflight exists to make impossible.
    """
    env = isolated_env(tmp_path)
    data = data_root(tmp_path)
    data.mkdir(parents=True, exist_ok=True)
    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    plugins.parent.mkdir(parents=True, exist_ok=True)
    plugins.symlink_to(data, target_is_directory=True)

    r = run_semlf(["install", "codex", "opencode"], env)
    assert r.returncode == 1, r.stdout
    assert "checker" in r.stderr
    assert not (data / "check_linefeeds.py").exists(), "half-applied"


def test_an_installed_but_unselected_row_is_checked_for_collision(tmp_path):
    """The population `colliding_destinations` gained: rows this request never selects.

    Install opencode first, so its own checker copy is recorded and written under the opencode plugins directory.
    Delete that directory and symlink it onto the payload root, then install codex.
    codex's request never selects `opencode-checker` — its owner is "opencode", not "codex" or "shared" —
    so only the pass over already-installed rows can see that the symlink now makes its destination name the same file as the shared `checker` row codex's request does select.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr

    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    shutil.rmtree(plugins)
    plugins.symlink_to(data_root(tmp_path), target_is_directory=True)

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1, r.stdout
    assert "resolve to" in r.stderr
    assert "opencode-checker" in r.stderr


def test_opencode_gets_the_shared_judgment_skill(tmp_path):
    """ADR-0006 for opencode, discharged by the shared row (ADR-0019).

    opencode reads `~/.agents/skills` natively,
    so the copy it once received under its own config root bought nothing.
    Installing opencode alone now publishes the one skill there,
    and every path that skill cites is published by a shared row the same install wrote.
    """
    r = run_semlf(["install", "opencode"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")

    assert str(data_root(tmp_path) / "check_linefeeds.py") in body
    assert str(data_root(tmp_path) / "README.md") in body
    assert (data_root(tmp_path) / "README.md").exists()

    # Nothing is written under opencode's own skills root any more.
    assert not (tmp_path / "xdg" / "opencode" / "skills").exists()
    # The plugin directory carries the plugin and its checker, and no README.
    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    assert (plugins / "semantic-linefeeds.ts").exists()
    assert not (plugins / "README.md").exists()


def test_uninstalling_codex_keeps_the_skill_opencode_still_uses(tmp_path):
    """The codex direction of the last-consumer rule.

    There is one skill now, so removing it with codex would take it away from opencode too.
    The removal legs travelled with codex as a holdover while the rows were renamed;
    the rule that replaced them removes the shared skill only when no target still has artifacts.
    opencode's own artifacts are untouched either way.
    """
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    assert skill.exists()

    assert run_semlf(["uninstall", "codex"], env).returncode == 0
    assert skill.exists(), "opencode is still installed and reads this skill"
    assert (plugins / "semantic-linefeeds.ts").exists()
    assert (plugins / "check_linefeeds.py").exists()


def setup_skill_paths(tmp_path):
    """The two setup destinations: the shared skill, and opencode's command.

    opencode's own copy of the skill is gone —
    it read the shared root all along, so the second copy was never reachable prose.
    """
    return (
        tmp_path / "home" / ".agents" / "skills" / "setup-semlf" / "SKILL.md",
        tmp_path / "xdg" / "opencode" / "commands" / "setup-semlf.md",
    )


def test_installing_codex_writes_the_shared_setup_skill_and_no_command(tmp_path):
    setup_skill, opencode_command = setup_skill_paths(tmp_path)
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert setup_skill.exists()
    # The command is opencode's own artifact, so naming codex must not write it.
    assert not opencode_command.exists()


def test_the_setup_skill_cites_no_payload(tmp_path):
    """The setup skill references no published file, so it needs no payload to exist.

    The judgment skill is the opposite case and cites the shared root deliberately;
    this one must stay self-contained,
    because it is what an agent runs when nothing is installed yet.
    """
    setup_skill, opencode_command = setup_skill_paths(tmp_path)
    r = run_semlf(["install", "opencode"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert setup_skill.exists()
    assert opencode_command.exists()

    body = setup_skill.read_text(encoding="utf-8")
    assert "check_linefeeds.py" not in body


def test_the_setup_skill_installs_its_canonical_bytes(tmp_path):
    """One row, one source, no transform: the installed file is the repository's.

    There is nothing left to drift against now that a second destination is gone,
    so what this pins is that the row still ships bytes rather than a rendering.
    """
    setup_skill, _ = setup_skill_paths(tmp_path)
    r = run_semlf(["install", "codex", "opencode"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (
        setup_skill.read_bytes()
        == (REPO / "skills" / "setup-semlf" / "SKILL.md").read_bytes()
    )


def test_the_opencode_command_delegates_rather_than_restating(tmp_path):
    """A command that copied the procedure would be a second place to update."""
    _, opencode_command = setup_skill_paths(tmp_path)
    run_semlf(["install", "opencode"], isolated_env(tmp_path))
    body = opencode_command.read_text(encoding="utf-8")
    assert "setup-semlf" in body
    assert "uv tool install" not in body
    assert "pipx install" not in body


def test_uninstall_removes_the_setup_artifacts_each_target_owns(tmp_path):
    """Uninstalling opencode takes its command; the shared skill is not its to remove.

    opencode owned a setup skill of its own before the shared root,
    and this test asserted its removal.
    That row is gone, so what remains true is the narrower claim:
    a target's uninstall removes the artifacts that target owns,
    and the shared skill leaves only when the request names every agent target.
    """
    setup_skill, opencode_command = setup_skill_paths(tmp_path)
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not opencode_command.exists()
    assert setup_skill.exists(), "the shared skill is not opencode's to remove"

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not setup_skill.exists()


def test_status_reports_the_setup_artifacts(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    out = run_semlf(["status"], env).stdout
    # Anchored on the line start: "skill:" is a substring of "setup skill:".
    lines = out.splitlines()
    assert any(line.startswith("skill: ") for line in lines), out
    assert any(line.startswith("setup skill: ") for line in lines), out
    assert any(line.startswith("opencode setup command: ") for line in lines), out


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
    (root / "check_linefeeds.py").write_text("hand-patched", encoding="utf-8")
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert (root / "check_linefeeds.py").read_text(encoding="utf-8") == "hand-patched"


def test_a_refusal_without_dry_run_aborts_the_whole_request(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched", encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (root / "README.md").exists()


def test_force_replaces_with_an_exclusive_backup(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched", encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert (root / "check_linefeeds.py.bak").read_text(
        encoding="utf-8"
    ) == "hand-patched"


def test_agentsmd_requires_an_explicit_path(tmp_path):
    r = run_semlf(["install", "agentsmd"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_agentsmd_with_a_path_is_first_class(tmp_path):
    target = tmp_path / "AGENTS.md"
    r = run_semlf(["install", "agentsmd", str(target)], isolated_env(tmp_path))
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
    r = run_semlf(["install", "codex", "--dry-run"], isolated_env(tmp_path))
    assert "[dry-run] " in r.stdout


def test_subcommand_help_prints_usage_and_exits_zero(tmp_path):
    for cmd in ("install", "status", "uninstall"):
        r = run_semlf([cmd, "--help"], isolated_env(tmp_path))
        assert r.returncode == 0, cmd
        assert "usage: semlf" in r.stdout


def test_status_reports_a_healthy_install(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout.lower()
    assert "checker" in out and "readme" in out
    assert "codex" in out


def test_status_reports_payload_lag_by_version_label(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    checker = data_root(tmp_path) / "check_linefeeds.py"
    stale = checker.read_text(encoding="utf-8").replace(
        '__version__ = "', '__version__ = "0.0.', 1
    )
    checker.write_text(stale, encoding="utf-8")
    # Make the stale copy managed so the state is lagging, not edited.
    import hashlib

    record = {
        "path": str(checker),
        "sha256": hashlib.sha256(stale.encode("utf-8")).hexdigest(),
        "version": "0.0.1",
    }
    state = tmp_path / "state" / "semlf" / "artifacts" / "checker.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "lag" in r.stdout.lower()
    assert "semlf install" in r.stdout


def test_status_names_no_consumer_leftovers_in_one_line(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    run_semlf(["uninstall", "codex"], env)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout
    assert "no remaining" in out.lower() or "leftover" in out.lower()
    assert str(data_root(tmp_path)) in out


def test_status_points_opencode_leftovers_at_their_real_path(tmp_path):
    """The leftover pointer derives from each identity row's own destination:
    an opencode-checker leftover lives in the opencode plugins directory, not a hand-maintained path.

    checker and readme are shared rows now,
    so losing opencode's own consumer signal leaves them without a consumer too,
    and their own destination — the neutral data root — legitimately joins the leftover list alongside it.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    (plugins / "semantic-linefeeds.ts").unlink()
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout
    assert "no remaining" in out.lower()
    assert str(plugins / "check_linefeeds.py") in out


def test_status_excludes_agentsmd_without_a_path(tmp_path):
    r = run_semlf(["status"], isolated_env(tmp_path))
    # "agentsmd:" (with the colon) is the actual status-line marker this asserts against;
    # a bare "agentsmd" substring can appear incidentally inside tmp_path's own directory name
    # (pytest truncates long test ids to 30 chars for tmp_path,
    # and this test's own name happens to survive that truncation).
    assert "agentsmd:" not in r.stdout.lower()


def test_status_agentsmd_reports_the_named_file(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    run_semlf(["install", "agentsmd", str(target)], env)
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert r.returncode == 0
    assert "present" in r.stdout.lower()
    r = run_semlf(["status", "agentsmd", str(tmp_path / "other.md")], env)
    assert "absent" in r.stdout.lower()


def test_status_agentsmd_reports_malformed_sentinels(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("<!-- semantic-linefeeds -->\nno close\n", encoding="utf-8")
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert "malformed" in r.stdout.lower()
    target.write_text(
        "<!-- /semantic-linefeeds -->\nreversed\n<!-- semantic-linefeeds -->\n",
        encoding="utf-8",
    )
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert "malformed" in r.stdout.lower()


def test_status_names_a_recorded_payload_whose_file_vanished(tmp_path):
    """Status reports every discoverable OR RECORDED artifact:
    a valid record with a missing file is missing, never silently omitted."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    run_semlf(["uninstall", "codex"], env)
    (data_root(tmp_path) / "check_linefeeds.py").unlink()
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "checker" in r.stdout and "missing" in r.stdout.lower()


def test_a_skill_only_machine_reports_the_payloads_as_leftovers(tmp_path):
    """A skill-only machine no longer proves codex, so its payloads read as leftovers.

    The skill used to count as codex's, because it referenced the neutral checker and README
    and removing only the hook must not downgrade those payloads.
    They are shared rows now, so that reason is gone
    and the skill proves some agent rather than codex specifically (ADR-0019).

    This is the reporting direction the design chose.
    A false "absent" costs a harmless leftover warning and a manual-removal pointer,
    which is the cheap side of a predicate that fails closed;
    the expensive side would be an opencode-only machine inventing a codex consumer
    and reporting genuinely orphaned payloads as expected.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    (tmp_path / "codex" / "hooks.json").write_text(
        '{"hooks": {"PostToolUse": []}}', encoding="utf-8"
    )
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert skill.exists(), "the skill is what used to keep the payloads expected"

    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "no remaining" in r.stdout.lower()
    assert str(data_root(tmp_path)) in r.stdout


def test_an_uninstalled_opencode_machine_reports_its_orphaned_payloads(tmp_path):
    """Everything shared is retained and reported now, the skills included.

    The skills used to leave with the last consumer.
    That rule rested on proving the other target absent, which is not always reachable,
    so retention is the answer and `status` is what keeps it from being silent.
    """
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0
    assert run_semlf(["uninstall", "opencode"], env).returncode == 0

    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert skill.is_file(), "the skills are retained until the user names every target"
    assert (data_root(tmp_path) / "check_linefeeds.py").exists()

    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout
    assert "no remaining consumer" in out.lower()
    assert str(data_root(tmp_path) / "check_linefeeds.py") in out
    assert str(data_root(tmp_path) / "README.md") in out


def test_uninstall_without_a_target_is_a_usage_error(tmp_path):
    r = run_semlf(["uninstall"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_uninstall_removes_hook_and_skill_but_keeps_payloads(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    hooks = json.loads((tmp_path / "codex" / "hooks.json").read_text())
    from semlf import manifest as m  # path inserted at module top

    assert m.owned_codex_hooks(hooks) == []
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert not skill.exists()
    assert (data_root(tmp_path) / "check_linefeeds.py").exists()
    assert (data_root(tmp_path) / "README.md").exists()


def test_uninstall_refuses_an_edited_skill_without_force(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.write_text("hand-patched", encoding="utf-8")
    # Clear its record so admission can only come from byte identity.
    (tmp_path / "state" / "semlf" / "artifacts" / "skill.json").unlink()
    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 1
    assert skill.exists()
    r = run_semlf(["uninstall", "codex", "opencode", "--force"], env)
    assert r.returncode == 0
    assert not skill.exists()


def test_uninstall_agentsmd_requires_and_uses_the_path(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("# mine\n", encoding="utf-8")
    run_semlf(["install", "agentsmd", str(target)], env)
    r = run_semlf(["uninstall", "agentsmd"], env)
    assert r.returncode == 64
    r = run_semlf(["uninstall", "agentsmd", str(target)], env)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "semantic-linefeeds" not in text
    assert "# mine" in text


def test_uninstall_dry_run_removes_nothing(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    plugin = tmp_path / "xdg" / "opencode" / "plugins" / "semantic-linefeeds.ts"
    assert plugin.exists()
    r = run_semlf(["uninstall", "opencode", "--dry-run"], env)
    assert r.returncode == 0
    assert plugin.exists()


def test_uninstall_dry_run_reports_a_would_be_refusal_at_exit_zero(tmp_path):
    """Dry-run dominates refusals on uninstall exactly as on install:
    report, write nothing, exit 0."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.write_text("hand-patched", encoding="utf-8")
    (tmp_path / "state" / "semlf" / "artifacts" / "skill.json").unlink()
    r = run_semlf(["uninstall", "codex", "opencode", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert skill.read_text(encoding="utf-8") == "hand-patched"


def test_a_target_recorded_under_another_config_home_keeps_the_skills(tmp_path):
    """A request naming one target leaves the shared skills alone.

    This machine's opencode lives where this environment does not look,
    which used to be the interesting part; it no longer decides anything.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr

    moved = dict(env, XDG_CONFIG_HOME=str(tmp_path / "elsewhere"))
    r = run_semlf(["uninstall", "codex"], moved)
    assert r.returncode == 0, r.stderr
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert shared.is_file(), "shared skill removed while opencode is still installed"


def test_an_unreadable_hooks_json_retains_the_shared_skills(tmp_path):
    """Retention no longer depends on reading this file at all.

    The request named one target, so the shared skills stay whatever hooks.json says.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    (tmp_path / "codex" / "hooks.json").write_text("{ not json", encoding="utf-8")

    run_semlf(["uninstall", "opencode"], env)
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert shared.is_file(), "an unreadable hooks.json must not authorise a delete"


def test_a_record_whose_file_is_gone_counts_absent(tmp_path):
    """Otherwise a hand-cleaned machine can never converge."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    plugin = tmp_path / "xdg" / "opencode" / "plugins" / "semantic-linefeeds.ts"
    plugin.unlink()

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert not shared.exists()


def test_removing_one_target_keeps_the_shared_skills(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert shared.is_file()


def test_naming_every_target_takes_the_skills_and_keeps_the_payloads(tmp_path):
    """Removing the last target is no longer what takes the skills; naming both is.

    The payloads keep the retain-and-report precedent either way.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    run_semlf(["uninstall", "opencode"], env)
    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = (
        tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert not shared.exists()
    assert (data_root(tmp_path) / "check_linefeeds.py").is_file()
    assert "retained" in r.stdout


def test_shared_removals_are_planned_after_every_target_artifact(tmp_path):
    """apply_plan stops at the first error and has no rollback.

    A shared removal placed early would strand a target with its own artifacts installed and its skill gone;
    planned last, the same failure leaves the skills intact and a re-run converges.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    # Both targets: the skill leg is planned only by a request naming every one of them,
    # and this test is about where that leg sits in the order.
    r = run_semlf(["uninstall", "codex", "opencode", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if "would remove" in ln]
    plugin = next(i for i, ln in enumerate(lines) if "semantic-linefeeds.ts" in ln)
    skill = next(i for i, ln in enumerate(lines) if "skills" in ln and "SKILL.md" in ln)
    assert plugin < skill


def orphaned_skill_machine(tmp_path):
    """A machine whose shared skills are installed and whose agents are not.

    Installing codex writes the skills,
    and blanking the hook by hand is the state a user reaches without ever running uninstall.
    The skills are the only thing left, which is what makes them removable at all.
    """
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "codex"], env).returncode == 0
    (tmp_path / "codex" / "hooks.json").write_text(
        '{"hooks": {"PostToolUse": []}}', encoding="utf-8"
    )
    agents_md = tmp_path / "AGENTS.md"
    assert run_semlf(["install", "agentsmd", str(agents_md)], env).returncode == 0
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert skill.is_file()
    return env, agents_md, skill


def test_a_request_naming_no_agent_target_never_removes_the_shared_skills(tmp_path):
    """The removal side of the rule `selects` already applies to installs.

    agentsmd is a paragraph of prose with no checker and no skill behind it,
    so a request that names it and no agent target neither publishes nor removes a skill.
    --force is the reason this needs a guard rather than a mitigation:
    it is a valid flag on this verb and it removes the refusal
    that would otherwise protect a hand-patched skill.
    """
    env, agents_md, skill = orphaned_skill_machine(tmp_path)
    r = run_semlf(["uninstall", "agentsmd", str(agents_md), "--force"], env)
    assert r.returncode == 0, r.stderr
    assert skill.is_file(), "a request naming no agent target removed a global skill"
    assert "semantic-linefeeds" not in agents_md.read_text(encoding="utf-8")


def test_naming_every_agent_target_still_collects_the_orphaned_skills(tmp_path):
    """The rule costs no convergence.

    A machine where nothing is installed still gives up the skills it once wrote,
    as long as the request names every agent target.
    """
    env, _, skill = orphaned_skill_machine(tmp_path)
    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()


def test_naming_one_agent_target_never_removes_the_shared_skills(tmp_path):
    """Removal acts on what the request names, never on what it infers about the rest.

    The old rule removed the skills as soon as every unnamed target looked absent.
    Looking absent is not being absent, and the file is gone either way.
    """
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0
    assert skill.is_file()

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert skill.is_file(), "a request naming one agent target removed the shared skill"


def test_naming_every_agent_target_removes_the_shared_skills(tmp_path):
    """The deliberate channel, and the only one."""
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    setup_skill, _ = setup_skill_paths(tmp_path)
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    assert not setup_skill.exists()


def test_a_codex_under_another_home_keeps_its_skills(tmp_path):
    """The case the deleted predicate could not decide.

    Codex installs under one CODEX_HOME and is then operated without that variable,
    so its hook entry is nowhere this environment looks.
    The old rule read that as absent and removed the skills that Codex still reads.
    """
    env = isolated_env(tmp_path)
    codex_env = dict(env, CODEX_HOME=str(tmp_path / "elsewhere-codex"))
    assert run_semlf(["install", "codex"], codex_env).returncode == 0
    assert run_semlf(["install", "opencode"], env).returncode == 0
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert skill.is_file()

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert skill.is_file(), "removed a skill a Codex under another home still reads"
