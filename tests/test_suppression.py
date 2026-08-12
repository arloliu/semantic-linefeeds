"""The suppression contract of ADR-0010: grammar, carriers, and the diagnose filter."""

from check_linefeeds import (
    DIRECTIVE_KINDS, MALFORMED, parse_directive,
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
