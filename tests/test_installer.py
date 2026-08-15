import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from check_linefeeds import AGENT_SUPPRESSION_NOTE
from conftest import HAS_GIT, REPO, SCRIPT, git, isolate_git_env

INSTALL = REPO / "scripts" / "install.py"


def run_install(args, env_overrides, cwd=None, timeout=20):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(INSTALL)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )


def isolated_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "HOME": str(home),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }


def auto_env(tmp_path, *stubs):
    # PATH is built from scratch: only a controlled stub directory,
    # so a developer machine that has codex or opencode installed cannot leak into the "not detected" assertions.
    # run_install invokes the installer via sys.executable,
    # so an empty-but-real PATH is safe.
    env = isolated_env(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name in stubs:
        stub = bindir / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    env["PATH"] = str(bindir)
    return env


def codex_hooks_path(tmp_path):
    return tmp_path / "codex" / "hooks.json"


def read_hooks(tmp_path):
    return json.loads(codex_hooks_path(tmp_path).read_text(encoding="utf-8"))


def test_codex_fresh_install_creates_hooks_json(tmp_path):
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    entries = data["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "apply_patch"
    command = entries[0]["hooks"][0]["command"]
    assert "check_linefeeds.py" in command
    assert "--hook codex" in command
    assert "trust" in r.stdout.lower()
    data_root = tmp_path / "data" / "semlf"
    assert str(data_root / "check_linefeeds.py") in command
    assert (data_root / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py"
    ).read_bytes()
    assert (data_root / "README.md").read_bytes() == (REPO / "README.md").read_bytes()


def test_codex_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    before = codex_hooks_path(tmp_path).read_text(encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert "up to date" in r.stdout.lower()
    assert codex_hooks_path(tmp_path).read_text(encoding="utf-8") == before


def test_codex_merge_preserves_existing_entries(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    existing = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "shell",
                    "hooks": [{"type": "command", "command": "echo hi"}],
                }
            ]
        },
        "unrelated": {"keep": True},
    }
    path.write_text(json.dumps(existing), encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    assert data["unrelated"] == {"keep": True}
    commands = [h["hooks"][0]["command"] for h in data["hooks"]["PostToolUse"]]
    assert commands[0] == "echo hi"
    assert any("check_linefeeds.py" in c for c in commands)
    assert path.with_name("hooks.json.bak").exists()


def test_codex_stale_path_is_updated_in_place(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    stale = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "apply_patch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "/old/clone/scripts/check_linefeeds.py" --hook codex',
                        }
                    ],
                }
            ]
        }
    }
    path.write_text(json.dumps(stale), encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "updat" in r.stdout.lower()
    entries = read_hooks(tmp_path)["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert "/old/clone/" not in entries[0]["hooks"][0]["command"]
    data_root = tmp_path / "data" / "semlf"
    assert str(data_root / "check_linefeeds.py") in entries[0]["hooks"][0]["command"]


def test_codex_unparseable_json_is_refused(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 1
    assert path.read_text(encoding="utf-8") == "not json"
    assert not path.with_name("hooks.json.bak").exists()


def test_codex_dry_run_writes_nothing(tmp_path):
    r = run_install(["--codex", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not codex_hooks_path(tmp_path).exists()
    assert "dry-run" in r.stdout.lower()


def test_usage_error_exits_64(tmp_path):
    assert run_install(["--bogus"], isolated_env(tmp_path)).returncode == 64


def test_help_exits_zero(tmp_path):
    r = run_install(["--help"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "--cli" in r.stdout


def test_cli_install_end_to_end(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    dest = tmp_path / "home" / ".local" / "bin" / "semlf"
    assert dest.exists() and os.access(dest, os.X_OK)
    bad = tmp_path / "bad.md"
    bad.write_text("One sentence. Another fused here.\n", encoding="utf-8")
    check = subprocess.run(
        [str(dest), "--file", str(bad)], capture_output=True, text=True
    )
    assert check.returncode == 1


def opencode_dir(tmp_path):
    return tmp_path / "xdg" / "opencode" / "plugins"


def test_opencode_fresh_install_copies_both_files(tmp_path):
    r = run_install(["--opencode"], isolated_env(tmp_path))
    assert r.returncode == 0
    d = opencode_dir(tmp_path)
    assert (d / "semantic-linefeeds.ts").exists()
    assert (d / "check_linefeeds.py").exists()
    src = (REPO / "adapters" / "opencode" / "semantic-linefeeds.ts").read_bytes()
    assert (d / "semantic-linefeeds.ts").read_bytes() == src


def test_opencode_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    r = run_install(["--opencode"], env)
    assert r.returncode == 0
    assert "up to date" in r.stdout.lower()


def test_opencode_changed_file_requires_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    target = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    target.write_text("// user hand-patch\n", encoding="utf-8")
    r = run_install(["--opencode"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr
    assert target.read_text(encoding="utf-8") == "// user hand-patch\n"


def test_opencode_force_overwrites_and_backs_up(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    target = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    target.write_text("// user hand-patch\n", encoding="utf-8")
    r = run_install(["--opencode", "--force"], env)
    assert r.returncode == 0
    src = (REPO / "adapters" / "opencode" / "semantic-linefeeds.ts").read_bytes()
    assert target.read_bytes() == src
    backup = target.with_name(target.name + ".bak")
    assert backup.read_text(encoding="utf-8") == "// user hand-patch\n"


def test_opencode_dry_run_writes_nothing(tmp_path):
    r = run_install(["--opencode", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not opencode_dir(tmp_path).exists()


SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"


def test_agentsmd_creates_file_with_block(tmp_path):
    r = run_install(
        ["--agentsmd", str(tmp_path / "AGENTS.md")],
        isolated_env(tmp_path),
        cwd=tmp_path,
    )
    assert r.returncode == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert SENTINEL_OPEN in text and SENTINEL_CLOSE in text
    assert "Semantic linefeeds" in text
    assert "semlf --file" in text  # portable: no <repo> placeholder, no absolute path
    assert str(REPO) not in text


def test_agentsmd_rerun_is_idempotent(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    run_install(["--agentsmd", str(target)], env, cwd=tmp_path)
    before = target.read_text(encoding="utf-8")
    r = run_install(["--agentsmd", str(target)], env, cwd=tmp_path)
    assert r.returncode == 0
    assert target.read_text(encoding="utf-8") == before


def test_agentsmd_replaces_block_and_keeps_user_text(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# My rules\n\nkeep me\n\n"
        f"{SENTINEL_OPEN}\nstale old block\n{SENTINEL_CLOSE}\n\ntail kept too\n",
        encoding="utf-8",
    )
    r = run_install(["--agentsmd", str(target)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "keep me" in text and "tail kept too" in text
    assert "stale old block" not in text
    assert "Semantic linefeeds" in text


def test_agentsmd_appends_to_existing_file_without_block(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# My rules\n", encoding="utf-8")
    run_install(["--agentsmd", str(target)], isolated_env(tmp_path), cwd=tmp_path)
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# My rules\n")
    assert SENTINEL_OPEN in text


def test_agentsmd_unbalanced_sentinels_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(f"{SENTINEL_OPEN}\nno close marker\n", encoding="utf-8")
    r = run_install(["--agentsmd", str(target)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == f"{SENTINEL_OPEN}\nno close marker\n"


def test_agentsmd_close_before_open_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    original = f"stray text\n{SENTINEL_CLOSE}\nmore text\n{SENTINEL_OPEN}\ntail\n"
    target.write_text(original, encoding="utf-8")
    r = run_install(["--agentsmd", str(target)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == original


def test_agentsmd_two_blocks_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    original = (
        f"{SENTINEL_OPEN}\nfirst block\n{SENTINEL_CLOSE}\n\n"
        f"{SENTINEL_OPEN}\nsecond block\n{SENTINEL_CLOSE}\n"
    )
    target.write_text(original, encoding="utf-8")
    r = run_install(["--agentsmd", str(target)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == original


def test_agentsmd_without_path_refuses(tmp_path):
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=str(tmp_path))
    assert r.returncode == 64
    assert "explicit path" in r.stderr
    assert not (tmp_path / "AGENTS.md").exists()


def test_bare_agentsmd_with_codex_writes_nothing(tmp_path):
    r = run_install(
        ["--codex", "--agentsmd"], isolated_env(tmp_path), cwd=str(tmp_path)
    )
    assert r.returncode == 64
    # Prevalidation must fire before the codex mode acts.
    assert not codex_hooks_path(tmp_path).exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_status_handles_undecodable_hooks_json(tmp_path):
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe{")
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    assert "unreadable" in r.stdout.lower()
    assert r.stderr == ""


@pytest.mark.parametrize(
    "payload,label",
    [
        ({"hooks": []}, "not installed"),
        ([1, 2, 3], "not installed"),
        (
            {"hooks": {"PostToolUse": [{"matcher": "apply_patch", "hooks": 5}]}},
            "not installed",
        ),
        ({"hooks": {"PostToolUse": ["a", "b"]}}, "not installed"),
    ],
)
def test_status_handles_a_malformed_hooks_shape_without_crashing(
    tmp_path, payload, label
):
    # Wrong-shaped-but-parseable JSON must never raise TypeError out of the comprehension:
    # every level is isinstance-guarded before it is indexed or iterated,
    # mirroring plan_codex_hook and doctor's own walk.
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == ""
    assert f"codex hook: {label}" in r.stdout


def test_agentsmd_explicit_path(tmp_path):
    other = tmp_path / "docs-agents.md"
    r = run_install(["--agentsmd", str(other)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    assert SENTINEL_OPEN in other.read_text(encoding="utf-8")


def test_status_reports_all_targets_and_claude_guidance(tmp_path):
    env = isolated_env(tmp_path)
    (Path(env["HOME"]) / ".claude").mkdir()
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    out = r.stdout
    assert "codex hook: not installed" in out
    assert "codex skill: not installed" in out
    assert "opencode plugin: not installed" in out
    assert "agentsmd:" not in out
    assert "claude plugin" in out


def test_status_sees_installed_targets(tmp_path):
    env = isolated_env(tmp_path)
    run_install(
        ["--codex", "--opencode", "--agentsmd", str(tmp_path / "AGENTS.md")],
        env,
        cwd=tmp_path,
    )
    out = run_install([], env, cwd=tmp_path).stdout
    assert "codex hook: installed" in out
    assert "codex skill: exact" in out
    assert "opencode plugin: exact" in out
    assert "agentsmd:" not in out


INSTALL_SH = REPO / "install.sh"


def make_source_repo(tmp_path):
    """A minimal git repo carrying just what install.py needs."""
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    shutil.copytree(REPO / "skills", src / "skills")
    shutil.copytree(REPO / "cli", src / "cli")
    shutil.copy(REPO / "README.md", src / "README.md")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    return src


def test_cloned_installer_imports_standalone(tmp_path):
    # install.py now imports semlf.manifest via a sys.path insert relative to its own checkout;
    # a clone missing cli/ cannot even start.
    repo = make_source_repo(tmp_path)
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util, sys; "
            f"spec = importlib.util.spec_from_file_location('install', r'{repo}/scripts/install.py'); "
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def run_install_sh(args, env_overrides, cwd=None):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        ["sh", str(INSTALL_SH)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def test_install_sh_clones_and_installs_codex(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    r = run_install_sh(
        ["--repo", str(src), "--home", str(home), "--codex"], isolated_env(tmp_path)
    )
    assert r.returncode == 0, r.stderr
    assert (home / "scripts" / "install.py").exists()
    assert codex_hooks_path(tmp_path).exists()


def test_install_sh_clone_installs_the_native_skill(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    r = run_install_sh(
        ["--repo", str(src), "--home", str(home), "--codex"], isolated_env(tmp_path)
    )
    assert r.returncode == 0, r.stderr
    skill = codex_skill_path(tmp_path)
    assert skill.exists()
    assert "CLAUDE_PLUGIN_ROOT" not in skill.read_text(encoding="utf-8")


def test_install_sh_rerun_pulls_and_is_idempotent(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    assert r.returncode == 0, r.stderr
    assert "up to date" in r.stdout.lower()


def test_install_sh_env_repo_and_dry_run(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    env["SEMLF_REPO"] = str(src)
    env["SEMLF_HOME"] = str(home)
    r = run_install_sh(["--codex", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert not codex_hooks_path(tmp_path).exists()
    assert "dry-run" in r.stdout.lower()


def test_install_sh_uses_own_checkout_without_repo(tmp_path):
    never = tmp_path / "never-created"
    env = isolated_env(tmp_path)
    env["SEMLF_HOME"] = str(never)
    r = run_install_sh([], env)
    assert r.returncode == 0, r.stderr
    assert "codex hook:" in r.stdout
    assert not never.exists()


def test_install_sh_quotes_apostrophe_in_pass_through_arg(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    target_dir = tmp_path / "O'Brien"
    target_dir.mkdir()
    target = target_dir / "AGENTS.md"
    r = run_install_sh(
        ["--repo", str(src), "--home", str(home), "--agentsmd", str(target)],
        isolated_env(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    assert target.exists()


def test_install_sh_home_flag_selects_the_checkout_with_an_isolated_home(tmp_path):
    # Proves --home controls where install.sh clones/reuses the checkout,
    # independent of $HOME --
    # not that $HOME can safely be absent entirely
    # (a codex skill install now always resolves Path.home(),
    # so HOME is set here to an isolated directory the way every other installer test isolates it, rather than removed).
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    isolated_home = tmp_path / "isolated-home"
    isolated_home.mkdir()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(isolated_home),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    r = subprocess.run(
        ["sh", str(INSTALL_SH), "--repo", str(src), "--home", str(home), "--codex"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    assert (home / "scripts" / "install.py").exists()


def test_install_sh_status_mode_is_safe_with_home_truly_unset(tmp_path):
    # A true HOME-unset run, with no mode flag at all (status mode), never --codex:
    # install.sh still clones the checkout into --home --
    # the one write this proof allows,
    # and it lands entirely inside tmp_path --
    # but `scripts/install.py` with no mode flag runs status(),
    # which only reads (Path.exists()/.read_text()) and prints;
    # it never calls atomic_write,
    # so nothing can be written outside tmp_path no matter where the real account's $HOME resolves.
    # This proves the bootstrapper itself tolerates a missing $HOME,
    # without ever exercising --codex's skill-install write path --
    # that path is proven hermetically by the isolated-HOME checkout-selection test above instead,
    # where the divergence and force-overwrite behavior stay exactly as designed.
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    r = subprocess.run(
        ["sh", str(INSTALL_SH), "--repo", str(src), "--home", str(home)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    assert "codex skill:" in r.stdout
    assert (home / "scripts" / "install.py").exists()


def test_install_sh_pinned_ref_rerun(tmp_path):
    src = make_source_repo(tmp_path)
    subprocess.run(["git", "-C", str(src), "tag", "v1"], check=True)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    args = ["--repo", str(src), "--home", str(home), "--ref", "v1", "--codex"]
    r1 = run_install_sh(args, env)
    assert r1.returncode == 0, r1.stderr
    r2 = run_install_sh(args, env)
    assert r2.returncode == 0, r2.stderr


def make_self_checkout_repo(tmp_path):
    """A minimal git repo carrying install.sh itself, plus what install.py needs."""
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    shutil.copytree(REPO / "skills", src / "skills")
    shutil.copytree(REPO / "cli", src / "cli")
    shutil.copy(REPO / "README.md", src / "README.md")
    shutil.copy(INSTALL_SH, src / "install.sh")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    subprocess.run(git + ["tag", "v1"], check=True)
    return src


def test_generated_checkout_fixtures_carry_every_registry_source(tmp_path):
    from semlf import registry

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for src in (
        make_source_repo(tmp_path / "a"),
        make_self_checkout_repo(tmp_path / "b"),
    ):
        for row in registry.ROWS:
            assert (src / row.source).is_file(), (src, row.source)


def test_cloned_self_checkout_imports_standalone(tmp_path):
    # Same smoke test as the make_source_repo constructor above, run against the self-checkout fixture's independently-built copy list.
    repo = make_self_checkout_repo(tmp_path)
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util, sys; "
            f"spec = importlib.util.spec_from_file_location('install', r'{repo}/scripts/install.py'); "
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_install_sh_self_checkout_honors_ref(tmp_path):
    # A self-checkout run (install.sh executed from inside its own checkout, no --repo)
    # must still honor an explicit --ref,
    # instead of silently installing whatever HEAD happens to be checked out.
    src = make_self_checkout_repo(tmp_path)
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]

    marker = src / "scripts" / "check_linefeeds.py"
    with marker.open("a", encoding="utf-8") as f:
        f.write("\n# MARKER_AFTER_V1\n")
    skill_marker = src / "skills" / "semantic-linefeeds" / "SKILL.md"
    with skill_marker.open("a", encoding="utf-8") as f:
        f.write("\nSKILL_MARKER_AFTER_V1\n")
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "second commit"], check=True)

    elsewhere = tmp_path / "elsewhere"
    env = isolated_env(tmp_path)
    r = subprocess.run(
        [
            "sh",
            str(src / "install.sh"),
            "--ref",
            "v1",
            "--home",
            str(elsewhere),
            "--codex",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    installed = (elsewhere / "scripts" / "check_linefeeds.py").read_text(
        encoding="utf-8"
    )
    assert "MARKER_AFTER_V1" not in installed
    installed_skill = codex_skill_path(tmp_path).read_text(encoding="utf-8")
    assert "SKILL_MARKER_AFTER_V1" not in installed_skill


def codex_skill_path(tmp_path):
    return tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"


def test_codex_install_writes_the_native_skill(tmp_path):
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    skill = codex_skill_path(tmp_path)
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    data_root = tmp_path / "data" / "semlf"
    assert f'python3 "{data_root}/check_linefeeds.py" --file <files>' in text
    assert "CLAUDE_PLUGIN_ROOT" not in text


def test_codex_skill_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    before = codex_skill_path(tmp_path).read_text(encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert "codex-skill: up to date" in r.stdout
    assert codex_skill_path(tmp_path).read_text(encoding="utf-8") == before


def test_codex_skill_hand_edit_requires_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    skill.write_text("# hand-patched\n", encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr
    assert skill.read_text(encoding="utf-8") == "# hand-patched\n"


def test_codex_skill_force_overwrites_and_backs_up(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    skill.write_text("# hand-patched\n", encoding="utf-8")
    r = run_install(["--codex", "--force"], env)
    assert r.returncode == 0
    data_root = tmp_path / "data" / "semlf"
    assert (
        f'python3 "{data_root}/check_linefeeds.py" --file <files>'
        in skill.read_text(encoding="utf-8")
    )
    backup = skill.with_name(skill.name + ".bak")
    assert backup.read_text(encoding="utf-8") == "# hand-patched\n"


def test_codex_skill_dry_run_writes_nothing(tmp_path):
    r = run_install(["--codex", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not codex_skill_path(tmp_path).exists()


def test_dry_run_reports_a_diverged_skill_at_exit_zero(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.write_text("hand-patched", encoding="utf-8")
    (tmp_path / "state" / "semlf" / "artifacts" / "codex-skill.json").unlink()
    r = run_install(["--codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert skill.read_text(encoding="utf-8") == "hand-patched"


def test_status_reports_codex_skill_states(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: not installed" in r.stdout
    run_install(["--codex"], env)
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: exact" in r.stdout
    codex_skill_path(tmp_path).write_text("# hand-patched\n", encoding="utf-8")
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: edited" in r.stdout
    # A recordless hand-made copy is unrecorded, not diverged/edited --
    # the classifier only calls a mismatch "edited" when a provenance record proves this kit once installed a different set of bytes there.
    entry_file(tmp_path, "codex-skill").unlink()
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: unrecorded" in r.stdout


def test_status_and_rerun_detect_a_crlf_converted_skill(tmp_path):
    # Python's text-mode read universally translates "\r\n" back to "\n".
    # A same-content-but-CRLF copy would therefore compare equal under a read_text() comparison, hiding from both status and a rerun --
    # exactly the gap the hook probe's own byte-level read does not have.
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    skill.write_bytes(
        skill.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: edited" in r.stdout

    r = run_install(["--codex"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr


def test_help_mentions_the_skill_and_the_widened_force_scope(tmp_path):
    r = run_install(["--help"], isolated_env(tmp_path))
    assert r.returncode == 0
    normalized = " ".join(r.stdout.split())
    assert "native semantic-linefeeds skill" in normalized
    assert "codex-skill" in normalized


import install as install_module  # noqa: E402 -- unit-style access to the module itself
from semlf import (
    lifecycle,  # noqa: E402 -- cli/ is on sys.path once install_module is imported
)


def test_codex_skill_dest_is_none_when_home_is_unresolvable(monkeypatch):
    # os.path.expanduser("~") returns its input unchanged when it cannot resolve a home directory;
    # Path.home() raises instead.
    # A real account with no resolvable home is not something a test can set up hermetically,
    # so the failure is simulated by monkeypatching the same expansion the core's own probe (_judgment_layer_present) already treats this way.
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    assert install_module.codex_skill_dest() is None


def test_install_codex_skill_refuses_without_a_resolvable_home(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    planned, refusals = lifecycle.plan_install(["codex"], None, False)
    assert planned == []
    assert any("home" in r.lower() for r in refusals)
    assert list(tmp_path.iterdir()) == []


def test_status_reports_no_home_to_check(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Bypass the other env-resolvable roots (codex_home, opencode_plugins_dir, semlf_data_dir)
    # so only the skill-destination guard, which has no env-var override, is exercised.
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    install_module.status()
    assert "codex skill: no home to check" in capsys.readouterr().out


def test_status_reports_no_home_on_every_path_without_env_overrides(
    monkeypatch, capsys
):
    # No CODEX_HOME/XDG_CONFIG_HOME override here, unlike the test above --
    # this reaches codex_home()'s and opencode_plugins_dir()'s own guards,
    # not just codex_skill_dest()'s, and must not crash on the way.
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.status()
    out = capsys.readouterr().out
    assert rc == 0
    assert "codex hook: no home to check" in out
    assert "opencode plugin: no home to check" in out
    assert "codex skill: no home to check" in out
    assert "cli: no home to check" in out


def test_install_codex_refuses_without_a_resolvable_home(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    planned, refusals = lifecycle.plan_install(["codex"], None, False)
    assert planned == []
    assert any("home" in r.lower() for r in refusals)
    assert list(tmp_path.iterdir()) == []


def test_install_opencode_refuses_without_a_resolvable_home(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    planned, refusals = lifecycle.plan_install(["opencode"], None, False)
    assert planned == []
    assert any("home" in r.lower() for r in refusals)
    assert list(tmp_path.iterdir()) == []


# The loop-stop sentence is pinned in tests/test_judgment_texts.py against the two source files.
# This asserts it again against the installed copy,
# so a rewrite dropping the sentence during installation would not go unnoticed.
LOOP_STOP_SENTENCE = (
    "stop retrying and surface the disagreement to the user instead of "
    "rewriting correct prose again."
)


def test_codex_skill_install_carries_the_bounded_disagreement_text(tmp_path):
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    text = codex_skill_path(tmp_path).read_text(encoding="utf-8")
    assert "## Bounded disagreement" in text
    assert AGENT_SUPPRESSION_NOTE in text
    assert LOOP_STOP_SENTENCE in text


def test_codex_skill_install_has_no_relative_links(tmp_path):
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    text = codex_skill_path(tmp_path).read_text(encoding="utf-8")
    assert "../" not in text


def test_the_installed_skill_is_visible_to_the_codex_hint(tmp_path, monkeypatch):
    # The installed skill body is the installer's real ~4.5KB transformed copy, not a hand-written fixture --
    # large enough that _looks_like_the_skill's 1025-byte read takes its TRUNCATED branch.
    # Nothing else runs the installer and then asks the probe or hook delivery to recognize the result,
    # so a mutation that rejected every truncated file would stay green without this test.
    env = isolated_env(tmp_path)
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    installed = codex_skill_path(tmp_path)
    assert len(installed.read_bytes()) > 1025

    # Run from a skill-free directory
    # so a positive result can only come from the $HOME probe, never from an incidental cwd-relative match.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    # (1) the probe itself, imported straight from the core.
    monkeypatch.setenv("HOME", env["HOME"])
    monkeypatch.chdir(elsewhere)
    from check_linefeeds import _judgment_layer_present

    assert _judgment_layer_present("codex") is True

    # (2) one real Codex advisory hook payload, driven through the same entrypoint an installed hook actually runs.
    text = (
        "This clause runs on and on well past the configured advisory "
        "threshold of one hundred and twenty characters, and the tail "
        "keeps going.\n"
    )
    added = "".join("+" + line + "\n" for line in text.splitlines())
    patch = "*** Begin Patch\n*** Update File: doc.md\n@@\n" + added + "*** End Patch"
    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )
    hook_env = os.environ.copy()
    hook_env["HOME"] = env["HOME"]
    hook = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook", "codex"],
        input=payload,
        capture_output=True,
        text=True,
        env=hook_env,
        cwd=str(elsewhere),
    )
    assert hook.returncode == 0
    context = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "load the semantic-linefeeds skill" in context


def core_version():
    from check_linefeeds import __version__

    return __version__


def test_build_pyz_produces_a_directly_executable_artifact(tmp_path):
    pyz = tmp_path / "semlf"
    install_module.build_pyz(pyz)
    assert pyz.exists() and os.access(pyz, os.X_OK)
    bad = tmp_path / "bad.md"
    bad.write_text("One sentence. Another fused on the same line.\n", encoding="utf-8")
    # Invoke the artifact itself — not through sys.executable —
    # so the shebang and the execute bit are what this test proves.
    r = subprocess.run(
        [str(pyz), "--file", str(bad)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert r.returncode == 1
    assert "fused" in r.stdout


def test_pyz_version_matches_the_core(tmp_path):
    pyz = tmp_path / "semlf"
    install_module.build_pyz(pyz)
    r = subprocess.run([str(pyz), "--version"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == f"semlf {core_version()}"


def test_pyz_state_ignores_timestamps(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    install_module.build_pyz(a)
    install_module.build_pyz(b)
    assert install_module.pyz_state(a) == install_module.pyz_state(b)


def test_pyz_state_ignores_timestamps_even_when_forced_to_differ(tmp_path):
    """Mutation-sensitive proof that pyz_state truly excludes member timestamps.

    Two consecutive builds can coincidentally share ZIP metadata.
    That comparison alone would still pass a mutant that hashes the whole archive including timestamps.
    This test forces every member's date_time to a different fixed value,
    proves the raw bytes changed, then proves pyz_state did not.
    """
    import zipfile as zf

    fresh = tmp_path / "fresh"
    install_module.build_pyz(fresh)
    original_bytes = fresh.read_bytes()

    retimed = tmp_path / "retimed"
    with zf.ZipFile(fresh) as src, zf.ZipFile(retimed, "w") as out:
        for name in src.namelist():
            info = zf.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = src.getinfo(name).compress_type
            out.writestr(info, src.read(name))
    content = retimed.read_bytes()
    retimed.write_bytes(
        b"#!" + install_module.PYZ_INTERPRETER.encode() + b"\n" + content
    )
    retimed.chmod(0o755)

    assert retimed.read_bytes() != original_bytes
    assert install_module.pyz_state(retimed) == install_module.pyz_state(fresh)


def test_pyz_state_detects_a_stripped_execute_bit(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    install_module.build_pyz(a)
    install_module.build_pyz(b)
    b.chmod(0o644)
    assert install_module.pyz_state(a) != install_module.pyz_state(b)


def test_pyz_state_measures_owner_execute_not_effective_access(tmp_path):
    """pyz_state records the owner-execute mode bit, not os.access effective reach.

    Group and other execute staying set must not paper over an owner-execute bit that was actually cleared.
    """
    a, b = tmp_path / "a", tmp_path / "b"
    install_module.build_pyz(a)
    install_module.build_pyz(b)
    b.chmod(0o655)  # owner rw-, group/other execute still set
    assert install_module.pyz_state(a) != install_module.pyz_state(b)
    assert not install_module.pyz_runnable(b)


def test_pyz_state_owner_bit_pinned_against_os_access_mutant(tmp_path, monkeypatch):
    """Pins pyz_state to the mode bit even when os.access would say otherwise.

    A non-root owner already gets a false os.access(path, os.X_OK) for 0o655,
    the same answer stat.S_IXUSR gives,
    so the test above alone would pass under either implementation.
    Forcing os.access to always return True makes the old os.access-based implementation blind to the cleared owner bit —
    if pyz_state ever regresses to consulting os.access,
    the two states below collapse to equal and this assertion catches it.
    """
    monkeypatch.setattr(install_module.os, "access", lambda *a, **k: True)
    a, b = tmp_path / "a", tmp_path / "b"
    install_module.build_pyz(a)
    install_module.build_pyz(b)
    b.chmod(0o655)  # owner rw-, group/other execute still set
    assert install_module.pyz_state(a) != install_module.pyz_state(b)
    assert not install_module.pyz_runnable(b)


def test_pyz_state_detects_a_changed_interpreter(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    install_module.build_pyz(a)
    install_module.build_pyz(b)
    body = b.read_bytes().split(b"\n", 1)[1]
    b.write_bytes(b"#!/usr/bin/env python2\n" + body)
    b.chmod(0o755)
    assert install_module.pyz_state(a) != install_module.pyz_state(b)


def test_pyz_state_is_none_for_a_non_zip_file(tmp_path):
    junk = tmp_path / "junk"
    junk.write_text("not a zip", encoding="utf-8")
    assert install_module.pyz_state(junk) is None
    assert install_module.pyz_state(tmp_path / "missing") is None


def test_pyz_state_is_none_for_an_encrypted_member(tmp_path):
    """Totality over hostile-but-valid archives (fix-report P0-2c).

    zipfile cannot itself write an encrypted member,
    so the general purpose bit flag (bit 0, "encrypted") is set by hand in both the local file header and the central directory of an otherwise normal archive.
    Reading that member then raises RuntimeError deep inside zipfile —
    exactly the shape a hostile pyz could present —
    and pyz_state's identity check must degrade to None, never crash.
    """
    import zipfile as zf

    src = tmp_path / "plain.zip"
    with zf.ZipFile(src, "w") as archive:
        archive.writestr("a.txt", b"hello world")
    data = bytearray(src.read_bytes())
    local_idx = data.find(b"PK\x03\x04")
    central_idx = data.find(b"PK\x01\x02")
    assert local_idx != -1 and central_idx != -1
    data[local_idx + 6] |= 0x01  # local file header flag bit 0
    data[central_idx + 8] |= 0x01  # central directory flag bit 0

    hostile = tmp_path / "hostile.zip"
    hostile.write_bytes(bytes(data))
    hostile.chmod(0o755)
    # Confirm the fixture actually reproduces the hostile condition.
    with zf.ZipFile(hostile) as archive:
        with pytest.raises(RuntimeError):
            archive.read("a.txt")
    assert install_module.pyz_state(hostile) is None


def test_pyz_state_is_none_for_a_tampered_lzma_member(tmp_path):
    """lzma.LZMAError is not an OSError subclass; pyz_state must still degrade to None.

    ZIP_LZMA is a real member compression method zipfile supports writing.
    Corrupting the embedded LZMA filter properties (not the payload)
    makes the decompressor raise lzma.LZMAError on read,
    which the earlier named-exception tuple did not cover —
    this pins the deliberately bare "except Exception" that replaced it.
    """
    import zipfile as zf

    src = tmp_path / "plain.zip"
    with zf.ZipFile(src, "w", zf.ZIP_LZMA) as archive:
        archive.writestr("a.txt", b"hello world" * 200)
    data = bytearray(src.read_bytes())
    local_idx = data.find(b"PK\x03\x04")
    assert local_idx != -1
    fname_len = int.from_bytes(data[local_idx + 26 : local_idx + 28], "little")
    extra_len = int.from_bytes(data[local_idx + 28 : local_idx + 30], "little")
    stream_start = local_idx + 30 + fname_len + extra_len
    # zipfile's LZMA member format: 2-byte version, 2-byte properties size,
    # then the properties themselves — corrupt only that region.
    psize = int.from_bytes(data[stream_start + 2 : stream_start + 4], "little")
    for i in range(stream_start + 4, stream_start + 4 + psize):
        data[i] = 0xFF

    hostile = tmp_path / "hostile-lzma.zip"
    hostile.write_bytes(bytes(data))
    hostile.chmod(0o755)
    # Confirm the fixture actually reproduces the hostile condition.
    import lzma

    with zf.ZipFile(hostile) as archive:
        with pytest.raises(lzma.LZMAError):
            archive.read("a.txt")
    assert install_module.pyz_state(hostile) is None


def test_pyz_runnable_accepts_a_fresh_build(tmp_path):
    pyz = tmp_path / "semlf"
    install_module.build_pyz(pyz)
    assert install_module.pyz_runnable(pyz)


def test_pyz_runnable_rejects_a_symlink_to_a_valid_build(tmp_path):
    """install_cli refuses symlink destinations, so status must never bless one."""
    real = tmp_path / "real"
    install_module.build_pyz(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    assert install_module.pyz_runnable(real)
    assert not install_module.pyz_runnable(link)


def test_pyz_runnable_rejects_each_broken_property(tmp_path):
    import zipfile as zf

    fresh = tmp_path / "fresh"
    install_module.build_pyz(fresh)
    # Stripped execute bit.
    a = tmp_path / "a"
    shutil.copy2(fresh, a)
    a.chmod(0o644)
    assert not install_module.pyz_runnable(a)
    # Foreign interpreter, members untouched.
    b = tmp_path / "b"
    body = fresh.read_bytes().split(b"\n", 1)[1]
    b.write_bytes(b"#!/usr/bin/env python2\n" + body)
    b.chmod(0o755)
    assert not install_module.pyz_runnable(b)
    # An executable zip missing a required member.
    for member in sorted(install_module.PYZ_REQUIRED_MEMBERS):
        c = tmp_path / ("missing-" + member.replace("/", "_"))
        with zf.ZipFile(fresh) as src, zf.ZipFile(c, "w") as out:
            for name in src.namelist():
                if name != member:
                    out.writestr(name, src.read(name))
        content = c.read_bytes()
        c.write_bytes(b"#!" + install_module.PYZ_INTERPRETER.encode() + b"\n" + content)
        c.chmod(0o755)
        assert not install_module.pyz_runnable(c)


def test_status_handles_an_encrypted_member_pyz_at_the_cli_destination(tmp_path):
    # Integration companion to test_pyz_state_is_none_for_an_encrypted_member:
    # a hostile pyz at the real cli destination must not crash status()
    # end to end through the guarded read path — it degrades to "not runnable".
    import zipfile as zf

    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)["--cli"]
    dest.parent.mkdir(parents=True)
    plain = tmp_path / "plain.zip"
    with zf.ZipFile(plain, "w") as archive:
        archive.writestr("a.txt", b"hello world")
    data = bytearray(plain.read_bytes())
    local_idx = data.find(b"PK\x03\x04")
    central_idx = data.find(b"PK\x01\x02")
    data[local_idx + 6] |= 0x01
    data[central_idx + 8] |= 0x01
    dest.write_bytes(
        b"#!" + install_module.PYZ_INTERPRETER.encode() + b"\n" + bytes(data)
    )
    dest.chmod(0o755)
    r = run_install([], env, timeout=10)
    assert r.returncode == 0
    assert "cli: present but not runnable" in r.stdout


def test_install_cli_places_semlf_on_local_bin(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    rc = install_module.install_cli(False, False)
    out = capsys.readouterr().out
    dest = tmp_path / ".local" / "bin" / "semlf"
    assert rc == 0 and dest.exists() and os.access(dest, os.X_OK)
    assert "installed" in out
    assert "would install" not in out


def test_cli_adopt_recreates_a_deleted_record(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    shutil.rmtree(tmp_path / "state" / "semlf")
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    record = tmp_path / "state" / "semlf" / "artifacts" / "cli.json"
    assert record.is_file()


def test_install_cli_is_idempotent_and_still_notes_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert install_module.install_cli(False, False) == 0
    capsys.readouterr()
    assert install_module.install_cli(False, False) == 0
    out = capsys.readouterr().out
    assert "already installed" in out
    # The PATH gap persists across a no-op rerun, so the note must too.
    assert "not on PATH" in out


def test_install_cli_refuses_divergent_file_without_force(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.parent.mkdir(parents=True)
    dest.write_text("something else", encoding="utf-8")
    assert install_module.install_cli(False, False) == 1
    assert "refusing" in capsys.readouterr().err


def test_install_cli_force_backs_up_the_old_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.parent.mkdir(parents=True)
    dest.write_text("something else", encoding="utf-8")
    assert install_module.install_cli(False, True) == 0
    backup = dest.with_name("semlf.bak")
    assert backup.read_text(encoding="utf-8") == "something else"
    assert os.access(dest, os.X_OK)


def test_install_cli_refuses_a_directory_destination(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.mkdir(parents=True)
    assert install_module.install_cli(False, True) == 1
    assert "refusing" in capsys.readouterr().err
    assert dest.is_dir()


def test_install_cli_refuses_symlink_destinations_even_with_force(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.parent.mkdir(parents=True)
    real = tmp_path / "real-file"
    real.write_text("regular", encoding="utf-8")
    dest.symlink_to(real)  # a symlink TO a regular file — is_file() would say yes
    assert install_module.install_cli(False, True) == 1
    assert "symlink" in capsys.readouterr().err
    assert real.read_text(encoding="utf-8") == "regular"
    dest.unlink()
    dest.symlink_to(tmp_path / "nowhere")  # dangling — exists() would say no
    assert install_module.install_cli(False, True) == 1
    assert "symlink" in capsys.readouterr().err


def test_publish_new_refuses_a_destination_that_appeared(tmp_path):
    """The exclusive primitive itself: a dest appearing after classification is refused."""
    staged = tmp_path / "staged"
    install_module.build_pyz(staged)
    dest = tmp_path / "dest"
    dest.write_text("appeared meanwhile", encoding="utf-8")
    assert install_module._publish_new(staged, dest) is False
    assert dest.read_text(encoding="utf-8") == "appeared meanwhile"


def test_install_cli_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert install_module.install_cli(True, False) == 0
    assert "would install" in capsys.readouterr().out
    assert not (tmp_path / ".local").exists()


def test_cli_bin_dest_is_none_when_home_is_unresolvable(monkeypatch):
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    assert install_module.cli_bin_dest() is None


def test_install_cli_refuses_without_a_resolvable_home(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.install_cli(False, False)
    assert rc == 1
    assert "home" in capsys.readouterr().err.lower()
    assert list(tmp_path.iterdir()) == []


def test_status_reports_the_cli_states(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)
    install_module.status()
    assert "cli: not installed" in capsys.readouterr().out
    install_module.install_cli(False, False)
    capsys.readouterr()
    install_module.status()
    assert "cli: installed" in capsys.readouterr().out
    (tmp_path / ".local" / "bin" / "semlf").chmod(0o644)
    install_module.status()
    assert "not runnable" in capsys.readouterr().out


def test_status_is_silent_about_the_shim_when_path_semlf_is_its_own_cli(tmp_path):
    # shim_warning compares against sys.argv[0] by default, which on the checkout door is install.py itself, not the pyz.
    # A bare comparison would falsely warn about the very cli status just reported installed.
    # status() must pass its own cli_bin_dest() as the expected target instead.
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    env["PATH"] = str(tmp_path / "home" / ".local" / "bin")
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    assert "on PATH resolves to" not in r.stdout


def test_status_warns_about_a_foreign_semlf_shadowing_the_installed_cli(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    foreign_dir = tmp_path / "foreign-bin"
    foreign_dir.mkdir()
    foreign = foreign_dir / "semlf"
    foreign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    foreign.chmod(0o755)
    env["PATH"] = str(foreign_dir)
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    assert "on PATH resolves to" in r.stdout


def test_agents_block_carries_no_absolute_path():
    block = lifecycle.agents_block()
    assert "semlf --file" in block
    assert "<repo>" not in block
    assert str(install_module.REPO) not in block


def test_agentsmd_warns_when_semlf_is_missing(tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = isolated_env(tmp_path)
    env["PATH"] = str(empty_bin)
    target = tmp_path / "AGENTS.md"
    r = run_install(["--agentsmd", str(target)], env)
    assert r.returncode == 0
    assert "not on PATH" in r.stdout
    # The gap persists on the idempotent rerun, so the warning must too.
    r = run_install(["--agentsmd", str(target)], env)
    assert r.returncode == 0
    assert "not on PATH" in r.stdout


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_pyz_runs_staged_mode_in_a_repository(tmp_path, monkeypatch):
    """The artifact the pre-commit entry invokes must own the git modes."""
    isolate_git_env(monkeypatch)
    pyz = tmp_path / "semlf"
    install_module.build_pyz(pyz)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    git("init", "-q", cwd=repo_dir)
    bad = repo_dir / "doc.md"
    bad.write_text("One sentence. Another fused on the same line.\n", encoding="utf-8")
    git("add", "doc.md", cwd=repo_dir)
    r = subprocess.run(
        [str(pyz), "--staged"], capture_output=True, text=True, cwd=str(repo_dir)
    )
    assert r.returncode == 1
    assert "fused" in r.stdout


def install_cli_once(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    return tmp_path / "home" / ".local" / "bin" / "semlf", env


def patch_installed_cli(dest):
    """Overwrite dest with content pyz_state actually sees as divergent.

    Bytes merely appended after a zipapp's central directory sit in the zip comment region
    and are invisible to every zip reader (comment length is read from the EOCD record, not inferred from file size),
    so they would not register as a divergence at all;
    a full rewrite is the only reliable way to simulate a hand-patched artifact.
    """
    patched = b"#!/usr/bin/env python3\n# hand-patched\n"
    dest.write_bytes(patched)
    return patched


def test_force_refuses_when_a_backup_already_exists(tmp_path):
    dest, env = install_cli_once(tmp_path)
    patched = patch_installed_cli(dest)
    bak = dest.with_name("semlf.bak")
    bak.write_bytes(b"precious earlier backup")
    r = run_install(["--cli", "--force"], env)
    assert r.returncode == 1
    assert "semlf.bak" in r.stderr
    assert bak.read_bytes() == b"precious earlier backup"
    assert dest.read_bytes() == patched
    leftovers = [
        p for p in dest.parent.iterdir() if p.name not in ("semlf", "semlf.bak")
    ]
    assert leftovers == []


def test_force_refuses_a_backup_symlink_without_following(tmp_path):
    dest, env = install_cli_once(tmp_path)
    patch_installed_cli(dest)
    target = tmp_path / "elsewhere"
    bak = dest.with_name("semlf.bak")
    bak.symlink_to(target)
    r = run_install(["--cli", "--force"], env)
    assert r.returncode == 1
    assert not target.exists()
    assert bak.is_symlink()
    leftovers = [
        p for p in dest.parent.iterdir() if p.name not in ("semlf", "semlf.bak")
    ]
    assert leftovers == []


def test_force_with_a_free_backup_slot_still_replaces(tmp_path):
    dest, env = install_cli_once(tmp_path)
    patched = patch_installed_cli(dest)
    r = run_install(["--cli", "--force"], env)
    assert r.returncode == 0
    assert dest.with_name("semlf.bak").read_bytes() == patched
    assert dest.read_bytes() != patched


def test_dry_run_force_reports_an_occupied_backup_slot(tmp_path):
    # Dry-run dominates the cli leg too:
    # an occupied slot is a would-refuse line at exit 0, not a real refusal.
    dest, env = install_cli_once(tmp_path)
    patch_installed_cli(dest)
    dest.with_name("semlf.bak").write_bytes(b"occupied")
    r = run_install(["--cli", "--force", "--dry-run"], env)
    assert r.returncode == 0
    assert "semlf.bak" in r.stdout
    assert "would refuse" in r.stdout


def test_dry_run_force_with_a_free_slot_reports_and_writes_nothing(tmp_path):
    dest, env = install_cli_once(tmp_path)
    patched = patch_installed_cli(dest)
    r = run_install(["--cli", "--force", "--dry-run"], env)
    assert r.returncode == 0
    assert "would back up and replace" in r.stdout
    assert dest.read_bytes() == patched
    assert not dest.with_name("semlf.bak").exists()


def load_install_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("install", INSTALL)
    install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install)
    return install


def test_a_failed_backup_releases_the_slot(tmp_path, monkeypatch):
    # Helper-level: inject a copystat failure
    # and prove the slot is released, the destination untouched, and the error surfaced.
    install = load_install_module()
    src = tmp_path / "src"
    src.write_bytes(b"artifact bytes")
    bak = tmp_path / "semlf.bak"

    def boom(*_args, **_kwargs):
        raise OSError("copystat failed")

    monkeypatch.setattr(install.shutil, "copystat", boom)
    with pytest.raises(OSError):
        install._exclusive_backup(src, bak, b"artifact bytes")
    assert not bak.exists()
    assert src.read_bytes() == b"artifact bytes"


def test_backup_preserves_the_classified_snapshot_not_a_later_read(
    tmp_path, monkeypatch
):
    # Red-capable: dest is mutated on disk between classification and the backup write —
    # from inside the second build_pyz call install_cli makes in that exact window —
    # simulating a same-user race.
    # The backup must hold what classification saw,
    # never a fresh read of the (now different) live destination.
    install = load_install_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert install.install_cli(dry=False, force=False) == 0
    dest = tmp_path / "home" / ".local" / "bin" / "semlf"
    patched = patch_installed_cli(dest)

    real_build_pyz = install.build_pyz
    calls = []

    def spy_build_pyz(target):
        real_build_pyz(target)
        calls.append(target)
        if len(calls) == 2:
            # The staged-replacement build: classification already ran.
            dest.write_bytes(b"mutated-after-classification\n")

    monkeypatch.setattr(install, "build_pyz", spy_build_pyz)

    assert install.install_cli(dry=False, force=True) == 0
    bak = dest.with_name("semlf.bak")
    assert bak.read_bytes() == patched


def test_a_failed_backup_fails_install_cli_cleanly(tmp_path, monkeypatch):
    # Call-site level: the same failure through install_cli must be a normal exit-1 diagnostic —
    # staged file cleaned up, destination unchanged, backup slot free, no traceback.
    # This test fails if install_cli ever stops catching the helper's OSError.
    install = load_install_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert install.install_cli(dry=False, force=False) == 0
    dest = tmp_path / "home" / ".local" / "bin" / "semlf"
    patched = patch_installed_cli(dest)

    def boom(*_args, **_kwargs):
        raise OSError("backup failed")

    monkeypatch.setattr(install, "_exclusive_backup", boom)
    assert install.install_cli(dry=False, force=True) == 1
    assert dest.read_bytes() == patched
    assert not dest.with_name("semlf.bak").exists()
    leftovers = [p for p in dest.parent.iterdir() if p.name != "semlf"]
    assert leftovers == []


# --- Provenance manifest and managed upgrade ---------------------------


def entry_file(tmp_path, name):
    return tmp_path / "state" / "semlf" / "artifacts" / (name + ".json")


def read_entry(tmp_path, name):
    return json.loads(entry_file(tmp_path, name).read_text(encoding="utf-8"))


def test_cli_install_records_provenance(tmp_path):
    dest, env = install_cli_once(tmp_path)
    entry = read_entry(tmp_path, "cli")
    assert entry["path"] == str(dest)
    import hashlib

    assert entry["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()


def test_managed_older_release_upgrades_without_force(tmp_path):
    dest, env = install_cli_once(tmp_path)
    older = b"#!/usr/bin/env python3\n# an older release's bytes\n"
    dest.write_bytes(older)
    import hashlib

    entry = read_entry(tmp_path, "cli")
    entry["sha256"] = hashlib.sha256(older).hexdigest()
    entry["version"] = "0.5.0"
    entry_file(tmp_path, "cli").write_text(json.dumps(entry), encoding="utf-8")
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    assert dest.read_bytes() != older
    assert not dest.with_name("semlf.bak").exists()


def test_managed_upgrade_ignores_an_occupied_backup_slot(tmp_path):
    # The backup slot gates only the unmanaged --force path;
    # a managed upgrade replaces a recorded release and never touches semlf.bak,
    # so dry-run and real run must both succeed with the slot occupied.
    dest, env = install_cli_once(tmp_path)
    older = b"#!/usr/bin/env python3\n# an older release's bytes\n"
    dest.write_bytes(older)
    import hashlib

    entry = read_entry(tmp_path, "cli")
    entry["sha256"] = hashlib.sha256(older).hexdigest()
    entry_file(tmp_path, "cli").write_text(json.dumps(entry), encoding="utf-8")
    bak = dest.with_name("semlf.bak")
    bak.write_bytes(b"occupied")
    r = run_install(["--cli", "--dry-run"], env)
    assert r.returncode == 0
    assert "managed" in r.stdout
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    assert bak.read_bytes() == b"occupied"


def test_hand_edited_copy_still_refuses_without_force(tmp_path):
    # A byte-append lands in the pyz's zip-comment region and never registers as a divergence (patch_installed_cli's docstring explains why).
    # patch_installed_cli is used here instead, since it reliably diverges pyz identity.
    dest, env = install_cli_once(tmp_path)
    patch_installed_cli(dest)
    r = run_install(["--cli"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr


def test_corrupt_state_means_unrecorded_not_a_crash(tmp_path):
    dest, env = install_cli_once(tmp_path)
    patch_installed_cli(dest)  # see test_hand_edited_copy_still_refuses_without_force
    entry_file(tmp_path, "cli").write_text("{broken", encoding="utf-8")
    r = run_install(["--cli"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr


def test_codex_skill_install_records_provenance(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    entry = read_entry(tmp_path, "codex-skill")
    import hashlib

    dest = codex_skill_path(tmp_path)
    assert entry["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()


def test_opencode_install_records_both_files(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--opencode"], env)
    assert r.returncode == 0
    import hashlib

    d = opencode_dir(tmp_path)
    plugin_entry = read_entry(tmp_path, "opencode-plugin")
    assert (
        plugin_entry["sha256"]
        == hashlib.sha256((d / "semantic-linefeeds.ts").read_bytes()).hexdigest()
    )
    checker_entry = read_entry(tmp_path, "opencode-checker")
    assert (
        checker_entry["sha256"]
        == hashlib.sha256((d / "check_linefeeds.py").read_bytes()).hexdigest()
    )


def test_managed_older_skill_upgrades_without_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    older = b"# an older skill body\n"
    skill.write_bytes(older)
    import hashlib

    entry = read_entry(tmp_path, "codex-skill")
    entry["sha256"] = hashlib.sha256(older).hexdigest()
    entry["version"] = "0.5.0"
    entry_file(tmp_path, "codex-skill").write_text(json.dumps(entry), encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert skill.read_bytes() != older
    assert not skill.with_name(skill.name + ".bak").exists()


def test_managed_older_opencode_plugin_upgrades_without_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    plugin = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    older = b"// an older plugin body\n"
    plugin.write_bytes(older)
    import hashlib

    entry = read_entry(tmp_path, "opencode-plugin")
    entry["sha256"] = hashlib.sha256(older).hexdigest()
    entry["version"] = "0.5.0"
    entry_file(tmp_path, "opencode-plugin").write_text(
        json.dumps(entry), encoding="utf-8"
    )
    r = run_install(["--opencode"], env)
    assert r.returncode == 0
    assert plugin.read_bytes() != older
    assert not plugin.with_name(plugin.name + ".bak").exists()


def test_occupied_backup_slot_refuses_the_skill_uniformly(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    skill.write_text("# hand-patched\n", encoding="utf-8")
    bak = skill.with_name(skill.name + ".bak")
    bak.write_bytes(b"occupied")
    r = run_install(["--codex"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr
    r = run_install(["--codex", "--force"], env)
    assert r.returncode == 1
    assert str(bak) in r.stderr
    assert bak.read_bytes() == b"occupied"
    assert skill.read_text(encoding="utf-8") == "# hand-patched\n"


def test_occupied_backup_slot_refuses_the_opencode_plugin_uniformly(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    plugin = opencode_dir(tmp_path) / "semantic-linefeeds.ts"
    plugin.write_text("// hand-patched\n", encoding="utf-8")
    bak = plugin.with_name(plugin.name + ".bak")
    bak.write_bytes(b"occupied")
    r = run_install(["--opencode"], env)
    assert r.returncode == 1
    assert "--force" in r.stderr
    r = run_install(["--opencode", "--force"], env)
    assert r.returncode == 1
    assert str(bak) in r.stderr
    assert bak.read_bytes() == b"occupied"
    assert plugin.read_text(encoding="utf-8") == "// hand-patched\n"


def test_dry_run_writes_no_state(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--cli", "--dry-run"], env)
    assert not (tmp_path / "state").exists()


def test_codex_dry_run_writes_no_state(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex", "--dry-run"], env)
    assert not (tmp_path / "state").exists()


def test_opencode_dry_run_writes_no_state(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode", "--dry-run"], env)
    assert not (tmp_path / "state").exists()


def test_dry_run_over_an_already_current_cli_does_not_create_a_state_entry(tmp_path):
    # The adoption guard:
    # install_cli's dry-run branch must not call _adopt_current_cli, so a dry-run rerun over an install that is already current never (re)creates state.
    dest, env = install_cli_once(tmp_path)
    shutil.rmtree(tmp_path / "state")
    r = run_install(["--cli", "--dry-run"], env)
    assert r.returncode == 0
    assert "already installed" in r.stdout
    assert not (tmp_path / "state").exists()


def test_adoption_never_rereads_the_destination(tmp_path, monkeypatch):
    # Red-capable:
    # every destination reader is booby-trapped, so any future re-read inside adoption fails this test immediately.
    install = load_install_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert install.install_cli(dry=False, force=False) == 0
    dest = tmp_path / "home" / ".local" / "bin" / "semlf"
    snapshot = install.guarded_pyz_state(dest)

    def boom(*_args, **_kwargs):
        raise AssertionError("adoption re-read the destination")

    monkeypatch.setattr(install.manifest, "read_regular_bytes", boom)
    monkeypatch.setattr(install.manifest, "classify", boom)
    install._adopt_current_cli(dest, snapshot)
    entry = json.loads(
        (tmp_path / "state" / "semlf" / "artifacts" / "cli.json").read_text(
            encoding="utf-8"
        )
    )
    assert entry["sha256"] == install.manifest.sha256_bytes(snapshot[1])


def single_file_destinations(tmp_path):
    return {
        "--codex": tmp_path
        / "home"
        / ".agents"
        / "skills"
        / "semantic-linefeeds"
        / "SKILL.md",
        "--opencode": tmp_path
        / "xdg"
        / "opencode"
        / "plugins"
        / "semantic-linefeeds.ts",
        "--cli": tmp_path / "home" / ".local" / "bin" / "semlf",
    }


@pytest.mark.parametrize("mode", ["--codex", "--opencode", "--cli"])
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_directory_at_a_destination_refuses_install(tmp_path, mode, force):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)[mode]
    dest.mkdir(parents=True)
    (dest / "keep").write_text("x", encoding="utf-8")
    r = run_install([mode] + force, env)
    assert r.returncode == 1
    assert (dest / "keep").exists()


@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_directory_at_the_opencode_checker_destination_refuses_install(
    tmp_path, force
):
    env = isolated_env(tmp_path)
    dest = tmp_path / "xdg" / "opencode" / "plugins" / "check_linefeeds.py"
    dest.mkdir(parents=True)
    (dest / "keep").write_text("x", encoding="utf-8")
    r = run_install(["--opencode"] + force, env)
    assert r.returncode == 1
    assert (dest / "keep").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no mkfifo")
@pytest.mark.parametrize("mode", ["--codex", "--opencode"])
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_fifo_at_a_skill_or_opencode_destination_refuses_install(
    tmp_path, mode, force
):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)[mode]
    dest.parent.mkdir(parents=True)
    os.mkfifo(dest)
    r = run_install([mode] + force, env, timeout=10)
    assert r.returncode == 1
    assert stat.S_ISFIFO(os.lstat(dest).st_mode)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no mkfifo")
def test_a_fifo_at_the_cli_destination_refuses_install_and_status_reports_not_runnable(
    tmp_path,
):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)["--cli"]
    dest.parent.mkdir(parents=True)
    os.mkfifo(dest)
    r = run_install(["--cli"], env, timeout=10)
    assert r.returncode == 1
    r = run_install([], env, timeout=10)
    assert r.returncode == 0
    assert "not runnable" in r.stdout
    assert stat.S_ISFIFO(os.lstat(dest).st_mode)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no mkfifo")
def test_status_reports_unreadable_for_a_fifo_skill_destination(tmp_path):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)["--codex"]
    dest.parent.mkdir(parents=True)
    os.mkfifo(dest)
    r = run_install([], env, timeout=10)
    assert r.returncode == 0
    assert "codex skill: special" in r.stdout


@pytest.mark.parametrize("mode", ["--codex", "--opencode"])
@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_symlink_at_a_skill_or_opencode_destination_refuses_install(
    tmp_path, mode, dangling, force
):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)[mode]
    dest.parent.mkdir(parents=True)
    if dangling:
        target = tmp_path / "nowhere"
    else:
        target = tmp_path / "real-target"
        target.write_text("x", encoding="utf-8")
    dest.symlink_to(target)
    r = run_install([mode] + force, env)
    assert r.returncode == 1
    assert dest.is_symlink()
    if not dangling:
        assert target.read_text(encoding="utf-8") == "x"


def test_status_reports_unreadable_for_a_dangling_symlink_opencode_destination(
    tmp_path,
):
    env = isolated_env(tmp_path)
    dest = single_file_destinations(tmp_path)["--opencode"]
    dest.parent.mkdir(parents=True)
    dest.symlink_to(tmp_path / "nowhere")
    r = run_install([], env)
    assert r.returncode == 0
    assert "opencode plugin: symlink" in r.stdout


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no mkfifo")
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_fifo_at_the_agentsmd_target_refuses_install(tmp_path, force):
    target = tmp_path / "AGENTS.md"
    os.mkfifo(target)
    r = run_install(
        ["--agentsmd", str(target)] + force, isolated_env(tmp_path), timeout=10
    )
    assert r.returncode == 1
    assert stat.S_ISFIFO(os.lstat(target).st_mode)


@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_symlink_at_the_agentsmd_target_refuses_install(tmp_path, dangling, force):
    target = tmp_path / "AGENTS.md"
    if dangling:
        real = tmp_path / "nowhere"
    else:
        real = tmp_path / "real-target"
        real.write_text("x", encoding="utf-8")
    target.symlink_to(real)
    r = run_install(["--agentsmd", str(target)] + force, isolated_env(tmp_path))
    assert r.returncode == 1
    assert target.is_symlink()
    if not dangling:
        assert real.read_text(encoding="utf-8") == "x"


@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_directory_at_the_agentsmd_target_refuses_install(tmp_path, force):
    # Asserts the named refusal message and a clean stderr, not just exit 1:
    # the pre-fix code let target.read_text() raise IsADirectoryError straight out of install_agentsmd,
    # which also exits 1 but via a traceback rather than a diagnosed refusal.
    target = tmp_path / "AGENTS.md"
    target.mkdir()
    (target / "keep").write_text("x", encoding="utf-8")
    r = run_install(["--agentsmd", str(target)] + force, isolated_env(tmp_path))
    assert r.returncode == 1
    assert (target / "keep").exists()
    assert "not a readable regular file" in r.stderr
    assert "Traceback" not in r.stderr


def test_undecodable_bytes_at_the_agentsmd_target_refuse_install(tmp_path):
    # Closes the UnicodeDecodeError branch install_agentsmd's guarded read adds:
    # a present, readable, regular file that just isn't UTF-8 must refuse,
    # rather than be silently treated as empty or overwritten.
    # Asserts the named message and a clean stderr, not just exit 1:
    # the pre-fix code let target.read_text() raise UnicodeDecodeError straight out of install_agentsmd,
    # which also exits 1 but via a traceback rather than a diagnosed refusal.
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"\xff\xfe{")
    r = run_install(["--agentsmd", str(target)], isolated_env(tmp_path))
    assert r.returncode == 1
    assert target.read_bytes() == b"\xff\xfe{"
    assert "cannot decode it as" in r.stderr
    assert "Traceback" not in r.stderr


def test_codex_refuses_a_hooks_bak_symlink_without_following(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    existing = {"hooks": {"PostToolUse": []}}
    original_text = json.dumps(existing)
    path.write_text(original_text, encoding="utf-8")
    target = tmp_path / "elsewhere"
    bak = path.with_name("hooks.json.bak")
    bak.symlink_to(target)
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 1
    assert not target.exists()
    assert bak.is_symlink()
    assert path.read_text(encoding="utf-8") == original_text


# --- The composed request: every selected leg preflights as one plan -----


def test_a_refusing_codex_leg_aborts_the_cli_leg_too(tmp_path):
    env = isolated_env(tmp_path)
    root = tmp_path / "data" / "semlf"
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("diverged", encoding="utf-8")
    r = run_install(["--codex", "--cli"], env)
    assert r.returncode == 1
    assert not (tmp_path / "home" / ".local" / "bin" / "semlf").exists()
    assert not (tmp_path / "codex" / "hooks.json").exists()


def test_a_refusing_cli_leg_aborts_the_codex_leg_too(tmp_path):
    env = isolated_env(tmp_path)
    bin_dir = tmp_path / "home" / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "semlf").symlink_to(bin_dir / "elsewhere")
    r = run_install(["--codex", "--cli"], env)
    assert r.returncode == 1
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (tmp_path / "data").exists()


def test_both_doors_render_identical_artifacts(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    env_a = isolated_env(tmp_path / "a")
    r = run_install(["--codex"], env_a)
    assert r.returncode == 0, r.stderr
    # The package door runs from a built zipapp, not the checkout.
    import importlib

    install_module_ = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install_module_.build_pyz(pyz)
    env_b = isolated_env(tmp_path / "b")
    full_env = os.environ.copy()
    full_env.update(env_b)
    r = subprocess.run(
        [sys.executable, str(pyz), "install", "codex"],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    root_a = str(tmp_path / "a" / "data").encode()
    root_b = str(tmp_path / "b" / "data").encode()
    for rel in (
        ("data", "semlf", "check_linefeeds.py"),
        ("data", "semlf", "README.md"),
        ("home", ".agents", "skills", "semantic-linefeeds", "SKILL.md"),
        ("codex", "hooks.json"),
    ):
        a = Path(tmp_path, "a", *rel).read_bytes()
        b = Path(tmp_path, "b", *rel).read_bytes()
        assert a.replace(root_a, b"ROOT") == b.replace(root_b, b"ROOT"), rel


# --- Uninstall -----------------------------------------------------------


def test_uninstall_requires_a_mode_flag(tmp_path):
    r = run_install(["--uninstall"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_uninstall_codex_removes_only_our_entries(tmp_path):
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "shell",
                            "hooks": [{"type": "command", "command": "echo hi"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    run_install(["--codex"], env)
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    commands = [h["hooks"][0]["command"] for h in data["hooks"]["PostToolUse"]]
    assert commands == ["echo hi"]
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert not skill.exists()
    assert not entry_file(tmp_path, "codex-skill").exists()


def test_uninstall_codex_when_absent_is_a_noop(tmp_path):
    r = run_install(["--uninstall", "--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "not installed" in r.stdout


def test_a_non_directory_codex_home_refuses_uninstall_without_touching_anything(
    tmp_path,
):
    # Same P1-1 pattern as _plan_file/_plan_cli/_plan_agentsmd, one level up:
    # $CODEX_HOME itself is a plain file, so lstat on its hooks.json raises
    # NotADirectoryError, which must refuse, not read as "not installed".
    env = isolated_env(tmp_path)
    codex_home_path = Path(env["CODEX_HOME"])
    codex_home_path.write_text("not a directory", encoding="utf-8")
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert codex_home_path.is_file()
    assert codex_home_path.read_text(encoding="utf-8") == "not a directory"


def test_an_edited_skill_refuses_the_whole_codex_request(tmp_path):
    # Preflight atomicity: the hook entry and the manifest must survive untouched when the skill leg refuses — never a partial uninstall.
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8"
    )
    hooks_before = codex_hooks_path(tmp_path).read_bytes()
    state_before = entry_file(tmp_path, "codex-skill").read_bytes()
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert skill.exists()
    assert codex_hooks_path(tmp_path).read_bytes() == hooks_before
    assert entry_file(tmp_path, "codex-skill").read_bytes() == state_before
    r = run_install(["--uninstall", "--codex", "--force"], env)
    assert r.returncode == 0
    assert not skill.exists()


def test_one_edited_opencode_file_refuses_both(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    d = tmp_path / "xdg" / "opencode" / "plugins"
    plugin = d / "semantic-linefeeds.ts"
    plugin.write_text(
        plugin.read_text(encoding="utf-8") + "\n// local\n", encoding="utf-8"
    )
    r = run_install(["--uninstall", "--opencode"], env)
    assert r.returncode == 1
    assert plugin.exists()
    assert (d / "check_linefeeds.py").exists()


def test_uninstall_preserves_a_lookalike_foreign_hook(tmp_path):
    # Structural ownership: a foreign command that merely mentions the checker's filename is not ours and must survive byte-for-byte.
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "shell",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo check_linefeeds.py",
                                }
                            ],
                        },
                        {
                            "matcher": "apply_patch",
                            "hooks": [{"type": "command", "command": 7}],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    run_install(["--codex"], env)
    r = run_install(["--uninstall", "--codex", "--force"], env)
    assert r.returncode == 0
    data = read_hooks(tmp_path)
    commands = [h["hooks"][0]["command"] for h in data["hooks"]["PostToolUse"]]
    assert "echo check_linefeeds.py" in commands
    assert 7 in commands


@pytest.mark.parametrize("mode", ["--codex", "--opencode", "--cli"])
@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_directory_at_any_single_file_target_refuses_uninstall(tmp_path, mode, force):
    # Directories are refusal-only under every flag: removing a tree is never this verb's one-file unlink.
    # single_file_destinations is the same helper the install-side directory matrix uses.
    env = isolated_env(tmp_path)
    run_install([mode], env)
    dest = single_file_destinations(tmp_path)[mode]
    dest.unlink()
    dest.mkdir()
    (dest / "keep").write_text("x", encoding="utf-8")
    r = run_install(["--uninstall", mode] + force, env)
    assert r.returncode == 1
    assert (dest / "keep").exists()


def test_uninstall_refuses_a_symlinked_skill_without_force(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    real = tmp_path / "moved-skill.md"
    real.write_bytes(skill.read_bytes())
    skill.unlink()
    skill.symlink_to(real)
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert skill.is_symlink()
    r = run_install(["--uninstall", "--codex", "--force"], env)
    assert r.returncode == 0
    assert not skill.is_symlink()
    assert real.exists()  # --force unlinks the link itself, never the target


def test_uninstall_opencode_removes_matching_files(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--opencode"], env)
    r = run_install(["--uninstall", "--opencode"], env)
    assert r.returncode == 0
    d = tmp_path / "xdg" / "opencode" / "plugins"
    assert not (d / "semantic-linefeeds.ts").exists()
    assert not (d / "check_linefeeds.py").exists()


def test_uninstall_cli_removes_a_managed_install(tmp_path):
    dest, env = install_cli_once(tmp_path)
    r = run_install(["--uninstall", "--cli"], env)
    assert r.returncode == 0
    assert not dest.exists()
    assert not entry_file(tmp_path, "cli").exists()


def test_uninstall_cli_refuses_an_edited_copy_without_force(tmp_path):
    dest, env = install_cli_once(tmp_path)
    dest.write_bytes(dest.read_bytes() + b"#patched\n")
    r = run_install(["--uninstall", "--cli"], env)
    assert r.returncode == 1
    assert dest.exists()


def test_uninstall_agentsmd_removes_only_the_block(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("# Mine\n\nkeep this\n", encoding="utf-8")
    run_install(["--agentsmd", str(target)], env)
    r = run_install(["--uninstall", "--agentsmd", str(target)], env)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "semantic-linefeeds" not in text
    assert "keep this" in text


def test_uninstall_refuses_a_symlinked_hooks_json(tmp_path):
    # Shared files are refusal-only: no flag unlinks hooks.json, and a symlink standing in for it refuses even under --force.
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    hooks = codex_hooks_path(tmp_path)
    real = tmp_path / "moved-hooks.json"
    real.write_bytes(hooks.read_bytes())
    hooks.unlink()
    hooks.symlink_to(real)
    for args in (["--uninstall", "--codex"], ["--uninstall", "--codex", "--force"]):
        r = run_install(args, env)
        assert r.returncode == 1
        assert hooks.is_symlink()
        assert real.exists()


def test_uninstall_with_no_home_refuses(monkeypatch):
    # POSIX expanduser falls back to the pwd database.
    # So "no home" is only reachable by making expanduser return its input unchanged — the exact condition the destination helpers guard on.
    install = load_install_module()
    monkeypatch.setattr(install.manifest.os.path, "expanduser", lambda p: p)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    install_args = type(
        "Args",
        (),
        {
            "codex": False,
            "opencode": False,
            "agentsmd": None,
            "cli": True,
            "force": False,
            "dry_run": False,
        },
    )()
    assert install.uninstall(install_args) == 1


def test_a_refusing_mode_blocks_the_other_selected_modes(tmp_path):
    # Request-wide preflight: an admissible --cli must not be removed
    # when the co-selected --codex leg refuses.
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    dest, _ = install_cli_once(tmp_path)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8"
    )
    r = run_install(["--uninstall", "--codex", "--cli"], env)
    assert r.returncode == 1
    assert dest.exists()
    assert entry_file(tmp_path, "cli").exists()


def test_plan_cli_never_hands_the_destination_to_pyz_state(tmp_path, monkeypatch):
    # Red-capable: pyz_state asserts it never receives the live destination.
    # So restoring the old pyz_state(dest) comparison in _plan_cli's exact-current branch turns this test red, while the fresh temporary build (and guarded_pyz_state's private copy) still pass through freely.
    # load_install_module is Task 1's helper in this same file.
    install = load_install_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert install.install_cli(dry=False, force=False) == 0
    dest = (tmp_path / "home" / ".local" / "bin" / "semlf").resolve()
    real_pyz_state = install.pyz_state

    def guarded(path):
        assert Path(path).resolve() != dest, "pyz_state received the live destination"
        return real_pyz_state(path)

    monkeypatch.setattr(install, "pyz_state", guarded)
    actions, refusals = [], []
    install._plan_cli(actions, refusals, force=False)
    assert refusals == []
    assert actions  # the exact-current branch admitted via the snapshot


def test_uninstall_dry_run_mutates_nothing_at_all(tmp_path):
    # The dry-run boundary covers the manifest too: a dry-run that forgot provenance would break the artifact's next managed upgrade.
    dest, env = install_cli_once(tmp_path)
    state_before = entry_file(tmp_path, "cli").read_bytes()
    r = run_install(["--uninstall", "--cli", "--dry-run"], env)
    assert r.returncode == 0
    assert "would remove" in r.stdout
    assert dest.exists()
    assert entry_file(tmp_path, "cli").read_bytes() == state_before


# --- Uninstall fix-report follow-ups --------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "an", "object"],
        {"hooks": "not-a-dict"},
        {"hooks": {"PostToolUse": "not-a-list"}},
    ],
)
def test_uninstall_codex_refuses_a_malformed_hooks_shape(tmp_path, payload):
    # Parity with install_codex's own guard: a hooks.json that parses as JSON but has a shape too strange to locate PostToolUse in is a refusal, never silently nothing-to-do.
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert path.read_bytes() == original


def test_uninstall_codex_treats_an_absent_posttooluse_list_as_a_noop(tmp_path):
    # A "hooks" or "PostToolUse" key that is simply absent from an otherwise-sane dict is empty, not strange, and must stay a no-op.
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    original = path.read_bytes()
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 0
    assert path.read_bytes() == original


def test_uninstall_codex_preserves_a_pre_existing_empty_foreign_block(tmp_path):
    # A foreign block that was already empty before we ever looked at it must never be treated as something our own filtering emptied.
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"hooks": {"PostToolUse": [{"matcher": "shell", "hooks": []}]}}),
        encoding="utf-8",
    )
    original = path.read_bytes()
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 0
    assert path.read_bytes() == original


def test_a_non_directory_parent_refuses_uninstall_without_touching_anything(tmp_path):
    # Only FileNotFoundError means "absent";
    # every other OSError from lstat
    # (here NotADirectoryError, because a path component is a plain file standing
    # where a directory belongs)
    # must become a named refusal that touches nothing,
    # not a silent "not installed" no-op (fix-report P1-1).
    env = isolated_env(tmp_path)
    skill_dir = tmp_path / "home" / ".agents" / "skills"
    skill_dir.mkdir(parents=True)
    blocker = skill_dir / "semantic-linefeeds"
    blocker.write_text("not a directory", encoding="utf-8")
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert blocker.is_file()
    assert blocker.read_text(encoding="utf-8") == "not a directory"


def test_forget_failure_after_a_successful_unlink_is_reported_accurately(tmp_path):
    # os.unlink(dest) and manifest.forget(name) are two separate filesystem operations bundled into one planned action.
    # A forget failure after a successful unlink must not misreport dest as never having been removed.
    dest, env = install_cli_once(tmp_path)
    state = entry_file(tmp_path, "cli")
    state.unlink()
    state.mkdir()
    (state / "keep").write_text("x", encoding="utf-8")
    r = run_install(["--uninstall", "--cli"], env)
    assert r.returncode == 1
    assert not dest.exists()
    # Pin that forget actually failed (not silently succeeded): the directory planted in its place must still be there.
    assert (state / "keep").exists()
    assert str(dest) in r.stderr
    assert "provenance" in r.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_force_overrides_an_unreadable_skill_file(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.chmod(0o000)
    r = run_install(["--uninstall", "--codex"], env)
    assert r.returncode == 1
    assert skill.exists()
    r = run_install(["--uninstall", "--codex", "--force"], env)
    assert r.returncode == 0
    assert not skill.exists()


def test_auto_detects_codex_by_binary_on_path(tmp_path):
    r = run_install(["--auto", "--dry-run"], auto_env(tmp_path, "codex"))
    assert r.returncode == 0
    assert "codex" in r.stdout
    assert "PATH" in r.stdout
    assert "opencode: not detected" in r.stdout


def test_auto_detects_opencode_by_config_dir(tmp_path):
    env = auto_env(tmp_path)
    (tmp_path / "xdg" / "opencode").mkdir(parents=True)
    r = run_install(["--auto", "--dry-run"], env)
    assert r.returncode == 0
    assert "opencode" in r.stdout
    assert "codex: not detected" in r.stdout


def test_auto_always_installs_the_cli(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--auto"], env)
    assert r.returncode == 0
    assert (tmp_path / "home" / ".local" / "bin" / "semlf").exists()


def test_auto_rejects_explicit_mode_flags(tmp_path):
    r = run_install(["--auto", "--codex"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_auto_rejects_uninstall(tmp_path):
    r = run_install(["--auto", "--uninstall"], isolated_env(tmp_path))
    assert r.returncode == 64


def setup_artifacts(tmp_path):
    """Codex's setup skill, opencode's setup skill, opencode's setup command."""
    return (
        tmp_path / "home" / ".agents" / "skills" / "setup-semlf" / "SKILL.md",
        tmp_path / "xdg" / "opencode" / "skills" / "setup-semlf" / "SKILL.md",
        tmp_path / "xdg" / "opencode" / "commands" / "setup-semlf.md",
    )


def test_checkout_door_installs_the_setup_artifacts(tmp_path):
    """The curl rung runs this script, so it must write what the package door writes.

    The setup skill tells an agent to fall back to `install.sh ... --auto`,
    which execs this installer:
    a door that skipped these rows would leave the very skill that recommended it uninstalled.
    """
    codex_skill, opencode_skill, opencode_command = setup_artifacts(tmp_path)
    assert run_install(["--codex"], isolated_env(tmp_path)).returncode == 0
    assert codex_skill.exists()
    assert run_install(["--opencode"], isolated_env(tmp_path)).returncode == 0
    assert opencode_skill.exists()
    assert opencode_command.exists()


def test_checkout_door_uninstall_removes_the_setup_artifacts(tmp_path):
    """Both doors plan removals from one list, so neither can orphan a file.

    This installer once kept its own copy of that list.
    Adding a row updated the package door and silently left this one removing the older set,
    which orphaned an artifact that `uninstall` reported as gone.
    """
    codex_skill, opencode_skill, opencode_command = setup_artifacts(tmp_path)
    env = isolated_env(tmp_path)
    run_install(["--codex", "--opencode"], env)
    assert codex_skill.exists() and opencode_skill.exists()

    assert run_install(["--codex", "--opencode", "--uninstall"], env).returncode == 0
    assert not codex_skill.exists()
    assert not opencode_skill.exists()
    assert not opencode_command.exists()
