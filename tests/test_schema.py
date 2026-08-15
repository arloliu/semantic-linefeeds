"""tests/test_schema.py — the versioned diagnostic schema."""

import json

import check_linefeeds


def test_schema_wraps_diagnostics_verbatim():
    text = "One sentence here. Another sentence follows.\n"
    diagnostics = check_linefeeds.diagnose(text, "doc.md")
    doc = check_linefeeds.to_schema("doc.md", diagnostics)
    assert doc["schema_version"] == check_linefeeds.DIAGNOSTIC_SCHEMA_VERSION == 1
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
    text = "Stop aa. Bb then aa. Bb again.\n"
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
