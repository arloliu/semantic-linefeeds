# ADR-0027: A suggestion replaces a window

**Status:** accepted
**Date:** 2026-08-20
**Context:** v0.9b, the suggestion shape
([plan](../plans/active/v0.9b-a-suggestion-that-reaches-the-line-below.md),
three external review rounds under `tmp/`, not committed)
**Amends:** the 2026-08-13 amendment of
[ADR-0007](0007-fixability-classes.md)

## Decision

A delivered suggestion may describe a two-raw-line replacement.
ADR-0007's amendment defined it as one break replacing one space on one source line,
prefix repeated, and nothing else;
what changes here is the window the suggestion may describe,
and nothing about how it is delivered:
it is still display text in hook feedback, and no path writes a file.

Five parts, each load-bearing.

**The window trigger is the detector's own `wrap` pairing.**
The suggestion absorbs the line below on the detector's own pairing only:
a `wrap` anchored on the fused finding's line, with no directive suppressing it there.
The wrap finder and the suggestion consult one shared predicate, `_wrap_paired`,
so no second definition of "the sentence continues" can drift from the first.
A suppressed `wrap` means the user blessed the break,
and the suggestion falls back to the one-line form rather than overriding a directive.

**The absorbed shape is rejoin-then-one-split: two lines in, two lines out.**
The second replacement line carries the split-off sentence rejoined with the lower prose,
one space standing where the anchor's trailing whitespace and terminator were.
No word changes, and nothing else moves.
On the repair corpus's joined window,
this is a one-cut break vector at a position the frozen candidate universe already enumerates,
so the delivered repair is always expressible in the instrument that scores it.

**A paired window with an unsafe lower line gets no suggestion at all.**
A one-line split there would repair half the sentence,
and a wrong repair is not a smaller right one.
The lower line's safety is judged by the same whitelists the anchor answers to,
each failure under its own `below_` withholding class.

**The schema says what a suggestion replaces.**
`suggestion` carries `replaces`, always present,
counting the raw lines the replacement covers, starting at the finding's line.
That changes what `lines` means, which is a breaking change to the document,
so `DIAGNOSTIC_SCHEMA_VERSION` is 2.
SARIF, annotations, and the CI gate never read a suggestion,
proven byte-identical either way.

**The taxonomy grew ten classes, once, before anything froze against it.**
Eight `below_` classes name the ways a paired lower line can be unsafe:
`below_terminator`, `below_boundary`, `below_open`, `below_protected_span`,
`below_prose_not_unique`, `below_prefix_mismatch`, `below_tail_rejected`,
`below_carrier_stripped`.
Two anchor classes came out of the calibration dry-run,
each from a repair the passes rejected:
`anchor_open` (the anchor's first word is lowercase,
so the split would strand a fragment that continues something above —
rejoin before you split, as a refusal)
and `anchor_unclosed` (nothing absorbed the anchor's ending
and that ending is not a place a line may end,
so the split's second line would strand an open fragment).
ADR-0024 binds this taxonomy into round 4's freeze;
extending it later would break a stratum a round was drawn on.

## Consequences

- Over the pinned calibration measurement,
  the exact set a period widening activates is 299 boundaries,
  and the shipped class is 11 of its former 34 —
  the other 23 were suggestions that would have repaired half a sentence,
  and this record is where they are withdrawn.
- The candidate constants `ADMITTED` and `CANDIDATE_ADMITTED` live in the core,
  so a pre-draw freeze's predicate digest binds the algorithm and the candidate in one hash.
- Whether periods join the shipped class is round 4's to answer,
  against the preregistered bar, by a session that did not tune
  (`tests/corpus/repairs/ROUND-4.md`);
  the decision will be ADR-0028, and no shipped surface admits a class before it.
