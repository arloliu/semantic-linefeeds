"""Measure the wrapping column a candidate source writes at.

    python3 tests/corpus/qualify.py <checkout> go|markdown

A source is admitted on how it wraps, on its licence, and on never having been read by a tuning session.
Nothing here reads the detector.
Selecting a repository by how many findings it draws would repeat, at repository granularity,
the error ADR-0003 forbids at candidate granularity.

The six sources of the first round were measured by a script nobody kept,
so their recorded numbers cannot be recomputed from this repository.
This file exists so that stops being true.
What it measures is stated rather than implied:

- A Go comment line is a line whose first non-blank characters are `//` and which carries text after them.
- A Markdown prose line is a non-blank line outside a fenced block
  that is not a heading, a table row, a quote, a list item, a link reference definition,
  an indented block, or raw HTML.
- Only runs of two or more adjacent such lines count.
  A wrapping column is visible where text wrapped, and a line standing alone never wrapped.

A line's length is the column it ends at with trailing whitespace removed and tabs left uncounted,
which is the same measurement the `raw_end_column` covariate records.
"""

import collections
import pathlib
import re
import subprocess
import sys

# What a source is selected on, and the only thing this file computes.
KINDS = ("go", "markdown")

SELECTION = {
    "go": ["*.go", ":!:*_test.go", ":!:vendor/*"],
    "markdown": ["*.md"],
}

LIST_MARKER_RE = re.compile(r"^([-*+]|\d+[.)])\s")
LINK_DEFINITION_RE = re.compile(r"^\[[^\]]+\]:\s")

# A line opening with one of these is structure rather than prose,
# and structure wraps at whatever column its content happens to reach.
NOT_PROSE = ("#", "|", ">", "<", "!", "---", "===")

FENCES = ("```", "~~~")


def files(root, kind):
    """The files the source's own selection command names."""
    return subprocess.run(["git", "-C", str(root), "ls-files"] + SELECTION[kind],
                          capture_output=True, text=True, check=True).stdout.split()


def is_go_comment(raw):
    """A Go comment line carrying text, rather than a bare `//` or code."""
    stripped = raw.lstrip()
    return stripped.startswith("//") and bool(stripped[2:].strip())


def is_markdown_prose(raw):
    """A Markdown line that is prose rather than structure.

    The fence state is not visible from one line,
    so this answers for a line already known to stand outside a fenced block.
    """
    stripped = raw.strip()
    if not stripped or raw.startswith(("    ", "\t")) or stripped.startswith(NOT_PROSE):
        return False
    return not (LIST_MARKER_RE.match(stripped) or LINK_DEFINITION_RE.match(stripped))


def runs(text, kind):
    """The end columns of each run of adjacent prose lines, run by run.

    A run of one is dropped by the caller rather than here,
    so what counts as adjacency stays in one place.
    """
    fenced, run = False, []
    for raw in text.splitlines():
        if kind == "markdown" and raw.strip().startswith(FENCES):
            fenced = not fenced
            raw = ""
        wanted = (is_go_comment(raw) if kind == "go"
                  else not fenced and is_markdown_prose(raw))
        if wanted:
            run.append(len(raw.rstrip()))
            continue
        if run:
            yield run
        run = []
    if run:
        yield run


def lengths(root, kind):
    out = []
    for name in files(root, kind):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out += [length for run in runs(text, kind) if len(run) > 1 for length in run]
    return out


def shape(measured):
    """The mode, and how much of the distribution stands near it.

    A source that wraps at a column piles its lines up against that column.
    One that does not has a mode by arithmetic and nothing behind it,
    which is what the two shares are for:
    a wide spread and a long tail say the mode is an artifact rather than a habit.
    """
    counts = collections.Counter(measured)
    mode = max(counts, key=lambda length: (counts[length], length))
    total = len(measured)
    return {
        "wrapping_column": mode,
        "lines": total,
        "within_two": sum(n for length, n in counts.items() if abs(length - mode) <= 2) / total,
        "beyond_six": sum(n for length, n in counts.items() if length > mode + 6) / total,
    }


def qualification(kind, shaped):
    """The sentence the manifest records, built from the measurement rather than typed beside it."""
    what = "Go `//` comment" if kind == "go" else "Markdown paragraph"
    return ("mode of raw %s line lengths is column %d, over %d lines, "
            "with %d%% within two columns of the mode and %d%% beyond six past it; "
            "measured by tests/corpus/qualify.py from line lengths, licence, and prior exposure only"
            % (what, shaped["wrapping_column"], shaped["lines"],
               round(shaped["within_two"] * 100), round(shaped["beyond_six"] * 100)))


def main(root, kind):
    if kind not in KINDS:
        sys.exit("the kind is one of " + ", ".join(KINDS))
    root = pathlib.Path(root).resolve()
    measured = lengths(root, kind)
    if not measured:
        sys.exit(f"{root} yields no {kind} lines to measure")
    shaped = shape(measured)
    print(f"wrapping_column {shaped['wrapping_column']}")
    print(qualification(kind, shaped))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
