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
    assert d["suggestion"] == {
        "lines": ["   Is this right?", "   Yes it is."],
        "replaces": 1,
    }


def test_fused_bang_in_a_python_comment_keeps_the_marker_on_both_lines():
    text = "# Stop now! Go later.\n"
    (d,) = diags(text, path="x.py")
    assert d["suggestion"] == {"lines": ["# Stop now!", "# Go later."], "replaces": 1}


def test_fused_bang_in_a_blockquote_keeps_the_quote_marker():
    text = "> Stop now! Go later.\n"
    (d,) = diags(text)
    assert d["suggestion"] == {"lines": ["> Stop now!", "> Go later."], "replaces": 1}


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


# --- the judged line -------------------------------------------------------
#
# `diagnose` does not read what `prose_stream` yields.
# A harness that re-extracts through the stream reads a different text from the finding's.


def walked(text, path="doc.md"):
    records, _suppressions = check_linefeeds.judged_lines(text, path)
    return records


def only(text, path="doc.md"):
    (record,) = walked(text, path)
    return record


def test_a_path_with_nothing_to_extract_is_not_walked_at_all():
    """None rather than an empty walk, which is what `diagnose` turns into no findings."""
    assert check_linefeeds.judged_lines("plain\n", "photo.png") is None


def test_a_standalone_directive_line_is_consumed_rather_than_judged():
    """It is a paragraph boundary, not prose, and the suppression it carries survives it."""
    records, suppressions = check_linefeeds.judged_lines(
        "<!-- semlf-ignore-next fused -->\nStop now! Go later.\n", "doc.md"
    )
    assert [record["line"] for record in records] == [2]
    assert suppressions == {2: {"fused"}}


def test_a_same_line_directive_leaves_the_line_judged_without_its_carrier():
    """The carrier comes off both views before any pattern runs, and its bytes are kept."""
    record = only("Stop now! Go later. <!-- semlf-ignore wrap -->\n")
    assert record["prose"] == record["raw"] == "Stop now! Go later."
    assert record["original_raw"] == "Stop now! Go later. <!-- semlf-ignore wrap -->"
    assert record["carrier"] == {
        "text": "<!-- semlf-ignore wrap -->",
        "offset": 0,
        "kinds": ("wrap",),
    }
    assert record["suppressed_kinds"] == ("wrap",)


def test_a_line_holding_only_a_carrier_is_not_judged():
    """Nothing is left of it once the carrier comes off, so there is no line to judge."""
    assert walked("<!-- semlf-ignore fused -->\n") == []


def test_an_unrecognized_trailing_tail_leaves_raw_and_prose_one_text():
    """A tail that is not a shared suffix of both views is not a carrier."""
    record = only("Stop now! Go later. not-a-directive\n")
    assert record["carrier"] is None
    assert record["original_raw"] == record["raw"]


def test_a_line_whose_prose_repeats_in_it_carries_no_leader_or_tail():
    """The shipped repair refuses to pick an occurrence, and neither does the record.

    No extractor reaches this today: it is constructed directly,
    because every path to `raw` today puts the prose in it exactly once.
    """
    record = dict(only("Stop now!\n"), raw="x Stop now! Stop now!")
    rebuilt = check_linefeeds._judged_record(
        "", [0, 0], 1, record["raw"], "Stop now!", record["raw"], None, 0
    )
    assert rebuilt["leader"] is None and rebuilt["tail"] is None


def test_a_crlf_terminator_survives_into_the_record():
    """A window is spliced back into the file, so the terminator has to be put back as it was."""
    records = walked("Stop now! Go later.\r\nAnd here it ends.\r\n")
    assert [record["terminator"] for record in records] == ["\r\n", "\r\n"]


def test_a_final_line_with_no_newline_carries_an_empty_terminator():
    assert only("Stop now! Go later.")["terminator"] == ""


