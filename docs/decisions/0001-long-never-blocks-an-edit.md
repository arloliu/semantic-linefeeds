# ADR-0001: `long` never blocks an edit

**Status:** accepted  
**Date:** 2026-08-10

## Context

`--file` mode excludes `long` from the exit code (`scripts/check_linefeeds.py:695`).
Hook mode does not:
both `run_hook_claude` and `run_hook_codex` exit 2 whenever *any* finding exists
(`scripts/check_linefeeds.py:601-605`, `scripts/check_linefeeds.py:671-678`).

Verified with one text of 141 characters carrying a boundary hint:
`--file` exits 0, hook exits 2.

Three contracts break at once:

- README documents `long` as advisory (`README.md:144-148`).
- The skill instructs the agent to leave such a line long (`skills/semantic-linefeeds/SKILL.md:41`).
- The hook blocks the edit anyway, so guidance and enforcement contradict each other.

No test covers `long` in hook mode, which is why this survived.
This roadmap's own drafting hit it:
an edit whose only finding was a 122-character advisory came back as a blocking error.

The exit condition is one line,
but the delivery is not:
an exit-0 hook writing to stderr is invisible to the model in both native hosts.
Claude Code sends exit-0 stderr only to its debug log,
and Codex expects model-visible non-blocking feedback as JSON on stdout, under `hookSpecificOutput.additionalContext`.
So the repair is exit 0 **plus** the host's non-blocking output protocol;
changing the status alone would delete the advice everywhere rather than unblock it.

## Decision

Hook mode exits 2 only for `fused` or `wrap`.
A `long`-only result exits 0 and delivers its advice through the host's model-visible protocol,
not through stderr.

## Consequences

- The status change alone is not enough.
  Delivered as exit 0 with stderr, the advice would vanish in both native hosts,
  so the repair is the status **and** the transport together.
- The opencode adapter appends output only at exit 2,
  so it needs the same repair or its users lose every advisory
  (`adapters/opencode/semantic-linefeeds.ts:47-61`).
- The renderer must stop opening a `long`-only report with "Fix these",
  which contradicts the instruction to leave such a line long.
- [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) narrowed the decision above.
  `fused` is now the only kind that exits 2,
  because a labeled corpus measured what `wrap` costs in false positives.
