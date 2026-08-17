# Detector Precision Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL —
> use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove three verified false positives from the shipped detector, stop `long` from arguing for breaks the reader does not need, and close the documentation gaps that make the tool look like it checked text it never examined.

**Architecture:**
Every change in Tasks 1–4 is a constant or a single predicate in `scripts/check_linefeeds.py`, and each one strictly *reduces* the finding set — the direction the project's precision-over-recall invariant permits without new evidence.
Tasks 5–8 are prose and skill edits that make shipped behaviour discoverable.
Tasks 9 and 10 both add findings — Task 9 by widening a gate, Task 10 by reporting every boundary on a line —
so each carries its own corpus check and each is gated on a fresh reviewer.

**Tech Stack:** Python 3.9+, stdlib only, `pytest`.
No new dependencies, and `scripts/check_linefeeds.py` stays one file.

**Spec:** [`tmp/2026-08-16-checker-improvements-and-readability/consolidated.md`](../../../tmp/2026-08-16-checker-improvements-and-readability/consolidated.md), with per-analyst detail in the four sibling reports in that directory.

## Global Constraints

- **The core stays one file.** `scripts/check_linefeeds.py`, Python 3.9+, stdlib imports only (`.agents/rules/100-project-map.md`). Every adapter depends on "copy one file, runs on bare python3".
- **Precision over recall.**
  A missed finding is acceptable; a false positive is a bug.
  A change that only removes findings needs no new labeled evidence,
  and a change that adds findings does.
- **Self-hosting.**
  Every Markdown file touched must pass `python3 scripts/check_linefeeds.py --file <files>` with zero `fused`/`wrap`.
  `long` findings are advisories to judge, not obey,
  and `tests/` is the sole exception.
- **Validation before any task is called done:** `python3 -m pytest tests/ -q`.
  Add `bun test adapters/opencode/` only if adapter TypeScript changed, which no task here does.
- **Commit messages carry no `Co-Authored-By` or attribution trailers.**
- **Run the linter before every commit.**
- **No suppression directives added on the tool's own authority** — that rule is what Task 6 documents, not something this plan may violate.

---

## Execution mode: inline vs sub-agent

The user asked which tasks warrant a sub-agent.
The criterion used:
a sub-agent earns its cost when a task is self-contained, has a clear test gate,
and either carries design risk that benefits from independent judgment
or would bloat the main thread with exploration.
Tasks that edit adjacent lines of the same file are cheaper inline,
because a sub-agent per task would serialize on the same file and re-derive the same context each time.

| Task | Mode | Why |
|---|---|---|
| 1–4 (detector constants and the `long` predicate) | **Inline** | Four edits inside 100 lines of one file, each with an existing parametrized test harness. A sub-agent per task would conflict on `scripts/check_linefeeds.py` and re-read the same constants four times. Cheaper and safer as one sequential inline batch with a commit per task. |
| 5–8 (README, SKILL.md, ROADMAP.md) | **Inline** | Prose edits that must match repo voice and pass the self-host checker. A sub-agent lacks the accumulated style context and would produce text needing rewrite anyway. |
| 9 (`wrap` lower-line gate) | **Sub-agent** | Widens a gate, so it adds findings and carries genuine false-positive risk. Wants an implementer who has not already argued for it, plus a corpus sweep before and after. Isolated to one predicate with a clear gate. |
| 11 (`BOUNDARY_HINT_RE` derivation) | **Inline** | One constant rebuilt from another, plus a message and its frozen contract. Small and mechanical, but it touches a pinned string, so it wants the same context as the other prose tasks. Runs after Task 3. |
| 10 (`fused` multi-boundary) | **Sub-agent** | Touches `diagnose()` control flow and interacts with suppression and with the `_fused_suggestion` single-match guard. Needs its own test sweep rather than a one-line edit. |

Tasks 1–8 run inline in dependency order.

**Tasks 9 and 10 must be dispatched sequentially, never in parallel.**
Both edit `diagnose()` within thirty lines of each other —
Task 10 at `:1302-1326` and Task 9 at `:1330-1342` —
so concurrent worktrees would conflict or clobber.
Run Task 10 first, since its ownership fix changes the lines Task 9 then reads.

---

## Task 1: WITHDRAWN — `al.` is not a false positive

**This task was removed during review — nothing is to be implemented here.**

The spec's FP-1 claimed `et al.` produces a blocking `fused` false positive,
and this task proposed adding `al` to `MID_SENTENCE_ABBREVIATIONS`.
An external review challenged it, and the challenge holds.

The two sentences the spec offered as evidence are genuinely two sentences:

| Line | Detector | Correct? |
|---|---|---|
| `The fix ships, per Smith et al. Next year we revise.` | `fused` | **Yes** — "The fix ships, per Smith et al." is a complete sentence and "Next year we revise." is another |
| `See Kernighan et al. The result holds.` | `fused` | **Yes** — same structure |
| `Smith et al. showed the result holds.` | *no finding* | **Yes** — mid-sentence use is followed by a lowercase word, which `FUSED_RE` already requires |
| `The Smith et al. Nature paper argues otherwise.` | `fused` | **No** — the only genuine false positive, and it needs a capitalised proper noun immediately after the citation |

`FUSED_RE` requires a following `[A-Z]` (`scripts/check_linefeeds.py:326`),
which already exempts the ordinary mid-sentence citation.
What remains splits in two:
cases where the abbreviation period really is the sentence period, where flagging is correct and suppressing would hide a real violation,
and the proper-noun case in the last row, where flagging is wrong.
No entry in this list can tell those apart, because both present the same characters to the rule.

The source comment states the governing test directly (`scripts/check_linefeeds.py:307-308`):
`etc.` and `resp.` are excluded from the exclusion list because "both commonly do end a sentence."
`al.` commonly ends a sentence too, so it belongs with them rather than with `vs.` and `cf.`,
which cannot end one.

Adding `al` would suppress the true positives above along with the false one.
How often each form occurs in real prose is not measured here,
and the withdrawal does not rest on a frequency claim — only on the fact that one exemption cannot separate the two uses.
The same reasoning withdraws `pp`, `fig`, `sec`, `ed`, and `trans`,
which were raised in the spec on the same mistaken basis.
A later review argued `pp`/`fig`/`sec` are safer than the rest and should land now;
measurement says otherwise, because their natural forms are followed by a digit,
which `FUSED_RE` never matches:

```
"See pp. 12-14 for the argument."   -> []
"Compare fig. 3 with the table."    -> []
"Read sec. 4 first."                -> []
```

There is no false positive to remove.

The genuine residual — an abbreviation followed by a capitalised proper noun mid-sentence —
is recorded as an open question in Task 8 rather than fixed by a global exemption,
because no entry in this list can distinguish the two uses.

---

## Task 2: full-width terminators in `OK_LINE_ENDERS`

A line ending `。` or `，` is read as unterminated, because `OK_LINE_ENDERS` holds no full-width punctuation.
When the next line opens on a lowercase ASCII word, `wrap` fires on correct text.
Mixed Chinese-English prose therefore draws a false positive at every language boundary.

This change only ever *removes* findings, so it cannot introduce a new false positive.

**Files:**
- Modify: `scripts/check_linefeeds.py:300`
- Test: `tests/test_precision.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `check_linefeeds.OK_LINE_ENDERS` gains full-width members.
  `line_ending(prose).endswith(OK_LINE_ENDERS)` at `scripts/check_linefeeds.py:1332` is the only consumer, and it needs no change.

- [x] **Step 1: Write the failing test**

Add to `tests/test_precision.py`, in a new section at the end of the abbreviations block:

```python
# --- full-width terminators -----------------------------------------------


def test_a_chinese_sentence_above_an_english_line_is_not_a_wrap():
    """A CJK terminator ends a line as surely as an ASCII one.

    Mixed-language prose is the norm in Chinese technical writing, so a
    boundary between a Chinese sentence and an English one is the common
    case rather than an edge case. Reading the CJK terminator as "no
    terminator" accuses correct text at every such boundary.
    """
    assert kinds("這是一個完整的句子。\nnext english line continues here.\n") == []
    assert kinds("這是列表的一項，\nnext item follows on its own line.\n") == []


def test_a_chinese_terminator_ends_a_go_comment_line_too():
    assert (
        kinds("package p\n\n// 這是列表，\n// next item\n", path="doc.go") == []
    )


def test_an_unterminated_chinese_line_above_an_english_one_still_wraps():
    """The other half: adding terminators must not bless every CJK line ending."""
    assert kinds("這是一個沒有標點結尾的句子\nnext english line continues here.\n") == [
        (1, "wrap")
    ]
```

- [x] **Step 2: Run the tests and confirm the first two fail**

Run: `python3 -m pytest tests/test_precision.py -v -k "chinese"`
Expected: `test_a_chinese_sentence_above_an_english_line_is_not_a_wrap` and `test_a_chinese_terminator_ends_a_go_comment_line_too` FAIL with `[(1, 'wrap')]`; `test_an_unterminated_chinese_line_above_an_english_one_still_wraps` already PASSES.

- [x] **Step 3: Add the full-width members**

In `scripts/check_linefeeds.py`, change line 300 from:

```python
OK_LINE_ENDERS = tuple(".!?;:,—-–)”\"'`")
```

to:

```python
# ASCII enders first, then their full-width counterparts.
# A CJK terminator ends a line as surely as an ASCII one,
# and without these a Chinese line above an English one reads as a severed clause —
# a false positive at every language boundary in mixed prose,
# which is the ordinary case in Chinese technical writing rather than an edge case.
# This is not CJK support: no kind gains the ability to analyze Chinese,
# the checker only stops accusing text it never understood.
OK_LINE_ENDERS = tuple(".!?;:,—-–)”\"'`" + "。！？；：，、）」』》】’")
```

- [x] **Step 4: Run the tests and confirm all three pass**

Run: `python3 -m pytest tests/test_precision.py -v -k "chinese"`
Expected: PASS.

- [x] **Step 5: Confirm the change only removes findings**

Run:

```bash
python3 scripts/check_linefeeds.py --json --file $(git ls-files '*.md' '*.py' | grep -v '^tests/') > /tmp/after.json
```

Compare the finding count against the same command run on `HEAD` in a second worktree.
Do not `git stash` — it sweeps unrelated working-tree state into the comparison.
Expected: the count is unchanged or lower, never higher.
This repo's prose is English, so unchanged is the likely result and is correct.

- [x] **Step 6: Run the full suite and commit**

Run: `python3 -m pytest tests/ -q`

```bash
git add scripts/check_linefeeds.py tests/test_precision.py
git commit -m "fix(detector): read a full-width terminator as ending a line

