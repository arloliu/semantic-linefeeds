"""Context-aware hooks: real line numbers when the file can be read and mapped."""

import json
import shutil
import uuid

import pytest

from conftest import REPO, run_cli
from check_linefeeds import skip_path, _locate_unique, _read_snapshot

FUSED = "One sentence here. Another sentence follows."


@pytest.fixture
def hook_dir():
    # Not under the platform temp directory and free of SKIP_DIRS
    # components, so skip_path can never silently blank these tests.
    scratch = REPO / f"hookscratch-{uuid.uuid4().hex}"
    scratch.mkdir()
    assert not skip_path(str(scratch / "doc.md"))
    try:
        yield scratch
    finally:
        shutil.rmtree(scratch)


def claude_edit(path, new_string, replace_all=False):
    tool_input = {"file_path": str(path), "new_string": new_string}
    if replace_all:
        tool_input["replace_all"] = True
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": tool_input,
    })


def claude_write(path, content):
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": content},
    })


def test_an_edit_reports_real_file_line_numbers(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 30 + FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 31" in result.stderr
    assert "of your edit" not in result.stderr
    assert "text just written" not in result.stderr


def test_an_ambiguous_edit_falls_back_to_the_snippet_report(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text(FUSED + "\n\nquiet middle prose\n\n" + FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr


def test_a_replace_all_edit_takes_the_snippet_fallback(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 30 + FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED, replace_all=True))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr


def test_a_missing_file_still_reports_the_edit(hook_dir):
    result = run_cli(["--hook", "claude"], claude_edit(hook_dir / "gone.md", FUSED))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr


def test_an_undecodable_file_degrades_to_the_snippet_report(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_bytes(FUSED.encode() + b"\n\xff\xfe broken\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr


def test_a_crlf_file_maps_an_lf_payload_to_real_lines(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_bytes(b"filler\r\n" * 4 + FUSED.encode() + b"\r\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 5" in result.stderr
    assert "of your edit" not in result.stderr


def test_a_write_reports_whole_file_line_numbers(hook_dir):
    doc = hook_dir / "doc.md"
    content = "clean opening prose\n\n" + FUSED + "\n"
    doc.write_text(content)
    result = run_cli(["--hook", "claude"], claude_write(doc, content))
    assert result.returncode == 2
    assert "line 3" in result.stderr
    assert "of your edit" not in result.stderr


def test_an_empty_new_string_is_an_explicit_no_op(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text(FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, ""))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_a_suppressed_finding_never_reaches_the_write_span_path(hook_dir):
    # Pins that the Write whole-file span still flows through suppression.
    doc = hook_dir / "doc.md"
    content = FUSED + " <!-- semlf-ignore fused -->\n"
    doc.write_text(content)
    result = run_cli(["--hook", "claude"], claude_write(doc, content))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_locate_unique_rejects_empty_missing_and_ambiguous():
    from check_linefeeds import _locate_unique
    assert _locate_unique("abc", "") is None
    assert _locate_unique("abc", "zzz") is None
    assert _locate_unique("aaaa", "aaa") is None  # overlap counts as ambiguous
    assert _locate_unique("abcabc", "abc") is None
    assert _locate_unique("xabcx", "abc") == {"start": 1, "end": 4}


def _shifted(stat, **changes):
    import types
    fields = {"st_dev": stat.st_dev, "st_ino": stat.st_ino,
              "st_size": stat.st_size, "st_mtime_ns": stat.st_mtime_ns}
    fields.update(changes)
    return types.SimpleNamespace(**fields)


def test_read_snapshot_degrades_when_the_file_changes_mid_read(hook_dir, monkeypatch):
    # The second fstat sees a moved mtime: an in-place write raced the read.
    import check_linefeeds
    from check_linefeeds import _read_snapshot
    doc = hook_dir / "doc.md"
    doc.write_text("stable text\n")
    real_fstat = check_linefeeds.os.fstat
    calls = []

    def racing_fstat(fd):
        s = real_fstat(fd)
        calls.append(s)
        return _shifted(s, st_mtime_ns=s.st_mtime_ns + 1) if len(calls) == 2 else s

    monkeypatch.setattr(check_linefeeds.os, "fstat", racing_fstat)
    assert _read_snapshot(str(doc)) is None


def test_read_snapshot_degrades_on_an_atomic_replacement(hook_dir, monkeypatch):
    # The final path stat names a different inode: the file was swapped
    # with one of identical size and restored mtime.
    import check_linefeeds
    from check_linefeeds import _read_snapshot
    doc = hook_dir / "doc.md"
    doc.write_text("stable text\n")
    real_stat = check_linefeeds.os.stat

    def swapped_stat(p, *a, **kw):
        s = real_stat(p, *a, **kw)
        return _shifted(s, st_ino=s.st_ino + 1)

    monkeypatch.setattr(check_linefeeds.os, "stat", swapped_stat)
    assert _read_snapshot(str(doc)) is None
