"""tests/test_git_modes.py — git snapshot providers and their matrix."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import HAS_GIT, git, git_out, isolate_git_env

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "cli"))
import check_linefeeds  # noqa: E402  (imported for path setup parity)
from semlf import cli as semlf_cli  # noqa: E402
from semlf import providers  # noqa: E402

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git is required")


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    isolate_git_env(monkeypatch)


FUSED = "One sentence. Another fused on the same line.\n"
CLEAN = "One sentence per line.\n"


def repo(tmp_path):
    git("init", "-q", cwd=tmp_path)
    return tmp_path


def commit_file(root, name, text, message="c"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git("add", name, cwd=root)
    git("commit", "-q", "-m", message, cwd=root)


def stage_file(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git("add", name, cwd=root)


def test_staged_reads_the_index_not_the_worktree(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "doc.md", FUSED)
    (root / "doc.md").write_text(CLEAN, encoding="utf-8")
    sources = providers.staged_sources(str(root))
    assert [(os.path.basename(p), t) for p, t in sources] == [("doc.md", FUSED)]


def test_staged_on_an_unborn_head_lists_the_first_files(tmp_path):
    root = repo(tmp_path)
    stage_file(root, "doc.md", FUSED)
    sources = providers.staged_sources(str(root))
    assert [t for _, t in sources] == [FUSED]


def test_diff_lists_only_unstaged_changes(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "staged.md", CLEAN)
    commit_file(root, "dirty.md", CLEAN)
    stage_file(root, "staged.md", FUSED)
    (root / "dirty.md").write_text(FUSED, encoding="utf-8")
    names = [os.path.basename(p) for p, _ in providers.diff_sources(str(root))]
    assert names == ["dirty.md"]


def test_changed_lists_staged_and_unstaged_against_head(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "a.md", CLEAN)
    commit_file(root, "b.md", CLEAN)
    stage_file(root, "a.md", FUSED)
    (root / "b.md").write_text(FUSED, encoding="utf-8")
    names = sorted(os.path.basename(p) for p, _ in providers.changed_sources(str(root)))
    assert names == ["a.md", "b.md"]


def test_changed_reads_the_worktree_not_the_index(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "doc.md", FUSED)
    worktree_text = "A different worktree sentence.\n"
    (root / "doc.md").write_text(worktree_text, encoding="utf-8")
    assert [t for _, t in providers.changed_sources(str(root))] == [worktree_text]


def test_changed_works_on_an_unborn_head(tmp_path):
    root = repo(tmp_path)
    stage_file(root, "doc.md", FUSED)
    assert [t for _, t in providers.changed_sources(str(root))] == [FUSED]


def test_deleted_files_never_appear(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    git("rm", "-q", "doc.md", cwd=root)
    assert providers.staged_sources(str(root)) == []
    assert providers.changed_sources(str(root)) == []


def test_untracked_files_never_appear(tmp_path):
    """git diff does not list untracked paths; stage a file to check it."""
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    (root / "new.md").write_text(FUSED, encoding="utf-8")
    assert providers.diff_sources(str(root)) == []
    assert providers.changed_sources(str(root)) == []


def test_non_checkable_extensions_are_filtered(tmp_path):
    root = repo(tmp_path)
    stage_file(root, "data.csv", "a,b\n")
    stage_file(root, "doc.md", CLEAN)
    names = [os.path.basename(p) for p, _ in providers.staged_sources(str(root))]
    assert names == ["doc.md"]


def test_excluded_paths_are_filtered_from_discovery(tmp_path):
    root = repo(tmp_path)
    commit_file(root, ".semlf.ini", "[semlf]\nexclude = generated/\n")
    stage_file(root, "generated/api.md", FUSED)
    stage_file(root, "doc.md", FUSED)
    names = [os.path.basename(p) for p, _ in providers.staged_sources(str(root))]
    assert names == ["doc.md"]


def test_filenames_with_spaces_survive_the_listing(tmp_path):
    root = repo(tmp_path)
    stage_file(root, "release notes.md", FUSED)
    sources = providers.staged_sources(str(root))
    assert [os.path.basename(p) for p, _ in sources] == ["release notes.md"]


def test_repo_root_outside_a_repository_raises(tmp_path, monkeypatch):
    # The host filesystem above tmp_path is not under the test's control
    # (TMPDIR can sit under a configured checkout),
    # so a ceiling pins discovery to the empty tmp_path.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(providers.SourceError):
        providers.repo_root()


def test_unreadable_worktree_content_is_loud(tmp_path, monkeypatch):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    (root / "doc.md").write_text(FUSED, encoding="utf-8")
    real_open = open

    def failing_open(path, *a, **k):
        if str(path).endswith("doc.md"):
            raise OSError("injected")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", failing_open)
    with pytest.raises(providers.SourceError):
        providers.diff_sources(str(root))


def test_unmerged_paths_are_a_loud_stop(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN, message="base")
    git("checkout", "-q", "-b", "one", cwd=root)
    commit_file(root, "doc.md", "One line.\n", message="one")
    git("checkout", "-q", "-b", "two", "HEAD~1", cwd=root)
    commit_file(root, "doc.md", "Two line.\n", message="two")
    merge = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "merge",
            "one",
        ],
        cwd=str(root),
        capture_output=True,
    )
    assert merge.returncode == 1  # a conflict, not a git refusal
    assert git_out("ls-files", "-u", cwd=root)  # the unmerged index is the fixture
    with pytest.raises(providers.SourceError):
        providers.staged_sources(str(root))


def test_typechange_to_symlink_is_skipped_not_read(tmp_path):
    """A symlink is never opened: not from the worktree, not from the index."""
    root = repo(tmp_path)
    target = tmp_path / "outside.md"
    target.write_text(FUSED, encoding="utf-8")
    commit_file(root, "doc.md", CLEAN)
    (root / "doc.md").unlink()
    (root / "doc.md").symlink_to(target)
    assert providers.diff_sources(str(root)) == []
    git("add", "doc.md", cwd=root)
    assert providers.staged_sources(str(root)) == []


def test_gitlinks_are_non_checkable(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    head = git_out("rev-parse", "HEAD", cwd=root)
    git("update-index", "--add", "--cacheinfo", f"160000,{head},linked.md", cwd=root)
    assert providers.staged_sources(str(root)) == []


def test_a_colon_named_file_reads_its_own_bytes(tmp_path):
    """A file named 0:doc.md must never be read as stage 0 of doc.md."""
    root = repo(tmp_path)
    stage_file(root, "doc.md", CLEAN)
    stage_file(root, "0:doc.md", FUSED)
    texts = {os.path.basename(p): t for p, t in providers.staged_sources(str(root))}
    assert texts["0:doc.md"] == FUSED
    assert texts["doc.md"] == CLEAN


def test_non_ascii_filenames_survive_quotepath(tmp_path):
    """-z output is verbatim; a quotepath-mangled name would fail the read."""
    root = repo(tmp_path)
    stage_file(root, "naïve.md", FUSED)
    sources = providers.staged_sources(str(root))
    assert [os.path.basename(p) for p, _ in sources] == ["naïve.md"]


def test_a_corrupt_head_is_loud_not_an_empty_tree_diff(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    (root / ".git" / "HEAD").write_text("0" * 40 + "\n", encoding="utf-8")
    with pytest.raises(providers.SourceError):
        providers.changed_sources(str(root))


def test_a_missing_git_executable_is_loud(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(providers.subprocess, "run", no_git)
    with pytest.raises(providers.SourceError):
        providers.repo_root()


def test_a_malformed_branch_target_is_loud_not_an_empty_tree_diff(tmp_path):
    """A born branch whose loose ref holds garbage must never look unborn."""
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    ref = git_out("symbolic-ref", "HEAD", cwd=root)
    ref_file = root / ".git" / Path(*ref.split("/"))
    ref_file.write_text("not a sha\n", encoding="utf-8")
    with pytest.raises(providers.SourceError):
        providers.changed_sources(str(root))


def test_symlink_recorded_type_gates_even_without_os_symlinks(tmp_path):
    """core.symlinks=false materializes a symlink as a plain file of link text.

    The 120000 index entry is created without any OS symlink privilege,
    so this pins the recorded-type gate, not the filesystem one.
    """
    root = repo(tmp_path)
    git("config", "core.symlinks", "false", cwd=root)
    commit_file(root, "doc.md", CLEAN)
    (root / "linktext").write_text("../outside", encoding="utf-8")
    blob = git_out("hash-object", "-w", "linktext", cwd=root)
    (root / "linktext").unlink()
    git("update-index", "--add", "--cacheinfo", f"120000,{blob},link.md", cwd=root)
    (root / "link.md").write_text("../outside\n", encoding="utf-8")
    assert providers.staged_sources(str(root)) == []
    assert providers.changed_sources(str(root)) == []


def test_parse_raw_accepts_each_supported_record():
    raw = (
        b":000000 100644 0000000000000000000000000000000000000000 "
        b"1111111111111111111111111111111111111111 A\0a.md\0"
        b":100644 100644 2222222222222222222222222222222222222222 "
        b"3333333333333333333333333333333333333333 M\0dir/b sp.md\0"
        b":100644 120000 4444444444444444444444444444444444444444 "
        b"5555555555555555555555555555555555555555 T\0link.md\0"
    )
    assert providers._parse_raw(raw) == [
        ("a.md", "100644", "1111111111111111111111111111111111111111"),
        ("dir/b sp.md", "100644", "3333333333333333333333333333333333333333"),
        ("link.md", "120000", "5555555555555555555555555555555555555555"),
    ]


def test_parse_raw_is_loud_for_unmerged_unknown_and_malformed():
    meta = (
        b":100644 100644 2222222222222222222222222222222222222222 "
        b"3333333333333333333333333333333333333333 "
    )
    good = meta + b"M\0ok.md\0"
    oid2, oid3 = b"2" * 40, b"3" * 40
    for stream in (
        meta + b"U\0conflicted.md\0",
        meta + b"X\0strange.md\0",
        meta + b"R087\0old.md\0new.md\0",  # impossible under --no-renames
        meta + b"C100\0src.md\0copy.md\0",
        meta + b"D\0gone.md\0",
        meta + b"A100\0scored.md\0",  # a scored status is never valid here
        b"garbage\0a.md\0",
        meta + b"M\0",
        # Each syntax guard falls independently —
        # one wrong dimension per row, the rest valid.
        # Post-image mode: octal but short.
        b":100644 10064 " + oid2 + b" " + oid3 + b" M\0a.md\0",
        # Post-image mode: right length, non-octal.
        b":100644 10z644 " + oid2 + b" " + oid3 + b" M\0a.md\0",
        # Object ids: hex and equal-width, but a width git never emits —
        # only the allowed-width guard can reject this row.
        b":100644 100644 2222 3333 M\0a.md\0",
        # Post-image oid: right length, non-hex.
        b":100644 100644 " + oid2 + b" " + b"g" * 40 + b" M\0a.md\0",
        # Pre-image mode malformed.
        b":1z0644 100644 " + oid2 + b" " + oid3 + b" M\0a.md\0",
        # Pre-image oid malformed.
        b":100644 100644 " + b"g" * 40 + b" " + oid3 + b" M\0a.md\0",
        # Mismatched id widths inside one record.
        b":100644 100644 " + oid2 + b" " + b"3" * 64 + b" M\0a.md\0",
        good + b"\0" + good,  # interior empty token
        good + b"garbage",  # trailing garbage after a valid prefix
        good[:-1],
    ):  # missing the terminal NUL
        with pytest.raises(providers.SourceError):
            providers._parse_raw(stream)


def test_parse_raw_accepts_only_a_cleanly_terminated_stream():
    """Empty output is the one zero-record form; a valid stream ends in one NUL."""
    assert providers._parse_raw(b"") == []
    meta = (
        b":100644 100644 2222222222222222222222222222222222222222 "
        b"3333333333333333333333333333333333333333 "
    )
    assert providers._parse_raw(meta + b"M\0ok.md\0") == [
        ("ok.md", "100644", "3333333333333333333333333333333333333333")
    ]


def test_parse_raw_accepts_the_sha256_width():
    """64-hex ids are the other repository width; support must be causal."""
    record = b":100644 100644 " + b"2" * 64 + b" " + b"3" * 64 + b" M\0sha256.md\0"
    assert providers._parse_raw(record) == [("sha256.md", "100644", "3" * 64)]


def test_parse_raw_keeps_hostile_path_bytes_verbatim():
    raw = (
        b":000000 100644 0000000000000000000000000000000000000000 "
        b"1111111111111111111111111111111111111111 A\0evil\tname\nwith.md\0"
    )
    assert providers._parse_raw(raw) == [
        ("evil\tname\nwith.md", "100644", "1111111111111111111111111111111111111111")
    ]


def test_undecodable_staged_bytes_are_replaced_not_dropped(tmp_path):
    """errors="replace" is contract: the file is checked, never silently absent."""
    root = repo(tmp_path)
    (root / "doc.md").write_bytes(b"One sentence line.\xff\xfe\n")
    git("add", "doc.md", cwd=root)
    sources = providers.staged_sources(str(root))
    assert len(sources) == 1
    text = sources[0][1]
    assert "�" in text
    assert "One sentence line." in text


def test_undecodable_worktree_bytes_are_replaced_not_dropped(tmp_path):
    """errors="replace" is contract at the worktree seam too, not just the blob read."""
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    (root / "doc.md").write_bytes(b"One sentence line.\xff\xfe\n")
    sources = providers.diff_sources(str(root))
    assert len(sources) == 1
    text = sources[0][1]
    assert "�" in text
    assert "One sentence line." in text


def test_raw_records_carry_full_object_ids_despite_abbrev_config(tmp_path):
    """--no-abbrev is the control: a host core.abbrev must not shorten the oid."""
    root = repo(tmp_path)
    git("config", "core.abbrev", "4", cwd=root)
    stage_file(root, "doc.md", FUSED)
    records = providers._raw_records(str(root), "--cached")
    assert len(records) == 1
    assert records[0][2] == git_out("rev-parse", ":doc.md", cwd=root)


def test_staged_reads_the_enumerated_object_across_an_index_update(
    tmp_path, monkeypatch
):
    """The record's oid is the identity read — a later restage cannot swap it."""
    root = repo(tmp_path)
    stage_file(root, "doc.md", FUSED)
    real_raw = providers._raw_records

    def raw_then_restage(*args, **kwargs):
        records = real_raw(*args, **kwargs)
        stage_file(root, "doc.md", CLEAN)  # the index moves after enumeration
        return records

    monkeypatch.setattr(providers, "_raw_records", raw_then_restage)
    assert [t for _, t in providers.staged_sources(str(root))] == [FUSED]


