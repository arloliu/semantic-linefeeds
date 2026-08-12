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
