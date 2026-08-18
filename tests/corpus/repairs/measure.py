"""Count the fused population by the classes that withhold its suggestion.

    python3 tests/corpus/repairs/measure.py <checkout-root> [--json <out>]

The plan for this corpus chose its strata and its per-stratum size from these counts,
so the instrument that produced them is committed rather than described.
`qualify.py` exists for the same reason:
a number nobody can recompute is a number the next reader has to take on trust.

Three things separate this from a reading of `_fused_suggestion`.

The population is the manifest's own selection command, through `files_of`,
and not a walk of every file with a checked suffix.
A walk pulls in tests and vendored code the draw will never see.

One unit is one boundary, not one line.
`diagnose` emits a diagnostic per `FUSED_RE` match and puts the same full prose line in each
(`scripts/check_linefeeds.py:1395-1423`),
so classifying from `FUSED_RE.search(prose)` would read every boundary on a line as the first one.

Every class that applies is counted, not the first one.
The shipped function stops at its first refusal because it only needs to know whether to speak;
a widening admits one class at a time and has to know which others still stand on the same line.

The classes are also finer than the refusals.
`_fused_suggestion` asks whether the character before the gap is `!` or `?`,
which answers "no" for a period and for a bang behind a closing quote alike,
and those are different repairs carrying different risks.

Nothing here reads a suggestion.
"""

import argparse
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402
from corpus_harness import files_of  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"

# Every class a suggestion can be withheld by, named so the name survives a widening.
# A class a later predicate admits stops being a refusal and keeps its identity here,
# because the round that scored it has to stay comparable to the round that did not.
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

# The terminator and any closing delimiters, read off the tail of one match rather than the head.
# `FUSED_RE` may open on a code span holding punctuation and whitespace of its own,
# so a search from the left can land inside the span instead of on the sentence boundary.
_BOUNDARY_RE = re.compile(r"([.!?])([\"')\]*_~]*)(\s+)")


def classes_for(prose, raw, match):
    """Every class that withholds a suggestion for one boundary, in declaration order."""
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

    # The gap and the punctuation are the ones abutting the following sentence,
    # which is the tail of the match after its opening capital or code span is removed.
    text = match.group(0)
    # The last one, not the first.
    # A match may open on a code span carrying punctuation and whitespace of its own,
    # and the sentence boundary is the one abutting the next sentence's opener,
    # which is where the match ends.
    boundary = None
    for candidate in _BOUNDARY_RE.finditer(text):
        boundary = candidate
    terminator, delimiters, gap = boundary.groups()

    if gap != " ":
        if "\t" in gap:
            found.append("gap_tab")
        elif gap == " " * len(gap):
            found.append("gap_multiple_spaces")
        else:
            found.append("gap_other_whitespace")
    if terminator == ".":
        found.append("terminator_period")
    if delimiters:
        found.append("closing_delimiter")

    # The prefix and tail tests are meaningless while the prose sits in the raw line twice:
    # the shipped function never reaches them,
    # and an arbitrary occurrence is not the one it would have picked.
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


def judged(raw, prose, path):
    """The raw line the detector judged, and whether a suppression carrier came off it.

    The call site strips a trailing carrier only when the extracted prose ends with it,
    and passes the stripped raw line onward (`scripts/check_linefeeds.py:1375-1389`).
    `diagnose` reports the stripped prose but anchors at the original raw line,
    so the two have to be brought back together here.

    **The carrier answer here is an inference, and it is the one number this file does not prove.**
    The detector decides from the prose as it stood *before* stripping,
    and what reaches this function is the prose after.
    A stripped line no longer ends with the carrier,
    and a line whose carrier was recognized but rejected commonly does not end with it either,
    so those two outcomes are not distinguishable from what is available here.
    The pinned output reports zero `carrier_stripped` units in all three sources,
    and that zero is unvalidated rather than measured.
    The plan's Task 2 replaces this with the detector's own value through `judged_lines`,
    and repins the output against it.
    Nothing else in this file depends on the answer:
    every other class is computed from the judged prose and raw line directly.
    """
    tail = clf.trailing_carrier(raw, clf.is_markdown(path), clf.lang_for_path(path))
    if not tail:
        return raw, False
    _parsed, judged_raw, carrier = tail
    if prose.rstrip(" \t").endswith(carrier):
        # The carrier is not a shared suffix of both views, so nothing was stripped.
        return raw, False
    return judged_raw, True


