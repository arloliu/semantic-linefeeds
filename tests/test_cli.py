from conftest import PAYLOADS, FIXTURES, run_cli, load_fixture, REPO, SCRIPT
import check_linefeeds
import io
import json
import os
import shutil
import subprocess
import sys

import pytest


def hook(payload_name):
    return run_cli(["--hook"], (PAYLOADS / payload_name).read_text())


def test_hook_bad_edit_blocks():
    r = hook("claude_edit_bad.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[wrap]" in r.stderr
    assert "semantic-linefeeds skill" in r.stderr


def test_hook_good_edit_passes():
    assert hook("claude_edit_good.json").returncode == 0


def test_hook_non_target_file_ignored():
    assert hook("claude_other_file.json").returncode == 0


def test_hook_malformed_json_never_crashes():
    assert run_cli(["--hook"], "not json").returncode == 0


def test_file_mode_bad_fixture_exits_1(tmp_path):
    text, _ = load_fixture(FIXTURES / "go" / "bad_wrapped.go")
    f = tmp_path / "bad_wrapped.go"
    f.write_text(text)
    assert run_cli(["--file", str(f)]).returncode == 1


def test_file_mode_long_is_advisory(tmp_path):
    text, _ = load_fixture(FIXTURES / "markdown" / "advisory_long.md")
    f = tmp_path / "advisory_long.md"
    f.write_text(text)
    r = run_cli(["--file", str(f)])
    assert r.returncode == 0
    assert "[long]" in r.stdout


def test_skip_path_relative_and_absolute():
    assert check_linefeeds.skip_path("vendor/doc.go")
    assert check_linefeeds.skip_path("/abs/vendor/doc.go")
    assert check_linefeeds.skip_path("./fixtures/bad.go")
    assert check_linefeeds.skip_path("a/b/node_modules/c.ts")
    assert check_linefeeds.skip_path("C:\\repo\\testdata\\x.go")
    assert not check_linefeeds.skip_path("src/vendored/doc.go")
    assert not check_linefeeds.skip_path("distance/notes.md")


def test_hook_accepts_explicit_claude_agent():
    r = run_cli(["--hook", "claude"], (PAYLOADS / "claude_edit_bad.json").read_text())
    assert r.returncode == 2


def test_file_json_output(tmp_path):
    text, expected = load_fixture(FIXTURES / "go" / "bad_wrapped.go")
    f = tmp_path / "bad_wrapped.go"
    f.write_text(text)
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 1
    data = json.loads(r.stdout)
    got = [(x["line"], x["kind"]) for x in data[0]["findings"]]
    assert sorted(got) == sorted(expected)


def test_file_json_clean_file_emits_empty_list(tmp_path):
    f = tmp_path / "clean.go"
    f.write_text("// One clean sentence.\npackage x\n")
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_file_json_long_only_still_exits_zero(tmp_path):
    text, _ = load_fixture(FIXTURES / "markdown" / "advisory_long.md")
    f = tmp_path / "advisory_long.md"
    f.write_text(text)
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 0
    assert json.loads(r.stdout)[0]["findings"][0]["kind"] == "long"


def test_unreadable_file_exits_1(tmp_path):
    r = run_cli(["--file", str(tmp_path / "missing.go")])
    assert r.returncode == 1
    assert "cannot read" in r.stderr


def test_help_exits_zero():
    assert run_cli(["--help"]).returncode == 0


def test_conflicting_modes_exit_64():
    assert run_cli(["--hook", "claude", "--file", "x.go"]).returncode == 64


def test_json_without_file_mode_exits_64():
    assert run_cli(["--hook", "claude", "--json"], "{}").returncode == 64


def test_no_mode_exits_64():
    assert run_cli([]).returncode == 64


def codex_hook(name):
    return run_cli(["--hook", "codex"], (PAYLOADS / name).read_text())


def test_codex_bad_patch_blocks():
    r = codex_hook("codex_apply_patch_bad.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr


def test_codex_good_patch_passes():
    assert codex_hook("codex_apply_patch_good.json").returncode == 0


def test_codex_non_target_patch_ignored():
    assert codex_hook("codex_apply_patch_other.json").returncode == 0


def test_codex_rename_dispatches_on_destination():
    # notes.txt would be ignored; the Move to: pkg/doc.go rename makes it Go.
    r = codex_hook("codex_apply_patch_rename.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr


def test_codex_disjoint_hunks_do_not_fuse():
    # Two separate addition runs in one file must not form one paragraph;
    # fusing them would fabricate a wrap finding.
    assert codex_hook("codex_apply_patch_two_runs.json").returncode == 0


def test_codex_multifile_patch_reports_each_target():
    r = codex_hook("codex_apply_patch_multifile.json")
    assert r.returncode == 2
    assert "a.go" in r.stderr
    assert "b.rs" in r.stderr


def test_codex_malformed_never_crashes():
    assert run_cli(["--hook", "codex"], "not json").returncode == 0


@pytest.mark.skipif(shutil.which("bun") is None, reason="bun not installed")
def test_opencode_plugin_unit_tests():
    r = subprocess.run(["bun", "test", "adapters/opencode/"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_skip_path_temp_roots(monkeypatch):
    monkeypatch.setattr(check_linefeeds.tempfile, "tempdir", "/var/folders/zz/T")
    assert check_linefeeds.skip_path("/var/folders/zz/T/prompt.md")
    assert check_linefeeds.skip_path("/var/folders/zz/T/deep/nested/note.md")
    assert not check_linefeeds.skip_path("/var/folders-other/doc.md")


def test_skip_path_tmp_component():
    assert check_linefeeds.skip_path("/tmp/claude/v1_review_prompt.md")
    assert check_linefeeds.skip_path("tmp/PROGRESS.md")
    assert check_linefeeds.skip_path("./tmp/notes.md")
    assert not check_linefeeds.skip_path("docs/tmpl/notes.md")


def test_hook_ignores_temp_markdown():
    import tempfile as _tf
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": _tf.gettempdir() + "/agent_prompt.md",
            "content": "Bad break here. Another sentence follows.\n",
        },
    })
    r = run_cli(["--hook"], payload)
    assert r.returncode == 0
    assert r.stderr == ""


def test_file_mode_still_checks_temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(check_linefeeds.tempfile, "tempdir", str(tmp_path))
    bad = tmp_path / "doc.md"
    bad.write_text("One sentence. Two sentences fused.\n", encoding="utf-8")
    assert check_linefeeds.run_files([str(bad)]) == 1


LONGISH = ("This clause runs on and on past sixty characters, "
           "and the tail keeps going to make the point.\n")


def test_long_limit_flag_lowers_threshold(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    r = run_cli(["--file", str(doc), "--long-limit", "60"])
    assert r.returncode == 0
    assert "[long]" in r.stdout


def test_long_limit_zero_disables_advisory(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("x" * 200 + ", and more text here.\n", encoding="utf-8")
    r = run_cli(["--file", str(doc), "--long-limit", "0"])
    assert r.returncode == 0
    assert "[long]" not in r.stdout


def test_long_limit_env_var(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMLF_LONG_LINE"] = "60"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc)],
        capture_output=True, text=True, env=env,
    )
    assert "[long]" in r.stdout


def test_long_limit_flag_beats_env(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMLF_LONG_LINE"] = "60"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc), "--long-limit", "1000"],
        capture_output=True, text=True, env=env,
    )
    assert "[long]" not in r.stdout


def test_long_limit_bad_env_falls_back(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMLF_LONG_LINE"] = "banana"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc)],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0
    assert "[long]" not in r.stdout  # 95 chars is under the 120 default


def test_long_limit_negative_is_usage_error(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("fine\n", encoding="utf-8")
    assert run_cli(["--file", str(doc), "--long-limit", "-5"]).returncode == 64


def raising_gettempdir():
    raise FileNotFoundError("no usable temporary directory")


def test_skip_path_survives_a_failing_temp_discovery(monkeypatch):
    """A host with no usable temp directory must not break path filtering.

    The exclusion is a convenience,
    so losing it costs a few findings on scratch files;
    raising costs the agent its edit.
    """
    monkeypatch.setattr(check_linefeeds.tempfile, "gettempdir", raising_gettempdir)
    assert check_linefeeds.skip_path("vendor/doc.go")
    assert not check_linefeeds.skip_path("src/doc.go")


def test_hook_survives_a_failing_temp_discovery(monkeypatch, capsys):
    """The whole hook, not just skip_path.

    Both entry points catch only JSON errors,
    so an exception raised deeper made the hook exit 1 before checking anything.
    """
    monkeypatch.setattr(check_linefeeds.tempfile, "gettempdir", raising_gettempdir)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/doc.md",
            "content": "One sentence here. Another sentence follows.\n",
        },
    })))
    assert check_linefeeds.run_hook_claude() == 2
    assert "[fused]" in capsys.readouterr().err


def test_version_prints_the_constant():
    r = run_cli(["--version"])
    assert r.returncode == 0
    assert r.stdout.strip().endswith(check_linefeeds.__version__)


def test_version_output_reads_the_constant_rather_than_a_literal(monkeypatch, capsys):
    """Asserting the current value proves only that the two agree today.

    A version hard-coded into the argparse action satisfies that just as well.
    So this drives the constant to a sentinel and demands it come back out.
    """
    monkeypatch.setattr(check_linefeeds, "__version__", "9.9.9-sentinel")
    monkeypatch.setattr(sys, "argv", ["check_linefeeds", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        check_linefeeds.main()
    assert excinfo.value.code == 0
    assert "9.9.9-sentinel" in capsys.readouterr().out


def test_plugin_manifest_agrees_with_the_version_constant():
    """One version, stated twice, must not drift.

    The manifest cannot import the core,
    since the core is copied standalone into hosts that never see this repository.
    """
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["version"] == check_linefeeds.__version__