@pytest.mark.parametrize(
    "outcome,unborn",
    [
        ((1, b"", b""), True),
        ((1, b"", b"warning: ignoring broken ref refs/heads/main\n"), False),
        ((0, b"deadbeef\n", b""), False),
        ((2, b"", b"fatal: broken\n"), False),
    ],
)
def test_head_probe_accepts_only_silent_absence(monkeypatch, outcome, unborn):
    """Absence is exit 1 with empty stderr; every other probe result stays loud."""

    def fake_git(root, *args, input_bytes=None):
        if args[0] == "rev-parse" and args[-1] == "HEAD":
            raise providers.SourceError("semlf: no head")
        if args[0] == "symbolic-ref":
            return b"refs/heads/main\n"
        if args[0] == "hash-object":
            return b"4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(providers, "_git", fake_git)
    monkeypatch.setattr(providers, "_git_query", lambda root, *args: outcome)
    if unborn:
        tree = providers._head_or_empty_tree("anywhere")
        assert tree == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    else:
        with pytest.raises(providers.SourceError):
            providers._head_or_empty_tree("anywhere")


def test_head_probe_requires_a_symbolic_head(monkeypatch):
    def fake_git(root, *args, input_bytes=None):
        raise providers.SourceError("semlf: failing")

    monkeypatch.setattr(providers, "_git", fake_git)
    with pytest.raises(providers.SourceError):
        providers._head_or_empty_tree("anywhere")


