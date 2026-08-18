# ADR-0022: A pre-draw freeze binds a round and the sample drawn under it

**Status:** accepted
**Date:** 2026-08-18
**Amended:** 2026-08-18 by
[ADR-0024](0024-a-repair-round-binds-more-than-its-predicate.md),
which binds the four things the "What this does not claim" section below leaves unbound,
for the rounds whose meaning depends on them.
**Amends:** [ADR-0008](0008-a-holdout-is-spent-by-being-opened.md) —
its fourth decision says the ledger "stops the ordering mistake".
The bundle freeze does.
The pre-draw record, which is the one that carries the prediction, did not,
and this record says what was missing and what now closes it.

## Context

The holdout protocol writes two kinds of ledger record.

A **bundle freeze** is written at sealing time.
It binds a predicate digest, a manifest digest, and the ciphertext digest of the bundle,
and `_require_freeze` checks all three before a bundle opens.
That record is tight, and nothing here changes it.

A **pre-draw freeze** is written before the prose exists.
It is the record that makes a holdout a prediction rather than a description:
a bundle freeze can only be written once the bundle exists,
by which time the predicate has had every opportunity to be fitted to the prose it will be scored on.

The pre-draw record named a predicate digest, a manifest digest, and an intent.
It named no round, and nothing tied it to the sample that was drawn after it.
`require_predicate_freeze` accepted any earlier record naming the current predicate.

Two consequences followed, and neither was refused by any tooling.

**A freeze for one round authorized every round.**
Round 3's commitment would stand in for round 4's whenever the predicate had not moved.

**A predicate could be tuned after the draw and committed to afterwards.**
Freeze A.
Draw the prose and label it.
Read it, and tune the predicate to B.
Append a pre-draw freeze for B.
Seal against B, which the seal permits because a record naming B now exists.
The bundle that results looks correctly sealed, and its bundle freeze is internally consistent,
because nothing anywhere recorded that the prose had been drawn under A.

That is the ordering the entire protocol exists to enforce.
It was being kept by the operator's care,
and ADR-0008 already says that care is not a mechanism.

## Decision

**A pre-draw freeze names the round it is for.**
A record with no round authorizes nothing,
because a record that names no round would otherwise authorize all of them.

**A round is frozen once.**
A second pre-draw freeze for a round is refused.
The second one is the record written after the prose has been read.

**The sample records the freeze it was drawn under.**
The draw writes that record's id into `sample.json`,
and the seal answers to that record rather than to any record naming the current predicate.
A seal whose sample names no freeze is refused,
and so is one naming a record the ledger does not hold.

**Rounds 1 to 3 stand as written, and the pre-draw path refuses them.**
Accepted records are never edited.
Their pre-draw records name no round, and round 1 wrote none at all.
They are therefore not honoured for drawing or sealing,
which is also the right answer on its own terms:
ADR-0008 retires a round's sources once the round has been opened,
and all three are spent.

**Opening and scoring the sealed bundles is untouched.**
Both answer to the bundle freeze, which binds a ciphertext rather than a round.
A test asserts each of the three bundles still resolves its own freeze record,
because a protocol repair that invalidates the evidence already gathered is not a repair.

## What this does not claim

The pre-draw record still binds only a predicate and a manifest.
A round is also decided by the reporting rules, the source selection, and the draw configuration,
and any of those can move between the freeze and the seal without this mechanism noticing.
Binding them is worth doing and is not done here.
The entry condition is the first round whose meaning depends on one of them,
which is the repair round the v0.9d plan describes.

## Alternatives rejected

**Rewrite the legacy records to carry a round.**
The ledger is append-only, and a rewritten line is exactly what the ledger exists to prevent:
it would let a run restate what it froze after reading the holdout.

**Bind the sample by its content digest instead of a record id.**
A sample is drawn deterministically from a seed,
so a content digest would be reproducible by anyone who could rerun the draw,
which is the property that makes it useless as evidence of when it was drawn.
The id names a ledger line that existed first.

**Leave it, and rely on the commit order in `git`.**
A reviewer can see that a freeze landed after a sample.
That is the same social check the protocol already declined to depend on,
and it fails silently when nobody looks.
