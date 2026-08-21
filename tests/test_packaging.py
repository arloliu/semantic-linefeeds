"""tests/test_packaging.py — the wheel ships the repo's own files, unforked."""

import json
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


import subprocess
import zipfile

sys.path.insert(0, str(REPO / "cli"))
from semlf import registry


def test_the_pyz_embeds_every_registry_member(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib

    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    with zipfile.ZipFile(pyz) as z:
        names = set(z.namelist())
        assert {r.member for r in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()


def test_pyz_required_members_cover_the_registry():
    import importlib

    sys.path.insert(0, str(REPO / "scripts"))
    install = importlib.import_module("install")
    assert {r.member for r in registry.ROWS} <= install.PYZ_REQUIRED_MEMBERS


def test_payload_bytes_reads_from_inside_a_zipapp(tmp_path):
    """The rendering source works from a pyz install, not only a checkout:
    the archive itself lands on sys.path via zipimport."""
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib

    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    code = (
        f"import sys; sys.path.insert(0, {str(pyz)!r}); "
        "from semlf import registry; "
        "sys.stdout.buffer.write(registry.payload_bytes('checker'))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == (REPO / "scripts" / "check_linefeeds.py").read_bytes()


def _setuptools_at_least_61():
    try:
        import setuptools

        return int(setuptools.__version__.split(".")[0]) >= 61
    except Exception:
        return False


def _pip_available():
    r = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True)
    return r.returncode == 0


WHEEL_PREREQS = pytest.mark.skipif(
    not (_setuptools_at_least_61() and _pip_available()),
    reason="wheel build needs pip and setuptools>=61",
)


# Skips guard only genuinely absent prerequisites, probed up front.
# Once a build starts, ANY backend failure is a test failure —
# a broken setup.py hook or a MANIFEST.in gap must never pass as a skip.
@WHEEL_PREREQS
def test_the_wheel_embeds_every_registry_member(tmp_path):
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(REPO),
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    wheels = list(tmp_path.glob("semlf-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as z:
        names = set(z.namelist())
        assert {r_.member for r_ in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()
    # Nothing packaging-only was left in the repository.
    assert not (REPO / "cli" / "semlf" / "payloads").exists()


def test_manifest_in_lists_every_registry_source():
    """The same gap the sdist test catches, named directly.

    That test proves the consequence by building an sdist and a wheel from it,
    which is slow and reports a MANIFEST.in omission as a wall of pip output.
    This one names the missing path,
    so a new registry row whose source was never packaged fails as one readable line instead.
    """
    sys.path.insert(0, str(REPO / "cli"))
    from semlf import registry

    included = {
        line.split(None, 1)[1].strip()
        for line in (REPO / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        if line.startswith("include ")
    }
    missing = sorted({row.source for row in registry.ROWS} - included)
    assert not missing, f"MANIFEST.in omits registry sources: {missing}"


@WHEEL_PREREQS
def test_a_wheel_built_from_the_sdist_carries_the_members(tmp_path):
    """MANIFEST.in must put every canonical payload source into the sdist,
    or a wheel built from it stages nothing."""
    r = subprocess.run(
        [sys.executable, "setup.py", "sdist", "--dist-dir", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    sdists = list(tmp_path.glob("semlf-*.tar.gz"))
    assert len(sdists) == 1
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(sdists[0]),
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(tmp_path / "from-sdist"),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    wheels = list((tmp_path / "from-sdist").glob("semlf-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as z:
        names = set(z.namelist())
        assert {row.member for row in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()


def test_the_distribution_identifiers_are_pinned():
    """The v1.0 identity contract: the names a user types or pins.

    Each of these names is a rename away from breaking an existing install command,
    so a rename must fail here first.
    """
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "semlf"' in pyproject
    assert 'requires-python = ">=3.9"' in pyproject
    assert "semlf = " in pyproject.split("[project.scripts]", 1)[1].split("[", 1)[0]

    hooks = (REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "- id: semlf" in hooks

    manifest = json.loads(
        (REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "semantic-linefeeds"
