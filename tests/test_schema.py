"""tests/test_schema.py — the versioned diagnostic schema."""

import json

import check_linefeeds


def test_schema_wraps_diagnostics_verbatim():
    text = "One sentence here. Another sentence follows.\n"
    diagnostics = check_linefeeds.diagnose(text, "doc.md")
    doc = check_linefeeds.to_schema("doc.md", diagnostics)
    assert doc["schema_version"] == check_linefeeds.DIAGNOSTIC_SCHEMA_VERSION == 2
    assert doc["path"] == "doc.md"
    assert doc["diagnostics"] == diagnostics


def test_schema_is_json_serializable_with_ranges():
    text = "One sentence here. Another sentence follows.\n"
    doc = check_linefeeds.to_schema("doc.md", check_linefeeds.diagnose(text, "doc.md"))
    parsed = json.loads(json.dumps(doc))
    (d,) = parsed["diagnostics"]
    assert set(d) >= {
        "kind",
        "line",
        "message",
        "excerpt",
        "anchor",
        "evidence",
        "ownership",
        "ownership_basis",
    }


def test_a_degraded_diagnostic_serializes_a_null_ownership():
    # A `wrap`, because a `fused` almost never degrades any more: see test_diagnostics.py.
    text = "the cat and the\nthe dog ran\n"
    doc = check_linefeeds.to_schema("doc.md", check_linefeeds.diagnose(text, "doc.md"))
    (d,) = json.loads(json.dumps(doc))["diagnostics"]
    assert d["ownership"] is None
    assert d["ownership_basis"] == "degraded"


def test_serialized_diagnostics_keep_the_frozen_kind_order():
    text = (
        "One sentence here. Another sentence follows, and this fused line also runs "
        "long enough that the advisory logic wants to flag it as well, which makes two kinds\n"
        "on\n"
    )
    doc = check_linefeeds.to_schema("doc.md", check_linefeeds.diagnose(text, "doc.md"))
    parsed = json.loads(json.dumps(doc))
    assert [d["kind"] for d in parsed["diagnostics"]] == ["fused", "long", "wrap"]


def test_text_renderer_reads_diagnostics_and_tuples_identically():
    text = "One sentence here. Another sentence follows.\n"
    diagnostics = check_linefeeds.diagnose(text, "doc.md")
    tuples = check_linefeeds.check(text, "doc.md")
    assert check_linefeeds.format_findings(
        diagnostics, "doc.md", snippet=False
    ) == check_linefeeds.format_findings(tuples, "doc.md", snippet=False)


def test_a_fused_diagnostic_carries_no_withholding_key_by_default():
    """`to_schema` passes diagnostics through verbatim.

    A key added to a finding therefore reaches every consumer of the document,
    so the class vector is opt-in and the default document is the one it always was.
    """
    text = "One sentence here. Another sentence follows.\n"
    doc = check_linefeeds.to_schema("doc.md", check_linefeeds.diagnose(text, "doc.md"))
    (d,) = doc["diagnostics"]
    assert "withheld_by" not in d


def test_the_withholding_flag_adds_the_key_and_changes_nothing_else():
    """The same finding either way, plus one key."""
    text = "One sentence here. Another sentence follows.\n"
    (plain,) = check_linefeeds.diagnose(text, "doc.md")
    (annotated,) = check_linefeeds.diagnose(text, "doc.md", withholding=True)
    assert annotated["withheld_by"] == ("terminator_period",)
    assert {k: v for k, v in annotated.items() if k != "withheld_by"} == plain
