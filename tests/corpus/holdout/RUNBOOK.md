# Sealing the holdout

Nothing here has been run.
This file exists so the sequence is decided before anyone is in the middle of it.

## Why the order matters

The holdout tests a predicate against prose nobody tuned against.
Two things can destroy that, and both are ordering mistakes rather than technical ones:

- Labeling the holdout in a session that then tunes the predicate.
  The agent has read the prose by then.
  Nothing enforces this, and it is recorded in the manifest's protocol notes.
- Freezing the predicate after reading the holdout,
  which lets a run restate what it froze once it knows the answer.

The predicate this bundle tests is `scripts/check_linefeeds.py` as of the freeze.
Changing it afterwards changes its digest, the freeze record stops matching, and scoring is refused.

## The sequence

1. **Check out the three holdout sources** at the commits `manifest.json` pins,
   one directory per source id, under one root.
2. **Draw**: `python3 tests/corpus/holdout/draw.py <checkout-root>`.
   The draw is a function of the seed and the pinned commits, so it is reproducible rather than trusted.
3. **Label** three blind passes from three model families,
   using `batch.py`, `collect.py`, and `promote.py` exactly as the calibration side did.
   `LABELING.md` is the procedure the labelers are given, and it says nothing about what any answer costs.
4. **Adjudicate** whatever the resolution table sends to a person, with `adjudicate.py`.
5. **Seal** the labeled sample with a passphrase that is never written down.
   Losing it destroys the holdout, and that is the accepted cost of not storing it.
6. **Freeze** the predicate, the calibration manifest, and the sealed bundle in `freeze.jsonl`.

Only then may the bundle be opened, once, and the result appended against that same record.

## What the holdout is being asked

The floors are already recorded in `manifest.json`, under `reporting.recall_floors.holdout`:
0.68 for `wrap` and 0.68 for `fused`.

They were stated on 2026-08-11, before any holdout unit existed,
at the weak end of what the calibration corpus supports rather than at its point estimate.
The calibration rates were 163 of 220 and 31 of 37 when those floors were written.
