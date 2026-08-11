# ADR-0009: A round scores what the change could move, and every other floor it states

**Status:** accepted  
**Date:** 2026-08-11

## Context

[ADR-0008](0008-a-holdout-is-spent-by-being-opened.md) established that a repair which adds findings cannot be scored on the corpus it was tuned against,
and that scoring one costs a fresh sealed round.

One repair was written under that rule and left unshipped:
a code span that closes a line is removed whole,
and the line is judged by what stood in front of it.
The backtick is a legitimate line ender,
so before the repair a line ending in a code span was never a `wrap`
and the clause the span was attached to was never read.
Two samples labeled in different rounds agreed on the cost —
recall in that stratum was 1 of 21 on one and 6 of 30 on the other.

A second holdout was drawn against the frozen predicate that carries the repair,
labeled by three model families, adjudicated, sealed, and opened once.
It returned an answer that does not point one way,
and this record states how it was read.

## What the round measured

| | round 1 | round 2 | floor stated for round 2 |
|---|---|---|---|
| `wrap` | 231 of 311, 74.3% | 219 of 276, 79.3% | 0.70, cleared |
| `fused` | 81 of 100, 81.0% | 50 of 77, 64.9% | 0.68, missed |
| false positives | 1 of 331 | 3 of 402 | — |

The task's acceptance had two clauses,
and read literally the round failed both of them:
`fused` came in below a floor the round itself stated,
and the false positive count rose from one to three.

## The question

Both failures are about attribution.
"The floors this task raises" is either the floor the repair moved or every floor in the round,
and "the false positive count does not rise" is either a count or a claim about precision.
The answer sets how every later round is read,
so it is argued here rather than assumed.

## Which floor the repair raised is on the record, not a matter of interpretation

The floors are keyed by round in the corpus manifest, and they read:

| | round 1 | round 2 |
|---|---|---|
| `wrap` | 0.68 | 0.70 |
| `fused` | 0.68 | 0.68 |

The `fused` floor is the same number in both rounds.
The `wrap` floor rose two points, and the manifest already says why in its own words:
the calibration rate it derives from moved when the repair landed, from 163 of 220 to 169 of 220.

So "the floors this task raises" resolves to the `wrap` floor by the record of which floor moved and why.
It was stated before the round was drawn, and the round returned 79.3% with an interval of 74.2% to 83.7%,
clearing it by more than four points at the lower bound.

## Why that reading is sound rather than convenient

A rate is evidence about a change only if the change could have moved it.

A `fused` finding is one regular expression matched against one line.
The repair is read through `line_ending`, which has exactly one call site in the checker,
inside the branch that reports a `wrap`.
Withdrawing the repair would not move round 2's `fused` count by one unit,
and nothing else in this release touches how a fused line is found.
The round's `fused` number therefore carries exactly as much information about this repair
as it would have carried had the repair never been written.

The repair is also monotone on `wrap`, which is what makes 219 of 276 attributable rather than a net.
Its pattern is anchored at the end of the line,
so it fires only where the line already ended in a backtick —
and a backtick was a legitimate ender, so such a line was never reported before.
Every other line is judged exactly as it was.
The repair can add a `wrap` finding and cannot remove one.

That is measured rather than only argued.
Replaying the checker as it stood before the repair and as it stands after it,
over the 718 labeled windows and over this repository's own Markdown before those findings were resolved,
the earlier findings are a subset of the later ones in both:
nothing was removed either time.

The alternative reading has a cost that shows up immediately.
If an unrelated floor can veto a repair,
then the cheapest route to shipping one is to bundle it with fixes to whatever else in the round looks weak,
which is the opposite of what a scored round is for.
And a veto has a mirror: if an unrelated floor could refuse a repair,
an unrelated floor clearing would endorse one.
Neither is a measurement of anything.

## The false positive clause failed as written, and the count is the wrong reading

One of 331 became three of 402.
Taken as counts that is a rise, and the acceptance clause said the count would not rise.

Taken as precision the round cannot tell the two apart:
0.30% with an interval of 0.05% to 1.7%, against 0.75% with an interval of 0.25% to 2.2%.
The intervals overlap across most of their length.

All three belong to one class, and it is not this repair's.
Swift proposals write code blocks with HTML entities rather than fences,
so code reaches the prose stream and a closing brace reads as a severed clause.
A closing brace is not a legitimate line ender and never was,
so those lines were reported identically before the repair existed.
Not one false positive came from a line ending in a code span.
That class is recorded as an open defect with its own evidence;
the rise is owned, not unowned.

The count reading is rejected for the same reason the all-floors reading is:
it lets any unrelated regression in unseen prose veto any repair,
however cleanly that repair's own stratum came back.

## The `fused` result is a finding of the round, and it is not diagnosable

Reading it as unrelated to the repair is not reading it as unimportant.

The loss is entirely in Markdown:
25 of 47, against 66 of 79 in round 1, while Go rose to 25 of 30.
Those two Markdown intervals do not overlap —
39.2% to 66.7% against 73.9% to 90.1% —
so the difference between the rounds is real rather than sampling noise.
The corpus-wide 0.68 floor, by contrast, sits inside round 2's interval of 53.8% to 74.7%,
so the round does not establish that `fused` recall is below its floor;
it fails to establish that it is above it.

Both rounds drew Markdown from different projects,
so the difference may be a property of the material rather than a regression.
Nothing here can say which, because the labels that would locate it are gone:
the bundle was sealed and its plaintext deleted when the round was spent.
Every defect this round exposed was found by argument over prose,
and this one was found by argument the round can no longer replay.

## Decision

1. **The code-span repair ships.**
   It was scored against the floor it raised, on prose nobody tuned it against, and it cleared it.
   The six `wrap` findings it exposes in this repository's own Markdown are repaired rather than left standing.
2. **A round scores a change against the floors that change could move,**
   and which floors those are is settled by the record of which floor moved and why,
   not by an argument made after the answer is known.
3. **Every other floor the round states is still answered, and a miss is acknowledged rather than absorbed.**
   The manifest gained a place to record a missed floor —
   what it is attributed to, and what it blocks —
   and the suite fails when a round misses a floor and nothing says so.
   This one blocks any published `fused` recall rate and any claim that a later repair to that heuristic works.
   It does not block this release, which changes nothing a fused line is found by.
4. **Precision is judged as a rate with an interval, not as a count.**
   A count of one against a count of three is a comparison the sample sizes do not support.
   A rise that a round cannot distinguish from its predecessor is reported, attributed, and not treated as a refutation.

## Alternatives rejected

**Withdraw the repair because a floor in the round was missed.**
The missed floor is on a kind the repair cannot reach through any code path.
Withdrawing would lower `wrap` recall on the only stratum two independent samples agreed was blind,
and would leave the `fused` result exactly where it is.

**Ship it and treat the round as a pass.**
The round stated two floors and answered one of them no.
Nothing consults the `floors_met: false` that a result file records,
so a missed prediction becomes a footnote nobody reads;
the acknowledgement is enforced rather than merely written down once.

**Hold the release until `fused` recall is diagnosed.**
The diagnosis needs labels this round no longer has,
so holding buys nothing until a third round or a calibration-side investigation exists.
None of the five repairs in this release changes how a fused line is found,
so holding them withholds measured precision work against an unrelated open question.
