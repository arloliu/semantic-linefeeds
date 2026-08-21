"""Context-aware hooks: real line numbers when the file can be read and mapped."""

import json
import shutil
import uuid

import pytest
from check_linefeeds import (
    AGENT_SUPPRESSION_NOTE,
    _judgment_layer_present,
    _locate_unique,
    _looks_like_the_skill,
    _read_snapshot,
    skip_path,
)
from conftest import REPO, run_cli

FUSED = "One sentence here. Another sentence follows."


@pytest.fixture
def hook_dir():
    # Not under the platform temp directory and free of SKIP_DIRS components, so skip_path can never silently blank these tests.
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
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": tool_input,
        }
    )


def claude_write(path, content):
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(path), "content": content},
        }
    )


def test_an_edit_reports_real_file_line_numbers(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 30 + FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 31" in result.stderr
    assert "of your edit" not in result.stderr
    assert "text just written" not in result.stderr


def test_a_mapped_report_still_ends_with_the_agent_instruction(hook_dir):
    # test_hook_delivery.py's two constant-last tests both use degraded
    # (unmapped) payloads; this pins the same property for a MAPPED,
    # real-line-number report.
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 30 + FUSED + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, FUSED))
    assert result.returncode == 2
    assert "line 31" in result.stderr
    assert result.stderr.rstrip().endswith(AGENT_SUPPRESSION_NOTE)


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


def test_an_opencode_style_write_as_new_string_maps_to_the_file(hook_dir):
    doc = hook_dir / "doc.md"
    content = "clean opening prose\n\n" + FUSED + "\n"
    doc.write_text(content)
    result = run_cli(["--hook", "claude"], claude_edit(doc, content))
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

    assert _locate_unique("abc", "") is None
    assert _locate_unique("abc", "zzz") is None
    assert _locate_unique("aaaa", "aaa") is None  # overlap counts as ambiguous
    assert _locate_unique("abcabc", "abc") is None
    assert _locate_unique("xabcx", "abc") == {"start": 1, "end": 4}


def _shifted(stat, **changes):
    import types

    fields = {
        "st_dev": stat.st_dev,
        "st_ino": stat.st_ino,
        "st_size": stat.st_size,
        "st_mtime_ns": stat.st_mtime_ns,
    }
    fields.update(changes)
    return types.SimpleNamespace(**fields)


def test_read_snapshot_degrades_when_the_file_changes_mid_read(hook_dir, monkeypatch):
    # The second fstat sees a moved mtime: an in-place write raced the read.
    import check_linefeeds

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
    # The final path stat names a different inode:
    # the file was swapped with one of identical size and restored mtime.
    import check_linefeeds

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
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": body},
        }
    )


NOTE_MARK = "approximate positions"


def test_a_located_patch_reports_real_line_numbers_without_the_note(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 10 + FUSED + "\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), FUSED)))
    assert result.returncode == 2
    assert "line 11" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_a_move_to_rename_reports_the_destination_path(hook_dir):
    # A `*** Move to:` rename must re-key the hunk to the destination path, both for language dispatch and for what the report names.
    old_doc = hook_dir / "orig.md"
    new_doc = hook_dir / "renamed.md"
    new_doc.write_text("filler\n" * 10 + FUSED + "\n")
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {old_doc}\n"
        f"*** Move to: {new_doc}\n"
        "@@\n"
        f"+{FUSED}\n"
        "*** End Patch"
    )
    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )
    result = run_cli(["--hook", "codex"], payload)
    assert result.returncode == 2
    assert str(new_doc) in result.stderr
    assert str(old_doc) not in result.stderr
    assert "line 11" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_context_lines_disambiguate_a_repeated_addition(hook_dir):
    # The same added text occurs twice on disk;
    # hunk context makes the mapping unique where a bare addition run could not.
    doc = hook_dir / "doc.md"
    doc.write_text(FUSED + "\n\nunique anchor prose\n" + FUSED + "\n")
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " unique anchor prose\n"
        f"+{FUSED}\n"
        "*** End Patch"
    )
    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )
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
    result = run_cli(
        ["--hook", "codex"],
        codex_patch((str(real), FUSED), (str(hook_dir / "gone.md"), FUSED)),
    )
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert result.stderr.count(NOTE_MARK) == 1


def test_a_clean_degraded_file_does_not_resurrect_the_note(hook_dir):
    # The degraded file's only content is clean,
    # so no snippet report survives filtering and the note must stay out.
    real = hook_dir / "real.md"
    real.write_text("filler\n" * 5 + FUSED + "\n")
    result = run_cli(
        ["--hook", "codex"],
        codex_patch(
            (str(real), FUSED), (str(hook_dir / "gone.md"), "clean prose line")
        ),
    )
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert NOTE_MARK not in result.stderr


