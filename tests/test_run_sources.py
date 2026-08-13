"""tests/test_run_sources.py — the shared source runner behind every mode."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_linefeeds

FUSED = "One sentence. Another fused on the same line.\n"
CLEAN = "One sentence per line.\n"

# Over 40 characters with a comma-led conjunction:
# the long predicate needs a boundary hint as well as length.
LONG_WITH_BOUNDARY = (
    "The exporter batches metrics in memory, "
    "and it retries failed uploads until the queue drains.\n"
)


def test_violation_exits_one_and_reports(capsys):
    rc = check_linefeeds.run_sources([("doc.md", FUSED)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "fused" in out and "doc.md" in out


def test_clean_sources_exit_zero_silently(capsys):
    rc = check_linefeeds.run_sources([("doc.md", CLEAN)])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_long_findings_are_advisory_only(capsys, monkeypatch):
    monkeypatch.setattr(check_linefeeds, "CLI_LONG_LIMIT", 40)
    rc = check_linefeeds.run_sources([("doc.md", LONG_WITH_BOUNDARY)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "long" in out


def test_json_mode_emits_a_report_list(capsys):
    rc = check_linefeeds.run_sources([("a.md", FUSED), ("b.md", CLEAN)],
                                     as_json=True)
    reports = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert [r["path"] for r in reports] == ["a.md"]


def test_empty_sources_are_clean(capsys):
    assert check_linefeeds.run_sources([]) == 0
    assert capsys.readouterr().out == ""
    assert check_linefeeds.run_sources([], as_json=True) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_run_files_still_forces_one_on_read_errors(tmp_path, capsys):
    """The reader keeps its own contract after the split."""
    good = tmp_path / "good.md"
    good.write_text(CLEAN, encoding="utf-8")
    rc = check_linefeeds.run_files([str(good), str(tmp_path / "missing.md")])
    captured = capsys.readouterr()
    assert rc == 1
    assert "cannot read" in captured.err
