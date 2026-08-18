"""Count the fused population by the class that withholds its suggestion.

    python3 tests/corpus/repairs/measure.py <path> [<path> ...]

The plan for this corpus chose its strata and its per-stratum size from these counts,
so the instrument that produced them is committed rather than described.
`qualify.py` exists for the same reason:
a number nobody can recompute is a number the next reader has to trust.

Two things separate this from a reading of `_fused_suggestion`.

Every class that applies is reported, not the first one.
The shipped function stops at its first refusal because it only needs to know whether to speak;
a widening admits one class at a time and has to know which others still stand on the same line.

The classes are finer than the refusals.
`_fused_suggestion` asks whether the character before the gap is `!` or `?`,
which answers "no" for a period and for `!"` alike,
and those are different repairs with different risks.
Nothing here reads a suggestion.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parent.parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402

# Every class a suggestion can be withheld by, named so the name survives a widening.
# A class admitted by a later predicate stops being a refusal and keeps its identity here,
# because the round that scored it has to stay comparable to the one that did not.
CLASSES = (
    "carriage_return",
    "many_boundaries",
    "protected_span",
    "prose_not_unique",
    "gap_multiple_spaces",
    "gap_tab",
    "gap_other_whitespace",
    "terminator_period",
    "closing_delimiter",
    "prefix_list_marker",
    "prefix_other",
    "tail_rejected",
    "carrier_stripped",
)

_LIST_MARKER_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")


def classes_for(prose, raw, match):
    """Every class that withholds a suggestion for this boundary, in declaration order."""
    found = []
    if "\r" in raw:
        found.append("carriage_return")
    if len(list(clf.FUSED_RE.finditer(prose))) != 1:
        found.append("many_boundaries")
    if "`" in prose or "<" in prose or ">" in prose:
        found.append("protected_span")

    occurrences = raw.count(prose)
    if occurrences != 1:
        found.append("prose_not_unique")

    text = match.group(0)
    gap = re.search(r"\s+", text).group(0)
    if gap != " ":
        if "\t" in gap:
            found.append("gap_tab")
        elif gap == " " * len(gap):
            found.append("gap_multiple_spaces")
        else:
            found.append("gap_other_whitespace")

    # The terminator is the `[.!?]` the pattern matched, not the character before the gap.
    # A closing quote or bracket may stand between the two,
    # and the shipped check reads that character instead,
    # so one refusal covers a period and a closing delimiter after a `!`.
    terminator, delimiters = re.search(r"([.!?])([\"')\]*_~]*)\s", text).groups()
    if terminator == ".":
        found.append("terminator_period")
    if delimiters:
        found.append("closing_delimiter")

    # The prefix and tail tests are meaningless while the prose sits in the raw line twice:
    # the shipped function never reaches them, and an arbitrary occurrence is not the one it would have picked.
    if occurrences == 1:
        idx = raw.find(prose)
        prefix, tail = raw[:idx], raw[idx + len(prose) :]
        if not clf._SUGGESTION_PREFIX_RE.match(prefix):
            found.append(
                "prefix_list_marker"
                if _LIST_MARKER_RE.match(prefix)
                else "prefix_other"
            )
        if not clf._SUGGESTION_TAIL_RE.match(tail):
            found.append("tail_rejected")
    return found


def carrier_was_stripped(raw, path):
    """Whether a trailing suppression carrier came off this line before it was judged.

    The call site strips it and refuses a suggestion afterwards,
    so it is a withholding class that lives outside `_fused_suggestion`.
    """
    tail = clf.trailing_carrier(
        raw, clf.is_markdown(path), clf.lang_for_path(path) or "go"
    )
    return bool(tail)


def measure(paths):
    per_class = dict.fromkeys(CLASSES, 0)
    co_wrap = dict.fromkeys(CLASSES, 0)
    total = suggested = suggested_co_wrap = 0

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            diagnostics = clf.diagnose(text, str(path))
        except Exception:  # a file the extractor cannot read is not a measurement
            continue
        wrapped = {d["line"] for d in diagnostics if d["kind"] == "wrap"}
        for diagnostic in diagnostics:
            if diagnostic["kind"] != "fused":
                continue
            raw = text[diagnostic["anchor"]["start"] : diagnostic["anchor"]["end"]]
            prose = diagnostic["excerpt"]
            match = clf.FUSED_RE.search(prose)
            if match is None:
                continue
            total += 1
            also = diagnostic["line"] in wrapped
            found = classes_for(prose, raw, match)
            if carrier_was_stripped(raw, str(path)):
                found.append("carrier_stripped")
            for name in found:
                per_class[name] += 1
                co_wrap[name] += also
            if not found:
                suggested += 1
                suggested_co_wrap += also

    return total, suggested, suggested_co_wrap, per_class, co_wrap


def main(argv):
    paths = []
    for arg in argv:
        root = pathlib.Path(arg)
        paths += sorted(root.rglob("*")) if root.is_dir() else [root]
    paths = [
        p for p in paths if p.is_file() and p.suffix in (".md", ".py", ".go", ".ts")
    ]

    total, suggested, suggested_co_wrap, per_class, co_wrap = measure(paths)
    print(f"{total} fused findings over {len(paths)} files")
    print(f"{'class':<24}{'n':>7}{'co-wrap':>9}")
    print(f"{'(none: suggested today)':<24}{suggested:>7}{suggested_co_wrap:>9}")
    for name in CLASSES:
        print(f"{name:<24}{per_class[name]:>7}{co_wrap[name]:>9}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["."])
