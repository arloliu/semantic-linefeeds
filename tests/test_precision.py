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


def test_a_code_span_is_never_peeled_as_emphasis():
    """Peeling the delimiter alone would expose whatever punctuation the code contains.

    A code span is removed whole instead, by `peel_code_span`, and for the opposite reason:
    the punctuation inside it says nothing about the sentence it sits in.
    """
    assert check_linefeeds.peel_emphasis("run `go build`") == "run `go build`"


# --- trailing code spans --------------------------------------------------

@pytest.mark.parametrize("line,peeled", [
    ("the compiler will assume all functions provide an `ABIInternal`",
     "the compiler will assume all functions provide an"),
    ("method: `window/collectInput`", "method:"),
    ("just using the measured `$r$`", "just using the measured"),
])
def test_a_span_that_closes_the_line_is_removed_whole(line, peeled):
    assert check_linefeeds.peel_code_span(line) == peeled


@pytest.mark.parametrize("line", [
    "`the whole line is one code span`",
    "run `go build` and then stop",
    "a line with no span at all",
    "a line with an unclosed `span",
])
def test_nothing_else_is_peeled(line):
    assert check_linefeeds.peel_code_span(line) == line


def test_a_line_ending_in_a_code_span_is_now_read_by_what_precedes_it():
    """The exemption cost four fifths of the stratum it covers.

    A backtick ends a line legitimately, so the clause the span was attached to
    was never examined at all.
    """
    assert kinds("the compiler will assume all functions provide an `ABIInternal`\n"
                 "implementation.\n") == [(1, "wrap")]


def test_a_line_ending_at_a_clause_boundary_before_a_span_is_left_alone():
    """The refutation case, and the reason the whole span goes rather than the delimiter.

    The punctuation that ends the clause stands in front of the span,
    and removing the span is what makes it readable.
    """
    assert kinds("method: `window/collectInput`\n"
                 "params: `FormField[]`\n") == []


def test_a_line_that_is_only_a_code_span_keeps_its_ending():
    """Code alone is not a clause, so there is no clause end to look for behind it."""
    assert kinds("`type [T] type Vector []T`\n"
                 "and the syntax described above is preferred.\n") == []


def test_emphasis_hiding_terminal_punctuation_no_longer_wraps():
    assert kinds("The backend is **required.**\nit has no default.\n") == []


def test_emphasis_hiding_nothing_still_wraps():
    assert kinds("The backend is **required**\nit has no default.\n") == [(1, "wrap")]


# --- fused across inline markup -------------------------------------------

def test_a_sentence_ending_on_a_code_span_still_fuses():
    """A closing backtick is unambiguous: the punctuation after it is the sentence's own.

    Prose that names APIs ends sentences on code spans constantly,
    and requiring the final word to be lowercase letters walked past every one.
    """
    assert kinds("A previous pitch used the names `nonconsuming` and `consuming`. "
                 "The current one drops both.\n") == [(1, "fused")]


def test_a_second_sentence_opening_with_a_code_span_still_fuses():
    """The right side asked for an uppercase letter, and `Data` opens with a backtick."""
    assert kinds("crosses framework boundaries. `Data` owns its underlying memory.\n"
                 ) == [(1, "fused")]


def test_emphasis_between_the_stop_and_the_space_no_longer_hides_a_fuse():
    """The closing class sat after the punctuation but knew nothing of emphasis marks."""
    assert kinds("**Make by-reference closures the default.** We felt this was right.\n"
                 ) == [(1, "fused")]


def test_a_bolded_label_beside_a_sentence_stays_quiet():
    """The fragment shape: emphasis before the stop is a label, not a sentence end."""
    assert kinds("**Base name**. If the iterator yields a value, the name is used.\n") == []


def test_a_bracketed_enumeration_is_not_a_sentence_end():
    """A closing bracket before the stop stays outside the rule: see (1). Then is prose."""
    assert kinds("walk the list as in (1). Then the walk continues to the next node.\n") == []