def test_worktree_read_never_follows_a_link_shaped_path(tmp_path):
    """The physical belt on its own: a 100644 record whose path is a link now."""
    root = repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(FUSED, encoding="utf-8")
    (root / "doc.md").symlink_to(outside)
    records = [("doc.md", "100644", "0" * 40)]
    assert providers._worktree_sources(str(root), records) == []
    assert (
        outside.read_text(encoding="utf-8") == FUSED
    )  # never opened for write, never followed


def test_typechange_to_regular_file_is_checked(tmp_path):
    """The inverse gate: a symlink that became a real file is prose again."""
    root = repo(tmp_path)
    outside = tmp_path / "target.md"
    outside.write_text(CLEAN, encoding="utf-8")
    (root / "doc.md").symlink_to(outside)
    git("add", "doc.md", cwd=root)
    git("commit", "-q", "-m", "link", cwd=root)
    (root / "doc.md").unlink()
    (root / "doc.md").write_text(FUSED, encoding="utf-8")
    git("add", "doc.md", cwd=root)
    assert [t for _, t in providers.staged_sources(str(root))] == [FUSED]


def test_isolate_git_env_neutralizes_a_hostile_environment(tmp_path, monkeypatch):
    """Seed the vectors the helper claims to close; prove each stays closed."""
    templates = tmp_path / "templates"
    (templates / "hooks").mkdir(parents=True)
    hook = templates / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    git("init", "-q", cwd=elsewhere)
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(templates))
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "init.templatedir")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(templates))
    isolate_git_env(monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    root = repo(work)
    stage_file(root, "doc.md", FUSED)
    # The template vectors (env and injected config) installed nothing,
    # and the GIT_DIR selector did not send the work elsewhere.
    assert not (root / ".git" / "hooks" / "post-commit").exists()
    records = providers._raw_records(str(root), "--cached")
    assert [r[0] for r in records] == ["doc.md"]


def test_matrix_staged_bad_worktree_fixed(tmp_path, monkeypatch, capsys):
    """Partial staging, direction one: the index still carries the violation."""
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "doc.md", FUSED)
    (root / "doc.md").write_text(CLEAN, encoding="utf-8")
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 1
    capsys.readouterr()
    assert semlf_cli.main(["--diff"]) == 0
    capsys.readouterr()
    assert semlf_cli.main(["--changed"]) == 0
    capsys.readouterr()


