"""tests/test_config.py — project config discovery (.semlf.ini)."""

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
    write(
        tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 100\n[semlf]\nlong-limit = 90\n"
    )
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
    write(
        tmp_path / ".semlf.ini",
        "[DEFAULT]\nlong-limit = 40\n[semlf]\nlong-limit = 90\n",
    )
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
    kinds = [
        d["kind"]
        for d in check_linefeeds.diagnose(
            target.read_text(encoding="utf-8"), str(target)
        )
    ]
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
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def kinds_in(text):
    return set(re.findall(r"\[(fused|wrap|long)\]", text))


# Fused (". A second"), over 40 chars, and boundary-hinted (", and"):
# a wrongly applied low threshold would add "long" and change the kind set.
FUSED_LINE = (
    "// The exporter batches metrics in memory, "
    "and it retries uploads. A second sentence follows."
)


def claude_payload(name, text):
    return {"tool_name": "Edit", "tool_input": {"file_path": name, "new_string": text}}


def codex_payload(name, text):
    # Mirrors tests/payloads/codex_apply_patch_bad.json's schema.
    patch = (
        "*** Begin Patch\n*** Update File: "
        + name
        + "\n@@\n+"
        + text
        + "\n*** End Patch"
    )
    return {
        "session_id": "s1",
        "turn_id": "t1",
        "transcript_path": "/tmp/t",
        "cwd": ".",
        "hook_event_name": "PostToolUse",
        "model": "m",
        "permission_mode": "default",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "tool_response": {"output": "Done"},
        "tool_use_id": "call_1",
    }


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
    cfg.chmod(
        0
    )  # unreadable; meaningless when running as root, like every permission test
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


def test_injected_config_read_error_is_inert_in_both_hooks(
    tmp_path, monkeypatch, capsys
):
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
    line = (
        "The exporter batches metrics in memory, "
        "and it retries failed uploads until the queue drains."
    )
    (tmp_path / "doc.md").write_text(line + "\n", encoding="utf-8")
    for agent, payload in (
        ("claude", claude_payload("doc.md", line)),
        ("codex", codex_payload("doc.md", line)),
    ):
        (tmp_path / ".semlf.ini").unlink(missing_ok=True)
        without = run_hook(payload, tmp_path, agent=agent)
        (tmp_path / ".semlf.ini").write_text(
            "[semlf]\nlong-limit = 40\n", encoding="utf-8"
        )
        with_cfg = run_hook(payload, tmp_path, agent=agent)
        assert without.returncode == 0 and with_cfg.returncode == 0
        assert kinds_in(without.stdout) == set()
        assert kinds_in(with_cfg.stdout) == {"long"}


def test_exclude_patterns_are_parsed_multiline(tmp_path):
    write(
        tmp_path / ".semlf.ini",
        "[semlf]\nexclude =\n    vendor/\n    docs/generated/\n    *.gen.md\n",
    )
    assert check_linefeeds.load_config(str(tmp_path)) == {
        "exclude": ["vendor/", "docs/generated/", "*.gen.md"]
    }


def test_exclude_single_line_value_is_one_pattern(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude = vendor/\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"exclude": ["vendor/"]}


