"""`prose_reflow`: whether two snapshots differ only in where their prose breaks.

The claim it verifies is the one a reflow-only commit makes:
no word changed, no code changed, no paragraph appeared or disappeared —
only the line breaks inside prose moved.
Collapsing whitespace over the whole file cannot verify that claim for code,
because splitting a comment line writes a new comment marker,
so the comparison reads the prose the way the detector reads it.
"""

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from check_linefeeds import prose_reflow  # noqa: E402


def verdict(old, new, path="doc.md"):
    return prose_reflow(old, new, path)


def test_moving_a_markdown_break_is_a_reflow():
    old = "One sentence here. Another sentence here.\n"
    new = "One sentence here.\nAnother sentence here.\n"
    assert verdict(old, new)["reflow"] is True


def test_rejoining_a_wrapped_pair_is_a_reflow():
    old = "a line that was wrapped\nat a column for no reason.\n"
    new = "a line that was wrapped at a column for no reason.\n"
    assert verdict(old, new)["reflow"] is True


def test_splitting_a_comment_writes_a_new_marker_and_is_still_a_reflow():
    old = "# One sentence here. Another sentence here.\nx = 1\n"
    new = "# One sentence here.\n# Another sentence here.\nx = 1\n"
    assert verdict(old, new, "code.py")["reflow"] is True


def test_a_changed_word_is_not_a_reflow():
    old = "One sentence here.\n"
    new = "One sentence there.\n"
    got = verdict(old, new)
    assert got["reflow"] is False
    assert "here" in got["reason"] or "there" in got["reason"]


def test_a_changed_code_line_is_not_a_reflow():
    old = "# A comment line here.\nx = 1\n"
    new = "# A comment line here.\nx = 2\n"
    got = verdict(old, new, "code.py")
    assert got["reflow"] is False
    assert "x = " in got["reason"]


def test_a_new_blank_line_splits_a_paragraph_and_is_not_a_reflow():
    old = "One sentence here.\nAnother sentence here.\n"
    new = "One sentence here.\n\nAnother sentence here.\n"
    assert verdict(old, new)["reflow"] is False


def test_a_word_moved_across_a_paragraph_is_not_a_reflow():
    """The words survive whole-file collapsing, and the meaning does not."""
    old = "One thing ends here.\n\ncode fence below\n"
    old = "First paragraph ends now.\n\nSecond paragraph starts.\n"
    new = "First paragraph ends.\n\nnow Second paragraph starts.\n"
    assert verdict(old, new)["reflow"] is False


def test_identical_snapshots_are_a_reflow_of_nothing():
    text = "One sentence here.\n"
    got = verdict(text, text)
    assert got["reflow"] is True
    assert got["moved"] == 0


def test_a_reflow_counts_the_breaks_it_moved():
    old = "One sentence here. Another sentence here.\n"
    new = "One sentence here.\nAnother sentence here.\n"
    assert verdict(old, new)["moved"] > 0


def test_indentation_alone_may_move_inside_prose():
    """A list continuation takes the content-column indent when it splits."""
    old = "- One sentence here. Another sentence here.\n"
    new = "- One sentence here.\n  Another sentence here.\n"
    assert verdict(old, new)["reflow"] is True


# --- the CLI verb, over real snapshots -------------------------------------

import pytest  # noqa: E402

sys.path.insert(0, str(REPO / "cli"))
from conftest import HAS_GIT, git, isolate_git_env  # noqa: E402
from semlf import cli as semlf_cli  # noqa: E402

pytestmark = []


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch):
    if HAS_GIT:
        isolate_git_env(monkeypatch)


def a_repo(tmp_path, monkeypatch):
    git("init", "-q", cwd=tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def commit(root, name, text):
    (root / name).write_text(text, encoding="utf-8")
    git("add", name, cwd=root)
    git("commit", "-q", "-m", "c", cwd=root)


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_passes_a_pure_break_move(tmp_path, monkeypatch, capsys):
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "doc.md", "One sentence here. Another sentence here.\n")
    (root / "doc.md").write_text(
        "One sentence here.\nAnother sentence here.\n", encoding="utf-8"
    )
    assert semlf_cli.main(["reflow"]) == 0
    out = capsys.readouterr().out
    assert "pure reflow" in out
    assert "1 break(s) moved" in out


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_names_the_word_that_changed(tmp_path, monkeypatch, capsys):
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "doc.md", "One sentence here.\n")
    (root / "doc.md").write_text("One sentence there.\n", encoding="utf-8")
    assert semlf_cli.main(["reflow"]) == 1
    out = capsys.readouterr().out
    assert "CHANGED" in out
    assert "'here.' -> 'there.'" in out


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_fails_on_a_file_outside_prose_scope(tmp_path, monkeypatch, capsys):
    """The claim is about the whole change, so a changed .json falsifies it."""
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "data.json", '{"a": 1}\n')
    (root / "data.json").write_text('{"a": 2}\n', encoding="utf-8")
    assert semlf_cli.main(["reflow"]) == 1


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_fails_on_a_deleted_file(tmp_path, monkeypatch, capsys):
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "doc.md", "One sentence here.\n")
    (root / "doc.md").unlink()
    assert semlf_cli.main(["reflow"]) == 1
    assert "deleted" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_takes_a_ref(tmp_path, monkeypatch, capsys):
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "doc.md", "One sentence here. Another sentence here.\n")
    commit(root, "doc.md", "One sentence here.\nAnother sentence here.\n")
    assert semlf_cli.main(["reflow", "HEAD~1"]) == 0
    assert "pure reflow" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_GIT, reason="git is required")
def test_reflow_verb_rejects_a_ref_that_is_not_a_commit(tmp_path, monkeypatch, capsys):
    root = a_repo(tmp_path, monkeypatch)
    commit(root, "doc.md", "One sentence here.\n")
    assert semlf_cli.main(["reflow", "no-such-ref"]) == 1
    assert "does not name a commit" in capsys.readouterr().err
