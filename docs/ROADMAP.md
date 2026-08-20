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
| A word that is both a subordinator and a preposition | a correct break before `after the request finishes` is called a `wrap`, while three labeled column wraps land on the prepositional use (`4 LE bytes right` / `after it`) | A signal that separates a clause opener from a preposition. `CONNECTORS` cannot: one entry admits both uses, which is why `before` and `after` are the two subordinators left out of the set. |

The citation-abbreviation item is closed by admitting `al.` to the exclusion list.
The same spelling can end a sentence,
but the precision rule prefers that bounded missed finding over a blocking false positive on ordinary citations.

The round's two extraction defects are repaired and off this table:
the `gofail:` directive cut and the Markdown licence-paragraph cut both landed,
scored against the pinned round-3 sources,
removing only the measured class and adding nothing.

The declined repairs stay declined with their numbers on record:
the bracket and emphasis forms of the markup class,
and the non-lowercase final word,
in the diagnosis and in [`docs/plans/done/v0.4.2-what-the-holdout-found.md`](plans/done/v0.4.2-what-the-holdout-found.md).
How a round is read when one floor clears and another does not is [ADR-0009](decisions/0009-a-round-scores-what-the-change-could-move.md).

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
  Entry condition: a suggestion must be able to reach the line below the one it replaces.
  Its shape today is a two-line replacement for the anchor line alone,
  and over the pinned evidence base a third of all `fused` lines carry a `wrap` as well,
  so widening the class without widening the shape would write that many stranded openings into files unattended.
- GitHub Action, SARIF, and annotations as serializers over the diagnostic schema. **Done.**
- A real-agent regression corpus.

### v1.0 — Stable contracts

These enter compatibility guarantees:
CLI surface, config schema, diagnostic schema, adapter API, suppression syntax, and exit codes.

[ADR-0011](decisions/0011-go-port-gated-on-field-evidence.md)'s Go-port gate must be settled before this tag,
in either direction, because the freeze removes the room a port would need to correct a contract it proves wrong.

## Deferred, with reasons

- **A numeric `confidence` field on diagnostics.**
  Holdout rounds now report rates, so the original "no number until observed rates support one" gate is crossed.
  What still blocks it is that those are corpus-stratum rates,
  and a per-finding number is a different claim the evidence does not support.
  Entry condition: a per-finding calibration, not another stratum rate.
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
  Measured and deferred.
  Across 219 commits, this repository's own history holds at most ten such repairs,
  and that is an over-count.
  A log cannot reach a population worth scoring at that rate,
  so the repair corpus elicits its population instead.
  Entry condition: enough repairs happening in the field to score a change against,
  rather than an argument that a log would be useful.
- **Testing whether an `and` joins two independent clauses.**
  `CONNECTORS` exempts every lower line opening with `and`,
  while the skill calls a compound-object `and` a mistake to avoid,
  so the one break the skill warns about hardest is the one the detector cannot catch.
  Closing it needs a subject-and-verb test on both halves,
  which is the grammar this project leaves to the judgment layer.
  The exemption is doing real precision work and stays;
  what is recorded here is that its unconditional form is a choice, not an oversight.
  The same test is what `BOUNDARY_HINT_RE` would need before it could hold more than six words.
  That pattern was once derived from `CONNECTORS`, and the derivation was withdrawn:
  a word there withholds a finding while a word in the hint pattern raises one,
  so the safe direction's tolerance leaked into the unsafe one,
  and filtering the result never converged —
  two review rounds each produced fresh comma-led forms that open no clause
  (`, since 2020`, `, once per day`, `, because of the delay`, `, though.`).
  A hint list has to be argued word by word from the uses a word has,
  and no labeled evidence exists to argue from,
  because the corpus asks only `wrap` and `fused` questions.
  The pattern's comma-led form still admits the enumeration a list closes on
  (`filters, hooks, and selectors`),
  which is a known cost of a choice older than any of this.
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
  Full-width terminators are now recognized as line enders,
  so mixed prose is no longer accused at the language boundary —
  but no kind analyzes CJK text, and the README says so.
  Real support is a per-kind redesign rather than a terminator set:
  `fused` needs a CJK token alternative and a no-space opener rule,
  `wrap` needs an end-of-clause decision for a language without inter-word spaces,
  and `long` needs a CJK boundary hint and a width that counts double-width glyphs.
  Entry condition: field reports from a CJK-writing user, or a labeled CJK corpus.

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
