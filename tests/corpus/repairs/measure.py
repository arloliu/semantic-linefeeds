"""Count the fused population by the classes that withhold its suggestion.

    python3 tests/corpus/repairs/measure.py <checkout-root> [--json <out>]

The plan for this corpus chose its strata and its per-stratum size from these counts,
so the instrument that produced them is committed rather than described.
`qualify.py` exists for the same reason:
a number nobody can recompute is a number the next reader has to take on trust.

Two things separate this from a plain run of the checker.

The population is the manifest's own selection command, through `files_of`,
and not a walk of every file with a checked suffix.
A walk pulls in tests and vendored code the draw will never see.

One unit is one boundary, not one line.
`diagnose` emits a diagnostic per `FUSED_RE` match and puts the same full prose line in each,
so classifying from `FUSED_RE.search(prose)` would read every boundary on a line as the first one.

The classes are the detector's own.
This file used to recompute them from the excerpt and the anchor,
which meant reconstructing the judged raw line
and inferring whether a suppression carrier had come off it.
That inference was the one number here that could not be proved.
`diagnose(..., withholding=True)` reports what the detector decided,
so there is nothing left to reconstruct,
and every count below is now measured rather than partly inferred.
The counts did not move when it changed,
which is what says the inference had been right.

Nothing here reads a suggestion.

To reproduce the pinned output,
clone the three calibration sources into one root at the commits `manifest.json` declares,
and point this at that root.
`tests/test_corpus_repairs.py` checks what the pinned output claims,
which is the part that goes stale when the detector moves underneath it.
"""

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
TESTS = HERE.parent.parent.parent
REPO = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds as clf  # noqa: E402
from corpus_harness import corpus_text, exact_set_key, files_of  # noqa: E402

MANIFEST = TESTS / "corpus" / "manifest.json"

# The names are the detector's, not a copy of them.
# A copy would drift the day a class is added, and this file is the plan's evidence.
CLASSES = clf.WITHHOLDING_CLASSES


def measure(root, source):
    per_class = collections.Counter()
    co_wrap = collections.Counter()
    exact = collections.Counter()
    exact_co_wrap = collections.Counter()
    totals = collections.Counter()
    skipped = []

    for name in files_of(source, root):
        try:
            text = corpus_text(root / name)
        except (OSError, UnicodeDecodeError) as problem:
            skipped.append(f"{name}: {problem}")
            continue
        try:
            diagnostics = clf.diagnose(text, name, withholding=True)
        except (
            Exception
        ) as problem:  # a file the extractor cannot read is not a measurement
            skipped.append(f"{name}: {problem}")
            continue

        wrapped = {d["line"] for d in diagnostics if d["kind"] == "wrap"}
        # One diagnostic per match, so one diagnostic is one unit.
        for diagnostic in diagnostics:
            if diagnostic["kind"] != "fused":
                continue
            totals["boundaries"] += 1
            found = diagnostic["withheld_by"]
            also = diagnostic["line"] in wrapped
            # The exact set is the sampling stratum: exact sets partition the population,
            # while class membership overlaps and cannot carry an unbiased marginal on its own.
            key = exact_set_key(found)
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
