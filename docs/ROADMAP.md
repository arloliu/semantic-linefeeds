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

## Releases

Five releases to 1.0, not eight.
This is early-stage `v0.x`, so a release is a coherent theme rather than a minimal shippable unit,
and each carries many commits.

Every ordering constraint established above is preserved,
but as **commit order inside a release** rather than as a separate tag.
That distinction matters:
the trust repairs below reach `main` in the first commits of v0.4.1,
months before the tag, and nothing waits on the corpus work that follows them.

### v0.4.1 — Trust and precision

Two commit groups, in this order.

**Group 1 — contract repairs.**
No heuristic changes, no new design, landing first because each is active trust damage.

- Hook mode exits 2 only for `fused` or `wrap`;
  `long` prints feedback and exits 0, matching `--file`, the README, and the skill.
- **Non-blocking findings use each host's model-visible protocol.**
  `long`-only results exit 0 and emit the host JSON object on stdout,
  with `hookEventName: "PostToolUse"` and the rendered advice in `additionalContext`.
  Exit 2 with stderr is retained for `fused` or `wrap`,
  which is the behavior in force until group 2 withdraws `wrap` from default feedback.
  Without this, exit 0 hides the advice in Claude and Codex rather than unblocking it.
- **The opencode adapter surfaces advisory output on exit 0 as well.**
  It renders the advisory text rather than raw transport JSON.
  It currently appends output only at exit 2 (`adapters/opencode/semantic-linefeeds.ts:47-61`),
  so the exit-code change alone would silently delete every `long` advisory for its users.
- The renderer stops opening a `long`-only report with "Fix these"
  (`scripts/check_linefeeds.py:568-584`), which contradicts the instruction to leave such a line long.
- The module docstring, CLI help, and the authoritative exit-code text are updated together
  (`scripts/check_linefeeds.py:10-18`, `scripts/check_linefeeds.py:707-719`,
  `.agents/rules/100-project-map.md:35-39`).
- `long`-only contract tests across the Claude, Codex, and opencode paths,
  asserting the host JSON shape and model-visible content rather than subprocess stderr alone,
  plus a mixed advisory-and-blocking case that stays at exit 2 without duplicating advice.
- **Temp-directory discovery fails open.**
  `skip_path()` calls `tempfile.gettempdir()` unprotected (`scripts/check_linefeeds.py:143-159`),
  and both hook entries catch only JSON errors,
  so an unwritable temp directory makes the hook exit 1 before it checks anything.
  That breaks Principle 7.
  The failure is caught, the temp exclusion is skipped, and a deterministic test covers it.
- `--version` on the core, sourced from one embedded version constant.

**Group 2 — precision.**

- `wrap` withdrawn from default hook feedback, per §6.2.1, and retained in `--file` audits.
- Abbreviation exclusions for `fused`, derived from the active regex.
  These land **in the same commit** as the withdrawal per §6.2.2,
  with a release-level test asserting the two become visible together.
- The §6.2.3 hook-output matrix, with the `SEMLF_EXPERIMENTAL_WRAP` opt-in surface.
- Connector, clustering, and width work all drop out of the plan with the withdrawal.
- The narrow emphasis repair from §5.2.
- A paragraph break at every Markdown list item.
- The §7 labeled corpus, manifest, accepted-miss list, and gates.
- The §8 portable-core boundary recorded, and `100-project-map.md` amended.
- Fix `--file --json PATH` ordering.

Exit criterion: zero false positives across the compliant corpus for every kind still in default feedback,
no `wrap` finding reachable without the explicit opt-in,
and every mutation test failing when its exception is removed.

### v0.5 — Changed spans, suppression, and the judgment layer

The architectural release.
Commit order matters here too:
the span model lands before context-aware hooks,
and suppression lands with them rather than after,
because widening what the hook can see without an escape hatch is what makes users disable a guardrail.

- `check(text, path, spans)`, with anchor, evidence, and ownership ranges (§9).
- Provenance and degraded-mapping fallback; the snippet mode retained as that fallback.
- A versioned diagnostic schema, with text as one renderer over it.
- Real Codex line numbers; the footer emitted once per run.
- No numeric `confidence` until observed rates support one.
- Suppression, on the §11 contract, shipped together with context-aware hooks.
- The judgment layer for **every** agent, not only Claude:
  native `SKILL.md` installation for Codex with status and idempotent upgrade,
  `SNIPPET.md` carrying the judgment rules as the fallback for agents without a skill mechanism,
  and hook feedback carrying suggested diffs (§10).

### v0.6 — Repository tooling and lifecycle

Where the kit stops being agent-only.
The packaged CLI lands before the first git mode, so no mode precedes the command that owns it.

- A packaged `semlf` artifact, on the §8.1 proof.
- `--staged` first, against the index blob, with an index-versus-worktree test matrix;
  then `--diff` and `--changed` on the same provider contract.
- `.pre-commit-hooks.yaml`, after the staged mode has its tests.
- Project config on the §8.2 shared discovery function.
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

- Suggestions and the restricted automatic class from §12.
- GitHub Action, SARIF, and annotations as serializers over the v0.5 schema.
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
  A concrete ordering is added when §9 ownership ranges make "the affected two lines" precise.
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