def test_a_span_enumeration_is_not_two_sentences():
    """Spans punctuated in sequence carry no second sentence after any of them."""
    assert kinds("the flags are `-a`. `-b`. `-c`.\n") == []


def test_a_trailing_span_fragment_is_not_a_second_sentence():
    """A span that ends the line after a stop is a fragment a labeler may not even call one."""
    assert kinds("The call looks like this. `make build`\n") == []


# --- list items -----------------------------------------------------------

def test_one_list_item_is_not_measured_against_the_next():
    assert kinds("- The value is cached, and\n- the cache expires hourly.\n") == []


def test_an_ordered_item_is_not_measured_against_the_next():
    assert kinds("1. The first step runs and\n2. the second step follows.\n") == []


def test_a_continuation_line_inside_one_item_is_still_measured():
    assert kinds("- a slice of the type that the caller supplies\n  of that type\n") == [(1, "wrap")]


def test_a_paragraph_is_still_measured_against_itself():
    assert kinds("a line that ends mid-clause because it was\nwrapped at a column.\n") == [(1, "wrap")]


# --- licence blocks -------------------------------------------------------

SECOND_LICENSE = (
    "// Copyright 2026 Arlo Liu. All rights reserved.\n"
    "\n"
    "package demo\n"
    "\n"
    "func First() {}\n"
    "\n"
    "// Copyright 2026 Arlo Liu\n"
    "// You may obtain a copy of the License at the address in the NOTICE file\n"
    "// distributed with this work.\n"
)


def test_a_licence_block_below_the_code_is_not_prose():
    """Only the leading region is found by extent, and a generated file carries two."""
    assert kinds(SECOND_LICENSE, "demo.go") == []


def test_prose_between_two_licence_blocks_is_still_checked():
    """The rule silences a paragraph carrying a marker, not the rest of the file."""
    text = SECOND_LICENSE.replace(
        "func First() {}\n",
        "// a line that ends mid-clause because it was\n"
        "// wrapped at a column.\n"
        "func First() {}\n")
    assert kinds(text, "demo.go") == [(5, "wrap")]


def test_a_comment_paragraph_naming_no_licence_is_untouched():
    assert kinds("package demo\n"
                 "\n"
                 "// a line that ends mid-clause because it was\n"
                 "// wrapped at a column.\n", "demo.go") == [(3, "wrap")]


# --- tables ---------------------------------------------------------------

PIPELESS_TABLE = (
    "Method | Collections\n"
    "---|---\n"
    "get returns a shared reference to the value | HashMap and TreeMap\n"
    "insert replaces the value already stored there | HashMap only\n"
)


def test_a_table_row_that_omits_its_leading_pipe_is_not_prose():
    """The first character marks nothing, so the delimiter row has to mark the block."""
    assert kinds(PIPELESS_TABLE) == []


def test_a_quoted_table_behaves_like_an_unquoted_one():
    quoted = "".join(f"> {line}\n" for line in PIPELESS_TABLE.splitlines())
    assert kinds(quoted) == []


def test_a_paragraph_containing_a_pipe_is_still_checked():
    """A pipe is a character prose uses; only a delimiter row under it means a table."""
    assert kinds("the flag reads a | separated list and it was\n"
                 "wrapped at a column.\n") == [(1, "wrap")]


def test_a_row_of_dashes_without_a_pipe_opens_no_table():
    """A setext underline would otherwise swallow the heading text above it."""
    assert kinds("One thing here. Another thing here.\n---\n") == [(1, "fused")]


def test_prose_after_a_table_is_still_checked():
    assert kinds(PIPELESS_TABLE + "\n"
                 "a line that ends mid-clause because it was\n"
                 "wrapped at a column.\n") == [(6, "wrap")]


# --- commented-out code ---------------------------------------------------