def test_a_blank_only_addition_terminates_and_stays_silent(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_text("existing prose\n")
    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    f"*** Begin Patch\n*** Update File: {doc}\n@@\n+\n*** End Patch"
                )
            },
        }
    )
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook", "codex"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
    )
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


def test_a_line_bounded_hit_beside_an_interior_one_still_maps_exactly(hook_dir):
    # The hunk body occurs twice: once as a complete line (the real hit)
    # and once as an interior substring of a longer, unrelated line.
    # An interior hit neither matches nor makes the real one ambiguous,
    # so the mapping must still be exact rather than degrading.
    doc = hook_dir / "doc.md"
    doc.write_text(
        "filler\n" * 3 + FUSED + "\n"
        "quiet middle prose\n"
        "a longer line embedding " + FUSED + " in its middle\n"
    )
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), FUSED)))
    assert result.returncode == 2
    assert "line 4" in result.stderr
    assert "line 1 of your edit" not in result.stderr
    assert NOTE_MARK not in result.stderr


def _codex_payload(patch):
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )


def test_a_deleted_blank_line_owns_the_wrap_it_creates(hook_dir):
    # ADR-0005: a deletion collapses to a zero-width boundary that must still own the finding it creates.
    # wrap is model-visible only under the opt-in,
    # and it is advisory,
    # so the report is the JSON envelope on stdout.
    doc = hook_dir / "doc.md"
    doc.write_text("a line that ends mid-clause because it was\nwrapped at a column.\n")
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " a line that ends mid-clause because it was\n"
        "-\n"
        " wrapped at a column.\n"
        "*** End Patch"
    )
    result = run_cli(
        ["--hook", "codex"], _codex_payload(patch), env={"SEMLF_EXPERIMENTAL_WRAP": "1"}
    )
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
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " One sentence here. Ok\n"
        "-\n"
        "*** End Patch"
    )
    result = run_cli(
        ["--hook", "codex"], _codex_payload(patch), env={"SEMLF_EXPERIMENTAL_WRAP": "1"}
    )
    assert result.returncode == 0
    body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "[wrap] line 1" in body
    assert "fused" not in body


def test_a_deletion_closing_a_hunk_at_eof_terminates_cleanly(hook_dir):
    doc = hook_dir / "doc.md"
    doc.write_bytes(b"closing prose line stands alone")  # no trailing newline
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " closing prose line stands alone\n"
        "-\n"
        "*** End Patch"
    )
    result = run_cli(["--hook", "codex"], _codex_payload(patch))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_a_true_eof_deletion_collapses_to_the_located_end(hook_dir, monkeypatch):
    # ADR-0005: a true-EOF deletion must collapse to located["end"].
    # A stray end + 1 would run one code point past the text.
    # The cleanliness test above tolerates either value,
    # since normalize_span accepts an out-of-range offset silently on an empty result.
    # This test captures the span diagnose actually receives.
    import io

    import check_linefeeds

    doc = hook_dir / "doc.md"
    snapshot_text = "closing prose line stands alone"  # no trailing newline
    doc.write_bytes(snapshot_text.encode())
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " closing prose line stands alone\n"
        "-\n"
        "*** End Patch"
    )
    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )

    real_diagnose = check_linefeeds.diagnose
    captured = []

    def recording_diagnose(text, path, spans=None):
        captured.append(spans)
        return real_diagnose(text, path, spans=spans)

    monkeypatch.setattr(check_linefeeds, "diagnose", recording_diagnose)
    monkeypatch.setattr(check_linefeeds.sys, "stdin", io.StringIO(payload))
    result = check_linefeeds.run_hook_codex()

    assert result == 0
    assert captured == [[{"at": len(snapshot_text)}]]