def test_the_raw_span_covers_the_line_the_carrier_was_still_on():
    """The span is the anchor, which is the file's line rather than the judged view of it."""
    text = "Stop now! Go later. <!-- semlf-ignore wrap -->\n"
    record = only(text)
    span = record["raw_span"]
    assert text[span["start"] : span["end"]] == record["original_raw"]


def test_a_blank_line_breaks_the_paragraph_and_a_directive_line_does_too():
    """Two records are in one paragraph exactly when nothing was dropped between them."""
    joined = walked("It ends mid-clause and\nthen it keeps running on.\n")
    assert len({record["paragraph"] for record in joined}) == 1
    split = walked("It ends mid-clause and\n\nthen it keeps running on.\n")
    assert len({record["paragraph"] for record in split}) == 2
    directive = walked(
        "It ends mid-clause and\n"
        "<!-- semlf-ignore-next long -->\n"
        "then it keeps running on.\n"
    )
    assert len({record["paragraph"] for record in directive}) == 2


# --- the withholding classes ----------------------------------------------


def withheld(text, path="doc.md"):
    return [
        d["withheld_by"]
        for d in check_linefeeds.diagnose(text, path, withholding=True)
        if d["kind"] == "fused"
    ]


def test_a_suggestion_is_produced_exactly_when_nothing_withholds_it():
    (classes,) = withheld("Stop now! Go later.\n")
    assert classes == ()
    (d,) = diags("Stop now! Go later.\n")
    assert d["suggestion"] == {"lines": ["Stop now!", "Go later."], "replaces": 1}


def test_a_period_boundary_is_its_own_class():
    assert withheld("One sentence here. Another sentence follows.\n") == [
        ("terminator_period",)
    ]


def test_a_closing_quote_before_the_gap_is_a_different_class_from_a_period():
    """The shipped helper answers "not ! or ?" to both, and they are different repairs."""
    assert withheld('He said "stop!" Then he left again.\n') == [("closing_delimiter",)]


def test_a_gap_of_two_spaces_is_its_own_class():
    assert withheld("Stop now!  Go later.\n") == [("gap_multiple_spaces",)]


def test_a_gap_holding_a_tab_is_its_own_class():
    assert withheld("Stop now!\tGo later.\n") == [("gap_tab",)]


def test_a_gap_of_any_other_whitespace_is_its_own_class():
    assert withheld("Stop now!\u00a0Go later.\n") == [("gap_other_whitespace",)]


def test_two_boundaries_on_one_line_are_classed_one_by_one():
    """Per match, not per line, so one line can carry two units with different classes."""
    assert withheld("Go now? Come here! Stay put.\n") == [
        ("many_boundaries",),
        ("many_boundaries",),
    ]
    assert withheld("Go now. Come here! Stay put.\n") == [
        ("many_boundaries", "terminator_period"),
        ("many_boundaries",),
    ]


def test_a_protected_span_anywhere_on_the_line_withholds():
    assert withheld("Run it now! Then read `the file` again.\n") == [
        ("protected_span",)
    ]
    assert withheld("Run it now! Then read a <tag> here.\n") == [("protected_span",)]


def test_a_list_marker_leader_is_a_different_class_from_any_other_leader():
    """A bullet and a docstring both fail the whitelist, and they are not one class."""
    assert withheld("- Stop now! Go later.\n") == [("prefix_list_marker",)]
    assert withheld("1. Stop now! Go later.\n") == [("prefix_list_marker",)]
    assert withheld('def f():\n    """Stop now! Go later."""\n', "x.py") == [
        ("prefix_other", "tail_rejected")
    ]


def test_anything_but_whitespace_behind_the_prose_withholds():
    """A block comment fails on both halves of its line, which is two classes and not one."""
    assert withheld("/* Stop now! Go later. */\n", "x.c") == [
        ("prefix_other", "tail_rejected")
    ]


