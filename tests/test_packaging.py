"""tests/test_packaging.py — the wheel ships the repo's own files, unforked."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import check_linefeeds


def _load():
    tomllib = pytest.importorskip("tomllib")
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def test_entry_point_targets_the_cli_main():
    assert _load()["project"]["scripts"]["semlf"] == "semlf.cli:main"


def test_version_is_dynamic_from_the_core():
    data = _load()
    assert "version" in data["project"]["dynamic"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "check_linefeeds.__version__"
    assert check_linefeeds.__version__


def test_wheel_carries_both_module_roots():
    st = _load()["tool"]["setuptools"]
    assert st["packages"] == ["semlf"]
    assert st["py-modules"] == ["check_linefeeds"]
    assert st["package-dir"]["semlf"] == "cli/semlf"
    assert st["package-dir"][""] == "scripts"


def test_python_floor_matches_the_core_contract():
    assert _load()["project"]["requires-python"] == ">=3.9"