def test_disjoint_runs_in_a_fallback_hunk_do_not_merge(hook_dir):
    # One hunk, two "+" runs split by a context line.
    # The file does not exist, so the snapshot path is unavailable, and the hunk falls back to the added-text check without ever needing to locate context.
    # Run-granularity joining keeps the two runs as separate paragraphs, so neither line's ending is judged against the other's start.
    # Joining the whole hunk with a bare "\n" instead would glue them into one paragraph and fabricate a wrap finding neither run has alone.
    doc = hook_dir / "gone.md"
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {doc}\n"
        "@@\n"
        " unrelated context one\n"
        "+This line ends without punctuation\n"
        " unrelated context two\n"
        "+continues awkwardly here.\n"
        "*** End Patch"
    )
    # wrap is withheld by default;
    # opt in so a fabricated wrap would actually surface instead of being silently filtered either way.
    result = run_cli(
        ["--hook", "codex"], _codex_payload(patch), env={"SEMLF_EXPERIMENTAL_WRAP": "1"}
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_a_question_fused_edit_reports_a_suggested_replacement(hook_dir):
    # Claude, mapped: an exact span located in a real snapshot.
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 5 + "Stop now? Go on.\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, "Stop now? Go on."))
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert "Suggested replacement for line 6:" in result.stderr
    assert "    Stop now?" in result.stderr
    assert "    Go on." in result.stderr


def test_a_degraded_claude_edit_still_carries_the_suggestion(hook_dir):
    # Claude, degraded: the edit's text occurs twice in the file,
    # so the mapped branch cannot pick one and the snippet fallback fires.
    doc = hook_dir / "doc.md"
    fused = "Stop now? Go on."
    doc.write_text(fused + "\n\nmiddle prose\n\n" + fused + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, fused))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr
    assert "Suggested replacement for line 1 of your edit:" in result.stderr
    assert "    Stop now?" in result.stderr
    assert "    Go on." in result.stderr