def test_a_rejected_tail_alone_withholds_on_its_own():
    """Constructed, because no extractor today leaves a bad tail behind a good leader."""
    record = check_linefeeds._judged_record(
        "", [0, 0], 1, "Stop now! Go later. */", "Stop now! Go later.", "", None, 0
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    assert check_linefeeds._fused_withholding(record, match) == ("tail_rejected",)


def test_a_stripped_carrier_leaves_the_finding_and_takes_the_suggestion():
    assert withheld("Stop now! Go later. <!-- semlf-ignore wrap -->\n") == [
        ("carrier_stripped",)
    ]
    (d,) = diags("Stop now! Go later. <!-- semlf-ignore wrap -->\n")
    assert "suggestion" not in d


def test_a_carriage_return_in_the_judged_line_withholds():
    """Constructed directly: every extractor reaches `raw` through splitlines,
    so no current entry path can put one there.
    """
    record = check_linefeeds._judged_record(
        "", [0, 0], 1, "Stop now!\rGo later.", "Stop now! Go later.", "", None, 0
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    assert "carriage_return" in check_linefeeds._fused_withholding(record, match)


def test_a_prose_line_that_is_not_unique_in_its_raw_line_withholds():
    """Also constructed: the prose sits in `raw` exactly once on every path today."""
    record = check_linefeeds._judged_record(
        "", [0, 0], 1, "Go now! X Go now! X", "Go now! X", "", None, 0
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    assert "prose_not_unique" in check_linefeeds._fused_withholding(record, match)


def test_the_prefix_and_tail_classes_are_absent_when_the_prose_is_not_unique():
    """Testing them against an arbitrary occurrence would invent a class the code never had."""
    record = check_linefeeds._judged_record(
        "", [0, 0], 1, "- Go now! X - Go now! X", "Go now! X", "", None, 0
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    classes = check_linefeeds._fused_withholding(record, match)
    assert "prose_not_unique" in classes
    assert not [name for name in classes if name.startswith(("prefix_", "tail_"))]


def test_the_boundary_is_read_from_the_end_of_a_match_and_not_its_start():
    """A match may open on a code span carrying punctuation and whitespace of its own.

    Reading from the start calls the space inside the span the gap,
    and the letter before it the terminator,
    which reports neither the real terminator nor the real gap.
    """
    (classes,) = withheld("Run `make now`. Then read it.\n")
    assert "terminator_period" in classes
    assert not [name for name in classes if name.startswith("gap_")]


# --- the below classes, present only under a wrap pairing ------------------

# One anchor whose sentence runs onto the line below,
# so the detector pairs the two and the lower line enters the repair.
PAIRED_CLEAN = "Stop now! Go later to the\nplace we talked about.\n"


def test_a_clean_paired_window_carries_no_class_at_all():
    assert withheld(PAIRED_CLEAN) == [()]


def test_a_clean_paired_window_absorbs_the_line_below():
    """Rejoin, then one split at the fused boundary; two lines replace two lines."""
    (d,) = [x for x in diags(PAIRED_CLEAN) if x["kind"] == "fused"]
    assert d["suggestion"] == {
        "lines": ["Stop now!", "Go later to the place we talked about."],
        "replaces": 2,
    }


def test_an_unpaired_suggestion_says_it_replaces_one_line():
    (d,) = diags("Stop now! Go later.\n")
    assert d["suggestion"] == {"lines": ["Stop now!", "Go later."], "replaces": 1}


def test_a_paired_window_with_an_unsafe_below_line_withholds_entirely():
    """A one-line split on a two-line window repairs half the sentence.

    That is a wrong repair rather than a smaller right one,
    so the unsafe pairing takes the suggestion with it.
    """
    fused = [
        d
        for d in diags("Stop now! Go later to the\nplace with `code` in it.\n")
        if d["kind"] == "fused"
    ]
    assert fused
    assert all("suggestion" not in d for d in fused)


def test_an_absorbed_suggestion_keeps_the_shared_leader_on_both_lines():
    text = "# Stop now! Go later to the\n# place we talked about.\n"
    (d,) = [x for x in diags(text, "x.py") if x["kind"] == "fused"]
    assert d["suggestion"] == {
        "lines": ["# Stop now!", "# Go later to the place we talked about."],
        "replaces": 2,
    }


def test_a_suppressed_wrap_falls_back_to_the_one_line_shape():
    """The user blessed the break, so the suggestion repairs the anchor alone."""
    text = "<!-- semlf-ignore-next wrap -->\nStop now! Go later to the\nplace we talked about.\n"
    (d,) = [x for x in diags(text) if x["kind"] == "fused"]
    assert d["suggestion"] == {
        "lines": ["Stop now!", "Go later to the"],
        "replaces": 1,
    }


def test_an_unpaired_anchor_never_carries_a_below_class():
    """The upper line closes its sentence, so no pairing puts the lower line in play."""
    (classes,) = withheld("Stop now! Go later.\nThen more prose follows.\n")
    assert not [name for name in classes if name.startswith("below_")]


def test_a_suppressed_wrap_yields_no_below_class_where_the_same_pair_would():
    """The user blessed the break, so the lower line leaves the repair."""
    unsuppressed = "Stop now! Go later to the\nplace with `code` in it.\n"
    assert withheld(unsuppressed) == [("below_protected_span",)]
    suppressed = "<!-- semlf-ignore-next wrap -->\n" + unsuppressed
    assert withheld(suppressed) == [()]


def test_a_crlf_pair_reaches_below_terminator_through_the_record():
    """The raw line never carries its terminator, so the record's own field decides."""
    assert withheld("Stop now! Go later to the\r\nplace we talked about.\r\n") == [
        ("below_terminator",)
    ]


def test_a_bare_cr_pair_reaches_below_terminator_through_the_record():
    assert withheld("Stop now! Go later to the\rplace we talked about.\r") == [
        ("below_terminator",)
    ]


def test_a_lower_line_with_its_own_boundary_still_reports_independently():
    """`below_boundary` withholds the anchor's repair without eating the lower finding."""
    text = "Stop now! Go later to the\nplace stands empty here! Then we left town.\n"
    assert withheld(text) == [("below_boundary",), ("anchor_open",)]
    kinds = [(d["line"], d["kind"]) for d in diags(text)]
    assert (1, "fused") in kinds and (2, "fused") in kinds


def test_below_prose_not_unique_excludes_the_prefix_and_tail_classes():
    """The same exclusivity the anchor's own classes keep."""
    anchor = only("Stop now! Go later to the\n")
    below = check_linefeeds._judged_record(
        "", [0, 0], 1, "place here. X place here. X", "place here. X", "", None, 0
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(anchor["prose"])
    classes = check_linefeeds._fused_withholding(anchor, match, below)
    assert "below_prose_not_unique" in classes
    assert not [
        name for name in classes if name.startswith(("below_prefix_", "below_tail_"))
    ]


def test_a_below_tail_is_judged_by_the_same_whitelist_as_the_anchor():
    """Constructed, because no extractor today leaves a bad tail behind a good leader."""
    anchor = only("Stop now! Go later to the\n")
    below = check_linefeeds._judged_record(
        "",
        [0, 0],
        1,
        "place we talked about. */",
        "place we talked about.",
        "",
        None,
        0,
    )
    (match,) = check_linefeeds.FUSED_RE.finditer(anchor["prose"])
    assert "below_tail_rejected" in check_linefeeds._fused_withholding(
        anchor, match, below
    )


def test_the_wrap_finder_and_the_suggestion_share_one_pairing_predicate():
    """One definition of "the sentence continues", consulted by both consumers.

    The pairing cases the wrap finder decides are exactly the cases the below classes appear in,
    so the two cannot drift.
    """
    paired = "Stop now! Go later to the\nplace with `code` in it.\n"
    unpaired = "Stop now! Go later here.\nThen more prose follows.\n"
    for text, expect in ((paired, True), (unpaired, False)):
        wraps = [d for d in diags(text) if d["kind"] == "wrap"]
        below_classes = [
            name
            for classes in withheld(text)
            for name in classes
            if name.startswith("below_")
        ]
        assert bool(wraps) is expect
        assert bool(below_classes) is expect


# One case per class.
# Deleting a class from the list then leaves a named test red,
# rather than quietly shrinking what the tuple can say.
# The two constructed cases are the two no extractor path reaches.
CLASS_CASES = {
    "many_boundaries": ("Go now? Come here! Stay put.\n", "doc.md"),
    "protected_span": ("Run it now! Then read `the file` again.\n", "doc.md"),
    "gap_multiple_spaces": ("Stop now!  Go later.\n", "doc.md"),
    "gap_tab": ("Stop now!\tGo later.\n", "doc.md"),
    "gap_other_whitespace": ("Stop now!\u00a0Go later.\n", "doc.md"),
    "terminator_period": ("One sentence here. Another sentence follows.\n", "doc.md"),
    "closing_delimiter": ('He said "stop!" Then he left again.\n', "doc.md"),
    "prefix_list_marker": ("- Stop now! Go later.\n", "doc.md"),
    "prefix_other": ("/* Stop now! Go later. */\n", "x.c"),
    "tail_rejected": ("/* Stop now! Go later. */\n", "x.c"),
    "carrier_stripped": (
        "Stop now! Go later. <!-- semlf-ignore wrap -->\n",
        "doc.md",
    ),
}

CONSTRUCTED_CASES = {
    "carriage_return": ("Stop now!\rGo later.", "Stop now! Go later."),
    "prose_not_unique": ("Go now! X Go now! X", "Go now! X"),
}

# The below classes an extractor path reaches, as (text, path) through `diagnose`.
BELOW_CLASS_CASES = {
    "below_terminator": (
        "Stop now! Go later to the\r\nplace we talked about.\r\n",
        "doc.md",
    ),
    "below_boundary": (
        "Stop now! Go later to the\nplace stands empty here! Then we left town.\n",
        "doc.md",
    ),
    "below_open": (
        "Stop now! Go later to the\nplace we talked about and\n",
        "doc.md",
    ),
    "below_protected_span": (
        "Stop now! Go later to the\nplace with `code` in it.\n",
        "doc.md",
    ),
    "below_prefix_mismatch": (
        "Stop now! Go later to the\n  place we talked about.\n",
        "doc.md",
    ),
    "below_carrier_stripped": (
        "Stop now! Go later to the\nplace we talked about. <!-- semlf-ignore long -->\n",
        "doc.md",
    ),
}

# The anchor-side condition the calibration dry-run earned:
# a lowercase opening word says the split's first line continues something above,
# and the rule is rejoin before you split.
ANCHOR_OPEN_CASE = ("then acks! A call follows here.\n", "doc.md")

# The two below classes no extractor path reaches, tested by construction above.
BELOW_CONSTRUCTED = {
    "below_prose_not_unique",
    "below_tail_rejected",
}


def test_a_mid_sentence_anchor_is_its_own_class():
    (classes,) = withheld(ANCHOR_OPEN_CASE[0])
    assert classes == ("anchor_open",)
    (d,) = diags(ANCHOR_OPEN_CASE[0])
    assert "suggestion" not in d


def test_a_sentence_initial_anchor_carries_no_anchor_open():
    (classes,) = withheld("Stop now! Go later.\n")
    assert "anchor_open" not in classes


def test_an_unpaired_anchor_whose_ending_no_line_may_end_on_withholds():
    """The detector cannot pair a continuation opening with a capital,
    and splitting would strand the open fragment ahead of it.
    """
    text = "Stop now! Go later to the\nI mean the other place entirely.\n"
    (classes,) = [c for c in withheld(text) if c is not None][:1]
    assert classes == ("anchor_unclosed",)
    fused = [d for d in diags(text) if d["kind"] == "fused"]
    assert all("suggestion" not in d for d in fused)


def test_a_comma_ending_is_a_place_a_line_may_end():
    """Sembr's own break points stay suggestible: line2 may end at a comma."""
    (classes,) = withheld("Stop now! Go later to the store,\nand buy the rest there.\n")
    assert "anchor_unclosed" not in classes


def test_a_suppressed_wrap_blesses_the_open_ending():
    """The directive targets exactly this ending, so the one-line fallback stands."""
    text = (
        "<!-- semlf-ignore-next wrap -->\n"
        "Stop now! Go later to the\nplace we talked about.\n"
    )
    (d,) = [x for x in diags(text) if x["kind"] == "fused"]
    assert d["suggestion"]["replaces"] == 1


@pytest.mark.parametrize("name", sorted(BELOW_CLASS_CASES))
def test_each_below_class_is_produced_by_a_case_that_names_it(name):
    text, path = BELOW_CLASS_CASES[name]
    assert any(name in classes for classes in withheld(text, path))


@pytest.mark.parametrize("name", sorted(CLASS_CASES))
def test_each_class_is_produced_by_a_case_that_names_it(name):
    text, path = CLASS_CASES[name]
    assert any(name in classes for classes in withheld(text, path))


@pytest.mark.parametrize("name", sorted(CONSTRUCTED_CASES))
def test_each_constructed_class_is_produced_by_its_case(name):
    raw, prose = CONSTRUCTED_CASES[name]
    record = check_linefeeds._judged_record("", [0, 0], 1, raw, prose, "", None, 0)
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    assert name in check_linefeeds._fused_withholding(record, match)


def test_every_declared_class_has_a_case():
    """A class nobody exercises is a stratum nobody can draw."""
    covered = (
        set(CLASS_CASES)
        | set(CONSTRUCTED_CASES)
        | set(BELOW_CLASS_CASES)
        | BELOW_CONSTRUCTED
        | {"anchor_open", "anchor_unclosed"}
    )
    assert covered == set(check_linefeeds.WITHHOLDING_CLASSES)
    assert len(set(check_linefeeds.WITHHOLDING_CLASSES)) == len(
        check_linefeeds.WITHHOLDING_CLASSES
    )


def test_classes_report_in_declaration_order():
    order = check_linefeeds.WITHHOLDING_CLASSES
    for classes in withheld("Go now?  Come `here`! Stay put.\n"):
        positions = [order.index(name) for name in classes]
        assert positions == sorted(positions)


# --- the admitted-class parameter -----------------------------------------


def test_the_candidate_admits_a_clean_period_boundary():
    record = only("One sentence here. Another sentence follows.\n")
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    assert check_linefeeds._fused_suggestion(record, match) is None
    assert check_linefeeds._fused_suggestion(
        record, match, admitted=check_linefeeds.CANDIDATE_ADMITTED
    ) == {"lines": ["One sentence here.", "Another sentence follows."], "replaces": 1}


def test_the_candidate_absorbs_a_paired_period_window():
    records = walked(
        "One sentence stops here. Another goes to the\nplace we talked about.\n"
    )
    anchor, below = records
    assert check_linefeeds._wrap_paired(anchor, below)
    (match,) = check_linefeeds.FUSED_RE.finditer(anchor["prose"])
    assert check_linefeeds._fused_suggestion(anchor, match, below) is None
    assert check_linefeeds._fused_suggestion(
        anchor, match, below, admitted=check_linefeeds.CANDIDATE_ADMITTED
    ) == {
        "lines": [
            "One sentence stops here.",
            "Another goes to the place we talked about.",
        ],
        "replaces": 2,
    }


def test_activation_needs_every_other_class_absent():
    """The activation rule in code form: a second class refuses both constants."""
    record = only("One `code` sentence ends here. Another follows.\n")
    (match,) = check_linefeeds.FUSED_RE.finditer(record["prose"])
    for admitted in (check_linefeeds.ADMITTED, check_linefeeds.CANDIDATE_ADMITTED):
        assert (
            check_linefeeds._fused_suggestion(record, match, admitted=admitted) is None
        )


def test_the_shipped_surface_passes_the_shipped_constant():
    """`diagnose` hands `_fused_suggestion` exactly `ADMITTED`, nothing wider."""
    (d,) = diags("One sentence here. Another sentence follows.\n")
    assert d["kind"] == "fused"
    assert "suggestion" not in d
