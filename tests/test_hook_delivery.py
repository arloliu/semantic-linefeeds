"""The hook delivery contract: status comes from the kinds, transport from the status.

Every exit-0 assertion parses stdout as the host's protocol rather than searching it.
A test that greps for the advice cannot tell "delivered to the model"
from "written where the model never reads it",
and that distinction is the entire point of this contract.

The blocking assertions search stderr instead, which is correct there:
stderr is a text channel with no shape to parse,
and both hosts already show it to the model.
"""

from conftest import run_cli
import json

import pytest

# One text per row of the delivery matrix.
# Each is verified against check() by test_case_texts_produce_the_intended_kinds.
# A detector change that invalidates a case therefore fails loudly,
# rather than quietly turning one matrix row into a duplicate of another.
LONG_ONLY = (
    "This clause runs on and on well past the configured advisory threshold "
    "of one hundred and twenty characters, and the tail keeps going.\n"
)
FUSED_ONLY = "One sentence here. Another sentence follows.\n"
FUSED_PLUS_LONG = FUSED_ONLY + LONG_ONLY
WRAP_ONLY = "a line that ends mid-clause because it was\nwrapped at a column.\n"
FUSED_PLUS_WRAP = FUSED_ONLY + "\n" + WRAP_ONLY

AGENTS = ["claude", "codex"]

# The opt-in that puts `wrap` back in front of the model.
OPT_IN = {"SEMLF_EXPERIMENTAL_WRAP": "1"}


def claude_payload(text):
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/x/doc.md", "content": text},
    })


def codex_payload(text):
    body = "".join("+" + line + "\n" for line in text.splitlines())
    patch = ("*** Begin Patch\n*** Update File: doc.md\n@@\n"
             + body + "*** End Patch")
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    })


PAYLOAD_FOR = {"claude": claude_payload, "codex": codex_payload}


def deliver(agent, text, env=None):
    return run_cli(["--hook", agent], PAYLOAD_FOR[agent](text), env=env)


def advisory(result):
    """Return the model-visible advice from an exit-0 hook run.

    Fails the calling test unless stdout parses as the host's non-blocking protocol.
    Anything else is advice the model never sees.
    """
    payload = json.loads(result.stdout)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PostToolUse"
    return hook_output["additionalContext"]


def test_case_texts_produce_the_intended_kinds():
    import check_linefeeds

    def kinds(text):
        return {f[1] for f in check_linefeeds.check(text, "doc.md")}

    assert kinds(LONG_ONLY) == {"long"}
    assert kinds(FUSED_ONLY) == {"fused"}
    assert kinds(FUSED_PLUS_LONG) == {"fused", "long"}
    assert kinds(WRAP_ONLY) == {"wrap"}
    assert kinds(FUSED_PLUS_WRAP) == {"fused", "wrap"}


@pytest.mark.parametrize("agent", AGENTS)
def test_fused_blocks_on_stderr(agent):
    r = deliver(agent, FUSED_ONLY)
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_long_only_exits_zero_and_stays_model_visible(agent):
    r = deliver(agent, LONG_ONLY)
    assert r.returncode == 0
    context = advisory(r)
    assert "[long]" in context
    # An advisory that arrives on stderr at exit 0 is invisible in both hosts.
    assert r.stderr == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_fused_plus_long_is_one_blocking_report(agent):
    r = deliver(agent, FUSED_PLUS_LONG)
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[long]" in r.stderr
    # One combined report, not the blocking one plus an advisory copy.
    assert r.stderr.count("semantic-linefeeds:") == 1
    assert r.stdout == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_clean_text_emits_nothing_at_all(agent):
    r = deliver(agent, "One clean sentence.\n")
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_advisory_does_not_tell_the_model_to_fix_anything(agent):
    """A `long` finding's prescribed outcome may be to leave the line long.

    Opening its report with "Fix these" contradicts that instruction,
    which is why the closing line depends on the kinds present.
    """
    assert "Fix these" not in advisory(deliver(agent, LONG_ONLY))


@pytest.mark.parametrize("agent", AGENTS)
def test_wrap_alone_tells_the_model_nothing(agent):
    """The withdrawal.

    `wrap` is the kind the labeled corpus shows misfiring,
    so it leaves hook feedback entirely rather than being downgraded to advice.
    Silence is the point: advice the model must weigh still costs it attention.
    """
    r = deliver(agent, WRAP_ONLY)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_wrap_is_withheld_from_a_report_it_would_otherwise_share(agent):
    """A blocking report must not smuggle the withdrawn kind in beside the blocking one."""
    r = deliver(agent, FUSED_PLUS_WRAP)
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[wrap]" not in r.stderr


@pytest.mark.parametrize("agent", AGENTS)
def test_the_opt_in_brings_wrap_back_without_blocking(agent):
    r = deliver(agent, WRAP_ONLY, env=OPT_IN)
    assert r.returncode == 0
    assert "[wrap]" in advisory(r)
    assert r.stderr == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_the_opt_in_asks_for_a_judgment_rather_than_a_rewrite(agent):
    """`wrap` is under evaluation, and the wording has to say so.

    A false positive becomes a change to correct prose
    exactly when the model is told to fix a finding this release could not trust.
    """
    context = advisory(deliver(agent, WRAP_ONLY, env=OPT_IN))
    assert "Fix these" not in context
    assert "evaluation" in context


def test_a_file_audit_still_reports_wrap(tmp_path):
    """The withdrawal is about what the model is told, not about what the tool can see."""
    target = tmp_path / "doc.md"
    target.write_text(WRAP_ONLY, encoding="utf-8")
    r = run_cli(["--file", str(target)])
    assert r.returncode == 1
    assert "[wrap]" in r.stdout


def test_codex_advisory_keeps_the_approximate_position_note():
    """Codex line numbers are positions within the patch, not the file.

    The note travels with the findings,
    so moving the advisory to stdout must not leave it behind on stderr.
    """
    assert "approximate" in advisory(deliver("codex", LONG_ONLY))


def test_codex_multifile_advisory_arrives_as_one_object():
    """Two advisory files must not produce two JSON objects on stdout.

    Concatenated objects are not parseable JSON,
    so the host would drop the whole payload rather than render both.
    """
    patch = ("*** Begin Patch\n"
             "*** Update File: a.md\n@@\n" + "+" + LONG_ONLY
             + "*** Update File: b.md\n@@\n" + "+" + LONG_ONLY
             + "*** End Patch")
    r = run_cli(["--hook", "codex"], json.dumps({
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    }))
    assert r.returncode == 0
    context = advisory(r)
    assert "a.md" in context
    assert "b.md" in context


def test_codex_mixed_files_block_and_carry_the_advisory():
    """One file fused, another only long.

    The status is blocking, so everything travels on the blocking path;
    splitting the report across two streams would hide half of it.
    """
    patch = ("*** Begin Patch\n"
             "*** Update File: a.md\n@@\n" + "+" + FUSED_ONLY
             + "*** Update File: b.md\n@@\n" + "+" + LONG_ONLY
             + "*** End Patch")
    r = run_cli(["--hook", "codex"], json.dumps({
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
    }))
    assert r.returncode == 2
    assert r.stdout == ""
    assert "[fused]" in r.stderr
    assert "[long]" in r.stderr