def test_exclude_blank_lines_and_leading_slash_are_normalized(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude =\n\n    /docs/generated/\n\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {
        "exclude": ["docs/generated/"]
    }


def test_exclude_backslashes_normalize_to_slashes(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude = docs\\generated\\\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {
        "exclude": ["docs/generated/"]
    }


def test_exclude_empty_value_yields_no_key(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude =\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_bad_long_limit_no_longer_drops_a_good_exclude(tmp_path):
    """Fail-open is per key: one bad value silences itself, not its neighbors."""
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = many\nexclude = vendor/\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"exclude": ["vendor/"]}


def test_both_keys_parse_together(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\nexclude = vendor/\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {
        "long_limit": 80,
        "exclude": ["vendor/"],
    }


def test_exclude_match_folder_name_at_any_depth():
    assert check_linefeeds._exclude_match("vendor/doc.md", ["vendor/"])
    assert check_linefeeds._exclude_match("a/vendor/doc.md", ["vendor/"])
    assert not check_linefeeds._exclude_match("doc.md", ["vendor/"])
    # The trailing slash names folders: a *file* named vendor is not one.
    assert not check_linefeeds._exclude_match("vendor", ["vendor/"])


def test_exclude_match_anchored_folder_chain():
    patterns = ["docs/generated/"]
    assert check_linefeeds._exclude_match("docs/generated/api.md", patterns)
    assert check_linefeeds._exclude_match("docs/generated/deep/x.md", patterns)
    assert not check_linefeeds._exclude_match("other/docs/generated/x.md", patterns)
    assert not check_linefeeds._exclude_match("docs/handwritten/x.md", patterns)
    # A folder pattern names what lives under the folder,
    # never a plain file whose own path spells the chain.
    assert not check_linefeeds._exclude_match("docs/generated", patterns)


def test_exclude_match_component_glob():
    assert check_linefeeds._exclude_match("notes/api.gen.md", ["*.gen.md"])
    assert check_linefeeds._exclude_match("api.gen.md", ["*.gen.md"])
    assert not check_linefeeds._exclude_match("api.md", ["*.gen.md"])
    # A slash-free bare name may also match a folder component.
    assert check_linefeeds._exclude_match("node_modules/x/doc.md", ["node_modules"])


def test_exclude_match_separators_are_boundaries():
    """The grammar's load-bearing rule: * and ? never cross a slash."""
    assert check_linefeeds._exclude_match("docs/api.md", ["docs/*.md"])
    assert not check_linefeeds._exclude_match("docs/deep/api.md", ["docs/*.md"])
    assert check_linefeeds._exclude_match("docs/deep/api.md", ["docs/*/api.md"])
    assert not check_linefeeds._exclude_match("docs/a/b/api.md", ["docs/*/api.md"])
    assert not check_linefeeds._exclude_match("docs/deep/api.md", ["docs/*"])
    assert not check_linefeeds._exclude_match("x/docs/api.md", ["docs/*.md"])
    assert not check_linefeeds._exclude_match("docs/x", ["docs?x"])


def test_exclude_match_is_case_sensitive_everywhere():
    assert not check_linefeeds._exclude_match("Vendor/doc.md", ["vendor/"])
    assert not check_linefeeds._exclude_match("API.GEN.MD", ["*.gen.md"])


def test_excluded_reads_the_discovered_config(tmp_path):
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude = generated/\n")
    inside = tmp_path / "generated" / "doc.md"
    write(inside, "text\n")
    outside = tmp_path / "docs" / "doc.md"
    write(outside, "text\n")
    assert check_linefeeds.excluded(str(inside))
    assert not check_linefeeds.excluded(str(outside))


def test_excluded_is_false_without_a_config(tmp_path):
    (tmp_path / ".git").mkdir()
    target = tmp_path / "vendor" / "doc.md"
    write(target, "text\n")
    assert not check_linefeeds.excluded(str(target))


def test_excluded_is_false_for_a_path_outside_the_config_root(tmp_path):
    """A config governs its own tree, never a sibling's."""
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    write(project / ".semlf.ini", "[semlf]\nexclude = *.md\n")
    sibling = tmp_path / "sibling" / "doc.md"
    write(sibling, "text\n")
    # Discovery starts at the sibling and never reaches project's config,
    # and even a directly handed config root refuses a path outside it.
    assert not check_linefeeds.excluded(str(sibling))


def test_policy_survives_a_vanished_directory(tmp_path):
    """A ghost path is governed by the nearest existing ancestor's config.

    This is the worktree-policy anchor for staged files whose parent
    directory was removed from the worktree: policy must not lapse
    just because the directory is index-only now.
    """
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude = generated/\n")
    ghost = tmp_path / "generated" / "gone" / "doc.md"  # never created
    assert check_linefeeds.excluded(str(ghost))


def test_long_limit_survives_a_vanished_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_LONG_LINE", raising=False)
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", None)
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    ghost = tmp_path / "nested" / "doc.md"
    assert check_linefeeds.active_long_limit(str(ghost)) == 40


def test_excluded_is_false_for_an_escaping_symlink(tmp_path):
    """The outside-root guard acts on the resolved path, not the spelling.

    The catch-all pattern makes this mutation-sensitive:
    without the ../-guard the component glob would match the resolved
    path's basename and wrongly exclude it.
    """
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    write(project / ".semlf.ini", "[semlf]\nexclude = *\n")
    outside = tmp_path / "outside.md"
    write(outside, "text\n")
    link = project / "doc.md"
    link.symlink_to(outside)
    assert not check_linefeeds.excluded(str(link))


def test_excluded_fails_open_when_relpath_cannot_form(tmp_path, monkeypatch):
    """Windows raises ValueError for a cross-drive relpath; the guard eats it."""
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", "[semlf]\nexclude = *\n")
    target = tmp_path / "doc.md"
    write(target, "text\n")

    def cross_drive(path, start=None):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(check_linefeeds.os.path, "relpath", cross_drive)
    assert not check_linefeeds.excluded(str(target))


def test_excluded_fails_open_on_a_hostile_config(tmp_path):
    (tmp_path / ".git").mkdir()
    target = tmp_path / "vendor" / "doc.md"
    write(target, "text\n")
    (tmp_path / ".semlf.ini").write_bytes(b"[semlf]\nexclude = \xff\xfe\n")
    assert not check_linefeeds.excluded(str(target))
    write(tmp_path / ".semlf.ini", "not an ini [[[")
    assert not check_linefeeds.excluded(str(target))


def test_excluded_resolves_symlinked_paths_to_the_real_tree(tmp_path):
    repo = tmp_path / "real"
    (repo / ".git").mkdir(parents=True)
    write(repo / ".semlf.ini", "[semlf]\nexclude = generated/\n")
    write(repo / "generated" / "doc.md", "text\n")
    link = tmp_path / "link"
    link.symlink_to(repo)
    assert check_linefeeds.excluded(str(link / "generated" / "doc.md"))


EXCLUDING_CONFIG = "[semlf]\nexclude = generated/\n"


def test_excluded_path_silences_the_claude_hook(tmp_path):
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", EXCLUDING_CONFIG)
    write(tmp_path / "generated" / "doc.go", FUSED_LINE + "\n")
    payload = claude_payload("generated/doc.go", FUSED_LINE)
    r = run_hook(payload, tmp_path)
    assert r.returncode == 0
    assert kinds_in(r.stderr) == set()
    # Control: the same payload bites once the config stops excluding it.
    (tmp_path / ".semlf.ini").unlink()
    r = run_hook(payload, tmp_path)
    assert r.returncode == 2
    assert kinds_in(r.stderr) == {"fused"}


def test_excluded_file_never_hides_its_patch_neighbors(tmp_path):
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", EXCLUDING_CONFIG)
    write(tmp_path / "generated" / "a.go", FUSED_LINE + "\n")
    write(tmp_path / "b.go", FUSED_LINE + "\n")
    patch = (
        "*** Begin Patch\n*** Update File: generated/a.go\n@@\n+"
        + FUSED_LINE
        + "\n*** End Patch\n*** Begin Patch\n*** Update File: b.go\n@@\n+"
        + FUSED_LINE
        + "\n*** End Patch"
    )
    payload = codex_payload("b.go", FUSED_LINE)
    payload["tool_input"] = {"command": patch}
    r = run_hook(payload, tmp_path, agent="codex")
    assert r.returncode == 2
    assert "b.go" in r.stderr
    assert "a.go" not in r.stderr


def test_explicit_file_mode_ignores_excludes(tmp_path):
    """Naming a path beats the discovery filter — always."""
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".semlf.ini", EXCLUDING_CONFIG)
    write(
        tmp_path / "generated" / "doc.md",
        "One sentence. Another fused on the same line.\n",
    )
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", "generated/doc.md"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert r.returncode == 1
    assert "fused" in r.stdout


def test_hostile_exclude_configs_never_change_hook_kinds(tmp_path):
    """The v0.6a hostile matrix, re-run with exclude payloads."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "doc.go").write_text(FUSED_LINE + "\n", encoding="utf-8")
    payload = claude_payload("doc.go", FUSED_LINE)
    hostile_excludes = [
        "[semlf]\nexclude = \n",
        "[semlf]\nexclude = doc.go\nexclude = doc.go\n",
        "[semlf]\nexclude = [\n",
        "[DEFAULT]\nexclude = doc.go\n[semlf]\nlong-limit = 120\n",
    ]
    for hostile in hostile_excludes:
        (tmp_path / ".semlf.ini").write_text(hostile, encoding="utf-8")
        r = run_hook(payload, tmp_path)
        assert r.returncode == 2, hostile
        assert kinds_in(r.stderr) == {"fused"}, hostile


# --- experimental-wrap ini key / experimental_wrap cfg dict key:
# env > ini > default(off) (ADR-0017) ---


def test_experimental_wrap_true_parses(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"experimental_wrap": True}


def test_experimental_wrap_false_parses(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = false\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"experimental_wrap": False}


def test_experimental_wrap_accepts_numeric_and_word_spellings(tmp_path):
    for spelling, expected in (
        ("1", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("no", False),
        ("off", False),
    ):
        write(tmp_path / ".semlf.ini", f"[semlf]\nexperimental-wrap = {spelling}\n")
        assert check_linefeeds.load_config(str(tmp_path)) == {
            "experimental_wrap": expected
        }, spelling


def test_experimental_wrap_is_case_insensitive(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = TRUE\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {"experimental_wrap": True}


def test_experimental_wrap_invalid_value_drops_the_key(tmp_path):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = maybe\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_experimental_wrap_combines_with_other_keys(tmp_path):
    write(
        tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\nexperimental-wrap = true\n"
    )
    assert check_linefeeds.load_config(str(tmp_path)) == {
        "long_limit": 80,
        "experimental_wrap": True,
    }


def test_bad_experimental_wrap_does_not_drop_a_good_long_limit(tmp_path):
    write(
        tmp_path / ".semlf.ini", "[semlf]\nlong-limit = 80\nexperimental-wrap = maybe\n"
    )
    assert check_linefeeds.load_config(str(tmp_path)) == {"long_limit": 80}


def test_old_underscore_spelling_in_ini_is_inert(tmp_path):
    """`experimental_wrap` (underscore) is not the ini key — `experimental-wrap` is.

    An unrecognized key is just prose configparser ignores,
    so this reads as "no experimental_wrap key present", same as no config at all.
    """
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental_wrap = true\n")
    assert check_linefeeds.load_config(str(tmp_path)) == {}


def test_opted_into_withheld_kind_no_config_or_env_defaults_off(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is False


def test_opted_into_withheld_kind_ini_true_enables(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is True


def test_opted_into_withheld_kind_ini_false_stays_off(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = false\n")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is False


def test_opted_into_withheld_kind_env_wins_over_ini_disable(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = false\n")
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "1")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is True


def test_opted_into_withheld_kind_env_wins_over_ini_enable(tmp_path, monkeypatch):
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "0")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is False


def test_opted_into_withheld_kind_invalid_ini_defaults_off(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = maybe\n")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is False


def test_opted_into_withheld_kind_no_path_falls_back_to_env_only(monkeypatch):
    """A call site with no file path still resolves — env-only, never a crash."""
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "1")
    assert check_linefeeds.opted_into_withheld_kind() is True
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "0")
    assert check_linefeeds.opted_into_withheld_kind() is False


def test_opted_into_withheld_kind_empty_env_string_falls_through_to_ini(
    tmp_path, monkeypatch
):
    """Set-but-empty is "unset" for this leg, same as opted_into_withheld_kind always read it.

    Pins the exact `if raw:` check against a change to `if raw.strip():`,
    which would flip this and the whitespace-only case below differently.
    """
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "")
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is True


def test_opted_into_withheld_kind_whitespace_env_string_wins_as_disabled(
    tmp_path, monkeypatch
):
    """Whitespace is non-empty, so the env leg decides outright and strips to "off".

    A change from `if raw:` to `if raw.strip():` would fall through to the ini's `true` here,
    silently flipping this case to enabled.
    """
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", " ")
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    assert check_linefeeds.opted_into_withheld_kind(str(tmp_path / "x.md")) is False


WRAP_ONLY = "a line that ends mid-clause because it was\nwrapped at a column.\n"


def codex_multiline_payload(name, text):
    """Like codex_payload, but prefixes every line.

    A multi-line text then survives the patch as one contiguous "add" run.
    codex_payload's single leading "+" would lose every line but the first.
    """
    body = "".join("+" + line + "\n" for line in text.splitlines())
    patch = (
        "*** Begin Patch\n*** Update File: " + name + "\n@@\n" + body + "*** End Patch"
    )
    return {
        "session_id": "s1",
        "turn_id": "t1",
        "transcript_path": "/tmp/t",
        "cwd": ".",
        "hook_event_name": "PostToolUse",
        "model": "m",
        "permission_mode": "default",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "tool_response": {"output": "Done"},
        "tool_use_id": "call_1",
    }


def test_experimental_wrap_ini_true_enables_wrap_in_hook_feedback(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    (tmp_path / ".git").mkdir()
    write(tmp_path / "doc.md", WRAP_ONLY)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    for agent, payload in (
        ("claude", claude_payload("doc.md", WRAP_ONLY)),
        ("codex", codex_multiline_payload("doc.md", WRAP_ONLY)),
    ):
        r = run_hook(payload, tmp_path, agent=agent)
        assert r.returncode == 0, agent
        assert kinds_in(r.stdout) == {"wrap"}, agent
        assert r.stderr == "", agent


def test_experimental_wrap_ini_false_env_true_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "1")
    (tmp_path / ".git").mkdir()
    write(tmp_path / "doc.md", WRAP_ONLY)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = false\n")
    for agent, payload in (
        ("claude", claude_payload("doc.md", WRAP_ONLY)),
        ("codex", codex_multiline_payload("doc.md", WRAP_ONLY)),
    ):
        r = run_hook(payload, tmp_path, agent=agent)
        assert r.returncode == 0, agent
        assert kinds_in(r.stdout) == {"wrap"}, agent


def test_experimental_wrap_ini_true_env_zero_env_wins_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMLF_EXPERIMENTAL_WRAP", "0")
    (tmp_path / ".git").mkdir()
    write(tmp_path / "doc.md", WRAP_ONLY)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = true\n")
    for agent, payload in (
        ("claude", claude_payload("doc.md", WRAP_ONLY)),
        ("codex", codex_multiline_payload("doc.md", WRAP_ONLY)),
    ):
        r = run_hook(payload, tmp_path, agent=agent)
        assert r.returncode == 0, agent
        assert r.stdout == "", agent
        assert r.stderr == "", agent


def test_experimental_wrap_invalid_ini_value_keeps_wrap_withheld(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    (tmp_path / ".git").mkdir()
    write(tmp_path / "doc.md", WRAP_ONLY)
    write(tmp_path / ".semlf.ini", "[semlf]\nexperimental-wrap = maybe\n")
    payload = claude_payload("doc.md", WRAP_ONLY)
    r = run_hook(payload, tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_experimental_wrap_no_config_matches_current_behavior(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMLF_EXPERIMENTAL_WRAP", raising=False)
    (tmp_path / ".git").mkdir()
    write(tmp_path / "doc.md", WRAP_ONLY)
    payload = claude_payload("doc.md", WRAP_ONLY)
    r = run_hook(payload, tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""
