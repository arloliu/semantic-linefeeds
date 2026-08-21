# Round 4: the widening's holdout, run by a session that did not tune

> **Amendment, 2026-08-21: this procedure runs as round 5.**
> Round 4's freeze bound a selection whose markdown source
> (dotnet-designs, CC-BY-4.0) the licence allowlist refuses,
> and the refusal surfaced only after that sample was drawn.
> The sample was discarded unopened and never sealed or committed;
> the ledger keeps one pre-draw freeze per round,
> so the corrected selection runs as round 5 under the same predicate digest the round-4 freeze carries.
> Read every `4` below as `5`.
> The manifest's protocol note and ADR-0028 carry the full record.

**If your session tuned, wrote, or scored this predicate, stop.
You cannot run this round.**
A session that tuned has read the material its labels would score,
so its labels measure memory rather than generalization.
The v0.9b plan's Tasks 1–8 built and tuned;
if you executed any of them, or read `_fused_suggestion` to improve it,
hand this file to a fresh session and close yours.

This file is procedure over machinery that already exists and refuses on its own.
If a step refuses, the refusal is the protocol working;
read what it says rather than working around it.

## What this round decides

Whether `CANDIDATE_ADMITTED` — the period class, frozen in
`scripts/check_linefeeds.py` — may become the shipped `ADMITTED` set.
The bar is preregistered in `tests/corpus/manifest.json` under `repair_admission`:
Wilson-95 lower bound ≥ 0.80 per activated stratum, independently;
three zero-tolerance conditions at zero;
reportability floors;
one algorithm on both sides;
and no admission without this round.
Nothing below chooses a number; everything was chosen before this file existed.

## 1. Declare three new sources

Three sources, none of the twelve the manifest already declares —
neither an id nor a repository url may repeat —
with exactly one source per composition:
`self-authored`, `third-party-code`, `third-party-markdown`.

Qualify each on line-length distribution alone, before reading any prose:

```bash
python3 tests/corpus/qualify.py <repo-url-or-path>
```

Declare them in `tests/corpus/manifest.json` under `sources`, each with
`"side": "holdout"`, `"round": 4`, its `composition`, `url`, `commit`,
`license`, `selection_command`, `wrapping_column`,
and the `qualification` sentence `qualify.py` printed.
The selection validator (`repair_round_sources`) refuses a wrong count,
a duplicated composition, a missing qualification, and any reused identity —
at the freeze, before the ledger moves.

## 2. Freeze, before drawing anything

```bash
python3 tests/corpus/holdout/freeze.py 4 \
  "the v0.9b window predicate with CANDIDATE_ADMITTED={terminator_period}, \
frozen before round 4 was drawn" --repair
```

This binds the predicate digest (algorithm and candidate in one hash),
the admission contract, the class taxonomy, the draw configuration,
the validated source selection, and the scoring code (ADR-0022, ADR-0024).
Commit the ledger line before going on.

## 3. Materialize and draw

```bash
python3 tests/corpus/repairs/checkout.py --root /tmp/src --side holdout
python3 tests/corpus/repairs/draw.py /tmp/src --round 4
```

The draw refuses without the freeze,
writes `drawn_under` and every binding into `tests/corpus/repairs/round-4/sample.json`,
and refuses to run twice.

## 4. Elicit, adjudicate

```bash
python3 tests/corpus/repairs/batch.py tests/corpus/repairs/round-4
bash tests/corpus/repairs/run_round.sh 4
python3 tests/corpus/repairs/adjudicate.py worksheet \
  tests/corpus/repairs/round-4 tests/corpus/repairs/round-4/answers
```

Three blind passes answer per `REPAIRING.md`,
and referrals are adjudicated per the worksheet;
no pass and no adjudicator sees a machine suggestion.

## 5. Seal, and spend with one open

```bash
python3 tests/corpus/repairs/seal.py 4
python3 tests/corpus/repairs/score.py /tmp/src \
  --bundle tests/corpus/repairs/round-4 --json tmp/round4-result.json
```

The seal recomputes every binding, refuses whichever moved,
and removes every plaintext file, leaving only `bundle.json`.
The scorer opens once, records the spend before any plaintext escapes,
scores `candidate` and `shipped` in one process through one algorithm,
applies the admission contract clause by clause,
and appends the paired evaluation to the ledger.
A second open refuses; a crash still leaves the bundle spent.

## 6. Record, for whichever way it went

Write `repair_admission_result` into `tests/corpus/manifest.json`,
copied from the sealed evaluation:
version 1, the admitted set, round 4, the freeze id,
the evaluation (ciphertext) digest, the predicate digest as frozen,
the scoring digest exactly as the sealed result carries it
(it was computed inside the one open,
and the guard compares it against the result and the freeze's own binding —
never retype it),
every activated stratum's counts and Wilson lower bound,
the three zero-tolerance counts, the outcome, and the decision ADR.
`repair_admission_result_problems` and the ledger cross-check must both come back empty.

**If the candidate cleared:**
set `ADMITTED = CANDIDATE_ADMITTED` in `scripts/check_linefeeds.py`, citing ADR-0028;
update "Automatic suggestions" in `docs/DETECTOR_SPEC.md`;
update the README's suggested-replacement section
(it says a suggestion never fires on a period boundary);
regenerate the diagnostics golden;
key `repair_floors` to round 4.

**If the candidate was refused:**
`ADMITTED` stays empty and the README's period sentence stays as it is;
the record still lands, carrying the refusal.

**Both ways:** ADR-0028 with every number;
`CHANGELOG.md` in user-facing words;
tick the v0.9 umbrella and `docs/ROADMAP.md`;
repin `tests/corpus/manifest.lock`;
full gate (`python3 -m pytest tests/ -q` with bun on `PATH`)
and the self-hosting check over every Markdown file touched.
The two-state precision guard in `tests/test_precision.py` validates the record you wrote,
and it needs no edit.
