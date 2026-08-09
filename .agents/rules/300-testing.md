# 300 - Testing

Apply before adding or changing tests or fixtures.

## Commands

```bash
python3 -m pytest tests/ -q                      # full suite; run before every commit
python3 -m pytest tests/ -q --update-golden      # refresh extraction goldens, then eyeball the diff
bun test adapters/opencode/                      # opencode plugin unit tests
```

A task is not done with red tests.
The bun suite may skip where bun is absent,
but a release requires a green run.

## Detector Fixtures (`tests/fixtures/<lang>/`)

- A fixture name declares intent: `bad_*`, `good_*`, or `advisory_*`.
- Inline markers assert findings:
  ` {fused}`, ` {wrap}`, or ` {long}` appended to a line asserts one finding of that kind on that line;
  markers are stripped before checking.
- `good_*` fixtures carry zero markers (test-enforced).
- A `wrap` finding is reported on the line that ends mid-clause (the upper line).
- Fixtures need not compile;
  they exercise the regex extractor,
  so ignore compiler or IDE diagnostics about them.

## Extraction Goldens (`tests/extractor/`)

Vale-style pairs: `in/N.<ext>` → `out/N.json` with the extracted prose lines.
Mint with `--update-golden`,
then eyeball the golden against the input before committing —
a golden refreshed blindly pins a bug as expected behavior.

## Payload Fixtures (`tests/payloads/`)

Recorded hook payloads replayed through the CLI by `tests/test_cli.py`.
They are contract artifacts authored from the agents' documented schemas;
if a live agent's real payload diverges,
capture the real payload (sanitized), replace the fixture, and re-run the suite.

## Test Intent

Tests must encode why behavior matters, not just what happens.
A test that cannot fail when the guarded behavior regresses is wrong;
prefer fixtures placed so a state leak or reset bug is observable,
not masked by a neighboring code path.