def test_a_mapped_codex_patch_carries_the_suggestion(hook_dir):
    # Codex, mapped: the hunk locates exactly once in a real snapshot.
    doc = hook_dir / "doc.md"
    doc.write_text("filler\n" * 5 + "Stop now? Go on.\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), "Stop now? Go on.")))
    assert result.returncode == 2
    assert "line 6" in result.stderr
    assert "Suggested replacement for line 6:" in result.stderr
    assert "    Stop now?" in result.stderr
    assert "    Go on." in result.stderr


def test_a_degraded_codex_patch_still_carries_the_suggestion(hook_dir):
    # Codex, degraded: the added text occurs twice,
    # so the hunk cannot locate exactly and the joined-added-runs fallback fires.
    doc = hook_dir / "doc.md"
    fused = "Stop now? Go on."
    doc.write_text(fused + "\n\nmiddle prose here\n\n" + fused + "\n")
    result = run_cli(["--hook", "codex"], codex_patch((str(doc), fused)))
    assert result.returncode == 2
    assert "line 1 of your edit" in result.stderr
    assert NOTE_MARK in result.stderr
    assert "Suggested replacement for line 1 of your edit:" in result.stderr
    assert "    Stop now?" in result.stderr
    assert "    Go on." in result.stderr


def test_a_two_file_patch_names_the_file_in_each_suggestion_label(hook_dir):
    # Both files carry the same fused "?" addition on the same line number,
    # so a label that dropped the file name would make the two suggestion blocks indistinguishable.
    doc_a = hook_dir / "a.md"
    doc_b = hook_dir / "b.md"
    fused = "Stop now? Go on."
    doc_a.write_text(fused + "\n")
    doc_b.write_text(fused + "\n")
    result = run_cli(
        ["--hook", "codex"], codex_patch((str(doc_a), fused), (str(doc_b), fused))
    )
    assert result.returncode == 2
    assert f"Suggested replacement for line 1 of {doc_a}:" in result.stderr
    assert f"Suggested replacement for line 1 of {doc_b}:" in result.stderr


def test_a_paired_mapped_edit_labels_the_two_lines_it_replaces(hook_dir):
    # The window's sentence continues on line 7, so the replacement covers 6-7.
    doc = hook_dir / "doc.md"
    doc.write_text(
        "filler\n" * 5 + "Stop now? Go later to the\nplace we talked about.\n"
    )
    result = run_cli(
        ["--hook", "claude"], claude_edit(doc, "Stop now? Go later to the")
    )
    assert result.returncode == 2
    assert "Suggested replacement for lines 6-7:" in result.stderr
    assert "    Stop now?" in result.stderr
    assert "    Go later to the place we talked about." in result.stderr


def test_a_paired_degraded_edit_keeps_the_two_line_label_in_snippet_mode(hook_dir):
    doc = hook_dir / "doc.md"
    pair = "Stop now? Go later to the\nplace we talked about."
    doc.write_text(pair + "\n\nmiddle prose\n\n" + pair + "\n")
    result = run_cli(["--hook", "claude"], claude_edit(doc, pair))
    assert result.returncode == 2
    assert "Suggested replacement for lines 1-2 of your edit:" in result.stderr


def test_a_two_file_patch_names_the_file_in_a_two_line_label(hook_dir):
    doc_a = hook_dir / "a.md"
    doc_b = hook_dir / "b.md"
    pair = "Stop now? Go later to the\nplace we talked about."
    doc_a.write_text(pair + "\n")
    doc_b.write_text(pair + "\n")
    result = run_cli(
        ["--hook", "codex"], codex_patch((str(doc_a), pair), (str(doc_b), pair))
    )
    assert result.returncode == 2
    assert f"Suggested replacement for lines 1-2 of {doc_a}:" in result.stderr
    assert f"Suggested replacement for lines 1-2 of {doc_b}:" in result.stderr


def _write_skill_frontmatter(path, name="semantic-linefeeds"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: test fixture\n---\n\nBody.\n",
        encoding="utf-8",
    )


def test_judgment_layer_present_true_for_a_valid_home_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_skill_frontmatter(
        tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert _judgment_layer_present("codex") is True


def test_judgment_layer_present_finds_opencodes_own_skill(tmp_path, monkeypatch):
    """opencode keeps its copy under its config root, not beside Codex's (ADR-0018).

    Its plugin declares the codex transport for an apply_patch-shaped payload,
    so a probe that only looked under `.agents/skills` would report no judgment layer on a machine where one is installed and loadable,
    and the feedback would stay silent about a skill sitting right there.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    assert _judgment_layer_present("codex") is False
    _write_skill_frontmatter(
        tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert _judgment_layer_present("codex") is True


def test_judgment_layer_present_false_for_a_wrong_name_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_skill_frontmatter(
        tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md",
        name="something-else",
    )
    assert _judgment_layer_present("codex") is False


def test_judgment_layer_present_false_for_a_name_line_with_no_frontmatter(
    tmp_path, monkeypatch
):
    # The exact name line is present in the file's body,
    # but the file carries no frontmatter block at all --
    # a bare substring search would wrongly accept this file.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "This file mentions the skill name inline.\nname: semantic-linefeeds\n",
        encoding="utf-8",
    )
    assert _judgment_layer_present("codex") is False


def test_judgment_layer_present_false_for_an_undecodable_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(b"\xff\xfe not valid utf-8")
    assert _judgment_layer_present("codex") is False


def test_judgment_layer_present_false_when_the_candidate_path_is_a_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    skill_as_dir = tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill_as_dir.mkdir(parents=True)
    assert _judgment_layer_present("codex") is False


def test_judgment_layer_present_true_for_a_repo_local_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "unused-home"))
    monkeypatch.chdir(tmp_path)
    _write_skill_frontmatter(
        tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    )
    assert _judgment_layer_present("codex") is True


def test_judgment_layer_present_false_with_no_skill_anywhere(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert _judgment_layer_present("codex") is False


def test_judgment_layer_present_skips_the_home_probe_when_expanduser_is_unresolved(
    tmp_path, monkeypatch
):
    # `os.path.expanduser("~")` returns its input unchanged when it cannot resolve a home directory (no $HOME and no usable pwd entry);
    # simulate that directly rather than trying to reproduce it via the environment, since an unset $HOME still resolves through the passwd database on most systems this suite runs on.
    import check_linefeeds

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(check_linefeeds.os.path, "expanduser", lambda p: p)
    assert _judgment_layer_present("codex") is False


def test_looks_like_the_skill_rejects_a_truncated_closing_delimiter(tmp_path):
    # Byte 1024 completes "\n---", but byte 1025 is "X", not a newline:
    # the file reads "---X...", not a closing delimiter,
    # and the helper must not mistake the edge of its own read buffer for end of file.
    prefix = b"---\nname: semantic-linefeeds\n"
    pad = 1024 - len(prefix) - len(b"\n---")
    body = prefix + (b"a" * pad) + b"\n---" + b"X" + b"\ndescription: after\n---\n"
    assert len(body[:1024]) == 1024 and body[:1024].endswith(b"\n---")
    skill = tmp_path / "boundary.md"
    skill.write_bytes(body)
    assert _looks_like_the_skill(str(skill)) is False


def test_looks_like_the_skill_accepts_a_true_end_of_file_close(tmp_path):
    # The whole file is under 1025 bytes, so the read never truncates;
    # "\n---" at the very end of that short read is a genuine close.
    skill = tmp_path / "short.md"
    skill.write_bytes(b"---\nname: semantic-linefeeds\n---")
    assert _looks_like_the_skill(str(skill)) is True
