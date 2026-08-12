"""tests/test_diagnostics.py — the ranges every diagnostic carries."""
import pytest

import check_linefeeds


def diags(text, path="doc.md", spans=None):
    return check_linefeeds.diagnose(text, path, spans)


def test_a_fused_diagnostic_owns_its_match_through_the_opening_token():
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == "here. Another"
    assert d["ownership_basis"] == "token"


def test_fused_ownership_stops_at_any_whitespace():
    text = "One sentence here. Another\tword follows and then more\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == "here. Another"
    assert text[d["ownership"]["end"]] == "\t"


def test_a_wrap_diagnostic_owns_the_boundary_tokens():
    text = ("the compiler will assume all functions provide an `ABIInternal`\n"
            "implementation.\n")
    (d,) = diags(text)
    assert d["kind"] == "wrap"
    owned = text[d["ownership"]["start"]:d["ownership"]["end"]]
    assert owned == "an `ABIInternal`\nimplementation"
    assert d["ownership_basis"] == "token"


def test_wrap_evidence_spans_both_lines_and_anchor_spans_one():
    text = ("the compiler will assume all functions provide an `ABIInternal`\n"
            "implementation.\n")
    (d,) = diags(text)
    anchor = text[d["anchor"]["start"]:d["anchor"]["end"]]
    assert "\n" not in anchor
    evidence = text[d["evidence"]["start"]:d["evidence"]["end"]]
    assert "\n" in evidence
    assert evidence.endswith("implementation.")


def test_a_comment_marker_degrades_nothing_when_prose_is_verbatim():
    text = "# One sentence here. Another sentence follows.\n"
    (d,) = diags(text, path="script.py")
    assert d["ownership_basis"] == "token"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == "here. Another"


def test_an_ambiguous_match_carries_no_ownership():
    text = "Stop aa. Bb then aa. Bb again.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert d["ownership"] is None
    assert d["ownership_basis"] == "degraded"


LONG_PROSE = ("This advisory line keeps going with a possible clause boundary, "
              "and it continues well past the configured limit so the checker "
              "flags it as long today.")


def test_long_ownership_is_the_prose_not_the_markers():
    text = "> " + LONG_PROSE + "\n"
    (d,) = diags(text)
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == d["excerpt"]
    assert text[:d["ownership"]["start"]] == "> "


def test_long_ownership_excludes_the_list_marker():
    text = "- " + LONG_PROSE + "\n"
    (d,) = diags(text)
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == LONG_PROSE
    assert text[:d["ownership"]["start"]] == "- "


def test_long_ownership_excludes_the_comment_marker():
    text = "// " + LONG_PROSE + "\n"
    (d,) = diags(text, path="main.go")
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"]:d["ownership"]["end"]] == LONG_PROSE
    assert text[:d["ownership"]["start"]] == "// "


def test_a_wrap_with_a_repeated_boundary_token_carries_no_ownership():
    # The two fixtures isolate the two lookup seams.
    # The first repeats only the upper terminal token ("count").
    # The second keeps the upper terminal ("each") unique.
    # It repeats only the lower opening token ("value") instead,
    # so each locate failure is pinned independently.
    upper_repeat = "the count matches the count\nremains stable for now\n"
    (d,) = diags(upper_repeat)
    assert d["kind"] == "wrap"
    assert d["ownership"] is None and d["ownership_basis"] == "degraded"
    lower_repeat = "the outcome depends on each\nvalue equals the value here\n"
    (d,) = diags(lower_repeat)
    assert d["kind"] == "wrap"
    assert d["ownership"] is None and d["ownership_basis"] == "degraded"


def test_a_finding_after_a_non_lf_separator_still_carries_ranges():
    for sep in ("\r", "\u2028"):
        text = "plain" + sep + "One sentence here. Another sentence follows.\n"
        (d,) = diags(text)
        assert d["line"] == 2
        assert text[d["ownership"]["start"]:d["ownership"]["end"]] == "here. Another"
        for key in ("anchor", "evidence", "ownership"):
            rng = d[key]
            assert 0 <= rng["start"] <= rng["end"] <= len(text)


def test_anchor_and_evidence_exclude_the_line_terminator():
    text = "One sentence here. Another sentence follows.\r\n"
    (d,) = diags(text)
    anchor = text[d["anchor"]["start"]:d["anchor"]["end"]]
    assert anchor == "One sentence here. Another sentence follows."
    assert d["evidence"] == d["anchor"]


def test_ranges_stay_inside_text_without_a_trailing_newline():
    text = "One sentence here. Another sentence follows."
    (d,) = diags(text)
    for key in ("anchor", "evidence", "ownership"):
        rng = d[key]
        assert 0 <= rng["start"] <= rng["end"] <= len(text)


def test_same_line_diagnostics_keep_the_frozen_kind_order():
    text = ("One sentence here. Another sentence follows, and this fused line also runs "
            "long enough that the advisory logic wants to flag it as well, which makes two kinds\n"
            "on\n")
    assert [d["kind"] for d in diags(text)] == ["fused", "long", "wrap"]


