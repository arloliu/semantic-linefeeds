# Sealing a holdout round

One directory per round, one bundle per directory, one evaluation per bundle.
`round-1/` is spent.

This file exists so the sequence is decided before anyone is in the middle of it.

## Why the order matters

The holdout tests a predicate against prose nobody tuned against.
Two things can destroy that, and both are ordering mistakes rather than technical ones:

- Labeling the holdout in a session that then tunes the predicate.
  The agent has read the prose by then.
  Nothing enforces this, and it is recorded in the manifest's protocol notes.
- Freezing the predicate after reading the holdout,
  which lets a run restate what it froze once it knows the answer.

The predicate a round tests is `scripts/check_linefeeds.py` as of the freeze.
Changing it afterwards changes its digest, the freeze record stops matching, and scoring is refused.

The first round kept that order by hand.
The second one is kept by the tooling:
`draw.py` refuses to draw and `seal.py` refuses to seal
while the ledger holds no freeze naming the predicate in front of it.

## The sequence

1. **Freeze the predicate**: `python3 tests/corpus/holdout/freeze.py <round> "<why this predicate, now>"`,
   and commit the ledger line before anything is drawn.
   The record names a predicate digest and nothing that has been read yet.
   Committing it first is what records the order in `git log`,
   where a reviewer can check it,
   rather than in the memory of whoever ran the scripts.
2. **Check out the round's sources** at the commits `manifest.json` pins,
   one directory per source id, under one root.
3. **Draw**: `python3 tests/corpus/holdout/draw.py <checkout-root> <round>`.
   The draw is a function of the seed and the pinned commits, so it is reproducible rather than trusted.
4. **Label** three blind passes from three model families,
   using `batch.py`, `collect.py`, and `promote.py` exactly as the calibration side did.
   `LABELING.md` is the procedure the labelers are given, and it says nothing about what any answer costs.
5. **Adjudicate** whatever the resolution table sends to a person, with `adjudicate.py`.
6. **State the floors** for this round in `manifest.json`,
   under `reporting.recall_floors.holdout`, from the calibration rates as they stand.
   `seal.py` refuses a round whose floors are unstated,
   because a floor stated after the labels are in hand is not a prediction.
7. **Seal**: `python3 tests/corpus/holdout/seal.py <round>`,
   with a passphrase that is never written down.
   Losing it destroys the round, and that is the accepted cost of not storing it.
   Sealing binds the ciphertext to the predicate frozen at step 1 and deletes the plaintext.

Only then may the bundle be opened, once,
with `python3 tests/corpus/holdout/evaluate.py <round>`,
and the result appended against that same record.

## What round 1 asked, and what it got

Its floors were 0.68 for `wrap` and 0.68 for `fused`,
stated on 2026-08-11 before any holdout unit existed,
at the weak end of what the calibration corpus supported rather than at its point estimate.
The calibration rates were 163 of 220 and 31 of 37 when those floors were written.

It returned 231 of 311 and 81 of 100, one false positive in 331 labeled non-violations,
and one blind spot both samples agree on.
[ADR-0008](../../../docs/decisions/0008-a-holdout-is-spent-by-being-opened.md) records what that cost and bought.
