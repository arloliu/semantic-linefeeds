"""tests/test_diagnostics.py — the ranges every diagnostic carries."""

import check_linefeeds
import pytest


def diags(text, path="doc.md", spans=None):
    return check_linefeeds.diagnose(text, path, spans)


def test_a_fused_diagnostic_owns_its_match_through_the_opening_token():
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == "here. Another"
    assert d["ownership_basis"] == "token"


def test_fused_ownership_stops_at_any_whitespace():
    text = "One sentence here. Another\tword follows and then more\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == "here. Another"
    assert text[d["ownership"]["end"]] == "\t"


def test_a_wrap_diagnostic_owns_the_boundary_tokens():
    text = (
        "the compiler will assume all functions provide an `ABIInternal`\n"
        "implementation.\n"
    )
    (d,) = diags(text)
    assert d["kind"] == "wrap"
    owned = text[d["ownership"]["start"] : d["ownership"]["end"]]
    assert owned == "an `ABIInternal`\nimplementation"
    assert d["ownership_basis"] == "token"


def test_wrap_evidence_spans_both_lines_and_anchor_spans_one():
    text = (
        "the compiler will assume all functions provide an `ABIInternal`\n"
        "implementation.\n"
    )
    (d,) = diags(text)
    anchor = text[d["anchor"]["start"] : d["anchor"]["end"]]
    assert "\n" not in anchor
    evidence = text[d["evidence"]["start"] : d["evidence"]["end"]]
    assert "\n" in evidence
    assert evidence.endswith("implementation.")


def test_a_comment_marker_degrades_nothing_when_prose_is_verbatim():
    text = "# One sentence here. Another sentence follows.\n"
    (d,) = diags(text, path="script.py")
    assert d["ownership_basis"] == "token"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == "here. Another"


def test_a_repeated_match_now_locates_each_boundary_exactly():
    """Locating by offset removes the ambiguity that used to force a degrade.

    The needle used to be the matched text,
    which a repeated phrase made unfindable,
    so ownership was dropped rather than guessed.
    Indexing into the located prose by the match offset is not a guess,
    so the finding keeps its exact range instead of being withheld under spans.
    """
    text = "Stop aa. Bb then aa. Bb again.\n"
    found = diags(text)
    assert len(found) == 2
    assert all(d["kind"] == "fused" for d in found)
    assert all(d["ownership_basis"] == "token" for d in found)


LONG_PROSE = (
    "This advisory line keeps going with a possible clause boundary, "
    "and it continues well past the configured limit so the checker "
    "flags it as long today."
)


def test_long_ownership_is_the_prose_not_the_markers():
    text = "> " + LONG_PROSE + "\n"
    (d,) = diags(text)
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == d["excerpt"]
    assert text[: d["ownership"]["start"]] == "> "


def test_long_ownership_excludes_the_list_marker():
    text = "- " + LONG_PROSE + "\n"
    (d,) = diags(text)
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == LONG_PROSE
    assert text[: d["ownership"]["start"]] == "- "


def test_long_ownership_excludes_the_comment_marker():
    text = "// " + LONG_PROSE + "\n"
    (d,) = diags(text, path="main.go")
    assert d["kind"] == "long"
    assert text[d["ownership"]["start"] : d["ownership"]["end"]] == LONG_PROSE
    assert text[: d["ownership"]["start"]] == "// "


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
        assert text[d["ownership"]["start"] : d["ownership"]["end"]] == "here. Another"
        for key in ("anchor", "evidence", "ownership"):
            rng = d[key]
            assert 0 <= rng["start"] <= rng["end"] <= len(text)


def test_anchor_and_evidence_exclude_the_line_terminator():
    text = "One sentence here. Another sentence follows.\r\n"
    (d,) = diags(text)
    anchor = text[d["anchor"]["start"] : d["anchor"]["end"]]
    assert anchor == "One sentence here. Another sentence follows."
    assert d["evidence"] == d["anchor"]


def test_ranges_stay_inside_text_without_a_trailing_newline():
    text = "One sentence here. Another sentence follows."
    (d,) = diags(text)
    for key in ("anchor", "evidence", "ownership"):
        rng = d[key]
        assert 0 <= rng["start"] <= rng["end"] <= len(text)


def test_same_line_diagnostics_keep_the_frozen_kind_order():
    text = (
        "One sentence here. Another sentence follows, and this fused line also runs "
        "long enough that the advisory logic wants to flag it as well, which makes two kinds\n"
        "on\n"
    )
    assert [d["kind"] for d in diags(text)] == ["fused", "long", "wrap"]


def test_check_is_a_projection_of_diagnose():
    text = "One sentence here. Another sentence follows.\n"
    assert check_linefeeds.check(text, "doc.md") == [
        (d["line"], d["kind"], d["message"], d["excerpt"])
        for d in check_linefeeds.diagnose(text, "doc.md")
    ]


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
    text = (
        "the compiler will assume all functions provide an `ABIInternal`\n"
        "implementation.\n"
    )
    newline_at = text.index("\n")
    assert len(diags(text, spans=[{"at": newline_at}])) == 1


def test_an_unchanged_boundary_is_not_reported_for_changed_evidence():
    """ADR-0005's founding case: new evidence must not resurrect an old boundary.

    The edit lands inside the lower line's tail, far from the boundary tokens,
    so the wrap whose evidence includes that line is still not owned by it.
    """
    text = (
        "the compiler will assume all functions provide an `ABIInternal`\n"
        "implementation of every method named in the manifest below.\n"
    )
    tail = text.rindex("manifest")
    assert diags(text, spans=[{"start": tail, "end": tail + 8}]) == []


