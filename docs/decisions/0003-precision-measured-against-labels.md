# ADR-0003: Precision is measured against independent labels

**Status:** accepted  
**Date:** 2026-08-10

## Context

Raw detector output cannot measure the detector.
Counts drawn from current findings exclude every violation the detector already misses,
which makes recall unfalsifiable,
and a lost true positive can be masked by a new false positive while a total holds steady.

The reference corpus is `cassandra-gocql-driver` at commit `930bac9531fa5ba8d9535619bf20b3da1d0ffbee`, selected with `git ls-files '*.go' '*.md' | head -200`.
It yields 2,827 findings across 161 of 164 files.
**Those are detector outputs, not reviewed labels,**
and no precision or recall claim rests on them.

## Decision

### A positive denominator independent of the detector

Candidates generated from current detector output would exclude every violation the detector already misses,
making recall unfalsifiable.
So the known-positive corpus is built independently:
by sampling prose regardless of detector verdict, then labeling.

- Every candidate is labeled true, false, or ambiguous.
- Ambiguous cases are excluded from rates and retained as qualitative cases.
- Recall is detected true violations over the **frozen** true-violation denominator, per kind and stratum.
- Calibration and holdout sources stay separate.
- Strata for `wrap`: prose width, raw end column, indentation depth, language,
  Markdown nesting, trailing inline markup, list-item adjacency,
  paragraph line count, and eligible-anchor count.
  The last two are the dimensions any future clustering signal would move,
  so they are stratified before such a signal is considered.

### Gates

- Zero false positives on calibration and holdout.
- Per-kind, per-stratum recall floors, **frozen before the parameter grid runs**,
  as either absolute counts or a maximum permitted drop from a recorded baseline.
  A floor chosen after seeing results is not a gate.
- Every new accepted miss fails the build until a reviewer approves a manifest change,
  so the accepted-miss list bounds future losses instead of merely recording past ones.
- Exact `(line, kind)` identity assertions, extending the marker mechanism
  (`tests/conftest.py:19-32`, `tests/test_detector.py:16-21`).
- Mutation sensitivity: removing any evidence rule, connector, or abbreviation exclusion must fail a specific test,
  rather than merely moving a total.

### One-shot holdout

Selecting parameters against calibration **and** holdout would use the holdout for model selection,
so it would stop being an independent test,
and predeclaring the grid does not repair that leakage.

The protocol is therefore:

1. Select every parameter using calibration data alone.
2. Freeze the exact words, tokenization, case normalization, markup handling,
   and any corroboration rule, with a manifest digest.
3. Open the holdout once and evaluate the frozen predicate.
4. A holdout failure rejects that candidate,
   and any further tuned attempt requires a **new, untouched** holdout.

Tooling enforces this: the calibration harness cannot read the holdout
until the predicate and manifest digest are frozen.

Any signal that changes whether a diagnostic exists is a qualifier, not corroboration,
and must clear this protocol in full.

### The fixture decision, corrected

The marked `wrap` fixtures do not all sit at narrow widths.
After marker removal, the Go anchors end at 77 and 74
(`tests/fixtures/go/bad_wrapped.go:1`, `tests/fixtures/go/bad_wrapped.go:4`),
and both Markdown anchors end at 75 (`tests/fixtures/markdown/bad_wrapped.md:3-4`).
Those four are exactly the four that survive a 65-column gate;
the claim held only for the eleven that do not.

Rewriting the short fixtures in place would erase the evidence needed to audit the recall trade,
which is moving the goalposts.

Corrected decision:

- Short fixtures are **preserved**, moved to an accepted-miss manifest with their expected status.
- Realistic-width positives are **added alongside**, not substituted.
- Every labeled true violation carries a frozen detected-or-accepted-miss status.
