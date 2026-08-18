"""The complete diagnostics of every fixture, frozen so a refactor has to prove itself.

`tests/test_diagnostics.py` asserts exact suggestion dictionaries for the cases it names.
This holds every diagnostic of every fixture, suggestion values included,
which is what turns "no behaviour change" from a claim into a check.

Regenerate with `--update-golden`, and only when the change is one you intend.
A golden rewritten to match new output is a record of what the code does,
not a check that it does what it did.
"""

import json
import sys

import check_linefeeds
import pytest
from conftest import FIXTURES, REPO

sys.path.insert(0, str(REPO / "scripts"))

GOLDEN = REPO / "tests" / "diagnostics" / "fixtures.json"

# Three trees, because no one of them covers the suggestion path.
# `tests/fixtures` carries one file per language and per good/bad pair,
# and not one of its files produces a suggestion.
# `tests/extractor/in` carries the inputs the extractor golden already walks,
# which are the files with the most tangled markers.
# `tests/diagnostics/fixtures` is this golden's own,
# written so that every branch of the suggestion path appears in it:
# each leader a suggestion may be built from, each reason one is withheld,
# a stripped carrier, a standalone directive, a malformed one, and CRLF.
ROOTS = (
    FIXTURES,
    REPO / "tests" / "extractor" / "in",
    REPO / "tests" / "diagnostics" / "fixtures",
)


def corpus():
    """Every fixture, by its repository-relative path, in a stable order."""
    found = []
    for root in ROOTS:
        found += [path for path in root.rglob("*") if path.is_file()]
    return sorted(found, key=lambda path: str(path.relative_to(REPO)))


def diagnosed(path):
    text = path.read_text(encoding="utf-8")
    return check_linefeeds.diagnose(text, str(path.relative_to(REPO)))


def current():
    return {
        str(path.relative_to(REPO)): diagnosed(path)
        for path in corpus()
        if check_linefeeds.prose_stream(path.read_text(encoding="utf-8"), str(path))
        is not None
    }


def test_every_fixture_diagnoses_exactly_as_it_did(request):
    """One assertion over the whole tree, because a refactor moves things one does not expect."""
    got = current()
    if request.config.getoption("--update-golden"):
        GOLDEN.write_text(
            json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(got) == sorted(want)
    for name in sorted(want):
        assert got[name] == want[name], name


def test_the_golden_holds_suggestions_and_not_merely_their_presence():
    """The value is the part a refactor of the suggestion path can quietly change."""
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    suggested = [
        diagnostic
        for diagnostics in want.values()
        for diagnostic in diagnostics
        if "suggestion" in diagnostic
    ]
    assert suggested, "no fixture produces a suggestion, so the golden proves nothing"
    for diagnostic in suggested:
        assert diagnostic["suggestion"]["lines"]


@pytest.mark.parametrize("root", ROOTS, ids=lambda p: p.name)
def test_the_golden_covers_both_fixture_trees(root):
    """A tree that stops being walked would silently shrink the check."""
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    prefix = str(root.relative_to(REPO))
    assert any(name.startswith(prefix) for name in want)
