"""The hook delivery contract: status comes from the kinds, transport from the status.

Every exit-0 assertion parses stdout as the host's protocol rather than searching it.
A test that greps for the advice cannot tell "delivered to the model"
from "written where the model never reads it",
and that distinction is the entire point of this contract.

The blocking assertions search stderr instead, which is correct there:
stderr is a text channel with no shape to parse,
and both hosts already show it to the model.
"""

import json

import pytest
from conftest import run_cli

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

# One line carrying both kinds at once,
# which is the shape a column-wrapped comment takes when a sentence ends mid-line
# and the sentence after it runs off the end of that same line.
FUSED_AND_WRAP_ON_ONE_LINE = (
    "One sentence here. Another sentence follows mid-clause because it\n"
    "was wrapped at a column.\n"
)
# The same shape with an advisory kind standing where the blocking one stood.
LONG_AND_WRAP_ON_ONE_LINE = (
    "This clause runs on and on well past the configured advisory threshold "
    "of one hundred and twenty characters, and the tail keeps\n"
    "going past the column it was wrapped at.\n"
)

AGENTS = ["claude", "codex"]

# The opt-in that puts `wrap` back in front of the model.
OPT_IN = {"SEMLF_EXPERIMENTAL_WRAP": "1"}


def claude_payload(text):
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/x/doc.md", "content": text},
        }
    )


def codex_payload(text):
    body = "".join("+" + line + "\n" for line in text.splitlines())
    patch = "*** Begin Patch\n*** Update File: doc.md\n@@\n" + body + "*** End Patch"
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
        }
    )


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
    assert kinds(FUSED_AND_WRAP_ON_ONE_LINE) == {"fused", "wrap"}
    assert kinds(LONG_AND_WRAP_ON_ONE_LINE) == {"long", "wrap"}


def test_the_one_line_cases_put_both_kinds_on_the_same_line():
    """The exception these cases exercise is scoped to one line, not to one file.

    A case whose two kinds drifted onto separate lines would quietly become a second FUSED_PLUS_WRAP,
    and the test below would then pass without exercising anything.
    """
    import check_linefeeds

    def lines(text, kind):
        return {f[0] for f in check_linefeeds.check(text, "doc.md") if f[1] == kind}

    for text, blocking in [
        (FUSED_AND_WRAP_ON_ONE_LINE, "fused"),
        (LONG_AND_WRAP_ON_ONE_LINE, "long"),
    ]:
        assert lines(text, blocking) == lines(text, "wrap")
    assert not lines(FUSED_PLUS_WRAP, "fused") & lines(FUSED_PLUS_WRAP, "wrap")


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
    """A blocking report carries the withdrawn kind only for the line it blocks.

    The two findings sit on different lines here,
    so the wrap describes prose this edit is not rewriting and stays out of the report.
    """
    r = deliver(agent, FUSED_PLUS_WRAP)
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[wrap]" not in r.stderr


@pytest.mark.parametrize("agent", AGENTS)
def test_a_wrap_on_a_blocked_line_travels_with_it(agent):
    """A line that is already being rewritten has nothing left for the withdrawal to protect.

    Splitting a fused line whose closing sentence continues below strands that opening on a line of its own,
    and the wrap is the only finding that says the opening belongs with the line under it.
    Withholding it here buys no quiet, because the edit is blocked either way.
    """
    r = deliver(agent, FUSED_AND_WRAP_ON_ONE_LINE)
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[wrap]" in r.stderr


@pytest.mark.parametrize("agent", AGENTS)
def test_a_delivered_wrap_directs_the_repair_rather_than_adding_one(agent):
    """A blocking report says "Fix these", and the withdrawn kind it now carries is not a second thing to fix.

    Before the exception a blocking report could not contain this kind,
    so its wording never had to account for one.
    Left unsaid, the kind the corpus shows misfiring arrives as a bare instruction to change a line,
    which is the outcome the withdrawal was written to prevent.
    """
    r = deliver(agent, FUSED_AND_WRAP_ON_ONE_LINE)
    assert "rejoin before you split" in r.stderr
    assert "not that a second repair is due" in r.stderr
    assert "already ends at a real clause boundary" in r.stderr


