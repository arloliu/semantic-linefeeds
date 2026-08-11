"""The exceptions this release adds, and the evidence that each one earns its place.

An exception nothing tests is an exception nobody can remove safely.
Every entry in the abbreviation list is checked against the rule it amends,
so a list that drifted away from the rule fails here rather than in the field.
"""

import json
import re

from conftest import run_cli
import pytest

import check_linefeeds

# The rule as it stood before any abbreviation was excluded from it.
NAIVE_FUSED_RE = re.compile(r"\b[a-z]{2,}[.!?][\"')\]]*\s+[A-Z]")


def kinds(text, path="doc.md"):
    return [(n, k) for n, k, _, _ in check_linefeeds.check(text, path)]


# --- abbreviations --------------------------------------------------------

@pytest.mark.parametrize("abbreviation", check_linefeeds.MID_SENTENCE_ABBREVIATIONS)
def test_each_excluded_abbreviation_is_one_the_rule_would_otherwise_match(abbreviation):
    """The list amends the active rule, so every entry must be reachable by it.

    An entry the rule can never match was copied from somewhere else,
    and it silently widens the exclusion the day the rule changes.
    """
    line = f"Consider one thing {abbreviation}. Another thing entirely.\n"
    assert NAIVE_FUSED_RE.search(line), f"{abbreviation}. cannot match the rule it excludes"
    assert kinds(line) == []


@pytest.mark.parametrize("abbreviation", ["Fig", "No", "Eq"])
def test_a_capitalized_abbreviation_needs_no_exclusion(abbreviation):
    """The rule wants two lowercase letters before the stop, which these never supply."""
    line = f"Consider one thing {abbreviation}. Another thing entirely.\n"
    assert not NAIVE_FUSED_RE.search(line)
    assert abbreviation.lower() not in check_linefeeds.MID_SENTENCE_ABBREVIATIONS
    assert kinds(line) == []


@pytest.mark.parametrize("abbreviation", ["e.g", "i.e"])
def test_a_single_letter_abbreviation_needs_no_exclusion(abbreviation):
    line = f"Consider one thing, {abbreviation}. Another thing entirely.\n"
    assert not NAIVE_FUSED_RE.search(line)
    assert kinds(line) == []


def test_a_word_merely_ending_in_an_excluded_abbreviation_still_fuses():
    """The exclusion is anchored at a word boundary, not matched anywhere in the word."""
    assert kinds("The two limits are five and ten, resp. The default is five.\n") == [(1, "fused")]


def test_a_sentence_end_that_is_not_an_abbreviation_still_fuses():
    assert kinds("One sentence here. Another sentence follows.\n") == [(1, "fused")]


# --- trailing emphasis ----------------------------------------------------

@pytest.mark.parametrize("line,peeled", [
    ("**Note:**", "**Note:"),
    ("The backend is **required.**", "The backend is **required."),
    ("The retry count is _optional._", "The retry count is _optional."),
    ("The old flag is ~~removed.~~", "The old flag is ~~removed."),
    ("A nested *emphasis inside **bold**.*", "A nested *emphasis inside **bold**."),
])
def test_a_closing_delimiter_is_peeled_when_something_opened_it(line, peeled):
    assert check_linefeeds.peel_emphasis(line) == peeled


@pytest.mark.parametrize("line", [
    "The multiplication sign is *",
    "A trailing underscore _",
    "The code span is `value.`",
    "A bare tilde ~",
])
def test_an_unopened_delimiter_is_left_alone(line):
    assert check_linefeeds.peel_emphasis(line) == line


def test_a_code_span_is_never_peeled():
    """The backtick already ends a line legitimately.

    Stripping it would expose whatever punctuation the code happens to contain,
    which is a new false positive rather than a repair.
    """
    assert check_linefeeds.peel_emphasis("run `go build`") == "run `go build`"


