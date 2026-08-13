"""tests/test_config.py — project config discovery (.semlf.ini)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_linefeeds


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_config_found_in_start_dir(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 100\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"long_limit": 100}


def test_config_found_by_walking_up(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 90\n")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert check_linefeeds.load_config(str(sub)) == {"long_limit": 90}


def test_nonexistent_start_dir_returns_empty_without_walking(tmp_path):
    """A start dir that does not exist must not ascend into real directories.

    The parent here holds both a config and a .git boundary,
    so a walk that ascended would find the config and return 80 —
    the assertion is mutation-sensitive against removing the existence guard.
    """
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\n")
    (tmp_path / ".git").mkdir()
    ghost = tmp_path / "does-not-exist"
    assert check_linefeeds.load_config(str(ghost)) == {}


def test_walk_stops_at_git_dir_boundary(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 90\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    inner = repo / "src"
    inner.mkdir()
    assert check_linefeeds.load_config(str(inner)) == {}


def test_walk_stops_at_git_file_boundary(tmp_path):
    """Worktrees mark the boundary with a .git file, not a directory."""
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 90\n")
    wt = tmp_path / "worktree"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    inner = wt / "src"
    inner.mkdir()
    assert check_linefeeds.load_config(str(inner)) == {}


def test_config_beside_git_boundary_applies(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write(repo / ".semlf.ini", "[semlf]\nlong-limit = 80\n")
    docs = repo / "docs"
    docs.mkdir()
    assert check_linefeeds.load_config(str(docs)) == {"long_limit": 80}


def test_symlinked_start_dir_resolves_to_the_real_repo(tmp_path):
    repo = tmp_path / "real"
    (repo / ".git").mkdir(parents=True)
    write(repo / ".semlf.ini", "[semlf]\nlong-limit = 70\n")
    link = tmp_path / "link"
    link.symlink_to(repo)
    assert check_linefeeds.load_config(str(link)) == {"long_limit": 70}


def test_filesystem_root_terminates_the_walk(tmp_path, monkeypatch):
    # The host filesystem above tmp_path is not under the test's control
    # (TMPDIR can sit under a configured checkout),
    # so both probes are pinned to "absent" and only termination is proven:
    # the walk must reach the filesystem root and stop, not loop.
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    monkeypatch.setattr(check_linefeeds.os.path, "isfile", lambda p: False)
    monkeypatch.setattr(check_linefeeds.os.path, "exists", lambda p: False)
    assert check_linefeeds.load_config(str(deep)) == {}


def test_malformed_file_is_ignored(tmp_path):
    write(tmp_path / ".semlf.ini", "not an ini file [[[")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_duplicate_sections_are_ignored(tmp_path):
    write(tmp_path / ".semlf.ini",
          "[semlf]\nlong-limit = 100\n[semlf]\nlong-limit = 90\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_undecodable_bytes_are_ignored(tmp_path):
    (tmp_path / ".semlf.ini").write_bytes(b"[semlf]\nlong-limit = \xff\xfe1\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_unreadable_file_is_ignored(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 100\n")
    real_open = open

    def failing_open(path, *a, **k):
        if str(path).endswith(".semlf.ini"):
            raise OSError("injected")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", failing_open)
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_bad_value_is_ignored(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = many\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_negative_value_is_ignored(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = -5\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_missing_section_is_ignored(tmp_path):
    write(tmp_path / ".semlf.ini", "[other]\nlong-limit = 100\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_default_section_key_does_not_leak_into_semlf(tmp_path):
    write(tmp_path / ".semlf.ini", "[DEFAULT]\nlong-limit = 40\n[semlf]\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_default_section_alone_is_ignored(tmp_path):
    write(tmp_path / ".semlf.ini", "[DEFAULT]\nlong-limit = 40\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_no_representable_section_name_can_act_as_defaults_source(tmp_path):
    """No section name, however exotic, can smuggle a key through defaults inheritance.

    The prior fix renamed the default section to a NUL-prefixed sentinel,
    but that name is still representable in a config file,
    since UTF-8 decodes an embedded NUL.
    A section literally spelled with that sentinel name must still fail to supply long-limit through inheritance into an empty [semlf].
    """
    write(tmp_path / ".semlf.ini", "[\x00disabled]\nlong-limit = 40\n[semlf]\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_semlf_key_still_works_beside_default_section(tmp_path):
    write(tmp_path / ".semlf.ini",
          "[DEFAULT]\nlong-limit = 40\n[semlf]\nlong-limit = 90\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"long_limit": 90}


def test_zero_disables_advisory(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 0\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"long_limit": 0}


def test_flag_beats_env_and_config(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\n")
    monkeypatch.setenv("SEMLF_LONG_LINE", "90")
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", 70)
    assert check_linefeeds.active_long_limit(str(tmp_path / "x.md")) == 70


def test_env_beats_config(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\n")
    monkeypatch.setenv("SEMLF_LONG_LINE", "90")
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    assert check_linefeeds.active_long_limit(str(tmp_path / "x.md")) == 90


def test_config_beats_default(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\n")
    monkeypatch.delenv("SEMLF_LONG_LINE", raising=False)
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    assert check_linefeeds.active_long_limit(str(tmp_path / "x.md")) == 80


def test_no_path_keeps_old_behavior(monkeypatch):
    monkeypatch.delenv("SEMLF_LONG_LINE", raising=False)
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    assert check_linefeeds.active_long_limit() == check_linefeeds.DEFAULT_LONG_LINE


# A line the long predicate can actually fire on:
# over 40 characters AND carrying a boundary hint
# (BOUNDARY_HINT_RE requires strong punctuation or a comma-led conjunction —
# sheer length is deliberately not enough, per the core's precision design).
LONG_WITH_BOUNDARY = (
    "The exporter batches metrics in memory, "
    "and it retries failed uploads until the queue drains."
)


def test_config_reaches_diagnose(tmp_path, monkeypatch):
    """End to end: a config file lowers the advisory threshold for diagnose()."""
    monkeypatch.delenv("SEMLF_LONG_LINE", raising=False)
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    target = tmp_path / "doc.md"
    write(target, LONG_WITH_BOUNDARY + "\n")
    kinds = [d["kind"] for d in
             check_linefeeds.diagnose(target.read_text(encoding="utf-8"), str(target))]
    assert kinds == ["long"]


def test_direct_diagnose_sees_config_changes_without_any_reset(tmp_path, monkeypatch):
    """Freshness is the contract: direct callers never manage hidden state.

    diagnose() is called straight from tests and adapters,
    so creating, changing, or removing .semlf.ini between two calls
    must take effect with no reset hook in between.
    """
    monkeypatch.delenv("SEMLF_LONG_LINE", raising=False)
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    target = tmp_path / "doc.md"
    write(target, LONG_WITH_BOUNDARY + "\n")
    text = target.read_text(encoding="utf-8")

    def kinds():
        return [d["kind"] for d in check_linefeeds.diagnose(text, str(target))]

    assert kinds() == []
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    assert kinds() == ["long"]
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 200\n")
    assert kinds() == []
    (tmp_path / ".semlf.ini").unlink()
    assert kinds() == []


import json
import re
import subprocess

from conftest import SCRIPT


def run_hook(payload, cwd, agent="claude"):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--hook", agent],
        input=json.dumps(payload), capture_output=True, text=True, cwd=str(cwd),
    )


def kinds_in(text):
    return set(re.findall(r"\[(fused|wrap|long)\]", text))


# Fused (". A second"), over 40 chars, and boundary-hinted (", and"):
# a wrongly applied low threshold would add "long" and change the kind set.
FUSED_LINE = ("// The exporter batches metrics in memory, "
              "and it retries uploads. A second sentence follows.")


def claude_payload(name, text):
    return {"tool_name": "Edit",
            "tool_input": {"file_path": name, "new_string": text}}


def codex_payload(name, text):
    # Mirrors tests/payloads/codex_apply_patch_bad.json's schema.
    patch = ("*** Begin Patch\n*** Update File: " + name + "\n@@\n+" + text +
             "\n*** End Patch")
    return {"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t",
            "cwd": ".", "hook_event_name": "PostToolUse", "model": "m",
            "permission_mode": "default", "tool_name": "apply_patch",
            "tool_input": {"command": patch},
            "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}


HOSTILE_CONFIGS = [
    "not an ini file [[[",
    "[semlf]\nlong-limit = many\n",
    "[semlf]\nlong-limit = 99999999999999999999\n",
    "[semlf]\nlong-limit = -1\n",
    "[semlf]\nlong-limit = 100\n[semlf]\nlong-limit = 40\n",
    "[DEFAULT]\nlong-limit = 40\n[semlf]\n",
    "[\x00disabled]\nlong-limit = 40\n[semlf]\n",
]


def hostile_variants(tmp_path):
    for hostile in HOSTILE_CONFIGS:
        (tmp_path / ".semlf.ini").write_text(hostile, encoding="utf-8")
        yield
    (tmp_path / ".semlf.ini").write_bytes(b"[semlf]\nlong-limit = \xff\xfe1\n")
    yield
    cfg = tmp_path / ".semlf.ini"
    cfg.write_text("[semlf]\nlong-limit = 40\n", encoding="utf-8")
    cfg.chmod(0)  # unreadable; meaningless when running as root, like every permission test
    try:
        yield
    finally:
        cfg.chmod(0o644)


def test_hostile_configs_never_change_claude_hook_kinds(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "doc.go").write_text(FUSED_LINE + "\n", encoding="utf-8")
    payload = claude_payload("doc.go", FUSED_LINE)
    baseline = run_hook(payload, tmp_path)
    assert baseline.returncode == 2
    assert kinds_in(baseline.stderr) == {"fused"}
    for _ in hostile_variants(tmp_path):
        r = run_hook(payload, tmp_path)
        assert r.returncode == 2
        assert kinds_in(r.stderr) == {"fused"}


def test_hostile_configs_never_change_codex_hook_kinds(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "doc.go").write_text(FUSED_LINE + "\n", encoding="utf-8")
    payload = codex_payload("doc.go", FUSED_LINE)
    baseline = run_hook(payload, tmp_path, agent="codex")
    assert baseline.returncode == 2
    assert kinds_in(baseline.stderr) == {"fused"}
    for _ in hostile_variants(tmp_path):
        r = run_hook(payload, tmp_path, agent="codex")
        assert r.returncode == 2
        assert kinds_in(r.stderr) == {"fused"}


def test_injected_config_read_error_is_inert_in_both_hooks(tmp_path, monkeypatch, capsys):
    """A config the OS refuses to read must not change hook behavior.

    chmod tricks are meaningless under root,
    so the OSError is injected directly and the hooks are driven in-process —
    this is the deterministic version of the unreadable-config case.
    The injection is scoped to the config filename;
    the hooks' own snapshot reads keep working.
    """
    import io
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "doc.go").write_text(FUSED_LINE + "\n", encoding="utf-8")
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    real_open = open

    def failing_open(path, *a, **k):
        if str(path).endswith(".semlf.ini"):
            raise OSError("injected")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", failing_open)
    for payload, entry in (
        (claude_payload("doc.go", FUSED_LINE), check_linefeeds.run_hook_claude),
        (codex_payload("doc.go", FUSED_LINE), check_linefeeds.run_hook_codex),
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        rc = entry()
        captured = capsys.readouterr()
        assert rc == 2
        assert kinds_in(captured.err) == {"fused"}


def test_valid_config_moves_only_the_long_threshold(tmp_path):
    (tmp_path / ".git").mkdir()
    line = ("The exporter batches metrics in memory, "
            "and it retries failed uploads until the queue drains.")
    (tmp_path / "doc.md").write_text(line + "\n", encoding="utf-8")
    for agent, payload in (("claude", claude_payload("doc.md", line)),
                           ("codex", codex_payload("doc.md", line))):
        (tmp_path / ".semlf.ini").unlink(missing_ok=True)
        without = run_hook(payload, tmp_path, agent=agent)
        (tmp_path / ".semlf.ini").write_text("[semlf]\nlong-limit = 40\n",
                                             encoding="utf-8")
        with_cfg = run_hook(payload, tmp_path, agent=agent)
        assert without.returncode == 0 and with_cfg.returncode == 0
        assert kinds_in(without.stdout) == set()
        assert kinds_in(with_cfg.stdout) == {"long"}
