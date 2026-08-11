# ADR-0008: A holdout is spent by being opened, and it buys more than a rate

**Status:** accepted  
**Date:** 2026-08-11

## Context

[ADR-0003](0003-precision-measured-against-labels.md) set the protocol:
select every parameter against calibration data,
freeze the predicate with a digest,
open the holdout once,
and require a new untouched holdout for any further tuned attempt.

v0.4.1 was the first release to run that protocol to completion.
A sealed bundle of 376 boundaries was drawn from three projects the tool had never been run against,
drawn after the predicate was frozen,
labeled by three model families,
adjudicated where they disagreed,
and opened once.

This record states what that round measured, what it cost, and what it bought,
because the last of the three is the part the protocol did not predict.

## What it measured

| | calibration | holdout |
|---|---|---|
| `wrap` | 163 of 220, 74.1% | 231 of 311, 74.3% |
| `fused` | 31 of 37, 83.8% | 81 of 100, 81.0% |
| false positives | 1 of 450 | 1 of 331 |

Both floors were stated before the holdout existed, and both were met.

Recall on three unseen projects landed within 0.2 points of the corpus the repairs were tuned against.
That is the claim the whole mechanism exists to be able to make,
and it is the first time this project could make it about anything.

## What it cost

The bundle is spent.
Its three sources have been read,
and reusing them would measure memory rather than generalization,
so they are retired along with the bundle.

The cost is therefore three sources, one labeling round across three model families,
one adjudication pass by the maintainer,
and a ledger entry that cannot be replayed.
That is the price of one scored predicate,
and a predicate that changes afterwards needs the price paid again.

## What it bought, which was not a rate

Four false positive classes came out of the round,
and none of them came out of the numbers:

- code commented out inside a doc comment,
- a Markdown table row that does not begin with a pipe,
- a second licence block further down a file,
- a rule of dashes used as a divider.

Three were found while adjudicating boundaries the labelers disagreed about.
One was the holdout's single false positive.
All four are now repaired, with a fixture each and a mutation that turns a named test red.

A fifth finding was a recall hole rather than a false positive:
a line ending in inline markup is a `wrap` the detector reported once in 21 on the calibration corpus
and six times in 30 on the holdout.
Two samples drawn from different projects and labeled in different rounds agreed about it,
which is a stronger statement than either sample could make alone.

## The part that is not flattering

Not one of the four classes was found by a test in this repository.

`tests/corpus/compliant/` is adversarial and collects the failure modes this project knows about.
It cannot hold a class nobody has thought of,
and every case in it was added after something else found the class first.
A test finds the classes its author imagined.
A corpus finds the classes its material contains.

Three of the four were found by people arguing about whether a line was prose.
That is the disagreement channel doing work the assertion channel structurally cannot do,
and it was treated as label noise to be resolved rather than as a defect source to be read.

## Decision

1. **A holdout is spent by being opened.**
   The budget for a precision claim includes drawing and labeling the next one.
   The ledger enforces the ordering; nothing enforces the budgeting but this line.
2. **Adjudication output is a defect source.**
   What labelers disagreed about is read for classes, not only resolved into labels.
   A round that produces no disagreements has told you nothing about what you have not thought of.
3. **A repair that adds findings cannot be scored on the corpus it was tuned against.**
   A never-flag rule can only remove findings and ships against the corpus in hand.
   A change to a positive predicate waits for prose nobody tuned against.
4. **The session that labels a holdout is not a session that tuned the predicate.**
   The ledger binds a predicate digest and refuses to open a bundle frozen against another one,
   which stops the ordering mistake but not the memory one.

## Alternatives rejected

**Reuse the spent sources with a fresh draw.**
The three sources have been read by whoever did the repairs.
A second sample from them measures how well the repairs generalize to the rest of a studied file,
which is not the question.

**Skip the holdout and trust the calibration floors.**
The floors are a regression gate.
They say a rate has not fallen on material the predicate was fitted to,
and they say nothing at all about material it was not.