A line closing on 。 or ， was read as unterminated, so an English line
beneath it tripped wrap on correct text. Mixed Chinese-English prose puts
that boundary in ordinary paragraphs, not edge cases.

This is not CJK support. No kind gains the ability to analyze Chinese;
the checker only stops accusing text it never understood. The change can
only withhold findings, so it cannot introduce a false positive."
```

---

## Task 3: the missing subordinator family in `CONNECTORS`

`CONNECTORS` holds `until`, `while`, and `because` but not `after`, `since`, `once`, or `before`.
A correct semantic break before one of the missing subordinators is accused as a `wrap`.
Verified false positives: `after`, `since`, `once`, `before`, `whereas`, `whenever`, `whether` — seven words, seven reproductions.
`wherever`, `whereupon`, and `lest` were proposed and are **not** scheduled: no reproduction was produced for them,
and a set entry with no test behind it is one nobody can safely remove later.

ADR-0002's refutations (demonstratives, pro-forms, code tokens) do not reach plain subordinators.
`docs/ROADMAP.md:71` frames the remaining `wrap` work as "a positive-evidence test, or nothing";
this is neither — it is a negative-test repair that removes a measured class without adding a predicate.

**Files:**
- Modify: `scripts/check_linefeeds.py:275-297`
- Test: `tests/test_precision.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `check_linefeeds.CONNECTORS` grows from 21 to 28 members,
  consumed only at `scripts/check_linefeeds.py:1334`.

- [x] **Step 1: Write the failing test**

Add to `tests/test_precision.py`:

```python
# --- subordinators --------------------------------------------------------


# Only the words with a verified false positive behind them.
# "wherever", "whereupon", and "lest" are grammatically capable of opening a clause
# but had no reproduction, and an entry nothing tests is one nobody can remove safely.
SUBORDINATORS = [
    "after",
    "since",
    "once",
    "before",
    "whereas",
    "whenever",
    "whether",
]


@pytest.mark.parametrize("word", SUBORDINATORS)
def test_a_break_before_a_subordinator_is_not_a_wrap(word):
    """A subordinator opens a clause, so a line starting with one continues legitimately.

    The list already holds until, while, and because. The members below open a
    clause by the same grammar, and their absence accuses a correct break for
    no reason but list membership.
    """
    assert kinds(f"Close the session\n{word} the request finishes.\n") == []


@pytest.mark.parametrize("word", ["until", "while", "because", "although"])
def test_the_subordinators_that_already_passed_still_pass(word):
    assert kinds(f"Close the session\n{word} the request finishes.\n") == []
```

- [x] **Step 2: Run the test and confirm the new words fail**

Run: `python3 -m pytest tests/test_precision.py -v -k "subordinator"`
Expected: all seven `SUBORDINATORS` cases FAIL with `[(1, 'wrap')]`; the four already-present words PASS.

- [x] **Step 3: Extend the set**

In `scripts/check_linefeeds.py`, the `CONNECTORS` set at lines 275–297 currently ends:

```python
    "until",
    "if",
    "as",
}
```

Change that tail to:

```python
    "until",
    "if",
    "as",
    # The rest of the subordinator family.
    # The members above were collected as they came up rather than as a family,
    # so a correct break before "after" was accused where the same break before "until" passed.
    # Completing the family removes a measured false-positive class
    # without adding a predicate the detector has to be right about.
    "after",
    "since",
    "once",
    "before",
    "whereas",
    "whenever",
    "whether",
}
```

- [x] **Step 4: Run the tests and confirm all pass**

Run: `python3 -m pytest tests/test_precision.py -v -k "subordinator"`
Expected: PASS, all eleven cases.

- [x] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.
If a corpus test asserts a `wrap` count, update the expected number
and note in the commit body that the drop is the repaired class.
(`tests/test_config.py:199` is a comment about `BOUNDARY_HINT_RE`, not an assertion — it needs no change.)

- [x] **Step 6: Commit**

```bash
git add scripts/check_linefeeds.py tests/test_precision.py
git commit -m "fix(detector): complete the subordinator family in CONNECTORS

until, while, and because passed while after, since, once, and before
were accused, because the list was collected word by word rather than as
a family. A correct break before a subordinate clause read as a severed
one for no reason but list membership.

ADR-0002 refuted demonstratives, pro-forms, and code tokens as wrap
signals; none of those arguments reaches a plain subordinator. This
removes a measured false-positive class without adding a predicate."
```

---

## Task 4: `long` measures the prose, not the carrier

`scripts/check_linefeeds.py:1368` compares `len(raw) > limit` while searching `prose` for a boundary.
`raw` carries indentation, the comment marker, and any Markdown carrier.
A 68-character sentence indented 56 columns raises a `long` advisory whose message then tells the agent to scan from column 120 on a line whose prose ends at 68.

This is the only mechanism in the system by which the tool argues for a break the reader does not need.

**Files:**
- Modify: `scripts/check_linefeeds.py:1368` and the message at `:1376`
- Test: `tests/test_precision.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the `long` finding's message reports the prose length,
  so any test asserting a character count in a `long` message must use that figure.

- [x] **Step 1: Write the failing test**

Add to `tests/test_precision.py`:

```python
# --- long measures the prose ----------------------------------------------


def test_indentation_does_not_make_a_short_sentence_long():
    """The advisory is about the sentence, not about the column the comment sits in.

    A nested struct pushes a comment rightward without making its prose any
    longer. Counting the carrier tells the agent to split a line that reads
    perfectly well, which is the one way this tool can cause the wrapping it
    exists to prevent.
    """
    sentence = "It flushes the queue, and the retry loop then drains it slowly here."
    assert len(sentence) == 68
    deep = "package p\n\n" + " " * 56 + "// " + sentence + "\n"
    flat = "package p\n\n// " + sentence + "\n"
    assert kinds(deep, path="doc.go") == kinds(flat, path="doc.go") == []


def test_a_genuinely_long_prose_line_still_draws_the_advisory():
    """The other half: measuring the prose must not silence a real one."""
    sentence = (
        "The exporter batches metrics in memory, and the flush loop then "
        "retries every failed upload with exponential backoff until the "
        "queue finally drains completely."
    )
    assert len(sentence) > 120
    assert kinds("package p\n\n// " + sentence + "\n", path="doc.go") == [(3, "long")]
```

- [x] **Step 2: Run the tests and confirm the first fails**

Run: `python3 -m pytest tests/test_precision.py -v -k "long or indentation"`
Expected: `test_indentation_does_not_make_a_short_sentence_long` FAILS,
since the deep case returns `[(3, 'long')]`, while the second test PASSES.

- [x] **Step 3: Measure the prose**

In `scripts/check_linefeeds.py`, change line 1368 from:

```python
        if limit and len(raw) > limit and BOUNDARY_HINT_RE.search(prose):
```

to:

```python
        # Measured on the prose, not on `raw`.
        # `raw` carries indentation, the comment marker, and any Markdown carrier,
        # none of which the reader parses as part of the sentence.
        # Counting them told a deeply nested comment to split a sentence that reads fine,
        # which is the one way this checker can cause the wrapping it exists to prevent.
        if limit and len(prose) > limit and BOUNDARY_HINT_RE.search(prose):
```

Then change the message on line 1376 from `{len(raw)} chars` to `{len(prose)} chars`.

- [x] **Step 4: Run the tests and confirm both pass**

Run: `python3 -m pytest tests/test_precision.py -v -k "long or indentation"`
Expected: PASS.

- [x] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.
Tests asserting a specific char count in a `long` message will need the prose figure;
update them and say so in the commit body.

- [x] **Step 6: Commit**

```bash
git add scripts/check_linefeeds.py tests/test_precision.py
git commit -m "fix(detector): measure long against the prose, not the carrier

The check compared len(raw) to the limit while searching the stripped
prose for a boundary, so indentation and the comment marker counted
toward a sentence's length. A 68-character sentence nested 56 columns
deep drew an advisory that then told the agent to scan rightward from
120 on a line whose prose ended at 68.

Every other finding describes something the checker fails to see. This
one had it arguing for a break the reader does not need."
```

---

## Task 5: document the per-language suppression carriers

`README.md:195-225` shows suppression only in Markdown (`<!-- semlf-ignore -->`).
A reader writing Go, Python, Rust, or Lua has no example, though the feature works in all of them:
`trailing_carrier` (`scripts/check_linefeeds.py:1569-1577`) uses each language's own line-comment marker.

Verified working: `//` (Go, Rust, C-family), `#` (Python, Ruby, shell), `--` (Lua, SQL), `<!-- -->` (Markdown).
`docs/decisions/0010-suppression-is-a-stateless-single-line-directive.md:66-76` already documents the grammar; only the README is silent.

**Files:**
- Modify: `README.md:195-225`

**Interfaces:**
- Consumes: nothing — documentation only, with no behaviour change.

- [x] **Step 1: Confirm the forms work before documenting them**

Run:

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "scripts")
import check_linefeeds as C
cases = [
    ("doc.go", "package p\n\n// Close the session   // semlf-ignore\n// after the request finishes.\n"),
    ("doc.py", '"""Doc.\n\nClose the session  # semlf-ignore\nafter the request finishes.\n"""\n'),
    ("doc.md", "# H\n\nClose the session <!-- semlf-ignore -->\nafter the request finishes.\n"),
]
for path, text in cases:
    print(path, C.check(text, path))
