import json

import pytest
from conftest import REPO

import check_linefeeds

IN_DIR = REPO / "tests" / "extractor" / "in"
OUT_DIR = REPO / "tests" / "extractor" / "out"


def extract(path):
    stream = check_linefeeds.prose_stream(path.read_text(encoding="utf-8"), str(path))
    assert stream is not None, f"{path} must be a target file type"
    return [{"line": n, "prose": p} for n, _raw, p in stream if p is not None]


@pytest.mark.parametrize("in_path", sorted(IN_DIR.iterdir()), ids=lambda p: p.name)
def test_extractor_golden(in_path, request):
    golden = OUT_DIR / (in_path.stem + ".json")
    got = extract(in_path)
    if request.config.getoption("--update-golden"):
        golden.write_text(json.dumps(got, indent=2) + "\n", encoding="utf-8")
    assert got == json.loads(golden.read_text(encoding="utf-8"))
