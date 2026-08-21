"""`semlf render`: SARIF and GitHub annotations as pure functions of the documents file.

A renderer never analyzes and never exits on finding content,
so the frozen exit contract is untouched by construction.
The documents list is exactly what `--json` emits,
which is what makes one analysis pass servable to every reader.
"""

import io
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "cli"))

import check_linefeeds as core  # noqa: E402
from semlf import cli as semlf_cli  # noqa: E402
from semlf import render  # noqa: E402


def document(path="doc.md", diagnostics=()):
    return {
        "schema_version": 2,
        "path": path,
        "diagnostics": list(diagnostics),
    }


def diagnostic(kind="fused", line=1, start=0, end=27, message="two sentences"):
    return {
        "kind": kind,
        "line": line,
        "message": message,
        "excerpt": "One sentence. Another here.",
        "anchor": {"start": start, "end": end},
        "evidence": {"start": start, "end": end},
        "ownership": {"start": start + 4, "end": end - 6},
        "ownership_basis": "token",
    }


TRIO = [
    diagnostic("fused", line=1, start=0, end=27),
    diagnostic("wrap", line=3, start=40, end=61, message="ends mid-clause"),
    diagnostic("long", line=5, start=80, end=210, message="advisory: long"),
]


def test_renderers_and_gate_ignore_the_suggestion_member():
    """A suggestion is hook-delivery payload; SARIF, annotations, and the gate never read it.

    Byte-identical output with and without one is what proves the schema-2
    `replaces` change cannot reach a CI reader.
    """
    import ci_gate

    bare = diagnostic("fused")
    carrying = dict(
        bare,
        suggestion={"lines": ["One sentence.", "Another here."], "replaces": 2},
    )
    without = [document(diagnostics=[bare])]
    with_suggestion = [document(diagnostics=[carrying])]
    assert json.dumps(render.sarif(without), sort_keys=True) == json.dumps(
        render.sarif(with_suggestion), sort_keys=True
    )
    assert list(render.github_annotations(without)) == list(
        render.github_annotations(with_suggestion)
    )
    assert ci_gate.gate(without, ["fused"]) == ci_gate.gate(with_suggestion, ["fused"])


# --- SARIF ------------------------------------------------------------------


def test_sarif_maps_the_three_kinds_to_the_three_levels():
    got = render.sarif([document(diagnostics=TRIO)])
    results = got["runs"][0]["results"]
    assert [r["level"] for r in results] == ["error", "warning", "note"]
    assert [r["ruleId"] for r in results] == ["fused", "wrap", "long"]


