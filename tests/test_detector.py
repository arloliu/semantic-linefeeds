import pytest
from conftest import ALLOWED_SUFFIXES, FIXTURES, load_fixture

import check_linefeeds

ALL_FIXTURES = sorted(p for p in FIXTURES.rglob("*") if p.is_file())


def test_fixture_corpus_is_intentional():
    for path in ALL_FIXTURES:
        assert path.suffix in ALLOWED_SUFFIXES, f"unexpected fixture type: {path}"
        assert path.name.startswith(("bad_", "good_", "advisory_")), \
            f"fixture name must declare intent: {path}"


@pytest.mark.parametrize("path", ALL_FIXTURES,
                         ids=lambda p: f"{p.parent.name}/{p.name}")
def test_fixture(path):
    text, expected = load_fixture(path)
    got = [(f[0], f[1]) for f in check_linefeeds.check(text, str(path))]
    assert sorted(got) == sorted(expected)


def test_good_fixtures_have_no_markers():
    for path in ALL_FIXTURES:
        if path.name.startswith("good_"):
            _, expected = load_fixture(path)
            assert expected == [], f"{path} is a good_ fixture but carries markers"
