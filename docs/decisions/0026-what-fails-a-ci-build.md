# ADR-0026: What fails a CI build

**Status:** accepted
**Date:** 2026-08-20
**Context:** v0.9c, the CI surface
([plan](../plans/done/v0.9c-ci-and-serializers.md),
three external review rounds under `tmp/`, not committed)

## Decision

A CI run gates on the rendered diagnostics, never on the checker's exit code,
and by default it fails a build on `fused` alone.

| kind | annotation | fails the build |
|---|---|---|
| `fused` | error | yes |
| `wrap` | warning | only under `fail-on: fused,wrap` |
| `long` | notice | never, and `long` in `fail-on` is refused rather than ignored |

## Why this gates on less than the CLI exits 1 on

`semlf --file` and the git modes exit 1 on any `fused` or `wrap`,
and that contract is frozen (ADR-0001 for `long`; the project map for the rest).
CI deliberately fails on less, and the inversion is not drift for two reasons.

The readers differ.
A hook message costs an agent a moment;
a red build costs a team a context switch, a re-push, and a wait.
`fused` carries the measured false-positive story
(the label corpus exists to keep it precise),
so it may spend that cost.
`wrap` was withdrawn from default hook feedback
because its precision was not measured to the same bar (ADR-0002),
and the same unmeasured risk prices a red build higher still.

The inversion lives outside the frozen contract.
The Action runs one analysis into a documents file
and everything downstream — annotations, SARIF, the gate —
is a pure function of that file.
The gate cannot read the exit code even if it wanted to be lazy:
the git modes exit 1 equally for a `wrap` the default gate passes
and for a provider failure the gate must never pass,
so the exit code does not carry the answer.
Statuses other than 0 and 1 fail the run before anything renders,
which is what keeps a broken snapshot from becoming a green build.

## The precedent, stated precisely

Default `wrap` warnings stand on the audit ADR-0002 retains:
an explicitly requested whole-file review reports `wrap`,
and a CI run is exactly such a review.
`fail-on: fused,wrap` is a separate, team-owned override
that knowingly accepts `wrap`'s unmeasured precision risk.
It claims no precedent from the hook's wrap opt-in:
ADR-0002 and ADR-0017 govern *visibility* while keeping exit 0,
which is a different policy axis from *blocking*,
and an earlier draft of this decision conflated them
until review round 1 separated the two.

## Consequences

- The Action installs the checker it shipped with
  (`pip install "$GITHUB_ACTION_PATH"`),
  so pinning the Action pins the policy and the code together,
  and no PyPI release gates the CI surface.
- `--base` reports span-owned diagnostics:
  a CI run annotates someone's pull request,
  and a finding that predates the branch is not that author's to answer.
- A team that widens `fail-on` owns the widening;
  nothing in this repository defaults to it,
  and nothing will until `wrap` precision is measured to the bar
  `fused` already meets.