def test_matrix_staged_clean_worktree_bad(tmp_path, monkeypatch, capsys):
    """Partial staging, direction two: only the worktree modes see the sin."""
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "doc.md", "A staged clean sentence.\n")
    (root / "doc.md").write_text(FUSED, encoding="utf-8")
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 0
    capsys.readouterr()
    assert semlf_cli.main(["--diff"]) == 1
    capsys.readouterr()
    assert semlf_cli.main(["--changed"]) == 1
    capsys.readouterr()


def test_matrix_rename_with_edits_reports_the_new_name(tmp_path, monkeypatch, capsys):
    """Under --no-renames the new path arrives as an addition — still checked."""
    root = repo(tmp_path)
    commit_file(root, "old.md", CLEAN)
    git("mv", "old.md", "new.md", cwd=root)
    stage_file(root, "new.md", FUSED)
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 1
    out = capsys.readouterr().out
    assert "new.md" in out
    assert "old.md" not in out


def test_matrix_subdirectory_invocation_reports_cwd_relative_paths(
    tmp_path, monkeypatch, capsys
):
    root = repo(tmp_path)
    commit_file(root, "docs/guide.md", CLEAN)
    (root / "sub").mkdir()
    stage_file(root, "docs/guide.md", FUSED)
    monkeypatch.chdir(root / "sub")
    assert semlf_cli.main(["--staged"]) == 1
    out = capsys.readouterr().out
    assert os.path.join("..", "docs", "guide.md") in out


