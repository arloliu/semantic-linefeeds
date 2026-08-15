"""tests/test_frozen_contract.py — v0.4.3's exact tuples and rendered bytes.

Written against the unchanged v0.4.3 core and green from day one.
Any later task that moves one byte of check() output or one byte of format_findings() text turns this file red.
"""

import check_linefeeds

FUSED = "One sentence here. Another sentence follows.\n"
WRAP = (
    "the compiler will assume all functions provide an `ABIInternal`\nimplementation.\n"
)
LONG = (
    "This advisory line keeps going with a possible clause boundary, "
    "and it continues well past the configured limit so the checker "
    "flags it as long today.\n"
)
MIXED = (
    "One sentence here. Another sentence follows, and this fused line also runs "
    "long enough that the advisory logic wants to flag it as well, which makes two kinds\n"
    "on\n"
)

FUSED_MSG = "two sentences on one line — one sentence per line"
WRAP_MSG = (
    "ends mid-clause (column-wrapped?) — "
    "break at sentence or clause boundaries, not at a column"
)
LONG_MSG = (
    "advisory: {n} chars with a possible clause boundary — "
    "scan from ~120 rightward for ';' ':' '—' or an independent-clause "
    "'and/but/so' / 'which/that/where', else backward; "
    "split only at a boundary where both sides stand alone, "
    "else leave the line long"
)


def test_fused_tuple_fields_are_frozen():
    assert check_linefeeds.check(FUSED, "doc.md") == [
        (1, "fused", FUSED_MSG, "One sentence here. Another sentence follows.")
    ]


def test_wrap_tuple_fields_are_frozen():
    assert check_linefeeds.check(WRAP, "doc.md") == [
        (
            1,
            "wrap",
            WRAP_MSG,
            "the compiler will assume all functions provide an `ABIInternal`",
        )
    ]


def test_long_tuple_fields_are_frozen():
    assert check_linefeeds.check(LONG, "doc.md") == [
        (1, "long", LONG_MSG.format(n=150), LONG.rstrip("\n"))
    ]


def test_same_line_findings_keep_fused_long_wrap_order():
    got = check_linefeeds.check(MIXED, "doc.md")
    assert [(line, kind) for line, kind, _, _ in got] == [
        (1, "fused"),
        (1, "long"),
        (1, "wrap"),
    ]


def test_blocking_report_bytes_without_snippet():
    got = check_linefeeds.format_findings(
        check_linefeeds.check(FUSED, "doc.md"), "doc.md", snippet=False
    )
    assert got == (
        "semantic-linefeeds: 1 issue(s) in doc.md:\n"
        "  [fused] line 1: two sentences on one line — one sentence per line\n"
        "         > One sentence here. Another sentence follows.\n"
        "Fix these in the block you just wrote: one sentence per line; "
        "split sentences over ~120 chars at a real clause boundary "
        "(both sides must stand alone); "
        "never break URLs, directives, or example code. "
        "A finding can be a false positive "
        "(e.g. an 'and' joining a compound object is not a boundary) — "
        "judge each one; leave the line alone if the break would sever a clause. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )


def test_blocking_report_bytes_with_snippet():
    got = check_linefeeds.format_findings(
        check_linefeeds.check(FUSED, "doc.md"), "doc.md", snippet=True
    )
    assert got == (
        "semantic-linefeeds: 1 issue(s) in the text just written to doc.md:\n"
        "  [fused] line 1 of your edit: "
        "two sentences on one line — one sentence per line\n"
        "         > One sentence here. Another sentence follows.\n"
        "Fix these in the block you just wrote: one sentence per line; "
        "split sentences over ~120 chars at a real clause boundary "
        "(both sides must stand alone); "
        "never break URLs, directives, or example code. "
        "A finding can be a false positive "
        "(e.g. an 'and' joining a compound object is not a boundary) — "
        "judge each one; leave the line alone if the break would sever a clause. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )


def test_advisory_report_bytes_with_snippet():
    got = check_linefeeds.format_findings(
        check_linefeeds.check(WRAP, "doc.md"), "doc.md", snippet=True
    )
    assert got == (
        "semantic-linefeeds: 1 issue(s) in the text just written to doc.md:\n"
        "  [wrap] line 1 of your edit: ends mid-clause (column-wrapped?) — "
        "break at sentence or clause boundaries, not at a column\n"
        "         > the compiler will assume all functions provide an `ABIInt...\n"
        "Consider these, and change nothing you are not sure about. "
        "A wrap finding is an evaluation of this checker rather than an "
        "instruction to you: decide whether the line already ends at a real "
        "clause boundary, and leave it exactly as it is if it does. "
        "Never break URLs, directives, or example code. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )


def test_advisory_wrap_report_truncates_and_never_says_fix():
    got = check_linefeeds.format_findings(
        check_linefeeds.check(WRAP, "doc.md"), "doc.md", snippet=False
    )
    assert got == (
        "semantic-linefeeds: 1 issue(s) in doc.md:\n"
        "  [wrap] line 1: ends mid-clause (column-wrapped?) — "
        "break at sentence or clause boundaries, not at a column\n"
        "         > the compiler will assume all functions provide an `ABIInt...\n"
        "Consider these, and change nothing you are not sure about. "
        "A wrap finding is an evaluation of this checker rather than an "
        "instruction to you: decide whether the line already ends at a real "
        "clause boundary, and leave it exactly as it is if it does. "
        "Never break URLs, directives, or example code. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )


def test_advisory_long_report_names_the_leave_it_long_answer():
    got = check_linefeeds.format_findings(
        check_linefeeds.check(LONG, "doc.md"), "doc.md", snippet=False
    )
    assert got == (
        "semantic-linefeeds: 1 issue(s) in doc.md:\n"
        "  [long] line 1: " + LONG_MSG.format(n=150) + "\n"
        "         > This advisory line keeps going with a possible clause bou...\n"
        "Consider these, and change nothing you are not sure about. "
        "A line over ~120 chars is worth splitting only at a real clause "
        "boundary where both sides stand alone. "
        "If there is no such boundary, leaving the line long is the right answer. "
        "Never break URLs, directives, or example code. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )


def test_mixed_report_orders_kinds_and_truncates_each_excerpt():
    # Secondary structural check; the byte proofs are the literal tests above.
    got = check_linefeeds.format_findings(
        check_linefeeds.check(MIXED, "doc.md"), "doc.md", snippet=True
    )
    head = "semantic-linefeeds: 3 issue(s) in the text just written to doc.md:"
    assert got.startswith(head)
    labels = [line for line in got.split("\n") if line.startswith("  [")]
    assert [label.split("]")[0] for label in labels] == [
        "  [fused",
        "  [long",
        "  [wrap",
    ]
    excerpts = [line for line in got.split("\n") if line.startswith("         > ")]
    assert all(line.endswith("...") for line in excerpts)


def test_no_report_gains_a_final_newline():
    for text in (FUSED, WRAP, LONG, MIXED):
        got = check_linefeeds.format_findings(
            check_linefeeds.check(text, "doc.md"), "doc.md", snippet=False
        )
        assert not got.endswith("\n")
