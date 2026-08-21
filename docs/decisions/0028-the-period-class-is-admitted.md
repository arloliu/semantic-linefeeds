# ADR-0028: The period class is admitted

**Status:** accepted
**Date:** 2026-08-21
**Context:** v0.9b Task 9, the widening's holdout
([plan](../plans/active/v0.9b-a-suggestion-that-reaches-the-line-below.md),
runbook `tests/corpus/repairs/ROUND-4.md`)
**Amends:** [ADR-0007](0007-fixability-classes.md)'s automatic class,
which shipped `!`/`?` and withheld the period

## Decision

`ADMITTED` in `scripts/check_linefeeds.py` is now `{"terminator_period"}`:
a `fused` boundary ending in a period carries the automatic two-line suggestion,
under exactly the window predicate the sealed round scored.
Nothing else about the suggestion changes —
it is still display text, and no path writes a file.

## The numbers

Sealed holdout round 5, spent 2026-08-21 in one scoring open:

- Activated stratum `terminator_period`: **34 of 35 acceptable**,
  Wilson-95 lower bound **0.8547** against the preregistered floor of **0.80**.
- 5 further units in the stratum were ambiguous and left the rate as cases,
  within the 25% reportability ceiling.
- All three zero-tolerance counts at **zero**:
  no repair failed to preserve prose,
  none changed a carrier,
  and none fired where only the original was acceptable.
- 28 other strata were drawn and scored through the same algorithm;
  in every one the candidate withheld (`fired` 0), as designed —
  admission activates one class only where every other class withholds.
- The shipped side, scored in the same process through the same algorithm,
  fired on none of the round's 1,071 judgeable units.
- Evidence chain in `tests/corpus/freeze.jsonl`:
  pre-draw freeze `sha256:d4e94736…` (predicate `431f5171…`, five binds),
  ciphertext `df7c5ea4…`, one spend, one paired evaluation.
  `repair_admission_result` in the manifest copies the sealed record,
  and the two-state precision guard validates it against the ledger.

## The round that ran, and the one that did not

The round was preregistered as round 4 and ran as round 5.
Round 4's freeze bound a source selection whose markdown source
(dotnet-designs, CC-BY-4.0) the licence allowlist refuses,
and the refusal surfaced at the test gate only after that sample was drawn.
The sample was discarded unopened:
never sealed, never scored, never committed,
and no predicate performance number was ever computed from it —
scoring happens only inside a sealed open, and none happened.
The ledger keeps one pre-draw freeze per round,
so the corrected selection —
the same unspent otx and pebble,
with tensorflow-community (Apache-2.0) replacing the refused source —
was declared and frozen as round 5 under the byte-identical predicate digest,
which the two ledger lines make checkable.
Round 4's freeze line stays in the ledger as the record of the refused attempt.

## Adjudication

Three blind passes (claude/sonnet, codex/gpt-5.6-terra, agy/gemini-3.7-flash)
answered all 1,071 judgeable units; 963 settled without a maintainer.
The 237 split referrals were adjudicated per `REPAIRING.md` against `skills/semantic-linefeeds/SKILL.md`,
with a written reason per unit in the sealed `adjudications.json`;
the 108 units where a pass reported the candidate list incomplete left the rate per ADR-0008.
Independence note: the adjudicating session's sibling family (claude)
agreed with the adjudication on only 36% of referred candidates,
against agy's 87% —
the adjudication tracked the rule's boundary classes, not the sibling's votes.

## Consequences

- `docs/DETECTOR_SPEC.md` "Automatic suggestions" and the README now state the period class ships,
  citing this ADR.
- `reporting.repair_floors` is keyed to round 5:
  `terminator_period` at 0.80,
  so a future run losing the admitted rate fails instead of passing quietly.
- The diagnostics golden gained the one suggestion the flip produces.
- A future widening (any other class) starts at a new freeze and a new round;
  nothing here pre-authorizes one.
