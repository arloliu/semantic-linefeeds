# ADR-0017: `experimental-wrap` joins `.semlf.ini`, env still wins

**Status:** accepted
**Date:** 2026-08-14
**Amends:** [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) —
its opt-in-is-an-environment-variable clause held only until project configuration existed.
[ADR-0012](0012-project-config-is-one-ini-file.md) shipped that in v0.6,
and this record spends it on `wrap`'s opt-in.
**Also amends:** [ADR-0012](0012-project-config-is-one-ini-file.md) —
`.semlf.ini` gains a third key, and this one carries its own precedence order.

## Decision

`.semlf.ini`'s `[semlf]` section gains a third key, `experimental-wrap`,
alongside `long-limit` and `exclude`:

```ini
[semlf]
experimental-wrap = true
```

It accepts any spelling `configparser.getboolean` already accepts —
`1`/`0`, `yes`/`no`, `on`/`off`, `true`/`false`, case-insensitive —
the same booleans a Python-adjacent config file already asks a user to write.
An unparsable value drops the key alone,
the same fail-open rule [ADR-0012](0012-project-config-is-one-ini-file.md)
already set for `long-limit`:
a typo turns the tuning off, never the checker.

Precedence is `$SEMLF_EXPERIMENTAL_WRAP` first, then the ini key, then off.
`$SEMLF_EXPERIMENTAL_WRAP` decides outright whenever it is set to any non-empty value,
using the same `DISABLED_VALUES` it already reads.
The environment variable can therefore force `wrap` off in a repository whose `.semlf.ini` turns it on,
exactly as it can force it on in one that never opted in.
This is the opposite of `long-limit`'s and `exclude`'s ordering,
where flag beats env beats ini:
`wrap` has no flag leg to defer to,
and the env var is the one surface every CI runner
and every ad-hoc `--hook` invocation already controls without touching a committed file,
so it keeps the last word.
Discovery reuses `active_long_limit`'s path-to-directory resolution
(nearest existing ancestor,
[ADR-0013](0013-git-modes-read-snapshots-through-providers.md)'s one-policy-source rule) —
the same config a file's `long-limit` and `exclude` come from governs its `wrap` opt-in too.

## Evidence

- [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) gave the environment-variable choice one reason:
  project configuration did not exist yet.
  It exists now, so the reason for confining the opt-in to the environment is gone,
  not the opt-in-is-narrow decision itself —
  `wrap` still leaves default feedback until a predicate clears the ADR-0002 holdout bar.
- Every hook call site already carries a file path
  (`scripts/check_linefeeds.py`'s `run_hook_claude` and `run_hook_codex` both call `deliver` with one),
  so config discovery costs no new plumbing.

## Alternatives rejected

- **Ini beats env.**
  Rejected because a project's committed opt-in should never be able to force `wrap` onto a CI run
  or an interactive session that explicitly asked for it off, or the reverse —
  the environment variable is the one surface a single invocation controls without editing a file.