def test_a_degraded_diagnostic_never_reports_under_spans():
    # The fixture is a `wrap`, because a `fused` almost never degrades any more:
    # its ownership is an offset into the located prose rather than a search for the matched text.
    # It is not unreachable, which an earlier version of this comment claimed.
    # A line that repeats its own extracted prose outside the comment still defeats the locate,
    # such as a one-line block comment whose text recurs in a string literal beside it.
    # No shape in the corpus does that, so a `fused` fixture would pin a line nobody writes.
    # `wrap` locates single words, so a word repeated on the upper line defeats the locate naturally.
    text = "the cat and the\nthe dog ran\n"
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
    assert (
        len(diags(commented, "main.go", spans=[{"start": inside, "end": inside + 1}]))
        == 1
    )


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


def test_fused_question_gets_a_two_line_suggestion_with_indentation():
    text = "   Is this right? Yes it is.\n"
    (d,) = diags(text)
    assert d["suggestion"] == {"lines": ["   Is this right?", "   Yes it is."]}


def test_fused_bang_in_a_python_comment_keeps_the_marker_on_both_lines():
    text = "# Stop now! Go later.\n"
    (d,) = diags(text, path="x.py")
    assert d["suggestion"] == {"lines": ["# Stop now!", "# Go later."]}


def test_fused_bang_in_a_blockquote_keeps_the_quote_marker():
    text = "> Stop now! Go later.\n"
    (d,) = diags(text)
    assert d["suggestion"] == {"lines": ["> Stop now!", "> Go later."]}


def test_a_period_fused_line_gets_no_suggestion():
    text = "One sentence here. Another sentence follows.\n"
    (d,) = diags(text)
    assert "suggestion" not in d


def test_a_two_boundary_line_gets_no_suggestion():
    text = "Go now? Come here! Stay put.\n"
    found = diags(text)
    assert len(found) == 2
    assert all(d["kind"] == "fused" for d in found)
    assert all("suggestion" not in d for d in found)


def test_fused_suggestion_byte_identity_holds_with_a_duplicated_prefix():
    # The suggestion replaces the single inter-sentence ASCII space with a line break followed by the repeated line leader;
    # outside that one insertion the bytes are identical to raw.
    # Compute the prefix exactly as the helper does: raw up to where the excerpt starts.
    cases = [
        ("   Is this right? Yes it is.\n", "doc.md"),  # indented
        ("# Stop now! Go later.\n", "x.py"),  # comment leader
        ("> Stop now! Go later.\n", "doc.md"),  # blockquote
    ]
    for text, path in cases:
        (d,) = diags(text, path=path)
        raw = text.rstrip("\n")
        idx = raw.find(d["excerpt"])
        prefix = raw[:idx]
        line1, line2 = d["suggestion"]["lines"]
        assert line1 + " " + line2[len(prefix) :] == raw


def test_a_code_span_anywhere_on_the_line_gets_no_suggestion():
    text = "Use `stop! Go` as code.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_terminator_before_a_closing_quote_gets_no_suggestion():
    text = 'He said "Stop now!" Go on.\n'
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_terminator_before_a_closing_paren_gets_no_suggestion():
    text = "(Stop now!) Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_terminator_before_a_closing_bracket_gets_no_suggestion():
    text = "[Stop now!] Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_terminator_before_closing_emphasis_gets_no_suggestion():
    text = "*Stop now!* Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_carrier_stripped_line_gets_no_suggestion():
    # The trailing carrier suppresses "long" only,
    # so the fused finding survives;
    # the carrier strip still withholds the suggestion (design condition 8), since the two-line shape has nowhere to put the carrier text back.
    text = "Stop now? Go on. <!-- semlf-ignore long -->\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_inline_html_markup_gets_no_suggestion():
    # FUSED_RE still matches inside the quoted attribute value,
    # and the line does not start with "<" so the Markdown extractor still reads it as ordinary prose (design condition 4).
    text = 'Use <span title="stop! Go">x</span>.\n'
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_list_item_gets_no_suggestion():
    # The list marker is stripped from prose but stays in raw,
    # so the prefix "- " fails the repeatable-leader whitelist (design condition 6).
    text = "- Stop now? Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_an_ordered_list_item_gets_no_suggestion():
    text = "1. Stop now? Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_an_asterisk_list_item_gets_no_suggestion():
    # `*` is a list bullet to the Markdown extractor (stripped from prose, kept in raw) exactly like "-";
    # it is deliberately absent from the prefix whitelist for that reason (design condition 6), even though it would otherwise also read as a valid block-comment continuation marker.
    text = "* Stop now? Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_one_line_python_docstring_gets_no_suggestion():
    # The prefix carries the opening triple quote and the tail carries the closing one;
    # both the prefix and tail gates reject this shape (design conditions 6 and 7).
    text = 'def f():\n    """Stop now? Go on."""\n'
    (d,) = diags(text, path="x.py")
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_one_line_block_comment_gets_no_suggestion():
    text = "/* Stop now? Go on. */\n"
    (d,) = diags(text, path="x.c")
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_tab_separator_gets_no_suggestion():
    text = "Stop now?\tGo on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_double_space_separator_gets_no_suggestion():
    text = "Stop now?  Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d


def test_a_non_breaking_space_separator_gets_no_suggestion():
    # FUSED_RE's `\s+` matches a non-breaking space under Python's default Unicode mode,
    # so this still fuses;
    # the exact-one-space gate (design condition 3) is what withholds it.
    # A literal non-breaking space is visually indistinguishable from an
    # ASCII one, so the escape below is deliberate.
    text = "Stop now?" + "\u00a0" + "Go on.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d
