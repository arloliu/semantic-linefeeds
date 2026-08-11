# Labeling procedure

This file is procedure, not rule.

The normative source for what counts as a violation is
[`skills/semantic-linefeeds/SKILL.md`](../../skills/semantic-linefeeds/SKILL.md),
pinned by digest in [`manifest.json`](manifest.json).
Judge every unit against that file.
If this one seems to contradict it, that file wins and this one is wrong.

## What a labeler sees

One unit is a boundary: an upper line, the lower line adjacent to it, and the paragraph they sit in.
Nothing else travels with it.

You will not see the detector's verdict, and you will not see another labeler's answers.
That is the point.
A label taken from detector output cannot measure the detector,
and three passes that read each other stop being three passes.

Units arrive in an order randomized for you, in bounded batches.
Order is randomized so that fatigue and drift do not line up across labelers.

## Two questions per unit

Answer both, every time.

1. **Is this boundary a violation?**
   Does the upper line end somewhere the rule says a line must not end?
2. **Is the upper line a violation on its own?**
   Does it hold more than one sentence?

Both questions take the same three answers.

## The three answers

**true** — the rule is broken here, and you could say which part of the rule.
Not this: a line you suspect is wrong but cannot trace to the rule is `ambiguous`, not `true`.

**false** — the rule is not broken here, and you could say why the line is allowed to end where it does.
Not this: prose you would have written differently, which the rule still permits, is `false` and not a complaint.

**ambiguous** — you have read the rule and it does not settle this line.
Not this: a case the rule does settle against your taste is `true` or `false`, whichever the rule says.

Reach for `ambiguous` when the rule's terms do not reach the case,
when the sentence has two readings and the break is right under one and wrong under the other,
or when deciding would need something the unit does not carry, such as what a name refers to.

These three are peers.
None of them is the safe answer and none of them is the answer that costs something,
so pick the one that is true of the line in front of you.
You are being asked what you think, not asked to guess what a reviewer wants.

## Non-English prose

Label it the same way, against the same rule.
Sentence boundaries and clause boundaries are what the rule turns on,
and both exist outside English.

Answer `ambiguous` only if you cannot read the language well enough to find its sentence boundaries.
Do not answer `ambiguous` merely because the prose is not English.

## Lines that never become candidates

A unit whose upper line falls in one of the never-break classes is not a candidate,
and its presence in a batch is a sampling defect to report rather than a line to label.

Those classes are named in `SKILL.md`:
URLs, compiler and lint directives, generated-file headers, code inside indented examples, table rows,
javadoc, JSDoc and doxygen tag lines, licence headers,
fenced code and `<pre>` blocks inside doc comments, doctest lines,
and Markdown link reference definitions.

Report these; do not label them.
A never-break line labeled `false` reads as evidence the detector was right to stay silent,
when the truth is that the line should never have been sampled.

## What happens to your answers

Two other passes judge the same units without seeing yours, and a maintainer reads the disagreements.

How the three are combined is deliberately not written here.
A labeler who knows which answer survives a disagreement answers a different question than this one.
