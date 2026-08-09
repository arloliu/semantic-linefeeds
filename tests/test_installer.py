import json
import os
import shutil
import subprocess
import sys

from conftest import REPO

INSTALL = REPO / "scripts" / "install.py"


def run_install(args, env_overrides, cwd=None):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(INSTALL)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def isolated_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "HOME": str(home),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }


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


def test_codex_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    before = codex_hooks_path(tmp_path).read_text(encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert "already" in r.stdout.lower()
    assert codex_hooks_path(tmp_path).read_text(encoding="utf-8") == before


def test_codex_merge_preserves_existing_entries(tmp_path):
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    existing = {"hooks": {"PostToolUse": [
        {"matcher": "shell", "hooks": [{"type": "command", "command": "echo hi"}]}
    ]}, "unrelated": {"keep": True}}
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
    stale = {"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": "python3 \"/old/clone/scripts/check_linefeeds.py\" --hook codex"}
        ]}
    ]}}
    path.write_text(json.dumps(stale), encoding="utf-8")
    r = run_install(["--codex"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "updat" in r.stdout.lower()
    entries = read_hooks(tmp_path)["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert "/old/clone/" not in entries[0]["hooks"][0]["command"]
    assert str(REPO) in entries[0]["hooks"][0]["command"]


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
    assert run_install(["--help"], isolated_env(tmp_path)).returncode == 0


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
    assert "already" in r.stdout.lower()


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
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert SENTINEL_OPEN in text and SENTINEL_CLOSE in text
    assert "Semantic linefeeds" in text
    assert str(REPO) in text  # the <repo> placeholder is substituted


def test_agentsmd_rerun_is_idempotent(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--agentsmd"], env, cwd=tmp_path)
    before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    r = run_install(["--agentsmd"], env, cwd=tmp_path)
    assert r.returncode == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == before


def test_agentsmd_replaces_block_and_keeps_user_text(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# My rules\n\nkeep me\n\n"
        f"{SENTINEL_OPEN}\nstale old block\n{SENTINEL_CLOSE}\n\ntail kept too\n",
        encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "keep me" in text and "tail kept too" in text
    assert "stale old block" not in text
    assert "Semantic linefeeds" in text


def test_agentsmd_appends_to_existing_file_without_block(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# My rules\n", encoding="utf-8")
    run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# My rules\n")
    assert SENTINEL_OPEN in text


def test_agentsmd_unbalanced_sentinels_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(f"{SENTINEL_OPEN}\nno close marker\n", encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == f"{SENTINEL_OPEN}\nno close marker\n"


def test_agentsmd_close_before_open_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    original = f"stray text\n{SENTINEL_CLOSE}\nmore text\n{SENTINEL_OPEN}\ntail\n"
    target.write_text(original, encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == original


def test_agentsmd_two_blocks_refused(tmp_path):
    target = tmp_path / "AGENTS.md"
    original = (
        f"{SENTINEL_OPEN}\nfirst block\n{SENTINEL_CLOSE}\n\n"
        f"{SENTINEL_OPEN}\nsecond block\n{SENTINEL_CLOSE}\n"
    )
    target.write_text(original, encoding="utf-8")
    r = run_install(["--agentsmd"], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 1
    assert target.read_text(encoding="utf-8") == original


def test_status_handles_undecodable_hooks_json(tmp_path):
    env = isolated_env(tmp_path)
    path = codex_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe{")
    r = run_install([], env, cwd=tmp_path)
    assert r.returncode == 0
    assert "unreadable" in r.stdout.lower()
    assert r.stderr == ""


def test_status_handles_undecodable_agentsmd(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_bytes(b"\xff\xfe{")
    r = run_install([], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == ""


def test_agentsmd_explicit_path(tmp_path):
    other = tmp_path / "docs-agents.md"
    r = run_install(["--agentsmd", str(other)], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    assert SENTINEL_OPEN in other.read_text(encoding="utf-8")


def test_status_reports_all_targets_and_claude_guidance(tmp_path):
    r = run_install([], isolated_env(tmp_path), cwd=tmp_path)
    assert r.returncode == 0
    out = r.stdout
    assert "codex: not installed" in out
    assert "opencode: not installed" in out
    assert "agentsmd" in out and "absent" in out
    assert "claude plugin" in out


def test_status_sees_installed_targets(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex", "--opencode", "--agentsmd"], env, cwd=tmp_path)
    out = run_install([], env, cwd=tmp_path).stdout
    assert "codex: installed" in out
    assert "opencode: installed" in out
    assert "present" in out


INSTALL_SH = REPO / "install.sh"


def make_source_repo(tmp_path):
    """A minimal git repo carrying just what install.py needs."""
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    return src


def run_install_sh(args, env_overrides, cwd=None):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        ["sh", str(INSTALL_SH)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def test_install_sh_clones_and_installs_codex(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"],
                       isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (home / "scripts" / "install.py").exists()
    assert codex_hooks_path(tmp_path).exists()


def test_install_sh_rerun_pulls_and_is_idempotent(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    assert r.returncode == 0, r.stderr
    assert "already" in r.stdout.lower()


def test_install_sh_env_repo_and_dry_run(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    env["SEMBR_REPO"] = str(src)
    env["SEMBR_HOME"] = str(home)
    r = run_install_sh(["--codex", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert not codex_hooks_path(tmp_path).exists()
    assert "dry-run" in r.stdout.lower()


def test_install_sh_uses_own_checkout_without_repo(tmp_path):
    never = tmp_path / "never-created"
    env = isolated_env(tmp_path)
    env["SEMBR_HOME"] = str(never)
    r = run_install_sh([], env)
    assert r.returncode == 0, r.stderr
    assert "codex:" in r.stdout
    assert not never.exists()


def test_install_sh_quotes_apostrophe_in_pass_through_arg(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    target_dir = tmp_path / "O'Brien"
    target_dir.mkdir()
    target = target_dir / "AGENTS.md"
    r = run_install_sh(["--repo", str(src), "--home", str(home),
                        "--agentsmd", str(target)],
                       isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert target.exists()


def test_install_sh_home_flag_without_home_env(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "CODEX_HOME": str(tmp_path / "codex"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }
    r = subprocess.run(
        ["sh", str(INSTALL_SH), "--repo", str(src), "--home", str(home), "--codex"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr


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


def test_install_sh_self_checkout_honors_ref(tmp_path):
    # A self-checkout run (install.sh executed from inside its own checkout, no --repo)
    # must still honor an explicit --ref,
    # instead of silently installing whatever HEAD happens to be checked out.
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    shutil.copy(INSTALL_SH, src / "install.sh")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    subprocess.run(git + ["tag", "v1"], check=True)

    marker = src / "scripts" / "check_linefeeds.py"
    with marker.open("a", encoding="utf-8") as f:
        f.write("\n# MARKER_AFTER_V1\n")
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "second commit"], check=True)

    elsewhere = tmp_path / "elsewhere"
    env = isolated_env(tmp_path)
    r = subprocess.run(
        ["sh", str(src / "install.sh"),
         "--ref", "v1", "--home", str(elsewhere), "--codex"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr
    installed = (elsewhere / "scripts" / "check_linefeeds.py").read_text(
        encoding="utf-8")
    assert "MARKER_AFTER_V1" not in installed
