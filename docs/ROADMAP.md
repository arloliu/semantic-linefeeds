# Roadmap

Where semantic-linefeeds is going.
Decisions and their rationale live in [`decisions/`](decisions/);
this file carries only what has not shipped yet.

When a release ships, its section moves out of here and into `CHANGELOG.md`.
The roadmap therefore only ever describes the future, and its length stays bounded.

## Governing constraints

Three constraints shape everything below, and they are not independent.

- **Precision is the prerequisite.**
  Nothing else matters while the detector accuses correct prose,
  because a user who is nagged about a correct line disables the hook,
  and the tool then has zero value.
- **Lint changes, not history.**
  Adopting the tool must never require reflowing a repository.
  This already describes the hook, and generalizing it to the CLI is most of the work ahead.
- **Diff-scoped checking is the bridge** from a personal guardrail to a repository standard.
  Without it the convention holds only for text written by an adopted agent.

A fourth is a non-goal:
more languages are the wrong next investment,
since marginal value has flattened while the workflow gap has not.

## Evidence base

Reproduce with:

```bash
git -C /path/to/cassandra-gocql-driver rev-parse HEAD   # 930bac9531fa5ba8d9535619bf20b3da1d0ffbee
cd /path/to/cassandra-gocql-driver
git ls-files '*.go' '*.md' | head -200 > /tmp/corpus.txt
xargs -a /tmp/corpus.txt python3 /path/to/semantic-linefeeds/scripts/check_linefeeds.py --json --file
```

| Measurement | Value |
|---|---|
| Files with findings | 161 of 164 |
| Total findings | 2,827 (`wrap` 1,705, `fused` 845, `long` 277) |
| `wrap` findings over Go files only | 1,440 |
| Raw end column of those `wrap` lines | median 75, 1,274 at or above 65 |

One caveat governs all of them:
**these are detector outputs, not reviewed labels.**
No precision or recall claim in this roadmap rests on a count of them.

A latency figure quoted in v2 (`git diff` at 0.65ms median over 20 runs, one machine)
is retained only as a local observation.
No decision depends on it.

## Open precision questions

Two sealed holdouts have been drawn, opened, and spent.
The three false positive classes they left behind are repaired,
and repairing them turned up a fourth that the record had folded into one of the three.
Two questions remain, and both need prose nobody has tuned against.

| Open item | Evidence | What it needs |
|---|---|---|
| `fused` recall on unseen Markdown | 25 of 47 in the second round, where the first returned 66 of 79 | the calibration side, or a third round |
| A fence is now closed only by its own mark, which releases prose the old rule skipped | one file gained 75 findings and lost 53 | a third round, which scores it first |

The `fused` question is not a defect anyone has localized, and the round that found it cannot:
its labels were deleted when the bundle was spent.
Until something localizes it, no `fused` rate may be published.

The fence repair is the only change since the last round that adds findings as well as removing them,
so it is the first thing a third holdout has to score.
What could be measured without one was:
no frozen status among the 718 labeled units moved,
and the compliant corpus is unmoved.
How a round is read when one floor clears and another does not is
[ADR-0009](decisions/0009-a-round-scores-what-the-change-could-move.md).

## Releases

Five releases to 1.0, not eight.
This is early-stage `v0.x`, so a release is a coherent theme rather than a minimal shippable unit,
and each carries many commits.

Every ordering constraint established above is preserved,
but as **commit order inside a release** rather than as a separate tag.

### v0.5 — Changed spans, suppression, and the judgment layer

The architectural release.
Commit order matters here too:
the span model lands before context-aware hooks,
and suppression lands with them rather than after,
because widening what the hook can see without an escape hatch is what makes users disable a guardrail.

- `check(text, path, spans)`, with anchor, evidence, and ownership ranges (ADR-0005).
- Provenance and degraded-mapping fallback; the snippet mode retained as that fallback.
- A versioned diagnostic schema, with text as one renderer over it.
- Real Codex line numbers; the footer emitted once per run.
- No numeric `confidence` until observed rates support one.
- Suppression, on the suppression contract, shipped together with context-aware hooks.
- The judgment layer for **every** agent, not only Claude:
  native `SKILL.md` installation for Codex with status and idempotent upgrade,
  `SNIPPET.md` carrying the judgment rules as the fallback for agents without a skill mechanism,
  and hook feedback carrying suggested diffs, per ADR-0006.

