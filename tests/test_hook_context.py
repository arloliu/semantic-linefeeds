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


import subprocess
import sys

from conftest import SCRIPT


def codex_patch(*entries):
    body = "*** Begin Patch\n"
    for path, added in entries:
        body += f"*** Update File: {path}\n@@\n"
        body += "".join("+" + line + "\n" for line in added.splitlines())
    body += "*** End Patch"
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": body},
    })


NOTE_MARK = "approximate positions"


def test_a_located_patch_reports_real_line_numbers_without_the_note(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 10 + FUSED + "\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), FUSED)))
    assert result.returncode == 2
    assert "line 11" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_context_lines_disambiguate_a_repeated_addition(hook_dir):
    # The same added text occurs twice on disk;
    # hunk context makes the mapping unique where a bare addition run could not.
    doc = hook_dir / "doc.md"
    doc.write_text(FUSED + "\n\nunique anchor prose\n" + FUSED + "\n")
    patch = ("*** Begin Patch\n"
             f"*** Update File: {doc}\n"
             "@@\n"
             " unique anchor prose\n"
             f"+{FUSED}\n"
             "*** End Patch")
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    })
    result = run_cli(["--hook", "codex"], payload)
    assert result.returncode == 2
    assert "line 4" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_an_ambiguous_hunk_falls_back_with_the_note(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text(FUSED + "\n\nmiddle prose here\n\n" + FUSED + "\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), FUSED)))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr
    assert NOTE_MARK in result.stderr


def test_mixed_files_carry_the_note_once(hook_dir):
    real = hook_dir / "real.md"
    real.write_text("filler\n" * 5 + FUSED + "\n")
    result = run_cli(["--hook", "codex"], codex_patch(
        (str(real), FUSED), (str(hook_dir / "gone.md"), FUSED)))
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert result.stderr.count(NOTE_MARK) == 1


def test_a_clean_degraded_file_does_not_resurrect_the_note(hook_dir):
    # The degraded file's only content is clean,
    # so no snippet report survives filtering and the note must stay out.
    real = hook_dir / "real.md"
    real.write_text("filler\n" * 5 + FUSED + "\n")
    result = run_cli(["--hook", "codex"], codex_patch(
        (str(real), FUSED), (str(hook_dir / "gone.md"), "clean prose line")))
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_a_blank_only_addition_terminates_and_stays_silent(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("existing prose\n")
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": (
            "*** Begin Patch\n"
            f"*** Update File: {doc}\n"
            "@@\n+\n*** End Patch")},
    })
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook", "codex"],
        input=payload, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0


def test_an_interior_substring_hit_is_not_an_exact_hunk(hook_dir):
    # The added text exists on disk only inside a longer unchanged line,
    # so the mapping must degrade rather than own the wrong text.
    doc = hook_dir / "doc.md"
    doc.write_text("a longer line embedding " + FUSED + " in its middle\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), FUSED)))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr
    assert NOTE_MARK in result.stderr


def _codex_payload(patch):
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    })


def test_a_deleted_blank_line_owns_the_wrap_it_creates(hook_dir):
    # ADR-0005: a deletion collapses to a zero-width boundary that must still own the finding it creates.
    # wrap is model-visible only under the opt-in,
    # and it is advisory,
    # so the report is the JSON envelope on stdout.
    doc = hook_dir / "doc.md"
    doc.write_text("a line that ends mid-clause because it was\n"
                   "wrapped at a column.\n")
    patch = ("*** Begin Patch\n"
             f"*** Update File: {doc}\n"
             "@@\n"
             " a line that ends mid-clause because it was\n"
             "-\n"
             " wrapped at a column.\n"
             "*** End Patch")
    result = run_cli(["--hook", "codex"], _codex_payload(patch),
                     env={"SEMLF_EXPERIMENTAL_WRAP": "1"})
    assert result.returncode == 0
    body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[wrap] line 1" in body
    assert NOTE_MARK not in body


def test_a_deletion_after_a_retained_finding_does_not_own_it(hook_dir):
    # Red today: the current hook is deletion-blind and emits nothing at all for a deletion-only patch.
    # The corrected mapping owns the new wrap between the neighbors
    # and delivers it under the opt-in,
    # while the boundary sits past the retained terminator and so does not touch the unchanged blocking fused finding,
    # whose ownership runs to the retained line's content end.
    # A boundary one code point early owns that fused finding too and turns this report blocking
    # — three behaviors, one assertion set.
    doc = hook_dir / "doc.md"
    doc.write_text("One sentence here. Ok\nfollowing prose line\n")
    patch = ("*** Begin Patch\n"
             f"*** Update File: {doc}\n"
             "@@\n"
             " One sentence here. Ok\n"
             "-\n"
             "*** End Patch")
    result = run_cli(["--hook", "codex"], _codex_payload(patch),
                     env={"SEMLF_EXPERIMENTAL_WRAP": "1"})
    assert result.returncode == 0
    body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[wrap] line 1" in body
    assert "fused" not in body


def test_a_deletion_closing_a_hunk_at_eof_terminates_cleanly(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_bytes(b"closing prose line stands alone")  # no trailing newline
    patch = ("*** Begin Patch\n"
             f"*** Update File: {doc}\n"
             "@@\n"
             " closing prose line stands alone\n"
             "-\n"
             "*** End Patch")
    result = run_cli(["--hook", "codex"], _codex_payload(patch))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_disjoint_runs_in_a_fallback_hunk_do_not_merge(hook_dir):
    # One hunk, two "+" runs split by a context line.
    # The file does not exist, so the snapshot path is unavailable, and the hunk falls back to the added-text check without ever needing to locate context.
    # Run-granularity joining keeps the two runs as separate paragraphs, so neither line's ending is judged against the other's start.
    # Joining the whole hunk with a bare "\n" instead would glue them into one paragraph and fabricate a wrap finding neither run has alone.
    doc = hook_dir / "gone.md"
    patch = ("*** Begin Patch\n"
             f"*** Update File: {doc}\n"
             "@@\n"
             " unrelated context one\n"
             "+This line ends without punctuation\n"
             " unrelated context two\n"
             "+continues awkwardly here.\n"
             "*** End Patch")
    # wrap is withheld by default;
    # opt in so a fabricated wrap would actually surface instead of being silently filtered either way.
    result = run_cli(["--hook", "codex"], _codex_payload(patch),
                     env={"SEMLF_EXPERIMENTAL_WRAP": "1"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""
