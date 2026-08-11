"""Enumerating the units a labeler will judge.

A candidate is neither a file nor a paragraph.
`wrap` is a property of an adjacent line boundary inside one paragraph, attributed to the upper line,
and `fused` is a property of a single line,
so a boundary carries both lines and both kinds get labeled from one reading.

Candidates come from the checker's own extractor.
That bounds every reported rate to the prose the extractor yields,
which is a cost the manifest states rather than a claim it avoids.
"""

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from corpus_harness import (  # noqa: E402
    COVARIATES, Boundary, ProseLine, band_of, boundaries, covariates, draw,
    draw_corpus, replay_kinds,
    labeling_batches)


def unit(upper_raw, lower_raw, path="x.go", strip="// ", rest=()):
    """A boundary built straight from two lines, for covariates that need no file."""
    def line(n, raw):
        return ProseLine(n, raw, raw.strip()[len(strip.strip()):].strip() if strip else raw.strip())
    paragraph = [line(1, upper_raw), line(2, lower_raw)]
    paragraph += [line(3 + i, extra) for i, extra in enumerate(rest)]
    return Boundary(path, paragraph[0], paragraph[1], paragraph)

GO = ("package x\n"
      "\n"
      "// One sentence here.\n"
      "// Another follows it.\n"
      "//\n"
      "// After the break.\n"
      "func f() {}\n")

MARKDOWN = ("# Title\n"
            "\n"
            "One sentence here.\n"
            "Another follows it.\n"
            "\n"
            "- a list item that runs on\n"
            "  and continues here\n")


def positions(units):
    return [(u.upper.lineno, u.lower.lineno) for u in units]


def test_adjacent_prose_lines_become_one_boundary():
    """Two lines in one paragraph are one unit, attributed to the upper line."""
    assert positions(boundaries(GO, "x.go")) == [(3, 4)]


def test_a_paragraph_break_joins_nothing_across_it():
    """The detector cannot fire across a break, so no unit may straddle one.

    A unit enumerated there would enter the denominator as a violation nobody could ever detect.
    """
    assert (6, 7) not in positions(boundaries(GO, "x.go"))


def test_a_boundary_carries_the_text_of_both_its_lines():
    """A labeler judges the prose, and the raw line is what carries the wrapping column."""
    unit = boundaries(GO, "x.go")[0]
    assert unit.upper.prose == "One sentence here."
    assert unit.lower.prose == "Another follows it."
    assert unit.upper.raw == "// One sentence here."


def test_a_list_item_and_its_continuation_are_one_paragraph_today():
    """Recorded because it is the extractor's current behavior, not because it is right.

    The list-item break is a repair this release makes,
    and a unit enumerated now must be re-enumerated after it lands.
    """
    assert positions(boundaries(MARKDOWN, "x.md")) == [(3, 4), (6, 7)]


LICENSED = ("// Copyright 2018-2022 The NATS Authors\n"
            "// Licensed under the Apache License, Version 2.0 (the \"License\");\n"
            "// you may not use this file except in compliance with the License.\n"
            "\n"
            "package x\n"
            "\n"
            "// One sentence here.\n"
            "// Another follows it.\n"
            "func f() {}\n")


def test_a_licence_header_yields_no_units():
    """The checker cuts the leading licence region, and the sampler has to cut the same one.

    A licence header is a never-break class,
    so a unit drawn from one is a violation the detector is structurally unable to report,
    and it would sit in the denominator forever.
    """
    assert positions(boundaries(LICENSED, "x.go")) == [(7, 8)]


def test_a_file_the_extractor_does_not_target_yields_no_units():
    """Recall is reported over the prose the extractor yields, and no more."""
    assert boundaries("hello there\nand more\n", "notes.txt") == []


def test_a_boundary_knows_the_paragraph_it_sits_in():
    """Paragraph line count is one of the nine recorded dimensions."""
    found = boundaries(GO, "x.go")[0]
    assert [line.lineno for line in found.paragraph] == [3, 4]


def test_all_nine_dimensions_come_back_for_every_unit():
    """All nine are recorded whether or not they drove a quota.

    Reporting is per-dimension marginals,
    and a reader recomputes any cross they want only from a complete vector.
    """
    assert set(covariates(boundaries(GO, "x.go")[0])) == set(COVARIATES)


