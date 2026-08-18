# ADR-0024: A repair round binds more than its predicate

**Status:** accepted
**Date:** 2026-08-18
**Amends:** [ADR-0022](0022-a-pre-draw-freeze-binds-a-round-and-a-sample.md) —
its "What this does not claim" section names four things a round depends on
that the pre-draw record did not bind.
This record binds them, for the rounds that depend on them.

## Context

ADR-0022 closed the hole where a pre-draw freeze named a predicate and nothing else.
A record now names its round, carries an id,
and the sample records the id it was drawn under.

That record said plainly what it did not claim.
The pre-draw record still binds only a predicate and a manifest,
and a round is also decided by its reporting rules, its source selection,
and its draw configuration.
It named the entry condition for closing that gap:
the first round whose meaning depends on one of them.

The repair round is that round.
Its meaning depends on four things beyond the predicate:

- the **admission contract**, which says what a candidate class must clear;
- the **class taxonomy**, which says what the strata are;
- the **draw configuration**, which says how many units each stratum gives up;
- and the **source selection**, which says which files the population comes from.

The admission contract is the sharpest of the four.
It lives in two places, `manifest.json` and an in-code constant,
and they are compared so that one moving is a failure.
That comparison catches one copy moving.
It catches nothing once both move together while a round is underway,
which is exactly the moment a losing candidate has a reason to lower a floor.

## Decision

**A round binds what it says it binds, and nothing more.**
`freeze_predicate` takes an optional map of named digests.
A labeling round passes none, because it reads none of these four;
binding them anyway would refuse a labeling seal over a contract that round never read.
A repair round passes all four.

**The seal recomputes them and refuses a mismatch.**
The draw copies what the freeze recorded into the sample,
the seal recomputes each digest from the tree as it stands,
and all three must agree.
A binding named by one side and not the other is a mismatch too:
a round frozen against three things cannot be sealed against four.

**The source selection is bound by its own digest, not the manifest's.**
`require_predicate_freeze` deliberately does not compare the manifest digest,
because a sample is drawn before its floors are stated
and the manifest is expected to move between the freeze and the seal.
A digest over the whole file would put that back.
What is bound is a list of each source's id, side, commit, and selection command,
so a new label moves nothing and a new commit moves everything.

**The draw configuration has one copy.**
It lives in the harness rather than in the script that runs the draw,
because a freeze that binds one copy and a draw that obeys another binds nothing.

**Records written before this change stay readable.**
A record's id is the digest of its own content without its id,
computed over the keys that are present,
so a record carrying no bindings still validates.
A protocol repair that made an existing ledger unreadable would not be a repair.

## What this does not claim

The reporting rules are still not bound by the pre-draw record.
They are bound by the bundle freeze, which is written at sealing time,
and a round's floors are stated between the draw and the seal by design.
Binding them earlier would require stating them before the prose exists,
which is a change to when floors are chosen rather than to how they are recorded.

## Alternatives rejected

**Bind all four on every round.**
A labeling round does not read the admission contract,
and refusing its seal because that contract moved would be a refusal with no meaning.
A mechanism that refuses for reasons unrelated to the round is one operators learn to bypass.

**Bind the manifest file instead of the source block.**
The manifest moves between a freeze and a seal by design.
Binding it would make every round refuse, which is the same as binding nothing.

**Compare the two copies of the contract harder.**
There is no comparison between two copies that survives both of them moving.
Only a digest recorded before the prose existed distinguishes that case,
which is what this record adds.