PY
```

Expected: `[]` for all three.

- [x] **Step 2: Replace the two Markdown-only examples with a per-language table**

In `README.md`, after the line `- \`semlf-ignore-next\` — withholds every finding anchored on the next line.`,
replace the "Standalone, on a line of its own:" and "Trailing, after the line it judges:" blocks with:

````markdown
The directive rides in a comment, so it is written the way the file's own language writes comments.

| Language | Standalone | Trailing |
|---|---|---|
| Markdown | `<!-- semlf-ignore-next -->` | `… judged text. <!-- semlf-ignore long -->` |
| Go, Rust, C-family, JavaScript | `// semlf-ignore-next` | `// … judged text.  // semlf-ignore long` |
| Python, Ruby, shell | `# semlf-ignore-next` | `# … judged text.  # semlf-ignore long` |
| Lua, SQL | `-- semlf-ignore-next` | `-- … judged text.  -- semlf-ignore long` |

Standalone, on a line of its own:

```markdown
<!-- semlf-ignore-next -->
A line the checker will leave alone.
```

```go
// semlf-ignore-next
// A line the checker will leave alone.
```

Trailing, after the line it judges:

```markdown
A long judged line that runs on past the limit. <!-- semlf-ignore long -->
```

```python
# A long judged line that runs on past the limit.  # semlf-ignore long
```

A trailing carrier is the rightmost comment marker to the end of the line,
so the judged text is whatever stands to its left.
````

Leave the paragraphs after these blocks — the `wrap` anchoring note, the kind-argument note, the malformed-directive note, and the agent-authority note — exactly as they are.

- [x] **Step 3: Verify the README still self-hosts**

Run: `python3 scripts/check_linefeeds.py --file README.md`
Expected: zero `fused` and zero `wrap`.
Judge any `long` advisories, and leave the line long rather than severing a clause.

- [x] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): show the suppression directive in every language

The section demonstrated only the Markdown carrier, so a reader working
in Go or Python had no example of a feature that has always worked for
them. The directive rides in a comment and is written the way the file's
own language writes comments; ADR-0010 already specified this and only
the README was silent."
```

---

## Task 6: bind the `wrap` repair to its two-line window

`skills/semantic-linefeeds/SKILL.md:38` says rejoin the severed clause.
`skills/semantic-linefeeds/SKILL.md:67-70` forbids reflowing untouched text.
These conflict when the severed clause continues into a third line, and an agent has no instruction on which rule wins — so two agents produce two different diffs from one finding.

`docs/ROADMAP.md:155-159` defers the fix until ADR-0005 ownership ranges make "the affected two lines" precise.
That blocker already shipped: `diagnose()` emits two-line evidence at `scripts/check_linefeeds.py:1344-1347` and a two-line ownership span at `:1348-1352`.

**Files:**
- Modify: `skills/semantic-linefeeds/SKILL.md:38`
- Modify: `docs/ROADMAP.md:155-159`

**Interfaces:**
- Consumes: nothing.
  Both agent-facing skill copies ship from this one source (ADR-0019), so editing it here reaches every target.

- [x] **Step 1: Add the bound to the `wrap` bullet**

In `skills/semantic-linefeeds/SKILL.md`, change line 38 from:

```markdown
- **wrap** — rejoin the severed clause onto one line, then re-split at sentence ends.
```

to:

```markdown
- **wrap** — rejoin the severed clause onto one line, then re-split at sentence ends.
  The repair is confined to the two lines the finding spans;
  if a correct re-split would push text into a third line you did not write,
  rejoin those two lines only and surface the rest under Bounded disagreement.
```

- [x] **Step 2: Remove the deferral from the roadmap**

In `docs/ROADMAP.md`, delete the "Legacy-paragraph editing recipe" bullet at lines 155–159 in full, and add to the `### v0.9 — Fixes and team integration` list:

```markdown
- The `wrap` repair recipe is bound to the finding's two-line ownership window,
  which closes the conflict between rejoining a severed clause and never reflowing stable text.
```

- [x] **Step 3: Verify both files self-host**

Run: `python3 scripts/check_linefeeds.py --file skills/semantic-linefeeds/SKILL.md docs/ROADMAP.md`
Expected: zero `fused` and zero `wrap`.

- [x] **Step 4: Run the skill-text tests**

Run: `python3 -m pytest tests/test_judgment_texts.py tests/ -q`
Expected: all pass.
If a test pins the skill's byte length or a digest, update it.

- [x] **Step 5: Commit**

```bash
git add skills/semantic-linefeeds/SKILL.md docs/ROADMAP.md
git commit -m "docs(skill): bound the wrap repair to the finding's two lines

The skill told an agent to rejoin a severed clause and also never to
reflow stable text, and said nothing about which wins when the clause
continues past the finding. One agent left the violation, another
reflowed the paragraph into an unreviewable whitespace diff.

The roadmap deferred this pending ADR-0005 ownership ranges. Those
shipped in v0.5 and diagnose() has emitted the two-line span since, so
the bound could be stated from what the diagnostic already carries."
```

---

## Task 7: say that CJK prose is not analyzed

All three kinds are structurally inert on Chinese:
`fused` requires `[a-z]{2,}` before an ASCII terminator (`scripts/check_linefeeds.py:322-327`),
`wrap` requires a lowercase ASCII opener on the lower line (`:1330`),
and `long` requires an ASCII boundary hint (`:380`).
After Task 2 the tool no longer *misfires* on Chinese, but it still reports nothing —
and a silent pass is indistinguishable from a verified one.

**Files:**
- Modify: `README.md` (the "What it checks" or equivalent scope section around `README.md:342-356`)
- Modify: `skills/semantic-linefeeds/SKILL.md`

**Interfaces:**
- Consumes: Task 2 must land first, so the note describes "not analyzed" rather than "analyzed incorrectly".

- [x] **Step 1: Add the scope note to the README**

In `README.md`, at the end of the section listing supported languages and file types, add:

```markdown
### What is not analyzed

The checker reads English prose.
Its three kinds each depend on an ASCII signal —
a lowercase word before the stop, a lowercase opener on the following line, an ASCII clause hint —
so CJK text is passed over rather than checked.
A Chinese, Japanese, or Korean paragraph therefore produces no findings,
however it is broken.
A full-width terminator is recognized as ending a line,
so mixed-language prose is not accused at the boundary,
but the CJK text itself is not examined.
```

- [x] **Step 2: Add the matching line to the skill**

In `skills/semantic-linefeeds/SKILL.md`, at the end of the "Never break" section, add:

```markdown
The checker analyzes English prose only.
CJK text produces no findings, so a clean run over it is silence rather than approval —
apply the one-thought-per-line rule from your own judgment there.
```

- [x] **Step 3: Verify both files self-host**

Run: `python3 scripts/check_linefeeds.py --file README.md skills/semantic-linefeeds/SKILL.md`
Expected: zero `fused` and zero `wrap`.

- [x] **Step 4: Run the full suite and commit**

Run: `python3 -m pytest tests/ -q`

```bash
git add README.md skills/semantic-linefeeds/SKILL.md
git commit -m "docs: say that CJK prose is passed over, not checked

Each kind depends on an ASCII signal, so a Chinese paragraph produces no
findings however it is broken. The hook still runs and still reports
nothing, which reads exactly like a verified pass.

Naming the limit costs a sentence and turns a silent no-op into a known
boundary."
```

---

## Task 8: restate the stale roadmap deferrals

Three "Deferred, with reasons" entries describe a world that has shipped past them.
Someone planning v0.9 reads a reason that is no longer the true reason.

**Files:**
- Modify: `docs/ROADMAP.md:118-120`, `:152-154`, `:171-174`

**Interfaces:**
- Consumes: Tasks 1–4 and 6 must land first, since two entries change because of them.

- [x] **Step 1: Restate the confidence-field entry**

The current reason is "no number ships until observed rates support one".
Rates now exist (`CHANGELOG.md:317-327`, `:474-478`), so the gate as written is crossed.
Replace the reason with the objection that actually still holds:

```markdown
- **A numeric `confidence` field on diagnostics.**
  Holdout rounds now report rates, so the original "no number until observed rates support one" gate is crossed.
  What still blocks it is that those are corpus-stratum rates,
  and a per-finding number is a different claim the evidence does not support.
  Entry condition: a per-finding calibration, not another stratum rate.
```

- [x] **Step 2: Fix the feedback-persistence version**

The entry defers to v0.7 "where the real-agent corpus needs the same data", but the corpus is a v0.9 item (`docs/ROADMAP.md:106`). Change the closing line to:

```markdown
  Deferred to v0.9, alongside the real-agent corpus that needs the same data.
```

- [x] **Step 3: Correct the CJK entry**

The current text says "`wrap` depends on inter-word spaces and a following capital". That describes `FUSED_RE` (`scripts/check_linefeeds.py:326`); `wrap` depends on a lowercase ASCII opener (`:1330`). Replace the bullet with:

```markdown
- **CJK support.**
  Full-width terminators are now recognized as line enders,
  so mixed prose is no longer accused at the language boundary —
  but no kind analyzes CJK text, and the README says so.
  Real support is a per-kind redesign rather than a terminator set:
  `fused` needs a CJK token alternative and a no-space opener rule,
  `wrap` needs an end-of-clause decision for a language without inter-word spaces,
  and `long` needs a CJK boundary hint and a width that counts double-width glyphs.
  Entry condition: field reports from a CJK-writing user, or a labeled CJK corpus.
```

- [x] **Step 4: Add the open question Task 1 deferred**

Add to the "Open precision questions" table:

```markdown
| An abbreviation followed by a capitalised proper noun | `The Smith et al. Nature paper argues otherwise.` draws a `fused` finding on one sentence | A signal that separates a citation period from a sentence period. The exclusion list cannot: the same characters carry both uses, and `al.` commonly ends a sentence, so exempting it would hide real violations (see the withdrawn Task 1). |
```

