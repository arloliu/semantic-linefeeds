"""tests/test_precommit_hook.py — the shipped pre-commit hook definition."""

from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".pre-commit-hooks.yaml"


def test_hook_manifest_is_exactly_one_semlf_hook():
    """The whole non-comment manifest, pinned line for line.

    Exactness is the point:
    a second hook, an `entry` with extra arguments, or `pass_filenames: true` (which would hand --staged worktree paths it must not read) all fail this comparison.
    """
    lines = [
        line
        for line in HOOKS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines == [
        "- id: semlf",
        "  name: semlf semantic linefeeds",
        "  description: one-thought-per-line prose in comments, docstrings, and Markdown",
        "  entry: semlf --staged",
        "  language: python",
        "  pass_filenames: false",
    ]
