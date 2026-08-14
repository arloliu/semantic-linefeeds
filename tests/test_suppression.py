"""The suppression contract of ADR-0010: grammar, carriers, and the diagnose filter."""

from check_linefeeds import (
    DIRECTIVE_KINDS,
    MALFORMED,
    parse_directive,
    prose_lines_markdown,
)


def test_a_bare_name_suppresses_every_kind():
    assert parse_directive("semlf-ignore") == (0, DIRECTIVE_KINDS)


def test_the_next_name_is_one_name_not_a_suffixed_one():
    assert parse_directive("semlf-ignore-next") == (1, DIRECTIVE_KINDS)


def test_kind_arguments_narrow_the_suppression():
    assert parse_directive("semlf-ignore-next fused") == (1, frozenset({"fused"}))
    assert parse_directive("semlf-ignore\tlong wrap") == (
        0,
        frozenset({"long", "wrap"}),
    )


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
    assert got == (
        (0, frozenset({"long"})),
        "A long judged line.",
        "<!-- semlf-ignore long -->",
    )


def test_only_the_final_html_comment_can_be_the_carrier():
    got = trailing_carrier("prose <!-- note --> more <!-- semlf-ignore -->", True, None)
    assert got == (
        (0, DIRECTIVE_KINDS),
        "prose <!-- note --> more",
        "<!-- semlf-ignore -->",
    )


def test_text_after_the_closer_disqualifies_the_comment():
    assert trailing_carrier("prose <!-- semlf-ignore --> tail", True, None) is None
    assert (
        trailing_carrier("prose <!-- semlf-ignore --> <!-- note -->", True, None)
        is None
    )


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
    assert first_row("<!-- semlf-ignore-next fused -->\nprose\n") == (
        1,
        "<!-- semlf-ignore-next fused -->",
        "semlf-ignore-next fused",
    )


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


from check_linefeeds import diagnose


def kinds_at(text, path="doc.md", spans=None):
    return [(d["line"], d["kind"]) for d in diagnose(text, path, spans=spans)]


FUSED = "One sentence here. Another sentence follows.\n"
FUSED_WRAP_UPPER = "One sentence here. Another sentence continues"
LOWER = "onto the lower line.\n"


def test_the_baseline_texts_produce_the_expected_kinds():
    # A characterization pin, green before and after this task.
    assert kinds_at(FUSED) == [(1, "fused")]
    assert kinds_at(FUSED_WRAP_UPPER + "\n" + LOWER) == [(1, "fused"), (1, "wrap")]


def test_a_trailing_directive_suppresses_its_own_line():
    text = "One sentence here. Another sentence follows. <!-- semlf-ignore fused -->\n"
    assert kinds_at(text) == []


def test_kind_narrowing_leaves_the_other_kind_alone():
    text = FUSED_WRAP_UPPER + " <!-- semlf-ignore fused -->\n" + LOWER
    assert kinds_at(text) == [(1, "wrap")]


def test_a_union_of_two_directives_covers_both_kinds():
    text = (
        "<!-- semlf-ignore-next wrap -->\n"
        + FUSED_WRAP_UPPER
        + " <!-- semlf-ignore fused -->\n"
        + LOWER
    )
    assert kinds_at(text) == []


def test_suppression_also_drops_a_span_owned_finding():
    text = "One sentence here. Another sentence follows. <!-- semlf-ignore fused -->\n"
    whole = [{"start": 0, "end": len(text)}]
    assert kinds_at(FUSED, spans=[{"start": 0, "end": len(FUSED)}]) == [(1, "fused")]
    assert kinds_at(text, spans=whole) == []


def test_a_standalone_next_directive_suppresses_the_following_line():
    assert kinds_at("<!-- semlf-ignore-next -->\n" + FUSED) == []
    assert kinds_at("# semlf-ignore-next\n# " + FUSED[:-1] + "\n", "x.py") == []


def test_the_next_directive_never_skips_a_blank_line():
    # A characterization pin for the no-skip rule.
    assert kinds_at("<!-- semlf-ignore-next -->\n\n" + FUSED) == [(3, "fused")]


