"""The suppression contract of ADR-0010: grammar, carriers, and the diagnose filter."""

from check_linefeeds import (
    DIRECTIVE_KINDS, MALFORMED, parse_directive, prose_lines_markdown,
)


def test_a_bare_name_suppresses_every_kind():
    assert parse_directive("semlf-ignore") == (0, DIRECTIVE_KINDS)


def test_the_next_name_is_one_name_not_a_suffixed_one():
    assert parse_directive("semlf-ignore-next") == (1, DIRECTIVE_KINDS)


def test_kind_arguments_narrow_the_suppression():
    assert parse_directive("semlf-ignore-next fused") == (1, frozenset({"fused"}))
    assert parse_directive("semlf-ignore\tlong wrap") == (0, frozenset({"long", "wrap"}))


def test_a_duplicate_kind_is_idempotent():
    assert parse_directive("semlf-ignore fused fused") == (0, frozenset({"fused"}))


def test_case_variants_and_near_names_are_ordinary_text():
    assert parse_directive("SEMLF-IGNORE") is None
    assert parse_directive("semlf-ignored") is None
    assert parse_directive("") is None
    assert parse_directive("just prose") is None


def test_any_unknown_argument_makes_the_directive_malformed():
    assert parse_directive("semlf-ignore fussed") is MALFORMED
    assert parse_directive("semlf-ignore -->") is MALFORMED
    assert parse_directive("semlf-ignore semlf-ignore-next") is MALFORMED


from check_linefeeds import lang_for_path, trailing_carrier

PY = lang_for_path("x.py")


def test_a_markdown_trailing_comment_is_a_carrier():
    got = trailing_carrier("A long judged line. <!-- semlf-ignore long -->", True, None)
    assert got == ((0, frozenset({"long"})), "A long judged line.",
                   "<!-- semlf-ignore long -->")


def test_only_the_final_html_comment_can_be_the_carrier():
    got = trailing_carrier("prose <!-- note --> more <!-- semlf-ignore -->", True, None)
    assert got == ((0, DIRECTIVE_KINDS), "prose <!-- note --> more",
                   "<!-- semlf-ignore -->")


def test_text_after_the_closer_disqualifies_the_comment():
    assert trailing_carrier("prose <!-- semlf-ignore --> tail", True, None) is None
    assert trailing_carrier("prose <!-- semlf-ignore --> <!-- note -->", True, None) is None


def test_a_line_comment_trailing_form_repeats_the_marker():
    got = trailing_carrier("# a judged line.  # semlf-ignore", False, PY)
    assert got == ((0, DIRECTIVE_KINDS), "# a judged line.", "# semlf-ignore")


def test_a_marker_inside_the_prose_does_not_confuse_the_tail():
    got = trailing_carrier("# see issue #42  # semlf-ignore", False, PY)
    assert got == ((0, DIRECTIVE_KINDS), "# see issue #42", "# semlf-ignore")


def test_a_lone_leading_marker_is_not_a_trailing_carrier():
    assert trailing_carrier("# semlf-ignore", False, PY) is None


def test_a_malformed_tail_is_inert_and_strips_nothing():
    assert trailing_carrier("# tail says # semlf-ignore x", False, PY) is None
    assert trailing_carrier("prose <!-- semlf-ignore fussed -->", True, None) is None


def test_a_bare_token_with_no_leader_is_not_a_carrier():
    assert trailing_carrier("no comment here semlf-ignore", True, None) is None


def first_row(md):
    return list(prose_lines_markdown(md))[0]


def test_a_directive_only_html_comment_is_yielded_as_prose():
    assert first_row("<!-- semlf-ignore-next fused -->\nprose\n") == \
        (1, "<!-- semlf-ignore-next fused -->", "semlf-ignore-next fused")


def test_a_blockquoted_directive_comment_is_yielded_as_prose():
    assert first_row("> <!-- semlf-ignore -->\n")[2] == "semlf-ignore"


def test_a_directive_comment_inside_a_fence_stays_excluded():
    rows = list(prose_lines_markdown("```\n<!-- semlf-ignore-next -->\n```\n"))
    assert rows[1] == (2, None, None)


def test_an_indented_directive_comment_stays_excluded():
    assert first_row("    <!-- semlf-ignore-next -->\n") == (1, None, None)


def test_a_malformed_directive_comment_stays_markup():
    assert first_row("<!-- semlf-ignore fussed -->\n") == (1, None, None)


def test_an_ordinary_html_comment_stays_markup():
    assert first_row("<!-- an ordinary comment -->\n") == (1, None, None)


def test_the_sampler_drops_a_standalone_directive_like_the_checker():
    # The sampling frame must enumerate the prose the detector sees;
    # a directive line the checker treats as a boundary must not be a sampled prose line.
    # The Markdown case uses the new HTML-comment candidate deliberately:
    # once the extractor yields it as prose, an unfixed sampler would join all three lines into one sampled run —
    # this test is the red gate for the `paragraphs` change.
    from corpus_harness import paragraphs
    md = "upper prose line one\n<!-- semlf-ignore-next -->\nlower prose line two\n"
    assert paragraphs(md, "doc.md") == []
    py = "# upper prose line one\n# semlf-ignore-next\n# lower prose line two\n"
    assert paragraphs(py, "x.py") == []