def test_the_language_is_recorded_as_a_name():
    """Every covariate has to survive the trip into the manifest.

    The extractor's language lookup hands back its whole specification,
    and storing that would put compiled patterns where a stratum label belongs.
    """
    assert covariates(boundaries(GO, "x.go")[0])["language"] == "go"
    assert covariates(boundaries(MARKDOWN, "x.md")[0])["language"] == "markdown"


def test_the_end_column_is_where_the_raw_line_actually_ends():
    """The wrapping column is a property of the raw line, not of the extracted prose."""
    assert covariates(unit("// One sentence here.", "// Another."))["raw_end_column"] == 21


def test_indentation_is_measured_in_columns_with_tabs_expanded():
    """A tab-indented comment sits where it is displayed, not where its bytes fall."""
    assert covariates(unit("\t// Indented.", "// Next."))["indentation_depth"] == 8


def test_prose_width_is_the_widest_raw_line_in_the_paragraph():
    """One line says where it ended; the paragraph says where the author was wrapping."""
    found = unit("// Short.", "// Also short.", rest=("// A rather longer line than those.",))
    assert covariates(found)["prose_width"] == 35


def test_trailing_inline_markup_is_read_off_the_upper_line():
    """Markup after the terminal punctuation is the case the detector cannot see past."""
    assert covariates(unit("// Ends in emphasis.*", "// Next."))["trailing_inline_markup"] is True
    assert covariates(unit("// Ends plainly.", "// Next."))["trailing_inline_markup"] is False


def test_list_item_adjacency_is_read_off_the_lower_line():
    """One item measured against the next is a different mistake from a wrapped clause."""
    found = unit("- first item", "- second item", path="x.md", strip="")
    assert covariates(found)["list_item_adjacency"] is True


def test_markdown_nesting_counts_the_markers_in_front_of_the_prose():
    """Deeply nested prose never reaches the extractor, so the shallow depths are what vary."""
    found = unit("> - a quoted list item", "> - another one", path="x.md", strip="")
    assert covariates(found)["markdown_nesting"] == 2


def test_eligible_anchors_are_counted_without_consulting_any_word_list():
    """The one dimension that is recorded and reported but never drives a quota.

    Its definition tracks half of the detector's own condition,
    so it is counted geometrically here rather than imported,
    and selecting on it would be a diluted form of sampling from findings.
    """
    wide = "a" * 15 + " " + "b" * 15 + " " + "c" * 15
    narrow = "a" * 14 + " " + "b" * 14
    assert covariates(unit("// " + wide, "// next."))["eligible_anchor_count"] == 2
    assert covariates(unit("// " + narrow, "// next."))["eligible_anchor_count"] == 0


def replayable(window, upper_index, path):
    return {"path": path, "raw_window": window, "upper_index": upper_index}


def test_a_stored_unit_reproduces_the_verdict_it_was_frozen_with():
    """The per-unit gate has to run offline, from the manifest and nothing else.

    A status nobody can recheck offline is a claim about the detector, not a test of it.
    """
    unit = replayable(["// The layout of structs on 64-bit systems",
                       "// will not change."], 0, "x.go")
    assert replay_kinds(unit) == {"wrap"}


def test_a_stored_unit_can_come_back_clean():
    """The gate needs both answers, or every accepted miss would read as detected."""
    unit = replayable(["// One sentence here.", "// Another follows it."], 0, "x.go")
    assert replay_kinds(unit) == set()


def test_a_stored_markdown_unit_replays_as_markdown():
    """Extraction differs by language, so the replay has to carry the language with it."""
    unit = replayable(["The layout of structs on 64-bit systems",
                       "will not change."], 0, "x.md")
    assert replay_kinds(unit) == {"wrap"}


def test_a_stored_comment_block_is_not_mistaken_for_a_licence_header():
    """A window of comments with nothing before it looks exactly like a file's licence region.

    The checker cuts that region, so a replay without a guard would report nothing at all
    and quietly turn every detected unit into an accepted miss.
    """
    unit = replayable(["// Copyright is not what this is about, and the layout of structs",
                       "// will not change."], 0, "x.go")
    assert replay_kinds(unit) == {"wrap"}


BANDS = (64, 71, 78, 85)


def candidate(n, column):
    """A stand-in unit that only has to carry an end column and an identity."""
    return {"id": f"u-{n:04d}", "raw_end_column": column}


def population():
    return [candidate(n, column)
            for n, column in enumerate([60] * 5 + [68] * 30 + [75] * 30 + [82] * 30 + [92] * 2)]