def test_a_malformed_trailing_directive_suppresses_nothing():
    # Green today; it pins that a typo cannot half-work.
    text = "One sentence here. Another sentence follows. <!-- semlf-ignore fussed -->\n"
    assert kinds_at(text) == [(1, "fused")]


def test_a_malformed_standalone_line_stays_visible_prose():
    # ADR-0010: inert means the findings stay visible, so the line stays prose.
    text = "semlf-ignore fussed. Another sentence follows.\n"
    assert kinds_at(text) == [(1, "fused")]


def test_a_malformed_standalone_line_still_forms_a_wrap():
    text = FUSED_WRAP_UPPER + "\nsemlf-ignore fussed here.\n"
    assert kinds_at(text) == [(1, "fused"), (1, "wrap")]


def test_a_repeated_marker_carrier_with_marker_leading_prose():
    # The carrier suffix is stripped from raw and prose alike,
    # so the leftover directive text can never fabricate a wrap.
    code = "// // semlf-ignore-next fused\n// lower prose continues here.\n"
    assert kinds_at(code, "x.go") == []


def test_a_bare_directive_line_in_a_docstring_suppresses_the_next_line():
    py = (
        'def f():\n    """\n    semlf-ignore-next\n'
        "    One sentence here. Another sentence follows.\n"
        '    """\n'
    )
    assert kinds_at(py, "x.py") == []


def test_a_standalone_directive_line_dissolves_a_wrap_it_stands_inside():
    code = (
        "# a line that ends mid-clause because it was\n"
        "# semlf-ignore\n"
        "# wrapped at a column.\n"
    )
    assert kinds_at(code, "x.py") == []


def test_a_directive_as_the_last_fence_line_cannot_reach_past_the_fence():
    # A characterization pin: fenced lines are excluded before recognition.
    text = "```\n<!-- semlf-ignore-next -->\n```\n" + FUSED
    assert kinds_at(text) == [(4, "fused")]


def test_a_bare_directive_inside_a_licence_paragraph_is_inert():
    md = (
        "opening prose stands alone\n\n"
        "Copyright (c) 2026 Example\n"
        "semlf-ignore-next fused\n"
        "One sentence here. Another sentence follows.\n"
        "\n"
        "One sentence here. Another sentence follows.\n"
    )
    assert kinds_at(md) == [(7, "fused")]


def test_an_html_directive_inside_a_licence_paragraph_is_inert():
    # The directive-only comment now travels the stream as prose,
    # so the licence cut silences it with its paragraph and diagnose
    # never sees a carrier — the ordering ADR-0010 requires.
    md = (
        "opening prose stands alone\n\n"
        "Copyright (c) 2026 Example\n"
        "<!-- semlf-ignore-next fused -->\n"
        "One sentence here. Another sentence follows.\n"
        "\n"
        "One sentence here. Another sentence follows.\n"
    )
    assert kinds_at(md) == [(7, "fused")]


def test_a_prose_line_that_is_exactly_a_directive_is_the_accepted_capture():
    assert kinds_at("some prose stands here\nsemlf-ignore-next\n" + FUSED) == []


def test_trailing_carriers_survive_every_prose_transform():
    cases = [
        (
            "> One sentence here. Another sentence follows. <!-- semlf-ignore fused -->\n",
            "doc.md",
        ),
        (
            "- One sentence here. Another sentence follows. <!-- semlf-ignore fused -->\n",
            "doc.md",
        ),
        (
            "/*\n * One sentence here. Another sentence follows.  // semlf-ignore fused\n */\n",
            "x.c",
        ),
        (
            'def f():\n    """\n    One sentence here. Another sentence follows.  # semlf-ignore fused\n    """\n',
            "x.py",
        ),
    ]
    for text, path in cases:
        assert kinds_at(text, path) == [], (text, path)


def test_long_is_suppressed_by_its_kind():
    long_line = (
        "This clause runs on and on well past the configured advisory "
        "threshold of one hundred and twenty characters, and the tail "
        "keeps going. <!-- semlf-ignore long -->\n"
    )
    assert kinds_at(long_line) == []


