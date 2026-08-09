from conftest import PAYLOADS, FIXTURES, run_cli, load_fixture
import check_linefeeds


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
