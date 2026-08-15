"""tests/test_judgment_texts.py — the judgment-layer surfaces carry the pinned wording."""

from check_linefeeds import AGENT_SUPPRESSION_NOTE
from conftest import REPO

SNIPPET = REPO / "adapters" / "agentsmd" / "SNIPPET.md"
SKILL = REPO / "skills" / "semantic-linefeeds" / "SKILL.md"

# The sentence that ends the bounded-disagreement loop.
# The two files phrase the sentence introducing it differently,
# but this closing sentence is worded identically in both.
# Deleting the whole loop-stop rule while keeping the heading and the suppression sentence would otherwise leave every existing assertion green.
LOOP_STOP_SENTENCE = (
    "stop retrying and surface the disagreement to the user instead of "
    "rewriting correct prose again."
)


def test_the_snippet_carries_the_verbatim_suppression_instruction():
    assert AGENT_SUPPRESSION_NOTE in SNIPPET.read_text(encoding="utf-8")


def test_the_skill_carries_the_verbatim_suppression_instruction():
    assert AGENT_SUPPRESSION_NOTE in SKILL.read_text(encoding="utf-8")


def test_the_snippet_carries_the_loop_stop_sentence():
    assert LOOP_STOP_SENTENCE in SNIPPET.read_text(encoding="utf-8")


def test_the_skill_carries_the_loop_stop_sentence():
    assert LOOP_STOP_SENTENCE in SKILL.read_text(encoding="utf-8")