def test_check_is_a_projection_of_diagnose():
    text = "One sentence here. Another sentence follows.\n"
    assert check_linefeeds.check(text, "doc.md") == [
        (d["line"], d["kind"], d["message"], d["excerpt"])
        for d in check_linefeeds.diagnose(text, "doc.md")]


def test_none_spans_report_everything_and_empty_spans_nothing():
    text = "One sentence here. Another sentence follows.\n"
    assert len(diags(text, spans=None)) == 1
    assert diags(text, spans=[]) == []


def test_a_span_inside_the_ownership_reports_the_diagnostic():
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    inside = d["ownership"]["start"] + 1
    assert len(diags(text, spans=[{"start": inside, "end": inside + 1}])) == 1


def test_a_span_elsewhere_in_the_line_reports_nothing():
    text = "One sentence here. Another sentence follows.\n"
    assert diags(text, spans=[{"start": 0, "end": 2}]) == []


def test_a_span_ending_or_starting_at_the_ownership_edge_reports_nothing():
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    own = d["ownership"]
    assert diags(text, spans=[{"start": 0, "end": own["start"]}]) == []
    assert diags(text, spans=[{"start": own["end"], "end": len(text)}]) == []


def test_a_zero_width_boundary_on_the_newline_owns_a_wrap():
    text = ("the compiler will assume all functions provide an `ABIInternal`\n"
            "implementation.\n")
    newline_at = text.index("\n")
    assert len(diags(text, spans=[{"at": newline_at}])) == 1


def test_an_unchanged_boundary_is_not_reported_for_changed_evidence():
    """ADR-0005's founding case: new evidence must not resurrect an old boundary.

    The edit lands inside the lower line's tail, far from the boundary tokens,
    so the wrap whose evidence includes that line is still not owned by it.
    """
    text = ("the compiler will assume all functions provide an `ABIInternal`\n"
            "implementation of every method named in the manifest below.\n")
    tail = text.rindex("manifest")
    assert diags(text, spans=[{"start": tail, "end": tail + 8}]) == []


def test_a_degraded_diagnostic_never_reports_under_spans():
    text = "Stop aa. Bb then aa. Bb again.\n"
    assert len(diags(text, spans=None)) == 1
    everything = [{"start": 0, "end": len(text)}]
    assert diags(text, spans=everything) == []


def test_an_ambiguous_wrap_token_suppresses_rather_than_widens():
    """`Use *`value`*` peels to a bare `*`, which its raw line holds twice.

    Whole-line fallback would let the tail edit below own this wrap;
    dropping ownership keeps the unrelated edit silent.
    """
    text = "Use *`value`*\nimplementation tail words here\n"
    assert "wrap" in [d["kind"] for d in diags(text)]
    tail = text.index("words")
    assert diags(text, spans=[{"start": tail, "end": tail + 5}]) == []


def test_editing_only_the_quote_marker_reports_no_long_advisory():
    text = "> " + LONG_PROSE + "\n"
    assert diags(text, spans=[{"start": 0, "end": 2}]) == []
    (d,) = diags(text)
    inside = d["ownership"]["start"] + 5
    assert len(diags(text, spans=[{"start": inside, "end": inside + 1}])) == 1


def test_editing_only_the_list_or_comment_marker_reports_nothing():
    listed = "- " + LONG_PROSE + "\n"
    assert diags(listed, spans=[{"start": 0, "end": 2}]) == []
    (d,) = diags(listed)
    inside = d["ownership"]["start"] + 5
    assert len(diags(listed, spans=[{"start": inside, "end": inside + 1}])) == 1
    commented = "// " + LONG_PROSE + "\n"
    assert diags(commented, "main.go", spans=[{"start": 0, "end": 3}]) == []
    (d,) = diags(commented, "main.go")
    inside = d["ownership"]["start"] + 5
    assert len(diags(commented, "main.go", spans=[{"start": inside, "end": inside + 1}])) == 1


def test_a_span_in_the_tab_separated_tail_reports_nothing():
    text = "One sentence here. Another\tword follows and then more\n"
    tail = text.index("follows")
    assert diags(text, spans=[{"start": tail, "end": tail + 7}]) == []


def test_a_repeated_boundary_token_keeps_unrelated_edits_silent():
    for text, needle in (
        ("the count matches the count\nremains stable for now\n", "now"),
        ("the outcome depends on each\nvalue equals the value here\n", "here"),
    ):
        assert len(diags(text, spans=None)) == 1
        tail = text.rindex(needle)
        assert diags(text, spans=[{"start": tail, "end": tail + len(needle)}]) == []


def test_a_degraded_mapping_span_still_filters_by_ownership():
    # What a degraded mapping forfeits is the hook's decision (Plan B);
    # the core filter treats both mapping values identically in this slice.
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    inside = d["ownership"]["start"] + 1
    span = {"start": inside, "end": inside + 1, "mapping": "degraded"}
    assert len(diags(text, spans=[span])) == 1


def test_a_malformed_span_raises_even_for_a_non_target_path():
    with pytest.raises(ValueError):
        check_linefeeds.diagnose("plain\n", "photo.png", [{"bogus": 1}])
