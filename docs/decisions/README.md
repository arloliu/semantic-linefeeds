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
| [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) | `wrap` leaves default hook feedback; three candidate predicates were refuted and none is adopted — opt-in surface amended by [ADR-0017](0017-experimental-wrap-also-lives-in-ini.md) |
| [ADR-0003](0003-precision-measured-against-labels.md) | Precision and recall are measured against independent labels, never against detector output |
| [ADR-0004](0004-portable-core-and-repository-cli.md) | The core stays one portable stdlib-only file; a separate CLI owns git, lifecycle, and rendering — lifecycle-verb parts superseded by [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) |
| [ADR-0005](0005-changed-span-analysis-and-ownership.md) | Analysis may see the whole file; reporting is restricted to diagnostics a change owns |
| [ADR-0006](0006-judgment-layer-for-every-agent.md) | Every agent receives the judgment layer, not only the one with a skill mechanism |
| [ADR-0007](0007-fixability-classes.md) | Automatic repair is restricted to `!` and `?`, and prefers handing the fix back to the agent |
| [ADR-0008](0008-a-holdout-is-spent-by-being-opened.md) | A holdout is spent by being opened; what labelers disagreed about is a defect source, not label noise |
| [ADR-0009](0009-a-round-scores-what-the-change-could-move.md) | A round scores a change against the floors that change could move, and every other floor it misses is acknowledged rather than absorbed |
| [ADR-0010](0010-suppression-is-a-stateless-single-line-directive.md) | Suppression is a stateless single-line directive, user-directed and scoped to exactly one line |
| [ADR-0011](0011-go-port-gated-on-field-evidence.md) | A Go port is deferred behind a field-evidence gate; v0.6 stays on the Python core and keeps the contract implementation-agnostic |
| [ADR-0012](0012-project-config-is-one-ini-file.md) | Project configuration is one `.semlf.ini` file, discovered by the core with flag/env/config/default precedence and a malformed file left inert |
| [ADR-0013](0013-git-modes-read-snapshots-through-providers.md) | Git modes read snapshots through providers: `--staged`/`--diff`/`--changed` each read one git enumeration, policy stays the working tree's in every mode, and `exclude` filters discovery only |
| [ADR-0014](0014-lifecycle-verbs-and-the-provenance-manifest.md) | Install, uninstall, and status stay in `scripts/install.py`; doctor and the identity module ship inside the artifact; provenance is one state file per artifact, refusal over overwrite on any trouble — verb split superseded by [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) |
| [ADR-0015](0015-distribution-channels.md) | pipx and uv install `semlf` from the repository, never PyPI automation; the wheel maps `cli/semlf` and `check_linefeeds.py` from their repo locations; the zipapp remains the air-gapped channel; one channel per machine, surfaced by three independent refusals — artifact contents, primary source, and collision story superseded by [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) |
| [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) | `semlf` is the single entry point and owns install, status, and uninstall; payloads embed through one declarative registry and publish to a neutral root; admission is the three-axis classifier; PyPI is the package channel's primary source and the zipapp stays behind the checkout door |
| [ADR-0017](0017-experimental-wrap-also-lives-in-ini.md) | `experimental-wrap` joins `.semlf.ini` beside `long-limit` and `exclude`; the environment variable still wins whenever it is set, so it can force `wrap` on or off regardless of the file |
| [ADR-0018](0018-skills-ship-per-target.md) | A skill ships once per target, to a root that target owns, and may only reference paths its own target installs; two agents that read the same directory still do not share a file in it — this completes [ADR-0006](0006-judgment-layer-for-every-agent.md) for opencode and leaves [ADR-0016](0016-one-entry-point-and-the-payload-registry.md)'s single-owner rows untouched — superseded by [ADR-0019](0019-one-skill-in-the-shared-root.md) |
| [ADR-0019](0019-one-skill-in-the-shared-root.md) | A skill is published once, to the shared root both targets already read, and semlf writes no symlink into any agent's own skills root; `checker` and `readme` become `shared` rows so one body can cite them; Codex is inferred from its hook entry for reporting, while removal takes the skills only when the request names every agent target (amended 2026-08-16; the conservative predicate that used to authorise it could not see a Codex under a non-default `CODEX_HOME`) — this supersedes [ADR-0018](0018-skills-ship-per-target.md) and amends [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) to allow a `shared` owner |
| [ADR-0020](0020-string-literal-inertness-follows-lexical-coverage.md) | String-literal content is inert only where the extractor has lexical coverage; Python multiline strings use the standard-library tokenizer, recognized docstrings remain prose, and other language profiles retain a named limitation — this narrows ADR-0010's universal wording to implemented behavior |
| [ADR-0021](0021-a-withheld-finding-travels-with-the-block-it-shares-a-line-with.md) | A withheld `wrap` is delivered when a blocking finding sits on the same line, because that line is being rewritten anyway and the `wrap` is what stops the repair stranding the sentence it splits off; an advisory does not corroborate, and every other line keeps the withdrawal — this amends [ADR-0002](0002-wrap-withdrawn-from-default-feedback.md) |

## Principles these records share

1. **Meaning before columns.**
2. **Long is better than broken**, and the enforcement path must honor that too.
3. **Check changes, not history.**
4. **Precision before recall, measured against labels rather than asserted.**
5. **Suggest before rewriting.**
6. **Suppression is an escape hatch, never a substitute for precision.**
7. **Integration failure must not break the agent.**
8. **Every agent gets the same judgment layer, not only the one with skills.**
