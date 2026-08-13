"""tests/test_judgment_texts.py — the judgment-layer surfaces carry the pinned wording."""
from conftest import REPO
from check_linefeeds import AGENT_SUPPRESSION_NOTE

SNIPPET = REPO / "adapters" / "agentsmd" / "SNIPPET.md"
SKILL = REPO / "skills" / "semantic-linefeeds" / "SKILL.md"


def test_the_snippet_carries_the_verbatim_suppression_instruction():
    assert AGENT_SUPPRESSION_NOTE in SNIPPET.read_text(encoding="utf-8")


def test_the_skill_carries_the_verbatim_suppression_instruction():
    assert AGENT_SUPPRESSION_NOTE in SKILL.read_text(encoding="utf-8")
