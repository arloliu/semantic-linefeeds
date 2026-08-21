# ADR-0030: v1.0 freezes eight contracts

**Status:** accepted
**Date:** 2026-08-21
**Context:** the v1.0.0 release
([plan](../plans/done/v1.0-stable-contracts.md))

## Decision

From v1.0.0, eight surfaces carry a compatibility guarantee under semantic versioning:
a breaking change to any of them costs a major version,
and an additive change costs a minor one.
Each surface names its canonical statement — where a consumer reads what is promised —
and the pins that turn an accidental break into a red test.

| Surface | Canonical statement | Pinned by |
|---|---|---|
| CLI surface | `semlf` usage text; README (modes and exit codes) | `tests/test_cli.py` (the portable core's own command line), `tests/test_semlf_cli.py` (the `semlf` command) |
| Config schema | README `.semlf.ini` section; `DETECTOR_SPEC.md` configuration | `tests/test_config.py` |
| Diagnostic schema | `DIAGNOSTIC_SCHEMA_VERSION = 2`; `DETECTOR_SPEC.md` field table | schema tests, `tests/test_diagnostics_golden.py`, `tests/test_frozen_contract.py`'s structural half |
| Adapter API | `DETECTOR_SPEC.md` public entry points; hook payload handling | payload replay tests, the bun suite |
| Suppression syntax | README suppression section; `DETECTOR_SPEC.md` | suppression fixtures |
| Exit codes | README exit-codes section (the matrix) | return-code assertions across `tests/test_cli.py`, `tests/test_semlf_cli.py`, `tests/test_git_modes.py`, and `tests/test_hook_delivery.py` |
| CI integration | `action.yml` inputs and output; ADR-0026's gate semantics; SARIF and annotation shapes | `tests/test_action_contract.py`, `tests/test_ci_gate.py`, `tests/test_render.py`'s exact-shape pins |
| Distribution identity | `pyproject.toml`; `.pre-commit-hooks.yaml`; `.claude-plugin/plugin.json` | `tests/test_packaging.py::test_the_distribution_identifiers_are_pinned` |

## What breaking and additive mean, per surface

Additive is defined per surface rather than by one slogan:

- **Diagnostic schema:** a new optional field is minor.
  A new `kind` is **major**:
  the kind set is closed, and the bundled renderers index fixed maps by it
  and raise on an unknown value,
  so a new kind would break every consumer that has not first learned to tolerate it.
  A newly required field, a removed field, or a changed field meaning is major.
- **CLI surface:** a new flag or mode is minor;
  a removed, renamed, or repurposed one is major.
- **Config schema:** a new key with a default is minor;
  a changed meaning or default of an existing key is major.
- **CI integration:** a new Action input with a default and a new output are minor;
  a changed input meaning, a changed default,
  or a changed gate mapping from a produced kind to a build result is major.
- **Suppression syntax:** a new directive form is minor;
  a changed meaning of an existing one is major.
- **Exit codes:** a new code for a new condition is minor;
  a changed meaning of an existing code is major.
- **Adapter API:** follows the diagnostic rules,
  since its entry points return the frozen shapes.
- **Distribution identity:** has no additive form —
  its changes are renames and floor raises, and both are major.

## What is not frozen

- **Detector judgment.**
  Which lines draw findings may change in any release;
  precision work continues under the holdout discipline.
  The freeze covers the shape findings arrive in
  and the mapping from a produced kind to the configured gate result,
  not the findings themselves.
- **Message and excerpt wording.**
  `message` is display text and may change in any release;
  `excerpt` carries source-derived content and was never fixable text.
  What stays stable for SARIF and annotation consumers is structure:
  rule identifiers (the three kinds), levels, and field placement.
  `tests/test_frozen_contract.py` keeps exact-byte assertions on wording
  as deliberate characterization — updateable, never a compatibility claim.
- **Experimental keys.**
  `experimental-wrap`, as env var and ini key, is named experimental
  and sits outside the guarantee.
- **The install lifecycle's file layout.**
  What `install` writes where is versioned by the manifest and repairable by `doctor`;
  the identifiers a user types or pins are the contract, the layout is not.

## Consequences

- The Go-port gate had to settle first, and did ([ADR-0029](0029-the-go-port-gate-closes-at-v1.md)):
  after this freeze, no implementation — port or otherwise —
  can adjust a contract it proves wrong for less than a major version.
- The audit that preceded this record returned one outcome per surface,
  and every gap it named is closed in the same release:

  | Surface | Audit outcome |
  |---|---|
  | CLI surface | documentation gap — `--hook` and `--version` were undocumented in README; closed by the exit-codes section |
  | Config schema | clean |
  | Diagnostic schema | documentation drift — the spec lacked `diagnose`'s `withholding` parameter and the `withheld_by` field, and called `message` frozen; all three corrected |
  | Adapter API | documentation drift — the entry-points table lacked the current `diagnose` signature; corrected |
  | Suppression syntax | clean |
  | Exit codes | documentation gap — no consolidated statement existed; closed by the README matrix |
  | CI integration | contract defect — the `fail-on` documentation and error message understated the accepted grammar; both now state it, pinned by boundary tests |
  | Distribution identity | missing pins — the package name and plugin name had no test; both pinned |
- `wrap` remaining withheld from default hook feedback (ADR-0002, ADR-0017)
  is judgment, not schema, and stays free to change with evidence.
