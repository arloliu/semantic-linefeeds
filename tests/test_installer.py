import json
import os
import shutil
import subprocess
import sys

from conftest import REPO, SCRIPT
from check_linefeeds import AGENT_SUPPRESSION_NOTE

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
    check = subprocess.run([str(dest), "--file", str(bad)],
                           capture_output=True, text=True)
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
    shutil.copytree(REPO / "skills", src / "skills")
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


def test_install_sh_clone_installs_the_native_skill(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"],
                       isolated_env(tmp_path))
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
    assert "already" in r.stdout.lower()


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
    }
    r = subprocess.run(
        ["sh", str(INSTALL_SH), "--repo", str(src), "--home", str(home), "--codex"],
        capture_output=True, text=True, env=env,
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
    }
    r = subprocess.run(
        ["sh", str(INSTALL_SH), "--repo", str(src), "--home", str(home)],
        capture_output=True, text=True, env=env,
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


def test_install_sh_self_checkout_honors_ref(tmp_path):
    # A self-checkout run (install.sh executed from inside its own checkout, no --repo)
    # must still honor an explicit --ref,
    # instead of silently installing whatever HEAD happens to be checked out.
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    shutil.copytree(REPO / "skills", src / "skills")
    shutil.copy(INSTALL_SH, src / "install.sh")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    subprocess.run(git + ["tag", "v1"], check=True)

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
        ["sh", str(src / "install.sh"),
         "--ref", "v1", "--home", str(elsewhere), "--codex"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr
    installed = (elsewhere / "scripts" / "check_linefeeds.py").read_text(
        encoding="utf-8")
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
    assert f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>' in text
    assert "CLAUDE_PLUGIN_ROOT" not in text


def test_codex_skill_rerun_is_a_noop(tmp_path):
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    before = codex_skill_path(tmp_path).read_text(encoding="utf-8")
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    assert "codex skill: already installed" in r.stdout
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
    assert (f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>'
            in skill.read_text(encoding="utf-8"))
    backup = skill.with_name(skill.name + ".bak")
    assert backup.read_text(encoding="utf-8") == "# hand-patched\n"


def test_codex_skill_dry_run_writes_nothing(tmp_path):
    r = run_install(["--codex", "--dry-run"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert not codex_skill_path(tmp_path).exists()


def test_status_reports_codex_skill_states(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: not installed" in r.stdout
    run_install(["--codex"], env)
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: installed" in r.stdout
    codex_skill_path(tmp_path).write_text("# hand-patched\n", encoding="utf-8")
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: diverged" in r.stdout
    codex_skill_path(tmp_path).write_bytes(b"\xff\xfe\x00")
    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: unreadable" in r.stdout


def test_status_and_rerun_detect_a_crlf_converted_skill(tmp_path):
    # Python's text-mode read universally translates "\r\n" back to "\n".
    # A same-content-but-CRLF copy would therefore compare equal under a read_text() comparison, hiding from both status and a rerun --
    # exactly the gap the hook probe's own byte-level read does not have.
    env = isolated_env(tmp_path)
    run_install(["--codex"], env)
    skill = codex_skill_path(tmp_path)
    skill.write_bytes(skill.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))

    r = run_install([], env, cwd=tmp_path)
    assert "codex skill: diverged" in r.stdout

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


def test_codex_skill_dest_is_none_when_home_is_unresolvable(monkeypatch):
    # os.path.expanduser("~") returns its input unchanged when it cannot resolve a home directory;
    # Path.home() raises instead.
    # A real account with no resolvable home is not something a test can set up hermetically,
    # so the failure is simulated by monkeypatching the same expansion the core's own probe (_judgment_layer_present) already treats this way.
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    assert install_module.codex_skill_dest() is None


def test_install_codex_skill_refuses_without_a_resolvable_home(monkeypatch, capsys):
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.install_codex_skill(False, False)
    assert rc == 1
    assert "home" in capsys.readouterr().err.lower()


def test_status_reports_no_home_to_check(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Bypass the two other Path.home() call sites (codex_home, opencode_plugins_dir)
    # so only the skill-destination guard is exercised.
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    install_module.status()
    assert "codex skill: no home to check" in capsys.readouterr().out


def test_status_reports_no_home_on_every_path_without_env_overrides(monkeypatch, capsys):
    # No CODEX_HOME/XDG_CONFIG_HOME override here, unlike the test above --
    # this reaches codex_home()'s and opencode_plugins_dir()'s own guards,
    # not just codex_skill_dest()'s, and must not crash on the way.
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.status()
    out = capsys.readouterr().out
    assert rc == 0
    assert "codex: no home to check" in out
    assert "opencode: no home to check" in out
    assert "codex skill: no home to check" in out
    assert "cli: no home to check" in out


def test_install_codex_refuses_without_a_resolvable_home(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.install_codex(False)
    assert rc == 1
    assert "home" in capsys.readouterr().err.lower()
    assert list(tmp_path.iterdir()) == []


def test_install_opencode_refuses_without_a_resolvable_home(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(install_module.os.path, "expanduser", lambda p: p)
    rc = install_module.install_opencode(False, False)
    assert rc == 1
    assert "home" in capsys.readouterr().err.lower()
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
    text = ("This clause runs on and on well past the configured advisory "
            "threshold of one hundred and twenty characters, and the tail "
            "keeps going.\n")
    added = "".join("+" + line + "\n" for line in text.splitlines())
    patch = ("*** Begin Patch\n*** Update File: doc.md\n@@\n"
              + added + "*** End Patch")
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    })
    hook_env = os.environ.copy()
    hook_env["HOME"] = env["HOME"]
    hook = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook", "codex"],
        input=payload, capture_output=True, text=True,
        env=hook_env, cwd=str(elsewhere),
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
    r = subprocess.run([str(pyz), "--file", str(bad)],
                       capture_output=True, text=True, cwd=str(tmp_path))
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
    retimed.write_bytes(b"#!" + install_module.PYZ_INTERPRETER.encode() + b"\n" + content)
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


def test_install_cli_places_semlf_on_local_bin(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = install_module.install_cli(False, False)
    out = capsys.readouterr().out
    dest = tmp_path / ".local" / "bin" / "semlf"
    assert rc == 0 and dest.exists() and os.access(dest, os.X_OK)
    assert "installed" in out


def test_install_cli_is_idempotent_and_still_notes_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
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


def test_install_cli_refuses_divergent_file_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.parent.mkdir(parents=True)
    dest.write_text("something else", encoding="utf-8")
    assert install_module.install_cli(False, False) == 1
    assert "refusing" in capsys.readouterr().err


def test_install_cli_force_backs_up_the_old_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.parent.mkdir(parents=True)
    dest.write_text("something else", encoding="utf-8")
    assert install_module.install_cli(False, True) == 0
    backup = dest.with_name("semlf.bak")
    assert backup.read_text(encoding="utf-8") == "something else"
    assert os.access(dest, os.X_OK)


def test_install_cli_refuses_a_directory_destination(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    dest = tmp_path / ".local" / "bin" / "semlf"
    dest.mkdir(parents=True)
    assert install_module.install_cli(False, True) == 1
    assert "refusing" in capsys.readouterr().err
    assert dest.is_dir()


def test_install_cli_refuses_symlink_destinations_even_with_force(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
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
