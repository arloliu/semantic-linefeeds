"""The Action's gate: what fails a build is read from the documents, not exits.

A wrap-only run exits 1 from the checker and still passes the default gate;
an unreadable documents file fails however clean the prose was.
"""

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import ci_gate  # noqa: E402


def documents_file(tmp_path, kinds):
    where = tmp_path / "docs.json"
    where.write_text(
        json.dumps(
            [
                {
                    "schema_version": 2,
                    "path": "doc.md",
                    "diagnostics": [
                        {"kind": kind, "line": 1, "message": "m", "excerpt": "e"}
                        for kind in kinds
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return str(where)


def test_a_wrap_alone_passes_the_default_gate(tmp_path, capsys):
    assert ci_gate.main([documents_file(tmp_path, ["wrap", "long"])]) == 0


def test_a_fused_fails_the_default_gate(tmp_path, capsys):
    assert ci_gate.main([documents_file(tmp_path, ["fused"])]) == 1
    assert "1 fused" in capsys.readouterr().err


def test_the_stricter_gate_fails_on_wrap(tmp_path, capsys):
    where = documents_file(tmp_path, ["wrap"])
    assert ci_gate.main(["--fail-on", "fused,wrap", where]) == 1


def test_long_is_refused_as_a_gate_value_not_ignored(tmp_path, capsys):
    where = documents_file(tmp_path, [])
    assert ci_gate.main(["--fail-on", "fused,long", where]) == 64
    assert "ADR-0001" in capsys.readouterr().err


def test_an_unreadable_documents_file_is_never_a_green_build(tmp_path, capsys):
    assert ci_gate.main([str(tmp_path / "absent.json")]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert ci_gate.main([str(broken)]) == 2


def test_a_clean_run_passes_and_says_so(tmp_path, capsys):
    assert ci_gate.main([documents_file(tmp_path, [])]) == 0
    assert "build passes" in capsys.readouterr().out
