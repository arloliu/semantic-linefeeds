"""tests/test_spans.py — the range model ADR-0005 fixes."""
import pytest

import check_linefeeds


def test_a_boundary_span_normalizes_to_zero_width():
    span = check_linefeeds.normalize_span({"at": 7})
    assert span == {"start": 7, "end": 7, "mapping": "exact"}


def test_a_range_span_keeps_its_mapping():
    span = check_linefeeds.normalize_span({"start": 3, "end": 9, "mapping": "degraded"})
    assert span == {"start": 3, "end": 9, "mapping": "degraded"}


@pytest.mark.parametrize("bad", [
    None,                                        # not a mapping at all
    7,                                           # nor is a number
    {"start": 9, "end": 3},                      # backwards
    {"start": -1, "end": 3},                     # negative offset
    {"at": 4, "start": 4, "end": 9},             # both shapes at once
    {"start": 3},                                # half a range
    {},                                          # neither shape
    {"at": True},                                # a bool is not an offset
    {"start": "3", "end": "9"},                  # strings are not offsets
    {"start": 3, "end": 9, "mapping": "fuzzy"},  # unknown mapping value
    {"start": 3, "end": 9, "size": 6},           # unknown key
])
def test_a_malformed_span_is_rejected(bad):
    with pytest.raises(ValueError):
        check_linefeeds.normalize_span(bad)


@pytest.mark.parametrize("rng,span,expected", [
    ({"start": 0, "end": 5}, {"start": 3, "end": 8}, True),    # overlap
    ({"start": 0, "end": 5}, {"start": 5, "end": 9}, False),   # adjacency is not overlap
    ({"start": 5, "end": 9}, {"start": 0, "end": 5}, False),   # nor from the other side
    ({"start": 0, "end": 5}, {"start": 6, "end": 9}, False),   # gap
    ({"start": 4, "end": 4}, {"start": 0, "end": 9}, True),    # boundary inside a range
    ({"start": 0, "end": 9}, {"start": 4, "end": 4}, True),    # either argument order
    ({"start": 4, "end": 4}, {"start": 4, "end": 9}, True),    # boundary on a range's start
    ({"start": 4, "end": 4}, {"start": 0, "end": 4}, True),    # boundary on a range's end
    ({"start": 4, "end": 4}, {"start": 4, "end": 4}, True),    # same point twice
    ({"start": 4, "end": 4}, {"start": 5, "end": 5}, False),   # distinct points
])
def test_ranges_overlap_strictly_and_boundaries_touch_edges(rng, span, expected):
    assert check_linefeeds.touches(rng, span) is expected


def test_line_offsets_address_every_line():
    text = "ab\ncde\n\nf"
    offsets = check_linefeeds.line_offsets(text)
    assert offsets == [0, 3, 7, 8, 9]


def test_line_offsets_pin_empty_text_and_trailing_newlines():
    assert check_linefeeds.line_offsets("") == [0]
    assert check_linefeeds.line_offsets("ab") == [0, 2]
    assert check_linefeeds.line_offsets("ab\n") == [0, 3]
    assert check_linefeeds.line_offsets("ab\n\n") == [0, 3, 4]


def test_line_offsets_keep_crlf_ordered_and_in_line_content():
    # CRLF handling proper is scheduled for v0.6.
    # Until then the pair stays inside its line's range and the table must stay valid.
    offsets = check_linefeeds.line_offsets("ab\r\ncd\r\n")
    assert offsets == [0, 4, 8]
    assert offsets == sorted(offsets)


def test_line_offsets_partition_exactly_as_splitlines_does():
    # Extractors number lines with str.splitlines.
    # This recognizes bare \r, Unicode separators, CRLF, and other terminators.
    # The table must agree with those line numbers or later indexing fails.
    for text in ("a\rb", "a\u2028b", "a\r\nb\rc\u2028d\n"):
        offsets = check_linefeeds.line_offsets(text)
        assert len(offsets) == len(text.splitlines()) + 1
        assert offsets == sorted(offsets)
        assert offsets[-1] == len(text)

def test_locate_finds_a_unique_needle():
    text = "one line\ntwo words here\n"
    offsets = check_linefeeds.line_offsets(text)
    found = check_linefeeds.locate_in_line(text, offsets, 2, "words")
    assert found == {"start": 13, "end": 18}


def test_locate_refuses_an_ambiguous_needle():
    text = "aa aa\n"
    offsets = check_linefeeds.line_offsets(text)
    assert check_linefeeds.locate_in_line(text, offsets, 1, "aa") is None


def test_locate_refuses_an_absent_needle():
    text = "plain\n"
    offsets = check_linefeeds.line_offsets(text)
    assert check_linefeeds.locate_in_line(text, offsets, 1, "gone") is None


def test_locate_refuses_a_line_number_off_the_table():
    offsets = check_linefeeds.line_offsets("plain\n")
    assert check_linefeeds.locate_in_line("plain\n", offsets, 0, "plain") is None
    assert check_linefeeds.locate_in_line("plain\n", offsets, 2, "plain") is None
