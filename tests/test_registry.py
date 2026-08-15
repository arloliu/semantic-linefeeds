"""tests/test_registry.py — one registry, no second mapping anywhere."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import manifest, registry

EXPECTED_IDS = [
    "checker",
    "readme",
    "codex-hook-template",
    "codex-skill",
    "opencode-plugin",
    "opencode-checker",
    "codex-setup-skill",
    "opencode-setup-skill",
    "opencode-setup-command",
    "agentsmd-snippet",
]


def test_rows_carry_the_designed_ids_in_apply_order():
    assert [r.id for r in registry.ROWS] == EXPECTED_IDS
    assert [r.order for r in registry.ROWS] == sorted(r.order for r in registry.ROWS)


def test_member_paths_follow_the_id():
    for row in registry.ROWS:
        assert row.member == f"semlf/payloads/{row.id}"


def test_owners_match_the_design_table():
    owners = {r.id: r.owner for r in registry.ROWS}
    assert owners == {
        "checker": "codex",
        "readme": "codex",
        "codex-hook-template": "codex",
        "codex-skill": "codex",
        "opencode-plugin": "opencode",
        "opencode-checker": "opencode",
        "codex-setup-skill": "codex",
        "opencode-setup-skill": "opencode",
        "opencode-setup-command": "opencode",
        "agentsmd-snippet": "agentsmd",
    }


def test_the_setup_skill_ships_once_per_target_from_one_source():
    """Per-target rows, single source: the property that keeps them from drifting.

    Two destinations exist because uninstalling one target must not remove the other target's file.
    They must nonetheless install identical bytes,
    so the source path is asserted equal rather than merely present —
    a second spelled-out path here is exactly how one root would keep shipping last release's skill.
    """
    setup_skills = [row for row in registry.ROWS if row.id.endswith("-setup-skill")]
    assert {row.id for row in setup_skills} == {
        "codex-setup-skill",
        "opencode-setup-skill",
    }
    assert {row.source for row in setup_skills} == {registry.SETUP_SKILL_SOURCE}
    assert len({row.member for row in setup_skills}) == 2


def test_the_two_no_record_rows_are_marked():
    unrecorded = {r.id for r in registry.ROWS if not r.recorded}
    assert unrecorded == {"codex-hook-template", "agentsmd-snippet"}


def test_identity_marks_exactly_the_digest_compared_payloads():
    assert {r.id for r in registry.ROWS if r.identity} == {
        "checker",
        "readme",
        "opencode-checker",
    }


def test_known_provenance_names_are_exactly_the_recorded_rows_plus_cli():
    """The drift channel between the two lists, closed.

    A recorded row without a `manifest.KNOWN` entry installs but cannot record provenance,
    and a KNOWN name without a row is a provenance slot nothing ever writes.
    Neither shows up as a test failure anywhere else,
    so adding a row and forgetting the other list is caught here rather than in the field.
    `cli` is the one deliberate asymmetry: it is installed by building a zipapp, not by copying a payload row.
    """
    recorded = {row.id for row in registry.ROWS if row.recorded}
    assert set(manifest.KNOWN) == {"cli"} | recorded


def test_every_consumer_field_is_complete(monkeypatch, tmp_path):
    """The no-second-mapping invariant:
    every recorded single-file row resolves a destination and renders bytes from the one table.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    data_dir = tmp_path / "data" / "semlf"
    for row in registry.ROWS:
        if row.recorded:
            assert callable(row.dest), row.id
            assert row.dest() is not None, row.id
            assert callable(row.render), row.id
            assert isinstance(row.render(data_dir), bytes), row.id
        elif row.id == "codex-hook-template":
            assert row.dest() is not None
            assert row.render is None
        else:  # agentsmd-snippet: user-named, never derived
            assert row.dest is None and row.render is None


def test_render_refuses_a_none_data_dir():
    with pytest.raises(ValueError):
        registry.render_codex_skill(None)
    with pytest.raises(ValueError):
        registry.render_codex_hook_entry(None)


def test_payload_bytes_serves_canonical_bytes_in_a_checkout():
    assert (
        registry.payload_bytes("checker")
        == (REPO / "scripts" / "check_linefeeds.py").read_bytes()
    )
    assert (
        registry.payload_bytes("opencode-checker")
        == (REPO / "scripts" / "check_linefeeds.py").read_bytes()
    )
    assert registry.payload_bytes("readme") == (REPO / "README.md").read_bytes()


def test_stage_payloads_places_every_member(tmp_path):
    registry.stage_payloads(tmp_path, repo=REPO)
    for row in registry.ROWS:
        staged = tmp_path / Path(*row.member.split("/"))
        assert staged.read_bytes() == (REPO / row.source).read_bytes()


def test_payload_bytes_prefers_a_staged_dir_beside_the_module(tmp_path, monkeypatch):
    # Simulate a wheel install: copy the package and stage payloads beside it.
    pkg = tmp_path / "site" / "semlf"
    pkg.mkdir(parents=True)
    for src in (REPO / "cli" / "semlf").glob("*.py"):
        (pkg / src.name).write_bytes(src.read_bytes())
    registry.stage_payloads(tmp_path / "site", repo=REPO)
    import subprocess
    import sys as _sys

    code = (
        "import sys; sys.path.insert(0, {!r}); "
        "from semlf import registry; "
        "sys.stdout.buffer.write(registry.payload_bytes('checker'))".format(
            str(tmp_path / "site")
        )
    )
    out = subprocess.run([_sys.executable, "-c", code], capture_output=True)
    assert out.returncode == 0
    assert out.stdout == (REPO / "scripts" / "check_linefeeds.py").read_bytes()


def test_render_codex_hook_entry_substitutes_exactly_once(tmp_path):
    entry = registry.render_codex_hook_entry(tmp_path / "data" / "semlf")
    assert entry["matcher"] == "apply_patch"
    command = entry["hooks"][0]["command"]
    assert command == (
        'python3 "%s" --hook codex'
        % (tmp_path / "data" / "semlf" / "check_linefeeds.py")
    )
    assert "__CHECKER__" not in command


def test_render_codex_skill_pins_all_three_rewrites(tmp_path):
    data_dir = tmp_path / "data" / "semlf"
    body = registry.render_codex_skill(data_dir)
    assert ('python3 "%s" --file <files>' % (data_dir / "check_linefeeds.py")) in body
    assert str(data_dir / "README.md") in body
    assert "CLAUDE_PLUGIN_ROOT" not in body
    assert "../../scripts/check_linefeeds.py" not in body
    assert "../../README.md" not in body


def test_a_wrong_match_count_fails_loud():
    with pytest.raises(registry.TransformError):
        registry._replace_exactly_once(
            "no match here", "__CHECKER__", "x", "codex hook template"
        )
    with pytest.raises(registry.TransformError):
        registry._replace_exactly_once("__X__ and __X__", "__X__", "x", "twice")
