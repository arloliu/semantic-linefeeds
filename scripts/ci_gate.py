"""Decide a CI step's status from the documents file, never from an exit code.

    python3 scripts/ci_gate.py --fail-on fused[,wrap] DOCUMENTS.json

The checker's git modes exit 1 for a `wrap` the default gate lets pass,
and exit 1 equally for a provider failure the gate must not let pass,
so the exit code alone cannot say what happened.
The documents file can:
the Action runs one analysis into it and this reads the verdict out.

`long` is refused as a gate value rather than ignored (ADR-0001):
a configuration that asks for it is wrong,
and doing something else with it quietly would hide that.
Ships with the Action's own checkout and is invoked by path,
so it is deliberately not part of the installed package.
"""

import argparse
import json
import pathlib
import sys

GATEABLE = ("fused", "wrap")


def gate(documents, fail_on):
    """The kinds that fail the build, counted; the count is the exit."""
    counted = dict.fromkeys(fail_on, 0)
    for document in documents:
        for diagnostic in document["diagnostics"]:
            if diagnostic["kind"] in counted:
                counted[diagnostic["kind"]] += 1
    return counted


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-on", default="fused")
    parser.add_argument("documents")
    args = parser.parse_args(argv)

    fail_on = tuple(part.strip() for part in args.fail_on.split(",") if part.strip())
    bad = [kind for kind in fail_on if kind not in GATEABLE]
    if bad or not fail_on:
        print(
            f"ci_gate: fail-on takes a comma-separated list of fused and wrap "
            f"in either order, at least one; whitespace is trimmed, and empty "
            f"segments and duplicates are ignored; "
            f"long never fails a build (ADR-0001): got {args.fail_on!r}",
            file=sys.stderr,
        )
        return 64
    try:
        documents = json.loads(pathlib.Path(args.documents).read_text(encoding="utf-8"))
        if not isinstance(documents, list):
            raise ValueError("not a documents list")
        counted = gate(documents, fail_on)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ci_gate: cannot read {args.documents}: {exc}", file=sys.stderr)
        return 2
    failing = {kind: count for kind, count in counted.items() if count}
    if failing:
        summary = ", ".join(f"{count} {kind}" for kind, count in failing.items())
        print(f"ci_gate: failing the build on {summary}", file=sys.stderr)
        return 1
    print(f"ci_gate: nothing in ({', '.join(fail_on)}) — build passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
