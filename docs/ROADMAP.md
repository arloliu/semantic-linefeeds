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

Two releases to 1.0.
This is early-stage `v0.x`, so a release is a coherent theme rather than a minimal shippable unit,
and each carries many commits.

Every ordering constraint established above is preserved,
but as **commit order inside a release** rather than as a separate tag.

The theme below kept its content while two version numbers went elsewhere.
v0.7 became the PyPI package and the install lifecycle,
and v0.8 the one shared skill both agents read;
neither was planned here, and both were worth doing first,
because a guardrail nobody can install cleanly has no team to integrate with.

### v0.9 — Fixes and team integration

- Hook-side mutation of the suggested replacement, gated by a content-hash check immediately before writing (ADR-0007);
  wider automatic-fix classes beyond `!`/`?`.
- GitHub Action, SARIF, and annotations as serializers over the diagnostic schema.
- A real-agent regression corpus.

### v1.0 — Stable contracts

These enter compatibility guarantees:
CLI surface, config schema, diagnostic schema, adapter API, suppression syntax, and exit codes.

[ADR-0011](decisions/0011-go-port-gated-on-field-evidence.md)'s Go-port gate must be settled before this tag,
in either direction, because the freeze removes the room a port would need to correct a contract it proves wrong.

## Deferred, with reasons

- **A numeric `confidence` field on diagnostics.**
  A deliberate absence carried forward from v0.5:
  no number ships until observed rates support one.
- **Go template files (`.tmpl`).**
  Invisible to the checker today, and reported from the field by go-secs.
  Support means a new extraction state machine for `{{/* ... */}}` comments amid template markup,
  which is exactly the precision risk the "more languages" non-goal prices.
  Entry condition: further field reports,
  or a labeled corpus showing the gap suppresses real findings.
- **User-scoped configuration.**
  Repository policy lives in the repository's `.semlf.ini`,
  and personal tuning already has env vars,
  so a user-level file would add a precedence layer
  and let two people see different findings in the same repo.
  Entry condition: field reports asking for machine-wide settings
  (for example a global scratch-directory exclude);
  if added, it sits below the repo config in precedence.
- **A prebuilt Go binary.**
  Deferred behind [ADR-0011](decisions/0011-go-port-gated-on-field-evidence.md)'s field-evidence gate:
  it opens only if a missing Python runtime proves to be a primary adoption blocker.
  Reviewed on 2026-08-14 and left closed — no field evidence of a missing-runtime adoption blocker —
  with the next review due before v1.0, which is also the deadline for settling it either way.
  The CLI contract stays implementation-agnostic so the option stays cheap to exercise.
- **An `--all` flag for `uninstall`.**
  Removing the shared skills takes `semlf uninstall codex opencode`,
  which asks the user to name a target they may never have installed.
  A flag would say the same thing more directly,
  and it was declined because naming the targets needs no new command surface to learn or to keep correct.
  Entry condition: users report the two-target form as a papercut,
  rather than one being predicted here.
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

The load-bearing claim is narrower than an explanation of *why* models emit column-wrapped prose,
and deliberately so:
agents produce non-semantic line breaks,
instructions alone do not reliably prevent it,
and a deterministic check at the tool boundary catches it.
Each of those is demonstrable;
the mechanism behind the first is a hypothesis the project does not need,
and the README no longer offers one.
