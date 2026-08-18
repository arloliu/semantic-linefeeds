# ADR-0021: A withheld finding travels with the block it shares a line with

**Status:** accepted
**Date:** 2026-08-18
**Amends:** [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) —
its withdrawal of `wrap` from default hook feedback now carries one exception,
scoped to a line a blocking finding already holds.

## Context

ADR-0002 removed `wrap` from hook feedback because the labeled corpus showed it misfiring,
and advice the model has to weigh costs attention even when it never blocks.
The withdrawal protects prose the edit was not going to touch.

A line can draw both kinds at once.
Column-wrapped prose produces that shape whenever a sentence ends mid-line
and the sentence after it runs off the end of the same line:

```text
// Package cache provides caches. A cache
// holds a bounded number of entries here
// and evicts old ones.
```

`fused` reports the stop after `caches`, and `wrap` reports that `A cache` opens a sentence that continues below.
A hook delivering only the first tells the model to split at the stop.
Following that instruction alone produces a worse file than the one it was given:

```text
// Package cache provides caches.
// A cache
// holds a bounded number of entries here
// and evicts old ones.
```

The wrapped original is uniformly broken and reads as one continuous block.
The repaired version puts a line holding no whole thought into a file whose rule is one thought per line,
so a reader who trusts the rule stops at `A cache` and has to start again.
It also widens the diff for the next edit to that sentence from two lines to three.

The rate is not marginal.
Over the pinned evidence base at `930bac9`, 893 lines carry a `fused`,
and 306 of them — 34.3% — carry a `wrap` on the same line.
The repository's own recorded hook payload for a blocking edit is an instance of the shape.

Withholding costs nothing on such a line.
The edit is blocked by the `fused` whatever happens to the `wrap`,
so the attention argument that justifies the withdrawal has no work left to do there.
What withholding does buy is a repair the checker knows to be wrong.

## Decision

A withheld finding is delivered when a blocking finding is anchored on the same line.
Everywhere else the withdrawal stands unchanged.

Corroboration comes from a blocking kind only.
An advisory leaves the line standing as its author wrote it,
so a withheld finding beside one still risks sending the model at prose that was never wrong.

The judgment layer states the repair order the exception exists to enable:
when one line draws both kinds, rejoin before splitting.

The blocking report says the same thing in its own words.
A report carrying a withheld finding names it as direction for the repair rather than a second repair,
gives that order, and keeps the judgment clause every other finding gets.
No blocking report could carry the kind before this record,
so its wording spoke only to the blocking one.
Left as it stood, the kind the corpus shows misfiring would arrive under "Fix these" with nothing qualifying it,
which is the outcome the withdrawal was written to prevent.

## Consequences

- A line already blocked shows the model both findings, and the repair can carry the split-off opening down.
- The withdrawal still governs every line no blocking finding holds, which is where its evidence was gathered.
- The exception is narrow by measurement: 306 of the evidence base's 1712 `wrap` findings, 17.9%.
- `wrap` gains no ability to block, and its exit status is unchanged.
- A file audit is unaffected, because it never withheld anything.
- The repair recipe now depends on two findings arriving together,
  so a change that splits their delivery breaks the recipe rather than degrading it quietly.
- The exception prevents the bad repair rather than catching it.
  A stranded opening draws only a `wrap`, and no block corroborates that line,
  so a hook still passes the damaged file in silence.
  Catching it after the fact needs the opt-in,
  or evidence that would reopen the withdrawal itself.

## Rejected alternatives

**Leave the withdrawal absolute and fix the recipe alone.**
Rejected as insufficient on its own, though it shipped alongside this record.
The recipe cannot name the line below when the finding it is given does not describe it,
and a rule the model has to apply from memory on every `fused` is weaker than evidence in front of it.

**Fold the second finding into the first one's message text.**
Rejected because it delivers the same information while hiding that a second finding exists.
A reader of the report could not tell the exception had applied,
and the delivery matrix would no longer describe what the hook emits.

**Withdraw the withdrawal.**
Rejected because ADR-0002's evidence is unchanged for the lines it was gathered on.
`wrap` still misfires on correct prose, and 82% of its findings remain outside default feedback.
