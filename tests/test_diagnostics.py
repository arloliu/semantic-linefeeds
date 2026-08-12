"""tests/test_diagnostics.py — the ranges every diagnostic carries."""
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
