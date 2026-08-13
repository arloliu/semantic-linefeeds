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

Three sealed holdouts have been drawn, opened, and spent.
The third stated floors of 0.70 for `wrap` and 0.68 for `fused` before it was drawn,
carried no credit for the two unscored repairs it existed to score,
and cleared both:
213 of 260 and 69 of 82, each lower bound nearly seven points above its floor.
Its Markdown `fused` stratum returned 50 of 59 where the second round returned 25 of 47,
the two intervals disjoint,
so the fence repair and the markup repair generalize and a `fused` rate is publishable again.
Whether the second round's own gap was its draw or the proxy is closed as unanswerable:
its labels are gone, and the question is moot for the predicate that ships.

What remains open is smaller and named:

| Open item | Evidence | What it needs |
|---|---|---|
| Adjacent telegraphic notes in Go comments read as one severed clause | three of the third round's four false positives | ADR-0002 territory: a positive-evidence `wrap` test, or nothing |

The round's two extraction defects are repaired and off this table:
the `gofail:` directive cut and the Markdown licence-paragraph cut both landed,
scored against the pinned round-3 sources,
removing only the measured class and adding nothing.

The declined repairs stay declined with their numbers on record:
the bracket and emphasis forms of the markup class,
and the non-lowercase final word,
in the diagnosis and in
[`docs/plans/done/v0.4.2-what-the-holdout-found.md`](plans/done/v0.4.2-what-the-holdout-found.md).
How a round is read when one floor clears and another does not is
[ADR-0009](decisions/0009-a-round-scores-what-the-change-could-move.md).

## Releases

Five releases to 1.0, not eight.
This is early-stage `v0.x`, so a release is a coherent theme rather than a minimal shippable unit,
and each carries many commits.

Every ordering constraint established above is preserved,
but as **commit order inside a release** rather than as a separate tag.

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

- Hook-side mutation of the suggested replacement, gated by a content-hash check immediately before writing (ADR-0007);
  wider automatic-fix classes beyond `!`/`?`.
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
Suppression is explicit, locally scoped, and user-directed.
Repeated hook feedback neither creates a suppression nor authorizes another rewrite attempt.

`uninstall` ships with the first packaged lifecycle command.
`doctor` ships before team integration,
and it replays a synthetic payload end to end rather than checking that files exist.

## Deferred, with reasons

- **A numeric `confidence` field on diagnostics.**
  A deliberate absence carried forward from v0.5:
  no number ships until observed rates support one.
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
- **More languages.**
  Marginal value has flattened.
- **Agent auto-detection for `semlf install`.**
  Useful, and cheap once the lifecycle commands exist, so it is scheduled with v0.6 rather than deferred.
- **More agent installers and an LSP.**
  A generic `--stdin --path` surface makes new adapters cheap;
  build that before adding targets one at a time.
- **A full NLP parser.**
  The detector's job is high-precision suspicion, not grammar.
- **An aggressive auto-formatter.**
  Reformat churn is the problem this project exists to avoid.
- **Inline trailing comments.**
  Higher parser complexity and false-positive risk for short text.
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