def test_emphasis_hiding_terminal_punctuation_no_longer_wraps():
    assert kinds("The backend is **required.**\nit has no default.\n") == []


def test_emphasis_hiding_nothing_still_wraps():
    assert kinds("The backend is **required**\nit has no default.\n") == [(1, "wrap")]


# --- list items -----------------------------------------------------------

def test_one_list_item_is_not_measured_against_the_next():
    assert kinds("- The value is cached, and\n- the cache expires hourly.\n") == []


def test_an_ordered_item_is_not_measured_against_the_next():
    assert kinds("1. The first step runs and\n2. the second step follows.\n") == []


def test_a_continuation_line_inside_one_item_is_still_measured():
    assert kinds("- a slice of the type that the caller supplies\n  of that type\n") == [(1, "wrap")]


def test_a_paragraph_is_still_measured_against_itself():
    assert kinds("a line that ends mid-clause because it was\nwrapped at a column.\n") == [(1, "wrap")]


# --- blockquotes ----------------------------------------------------------

QUOTED = [
    ("a fence", "> Intro.\n>\n> ```go\n> code := line()\n> ```\n"),
    # The code has to be shaped so that reading it as prose produces a finding.
    # An opening brace is not a line ender and the next line starts lowercase,
    # which is a wrap the moment the four-space rule stops applying.
    ("indented code", "> Intro.\n>\n>     for _, s := range items {\n>         process(s)\n>     }\n"),
    ("a heading", "> ## One thing. Another thing.\n"),
    ("a table", "> | One thing here. Another thing here. | b |\n"),
    ("a reference definition", "> [ref]: One thing here. Another thing here.\n"),
    ("inline HTML", "> <div>One thing. Another thing.</div>\n"),
]


@pytest.mark.parametrize("what,text", QUOTED, ids=[name for name, _ in QUOTED])
def test_a_quoted_line_keeps_the_exemption_it_would_have_unquoted(what, text):
    unquoted = "\n".join(
        re.sub(r"^ {0,3}> ?", "", line) for line in text.splitlines()) + "\n"
    assert kinds(unquoted) == [], f"the unquoted case is not exempt either: {what}"
    assert kinds(text) == []


def test_quoted_prose_is_still_prose():
    assert kinds("> One sentence here. Another sentence follows.\n") == [(1, "fused")]


def test_prose_quoted_twice_is_still_prose():
    assert kinds(">> One sentence here. Another sentence follows.\n") == [(1, "fused")]


def test_a_quoted_wrap_is_still_a_wrap():
    assert kinds("> a line that ends mid-clause because it was\n> wrapped at a column.\n") == [(1, "wrap")]


def test_a_quote_marker_alone_breaks_the_paragraph():
    assert kinds("> a line that ends mid-clause because it was\n>\n> wrapped at a column.\n") == []


# --- the release ----------------------------------------------------------

def hook_status(text):
    """The exit code a write of this text would produce, through the real hook."""
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/x/doc.md", "content": text},
    })
    return run_cli(["--hook", "claude"], payload).returncode


@pytest.mark.parametrize("abbreviation", check_linefeeds.MID_SENTENCE_ABBREVIATIONS)
def test_the_sole_blocking_kind_no_longer_misfires_on_an_abbreviation(abbreviation):
    """The withdrawal and the exclusions have to arrive together.

    Withdrawing `wrap` leaves `fused` as the only kind that can refuse an edit.
    A `fused` still firing on "vs." would then be the whole distance
    between correct prose and a blocked write.
    """
    assert check_linefeeds.BLOCKING_KINDS == frozenset({"fused"})
    assert hook_status(f"Compare one thing {abbreviation}. Another thing entirely.\n") == 0


def test_the_blocking_kind_still_refuses_a_genuine_fusion():
    """The other half: an exclusion set wide enough to block nothing blocks nothing."""
    assert hook_status("One sentence here. Another sentence follows.\n") == 2