### v0.6 — Repository tooling and lifecycle

Where the kit stops being agent-only.
The packaged CLI lands before the first git mode, so no mode precedes the command that owns it.

- A packaged `semlf` artifact, on the packaging proof in ADR-0004.
- `--staged` first, against the index blob, with an index-versus-worktree test matrix;
  then `--diff` and `--changed` on the same provider contract.
- `.pre-commit-hooks.yaml`, after the staged mode has its tests.
- Project config on the shared discovery function in ADR-0004.
- `uninstall`, `doctor`, and agent auto-detection.
  Skill removal is covered by `uninstall`.
- Managed upgrade on a provenance manifest recording installed digest and version,
  so an untouched older release updates while a hand edit still refuses.
- `pipx` and `uv tool` distribution, with the zipapp retained for air-gapped and mirrored installs.
- `SEMANTIC_LINEFEEDS_CHECK` renamed to `SEMLF_*` with a deprecated alias
  (`adapters/opencode/semantic-linefeeds.ts:44`).
- `--agentsmd` refuses to default to the current directory (`scripts/install.py:186`),
  and `status()` reports against the resolved install target rather than `./AGENTS.md`
  (`scripts/install.py:239-247`).
- Windows paths and CRLF become testable here, across every adapter.

### v0.7 — Fixes and team integration

- Suggestions and the restricted automatic class from ADR-0007.
- GitHub Action, SARIF, and annotations as serializers over the diagnostic schema.
- A real-agent regression corpus.

### v1.0 — Stable contracts

These enter compatibility guarantees:
CLI surface, config schema, diagnostic schema, adapter API, suppression syntax, and exit codes.

## Suppression and operational contracts

Suppression ships **with** the release that widens hook visibility, never after it.
Its contract is specified before that release:
directive syntax, scope, nesting, malformed-state behavior, protected-context handling,
and interaction with changed spans and ownership ranges.

`uninstall` ships with the first packaged lifecycle command.
`doctor` ships before team integration,
and it replays a synthetic payload end to end rather than checking that files exist.

## Deferred, with reasons

- **Protected-span masking.**
  Masking URLs, inline code, links, and directives instead of skipping the whole line is a real improvement.
  It is a recall feature, so it follows the precision work, and it fits the v0.5 redesign.
  Entry condition: the labeled corpus must show masking creates no false positives around protected content.
- **Feedback persistence.**
  A session log of findings would show whether agents actually repaired what was reported.
  Deferred to v0.7, where the real-agent corpus needs the same data.
- **Legacy-paragraph editing recipe.**
  The skill simultaneously requires rejoining a severed clause and never reflowing stable text
  (`skills/semantic-linefeeds/SKILL.md:38`, `skills/semantic-linefeeds/SKILL.md:67-70`),
  which conflict when the severed clause continues into untouched prose.
  A concrete ordering is added when the ADR-0005 ownership ranges make "the affected two lines" precise.
- **More languages.** Marginal value has flattened.
- **Agent auto-detection for `semlf install`.**
  Useful, and cheap once the lifecycle commands exist, so it is scheduled with v0.6 rather than deferred.
- **More agent installers and an LSP.**
  A generic `--stdin --path` surface makes new adapters cheap;
  build that before adding targets one at a time.
- **A full NLP parser.** The detector's job is high-precision suspicion, not grammar.
- **An aggressive auto-formatter.** Reformat churn is the problem this project exists to avoid.
- **Inline trailing comments.** Higher parser complexity and false-positive risk for short text.
- **CJK support.**
  Adding `。！？` to the terminator sets is cheap,
  but `wrap` depends on inter-word spaces and a following capital,
  so real CJK support is larger than terminators alone.

## Positioning

> A diff-aware prose guardrail for AI coding agents and source repositories.

The README should drop its explanation of *why* models emit column-wrapped prose.
That is a hypothesis the project does not need.
The load-bearing claim is narrower and demonstrable:
agents produce non-semantic line breaks,
instructions alone do not reliably prevent it,
and a deterministic check at the tool boundary catches it.
