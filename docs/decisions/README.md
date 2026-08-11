# Decisions

Architecture decision records.
Each one states a decision that is expensive to revisit,
the evidence behind it, and the alternatives that were rejected.

An accepted record is not edited.
A decision that changes gets a new record that supersedes the old one,
so the reasoning that was true at the time stays readable.

## Why these live apart from the rules

[`.agents/rules/`](../../.agents/rules/) holds the rules an agent must follow,
and they are short because they are read on every task.
These records hold **why** those rules exist,
and they are long because they are read only when someone wants to overturn one.

If a record and a rule disagree, the rule wins until a new record supersedes it.

## The records

| Record | Decision |
|---|---|
| [ADR-0001](0001-long-never-blocks-an-edit.md) | `long` never blocks an edit, and non-blocking findings use each host's model-visible protocol |
| [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) | `wrap` leaves default hook feedback; three candidate predicates were refuted and none is adopted |
| [ADR-0003](0003-precision-measured-against-labels.md) | Precision and recall are measured against independent labels, never against detector output |
| [ADR-0004](0004-portable-core-and-repository-cli.md) | The core stays one portable stdlib-only file; a separate CLI owns git, lifecycle, and rendering |
| [ADR-0005](0005-changed-span-analysis-and-ownership.md) | Analysis may see the whole file; reporting is restricted to diagnostics a change owns |
| [ADR-0006](0006-judgment-layer-for-every-agent.md) | Every agent receives the judgment layer, not only the one with a skill mechanism |
| [ADR-0007](0007-fixability-classes.md) | Automatic repair is restricted to `!` and `?`, and prefers handing the fix back to the agent |
| [ADR-0008](0008-a-holdout-is-spent-by-being-opened.md) | A holdout is spent by being opened; what labelers disagreed about is a defect source, not label noise |

## Principles these records share

1. **Meaning before columns.**
2. **Long is better than broken**, and the enforcement path must honor that too.
3. **Check changes, not history.**
4. **Precision before recall, measured against labels rather than asserted.**
5. **Suggest before rewriting.**
6. **Suppression is an escape hatch, never a substitute for precision.**
7. **Integration failure must not break the agent.**
8. **Every agent gets the same judgment layer, not only the one with skills.**
