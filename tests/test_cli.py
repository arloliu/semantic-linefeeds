from conftest import PAYLOADS, FIXTURES, run_cli, load_fixture, REPO
import check_linefeeds
import json
import shutil
import subprocess

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