def test_matrix_config_governs_staged_content_from_a_subdirectory(
    tmp_path, monkeypatch, capsys
):
    """Config discovery keys off the checked path, not the invoking directory."""
    root = repo(tmp_path)
    commit_file(root, ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    line = (
        "The exporter batches metrics in memory, "
        "and it retries failed uploads until the queue drains.\n"
    )
    (root / "sub").mkdir()
    stage_file(root, "doc.md", line)
    monkeypatch.chdir(root / "sub")
    rc = semlf_cli.main(["--staged"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "long" in out


def test_matrix_policy_is_the_worktrees_even_for_staged_content(
    tmp_path, monkeypatch, capsys
):
    """ADR-0013's ruling: one policy source — the working tree — in every mode.

    Direction one: an exclude that exists only in the worktree governs --staged.
    """
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "generated/api.md", FUSED)
    (root / ".semlf.ini").write_text(
        "[semlf]\nexclude = generated/\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 0
    capsys.readouterr()


def test_matrix_a_staged_only_exclude_does_not_govern(tmp_path, monkeypatch, capsys):
    """Direction two: policy staged but absent from the worktree is not in force."""
    root = repo(tmp_path)
    stage_file(root, ".semlf.ini", "[semlf]\nexclude = generated/\n")
    stage_file(root, "generated/api.md", FUSED)
    (root / ".semlf.ini").unlink()
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 1
    assert "fused" in capsys.readouterr().out


def test_matrix_a_staged_only_long_limit_does_not_govern(tmp_path, monkeypatch, capsys):
    """The same divergence pin for the long-limit leg of the policy."""
    root = repo(tmp_path)
    line = (
        "The exporter batches metrics in memory, "
        "and it retries failed uploads until the queue drains.\n"
    )
    stage_file(root, ".semlf.ini", "[semlf]\nlong-limit = 40\n")
    stage_file(root, "doc.md", line)
    (root / ".semlf.ini").unlink()
    monkeypatch.chdir(root)
    rc = semlf_cli.main(["--staged"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "long" not in out


def test_matrix_crlf_content_fires_in_every_mode(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    crlf = FUSED.replace("\n", "\r\n")
    (root / "doc.md").write_bytes(crlf.encode("utf-8"))
    git("-c", "core.autocrlf=false", "add", "doc.md", cwd=root)
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--staged"]) == 1
    assert "fused" in capsys.readouterr().out
    assert semlf_cli.main(["check", "doc.md"]) == 1
    assert "fused" in capsys.readouterr().out


def test_matrix_crlf_content_fires_in_worktree_modes(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    crlf = FUSED.replace("\n", "\r\n")
    (root / "doc.md").write_bytes(crlf.encode("utf-8"))
    monkeypatch.chdir(root)
    assert semlf_cli.main(["--diff"]) == 1
    assert "fused" in capsys.readouterr().out
    assert semlf_cli.main(["--changed"]) == 1
    assert "fused" in capsys.readouterr().out


def test_matrix_crlf_hook_payload_still_blocks(tmp_path):
    import json

    (tmp_path / ".git").mkdir()
    text = "// One sentence. Another fused here.\r\n"
    (tmp_path / "doc.go").write_bytes(text.encode("utf-8"))
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "doc.go", "new_string": text},
    }
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "check_linefeeds.py"),
            "--hook",
            "claude",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert r.returncode == 2
    assert "fused" in r.stderr


def test_matrix_crlf_codex_hook_payload_still_blocks(tmp_path):
    import json

    (tmp_path / ".git").mkdir()
    text = "// One sentence. Another fused here.\r\n"
    (tmp_path / "doc.go").write_bytes(text.encode("utf-8"))
    patch = (
        "*** Begin Patch\n*** Update File: doc.go\n@@\n+"
        + "// One sentence. Another fused here."
        + "\n*** End Patch"
    )
    payload = {
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
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "check_linefeeds.py"),
            "--hook",
            "codex",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert r.returncode == 2
    assert "fused" in r.stderr


def test_matrix_staged_nested_path_keeps_worktree_policy(tmp_path, monkeypatch, capsys):
    """A vanished worktree parent must not cost the file its policy.

    Both halves of the ruling:
    the root worktree exclude still suppresses the staged nested file,
    and the root worktree long-limit still governs its diagnosis.
    """
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    stage_file(root, "nested/doc.md", FUSED)
    import shutil

    shutil.rmtree(root / "nested")
    monkeypatch.chdir(root)
    (root / ".semlf.ini").write_text("[semlf]\nexclude = nested/\n", encoding="utf-8")
    assert semlf_cli.main(["--staged"]) == 0
    capsys.readouterr()
    (root / ".semlf.ini").unlink()
    assert semlf_cli.main(["--staged"]) == 1
    capsys.readouterr()


def test_matrix_staged_nested_path_keeps_worktree_long_limit(
    tmp_path, monkeypatch, capsys
):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    line = (
        "The exporter batches metrics in memory, "
        "and it retries failed uploads until the queue drains.\n"
    )
    stage_file(root, "nested/doc.md", line)
    import shutil

    shutil.rmtree(root / "nested")
    monkeypatch.chdir(root)
    (root / ".semlf.ini").write_text("[semlf]\nlong-limit = 40\n", encoding="utf-8")
    rc = semlf_cli.main(["--staged"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "long" in out


def test_matcher_survives_windows_shaped_relative_paths():
    """The pure matcher sees /-normalized input; these pin the normalization seam."""
    cfg = check_linefeeds._exclude_match
    assert cfg("vendor/doc.md", ["vendor/"])
    assert cfg("docs/generated/api.md", ["docs/generated/"])
    assert not cfg("docsX/generated/api.md", ["docs/generated/"])


def test_excluded_normalizes_backslash_config_patterns(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".semlf.ini").write_text(
        "[semlf]\nexclude = docs\\generated\\\n", encoding="utf-8"
    )
    target = tmp_path / "docs" / "generated" / "api.md"
    target.parent.mkdir(parents=True)
    target.write_text("text\n", encoding="utf-8")
    assert check_linefeeds.excluded(str(target))


import json  # noqa: E402

# --- the CI selection modes: --base and --all -------------------------------
#
# --base reports span-owned diagnostics:
# a CI run annotates someone's pull request,
# and a finding that predates the branch is not that author's to answer.
# The spans come from one coordinate system, the core's own line partition —
# git's LF-only hunk arithmetic never enters.


def pr_shaped(tmp_path, base_text, branch_text, name="doc.md"):
    """main holds base_text; a branch holds branch_text; checkout is clean."""
    root = repo(tmp_path)
    # The isolated environment has no init.defaultBranch, so name it explicitly.
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=root)
    commit_file(root, name, base_text)
    git("checkout", "-q", "-b", "feature", cwd=root)
    commit_file(root, name, branch_text, message="change")
    return root


def run_semlf(argv, cwd, monkeypatch):
    monkeypatch.chdir(cwd)
    return semlf_cli.main(argv)


def test_base_sees_the_pr_where_changed_sees_nothing(tmp_path, monkeypatch, capsys):
    root = pr_shaped(
        tmp_path,
        "One clean line.\n",
        "One clean line.\nTwo sentences. On one line.\n",
    )
    assert run_semlf(["--changed", "--json"], root, monkeypatch) == 0
    assert json.loads(capsys.readouterr().out) == []
    code = run_semlf(["--base", "main", "--json"], root, monkeypatch)
    documents = json.loads(capsys.readouterr().out)
    assert code == 1
    assert [d["kind"] for doc in documents for d in doc["diagnostics"]] == ["fused"]


def test_base_reports_only_what_the_change_owns(tmp_path, monkeypatch, capsys):
    """One pre-existing finding, one finding on a changed line; only the second."""
    root = pr_shaped(
        tmp_path,
        "Old fused pair. Sitting here already.\n\nA clean paragraph.\n",
        "Old fused pair. Sitting here already.\n\nNew fused pair. Added by the branch.\n",
    )
    assert run_semlf(["--base", "main", "--json"], root, monkeypatch) == 1
    documents = json.loads(capsys.readouterr().out)
    lines = [d["line"] for doc in documents for d in doc["diagnostics"]]
    assert lines == [3]


def test_base_owns_a_finding_created_by_deleting_a_newline(
    tmp_path, monkeypatch, capsys
):
    """The deletion leaves a zero-width boundary, and the boundary owns the fusion."""
    root = pr_shaped(
        tmp_path,
        "One whole sentence here.\nAnother whole sentence.\n",
        "One whole sentence here. Another whole sentence.\n",
    )
    assert run_semlf(["--base", "main", "--json"], root, monkeypatch) == 1
    documents = json.loads(capsys.readouterr().out)
    assert [d["kind"] for doc in documents for d in doc["diagnostics"]] == ["fused"]


def test_base_owns_a_change_after_a_form_feed(tmp_path, monkeypatch, capsys):
    """No LF arithmetic: the form feed is a line boundary to the core, not to git."""
    root = pr_shaped(
        tmp_path,
        "Intro line.\x0cA clean line here.\n",
        "Intro line.\x0cTwo sentences. On one line.\n",
    )
    assert run_semlf(["--base", "main", "--json"], root, monkeypatch) == 1
    documents = json.loads(capsys.readouterr().out)
    assert [d["line"] for doc in documents for d in doc["diagnostics"]] == [2]


def test_an_unresolvable_base_names_the_remedy(tmp_path, monkeypatch, capsys):
    root = pr_shaped(tmp_path, "One line.\n", "One line.\nTwo. Fused here.\n")
    assert run_semlf(["--base", "no-such-ref", "--json"], root, monkeypatch) == 1
    err = capsys.readouterr().err
    assert "no-such-ref" in err
    assert "fetch-depth" in err or "deepen" in err or "does not resolve" in err


def test_all_respects_excludes_where_file_does_not(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    commit_file(root, ".semlf.ini", "[semlf]\nexclude = vendored/**\n")
    commit_file(root, "vendored/x.md", FUSED)
    commit_file(root, "doc.md", FUSED)
    assert run_semlf(["--all", "--json"], root, monkeypatch) == 1
    documents = json.loads(capsys.readouterr().out)
    paths = {os.path.basename(doc["path"]) for doc in documents if doc["diagnostics"]}
    assert paths == {"doc.md"}


def test_all_skips_a_symlink_by_its_recorded_mode(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    (root / "link.md").symlink_to("doc.md")
    git("add", "link.md", cwd=root)
    git("commit", "-q", "-m", "link", cwd=root)
    assert run_semlf(["--all", "--json"], root, monkeypatch) == 0
    documents = json.loads(capsys.readouterr().out)
    assert all("link.md" not in doc["path"] for doc in documents)


def test_all_refuses_an_unmerged_index_loudly(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    git("checkout", "-q", "-b", "one", cwd=root)
    commit_file(root, "doc.md", "One side.\n", message="one")
    git("checkout", "-q", "-b", "two", "HEAD~1", cwd=root)
    commit_file(root, "doc.md", "Two side.\n", message="two")
    merge = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "one"],
        cwd=str(root),
        capture_output=True,
    )
    assert merge.returncode == 1, merge.stderr  # a conflict, not a git refusal
    assert git_out("ls-files", "-u", cwd=root)
    assert run_semlf(["--all", "--json"], root, monkeypatch) == 1
    assert "unmerged" in capsys.readouterr().err


def test_all_survives_a_newline_bearing_name(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    commit_file(root, "doc.md", CLEAN)
    weird = root / "we\nird.md"
    weird.write_text(FUSED, encoding="utf-8")
    git("add", "we\nird.md", cwd=root)
    git("commit", "-q", "-m", "weird", cwd=root)
    assert run_semlf(["--all", "--json"], root, monkeypatch) == 1
    documents = json.loads(capsys.readouterr().out)
    assert any("ird.md" in doc["path"] for doc in documents)
