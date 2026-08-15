"""tests/test_classify.py — every cell of the admission matrix, per axis."""

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import classify, manifest

RENDERED = b"current rendering\n"
VERSION = "0.7.0"


def entry_for(path, data, version):
    return {
        "path": str(path),
        "sha256": manifest.sha256_bytes(data),
        "version": version,
    }


def verdict(dest, entry=None, rendered=RENDERED, version=VERSION, force=False):
    return classify.classify_artifact(entry, dest, rendered, version, force)


# --- version ordering -------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0.7.0", (0, 7, 0)),
        ("1.0", (1, 0)),
        ("10", (10,)),
        ("0.7.0rc1", None),
        ("", None),
        ("1..2", None),
        ("-1.0", None),
        (None, None),
        ("a.b", None),
        ("²", None),
        ("٣.٧", None),
    ],
)
def test_versions_order_as_dot_separated_integer_tuples(text, expected):
    assert classify.parse_version(text) == expected


# --- object-state axis ------------------------------------------------------


def test_absent_writes(tmp_path):
    v = verdict(tmp_path / "a")
    assert (v.state, v.action) == ("absent", "write")


def test_symlink_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.symlink_to(tmp_path / "elsewhere")
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("symlink", "refuse")


def test_directory_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.mkdir()
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("directory", "refuse")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_special_file_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    os.mkfifo(dest)
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("special", "refuse")


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores permission bits"
)
def test_unreadable_file_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"content\n")
    dest.chmod(0o000)
    try:
        for force in (False, True):
            v = verdict(dest, force=force)
            assert (v.state, v.action) == ("unreadable", "refuse")
    finally:
        dest.chmod(0o644)


def test_oversized_file_is_unreadable_even_with_force(tmp_path, monkeypatch):
    """Over CLASSIFY_LIMIT reads as None through the guarded primitive,
    so the classifier must refuse it as unreadable, force or not."""
    dest = tmp_path / "a"
    dest.write_bytes(b"x" * 32)
    monkeypatch.setattr(manifest, "CLASSIFY_LIMIT", 16)
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("unreadable", "refuse")


# --- provenance axis (readable regular file) --------------------------------


def test_exact_rendering_adopts(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(RENDERED)
    v = verdict(dest)
    assert (v.state, v.action) == ("exact", "adopt")


@pytest.mark.parametrize("force", [False, True])
def test_force_does_not_change_the_permissive_cells(tmp_path, force):
    """The design table marks absent, exact, managed-older, and managed-equal
    as `same` under --force: pin all four both ways."""
    dest = tmp_path / "a"
    assert verdict(dest, force=force).action == "write"
    dest.write_bytes(RENDERED)
    assert verdict(dest, force=force).action == "adopt"
    dest.write_bytes(b"older managed bytes\n")
    e = entry_for(dest, b"older managed bytes\n", "0.6.0")
    assert verdict(dest, entry=e, force=force).action == "replace"
    dest.write_bytes(b"equal-version other build\n")
    e = entry_for(dest, b"equal-version other build\n", VERSION)
    assert verdict(dest, entry=e, force=force).action == "replace"


def test_managed_older_replaces_without_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"older bytes\n")
    e = entry_for(dest, b"older bytes\n", "0.6.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-older", "replace")


def test_managed_newer_refuses_then_forces_a_downgrade(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"newer bytes\n")
    e = entry_for(dest, b"newer bytes\n", "0.8.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-newer", "refuse")
    assert "newer than this artifact" in v.detail
    assert "--force" in v.detail
    forced = verdict(dest, entry=e, force=True)
    assert (forced.state, forced.action) == ("managed-newer", "replace")


def test_managed_equal_version_different_bytes_replaces(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"same version other build\n")
    e = entry_for(dest, b"same version other build\n", VERSION)
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-equal", "replace")


def test_managed_unorderable_refuses_then_forces(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"who knows\n")
    e = entry_for(dest, b"who knows\n", "v0.6-beta")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-unorderable", "refuse")
    assert "cannot order" in v.detail
    forced = verdict(dest, entry=e, force=True)
    assert forced.action == "replace"


def test_edited_refuses_then_forces_a_backup_replace(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"hand-patched\n")
    e = entry_for(dest, b"what was recorded\n", "0.6.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("edited", "refuse")
    forced = verdict(dest, entry=e, force=True)
    assert (forced.state, forced.action) == ("edited", "backup-replace")
    assert forced.snapshot == b"hand-patched\n"


def test_unrecorded_refuses_then_forces_a_backup_replace(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"no record of this\n")
    v = verdict(dest)
    assert (v.state, v.action) == ("unrecorded", "refuse")
    forced = verdict(dest, force=True)
    assert forced.action == "backup-replace"


def test_occupied_backup_slot_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"diverged\n")
    dest.with_name("a.bak").write_bytes(b"already here")
    forced = verdict(dest, force=True)
    assert forced.action == "refuse"
    assert ".bak" in forced.detail
