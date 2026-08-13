"""tests/test_semlf_cli.py — the semlf CLI delegates everything to the core."""
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "cli"))
import check_linefeeds
from semlf import cli as semlf_cli


def test_version_names_semlf_with_the_core_version(capsys):
    rc = semlf_cli.main(["--version"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == f"semlf {check_linefeeds.__version__}"


def test_forwarded_version_names_semlf_too(capsys):
    # `--version` short-circuits before argv reaches the core,
    # but a spelling like `check --version` is rewritten to `--file --version`,
    # and it hits the core's own argparse --version action instead.
    # That action must also report the invoking surface, not the core's internal name.
    rc = semlf_cli.main(["check", "--version"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == f"semlf {check_linefeeds.__version__}"


def test_help_names_semlf_not_the_core(capsys):
    for argv in (["--help"], ["-h"], ["check", "--help"], ["check", "-h"]):
        rc = semlf_cli.main(argv)
        out = capsys.readouterr().out
        assert rc == 0
        assert "semlf" in out
        assert "check PATH" in out
        assert "check_linefeeds" not in out


def test_check_without_paths_is_a_semlf_usage_error(capsys):
    rc = semlf_cli.main(["check"])
    err = capsys.readouterr().err
    assert rc == 64
    assert "semlf" in err
    assert "check_linefeeds" not in err


def test_file_mode_parity_on_a_violation(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text("One sentence. Another fused on the same line.\n", encoding="utf-8")
    rc = semlf_cli.main(["--file", str(bad)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "fused" in out


def test_check_subcommand_is_file_mode(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text("One sentence. Another fused on the same line.\n", encoding="utf-8")
    rc = semlf_cli.main(["check", str(bad)])
    assert rc == 1
    assert "fused" in capsys.readouterr().out


def test_clean_file_exits_zero(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("One sentence per line.\n", encoding="utf-8")
    assert semlf_cli.main(["--file", str(good)]) == 0
    assert semlf_cli.main(["check", str(good)]) == 0


def test_unreadable_input_exits_one(tmp_path, capsys):
    assert semlf_cli.main(["--file", str(tmp_path / "missing.md")]) == 1
    capsys.readouterr()


def test_every_usage_error_names_semlf(capsys):
    for argv in ([], ["--file"], ["check", "--json"], ["--bogus"],
                 ["--file", "x.md", "--long-limit", "-1"]):
        rc = semlf_cli.main(argv)
        err = capsys.readouterr().err
        assert rc == 64
        assert "semlf" in err
        assert "check_linefeeds" not in err


def test_hook_passthrough_keeps_exit_two(tmp_path, capsys, monkeypatch):
    # Hook mode skips tmp-component and platform-temp paths before diagnosis,
    # so the payload path is relative and cwd moves into the temp repo.
    monkeypatch.chdir(tmp_path)
    text = "// One sentence. Another fused here.\n"
    (tmp_path / "doc.go").write_text(text, encoding="utf-8")
    payload = {"tool_name": "Edit",
               "tool_input": {"file_path": "doc.go", "new_string": text}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    rc = semlf_cli.main(["--hook", "claude"])
    capsys.readouterr()
    assert rc == 2


def test_invocation_state_is_restored(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("One sentence per line.\n", encoding="utf-8")
    before_argv = list(sys.argv)
    before_limit = check_linefeeds.CLI_LONG_LIMIT
    semlf_cli.main(["--file", str(good), "--long-limit", "0"])
    assert sys.argv == before_argv
    assert check_linefeeds.CLI_LONG_LIMIT == before_limit


def test_long_limit_does_not_leak_between_calls(tmp_path, capsys):
    """A flag on call one must not still be in force on call two.

    The sentence carries a comma-led conjunction:
    the long predicate needs a boundary hint as well as length,
    so a hintless sentence would never fire and the test would prove nothing.
    """
    doc = tmp_path / "doc.md"
    line = ("The exporter batches metrics in memory, "
            "and it retries failed uploads until the queue drains.")
    doc.write_text(line + "\n", encoding="utf-8")
    semlf_cli.main(["--file", str(doc), "--long-limit", "40"])
    first = capsys.readouterr().out
    assert "long" in first
    semlf_cli.main(["--file", str(doc)])
    second = capsys.readouterr().out
    assert "long" not in second
    semlf_cli.main(["--file", str(doc), "--long-limit", "40"])
    third = capsys.readouterr().out
    assert "long" in third


def test_state_is_restored_after_an_injected_crash(tmp_path, monkeypatch):
    before_argv = list(sys.argv)
    before_limit = check_linefeeds.CLI_LONG_LIMIT

    def boom(prog=None):
        # Same signature as the seam, or the TypeError would fire
        # before the injected crash and prove nothing.
        raise RuntimeError("injected")

    monkeypatch.setattr(check_linefeeds, "main", boom)
    with pytest.raises(RuntimeError):
        semlf_cli.main(["--file", "whatever.md"])
    assert sys.argv == before_argv
    assert check_linefeeds.CLI_LONG_LIMIT == before_limit
