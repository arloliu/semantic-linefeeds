# ADR-0023: What a repair corpus measures, and how a widening is scored against it

**Status:** accepted
**Date:** 2026-08-18
**Relates to:** [ADR-0003](0003-precision-measured-against-labels.md),
[ADR-0007](0007-fixability-classes.md),
[ADR-0008](0008-a-holdout-is-spent-by-being-opened.md),
[ADR-0021](0021-a-withheld-finding-travels-with-a-blocking-one.md).

## Context

The existing corpus measures whether a finding is correct.
It says nothing about what happens next.

The automatic repair this project ships is deliberately narrow.
It fires only where a boundary's punctuation is `!` or `?`,
the gap is a single ASCII space,
the line holds no protected span,
and the leader and tail around the prose pass a structural whitelist.
Across the three calibration sources that is **34 boundaries out of 5,027**,
and **32 of the 34 are in one source**.

Widening it means letting the tool rewrite prose in cases it refuses today.
The question that has to be answered first is not whether the detector was right.
It is: given a finding delivered the way the hook delivers one,
what does a repairing agent do with the line, and was that right.

Nothing in this repository measured that.

## Decision

**The stratum is an exact set of withholding classes, not a class marginal.**
Class membership overlaps.
A line refused for three reasons belongs to three classes,
so a quota on one class raises the selection chance of another class's members,
and a raw marginal over such a draw is biased for the population marginal.
Exact sets are disjoint.
A stratified draw over them has known inclusion probabilities,
and a class marginal becomes a weighted derived report that is labelled as one.

**The unit is a window of one or two judged lines, not a boundary.**
The shipped repair replaces the anchor alone.
Most of the population it would be widened into carries a `wrap` as well,
which means the anchor ends mid-clause and the rejoin comes before the split
([ADR-0021](0021-a-withheld-finding-travels-with-a-blocking-one.md)).
So the window is the anchor and the line beneath it when they share a paragraph.
A finding on the last judged line of a paragraph has no line beneath it.
The one-line form exists so that those units are representable rather than dropped.

**A repair normalizes to a break vector and three validity judgments.**
The replacement is spliced into the file and re-read through the detector's own walk.
A list marker, an indent, a docstring, and a comment leader are then all decided there,
by the detector rather than by a second opinion about what a leader looks like.
What comes back is where the prose now breaks,
whether the prose is the same text,
whether every leader, tail, and suppression carrier stayed where the rule puts it,
and whether the result is still prose in one paragraph with nothing outside it changed.

The original window is a point in that space.
Leaving a line alone is therefore an answer the corpus can record.
A finding whose right answer is to change nothing is an outcome here rather than a hole.

**The acceptable set is a verdict on a generated universe.**
A label has three values and a repair does not:
a long line can break at either of two real clause boundaries,
and both results are correct prose.

Asking three passes what else they would accept improves on asking none,
but all three can omit the same valid break and agree by omission.
So the candidates are generated mechanically and the passes judge them.
A position is offered when it sits immediately after a sentence boundary,
a semicolon, a colon, an em dash, or a comma,
and also where the window already breaks.
That last source is not lexical, and it is the majority case:
an anchor that ends mid-clause breaks where no lexical rule offers a cut,
so without it the original would be missing from most of the population's universes.
No semantic test is applied.
Offering a comma that turns out to join a compound object is correct behaviour:
the passes reject it, and the rejection is data.

A pass reporting a repair the generator never offered refuses that unit.
Three-pass coverage of a universe is the only thing that makes a set complete,
so a candidate added after the coverage failed has no coverage.

**The bar is an absolute preregistered floor, not a comparison against what ships.**
The obvious construction requires a candidate class to be no worse than the shipped one.
It was rejected for three reasons.

The shipped class is 34 boundaries with 32 in one source,
so a bar derived from it is a bar derived from that source.

A lower bound compared against a lower bound is not a non-inferiority test.
It compares two one-sample intervals rather than estimating their difference,
and the arithmetic is not close.
A baseline of 10 of 10 has a Wilson-95 lower bound near 0.722,
so a candidate of 36 of 40 clears it at a lower bound of 0.769
while being ten points worse.

And the two sides would not be running the same algorithm:
today's repair replaces the anchor while a successor absorbs the line below,
which changes the repair shape and the eligibility class at once.

So the floor is **an absolute 0.80 on each activated stratum's Wilson-95 lower bound**,
taken stratum by stratum rather than pooled,
and preregistered before any repair was elicited.
A population-weighted combination is computed and reported as description
and decides nothing.
One interval over a weighted mean would need a stratified variance estimator nobody defined.
Several units can also share one window and so one outcome,
which a binomial interval would count as independent trials.

**The elicited stimulus is a blinded hook body, not complete hook feedback.**
A pass is shown the report body the checker renders,
and not the suggested-replacement block a host appends beside it.
That is a deliberate redaction, and it has a cost worth stating plainly.
The defect rates this corpus reports describe agents given less context than a real one has.
They are a floor on how well agents repair, not an estimate of it.

**The conditional is not the denominator ADR-0003 forbids.**
A denominator built from detector output is forbidden by
[ADR-0003](0003-precision-measured-against-labels.md).
Candidates drawn from current findings exclude every violation the detector already misses,
which makes the miss unfalsifiable.
That rule protects a recall claim.
The quantity here is conditional on delivery by construction:
"given that a finding reached the agent, was the repair right"
has the detector's firing in its condition rather than in its denominator,
and a finding the detector never raises has no repair to measure.
Both corpora are needed and neither substitutes for the other.

## What this does not claim

No class is admissible on what this corpus contains.
Every number in it is measured on the calibration side,
and admission is scored on a holdout round drawn after the widened predicate is frozen,
by a session that did not tune that predicate
([ADR-0008](0008-a-holdout-is-spent-by-being-opened.md)).

## Alternatives rejected

**Capture repairs from real sessions instead of eliciting them.**
Measured rather than argued.
Over 219 first-parent commits, this repository's history holds at most **10** of them.
That count over-counts.
A deleted line and an unrelated rewrite both look like a repair.
Ten over-counted events cannot score anything.
The entry condition for a capture channel is field volume, not a better argument.

**Ask the passes to propose repairs freely and take the union.**
That is the agreement-by-omission failure the generated universe exists to prevent.

**Score a widening on the calibration corpus.**
The predicate would be fitted to the prose it is scored on,
which is what the holdout discipline exists to stop.