COMMENTED_OUT = (
    "package example\n"
    "\n"
    "// Open a session and close it when the work is done.\n"
    "// session, err := pool.Acquire(ctx)\n"
    "// if err != nil {\n"
    "//     return err\n"
    "// }\n"
    "// defer session.Release()\n"
)


def test_a_lone_closing_brace_is_not_measured_against_the_line_below_it():
    """A worked example written as line comments never reaches the indented-example rule.

    The closing brace ends no clause and the call under it starts none,
    so the two were read as one wrapped sentence.
    """
    assert kinds(COMMENTED_OUT, "example.go") == []


@pytest.mark.parametrize("line", ["}", "})", "});", ")", "],", "} )"])
def test_a_line_of_only_code_punctuation_is_not_prose(line):
    assert check_linefeeds.comment_body(line) is None


@pytest.mark.parametrize("line", [
    "}, and the handler returns",
    "The closing brace } ends the block",
    "—",
])
def test_a_line_carrying_anything_else_is_still_prose(line):
    """The rule reads a whole line, not a character class found anywhere in one.

    An em dash alone is punctuation a person wrote,
    and swallowing it would hide the boundary it stands at.
    """
    assert check_linefeeds.comment_body(line) == line


# --- dividers -------------------------------------------------------------

DASH_DIVIDER = ("package example\n"
                "\n"
                "// ----------------------\n"
                "// Write Operations\n"
                "// ----------------------\n")


def test_a_divider_breaks_the_paragraph_around_it():
    """The label under a rule of dashes continues no sentence above it.

    A dash ends a line legitimately, so this pair never reported a wrap.
    It reached the sampling frame instead,
    where it sat as a boundary about which there was nothing to decide.
    """
    stream = check_linefeeds.prose_stream(DASH_DIVIDER, "example.go")
    assert [(n, p) for n, _, p in stream if p is not None] == [(4, "Write Operations")]


def test_a_divider_of_a_character_that_ends_no_line_no_longer_wraps():
    assert kinds("package example\n"
                 "\n"
                 "// ======================\n"
                 "// write operations here\n", "example.go") == []


@pytest.mark.parametrize("line", ["---", "======================", "***", "..."])
def test_a_run_of_one_punctuation_mark_is_not_prose(line):
    assert check_linefeeds.comment_body(line) is None


@pytest.mark.parametrize("line", ["—", "--", "-=-=-=", "- a list item"])
def test_a_line_short_of_a_rule_is_still_prose(line):
    """Three characters minimum, of one mark, so nothing a person wrote mid-sentence goes."""
    assert check_linefeeds.comment_body(line) == line


def test_prose_containing_dashes_is_untouched():
    assert kinds("package example\n"
                 "\n"
                 "// a line -- with dashes in it -- that ends mid-clause and was\n"
                 "// wrapped at a column.\n", "example.go") == [(3, "wrap")]


def test_prose_after_commented_out_code_is_still_measured():
    """The rule breaks the paragraph; it does not switch the checker off for the rest."""
    text = ("package example\n"
            "\n"
            "// }\n"
            "// a line that ends mid-clause because it was\n"
            "// wrapped at a column.\n")
    assert kinds(text, "example.go") == [(4, "wrap")]


# --- a licence header behind a build directive ----------------------------

APACHE_HEADER = (
    "/*\n"
    " *\n"
    " * Copyright 2026 Arlo Liu.\n"
    " *\n"
    " * Licensed under the Apache License, Version 2.0 (the \"License\");\n"
    " * you may not use this file except in compliance with the License.\n"
    " * You may obtain a copy of the License at\n"
    " *\n"
    " *     http://www.apache.org/licenses/LICENSE-2.0\n"
    " *\n"
    " * Unless required by applicable law or agreed to in writing, software\n"
    " * distributed under the License is distributed on an \"AS IS\" BASIS,\n"
    " * See the License for the specific language governing permissions and\n"
    " * limitations under the License.\n"
    " *\n"
    " */\n"
    "\n"
    "package demo\n"
)