@pytest.mark.parametrize("agent", AGENTS)
def test_a_blocking_report_carrying_no_wrap_is_worded_as_before(agent):
    """The added sentence belongs to the report that carries the withdrawn kind, and to no other."""
    r = deliver(agent, FUSED_ONLY)
    assert "Fix these in the block you just wrote" in r.stderr
    assert "rejoin before you split" not in r.stderr


@pytest.mark.parametrize("agent", AGENTS)
def test_a_wrap_beside_an_advisory_stays_withheld(agent):
    """Only a blocking finding corroborates a wrap.

    An advisory leaves the line standing as its author wrote it,
    so a wrap delivered beside one still risks sending the model at prose that was never wrong.
    """
    r = deliver(agent, LONG_AND_WRAP_ON_ONE_LINE)
    assert r.returncode == 0
    context = advisory(r)
    assert "[long]" in context
    assert "[wrap]" not in context


@pytest.mark.parametrize("agent", AGENTS)
def test_the_opt_in_brings_wrap_back_without_blocking(agent):
    r = deliver(agent, WRAP_ONLY, env=OPT_IN)
    assert r.returncode == 0
    assert "[wrap]" in advisory(r)
    assert r.stderr == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_the_opt_in_asks_for_a_judgment_rather_than_a_rewrite(agent):
    """`wrap` is under evaluation, and the wording has to say so.

    A false positive becomes a change to correct prose exactly when the model is told to fix a finding this release could not trust.
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


# Valid JSON that is not the payload shape either host documents.
# A hook that crashes on one of these fails closed,
# which is the failure mode a post-edit hook is least allowed to have.
MALFORMED = [
    "[1, 2]",
    '"a string"',
    "42",
    "null",
    "true",
    '{"tool_input": "not an object"}',
    '{"tool_input": {"file_path": 7}}',
    '{"tool_input": {"file_path": "a.md", "content": 7}}',
    '{"tool_name": "apply_patch", "tool_input": [1, 2]}',
    '{"tool_name": "apply_patch", "tool_input": {"command": 42}}',
]


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("payload", MALFORMED, ids=lambda p: p[:24])
def test_a_payload_of_the_wrong_shape_fails_open(agent, payload):
    """Parsing succeeded and the shape was still wrong, which is not the same case.

    The JSON guard already covers text that does not parse.
    Attribute access was reached unguarded, and raised,
    for text that parses into a list, a number, or an object whose fields hold the wrong type.
    """
    r = run_cli(["--hook", agent], payload)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert r.stderr == ""


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
    patch = (
        "*** Begin Patch\n"
        "*** Update File: a.md\n@@\n"
        + "+"
        + LONG_ONLY
        + "*** Update File: b.md\n@@\n"
        + "+"
        + LONG_ONLY
        + "*** End Patch"
    )
    r = run_cli(
        ["--hook", "codex"],
        json.dumps(
            {
                "tool_name": "apply_patch",
                "tool_input": {"command": patch},
            }
        ),
    )
    assert r.returncode == 0
    context = advisory(r)
    assert "a.md" in context
    assert "b.md" in context


def test_codex_mixed_files_block_and_carry_the_advisory():
    """One file fused, another only long.

    The status is blocking, so everything travels on the blocking path;
    splitting the report across two streams would hide half of it.
    """
    patch = (
        "*** Begin Patch\n"
        "*** Update File: a.md\n@@\n"
        + "+"
        + FUSED_ONLY
        + "*** Update File: b.md\n@@\n"
        + "+"
        + LONG_ONLY
        + "*** End Patch"
    )
    r = run_cli(
        ["--hook", "codex"],
        json.dumps(
            {
                "tool_name": "apply_patch",
                "tool_input": {"command": patch},
            }
        ),
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert "[fused]" in r.stderr
    assert "[long]" in r.stderr


from check_linefeeds import AGENT_JUDGMENT_NOTE, AGENT_SUPPRESSION_NOTE


def test_a_blocking_report_ends_with_the_instruction():
    for agent in AGENTS:
        result = deliver(agent, FUSED_ONLY)
        assert result.stderr.count(AGENT_SUPPRESSION_NOTE) == 1
        assert result.stderr.rstrip().endswith(AGENT_SUPPRESSION_NOTE)


def test_an_advisory_report_ends_with_the_instruction():
    for agent in AGENTS:
        result = deliver(agent, LONG_ONLY)
        assert advisory(result).rstrip().endswith(AGENT_SUPPRESSION_NOTE)


def test_a_degraded_codex_note_comes_before_the_instruction():
    # The delivery-test Codex payloads name files absent on disk,
    # so the report is degraded and carries the approximate-position note;
    # the instruction must still be the report's last text.
    result = deliver("codex", LONG_ONLY)
    body = advisory(result)
    assert "approximate positions" in body
    assert body.index("approximate positions") < body.index(AGENT_SUPPRESSION_NOTE)


def test_the_agent_instruction_wording_is_pinned():
    # The endswith/placement tests above import AGENT_SUPPRESSION_NOTE and assert against the constant itself,
    # so a rewording keeps them green.
    # This pins the literal text (scripts/check_linefeeds.py) so a rewording is caught here instead.
    assert AGENT_SUPPRESSION_NOTE == (
        "An agent never adds a suppression directive on its own authority: "
        "if you judge a finding to be a false positive, leave the text as it is "
        "and surface the disagreement to the user instead."
    )


def test_the_judgment_note_wording_is_pinned():
    assert AGENT_JUDGMENT_NOTE == (
        "Judge a finding before rewriting: if you consider it a false positive, or "
        "the same finding survives one repair attempt, stop retrying and surface "
        "the disagreement to the user instead of rewriting correct prose again."
    )


def test_a_blocking_report_carries_the_judgment_note_before_suppression():
    for agent in AGENTS:
        result = deliver(agent, FUSED_ONLY)
        body = result.stderr
        assert AGENT_JUDGMENT_NOTE in body
        assert body.index(AGENT_JUDGMENT_NOTE) < body.index(AGENT_SUPPRESSION_NOTE)


def test_an_advisory_report_carries_the_judgment_note_before_suppression():
    for agent in AGENTS:
        body = advisory(deliver(agent, LONG_ONLY))
        assert AGENT_JUDGMENT_NOTE in body
        assert body.index(AGENT_JUDGMENT_NOTE) < body.index(AGENT_SUPPRESSION_NOTE)


def test_claude_advisory_always_names_the_skill(tmp_path):
    r = deliver("claude", LONG_ONLY, env={"HOME": str(tmp_path)})
    assert "load the semantic-linefeeds skill" in advisory(r)


def test_codex_advisory_omits_the_skill_hint_without_an_installed_skill(
    tmp_path, monkeypatch
):
    # The probe also checks a cwd-relative candidate;
    # chdir into the empty tmp_path so that branch cannot accidentally see this repo's own working tree instead of the fixture being tested.
    monkeypatch.chdir(tmp_path)
    r = deliver("codex", LONG_ONLY, env={"HOME": str(tmp_path)})
    assert "load the semantic-linefeeds skill" not in advisory(r)


def test_codex_advisory_names_the_skill_when_one_is_installed(tmp_path, monkeypatch):
    # An installed-shape fixture, not a bare placeholder:
    # the probe requires real frontmatter naming the skill,
    # so a file that merely exists at the right path is not enough to satisfy it.
    skill = tmp_path / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: semantic-linefeeds\ndescription: test fixture\n---\n\nBody.\n",
        encoding="utf-8",
    )
    # Run from a skill-free directory so this positive result comes from the HOME probe, not from an incidental cwd-relative match.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    r = deliver("codex", LONG_ONLY, env={"HOME": str(tmp_path)})
    assert "load the semantic-linefeeds skill" in advisory(r)


def test_the_suggestion_block_precedes_the_judgment_note():
    r = deliver("claude", "Stop now! Go on.\n")
    assert r.returncode == 2
    body = r.stderr
    assert "Suggested replacement for line 1:" in body
    assert body.index("Suggested replacement for line 1:") < body.index(
        AGENT_JUDGMENT_NOTE
    )
    assert body.index(AGENT_JUDGMENT_NOTE) < body.index(AGENT_SUPPRESSION_NOTE)


def test_a_degraded_note_precedes_the_judgment_note():
    body = advisory(deliver("codex", LONG_ONLY))
    assert body.index("approximate positions") < body.index(AGENT_JUDGMENT_NOTE)
    assert body.index(AGENT_JUDGMENT_NOTE) < body.index(AGENT_SUPPRESSION_NOTE)