def test_a_level_is_the_band_a_value_falls_in():
    """Levels are fixed before the draw, so no band can be redrawn around a result."""
    assert band_of(60, BANDS) == "..64"
    assert band_of(64, BANDS) == "..64"
    assert band_of(65, BANDS) == "65..71"
    assert band_of(92, BANDS) == "86.."


def test_the_same_seed_draws_the_same_sample():
    """A reviewer redraws the sample from the manifest rather than trusting the run."""
    first = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-1")
    again = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-1")
    assert [u["id"] for u in first] == [u["id"] for u in again]


def test_a_different_seed_draws_a_different_sample():
    """A seed that changed nothing would make the recorded seed decorative."""
    first = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-1")
    other = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-2")
    assert [u["id"] for u in first] != [u["id"] for u in other]


def test_every_level_contributes_its_quota():
    """Quota sampling is what keeps a structurally rare level from vanishing."""
    sample = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-1")
    counts = collections.Counter(band_of(u["raw_end_column"], BANDS) for u in sample)
    assert counts["65..71"] == counts["72..78"] == counts["79..85"] == 4


def test_a_level_thinner_than_its_quota_contributes_all_it_has():
    """Taking fewer is honest; the report says x/n and prints no percentage."""
    sample = draw(population(), "raw_end_column", BANDS, per_level=4, seed="pilot-1")
    counts = collections.Counter(band_of(u["raw_end_column"], BANDS) for u in sample)
    assert counts["86.."] == 2


def rare(n, nesting, markup):
    return {"id": f"r-{n:04d}",
            "covariates": {"markdown_nesting": nesting, "trailing_inline_markup": markup}}


def rare_population():
    """Common units in bulk, and two levels that barely exist, as the real population looks."""
    out = [rare(n, 0, False) for n in range(200)]
    out += [rare(200 + n, 1, False) for n in range(30)]
    out += [rare(300 + n, 2, False) for n in range(3)]
    out += [rare(400 + n, 0, True) for n in range(20)]
    return out


QUOTAS = {"markdown_nesting": (None, 10), "trailing_inline_markup": (None, 10)}


def test_a_rare_level_is_topped_up_to_its_quota():
    """Quotas exist because a random draw leaves the structurally rare levels empty.

    Nesting depth one is 12% of this population, so a base of twenty would carry two or three.
    """
    drawn = draw_corpus(rare_population(), 20, QUOTAS, "corpus-1")
    counts = collections.Counter(u["covariates"]["markdown_nesting"] for u in drawn)
    assert counts[1] >= 10
    assert counts[0] >= 10


def test_a_level_thinner_than_its_quota_contributes_everything_it_has():
    """Taking fewer is honest, and the per-unit gate still guards what was taken."""
    drawn = draw_corpus(rare_population(), 20, QUOTAS, "corpus-1")
    counts = collections.Counter(u["covariates"]["markdown_nesting"] for u in drawn)
    assert counts[2] == 3


def test_the_base_sample_is_kept_whole():
    """The base is what spreads the dimensions no quota touches, so topping up may not replace it."""
    base = draw_corpus(rare_population(), 20, {}, "corpus-1")
    topped = {u["id"] for u in draw_corpus(rare_population(), 20, QUOTAS, "corpus-1")}
    assert {u["id"] for u in base} <= topped


def test_the_same_seed_draws_the_same_corpus():
    """A reviewer redraws the corpus rather than trusting the run that made it."""
    first = draw_corpus(rare_population(), 20, QUOTAS, "corpus-1")
    again = draw_corpus(rare_population(), 20, QUOTAS, "corpus-1")
    assert [u["id"] for u in first] == [u["id"] for u in again]


def test_each_labeler_sees_its_own_order():
    """Order is randomized per labeler so fatigue and drift do not line up across passes."""
    sample = draw(population(), "raw_end_column", BANDS, per_level=8, seed="pilot-1")
    mine = [u["id"] for batch in labeling_batches(sample, "claude", size=5) for u in batch]
    theirs = [u["id"] for batch in labeling_batches(sample, "codex", size=5) for u in batch]
    assert sorted(mine) == sorted(theirs)
    assert mine != theirs


def test_batches_are_bounded():
    """A labeler judging a hundred units in one reading drifts within the reading."""
    sample = draw(population(), "raw_end_column", BANDS, per_level=8, seed="pilot-1")
    assert all(len(batch) <= 5 for batch in labeling_batches(sample, "claude", size=5))