def test_sarif_never_copies_an_absolute_offset_into_a_column():
    """The anchor is an absolute code-point span over the whole file.

    A finding after line 1 whose anchor starts at offset 40 is at column 1 of its own line,
    not at column 41 of anything.
    """
    got = render.sarif(
        [document(diagnostics=[diagnostic("wrap", line=3, start=40, end=61)])]
    )
    region = got["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region["startLine"] == 3
    assert region["endLine"] == 3
    assert region["startColumn"] == 1
    assert region["endColumn"] == 22  # anchor length + 1, not an offset
    assert region["endColumn"] != 41


def test_sarif_declares_its_measurement_units():
    got = render.sarif([document(diagnostics=TRIO)])
    run = got["runs"][0]
    assert run["columnKind"] == "unicodeCodePoints"
    # Every boundary the core's splitlines recognizes, CRLF before its prefixes.
    assert run["newlineSequences"][0] == "\r\n"
    assert set(run["newlineSequences"]) == {
        "\r\n",
        "\n",
        "\r",
        "\x0b",
        "\x0c",
        "\x1c",
        "\x1d",
        "\x1e",
        "\x85",
        " ",
        " ",
    }


def test_sarif_of_nothing_is_a_valid_document_with_zero_results():
    got = render.sarif([])
    assert got["version"] == "2.1.0"
    assert got["runs"][0]["results"] == []
    assert got["runs"][0]["tool"]["driver"]["name"] == "semlf"
    assert got["runs"][0]["tool"]["driver"]["version"] == core.__version__


def test_sarif_rules_carry_the_kind_descriptions():
    got = render.sarif([document(diagnostics=TRIO)])
    rules = {r["id"] for r in got["runs"][0]["tool"]["driver"]["rules"]}
    assert rules == {"fused", "wrap", "long"}


def test_sarif_line_and_column_integrity_across_odd_boundaries():
    """Real analysis through the real emitters, on text with non-LF separators."""
    for text, path in (
        ("intro line.\r\nOne sentence. Another here.\r\n", "crlf.md"),
        ("intro line. One sentence. Another here.\n", "ls.md"),
        ("intro line.\x0cOne sentence. Another here.\n", "ff.md"),
        ("intro \U0001f600 emoji.\nOne sentence. Another here.\n", "astral.md"),
    ):
        findings = core.diagnose(text, path)
        assert findings, path
        docs = [core.to_schema(path, findings)]
        region = render.sarif(docs)["runs"][0]["results"][0]["locations"][0][
            "physicalLocation"
        ]["region"]
        assert region["startLine"] == 2, path
        assert region["startColumn"] == 1, path


# --- GitHub annotations -----------------------------------------------------


def test_annotations_map_the_three_kinds_to_the_three_commands():
    lines = list(render.github_annotations([document(diagnostics=TRIO)]))
    assert len(lines) == 3
    assert lines[0].startswith("::error ")
    assert lines[1].startswith("::warning ")
    assert lines[2].startswith("::notice ")


def test_annotations_pin_the_location_properties():
    """Exact decoded properties for a finding after line 1, not just presence."""
    lines = list(
        render.github_annotations(
            [document("docs/a.md", [diagnostic("fused", line=7, message="msg here")])]
        )
    )
    (line,) = lines
    head, message = line.split("::", 2)[1:]
    props = dict(part.split("=", 1) for part in head.split(" ", 1)[1].split(","))
    assert props["file"] == "docs/a.md"
    assert props["line"] == "7"
    assert props["endLine"] == "7"
    assert props["title"] == "semlf%3A fused"  # : escapes in properties
    assert props["title"].replace("%3A", ":") == "semlf: fused"
    assert message == "msg here"


@pytest.mark.parametrize(
    "hostile",
    ["a%b.md", "a,b.md", "a:b.md", "a\rb.md", "a\nb.md", "檔案.md"],
    ids=["percent", "comma", "colon", "cr", "lf", "non-ascii"],
)
def test_annotation_properties_survive_a_hostile_path(hostile):
    lines = list(render.github_annotations([document(hostile, [diagnostic("fused")])]))
    (line,) = lines
    assert "\n" not in line and "\r" not in line
    head = line.split("::", 2)[1]
    props = dict(part.split("=", 1) for part in head.split(" ", 1)[1].split(","))
    decoded = (
        props["file"]
        .replace("%3A", ":")
        .replace("%2C", ",")
        .replace("%0D", "\r")
        .replace("%0A", "\n")
        .replace("%25", "%")
    )
    assert decoded == hostile


def test_annotation_message_escapes_less_than_properties():
    """Message data escapes %, CR, LF; only properties escape : and ,."""
    lines = list(
        render.github_annotations(
            [document("a.md", [diagnostic("fused", message="x: 1, y%\r\nz")])]
        )
    )
    (line,) = lines
    message = line.split("::", 2)[2]
    assert message == "x: 1, y%25%0D%0Az"


# --- the subcommand ---------------------------------------------------------


def run_render(argv, stdin_text=""):
    saved = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    try:
        return semlf_cli.main(argv)
    finally:
        sys.stdin = saved


def test_render_reads_a_documents_file(tmp_path, capsys):
    where = tmp_path / "docs.json"
    where.write_text(json.dumps([document(diagnostics=TRIO)]), encoding="utf-8")
    assert run_render(["render", "sarif", str(where)]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["version"] == "2.1.0"


def test_render_reads_stdin_when_given_a_dash(capsys):
    payload = json.dumps([document(diagnostics=TRIO)])
    assert run_render(["render", "github", "-"], stdin_text=payload) == 0
    assert capsys.readouterr().out.count("::") >= 3


def test_render_never_exits_on_finding_content(capsys):
    """Three fused findings render at exit 0; the gate is someone else's job."""
    payload = json.dumps([document(diagnostics=[diagnostic("fused")] * 3)])
    assert run_render(["render", "sarif", "-"], stdin_text=payload) == 0


def test_render_rejects_a_wrong_renderer_name(capsys):
    assert run_render(["render", "html", "-"]) == 64
    assert run_render(["render"]) == 64


def test_render_rejects_unusable_input(tmp_path, capsys):
    assert run_render(["render", "sarif", str(tmp_path / "absent.json")]) == 1
    assert run_render(["render", "sarif", "-"], stdin_text="not json") == 1
    assert run_render(["render", "sarif", "-"], stdin_text='{"not": "a list"}') == 1


def test_sarif_shape_is_pinned_exactly():
    # The v1.0 contract pin: every key a SARIF consumer reads, byte for byte, over one representative diagnostic.
    # Wording is display-only and never part of the pin:
    # the finding message is supplied by this test,
    # and the rule descriptions are read from render._RULES,
    # so an intentional wording edit lands in exactly one place.
    got = render.sarif([document(diagnostics=[diagnostic()])])
    assert got == {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "semlf",
                        "version": core.__version__,
                        "informationUri": "https://github.com/arloliu/semantic-linefeeds",
                        "rules": [
                            {
                                "id": "fused",
                                "shortDescription": {"text": render._RULES["fused"]},
                            },
                            {
                                "id": "wrap",
                                "shortDescription": {"text": render._RULES["wrap"]},
                            },
                            {
                                "id": "long",
                                "shortDescription": {"text": render._RULES["long"]},
                            },
                        ],
                    }
                },
                "columnKind": "unicodeCodePoints",
                "newlineSequences": render._NEWLINES,
                "results": [
                    {
                        "ruleId": "fused",
                        "level": "error",
                        "message": {"text": "two sentences"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "doc.md"},
                                    "region": {
                                        "startLine": 1,
                                        "endLine": 1,
                                        "startColumn": 1,
                                        "endColumn": 28,
                                    },
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_annotation_command_shape_is_pinned_exactly():
    got = list(
        render.github_annotations(
            [document(diagnostics=[diagnostic(message="a % and\na colon: here")])]
        )
    )
    assert got == [
        "::error file=doc.md,line=1,endLine=1,title=semlf%3A fused"
        "::a %25 and%0Aa colon: here"
    ]