- [x] **Step 5: Verify the roadmap self-hosts**

Run: `python3 scripts/check_linefeeds.py --file docs/ROADMAP.md`
Expected: zero `fused` and zero `wrap`.

- [x] **Step 6: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): restate three deferrals against shipped reality

The confidence-field gate was written as 'until observed rates exist'
and those rates now exist; the real objection is that stratum rates are
not per-finding confidence. Feedback persistence deferred to v0.7 for a
corpus that now lives in v0.9. The CJK entry attributed FUSED_RE's
space-and-capital dependence to wrap.

Also records the citation abbreviations beyond al. as an open question
rather than leaving them undocumented."
```

---

## Task 9: let `wrap` see a lower line that opens on markup — **sub-agent**

`scripts/check_linefeeds.py:1330` requires `re.match(r"[a-z]+", prose)` on the lower line,
so a pair whose lower line opens on `[`, a backtick, or `*` is discarded before any judgment runs.
17 breaks in this repository's live prose strand a governing word above such a line
(`docs/ROADMAP.md:81`, `:83`, `.agents/rules/000-agent-contract.md:52`,
`docs/decisions/0002-wrap-withdrawn-from-default-feedback.md:195`, and 13 more listed in the spec's appendix).

**This is the only task that widens `wrap` detection**, so it carries real false-positive risk and needs its own evidence.
Tasks 10 and 11 also add findings, by other mechanisms, and each carries its own audit.

**Files:**
- Modify: `scripts/check_linefeeds.py:1328-1342`
- Test: `tests/test_precision.py`

**Interfaces:**
- Consumes: `CONNECTORS` as extended by Task 3, and the two-line repair rule added by Task 6, which Step 7 applies.
  Task 2 also shifts the `wrap` baseline, so it must land before the Step 1 measurement.
- Produces: no new public name.
  The `wrap` finding's `ownership` still spans the upper line's last word through the lower line's first token;
  the locate at `:1342` must be given the matched token when the opener is markup.

- [x] **Step 1: Capture the baseline finding count**

Run:

```bash
python3 scripts/check_linefeeds.py --json --file $(git ls-files '*.md' '*.go' '*.py' | grep -v '^tests/') > /tmp/wrap-before.json
python3 -c "import json;d=json.load(open('/tmp/wrap-before.json'));print(sum(1 for f in d for g in f['diagnostics'] if g['kind']=='wrap'))"
```

Record the number, which is the denominator for Step 5.

- [x] **Step 2: Write the failing tests**

```python
# --- a lower line that opens on markup ------------------------------------


def test_a_stranded_preposition_above_a_link_is_a_wrap():
    """The governing word is left on the upper line and the link looks self-contained.

    This is the corpus's most common real break at a non-boundary, and the
    lowercase-opener gate discarded the pair before any judgment ran.
    """
    text = "The declined repairs stay declined,\nin the diagnosis and in\n[the plan](plan.md).\n"
    assert (2, "wrap") in kinds(text)


def test_a_stranded_copula_above_a_code_span_is_a_wrap():
    text = "How a round is read when one floor clears is\n`docs/decisions/0009.md`.\n"
    assert kinds(text) == [(1, "wrap")]


def test_a_terminated_line_above_a_link_is_still_not_a_wrap():
    """The gate widens; the terminator test must still do its job."""
    assert kinds("The repairs stay declined.\n[the plan](plan.md).\n") == []


def test_a_parenthetical_citation_after_a_complete_clause_is_not_a_wrap():
    """A parenthetical on its own line is a legitimate semantic break.

    This is the largest class the old gate discarded, and widening the gate
    must not convert it into an accusation.
    """
    assert kinds("The verbs no longer need a checkout to copy from.\n([ADR-0016](adr.md))\n") == []
```

- [x] **Step 3: Run and confirm the first two fail**

Run: `python3 -m pytest tests/test_precision.py -v -k "markup or stranded or parenthetical"`
Expected: the two stranded tests FAIL (empty result); the two negative tests PASS.

- [x] **Step 4: Widen the opener**

Replace the opener match at `scripts/check_linefeeds.py:1330` and its use at `:1342`.
The lower line may open on a Markdown link, a code span, or a bold span —
three unambiguous prefixes, not an open set.
Define beside the other constants:

```python
# A lower line may open on markup rather than on a word.
# The three forms below are unambiguous openers a writer puts at the start of a line
# because the span reads as self-contained,
# which is exactly when the word governing it gets stranded on the line above.
# Anything else still fails the opener test:
# the gate widens to three named forms, it does not open.
#
# The bold form excludes a span ending in ":", which is a field label rather than prose.
# An ADR header writes "**Status:** accepted" above "**Date:** 2026-08-10",
# a two-row table written without a table syntax,
# and reading the second row as a severed clause accuses metadata that has no clause to sever.
MARKUP_OPENER_RE = re.compile(r"\[[^\]]+\](?=[(\[])|`[^`]+`|\*\*[^*]*[^*:]\*\*")
```

**Measured before writing this task, over the repo's Markdown outside `tests/` and `docs/plans/`:**

| Opener set | New findings | ADR metadata rows accused | Known stranded-word cases caught |
|---|---|---|---|
| link, code span, any bold | 62 | 27 | 8 of 8 |
| link, code span only | 34 | 0 | 7 of 8 |
| link, code span, bold not ending in `:` | **35** | **0** | **8 of 8** |

The third row is the regex above.
Dropping bold entirely also clears the metadata class but loses `docs/decisions/0002-wrap-withdrawn-from-default-feedback.md:195`
(`…some predicate reaches` / `**zero false positives…**`), which is a genuine stranded verb.

Note also that `(` is already excluded by construction —
no alternative in the pattern starts with it, and the match is anchored —
so the 337 pairs opening on a parenthetical stay skipped without a special case.
Verified: `([ADR-0016](adr.md))` and `(see the note)` both fail the match.

Then at `:1330`, replace:

```python
            first_word = re.match(r"[a-z]+", prose)
```

with:

```python
            first_word = re.match(r"[a-z]+", prose) or MARKUP_OPENER_RE.match(prose)
```

The `CONNECTORS` test at `:1334` must only apply to a word opener, since markup is never a connector:

```python
                and (
                    not first_word.group(0).isalpha()
                    or first_word.group(0) not in CONNECTORS
                )
```

The locate at `:1342` already uses `first_word.group(0)`, which is now the markup token; confirm `locate_in_line` finds it and that a failed locate degrades to `ownership: None` rather than widening the range.

- [x] **Step 5: Run the tests, then re-measure the corpus**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.

Then re-run the Step 1 command into `/tmp/wrap-after.json` and diff the new `wrap` findings:

```bash
python3 - <<'PY'
import json
before = {(f["path"], g["line"]) for f in json.load(open("/tmp/wrap-before.json")) for g in f["diagnostics"] if g["kind"] == "wrap"}
after = {(f["path"], g["line"]) for f in json.load(open("/tmp/wrap-after.json")) for g in f["diagnostics"] if g["kind"] == "wrap"}
for p, l in sorted(after - before):
    print(f"{p}:{l}")
PY
```

- [x] **Step 6: Judge every new finding by hand**

Read each line the diff prints.
**Expect roughly 35 new findings in live prose.**
The spec's appendix lists 17 instances of the known stranded-word class,
of which this gate surfaces **15**.
Two are deliberately out of reach and must not be hunted for:
`.agents/rules/100-project-map.md:46` opens on `(`, which the gate excludes on purpose,
and `docs/research/2026-08-08-widening-scope.md:66` opens on a double quote, which is not one of the three named forms.
The other ~18 are mostly in `docs/research/` and are unjudged — they are the work of this step, not a surprise.

**Acceptance: every new finding is a genuine stranded governing word.**
Do not commit until each one is defensible.

Two gate widths were already ruled out by measurement and must not be reintroduced:
allowing any bold opener accuses 27 ADR metadata rows,
and dropping bold entirely loses a genuine stranded verb.
If a new false-positive class appears that neither variant predicted,
narrow `MARKUP_OPENER_RE` further, re-measure from Step 5, and record the new table row here.
Do not widen it.

- [x] **Step 7: Fix the findings this change surfaces in the repo's own prose**

Every finding accepted in Step 6 is now reported by the checker the repo self-hosts on.
Repair each within its two-line window, per the rule Task 6 added.
Run: `python3 scripts/check_linefeeds.py --file $(git ls-files '*.md' | grep -v '^tests/')`
Expected: zero `fused` and zero `wrap`.

- [x] **Step 8: Commit**

Stage the repaired Markdown from Step 7 alongside the code, or the repo lands self-host-dirty.

```bash
git add scripts/check_linefeeds.py tests/test_precision.py
git add $(git diff --name-only -- '*.md')
git commit -m "feat(detector): read a lower line that opens on markup

The opener test required a lowercase word, so a pair whose lower line
began with a link, a code span, or a bold span was discarded before any
judgment ran. That is where the corpus's real breaks at a non-boundary
live: a writer breaks before an inline link because the link reads as
self-contained, and the preposition or copula governing it is stranded
above.

The gate widens to three named forms rather than opening. Every finding
this surfaces in the repo's own prose was judged by hand before landing."
```

---

## Task 10: report every `fused` boundary on a line — **sub-agent**

`scripts/check_linefeeds.py:1302` performs a single `FUSED_RE.search`,
so a line holding four sentence boundaries reports one finding.
That collides with `skills/semantic-linefeeds/SKILL.md:74-76`,
which ends the repair loop on a finding that "survives one repair attempt" —
an agent that splits once, re-runs, and sees `fused` again may read that as a survival and stop.

`_fused_suggestion` already asks the multi-match question at `:1218`
(`len(list(FUSED_RE.finditer(prose))) != 1`), so the codebase knows the distinction one level down.

**Files:**
- Modify: `scripts/check_linefeeds.py:1302-1326`
- Test: `tests/test_precision.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `diagnose()` may return more than one `fused` dict for the same `line`.
  Consumers that key diagnostics by line number must tolerate duplicates —
  check `to_schema` (`:1413`), `format_findings` (`:1443`), and the suppression filter (`:1394-1399`),
  which suppresses by `(line, kind)` and therefore still withholds all of them together.

- [x] **Step 1: Write the failing test**

```python
def test_every_fused_boundary_on_a_line_is_reported():
    """One finding per boundary, not one per line.

    The skill ends the repair loop on a finding that survives one attempt.
    A line reporting its boundaries one at a time looks exactly like a
    finding that survived, so an agent stops with the line still fused.
    """
    text = "alpha beta. Gamma delta. Epsilon zeta. Eta theta.\n"
    assert kinds(text) == [(1, "fused"), (1, "fused"), (1, "fused")]


def test_a_single_boundary_still_reports_once():
    assert kinds("alpha beta. Gamma delta.\n") == [(1, "fused")]
```

- [x] **Step 2: Run and confirm the first fails**

Run: `python3 -m pytest tests/test_precision.py -v -k "fused_boundary or single_boundary"`
Expected: the first FAILS with one finding instead of three; the second PASSES.

- [x] **Step 3: Iterate the matches**

In `scripts/check_linefeeds.py`, change line 1302 from:

```python
        match = FUSED_RE.search(prose)
        if match:
```

to:

```python
        # Every boundary on the line, not just the first.
        # The skill ends its repair loop on a finding that survives one attempt,
        # and a line that surrenders its boundaries one per pass is indistinguishable from one that survived,
        # so an agent stops with the line still fused.
        for match in FUSED_RE.finditer(prose):
```

Re-indent the body through line 1326 by one level.
The suggestion call at `:1323` needs no change: `_fused_suggestion` independently refuses any line with more than one match, so a multi-boundary line still carries no suggestion.

- [x] **Step 4: Locate each boundary by offset, not by re-searching its text**

`scripts/check_linefeeds.py:1305` currently locates ownership by searching the raw line for `match.group(0)`.
`locate_in_line` returns `None` when the needle occurs more than once (`scripts/check_linefeeds.py:748`),
so a line with a repeated phrase degrades to `ownership: None`,
and a degraded diagnostic is withheld entirely under spans (`:1387-1393`) — which is hook mode.

Verified on the current code, before any change from this plan:
a line repeating the same short sentence three times already reports `ownership=None, basis=degraded`,
and `diagnose(..., spans=[...])` returns `[]` for it while the unspanned call returns the finding.
**This is a pre-existing defect, not one Task 10 introduces** —
but iterating the matches is the moment it becomes systematic, so it is repaired here.

Replace the locate at `:1305-1309`:

```python
            located = locate_in_line(text, offsets, lineno, match.group(0))
            if located and located["end"] <= anchor["end"]:
                tail = re.search(r"\s", text[located["end"] : anchor["end"]])
                end = located["end"] + tail.start() if tail else anchor["end"]
                ownership, basis = {"start": located["start"], "end": end}, "token"
            else:
                ownership, basis = None, "degraded"
```

with a locate of the prose once, then an index into it by the match's own offset:

```python
            # Located by offset within the prose, not by re-searching the matched text.
            # Two boundaries on one line can match identical strings ("It works. It works. It works."),
            # and a repeated needle makes locate_in_line refuse rather than guess,
            # which withholds the finding entirely under spans.
            # The prose is located once and the match indexes into it,
            # which is the same shape the `long` branch already uses at :1370.
            prose_at = locate_in_line(text, offsets, lineno, prose)
            located = (
                {
                    "start": prose_at["start"] + match.start(),
                    "end": prose_at["start"] + match.end(),
                }
                if prose_at
                else None
            )
            if located and located["end"] <= anchor["end"]:
                tail = re.search(r"\s", text[located["end"] : anchor["end"]])
                end = located["end"] + tail.start() if tail else anchor["end"]
                ownership, basis = {"start": located["start"], "end": end}, "token"
            else:
                ownership, basis = None, "degraded"
```

Add the regression test:

```python
def test_a_repeated_phrase_still_locates_each_boundary_exactly():
    """A repeated needle used to make the locate refuse, which withheld the finding in hook mode."""
    text = "# H\n\nIt works. It works. It works.\n"
    found = [d for d in check_linefeeds.diagnose(text, "doc.md") if d["kind"] == "fused"]
    assert len(found) == 2
    assert all(d["ownership_basis"] == "token" for d in found)
    starts = [d["ownership"]["start"] for d in found]
    assert starts[0] != starts[1]
```

- [x] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_precision.py -v -k "fused_boundary or single_boundary"`
Expected: PASS.

- [x] **Step 6: Update the two existing tests this change breaks**

Both destructure a single diagnostic from a line that holds two boundaries,
so they raise `ValueError` the moment the finder iterates.
Neither is incidental — each encodes behaviour this task deliberately changes,
so each needs its assertion restated rather than deleted.

`tests/test_diagnostics.py:59-64`, `test_an_ambiguous_match_carries_no_ownership`:

```python
    text = "Stop aa. Bb then aa. Bb again.\n"
    (d,) = diags(text)
    assert d["ownership"] is None
    assert d["ownership_basis"] == "degraded"
```

This test **specifies** the degraded ownership that Step 4 repairs,
so it is not merely a count that drifted.
`locate_in_line`'s docstring calls the refusal deliberate — "forces the caller to drop ownership rather than guess"
(`scripts/check_linefeeds.py:741`) — and Step 4's offset arithmetic removes the guess entirely,
which makes exact ownership available where the old approach could only decline.
Restate it as two findings that now locate exactly, and record in the test why the old expectation changed:

```python
def test_a_repeated_match_now_locates_each_boundary_exactly():
    """Locating by offset removes the ambiguity that used to force a degrade.

    The needle used to be the matched text, which a repeated phrase made
    unfindable, so ownership was dropped rather than guessed. Indexing into
    the located prose by the match offset is not a guess, so the finding
    keeps its exact range instead of being withheld under spans.
    """
    text = "Stop aa. Bb then aa. Bb again.\n"
    found = diags(text)
    assert len(found) == 2
    assert all(d["ownership_basis"] == "token" for d in found)
```

Two further tests use the same two-boundary fixture and break the same way.
Both exist to exercise *degraded* ownership, which Step 4 removes — and not only for this fixture.

**After Step 4, a degraded `fused` is unreachable through the current extractors.**
Degrading now requires `locate_in_line` to fail on `prose` itself,
but `prose` is the line's own content and was found exactly once in every case tried —
Markdown paragraph, list item, blockquote, and Go comment, each with a deliberately repeated phrase.
Every extractor derives `prose` as one contiguous substring of its raw line,
so once that occurrence is located, `match.start()` fixes each boundary exactly.
These two tests cannot be rehomed on another `fused` fixture; there is none.

**Move both onto a `wrap` fixture, which still degrades.**
`wrap` locates single words (`scripts/check_linefeeds.py:1338-1342`),
so a word repeated on the upper line still defeats the locate.
Verified fixture:

```python
    text = "the cat and the\nthe dog ran\n"
```

This yields one `wrap` with `ownership_basis == "degraded"`,
because the upper line's last word `the` occurs twice on it.

**Do not delete these tests:** they pin the contract that a degraded diagnostic is withheld under spans
and serializes a null ownership, and that contract still holds — only the kind that can reach it changes.

- `tests/test_diagnostics.py:207-211`, `test_a_degraded_diagnostic_never_reports_under_spans` — asserts `len(diags(text, spans=None)) == 1`.
- `tests/test_schema.py:33-39`, `test_a_degraded_diagnostic_serializes_a_null_ownership` — destructures `(d,)` from the serialized diagnostics.

`tests/test_diagnostics.py:305-309`, `test_a_two_boundary_line_gets_no_suggestion`:

```python
    text = "Go now? Come here! Stay put.\n"
    (d,) = diags(text)
    assert d["kind"] == "fused"
    assert "suggestion" not in d
```

Its point — a multi-boundary line carries no suggestion — still holds and must be kept.
Only the destructuring changes:

```python
    text = "Go now? Come here! Stay put.\n"
    found = diags(text)
    assert len(found) == 2
    assert all(d["kind"] == "fused" for d in found)
    assert all("suggestion" not in d for d in found)
```

- [x] **Step 7: Check the remaining consumers**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.
Pay attention to `tests/test_diagnostics.py` and `tests/test_suppression.py`:
a suppression directive on a multi-boundary line must still withhold every finding on it,
since the filter keys on `(line, kind)`.

Add a regression test to `tests/test_suppression.py`:

```python
def test_one_directive_suppresses_every_fused_boundary_on_its_line():
    text = "<!-- semlf-ignore-next -->\nalpha beta. Gamma delta. Epsilon zeta.\n"
    assert check_linefeeds.check(text, "doc.md") == []
```

- [x] **Step 8: Re-measure the corpus**

A count cannot distinguish a genuine second boundary from one boundary reported twice.
Compare locations and ownership, not totals:

```bash
python3 scripts/check_linefeeds.py --json --file $(git ls-files '*.md' | grep -v '^tests/') \
  | python3 -c "import json,sys; [print(f[\"path\"], d[\"line\"], d[\"ownership\"]) for f in json.load(sys.stdin) for d in f[\"diagnostics\"] if d[\"kind\"]=='fused']"
```

Every `fused` on the same line must carry a distinct `ownership` range.
Two identical ranges on one line mean the loop is reporting one boundary twice.

Repair any newly surfaced boundaries so the repo still self-hosts clean.

- [x] **Step 9: Commit**

Stage any Markdown repaired in Step 8 alongside the code.

```bash
git add scripts/check_linefeeds.py tests/test_precision.py tests/test_suppression.py tests/test_diagnostics.py tests/test_schema.py
git add $(git diff --name-only -- '*.md')
git commit -m "fix(detector): report every fused boundary on a line

The finder ran one search per line, so a line with three sentence
boundaries surrendered them one pass at a time. The skill ends its
repair loop on a finding that survives one attempt, and a recurring kind
looks exactly like a surviving finding, so an agent could stop with the
line still fused.

_fused_suggestion already counted matches to refuse ambiguous repairs;
the finder above it now asks the same question."
```

---

## Task 11: derive `BOUNDARY_HINT_RE` from `CONNECTORS`, and record the `and` asymmetry

Two lists encode one concept — "a word that opens a clause" — and disagree.
`scripts/check_linefeeds.py:380` hints only on `, (and|but|so|which|that|where)`,
while `CONNECTORS` holds 21 words before Task 3 and 28 after it.
A 130-character line containing `, because` draws no `long` advisory though `because` is a connector.

The comma-led requirement stays: `scripts/check_linefeeds.py:378-379` records that a bare `and` is usually a compound object, and that reasoning is unaffected by which words the list holds.

**Measured** over this repo's prose, with `long` already on prose width per Task 4:
87 advisories today, and 98 when derived from the extended list — eleven more.
`long` never blocks (ADR-0001), so eleven additional advisories cost attention and nothing else.

**Files:**
- Modify: `scripts/check_linefeeds.py:378-380`
- Modify: `docs/ROADMAP.md` (the `and` asymmetry note)
- Test: `tests/test_precision.py`

**Interfaces:**
- Consumes: `CONNECTORS` as extended by Task 3, so this task must follow it.
- Produces: `BOUNDARY_HINT_RE` is built from `CONNECTORS` rather than from its own literal list.

- [x] **Step 1: Write the failing test**

```python
def test_the_boundary_hint_covers_every_connector():
    """One concept, one list. A second literal list drifts from the first silently."""
    for word in check_linefeeds.CONNECTORS:
        line = "x" * 130 + f", {word} the rest of the sentence continues here."
        assert check_linefeeds.BOUNDARY_HINT_RE.search(line), word
```

- [x] **Step 2: Run and confirm it fails**

Run: `python3 -m pytest tests/test_precision.py::test_the_boundary_hint_covers_every_connector -v`
Expected: FAIL on the first connector absent from the literal list (`although`, `as`, `because`, and 12 more).

- [x] **Step 3: Build the pattern from the set**

Move `BOUNDARY_HINT_RE` below the `CONNECTORS` definition and replace its literal alternation:

```python
# Built from CONNECTORS rather than from a second literal list.
# Both encode "a word that opens a clause", and two copies drifted:
# the literal held six of the set's twenty-one words,
# so a line breaking at ", because" drew no advisory while ", which" did.
# The comma-led form is still required.
# A bare "and" is usually a compound object rather than a boundary,
# and that reasoning is about the comma, not about which words the list holds.
BOUNDARY_HINT_RE = re.compile(
    r"[;:—]|\s–\s|, (?:" + "|".join(sorted(CONNECTORS)) + r")\b"
)
```

Sorting matters only for a stable pattern string; alternation order does not affect matching here because `\b` anchors each alternative.

- [x] **Step 4: Update the advisory message and its frozen contract**

The message still names six words while the pattern now recognises 28
(`scripts/check_linefeeds.py:1376`),
and it is pinned byte-for-byte as `LONG_MSG` at `tests/test_frozen_contract.py:29-35`.
A `long` raised by `, because` would tell the reader to look for `and/but/so` — advice that does not match its own trigger.

Enumerating 28 words in a hook message is unreadable, so the message names the classes instead.
Change the message text at `scripts/check_linefeeds.py:1376` from:

```
scan from ~120 rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward
```

to:

```
scan from ~120 rightward for ';' ':' '—', a coordinating conjunction, or a word opening a subordinate clause, else backward
```

Update `LONG_MSG` in `tests/test_frozen_contract.py:29-35` to the same bytes.
Check `skills/semantic-linefeeds/SKILL.md:43-49` for the same drift:
its boundary definition lists the six words too, and it is the text an agent acts on.
Either widen it to match, or state there that the list is illustrative rather than exhaustive.

- [x] **Step 5: Audit the eleven additional advisories**

The global constraint says a change that adds findings needs evidence, and this adds eleven.
`long` never blocks, so the bar is lower than Task 9's — but "lower" is not "none".

```bash
python3 scripts/check_linefeeds.py --json --file $(git ls-files '*.md' '*.py' | grep -v '^tests/') > /tmp/long-after.json
```

Diff against the same command run on `HEAD` in a second worktree and read every new advisory.
**Acceptance: each one names a line where a real clause boundary exists.**
An advisory pointing at a line with no boundary is noise,
and noise in the one non-blocking kind is still attention spent.
If any addition fails, narrow the derivation and re-measure.

- [x] **Step 6: Run the tests**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.
`tests/test_config.py:199` carries a comment about `BOUNDARY_HINT_RE` requiring strong punctuation or a comma-led conjunction,
and that statement stays true.
Check whether the fixture beneath it now draws an advisory it did not before, and update the expectation if so.

- [x] **Step 7: Record the `and` asymmetry in the roadmap**

Spec item 2.4 has no code fix.
`CONNECTORS` exempts any lower line opening with `and`,
while `skills/semantic-linefeeds/SKILL.md:45-49` requires that both sides stand alone.
Closing that needs a subject-verb test, which is the NLP `docs/ROADMAP.md:165-166` declines.
Record it instead, under "Deferred, with reasons":

```markdown
- **Testing whether an `and` joins two independent clauses.**
  `CONNECTORS` exempts every lower line opening with `and`,
  while the skill calls a compound-object `and` a mistake to avoid,
  so the one break the skill warns about hardest is the one the detector cannot catch.
  Closing it needs a subject-and-verb test on both halves,
  which is the grammar this project leaves to the judgment layer.
  The exemption is doing real precision work and stays;
  what is recorded here is that its unconditional form is a choice, not an oversight.
```

- [x] **Step 8: Verify the roadmap self-hosts and commit**

Run: `python3 scripts/check_linefeeds.py --file docs/ROADMAP.md`

```bash
git add scripts/check_linefeeds.py docs/ROADMAP.md tests/test_precision.py tests/test_frozen_contract.py skills/semantic-linefeeds/SKILL.md
git commit -m "refactor(detector): build the boundary hint from CONNECTORS

The hint pattern held six of the connector set's words in a second
literal list, so a line breaking at ', because' drew no advisory while
', which' did. Both lists encode 'a word that opens a clause', and the
copy had drifted.

The comma-led requirement is unchanged: a bare 'and' is usually a
compound object, and that reasoning is about the comma rather than about
which words the list holds. Measured at eleven additional advisories
over this repo's prose, none of which block."
```

---

## Self-review

**Spec coverage.**
Consolidated report items FP-1, FP-2, and FP-3 map to Tasks 1, 2, and 3.
Item 2.1 maps to Task 4, item 2.2 to Task 9, item 2.3 to Tasks 2 and 7,
item 2.6 to Task 10, item 2.8 to Task 8, and Part 3 to Task 6.
The suppression-syntax point is Task 5.

**Items 2.4 and 2.5 are both handled by Task 11.**
Item 2.5 is its code change, and item 2.4 is its Step 7 roadmap entry —
documenting the `and` asymmetry rather than closing it, since closing it needs the subject-verb test the project declines.

**Spec item 2.7 is skipped, not overlooked.**
`FUSED_RE` requires an uppercase opener, so a second sentence starting on a quote, a digit, or an apostrophe is invisible
(`scripts/check_linefeeds.py:326`).
That is a verified recall gap with no task here.
Widening the opener touches the sole blocking kind, which makes it the highest-risk change in the whole set,
and it deserves its own plan with its own corpus evidence rather than a step appended to this one.

**Type consistency.**
`MARKUP_OPENER_RE` is defined in Task 9 and used only there,
and `SUBORDINATORS` is a test-local list in Task 3.
No task references a name another task did not define.

**Ordering.**
Task 7 depends on Task 2.
Task 8 depends on Tasks 2, 3, 4, and 6 (Task 1 is withdrawn and contributes nothing).
Task 9 depends on Tasks 2, 3, and 6 — Task 2 and 3 shift the `wrap` baseline it measures, and Task 6 supplies the repair rule its Step 7 applies.
Task 11 depends on Task 3, whose set it derives from.
Task 11 follows Task 3, whose set it derives from.
Tasks 9 and 10 touch adjacent regions of `diagnose()` and are strictly sequential, Task 10 first.

---

## What changed during execution

All ten scheduled tasks landed on `fix/detector-precision`, in the order 2, 3, 4, 5, 6, 7, 8, 11, 10, 9.
Task 11 was moved ahead of Tasks 10 and 9 because Task 9's Step 7 rejoins severed clauses,
which lengthens lines and manufactures `long` advisories,
and running Task 11 afterwards would have made its added advisories impossible to attribute.
Three tasks reached a different answer than the plan specified.
Each is recorded here with the measurement that changed it.

### Task 3 shipped five subordinators, not seven

`before` and `after` were withdrawn.
Both open a subordinate clause, which is the false positive the task was written to remove,
and both also stand as an ordinary preposition or adverb.
The calibration corpus carries three labeled column wraps that land on the second use,
each labeled `true` with `agy`, `claude`, and `codex` agreeing:

| Unit | The break |
|---|---|
| `styx:internal/transport/shm/writer.go:1517` | `4 LE bytes right` / `after it` |
| `go-proposal:design/16085-conversions-ignore-tags.md:113` | `the operation panicked` / `before.` |
| `go-proposal:design/draft-embed.md:181` | `a Go version` / `before Go 1._N_` |

Admitting either word turns all three from `detected` into `accepted_miss`.
This is the same shape as the withdrawn Task 1:
one list entry cannot separate two uses that present the same characters to the rule.
The difference is that Task 1 rested on argument alone and this rests on measurement.
The user confirmed the withdrawal, and both uses are now pinned by tests.

**Carry this forward:** `since` and `once` shipped with the same ambiguity
and were kept only because the calibration corpus carries no instance of their prepositional use.
A future false positive on either is the known class rather than a surprise.

### Task 11 holds `or` out of the derivation

`CONNECTORS` ended at 26 members rather than the plan's 28, so the plan's "eleven more advisories" could not hold.
Deriving the pattern from the whole set added 20 advisories, not 11.
Fourteen of those came from a comma-led `or`,
and every one closed an enumeration or joined a compound subject rather than opening a clause —
`configuration, filters, hooks, or repository selectors`.
That is the failure the existing comment already names for a bare `and`,
except that the comma does not rescue it,
because the closing comma of a list is exactly where `or` appears.

Step 5's acceptance test is that every addition names a line where a real clause boundary exists,
and Step 5 directs the implementer to narrow the derivation and re-measure when one fails.
`NOT_A_BOUNDARY_HINT` is that narrowing.
Holding `or` out leaves 7 additions, each a genuine subordinate clause opened by `since`, `because`, or `while`.
The exclusion is pinned by a test, and the roadmap records that the subject-and-verb test
which would settle the `and` asymmetry would settle `or` with it.

### Task 9 repaired 21 of 124 findings

The sweep surfaced 124 new `wrap` findings across `.md`, `.go`, and `.py`, not the plan's ~35.
The plan's figure was measured "outside `tests/` and `docs/plans/`",
and that same boundary yields 36 here, so the gate is calibrated as the plan measured it.
The other 88 are in `docs/plans/done/` and `docs/research/`.

The user scoped the repair to live prose.
All 21 findings in ADRs, `CHANGELOG.md`, `docs/ROADMAP.md`, `.agents/rules/`,
`adapters/codex/INSTALL.md`, and `cli/semlf/lifecycle.py` were read by hand,
judged as genuine stranded governing words, and rejoined within the two-line window Task 6 defined.
The 103 in the archives are left alone:
they are the record of executed plans and research notes,
many sit inside quoted source lines and `- Modify:` bullets,
and rewrapping them would edit what those plans specified rather than fix prose anyone reads.

Nothing enforces a full-tree sweep today —
pre-commit checks `--staged`, `make selfcheck` checks files changed since `HEAD`, and there is no CI —
so the archives break no gate.

### Corpus approvals

Three status changes and three rubric repins were recorded in `tests/corpus/manifest.lock`,
each with the reason the gate demands:

- Task 6, Task 7, and Task 11 each edited `skills/semantic-linefeeds/SKILL.md`, which the manifest pins by digest.
  No label moved in any of the three.
  The `wrap` repair bound governs how wide a repair may reach rather than what counts as a violation;
  the CJK note records a scope the detector already had, and no unit carries CJK text;
  the clause-boundary definition governs where a long line may be split, and no unit asks a `long` question.
- Task 9 moved three labeled-`true` units from `accepted_miss` to `detected`.
  No unit labeled `false` changed status,
  so the widened gate is a measured recall gain with no measured false positive.

### Verification

`python3 -m pytest tests/ -q` — 1270 passed, 1 skipped, 1 xfailed.
`make lint` — clean.
Live prose self-hosts with zero `fused` and zero `wrap`.

---

## What the external review round found

Three reviewers read the branch after all ten tasks landed:
Codex (`gpt-5.6-sol`, xhigh), agy (`gemini-3.1-pro-high`), and opencode (`deepseek-v4-flash-free`).
Every finding below was reproduced by hand before it was accepted or rejected.

### Unanimous P0: a markup opener bypassed both opener tests

All three reviewers found the same defect independently, and it is real.
Task 9's gate read `first_word.group(0)`, which for a markup match is the whole token.
A token carries punctuation, so `isalpha()` is always false,
which short-circuited the `CONNECTORS` exemption,
and the token never reads as capitalised,
which lost the exemption the bare path gets from matching `[a-z]+` only.
Both leaks accused correct prose:

| Lower line | Before the fix | Bare spelling |
|---|---|---|
| `**because** the request finishes.` | `wrap` | no finding |
| `` `until` the queue drains.`` | `wrap` | no finding |
| `**However**, this is a new sentence.` | `wrap` | no finding |
| `[However](x.md) this is new.` | `wrap` | no finding |

The fix reads the markup's *inner* word and puts it through the same two tests the bare word takes,
which is what `line_opener` now does.
Markup is punctuation the reader looks through, not the word the line opens on.
Repo-wide `wrap` fell from 124 to 63, all three approved corpus units still detect,
and the bold branch — which had no test at all, and which the measurement had called the riskiest —
is now covered.

### Confirmed: a degraded `fused` was never unreachable

The claim at line 1164 above is **false**, and the tests rehomed onto `wrap` cited it.
`locate_in_line` searches for `prose` inside the raw line, and `prose` is not always unique there:
a one-line block comment whose text recurs in a string literal beside it degrades,
as does a docstring followed by a comment repeating it.

The code is correct — degrading to a null ownership is the safe, documented behaviour —
so what needed fixing was the claim, not the checker.
It is narrowed wherever it appeared rather than restored as a fixture,
because no shape in the corpus reaches it and a test for it would pin a line nobody writes.

### Codex alone: the boundary hint derives an addition list from a removal list

`CONNECTORS` is a set whose members *remove* findings, so over-including costs recall, which is safe.
`BOUNDARY_HINT_RE` *adds* findings, so over-including costs precision, which is a bug.
Deriving the second from the first conflates two opposite risk directions,
and holding `or` out patched one symptom rather than the mechanism.
Constructed probes draw an advisory with no clause boundary in sight:
`, since 2020`, `, once per day`, `, until further notice`, `, as well as`, `, nor`, `, whether or not`.

None of these occurs in this repository, where all seven measured additions were genuine,
and `long` never blocks.
The exclusion set is therefore widened to every word demonstrated to fire on a non-clausal use,
each pinned by a test, with the set documented as evidence-driven and open to growing again.

### Rejected: the "metadata row" class is not new

Codex reported that a bare label above a code span draws a `wrap`.
It does — and it did so before this branch,
because a lower line reading `python3` matches the old lowercase gate just as well.
Reproduced on `main`, which returns the same finding.
This is pre-existing behaviour extended consistently to markup, not a regression, and nothing is changed for it.

### Accepted: the Task 11 rubric repin was justified too narrowly

The lock reason said the clause-boundary edit touches only `long`, and no corpus unit asks a `long` question.
That is true but beside the point:
the skill is the normative rubric for *all* labeling,
and labelers judge whether an upper line ends at an allowed boundary,
which the new subordinator wording bears on directly.

`styx:internal/observeq/dispatch.go:88#wrap` is a live disagreement the new wording reaches —
one `false`, one `ambiguous`, one `true`.
No detection changes, because its upper line ends in a comma,
and no frozen status moves, because the unit carries `expected: None`.
The lock reason is corrected to say so and to flag the unit for re-adjudication.

### Deferred: commit subject lengths

All eleven subjects run 52 to 71 characters against a documented 50-character cap,
and four bodies carry a 73-character line against a 72-character cap
(`.agents/rules/600-git-conventions.md`).
The rule file records that these are enforced by convention and review rather than tooling.
Rewriting eleven messages rewrites eleven commits, so it is left for the user to call before merge.

---

## What the second review round found

The same three reviewers read the fix commit.
Every finding was reproduced before it was accepted or rejected.

### Task 11's derivation is withdrawn

Codex held that filtering the derived hint set treated symptoms rather than the mechanism,
and a second round of probes proved it:
`, because of the delay` and `, though.` draw an advisory with no clause in sight,
and both are new in this branch, where `, so far.` and `, but for` are not.
Each round removed the words it was shown and the next round found more,
which is what a list argued from counter-examples rather than from evidence does.

The user withdrew the derivation.
`BOUNDARY_HINT_RE` is its own six-word list again, exactly as it was before this work,
and the advisory message and its frozen contract revert with it.
What survives is a test that pins twelve comma-led non-clausal uses,
so the next attempt to derive this pattern fails there first,
and a roadmap entry recording that a hint list needs a per-word argument
that no labeled evidence currently supports —
the corpus asks only `wrap` and `fused` questions, never a `long` one.

This costs the drift the task set out to close:
a line breaking at `, because` draws no advisory while `, which` does.
That asymmetry is real and is now a recorded, deliberate one rather than an accident.

### A fully bolded metadata row was a new false positive

Codex found `**runtime: python3**` above `**platform: linux**` drawing a `wrap`,
and it is new in this branch.
The bold form excluded a span whose colon sits at the end, which catches `**Status:**`,
and missed the whole-row form where the colon sits inside.
A colon anywhere in a bold span now excludes it.

opencode then found the cost of that: a bold sentence containing a colon is no longer read.
That is a miss rather than an accusation,
and this project trades in that direction every time, so the exclusion stands and the comment says so.

### The CJK scope note claimed more than the code does

The skill said CJK text produces no findings.
A CJK paragraph does produce none, however it is broken,
but an unterminated CJK line above an English one draws a `wrap` anchored on the CJK line,
because the judgment is read off the English opener.
The committed test asserted exactly that while the published note denied it.
Both the skill and the README now say which is which, and a test pins both halves.

### Rejected: `and` and `but` closing an enumeration

agy filed as a P0 that a comma-led `and` closes an Oxford list rather than opening a clause.
It does — and it does so identically on `main`,
because `and` and `but` are two of the six words this pattern has always held.
The original source comment names that exact case
and chose the comma-led form as the mitigation,
so the residue is a known cost of a decision older than this plan.
The user left it in place and it is recorded in the roadmap beside the `and` deferral.

---

## What the third review round found

### A rejection from round two was wrong

Round two recorded that `Runtime` above `` `python3` `` was pre-existing behaviour.
It is not, and the disconfirmation that established it tested the wrong control:
it compared against `Runtime` above a **bare** `python3`, which the plain-word opener has always read,
rather than against `Runtime` above a **code span**, which only this branch reads.
On `main` the code-span form is silent.
Codex caught the error and it is corrected here rather than left in the record.

### Three more markup metadata rows

With the code-span case, three shapes still drew a `wrap` that `main` does not:

| Row | Why it slipped through |
|---|---|
| `**runtime：python3**` | the exclusion knew the ASCII colon and not the full-width one |
| `**status**` above `**accepted**` | no colon at all, and the tests covered only the capitalised form |
| `Runtime` above `` `python3` `` | no bold at all; the label sits on the upper line |

Six such classes have now been found across three rounds, all from this one gate,
which is the signature that withdrew the boundary-hint derivation.
The user narrowed rather than withdrew, on a distinction the two cases do not share:
this gate carries labeled evidence — three calibration units labeled `true` moved to `detected`
and no unit labeled `false` moved at all — where the hint pattern had none and could have none,
because the corpus asks no `long` question.

Two rules close all three:
a bold span is a label unless it holds a space and no colon of either width,
and a markup opener needs more than one word on the line above it,
since a lone word is a field name rather than a clause missing its object.
Every one of the six classes is silent, every genuine case still fires,
and all three corpus units still detect.

The second rule gives up a real finding:
`Requires` above a code span strands a verb exactly as `reaches` does,
and cannot be told from a field label.
That is recorded in a test rather than left to be rediscovered.

### The CJK note was still wrong, in the other direction

Round two corrected "CJK produces no findings" to cover `wrap`, and stopped there.
The `long` hint looks for `—` and `:`, which CJK writing also uses,
so an over-long Chinese line draws the advisory.
The note now separates the two sentence-reading kinds, which never fire on CJK text,
from `long`, which can, and names that a complaint about width.
opencode also caught that "blocking-capable kinds" was wrong for a second reason:
only `fused` blocks.

### A review artifact, not a defect

opencode reported an unclean working tree and a stale digest as a P0.
Both were true when it read: it was reviewing while these corrections were being written.
The sequencing was the mistake, not the code.

---

## A field report, and the trap it exposed

A user scanning their own project with v0.8.0 reported a column-wrapped godoc comment
"repaired" into a single over-long line:

```
-// loadConfig fetchs the configuration from the controller
-// at controllerURL, retrying with exponential backoff until either a fetch
-// success...
+// loadConfig fetchs the configuration from the controller at controllerURL, retrying with …
```

Every step in that chain behaved as designed, which is what made it worth fixing.

1. `wrap` fired correctly.
   `from the controller` above `at controllerURL` severs a noun from the phrase modifying it.
2. The skill says to rejoin the severed clause and re-split at sentence ends.
   There is one sentence here, so re-splitting at sentence ends yields one line of 166 characters.
3. `long` then reported **nothing**.
   Its boundary hint holds six words, and the real break in that line is `, retrying` —
   a comma-led participle no connector list was ever going to match.
4. The agent had no signal and stopped.

The defect is not the narrow word list.
It is that **withholding the advisory made silence carry two meanings**:
"this line is fine" and "this line is long and I cannot see where it breaks".
The skill already told an agent to leave a line long when it finds no boundary,
but the agent never entered that decision, because no finding ever arrived.

Measured over the 220 labeled-true `wrap` units in the calibration corpus,
simulating the rejoin the skill asks for:

| Outcome of the repair | Units |
|---|---|
| rejoined line stays under the limit | 98 |
| rejoined line is long, and the checker can advise | 64 |
| rejoined line is long, and the checker says nothing | **58** |

Roughly one repair in four ended in the silent case.

`long` now reports every over-limit line and says which case it is.
The hinted message is unchanged, byte for byte.
The new message states that no boundary was recognized,
that the word list is short rather than complete,
and that leaving the line long is the right answer when there is genuinely nowhere to break.
Both are pinned in the frozen contract.

**What this costs.**
98 more advisories across this repository, 42 of them in live prose.
Reading them, nearly all sit on a real comma-led break the six-word list cannot see —
`, folded into …`, `, no checker destination exists yet`, `, never less careful with …`.
Two consequences are worth stating plainly rather than discovering later:

- A correct line over the limit now always draws an advisory.
  `tests/fixtures/go/good_sembr.go` carried a 129-character line that did,
  so it is split at its own comma-led boundary,
  and a new `advisory_long_without_boundary.go` fixture pins the case instead.
- CJK prose draws the advisory on length alone.
  `long` counts characters and does not read the sentence,
  so this is the one kind that was never CJK-blind;
  the note in the skill and the README now says so directly.

---

## What the fourth review round found, and what it withdrew

### Task 9 is withdrawn

The markup opener produced a seventh false-positive class:
a two-word field label above a code span,
which the one-word guard added in round three does not reach.

| Round | Class |
|---|---|
| 1 | a markup-wrapped connector, and a markup-wrapped capitalised word |
| 2 | a whole-row bold label |
| 3 | a full-width colon, a colonless bold label, a bare label above a code span |
| 4 | a two-word label above a code span |

Counting words cannot close it.
`Execution time` and the genuine `As a simple example the gopls binary is in the module` both end on a lowercase content noun,
and what separates them is that one holds a verb and the other does not —
the grammar this project leaves to the judgment layer.

The gate is removed and the opener test wants a lowercase word again, as it did before this work.
The three calibration units it had moved to `detected` return to `accepted_miss`.
That recall is given up deliberately:
a writer does break before an inline link because the link reads as self-contained,
and the word governing it is stranded above.
Every shape found across the four rounds is now a parametrized test,
so a future attempt has a list to clear before it ships,
and the miss itself is pinned rather than forgotten.

### The precision invariant is amended rather than quietly broken

Codex would not pass `long` firing on length alone
while [`100-project-map.md`](../../.agents/rules/100-project-map.md) still said to skip the line when a heuristic is uncertain.
It was right that the code and the rule disagreed.

The rule now carves out one exemption and says why:
a measurement that needs no heuristic may report what it measured.
`long` counts characters, which is not a judgment about the prose.
The exemption covers a count rather than a guess, and `long` never blocks.

**One argument made for this was wrong, and is withdrawn here.**
It cited `tests/corpus/compliant/` gaining no finding,
the set whose README says every finding against it is a false positive by construction.
That is true and proves nothing:
the longest line in that corpus is 57 characters,
so no file in it can reach a limit of 120 and the exemption is never exercised there.
Codex and opencode both caught it.

What actually supports the exemption is narrower and worth stating as such.
Of 42 additions in live prose, 35 sit on a real break the six-word hint cannot see
and 7 sit on a line with nowhere to break, which is attention spent for nothing.
A correct over-long line with no boundary now draws an advisory where it drew silence,
and by the project's own definition that is a false positive —
accepted here because it never blocks, because its message says to leave such a line alone,
and because the silence it replaces was misreading a real repair loop.
The corpus offers no negative control for this, which is a gap rather than a defence.

### Four errors in the record, all mine

- **The corpus measurement was overstated.**
  It reported 69 / 79 / 72 by rejoining the two lines and stopping there,
  where the skill says to rejoin *and then re-split at sentence ends*.
  Simulating the whole repair gives 98 / 64 / 58 —
  roughly one repair in four ends in silence, not one in three.
  The direction is unchanged and the field report stands.
- **The corpus was misnamed.**
  Every unit record is from the calibration side;
  the holdout sources carry no unit records at all.
  Calling them holdout units overstated how independent the evidence was.
  Corrected in the source, the tests, the changelog, and here — twice, since the first pass missed two lines that a reviewer then found.
- **The new fixture pinned the wrong message.**
  `advisory_long_without_boundary.go` contained `, and`,
  which the hint list matches, so it exercised the hinted path its name denies.
- **The shipped descriptions still advertised the old contract.**
  The module docstring and the README both defined `long` as needing a likely clause boundary.

### One reviewer claim did not survive

opencode reported the two-word label case as pre-existing.
It is not: `Execution time` above a code span is silent on `main` and fired on the branch,
as are `OS type`, `Return value`, `Install command`, and `Runtime environment`.
Reproduced against `main` before the withdrawal.

---

## What the fifth review round found

All three reviewers returned zero P0.
Two said merge; one said fix then merge.
They converged, independently, on the same hole in the amendment,
which is the strongest signal any round of this review has produced.

### The exemption was too wide

The rule licensed "a measurement that needs no heuristic".
Each reviewer widened it in a different direction and each direction was real:

- a count of commas or of capitalised words is equally "a measurement",
  and flagging prose on one would be a guess dressed as arithmetic;
- so is a count of `raw` width,
  which this branch's own Task 4 removed after it accused correctly written text;
- and nothing in the sentence said *advisory*,
  so a future contributor could read it as licensing a **blocking** count.

The exemption now names three limits and why each exists:
advisory only, length of the extracted prose only,
and a heuristic may refine the message but never gate the report.
A finding that cannot meet all three stays under the ordinary rule.

### The evidence cited for it was non-causal

The amendment claimed support from `tests/corpus/compliant/` gaining no finding.
The longest line in that corpus is 57 characters,
so nothing in it can reach a 120-character limit and the exemption is never exercised there.
The claim was true and empty.
It is withdrawn above and replaced with what the change actually rests on,
including the admission that a correct over-long line with nowhere to break now draws an advisory,
where it drew silence before,
which by this project's definition is a false positive accepted for stated reasons.
The corpus offers no negative control for it.
That is a gap, and calling it one is more useful than the sentence it replaces.

### Five stale strings

A reviewer found each of these after the round that was supposed to have fixed them:
a source comment still saying "a third" where the corrected figure is about a quarter,
two plan lines still calling calibration units holdout units,
and two test descriptions still stating that `long` needs a boundary hint as well as length.
The corrections in the previous round were real but incomplete,
and the claim that they were complete was itself one of the things needing correction.
