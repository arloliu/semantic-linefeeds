"""The compliant corpus: prose that is already correct and must draw no complaint.

This is the negative set.
Every file here follows the convention,
so any finding against one of them is a false positive by construction.

The gate asks what the model is actually told, rather than what `check()` returns.
Those differ: a kind can stay in `--file` audits while leaving hook feedback,
and a diagnostic nobody is shown costs nothing.
Each file goes through the hook the way a write would.
That keeps the gate honest as the set of reported kinds narrows.
"""

from conftest import run_cli
import json
import pathlib

import pytest

CORPUS = pathlib.Path(__file__).resolve().parent / "corpus"
COMPLIANT = CORPUS / "compliant"
RECORD = CORPUS / "known_false_positives.json"


def corpus_files():
    return sorted(p for p in COMPLIANT.rglob("*") if p.is_file())


def relative(path):
    return path.relative_to(COMPLIANT).as_posix()


def findings_for(path):
    """Every finding `check()` produces, as (line, kind) pairs."""
    import check_linefeeds

    text = path.read_text(encoding="utf-8")
    return [(n, k) for n, k, _, _ in check_linefeeds.check(text, str(path))]


def model_visible_output(path):
    """What a host would show the model after this file was written.

    Returns the empty string when the model is told nothing,
    which is the only acceptable result for a compliant file.
    """
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": path.read_text(encoding="utf-8")},
    })
    result = run_cli(["--hook", "claude"], payload)
    if result.returncode == 2:
        return result.stderr
    if result.stdout.strip():
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]
    return ""


def load_record():
    return {k: [tuple(pair) for pair in v]
            for k, v in json.loads(RECORD.read_text(encoding="utf-8")).items()}


def test_the_corpus_is_not_empty():
    """A gate over nothing passes for the wrong reason."""
    assert len(corpus_files()) >= 8


def test_every_corpus_file_is_accounted_for():
    """Adding a file without recording its status must not pass silently."""
    recorded = set(load_record())
    present = {relative(p) for p in corpus_files()}
    assert recorded <= present, f"recorded but missing from disk: {sorted(recorded - present)}"
    unrecorded = sorted(p for p in present - recorded if findings_for(COMPLIANT / p))
    assert not unrecorded, f"files with findings that the record does not mention: {unrecorded}"


def test_recorded_false_positives_have_not_changed():
    """The working gate.

    A case that was fixed is as worth knowing about as one that appeared.
    Both directions fail, and both name the file and the line.
    """
    record = load_record()
    appeared, disappeared = [], []
    for path in corpus_files():
        name = relative(path)
        current = set(findings_for(path))
        expected = set(record.get(name, []))
        appeared += [f"{name}:{n} [{k}]" for n, k in sorted(current - expected)]
        disappeared += [f"{name}:{n} [{k}]" for n, k in sorted(expected - current)]
    assert not appeared, (
        "new false positives against correct prose:\n  " + "\n  ".join(appeared))
    assert not disappeared, (
        "these were fixed; remove them from the record:\n  " + "\n  ".join(disappeared))


def gate_can_hear():
    """Whether hook mode still complains about prose known to be wrong."""
    return "[fused]" in model_visible_output(CORPUS / "control" / "fused.go")


def test_the_gate_can_still_hear_a_complaint():
    """The positive control for the gate below.

    Hook mode skips whole classes of path, the platform temp directory among them,
    so a checkout under that directory makes every corpus file invisible
    and the resulting silence certifies nothing.
    This fails loudly in that case rather than reading as a repaired detector.
    """
    assert gate_can_hear(), (
        "prose known to be wrong drew no complaint, so the gate below is measuring "
        "nothing; a checkout under the platform temp directory does exactly this")


def test_compliant_corpus_draws_no_complaint():
    """The goal this release exists to reach, and now reaches.

    Eleven findings against this corpus survive in `check()` and are recorded above.
    Every one of them is a `wrap`, which is the kind this release withholds from the model,
    so a person auditing a file still sees them and a model being written for does not.
    """
    if not gate_can_hear():
        pytest.skip("hook mode cannot see this checkout, so silence here would "
                    "read as a repair rather than as a blind gate")
    complaints = []
    for path in corpus_files():
        output = model_visible_output(path)
        if output:
            for line in output.splitlines():
                if line.lstrip().startswith("["):
                    complaints.append(f"{relative(path)}: {line.strip()}")
    assert not complaints, (
        "correct prose was complained about:\n  " + "\n  ".join(complaints))