BUILD_TAGGED = "//go:build !race\n// +build !race\n\n" + APACHE_HEADER


def prose_after_the_licence_cut(text, path):
    """The prose lines the checker judges, which is also the frame a sample is drawn from."""
    stream = check_linefeeds.prose_stream(text, path)
    return [(n, p) for n, _, p in check_linefeeds.without_license_text(stream, text, path)
            if p is not None]


def test_a_licence_header_is_cut_whether_or_not_a_directive_stands_above_it():
    """The directives were the whole difference between a cut header and an uncut one.

    A build constraint is not a comment scope of its own.
    Reading it as one ended the leading region at the blank line under it,
    which left the licence below judged as prose,
    and put its sentences into a sampling frame as boundaries with nothing to decide.
    """
    assert prose_after_the_licence_cut(APACHE_HEADER, "demo.go") == []
    assert prose_after_the_licence_cut(BUILD_TAGGED, "demo.go") == []


def test_a_directive_preamble_does_not_silence_the_comment_under_it():
    """The preamble is stepped over to find a licence, not to switch the file off."""
    text = ("//go:build !race\n"
            "// +build !race\n"
            "\n"
            "// a line that ends mid-clause because it was\n"
            "// wrapped at a column.\n")
    assert kinds(text, "demo.go") == [(4, "wrap")]


def test_prose_below_a_build_tagged_licence_is_still_checked():
    text = BUILD_TAGGED + ("\n"
                           "// a line that ends mid-clause because it was\n"
                           "// wrapped at a column.\n")
    assert kinds(text, "demo.go") == [(23, "wrap")]


@pytest.mark.parametrize("directive", ["//go:build !race", "// +build !race", "//go:generate stringer"])
def test_each_directive_shape_is_stepped_over(directive):
    assert prose_after_the_licence_cut(directive + "\n\n" + APACHE_HEADER, "demo.go") == []


# --- a generated file that says so below its licence ----------------------

GENERATED_BELOW_LICENCE = (
    "// Copyright 2026 Arlo Liu. All rights reserved.\n"
    "//\n"
    "// Licensed under the Apache License, Version 2.0 (the \"License\");\n"
    "// you may not use this file except in compliance with the License.\n"
    "// You may obtain a copy of the License at\n"
    "//\n"
    "//     http://www.apache.org/licenses/LICENSE-2.0\n"
    "//\n"
    "// Unless required by applicable law or agreed to in writing, software\n"
    "// distributed under the License is distributed on an \"AS IS\" BASIS.\n"
    "\n"
    "// Code generated by protoc-gen-go. DO NOT EDIT.\n"
    "// versions:\n"
    "//   protoc-gen-go v1.28.1\n"
    "\n"
    "package demo\n"
    "\n"
    "// a line that ends mid-clause because it was\n"
    "// wrapped at a column.\n"
)


def test_a_generated_marker_below_a_licence_block_still_skips_the_file():
    """Only a file's first five lines were read, and a licence is longer than five.

    A generated file is not written by a person,
    so nothing in it is prose anybody can act on a finding about.
    """
    assert kinds(GENERATED_BELOW_LICENCE, "demo.pb.go") == []


def test_the_licence_alone_would_not_have_skipped_the_file():
    """Otherwise the case above passes on the licence rather than on the marker."""
    without_marker = GENERATED_BELOW_LICENCE.replace(
        "// Code generated by protoc-gen-go. DO NOT EDIT.\n"
        "// versions:\n"
        "//   protoc-gen-go v1.28.1\n"
        "\n", "")
    assert kinds(without_marker, "demo.pb.go") == [(14, "wrap")]