def test_long_measures_the_judged_prefix_not_the_carrier():
    base = (
        "This clause stops just short of the configured advisory threshold "
        "of one hundred and twenty characters, and no more."
    )
    raw = base + " <!-- semlf-ignore fused -->"
    assert len(base) <= 120 < len(raw)
    assert kinds_at(raw + "\n") == []


def test_a_standalone_html_directive_amid_prose_is_a_boundary():
    # Task 3 made this line prose; until this task recognizes it, a wrap
    # is manufactured across it.  Recognition makes it a boundary again.
    md = (
        "This is the first sentence of a paragraph\n"
        "<!-- semlf-ignore-next wrap -->\n"
        "and this clause continues it across the break.\n"
    )
    assert kinds_at(md) == []


# ADR-0010 permits only ASCII space/tab as directive WS.
# That includes the whitespace between a comment leader and the directive,
# and the whitespace at the raw line's ends.
# The extractor's own Unicode-aware .strip() calls fold wider whitespace
# (NBSP, em space, ...) away before parse_directive ever sees it.
# Left unguarded, that would let text outside the grammar authorize a suppression.


def test_nbsp_after_a_comment_leader_does_not_authorize_suppression():
    text = "# semlf-ignore-next fused\n# " + FUSED
    assert kinds_at(text, "x.py") == [(2, "fused")]


def test_em_space_padded_markdown_standalone_does_not_authorize_suppression():
    text = " <!--semlf-ignore-next fused--> \n" + FUSED
    assert kinds_at(text) == [(2, "fused")]


def test_the_ascii_standalone_forms_still_suppress():
    # The legit forms this guard must leave alone.
    # See also test_a_bare_directive_line_in_a_docstring_suppresses_the_next_line
    # and test_a_standalone_html_directive_amid_prose_is_a_boundary above.
    assert kinds_at("# semlf-ignore-next fused\n# " + FUSED, "x.py") == []
    assert kinds_at("<!--semlf-ignore-next fused-->\n" + FUSED) == []


def test_a_rejected_html_carrier_does_not_fabricate_wraps_with_neighbors():
    # The tests above use FUSED as a neighbor,
    # whose capital "One" never trips wrap detection either way,
    # so they cannot see a carrier leaking into the prose stream.
    # A rejected directive HTML comment must drop as markup,
    # exactly like a malformed one: a paragraph boundary.
    # It must not leak into the prose stream as visible text
    # and form a wrap with its real, lowercase-starting neighbors.
    upper = "a line that ends mid-clause because it was\n"
    lower = "wrapped at a column.\n"

    def wrapped(pad):
        return upper + pad + "<!-- semlf-ignore-next fused -->" + pad + "\n" + lower

    def leading_only(pad):
        return upper + pad + "<!-- semlf-ignore-next fused -->\n" + lower

    def trailing_only(pad):
        return upper + "<!-- semlf-ignore-next fused -->" + pad + "\n" + lower

    for pad in (" ", "\xa0"):  # em space, NBSP
        assert kinds_at(wrapped(pad)) == []
        assert kinds_at(leading_only(pad)) == []
        assert kinds_at(trailing_only(pad)) == []


def test_a_rejected_html_carrier_still_does_not_suppress_its_target():
    # The non-suppression contract, re-checked against lowercase neighbors.
    # The carrier is now a paragraph boundary rather than leaked prose,
    # and the planted finding on its "-next" target must still survive untouched.
    md = " <!--semlf-ignore-next fused--> \n" + FUSED
    assert kinds_at(md) == [(2, "fused")]


def test_a_directive_after_a_licence_paragraph_still_suppresses():
    # Both cuts run in one file: the licence paragraph is silenced by the
    # licence cut, and the standalone directive in the paragraph after it
    # still reaches recognition and suppresses its own target.
    # "Copyright (c)." followed by "All" would itself read as fused,
    # which is what proves the licence line was actually cut rather than
    # merely clean on its own.
    md = (
        "Copyright (c) 2026 Example. All rights are reserved statically.\n"
        "\n"
        "<!-- semlf-ignore-next fused -->\n" + FUSED
    )
    assert kinds_at(md) == []
