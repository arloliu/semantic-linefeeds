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