def test_a_marker_far_below_the_header_skips_nothing():
    """The marker belongs to a file header; prose further down naming it is prose."""
    text = ("package demo\n"
            "\n"
            "func First() {}\n"
            "\n"
            "func Second() {}\n"
            "\n"
            "// Code generated by hand, DO NOT EDIT\n"
            "\n"
            "// a line that ends mid-clause because it was\n"
            "// wrapped at a column.\n")
    assert kinds(text, "demo.go") == [(9, "wrap")]


def test_the_first_five_lines_are_still_read_wherever_the_marker_sits():
    """The header scan is added to that reach rather than replacing it.

    Narrowing the old rule to the header would start checking files it now skips,
    and a change that adds findings is not one this corpus can score.
    """
    text = ("package demo\n"
            "\n"
            "// Code generated by hand, DO NOT EDIT\n"
            "// a line that ends mid-clause because it was\n"
            "// wrapped at a column.\n")
    assert kinds(text, "demo.go") == []


# --- HTML and fenced code in Markdown -------------------------------------

PRE_BLOCK = (
    "Intro paragraph.\n"
    "\n"
    "<pre>\n"
    "struct Foo {\n"
    "  let bar: Int\n"
    "}\n"
    "</pre>\n"
)


def test_code_inside_a_pre_block_is_not_prose():
    """A proposal that writes its examples as HTML rather than as a fence.

    The opening tag was already skipped for starting with a bracket,
    and every line of code under it was read as prose.
    """
    assert kinds(PRE_BLOCK) == []


def test_prose_after_a_pre_block_is_still_checked():
    text = PRE_BLOCK + ("\n"
                        "a line that ends mid-clause because it was\n"
                        "wrapped at a column.\n")
    assert kinds(text) == [(9, "wrap")]


FENCE_CLOSED_BY_THE_OTHER_MARK = (
    "```\n"
    "~~~~~~~\n"
    "```\n"
    "\n"
    "Intro paragraph.\n"
    "\n"
    "```swift\n"
    "struct Foo {\n"
    "  let bar: Int\n"
    "}\n"
    "```\n"
)


def test_a_fence_is_closed_only_by_its_own_mark():
    """One flag for both marks lets a tilde run inside a backtick fence close it.

    Every fence after that point is inverted,
    so prose is skipped and the code in the next block is read as prose.
    """
    assert kinds(FENCE_CLOSED_BY_THE_OTHER_MARK) == []


def test_a_tilde_fence_still_opens_and_closes_on_its_own():
    text = ("~~~\n"
            "struct Foo {\n"
            "  let bar: Int\n"
            "}\n"
            "~~~\n"
            "\n"
            "a line that ends mid-clause because it was\n"
            "wrapped at a column.\n")
    assert kinds(text) == [(7, "wrap")]


def test_a_backtick_run_inside_a_tilde_fence_closes_nothing():
    text = ("~~~\n"
            "```\n"
            "~~~\n"
            "\n"
            "a line that ends mid-clause because it was\n"
            "wrapped at a column.\n")
    assert kinds(text) == [(5, "wrap")]


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


# --- a gofail directive in a Go comment -----------------------------------


def test_a_gofail_directive_line_is_not_prose():
    """`// gofail: var x T` is machine input for a failpoint generator.

    The spaced form slips past the unspaced directive pattern,
    and the third corpus round measured a wrap accusation on one.
    """
    text = ("package backend\n"
            "\n"
            "func defragdb() error {\n"
            "\t// gofail: var defragdbFail string\n"
            "\t// return fmt.Errorf(defragdbFail)\n"
            "\treturn nil\n"
            "}\n")
    assert kinds(text, "backend.go") == []


def test_a_spaced_prose_label_is_not_read_as_a_directive():
    """Only `gofail:` earns the spaced-directive reading; prose labels stay prose."""
    text = ("package demo\n"
            "\n"
            "// note: a line that ends mid-clause because it was\n"
            "// wrapped at a column.\n")
    assert kinds(text, "demo.go") == [(3, "wrap")]