def measure(root, source):
    per_class = collections.Counter()
    co_wrap = collections.Counter()
    exact = collections.Counter()
    exact_co_wrap = collections.Counter()
    totals = collections.Counter()
    skipped = []

    for name in files_of(source, root):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as problem:
            skipped.append(f"{name}: {problem}")
            continue
        try:
            diagnostics = clf.diagnose(text, name)
        except (
            Exception
        ) as problem:  # a file the extractor cannot read is not a measurement
            skipped.append(f"{name}: {problem}")
            continue

        wrapped = {d["line"] for d in diagnostics if d["kind"] == "wrap"}
        # One diagnostic per match, all carrying the same prose:
        # collapse to one line and iterate the matches here instead.
        lines = {}
        for diagnostic in diagnostics:
            if diagnostic["kind"] == "fused":
                lines[diagnostic["line"]] = diagnostic

        for lineno, diagnostic in sorted(lines.items()):
            prose = diagnostic["excerpt"]
            raw = text[diagnostic["anchor"]["start"] : diagnostic["anchor"]["end"]]
            raw, stripped = judged(raw, prose, name)
            also = lineno in wrapped
            for match in clf.FUSED_RE.finditer(prose):
                totals["boundaries"] += 1
                found = classes_for(prose, raw, match)
                if stripped:
                    found.append("carrier_stripped")
                # The exact set is the sampling stratum: exact sets partition the population,
                # while class membership overlaps and cannot carry an unbiased marginal on its own.
                key = ",".join(sorted(found))
                exact[key] += 1
                exact_co_wrap[key] += also
                for cls in found:
                    per_class[cls] += 1
                    co_wrap[cls] += also
                if not found:
                    totals["suggested"] += 1
                    totals["suggested_co_wrap"] += also
                totals["co_wrap"] += also
    return totals, per_class, co_wrap, exact, exact_co_wrap, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="directory holding one checkout per source id")
    parser.add_argument("--side", default="calibration")
    parser.add_argument("--json", dest="out")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = {}
    for source in manifest["sources"]:
        if source["side"] != args.side:
            continue
        checkout = root / source["id"]
        if not (checkout / ".git").exists():
            print(f"{source['id']}: no checkout at {checkout}", file=sys.stderr)
            continue
        totals, per_class, co_wrap, exact, exact_co, skipped = measure(checkout, source)
        report[source["id"]] = {
            "commit": source["commit"],
            "selection_command": source["selection_command"],
            "totals": dict(totals),
            "per_class": {name: per_class[name] for name in CLASSES},
            "co_wrap": {name: co_wrap[name] for name in CLASSES},
            "exact_sets": dict(exact),
            "exact_sets_co_wrap": dict(exact_co),
            "skipped": skipped,
        }

    combined = collections.Counter()
    combined_co = collections.Counter()
    exact_all = collections.Counter()
    exact_all_co = collections.Counter()
    boundaries = suggested = suggested_co = 0
    for body in report.values():
        boundaries += body["totals"].get("boundaries", 0)
        suggested += body["totals"].get("suggested", 0)
        suggested_co += body["totals"].get("suggested_co_wrap", 0)
        for name in CLASSES:
            combined[name] += body["per_class"][name]
            combined_co[name] += body["co_wrap"][name]
        for key, count in body["exact_sets"].items():
            exact_all[key] += count
            exact_all_co[key] += body["exact_sets_co_wrap"][key]

    print(f"{boundaries} fused boundaries over {len(report)} sources")
    print(f"{'class':<24}{'n':>8}{'co-wrap':>9}")
    print(f"{'(none: suggested today)':<24}{suggested:>8}{suggested_co:>9}")
    for name in CLASSES:
        print(f"{name:<24}{combined[name]:>8}{combined_co[name]:>9}")
    print(f"\n{len(exact_all)} exact class sets, which are the sampling strata")
    print(f"{'n':>8}{'co-wrap':>9}  set")
    for key, count in exact_all.most_common():
        shown = "{" + key.replace(",", ", ") + "}" if key else "{} (suggested today)"
        print(f"{count:>8}{exact_all_co[key]:>9}  {shown}")

    for source_id, body in report.items():
        if body["skipped"]:
            print(f"{source_id}: {len(body['skipped'])} files skipped", file=sys.stderr)

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
