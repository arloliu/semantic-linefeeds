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


# The rule that keeps a fused repair from stranding the sentence it splits off.
# Both surfaces carry it in their own words:
# the skill also spells out the order to apply the two kinds in, and the snippet states the join alone.
# Wording drift here is silent — the checker cannot tell a repair recipe from any other prose —
# so the sentences are pinned rather than merely present.
SKILL_CARRY_SENTENCE = (
    "join that text to the line below instead of leaving it standing alone."
)
SKILL_ORDER_SENTENCE = (
    "When one line draws both `fused` and `wrap`, rejoin before you split."
)
SNIPPET_CARRY_SENTENCE = "join it there rather than leaving it alone."


def test_the_skill_says_where_a_split_off_opening_belongs():
    assert SKILL_CARRY_SENTENCE in SKILL.read_text(encoding="utf-8")


def test_the_skill_gives_the_order_for_a_line_holding_both_kinds():
    assert SKILL_ORDER_SENTENCE in SKILL.read_text(encoding="utf-8")


def test_the_snippet_says_where_a_split_off_opening_belongs():
    assert SNIPPET_CARRY_SENTENCE in SNIPPET.read_text(encoding="utf-8")
